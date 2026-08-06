from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, unique_strings, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .project_events import project_events
from .paths import ForgePaths
from .state import load_settings

GUARDRAIL_SCHEMA = 1
GUARDRAIL_MODE = "atomic-change-set"
EVENT_GUARDRAIL_MODE = "event-obligation"
GUARDRAIL_MODES = {GUARDRAIL_MODE, EVENT_GUARDRAIL_MODE}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required_string(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Guardrail contract requires {label}.")
    return text


def _required_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Guardrail contract requires {label} as an array.")
    rows = unique_strings(value)
    if not rows:
        raise ValueError(f"Guardrail contract requires at least one {label} entry.")
    return rows


def _contract_fingerprint(contract: dict[str, Any]) -> str:
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_path(project_root: Path, forge_root: Path, raw_path: str | Path) -> tuple[Path, str]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError("Guardrail contracts must be regular project files outside .forge.")
    if _inside(path, forge_root):
        raise ValueError("Guardrail contracts cannot come from the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Guardrail contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def validate_guardrail_contract(
    project_root: Path,
    forge_root: Path,
    contract_path: str | Path,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source_path(project_root, forge_root.resolve(), contract_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Guardrail contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != GUARDRAIL_SCHEMA:
        raise ValueError("Guardrail contract must be an object using schema 1.")

    guardrail_id = _required_string(raw.get("guardrail_id"), "guardrail_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in guardrail_id):
        raise ValueError("guardrail_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    title = _required_string(raw.get("title"), "title", minimum=8)
    authority = _required_string(raw.get("authority"), "authority")
    rationale = _required_string(raw.get("rationale"), "rationale", minimum=20)
    verification_boundary = _required_string(raw.get("verification_boundary"), "verification_boundary", minimum=20)
    mode = str(raw.get("mode", "")).strip()
    if mode not in GUARDRAIL_MODES:
        raise ValueError(f"Guardrail contract mode must be one of: {', '.join(sorted(GUARDRAIL_MODES))}.")

    evidence_paths = _required_string_list(raw.get("evidence_paths"), "evidence_paths")
    normalized_evidence: list[str] = []
    for item in evidence_paths:
        candidate = (project_root / item).resolve()
        if not _inside(candidate, project_root) or _inside(candidate, project_root / ".forge"):
            raise ValueError(f"Guardrail evidence path is outside the project or inside .forge: {item}")
        if _inside(candidate, forge_root):
            raise ValueError(f"Guardrail evidence cannot point into the Forge distribution: {item}")
        if not candidate.exists():
            raise ValueError(f"Guardrail evidence path does not exist: {item}")
        normalized_evidence.append(normalize_rel(candidate.relative_to(project_root)))

    surfaces_raw = raw.get("required_surfaces" if mode == GUARDRAIL_MODE else "blocks")
    minimum_surfaces = 2 if mode == GUARDRAIL_MODE else 1
    label = "required_surfaces" if mode == GUARDRAIL_MODE else "blocks"
    if not isinstance(surfaces_raw, list) or len(surfaces_raw) < minimum_surfaces:
        raise ValueError(f"Guardrail contract requires at least {minimum_surfaces} {label} entr{'y' if minimum_surfaces == 1 else 'ies'}.")
    surfaces: list[dict[str, Any]] = []
    surface_ids: set[str] = set()
    all_patterns: list[str] = []
    for index, item in enumerate(surfaces_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{label} entry {index} must be an object.")
        surface_id = _required_string(item.get("id"), f"{label}[{index}].id")
        if surface_id in surface_ids:
            raise ValueError(f"Duplicate guardrail surface id: {surface_id}")
        surface_ids.add(surface_id)
        description = _required_string(item.get("description"), f"{label}[{index}].description", minimum=8)
        patterns = _required_string_list(item.get("path_patterns"), f"{label}[{index}].path_patterns")
        normalized_patterns = [normalize_rel(pattern.lstrip("/")) for pattern in patterns]
        if any(pattern.startswith("../") or pattern == ".." for pattern in normalized_patterns):
            raise ValueError("Guardrail path patterns cannot escape the project root.")
        all_patterns.extend(normalized_patterns)
        surfaces.append({"id": surface_id, "description": description, "path_patterns": normalized_patterns})

    contract: dict[str, Any] = {
        "schema": GUARDRAIL_SCHEMA,
        "guardrail_id": guardrail_id,
        "title": title,
        "authority": authority,
        "rationale": rationale,
        "mode": mode,
        "evidence_paths": normalized_evidence,
        "required_surfaces": surfaces,
        "verification_boundary": verification_boundary,
    }
    if mode == GUARDRAIL_MODE:
        unsafe_partial_state = _required_string(raw.get("unsafe_partial_state"), "unsafe_partial_state", minimum=20)
        trigger_paths = raw.get("trigger_paths")
        trigger_patterns = (
            [normalize_rel(item.lstrip("/")) for item in _required_string_list(trigger_paths, "trigger_paths")]
            if trigger_paths is not None else unique_strings(all_patterns)
        )
        if any(pattern.startswith("../") or pattern == ".." for pattern in trigger_patterns):
            raise ValueError("Guardrail trigger patterns cannot escape the project root.")
        contract.update({
            "trigger_paths": trigger_patterns,
            "unsafe_partial_state": unsafe_partial_state,
        })
    else:
        closes_at = raw.get("closes_at")
        if not isinstance(closes_at, dict):
            raise ValueError("Event obligation requires closes_at as an object.")
        event_id = _required_string(closes_at.get("event_id"), "closes_at.event_id")
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in event_id):
            raise ValueError("closes_at.event_id may contain only lowercase letters, numbers, hyphens, and underscores.")
        event_description = _required_string(closes_at.get("description"), "closes_at.description", minimum=12)
        unsafe_after_close = _required_string(raw.get("unsafe_after_close"), "unsafe_after_close", minimum=20)
        contract.update({
            "closes_at": {"event_id": event_id, "description": event_description},
            "unsafe_after_close": unsafe_after_close,
            "trigger_paths": unique_strings(all_patterns),
        })

    return {
        "contract": contract,
        "source": relative,
        "fingerprint": _contract_fingerprint(contract),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _record_status(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(
        project_root, record,
        changed_status="rerecord-required",
        missing_reason="The project-owned guardrail contract source is missing.",
        changed_reason="The project-owned guardrail contract changed after authority recorded it.",
    )


def guardrail_records(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root.resolve())
    raw = settings.get("guardrails", {}) if isinstance(settings, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {
        guardrail_id: _record_status(project_root.resolve(), record)
        for guardrail_id, record in raw.items()
        if isinstance(record, dict)
    }


def record_guardrail(
    project_root: Path,
    forge_root: Path,
    contract_path: str | Path,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_guardrail_contract(project_root, forge_root, contract_path)
    contract = validated["contract"]
    guardrail_id = contract["guardrail_id"]
    settings = load_settings(project_root)
    rows = settings.get("guardrails", {})
    if not isinstance(rows, dict):
        rows = {}
    record = {
        "status": "active",
        "guardrail_id": guardrail_id,
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    rows[guardrail_id] = record
    settings["guardrails"] = rows
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "guardrail-recorded", {
        "guardrail_id": guardrail_id,
        "title": contract["title"],
        "authority": contract["authority"],
        "rationale": contract["rationale"],
        "mode": contract["mode"],
        "contract_source": validated["source"],
        "contract_fingerprint": validated["fingerprint"],
        "evidence_paths": contract["evidence_paths"],
        "required_surfaces": contract["required_surfaces"],
        "unsafe_partial_state": contract.get("unsafe_partial_state", contract.get("unsafe_after_close", "")),
        "closes_at": contract.get("closes_at", {}),
        "verification_boundary": contract["verification_boundary"],
    }, source=contract["authority"])
    record["event_id"] = event["id"]
    rows[guardrail_id] = record
    settings["guardrails"] = rows
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_guardrail(project_root: Path, guardrail_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    project_root = project_root.resolve()
    guardrail_id = _required_string(guardrail_id, "guardrail_id")
    reason = _required_string(reason, "retirement reason", minimum=12)
    authority = _required_string(authority, "retirement authority")
    settings = load_settings(project_root)
    rows = settings.get("guardrails", {})
    if not isinstance(rows, dict) or guardrail_id not in rows:
        raise ValueError(f"Guardrail is not active or recorded: {guardrail_id}")
    previous = rows[guardrail_id] if isinstance(rows[guardrail_id], dict) else {}
    record = dict(previous)
    record.update({
        "status": "retired",
        "retired_utc": utc_now(),
        "retirement_reason": reason,
        "retirement_authority": authority,
    })
    rows[guardrail_id] = record
    settings["guardrails"] = rows
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "guardrail-retired", {
        "guardrail_id": guardrail_id,
        "reason": reason,
        "authority": authority,
        "previous_contract_fingerprint": previous.get("contract_fingerprint", ""),
    }, source=authority)
    record["event_id"] = event["id"]
    return record


def _matches(path: str, pattern: str) -> bool:
    normalized = normalize_rel(path)
    pattern = normalize_rel(pattern)
    if fnmatch.fnmatchcase(normalized, pattern):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return normalized == prefix or normalized.startswith(prefix + "/")
    return False


def evaluate_guardrails(project_root: Path, changed_paths: list[str]) -> dict[str, Any]:
    changed = unique_strings(normalize_rel(item) for item in changed_paths)
    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    active_count = 0
    confirmed_events = project_events(project_root)

    for guardrail_id, record in sorted(guardrail_records(project_root).items()):
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        if record.get("status") == "retired":
            continue
        active_count += 1
        mode = str(contract.get("mode", GUARDRAIL_MODE))
        trigger_patterns = contract.get("trigger_paths", []) if isinstance(contract.get("trigger_paths"), list) else []
        source = str(record.get("contract_source", ""))
        triggered_paths = [path for path in changed if any(_matches(path, pattern) for pattern in trigger_patterns)]
        source_changed = bool(source and source in changed)
        event_id = str(contract.get("closes_at", {}).get("event_id", "")) if isinstance(contract.get("closes_at"), dict) else ""
        event_record = confirmed_events.get(event_id, {}) if event_id else {}
        event_closed = bool(event_record and event_record.get("status") == "confirmed")
        lifecycle_triggered = bool(triggered_paths or source_changed or (mode == EVENT_GUARDRAIL_MODE and event_closed))

        if record.get("status") != "active":
            evaluation = {
                "guardrail_id": guardrail_id,
                "title": contract.get("title", guardrail_id),
                "status": "BLOCKED" if lifecycle_triggered else "ATTENTION",
                "reason": record.get("reason", "The guardrail must be recorded again."),
                "triggered_paths": triggered_paths,
                "contract_source": source,
                "mode": mode,
            }
            evaluations.append(evaluation)
            if lifecycle_triggered:
                findings.append({
                    "check": "core.guardrail-current",
                    "severity": "blocker",
                    "path": source or ".",
                    "line": 0,
                    "message": f"Guardrail {guardrail_id} is not current: {evaluation['reason']}",
                })
            continue

        if mode == EVENT_GUARDRAIL_MODE and not event_closed:
            evaluations.append({
                "guardrail_id": guardrail_id,
                "title": contract.get("title", guardrail_id),
                "status": "WAITING_FOR_EVENT",
                "mode": mode,
                "event_id": event_id,
                "event_description": contract.get("closes_at", {}).get("description", ""),
                "triggered_paths": [],
                "touched_surfaces": [],
                "missing_surfaces": [],
                "contract_source": source,
                "verification_boundary": contract.get("verification_boundary", ""),
            })
            continue

        if mode == GUARDRAIL_MODE and not triggered_paths:
            evaluations.append({
                "guardrail_id": guardrail_id,
                "title": contract.get("title", guardrail_id),
                "status": "NOT_APPLICABLE",
                "mode": mode,
                "triggered_paths": [],
                "touched_surfaces": [],
                "missing_surfaces": [],
                "contract_source": source,
                "verification_boundary": contract.get("verification_boundary", ""),
            })
            continue

        touched: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for surface in contract.get("required_surfaces", []):
            if not isinstance(surface, dict):
                continue
            patterns = surface.get("path_patterns", []) if isinstance(surface.get("path_patterns"), list) else []
            matches = [path for path in changed if any(_matches(path, pattern) for pattern in patterns)]
            row = {
                "id": surface.get("id", ""),
                "description": surface.get("description", ""),
                "matching_paths": matches,
            }
            (touched if matches else missing).append(row)

        if mode == EVENT_GUARDRAIL_MODE:
            status = "FAIL" if missing else "AUTHORITY_REVIEW_REQUIRED"
            unsafe = contract.get("unsafe_after_close", "")
            evaluation = {
                "guardrail_id": guardrail_id,
                "title": contract.get("title", guardrail_id),
                "status": status,
                "mode": mode,
                "authority": contract.get("authority", ""),
                "event_id": event_id,
                "event_confirmed_utc": event_record.get("confirmed_utc", ""),
                "event_evidence": event_record.get("evidence_path", ""),
                "triggered_paths": triggered_paths,
                "touched_surfaces": touched,
                "missing_surfaces": missing,
                "unsafe_after_close": unsafe,
                "verification_boundary": contract.get("verification_boundary", ""),
                "contract_source": source,
                "event_ledger_id": event_record.get("ledger_event_id", ""),
            }
            evaluations.append(evaluation)
            if missing:
                missing_text = ", ".join(str(item.get("id", "")) for item in missing)
                message = (
                    f"Guardrail {guardrail_id} free-change window closed at event {event_id}. "
                    f"Missing obligated surface(s): {missing_text}. Unsafe after closure: {unsafe}"
                )
            else:
                message = (
                    f"Guardrail {guardrail_id} has change coverage for every declared obligation after event {event_id}, "
                    "but project authority must review the result and retire or replace the guardrail before Check can pass."
                )
            findings.append({
                "check": "core.event-obligation",
                "severity": "blocker",
                "path": triggered_paths[0] if triggered_paths else source or ".",
                "line": 0,
                "message": message,
            })
            continue

        status = "PASS" if not missing else "FAIL"
        evaluation = {
            "guardrail_id": guardrail_id,
            "title": contract.get("title", guardrail_id),
            "status": status,
            "mode": mode,
            "authority": contract.get("authority", ""),
            "triggered_paths": triggered_paths,
            "touched_surfaces": touched,
            "missing_surfaces": missing,
            "unsafe_partial_state": contract.get("unsafe_partial_state", ""),
            "unsafe_after_close": contract.get("unsafe_after_close", ""),
            "event_id": contract.get("closes_at", {}).get("event_id", "") if isinstance(contract.get("closes_at"), dict) else "",
            "event_description": contract.get("closes_at", {}).get("description", "") if isinstance(contract.get("closes_at"), dict) else "",
            "verification_boundary": contract.get("verification_boundary", ""),
            "contract_source": source,
            "event_id": record.get("event_id", ""),
        }
        evaluations.append(evaluation)
        if missing:
            missing_text = ", ".join(str(item.get("id", "")) for item in missing)
            findings.append({
                "check": "core.atomic-guardrail",
                "severity": "blocker",
                "path": triggered_paths[0] if triggered_paths else ".",
                "line": 0,
                "message": (
                    f"Guardrail {guardrail_id} requires one atomic change set. Missing required surface(s): {missing_text}. "
                    f"Unsafe partial state: {contract.get('unsafe_partial_state', '')}"
                ),
            })

    return {
        "schema": 2,
        "active_count": active_count,
        "evaluated_count": len(evaluations),
        "triggered_count": sum(1 for item in evaluations if item.get("status") not in {"NOT_APPLICABLE", "ATTENTION", "WAITING_FOR_EVENT"}),
        "status": "FAIL" if findings else "PASS",
        "evaluations": evaluations,
        "findings": findings,
        "truth_boundary": (
            "A passing atomic guardrail means every declared required surface appears in the canonical observed change set. "
            "An event obligation remains blocking after its closing event until project authority reviews and retires or replaces it. "
            "A passing result does not prove feature correctness, migration safety, public behavior, or release readiness."
        ),
    }


def guardrail_summary(project_root: Path) -> dict[str, Any]:
    active: list[dict[str, Any]] = []
    attention: list[dict[str, Any]] = []
    retired: list[dict[str, Any]] = []
    for guardrail_id, record in sorted(guardrail_records(project_root).items()):
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        row = {
            "guardrail_id": guardrail_id,
            "title": contract.get("title", guardrail_id),
            "status": record.get("status", "unknown"),
            "mode": contract.get("mode", ""),
            "authority": contract.get("authority", ""),
            "contract_source": record.get("contract_source", ""),
            "required_surfaces": [
                {"id": item.get("id", ""), "description": item.get("description", "")}
                for item in contract.get("required_surfaces", []) if isinstance(item, dict)
            ],
            "unsafe_partial_state": contract.get("unsafe_partial_state", ""),
            "unsafe_after_close": contract.get("unsafe_after_close", ""),
            "event_id": contract.get("closes_at", {}).get("event_id", "") if isinstance(contract.get("closes_at"), dict) else "",
            "event_description": contract.get("closes_at", {}).get("description", "") if isinstance(contract.get("closes_at"), dict) else "",
            "verification_boundary": contract.get("verification_boundary", ""),
            "reason": record.get("reason", ""),
        }
        if row["status"] == "active":
            active.append(row)
        elif row["status"] == "retired":
            retired.append(row)
        else:
            attention.append(row)
    return {
        "schema": 1,
        "active": active,
        "attention": attention,
        "retired_count": len(retired),
        "truth_boundary": (
            "Guardrails are authority-recorded project rules. Forge does not infer or activate them from prose alone; event obligations remain dormant until an authority-confirmed project event closes their temporary window."
        ),
    }

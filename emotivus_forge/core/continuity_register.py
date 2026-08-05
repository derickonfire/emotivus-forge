from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, read_json, read_jsonl, sha256_file, utc_now, write_json
from .ledger import record_event
from .paths import ForgePaths
from .state import load_settings

CONTINUITY_REGISTER_SCHEMA = 1
TRUST_LEVELS = (
    "automatically-extracted",
    "agent-inferred",
    "developer-recorded",
    "project-evidenced",
    "owner-declared",
)
TRUST_RANK = {name: index for index, name in enumerate(TRUST_LEVELS)}
GAP_PRIORITIES = ("low", "medium", "high", "blocker")
GAP_STATUSES = ("open", "resolved")
BLOCKING_SCOPES = ("resume", "check", "ship", "deployment", "release", "roadmap")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Continuity register requires {label}.")
    return text


def _project_file(project_root: Path, forge_root: Path, raw_path: str | Path, label: str) -> tuple[Path, str]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError(f"{label} must be a regular project file outside .forge.")
    if _inside(path, forge_root):
        raise ValueError(f"{label} cannot come from the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _ledger_event_ids(project_root: Path) -> set[str]:
    return {str(row.get("id", "")) for row in read_jsonl(ForgePaths(project_root).ledger) if isinstance(row, dict)}


def _support_rows(
    project_root: Path,
    forge_root: Path,
    raw: Any,
    *,
    fact_key: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"Continuity fact {fact_key} requires at least one support reference.")
    rows: list[dict[str, Any]] = []
    controls: dict[str, dict[str, Any]] = {}
    event_ids = _ledger_event_ids(project_root)
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Continuity fact {fact_key} support {index} must be an object.")
        kind = _required(item.get("kind"), f"facts.{fact_key}.support[{index}].kind")
        if kind == "project-file":
            path, relative = _project_file(project_root, forge_root, _required(item.get("path"), f"facts.{fact_key}.support[{index}].path"), "Continuity support")
            digest = sha256_file(path)
            byte_length = path.stat().st_size
            declared_digest = str(item.get("sha256", "")).strip()
            declared_bytes = item.get("bytes")
            if declared_digest and declared_digest != digest:
                raise ValueError(f"Continuity support {relative} SHA-256 does not match its current bytes.")
            if declared_bytes is not None and int(declared_bytes) != byte_length:
                raise ValueError(f"Continuity support {relative} byte length does not match its current bytes.")
            row = {
                "kind": kind,
                "path": relative,
                "sha256": digest,
                "bytes": byte_length,
                "locator": str(item.get("locator", "")).strip(),
                "note": str(item.get("note", "")).strip(),
            }
            controls[relative] = {"sha256": digest, "bytes": byte_length}
        elif kind == "ledger-event":
            event_id = _required(item.get("event_id"), f"facts.{fact_key}.support[{index}].event_id")
            if event_id not in event_ids:
                raise ValueError(f"Continuity fact {fact_key} references unknown Ledger event {event_id}.")
            row = {"kind": kind, "event_id": event_id, "note": str(item.get("note", "")).strip()}
        elif kind == "contract-declaration":
            row = {
                "kind": kind,
                "note": _required(item.get("note"), f"facts.{fact_key}.support[{index}].note", minimum=8),
            }
        else:
            raise ValueError(f"Continuity fact {fact_key} support kind must be project-file, ledger-event, or contract-declaration.")
        if row not in rows:
            rows.append(row)
    return rows, controls


def _normalize_facts(project_root: Path, forge_root: Path, raw: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(raw, list):
        raise ValueError("Continuity register facts must be an array.")
    rows: list[dict[str, Any]] = []
    controls: dict[str, dict[str, Any]] = {}
    keys: set[str] = set()
    ids: set[str] = set()
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Continuity fact {index} must be an object.")
        fact_id = _required(item.get("fact_id"), f"facts[{index}].fact_id")
        key = _required(item.get("key"), f"facts[{index}].key")
        if fact_id in ids:
            raise ValueError(f"Duplicate continuity fact_id: {fact_id}")
        if key in keys:
            raise ValueError(f"Duplicate active continuity fact key: {key}")
        ids.add(fact_id); keys.add(key)
        if "value" not in item or item.get("value") in (None, "", []):
            raise ValueError(f"Continuity fact {key} requires a non-empty value.")
        trust = str(item.get("trust", "")).strip().lower()
        if trust not in TRUST_LEVELS:
            raise ValueError(f"Continuity fact {key} trust must be one of: {', '.join(TRUST_LEVELS)}")
        support, support_controls = _support_rows(project_root, forge_root, item.get("support"), fact_key=key)
        kinds = {row["kind"] for row in support}
        if trust == "project-evidenced" and "project-file" not in kinds:
            raise ValueError(f"Project-evidenced continuity fact {key} requires project-file support.")
        if trust == "owner-declared" and not ({"contract-declaration", "ledger-event"} & kinds):
            raise ValueError(f"Owner-declared continuity fact {key} requires a contract declaration or Ledger event.")
        rationale = _required(item.get("rationale"), f"facts.{key}.rationale", minimum=10)
        truth_boundary = _required(item.get("truth_boundary"), f"facts.{key}.truth_boundary", minimum=20)
        row = {
            "fact_id": fact_id,
            "key": key,
            "value": item.get("value"),
            "trust": trust,
            "trust_rank": TRUST_RANK[trust],
            "rationale": rationale,
            "impact": str(item.get("impact", "")).strip(),
            "change_reason": str(item.get("change_reason", "")).strip(),
            "support": support,
            "truth_boundary": truth_boundary,
        }
        rows.append(row)
        controls.update(support_controls)
    return rows, controls


def _normalize_gap_evidence(project_root: Path, forge_root: Path, raw: Any, gap_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if raw in (None, []):
        return [], {}
    return _support_rows(project_root, forge_root, raw, fact_key=f"gap:{gap_id}")


def _normalize_gaps(project_root: Path, forge_root: Path, raw: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(raw, list):
        raise ValueError("Continuity register gaps must be an array.")
    rows: list[dict[str, Any]] = []
    controls: dict[str, dict[str, Any]] = {}
    ids: set[str] = set()
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Continuity gap {index} must be an object.")
        gap_id = _required(item.get("gap_id"), f"gaps[{index}].gap_id")
        if gap_id in ids:
            raise ValueError(f"Duplicate continuity gap_id: {gap_id}")
        ids.add(gap_id)
        priority = str(item.get("priority", "medium")).strip().lower()
        if priority not in GAP_PRIORITIES:
            raise ValueError(f"Continuity gap {gap_id} priority must be one of: {', '.join(GAP_PRIORITIES)}")
        status = str(item.get("status", "open")).strip().lower()
        if status not in GAP_STATUSES:
            raise ValueError(f"Continuity gap {gap_id} status must be open or resolved.")
        blocking = item.get("blocking_scopes", [])
        if not isinstance(blocking, list):
            raise ValueError(f"Continuity gap {gap_id} blocking_scopes must be an array.")
        scopes = sorted({str(value).strip().lower() for value in blocking if str(value).strip()})
        invalid = [value for value in scopes if value not in BLOCKING_SCOPES]
        if invalid:
            raise ValueError(f"Continuity gap {gap_id} has unsupported blocking scope(s): {', '.join(invalid)}")
        evidence, evidence_controls = _normalize_gap_evidence(project_root, forge_root, item.get("evidence"), gap_id)
        resolution = str(item.get("resolution", "")).strip()
        if status == "resolved" and (len(resolution) < 10 or not evidence):
            raise ValueError(f"Resolved continuity gap {gap_id} requires a resolution and evidence.")
        row = {
            "gap_id": gap_id,
            "question": _required(item.get("question"), f"gaps.{gap_id}.question", minimum=10),
            "priority": priority,
            "status": status,
            "blocking_scopes": scopes,
            "required_evidence": _required(item.get("required_evidence"), f"gaps.{gap_id}.required_evidence", minimum=10),
            "owner": str(item.get("owner", "")).strip(),
            "resolution": resolution,
            "evidence": evidence,
            "truth_boundary": _required(item.get("truth_boundary"), f"gaps.{gap_id}.truth_boundary", minimum=20),
        }
        rows.append(row)
        controls.update(evidence_controls)
    return rows, controls


def _active_record(settings: dict[str, Any]) -> dict[str, Any]:
    active_id = str(settings.get("active_continuity_register_id", "")).strip()
    registers = settings.get("continuity_registers", {}) if isinstance(settings.get("continuity_registers"), dict) else {}
    record = registers.get(active_id, {}) if active_id else {}
    return record if isinstance(record, dict) else {}


def _validate_supersession(settings: dict[str, Any], register: dict[str, Any]) -> None:
    previous_record = _active_record(settings)
    if not previous_record or previous_record.get("status") != "active":
        if register.get("supersedes_register_id"):
            raise ValueError("Continuity register cannot supersede a register that is not active.")
        return
    previous = previous_record.get("register", {}) if isinstance(previous_record.get("register"), dict) else {}
    previous_id = str(previous.get("register_id", ""))
    if register.get("supersedes_register_id") != previous_id:
        raise ValueError(f"A new continuity register must explicitly supersede active register {previous_id}.")
    if len(str(register.get("change_reason", "")).strip()) < 10:
        raise ValueError("A superseding continuity register requires a durable change_reason.")
    old_facts = {str(item.get("key", "")): item for item in previous.get("facts", []) if isinstance(item, dict)}
    new_facts = {str(item.get("key", "")): item for item in register.get("facts", []) if isinstance(item, dict)}
    retired = set(register.get("retired_fact_keys", []))
    for key, old in old_facts.items():
        if key not in new_facts:
            if key not in retired:
                raise ValueError(f"Continuity fact {key} was omitted without explicit retirement.")
            continue
        new = new_facts[key]
        if old.get("value") != new.get("value"):
            if int(new.get("trust_rank", -1)) < int(old.get("trust_rank", -1)):
                raise ValueError(f"Continuity fact {key} cannot be changed by a lower-trust source.")
            if len(str(new.get("change_reason", "")).strip()) < 10:
                raise ValueError(f"Changed continuity fact {key} requires change_reason.")
    old_open_gaps = {
        str(item.get("gap_id", "")) for item in previous.get("gaps", [])
        if isinstance(item, dict) and item.get("status") == "open"
    }
    new_gap_ids = {str(item.get("gap_id", "")) for item in register.get("gaps", []) if isinstance(item, dict)}
    retired_gaps = set(register.get("retired_gap_ids", []))
    missing_gaps = old_open_gaps - new_gap_ids - retired_gaps
    if missing_gaps:
        raise ValueError(f"Open continuity gap(s) omitted without resolution or retirement: {', '.join(sorted(missing_gaps))}")


def validate_continuity_register(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve(); forge_root = forge_root.resolve()
    source, relative = _project_file(project_root, forge_root, source_path, "Continuity register")
    raw = read_json(source, None, strict=False)
    if not isinstance(raw, dict) or raw.get("schema") != CONTINUITY_REGISTER_SCHEMA:
        raise ValueError("Continuity register must be valid UTF-8 JSON using schema 1.")
    facts, fact_controls = _normalize_facts(project_root, forge_root, raw.get("facts", []))
    gaps, gap_controls = _normalize_gaps(project_root, forge_root, raw.get("gaps", []))
    retired_fact_keys = sorted({str(value).strip() for value in raw.get("retired_fact_keys", []) if str(value).strip()}) if isinstance(raw.get("retired_fact_keys", []), list) else []
    retired_gap_ids = sorted({str(value).strip() for value in raw.get("retired_gap_ids", []) if str(value).strip()}) if isinstance(raw.get("retired_gap_ids", []), list) else []
    register = {
        "schema": 1,
        "register_id": _required(raw.get("register_id"), "register_id"),
        "authority": _required(raw.get("authority"), "authority"),
        "supersedes_register_id": str(raw.get("supersedes_register_id", "")).strip(),
        "change_reason": str(raw.get("change_reason", "")).strip(),
        "facts": facts,
        "gaps": gaps,
        "retired_fact_keys": retired_fact_keys,
        "retired_gap_ids": retired_gap_ids,
        "truth_boundary": _required(raw.get("truth_boundary"), "truth_boundary", minimum=40),
    }
    settings = load_settings(project_root)
    _validate_supersession(settings, register)
    controls = {relative: {"sha256": sha256_file(source), "bytes": source.stat().st_size}}
    controls.update(fact_controls); controls.update(gap_controls)
    encoded = json.dumps(register, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "register": register,
        "contract_source": relative,
        "source_fingerprint": controls[relative]["sha256"],
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "controls": controls,
        "control_paths": sorted(controls),
    }


def record_continuity_register(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_continuity_register(project_root, forge_root, source_path)
    register = validated["register"]
    settings = load_settings(project_root)
    registers = settings.get("continuity_registers", {}) if isinstance(settings.get("continuity_registers"), dict) else {}
    previous_id = str(settings.get("active_continuity_register_id", "")).strip()
    if previous_id and previous_id in registers and isinstance(registers[previous_id], dict):
        previous = dict(registers[previous_id])
        previous["status"] = "superseded"
        previous["superseded_utc"] = utc_now()
        previous["superseded_by"] = register["register_id"]
        registers[previous_id] = previous
    record = {
        "status": "active",
        "recorded_utc": utc_now(),
        "contract_source": validated["contract_source"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "controls": validated["controls"],
        "register": register,
    }
    registers[register["register_id"]] = record
    settings["continuity_registers"] = registers
    settings["active_continuity_register_id"] = register["register_id"]
    settings["continuity_control_paths"] = validated["control_paths"]
    # The register contract itself is Forge control metadata and must not create
    # an artificial project-lineage mutation. Supporting project files remain
    # part of the project tree so their changes still affect lineage and facts.
    lineage_controls = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    if validated["contract_source"] not in lineage_controls:
        lineage_controls.append(validated["contract_source"])
    settings["lineage_control_paths"] = sorted(lineage_controls)
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "continuity-register-recorded", {
        "register_id": register["register_id"],
        "supersedes_register_id": register["supersedes_register_id"],
        "fact_count": len(register["facts"]),
        "open_gap_count": sum(1 for gap in register["gaps"] if gap["status"] == "open"),
        "trust_counts": {trust: sum(1 for fact in register["facts"] if fact["trust"] == trust) for trust in TRUST_LEVELS},
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
    }, source=register["authority"])
    record["event_id"] = event["id"]
    registers[register["register_id"]] = record
    settings["continuity_registers"] = registers
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_continuity_register(project_root: Path, register_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    project_root = project_root.resolve()
    register_id = _required(register_id, "register_id")
    reason = _required(reason, "retirement reason", minimum=10)
    settings = load_settings(project_root)
    registers = settings.get("continuity_registers", {}) if isinstance(settings.get("continuity_registers"), dict) else {}
    current = registers.get(register_id)
    if not isinstance(current, dict):
        raise ValueError(f"Unknown continuity register: {register_id}")
    if current.get("status") == "retired":
        raise ValueError(f"Continuity register {register_id} is already retired.")
    retired = dict(current)
    retired.update({"status": "retired", "retired_utc": utc_now(), "retirement_reason": reason, "retired_by": authority})
    registers[register_id] = retired
    settings["continuity_registers"] = registers
    if str(settings.get("active_continuity_register_id", "")) == register_id:
        settings["active_continuity_register_id"] = ""
        settings["continuity_control_paths"] = []
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "continuity-register-retired", {
        "register_id": register_id,
        "reason": reason,
    }, source=authority)
    retired["retirement_event_id"] = event["id"]
    registers[register_id] = retired
    settings["continuity_registers"] = registers
    write_json(ForgePaths(project_root).settings, settings)
    return retired


def _current_record(project_root: Path) -> dict[str, Any]:
    settings = load_settings(project_root.resolve())
    return _active_record(settings)


def assess_continuity_register(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    record = _current_record(project_root)
    if not record:
        return {
            "schema": 1,
            "status": "NOT_DECLARED",
            "reason": "No governed continuity register is active.",
            "fact_count": 0,
            "open_gap_count": 0,
            "blocker_gap_count": 0,
            "ship_blocking_gap_count": 0,
            "facts": [],
            "gaps": [],
            "truth_boundary": "Session Close and Resume remain available, but durable facts and knowledge gaps are not authority-governed.",
        }
    if record.get("status") != "active":
        return {
            "schema": 1,
            "status": "NOT_DECLARED",
            "reason": "The previously recorded continuity register is not active.",
            "fact_count": 0,
            "open_gap_count": 0,
            "blocker_gap_count": 0,
            "ship_blocking_gap_count": 0,
            "facts": [],
            "gaps": [],
            "truth_boundary": "Retired or superseded continuity registers remain historical records only.",
        }
    source = project_root / str(record.get("contract_source", ""))
    if not source.is_file() or source.is_symlink():
        return {"schema": 1, "status": "APPROVAL_REQUIRED", "reason": "The active continuity register source is missing.", "fact_count": 0, "open_gap_count": 0, "blocker_gap_count": 0, "ship_blocking_gap_count": 0, "facts": [], "gaps": []}
    if sha256_file(source) != str(record.get("source_fingerprint", "")):
        return {"schema": 1, "status": "APPROVAL_REQUIRED", "reason": "The active continuity register source changed and must be recorded again.", "fact_count": 0, "open_gap_count": 0, "blocker_gap_count": 0, "ship_blocking_gap_count": 0, "facts": [], "gaps": []}
    controls = record.get("controls", {}) if isinstance(record.get("controls"), dict) else {}
    stale_controls: list[str] = []
    for relative, expected in sorted(controls.items()):
        if relative == record.get("contract_source"):
            continue
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            stale_controls.append(f"{relative} missing")
            continue
        if sha256_file(path) != str(expected.get("sha256", "")) or path.stat().st_size != int(expected.get("bytes", -1)):
            stale_controls.append(f"{relative} changed")
    register = record.get("register", {}) if isinstance(record.get("register"), dict) else {}
    facts = register.get("facts", []) if isinstance(register.get("facts"), list) else []
    gaps = register.get("gaps", []) if isinstance(register.get("gaps"), list) else []
    open_gaps = [gap for gap in gaps if isinstance(gap, dict) and gap.get("status") == "open"]
    blocker_gaps = [gap for gap in open_gaps if gap.get("priority") == "blocker"]
    ship_blocking = [gap for gap in open_gaps if "ship" in gap.get("blocking_scopes", []) or "release" in gap.get("blocking_scopes", [])]
    status = "STALE" if stale_controls else "CURRENT"
    reason = (
        f"{len(stale_controls)} supporting project file(s) changed or disappeared."
        if stale_controls
        else "The active continuity register and its project-file support match their recorded bytes."
    )
    trust_counts = {trust: sum(1 for fact in facts if isinstance(fact, dict) and fact.get("trust") == trust) for trust in TRUST_LEVELS}
    return {
        "schema": 1,
        "status": status,
        "reason": reason,
        "register_id": str(register.get("register_id", "")),
        "recorded_utc": str(record.get("recorded_utc", "")),
        "fact_count": len(facts),
        "open_gap_count": len(open_gaps),
        "blocker_gap_count": len(blocker_gaps),
        "ship_blocking_gap_count": len(ship_blocking),
        "trust_counts": trust_counts,
        "facts": facts,
        "gaps": gaps,
        "stale_controls": stale_controls,
        "contract_source": str(record.get("contract_source", "")),
        "contract_fingerprint": str(record.get("contract_fingerprint", "")),
        "truth_boundary": str(register.get("truth_boundary", "")),
    }


def continuity_register_summary(project_root: Path) -> dict[str, Any]:
    return assess_continuity_register(project_root)

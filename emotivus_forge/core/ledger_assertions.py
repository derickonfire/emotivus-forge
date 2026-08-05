from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from .common import normalize_rel, read_json, unique_strings, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .state import load_settings

ASSERTION_SCHEMA = 1
ASSERTION_KINDS = {
    "path-exists",
    "path-absent",
    "file-contains",
    "file-not-contains",
    "json-equals",
    "zip-excludes-prefix",
    "zip-includes-path",
}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Ledger assertion contract requires {label}.")
    return text


def _safe_source(project_root: Path, forge_root: Path, raw: str | Path) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root):
        raise ValueError("Ledger assertion contracts must be project-owned files outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Ledger assertion contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _safe_relative(project_root: Path, raw: Any, label: str) -> str:
    relative = normalize_rel(_required(raw, label).lstrip("/"))
    target = (project_root / relative).resolve()
    if relative in {"", "."} or relative.startswith("../") or not _inside(target, project_root) or _inside(target, project_root / ".forge"):
        raise ValueError(f"{label} must remain inside the project and outside .forge.")
    return relative


def validate_ledger_assertion_contract(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _safe_source(project_root, forge_root.resolve(), contract_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Ledger assertion contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != ASSERTION_SCHEMA:
        raise ValueError("Ledger assertion contract must be an object using schema 1.")
    assertion_id = _required(raw.get("assertion_id"), "assertion_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in assertion_id):
        raise ValueError("assertion_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    record_type = _required(raw.get("record_type"), "record_type")
    if record_type not in {"decision", "resolved-defect", "guardrail", "release-rule", "project-rule"}:
        raise ValueError("record_type must be decision, resolved-defect, guardrail, release-rule, or project-rule.")
    rationale = _required(raw.get("rationale"), "rationale", minimum=20)
    boundary = _required(raw.get("verification_boundary"), "verification_boundary", minimum=20)
    evidence_paths = raw.get("evidence_paths", [])
    if not isinstance(evidence_paths, list) or not evidence_paths:
        raise ValueError("Ledger assertion contract requires evidence_paths as a non-empty array.")
    normalized_evidence: list[str] = []
    for item in unique_strings(evidence_paths):
        rel = _safe_relative(project_root, item, "evidence path")
        if not (project_root / rel).exists():
            raise ValueError(f"Ledger assertion evidence path does not exist: {rel}")
        normalized_evidence.append(rel)
    rows = raw.get("assertions")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Ledger assertion contract requires at least one assertion.")
    assertions: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(rows, 1):
        if not isinstance(item, dict):
            raise ValueError(f"assertions[{index}] must be an object.")
        item_id = _required(item.get("id"), f"assertions[{index}].id")
        if item_id in ids:
            raise ValueError(f"Duplicate ledger assertion item id: {item_id}")
        ids.add(item_id)
        kind = _required(item.get("kind"), f"assertions[{index}].kind")
        if kind not in ASSERTION_KINDS:
            raise ValueError(f"Unsupported ledger assertion kind: {kind}")
        target = _safe_relative(project_root, item.get("path"), f"assertions[{index}].path")
        row: dict[str, Any] = {"id": item_id, "kind": kind, "path": target}
        if kind in {"file-contains", "file-not-contains"}:
            row["text"] = _required(item.get("text"), f"assertions[{index}].text")
        elif kind == "json-equals":
            row["key"] = _required(item.get("key"), f"assertions[{index}].key")
            if "value" not in item:
                raise ValueError(f"assertions[{index}].value is required.")
            row["value"] = item.get("value")
        elif kind == "zip-excludes-prefix":
            row["prefix"] = normalize_rel(_required(item.get("prefix"), f"assertions[{index}].prefix").lstrip("/"))
        elif kind == "zip-includes-path":
            row["member"] = normalize_rel(_required(item.get("member"), f"assertions[{index}].member").lstrip("/"))
        assertions.append(row)
    contract = {
        "schema": ASSERTION_SCHEMA,
        "assertion_id": assertion_id,
        "title": title,
        "authority": authority,
        "record_type": record_type,
        "rationale": rationale,
        "evidence_paths": normalized_evidence,
        "assertions": assertions,
        "verification_boundary": boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(
        project_root,
        record,
        changed_status="approval-required",
        missing_reason="The project-owned ledger assertion source is missing.",
        changed_reason="The project-owned ledger assertion changed after authority approval.",
    )


def ledger_assertion_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("ledger_assertions", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_ledger_assertion(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    validated = validate_ledger_assertion_contract(project_root, forge_root, contract_path)
    contract = validated["contract"]
    assertion_id = contract["assertion_id"]
    settings = load_settings(project_root)
    records = settings.get("ledger_assertions", {})
    if not isinstance(records, dict):
        records = {}
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "assertion_id": assertion_id,
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[assertion_id] = record
    settings["ledger_assertions"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "ledger-assertion-recorded", {
        "assertion_id": assertion_id,
        "title": contract["title"],
        "record_type": contract["record_type"],
        "authority": contract["authority"],
        "contract_source": validated["source"],
        "assertion_count": len(contract["assertions"]),
        "verification_boundary": contract["verification_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_ledger_assertion(project_root: Path, assertion_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("ledger_assertions", {})
    if not isinstance(records, dict) or assertion_id not in records or not isinstance(records[assertion_id], dict):
        raise ValueError(f"Ledger assertion is not recorded: {assertion_id}")
    record = dict(records[assertion_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[assertion_id] = record
    settings["ledger_assertions"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "ledger-assertion-retired", {"assertion_id": assertion_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _json_lookup(value: Any, dotted: str) -> tuple[bool, Any]:
    current = value
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def _evaluate_item(project_root: Path, item: dict[str, Any]) -> tuple[bool, str]:
    path = project_root / str(item.get("path", ""))
    kind = str(item.get("kind", ""))
    if kind == "path-exists":
        return path.exists(), "required path is missing"
    if kind == "path-absent":
        return not path.exists(), "prohibited path exists"
    if not path.is_file() or path.is_symlink():
        return False, "target is missing or is not a regular file"
    if kind in {"file-contains", "file-not-contains"}:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False, "target is not readable UTF-8 text"
        present = str(item.get("text", "")) in text
        return (present, "required text is absent") if kind == "file-contains" else (not present, "prohibited text is present")
    if kind == "json-equals":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False, "target is not valid UTF-8 JSON"
        found, actual = _json_lookup(value, str(item.get("key", "")))
        if not found:
            return False, "declared JSON key is absent"
        return actual == item.get("value"), f"JSON value differs: observed {actual!r}"
    if kind in {"zip-excludes-prefix", "zip-includes-path"}:
        try:
            with zipfile.ZipFile(path) as archive:
                members = [normalize_rel(name).lstrip("/") for name in archive.namelist()]
        except (OSError, zipfile.BadZipFile):
            return False, "target is not a readable ZIP archive"
        if kind == "zip-excludes-prefix":
            prefix = str(item.get("prefix", "")).rstrip("/")
            hit = next((name for name in members if name == prefix or name.startswith(prefix + "/")), "")
            return not bool(hit), f"archive contains prohibited prefix via {hit}"
        member = str(item.get("member", ""))
        return member in members, "required archive member is absent"
    return False, "unsupported assertion kind"


def evaluate_ledger_assertions(project_root: Path) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    active = 0
    for assertion_id, record in sorted(ledger_assertion_records(project_root).items()):
        if record.get("status") == "retired":
            continue
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        source = str(record.get("contract_source", ""))
        if record.get("lifecycle_status") != "active":
            evaluations.append({"assertion_id": assertion_id, "title": contract.get("title", assertion_id), "status": "APPROVAL_REQUIRED", "reason": record.get("reason", "Authority approval is not current."), "contract_source": source, "items": []})
            findings.append({"check": "core.ledger-assertions", "severity": "blocker", "path": source or ".", "line": 0, "message": f"Ledger assertion {assertion_id} is not current: {record.get('reason', 'authority approval required')}"})
            continue
        active += 1
        item_rows: list[dict[str, Any]] = []
        failed = False
        for item in contract.get("assertions", []):
            if not isinstance(item, dict):
                continue
            passed, reason = _evaluate_item(project_root, item)
            item_rows.append({"id": item.get("id", ""), "kind": item.get("kind", ""), "path": item.get("path", ""), "status": "PASS" if passed else "FAIL", "reason": "" if passed else reason})
            if not passed:
                failed = True
                findings.append({"check": "core.ledger-assertions", "severity": "blocker", "path": item.get("path", "."), "line": 0, "message": f"Ledger assertion {assertion_id}/{item.get('id', 'item')} failed: {reason}."})
        evaluations.append({
            "assertion_id": assertion_id,
            "title": contract.get("title", assertion_id),
            "record_type": contract.get("record_type", "project-rule"),
            "status": "FAIL" if failed else "PASS",
            "contract_source": source,
            "items": item_rows,
            "verification_boundary": contract.get("verification_boundary", ""),
        })
    return {
        "schema": 1,
        "status": "FAIL" if findings else "PASS",
        "active_count": active,
        "evaluations": evaluations,
        "findings": findings,
        "truth_boundary": "Ledger assertions re-evaluate authority-recorded deterministic obligations. Passing them does not prove the surrounding feature, decision, or release is complete or correct.",
    }


def ledger_assertion_summary(project_root: Path) -> dict[str, Any]:
    active: list[dict[str, Any]] = []
    attention: list[dict[str, Any]] = []
    retired = 0
    for assertion_id, record in sorted(ledger_assertion_records(project_root).items()):
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        row = {"assertion_id": assertion_id, "title": contract.get("title", assertion_id), "record_type": contract.get("record_type", "project-rule"), "status": record.get("lifecycle_status", record.get("status", "proposed")), "reason": record.get("reason", ""), "assertion_count": len(contract.get("assertions", []))}
        if record.get("status") == "retired":
            retired += 1
        elif row["status"] == "active":
            active.append(row)
        else:
            attention.append(row)
    return {"schema": 1, "active": active, "attention": attention, "retired_count": retired, "truth_boundary": "The summary reports authority and source currency, not assertion outcomes. Outcomes are evaluated during Check."}

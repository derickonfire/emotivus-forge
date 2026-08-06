from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, unique_strings, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .state import load_settings
from .truth import normalize_verification_tier

QUALIFICATION_SCHEMA = 1


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Check qualification requires {label}.")
    return text


def _source(project_root: Path, forge_root: Path, raw: str | Path, label: str) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root):
        raise ValueError(f"{label} must be project-owned and outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def validate_check_qualification(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source(project_root, forge_root.resolve(), contract_path, "Qualification contract")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Check qualification is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != QUALIFICATION_SCHEMA:
        raise ValueError("Check qualification must be an object using schema 1.")
    qualification_id = _required(raw.get("qualification_id"), "qualification_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in qualification_id):
        raise ValueError("qualification_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    check_id = _required(raw.get("check_id"), "check_id")
    authority = _required(raw.get("authority"), "authority")
    check_path, check_relative = _source(project_root, forge_root.resolve(), raw.get("check_source", ""), "check_source")
    tier = normalize_verification_tier(raw.get("verification_tier", "sandbox"), default="sandbox")
    cases = raw.get("negative_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Check qualification requires at least one negative_cases entry.")
    negative_cases: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(cases, 1):
        if not isinstance(item, dict):
            raise ValueError(f"negative_cases[{index}] must be an object.")
        case_id = _required(item.get("id"), f"negative_cases[{index}].id")
        if case_id in ids:
            raise ValueError(f"Duplicate negative case id: {case_id}")
        ids.add(case_id)
        description = _required(item.get("description"), f"negative_cases[{index}].description", minimum=12)
        observed = str(item.get("observed_result", "")).strip().upper()
        expected = str(item.get("expected_result", "FAIL")).strip().upper()
        if expected != "FAIL" or observed != "FAIL":
            raise ValueError("Every qualification negative case must expect FAIL and have an observed_result of FAIL.")
        evidence_path, evidence_relative = _source(project_root, forge_root.resolve(), item.get("evidence_path", ""), f"negative_cases[{index}].evidence_path")
        negative_cases.append({
            "id": case_id,
            "description": description,
            "expected_result": "FAIL",
            "observed_result": "FAIL",
            "evidence_path": evidence_relative,
            "evidence_fingerprint": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "observed_utc": _required(item.get("observed_utc"), f"negative_cases[{index}].observed_utc"),
        })
    limitations = unique_strings(raw.get("limitations", [])) if isinstance(raw.get("limitations", []), list) else []
    surface_count = raw.get("scanned_surface_count")
    if surface_count is not None and (not isinstance(surface_count, int) or surface_count < 0):
        raise ValueError("scanned_surface_count must be a non-negative integer when supplied.")
    boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=20)
    contract = {
        "schema": QUALIFICATION_SCHEMA,
        "qualification_id": qualification_id,
        "check_id": check_id,
        "authority": authority,
        "check_source": check_relative,
        "verification_tier": tier,
        "negative_cases": negative_cases,
        "limitations": limitations,
        "scanned_surface_count": surface_count,
        "truth_boundary": boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
        "check_source_fingerprint": hashlib.sha256(check_path.read_bytes()).hexdigest(),
    }


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    current = fingerprint_bound_status(
        project_root,
        record,
        changed_status="approval-required",
        missing_reason="The project-owned check qualification source is missing.",
        changed_reason="The project-owned check qualification changed after authority approval.",
    )
    if current.get("lifecycle_status") != "active":
        return current
    contract = current.get("contract", {}) if isinstance(current.get("contract"), dict) else {}
    check_source = str(contract.get("check_source", ""))
    path = project_root / check_source
    if not path.is_file() or path.is_symlink():
        current.update({"status": "approval-required", "lifecycle_status": "approval-required", "reason": "The qualified check source is missing."})
        return current
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != str(current.get("check_source_fingerprint", "")):
        current.update({"status": "approval-required", "lifecycle_status": "approval-required", "reason": "The qualified check source changed after its negative-test evidence was recorded.", "current_check_source_fingerprint": actual})
        return current
    for case in contract.get("negative_cases", []):
        if not isinstance(case, dict):
            continue
        evidence = project_root / str(case.get("evidence_path", ""))
        if not evidence.is_file() or evidence.is_symlink() or hashlib.sha256(evidence.read_bytes()).hexdigest() != str(case.get("evidence_fingerprint", "")):
            current.update({"status": "approval-required", "lifecycle_status": "approval-required", "reason": f"Qualification evidence for negative case {case.get('id', '')} is missing or changed."})
            return current
    return current


def check_qualification_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("check_qualifications", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_check_qualification(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    validated = validate_check_qualification(project_root, forge_root, contract_path)
    contract = validated["contract"]
    qualification_id = contract["qualification_id"]
    settings = load_settings(project_root)
    records = settings.get("check_qualifications", {})
    if not isinstance(records, dict):
        records = {}
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "qualification_id": qualification_id,
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "check_source_fingerprint": validated["check_source_fingerprint"],
        "contract": contract,
    }
    records[qualification_id] = record
    settings["check_qualifications"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "check-qualification-recorded", {
        "qualification_id": qualification_id,
        "check_id": contract["check_id"],
        "authority": contract["authority"],
        "check_source": contract["check_source"],
        "negative_case_count": len(contract["negative_cases"]),
        "limitations": contract["limitations"],
        "truth_boundary": contract["truth_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_check_qualification(project_root: Path, qualification_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("check_qualifications", {})
    if not isinstance(records, dict) or qualification_id not in records or not isinstance(records[qualification_id], dict):
        raise ValueError(f"Check qualification is not recorded: {qualification_id}")
    record = dict(records[qualification_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[qualification_id] = record
    settings["check_qualifications"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "check-qualification-retired", {"qualification_id": qualification_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def qualify_evidence_records(project_root: Path, evidence_records: list[dict[str, Any]]) -> dict[str, Any]:
    by_check: dict[str, list[dict[str, Any]]] = {}
    records = check_qualification_records(project_root)
    for qualification_id, record in records.items():
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        check_id = str(contract.get("check_id", ""))
        if check_id:
            by_check.setdefault(check_id, []).append({**record, "qualification_id": qualification_id})
    rows: list[dict[str, Any]] = []
    counts = {"qualified": 0, "unqualified": 0, "stale": 0}
    for evidence in evidence_records:
        if not isinstance(evidence, dict):
            continue
        check_id = str(evidence.get("id", ""))
        candidates = by_check.get(check_id, [])
        active = next((item for item in candidates if item.get("lifecycle_status") == "active"), None)
        stale = next((item for item in candidates if item.get("lifecycle_status") == "approval-required"), None)
        if active:
            contract = active.get("contract", {}) if isinstance(active.get("contract"), dict) else {}
            status = "qualified"
            details = {
                "qualification_id": active.get("qualification_id", ""),
                "negative_case_count": len(contract.get("negative_cases", [])),
                "limitations": contract.get("limitations", []),
                "scanned_surface_count": contract.get("scanned_surface_count"),
                "verification_tier": contract.get("verification_tier", "sandbox"),
            }
        elif stale:
            status = "stale"
            details = {"qualification_id": stale.get("qualification_id", ""), "reason": stale.get("reason", "Qualification approval is stale.")}
        else:
            status = "unqualified"
            details = {"reason": "No current authority-recorded negative-test qualification exists for this check id."}
        counts[status] += 1
        rows.append({"check_id": check_id, "evidence_status": evidence.get("status", "UNKNOWN"), "qualification_status": status, **details})
    return {
        "schema": 1,
        "evidence_check_count": len(rows),
        "counts": counts,
        "records": rows,
        "qualified_ratio": f"{counts['qualified']}/{len(rows)}" if rows else "0/0",
        "truth_boundary": "Qualification shows that a check was observed failing on recorded known-bad input for its current source fingerprint. It does not prove complete defect coverage or that its test model matches production reality.",
    }


def check_qualification_summary(project_root: Path) -> dict[str, Any]:
    active = 0
    attention = 0
    retired = 0
    negative_cases = 0
    for record in check_qualification_records(project_root).values():
        if record.get("status") == "retired":
            retired += 1
        elif record.get("lifecycle_status") == "active":
            active += 1
            contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
            negative_cases += len(contract.get("negative_cases", []))
        else:
            attention += 1
    return {"schema": 1, "active": active, "attention": attention, "retired": retired, "negative_cases": negative_cases, "truth_boundary": "Counts describe recorded qualification evidence, not universal check accuracy."}

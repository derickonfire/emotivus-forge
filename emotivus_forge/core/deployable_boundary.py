from __future__ import annotations

import fnmatch
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .project_identity import project_identity_record
from .provenance import provenance_records
from .state import load_settings

BOUNDARY_SCHEMA = 1
VALID_DELTA_MODES = {"exact", "subset"}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Deployable boundary requires {label}.")
    return text


def _safe_source(project_root: Path, forge_root: Path, raw: str | Path) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError("Deployable boundary contracts must be project-owned files outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Deployable boundary contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _safe_pattern(raw: Any, label: str) -> str:
    pattern = normalize_rel(_required(raw, label).lstrip("/"))
    if pattern.startswith("../") or "/../" in f"/{pattern}/" or pattern in {"", ".forge", ".forge/**"}:
        raise ValueError(f"{label} must remain inside the project and outside .forge.")
    return pattern


def validate_deployable_boundary_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _safe_source(project_root, forge_root, source_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Deployable boundary contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != BOUNDARY_SCHEMA:
        raise ValueError("Deployable boundary contract must be an object using schema 1.")
    boundary_id = _required(raw.get("boundary_id"), "boundary_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in boundary_id):
        raise ValueError("boundary_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    strict_unclassified = bool(raw.get("strict_unclassified", True))
    roles_raw = raw.get("roles")
    if not isinstance(roles_raw, list) or not roles_raw:
        raise ValueError("Deployable boundary requires a non-empty roles array.")
    roles: list[dict[str, Any]] = []
    role_ids: set[str] = set()
    for index, item in enumerate(roles_raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"roles[{index}] must be an object.")
        role = _required(item.get("role"), f"roles[{index}].role")
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in role):
            raise ValueError(f"roles[{index}].role may contain only lowercase letters, numbers, hyphens, and underscores.")
        if role in role_ids:
            raise ValueError(f"Duplicate deployable-boundary role: {role}")
        role_ids.add(role)
        patterns_raw = item.get("patterns")
        if not isinstance(patterns_raw, list) or not patterns_raw:
            raise ValueError(f"roles[{index}].patterns must be a non-empty array.")
        patterns = [_safe_pattern(value, f"roles[{index}].patterns") for value in patterns_raw]
        roles.append({"role": role, "patterns": patterns, "description": str(item.get("description", "")).strip()})
    blocked_roles_raw = raw.get("blocked_from_delivery", ["prohibited"])
    if not isinstance(blocked_roles_raw, list):
        raise ValueError("blocked_from_delivery must be an array.")
    blocked_roles = sorted({str(value).strip() for value in blocked_roles_raw if str(value).strip()})
    unknown = [value for value in blocked_roles if value not in role_ids]
    if unknown:
        raise ValueError(f"blocked_from_delivery references unknown role(s): {', '.join(unknown)}")
    deltas_raw = raw.get("delta_artifacts", [])
    if not isinstance(deltas_raw, list):
        raise ValueError("delta_artifacts must be an array.")
    delta_artifacts: list[dict[str, Any]] = []
    delta_ids: set[str] = set()
    for index, item in enumerate(deltas_raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"delta_artifacts[{index}] must be an object.")
        delta_id = _required(item.get("id"), f"delta_artifacts[{index}].id")
        if delta_id in delta_ids:
            raise ValueError(f"Duplicate delta artifact id: {delta_id}")
        delta_ids.add(delta_id)
        provenance_id = _required(item.get("provenance_id"), f"delta_artifacts[{index}].provenance_id")
        mode = str(item.get("mode", "exact")).strip()
        if mode not in VALID_DELTA_MODES:
            raise ValueError(f"delta_artifacts[{index}].mode must be exact or subset.")
        allowed_raw = item.get("allowed_roles")
        if not isinstance(allowed_raw, list) or not allowed_raw:
            raise ValueError(f"delta_artifacts[{index}].allowed_roles must be a non-empty array.")
        allowed_roles = sorted({str(value).strip() for value in allowed_raw if str(value).strip()})
        unknown_allowed = [value for value in allowed_roles if value not in role_ids]
        if unknown_allowed:
            raise ValueError(f"delta_artifacts[{index}] references unknown role(s): {', '.join(unknown_allowed)}")
        baseline = _required(item.get("computed_for_baseline_build_id"), f"delta_artifacts[{index}].computed_for_baseline_build_id")
        member_prefix = normalize_rel(str(item.get("member_prefix", "")).strip().strip("/"))
        delta_artifacts.append({
            "id": delta_id,
            "provenance_id": provenance_id,
            "mode": mode,
            "allowed_roles": allowed_roles,
            "computed_for_baseline_build_id": baseline,
            "member_prefix": member_prefix,
        })
    verification_boundary = _required(raw.get("verification_boundary"), "verification_boundary", minimum=30)
    contract = {
        "schema": BOUNDARY_SCHEMA,
        "boundary_id": boundary_id,
        "title": title,
        "authority": authority,
        "strict_unclassified": strict_unclassified,
        "roles": roles,
        "blocked_from_delivery": blocked_roles,
        "delta_artifacts": delta_artifacts,
        "verification_boundary": verification_boundary,
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
        missing_reason="The project-owned deployable-boundary source is missing.",
        changed_reason="The project-owned deployable-boundary source changed after authority approval.",
    )


def deployable_boundary_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("deployable_boundaries", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_deployable_boundary(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_deployable_boundary_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.get("deployable_boundaries", {})
    if not isinstance(records, dict):
        records = {}
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "boundary_id": contract["boundary_id"],
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[contract["boundary_id"]] = record
    settings["deployable_boundaries"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "deployable-boundary-recorded", {
        "boundary_id": contract["boundary_id"],
        "title": contract["title"],
        "authority": contract["authority"],
        "role_count": len(contract["roles"]),
        "delta_artifact_count": len(contract["delta_artifacts"]),
        "verification_boundary": contract["verification_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_deployable_boundary(project_root: Path, boundary_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("deployable_boundaries", {})
    if not isinstance(records, dict) or boundary_id not in records or not isinstance(records[boundary_id], dict):
        raise ValueError(f"Deployable boundary is not recorded: {boundary_id}")
    record = dict(records[boundary_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[boundary_id] = record
    settings["deployable_boundaries"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "deployable-boundary-retired", {"boundary_id": boundary_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _classify(path: str, roles: list[dict[str, Any]]) -> list[str]:
    matches: list[str] = []
    for role in roles:
        if any(fnmatch.fnmatch(path, pattern) for pattern in role.get("patterns", [])):
            matches.append(str(role.get("role", "")))
    return sorted(set(value for value in matches if value))


def _current_baseline(project_root: Path) -> str:
    record = project_identity_record(project_root)
    if record.get("lifecycle_status") != "active":
        return ""
    identity = record.get("identity", {}) if isinstance(record.get("identity"), dict) else {}
    baseline = identity.get("baseline", {}) if isinstance(identity.get("baseline"), dict) else {}
    return str(baseline.get("build_id", "")).strip()


def _zip_members(path: Path, member_prefix: str) -> tuple[list[str], str]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [normalize_rel(info.filename).lstrip("/") for info in archive.infolist() if not info.is_dir()]
    except (OSError, zipfile.BadZipFile):
        return [], "artifact is not a readable ZIP archive"
    prefix = member_prefix.rstrip("/")
    if prefix:
        prefix_with_slash = prefix + "/"
        members = [name[len(prefix_with_slash):] for name in members if name.startswith(prefix_with_slash)]
    return sorted(set(name for name in members if name)), ""


def evaluate_deployable_boundaries(project_root: Path, changed_paths: list[str]) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    active_count = 0
    classified_total = 0
    unclassified_total = 0
    overlap_total = 0
    provenance = provenance_records(project_root)
    baseline = _current_baseline(project_root)
    for boundary_id, record in sorted(deployable_boundary_records(project_root).items()):
        if record.get("status") == "retired":
            continue
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        source = str(record.get("contract_source", ""))
        if record.get("lifecycle_status") != "active":
            evaluations.append({"boundary_id": boundary_id, "title": contract.get("title", boundary_id), "status": "APPROVAL_REQUIRED", "reason": record.get("reason", "Authority approval is not current."), "contract_source": source})
            findings.append({"check": "core.deployable-boundary", "severity": "blocker", "path": source or ".", "line": 0, "message": f"Deployable boundary {boundary_id} is not current: {record.get('reason', 'authority approval required')}"})
            continue
        active_count += 1
        roles = contract.get("roles", []) if isinstance(contract.get("roles"), list) else []
        rows: list[dict[str, Any]] = []
        mapping: dict[str, list[str]] = {}
        failed = False
        for changed in changed_paths:
            matched = _classify(changed, roles)
            mapping[changed] = matched
            status = "CLASSIFIED" if len(matched) == 1 else "OVERLAP" if len(matched) > 1 else "UNCLASSIFIED"
            rows.append({"path": changed, "roles": matched, "status": status})
            if status == "CLASSIFIED":
                classified_total += 1
            elif status == "OVERLAP":
                overlap_total += 1
                failed = True
                findings.append({"check": "core.deployable-boundary", "severity": "blocker", "path": changed, "line": 0, "message": f"Changed path matches multiple delivery roles in {boundary_id}: {', '.join(matched)}."})
            else:
                unclassified_total += 1
                severity = "blocker" if contract.get("strict_unclassified", True) else "warning"
                failed = failed or severity == "blocker"
                findings.append({"check": "core.deployable-boundary", "severity": severity, "path": changed, "line": 0, "message": f"Changed path is not classified by deployable boundary {boundary_id}."})
        delta_rows: list[dict[str, Any]] = []
        for delta in contract.get("delta_artifacts", []):
            if not isinstance(delta, dict):
                continue
            delta_id = str(delta.get("id", "delta"))
            provenance_id = str(delta.get("provenance_id", ""))
            p_record = provenance.get(provenance_id, {}) if isinstance(provenance.get(provenance_id), dict) else {}
            reasons: list[str] = []
            artifact_path = ""
            if not p_record:
                reasons.append("referenced artifact provenance is not recorded")
            elif p_record.get("lifecycle_status") != "active":
                reasons.append("referenced artifact provenance is not current")
            else:
                p_contract = p_record.get("contract", {}) if isinstance(p_record.get("contract"), dict) else {}
                artifact_path = str(p_contract.get("artifact_path", ""))
            declared_baseline = str(delta.get("computed_for_baseline_build_id", ""))
            if not baseline:
                reasons.append("current owner-declared baseline is unavailable")
            elif declared_baseline != baseline:
                reasons.append(f"delta baseline {declared_baseline} does not match current owner-declared baseline {baseline}")
            allowed_roles = set(str(value) for value in delta.get("allowed_roles", []))
            expected = sorted(path for path, matched in mapping.items() if len(matched) == 1 and matched[0] in allowed_roles)
            actual: list[str] = []
            if artifact_path:
                actual, zip_error = _zip_members(project_root / artifact_path, str(delta.get("member_prefix", "")))
                if zip_error:
                    reasons.append(zip_error)
            blocked_roles = set(str(value) for value in contract.get("blocked_from_delivery", []))
            prohibited_members = sorted(path for path in actual if any(role in blocked_roles for role in _classify(path, roles)))
            if prohibited_members:
                reasons.append(f"delta contains {len(prohibited_members)} path(s) from blocked delivery roles")
            mode = str(delta.get("mode", "exact"))
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            if mode == "exact" and (missing or extra):
                reasons.append(f"delta path set differs from authoritative allowed changed set: {len(missing)} missing, {len(extra)} extra")
            elif mode == "subset" and extra:
                reasons.append(f"delta contains {len(extra)} path(s) outside the authoritative allowed changed set")
            delta_status = "PASS" if not reasons else "FAIL"
            if reasons:
                failed = True
                findings.append({"check": "core.deployable-boundary", "severity": "blocker", "path": artifact_path or source or ".", "line": 0, "message": f"Delta artifact {boundary_id}/{delta_id} failed: {'; '.join(reasons)}."})
            delta_rows.append({
                "id": delta_id,
                "status": delta_status,
                "provenance_id": provenance_id,
                "artifact_path": artifact_path,
                "mode": mode,
                "baseline": declared_baseline,
                "expected_count": len(expected),
                "actual_count": len(actual),
                "missing_paths": missing,
                "extra_paths": extra,
                "prohibited_paths": prohibited_members,
                "reasons": reasons,
            })
        evaluations.append({
            "boundary_id": boundary_id,
            "title": contract.get("title", boundary_id),
            "status": "FAIL" if failed else "PASS",
            "contract_source": source,
            "classified_paths": rows,
            "delta_artifacts": delta_rows,
            "verification_boundary": contract.get("verification_boundary", ""),
        })
    status = "FAIL" if any(item.get("severity") == "blocker" for item in findings) else "WARN" if findings else "PASS"
    return {
        "schema": 1,
        "status": status,
        "active_count": active_count,
        "classified_count": classified_total,
        "unclassified_count": unclassified_total,
        "overlap_count": overlap_total,
        "evaluations": evaluations,
        "findings": findings,
        "truth_boundary": "Deployable boundaries classify the canonical observed changed path set and can compare registered delta ZIP members to allowed changed paths and the owner-declared baseline. They do not prove deployment, package behavior, or release readiness.",
    }


def deployable_boundary_summary(project_root: Path) -> dict[str, Any]:
    active = 0
    attention = 0
    retired = 0
    delta_count = 0
    for record in deployable_boundary_records(project_root).values():
        if record.get("status") == "retired":
            retired += 1
        elif record.get("lifecycle_status") == "active":
            active += 1
            contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
            delta_count += len(contract.get("delta_artifacts", [])) if isinstance(contract.get("delta_artifacts"), list) else 0
        else:
            attention += 1
    return {"schema": 1, "active": active, "attention": attention, "retired": retired, "delta_artifacts": delta_count, "truth_boundary": "The summary reports authority and source currency only; Check evaluates changed-path and delta membership claims."}

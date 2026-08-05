from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .project_identity import project_identity_record
from .state import load_settings
from .truth import TIER_RANK, normalize_verification_tier

MATRIX_SCHEMA = 1
STAGES = {"local", "sandbox", "staging", "production"}
EVIDENCE_AUTHORITIES = {"owner", "external-ci"}
MIGRATION_MODES = {"none", "clean-install", "upgrade"}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Runtime-state matrix requires {label}.")
    return text


def _source(project_root: Path, forge_root: Path, raw: str | Path, label: str) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError(f"{label} must be a project-owned regular file outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _safe_relative(project_root: Path, raw: Any, label: str) -> tuple[Path, str]:
    relative = normalize_rel(_required(raw, label).lstrip("/"))
    path = (project_root / relative).resolve()
    if relative in {"", "."} or relative.startswith("../") or not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError(f"{label} must remain inside the project and outside .forge.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {relative}")
    return path, relative


def _string_list(value: Any, label: str, *, required: bool = False, limit: int = 30) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array.")
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    if required and not rows:
        raise ValueError(f"{label} requires at least one entry.")
    if len(rows) > limit:
        raise ValueError(f"{label} may contain at most {limit} entries.")
    return rows


def _lookup_identity(identity: dict[str, Any], field: str) -> Any:
    current: Any = identity
    for part in field.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError(f"Runtime-state candidate field is unavailable in the active project identity: {field}")
    if isinstance(current, (dict, list)):
        return json.loads(json.dumps(current, sort_keys=True, ensure_ascii=False))
    return current


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_runtime_matrix_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source(project_root, forge_root, source_path, "Runtime-state matrix contract")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Runtime-state matrix contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != MATRIX_SCHEMA:
        raise ValueError("Runtime-state matrix contract must be an object using schema 1.")
    matrix_id = _required(raw.get("matrix_id"), "matrix_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in matrix_id):
        raise ValueError("matrix_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    identity_record = project_identity_record(project_root)
    if identity_record.get("status") != "active":
        raise ValueError("Runtime-state matrix requires a current owner-recorded project identity.")
    identity = identity_record.get("identity", {}) if isinstance(identity_record.get("identity"), dict) else {}
    candidate_fields = _string_list(raw.get("candidate_fields"), "candidate_fields", required=True, limit=20)
    candidate_binding = {field: _lookup_identity(identity, field) for field in candidate_fields}

    scenarios_raw = raw.get("scenarios")
    if not isinstance(scenarios_raw, list) or not scenarios_raw:
        raise ValueError("Runtime-state matrix requires a non-empty scenarios array.")
    if len(scenarios_raw) > 20:
        raise ValueError("Runtime-state matrix may contain at most 20 scenarios.")
    scenarios: list[dict[str, Any]] = []
    scenario_ids: set[str] = set()
    for index, item in enumerate(scenarios_raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"scenarios[{index}] must be an object.")
        scenario_id = _required(item.get("scenario_id"), f"scenarios[{index}].scenario_id")
        if scenario_id in scenario_ids:
            raise ValueError(f"Duplicate runtime-state scenario_id: {scenario_id}")
        scenario_ids.add(scenario_id)
        target_environment = _required(item.get("target_environment"), f"scenarios[{index}].target_environment", minimum=3)
        stage = str(item.get("deployment_stage", "")).strip().lower()
        if stage not in STAGES:
            raise ValueError(f"scenarios[{index}].deployment_stage must be one of {sorted(STAGES)}.")
        tier = normalize_verification_tier(item.get("verification_tier"), default=stage if stage in {"staging", "production"} else "sandbox")
        prior = item.get("prior_state")
        if not isinstance(prior, dict):
            raise ValueError(f"scenarios[{index}].prior_state must be an object.")
        prior_state = {
            "state_id": _required(prior.get("state_id"), f"scenarios[{index}].prior_state.state_id"),
            "description": _required(prior.get("description"), f"scenarios[{index}].prior_state.description", minimum=12),
            "source": _required(prior.get("source"), f"scenarios[{index}].prior_state.source"),
        }
        baseline_field = _required(item.get("baseline_field", "baseline.build_id"), f"scenarios[{index}].baseline_field")
        baseline_value = _lookup_identity(identity, baseline_field)
        migration_mode = str(item.get("migration_mode", "upgrade")).strip().lower()
        if migration_mode not in MIGRATION_MODES:
            raise ValueError(f"scenarios[{index}].migration_mode must be one of {sorted(MIGRATION_MODES)}.")
        migration_rows = _string_list(item.get("migration_paths", []), f"scenarios[{index}].migration_paths", required=migration_mode == "upgrade")
        if migration_mode == "none" and migration_rows:
            raise ValueError(f"scenarios[{index}] migration_mode none cannot declare migration_paths.")
        migrations: list[dict[str, str]] = []
        for raw_migration in migration_rows:
            migration_path, migration_relative = _safe_relative(project_root, raw_migration, f"scenarios[{index}].migration_paths")
            migrations.append({"path": migration_relative, "sha256": _sha(migration_path)})
        recipe_ids = _string_list(item.get("runtime_recipe_ids"), f"scenarios[{index}].runtime_recipe_ids", required=True, limit=20)
        evidence_authorities = _string_list(item.get("evidence_authorities", ["owner", "external-ci"]), f"scenarios[{index}].evidence_authorities", required=True, limit=2)
        if any(value not in EVIDENCE_AUTHORITIES for value in evidence_authorities):
            raise ValueError(f"scenarios[{index}].evidence_authorities may contain only owner or external-ci.")
        exclusions = _string_list(item.get("exclusions"), f"scenarios[{index}].exclusions", required=True, limit=20)
        scenarios.append({
            "scenario_id": scenario_id,
            "target_environment": target_environment,
            "deployment_stage": stage,
            "verification_tier": tier,
            "prior_state": prior_state,
            "baseline_field": baseline_field,
            "baseline_value": baseline_value,
            "migration_mode": migration_mode,
            "migrations": migrations,
            "runtime_recipe_ids": recipe_ids,
            "evidence_authorities": evidence_authorities,
            "exclusions": exclusions,
        })
    verification_boundary = _required(raw.get("verification_boundary"), "verification_boundary", minimum=40)
    contract = {
        "schema": MATRIX_SCHEMA,
        "matrix_id": matrix_id,
        "title": title,
        "authority": authority,
        "candidate_fields": candidate_fields,
        "candidate_binding": candidate_binding,
        "identity_contract_fingerprint": identity_record.get("contract_fingerprint", ""),
        "scenarios": scenarios,
        "verification_boundary": verification_boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": _sha(path),
    }


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    current = fingerprint_bound_status(
        project_root,
        record,
        changed_status="approval-required",
        missing_reason="The project-owned runtime-state matrix source is missing.",
        changed_reason="The project-owned runtime-state matrix changed after authority approval.",
    )
    if current.get("lifecycle_status") != "active":
        return current
    identity = project_identity_record(project_root)
    if identity.get("status") != "active":
        return {**current, "lifecycle_status": "approval-required", "status": "approval-required", "reason": "The project identity is not current."}
    contract = current.get("contract", {}) if isinstance(current.get("contract"), dict) else {}
    if contract.get("identity_contract_fingerprint") != identity.get("contract_fingerprint"):
        return {**current, "lifecycle_status": "approval-required", "status": "approval-required", "reason": "The project identity changed after the runtime-state matrix was recorded."}
    for scenario in contract.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        for migration in scenario.get("migrations", []):
            if not isinstance(migration, dict):
                continue
            path = project_root / str(migration.get("path", ""))
            if not path.is_file() or path.is_symlink() or _sha(path) != migration.get("sha256"):
                return {**current, "lifecycle_status": "approval-required", "status": "approval-required", "reason": f"Migration input changed after matrix approval: {migration.get('path', '')}"}
    return current


def runtime_matrix_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("runtime_state_matrices", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_runtime_matrix(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_runtime_matrix_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.get("runtime_state_matrices", {})
    if not isinstance(records, dict):
        records = {}
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "matrix_id": contract["matrix_id"],
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[contract["matrix_id"]] = record
    settings["runtime_state_matrices"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "runtime-state-matrix-recorded", {
        "matrix_id": contract["matrix_id"],
        "title": contract["title"],
        "authority": contract["authority"],
        "scenario_count": len(contract["scenarios"]),
        "candidate_binding": contract["candidate_binding"],
        "verification_boundary": contract["verification_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_runtime_matrix(project_root: Path, matrix_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("runtime_state_matrices", {})
    if not isinstance(records, dict) or matrix_id not in records or not isinstance(records[matrix_id], dict):
        raise ValueError(f"Runtime-state matrix is not recorded: {matrix_id}")
    record = dict(records[matrix_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[matrix_id] = record
    settings["runtime_state_matrices"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "runtime-state-matrix-retired", {"matrix_id": matrix_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _read_evidence(project_root: Path, forge_root: Path, raw_path: str | Path) -> tuple[dict[str, Any], str, str]:
    path, relative = _source(project_root, forge_root, raw_path, "Runtime-state evidence")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Runtime-state evidence is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise ValueError("Runtime-state evidence must be an object using schema 1.")
    return raw, relative, _sha(path)


def _runtime_results(capability_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for capability in capability_results:
        if not isinstance(capability, dict) or capability.get("capability_id") != "runtime-proof":
            continue
        for evaluation in capability.get("evaluations", []):
            if isinstance(evaluation, dict) and evaluation.get("recipe_id"):
                rows[str(evaluation["recipe_id"])] = evaluation
    return rows


def evaluate_runtime_matrices(
    project_root: Path,
    forge_root: Path,
    capability_results: list[dict[str, Any]],
    evidence_paths: list[str] | None = None,
) -> dict[str, Any]:
    evidence_by_key: dict[tuple[str, str], tuple[dict[str, Any], str, str]] = {}
    findings: list[dict[str, Any]] = []
    for raw_path in evidence_paths or []:
        try:
            evidence, source, digest = _read_evidence(project_root, forge_root, raw_path)
        except ValueError as exc:
            findings.append({"check": "core.runtime-state-matrix", "severity": "blocker", "path": str(raw_path), "line": 0, "message": str(exc)})
            continue
        key = (str(evidence.get("matrix_id", "")), str(evidence.get("scenario_id", "")))
        if not all(key):
            findings.append({"check": "core.runtime-state-matrix", "severity": "blocker", "path": source, "line": 0, "message": "Runtime-state evidence requires matrix_id and scenario_id."})
            continue
        if key in evidence_by_key:
            findings.append({"check": "core.runtime-state-matrix", "severity": "blocker", "path": source, "line": 0, "message": f"Duplicate runtime-state evidence for {key[0]}/{key[1]}."})
            continue
        evidence_by_key[key] = (evidence, source, digest)

    runtime = _runtime_results(capability_results)
    evaluations: list[dict[str, Any]] = []
    active_count = 0
    scenario_count = 0
    confirmed_count = 0
    not_run_count = 0
    for matrix_id, record in sorted(runtime_matrix_records(project_root).items()):
        if record.get("status") == "retired":
            continue
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        source = str(record.get("contract_source", ""))
        if record.get("lifecycle_status") != "active":
            evaluations.append({"matrix_id": matrix_id, "title": contract.get("title", matrix_id), "status": "APPROVAL_REQUIRED", "reason": record.get("reason", "Authority approval is not current."), "contract_source": source, "scenarios": []})
            findings.append({"check": "core.runtime-state-matrix", "severity": "blocker", "path": source or ".", "line": 0, "message": f"Runtime-state matrix {matrix_id} is not current: {record.get('reason', 'authority approval required')}"})
            continue
        active_count += 1
        scenario_rows: list[dict[str, Any]] = []
        matrix_failed = False
        for scenario in contract.get("scenarios", []):
            if not isinstance(scenario, dict):
                continue
            scenario_count += 1
            scenario_id = str(scenario.get("scenario_id", ""))
            evidence_entry = evidence_by_key.pop((matrix_id, scenario_id), None)
            if evidence_entry is None:
                not_run_count += 1
                scenario_rows.append({"scenario_id": scenario_id, "status": "NOT_RUN", "truth_state": "NOT_RUN", "reason": "No authority or CI runtime-state evidence was supplied for this scenario.", "verification_tier": scenario.get("verification_tier", "sandbox")})
                continue
            evidence, evidence_source, evidence_digest = evidence_entry
            reasons: list[str] = []
            authority = str(evidence.get("authority", "")).strip()
            if authority not in scenario.get("evidence_authorities", []):
                reasons.append(f"evidence authority {authority or '(missing)'} is not permitted")
            if evidence.get("candidate_binding") != contract.get("candidate_binding"):
                reasons.append("candidate binding does not match the recorded matrix candidate")
            if str(evidence.get("target_environment", "")) != str(scenario.get("target_environment", "")):
                reasons.append("target environment does not match the scenario")
            if str(evidence.get("deployment_stage", "")).lower() != str(scenario.get("deployment_stage", "")):
                reasons.append("deployment stage does not match the scenario")
            if str(evidence.get("prior_state_id", "")) != str(scenario.get("prior_state", {}).get("state_id", "")):
                reasons.append("prior persisted-state identity does not match the scenario")
            if evidence.get("baseline_value") != scenario.get("baseline_value"):
                reasons.append("baseline binding does not match the scenario")
            if str(evidence.get("deployment_result", "")).upper() != "PASS":
                reasons.append("deployment evidence did not report PASS")
            migration_results = evidence.get("migration_results", []) if isinstance(evidence.get("migration_results"), list) else []
            migration_map = {str(row.get("path", "")): row for row in migration_results if isinstance(row, dict)}
            for migration in scenario.get("migrations", []):
                row = migration_map.get(str(migration.get("path", "")), {})
                if str(row.get("status", "")).upper() != "PASS" or row.get("sha256") != migration.get("sha256"):
                    reasons.append(f"migration evidence is missing, failed, or stale for {migration.get('path', '')}")
            recipe_results: list[dict[str, Any]] = []
            for recipe_id in scenario.get("runtime_recipe_ids", []):
                result = runtime.get(str(recipe_id))
                if not result:
                    reasons.append(f"required runtime recipe was not executed in this Check: {recipe_id}")
                    recipe_results.append({"recipe_id": recipe_id, "status": "NOT_RUN"})
                elif result.get("status") != "PASS":
                    reasons.append(f"required runtime recipe did not pass: {recipe_id}")
                    recipe_results.append({"recipe_id": recipe_id, "status": result.get("status", "UNKNOWN")})
                elif TIER_RANK.get(str(result.get("verification_tier", "sandbox")), 0) < TIER_RANK.get(str(scenario.get("verification_tier", "sandbox")), 0):
                    reasons.append(f"required runtime recipe tier is below the scenario tier: {recipe_id}")
                    recipe_results.append({"recipe_id": recipe_id, "status": "INSUFFICIENT_TIER", "verification_tier": result.get("verification_tier", "sandbox")})
                else:
                    recipe_results.append({"recipe_id": recipe_id, "status": "PASS", "verification_tier": result.get("verification_tier", "sandbox"), "response_sha256": result.get("observed", {}).get("response_sha256", "")})
            passed = not reasons
            if passed:
                confirmed_count += 1
            else:
                matrix_failed = True
                findings.append({"check": "core.runtime-state-matrix", "severity": "blocker", "path": evidence_source, "line": 0, "message": f"Runtime-state scenario {matrix_id}/{scenario_id} failed: {'; '.join(reasons)}."})
            scenario_rows.append({
                "scenario_id": scenario_id,
                "status": "PASS" if passed else "FAIL",
                "truth_state": "CONFIRMED" if passed else "CONTRADICTED",
                "verification_tier": scenario.get("verification_tier", "sandbox"),
                "target_environment": scenario.get("target_environment", ""),
                "deployment_stage": scenario.get("deployment_stage", ""),
                "prior_state_id": scenario.get("prior_state", {}).get("state_id", ""),
                "baseline_value": scenario.get("baseline_value"),
                "evidence_source": evidence_source,
                "evidence_sha256": evidence_digest,
                "authority": authority,
                "runtime_recipes": recipe_results,
                "reason": "; ".join(reasons),
                "exclusions": scenario.get("exclusions", []),
            })
        matrix_status = "FAIL" if matrix_failed else ("NOT_RUN" if scenario_rows and all(row.get("status") == "NOT_RUN" for row in scenario_rows) else "PASS")
        evaluations.append({"matrix_id": matrix_id, "title": contract.get("title", matrix_id), "status": matrix_status, "contract_source": source, "candidate_binding": contract.get("candidate_binding", {}), "scenarios": scenario_rows, "verification_boundary": contract.get("verification_boundary", "")})

    for (matrix_id, scenario_id), (_, source, _) in evidence_by_key.items():
        findings.append({"check": "core.runtime-state-matrix", "severity": "blocker", "path": source, "line": 0, "message": f"Runtime-state evidence references an unrecorded or inactive scenario: {matrix_id}/{scenario_id}."})

    status = "FAIL" if any(item.get("severity") == "blocker" for item in findings) else ("NOT_RUN" if scenario_count and confirmed_count == 0 and not_run_count == scenario_count else "PASS")
    return {
        "schema": 1,
        "status": status,
        "active_count": active_count,
        "scenario_count": scenario_count,
        "confirmed_count": confirmed_count,
        "not_run_count": not_run_count,
        "evaluations": evaluations,
        "findings": findings,
        "truth_boundary": "A passing scenario confirms only that authority-bound deployment and migration testimony matches the exact recorded candidate, baseline, prior-state identity, current migration bytes, and same-Check runtime recipes. Forge did not perform the deployment, restore persisted state, execute migrations, inspect secrets, or certify release readiness.",
    }


def runtime_matrix_summary(project_root: Path) -> dict[str, Any]:
    active = attention = retired = scenarios = 0
    for record in runtime_matrix_records(project_root).values():
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        if record.get("status") == "retired":
            retired += 1
        elif record.get("lifecycle_status") == "active":
            active += 1
            scenarios += len(contract.get("scenarios", [])) if isinstance(contract.get("scenarios"), list) else 0
        else:
            attention += 1
    return {"schema": 1, "active": active, "attention": attention, "retired": retired, "scenarios": scenarios, "truth_boundary": "The summary reports current matrix authority and scenario counts only; Check evaluates supplied evidence against current candidate and runtime results."}

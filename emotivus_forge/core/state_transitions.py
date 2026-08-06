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
from .semantic_state import evaluate_semantic_validators, validate_semantic_validators
from .state import load_settings
from .truth import TIER_RANK, normalize_verification_tier

TRANSITION_SCHEMA = 2
SUPPORTED_TRANSITION_SCHEMAS = {1, 2}
STAGES = {"local", "sandbox", "staging", "production"}
EVIDENCE_AUTHORITIES = {"owner", "external-ci"}
COMPARISON_MODES = {"exact", "semantic", "exact-and-semantic"}
ROLLBACK_REQUIREMENTS = {"none", "availability", "drill"}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Persisted-state transition requires {label}.")
    return text


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _project_file(project_root: Path, raw: Any, label: str) -> tuple[Path, str]:
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
            raise ValueError(f"Persisted-state candidate field is unavailable in the active project identity: {field}")
    if isinstance(current, (dict, list)):
        return json.loads(json.dumps(current, sort_keys=True, ensure_ascii=False))
    return current


def _bound_file(project_root: Path, raw: Any, label: str) -> dict[str, str]:
    path, relative = _project_file(project_root, raw, label)
    return {"path": relative, "sha256": _sha(path)}


def _state_contract(project_root: Path, raw: dict[str, Any], label: str) -> dict[str, Any]:
    mode = str(raw.get("comparison_mode", "exact")).strip().lower()
    if mode not in COMPARISON_MODES:
        raise ValueError(f"{label}.comparison_mode must be one of {sorted(COMPARISON_MODES)}.")
    validators = validate_semantic_validators(raw.get("semantic_validators", []), f"{label}.semantic_validators")
    if mode in {"semantic", "exact-and-semantic"} and not validators:
        raise ValueError(f"{label} requires semantic_validators when comparison_mode is {mode}.")
    return {
        "state_id": _required(raw.get("state_id"), f"{label}.state_id"),
        "description": _required(raw.get("description"), f"{label}.description", minimum=12),
        "fixture": _bound_file(project_root, raw.get("fixture_path"), f"{label}.fixture_path"),
        "comparison_mode": mode,
        "semantic_validators": validators,
    }


def _coverage_contract(raw: Any, transition_ids: set[str]) -> list[dict[str, Any]]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ValueError("coverage_requirements must be an array.")
    if len(raw) > 30:
        raise ValueError("coverage_requirements may contain at most 30 entries.")
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"coverage_requirements[{index}] must be an object.")
        coverage_id = _required(item.get("coverage_id"), f"coverage_requirements[{index}].coverage_id")
        if coverage_id in seen:
            raise ValueError(f"Duplicate coverage_id: {coverage_id}")
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in coverage_id):
            raise ValueError("coverage_id may contain only lowercase letters, numbers, hyphens, and underscores.")
        seen.add(coverage_id)
        description = _required(item.get("description"), f"coverage_requirements[{index}].description", minimum=12)
        mode = str(item.get("mode", "all")).strip().lower()
        if mode not in {"all", "any"}:
            raise ValueError(f"coverage_requirements[{index}].mode must be all or any.")
        required_ids = _string_list(item.get("transition_ids"), f"coverage_requirements[{index}].transition_ids", required=True, limit=20)
        unknown = sorted(set(required_ids) - transition_ids)
        if unknown:
            raise ValueError(f"coverage requirement {coverage_id} references unknown transition(s): {', '.join(unknown)}")
        rows.append({"coverage_id": coverage_id, "description": description, "mode": mode, "transition_ids": required_ids})
    return rows


def validate_state_transition_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source(project_root, forge_root, source_path, "Persisted-state transition contract")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Persisted-state transition contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") not in SUPPORTED_TRANSITION_SCHEMAS:
        raise ValueError("Persisted-state transition contract must be an object using schema 1 or 2.")
    plan_id = _required(raw.get("plan_id"), "plan_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in plan_id):
        raise ValueError("plan_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    identity_record = project_identity_record(project_root)
    if identity_record.get("status") != "active":
        raise ValueError("Persisted-state transition requires a current owner-recorded project identity.")
    identity = identity_record.get("identity", {}) if isinstance(identity_record.get("identity"), dict) else {}
    candidate_fields = _string_list(raw.get("candidate_fields"), "candidate_fields", required=True, limit=20)
    candidate_binding = {field: _lookup_identity(identity, field) for field in candidate_fields}

    transitions_raw = raw.get("transitions")
    if not isinstance(transitions_raw, list) or not transitions_raw:
        raise ValueError("Persisted-state transition contract requires a non-empty transitions array.")
    if len(transitions_raw) > 20:
        raise ValueError("Persisted-state transition contract may contain at most 20 transitions.")
    transition_ids: set[str] = set()
    transitions: list[dict[str, Any]] = []
    for index, item in enumerate(transitions_raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"transitions[{index}] must be an object.")
        transition_id = _required(item.get("transition_id"), f"transitions[{index}].transition_id")
        if transition_id in transition_ids:
            raise ValueError(f"Duplicate persisted-state transition_id: {transition_id}")
        transition_ids.add(transition_id)
        target_environment = _required(item.get("target_environment"), f"transitions[{index}].target_environment", minimum=3)
        stage = str(item.get("deployment_stage", "")).strip().lower()
        if stage not in STAGES:
            raise ValueError(f"transitions[{index}].deployment_stage must be one of {sorted(STAGES)}.")
        tier = normalize_verification_tier(item.get("verification_tier"), default=stage if stage in {"staging", "production"} else "sandbox")
        baseline_field = _required(item.get("baseline_field", "baseline.build_id"), f"transitions[{index}].baseline_field")
        baseline_value = _lookup_identity(identity, baseline_field)

        before = item.get("before_state")
        after = item.get("expected_after_state")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError(f"transitions[{index}] requires before_state and expected_after_state objects.")
        before_state = _state_contract(project_root, before, f"transitions[{index}].before_state")
        after_state = _state_contract(project_root, after, f"transitions[{index}].expected_after_state")
        artifact = _bound_file(project_root, item.get("deployment_artifact_path"), f"transitions[{index}].deployment_artifact_path")
        migrations: list[dict[str, str]] = []
        for raw_migration in _string_list(item.get("migration_paths", []), f"transitions[{index}].migration_paths", limit=30):
            migrations.append(_bound_file(project_root, raw_migration, f"transitions[{index}].migration_paths"))
        runtime_recipe_ids = _string_list(item.get("runtime_recipe_ids"), f"transitions[{index}].runtime_recipe_ids", required=True, limit=20)
        evidence_authorities = _string_list(item.get("evidence_authorities", ["owner", "external-ci"]), f"transitions[{index}].evidence_authorities", required=True, limit=2)
        if any(value not in EVIDENCE_AUTHORITIES for value in evidence_authorities):
            raise ValueError(f"transitions[{index}].evidence_authorities may contain only owner or external-ci.")
        rollback_raw = item.get("rollback", {})
        if not isinstance(rollback_raw, dict):
            raise ValueError(f"transitions[{index}].rollback must be an object.")
        requirement = str(rollback_raw.get("requirement", "")).strip().lower()
        if not requirement:
            requirement = "drill" if bool(rollback_raw.get("required", False)) else "none"
        if requirement not in ROLLBACK_REQUIREMENTS:
            raise ValueError(f"transitions[{index}].rollback.requirement must be one of {sorted(ROLLBACK_REQUIREMENTS)}.")
        rollback_recipes = _string_list(rollback_raw.get("runtime_recipe_ids", []), f"transitions[{index}].rollback.runtime_recipe_ids", required=requirement == "drill", limit=20)
        rollback = {
            "requirement": requirement,
            "required": requirement != "none",
            "availability_required": requirement in {"availability", "drill"},
            "drill_required": requirement == "drill",
            "restored_state_id": _required(rollback_raw.get("restored_state_id", before_state["state_id"]), f"transitions[{index}].rollback.restored_state_id"),
            "runtime_recipe_ids": rollback_recipes,
        }
        exclusions = _string_list(item.get("exclusions"), f"transitions[{index}].exclusions", required=True, limit=20)
        transitions.append({
            "transition_id": transition_id,
            "target_environment": target_environment,
            "deployment_stage": stage,
            "verification_tier": tier,
            "baseline_field": baseline_field,
            "baseline_value": baseline_value,
            "before_state": before_state,
            "expected_after_state": after_state,
            "deployment_artifact": artifact,
            "migrations": migrations,
            "runtime_recipe_ids": runtime_recipe_ids,
            "evidence_authorities": evidence_authorities,
            "rollback": rollback,
            "exclusions": exclusions,
        })
    coverage_requirements = _coverage_contract(raw.get("coverage_requirements", []), transition_ids)
    verification_boundary = _required(raw.get("verification_boundary"), "verification_boundary", minimum=50)
    contract = {
        "schema": TRANSITION_SCHEMA,
        "source_schema": raw.get("schema"),
        "plan_id": plan_id,
        "title": title,
        "authority": authority,
        "candidate_fields": candidate_fields,
        "candidate_binding": candidate_binding,
        "identity_contract_fingerprint": identity_record.get("contract_fingerprint", ""),
        "transitions": transitions,
        "coverage_requirements": coverage_requirements,
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
        missing_reason="The project-owned persisted-state transition source is missing.",
        changed_reason="The project-owned persisted-state transition contract changed after authority approval.",
    )
    if current.get("lifecycle_status") != "active":
        return current
    identity = project_identity_record(project_root)
    if identity.get("status") != "active":
        return {**current, "lifecycle_status": "approval-required", "status": "approval-required", "reason": "The project identity is not current."}
    contract = current.get("contract", {}) if isinstance(current.get("contract"), dict) else {}
    if contract.get("identity_contract_fingerprint") != identity.get("contract_fingerprint"):
        return {**current, "lifecycle_status": "approval-required", "status": "approval-required", "reason": "The project identity changed after the persisted-state transition was recorded."}
    for transition in contract.get("transitions", []):
        if not isinstance(transition, dict):
            continue
        bound_files = [
            transition.get("before_state", {}).get("fixture", {}),
            transition.get("expected_after_state", {}).get("fixture", {}),
            transition.get("deployment_artifact", {}),
            *transition.get("migrations", []),
        ]
        for bound in bound_files:
            if not isinstance(bound, dict):
                continue
            rel = str(bound.get("path", ""))
            path = project_root / rel
            if not path.is_file() or path.is_symlink() or _sha(path) != bound.get("sha256"):
                return {**current, "lifecycle_status": "approval-required", "status": "approval-required", "reason": f"Bound transition input changed after approval: {rel}"}
    return current


def state_transition_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("state_transition_plans", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_state_transition(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_state_transition_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.get("state_transition_plans", {})
    if not isinstance(records, dict):
        records = {}
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "plan_id": contract["plan_id"],
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[contract["plan_id"]] = record
    settings["state_transition_plans"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "state-transition-plan-recorded", {
        "plan_id": contract["plan_id"],
        "title": contract["title"],
        "authority": contract["authority"],
        "transition_count": len(contract["transitions"]),
        "candidate_binding": contract["candidate_binding"],
        "verification_boundary": contract["verification_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_state_transition(project_root: Path, plan_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("state_transition_plans", {})
    if not isinstance(records, dict) or plan_id not in records or not isinstance(records[plan_id], dict):
        raise ValueError(f"Persisted-state transition plan is not recorded: {plan_id}")
    record = dict(records[plan_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[plan_id] = record
    settings["state_transition_plans"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "state-transition-plan-retired", {"plan_id": plan_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _read_json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise ValueError(f"{label} must be an object using schema 1.")
    return raw


def _runtime_results(capability_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for capability in capability_results:
        if not isinstance(capability, dict) or capability.get("capability_id") != "runtime-proof":
            continue
        for evaluation in capability.get("evaluations", []):
            if isinstance(evaluation, dict) and evaluation.get("recipe_id"):
                rows[str(evaluation["recipe_id"])] = evaluation
    return rows


def _recipe_checks(runtime: dict[str, dict[str, Any]], recipe_ids: list[str], tier: str, reasons: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for recipe_id in recipe_ids:
        result = runtime.get(recipe_id)
        if not result:
            reasons.append(f"required runtime recipe was not executed in this Check: {recipe_id}")
            rows.append({"recipe_id": recipe_id, "status": "NOT_RUN"})
        elif result.get("status") != "PASS":
            reasons.append(f"required runtime recipe did not pass: {recipe_id}")
            rows.append({"recipe_id": recipe_id, "status": result.get("status", "UNKNOWN")})
        elif TIER_RANK.get(str(result.get("verification_tier", "sandbox")), 0) < TIER_RANK.get(tier, 0):
            reasons.append(f"required runtime recipe tier is below the transition tier: {recipe_id}")
            rows.append({"recipe_id": recipe_id, "status": "INSUFFICIENT_TIER", "verification_tier": result.get("verification_tier", "sandbox")})
        else:
            rows.append({"recipe_id": recipe_id, "status": "PASS", "verification_tier": result.get("verification_tier", "sandbox"), "response_sha256": result.get("observed", {}).get("response_sha256", "")})
    return rows


def _validate_receipt(receipt: dict[str, Any], *, kind: str, transition: dict[str, Any], contract: dict[str, Any], project_root: Path, reasons: list[str]) -> dict[str, Any]:
    if receipt.get("kind") != kind:
        reasons.append(f"{kind} has the wrong kind")
    if receipt.get("candidate_binding") != contract.get("candidate_binding"):
        reasons.append(f"{kind} candidate binding does not match")
    if receipt.get("target_environment") != transition.get("target_environment"):
        reasons.append(f"{kind} target environment does not match")
    if str(receipt.get("deployment_stage", "")).lower() != transition.get("deployment_stage"):
        reasons.append(f"{kind} deployment stage does not match")
    if receipt.get("baseline_value") != transition.get("baseline_value"):
        reasons.append(f"{kind} baseline does not match")
    if str(receipt.get("result", "")).upper() != "PASS":
        reasons.append(f"{kind} did not report PASS")
    observed_utc = str(receipt.get("observed_utc", "")).strip()
    if not observed_utc:
        reasons.append(f"{kind} requires observed_utc")
    artifact = transition.get("deployment_artifact", {}) if isinstance(transition.get("deployment_artifact"), dict) else {}
    if kind == "deployment-receipt":
        if receipt.get("artifact_path") != artifact.get("path"):
            reasons.append("deployment-receipt artifact path does not match")
        artifact_path = project_root / str(artifact.get("path", ""))
        current_digest = _sha(artifact_path) if artifact_path.is_file() and not artifact_path.is_symlink() else ""
        if receipt.get("artifact_sha256") != artifact.get("sha256") or current_digest != artifact.get("sha256"):
            reasons.append("deployment-receipt artifact digest is missing or stale")
    return {"kind": kind, "observed_utc": observed_utc}


def _snapshot_evaluation(project_root: Path, raw_path: Any, label: str, state_contract: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    relative = digest = ""
    semantic: dict[str, Any] = {"status": "NOT_CONFIGURED", "passed": 0, "failed": 0, "results": []}
    try:
        path, relative = _project_file(project_root, raw_path, label)
        digest = _sha(path)
        mode = str(state_contract.get("comparison_mode", "exact"))
        expected_digest = str(state_contract.get("fixture", {}).get("sha256", ""))
        if mode in {"exact", "exact-and-semantic"} and digest != expected_digest:
            reasons.append(f"{label} does not match the recorded exact fixture")
        validators = state_contract.get("semantic_validators", []) if isinstance(state_contract.get("semantic_validators"), list) else []
        if mode in {"semantic", "exact-and-semantic"}:
            semantic = evaluate_semantic_validators(path, validators)
            if semantic.get("status") != "PASS":
                reasons.append(f"{label} failed semantic validation: {semantic.get('reason', 'semantic validator failure')}")
    except ValueError as exc:
        reasons.append(str(exc))
    return {
        "path": relative,
        "sha256": digest,
        "comparison_mode": state_contract.get("comparison_mode", "exact"),
        "semantic": semantic,
    }


def _coverage_evaluation(requirements: list[dict[str, Any]], transition_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_by_id = {str(row.get("transition_id", "")): str(row.get("status", "UNKNOWN")) for row in transition_rows if isinstance(row, dict)}
    rows: list[dict[str, Any]] = []
    counts = {"PASS": 0, "PARTIAL": 0, "NOT_RUN": 0, "FAIL": 0}
    for requirement in requirements:
        transition_ids = [str(item) for item in requirement.get("transition_ids", [])]
        statuses = [status_by_id.get(item, "UNKNOWN") for item in transition_ids]
        mode = str(requirement.get("mode", "all"))
        if mode == "any":
            if any(value == "PASS" for value in statuses):
                status = "PASS"
            elif statuses and all(value == "NOT_RUN" for value in statuses):
                status = "NOT_RUN"
            elif statuses and all(value == "FAIL" for value in statuses):
                status = "FAIL"
            else:
                status = "PARTIAL"
        else:
            if statuses and all(value == "PASS" for value in statuses):
                status = "PASS"
            elif any(value == "FAIL" for value in statuses):
                status = "FAIL"
            elif statuses and all(value == "NOT_RUN" for value in statuses):
                status = "NOT_RUN"
            else:
                status = "PARTIAL"
        counts[status] += 1
        rows.append({
            "coverage_id": requirement.get("coverage_id", ""),
            "description": requirement.get("description", ""),
            "mode": mode,
            "transition_ids": transition_ids,
            "transition_statuses": statuses,
            "status": status,
        })
    return {"requirements": rows, "counts": counts, "required_count": len(rows), "confirmed_count": counts["PASS"], "not_run_count": counts["NOT_RUN"], "partial_count": counts["PARTIAL"], "failed_count": counts["FAIL"]}

def evaluate_state_transitions(
    project_root: Path,
    forge_root: Path,
    capability_results: list[dict[str, Any]],
    evidence_paths: list[str] | None = None,
) -> dict[str, Any]:
    evidence_by_key: dict[tuple[str, str], tuple[dict[str, Any], str, str]] = {}
    findings: list[dict[str, Any]] = []
    for raw_path in evidence_paths or []:
        try:
            path, source = _source(project_root, forge_root, raw_path, "Persisted-state transition evidence")
            evidence = _read_json_file(path, "Persisted-state transition evidence")
            digest = _sha(path)
        except ValueError as exc:
            findings.append({"check": "core.state-transition", "severity": "blocker", "path": str(raw_path), "line": 0, "message": str(exc)})
            continue
        key = (str(evidence.get("plan_id", "")), str(evidence.get("transition_id", "")))
        if not all(key):
            findings.append({"check": "core.state-transition", "severity": "blocker", "path": source, "line": 0, "message": "Persisted-state transition evidence requires plan_id and transition_id."})
            continue
        if key in evidence_by_key:
            findings.append({"check": "core.state-transition", "severity": "blocker", "path": source, "line": 0, "message": f"Duplicate persisted-state evidence for {key[0]}/{key[1]}."})
            continue
        evidence_by_key[key] = (evidence, source, digest)

    runtime = _runtime_results(capability_results)
    evaluations: list[dict[str, Any]] = []
    active_count = transition_count = confirmed_count = not_run_count = partial_plan_count = 0
    rollback_availability_confirmed_count = rollback_drill_confirmed_count = rollback_correctness_confirmed_count = 0
    coverage_required_count = coverage_confirmed_count = coverage_not_run_count = coverage_partial_count = 0
    for plan_id, record in sorted(state_transition_records(project_root).items()):
        if record.get("status") == "retired":
            continue
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        source = str(record.get("contract_source", ""))
        if record.get("lifecycle_status") != "active":
            evaluations.append({"plan_id": plan_id, "title": contract.get("title", plan_id), "status": "APPROVAL_REQUIRED", "reason": record.get("reason", "Authority approval is not current."), "contract_source": source, "transitions": [], "coverage": {}})
            findings.append({"check": "core.state-transition", "severity": "blocker", "path": source or ".", "line": 0, "message": f"Persisted-state transition plan {plan_id} is not current: {record.get('reason', 'authority approval required')}"})
            continue
        active_count += 1
        transition_rows: list[dict[str, Any]] = []
        plan_failed = False
        for transition in contract.get("transitions", []):
            if not isinstance(transition, dict):
                continue
            transition_count += 1
            transition_id = str(transition.get("transition_id", ""))
            rollback_contract = transition.get("rollback", {}) if isinstance(transition.get("rollback"), dict) else {}
            rollback_requirement = str(rollback_contract.get("requirement", "drill" if rollback_contract.get("required") else "none"))
            evidence_entry = evidence_by_key.pop((plan_id, transition_id), None)
            if evidence_entry is None:
                not_run_count += 1
                transition_rows.append({
                    "transition_id": transition_id,
                    "status": "NOT_RUN",
                    "truth_state": "NOT_RUN",
                    "reason": "No owner or external-CI state-transition evidence was supplied.",
                    "verification_tier": transition.get("verification_tier", "sandbox"),
                    "rollback": {"requirement": rollback_requirement, "availability_status": "NOT_RUN" if rollback_requirement != "none" else "NOT_REQUIRED", "drill_status": "NOT_RUN" if rollback_requirement == "drill" else "NOT_REQUIRED", "post_rollback_correctness": "NOT_RUN" if rollback_requirement == "drill" else "NOT_REQUIRED"},
                })
                continue
            evidence, evidence_source, evidence_digest = evidence_entry
            reasons: list[str] = []
            authority = str(evidence.get("authority", "")).strip()
            if authority not in transition.get("evidence_authorities", []):
                reasons.append(f"evidence authority {authority or '(missing)'} is not permitted")
            if evidence.get("candidate_binding") != contract.get("candidate_binding"):
                reasons.append("candidate binding does not match the transition plan")
            if evidence.get("target_environment") != transition.get("target_environment"):
                reasons.append("target environment does not match the transition")
            if str(evidence.get("deployment_stage", "")).lower() != transition.get("deployment_stage"):
                reasons.append("deployment stage does not match the transition")
            if evidence.get("baseline_value") != transition.get("baseline_value"):
                reasons.append("baseline binding does not match the transition")
            if str(evidence.get("transition_result", "")).upper() != "PASS":
                reasons.append("state transition did not report PASS")

            before_eval = _snapshot_evaluation(project_root, evidence.get("before_snapshot_path"), "before-state snapshot", transition.get("before_state", {}), reasons)
            after_eval = _snapshot_evaluation(project_root, evidence.get("after_snapshot_path"), "after-state snapshot", transition.get("expected_after_state", {}), reasons)
            receipt_relative = ""
            deployment_receipt: dict[str, Any] = {}
            receipt_path: Path | None = None
            try:
                receipt_path, receipt_relative = _project_file(project_root, evidence.get("deployment_receipt_path"), "deployment_receipt_path")
                receipt = _read_json_file(receipt_path, "Deployment receipt")
                deployment_receipt = _validate_receipt(receipt, kind="deployment-receipt", transition=transition, contract=contract, project_root=project_root, reasons=reasons)
            except ValueError as exc:
                reasons.append(str(exc))

            migration_results = evidence.get("migration_results", []) if isinstance(evidence.get("migration_results"), list) else []
            migration_map = {str(row.get("path", "")): row for row in migration_results if isinstance(row, dict)}
            for migration in transition.get("migrations", []):
                row = migration_map.get(str(migration.get("path", "")), {})
                if str(row.get("status", "")).upper() != "PASS" or row.get("sha256") != migration.get("sha256"):
                    reasons.append(f"migration evidence is missing, failed, or stale for {migration.get('path', '')}")

            runtime_rows = _recipe_checks(runtime, list(transition.get("runtime_recipe_ids", [])), str(transition.get("verification_tier", "sandbox")), reasons)
            rollback = evidence.get("rollback") if isinstance(evidence.get("rollback"), dict) else {}
            availability_status = "NOT_REQUIRED" if rollback_requirement == "none" else "NOT_RUN"
            drill_status = "NOT_REQUIRED" if rollback_requirement != "drill" else "NOT_RUN"
            correctness_status = "NOT_REQUIRED" if rollback_requirement != "drill" else "NOT_RUN"
            availability_receipt_relative = availability_receipt_digest = ""
            restored_eval: dict[str, Any] = {"path": "", "sha256": "", "comparison_mode": transition.get("before_state", {}).get("comparison_mode", "exact"), "semantic": {"status": "NOT_CONFIGURED", "passed": 0, "failed": 0, "results": []}}
            rollback_receipt_relative = rollback_receipt_digest = ""
            rollback_runtime: list[dict[str, Any]] = []
            if rollback_requirement == "availability" or str(rollback.get("availability_receipt_path", "")).strip():
                try:
                    availability_path, availability_receipt_relative = _project_file(project_root, rollback.get("availability_receipt_path"), "rollback availability receipt")
                    availability_receipt = _read_json_file(availability_path, "Rollback availability receipt")
                    availability_receipt_digest = _sha(availability_path)
                    availability_reasons_before = len(reasons)
                    _validate_receipt(availability_receipt, kind="rollback-availability-receipt", transition=transition, contract=contract, project_root=project_root, reasons=reasons)
                    if not str(availability_receipt.get("rollback_method", "")).strip():
                        reasons.append("rollback-availability-receipt requires rollback_method")
                    availability_status = "PASS" if len(reasons) == availability_reasons_before else "FAIL"
                except ValueError as exc:
                    reasons.append(str(exc))
                    availability_status = "FAIL"
            if rollback_requirement == "drill":
                drill_reasons_before = len(reasons)
                if not rollback:
                    reasons.append("required rollback evidence was not supplied")
                if str(rollback.get("result", "")).upper() != "PASS":
                    reasons.append("rollback drill did not report PASS")
                restored_eval = _snapshot_evaluation(project_root, rollback.get("restored_snapshot_path"), "rollback restored-state snapshot", transition.get("before_state", {}), reasons)
                try:
                    rollback_receipt_path, rollback_receipt_relative = _project_file(project_root, rollback.get("receipt_path"), "rollback.receipt_path")
                    rollback_receipt = _read_json_file(rollback_receipt_path, "Rollback receipt")
                    rollback_receipt_digest = _sha(rollback_receipt_path)
                    _validate_receipt(rollback_receipt, kind="rollback-receipt", transition=transition, contract=contract, project_root=project_root, reasons=reasons)
                    if rollback_receipt.get("from_state_id") != transition.get("expected_after_state", {}).get("state_id"):
                        reasons.append("rollback-receipt from_state_id does not match the expected after-state")
                    if rollback_receipt.get("restored_state_id") != rollback_contract.get("restored_state_id"):
                        reasons.append("rollback-receipt restored_state_id does not match the contract")
                except ValueError as exc:
                    reasons.append(str(exc))
                rollback_runtime = _recipe_checks(runtime, list(rollback_contract.get("runtime_recipe_ids", [])), str(transition.get("verification_tier", "sandbox")), reasons)
                drill_status = "PASS" if len(reasons) == drill_reasons_before else "FAIL"
                if drill_status == "PASS":
                    availability_status = "PASS"
                correctness_status = "PASS" if restored_eval.get("semantic", {}).get("status") in {"PASS", "NOT_CONFIGURED"} and not any("restored-state snapshot" in reason for reason in reasons) else "FAIL"

            passed = not reasons
            if passed:
                confirmed_count += 1
                if rollback_requirement in {"availability", "drill"}:
                    rollback_availability_confirmed_count += 1
                if rollback_requirement == "drill":
                    rollback_drill_confirmed_count += 1
                    rollback_correctness_confirmed_count += 1
            else:
                plan_failed = True
                findings.append({"check": "core.state-transition", "severity": "blocker", "path": evidence_source, "line": 0, "message": f"Persisted-state transition {plan_id}/{transition_id} failed: {'; '.join(reasons)}."})
            transition_rows.append({
                "transition_id": transition_id,
                "status": "PASS" if passed else "FAIL",
                "truth_state": "CONFIRMED" if passed else "CONTRADICTED",
                "verification_tier": transition.get("verification_tier", "sandbox"),
                "target_environment": transition.get("target_environment", ""),
                "deployment_stage": transition.get("deployment_stage", ""),
                "baseline_value": transition.get("baseline_value"),
                "before_state_id": transition.get("before_state", {}).get("state_id", ""),
                "after_state_id": transition.get("expected_after_state", {}).get("state_id", ""),
                "before_snapshot": before_eval,
                "after_snapshot": after_eval,
                "deployment_artifact": transition.get("deployment_artifact", {}),
                "deployment_receipt_path": receipt_relative,
                "deployment_receipt_sha256": _sha(receipt_path) if receipt_path is not None else "",
                "deployment_receipt": deployment_receipt,
                "authority": authority,
                "evidence_source": evidence_source,
                "evidence_sha256": evidence_digest,
                "runtime_recipes": runtime_rows,
                "rollback": {
                    "required": rollback_requirement != "none",
                    "requirement": rollback_requirement,
                    "status": ("NOT_REQUIRED" if rollback_requirement == "none" else (availability_status if rollback_requirement == "availability" else drill_status)),
                    "availability_status": availability_status,
                    "availability_receipt_path": availability_receipt_relative,
                    "availability_receipt_sha256": availability_receipt_digest,
                    "drill_status": drill_status,
                    "post_rollback_correctness": correctness_status,
                    "restored_snapshot": restored_eval,
                    "receipt_path": rollback_receipt_relative,
                    "receipt_sha256": rollback_receipt_digest,
                    "runtime_recipes": rollback_runtime,
                },
                "reason": "; ".join(reasons),
                "exclusions": transition.get("exclusions", []),
            })
        coverage = _coverage_evaluation(contract.get("coverage_requirements", []), transition_rows)
        coverage_required_count += coverage.get("required_count", 0)
        coverage_confirmed_count += coverage.get("confirmed_count", 0)
        coverage_not_run_count += coverage.get("not_run_count", 0)
        coverage_partial_count += coverage.get("partial_count", 0)
        statuses = [str(row.get("status", "UNKNOWN")) for row in transition_rows]
        if plan_failed or coverage.get("failed_count", 0):
            plan_status = "FAIL"
        elif statuses and all(value == "NOT_RUN" for value in statuses):
            plan_status = "NOT_RUN"
        elif statuses and all(value == "PASS" for value in statuses) and coverage.get("partial_count", 0) == 0 and coverage.get("not_run_count", 0) == 0:
            plan_status = "PASS"
        else:
            plan_status = "PARTIAL"
            partial_plan_count += 1
        evaluations.append({"plan_id": plan_id, "title": contract.get("title", plan_id), "status": plan_status, "contract_source": source, "transitions": transition_rows, "coverage": coverage, "verification_boundary": contract.get("verification_boundary", "")})

    for (plan_id, transition_id), (_, source, _) in evidence_by_key.items():
        findings.append({"check": "core.state-transition", "severity": "blocker", "path": source, "line": 0, "message": f"Evidence references an unknown or inactive persisted-state transition: {plan_id}/{transition_id}."})
    status = "FAIL" if any(item.get("severity") == "blocker" for item in findings) else "PASS"
    return {
        "schema": 2,
        "status": status,
        "active_count": active_count,
        "transition_count": transition_count,
        "confirmed_count": confirmed_count,
        "not_run_count": not_run_count,
        "partial_plan_count": partial_plan_count,
        "rollback_confirmed_count": rollback_drill_confirmed_count,
        "rollback_availability_confirmed_count": rollback_availability_confirmed_count,
        "rollback_drill_confirmed_count": rollback_drill_confirmed_count,
        "rollback_correctness_confirmed_count": rollback_correctness_confirmed_count,
        "coverage_required_count": coverage_required_count,
        "coverage_confirmed_count": coverage_confirmed_count,
        "coverage_not_run_count": coverage_not_run_count,
        "coverage_partial_count": coverage_partial_count,
        "evaluations": evaluations,
        "findings": findings,
        "truth_boundary": "A passing transition confirms only that authority-bound snapshots, safe project-owned JSON semantic validators, migration testimony, exact artifact receipt, candidate and baseline bindings, same-Check runtime recipes, and the declared rollback availability or drill evidence agree. Forge did not deploy, migrate, restore, execute arbitrary validators, inspect hidden database contents, or certify release readiness.",
    }

def state_transition_summary(project_root: Path) -> dict[str, Any]:
    active = attention = retired = transitions = rollback_required = rollback_availability = rollback_drill = semantic_states = coverage_requirements = 0
    for record in state_transition_records(project_root).values():
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        if record.get("status") == "retired":
            retired += 1
        elif record.get("lifecycle_status") == "active":
            active += 1
            rows = contract.get("transitions", []) if isinstance(contract.get("transitions"), list) else []
            transitions += len(rows)
            coverage_requirements += len(contract.get("coverage_requirements", [])) if isinstance(contract.get("coverage_requirements"), list) else 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                rollback = row.get("rollback", {}) if isinstance(row.get("rollback"), dict) else {}
                requirement = str(rollback.get("requirement", "drill" if rollback.get("required") else "none"))
                if requirement != "none":
                    rollback_required += 1
                    rollback_availability += 1
                if requirement == "drill":
                    rollback_drill += 1
                for state_key in ("before_state", "expected_after_state"):
                    state = row.get(state_key, {}) if isinstance(row.get(state_key), dict) else {}
                    if state.get("comparison_mode") in {"semantic", "exact-and-semantic"}:
                        semantic_states += 1
        else:
            attention += 1
    return {
        "schema": 2,
        "active": active,
        "attention": attention,
        "retired": retired,
        "transitions": transitions,
        "rollback_required": rollback_required,
        "rollback_availability": rollback_availability,
        "rollback_drill": rollback_drill,
        "semantic_states": semantic_states,
        "coverage_requirements": coverage_requirements,
        "truth_boundary": "The summary reports current transition authority and compact counts only; Check evaluates supplied snapshots, semantic invariants, receipts, coverage, candidate, artifact, migration, and runtime evidence.",
    }


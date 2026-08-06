from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import normalize_rel, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .release_package import evaluate_release_package
from .state import load_settings

CONTRACT_SCHEMA = 2
RECEIPT_SCHEMA = 2
RATINGS = {"correct", "partial", "incorrect"}
REVIEWERS = {"owner", "human-reviewer", "external-reviewer", "controlled-fixture"}
HUMAN_REVIEWERS = {"owner", "human-reviewer", "external-reviewer"}
INDEPENDENT_REVIEWERS = {"external-reviewer"}
SCENARIOS = {"first-contact", "continuation", "defect-investigation", "release-packaging", "custom"}
ARM_ORDERS = {"randomized", "forge-first", "control-first"}
HEX = set("0123456789abcdef")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Cold-session validation requires {label}.")
    return text


def _identifier(value: Any, label: str) -> str:
    text = _required(value, label)
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in text):
        raise ValueError(f"{label} may contain only lowercase letters, numbers, hyphens, and underscores.")
    return text


def _digest(value: Any, label: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(char not in HEX for char in text):
        raise ValueError(f"{label} must be an exact lowercase SHA-256 digest.")
    return text


def _parse_utc(value: Any, label: str) -> datetime:
    text = _required(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be timezone-aware ISO 8601.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware ISO 8601.")
    return parsed.astimezone(timezone.utc)


def _source(project_root: Path, forge_root: Path, raw: str | Path, label: str) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError(f"{label} must be a project-owned file outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return raw


def _positive_int(value: Any, label: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer of at least {minimum}.")
    return value


def validate_cold_session_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    source, relative = _source(project_root, forge_root, source_path, "Cold-session validation contract")
    raw = _read_json(source, "Cold-session validation contract")
    if raw.get("schema") != CONTRACT_SCHEMA:
        raise ValueError("Cold-session validation contract must use schema 2; schema 1 cannot establish real matched-trial release evidence.")
    validation_id = _identifier(raw.get("validation_id"), "validation_id")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    host_release_package_id = _identifier(raw.get("host_release_package_id"), "host_release_package_id")

    runtime_path, runtime_rel = _source(
        project_root, forge_root, raw.get("forge_runtime_artifact_path", ""), "Forge runtime artifact"
    )
    runtime_sha = sha256_file(runtime_path)
    runtime_bytes = runtime_path.stat().st_size

    minimum_pairs = _positive_int(raw.get("minimum_pairs", 3), "minimum_pairs")
    minimum_models = _positive_int(raw.get("minimum_models", 1), "minimum_models")
    minimum_tasks = _positive_int(raw.get("minimum_distinct_task_packets", 2), "minimum_distinct_task_packets")
    minimum_baselines = _positive_int(raw.get("minimum_distinct_host_baselines", 1), "minimum_distinct_host_baselines")
    minimum_external = raw.get("minimum_external_review_pairs", 0)
    if isinstance(minimum_external, bool) or not isinstance(minimum_external, int) or minimum_external < 0:
        raise ValueError("minimum_external_review_pairs must be a non-negative integer.")
    if minimum_external > minimum_pairs:
        raise ValueError("minimum_external_review_pairs cannot exceed minimum_pairs.")
    maximum_age = _positive_int(raw.get("maximum_receipt_age_days", 45), "maximum_receipt_age_days")
    if maximum_age > 365:
        raise ValueError("maximum_receipt_age_days cannot exceed 365.")

    scenarios_raw = raw.get("required_scenarios")
    if not isinstance(scenarios_raw, list) or not scenarios_raw:
        raise ValueError("required_scenarios must be a non-empty array.")
    scenarios: list[str] = []
    for item in scenarios_raw:
        scenario = str(item or "").strip()
        if scenario not in SCENARIOS:
            raise ValueError(f"Unsupported cold-session scenario: {scenario}")
        if scenario not in scenarios:
            scenarios.append(scenario)

    receipts_raw = raw.get("pair_receipts")
    if not isinstance(receipts_raw, list) or not receipts_raw:
        raise ValueError("pair_receipts must be a non-empty array.")
    receipts: list[str] = []
    for item in receipts_raw:
        _, receipt_rel = _source(project_root, forge_root, item, "Cold-session pair receipt")
        if receipt_rel in receipts:
            raise ValueError(f"Cold-session pair receipt is listed more than once: {receipt_rel}")
        receipts.append(receipt_rel)

    thresholds = raw.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object.")
    max_incorrect_objective = thresholds.get("max_forge_incorrect_objective_rate", 0.0)
    max_incorrect_first_action = thresholds.get("max_forge_incorrect_first_action_rate", 0.0)
    max_owner_corrections = thresholds.get("max_forge_owner_corrections_per_pair", 2.0)
    for value, label in (
        (max_incorrect_objective, "max_forge_incorrect_objective_rate"),
        (max_incorrect_first_action, "max_forge_incorrect_first_action_rate"),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise ValueError(f"{label} must be a number from 0 to 1.")
    if isinstance(max_owner_corrections, bool) or not isinstance(max_owner_corrections, (int, float)) or float(max_owner_corrections) < 0:
        raise ValueError("max_forge_owner_corrections_per_pair must be non-negative.")
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=80)

    contract = {
        "schema": CONTRACT_SCHEMA,
        "validation_id": validation_id,
        "title": title,
        "authority": authority,
        "host_release_package_id": host_release_package_id,
        "forge_runtime": {
            "artifact_path": runtime_rel,
            "artifact_sha256": runtime_sha,
            "artifact_bytes": runtime_bytes,
        },
        "minimum_pairs": minimum_pairs,
        "minimum_models": minimum_models,
        "minimum_distinct_task_packets": minimum_tasks,
        "minimum_distinct_host_baselines": minimum_baselines,
        "minimum_external_review_pairs": minimum_external,
        "maximum_receipt_age_days": maximum_age,
        "required_scenarios": scenarios,
        "pair_receipts": receipts,
        "thresholds": {
            "max_forge_incorrect_objective_rate": float(max_incorrect_objective),
            "max_forge_incorrect_first_action_rate": float(max_incorrect_first_action),
            "max_forge_owner_corrections_per_pair": float(max_owner_corrections),
        },
        "truth_boundary": truth_boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(
        project_root,
        record,
        changed_status="approval-required",
        missing_reason="The project-owned cold-session validation contract is missing.",
        changed_reason="The project-owned cold-session validation contract changed after authority approval.",
    )


def cold_session_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("cold_session_validations", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_cold_session_validation(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_cold_session_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.get("cold_session_validations", {})
    if not isinstance(records, dict):
        records = {}
    for identifier, existing in records.items():
        if identifier == contract["validation_id"] or not isinstance(existing, dict):
            continue
        if existing.get("lifecycle_status", existing.get("status")) == "active":
            raise ValueError(f"Only one active cold-session validation may exist; retire {identifier} first.")
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "validation_id": contract["validation_id"],
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[contract["validation_id"]] = record
    settings["cold_session_validations"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "cold-session-validation-recorded", {
        "validation_id": contract["validation_id"],
        "host_release_package_id": contract["host_release_package_id"],
        "forge_runtime_sha256": contract["forge_runtime"]["artifact_sha256"],
        "minimum_pairs": contract["minimum_pairs"],
        "minimum_models": contract["minimum_models"],
        "required_scenarios": contract["required_scenarios"],
        "truth_boundary": contract["truth_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_cold_session_validation(project_root: Path, validation_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("cold_session_validations", {})
    if not isinstance(records, dict) or validation_id not in records or not isinstance(records[validation_id], dict):
        raise ValueError(f"Cold-session validation is not recorded: {validation_id}")
    record = dict(records[validation_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[validation_id] = record
    settings["cold_session_validations"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "cold-session-validation-retired", {"validation_id": validation_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _bound_file(project_root: Path, raw_path: Any, raw_sha: Any, label: str) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    relative = str(raw_path or "").strip()
    expected = str(raw_sha or "").strip().lower()
    candidate = (project_root / relative).resolve() if relative else Path()
    if not relative or not _inside(candidate, project_root) or _inside(candidate, project_root / ".forge") or not candidate.is_file() or candidate.is_symlink():
        reasons.append(f"{label}_path is missing or unsafe.")
        actual = ""
    else:
        actual = sha256_file(candidate)
    if len(expected) != 64 or any(char not in HEX for char in expected):
        reasons.append(f"{label}_sha256 must be an exact lowercase SHA-256 digest.")
    elif actual and actual != expected:
        reasons.append(f"{label}_sha256 is stale or incorrect.")
    return {"path": relative, "sha256": expected}, reasons


def _arm(project_root: Path, raw: Any, label: str) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    if not isinstance(raw, dict):
        return {}, [f"{label} must be an object."]
    objective = str(raw.get("objective_recovery", "")).strip()
    first_action = str(raw.get("first_action", "")).strip()
    if objective not in RATINGS:
        reasons.append(f"{label}.objective_recovery is invalid.")
    if first_action not in RATINGS:
        reasons.append(f"{label}.first_action is invalid.")
    corrections = raw.get("owner_corrections", 0)
    if isinstance(corrections, bool) or not isinstance(corrections, int) or corrections < 0:
        reasons.append(f"{label}.owner_corrections must be a non-negative integer.")
        corrections = 0
    minutes = raw.get("time_to_meaningful_minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or float(minutes) < 0:
        reasons.append(f"{label}.time_to_meaningful_minutes must be non-negative.")
        minutes = 0.0
    evidence, evidence_reasons = _bound_file(project_root, raw.get("evidence_path"), raw.get("evidence_sha256"), f"{label}.evidence")
    reasons.extend(evidence_reasons)
    input_tokens = raw.get("input_tokens")
    output_tokens = raw.get("output_tokens")
    for value, name in ((input_tokens, "input_tokens"), (output_tokens, "output_tokens")):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            reasons.append(f"{label}.{name} must be a non-negative integer when supplied.")
    return {
        "objective_recovery": objective,
        "first_action": first_action,
        "owner_corrections": corrections,
        "time_to_meaningful_minutes": float(minutes),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "evidence_path": evidence["path"],
        "evidence_sha256": evidence["sha256"],
    }, reasons


def _pair_receipt(
    project_root: Path,
    relative: str,
    *,
    validation_id: str,
    host_release_package_id: str,
    host_package_sha: str,
    host_package_bytes: int,
    forge_runtime_sha: str,
    forge_runtime_bytes: int,
    maximum_age_days: int,
) -> dict[str, Any]:
    path = project_root / relative
    try:
        raw = _read_json(path, "Cold-session pair receipt")
    except ValueError as exc:
        return {"status": "FAIL", "path": relative, "reason": str(exc)}
    reasons: list[str] = []
    if raw.get("schema") != RECEIPT_SCHEMA:
        reasons.append("Cold-session pair receipt must use schema 2.")
    pair_id = str(raw.get("pair_id", "")).strip()
    if not pair_id:
        reasons.append("Cold-session pair receipt requires pair_id.")
    if str(raw.get("validation_id", "")) != validation_id:
        reasons.append("Cold-session pair validation_id does not match.")
    if str(raw.get("host_release_package_id", "")) != host_release_package_id:
        reasons.append("Cold-session pair host_release_package_id does not match.")
    if str(raw.get("host_package_sha256", "")) != host_package_sha or raw.get("host_package_bytes") != host_package_bytes:
        reasons.append("Cold-session pair does not bind to the exact host release package.")
    if str(raw.get("forge_runtime_sha256", "")) != forge_runtime_sha or raw.get("forge_runtime_bytes") != forge_runtime_bytes:
        reasons.append("Cold-session pair does not bind to the exact Forge runtime artifact.")

    observed_text = str(raw.get("observed_utc", "")).strip()
    try:
        observed = _parse_utc(observed_text, "Cold-session pair observed_utc")
        age_days = (datetime.now(timezone.utc) - observed).total_seconds() / 86400
        if age_days < -0.01:
            reasons.append("Cold-session pair observed_utc cannot be in the future.")
        elif age_days > maximum_age_days:
            reasons.append("Cold-session pair evidence is older than the contract permits.")
    except ValueError as exc:
        reasons.append(str(exc))
        age_days = None

    provider = str(raw.get("provider", "")).strip()
    model = str(raw.get("model", "")).strip()
    settings_fingerprint = str(raw.get("model_settings_fingerprint", "")).strip().lower()
    scenario = str(raw.get("scenario", "")).strip()
    reviewer_role = str(raw.get("reviewer_role", "")).strip()
    reviewer_id = str(raw.get("reviewer_id", "")).strip()
    arm_order = str(raw.get("arm_order", "")).strip()
    forge_session_id = str(raw.get("forge_session_id", "")).strip()
    control_session_id = str(raw.get("control_session_id", "")).strip()
    if not provider:
        reasons.append("Cold-session pair requires provider.")
    if not model:
        reasons.append("Cold-session pair requires model.")
    if len(settings_fingerprint) != 64 or any(char not in HEX for char in settings_fingerprint):
        reasons.append("Cold-session pair model_settings_fingerprint must be an exact lowercase SHA-256 digest.")
    if scenario not in SCENARIOS:
        reasons.append("Cold-session pair scenario is invalid.")
    if reviewer_role not in REVIEWERS:
        reasons.append("Cold-session pair reviewer_role is invalid.")
    if not reviewer_id:
        reasons.append("Cold-session pair requires reviewer_id.")
    if arm_order not in ARM_ORDERS:
        reasons.append("Cold-session pair arm_order is invalid.")
    if not forge_session_id or not control_session_id or forge_session_id == control_session_id:
        reasons.append("Cold-session pair requires distinct non-empty forge_session_id and control_session_id values.")
    if raw.get("fresh_agents") is not True:
        reasons.append("Cold-session pair must confirm fresh_agents=true.")

    conditions = raw.get("matched_conditions")
    if not isinstance(conditions, dict):
        reasons.append("Cold-session pair matched_conditions must be an object.")
        conditions = {}
    for key in ("same_provider", "same_model", "same_model_settings", "same_task_packet", "isolated_sessions"):
        if conditions.get(key) is not True:
            reasons.append(f"Cold-session pair matched_conditions.{key} must be true.")
    if conditions.get("forge_arm_used_exact_runtime") is not True:
        reasons.append("Cold-session pair must confirm that the Forge arm used the exact bound runtime.")
    if conditions.get("control_arm_had_no_forge_access") is not True:
        reasons.append("Cold-session pair must confirm that the control arm had no Forge access.")

    task_packet, task_reasons = _bound_file(project_root, raw.get("task_packet_path"), raw.get("task_packet_sha256"), "task_packet")
    baseline, baseline_reasons = _bound_file(project_root, raw.get("host_baseline_manifest_path"), raw.get("host_baseline_manifest_sha256"), "host_baseline_manifest")
    reasons.extend(task_reasons)
    reasons.extend(baseline_reasons)

    forge_arm, forge_reasons = _arm(project_root, raw.get("forge_arm"), "forge_arm")
    control_arm, control_reasons = _arm(project_root, raw.get("control_arm"), "control_arm")
    reasons.extend(forge_reasons)
    reasons.extend(control_reasons)
    return {
        "status": "PASS" if not reasons else "FAIL",
        "path": relative,
        "pair_id": pair_id,
        "provider": provider,
        "model": model,
        "model_settings_fingerprint": settings_fingerprint,
        "scenario": scenario,
        "reviewer_role": reviewer_role,
        "reviewer_id": reviewer_id,
        "human_reviewed": reviewer_role in HUMAN_REVIEWERS,
        "independent_review": reviewer_role in INDEPENDENT_REVIEWERS,
        "arm_order": arm_order,
        "task_packet_sha256": task_packet["sha256"],
        "host_baseline_sha256": baseline["sha256"],
        "age_days": round(age_days, 3) if isinstance(age_days, float) else None,
        "forge_arm": forge_arm,
        "control_arm": control_arm,
        "reason": "Matched fresh-agent pair is current, arm-equivalent, isolated, human-classified, and bound to the exact host package and Forge runtime." if not reasons else " ".join(reasons),
    }


def evaluate_cold_session_validation(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    records = cold_session_records(project_root)
    active = [row for row in records.values() if row.get("lifecycle_status") == "active"]
    if not active:
        return {
            "schema": CONTRACT_SCHEMA,
            "status": "NOT_RUN",
            "pair_count": 0,
            "minimum_pairs": 0,
            "model_count": 0,
            "minimum_models": 0,
            "truth_boundary": "No cold-session validation contract is active.",
        }
    if len(active) > 1:
        return {
            "schema": CONTRACT_SCHEMA,
            "status": "FAIL",
            "pair_count": 0,
            "minimum_pairs": 0,
            "model_count": 0,
            "minimum_models": 0,
            "reason": "Only one active cold-session validation contract may establish the Ship claim.",
            "truth_boundary": "Matched observations remain bounded local evidence.",
        }
    record = active[0]
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    if contract.get("schema") != CONTRACT_SCHEMA:
        return {
            "schema": CONTRACT_SCHEMA,
            "status": "UPGRADE_REQUIRED",
            "validation_id": contract.get("validation_id", ""),
            "pair_count": 0,
            "minimum_pairs": contract.get("minimum_pairs", 0),
            "model_count": 0,
            "minimum_models": contract.get("minimum_models", 0),
            "reason": "Legacy schema-1 cold-session evidence lacks runtime separation, arm-equivalence, age, and real-review safeguards; record a schema-2 contract.",
            "truth_boundary": str(contract.get("truth_boundary", "Cold-session validation remains bounded.")),
        }
    if record.get("status") != "active":
        return {
            "schema": CONTRACT_SCHEMA,
            "status": "FAIL",
            "validation_id": contract.get("validation_id", ""),
            "pair_count": 0,
            "minimum_pairs": contract.get("minimum_pairs", 0),
            "model_count": 0,
            "minimum_models": contract.get("minimum_models", 0),
            "reason": str(record.get("reason", "Cold-session authority is not current.")),
            "truth_boundary": str(contract.get("truth_boundary", "Cold-session validation remains bounded.")),
        }

    runtime = contract.get("forge_runtime", {}) if isinstance(contract.get("forge_runtime"), dict) else {}
    runtime_path = project_root / str(runtime.get("artifact_path", ""))
    if not runtime_path.is_file() or runtime_path.is_symlink() or sha256_file(runtime_path) != str(runtime.get("artifact_sha256", "")) or runtime_path.stat().st_size != int(runtime.get("artifact_bytes", 0) or 0):
        return {
            "schema": CONTRACT_SCHEMA,
            "status": "FAIL",
            "validation_id": contract.get("validation_id", ""),
            "pair_count": 0,
            "minimum_pairs": contract.get("minimum_pairs", 0),
            "model_count": 0,
            "minimum_models": contract.get("minimum_models", 0),
            "reason": "The exact Forge runtime artifact changed or is missing after the validation contract was recorded.",
            "truth_boundary": str(contract.get("truth_boundary", "Cold-session validation remains bounded.")),
        }

    package_eval = evaluate_release_package(project_root)
    final_package = package_eval.get("final_package", {}) if isinstance(package_eval.get("final_package"), dict) else {}
    if final_package.get("status") != "PASS" or str(package_eval.get("release_package_id", "")) != str(contract.get("host_release_package_id", "")):
        return {
            "schema": CONTRACT_SCHEMA,
            "status": "NOT_RUN",
            "validation_id": contract.get("validation_id", ""),
            "pair_count": 0,
            "minimum_pairs": contract.get("minimum_pairs", 0),
            "model_count": 0,
            "minimum_models": contract.get("minimum_models", 0),
            "reason": "The exact host final-package claim must pass before cold-session evidence is assessed.",
            "truth_boundary": str(contract.get("truth_boundary", "Cold-session validation remains bounded.")),
        }

    receipts = [
        _pair_receipt(
            project_root,
            relative,
            validation_id=str(contract.get("validation_id", "")),
            host_release_package_id=str(contract.get("host_release_package_id", "")),
            host_package_sha=str(final_package.get("artifact_sha256", "")),
            host_package_bytes=int(final_package.get("artifact_bytes", 0) or 0),
            forge_runtime_sha=str(runtime.get("artifact_sha256", "")),
            forge_runtime_bytes=int(runtime.get("artifact_bytes", 0) or 0),
            maximum_age_days=int(contract.get("maximum_receipt_age_days", 45) or 45),
        )
        for relative in contract.get("pair_receipts", [])
    ]
    failed = [row for row in receipts if row.get("status") != "PASS"]
    passing = [row for row in receipts if row.get("status") == "PASS"]
    qualifying = [row for row in passing if row.get("human_reviewed") is True]
    fixtures = [row for row in passing if row.get("human_reviewed") is not True]
    independent = [row for row in qualifying if row.get("independent_review") is True]

    pair_ids = [str(row.get("pair_id", "")) for row in passing]
    duplicate_pair_ids = sorted({item for item in pair_ids if item and pair_ids.count(item) > 1})
    models = sorted({str(row.get("model", "")) for row in qualifying if str(row.get("model", ""))})
    scenarios = sorted({str(row.get("scenario", "")) for row in qualifying if str(row.get("scenario", ""))})
    tasks = sorted({str(row.get("task_packet_sha256", "")) for row in qualifying if str(row.get("task_packet_sha256", ""))})
    baselines = sorted({str(row.get("host_baseline_sha256", "")) for row in qualifying if str(row.get("host_baseline_sha256", ""))})
    required_scenarios = [str(item) for item in contract.get("required_scenarios", [])]
    missing_scenarios = [item for item in required_scenarios if item not in scenarios]

    pair_count = len(qualifying)
    incorrect_objectives = sum(1 for row in qualifying if row.get("forge_arm", {}).get("objective_recovery") == "incorrect")
    incorrect_first_actions = sum(1 for row in qualifying if row.get("forge_arm", {}).get("first_action") == "incorrect")
    corrections = sum(int(row.get("forge_arm", {}).get("owner_corrections", 0) or 0) for row in qualifying)
    objective_rate = incorrect_objectives / pair_count if pair_count else 0.0
    first_action_rate = incorrect_first_actions / pair_count if pair_count else 0.0
    corrections_per_pair = corrections / pair_count if pair_count else 0.0
    thresholds = contract.get("thresholds", {}) if isinstance(contract.get("thresholds"), dict) else {}
    threshold_failures: list[str] = []
    if objective_rate > float(thresholds.get("max_forge_incorrect_objective_rate", 0.0)):
        threshold_failures.append("Forge objective-recovery error rate exceeds the authority-approved threshold.")
    if first_action_rate > float(thresholds.get("max_forge_incorrect_first_action_rate", 0.0)):
        threshold_failures.append("Forge first-action error rate exceeds the authority-approved threshold.")
    if corrections_per_pair > float(thresholds.get("max_forge_owner_corrections_per_pair", 2.0)):
        threshold_failures.append("Forge owner-correction rate exceeds the authority-approved threshold.")
    if duplicate_pair_ids:
        threshold_failures.append("Duplicate pair_id values prevent matched-trial evidence from being counted independently.")

    coverage_missing: list[str] = []
    if pair_count < int(contract.get("minimum_pairs", 0)):
        coverage_missing.append("human-reviewed pair minimum")
    if len(models) < int(contract.get("minimum_models", 0)):
        coverage_missing.append("model coverage")
    if len(tasks) < int(contract.get("minimum_distinct_task_packets", 0)):
        coverage_missing.append("distinct task-packet coverage")
    if len(baselines) < int(contract.get("minimum_distinct_host_baselines", 0)):
        coverage_missing.append("distinct host-baseline coverage")
    if len(independent) < int(contract.get("minimum_external_review_pairs", 0)):
        coverage_missing.append("external-review coverage")
    if missing_scenarios:
        coverage_missing.append("required scenario coverage")

    if failed or threshold_failures:
        status = "FAIL"
    elif coverage_missing:
        status = "PARTIAL"
    else:
        status = "PASS"
    return {
        "schema": CONTRACT_SCHEMA,
        "status": status,
        "validation_id": contract.get("validation_id", ""),
        "pair_count": pair_count,
        "minimum_pairs": contract.get("minimum_pairs", 0),
        "fixture_pair_count": len(fixtures),
        "independent_pair_count": len(independent),
        "minimum_external_review_pairs": contract.get("minimum_external_review_pairs", 0),
        "model_count": len(models),
        "minimum_models": contract.get("minimum_models", 0),
        "task_packet_count": len(tasks),
        "minimum_distinct_task_packets": contract.get("minimum_distinct_task_packets", 0),
        "host_baseline_count": len(baselines),
        "minimum_distinct_host_baselines": contract.get("minimum_distinct_host_baselines", 0),
        "models": models,
        "scenarios": scenarios,
        "missing_scenarios": missing_scenarios,
        "coverage_missing": coverage_missing,
        "failed_receipts": len(failed),
        "forge_runtime_sha256": runtime.get("artifact_sha256", ""),
        "host_package_sha256": final_package.get("artifact_sha256", ""),
        "forge_objective_error_rate": round(objective_rate, 4),
        "forge_first_action_error_rate": round(first_action_rate, 4),
        "forge_owner_corrections_per_pair": round(corrections_per_pair, 4),
        "threshold_failures": threshold_failures,
        "receipts": receipts,
        "truth_boundary": str(contract.get("truth_boundary", "Matched observations are bounded field evidence, not universal or causal proof.")),
    }


def cold_session_summary(project_root: Path) -> dict[str, Any]:
    evaluation = evaluate_cold_session_validation(project_root)
    return {
        "schema": CONTRACT_SCHEMA,
        "status": evaluation.get("status", "NOT_RUN"),
        "pair_ratio": f"{evaluation.get('pair_count', 0)}/{evaluation.get('minimum_pairs', 0)}",
        "model_ratio": f"{evaluation.get('model_count', 0)}/{evaluation.get('minimum_models', 0)}",
        "task_ratio": f"{evaluation.get('task_packet_count', 0)}/{evaluation.get('minimum_distinct_task_packets', 0)}",
        "baseline_ratio": f"{evaluation.get('host_baseline_count', 0)}/{evaluation.get('minimum_distinct_host_baselines', 0)}",
        "fixture_pairs": evaluation.get("fixture_pair_count", 0),
        "missing_scenarios": len(evaluation.get("missing_scenarios", [])) if isinstance(evaluation.get("missing_scenarios"), list) else 0,
        "truth_boundary": "Compact matched cold-session status only; receipt evidence, identities, task packets, runtime digests, and token counts remain local.",
    }

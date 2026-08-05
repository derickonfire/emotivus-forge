from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from .common import normalize_rel, read_jsonl, unique_strings, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .state import load_settings
from .telemetry import record_metric

TRIAL_SCHEMA = 1
OBSERVATION_SCHEMA = 1
PROJECT_PROFILES = (
    "mature-native-tooling",
    "growing-weak-documentation",
    "small-new-project",
    "zip-multi-session",
    "custom",
)
SCENARIOS = (
    "first-contact",
    "continuation",
    "defect-investigation",
    "release-packaging",
    "custom",
)
RECOVERY_RATINGS = ("correct", "partial", "incorrect", "not-measured")
INGESTION_RATINGS = ("complete", "partial", "missed", "not-applicable", "not-measured")
DOCTOR_GROUND_TRUTH = ("needed", "not-needed", "not-measured")
DOCTOR_RESULT = ("recommended", "not-recommended", "not-measured")
DIAGNOSIS_RATINGS = ("correct", "partial", "incorrect", "not-applicable", "not-measured")
GUARDRAIL_GROUND_TRUTH = ("should-trigger", "should-not-trigger", "not-measured")
GUARDRAIL_RESULT = ("triggered", "not-triggered", "not-measured")
REVIEWER_ROLES = ("owner", "human-reviewer", "external-reviewer", "controlled-fixture")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required_string(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Field trial requires {label}.")
    return text


def _identifier(value: Any, label: str) -> str:
    text = _required_string(value, label)
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in text):
        raise ValueError(f"{label} may contain only lowercase letters, numbers, hyphens, and underscores.")
    return text


def _enum(value: Any, label: str, allowed: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    if text not in allowed:
        raise ValueError(f"{label} must be one of: {', '.join(allowed)}")
    return text


def _score(value: Any, label: str, *, optional: bool = True) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"{label} must be an integer from 1 to 5.")
    return value


def _nonnegative_number(value: Any, label: str, *, optional: bool = True) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{label} must be a non-negative number.")
    return float(value)


def _source_path(project_root: Path, forge_root: Path, raw_path: str | Path, *, label: str) -> tuple[Path, str]:
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


def _project_evidence_path(project_root: Path, forge_root: Path, raw: str, *, label: str) -> str:
    candidate = (project_root / raw).resolve()
    if not _inside(candidate, project_root) or _inside(candidate, project_root / ".forge"):
        raise ValueError(f"{label} is outside the project or inside .forge: {raw}")
    if _inside(candidate, forge_root):
        raise ValueError(f"{label} cannot point into the Forge distribution: {raw}")
    if not candidate.exists():
        raise ValueError(f"{label} does not exist: {raw}")
    return normalize_rel(candidate.relative_to(project_root))


def _fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_trial_contract(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source_path(project_root, forge_root.resolve(), contract_path, label="Field trial contract")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Field trial contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != TRIAL_SCHEMA:
        raise ValueError("Field trial contract must be an object using schema 1.")

    trial_id = _identifier(raw.get("trial_id"), "trial_id")
    title = _required_string(raw.get("title"), "title", minimum=8)
    authority = _required_string(raw.get("authority"), "authority")
    rationale = _required_string(raw.get("rationale"), "rationale", minimum=20)
    project_profile = _enum(raw.get("project_profile"), "project_profile", PROJECT_PROFILES)
    models = unique_strings(raw.get("models", []) if isinstance(raw.get("models"), list) else [])
    if not models:
        raise ValueError("Field trial requires at least one model label.")
    scenarios_raw = raw.get("scenarios")
    if not isinstance(scenarios_raw, list):
        raise ValueError("Field trial requires scenarios as an array.")
    scenarios = unique_strings(scenarios_raw)
    if not scenarios:
        raise ValueError("Field trial requires at least one scenario.")
    for scenario in scenarios:
        _enum(scenario, "scenario", SCENARIOS)
    truth_paths_raw = raw.get("ground_truth_paths")
    if not isinstance(truth_paths_raw, list) or not truth_paths_raw:
        raise ValueError("Field trial requires at least one ground_truth_paths entry.")
    truth_paths = [
        _project_evidence_path(project_root, forge_root.resolve(), str(item), label="Field trial ground truth path")
        for item in unique_strings(truth_paths_raw)
    ]
    minimum_observations = raw.get("minimum_observations", 3)
    if isinstance(minimum_observations, bool) or not isinstance(minimum_observations, int) or minimum_observations < 1:
        raise ValueError("minimum_observations must be an integer of at least 1.")
    measures = unique_strings(raw.get("measures", []) if isinstance(raw.get("measures"), list) else [])
    supported_measures = {
        "objective-recovery",
        "authority-discovery",
        "resume-usefulness",
        "owner-comprehension",
        "time-to-meaningful-work",
        "native-evidence-ingestion",
        "doctor-recommendation",
        "doctor-diagnosis",
        "guardrail-trigger",
        "contract-usability",
    }
    if not measures:
        raise ValueError("Field trial requires at least one measure.")
    unsupported = sorted(set(measures) - supported_measures)
    if unsupported:
        raise ValueError(f"Unsupported field trial measure(s): {', '.join(unsupported)}")
    truth_boundary = _required_string(raw.get("truth_boundary"), "truth_boundary", minimum=30)

    contract = {
        "schema": TRIAL_SCHEMA,
        "trial_id": trial_id,
        "title": title,
        "authority": authority,
        "rationale": rationale,
        "project_profile": project_profile,
        "models": models,
        "scenarios": scenarios,
        "ground_truth_paths": truth_paths,
        "minimum_observations": minimum_observations,
        "measures": measures,
        "truth_boundary": truth_boundary,
    }
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": _fingerprint(contract),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _record_status(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(
        project_root, record,
        changed_status="rerecord-required",
        missing_reason="The project-owned field trial contract source is missing.",
        changed_reason="The project-owned field trial contract changed after authority recorded it.",
    )


def trial_records(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root.resolve())
    raw = settings.get("field_trials", {}) if isinstance(settings, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {
        trial_id: _record_status(project_root.resolve(), record)
        for trial_id, record in raw.items()
        if isinstance(record, dict)
    }


def record_trial(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_trial_contract(project_root, forge_root, contract_path)
    contract = validated["contract"]
    trial_id = contract["trial_id"]
    settings = load_settings(project_root)
    rows = settings.get("field_trials", {})
    if not isinstance(rows, dict):
        rows = {}
    record = {
        "status": "active",
        "trial_id": trial_id,
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        **contract,
    }
    rows[trial_id] = record
    settings["field_trials"] = rows
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "field-trial-recorded", record, source="operator")
    record_metric(project_root, "field-trial-recorded", {
        "trial_id": trial_id,
        "project_profile": contract["project_profile"],
        "model_count": len(contract["models"]),
        "scenario_count": len(contract["scenarios"]),
        "measure_count": len(contract["measures"]),
    })
    return record


def retire_trial(project_root: Path, trial_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    project_root = project_root.resolve()
    trial_id = str(trial_id).strip()
    reason = str(reason).strip()
    authority = str(authority).strip()
    if not trial_id or not reason or not authority:
        raise ValueError("Retiring a field trial requires trial ID, reason, and authority.")
    settings = load_settings(project_root)
    rows = settings.get("field_trials", {})
    if not isinstance(rows, dict) or trial_id not in rows or not isinstance(rows[trial_id], dict):
        raise ValueError(f"Unknown field trial: {trial_id}")
    record = dict(rows[trial_id])
    record.update({"status": "retired", "retired_utc": utc_now(), "retired_reason": reason, "retired_authority": authority})
    rows[trial_id] = record
    settings["field_trials"] = rows
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "field-trial-retired", {
        "trial_id": trial_id,
        "reason": reason,
        "authority": authority,
        "contract_fingerprint": record.get("contract_fingerprint", ""),
    }, source="operator")
    return record


def _observation_outcomes(raw: dict[str, Any], project_root: Path, forge_root: Path) -> dict[str, Any]:
    outcomes = raw.get("outcomes")
    if not isinstance(outcomes, dict):
        raise ValueError("Field observation requires outcomes as an object.")
    objective = _enum(outcomes.get("objective_recovery", "not-measured"), "objective_recovery", RECOVERY_RATINGS)
    authority = _enum(outcomes.get("authority_discovery", "not-measured"), "authority_discovery", RECOVERY_RATINGS)
    native = _enum(outcomes.get("native_evidence_ingestion", "not-measured"), "native_evidence_ingestion", INGESTION_RATINGS)

    doctor_raw = outcomes.get("doctor", {})
    if not isinstance(doctor_raw, dict):
        raise ValueError("doctor outcome must be an object.")
    doctor = {
        "ground_truth": _enum(doctor_raw.get("ground_truth", "not-measured"), "doctor.ground_truth", DOCTOR_GROUND_TRUTH),
        "forge_result": _enum(doctor_raw.get("forge_result", "not-measured"), "doctor.forge_result", DOCTOR_RESULT),
        "diagnosis": _enum(doctor_raw.get("diagnosis", "not-measured"), "doctor.diagnosis", DIAGNOSIS_RATINGS),
    }
    guardrail_raw = outcomes.get("guardrail", {})
    if not isinstance(guardrail_raw, dict):
        raise ValueError("guardrail outcome must be an object.")
    guardrail = {
        "ground_truth": _enum(guardrail_raw.get("ground_truth", "not-measured"), "guardrail.ground_truth", GUARDRAIL_GROUND_TRUTH),
        "forge_result": _enum(guardrail_raw.get("forge_result", "not-measured"), "guardrail.forge_result", GUARDRAIL_RESULT),
    }
    evidence_paths_raw = outcomes.get("evidence_paths", [])
    if not isinstance(evidence_paths_raw, list):
        raise ValueError("outcomes.evidence_paths must be an array.")
    evidence_paths = [
        _project_evidence_path(project_root, forge_root, str(item), label="Field observation evidence path")
        for item in unique_strings(evidence_paths_raw)
    ]
    notes = str(outcomes.get("notes", "")).strip()
    return {
        "objective_recovery": objective,
        "authority_discovery": authority,
        "resume_usefulness_score": _score(outcomes.get("resume_usefulness_score"), "resume_usefulness_score"),
        "owner_comprehension_score": _score(outcomes.get("owner_comprehension_score"), "owner_comprehension_score"),
        "contract_usability_score": _score(outcomes.get("contract_usability_score"), "contract_usability_score"),
        "time_to_meaningful_work_minutes": _nonnegative_number(outcomes.get("time_to_meaningful_work_minutes"), "time_to_meaningful_work_minutes"),
        "native_evidence_ingestion": native,
        "doctor": doctor,
        "guardrail": guardrail,
        "evidence_paths": evidence_paths,
        "notes": notes,
    }


def validate_observation(project_root: Path, forge_root: Path, observation_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source_path(project_root, forge_root.resolve(), observation_path, label="Field observation")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Field observation is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != OBSERVATION_SCHEMA:
        raise ValueError("Field observation must be an object using schema 1.")
    observation_id = _identifier(raw.get("observation_id"), "observation_id")
    trial_id = _identifier(raw.get("trial_id"), "trial_id")
    reviewer = _required_string(raw.get("reviewer"), "reviewer")
    reviewer_role = _enum(raw.get("reviewer_role"), "reviewer_role", REVIEWER_ROLES)
    scenario = _enum(raw.get("scenario"), "scenario", SCENARIOS)
    model = _required_string(raw.get("model"), "model")
    task_id = _required_string(raw.get("task_id"), "task_id")
    trials = trial_records(project_root)
    trial = trials.get(trial_id)
    if not isinstance(trial, dict):
        raise ValueError(f"Field observation references unknown trial: {trial_id}")
    if trial.get("status") != "active":
        raise ValueError(f"Field trial {trial_id} is not active: {trial.get('reason', trial.get('status', 'unknown'))}")
    if model not in trial.get("models", []):
        raise ValueError(f"Model {model!r} is not declared by field trial {trial_id}.")
    if scenario not in trial.get("scenarios", []):
        raise ValueError(f"Scenario {scenario!r} is not declared by field trial {trial_id}.")
    if observation_id in _existing_observation_ids(project_root):
        raise ValueError(f"Field observation ID already exists: {observation_id}")
    outcomes = _observation_outcomes(raw, project_root, forge_root.resolve())
    observation = {
        "schema": OBSERVATION_SCHEMA,
        "observation_id": observation_id,
        "trial_id": trial_id,
        "task_id": task_id,
        "scenario": scenario,
        "model": model,
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "outcomes": outcomes,
        "truth_boundary": (
            "This observation is operator- or fixture-supplied field evidence. Forge validates its structure and aggregates it, "
            "but does not independently verify the reviewer judgment or generalize it beyond the observed sample."
        ),
    }
    return {
        "observation": observation,
        "source": relative,
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
        "trial_contract_fingerprint": trial.get("contract_fingerprint", ""),
    }


def _existing_observation_ids(project_root: Path) -> set[str]:
    ids: set[str] = set()
    for event in read_jsonl(ForgePaths(project_root).ledger):
        if event.get("kind") != "field-observation" or not isinstance(event.get("payload"), dict):
            continue
        value = str(event["payload"].get("observation_id", "")).strip()
        if value:
            ids.add(value)
    return ids


def record_observation(
    project_root: Path,
    forge_root: Path,
    observation_path: str | Path,
    *,
    session_event_id: str,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_observation(project_root, forge_root, observation_path)
    observation = validated["observation"]
    if observation["observation_id"] in _existing_observation_ids(project_root):
        raise ValueError(f"Field observation ID already exists: {observation['observation_id']}")
    payload = {
        **observation,
        "recorded_utc": utc_now(),
        "source": validated["source"],
        "source_fingerprint": validated["source_fingerprint"],
        "trial_contract_fingerprint": validated["trial_contract_fingerprint"],
        "session_event_id": session_event_id,
    }
    event = record_event(project_root, "field-observation", payload, source="operator")
    record_metric(project_root, "field-observation", {
        "event_id": event["id"],
        "observation_id": observation["observation_id"],
        "trial_id": observation["trial_id"],
        "scenario": observation["scenario"],
        "model": observation["model"],
        "reviewer_role": observation["reviewer_role"],
        "time_to_meaningful_work_minutes": observation["outcomes"].get("time_to_meaningful_work_minutes"),
    })
    return {"event_id": event["id"], **payload}


def _rate(rows: list[str], positive: str) -> dict[str, Any]:
    measured = [value for value in rows if value != "not-measured"]
    counts = {value: measured.count(value) for value in sorted(set(measured))}
    return {
        "measured": len(measured),
        "counts": counts,
        "positive_rate": round(measured.count(positive) / len(measured), 4) if measured else None,
    }


def _score_summary(values: list[int | None]) -> dict[str, Any]:
    measured = [float(value) for value in values if isinstance(value, int)]
    return {
        "measured": len(measured),
        "average": round(statistics.mean(measured), 3) if measured else None,
        "median": round(statistics.median(measured), 3) if measured else None,
    }


def _time_summary(values: list[float | None]) -> dict[str, Any]:
    measured = [float(value) for value in values if isinstance(value, (int, float))]
    return {
        "measured": len(measured),
        "average_minutes": round(statistics.mean(measured), 3) if measured else None,
        "median_minutes": round(statistics.median(measured), 3) if measured else None,
    }


def _binary_matrix(rows: list[tuple[str, str]], *, positive_truth: str, positive_result: str) -> dict[str, Any]:
    matrix = {"true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0}
    measured = 0
    for truth, result in rows:
        if "not-measured" in {truth, result}:
            continue
        measured += 1
        if truth == positive_truth and result == positive_result:
            matrix["true_positive"] += 1
        elif truth != positive_truth and result != positive_result:
            matrix["true_negative"] += 1
        elif truth != positive_truth and result == positive_result:
            matrix["false_positive"] += 1
        else:
            matrix["false_negative"] += 1
    tp = matrix["true_positive"]
    fp = matrix["false_positive"]
    fn = matrix["false_negative"]
    precision = round(tp / (tp + fp), 4) if tp + fp else None
    recall = round(tp / (tp + fn), 4) if tp + fn else None
    return {"measured": measured, "matrix": matrix, "precision": precision, "recall": recall}


def _observation_rows(project_root: Path, trial_id: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in read_jsonl(ForgePaths(project_root).ledger):
        if event.get("kind") != "field-observation" or not isinstance(event.get("payload"), dict):
            continue
        payload = event["payload"]
        if trial_id and payload.get("trial_id") != trial_id:
            continue
        rows.append(payload)
    return rows


def summarize_trial(project_root: Path, trial: dict[str, Any]) -> dict[str, Any]:
    trial_id = str(trial.get("trial_id", ""))
    rows = _observation_rows(project_root, trial_id)
    outcomes = [row.get("outcomes", {}) for row in rows if isinstance(row.get("outcomes"), dict)]
    minimum = int(trial.get("minimum_observations", 3) or 3)
    doctor_pairs = [
        (str(item.get("doctor", {}).get("ground_truth", "not-measured")), str(item.get("doctor", {}).get("forge_result", "not-measured")))
        for item in outcomes if isinstance(item.get("doctor"), dict)
    ]
    guardrail_pairs = [
        (str(item.get("guardrail", {}).get("ground_truth", "not-measured")), str(item.get("guardrail", {}).get("forge_result", "not-measured")))
        for item in outcomes if isinstance(item.get("guardrail"), dict)
    ]
    return {
        "trial_id": trial_id,
        "title": trial.get("title", trial_id),
        "status": trial.get("status", "unknown"),
        "project_profile": trial.get("project_profile", ""),
        "observation_count": len(rows),
        "minimum_observations": minimum,
        "sample_status": "minimum-met" if len(rows) >= minimum else "insufficient-observations",
        "models_observed": sorted({str(row.get("model", "")) for row in rows if str(row.get("model", ""))}),
        "scenarios_observed": sorted({str(row.get("scenario", "")) for row in rows if str(row.get("scenario", ""))}),
        "objective_recovery": _rate([str(item.get("objective_recovery", "not-measured")) for item in outcomes], "correct"),
        "authority_discovery": _rate([str(item.get("authority_discovery", "not-measured")) for item in outcomes], "correct"),
        "resume_usefulness": _score_summary([item.get("resume_usefulness_score") for item in outcomes]),
        "owner_comprehension": _score_summary([item.get("owner_comprehension_score") for item in outcomes]),
        "contract_usability": _score_summary([item.get("contract_usability_score") for item in outcomes]),
        "time_to_meaningful_work": _time_summary([item.get("time_to_meaningful_work_minutes") for item in outcomes]),
        "native_evidence_ingestion": _rate([str(item.get("native_evidence_ingestion", "not-measured")) for item in outcomes], "complete"),
        "doctor_recommendation": _binary_matrix(doctor_pairs, positive_truth="needed", positive_result="recommended"),
        "doctor_diagnosis": _rate([
            str(item.get("doctor", {}).get("diagnosis", "not-measured"))
            for item in outcomes if isinstance(item.get("doctor"), dict)
        ], "correct"),
        "guardrail_trigger": _binary_matrix(guardrail_pairs, positive_truth="should-trigger", positive_result="triggered"),
        "truth_boundary": (
            "Results describe only operator- or fixture-supplied observations in this project-local sample. "
            "They are not independent proof of causality, universal accuracy, commercial value, or release readiness."
        ),
    }


def field_trial_summary(project_root: Path) -> dict[str, Any]:
    records = trial_records(project_root.resolve())
    trials = [summarize_trial(project_root.resolve(), record) for record in records.values()]
    active = [item for item in trials if item.get("status") == "active"]
    attention = [item for item in trials if item.get("status") == "rerecord-required"]
    return {
        "schema": 1,
        "active": active,
        "attention": attention,
        "retired": [item for item in trials if item.get("status") == "retired"],
        "total_observations": sum(int(item.get("observation_count", 0) or 0) for item in trials),
        "truth_boundary": (
            "Forge records and aggregates field observations but does not grade itself, infer reviewer ground truth, "
            "or generalize project-local samples into universal product claims."
        ),
    }

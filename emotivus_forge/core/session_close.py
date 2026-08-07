from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .changes import detect_changes, snapshot_fingerprint
from .common import read_json, read_jsonl, unique_strings, utc_now, write_json
from .ledger import record_event
from .paths import ForgePaths
from .state import load_settings, load_state, save_state
from .telemetry import record_interaction_session, record_metric

SESSION_TYPES = (
    "code-increment",
    "decision-checkpoint",
    "audit",
    "release-candidate",
    "deployment",
)


def load_session_close_digest(path: Path) -> dict[str, Any]:
    """Load and validate a JSON session-close digest for the one-command 'leave' path
    (Run Forge --close), so a cold model can end a session without switching to a
    separate close workflow. A digest is the model's compact end-of-session record; raw
    transcripts are neither expected nor retained. Requires a non-empty next_action;
    session_type defaults to 'code-increment' and must be one of SESSION_TYPES. Returns
    the normalized close_data plus any optional continuity-export request. Raises
    ValueError with a plain-language reason on any malformed or missing-required input."""
    import json

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Session-close digest could not be read as JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Session-close digest must be a JSON object.")
    next_action = str(raw.get("next_action", "")).strip()
    if not next_action:
        raise ValueError("Session-close digest requires a non-empty next_action.")
    session_type = str(raw.get("session_type", "code-increment")).strip() or "code-increment"
    if session_type not in SESSION_TYPES:
        raise ValueError(f"session_type must be one of: {', '.join(SESSION_TYPES)}")

    def _str_list(value: Any) -> list[str]:
        return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []

    def _pair_list(value: Any) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    rows.append({str(k): str(v) for k, v in item.items()})
        return rows

    telemetry = raw.get("interaction_telemetry", {})
    close_data = {
        "session_type": session_type,
        "summary": str(raw.get("summary", "")),
        "completed_work": _str_list(raw.get("completed_work")),
        "decisions": _pair_list(raw.get("decisions")),
        "owner_facts": _pair_list(raw.get("owner_facts")),
        "unresolved_risks": _str_list(raw.get("unresolved_risks")),
        "next_action": next_action,
        "interaction_telemetry": telemetry if isinstance(telemetry, dict) else {},
        "field_observation_path": str(raw.get("field_observation_path", "")),
    }
    return {
        "close_data": close_data,
        "export_continuity_path": str(raw.get("export_continuity_path", "")).strip(),
        "development_package": str(raw.get("development_package", "")).strip(),
    }



def parse_durable_pairs(values: list[str], *, label: str, detail_label: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in values:
        text = str(raw).strip()
        if "::" not in text:
            raise ValueError(f"{label} must use TEXT::{detail_label.upper()}")
        primary, detail = (part.strip() for part in text.split("::", 1))
        if not primary or not detail:
            raise ValueError(f"{label} requires both text and {detail_label}")
        row = {"text": primary, detail_label: detail}
        if row not in rows:
            rows.append(row)
    return rows


def latest_session_close(project_root: Path) -> dict[str, Any] | None:
    events = read_jsonl(ForgePaths(project_root).ledger)
    for event in reversed(events):
        if event.get("kind") == "session-close" and isinstance(event.get("payload"), dict):
            return event
    return None


def assess_continuity(
    project_root: Path,
    *,
    current_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = latest_session_close(project_root)
    if event is None:
        return {
            "status": "not-established",
            "reason": "Continuity has not yet been established; this is expected until the first Session Close.",
            "event_id": "",
            "next_action": "",
            "session_type": "",
            "closed_utc": "",
            "confidence": "not-applicable",
        }
    payload = event.get("payload", {})
    recorded = payload.get("continuity_snapshot", {}) if isinstance(payload, dict) else {}
    recorded_fingerprint = str(recorded.get("fingerprint", "")) if isinstance(recorded, dict) else ""
    if current_snapshot is None:
        state = load_state(project_root)
        current_snapshot = state.get("snapshot", {}) if isinstance(state.get("snapshot"), dict) else {}
    current_fingerprint = snapshot_fingerprint(current_snapshot)
    truncated = bool(current_snapshot.get("truncated")) if isinstance(current_snapshot, dict) else False
    status = "current" if recorded_fingerprint and recorded_fingerprint == current_fingerprint else "stale"
    reason = (
        "The latest Session Close matches the current observed project state."
        if status == "current"
        else "The project state changed after the latest Session Close."
    )
    next_action = payload.get("next_action", {}) if isinstance(payload, dict) else {}
    return {
        "status": status,
        "reason": reason,
        "event_id": str(event.get("id", "")),
        "next_action": str(next_action.get("text", "")) if isinstance(next_action, dict) else "",
        "session_type": str(payload.get("session_type", "")) if isinstance(payload, dict) else "",
        "closed_utc": str(event.get("utc", "")),
        "confidence": "bounded" if truncated or bool(recorded.get("truncated")) else "high",
    }


def _check_summary(check_payload: dict[str, Any]) -> dict[str, Any]:
    native = check_payload.get("native_gate", {}) if isinstance(check_payload.get("native_gate"), dict) else {}
    findings = check_payload.get("findings", []) if isinstance(check_payload.get("findings"), list) else []
    scope = check_payload.get("claim_scope", {}) if isinstance(check_payload.get("claim_scope"), dict) else {}
    return {
        "status": str(check_payload.get("status", "UNKNOWN")),
        "claim": str(check_payload.get("claim", "Scoped Check")),
        "finding_count": len(findings),
        "findings": findings,
        "native_gate_status": str(native.get("status", "NOT_RUN")),
        "native_evidence_ref": (
            str(native.get("raw_evidence", {}).get("result", ""))
            if isinstance(native.get("raw_evidence"), dict)
            else ""
        ),
        "checkpointed": bool(check_payload.get("checkpointed")),
        "scope": scope,
        "truth_summary": check_payload.get("truth_summary", {}) if isinstance(check_payload.get("truth_summary"), dict) else {},
        "native_truth": native.get("truth", {}) if isinstance(native.get("truth"), dict) else {},
        "self_currency_status": str(check_payload.get("self_currency", {}).get("status", "UNKNOWN")) if isinstance(check_payload.get("self_currency"), dict) else "UNKNOWN",
    }


def build_session_close_preflight(
    *,
    session_type: str,
    next_action: str,
    completed_work: list[str],
    decisions: list[dict[str, str]],
    owner_facts: list[dict[str, str]],
    unresolved_risks: list[str],
    check_payload: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    normalized_next = " ".join(next_action.casefold().split())
    normalized_completed = {" ".join(item.casefold().split()) for item in completed_work}
    if normalized_next and normalized_next in normalized_completed:
        errors.append("The exact next action is also listed as completed work.")
    for index, item in enumerate(decisions, 1):
        if not str(item.get("text", "")).strip() or not str(item.get("rationale", "")).strip():
            errors.append(f"Decision {index} must include both text and rationale.")
    for index, item in enumerate(owner_facts, 1):
        if not str(item.get("text", "")).strip() or not str(item.get("impact", "")).strip():
            errors.append(f"Owner fact {index} must include both text and design impact.")
    check_status = str(check_payload.get("status", "UNKNOWN")) if isinstance(check_payload, dict) else "UNKNOWN"
    if session_type in {"release-candidate", "deployment"} and check_status != "PASS":
        warnings.append(
            f"This {session_type} Session Close has no passing scoped Check; recording it does not certify the release or deployment."
        )
    truth_summary = check_payload.get("truth_summary", {}) if isinstance(check_payload, dict) and isinstance(check_payload.get("truth_summary"), dict) else {}
    unresolved = int(truth_summary.get("unresolved_count", 0) or 0)
    if session_type in {"release-candidate", "deployment"} and unresolved:
        warnings.append(
            f"This {session_type} handoff contains {unresolved} unknown, stale, blocked, contradicted, or not-run truth-state record(s)."
        )
    if unresolved_risks and not next_action:
        errors.append("Unresolved risks require an exact next action.")
    status = "BLOCKED" if errors else "ATTENTION" if warnings else "READY"
    return {
        "schema": 1,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "capture": {
            "session_type": session_type,
            "completed_items": len(completed_work),
            "decisions": len(decisions),
            "owner_facts": len(owner_facts),
            "unresolved_risks": len(unresolved_risks),
            "check_status": check_status,
            "next_action": next_action,
        },
        "boundary": "Preflight checks internal consistency of the handoff; it does not prove the work or release is correct.",
    }


def close_session(
    project_root: Path,
    forge_root: Path,
    *,
    session_type: str,
    next_action: str,
    completed_work: list[str] | None = None,
    decisions: list[dict[str, str]] | None = None,
    owner_facts: list[dict[str, str]] | None = None,
    unresolved_risks: list[str] | None = None,
    summary: str = "",
    check_payload: dict[str, Any] | None = None,
    current_snapshot: dict[str, Any] | None = None,
    interaction_telemetry: dict[str, Any] | None = None,
    field_observation_path: str = "",
) -> dict[str, Any]:
    started = time.monotonic()
    project_root = project_root.resolve()
    session_type = str(session_type).strip()
    if session_type not in SESSION_TYPES:
        raise ValueError(f"session_type must be one of: {', '.join(SESSION_TYPES)}")
    next_action = str(next_action).strip()
    if not next_action:
        raise ValueError("Session Close requires an exact next action.")
    field_observation_path = str(field_observation_path).strip()
    completed = unique_strings(completed_work or [])
    risks = unique_strings(unresolved_risks or [])
    decision_rows = [item for item in (decisions or []) if isinstance(item, dict)]
    fact_rows = [item for item in (owner_facts or []) if isinstance(item, dict)]
    preflight = build_session_close_preflight(
        session_type=session_type,
        next_action=next_action,
        completed_work=completed,
        decisions=decision_rows,
        owner_facts=fact_rows,
        unresolved_risks=risks,
        check_payload=check_payload or {},
    )
    if preflight["status"] == "BLOCKED":
        raise ValueError("Session Close preflight blocked: " + " ".join(preflight["errors"]))
    if field_observation_path:
        from .field_trials import validate_observation
        validate_observation(project_root, forge_root, field_observation_path)
    if current_snapshot is None:
        state = load_state(project_root)
        settings = load_settings(project_root)
        changes = detect_changes(project_root, forge_root, state.get("snapshot", {}), settings)
        current_snapshot = changes["current_snapshot"]
        changed_paths = changes["paths"]
    else:
        changed_paths = []
        if isinstance(check_payload, dict):
            change_data = check_payload.get("changes", {})
            if isinstance(change_data, dict) and isinstance(change_data.get("paths"), list):
                changed_paths = unique_strings(change_data["paths"])
    continuity_snapshot = {
        "fingerprint": snapshot_fingerprint(current_snapshot),
        "file_count": int(current_snapshot.get("file_count", 0) or 0),
        "truncated": bool(current_snapshot.get("truncated")),
    }
    checks = _check_summary(check_payload or {})
    payload = {
        "schema": 1,
        "preflight": preflight,
        "session_type": session_type,
        "summary": str(summary).strip(),
        "completed_work": completed,
        "changed_files": changed_paths,
        "decisions": [
            {
                "text": str(item.get("text", "")).strip(),
                "rationale": str(item.get("rationale", "")).strip(),
                "status": "accepted",
            }
            for item in decision_rows
            if str(item.get("text", "")).strip() and str(item.get("rationale", "")).strip()
        ],
        "owner_facts": [
            {
                "text": str(item.get("text", "")).strip(),
                "impact": str(item.get("impact", "")).strip(),
            }
            for item in fact_rows
            if str(item.get("text", "")).strip() and str(item.get("impact", "")).strip()
        ],
        "checks": checks,
        "unresolved_risks": risks,
        "next_action": {
            "text": next_action,
            "status": "confirmed-at-session-close",
            "source": "session-close",
        },
        "continuity_snapshot": continuity_snapshot,
    }
    if isinstance(interaction_telemetry, dict):
        payload["interaction_telemetry"] = interaction_telemetry
    event = record_event(project_root, "session-close", payload, source="operator")
    state = load_state(project_root)
    state["last_operation"] = "session-close"
    state["last_session_close"] = {
        "event_id": event["id"],
        "utc": event["utc"],
        "session_type": session_type,
        "next_action": next_action,
        "continuity_fingerprint": continuity_snapshot["fingerprint"],
        "check_status": checks["status"],
    }
    save_state(project_root, state)
    passport_path = ForgePaths(project_root).passport
    passport = read_json(passport_path, {})
    if isinstance(passport, dict):
        if passport.get("maturity") == "Orientation":
            passport["maturity"] = "Working familiarity"
        passport["continuity"] = {
            "status": "current",
            "last_session_event": event["id"],
            "last_session_utc": event["utc"],
            "session_type": session_type,
            "exact_next_action": next_action,
        }
        write_json(passport_path, passport)
    if isinstance(interaction_telemetry, dict):
        record_interaction_session(project_root, interaction_telemetry, session_event_id=event["id"])
    field_observation: dict[str, Any] = {}
    if field_observation_path:
        from .field_trials import record_observation
        field_observation = record_observation(
            project_root, forge_root, field_observation_path, session_event_id=event["id"]
        )
    record_metric(project_root, "session-close", {
        "duration_ms": round((time.monotonic() - started) * 1000),
        "session_type": session_type,
        "completed_items": len(payload["completed_work"]),
        "changed_paths": len(payload["changed_files"]),
        "decisions": len(payload["decisions"]),
        "owner_facts": len(payload["owner_facts"]),
        "risks": len(payload["unresolved_risks"]),
        "check_status": checks["status"],
        "field_observation_recorded": bool(field_observation),
    })
    return {
        "schema": 1,
        "status": "CLOSED",
        "event_id": event["id"],
        "closed_utc": event["utc"],
        **payload,
        "field_observation": field_observation,
    }

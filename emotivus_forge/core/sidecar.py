from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import utc_now
from .state import load_state, save_state

SIDECAR_MODES = ("development-sidecar", "evidence-analysis", "release-assessment")


def update_sidecar_status(
    project_root: Path,
    *,
    mode: str,
    operation: str,
    work_scope: str = "",
    authority_status: str = "",
    unexpected_mutations: int | None = None,
    check_status: str = "",
    ship_status: str = "",
    ship_active: bool = False,
) -> dict[str, Any]:
    mode = str(mode).strip()
    if mode not in SIDECAR_MODES:
        raise ValueError(f"sidecar mode must be one of: {', '.join(SIDECAR_MODES)}")
    state = load_state(project_root.resolve())
    previous = state.get("sidecar", {}) if isinstance(state.get("sidecar"), dict) else {}
    last_check = state.get("last_check", {}) if isinstance(state.get("last_check"), dict) else {}
    record = {
        "schema": 1,
        "mode": mode,
        "operation": str(operation).strip(),
        "work_scope": str(work_scope).strip(),
        "authority_status": str(authority_status or previous.get("authority_status", "")).strip(),
        "unexpected_mutations": int(unexpected_mutations if unexpected_mutations is not None else previous.get("unexpected_mutations", 0) or 0),
        "last_scoped_check_status": str(check_status or last_check.get("status", previous.get("last_scoped_check_status", "NOT_RUN"))),
        "last_scoped_check_utc": str(last_check.get("utc", previous.get("last_scoped_check_utc", ""))),
        "last_ship_status": str(ship_status or previous.get("last_ship_status", "NOT_RUN")),
        "ship_assessment_active": bool(ship_active),
        "authority_changed_by_operation": False,
        "updated_utc": utc_now(),
        "truth_boundary": "This compact sidecar status reports Forge operation state only; it does not monitor the chat continuously, infer authorship, authorize changes, or run in the background.",
    }
    state["sidecar"] = record
    save_state(project_root, state)
    return record


def sidecar_status(project_root: Path) -> dict[str, Any]:
    state = load_state(project_root.resolve())
    value = state.get("sidecar", {}) if isinstance(state.get("sidecar"), dict) else {}
    if value:
        return value
    return {
        "schema": 1,
        "mode": "development-sidecar",
        "operation": "not-established",
        "work_scope": "",
        "authority_status": "",
        "unexpected_mutations": 0,
        "last_scoped_check_status": "NOT_RUN",
        "last_scoped_check_utc": "",
        "last_ship_status": "NOT_RUN",
        "ship_assessment_active": False,
        "authority_changed_by_operation": False,
        "updated_utc": "",
        "truth_boundary": "No persisted sidecar status exists yet.",
    }

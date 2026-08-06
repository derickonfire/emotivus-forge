from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import __version__
from .changes import detect_changes
from .authority_baseline import assess_authority_baseline
from .capabilities import capability_activations
from .common import read_json
from .paths import ForgePaths
from .session_close import assess_continuity
from .state import is_adopted, load_settings, load_state


def build_help(project_root: Path, forge_root: Path, topic: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    if topic:
        descriptions = {
            "adopt": "Create or refresh the minimal Project Passport without loading advanced assurance.",
            "resume": "Read the layered continuity packet and exact next action.",
            "check": "Run changed-file scoped checks; native tools run only after explicit approval.",
            "ship": "Assess cumulative exact-package release claims. Release-ready requires every current lower claim plus a separate exact-package project-declared authorization.",
            "advanced": "Show active-core capability metadata and project activation state without importing vaulted legacy code.",
        }
        return {"schema": 1, "topic": topic, "description": descriptions[topic]}
    if not is_adopted(project_root):
        state = "NOT_ADOPTED"
        recommendation = "adopt"
        changes = {"status": "unknown", "count": 0, "paths": []}
        continuity = {"status": "unknown", "reason": "Project is not adopted."}
        authority_baseline = {"status": "NOT_ESTABLISHED", "pending_count": 0, "release_eligible": False}
    else:
        state_data = load_state(project_root)
        changes = detect_changes(project_root, forge_root, state_data.get("snapshot", {}), load_settings(project_root))
        authority_baseline = assess_authority_baseline(state_data, changes.get("current_snapshot", {}), project_root=project_root)
        continuity = assess_continuity(project_root, current_snapshot=changes["current_snapshot"])
        authorities = read_json(ForgePaths(project_root).authorities, {})
        native_tools = read_json(ForgePaths(project_root).native_tools, {})
        authority_confirmation = authorities.get("confirmation", {}) if isinstance(authorities, dict) else {}
        native_approval = native_tools.get("approval", {}) if isinstance(native_tools, dict) else {}
        capability_states = capability_activations(project_root)
        capability_reactivation = any(
            item.get("status") == "reactivation-required" for item in capability_states.values()
            if isinstance(item, dict)
        )
        needs_confirmation = (
            bool(authority_confirmation.get("required")) if isinstance(authority_confirmation, dict) else False
        ) or (
            native_approval.get("status") in {"required", "reapproval-required"} if isinstance(native_approval, dict) else False
        ) or capability_reactivation
        if changes["count"]:
            state = "CHANGED"
            recommendation = "check"
        elif needs_confirmation:
            state = "NEEDS_CONFIRMATION"
            recommendation = "adopt"
        elif continuity.get("status") == "stale":
            state = "CONTINUITY_STALE"
            recommendation = "resume"
        elif continuity.get("status") == "not-established":
            state = "READY"
            recommendation = "resume"
        else:
            state = "READY"
            recommendation = "resume"
    passport = read_json(ForgePaths(project_root).passport, {})
    return {
        "schema": 1,
        "product": "Emotivus Forge",
        "version": __version__,
        "public_commands": ["help", "adopt", "resume", "check", "ship"],
        "project_state": state,
        "recommended_command": recommendation,
        "changes": {key: value for key, value in changes.items() if key != "current_snapshot"},
        "continuity": continuity,
        "authority_baseline": authority_baseline,
        "project": passport.get("identity", {}) if isinstance(passport, dict) else {},
        "scope": "Help inspects only minimal Forge state and bounded file metadata.",
    }


def render_help(payload: dict[str, Any]) -> str:
    if payload.get("topic"):
        return f"FORGE {str(payload['topic']).upper()}\n{payload.get('description', '')}\n"
    project = payload.get("project", {}) if isinstance(payload.get("project"), dict) else {}
    lines = [
        f"Emotivus Forge {__version__}",
        "Five commands: Help · Adopt · Resume · Check · Ship",
        f"Project: {project.get('name', 'Not adopted')}",
        f"State: {payload.get('project_state', 'UNKNOWN')}",
        f"Continuity: {payload.get('continuity', {}).get('status', 'unknown')}",
        f"Authority baseline: {payload.get('authority_baseline', {}).get('status', 'NOT_ESTABLISHED')} · {payload.get('authority_baseline', {}).get('pending_count', 0)} quarantined path(s)",
        f"Do next: forge {payload.get('recommended_command', 'help')}",
        "",
        "Help and ordinary startup do not load the capability vault or advanced assurance engines.",
    ]
    return "\n".join(lines).rstrip() + "\n"

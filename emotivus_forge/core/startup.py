from __future__ import annotations

from pathlib import Path
from typing import Any
import time

from .common import read_json
from .guidance import build_help
from .passport import build_passport
from .paths import ForgePaths
from .resume import build_resume
from .recommended_prompt import build_recommended_prompt
from .state import is_adopted
from .session_reconciliation import load_session_context, build_session_reconciliation, build_forge_brief
from .sidecar import update_sidecar_status
from .storage import inspect_state_integrity
from .workspace_integrity import start_workspace_observation
from .artifact_collision import observe_version_collisions


def _looks_like_forge_artifact(name: str) -> bool:
    lower = name.lower()
    return lower.startswith("emotivus-forge") or lower.startswith("run-forge") or lower in {
        "forge", "forge.py", "forge.cmd", "frg", "frg.py", "frg.cmd"
    }


def resolve_project_root(requested: Path, forge_root: Path) -> tuple[Path, list[str]]:
    requested = requested.resolve()
    forge_root = forge_root.resolve()
    candidate = forge_root.parent if requested == forge_root or forge_root in requested.parents else requested
    entries: list[str] = []
    try:
        for path in sorted(candidate.iterdir(), key=lambda item: item.name.lower()):
            if path.name in {".forge", ".DS_Store", "Thumbs.db"}:
                continue
            if path.resolve() == forge_root or _looks_like_forge_artifact(path.name):
                continue
            entries.append(path.name)
    except OSError:
        pass
    return candidate, entries


def run_forge(project_root: Path, forge_root: Path, *, budget: str = "compact", session_context_path: str = "") -> dict[str, Any]:
    started = time.monotonic()
    project_root, host_entries = resolve_project_root(project_root, forge_root)
    integrity = inspect_state_integrity(project_root)
    if integrity.get("status") == "BLOCKED":
        payload = {
            "schema": 1,
            "status": "BLOCKED",
            "action": "STATE INTEGRITY",
            "project_root": str(project_root),
            "reason": "Persisted Forge state is malformed and was preserved unchanged.",
            "state_integrity": integrity,
            "next_action": "Restore the affected .forge state file from a trusted backup or repair it explicitly before continuing.",
            "safety": {
                "ship_invoked": False,
                "destructive_action_invoked": False,
                "vault_loaded": False,
                "advanced_loaded": False,
            },
        }
        payload["recommended_prompt"] = build_recommended_prompt(payload)
        return payload
    if not host_entries:
        payload = {
            "schema": 1,
            "status": "NEEDS_PROJECT",
            "action": "NONE",
            "project_root": str(project_root),
            "reason": "No host-project files were found beside Forge.",
            "next_action": "Extract the target project beside Emotivus-Forge and run Forge from the project root.",
        }
        payload["recommended_prompt"] = build_recommended_prompt(payload)
        return payload
    session_context = load_session_context(session_context_path, project_root=project_root) if str(session_context_path).strip() else None
    if not is_adopted(project_root):
        passport = build_passport(project_root, forge_root)
        resume = build_resume(project_root, forge_root, budget=budget, refresh=False)
        action = "ADOPT + RESUME"
        check = None
    else:
        guide = build_help(project_root, forge_root)
        if guide["project_state"] == "CHANGED":
            from ..services.scoped_check import run_scoped_check
            check = run_scoped_check(project_root, forge_root)
            action = "SCOPED CHECK + RESUME"
        else:
            check = None
            action = "RESUME"
        passport = read_json(ForgePaths(project_root).passport, {})
        if not isinstance(passport, dict):
            passport = {}
        resume = build_resume(project_root, forge_root, budget=budget, refresh=False)
    artifact_collisions = observe_version_collisions(project_root)
    status = (
        "BLOCKED"
        if (check and check.get("status") != "PASS") or artifact_collisions.get("status") != "PASS"
        else resume.get("status", "ATTENTION")
    )
    payload = {
        "schema": 1,
        "status": status,
        "action": action,
        "project_root": str(project_root),
        "project": passport.get("identity", {}),
        "objective": resume.get("objective", {}),
        "next_action": resume.get("next_action", {}),
        "changes": resume.get("changes", {}),
        "authority_baseline": resume.get("authority_baseline", {}),
        "uncertainties": resume.get("uncertainties", []),
        "attention_items": resume.get("attention_items", []),
        "attention_counts": resume.get("attention_counts", {}),
        "continuity": resume.get("continuity", {}),
        "session_close": resume.get("session_close", {}),
        "knowledge_delta": passport.get("knowledge_delta", {}) if isinstance(passport, dict) else {},
        "state_integrity": inspect_state_integrity(project_root),
        "artifact_version_collisions": artifact_collisions,
        "decision_forks": resume.get("decision_forks", {}),
        "presentation_profile": resume.get("presentation_profile", {}),
        "check": check,
        "passport": str(project_root / ".forge" / "passport.json"),
        "resume": str(project_root / ".forge" / "resume.md"),
        "safety": {
            "ship_invoked": False,
            "destructive_action_invoked": False,
            "vault_loaded": False,
            "advanced_loaded": False,
        },
    }
    payload["session_reconciliation"] = build_session_reconciliation(session_context, changes=payload.get("changes", {}), check=check)
    payload["active_pass"] = {
        "status": "COMPLETE",
        "duration_ms": round((time.monotonic() - started) * 1000),
        "budget": "bounded-1-to-5-minute-target",
        "phases": ["identity", "continuity", "session-intent", "change-scope", "safe-checks", "reconciliation", "brief"],
    }
    payload["forge_brief"] = build_forge_brief(payload)
    payload["sidecar"] = update_sidecar_status(
        project_root, mode="development-sidecar", operation="run-forge-active-pass",
        work_scope=str(payload.get("forge_brief", {}).get("objective", "")),
        authority_status=str(payload.get("authority_baseline", {}).get("status", "")),
        unexpected_mutations=int(payload.get("authority_baseline", {}).get("pending_count", 0) or 0),
        check_status=str(check.get("status", "NOT_RUN")) if isinstance(check, dict) else "NOT_RUN",
    )
    payload["workspace_integrity"] = start_workspace_observation(project_root)
    payload["recommended_prompt"] = build_recommended_prompt(payload)
    return payload


def render_run(payload: dict[str, Any]) -> str:
    if payload.get("status") == "NEEDS_PROJECT":
        recommended = payload.get("recommended_prompt", {}) if isinstance(payload.get("recommended_prompt"), dict) else {}
        line = str(recommended.get("text", "")).strip()
        suffix = f"\n\n**Forge recommends this prompt —** {line}" if line else ""
        return f"FORGE NOT STARTED\n{payload.get('reason')}\nDo next: {payload.get('next_action')}{suffix}\n"
    project = payload.get("project", {}) if isinstance(payload.get("project"), dict) else {}
    objective = payload.get("objective", {}) if isinstance(payload.get("objective"), dict) else {}
    changes = payload.get("changes", {}) if isinstance(payload.get("changes"), dict) else {}
    forks = payload.get("decision_forks", {}) if isinstance(payload.get("decision_forks"), dict) else {}
    lines = [
        f"FORGE STARTED — {payload.get('status', 'UNKNOWN')}",
        f"Project: {project.get('name', Path(str(payload.get('project_root', '.'))).name)}",
        f"Action: {payload.get('action', 'UNKNOWN')}",
        f"Active pass: {payload.get('active_pass', {}).get('status', 'NOT_RUN')} · then passive sidecar",
        f"Objective: {objective.get('text', '') or 'Not confirmed'}",
        f"Changes: {changes.get('count', 0)} path(s)",
        f"Authority baseline: {payload.get('authority_baseline', {}).get('status', 'NOT_ESTABLISHED')} · {payload.get('authority_baseline', {}).get('pending_count', 0)} quarantined path(s)",
        f"Continuity: {payload.get('continuity', {}).get('status', 'unknown')}",
        f"Artifact collisions: {payload.get('artifact_version_collisions', {}).get('status', 'NOT_RUN')}",
        f"Next action: {payload.get('next_action', {}).get('text', '')}",
        f"Decision forks: {len(forks.get('pending', []))} pending; {len(forks.get('contradictions', []))} contradiction warning(s)",
        f"Session reconciliation: {payload.get('session_reconciliation', {}).get('status', 'NOT_SUPPLIED')}",
        f"Passport: {payload.get('passport', '')}",
        f"Resume: {payload.get('resume', '')}",
    ]
    brief = payload.get("forge_brief", {}) if isinstance(payload.get("forge_brief"), dict) else {}
    if brief:
        evidence = brief.get("evidence", {}) if isinstance(brief.get("evidence"), dict) else {}
        lines.extend([
            "",
            "FORGE BRIEF",
            f"Mode: active pass complete → {brief.get('phase', 'passive')} sidecar",
            f"Conversation/code alignment: {brief.get('conversation_code_alignment', 'NOT_SUPPLIED')}",
            f"Evidence: scoped Check {evidence.get('scoped_check', 'NOT_RUN')} · native {evidence.get('native_gate', 'NOT_RUN')} · {evidence.get('checked_paths', 0)} checked path(s)",
            f"Claimed but not proven: {len(brief.get('claimed_not_proven', []))}",
            f"Exact next action: {brief.get('exact_next_action', '')}",
        ])
    recommended = payload.get("recommended_prompt", {}) if isinstance(payload.get("recommended_prompt"), dict) else {}
    recommended_text = str(recommended.get("text", "")).strip()
    if recommended_text:
        lines.extend(["", f"**Forge recommends this prompt —** {recommended_text}"])
    lines.extend([
        "",
        "Forge did not load advanced or vaulted capabilities and did not Ship, deploy, delete, migrate production data, or repair the environment.",
    ])
    return "\n".join(lines).rstrip() + "\n"

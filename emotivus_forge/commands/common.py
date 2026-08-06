from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.notices import render_notice


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def active_state_count(project_root: Path) -> int:
    root = project_root / ".forge"
    return sum(1 for path in root.iterdir() if path.is_file()) if root.is_dir() else 0


def append_notice(text: str, payload: dict[str, Any]) -> str:
    notice = render_notice(payload.get("ai_notice") if isinstance(payload, dict) else None)
    if not notice:
        return text
    return text.rstrip() + "\n\n" + notice


def render_adopt(passport: dict[str, Any], project_root: Path) -> str:
    objective = passport.get("objective", {}) if isinstance(passport.get("objective"), dict) else {}
    native = passport.get("native_gate", {}) if isinstance(passport.get("native_gate"), dict) else {}
    canonical = native.get("canonical") if isinstance(native, dict) else None
    approval = native.get("approval", {}) if isinstance(native, dict) else {}
    delta = passport.get("knowledge_delta", {}) if isinstance(passport.get("knowledge_delta"), dict) else {}
    lines = [
        "FORGE ADOPT — COMPLETE",
        f"Project: {passport.get('identity', {}).get('name', project_root.name)}",
        f"Objective: {objective.get('text', '') or 'Not confirmed'}",
        f"Files observed: {passport.get('orientation', {}).get('files_observed', 0)}",
        f"Minimal state files: {active_state_count(project_root)}",
        f"Knowledge delta: {delta.get('meaningful_count', 0)} meaningful change(s)",
        f"Native gate: {canonical.get('source') if isinstance(canonical, dict) else 'None detected'}",
    ]
    authority = passport.get("authority_baseline", {}) if isinstance(passport.get("authority_baseline"), dict) else {}
    lines.append(f"Authority baseline: {authority.get('status', 'NOT_ESTABLISHED')} · {authority.get('pending_count', 0)} quarantined path(s) · strength {authority.get('baseline_strength', 'not-established')}")
    authorization = passport.get("baseline_authorization", {}) if isinstance(passport.get("baseline_authorization"), dict) else {}
    if authorization:
        lines.append(f"Authorized baseline: {authorization.get('baseline_id', '')} · {authorization.get('strength', {}).get('status', 'bounded')} · recheck required")
    if isinstance(canonical, dict):
        lines.append(f"Proposed command: {' '.join(str(item) for item in canonical.get('command', []))}")
        lines.append(f"Native policy: {approval.get('execution_mode', 'unassigned') if isinstance(approval, dict) else 'unassigned'} ({approval.get('status', 'required') if isinstance(approval, dict) else 'required'})")
    resolution = passport.get("decision_fork_resolution", {}) if isinstance(passport.get("decision_fork_resolution"), dict) else {}
    if resolution:
        accepted = resolution.get("accepted_option", {}) if isinstance(resolution.get("accepted_option"), dict) else {}
        lines.append(f"Decision fork: {resolution.get('fork_id', '')} → {accepted.get('id', '')}")
        lines.append(f"Decision authority: {resolution.get('authority', '')}")
    capabilities = passport.get("advanced_capabilities", {}) if isinstance(passport.get("advanced_capabilities"), dict) else {}
    guardrails = passport.get("guardrails", {}) if isinstance(passport.get("guardrails"), dict) else {}
    field_trials = passport.get("field_trials", {}) if isinstance(passport.get("field_trials"), dict) else {}
    lines.append(f"Advanced capabilities: {len(capabilities.get('active', []))} active; {len(capabilities.get('recommendations', []))} recommendation(s)")
    lines.append(f"Safety guardrails: {len(guardrails.get('active', []))} active; {len(guardrails.get('attention', []))} attention")
    lines.append(f"Field trials: {len(field_trials.get('active', []))} active; {field_trials.get('total_observations', 0)} observation(s)")
    for item in capabilities.get("active", [])[:5]:
        if isinstance(item, dict):
            lines.append(f"  - {item.get('name', item.get('capability_id', 'Capability'))}: {item.get('status', 'unknown')} via {item.get('contract_source', '')}")
    lines.extend([
        f"Uncertainties: {len(passport.get('uncertainties', []))}",
        "Excluded: Graph, Lab, runtime proof, release proof, remediation, CI, and tool absorption.",
    ])
    return append_notice("\n".join(lines).rstrip() + "\n", passport)

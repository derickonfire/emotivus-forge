from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .utils import read_json, tree_snapshot, utc_now

PUBLIC_COMMANDS = ("help", "adopt", "resume", "check", "ship")
PASSPORT_DIR = Path(".forge/passport")


def _command_name() -> str:
    value = os.environ.get("FORGE_INVOKED_AS", "forge").strip().lower()
    return "frg" if value == "frg" else "forge"


def _alias_command(value: str) -> str:
    command_name = _command_name()
    if command_name == "forge":
        return value
    return value.replace("python3 Emotivus-Forge/forge.py", "python3 Emotivus-Forge/frg.py").replace("forge ", f"{command_name} ")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_product(forge_root: Path) -> dict[str, Any]:
    product = _read_object(forge_root / "FORGE-PRODUCT.json")
    if not product:
        raise RuntimeError("FORGE-PRODUCT.json is missing or invalid")
    return product


def _commands(product: dict[str, Any]) -> list[dict[str, Any]]:
    commands = product.get("public_commands", [])
    if not isinstance(commands, list):
        return []
    return [item for item in commands if isinstance(item, dict)]


def _command_topic(product: dict[str, Any], topic: str) -> dict[str, Any]:
    for item in _commands(product):
        if str(item.get("name", "")).strip().lower() == topic:
            return item
    raise RuntimeError(f"no public help topic is defined for {topic}")


def _snapshot_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_paths = set(previous)
    current_paths = set(current)
    added = sorted(current_paths - previous_paths)
    removed = sorted(previous_paths - current_paths)
    modified = sorted(
        path for path in previous_paths & current_paths
        if previous.get(path, {}).get("sha256") != current.get(path, {}).get("sha256")
        or previous.get(path, {}).get("kind") != current.get(path, {}).get("kind")
    )
    paths = added + modified + removed
    return {
        "status": "changed" if paths else "unchanged",
        "count": len(paths),
        "added": added,
        "modified": modified,
        "removed": removed,
        "paths": paths,
    }


def _project_guidance(project_root: Path, forge_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    config_path = project_root / ".emotivus-forge.json"
    passport_path = project_root / PASSPORT_DIR / "passport.json"
    observed_path = project_root / PASSPORT_DIR / "observed-snapshot.json"
    adopted_path = project_root / PASSPORT_DIR / "adopted-snapshot.json"

    if not config_path.is_file():
        return {
            "state": "NOT_ADOPTED",
            "project": project_root.name,
            "project_root": str(project_root),
            "passport": "missing",
            "changes": {"status": "unknown", "count": 0, "paths": []},
            "next_action": {
                "command": _alias_command("forge adopt ."),
                "reason": "Forge has not created a Project Passport for this project yet.",
            },
            "proof": {"claim_level": "none", "claim_status": "NOT_RUN"},
            "objective": "No Forge continuity state exists yet.",
        }

    config = _read_object(config_path)
    passport = _read_object(passport_path)
    project_name = str(config.get("project", {}).get("name", project_root.name))
    if not passport:
        return {
            "state": "ADOPTION_INCOMPLETE",
            "project": project_name,
            "project_root": str(project_root),
            "passport": "missing",
            "changes": {"status": "unknown", "count": 0, "paths": []},
            "next_action": {
                "command": _alias_command("forge adopt ."),
                "reason": "Forge configuration exists, but the authoritative Project Passport is missing.",
            },
            "proof": {"claim_level": "none", "claim_status": "NOT_RUN"},
            "objective": "Project configuration exists, but adoption is incomplete.",
        }

    excludes = config.get("paths", {}).get("exclude", [])
    current = tree_snapshot(project_root, excludes, forge_root)
    previous = _read_object(observed_path) or _read_object(adopted_path)
    changes = _snapshot_diff(previous, current) if previous else {
        "status": "unknown", "count": 0, "added": [], "modified": [], "removed": [], "paths": [],
    }

    next_action = passport.get("next_action", {}) if isinstance(passport.get("next_action"), dict) else {}
    if changes.get("count", 0):
        next_action = {
            "command": _alias_command("forge check . --profile quick"),
            "reason": f"{changes.get('count', 0)} path(s) changed since the last Forge observation.",
        }
    elif not next_action.get("command"):
        next_action = {
            "command": _alias_command("forge resume ."),
            "reason": "Review the current objective and continuation packet before editing.",
        }

    evidence = passport.get("evidence", {}) if isinstance(passport.get("evidence"), dict) else {}
    objective = passport.get("continuity", {}).get("objective", {})
    objective_text = objective.get("text", "") if isinstance(objective, dict) else str(objective)
    return {
        "state": "CHANGED" if changes.get("count", 0) else "READY",
        "project": project_name,
        "project_root": str(project_root),
        "passport": str(passport_path),
        "changes": changes,
        "next_action": next_action,
        "proof": {
            "claim_level": evidence.get("claim_level", "none"),
            "claim_status": evidence.get("claim_status", "NOT_RUN"),
        },
        "objective": objective_text or "No declared next action was found.",
        "token_efficiency": passport.get("continuity", {}).get("token_efficiency", {}),
    }


def build_help_guide(
    project_root: Path,
    forge_root: Path,
    *,
    topic: str = "",
) -> dict[str, Any]:
    """Build safe, read-only guidance for first contact and normal operation."""
    product = _load_product(forge_root)
    normalized_topic = topic.strip().lower()
    if normalized_topic:
        command = dict(_command_topic(product, normalized_topic))
        command["command"] = _alias_command(str(command.get("command", "")))
        command["next"] = _alias_command(str(command.get("next", "")))
        return {
            "schema": 1,
            "generated_utc": utc_now(),
            "status": "PASS",
            "mode": "topic",
            "topic": normalized_topic,
            "headline": product.get("headline", "Five commands. One Project Passport. Any coding AI."),
            "command": command,
        }

    project = _project_guidance(project_root, forge_root)
    return {
        "schema": 1,
        "generated_utc": utc_now(),
        "status": "PASS",
        "mode": "project",
        "headline": product.get("headline", "Five commands. One Project Passport. Any coding AI."),
        "summary": product.get("summary", ""),
        "command_name": _command_name(),
        "workflow": [
            {**item, "command": _alias_command(str(item.get("command", ""))), "next": _alias_command(str(item.get("next", "")))}
            for item in _commands(product)
        ],
        "project_state": project,
        "advanced": {
            "command": _alias_command("forge advanced"),
            "help_command": _alias_command("forge help advanced"),
            "required_for_normal_use": False,
        },
    }


def render_help_guide(payload: dict[str, Any]) -> str:
    """Render the public Help command for humans without hiding machine-readable details."""
    lines = ["Emotivus Forge", str(payload.get("headline", "")), ""]
    if payload.get("mode") == "topic":
        command = payload.get("command", {})
        lines.extend([
            f"{command.get('name', '').upper()}",
            str(command.get("description", "")),
            "",
            f"Use:  {command.get('command', '')}",
        ])
        when = str(command.get("when_to_use", "")).strip()
        if when:
            lines.append(f"When: {when}")
        outputs = command.get("outputs", [])
        if isinstance(outputs, list) and outputs:
            lines.extend(["", "Produces:"] + [f"  - {item}" for item in outputs])
        next_step = str(command.get("next", "")).strip()
        if next_step:
            lines.extend(["", f"Next: {next_step}"])
        return "\n".join(lines).rstrip() + "\n"

    state = payload.get("project_state", {})
    next_action = state.get("next_action", {})
    proof = state.get("proof", {})
    token_efficiency = state.get("token_efficiency", {}) if isinstance(state.get("token_efficiency"), dict) else {}
    project_tokens = int(token_efficiency.get("project_token_equivalent_estimate", 0) or 0)
    context_line = (
        f"Context: compact Resume targets {token_efficiency.get('default_resume_budget_tokens', 1200)} tokens "
        f"instead of reloading ~{project_tokens:,} project token-equivalent"
        if project_tokens else "Context: measured after Adopt; Resume supplies minimum sufficient project truth"
    )
    lines.extend([
        f"Project: {state.get('project', '')}",
        f"State:   {state.get('state', 'UNKNOWN')}",
        f"Goal:    {state.get('objective', '')}",
        f"Changes: {state.get('changes', {}).get('count', 0)} path(s) since the last Forge observation",
        f"Proof:   {proof.get('claim_level', 'none')} ({proof.get('claim_status', 'NOT_RUN')})",
        context_line,
        "",
        f"Do next: {next_action.get('command', 'forge adopt .')}",
        f"Why:     {next_action.get('reason', '')}",
        "",
        "Five public commands:",
    ])
    for item in payload.get("workflow", []):
        lines.append(f"  {str(item.get('name', '')).lower():<7} {item.get('description', '')}")
    lines.extend([
        "",
        f"Learn one command: {payload.get('command_name', 'forge')} help <adopt|resume|check|ship>",
        f"Expert controls:  {payload.get('command_name', 'forge')} advanced",
    ])
    return "\n".join(lines).rstrip() + "\n"

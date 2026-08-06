"""Optional five-command session adapters.

A host — an MCP server, a coding-agent hook, a CI step — may ask Forge what it should
invoke at a session lifecycle event. Forge answers with a declarative contract. It does
not install itself, watch anything, or run in the background.

Three events map to existing behavior only:

``session_start``
    may invoke **Run Forge**, the bounded active pass.

``milestone``
    may invoke **Check**.

``session_end``
    may *guide* Session Close. Guidance only: it never performs an authority transition.

Everything is off by default. A disabled global switch overrides every per-event switch,
so enabling one event by accident cannot activate the layer.

Hard prohibitions, enforced here rather than merely documented:

* No sixth public command. Only Help, Adopt, Resume, Check, Ship may be mapped.
* No ninth state file. Adapters read settings and emit a contract; they persist nothing.
* No daemon. The contract declares a host-invoked one-shot process model.
* No silent authority transition. Any configuration requesting baseline advancement,
  change approval, merge, or release authorization is rejected, not quietly ignored.
"""
from __future__ import annotations

from typing import Any

PUBLIC_COMMANDS = ("help", "adopt", "resume", "check", "ship")

# Run Forge is the no-command experience, not a sixth command. Session Close is a
# guided outcome of Ship/Check flow, not a command either. Both are named here as
# *behaviors*, and each resolves to public-command surface or to guidance only.
SESSION_START = "session_start"
MILESTONE = "milestone"
SESSION_END = "session_end"

ADAPTER_EVENTS = (SESSION_START, MILESTONE, SESSION_END)

EVENT_CONTRACT: dict[str, dict[str, Any]] = {
    SESSION_START: {
        "behavior": "run-forge",
        "public_command": None,  # no-command experience
        "mode": "invoke",
        "description": "Bounded active project-intelligence pass, then passive sidecar.",
    },
    MILESTONE: {
        "behavior": "check",
        "public_command": "check",
        "mode": "invoke",
        "description": "Scoped verification of the current change set.",
    },
    SESSION_END: {
        "behavior": "session-close",
        "public_command": None,
        "mode": "guide",
        "description": "Guide the operator through Session Close. Never performs it unattended.",
    },
}

# A configuration may not request any of these. They are authority transitions.
PROHIBITED_EFFECTS = (
    "advance_baseline",
    "approve_changes",
    "merge_files",
    "authorize_release",
    "adopt",
    "ship",
    "mutate_state",
    "rewrite_prompt",
    "run_continuously",
)


def default_settings() -> dict[str, Any]:
    """The shipped default: every adapter off."""
    return {
        "enabled": False,
        "events": {
            SESSION_START: {"enabled": False},
            MILESTONE: {"enabled": False},
            SESSION_END: {"enabled": False},
        },
    }


def validate(configuration: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return configuration problems. An empty list means the configuration is usable."""
    problems: list[dict[str, str]] = []
    config = configuration or {}
    events = config.get("events", {})
    if not isinstance(events, dict):
        return [{"event": "*", "problem": "events must be an object"}]
    for name, value in events.items():
        if name not in ADAPTER_EVENTS:
            problems.append({"event": str(name), "problem": "unknown adapter event"})
            continue
        if not isinstance(value, dict):
            problems.append({"event": name, "problem": "event configuration must be an object"})
            continue
        command = value.get("public_command")
        if command is not None and command not in PUBLIC_COMMANDS:
            problems.append({
                "event": name,
                "problem": f"'{command}' is not one of the five public commands; adapters cannot add a sixth",
            })
        if name == SESSION_END and value.get("mode", "guide") != "guide":
            problems.append({
                "event": name,
                "problem": "session_end is guidance only; it cannot be set to invoke",
            })
        for effect in value.get("effects", []) or []:
            if effect in PROHIBITED_EFFECTS:
                problems.append({
                    "event": name,
                    "problem": f"'{effect}' is an authority transition and cannot be delegated to an adapter",
                })
    return sorted(problems, key=lambda item: (item["event"], item["problem"]))


def resolve(configuration: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the effective adapter state.

    The global switch dominates: with ``enabled`` false every event is inactive
    regardless of its own switch.
    """
    config = configuration or default_settings()
    problems = validate(config)
    globally_enabled = bool(config.get("enabled", False)) and not problems
    events = config.get("events", {}) if isinstance(config.get("events"), dict) else {}
    resolved: dict[str, Any] = {}
    for name in ADAPTER_EVENTS:
        contract = EVENT_CONTRACT[name]
        requested = events.get(name, {}) if isinstance(events.get(name), dict) else {}
        event_enabled = bool(requested.get("enabled", False))
        resolved[name] = {
            "event": name,
            "behavior": contract["behavior"],
            "public_command": contract["public_command"],
            "mode": contract["mode"],
            "description": contract["description"],
            "requested": event_enabled,
            "active": globally_enabled and event_enabled,
        }
    return {
        "schema": "forge-session-adapters/1",
        "globally_enabled": globally_enabled,
        "events": resolved,
        "active_events": sorted(name for name, item in resolved.items() if item["active"]),
        "problems": problems,
    }


def contract(configuration: dict[str, Any] | None = None) -> dict[str, Any]:
    """Emit the declarative contract a host reads to decide what to invoke."""
    resolution = resolve(configuration)
    return {
        "schema": "forge-session-adapters/1",
        "default_state": "off",
        "process_model": "host-invoked-one-shot",
        "runs_continuously": False,
        "installs_hooks": False,
        "rewrites_prompts": False,
        "adds_public_command": False,
        "adds_state_file": False,
        "public_commands": list(PUBLIC_COMMANDS),
        "prohibited_effects": list(PROHIBITED_EFFECTS),
        "globally_enabled": resolution["globally_enabled"],
        "events": resolution["events"],
        "active_events": resolution["active_events"],
        "problems": resolution["problems"],
        "truth_boundary": (
            "This contract describes what a host may invoke. Forge does not install, "
            "schedule, or observe anything on its own, and an adapter never performs an "
            "authority transition. An invocation through an adapter carries exactly the "
            "authority of the same command run by hand — no more."
        ),
    }

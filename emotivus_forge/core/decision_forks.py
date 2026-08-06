from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .common import read_json, unique_strings, utc_now, write_json
from .ledger import read_events, record_event
from .orientation import iter_project_files
from .paths import ForgePaths
from .state import load_settings, load_state, save_state
from .telemetry import record_metric

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".html", ".htm", ".php", ".py", ".js", ".ts", ".tsx", ".json", ".sql"}
AUTHORITY_SUFFIXES = {".md", ".txt", ".rst"}

DATE_ONLY_PATTERNS = (
    re.compile(r"type\s*=\s*['\"]date['\"]", re.I),
    re.compile(r"\bdate[- ]only\b", re.I),
    re.compile(r"\bcalendar date\b", re.I),
    re.compile(r"\b(?:due|deadline|followup|follow_up)_date\b", re.I),
    re.compile(r"\bstores? (?:only )?(?:a )?date(?: without (?:a )?time)?\b", re.I),
)
EXACT_TIME_REQUIREMENT_PATTERNS = (
    re.compile(r"\bimmediate\b", re.I),
    re.compile(r"\b(?:15|30)\s*[- ]?minutes?\b", re.I),
    re.compile(r"\bminute[- ]level\b", re.I),
    re.compile(r"\bexact (?:due )?time\b", re.I),
    re.compile(r"\bexact deadline\b", re.I),
    re.compile(r"\btime-specific\b", re.I),
)
EXACT_TIME_IMPLEMENTATION_PATTERNS = (
    re.compile(r"\bdue_at\b", re.I),
    re.compile(r"\bdeadline_at\b", re.I),
    re.compile(r"\bdatetime(?:-local)?\b", re.I),
    re.compile(r"\btimestamp\b", re.I),
    re.compile(r"\bnullable exact time\b", re.I),
)
COERCION_PATTERNS = (
    re.compile(r"\bround(?:ed|ing)? (?:the )?(?:deadline|time) to (?:the )?(?:day|date)\b", re.I),
    re.compile(r"\bmap(?:ped|ping)? (?:15|30)[- ]minute(?:s)? to (?:today|a date)\b", re.I),
    re.compile(r"\bexact presets?.{0,80}\btype\s*=\s*['\"]date['\"]", re.I | re.S),
)


def _read_text(path: Path, limit: int = 400_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _matched_labels(text: str, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    labels: list[str] = []
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = re.sub(r"\s+", " ", match.group(0)).strip()[:100]
            if value and value not in labels:
                labels.append(value)
    return labels


def _authority_paths(authorities: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    selected = authorities.get("selected_by_kind", {})
    if isinstance(selected, dict):
        for item in selected.values():
            if isinstance(item, dict) and str(item.get("path", "")).strip():
                result.add(str(item["path"]).strip())
    for item in authorities.get("candidates", []):
        if isinstance(item, dict) and int(item.get("score", 0) or 0) >= 60:
            path = str(item.get("path", "")).strip()
            if path:
                result.add(path)
    return result


def _scan_signals(project_root: Path, forge_root: Path, authorities: dict[str, Any], *, max_files: int = 300) -> dict[str, Any]:
    authority_paths = _authority_paths(authorities)
    date_only: list[dict[str, Any]] = []
    exact_requirements: list[dict[str, Any]] = []
    exact_implementation: list[dict[str, Any]] = []
    coercions: list[dict[str, Any]] = []
    scanned = 0
    for path in iter_project_files(project_root, forge_root, max_files=max_files, max_depth=6):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = _read_text(path)
        if not text:
            continue
        scanned += 1
        relative = path.relative_to(project_root).as_posix()
        is_authority = relative in authority_paths
        date_matches = _matched_labels(text, DATE_ONLY_PATTERNS)
        exact_req_matches = _matched_labels(text, EXACT_TIME_REQUIREMENT_PATTERNS)
        exact_impl_matches = _matched_labels(text, EXACT_TIME_IMPLEMENTATION_PATTERNS)
        coercion_matches = _matched_labels(text, COERCION_PATTERNS)
        if date_matches:
            date_only.append({"path": relative, "signals": date_matches[:4], "authority": is_authority})
        if exact_req_matches and is_authority:
            exact_requirements.append({"path": relative, "signals": exact_req_matches[:4], "authority": True})
        elif exact_req_matches and path.suffix.lower() not in AUTHORITY_SUFFIXES:
            # UI labels and implementation copy are also evidence that exact precision is being introduced.
            exact_requirements.append({"path": relative, "signals": exact_req_matches[:4], "authority": False})
        if exact_impl_matches:
            exact_implementation.append({"path": relative, "signals": exact_impl_matches[:4], "authority": is_authority})
        if coercion_matches:
            coercions.append({"path": relative, "signals": coercion_matches[:4], "authority": is_authority})
    return {
        "scanned_files": scanned,
        "date_only": date_only,
        "exact_requirements": exact_requirements,
        "exact_implementation": exact_implementation,
        "coercions": coercions,
    }


def _deadline_precision_fork(signals: dict[str, Any]) -> dict[str, Any] | None:
    authority_requirements = [item for item in signals["exact_requirements"] if item.get("authority")]
    if not signals["date_only"] or not authority_requirements:
        return None
    evidence = []
    for group, label in (("date_only", "current-constraint"), ("exact_requirements", "requested-capability")):
        for item in signals[group][:4]:
            evidence.append({"kind": label, **item})
    return {
        "schema": 1,
        "id": "deadline-precision",
        "detector": "date-only-versus-exact-time",
        "status": "pending",
        "title": "Deadline precision: calendar date or exact time",
        "existing_constraint": "Observed project records or inputs represent deadlines as calendar dates without guaranteed time-of-day precision.",
        "requested_capability": "Observed requirements or interface text introduce immediate or minute-level deadlines that require an exact timestamp.",
        "evidence": evidence,
        "options": [
            {
                "id": "preserve-date-only",
                "label": "Preserve date-only deadlines",
                "implications": [
                    "Retains the smallest data and migration surface.",
                    "Exact minute-level presets must be removed or explicitly declined.",
                    "Existing calendar-day semantics remain unchanged.",
                ],
                "supports_requested_capability": False,
                "recommended": False,
            },
            {
                "id": "add-optional-exact-time",
                "label": "Add an optional exact timestamp while retaining date-only records",
                "implications": [
                    "Supports immediate and minute-level deadlines honestly.",
                    "Requires storage, migration, ordering, late-state, display, and timezone contracts.",
                    "Historical date-only records remain valid without inventing a time.",
                ],
                "supports_requested_capability": True,
                "recommended": True,
            },
            {
                "id": "coerce-exact-presets-to-dates",
                "label": "Map exact presets onto calendar dates",
                "implications": [
                    "Avoids a schema change but discards requested precision.",
                    "Can label a deadline as exact when the model cannot represent it.",
                    "Creates misleading late-state and ordering behavior.",
                ],
                "supports_requested_capability": False,
                "recommended": False,
                "risk": "misrepresents precision",
            },
        ],
        "recommendation": {
            "option_id": "add-optional-exact-time",
            "reason": "It is the only option that preserves historical date-only data while representing exact deadlines honestly.",
        },
        "required_authority": "product owner or confirmed architecture-decision authority",
        "confidence": "high",
    }


def latest_fork_resolutions(project_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for event in read_events(project_root, kinds={"decision-fork-resolution"}):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        fork_id = str(payload.get("fork_id", "")).strip()
        if fork_id:
            result[fork_id] = {**payload, "event_id": event.get("id", ""), "utc": event.get("utc", "")}
    return result


def _option_map(fork: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id", "")): item
        for item in fork.get("options", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def resolve_decision_fork(
    project_root: Path,
    forge_root: Path,
    *,
    fork_id: str,
    option_id: str,
    rationale: str,
    authority: str = "owner",
    authorities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    rationale = str(rationale).strip()
    authority = str(authority).strip() or "owner"
    if not rationale:
        raise ValueError("Resolving a decision fork requires a rationale.")
    analysis = analyze_decision_forks(project_root, forge_root, authorities=authorities)
    fork = next((item for item in analysis["forks"] if item.get("id") == fork_id), None)
    if not isinstance(fork, dict):
        raise ValueError(f"Decision fork is not currently evidenced: {fork_id}")
    options = _option_map(fork)
    if option_id not in options:
        raise ValueError(f"Unknown option for {fork_id}: {option_id}")
    accepted = options[option_id]
    rejected = [item for key, item in options.items() if key != option_id]
    payload = {
        "schema": 1,
        "fork_id": fork_id,
        "title": fork.get("title", fork_id),
        "existing_constraint": fork.get("existing_constraint", ""),
        "requested_capability": fork.get("requested_capability", ""),
        "accepted_option": accepted,
        "rejected_options": rejected,
        "rationale": rationale,
        "authority": authority,
        "status": "confirmed",
        "evidence": fork.get("evidence", []),
    }
    event = record_event(project_root, "decision-fork-resolution", payload, source=authority)
    state = load_state(project_root)
    decisions = state.get("governing_decisions", {})
    if not isinstance(decisions, dict):
        decisions = {}
    decisions[fork_id] = {
        "event_id": event["id"],
        "utc": event["utc"],
        "accepted_option_id": option_id,
        "rationale": rationale,
        "authority": authority,
    }
    state["governing_decisions"] = decisions
    state["last_operation"] = "decision-fork-resolution"
    save_state(project_root, state)
    record_metric(project_root, "decision-fork-resolution", {
        "fork_id": fork_id,
        "accepted_option_id": option_id,
        "rejected_option_count": len(rejected),
        "authority": authority,
    })
    return {**payload, "event_id": event["id"], "resolved_utc": event["utc"]}


def _contradictions(
    project_root: Path,
    changes: dict[str, Any] | None,
    fork: dict[str, Any],
    resolution: dict[str, Any],
    signals: dict[str, Any],
) -> list[dict[str, Any]]:
    accepted = resolution.get("accepted_option", {})
    option_id = str(accepted.get("id", "")) if isinstance(accepted, dict) else ""
    changed = set(changes.get("paths", [])) if isinstance(changes, dict) and isinstance(changes.get("paths"), list) else set()
    warnings: list[dict[str, Any]] = []
    if fork.get("id") != "deadline-precision":
        return warnings
    implementation_paths = {
        item["path"] for group in (signals["date_only"], signals["exact_implementation"], signals["coercions"])
        for item in group if not item.get("authority")
    }
    relevant_changed = sorted(changed & implementation_paths)
    if option_id == "add-optional-exact-time":
        conflicting = [item for item in signals["coercions"] if not changed or item["path"] in changed]
        if conflicting:
            warnings.append({
                "fork_id": fork["id"],
                "severity": "warning",
                "message": "Observed work appears to coerce exact deadlines into date-only values, contradicting the confirmed optional exact-time decision.",
                "paths": sorted({item["path"] for item in conflicting}),
                "decision_event": resolution.get("event_id", ""),
            })
        elif relevant_changed and signals["date_only"] and not signals["exact_implementation"]:
            warnings.append({
                "fork_id": fork["id"],
                "severity": "warning",
                "message": "Changed implementation still exposes date-only deadline storage while the confirmed decision requires optional exact-time support.",
                "paths": relevant_changed,
                "decision_event": resolution.get("event_id", ""),
            })
    elif option_id == "preserve-date-only":
        conflicting = [item for item in signals["exact_implementation"] if not changed or item["path"] in changed]
        if conflicting:
            warnings.append({
                "fork_id": fork["id"],
                "severity": "warning",
                "message": "Observed work introduces exact-time storage despite the confirmed decision to preserve date-only deadlines.",
                "paths": sorted({item["path"] for item in conflicting}),
                "decision_event": resolution.get("event_id", ""),
            })
    elif option_id == "coerce-exact-presets-to-dates" and signals["exact_implementation"]:
        warnings.append({
            "fork_id": fork["id"],
            "severity": "warning",
            "message": "Observed work introduces exact-time storage despite the confirmed decision to coerce exact presets to dates.",
            "paths": sorted({item["path"] for item in signals["exact_implementation"]}),
            "decision_event": resolution.get("event_id", ""),
        })
    return warnings


def analyze_decision_forks(
    project_root: Path,
    forge_root: Path,
    *,
    authorities: dict[str, Any] | None = None,
    changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    if authorities is None:
        authorities = read_json(ForgePaths(project_root).authorities, {})
        if not isinstance(authorities, dict):
            authorities = {}
    signals = _scan_signals(project_root, forge_root, authorities)
    forks = [item for item in (_deadline_precision_fork(signals),) if isinstance(item, dict)]
    resolutions = latest_fork_resolutions(project_root)
    pending: list[dict[str, Any]] = []
    governing: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    for fork in forks:
        resolution = resolutions.get(str(fork.get("id", "")))
        if resolution:
            accepted = resolution.get("accepted_option", {}) if isinstance(resolution.get("accepted_option"), dict) else {}
            governing.append({
                "fork_id": fork["id"],
                "title": fork["title"],
                "accepted_option": accepted,
                "rejected_options": resolution.get("rejected_options", []),
                "rationale": resolution.get("rationale", ""),
                "authority": resolution.get("authority", ""),
                "event_id": resolution.get("event_id", ""),
                "utc": resolution.get("utc", ""),
                "existing_constraint": resolution.get("existing_constraint", fork.get("existing_constraint", "")),
            })
            contradictions.extend(_contradictions(project_root, changes, fork, resolution, signals))
        else:
            pending.append(fork)
    # Retain governing decisions even if the triggering prose is later removed.
    known_ids = {item["fork_id"] for item in governing}
    for fork_id, resolution in resolutions.items():
        if fork_id in known_ids:
            continue
        accepted = resolution.get("accepted_option", {}) if isinstance(resolution.get("accepted_option"), dict) else {}
        governing.append({
            "fork_id": fork_id,
            "title": resolution.get("title", fork_id),
            "accepted_option": accepted,
            "rejected_options": resolution.get("rejected_options", []),
            "rationale": resolution.get("rationale", ""),
            "authority": resolution.get("authority", ""),
            "event_id": resolution.get("event_id", ""),
            "utc": resolution.get("utc", ""),
            "existing_constraint": resolution.get("existing_constraint", ""),
        })
    return {
        "schema": 1,
        "generated_utc": utc_now(),
        "forks": forks,
        "pending": pending,
        "governing_decisions": sorted(governing, key=lambda item: str(item.get("fork_id", ""))),
        "contradictions": contradictions,
        "scan": {"files": signals["scanned_files"]},
    }

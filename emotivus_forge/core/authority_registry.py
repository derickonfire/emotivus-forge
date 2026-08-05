from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from .common import read_json, utc_now, write_json
from .ledger import record_event
from .orientation import iter_project_files
from .paths import ForgePaths

AUTHORITY_NAMES: dict[str, tuple[str, ...]] = {
    "roadmap": ("roadmap.md", "backlog.md", "todo.md", "plan.md"),
    "release": ("release.md", "release-notes.md", "changelog.md", "current-release.md"),
    "decisions": ("decisions.md", "adr.md", "architecture-decisions.md", "governance.md"),
    "requirements": ("requirements.md", "spec.md", "product.md", "prd.md"),
    "verification": ("verification.md", "quality.md", "testing.md", "certification.md"),
}
AUTHORITY_KINDS = tuple(AUTHORITY_NAMES)
ARCHIVE_PARTS = {"archive", "archived", "old", "legacy", "deprecated", "history", "historical"}

OBJECTIVE_HEADINGS = (
    "the next action", "next action", "exact next action", "current objective",
    "active objective", "current work", "do next", "immediate next development sequence",
)
GOVERNANCE_HEADINGS = (
    "governance", "owner decisions", "decision authority", "rules", "constraints",
)

AUTHORITY_LINK_RE = re.compile(
    r"`(?P<code>[^`]+\.(?:md|txt|rst))`"
    r"|\[[^\]]+\]\((?P<link>[^)]+\.(?:md|txt|rst))(?:#[^)]+)?\)"
    r"|(?P<plain>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:md|txt|rst))",
    re.I,
)
COMPLETE_MARKERS = re.compile(
    r"\b(?:built|satisfied|closed|complete(?:d)?|shipped|done|resolved|implemented|retired|cancelled|canceled)\b",
    re.I,
)
OPEN_MARKERS = re.compile(r"\b(?:open|next|todo|pending|planned|deferred|active|build|implement|create|add|fix)\b", re.I)
META_REDIRECT = re.compile(r"\b(?:see|refer(?: to)?|consult|full ordered plan|roadmap order|ordered plan)\b", re.I)


def _kind_for_name(name: str) -> tuple[str, int]:
    lower = name.lower()
    for kind, names in AUTHORITY_NAMES.items():
        if lower in names:
            return kind, 100
    if lower.endswith((".md", ".txt", ".rst")):
        for kind, names in AUTHORITY_NAMES.items():
            if any(token.split(".", 1)[0] in lower for token in names):
                return kind, 65
    return "record", 20


def _read_text(path: Path, limit: int = 256_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            if current_title or current_lines:
                sections.append((current_title, current_lines))
            current_title = re.sub(r"[*_`]+", "", match.group(1)).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title or current_lines:
        sections.append((current_title, current_lines))
    return sections


def _strip_action_prefix(value: str) -> str:
    value = re.sub(r"^[-*+]\s+", "", value)
    value = re.sub(r"^\d+[.)]\s+", "", value)
    value = re.sub(r"^\[[ xX]\]\s+", "", value)
    return value.strip()


def _first_action(lines: list[str]) -> str:
    for raw in lines:
        value = raw.strip()
        if not value or value.startswith("<!--"):
            continue
        value = _strip_action_prefix(value)
        if value and not value.startswith("#"):
            return value[:600]
    return ""


def _authority_links(value: str) -> list[str]:
    links: list[str] = []
    for match in AUTHORITY_LINK_RE.finditer(value):
        raw = next((group for group in match.groups() if group), "")
        raw = raw.strip().split("#", 1)[0].replace("\\", "/")
        while raw.startswith("./"):
            raw = raw[2:]
        if raw and raw not in links:
            links.append(raw)
    return links


def _objective_quality(value: str) -> tuple[str, str]:
    clean = " ".join(value.split()).strip()
    if not clean:
        return "rejected", "Objective text is empty."
    links = _authority_links(clean)
    if links and META_REDIRECT.search(clean):
        return "redirect", "The line points to a more authoritative planning record instead of stating the work itself."
    if len(clean) < 8:
        return "rejected", "Objective text is too short to guide work safely."
    if clean.count("`") % 2 or clean.count("[") != clean.count("]") or clean.count("(") != clean.count(")"):
        return "rejected", "Objective text contains an incomplete markup fragment."
    tail = re.search(r"[.!?]\s+([A-Za-z][A-Za-z -]{0,30})$", clean)
    if tail and len(tail.group(1).split()) <= 3 and not clean.endswith((".", "!", "?", ")", "]", "`")):
        return "rejected", "Objective text appears truncated after a completed sentence."
    if clean.endswith(("…", "...")):
        return "rejected", "Objective text ends in an unresolved truncation marker."
    return "accepted", ""


def _completed_item(raw: str) -> bool:
    value = raw.strip()
    if re.match(r"^[-*+]\s+\[[xX]\]", value):
        return True
    lower = value.casefold()
    if any(token in lower for token in ("not complete", "not completed", "not built", "not shipped", "unresolved")):
        return False
    return bool(COMPLETE_MARKERS.search(value)) and not bool(OPEN_MARKERS.search(value))


def _ordered_candidates(text: str) -> list[str]:
    sections = _sections(text)
    preferred: list[list[str]] = []
    fallback: list[list[str]] = []
    for title, lines in sections:
        normalized = re.sub(r"[^a-z0-9]+", " ", title).strip()
        if any(token in normalized for token in ("roadmap", "order", "next", "active", "current", "priority", "plan")):
            preferred.append(lines)
        else:
            fallback.append(lines)
    results: list[str] = []
    for lines in [*preferred, *fallback]:
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith(("<!--", "#")):
                continue
            if line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if not cells or all(re.fullmatch(r":?-{3,}:?", cell or "---") for cell in cells):
                    continue
                if any(cell.casefold() in {"item", "status", "state", "roadmap item", "actual state"} for cell in cells):
                    continue
                if _completed_item(" ".join(cells)):
                    continue
                meaningful = [cell for cell in cells if cell and not re.fullmatch(r"\d+[.)]?", cell)]
                if meaningful:
                    candidate = meaningful[0]
                    if candidate not in results:
                        results.append(candidate[:600])
                continue
            if not re.match(r"^(?:[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s+)", line):
                continue
            if _completed_item(line):
                continue
            candidate = _strip_action_prefix(line)
            candidate = re.sub(r"\s+(?:—|-|:)\s+(?:OPEN|PENDING|PLANNED|DEFERRED)\s*$", "", candidate, flags=re.I)
            quality, _ = _objective_quality(candidate)
            if quality == "accepted" and candidate not in results:
                results.append(candidate[:600])
    return results


def _resolve_link_path(project_root: Path, source_relative: str, raw: str) -> Path | None:
    candidates = [project_root / raw]
    source_parent = (project_root / source_relative).parent
    candidates.append(source_parent / raw)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(project_root.resolve())
        except (OSError, ValueError):
            continue
        if resolved.is_file() and not resolved.is_symlink():
            return resolved
    return None


def _extract_objective(text: str) -> tuple[str, str, str]:
    for title, lines in _sections(text):
        normalized = re.sub(r"[^a-z0-9]+", " ", title).strip()
        if any(heading == normalized or heading in normalized for heading in OBJECTIVE_HEADINGS):
            action = _first_action(lines)
            if action:
                quality, _ = _objective_quality(action)
                return action, title, "explicit" if quality == "accepted" else quality
    for line in text.splitlines():
        match = re.match(r"^\s*(?:next action|current objective|do next)\s*:\s*(.+)$", line, re.I)
        if match and match.group(1).strip():
            action = match.group(1).strip()[:600]
            quality, _ = _objective_quality(action)
            return action, "inline", "explicit" if quality == "accepted" else quality
    return "", "", "unknown"


def _resolve_linked_objective(
    project_root: Path, source_relative: str, action: str, *, max_depth: int = 2
) -> dict[str, str] | None:
    pending = [(source_relative, action, 0)]
    visited: set[str] = set()
    while pending:
        linked_from, value, depth = pending.pop(0)
        if depth >= max_depth:
            continue
        for raw in _authority_links(value):
            target = _resolve_link_path(project_root, linked_from, raw)
            if target is None:
                continue
            relative = target.relative_to(project_root.resolve()).as_posix()
            if relative in visited:
                continue
            visited.add(relative)
            target_text = _read_text(target)
            if not target_text:
                continue
            objective, heading, status = _extract_objective(target_text)
            if objective:
                quality, reason = _objective_quality(objective)
                if quality == "accepted":
                    return {
                        "text": objective, "source": relative, "heading": heading,
                        "status": "linked-explicit", "linked_from": source_relative,
                        "resolution_method": "authority-link", "rejection_reason": "",
                    }
                if quality == "redirect":
                    pending.append((relative, objective, depth + 1))
                elif reason:
                    continue
            ordered = _ordered_candidates(target_text)
            if ordered:
                return {
                    "text": ordered[0], "source": relative, "heading": "ordered-plan",
                    "status": "linked-ordered", "linked_from": source_relative,
                    "resolution_method": "authority-link", "rejection_reason": "",
                }
    return None

def _extract_governance(text: str) -> list[str]:
    result: list[str] = []
    for title, lines in _sections(text):
        normalized = re.sub(r"[^a-z0-9]+", " ", title).strip()
        if any(heading in normalized for heading in GOVERNANCE_HEADINGS):
            for raw in lines:
                value = re.sub(r"^\s*[-*+]\s+", "", raw).strip()
                if value and len(value) <= 500 and value not in result:
                    result.append(value)
                if len(result) >= 12:
                    return result
    return result


def _lifecycle(relative: str) -> tuple[str, int]:
    parts = {part.lower() for part in Path(relative).parts}
    if parts & ARCHIVE_PARTS:
        return "archived", -45
    return "active-candidate", 0


def _precedence_bonus(relative: str, kind: str, settings: dict[str, Any] | None) -> int:
    if not isinstance(settings, dict):
        return 0
    precedence = settings.get("authority_path_precedence", {})
    if not isinstance(precedence, dict):
        return 0
    patterns = precedence.get(kind, [])
    if not isinstance(patterns, list):
        return 0
    for index, raw in enumerate(patterns):
        pattern = str(raw).strip()
        if pattern and fnmatch.fnmatch(relative, pattern):
            return max(5, 60 - index * 5)
    return 0


def discover_authorities(
    project_root: Path,
    forge_root: Path,
    *,
    max_candidates: int = 40,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    objective_options: list[dict[str, Any]] = []
    rejected_objectives: list[dict[str, Any]] = []
    governance: list[dict[str, Any]] = []
    for path in iter_project_files(project_root, forge_root, max_files=1000, max_depth=5):
        if path.suffix.lower() not in {".md", ".txt", ".rst"}:
            continue
        kind, score = _kind_for_name(path.name)
        if score < 60 and len(candidates) >= max_candidates:
            continue
        text = _read_text(path)
        if not text:
            continue
        relative = path.relative_to(project_root).as_posix()
        lifecycle, lifecycle_adjustment = _lifecycle(relative)
        objective, heading, objective_status = _extract_objective(text)
        linked_objective: dict[str, str] | None = None
        objective_quality, rejection_reason = _objective_quality(objective) if objective else ("rejected", "")
        if objective and objective_quality == "redirect":
            linked_objective = _resolve_linked_objective(project_root, relative, objective)
        rules = _extract_governance(text)
        score += lifecycle_adjustment + _precedence_bonus(relative, kind, settings)
        accepted_objective = bool(linked_objective or (objective and objective_quality == "accepted"))
        candidate = {
            "path": relative,
            "kind": kind,
            "score": score + (30 if accepted_objective else 0) + (10 if rules else 0),
            "status": "observed",
            "lifecycle": lifecycle,
            "objective_heading": linked_objective.get("heading", "") if linked_objective else heading,
        }
        candidates.append(candidate)
        if linked_objective:
            objective_options.append({
                **linked_objective,
                "score": candidate["score"] + 20,
                "lifecycle": _lifecycle(linked_objective["source"])[0],
            })
            rejected_objectives.append({
                "text": objective, "source": relative, "heading": heading,
                "status": objective_status, "reason": "Redirected to the linked authoritative planning record.",
            })
        elif objective and objective_quality == "accepted":
            objective_options.append({
                "text": objective,
                "source": relative,
                "heading": heading,
                "score": candidate["score"],
                "status": objective_status,
                "lifecycle": lifecycle,
                "linked_from": "",
                "resolution_method": "direct",
            })
        elif objective:
            rejected_objectives.append({
                "text": objective, "source": relative, "heading": heading,
                "status": objective_status, "reason": rejection_reason or "Objective text is not safe to use as a work instruction.",
            })
        if rules:
            governance.append({"source": relative, "rules": rules, "score": candidate["score"], "lifecycle": lifecycle})
    candidates.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
    objective_options.sort(key=lambda item: (-int(item["score"]), str(item["source"])))
    selected = objective_options[0] if objective_options else {
        "text": "", "source": "", "heading": "", "score": 0, "status": "unknown", "lifecycle": "unknown"
    }
    conflicts = [item for item in objective_options[1:6] if item["text"] != selected["text"]]
    selected_by_kind: dict[str, dict[str, Any] | None] = {}
    for kind in AUTHORITY_KINDS:
        selected_by_kind[kind] = next((item for item in candidates if item["kind"] == kind and item["lifecycle"] != "archived"), None)
    return {
        "schema": 2,
        "updated_utc": utc_now(),
        "candidates": candidates[:max_candidates],
        "selected_by_kind": selected_by_kind,
        "objective": {
            **selected,
            "confidence": "high" if selected["status"] in {"explicit", "linked-explicit", "linked-ordered"} and not conflicts and selected.get("lifecycle") != "archived" else "medium" if selected["text"] else "low",
            "alternatives": conflicts,
        },
        "rejected_objectives": rejected_objectives[:12],
        "governance": sorted(governance, key=lambda item: -int(item["score"]))[:8],
        "confirmation": {
            "required": bool(conflicts) or not bool(selected["text"]),
            "reason": (
                "Conflicting objective records were found." if conflicts
                else "Objective candidates were rejected as fragments or redirects without a resolvable authority target." if rejected_objectives and not selected["text"]
                else "No explicit current objective was found." if not selected["text"]
                else ""
            ),
        },
    }


def _apply_confirmed(discovered: dict[str, Any], confirmed: dict[str, Any]) -> None:
    discovered["confirmed"] = confirmed
    roles = confirmed.get("roles", {})
    if isinstance(roles, dict):
        selected = discovered.get("selected_by_kind", {})
        if not isinstance(selected, dict):
            selected = {}
        for kind, source in roles.items():
            if kind not in AUTHORITY_KINDS:
                continue
            match = next((item for item in discovered.get("candidates", []) if item.get("path") == source), None)
            if match:
                selected[kind] = {**match, "status": "confirmed"}
        discovered["selected_by_kind"] = selected
    confirmed_objective = str(confirmed.get("objective", "")).strip()
    if confirmed_objective:
        discovered["objective"] = {
            "text": confirmed_objective,
            "source": str(confirmed.get("objective_source", "owner")),
            "heading": "owner-confirmed",
            "score": 1000,
            "status": "confirmed",
            "lifecycle": "confirmed",
            "confidence": "high",
            "alternatives": discovered.get("objective", {}).get("alternatives", []),
        }
        discovered["confirmation"] = {"required": False, "reason": ""}


def load_or_discover_authorities(
    project_root: Path,
    forge_root: Path,
    *,
    refresh: bool = True,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = ForgePaths(project_root)
    existing = read_json(paths.authorities, {})
    if not refresh and isinstance(existing, dict) and existing.get("schema") in {1, 2}:
        return existing
    budget = int(settings.get("authority_candidate_budget", 40)) if isinstance(settings, dict) else 40
    discovered = discover_authorities(project_root, forge_root, max_candidates=budget, settings=settings)
    if isinstance(existing, dict):
        confirmed = existing.get("confirmed", {})
        if isinstance(confirmed, dict):
            _apply_confirmed(discovered, confirmed)
    write_json(paths.authorities, discovered)
    return discovered


def confirm_authorities(
    project_root: Path,
    forge_root: Path,
    *,
    objective: str = "",
    objective_source: str = "owner",
    roles: dict[str, str] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    registry = load_or_discover_authorities(project_root, forge_root, refresh=True, settings=settings)
    existing = registry.get("confirmed", {})
    confirmed = dict(existing) if isinstance(existing, dict) else {}
    clean_objective = objective.strip()
    if clean_objective:
        clean_source = objective_source.strip() or "owner"
        if clean_source != "owner":
            source_path = (project_root / clean_source).resolve()
            try:
                source_path.relative_to(project_root)
            except ValueError as exc:
                raise RuntimeError(f"Objective source must remain inside the project: {clean_source}") from exc
            if not source_path.is_file():
                raise RuntimeError(f"Objective source does not exist: {clean_source}")
            clean_source = source_path.relative_to(project_root).as_posix()
        confirmed["objective"] = clean_objective[:600]
        confirmed["objective_source"] = clean_source
    if roles:
        clean_roles = dict(confirmed.get("roles", {})) if isinstance(confirmed.get("roles"), dict) else {}
        candidate_paths = {str(item.get("path")) for item in registry.get("candidates", []) if isinstance(item, dict)}
        for kind, source in roles.items():
            if kind not in AUTHORITY_KINDS:
                raise RuntimeError(f"Unknown authority kind: {kind}")
            clean_source = source.strip()
            if clean_source not in candidate_paths:
                raise RuntimeError(f"Authority candidate is not registered for {kind}: {clean_source}")
            clean_roles[kind] = clean_source
        confirmed["roles"] = clean_roles
    if not confirmed:
        raise RuntimeError("No authority confirmation was supplied.")
    confirmed["confirmed_utc"] = utc_now()
    registry["confirmed"] = confirmed
    _apply_confirmed(registry, confirmed)
    write_json(ForgePaths(project_root).authorities, registry)
    record_event(project_root, "authority-confirmation", {
        "objective": confirmed.get("objective", ""),
        "objective_source": confirmed.get("objective_source", ""),
        "roles": confirmed.get("roles", {}),
        "confirmed_utc": confirmed.get("confirmed_utc", ""),
    }, source="owner")
    return registry

"""Non-authoritative code orientation.

Orientation answers "where does work happen in this project" so a session can spend
its attention well. It is **inference**, and Forge marks it as inference everywhere.

Three views:

``active_zones``
    Directories weighted by how often the change ledger recorded work in them.

``centrality``
    Files weighted by how many other files reference them.

``coupling``
    File pairs that the ledger recorded changing together.

Every record carries ``authority: "none"`` and ``evidence_tier: "inferred"``. Nothing here
may advance a baseline, qualify a Check, authorize a release, or become a governed fact. A
file that scores high is a file worth *looking* at, never a file proven important. Zones and
coupling come only from recorded ledger history; when no ledger exists, Forge reports an
explicit knowledge gap rather than guessing from filesystem timestamps, which vary by
checkout, copy, and archive extraction.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

AUTHORITY = "none"
EVIDENCE_TIER = "inferred"

SOURCE_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".php", ".rb", ".go",
    ".rs", ".java", ".cs", ".css", ".scss", ".sql", ".sh", ".html",
}

# A reference is the file's stem appearing as a whole word elsewhere. This is a
# deliberately shallow signal: it needs no language server, no parse tree, and no
# network, and it degrades honestly across mixed-language trees.
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

TRUTH_BOUNDARY = (
    "Code orientation is inferred from shallow textual references and recorded ledger "
    "history. It is not a call graph, not a dependency resolution, and not proof that any "
    "file matters. A high score means look here first; it never means authorized, verified, "
    "or important. Orientation must not advance a baseline, qualify a Check, or authorize a "
    "release."
)


def _is_source(relative: str) -> bool:
    return Path(relative).suffix.lower() in SOURCE_SUFFIXES


def _stem(relative: str) -> str:
    return Path(relative).stem


def _zone_of(relative: str, depth: int = 2) -> str:
    parts = Path(relative).parts[:-1]
    if not parts:
        return "."
    return "/".join(parts[:depth])


def _record(**fields: Any) -> dict[str, Any]:
    row = {"authority": AUTHORITY, "evidence_tier": EVIDENCE_TIER}
    row.update(fields)
    return row


def compute_centrality(
    project_root: Path,
    relative_paths: Iterable[str],
    *,
    max_files: int = 400,
    max_file_bytes: int = 512_000,
    top: int = 20,
) -> dict[str, Any]:
    """Rank files by how many *other* files mention their stem as a whole word.

    Self-references never count. A stem shared by several files is ambiguous, so every
    file carrying that stem is marked ``ambiguous_stem`` rather than silently credited.
    """
    sources = sorted(p for p in relative_paths if _is_source(p))
    truncated = len(sources) > max_files
    sources = sources[:max_files]
    stem_owners: dict[str, list[str]] = defaultdict(list)
    for relative in sources:
        stem_owners[_stem(relative)].append(relative)

    referenced_by: dict[str, set[str]] = defaultdict(set)
    scanned = 0
    for relative in sources:
        path = project_root / relative
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size > max_file_bytes:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        own = _stem(relative)
        for word in set(_WORD.findall(text)):
            if word == own or word not in stem_owners:
                continue
            for owner in stem_owners[word]:
                if owner != relative:
                    referenced_by[owner].add(relative)

    rows = [
        _record(
            path=relative,
            referenced_by_count=len(referenced_by.get(relative, ())),
            ambiguous_stem=len(stem_owners[_stem(relative)]) > 1,
        )
        for relative in sources
    ]
    rows.sort(key=lambda r: (-r["referenced_by_count"], r["path"]))
    return {
        "top": rows[:top],
        "files_considered": len(sources),
        "files_scanned": scanned,
        "truncated": truncated,
        "method": "whole-word stem reference counting, self-references excluded",
    }


def compute_active_zones(
    events: Iterable[dict[str, Any]] | None,
    *,
    depth: int = 2,
    top: int = 15,
) -> dict[str, Any]:
    """Weight directories by recorded ledger activity. No ledger means no claim."""
    if events is None:
        return {
            "top": [],
            "events_considered": 0,
            "knowledge_gap": "No change ledger was supplied, so active zones are unknown.",
            "method": "ledger-recorded changed paths only",
        }
    counts: Counter[str] = Counter()
    considered = 0
    for event in events:
        paths = event.get("paths") or event.get("changed_paths") or []
        if not isinstance(paths, list):
            continue
        considered += 1
        for relative in {str(p) for p in paths if isinstance(p, str)}:
            counts[_zone_of(relative, depth)] += 1
    rows = [_record(zone=zone, event_count=count) for zone, count in counts.items()]
    rows.sort(key=lambda r: (-r["event_count"], r["zone"]))
    result = {
        "top": rows[:top],
        "events_considered": considered,
        "method": "ledger-recorded changed paths only",
    }
    if not rows:
        result["knowledge_gap"] = "The change ledger recorded no changed paths."
    return result


def compute_coupling(
    events: Iterable[dict[str, Any]] | None,
    *,
    min_events: int = 2,
    top: int = 20,
    max_paths_per_event: int = 60,
) -> dict[str, Any]:
    """Pair files the ledger recorded changing together at least ``min_events`` times.

    Events touching very many paths are skipped: a sweeping refactor couples everything
    with everything and would drown the signal in noise.
    """
    if events is None:
        return {
            "top": [],
            "events_considered": 0,
            "knowledge_gap": "No change ledger was supplied, so change coupling is unknown.",
            "method": "ledger co-occurrence",
            "min_events": min_events,
        }
    pairs: Counter[tuple[str, str]] = Counter()
    considered = 0
    skipped_wide = 0
    for event in events:
        paths = event.get("paths") or event.get("changed_paths") or []
        if not isinstance(paths, list):
            continue
        unique = sorted({str(p) for p in paths if isinstance(p, str)})
        if len(unique) > max_paths_per_event:
            skipped_wide += 1
            continue
        considered += 1
        for i, left in enumerate(unique):
            for right in unique[i + 1:]:
                pairs[(left, right)] += 1
    rows = [
        _record(paths=[left, right], co_change_count=count)
        for (left, right), count in pairs.items()
        if count >= min_events
    ]
    rows.sort(key=lambda r: (-r["co_change_count"], r["paths"][0], r["paths"][1]))
    result = {
        "top": rows[:top],
        "events_considered": considered,
        "wide_events_skipped": skipped_wide,
        "min_events": min_events,
        "method": "ledger co-occurrence",
    }
    if not rows:
        result["knowledge_gap"] = "No file pair reached the co-change threshold."
    return result


def orient_code(
    project_root: Path,
    relative_paths: Iterable[str],
    events: Iterable[dict[str, Any]] | None = None,
    **budgets: Any,
) -> dict[str, Any]:
    """Produce one bounded, deterministic, explicitly non-authoritative orientation."""
    paths = list(relative_paths)
    events_list = list(events) if events is not None else None
    centrality = compute_centrality(project_root, paths, **{
        k: v for k, v in budgets.items() if k in ("max_files", "max_file_bytes", "top")
    })
    zones = compute_active_zones(events_list)
    coupling = compute_coupling(events_list)
    gaps = [
        view[key]
        for view, key in ((zones, "knowledge_gap"), (coupling, "knowledge_gap"))
        if key in view
    ]
    return {
        "schema": "forge-code-orientation/1",
        "authority": AUTHORITY,
        "evidence_tier": EVIDENCE_TIER,
        "advances_baseline": False,
        "qualifies_check": False,
        "authorizes_release": False,
        "becomes_governed_fact": False,
        "active_zones": zones,
        "centrality": centrality,
        "coupling": coupling,
        "knowledge_gaps": gaps,
        "truth_boundary": TRUTH_BOUNDARY,
    }

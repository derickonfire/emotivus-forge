"""Append-only, hash-chained witness ledger: claim -> ground truth -> verdict.

This is the durable home for the "man with the binoculars" role: a record of claims
made across a collaboration (governance docs, bus messages, checkpoints) each bound to
independently-verifiable ground truth (git objects, file bytes, run IDs) with a verdict.

It is deliberately SEPARATE from the Forge event ledger (`core/ledger.py`, which records
Forge's own lifecycle events) and from ledger-assertions (`core/ledger_assertions.py`,
which record obligations to re-check). This ledger records witness *history*.

Honesty invariants (carried from Forge's founding "never upgrade NOT_RUN to PASS" rule):
  * Append-only. Entries are never mutated or deleted.
  * A changed verdict is a NEW entry that SUPERSEDES the prior one; the superseded entry
    stays readable and the lineage is preserved (supersede, don't delete).
  * No auto-upgrade. Nothing here changes an entry's verdict. UNVERIFIABLE is terminal
    for its entry and never silently becomes CONFIRMED.
  * Hash-chained. Every entry carries the canonical hash of the prior entry, so any
    tamper (including an edited verdict) is detectable.

Boundary: this ledger records verdicts and their provenance. It does NOT re-derive
ground truth (that is the binder track). `verify_ledger` proves chain integrity, not the
correctness of any single verdict.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import append_jsonl, read_jsonl, read_jsonl_report, utc_now
from .paths import ForgePaths

SCHEMA = 1
VERDICTS = {"CONFIRMED", "CONTRADICTED", "UNVERIFIABLE", "INCOMPLETE"}
_CANONICAL_EXCLUDED = {"entry_hash"}

TRUTH_LEDGER_BOUNDARY = (
    "This ledger records witness verdicts and their provenance, append-only and "
    "supersede-not-delete. It does not re-derive ground truth; an entry is only as sound "
    "as the method that produced its verdict. Verification proves chain integrity, not "
    "that any single verdict is correct."
)


def _canonical_hash(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key not in _CANONICAL_EXCLUDED}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _entry_id(timestamp: str, semantic: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    return f"tl-{timestamp.replace('-', '').replace(':', '')[:15]}-{digest}"


def _require_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Truth-ledger entry requires {label}.")
    return text


def _normalize_ground_truth(ground_truth: Any) -> dict[str, Any]:
    if ground_truth in (None, ""):
        return {"kind": "none"}
    if not isinstance(ground_truth, dict):
        raise ValueError("Truth-ledger ground_truth must be an object.")
    kind = str(ground_truth.get("kind", "")).strip() or "none"
    normalized = {"kind": kind}
    for key in ("pointer", "observed", "expected"):
        if key in ground_truth and ground_truth[key] not in (None, ""):
            normalized[key] = ground_truth[key]
    return normalized


def truth_ledger_path(project_root: Path) -> Path:
    return ForgePaths(project_root).truth_ledger


def read_ledger(project_root: Path) -> list[dict[str, Any]]:
    return read_jsonl(truth_ledger_path(project_root))


def _tip_ids(entries: list[dict[str, Any]]) -> set[str]:
    superseded = {str(entry.get("supersedes", "")) for entry in entries if entry.get("supersedes")}
    return {str(entry.get("id", "")) for entry in entries if str(entry.get("id", "")) not in superseded}


def append_claim(
    project_root: Path,
    *,
    claim: str,
    verdict: str,
    subject: str = "project",
    source: str = "",
    source_ref: str = "",
    ground_truth: Any = None,
    method: str = "",
    observer: str = "forge-observer",
    note: str = "",
    supersedes: str = "",
) -> dict[str, Any]:
    """Append one witness entry. A changed verdict must supersede a prior entry, never edit it."""
    claim_text = _require_text(claim, "a claim")
    verdict = str(verdict or "").strip().upper()
    if verdict not in VERDICTS:
        raise ValueError(f"Truth-ledger verdict must be one of {sorted(VERDICTS)}; got {verdict!r}.")
    subject = _require_text(subject, "a subject")
    supersedes = str(supersedes or "").strip()

    existing = read_ledger(project_root)
    lineage = ""
    if supersedes:
        target = next((entry for entry in existing if str(entry.get("id", "")) == supersedes), None)
        if target is None:
            raise ValueError(f"Cannot supersede unknown truth-ledger entry: {supersedes}")
        if supersedes not in _tip_ids(existing):
            raise ValueError(
                f"Truth-ledger entry {supersedes} is already superseded; supersede the current tip of its lineage instead."
            )
        lineage = str(target.get("lineage", "")) or supersedes

    timestamp = utc_now()
    semantic = {
        "subject": subject,
        "claim": claim_text,
        "verdict": verdict,
        "source": str(source or ""),
        "observer": str(observer or "forge-observer"),
        "supersedes": supersedes,
    }
    entry_id = _entry_id(timestamp, semantic)
    if not lineage:
        lineage = entry_id
    previous_hash = _canonical_hash(existing[-1]) if existing else ""
    entry = {
        "schema": SCHEMA,
        "id": entry_id,
        "utc": timestamp,
        "subject": subject,
        "claim": {"text": claim_text, "source": str(source or ""), "source_ref": str(source_ref or "")},
        "ground_truth": _normalize_ground_truth(ground_truth),
        "verdict": verdict,
        "method": str(method or ""),
        "observer": str(observer or "forge-observer"),
        "note": str(note or ""),
        "supersedes": supersedes,
        "lineage": lineage,
        "previous_entry_hash": previous_hash,
    }
    entry["entry_hash"] = _canonical_hash(entry)
    append_jsonl(truth_ledger_path(project_root), entry)
    return entry


def supersede_claim(
    project_root: Path,
    target_id: str,
    *,
    claim: str,
    verdict: str,
    **fields: Any,
) -> dict[str, Any]:
    """Convenience wrapper: append a new entry that supersedes ``target_id``.

    The prior entry is never modified; the new entry links to it and inherits its lineage.
    """
    target_id = _require_text(target_id, "a target entry id")
    return append_claim(project_root, claim=claim, verdict=verdict, supersedes=target_id, **fields)


def verify_ledger(project_root: Path) -> dict[str, Any]:
    """Verify chain integrity and report verdict tallies. Chain integrity only — not verdict correctness."""
    path = truth_ledger_path(project_root)
    rows, syntax_issues = read_jsonl_report(path)
    issues: list[dict[str, Any]] = [issue.to_dict() for issue in syntax_issues]
    previous_hash = ""
    for index, row in enumerate(rows, 1):
        actual = str(row.get("entry_hash", ""))
        expected = _canonical_hash(row)
        if not actual:
            issues.append({"path": str(path), "line": index, "message": "truth-ledger entry is missing its entry hash"})
        elif actual != expected:
            issues.append({"path": str(path), "line": index, "message": "truth-ledger entry hash does not match its content"})
        declared_previous = str(row.get("previous_entry_hash", ""))
        if declared_previous != previous_hash:
            issues.append({"path": str(path), "line": index, "message": "truth-ledger previous-entry hash does not match the preceding record"})
        verdict = str(row.get("verdict", ""))
        if verdict not in VERDICTS:
            issues.append({"path": str(path), "line": index, "message": f"truth-ledger entry has an unknown verdict: {verdict!r}"})
        previous_hash = expected
    tip_ids = _tip_ids(rows)
    tallies_all = _tally(rows)
    tallies_current = _tally([row for row in rows if str(row.get("id", "")) in tip_ids])
    return {
        "schema": SCHEMA,
        "status": "BLOCKED" if issues else "HEALTHY",
        "records": len(rows),
        "lineage_count": len({str(row.get("lineage", "")) for row in rows}),
        "tallies_current": tallies_current,
        "tallies_all": tallies_all,
        "contradicted_tips": sorted(
            str(row.get("id", "")) for row in rows if str(row.get("id", "")) in tip_ids and row.get("verdict") == "CONTRADICTED"
        ),
        "issues": issues,
        "truth_boundary": TRUTH_LEDGER_BOUNDARY,
    }


def _tally(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {verdict: 0 for verdict in sorted(VERDICTS)}
    for row in rows:
        verdict = str(row.get("verdict", ""))
        if verdict in counts:
            counts[verdict] += 1
    return counts


def _ordered_lineage(root: dict[str, Any], by_supersedes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [root]
    current_id = str(root.get("id", ""))
    seen = {current_id}
    while current_id in by_supersedes:
        nxt = by_supersedes[current_id]
        nxt_id = str(nxt.get("id", ""))
        if nxt_id in seen:  # defensive: never loop on a malformed chain
            break
        ordered.append(nxt)
        seen.add(nxt_id)
        current_id = nxt_id
    return ordered


def current_view(project_root: Path) -> dict[str, Any]:
    """Fold supersession: the current verdict per claim-lineage, with history and verdict flips."""
    rows = read_ledger(project_root)
    by_supersedes: dict[str, dict[str, Any]] = {}
    for row in rows:
        parent = str(row.get("supersedes", ""))
        if parent:
            by_supersedes[parent] = row
    lineage_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        lineage_groups.setdefault(str(row.get("lineage", "")), []).append(row)

    lineages: list[dict[str, Any]] = []
    total_flips = 0
    for lineage_id, group in lineage_groups.items():
        root = next((row for row in group if not str(row.get("supersedes", ""))), group[0])
        ordered = _ordered_lineage(root, by_supersedes)
        flips: list[dict[str, str]] = []
        for earlier, later in zip(ordered, ordered[1:]):
            if earlier.get("verdict") != later.get("verdict"):
                flips.append({
                    "from_verdict": str(earlier.get("verdict", "")),
                    "to_verdict": str(later.get("verdict", "")),
                    "from_id": str(earlier.get("id", "")),
                    "to_id": str(later.get("id", "")),
                })
        total_flips += len(flips)
        tip = ordered[-1]
        lineages.append({
            "lineage": lineage_id,
            "subject": str(tip.get("subject", "")),
            "claim": tip.get("claim", {}).get("text", "") if isinstance(tip.get("claim"), dict) else "",
            "current_verdict": str(tip.get("verdict", "")),
            "tip_id": str(tip.get("id", "")),
            "revisions": len(ordered) - 1,
            "verdict_flips": flips,
            "history": [
                {"id": str(item.get("id", "")), "verdict": str(item.get("verdict", "")), "utc": str(item.get("utc", ""))}
                for item in ordered
            ],
        })
    lineages.sort(key=lambda item: item["lineage"])
    return {
        "schema": SCHEMA,
        "lineage_count": len(lineages),
        "verdict_flip_count": total_flips,
        "tallies_current": _tally([
            next(row for row in rows if str(row.get("id", "")) == lineage["tip_id"]) for lineage in lineages
        ]) if lineages else _tally([]),
        "lineages": lineages,
        "truth_boundary": TRUTH_LEDGER_BOUNDARY,
    }

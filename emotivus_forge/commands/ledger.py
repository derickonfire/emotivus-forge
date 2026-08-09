"""`forge ledger` — the witness truth-ledger command surface.

Append-only, hash-chained, supersede-not-delete. Advisory and read-only with respect
to the project's authority state: it records witness verdicts, it never authorizes
anything.

  append    record a claim -> ground-truth -> verdict entry
  supersede append a new verdict that supersedes a prior entry (never edits it)
  verify    prove chain integrity (exit 0 HEALTHY, 1 BLOCKED)
  show      the current verdict per claim-lineage, with history and verdict flips
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.truth_ledger import (
    append_claim,
    current_view,
    supersede_claim,
    verify_ledger,
)
from .common import print_json


def _ground_truth(args: Any) -> dict[str, Any] | None:
    kind = str(getattr(args, "gt_kind", "") or "").strip()
    pointer = str(getattr(args, "gt_pointer", "") or "").strip()
    observed = str(getattr(args, "gt_observed", "") or "").strip()
    if not (kind or pointer or observed):
        return None
    payload: dict[str, Any] = {"kind": kind or "recorded"}
    if pointer:
        payload["pointer"] = pointer
    if observed:
        payload["observed"] = observed
    return payload


def _project(args: Any) -> Path:
    return Path(getattr(args, "project", ".") or ".").resolve()


def _render_entry(entry: dict[str, Any]) -> str:
    claim = entry.get("claim", {}) if isinstance(entry.get("claim"), dict) else {}
    lines = [
        f"forge ledger — recorded [{entry['verdict']}]",
        f"  id:      {entry['id']}",
        f"  subject: {entry['subject']}",
        f"  claim:   {claim.get('text', '')}",
    ]
    if entry.get("supersedes"):
        lines.append(f"  supersedes: {entry['supersedes']} (prior entry preserved)")
    lines.append(f"  lineage: {entry['lineage']}")
    return "\n".join(lines)


def _render_verify(report: dict[str, Any]) -> str:
    lines = [
        f"forge ledger verify — {report['status']}",
        f"  records: {report['records']}   lineages: {report['lineage_count']}",
        f"  current verdicts: {report['tallies_current']}",
    ]
    if report.get("contradicted_tips"):
        lines.append(f"  active CONTRADICTED: {', '.join(report['contradicted_tips'])}")
    for issue in report.get("issues", []):
        lines.append(f"  [issue] line {issue.get('line', '?')}: {issue.get('message', '')}")
    lines.append(f"  boundary: {report['truth_boundary']}")
    return "\n".join(lines)


def _render_show(view: dict[str, Any]) -> str:
    lines = [
        f"forge ledger — {view['lineage_count']} claim-lineage(s), {view['verdict_flip_count']} verdict flip(s)",
        f"  current verdicts: {view['tallies_current']}",
        "",
    ]
    for lineage in view["lineages"]:
        lines.append(f"  [{lineage['current_verdict']}] {lineage['claim']}")
        lines.append(f"        tip {lineage['tip_id']} · {lineage['revisions']} revision(s) · subject {lineage['subject']}")
        for flip in lineage["verdict_flips"]:
            lines.append(f"        ⟳ flip {flip['from_verdict']} → {flip['to_verdict']} ({flip['from_id']} → {flip['to_id']})")
    lines.append("")
    lines.append(f"  boundary: {view['truth_boundary']}")
    return "\n".join(lines)


def handle_ledger(args: Any, parser: Any, forge_root: Path) -> int:
    action = getattr(args, "ledger_command", None)
    json_output = bool(getattr(args, "json", False))

    if action == "append":
        entry = append_claim(
            _project(args),
            claim=args.claim,
            verdict=args.verdict,
            subject=getattr(args, "subject", "project"),
            source=getattr(args, "source", ""),
            source_ref=getattr(args, "source_ref", ""),
            ground_truth=_ground_truth(args),
            method=getattr(args, "method", ""),
            observer=getattr(args, "observer", "forge-observer"),
            note=getattr(args, "note", ""),
        )
        print_json(entry) if json_output else print(_render_entry(entry))
        return 0

    if action == "supersede":
        entry = supersede_claim(
            _project(args),
            args.target,
            claim=args.claim,
            verdict=args.verdict,
            subject=getattr(args, "subject", "project"),
            source=getattr(args, "source", ""),
            source_ref=getattr(args, "source_ref", ""),
            ground_truth=_ground_truth(args),
            method=getattr(args, "method", ""),
            observer=getattr(args, "observer", "forge-observer"),
            note=getattr(args, "note", ""),
        )
        print_json(entry) if json_output else print(_render_entry(entry))
        return 0

    if action == "verify":
        report = verify_ledger(_project(args))
        print_json(report) if json_output else print(_render_verify(report))
        return 0 if report["status"] == "HEALTHY" else 1

    if action == "show":
        view = current_view(_project(args))
        print_json(view) if json_output else print(_render_show(view))
        return 0

    parser.error("forge ledger requires an action: append | supersede | verify | show")
    return 2  # pragma: no cover - parser.error exits

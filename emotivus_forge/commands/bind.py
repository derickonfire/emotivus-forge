"""`forge bind` — first-class command surface for the deterministic G1 binders.

Advisory, read-only, never authority. Each binder's verdict maps to an exit code
so the command doubles as a CI gate:
  release-truth / gate-diff : 0 CONFIRMED, 1 CONTRADICTED, 2 NOT_RUN
  gate-coverage             : 0 COVERED,   1 GAPS,        2 NOT_RUN
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.source_anchored_release import bind_source_anchored_release, CONFIRMED, CONTRADICTED
from ..core.gate_coverage import report_gate_coverage, COVERED, GAPS
from ..core.gate_diff_monotonicity import report_gate_diff_monotonicity
from .common import print_json

_EXIT = {CONFIRMED: 0, CONTRADICTED: 1, COVERED: 0, GAPS: 1}  # everything else (NOT_RUN) -> 2


def _render(result: dict) -> str:
    lines = [f"forge bind — {result['verdict']}", f"  target: {result['target']}"]
    if "base" in result:
        lines.append(f"  base:   {result['base']}")
    lines.append(f"  head:   {result['head']}")
    if "inventory_count" in result:
        lines.append(f"  inventory: {result['inventory_count']} check(s); unwired: {len(result.get('unwired_checks', []))}")
    lines.append("")
    for f in result["findings"]:
        lines.append(f"  [{f['state']}] {f['check']}")
        lines.append(f"        {f['detail']}")
        if f.get("reproduce"):
            lines.append(f"        reproduce: {f['reproduce']}")
    lines.append("")
    lines.append(f"  truth boundary: {result['truth_boundary']}")
    return "\n".join(lines)


def handle_bind(args: Any, parser: Any, forge_root: Path) -> int:
    binder = getattr(args, "binder", None)
    if not binder:
        parser.error("forge bind requires a binder: release-truth | gate-coverage | gate-diff")
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"config error: {exc}")

    if binder == "release-truth":
        result = bind_source_anchored_release(args.repo, args.head, config)
    elif binder == "gate-coverage":
        result = report_gate_coverage(args.repo, args.head, config)
    elif binder == "gate-diff":
        result = report_gate_diff_monotonicity(args.repo, args.base, args.head, config)
    else:  # pragma: no cover - argparse guards the choices
        parser.error(f"unknown binder {binder!r}")

    if getattr(args, "json", False):
        print_json(result)
    else:
        print(_render(result))
    return _EXIT.get(result["verdict"], 2)

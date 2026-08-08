#!/usr/bin/env python3
"""Report check scripts present in a tree but not referenced by its declared gate sources.

Advisory, read-only. Exit code doubles as a CI gate: 0 COVERED, 1 GAPS, 2 NOT_RUN
(indeterminate — never upgraded to a coverage claim).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emotivus_forge.core.gate_coverage import (  # noqa: E402
    report_gate_coverage,
    COVERED,
    GAPS,
)

_EXIT = {COVERED: 0, GAPS: 1}


def _render(result: dict) -> str:
    lines = [
        f"gate-coverage differ — {result['verdict']}",
        f"  target: {result['target']}",
        f"  head:   {result['head']}",
        f"  inventory: {result['inventory_count']} check(s); unwired: {len(result['unwired_checks'])}",
        "",
    ]
    for f in result["findings"]:
        lines.append(f"  [{f['state']}] {f['check']}")
        lines.append(f"        {f['detail']}")
        if f.get("reproduce"):
            lines.append(f"        reproduce: {f['reproduce']}")
    lines.append("")
    lines.append(f"  truth boundary: {result['truth_boundary']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Path to the target git repository")
    parser.add_argument("--head", required=True, help="Commit/ref to assess")
    parser.add_argument("--config", required=True, type=Path, help="Gate-coverage config JSON")
    parser.add_argument("--json", action="store_true", help="Emit the typed result as JSON")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    result = report_gate_coverage(args.repo, args.head, config)
    print(json.dumps(result, indent=2) if args.json else _render(result))
    return _EXIT.get(result["verdict"], 2)


if __name__ == "__main__":
    raise SystemExit(main())

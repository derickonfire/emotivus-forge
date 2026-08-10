"""`forge init` — scaffold Forge's truth+protocol layer into a project repo (R10).

North-star headline: plant the discipline in ONE command, strictly additively, and
emit a protocol that `forge protocol verify` certifies on day one. Advisory: it
writes scaffolding into the TARGET repo (never Forge's own tree) and never
overwrites an existing file. Version-bump / seal stay the owner's act.

Exit code: 0 when the scaffold's seed protocol verifies (the day-one EXIT bar),
1 only if that internal self-check fails (a Forge bug, surfaced immediately).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.protocol_verify import CONFIRMED
from ..core.scaffold import apply_scaffold
from .common import print_json


def _render(result: dict) -> str:
    dry = result["dry_run"]
    header = f"forge init — {result['profile']} profile" + (" (dry run)" if dry else "")
    created = result["create_count"] if dry else len(result["written"])
    verb = "would create" if dry else "created"
    lines = [
        header,
        f"  target: {result['target']}   ci: {result['ci']}",
        f"  {verb}: {created}   skipped (already present): {result['skip_count']}",
        "",
    ]
    for p in result["planned"]:
        if p["action"] == "skip-exists":
            mark = "skip"
        else:
            mark = "would +" if dry else "+"
        lines.append(f"  [{mark}] {p['path']}")
    lines.append("")
    live = " / LIVE" if result["seed_liveness"] else ""
    lines.append(f"  seed protocol verifies: {result['seed_verdict']}{live}")
    lines.append("  next: wire ./forge-gate.sh into CI or a pre-push hook "
                 "(set FORGE=... if Forge is not on PATH).")
    return "\n".join(lines)


def handle_init(args: Any, parser: Any, forge_root: Path) -> int:
    target = getattr(args, "project", ".") or "."
    root = Path(target)
    if not root.exists():
        parser.error(f"target does not exist: {target}")
    if not root.is_dir():
        parser.error(f"target is not a directory: {target}")

    profile = getattr(args, "profile", "truth")
    ci = getattr(args, "ci", "none") or "none"
    try:
        result = apply_scaffold(str(root), profile, ci,
                                dry_run=bool(getattr(args, "dry_run", False)))
    except ValueError as exc:  # pragma: no cover - argparse guards the choices
        parser.error(str(exc))

    if getattr(args, "json", False):
        print_json(result)
    else:
        print(_render(result))
    return 0 if result["seed_verdict"] == CONFIRMED else 1

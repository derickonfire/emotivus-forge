"""`forge protocol verify` — verify a multi-agent git collaboration protocol (R9).

Advisory, read-only, never authority. The verdict maps to an exit code so the
command doubles as a CI gate for a coordination bus:
  0 CONFIRMED (all invariants hold) · 1 CONTRADICTED (a violation) · 2 NOT_RUN.

With ``--ledger`` the verdict is recorded in the project truth ledger as a
binder-derived entry (schema 2); a CONFIRMED protocol arrives machine-earned with
the re-run command, and an unassessable protocol lands as terminal UNVERIFIABLE.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.protocol_verify import CONFIRMED, CONTRADICTED, verify_protocol
from ..core.truth_ledger import record_binder_result
from .common import print_json

_EXIT = {CONFIRMED: 0, CONTRADICTED: 1}  # NOT_RUN -> 2


def _render(result: dict) -> str:
    lines = [
        f"forge protocol verify — {result['verdict']}",
        f"  target: {result['target']}   records: {result['record_count']}   "
        f"head-currency: {'yes' if result['head_currency_checked'] else 'no (no --repo)'}   "
        f"liveness: {'checked' if result['liveness_checked'] else 'skipped'}",
        "",
    ]
    for f in result["findings"]:
        lines.append(f"  [{f['state']}] {f['check']}")
        lines.append(f"        {f['detail']}")
        if f.get("reproduce"):
            lines.append(f"        reproduce: {f['reproduce']}")
    lines.append("")
    if result.get("ledger_entry_id"):
        lines.append(f"  ledger: recorded as {result['ledger_entry_id']} ({result['ledger_verdict']}, binder-derived)")
    lines.append(f"  truth boundary: {result['truth_boundary']}")
    return "\n".join(lines)


def handle_protocol(args: Any, parser: Any, forge_root: Path) -> int:
    if getattr(args, "protocol_command", None) != "verify":
        parser.error("forge protocol requires an action: verify")
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"config error: {exc}")
    if not isinstance(config, dict):
        parser.error("protocol config must be a JSON object")

    result = verify_protocol(
        config,
        repo=getattr(args, "repo", ""),
        check_liveness=bool(getattr(args, "liveness", False)),
        source=args.config,
    )

    if getattr(args, "ledger", False):
        try:
            entry = record_binder_result(
                Path(getattr(args, "project", ".") or ".").resolve(),
                result,
                source="forge protocol verify",
            )
            result["ledger_entry_id"] = entry["id"]
            result["ledger_verdict"] = entry["verdict"]
        except ValueError as exc:
            parser.error(f"ledger refused the protocol result: {exc}")

    if getattr(args, "json", False):
        print_json(result)
    else:
        print(_render(result))
    return _EXIT.get(result["verdict"], 2)

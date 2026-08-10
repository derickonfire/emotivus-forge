"""Integration tests for the `forge ledger` command surface (cli dispatch + exit codes)."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.cli import main


def _run(*argv: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(list(argv))
    return code, buffer.getvalue()


class LedgerCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_append_verify_show_cycle(self) -> None:
        code, out = _run(
            "ledger", "append", "--project", str(self.root),
            "--claim", "PR#20 head descends from base", "--verdict", "CONFIRMED",
            "--source", "WORK-REGISTER", "--gt-kind", "merge-base",
            "--derivation", "binder",
            "--reproduce", "git merge-base --is-ancestor 305fb7f e5dc360",
            "--json",
        )
        self.assertEqual(code, 0)
        entry = json.loads(out)
        self.assertEqual(entry["verdict"], "CONFIRMED")
        self.assertEqual(entry["derivation"], "binder")

        code, _ = _run("ledger", "verify", "--project", str(self.root))
        self.assertEqual(code, 0)

        code, out = _run("ledger", "show", "--project", str(self.root), "--json")
        self.assertEqual(code, 0)
        view = json.loads(out)
        self.assertEqual(view["lineage_count"], 1)

    def test_supersede_via_cli_and_flip(self) -> None:
        code, out = _run(
            "ledger", "append", "--project", str(self.root),
            "--claim", "stale read", "--verdict", "CONTRADICTED", "--json",
        )
        target = json.loads(out)["id"]
        code, out = _run(
            "ledger", "supersede", "--project", str(self.root), "--target", target,
            "--claim", "corrected read", "--verdict", "CONFIRMED",
            "--derivation", "binder", "--gt-kind", "git-rev-list",
            "--reproduce", "git fetch --force && git rev-parse HEAD",
            "--json",
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["supersedes"], target)

        code, out = _run("ledger", "show", "--project", str(self.root), "--json")
        self.assertEqual(json.loads(out)["verdict_flip_count"], 1)

    def test_verify_blocked_exit_code_on_tamper(self) -> None:
        _run("ledger", "append", "--project", str(self.root), "--claim", "a", "--verdict", "ATTESTED")
        _run("ledger", "append", "--project", str(self.root), "--claim", "b", "--verdict", "ATTESTED")
        path = self.root / ".forge" / "truth-ledger.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows[0]["verdict"] = "CONTRADICTED"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        code, _ = _run("ledger", "verify", "--project", str(self.root))
        self.assertEqual(code, 1)

    def test_invalid_verdict_is_rejected_by_argparse(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            _run("ledger", "append", "--project", str(self.root), "--claim", "x", "--verdict", "PASS")
        self.assertNotEqual(ctx.exception.code, 0)

    def test_hand_asserted_confirmed_is_refused_at_the_cli(self) -> None:
        # The field-note reproduction: bare `--verdict CONFIRMED` must not record.
        with self.assertRaises(SystemExit) as ctx:
            _run(
                "ledger", "append", "--project", str(self.root),
                "--claim", "dead code confirmed by reasoning", "--verdict", "CONFIRMED",
            )
        self.assertNotEqual(ctx.exception.code, 0)
        # Nothing was written: the ledger file does not exist / has no rows.
        path = self.root / ".forge" / "truth-ledger.jsonl"
        self.assertFalse(path.exists() and path.read_text(encoding="utf-8").strip())

    def test_attested_judgement_records_and_renders_provenance(self) -> None:
        code, out = _run(
            "ledger", "append", "--project", str(self.root),
            "--claim", "mutation block unreachable (reasoning over source)",
            "--verdict", "ATTESTED", "--json",
        )
        self.assertEqual(code, 0)
        entry = json.loads(out)
        self.assertEqual(entry["verdict"], "ATTESTED")
        self.assertEqual(entry["derivation"], "asserted")

        code, out = _run("ledger", "verify", "--project", str(self.root), "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["tallies_current"]["ATTESTED"], 1)
        self.assertEqual(report["derivations_current"]["asserted"], 1)
        self.assertEqual(report["unbound_confirmed"], [])

        code, out = _run("ledger", "show", "--project", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("(asserted)", out)


if __name__ == "__main__":
    unittest.main()

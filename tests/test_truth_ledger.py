"""Isolated tests for the witness truth ledger (G1 project-truth).

Locks the honesty invariants: append-only, supersede-not-delete, hash-chained,
no verdict auto-upgrade, verdict-flip visibility, and tamper detection. Reproduces
the shape of the hand-kept observer ledger (a claim, a stale-ref near-miss later
superseded by the force-fetched truth, and the resulting verdict flip).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.truth_ledger import (
    VERDICTS,
    append_claim,
    current_view,
    read_ledger,
    supersede_claim,
    truth_ledger_path,
    verify_ledger,
)


class TruthLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_append_and_read_roundtrip(self) -> None:
        entry = append_claim(
            self.root,
            claim="PR#20 head e5dc360 descends from base 305fb7f",
            verdict="CONFIRMED",
            source="ACTIVE-WORK-REGISTER.md",
            ground_truth={"kind": "merge-base", "pointer": "305fb7f", "observed": "is-ancestor"},
            method="git merge-base --is-ancestor 305fb7f e5dc360",
        )
        rows = read_ledger(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "CONFIRMED")
        # lineage of a root entry is its own id
        self.assertEqual(entry["lineage"], entry["id"])
        self.assertEqual(rows[0]["previous_entry_hash"], "")
        self.assertTrue(rows[0]["entry_hash"])

    def test_chain_healthy_across_appends(self) -> None:
        for i in range(4):
            append_claim(self.root, claim=f"claim {i}", verdict="CONFIRMED")
        report = verify_ledger(self.root)
        self.assertEqual(report["status"], "HEALTHY")
        self.assertEqual(report["records"], 4)
        self.assertEqual(report["issues"], [])

    def test_supersede_preserves_prior_entry(self) -> None:
        first = append_claim(self.root, claim="reconciled head still shows .pyc", verdict="CONTRADICTED")
        second = supersede_claim(
            self.root, first["id"],
            claim="force-fetched truth: .pyc dropped", verdict="CONFIRMED",
        )
        rows = read_ledger(self.root)
        # supersede-not-delete: both rows remain, superseded one unchanged
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], first["id"])
        self.assertEqual(rows[0]["verdict"], "CONTRADICTED")
        self.assertEqual(second["supersedes"], first["id"])
        self.assertEqual(second["lineage"], first["id"])
        self.assertEqual(verify_ledger(self.root)["status"], "HEALTHY")

    def test_supersede_unknown_target_rejected(self) -> None:
        with self.assertRaises(ValueError):
            supersede_claim(self.root, "tl-does-not-exist", claim="x", verdict="CONFIRMED")

    def test_cannot_supersede_a_non_tip(self) -> None:
        first = append_claim(self.root, claim="v1", verdict="UNVERIFIABLE")
        supersede_claim(self.root, first["id"], claim="v2", verdict="CONFIRMED")
        # first is no longer the tip; superseding it again is a fork and must be rejected
        with self.assertRaises(ValueError):
            supersede_claim(self.root, first["id"], claim="v2-fork", verdict="CONTRADICTED")

    def test_invalid_verdict_rejected(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(self.root, claim="x", verdict="PASS")

    def test_empty_claim_rejected(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(self.root, claim="   ", verdict="CONFIRMED")

    def test_unverifiable_is_terminal_and_never_auto_upgraded(self) -> None:
        entry = append_claim(self.root, claim="CI green at head X", verdict="UNVERIFIABLE")
        # reading, verifying and folding must never change the recorded verdict
        self.assertEqual(read_ledger(self.root)[0]["verdict"], "UNVERIFIABLE")
        self.assertEqual(verify_ledger(self.root)["tallies_current"]["UNVERIFIABLE"], 1)
        view = current_view(self.root)
        self.assertEqual(view["lineages"][0]["current_verdict"], "UNVERIFIABLE")
        self.assertEqual(entry["verdict"], "UNVERIFIABLE")

    def test_verdict_flip_is_surfaced(self) -> None:
        first = append_claim(self.root, claim="stale read", verdict="CONTRADICTED")
        supersede_claim(self.root, first["id"], claim="corrected read", verdict="CONFIRMED")
        view = current_view(self.root)
        self.assertEqual(view["verdict_flip_count"], 1)
        lineage = view["lineages"][0]
        self.assertEqual(lineage["current_verdict"], "CONFIRMED")
        self.assertEqual(lineage["verdict_flips"][0]["from_verdict"], "CONTRADICTED")
        self.assertEqual(lineage["verdict_flips"][0]["to_verdict"], "CONFIRMED")

    def test_tamper_is_detected(self) -> None:
        append_claim(self.root, claim="honest", verdict="CONFIRMED")
        append_claim(self.root, claim="second", verdict="CONFIRMED")
        path = truth_ledger_path(self.root)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        # forge a verdict on the first row without recomputing its hash
        rows[0]["verdict"] = "CONTRADICTED"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        report = verify_ledger(self.root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("does not match" in issue["message"] for issue in report["issues"]))

    def test_contradicted_tip_is_reported(self) -> None:
        append_claim(self.root, claim="a real contradiction", verdict="CONTRADICTED")
        report = verify_ledger(self.root)
        self.assertEqual(len(report["contradicted_tips"]), 1)

    def test_verdicts_constant_shape(self) -> None:
        self.assertEqual(VERDICTS, {"CONFIRMED", "CONTRADICTED", "UNVERIFIABLE", "INCOMPLETE"})


if __name__ == "__main__":
    unittest.main()

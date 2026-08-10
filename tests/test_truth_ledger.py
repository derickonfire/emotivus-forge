"""Isolated tests for the witness truth ledger (G1 project-truth).

Locks the honesty invariants: append-only, supersede-not-delete, hash-chained,
no verdict auto-upgrade, verdict-flip visibility, and tamper detection. Reproduces
the shape of the hand-kept observer ledger (a claim, a stale-ref near-miss later
superseded by the force-fetched truth, and the resulting verdict flip).

Schema 2 adds the CONFIRMED/ATTESTED provenance split — "never upgrade NOT_RUN to
PASS" applied to the ledger itself: CONFIRMED is reserved for binder-derived verdicts
that carry a reproduce command and a ground-truth binding; an unbound human/model
judgement is ATTESTED and is never rendered as CONFIRMED.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.truth_ledger import (
    DERIVATIONS,
    VERDICTS,
    append_binder_verdict,
    append_claim,
    current_view,
    read_ledger,
    record_binder_result,
    supersede_claim,
    truth_ledger_path,
    verify_ledger,
)

# The canonical binder-backed provenance used across these tests.
_BINDER = dict(
    derivation="binder",
    reproduce="git merge-base --is-ancestor 305fb7f e5dc360",
    ground_truth={"kind": "merge-base", "pointer": "305fb7f", "observed": "is-ancestor"},
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
            method="ancestry check",
            **_BINDER,
        )
        rows = read_ledger(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "CONFIRMED")
        self.assertEqual(rows[0]["derivation"], "binder")
        self.assertEqual(rows[0]["reproduce"], _BINDER["reproduce"])
        # lineage of a root entry is its own id
        self.assertEqual(entry["lineage"], entry["id"])
        self.assertEqual(rows[0]["previous_entry_hash"], "")
        self.assertTrue(rows[0]["entry_hash"])

    def test_chain_healthy_across_appends(self) -> None:
        for i in range(4):
            append_claim(self.root, claim=f"claim {i}", verdict="CONFIRMED", **_BINDER)
        report = verify_ledger(self.root)
        self.assertEqual(report["status"], "HEALTHY")
        self.assertEqual(report["records"], 4)
        self.assertEqual(report["issues"], [])

    def test_supersede_preserves_prior_entry(self) -> None:
        first = append_claim(self.root, claim="reconciled head still shows .pyc", verdict="CONTRADICTED")
        second = supersede_claim(
            self.root, first["id"],
            claim="force-fetched truth: .pyc dropped", verdict="CONFIRMED",
            **_BINDER,
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
            supersede_claim(self.root, "tl-does-not-exist", claim="x", verdict="ATTESTED")

    def test_cannot_supersede_a_non_tip(self) -> None:
        first = append_claim(self.root, claim="v1", verdict="UNVERIFIABLE")
        supersede_claim(self.root, first["id"], claim="v2", verdict="CONFIRMED", **_BINDER)
        # first is no longer the tip; superseding it again is a fork and must be rejected
        with self.assertRaises(ValueError):
            supersede_claim(self.root, first["id"], claim="v2-fork", verdict="CONTRADICTED")

    def test_invalid_verdict_rejected(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(self.root, claim="x", verdict="PASS")

    def test_empty_claim_rejected(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(self.root, claim="   ", verdict="ATTESTED")

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
        supersede_claim(self.root, first["id"], claim="corrected read", verdict="CONFIRMED", **_BINDER)
        view = current_view(self.root)
        self.assertEqual(view["verdict_flip_count"], 1)
        lineage = view["lineages"][0]
        self.assertEqual(lineage["current_verdict"], "CONFIRMED")
        self.assertEqual(lineage["verdict_flips"][0]["from_verdict"], "CONTRADICTED")
        self.assertEqual(lineage["verdict_flips"][0]["to_verdict"], "CONFIRMED")

    def test_tamper_is_detected(self) -> None:
        append_claim(self.root, claim="honest", verdict="CONFIRMED", **_BINDER)
        append_claim(self.root, claim="second", verdict="CONFIRMED", **_BINDER)
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
        self.assertEqual(VERDICTS, {"CONFIRMED", "ATTESTED", "CONTRADICTED", "UNVERIFIABLE", "INCOMPLETE"})
        self.assertEqual(DERIVATIONS, {"binder", "asserted"})


class ConfirmedProvenanceTests(unittest.TestCase):
    """The CONFIRMED/ATTESTED split: the ledger refuses to record unbound verified truth.

    Field-driven (planning/FIELD-NOTE-linecheck-reviewer-on-adopting-forge.md): a peer
    session appended hand-asserted CONFIRMED entries and got a HEALTHY chain — a
    tamper-evident record of unverified claims. These tests lock the door it walked through.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_hand_asserted_confirmed_is_refused(self) -> None:
        # The exact field-note reproduction: `--verdict CONFIRMED` with no binder backing.
        with self.assertRaises(ValueError) as ctx:
            append_claim(self.root, claim="run.php mutation block is dead code", verdict="CONFIRMED")
        self.assertIn("ATTESTED", str(ctx.exception))
        self.assertEqual(read_ledger(self.root), [])  # nothing was recorded

    def test_confirmed_without_reproduce_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(
                self.root, claim="x", verdict="CONFIRMED",
                derivation="binder", reproduce="",
                ground_truth={"kind": "sha256", "pointer": "f", "observed": "abc"},
            )

    def test_confirmed_without_ground_truth_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(
                self.root, claim="x", verdict="CONFIRMED",
                derivation="binder", reproduce="sha256sum f",
            )

    def test_attested_records_unbound_judgement(self) -> None:
        entry = append_claim(self.root, claim="mutation block unreachable (reasoning over source)", verdict="ATTESTED")
        self.assertEqual(entry["verdict"], "ATTESTED")
        self.assertEqual(entry["derivation"], "asserted")
        report = verify_ledger(self.root)
        self.assertEqual(report["status"], "HEALTHY")
        self.assertEqual(report["tallies_current"]["ATTESTED"], 1)
        self.assertEqual(report["tallies_current"]["CONFIRMED"], 0)

    def test_attested_cannot_masquerade_as_binder_derived(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(
                self.root, claim="x", verdict="ATTESTED",
                derivation="binder", reproduce="cmd",
                ground_truth={"kind": "sha256", "pointer": "f", "observed": "abc"},
            )

    def test_binder_derivation_requires_backing_even_for_negative_verdicts(self) -> None:
        # Claiming "a binder derived this" without the evidence is itself a lie.
        with self.assertRaises(ValueError):
            append_claim(self.root, claim="x", verdict="CONTRADICTED", derivation="binder")

    def test_unknown_derivation_rejected(self) -> None:
        with self.assertRaises(ValueError):
            append_claim(self.root, claim="x", verdict="ATTESTED", derivation="vibes")

    def test_attested_upgrade_to_confirmed_requires_binder_backing(self) -> None:
        first = append_claim(self.root, claim="believed green", verdict="ATTESTED")
        # An upgrade attempt without a binder re-derivation is refused...
        with self.assertRaises(ValueError):
            supersede_claim(self.root, first["id"], claim="now checked", verdict="CONFIRMED")
        # ...and succeeds only with the binder evidence attached (visible as a flip).
        upgraded = supersede_claim(
            self.root, first["id"], claim="now checked", verdict="CONFIRMED", **_BINDER,
        )
        self.assertEqual(upgraded["verdict"], "CONFIRMED")
        view = current_view(self.root)
        self.assertEqual(view["verdict_flip_count"], 1)
        self.assertEqual(view["lineages"][0]["current_derivation"], "binder")

    def test_smuggled_unbound_confirmed_is_flagged_at_verify(self) -> None:
        # Bypass the constructor entirely: hand-write a rehashed, chain-consistent
        # unbound CONFIRMED (what a legacy schema-1 file or a determined tamperer
        # would produce). The chain math is fine; provenance enforcement must still
        # refuse to render it as verified truth.
        import hashlib

        entry = {
            "schema": 1,
            "id": "tl-legacy-0001",
            "utc": "2026-08-09T00:00:00Z",
            "subject": "project",
            "claim": {"text": "hand-typed verified claim", "source": "", "source_ref": ""},
            "ground_truth": {"kind": "none"},
            "verdict": "CONFIRMED",
            "method": "",
            "observer": "hand",
            "note": "",
            "supersedes": "",
            "lineage": "tl-legacy-0001",
            "previous_entry_hash": "",
        }
        raw = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        entry["entry_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        path = truth_ledger_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        report = verify_ledger(self.root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["unbound_confirmed"], ["tl-legacy-0001"])
        self.assertTrue(any("not binder-backed" in issue["message"] for issue in report["issues"]))

    def test_provenance_tallies_are_reported(self) -> None:
        append_claim(self.root, claim="bound", verdict="CONFIRMED", **_BINDER)
        append_claim(self.root, claim="judged", verdict="ATTESTED")
        report = verify_ledger(self.root)
        self.assertEqual(report["derivations_current"], {"asserted": 1, "binder": 1})
        view = current_view(self.root)
        derivations = {l["current_derivation"] for l in view["lineages"]}
        self.assertEqual(derivations, {"binder", "asserted"})


class BinderEmissionTests(unittest.TestCase):
    """Binder results feed the ledger as genuinely binder-derived entries."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_append_binder_verdict_is_binder_backed(self) -> None:
        entry = append_binder_verdict(
            self.root,
            claim="release-truth CONFIRMED at head abc123",
            verdict="CONFIRMED",
            reproduce="forge bind release-truth --repo . --head abc123 --config bind.json",
            ground_truth={"kind": "binder", "pointer": "abc123", "observed": "CONFIRMED"},
        )
        self.assertEqual(entry["derivation"], "binder")
        self.assertEqual(entry["observer"], "forge-binder")
        self.assertEqual(verify_ledger(self.root)["status"], "HEALTHY")

    def test_record_binder_result_confirmed(self) -> None:
        result = {
            "verdict": "CONFIRMED",
            "target": "release-truth",
            "head": "abc123",
            "findings": [
                {"check": "true-accepted-schema", "state": "CONFIRMED", "detail": "ok",
                 "reproduce": "git show abc123:state.json | jq .schema"},
            ],
            "truth_boundary": "binder boundary",
        }
        entry = record_binder_result(self.root, result)
        self.assertEqual(entry["verdict"], "CONFIRMED")
        self.assertEqual(entry["derivation"], "binder")
        self.assertIn("git show abc123", entry["reproduce"])
        self.assertEqual(entry["ground_truth"]["pointer"], "abc123")

    def test_record_binder_result_not_run_maps_to_unverifiable(self) -> None:
        # NOT_RUN never becomes a positive verdict — the founding invariant.
        result = {"verdict": "NOT_RUN", "target": "gate-diff", "head": "", "findings": []}
        entry = record_binder_result(self.root, result)
        self.assertEqual(entry["verdict"], "UNVERIFIABLE")

    def test_record_binder_result_gaps_maps_to_contradicted(self) -> None:
        result = {
            "verdict": "GAPS",
            "target": "gate-coverage",
            "head": "abc123",
            "findings": [{"check": "wiring", "state": "GAPS", "detail": "unwired", "reproduce": "forge bind gate-coverage ..."}],
        }
        entry = record_binder_result(self.root, result)
        self.assertEqual(entry["verdict"], "CONTRADICTED")

    def test_record_binder_result_confirmed_without_reproduce_is_refused(self) -> None:
        # A "binder" result that cannot say how it checked has not earned CONFIRMED.
        result = {"verdict": "CONFIRMED", "target": "release-truth", "head": "abc123", "findings": []}
        with self.assertRaises(ValueError):
            record_binder_result(self.root, result)


if __name__ == "__main__":
    unittest.main()

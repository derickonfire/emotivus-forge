from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.lifecycle import (
    lifecycle_transition_summary,
    record_lifecycle_transition,
)
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class LifecycleTransitionTests(ForgeTestCase):
    def _write(self, root: Path, **overrides: object) -> str:
        payload = {
            "schema": 1,
            "component": "legacy-secret-scanner",
            "disposition": "replace",
            "authority": "owner",
            "reason": "Superseded by the ranked ecosystem resolver.",
            "successor": "ecosystem-resolver",
            "preserved_invariants": ["exact identity", "secret BLOCK coverage"],
        }
        payload.update(overrides)
        (root / "lifecycle-transition.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return "lifecycle-transition.json"

    def test_replace_transition_is_recorded_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            result = record_lifecycle_transition(root, FORGE_ROOT, self._write(root))
            self.assertEqual(result["disposition"], "replace")
            self.assertTrue(result["event_id"])
            summary = lifecycle_transition_summary(root)
            self.assertEqual(summary["transition_count"], 1)
            self.assertEqual(summary["by_disposition"].get("replace"), 1)
            self.assertEqual(summary["components"]["legacy-secret-scanner"]["successor"], "ecosystem-resolver")

    def test_retain_transition_needs_no_successor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_lifecycle_transition(root, FORGE_ROOT, self._write(root, disposition="retain", successor="", preserved_invariants=[]))
            self.assertEqual(lifecycle_transition_summary(root)["by_disposition"].get("retain"), 1)

    def test_replace_requires_successor_and_preserved_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            with self.assertRaisesRegex(ValueError, "successor"):
                record_lifecycle_transition(root, FORGE_ROOT, self._write(root, successor=""))
            with self.assertRaisesRegex(ValueError, "invariants"):
                record_lifecycle_transition(root, FORGE_ROOT, self._write(root, preserved_invariants=[]))

    def test_invalid_disposition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            with self.assertRaisesRegex(ValueError, "disposition"):
                record_lifecycle_transition(root, FORGE_ROOT, self._write(root, disposition="delete"))

    def test_transition_binding_labels_instance_bound_vs_imported(self) -> None:
        # GM-2 (G3 field test): lifecycle transitions are authority-declared, so like
        # authority and provenance they are instance-bound. A legit local transition is
        # instance-bound; a forged/imported unsigned event (self-consistent chain) is
        # labeled self-consistent, never counted as an authentic in-instance record.
        import json as _json
        from emotivus_forge.core.ledger import _canonical_hash
        from emotivus_forge.core.paths import ForgePaths
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_lifecycle_transition(root, FORGE_ROOT, self._write(root))
            summary = lifecycle_transition_summary(root)
            self.assertEqual(summary["instance_bound_count"], 1)
            self.assertEqual(summary["self_consistent_count"], 0)
            self.assertEqual(summary["components"]["legacy-secret-scanner"]["binding"], "instance-bound")

            # Forge an unsigned imported transition with a self-consistent chain.
            ledger = ForgePaths(root).ledger
            rows = [_json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
            event = {
                "schema": 2, "id": "forged-lifecycle", "utc": "2020-01-01T00:00:00+00:00",
                "kind": "component-lifecycle-transition", "source": "owner",
                "previous_event_hash": _canonical_hash(rows[-1]),
                "payload": {"component": "imported-widget", "disposition": "retire", "authority": "owner", "reason": "imported"},
            }
            event["event_hash"] = _canonical_hash(event)
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write(_json.dumps(event) + "\n")

            after = lifecycle_transition_summary(root)
            self.assertEqual(after["self_consistent_count"], 1)
            self.assertEqual(after["components"]["imported-widget"]["binding"], "self-consistent")

    def test_replace_invariants_are_verified_against_scoped_check_truth(self) -> None:
        # P4-05: a replace can declare structured invariant_checks (subject + required
        # truth-state). Forge verifies them against the current scoped-Check truth
        # records and reports preserved vs violated — free-text invariants stay recorded
        # but unverified.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._write(
                root,
                invariant_checks=[
                    {"subject": "observed-change-reconciliation", "required_truth_state": "OBSERVED"},
                    {"subject": "authority-baseline", "required_truth_state": "CONFIRMED"},
                ],
            )
            record_lifecycle_transition(root, FORGE_ROOT, "lifecycle-transition.json")
            payload = run_scoped_check(root, FORGE_ROOT)
            invariants = payload["lifecycle_invariants"]
            self.assertEqual(invariants["status"], "VIOLATED")
            component = invariants["components"]["legacy-secret-scanner"]
            self.assertIn("observed-change-reconciliation", [p["subject"] for p in component["preserved"]])
            self.assertIn("authority-baseline", [v["subject"] for v in component["violated"]])
            self.assertIn("exact identity", component["unverified_freetext"])
            self.assertTrue(any(f.get("check") == "core.lifecycle-invariant" for f in payload["findings"]))

    def test_resume_surfaces_lifecycle_transitions_only_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self.assertNotIn("Component lifecycle:", build_resume(root, FORGE_ROOT, budget="compact")["markdown"])
            record_lifecycle_transition(root, FORGE_ROOT, self._write(root))
            self.assertIn("Component lifecycle:", build_resume(root, FORGE_ROOT, budget="compact")["markdown"])

from __future__ import annotations

import tempfile
from pathlib import Path

from emotivus_forge.core.native_tools import approve_canonical_native_tool, load_or_discover_native_tools
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.self_currency import assess_self_currency
from emotivus_forge.core.truth import TruthRecord, normalize_truth_state, summarize_truth_records
from emotivus_forge.services.native_gate import parse_native_evidence
from emotivus_forge.services.scoped_check import run_scoped_check

from tests.support import FORGE_ROOT, ForgeTestCase


class TruthAndCurrencyTests(ForgeTestCase):
    def test_truth_state_vocabulary_is_normalized_and_bounded(self) -> None:
        self.assertEqual(normalize_truth_state("blocked-attempted"), "BLOCKED_ATTEMPTED")
        self.assertEqual(normalize_truth_state("anything-else"), "UNKNOWN")
        summary = summarize_truth_records([
            TruthRecord("a", "OBSERVED", result="PASS", verification_tier="static", attempted=True),
            TruthRecord("b", "NOT_RUN", result="NOT_RUN", verification_tier="production", attempted=False),
        ])
        self.assertEqual(summary["state_counts"], {"NOT_RUN": 1, "OBSERVED": 1})
        self.assertEqual(summary["highest_observed_tier"], "static")
        self.assertEqual(summary["unresolved_count"], 1)

    def test_structured_native_evidence_preserves_verification_tier(self) -> None:
        parsed = parse_native_evidence(
            'FORGE_EVIDENCE {"id":"browser-home","status":"PASS","type":"browser","tier":"headless","surfaces":["website"]}\n',
            "",
        )
        self.assertEqual(parsed["entries"][0]["truth_state"], "OBSERVED")
        self.assertEqual(parsed["entries"][0]["verification_tier"], "headless")
        self.assertEqual(parsed["truth_summary"]["highest_observed_tier"], "headless")

    def test_unrequested_native_gate_remains_not_run_not_explained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "tools").mkdir()
            gate = root / "tools" / "run_all_checks.sh"
            gate.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            approve_canonical_native_tool(root, self._native_invocation_contract(root, expected_count=1).name)
            result = run_scoped_check(root, FORGE_ROOT, run_native=False)
            self.assertEqual(result["native_gate"]["truth"]["truth_state"], "NOT_RUN")
            self.assertFalse(result["native_gate"]["truth"]["attempted"])
            self.assertEqual(result["truth_summary"]["state_counts"]["NOT_RUN"], 2)  # gate + no prior native evidence

    def test_unapproved_native_gate_is_blocked_without_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "tools").mkdir()
            gate = root / "tools" / "run_all_checks.sh"
            gate.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            result = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(result["native_gate"]["status"], "BLOCKED")
            self.assertEqual(result["native_gate"]["truth"]["truth_state"], "BLOCKED_UNATTEMPTED")
            self.assertFalse(result["native_gate"]["truth"]["attempted"])

    def test_self_currency_warns_when_objective_source_disappears(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            passport = build_passport(root, FORGE_ROOT)
            (root / "BACKLOG.md").unlink()
            authorities = {
                "objective": {"text": "Add a login screen.", "source": "BACKLOG.md"},
            }
            native = load_or_discover_native_tools(root, refresh=True)
            currency = assess_self_currency(root, passport, authorities, native)
            self.assertEqual(currency["status"], "WARN")
            objective = next(row for row in currency["records"] if row["subject"] == "continuity.objective")
            self.assertEqual(objective["truth_state"], "STALE")
            self.assertTrue(currency["attention"])
            resumed = build_resume(root, FORGE_ROOT)
            resumed_objective = next(row for row in resumed["self_currency"]["records"] if row["subject"] == "continuity.objective")
            self.assertEqual(resumed_objective["truth_state"], "STALE")

    def test_absent_native_gate_is_visible_but_not_noisy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            passport = build_passport(root, FORGE_ROOT)
            currency = passport["self_currency"]
            self.assertEqual(currency["status"], "PASS")
            native = next(row for row in currency["records"] if row["subject"] == "native-gate.source")
            self.assertEqual(native["truth_state"], "UNKNOWN")
            self.assertNotIn(native["reason"], currency["attention"])

    def test_resume_reports_compact_self_currency_without_dumping_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            payload = build_resume(root, FORGE_ROOT)
            self.assertIn("Forge self-currency:", payload["markdown"])
            self.assertIn("self_currency", payload)
            self.assertNotIn("native-gate.approval", payload["markdown"])

    def test_scoped_check_labels_static_observations_and_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            (root / "index.php").write_text("<?php echo 'changed';\n", encoding="utf-8")
            result = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertIn("OBSERVED", result["truth_summary"]["state_counts"])
            self.assertIn("NOT_RUN", result["truth_summary"]["state_counts"])
            self.assertEqual(result["truth_summary"]["highest_observed_tier"], "static")
            self.assertFalse(result["claim_scope"]["project_level_success"])
            self.assertIn("one blocker never explains another result", result["claim_scope"]["truth_boundary"])

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.authority_baseline import (
    assess_authority_baseline,
    authorize_current_baseline,
)
from emotivus_forge.core.changes import detect_changes
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.state import load_settings, load_state
from emotivus_forge.services.scoped_check import render_check, run_scoped_check
from emotivus_forge.services.ship import ship_project
from emotivus_forge.core.state import CORE_STATE_SCHEMA
from tests.support import FORGE_ROOT, ForgeTestCase


class AuthorityBaselineTests(ForgeTestCase):
    def test_adopt_refresh_does_not_erase_intervening_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            before = load_state(root)["snapshot"]
            (root / "index.php").write_text("<?php echo 'foreign edit';\n", encoding="utf-8")

            refreshed = build_passport(root, FORGE_ROOT)
            state = load_state(root)
            changes = detect_changes(root, FORGE_ROOT, state["snapshot"], load_settings(root))

            self.assertEqual(state["snapshot"], before)
            self.assertEqual(changes["paths"], ["index.php"])
            self.assertEqual(refreshed["authority_baseline"]["status"], "NOT_ESTABLISHED")
            ledger = (root / ".forge" / "ledger.jsonl").read_text(encoding="utf-8")
            self.assertIn('"observed_checkpoint_preserved":true', ledger)

    def test_plain_checkpoint_is_not_run_without_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            payload = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["authority_baseline"]["status"], "NOT_ESTABLISHED")
            state = load_state(root)
            self.assertFalse(state["last_check"]["checkpointed"])
            self.assertFalse(state["last_check"]["authority_current"])
            levels = {item["level_id"]: item for item in ship_project(root, FORGE_ROOT)["claim_readiness"]["levels"]}
            self.assertEqual(levels["authority-recorded-candidate"]["status"], "FAIL")

    def test_authorization_is_exact_fingerprint_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            check = run_scoped_check(root, FORGE_ROOT)
            reviewed = check["authority_baseline"]["current_fingerprint"]
            (root / "index.php").write_text("<?php echo 'changed after review';\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "changed after the fingerprint was reviewed"):
                authorize_current_baseline(
                    root,
                    FORGE_ROOT,
                    expected_fingerprint=reviewed,
                    authority="owner",
                    reason="Reviewed the earlier tree.",
                )
            self.assertNotEqual(load_state(root).get("authority_baseline", {}).get("status"), "active")

    def test_authorization_quarantines_later_mutation_and_requires_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            check = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            authorization = authorize_current_baseline(
                root,
                FORGE_ROOT,
                expected_fingerprint=check["authority_baseline"]["current_fingerprint"],
                authority="owner",
                reason="Reviewed and accepted the exact neutral fixture tree.",
            )
            self.assertTrue(authorization["checkpoint_revalidation_required"])
            self.assertFalse(load_state(root)["last_check"]["checkpointed"])

            rechecked = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            self.assertEqual(rechecked["authority_baseline"]["status"], "CURRENT")
            self.assertTrue(load_state(root)["last_check"]["authority_current"])

            (root / "README.md").write_text("# Changed without authority\n", encoding="utf-8")
            changed = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            self.assertEqual(changed["status"], "PASS")
            self.assertEqual(changed["authority_baseline"]["status"], "QUARANTINED")
            self.assertEqual(changed["authority_baseline"]["pending_paths"], ["README.md"])
            self.assertFalse(load_state(root)["last_check"]["authority_current"])
            repeated = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(repeated["changes"]["count"], 0)
            self.assertEqual(repeated["authority_baseline"]["status"], "QUARANTINED")
            self.assertEqual(repeated["authority_baseline"]["pending_paths"], ["README.md"])

    def test_check_human_output_exposes_exact_review_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            payload = run_scoped_check(root, FORGE_ROOT)
            fingerprint = payload["authority_baseline"]["current_fingerprint"]
            rendered = render_check(payload)
            self.assertEqual(len(fingerprint), 64)
            self.assertIn(f"Review fingerprint: {fingerprint}", rendered)

    def test_cli_records_baseline_in_separate_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            check = run_scoped_check(root, FORGE_ROOT)
            fingerprint = check["authority_baseline"]["current_fingerprint"]
            command = [
                sys.executable,
                str(FORGE_ROOT / "forge.py"),
                "adopt",
                str(root),
                "--authorize-baseline",
                fingerprint,
                "--baseline-reason",
                "Reviewed exact tree and accepted the current project state.",
                "--json",
            ]
            result = subprocess.run(command, cwd=FORGE_ROOT, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["baseline_authorization"]["status"], "AUTHORIZED")
            self.assertEqual(payload["baseline_authorization"]["snapshot_fingerprint"], fingerprint)
            state = load_state(root)
            self.assertEqual(state["authority_baseline"]["status"], "active")
            self.assertEqual(state["authority_baseline"]["snapshot_fingerprint"], fingerprint)
            self.assertFalse(state["last_check"].get("checkpointed", False))

    def test_contradicted_authority_record_blocks_check_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            check = run_scoped_check(root, FORGE_ROOT)
            authorize_current_baseline(
                root,
                FORGE_ROOT,
                expected_fingerprint=check["authority_baseline"]["current_fingerprint"],
                authority="owner",
                reason="Reviewed exact tree.",
            )
            state_path = root / ".forge" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["authority_baseline"]["snapshot_fingerprint"] = "0" * 64
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

            payload = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["authority_baseline"]["status"], "CONTRADICTED")
            self.assertIn("core.authority-baseline-integrity", payload["executed_checks"])
            self.assertFalse(payload["checkpointed"])

    def test_bounded_authority_snapshot_cannot_support_ship_authority_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            settings_path = root / ".forge" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["hash_total_budget_bytes"] = 1
            settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
            check = run_scoped_check(root, FORGE_ROOT)
            authorization = authorize_current_baseline(
                root,
                FORGE_ROOT,
                expected_fingerprint=check["authority_baseline"]["current_fingerprint"],
                authority="owner",
                reason="Accepted only within the configured bounded scan.",
            )
            self.assertEqual(authorization["strength"]["status"], "bounded")
            assessment = assess_authority_baseline(load_state(root), load_state(root)["snapshot"], project_root=root)
            self.assertFalse(assessment["release_eligible"])
            # M-G1-2: a bounded (un-hashed) comparison must report bounded change
            # confidence, never a bare proven "0 changed".
            self.assertEqual(assessment.get("change_confidence"), "bounded")
            self.assertTrue(assessment.get("unverified_paths"))
            from emotivus_forge.core.changes import change_count_phrase, compare_snapshots
            same_unhashed = {"files": {"big.bin": {"size": 9, "mtime_ns": 1, "sha256": ""}}}
            cmp = compare_snapshots(same_unhashed, same_unhashed)
            self.assertEqual(cmp["count"], 0)
            self.assertEqual(cmp["unverified"], ["big.bin"])
            self.assertIn("bounded", change_count_phrase(cmp))
            # M-G1-1: the legitimately authorized baseline is corroborated by a
            # chain-verified authorization event; an imported one with no matching
            # ledger event is demoted to UNCORROBORATED and is not release-eligible.
            self.assertIs(assessment.get("corroboration", {}).get("corroborated"), True)
            # 0.560 (DG-1..DG-5): corroboration is honest that the chain is unkeyed —
            # it proves self-consistency, not cryptographic in-instance authorship.
            self.assertEqual(assessment["corroboration"].get("binding"), "unkeyed-self-consistent")
            self.assertIn("unkeyed", assessment["corroboration"].get("reason", ""))
            self.assertNotIn("in this instance's ledger", assessment["corroboration"].get("reason", ""))
            from emotivus_forge.core.authority_baseline import TRUTH_BOUNDARY
            self.assertIn("unkeyed", TRUTH_BOUNDARY)
            fabricated = load_state(root)
            fabricated["authority_baseline"] = {**fabricated["authority_baseline"], "baseline_id": "f" * 20}
            imported = assess_authority_baseline(fabricated, fabricated["snapshot"], project_root=root)
            self.assertEqual(imported["status"], "UNCORROBORATED")
            self.assertFalse(imported["release_eligible"])

    def test_cli_requires_baseline_authorization_as_separate_adopt_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            check = run_scoped_check(root, FORGE_ROOT)
            command = [
                sys.executable,
                str(FORGE_ROOT / "forge.py"),
                "adopt",
                str(root),
                "--authorize-baseline",
                check["authority_baseline"]["current_fingerprint"],
                "--baseline-reason",
                "Reviewed exact tree.",
                "--confirm-objective",
                "Do unrelated work.",
                "--json",
            ]
            result = subprocess.run(command, cwd=FORGE_ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be a separate Adopt operation", result.stderr)
            self.assertNotEqual(load_state(root).get("authority_baseline", {}).get("status"), "active")

    def test_schema_two_migration_preserves_observed_snapshot_without_inferred_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            state_path = root / ".forge" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            original_snapshot = state["snapshot"]
            state["schema"] = 2
            state.pop("authority_baseline", None)
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

            migrated = load_state(root)
            self.assertEqual(migrated["schema"], CORE_STATE_SCHEMA)
            self.assertEqual(migrated["snapshot"], original_snapshot)
            self.assertEqual(migrated["authority_baseline"]["status"], "not-established")
            self.assertIn("require explicit", migrated["authority_baseline"]["migration_reason"])


if __name__ == "__main__":
    unittest.main()

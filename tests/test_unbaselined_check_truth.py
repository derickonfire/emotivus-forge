from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from emotivus_forge.core.authority_baseline import authorize_current_baseline
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.state import load_state
from emotivus_forge.services.scoped_check import render_check, run_scoped_check
from emotivus_forge.services.ship import ship_project
from tests.support import FORGE_ROOT, ForgeTestCase


class UnbaselinedCheckTruthTests(ForgeTestCase):
    def test_unbaselined_unchanged_tree_is_not_run_and_cannot_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)

            result = run_scoped_check(root, FORGE_ROOT, checkpoint=True)

            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["claim"], "Scoped Check NOT_RUN")
            self.assertEqual(result["aggregate_eligibility"]["status"], "NOT_ELIGIBLE")
            self.assertIn("--authorize-baseline", result["aggregate_eligibility"]["resolving_command"])
            self.assertFalse(result["checkpointed"])
            self.assertFalse(load_state(root)["last_check"]["checkpointed"])
            self.assertEqual(load_state(root)["last_check"]["status"], "NOT_RUN")

            levels = {
                item["level_id"]: item
                for item in ship_project(root, FORGE_ROOT)["claim_readiness"]["levels"]
            }
            requirements = {
                item["requirement_id"]: item
                for item in levels["checkpointed-candidate"]["requirements"]
            }
            self.assertEqual(requirements["last-check-pass"]["status"], "NOT_RUN")
            self.assertEqual(requirements["checkpointed"]["status"], "NOT_RUN")

    def test_unbaselined_clean_change_preserves_observations_without_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            (root / "index.php").write_text("<?php echo 'clean changed';\n", encoding="utf-8")

            result = run_scoped_check(root, FORGE_ROOT)

            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["changes"]["paths"], ["index.php"])
            self.assertIn("index.php", result["checked_paths"])
            self.assertFalse(any(item["severity"] == "blocker" for item in result["findings"]))
            self.assertIn("No explicit project-authority baseline", result["reason"])

    def test_unbaselined_defect_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            (root / "index.php").write_text(
                "<<<<<<< HEAD\nleft\n=======\nright\n>>>>>>> branch\n",
                encoding="utf-8",
            )

            result = run_scoped_check(root, FORGE_ROOT)

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["claim"], "Scoped Check FAIL")
            self.assertTrue(any(item["check"] == "core.merge-marker" for item in result["findings"]))

    def test_explicit_authority_baseline_restores_eligible_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            first = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(first["status"], "NOT_RUN")

            authorize_current_baseline(
                root,
                FORGE_ROOT,
                expected_fingerprint=first["authority_baseline"]["current_fingerprint"],
                authority="owner",
                reason="Reviewed and accepted the exact neutral fixture tree.",
            )
            result = run_scoped_check(root, FORGE_ROOT, checkpoint=True)

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["claim"], "Scoped Check PASS")
            self.assertEqual(result["aggregate_eligibility"]["status"], "ELIGIBLE")
            self.assertTrue(result["checkpointed"])

    def test_human_and_cli_surfaces_report_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            result = run_scoped_check(root, FORGE_ROOT)
            rendered = render_check(result)
            self.assertIn("FORGE Scoped Check NOT_RUN", rendered)
            self.assertIn("Aggregate eligibility: NOT_ELIGIBLE", rendered)
            self.assertIn("Resolve with: forge adopt", rendered)
            self.assertIn("No project-level or release-level PASS was produced.", rendered)

            process = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "check", str(root), "--json"],
                cwd=FORGE_ROOT,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(process.returncode, 1)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["aggregate_eligibility"]["status"], "NOT_ELIGIBLE")

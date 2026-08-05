from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

from emotivus_forge.core.artifact_collision import observe_version_collisions
from emotivus_forge.core.authority_baseline import authorize_current_baseline
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.state import load_state
from emotivus_forge.core.workspace_integrity import (
    assess_workspace_integrity,
    fingerprint_selection,
    fingerprint_workspace,
    require_selection_unchanged,
)
from emotivus_forge.services.scoped_check import run_scoped_check
from emotivus_forge.services.ship import ship_project
from tests.support import FORGE_ROOT, ForgeTestCase


class WorkspaceIntegrityTests(ForgeTestCase):
    def _zip(self, path: Path, version: str, payload: str = "ok") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Project/FORGE-MANIFEST.json", json.dumps({"version": version}))
            archive.writestr("Project/payload.txt", payload)
        return path

    def test_workspace_fingerprint_is_content_addressed_not_mtime_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            first = fingerprint_workspace(root)
            os.utime(root / "index.php", (1_000_000_000, 1_000_000_000))
            second = fingerprint_workspace(root)
            self.assertEqual(first["fingerprint"], second["fingerprint"])
            (root / "index.php").write_text("<?php echo 'changed';\n", encoding="utf-8")
            third = fingerprint_workspace(root)
            self.assertNotEqual(second["fingerprint"], third["fingerprint"])

    def test_forge_state_is_excluded_from_workspace_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            first = fingerprint_workspace(root)
            (root / ".forge" / "resume.md").write_text("changed state only\n", encoding="utf-8")
            second = fingerprint_workspace(root)
            self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_passing_checkpoint_records_exact_seal_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            observed = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(observed["status"], "NOT_RUN")
            authorize_current_baseline(
                root,
                FORGE_ROOT,
                expected_fingerprint=observed["authority_baseline"]["current_fingerprint"],
                authority="owner",
                reason="Reviewed the exact workspace before recording a seal candidate.",
            )
            result = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["workspace_integrity"]["status"], "CURRENT")
            self.assertEqual(assess_workspace_integrity(root)["status"], "CURRENT")
            state = load_state(root)
            self.assertEqual(state["schema"], 5)
            self.assertTrue(state["workspace_integrity"]["seal_candidate"]["fingerprint"])

    def test_post_checkpoint_content_drift_blocks_ship(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            observed = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(observed["status"], "NOT_RUN")
            authorize_current_baseline(
                root,
                FORGE_ROOT,
                expected_fingerprint=observed["authority_baseline"]["current_fingerprint"],
                authority="owner",
                reason="Reviewed the exact workspace before the drift scenario.",
            )
            checked = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            self.assertEqual(checked["status"], "PASS")
            (root / "index.php").write_text("<?php echo 'rival writer';\n", encoding="utf-8")
            result = ship_project(root, FORGE_ROOT)
            self.assertEqual(result["workspace_integrity"]["status"], "DRIFTED")
            self.assertFalse(result["release_ready"])
            self.assertIn("workspace seal candidate", " ".join(result["required_before_activation"]))

    def test_selection_guard_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            files = [root / "index.php", root / "BACKLOG.md"]
            before = fingerprint_selection(root, files)
            require_selection_unchanged(root, files, before)
            (root / "index.php").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "drifted during the build"):
                require_selection_unchanged(root, files, before)

    def test_same_basename_and_version_with_different_bytes_is_a_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._zip(root / "a" / "RUN-FORGE-1.2.3.zip", "1.2.3", "first")
            self._zip(root / "b" / "RUN-FORGE-1.2.3.zip", "1.2.3", "second")
            result = observe_version_collisions(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["collisions"][0]["distinct_sha256_count"], 2)

    def test_same_version_different_artifact_names_do_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._zip(root / "RUN-FORGE-1.2.3.zip", "1.2.3", "public")
            self._zip(root / "Emotivus-Forge-1.2.3-Development.zip", "1.2.3", "development")
            self.assertEqual(observe_version_collisions(root)["status"], "PASS")

    def test_filename_and_manifest_version_disagreement_fails_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._zip(root / "RUN-FORGE-1.2.3.zip", "1.2.4", "mismatch")
            result = observe_version_collisions(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("differs", result["problems"][0]["problem"])

    def test_artifact_observer_respects_project_forgeignore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".forgeignore").write_text("reference/**\n", encoding="utf-8")
            self._zip(root / "reference" / "a" / "RUN-FORGE-1.2.3.zip", "1.2.3", "first")
            self._zip(root / "reference" / "b" / "RUN-FORGE-1.2.3.zip", "1.2.3", "second")
            result = observe_version_collisions(root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["artifacts_scanned"], 0)
            self.assertEqual(result["project_ignore_patterns"], ["reference/**"])

from __future__ import annotations

import tempfile
from pathlib import Path

from emotivus_forge.core.authority_registry import discover_authorities
from emotivus_forge.core.decision_forks import analyze_decision_forks
from emotivus_forge.core.orientation import build_snapshot
from tests.support import FORGE_ROOT, ForgeTestCase


class OrientationSafetyTests(ForgeTestCase):
    def test_project_forgeignore_excludes_matching_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "generated").mkdir()
            (root / "generated" / "bundle.js").write_text("large generated output", encoding="utf-8")
            (root / "notes.tmp").write_text("temporary", encoding="utf-8")
            (root / ".forgeignore").write_text("generated/**\n*.tmp\n", encoding="utf-8")
            snapshot = build_snapshot(root, FORGE_ROOT)
            self.assertNotIn("generated/bundle.js", snapshot["files"])
            self.assertNotIn("notes.tmp", snapshot["files"])
            self.assertIn(".forgeignore", snapshot["files"])
            self.assertIn("BACKLOG.md", snapshot["files"])

    def test_project_ignore_excludes_example_authority_and_decision_fork(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Neutral source\n", encoding="utf-8")
            (root / ".forgeignore").write_text("examples/**\n", encoding="utf-8")
            (root / "examples").mkdir()
            (root / "examples" / "BACKLOG.example.md").write_text(
                "# Example\n\n## The next action\n\n- Add an immediate 15-minute deadline to a date-only field.\n",
                encoding="utf-8",
            )
            authorities = discover_authorities(root, FORGE_ROOT)
            self.assertNotEqual(authorities["objective"].get("source"), "examples/BACKLOG.example.md")
            self.assertFalse(any(item.get("path", "").startswith("examples/") for item in authorities["candidates"]))
            forks = analyze_decision_forks(root, FORGE_ROOT, authorities=authorities)
            self.assertEqual(forks["pending"], [])

    def test_symlinked_files_outside_project_are_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external_directory:
            root = Path(directory)
            external = Path(external_directory) / "outside-secret.txt"
            external.write_text("outside", encoding="utf-8")
            self._fixture(root)
            link = root / "linked-secret.txt"
            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable in this environment")
            snapshot = build_snapshot(root, FORGE_ROOT)
            self.assertNotIn("linked-secret.txt", snapshot["files"])

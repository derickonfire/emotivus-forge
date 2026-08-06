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
        # M-G1-3 / M-G1-5: a name scraped from a README heading is inferred, never
        # confirmed; a command line is never taken as a description; and `go run` is
        # only suggested for an observed main package, not a library.
        from emotivus_forge.core.orientation import derive_orientation, orient_project
        from emotivus_forge.core.state import ensure_settings, load_settings
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Scraped Title\n\nnpm install && npm run build\n", encoding="utf-8")
            (root / "go.mod").write_text("module example.com/lib\n", encoding="utf-8")
            (root / "lib.go").write_text("package lib\n", encoding="utf-8")
            brief = derive_orientation(root, {"README.md", "go.mod", "lib.go"})
            self.assertEqual(brief["description"], "")            # command not used as identity
            self.assertEqual(brief["run"], "go build ./...")      # library, not `go run`
            self.assertEqual(brief["commands_tier"], "inferred")
            ensure_settings(root)
            identity = orient_project(root, FORGE_ROOT, load_settings(root))["identity"]
            # A manifest-declared name is observed; a README/title scrape is inferred;
            # neither is ever "confirmed" — that is reserved for the owner-recorded path.
            self.assertEqual(identity["name_source"], "go.mod")
            self.assertEqual(identity["status"], "observed")
            self.assertNotEqual(identity["status"], "confirmed")

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

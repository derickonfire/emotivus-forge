from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from emotivus_forge.core.paths import ForgePaths, redirect_state, state_root
from tests.support import FORGE_ROOT, ForgeTestCase


def _tree_digest(root: Path) -> str:
    """Stable digest of every file under root (excluding .git), for tamper checks."""
    entries = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        entries.append(str(path.relative_to(root)))
        entries.append(hashlib.sha256(path.read_bytes()).hexdigest())
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


class ReadOnlyConsultTests(ForgeTestCase):
    def _forge(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(FORGE_ROOT / "forge.py"), *args],
            cwd=FORGE_ROOT, text=True, capture_output=True, timeout=60,
        )

    def _project(self, root: Path) -> None:
        (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
        (root / "README.md").write_text("# Demo\n", encoding="utf-8")

    def test_state_root_default_and_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Default: state_root is project/.forge and ForgePaths agrees.
            self.assertEqual(state_root(root), root / ".forge")
            self.assertEqual(ForgePaths(root).root, root / ".forge")
            alt = root / "elsewhere" / ".forge"
            with redirect_state(root, alt):
                self.assertEqual(state_root(root), alt)
                self.assertEqual(ForgePaths(root).state, alt / "state.json")
            # Redirect is fully unwound afterwards.
            self.assertEqual(state_root(root), root / ".forge")

    def test_read_only_run_writes_nothing_into_fresh_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            before = _tree_digest(root)
            result = self._forge("run", "--read-only", str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / ".forge").exists(), "read-only run created .forge in the project")
            self.assertEqual(_tree_digest(root), before, "read-only run modified the project tree")

    def test_read_only_run_preserves_existing_state_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            self.assertEqual(self._forge("adopt", str(root)).returncode, 0)
            self.assertTrue((root / ".forge").is_dir())
            before = _tree_digest(root)
            self.assertEqual(self._forge("run", "--read-only", str(root)).returncode, 0)
            self.assertEqual(self._forge("resume", "--read-only", str(root)).returncode, 0)
            self.assertEqual(_tree_digest(root), before, "read-only consultation mutated existing .forge state")

    def test_read_only_payload_is_labeled_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            result = self._forge("run", "--read-only", str(root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIs(payload.get("read_only"), True)
            self.assertIn("wrote nothing", payload.get("read_only_limitations", ""))

    def test_normal_run_still_persists_state(self) -> None:
        # Control: without --read-only, Forge persists .forge as before.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            self.assertEqual(self._forge("run", str(root)).returncode, 0)
            self.assertTrue((root / ".forge" / "state.json").is_file(), "normal run must still persist state")

    def test_read_only_resume_reads_real_continuity_state(self) -> None:
        # Read-only resume must reflect the project's real prior state, not a blank.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._project(root)
            self.assertEqual(self._forge("adopt", str(root)).returncode, 0)
            result = self._forge("resume", "--read-only", str(root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIs(payload.get("read_only"), True)
            self.assertIn("markdown", payload)

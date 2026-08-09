"""Isolated tests for gate-diff monotonicity (G1 project-truth).

Reproduces, in a self-contained temp git repository, the LineCheck gate-edit
situations: a schema-pin bump that only changes a literal (monotonic → CONFIRMED),
an assertion removed (→ CONTRADICTED), and a new SKIP path introduced
(→ CONTRADICTED). Unreachable refs → NOT_RUN.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.gate_diff_monotonicity import (
    report_gate_diff_monotonicity, CONFIRMED, CONTRADICTED, NOT_RUN,
)

CONFIG = {"gate_paths": ["tools/check_*.php"]}

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00 +0000",
}

_BASE_CHECK = """<?php
$ok(strpos($schema, "define('LC_SCHEMA_VERSION', 72)") !== false, 'schema is stamped');
$ok(str_contains($body, 'Done'), 'the card shows progress');
$ok(count($rows) === 3, 'three rows render');
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, env=_ENV)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


class GateDiffMonotonicityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q")
        _write(self.root, "tools/check_worklist.php", _BASE_CHECK)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "base gate")
        self.base = _git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _head(self, new_check: str) -> str:
        _write(self.root, "tools/check_worklist.php", new_check)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "edit gate")
        return _git(self.root, "rev-parse", "HEAD")

    def test_pin_bump_only_literal_is_monotonic(self) -> None:
        head = self._head(_BASE_CHECK.replace("LC_SCHEMA_VERSION', 72", "LC_SCHEMA_VERSION', 73"))
        result = report_gate_diff_monotonicity(str(self.root), self.base, head, CONFIG)
        self.assertEqual(result["verdict"], CONFIRMED, result)

    def test_removed_assertion_is_contradicted(self) -> None:
        # Drop the "three rows render" assertion.
        reduced = "\n".join(l for l in _BASE_CHECK.splitlines() if "three rows" not in l) + "\n"
        head = self._head(reduced)
        result = report_gate_diff_monotonicity(str(self.root), self.base, head, CONFIG)
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertTrue(any(f["check"] == "assertion-preservation" and f["state"] == CONTRADICTED
                            for f in result["findings"]))

    def test_new_skip_path_is_contradicted(self) -> None:
        with_skip = _BASE_CHECK + '$ok(true, "guard"); echo "SKIP — no db"; // markTestSkipped\n'
        head = self._head(with_skip)
        result = report_gate_diff_monotonicity(str(self.root), self.base, head, CONFIG)
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertTrue(any(f["check"] == "no-new-skip" and f["state"] == CONTRADICTED
                            for f in result["findings"]))

    def test_added_assertion_is_monotonic(self) -> None:
        stronger = _BASE_CHECK + '$ok($x > 0, "new invariant");\n'
        head = self._head(stronger)
        result = report_gate_diff_monotonicity(str(self.root), self.base, head, CONFIG)
        self.assertEqual(result["verdict"], CONFIRMED, result)

    def test_added_check_with_skip_guard_is_additive(self) -> None:
        # A brand-new check file that legitimately contains a "SKIP if no DB" guard is
        # additive coverage, not a weakening of the existing gate. (The real LC-004 case.)
        _write(self.root, "tools/check_new_behavior.php",
               '<?php\n$ok(true, "ran");\nif (!$db) { echo "SKIP — no database server"; return; }\n')
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "add new behavior check with skip guard")
        head = _git(self.root, "rev-parse", "HEAD")
        result = report_gate_diff_monotonicity(str(self.root), self.base, head, CONFIG)
        self.assertEqual(result["verdict"], CONFIRMED, result)

    def test_deleted_check_is_contradicted(self) -> None:
        (self.root / "tools" / "check_worklist.php").unlink()
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "delete a check")
        head = _git(self.root, "rev-parse", "HEAD")
        result = report_gate_diff_monotonicity(str(self.root), self.base, head, CONFIG)
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertTrue(any(f["check"] == "assertion-preservation" and f["state"] == CONTRADICTED
                            for f in result["findings"]))

    def test_no_gate_files_changed_is_confirmed(self) -> None:
        _write(self.root, "README.md", "unrelated\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "docs only")
        head = _git(self.root, "rev-parse", "HEAD")
        result = report_gate_diff_monotonicity(str(self.root), self.base, head, CONFIG)
        self.assertEqual(result["verdict"], CONFIRMED, result)
        self.assertTrue(any(f["check"] == "scope" for f in result["findings"]))

    def test_unreachable_ref_is_not_run(self) -> None:
        result = report_gate_diff_monotonicity(str(self.root), self.base, "deadbeef" * 5, CONFIG)
        self.assertEqual(result["verdict"], NOT_RUN, result)


if __name__ == "__main__":
    unittest.main()

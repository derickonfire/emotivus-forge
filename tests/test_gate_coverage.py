"""Isolated tests for the gate-coverage differ (G1 project-truth).

Reproduces, in a self-contained temp git repository, the LineCheck situation: a
check script exists in the tree but is not referenced by the CI gate. The differ
must report the gap (each unwired check NOT_RUN), COVERED when all are wired, and
NOT_RUN when the gate sweeps the inventory by glob (per-check coverage
indeterminate) or when it cannot assess.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.gate_coverage import (
    report_gate_coverage, COVERED, GAPS, NOT_RUN,
)

CONFIG = {
    "check_inventory": ["tools/check_*.php"],
    "gate_sources": [".github/workflows/gate.yml"],
}

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00 +0000",
}


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


class GateCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q")
        for name in ("check_a", "check_b", "check_c"):
            _write(self.root, f"tools/{name}.php", f"<?php /* {name} */\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _commit(self, gate_yaml: str) -> str:
        _write(self.root, ".github/workflows/gate.yml", gate_yaml)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "state")
        return _git(self.root, "rev-parse", "HEAD")

    def test_gap_when_a_check_is_not_wired(self) -> None:
        head = self._commit("steps:\n  - run: php tools/check_a.php\n  - run: php tools/check_b.php\n")
        result = report_gate_coverage(str(self.root), head, CONFIG)
        self.assertEqual(result["verdict"], GAPS, result)
        self.assertEqual(result["unwired_checks"], ["tools/check_c.php"])

    def test_covered_when_all_wired(self) -> None:
        head = self._commit(
            "steps:\n  - run: php tools/check_a.php\n  - run: php tools/check_b.php\n"
            "  - run: php tools/check_c.php\n")
        result = report_gate_coverage(str(self.root), head, CONFIG)
        self.assertEqual(result["verdict"], COVERED, result)
        self.assertEqual(result["unwired_checks"], [])

    def test_glob_sweep_is_indeterminate_not_run(self) -> None:
        # The gate loops over the inventory by pattern → per-check coverage is meaningless.
        head = self._commit("steps:\n  - run: for f in tools/check_*.php; do php \"$f\"; done\n")
        result = report_gate_coverage(str(self.root), head, CONFIG)
        self.assertEqual(result["verdict"], NOT_RUN, result)
        self.assertTrue(any(f["check"] == "invocation-style" for f in result["findings"]))

    def test_no_gate_sources_is_not_run(self) -> None:
        # Commit checks but a workflow that doesn't match the declared gate_sources glob.
        _write(self.root, "other.txt", "x\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "no gate")
        head = _git(self.root, "rev-parse", "HEAD")
        result = report_gate_coverage(str(self.root), head, CONFIG)
        self.assertEqual(result["verdict"], NOT_RUN, result)

    def test_unreachable_head_is_not_run(self) -> None:
        result = report_gate_coverage(str(self.root), "deadbeef" * 5, CONFIG)
        self.assertEqual(result["verdict"], NOT_RUN, result)


if __name__ == "__main__":
    unittest.main()

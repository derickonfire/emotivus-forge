"""Integration tests for the `forge bind` command surface (cli dispatch + exit codes)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.cli import main

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00 +0000",
}


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=_ENV)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


class BindCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tools").mkdir()
        (self.root / "tools" / "check_a.php").write_text('<?php $ok(true, "x");\n', encoding="utf-8")
        _git(self.root, "init", "-q")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "base")
        self.base = _git(self.root, "rev-parse", "HEAD")
        (self.root / "tools" / "check_a.php").write_text('<?php $ok(true, "x"); $ok(1, "y");\n', encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "add assertion")
        self.head = _git(self.root, "rev-parse", "HEAD")
        self.cfg = self.root / "cfg.json"
        self.cfg.write_text(json.dumps({"gate_paths": ["tools/check_*.php"]}), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_gate_diff_confirmed_exit_zero(self) -> None:
        code = main(["bind", "gate-diff", "--repo", str(self.root),
                     "--base", self.base, "--head", self.head, "--config", str(self.cfg)])
        self.assertEqual(code, 0)

    def test_gate_diff_json_confirmed_exit_zero(self) -> None:
        code = main(["bind", "gate-diff", "--repo", str(self.root),
                     "--base", self.base, "--head", self.head, "--config", str(self.cfg), "--json"])
        self.assertEqual(code, 0)

    def test_unreachable_head_exit_two(self) -> None:
        code = main(["bind", "gate-diff", "--repo", str(self.root),
                     "--base", self.base, "--head", "deadbeef" * 5, "--config", str(self.cfg)])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

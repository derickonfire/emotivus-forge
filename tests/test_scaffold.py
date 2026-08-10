"""Isolated tests for `forge init` — the truth+protocol scaffolder (G1; R10).

Scored trial for the observed miss (the discipline has no one-command on-ramp):
the roadmap EXIT is "`forge init` produces a repo that `forge protocol verify`
passes on day one." These tests encode that literally — the emitted
`.forge/protocol.json` verifies CONFIRMED/LIVE both through the direct API and by
executing the scaffolded `forge-gate.sh` end-to-end — and lock the additive
(never-overwrite), profile, dry-run, and CI-emission behavior.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.cli import main
from emotivus_forge.core.protocol_verify import CONFIRMED, verify_protocol
from emotivus_forge.core.scaffold import (
    PROFILES, apply_scaffold, plan_scaffold, seed_protocol,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

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


class ScaffoldFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _paths(self, result: dict) -> set[str]:
        return {p["path"] for p in result["planned"]}


class ProfileFileSetTests(ScaffoldFixture):
    def test_truth_profile_emits_truth_layer_only(self) -> None:
        result = apply_scaffold(str(self.root), "truth")
        self.assertEqual(
            self._paths(result),
            {".forge/protocol.json", "forge-gate.sh", ".forge/README.md"},
        )
        self.assertTrue((self.root / ".forge" / "protocol.json").is_file())
        self.assertTrue((self.root / "forge-gate.sh").is_file())
        # No coordination ceremony in the default profile.
        self.assertFalse((self.root / "AI-OPERATING-AGREEMENT.md").exists())
        self.assertFalse((self.root / "exchange").exists())

    def test_pair_adds_operating_agreement_only(self) -> None:
        result = apply_scaffold(str(self.root), "pair")
        self.assertIn("AI-OPERATING-AGREEMENT.md", self._paths(result))
        self.assertNotIn("exchange/README.md", self._paths(result))
        self.assertNotIn("ROLE-MATRIX.md", self._paths(result))

    def test_fleet_adds_full_substrate(self) -> None:
        result = apply_scaffold(str(self.root), "fleet")
        self.assertLessEqual(
            {"AI-OPERATING-AGREEMENT.md", "exchange/README.md",
             "AUTHORITY-INDEX.md", "WORK-REGISTER.md", "ROLE-MATRIX.md"},
            self._paths(result),
        )
        self.assertTrue((self.root / "exchange" / "README.md").is_file())

    def test_ci_github_emits_workflow_only_when_requested(self) -> None:
        without = apply_scaffold(str(self.root), "truth", "none")
        self.assertNotIn(".github/workflows/forge-gate.yml", self._paths(without))
        other = Path(tempfile.mkdtemp())
        try:
            withci = apply_scaffold(str(other), "truth", "github")
            self.assertIn(".github/workflows/forge-gate.yml", self._paths(withci))
            self.assertTrue((other / ".github" / "workflows" / "forge-gate.yml").is_file())
        finally:
            __import__("shutil").rmtree(other)

    def test_gate_script_is_executable(self) -> None:
        apply_scaffold(str(self.root), "truth")
        mode = (self.root / "forge-gate.sh").stat().st_mode
        self.assertTrue(mode & 0o111, "forge-gate.sh must be executable")

    def test_unknown_profile_raises(self) -> None:
        with self.assertRaises(ValueError):
            apply_scaffold(str(self.root), "vibes")

    def test_unknown_ci_raises(self) -> None:
        with self.assertRaises(ValueError):
            apply_scaffold(str(self.root), "truth", "gitlab")


class SeedProtocolTests(ScaffoldFixture):
    def test_seed_is_not_empty(self) -> None:
        # An empty protocol is NOT_RUN (not a pass); the seed must carry a record.
        self.assertTrue(seed_protocol()["records"])

    def test_seed_verifies_confirmed_live_no_repo(self) -> None:
        result = verify_protocol(seed_protocol(), check_liveness=True)
        self.assertEqual(result["verdict"], CONFIRMED, result)
        liveness = [f for f in result["findings"] if f["check"] == "liveness"]
        self.assertEqual(liveness[0]["state"], CONFIRMED)

    def test_seed_does_not_pin_a_head_so_it_cannot_rot(self) -> None:
        # The genesis record pins no head, so there is nothing for the R8 head-
        # currency guard to fail on as the tree moves — the seed stays CONFIRMED.
        self.assertTrue(all(r.get("type") != "claim" for r in seed_protocol()["records"]))


class DayOneExitProofTests(ScaffoldFixture):
    """The roadmap EXIT criterion, encoded for every profile."""

    def _init_git_repo(self) -> Path:
        _git(self.root, "init", "-q", "-b", "main")
        (self.root / "README.md").write_text("# adopter\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "base")
        return self.root

    def test_emitted_protocol_verifies_for_every_profile(self) -> None:
        repo = self._init_git_repo()
        for profile in PROFILES:
            with self.subTest(profile=profile):
                target = Path(tempfile.mkdtemp())
                try:
                    apply_scaffold(str(target), profile)
                    cfg = json.loads((target / ".forge" / "protocol.json").read_text(encoding="utf-8"))
                    # No repo: pinning + structure + liveness.
                    self.assertEqual(verify_protocol(cfg, check_liveness=True)["verdict"], CONFIRMED)
                    # With a real repo: head-currency guard active, still CONFIRMED
                    # (genesis act pins no head, so nothing can go stale).
                    bound = verify_protocol(cfg, repo=str(repo), check_liveness=True)
                    self.assertEqual(bound["verdict"], CONFIRMED, bound)
                finally:
                    __import__("shutil").rmtree(target)

    def test_scaffolded_gate_script_runs_green_end_to_end(self) -> None:
        # The literal EXIT: run the emitted forge-gate.sh (which calls Phase-3
        # protocol verify) and require exit 0. Forge is supplied via $FORGE.
        self._init_git_repo()
        apply_scaffold(str(self.root), "truth")
        env = {**os.environ, "FORGE": f"{sys.executable} {_REPO_ROOT / 'forge.py'}"}
        proc = subprocess.run(["sh", "forge-gate.sh"], cwd=str(self.root),
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("forge-gate: OK", proc.stdout)


class AdditiveTests(ScaffoldFixture):
    def test_second_init_writes_nothing_and_preserves_content(self) -> None:
        apply_scaffold(str(self.root), "truth")
        # Owner edits a scaffolded file; a re-init must not clobber it.
        gate = self.root / "forge-gate.sh"
        gate.write_text("# owner-customized\n", encoding="utf-8")
        again = apply_scaffold(str(self.root), "truth")
        self.assertEqual(again["written"], [])
        self.assertTrue(all(p["action"] == "skip-exists" for p in again["planned"]))
        self.assertEqual(gate.read_text(encoding="utf-8"), "# owner-customized\n")

    def test_preexisting_file_is_reported_skipped_not_overwritten(self) -> None:
        (self.root / "AI-OPERATING-AGREEMENT.md").write_text("mine\n", encoding="utf-8")
        result = apply_scaffold(str(self.root), "pair")
        agreement = [p for p in result["planned"] if p["path"] == "AI-OPERATING-AGREEMENT.md"][0]
        self.assertEqual(agreement["action"], "skip-exists")
        self.assertEqual((self.root / "AI-OPERATING-AGREEMENT.md").read_text(encoding="utf-8"), "mine\n")

    def test_dry_run_writes_nothing(self) -> None:
        result = apply_scaffold(str(self.root), "fleet", "github", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["written"], [])
        self.assertGreater(result["create_count"], 0)
        self.assertFalse((self.root / ".forge").exists())
        self.assertFalse((self.root / "forge-gate.sh").exists())

    def test_plan_does_not_write(self) -> None:
        plan_scaffold(str(self.root), "truth")
        self.assertFalse((self.root / ".forge").exists())


class InitCliTests(ScaffoldFixture):
    def _run(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            try:
                code = main(list(argv))
            except SystemExit as exc:
                code = int(exc.code or 0)
        return code, buffer.getvalue()

    def test_cli_init_exits_zero_and_writes(self) -> None:
        code, out = self._run("init", str(self.root), "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["seed_verdict"], CONFIRMED)
        self.assertTrue((self.root / ".forge" / "protocol.json").is_file())

    def test_cli_dry_run_writes_nothing(self) -> None:
        code, out = self._run("init", str(self.root), "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["written"], [])
        self.assertFalse((self.root / ".forge").exists())

    def test_cli_missing_target_errors(self) -> None:
        missing = self.root / "does-not-exist"
        code, _ = self._run("init", str(missing))
        self.assertNotEqual(code, 0)

    def test_cli_profile_and_ci_flow_through(self) -> None:
        code, out = self._run("init", str(self.root), "--profile", "fleet", "--ci", "github", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["profile"], "fleet")
        self.assertEqual(payload["ci"], "github")
        self.assertTrue((self.root / ".github" / "workflows" / "forge-gate.yml").is_file())


if __name__ == "__main__":
    unittest.main()

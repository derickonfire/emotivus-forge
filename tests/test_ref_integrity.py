"""Isolated tests for the shared head-integrity guard (R8: stale-ref / force-fetch).

Reproduces, in self-contained temp git repositories (a real remote + clone pair
where needed), the LineCheck stale-ref near-miss: a claim evaluated at a
rebased/force-pushed-away head, or at a stale remote-tracking snapshot, must be
refused (NOT_RUN) — never answered with a content verdict that would be false
for the claim. Also locks the guard's integration into all three G1 binders.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.ref_integrity import (
    FRESH,
    MISSING,
    NOT_A_COMMIT,
    REMOTE_UNVERIFIED,
    STALE_REMOTE_REF,
    SUPERSEDED,
    assess_head,
    guard_finding,
)
from emotivus_forge.core.gate_coverage import report_gate_coverage
from emotivus_forge.core.gate_diff_monotonicity import report_gate_diff_monotonicity
from emotivus_forge.core.source_anchored_release import bind_source_anchored_release

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00 +0000",
}


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, env=_ENV)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class AssessHeadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q", "-b", "main")
        _write(self.root, "a.txt", "one\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "first")
        self.first = _git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_reachable_exact_sha_is_fresh(self) -> None:
        report = assess_head(str(self.root), self.first)
        self.assertEqual(report["status"], FRESH)
        self.assertEqual(report["resolved"], self.first)

    def test_missing_sha_is_missing(self) -> None:
        report = assess_head(str(self.root), "0" * 40)
        self.assertEqual(report["status"], MISSING)

    def test_empty_ref_is_missing(self) -> None:
        self.assertEqual(assess_head(str(self.root), "")["status"], MISSING)

    def test_blob_is_not_a_commit(self) -> None:
        blob = _git(self.root, "rev-parse", f"{self.first}:a.txt")
        report = assess_head(str(self.root), blob)
        self.assertEqual(report["status"], NOT_A_COMMIT)

    def test_local_branch_name_is_fresh(self) -> None:
        report = assess_head(str(self.root), "main")
        self.assertEqual(report["status"], FRESH)
        self.assertEqual(report["resolved"], self.first)

    def test_head_is_fresh(self) -> None:
        self.assertEqual(assess_head(str(self.root), "HEAD")["status"], FRESH)

    def test_amended_away_head_is_superseded(self) -> None:
        # The rebase/force-push signature: the old head still exists in the object
        # store but no current ref reaches it. Existence must not read as currency.
        _write(self.root, "a.txt", "two\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--amend", "-m", "first, rewritten")
        report = assess_head(str(self.root), self.first)
        self.assertEqual(report["status"], SUPERSEDED)
        self.assertIn("force", report["detail"].lower())  # remedy names force-fetch

    def test_older_ancestor_commit_is_fresh_not_superseded(self) -> None:
        # History position is not staleness: an older commit reachable from the
        # branch tip is legitimate binding ground (e.g. an accepted source).
        _write(self.root, "b.txt", "more\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "second")
        report = assess_head(str(self.root), self.first)
        self.assertEqual(report["status"], FRESH)

    def test_abbreviated_superseded_sha_is_superseded_not_fresh(self) -> None:
        # Regression (review finding #1): the SUPERSEDED check must key on whether the
        # anchor is a raw object id, NOT on the 40/64-char spelling. An abbreviated or
        # 12-char form of a rebased-away head previously slipped through as FRESH.
        _write(self.root, "a.txt", "two\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--amend", "-m", "rewritten")
        for spelling in (self.first[:7], self.first[:12], self.first.upper()):
            self.assertEqual(assess_head(str(self.root), spelling)["status"], SUPERSEDED,
                             f"spelling {spelling!r} must be SUPERSEDED")

    def test_abbreviated_reachable_sha_is_fresh(self) -> None:
        for spelling in (self.first[:7], self.first[:12], self.first.upper()):
            self.assertEqual(assess_head(str(self.root), spelling)["status"], FRESH,
                             f"spelling {spelling!r} must be FRESH")


class RemoteFreshnessTests(unittest.TestCase):
    """A real remote + clone pair: stale remote-tracking snapshots must be refused."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.remote = base / "remote.git"
        self.remote.mkdir()
        _git(self.remote, "init", "-q", "--bare", "-b", "main")
        seed = base / "seed"
        seed.mkdir()
        _git(seed, "init", "-q", "-b", "main")
        _write(seed, "a.txt", "one\n")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-q", "-m", "first")
        _git(seed, "remote", "add", "origin", str(self.remote))
        _git(seed, "push", "-q", "origin", "main")
        self.seed = seed
        self.clone = base / "clone"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.clone)],
                       capture_output=True, text=True, env=_ENV, check=True)
        self.first = _git(self.clone, "rev-parse", "origin/main")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_current_remote_tracking_ref_is_fresh(self) -> None:
        report = assess_head(str(self.clone), "origin/main")
        self.assertEqual(report["status"], FRESH)

    def test_force_pushed_remote_makes_local_snapshot_stale(self) -> None:
        # Rewrite history at the remote; the clone's origin/main now lies.
        _write(self.seed, "a.txt", "rewritten\n")
        _git(self.seed, "add", "-A")
        _git(self.seed, "commit", "-q", "--amend", "-m", "first, rewritten")
        _git(self.seed, "push", "-q", "--force", "origin", "main")

        report = assess_head(str(self.clone), "origin/main")
        self.assertEqual(report["status"], STALE_REMOTE_REF)
        self.assertIn(self.first[:12], report["detail"])  # names both sides
        self.assertIn("fetch --force", report["detail"])  # remedy is explicit

        # After the force-fetch the same name is fresh again.
        _git(self.clone, "fetch", "--force", "-q", "origin")
        self.assertEqual(assess_head(str(self.clone), "origin/main")["status"], FRESH)

    def test_unreachable_remote_is_refused_not_assumed(self) -> None:
        _git(self.clone, "remote", "set-url", "origin",
             str(Path(self._tmp.name) / "does-not-exist.git"))
        report = assess_head(str(self.clone), "origin/main")
        self.assertEqual(report["status"], REMOTE_UNVERIFIED)

    def test_exact_sha_reachable_only_via_remote_ref_is_superseded(self) -> None:
        # Regression (review finding #3): an exact SHA reachable ONLY through a
        # remote-tracking ref (no local branch/tag/HEAD reaches it) must NOT be laundered
        # into FRESH — remote-tracking refs are unverified snapshots. Build commit B,
        # push it, fetch it (origin/main -> B) while the clone's local main + HEAD stay
        # at the earlier commit, so B is reached only by origin/main.
        _write(self.seed, "b.txt", "second\n")
        _git(self.seed, "add", "-A")
        _git(self.seed, "commit", "-q", "-m", "second")
        _git(self.seed, "push", "-q", "origin", "main")
        b_sha = _git(self.seed, "rev-parse", "HEAD")
        _git(self.clone, "fetch", "-q", "origin")  # origin/main -> B; local main stays behind
        self.assertEqual(_git(self.clone, "rev-parse", "origin/main"), b_sha)
        self.assertNotEqual(_git(self.clone, "rev-parse", "main"), b_sha)  # local main lags
        report = assess_head(str(self.clone), b_sha)
        self.assertEqual(report["status"], SUPERSEDED,
                         "an exact SHA reached only by a remote-tracking ref must be SUPERSEDED")
        # And binding the NAME origin/main (now fresh) is FRESH — the name path verifies it.
        self.assertEqual(assess_head(str(self.clone), "origin/main")["status"], FRESH)


class GuardFindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q", "-b", "main")
        _write(self.root, "a.txt", "one\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "first")
        self.first = _git(self.root, "rev-parse", "HEAD")
        _write(self.root, "a.txt", "two\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--amend", "-m", "rewritten")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_superseded_head_blocks_with_not_run_finding(self) -> None:
        blocking, assessment = guard_finding(str(self.root), self.first)
        self.assertIsNotNone(blocking)
        self.assertEqual(blocking["state"], "NOT_RUN")
        self.assertIn("SUPERSEDED", blocking["detail"])
        self.assertEqual(assessment["status"], SUPERSEDED)

    def test_allow_superseded_unblocks_but_reports(self) -> None:
        blocking, assessment = guard_finding(str(self.root), self.first, allow_superseded=True)
        self.assertIsNone(blocking)
        self.assertEqual(assessment["status"], SUPERSEDED)


class BinderIntegrationTests(unittest.TestCase):
    """The scored-trial core: a rebased-away head must yield NOT_RUN from every
    binder — never the false CONTRADICTED the stale tree would have produced."""

    RELEASE_CONFIG = {
        "release_state_file": "RELEASE-STATE.json",
        "accepted_schema_pointer": "/schema",
        "accepted_source_pointer": "/source_commit",
        "schema_source": {"file": "schema.py", "regex": r"SCHEMA\s*=\s*(\d+)"},
        "candidate_schema_pointer": "/candidate/schema",
        "candidate_status_pointer": "/candidate/status",
        "candidate_not_accepted_statuses": ["review"],
        "candidate_acceptance_evidence_pointer": "/candidate/evidence",
        "accepted_surfaces": ["README.md"],
        "schema_claim_regex": r"schema[^0-9]{0,10}(?P<n>\d+)",
    }

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q", "-b", "main")
        # A tree whose release truth is WRONG (schema mismatch): the old code path
        # would report CONTRADICTED here. After supersession the only honest
        # answer for a claim about current truth is a refusal.
        _write(self.root, "schema.py", "SCHEMA = 72\n")
        _write(self.root, "README.md", "ships schema 73\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "lying head")
        self.lying_source = _git(self.root, "rev-parse", "HEAD")
        _write(self.root, "RELEASE-STATE.json", json.dumps({
            "schema": 73, "source_commit": self.lying_source,
            "candidate": {"schema": 73, "status": "accepted", "evidence": "x"},
        }))
        _write(self.root, "checks/check_a.py", "assertTrue(1)\n")
        _write(self.root, "gate.sh", "python checks/check_a.py\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "lying release state")
        self.old_head = _git(self.root, "rev-parse", "HEAD")
        # Sanity: at the still-reachable head the binder DOES contradict.
        pre = bind_source_anchored_release(str(self.root), self.old_head, self.RELEASE_CONFIG)
        assert pre["verdict"] == "CONTRADICTED", pre
        # Now the rebase/force-push: rewrite history so old_head is superseded.
        _git(self.root, "reset", "-q", "--hard", "HEAD~1")
        _write(self.root, "honest.txt", "rewritten history\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "rewritten")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_release_truth_refuses_superseded_head(self) -> None:
        result = bind_source_anchored_release(str(self.root), self.old_head, self.RELEASE_CONFIG)
        self.assertEqual(result["verdict"], "NOT_RUN", result)  # NOT the false CONTRADICTED
        self.assertTrue(any("SUPERSEDED" in f["detail"] for f in result["findings"]))

    def test_release_truth_allow_superseded_binds_historically(self) -> None:
        config = {**self.RELEASE_CONFIG, "allow_superseded_head": True}
        result = bind_source_anchored_release(str(self.root), self.old_head, config)
        # Deliberate historical bind: the content verdict returns, with the waiver recorded.
        self.assertEqual(result["verdict"], "CONTRADICTED", result)
        self.assertTrue(any(f["check"] == "head-integrity" for f in result["findings"]))

    def test_gate_coverage_refuses_superseded_head(self) -> None:
        config = {"check_inventory": ["checks/check_*.py"], "gate_sources": ["gate.sh"]}
        result = report_gate_coverage(str(self.root), self.old_head, config)
        self.assertEqual(result["verdict"], "NOT_RUN", result)
        self.assertTrue(any("SUPERSEDED" in f["detail"] for f in result["findings"]))

    def test_gate_diff_refuses_superseded_anchor(self) -> None:
        config = {"gate_paths": ["checks/*", "gate.sh"]}
        current = _git(self.root, "rev-parse", "HEAD")
        result = report_gate_diff_monotonicity(str(self.root), self.old_head, current, config)
        self.assertEqual(result["verdict"], "NOT_RUN", result)
        self.assertTrue(any("SUPERSEDED" in f["detail"] for f in result["findings"]))


if __name__ == "__main__":
    unittest.main()

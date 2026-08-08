"""Isolated tests for source-anchored release verification (G1 truth core).

Reproduces, in a self-contained temp git repository, the exact failure mode the
LineCheck engagement exposed: a release declared accepted at a schema its
accepted source never shipped, with public surfaces rewritten to the candidate
value — a lie every internal-consistency gate passed green. The binder must
CONTRADICT it, CONFIRM the honest split, and return NOT_RUN when it cannot reach
the anchor (never upgrading absence to a confirmation).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.source_anchored_release import (
    bind_source_anchored_release, CONFIRMED, CONTRADICTED, NOT_RUN,
)

CONFIG = {
    "release_state_file": "Release/RELEASE-STATE.json",
    "accepted_schema_pointer": "/schema_step",
    "accepted_source_pointer": "/source_commit",
    "schema_source": {"file": "site/app/schema.php", "regex": r"LC_SCHEMA_VERSION',\s*(\d+)"},
    "candidate_schema_pointer": "/current_candidate/schema_step",
    "candidate_status_pointer": "/current_candidate/status",
    "candidate_not_accepted_statuses": ["implemented_in_review_not_accepted"],
    "candidate_acceptance_evidence_pointer": "/current_candidate/acceptance_evidence",
    "accepted_surfaces": ["README-EXPORT.md"],
    "schema_claim_regex": r"schema[^0-9]{0,14}(?:step[^0-9]{0,4})?(?P<n>\d{2,3})",
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


def _release_state(source_sha: str, top_schema: int, cand_status: str, cand_evidence) -> str:
    return json.dumps({
        "schema_step": top_schema,
        "source_commit": source_sha,
        "current_candidate": {
            "schema_step": 73,
            "status": cand_status,
            "acceptance_evidence": cand_evidence,
        },
    }, indent=2)


class SourceAnchoredReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q")
        # Accepted source commit: schema 72 is what the accepted release truly shipped.
        _write(self.root, "site/app/schema.php", "<?php\ndefine('LC_SCHEMA_VERSION', 72);\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "accepted source at schema 72")
        self.source_sha = _git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _head_with(self, release_state: str, readme: str) -> str:
        # Advance schema.php to the candidate (73) as the branch would, then declare release state.
        _write(self.root, "site/app/schema.php", "<?php\ndefine('LC_SCHEMA_VERSION', 73);\n")
        _write(self.root, "Release/RELEASE-STATE.json", release_state)
        _write(self.root, "README-EXPORT.md", readme)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "candidate head")
        return _git(self.root, "rev-parse", "HEAD")

    def _bind(self, head: str) -> dict:
        return bind_source_anchored_release(str(self.root), head, CONFIG)

    def test_clean_split_confirms(self) -> None:
        head = self._head_with(
            _release_state(self.source_sha, 72, "implemented_in_review_not_accepted", None),
            "**Schema:** step 72\n")
        result = self._bind(head)
        self.assertEqual(result["verdict"], CONFIRMED, result)

    def test_top_schema_moved_ahead_is_contradicted(self) -> None:
        # RELEASE-STATE top schema moved to 73 while the accepted source shipped 72.
        head = self._head_with(
            _release_state(self.source_sha, 73, "implemented_in_review_not_accepted", None),
            "**Schema:** step 72\n")
        result = self._bind(head)
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertTrue(any(f["check"] == "release-state-top-schema" and f["state"] == CONTRADICTED
                            for f in result["findings"]))

    def test_accepted_surface_leaks_candidate_is_contradicted(self) -> None:
        # The exact codex/0033 failure: an accepted/public surface claims schema 73.
        head = self._head_with(
            _release_state(self.source_sha, 72, "implemented_in_review_not_accepted", None),
            "**Schema:** step 73\n")
        result = self._bind(head)
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertTrue(any(f["check"] == "accepted-surface-states-true-schema" and f["state"] == CONTRADICTED
                            for f in result["findings"]))

    def test_strict_mode_flags_wrong_non_candidate_number(self) -> None:
        # A surface stating a wrong schema (71) that is neither the true 72 nor the candidate 73.
        head = self._head_with(
            _release_state(self.source_sha, 72, "implemented_in_review_not_accepted", None),
            "**Schema:** step 71\n")
        strict = dict(CONFIG, surface_schema_mode="strict")
        result = bind_source_anchored_release(str(self.root), head, strict)
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertTrue(any(f["check"] == "accepted-surface-states-true-schema" and f["state"] == CONTRADICTED
                            for f in result["findings"]))

    def test_strict_mode_tolerates_allowlisted_historical_number(self) -> None:
        # A surface that legitimately mentions a historical schema (68) alongside the true 72.
        head = self._head_with(
            _release_state(self.source_sha, 72, "implemented_in_review_not_accepted", None),
            "Upgraded from schema step 68 to schema step 72.\n")
        strict = dict(CONFIG, surface_schema_mode="strict", historical_schema_allowlist=[68])
        result = bind_source_anchored_release(str(self.root), head, strict)
        self.assertEqual(result["verdict"], CONFIRMED, result)

    def test_candidate_carrying_acceptance_evidence_is_contradicted(self) -> None:
        head = self._head_with(
            _release_state(self.source_sha, 72, "implemented_in_review_not_accepted", {"run": "x"}),
            "**Schema:** step 72\n")
        result = self._bind(head)
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertTrue(any(f["check"] == "candidate-labelled-not-accepted" and f["state"] == CONTRADICTED
                            for f in result["findings"]))

    def test_unreachable_head_is_not_run(self) -> None:
        result = self._bind("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        self.assertEqual(result["verdict"], NOT_RUN, result)

    def test_unreachable_accepted_source_is_not_run_not_confirmed(self) -> None:
        # Anchor missing → must be NOT_RUN, never silently CONFIRMED.
        head = self._head_with(
            _release_state("f" * 40, 72, "implemented_in_review_not_accepted", None),
            "**Schema:** step 72\n")
        result = self._bind(head)
        self.assertEqual(result["verdict"], NOT_RUN, result)

    def test_baseline_invariance_identity_confirms(self) -> None:
        head = self._head_with(
            _release_state(self.source_sha, 72, "implemented_in_review_not_accepted", None),
            "**Schema:** step 72\n")
        config = dict(CONFIG, baseline_invariance={
            "certified_head": head,
            "paths": ["Release/RELEASE-STATE.json", "README-EXPORT.md"],
        })
        result = bind_source_anchored_release(str(self.root), head, config)
        self.assertEqual(result["verdict"], CONFIRMED, result)


if __name__ == "__main__":
    unittest.main()

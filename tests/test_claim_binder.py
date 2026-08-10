"""Isolated tests for the generalized structured-claim binder (G1; R3).

Each claim type is evaluated against a real temp git repository: CONFIRMED with a
reproduce command when the relation holds, CONTRADICTED when it fails, NOT_RUN
when it cannot be assessed — and the shared head-integrity guard refuses claims
anchored at superseded heads (the LineCheck stale-ref shape). Also locks the
`forge bind claims` CLI and the --ledger feed: verdicts land in the truth ledger
as binder-derived entries, with NOT_RUN mapping to terminal UNVERIFIABLE.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.cli import main
from emotivus_forge.core.claim_binder import bind_claims, CONFIRMED, CONTRADICTED, NOT_RUN
from emotivus_forge.core.truth_ledger import read_ledger

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


class ClaimBinderFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q", "-b", "main")
        _write(self.root, "charter.md", "the received charter\n")
        _write(self.root, "version.py", 'VERSION = "3"\n')
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "base")
        self.base = _git(self.root, "rev-parse", "HEAD")
        _write(self.root, "feature.txt", "work\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "head")
        self.head = _git(self.root, "rev-parse", "HEAD")
        self.charter_sha256 = hashlib.sha256(b"the received charter\n").hexdigest()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _bind(self, *claims: dict, **config) -> dict:
        return bind_claims(str(self.root), {"claims": list(claims), **config})


class ClaimTypeTests(ClaimBinderFixture):
    def test_head_equals_confirmed_and_contradicted(self) -> None:
        good = self._bind({"id": "pin", "type": "head-equals", "ref": "main", "sha": self.head})
        self.assertEqual(good["verdict"], CONFIRMED, good)
        self.assertTrue(good["findings"][0]["reproduce"])
        bad = self._bind({"id": "pin", "type": "head-equals", "ref": "main", "sha": self.base})
        self.assertEqual(bad["verdict"], CONTRADICTED, bad)

    def test_ancestry_confirmed_and_contradicted(self) -> None:
        good = self._bind({"id": "anc", "type": "ancestry", "ancestor": self.base, "descendant": self.head})
        self.assertEqual(good["verdict"], CONFIRMED, good)
        bad = self._bind({"id": "anc", "type": "ancestry", "ancestor": self.head, "descendant": self.base})
        self.assertEqual(bad["verdict"], CONTRADICTED, bad)

    def test_blob_identity_across_refs(self) -> None:
        # The "verbatim received-source charter unchanged" receipt, mechanized.
        good = self._bind({"id": "charter", "type": "blob-identity", "ref": self.head,
                           "path": "charter.md", "other_ref": self.base})
        self.assertEqual(good["verdict"], CONFIRMED, good)
        bad = self._bind({"id": "drift", "type": "blob-identity", "ref": self.head,
                          "path": "feature.txt", "other_ref": self.base, "other_path": "charter.md"})
        self.assertEqual(bad["verdict"], CONTRADICTED, bad)

    def test_blob_identity_against_stated_blob_sha(self) -> None:
        blob = _git(self.root, "rev-parse", f"{self.head}:charter.md")
        good = self._bind({"id": "b", "type": "blob-identity", "ref": self.head,
                           "path": "charter.md", "blob_sha": blob})
        self.assertEqual(good["verdict"], CONFIRMED, good)

    def test_file_sha256(self) -> None:
        good = self._bind({"id": "h", "type": "file-sha256", "ref": self.head,
                           "path": "charter.md", "sha256": self.charter_sha256})
        self.assertEqual(good["verdict"], CONFIRMED, good)
        bad = self._bind({"id": "h", "type": "file-sha256", "ref": self.head,
                          "path": "charter.md", "sha256": "0" * 64})
        self.assertEqual(bad["verdict"], CONTRADICTED, bad)

    def test_file_regex_with_capture(self) -> None:
        good = self._bind({"id": "v", "type": "file-regex", "ref": self.head,
                           "path": "version.py", "regex": r'VERSION = "(\d+)"', "expect": "3"})
        self.assertEqual(good["verdict"], CONFIRMED, good)
        bad = self._bind({"id": "v", "type": "file-regex", "ref": self.head,
                          "path": "version.py", "regex": r'VERSION = "(\d+)"', "expect": "4"})
        self.assertEqual(bad["verdict"], CONTRADICTED, bad)

    def test_absent_file_is_not_run_never_contradicted(self) -> None:
        result = self._bind({"id": "gone", "type": "file-sha256", "ref": self.head,
                             "path": "missing.txt", "sha256": "0" * 64})
        self.assertEqual(result["verdict"], NOT_RUN, result)

    def test_head_equals_accepts_abbreviated_claimed_sha(self) -> None:
        # Regression (review finding #4): a TRUE claim stated with git's own short-sha
        # form must not be a false CONTRADICTED.
        for sha in (self.head[:7], self.head[:12], self.head.upper()):
            good = self._bind({"id": "pin", "type": "head-equals", "ref": "main", "sha": sha})
            self.assertEqual(good["verdict"], CONFIRMED, (sha, good))
        # A short prefix that is genuinely wrong is still CONTRADICTED.
        wrong = self._bind({"id": "pin", "type": "head-equals", "ref": "main", "sha": self.base[:12]})
        self.assertEqual(wrong["verdict"], CONTRADICTED, wrong)

    def test_blob_identity_without_target_is_not_run(self) -> None:
        # Regression (review finding #6): neither other_ref nor blob_sha -> unassessable.
        result = self._bind({"id": "b", "type": "blob-identity", "ref": self.head, "path": "charter.md"})
        self.assertEqual(result["verdict"], NOT_RUN, result)


class ClaimSetSemanticsTests(ClaimBinderFixture):
    def test_empty_claim_set_is_not_run(self) -> None:
        self.assertEqual(bind_claims(str(self.root), {"claims": []})["verdict"], NOT_RUN)
        self.assertEqual(bind_claims(str(self.root), {})["verdict"], NOT_RUN)

    def test_unknown_type_and_missing_fields_are_not_run(self) -> None:
        result = self._bind({"id": "x", "type": "vibes"}, {"id": "y", "type": "ancestry"})
        self.assertEqual(result["verdict"], NOT_RUN, result)
        details = " ".join(f["detail"] for f in result["findings"])
        self.assertIn("unknown claim type", details)
        self.assertIn("missing required field", details)

    def test_verdict_precedence_contradicted_wins(self) -> None:
        result = self._bind(
            {"id": "ok", "type": "ancestry", "ancestor": self.base, "descendant": self.head},
            {"id": "gone", "type": "file-sha256", "ref": self.head, "path": "no.txt", "sha256": "0" * 64},
            {"id": "bad", "type": "head-equals", "ref": "main", "sha": self.base},
        )
        self.assertEqual(result["verdict"], CONTRADICTED, result)

    def test_blob_identity_guards_other_ref(self) -> None:
        # Regression (review finding #2): other_ref is a genuine resolution anchor, so a
        # superseded/stale other_ref must be refused (NOT_RUN), never yield a content
        # verdict against unverified state — even when the bytes happen to match.
        superseded = self.head  # captured in setUp
        _git(self.root, "commit", "-q", "--amend", "-m", "rewrite head")  # superseded is now unreachable
        result = self._bind({"id": "charter", "type": "blob-identity", "ref": "HEAD",
                             "path": "charter.md", "other_ref": superseded, "other_path": "charter.md"})
        self.assertEqual(result["verdict"], NOT_RUN, result)
        self.assertIn("SUPERSEDED", result["findings"][0]["detail"])

    def test_superseded_anchor_is_refused_not_verdicted(self) -> None:
        # Rewrite history so self.head is force-pushed away; a claim anchored
        # there must be refused (NOT_RUN), never answered with a content verdict.
        _git(self.root, "reset", "-q", "--hard", "HEAD~1")
        _write(self.root, "other.txt", "rewritten\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "rewritten")
        result = self._bind({"id": "stale", "type": "file-sha256", "ref": self.head,
                             "path": "charter.md", "sha256": self.charter_sha256})
        self.assertEqual(result["verdict"], NOT_RUN, result)
        self.assertIn("SUPERSEDED", result["findings"][0]["detail"])


class BindClaimsCliTests(ClaimBinderFixture):
    def _run(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            try:
                code = main(list(argv))
            except SystemExit as exc:  # argparse error path
                code = int(exc.code or 0)
        return code, buffer.getvalue()

    def _config_file(self, payload: dict) -> str:
        path = self.root / "claims.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_cli_confirmed_exit_zero_and_json(self) -> None:
        config = self._config_file({"claims": [
            {"id": "anc", "type": "ancestry", "ancestor": self.base, "descendant": self.head},
        ]})
        code, out = self._run("bind", "claims", "--repo", str(self.root), "--config", config, "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["verdict"], CONFIRMED)
        self.assertEqual(payload["claim_count"], 1)

    def test_cli_contradicted_exit_one(self) -> None:
        config = self._config_file({"claims": [
            {"id": "pin", "type": "head-equals", "ref": "main", "sha": self.base},
        ]})
        code, _ = self._run("bind", "claims", "--repo", str(self.root), "--config", config)
        self.assertEqual(code, 1)

    def test_ledger_feed_records_binder_derived_confirmed(self) -> None:
        project = self.root / "project"
        project.mkdir()
        config = self._config_file({"claims": [
            {"id": "anc", "type": "ancestry", "ancestor": self.base, "descendant": self.head},
        ]})
        code, _ = self._run("bind", "claims", "--repo", str(self.root), "--config", config,
                            "--ledger", "--project", str(project))
        self.assertEqual(code, 0)
        rows = read_ledger(project)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "CONFIRMED")
        self.assertEqual(rows[0]["derivation"], "binder")
        self.assertIn("merge-base --is-ancestor", rows[0]["reproduce"])

    def test_ledger_feed_maps_guard_refusal_to_unverifiable(self) -> None:
        # Force-push away the head, then bind a claim anchored at it with --ledger:
        # the entry must land UNVERIFIABLE (terminal), never a positive verdict.
        _git(self.root, "reset", "-q", "--hard", "HEAD~1")
        _write(self.root, "other.txt", "rewritten\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "rewritten")
        project = self.root / "project"
        project.mkdir()
        config = self._config_file({"claims": [
            {"id": "stale", "type": "file-sha256", "ref": self.head,
             "path": "charter.md", "sha256": self.charter_sha256},
        ]})
        code, _ = self._run("bind", "claims", "--repo", str(self.root), "--config", config,
                            "--ledger", "--project", str(project))
        self.assertEqual(code, 2)
        rows = read_ledger(project)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "UNVERIFIABLE")
        self.assertEqual(rows[0]["derivation"], "binder")


if __name__ == "__main__":
    unittest.main()

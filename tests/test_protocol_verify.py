"""Isolated tests for `forge protocol verify` (G1; R9 — protocol verify + enforce).

Scored trial for the observed miss (protocol invariants living only in prose): a
healthy declared protocol confirms; each invariant violation is CAUGHT, not
smoothed — including the LineCheck shape of a claim pinned to a moving ref or a
rebased-away (superseded) head, verified through the R8 head-integrity guard.
Also locks the single-baton liveness check and the `--ledger` binder feed.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.cli import main
from emotivus_forge.core.protocol_verify import (
    CONFIRMED, CONTRADICTED, NOT_RUN, verify_protocol,
)
from emotivus_forge.core.truth_ledger import read_ledger

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


def _states(result: dict) -> dict[str, str]:
    return {f["check"]: f["state"] for f in result["findings"]}


class GitFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q", "-b", "main")
        (self.root / "a.txt").write_text("one\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "one")
        self.head = _git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _healthy(self) -> dict:
        return {
            "initial_holder": "codex",
            "records": [
                {"id": "c1", "party": "codex", "type": "claim", "pins_head": self.head},
                {"id": "a1", "party": "claude", "type": "accept", "pins_head": self.head,
                 "receipt": {"reviewed_head": self.head, "review_id": "4891354017"}},
                {"id": "h1", "party": "codex", "type": "handoff", "from": "codex", "to": "claude"},
                {"id": "m1", "party": "owner", "type": "act", "irreversible": True, "owner_authorized": "owner-sig"},
            ],
        }


class HealthyProtocolTests(GitFixture):
    def test_healthy_protocol_confirms(self) -> None:
        result = verify_protocol(self._healthy(), repo=str(self.root), check_liveness=True)
        self.assertEqual(result["verdict"], CONFIRMED, result)
        self.assertTrue(result["head_currency_checked"])
        self.assertEqual(_states(result)["liveness"], CONFIRMED)

    def test_confirmed_findings_carry_reproduce(self) -> None:
        # So a CONFIRMED protocol can back a binder-derived ledger entry.
        result = verify_protocol(self._healthy(), repo=str(self.root), check_liveness=True)
        self.assertTrue(all(f["reproduce"] for f in result["findings"]))


class ExactHeadInvariantTests(GitFixture):
    def test_moving_ref_claim_is_contradicted(self) -> None:
        cfg = {"records": [{"id": "c1", "party": "codex", "type": "claim", "pins_head": "main"}]}
        result = verify_protocol(cfg, repo=str(self.root))
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertEqual(_states(result)["exact-head:c1"], CONTRADICTED)
        self.assertIn("moves", result["findings"][-1]["detail"])

    def test_superseded_head_claim_is_contradicted(self) -> None:
        # The LineCheck `main@1780e3b` shape: a claim pinned to a rebased-away head.
        stale = self.head
        (self.root / "a.txt").write_text("two\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--amend", "-m", "rewritten")  # stale now superseded
        cfg = {"records": [{"id": "c1", "party": "codex", "type": "claim", "pins_head": stale}]}
        result = verify_protocol(cfg, repo=str(self.root))
        self.assertEqual(result["verdict"], CONTRADICTED, result)
        self.assertIn("not current", _find(result, "exact-head:c1")["detail"])

    def test_missing_head_is_contradicted(self) -> None:
        cfg = {"records": [{"id": "c1", "party": "codex", "type": "claim"}]}
        self.assertEqual(verify_protocol(cfg, repo=str(self.root))["verdict"], CONTRADICTED)

    def test_no_repo_checks_pinning_only(self) -> None:
        # Without --repo, an exact id confirms pinning (currency explicitly not checked),
        # while a moving name is still a violation.
        good = verify_protocol({"records": [{"id": "c", "party": "p", "type": "claim", "pins_head": self.head}]})
        self.assertEqual(_find(good, "exact-head:c")["state"], CONFIRMED)
        self.assertIn("currency not checked", _find(good, "exact-head:c")["detail"])
        bad = verify_protocol({"records": [{"id": "c", "party": "p", "type": "claim", "pins_head": "feature-branch"}]})
        self.assertEqual(_find(bad, "exact-head:c")["state"], CONTRADICTED)


class ReceiptInvariantTests(GitFixture):
    def test_accept_without_receipt_is_contradicted(self) -> None:
        cfg = {"records": [{"id": "a1", "party": "claude", "type": "accept", "pins_head": self.head}]}
        result = verify_protocol(cfg, repo=str(self.root))
        self.assertEqual(_find(result, "bindable-receipt:a1")["state"], CONTRADICTED)

    def test_receipt_without_exact_reviewed_head_is_contradicted(self) -> None:
        cfg = {"records": [{"id": "a1", "party": "claude", "type": "accept", "pins_head": self.head,
                            "receipt": {"reviewed_head": "main", "review_id": "1"}}]}
        self.assertEqual(_find(verify_protocol(cfg), "bindable-receipt:a1")["state"], CONTRADICTED)

    def test_receipt_without_evidence_is_contradicted(self) -> None:
        cfg = {"records": [{"id": "a1", "party": "claude", "type": "accept", "pins_head": self.head,
                            "receipt": {"reviewed_head": self.head}}]}
        self.assertEqual(_find(verify_protocol(cfg), "bindable-receipt:a1")["state"], CONTRADICTED)


class StructuredStateInvariantTests(GitFixture):
    def test_unknown_type_is_prose_only(self) -> None:
        cfg = {"records": [{"id": "x", "party": "p", "type": "vibes"}]}
        self.assertEqual(_find(verify_protocol(cfg), "structured-state:x")["state"], CONTRADICTED)

    def test_missing_party_is_prose_only(self) -> None:
        cfg = {"records": [{"id": "x", "type": "claim", "pins_head": "deadbeefcafe"}]}
        self.assertEqual(_find(verify_protocol(cfg), "structured-state:x")["state"], CONTRADICTED)


class SupersessionInvariantTests(GitFixture):
    def test_supersede_unknown_target_is_contradicted(self) -> None:
        cfg = {"records": [{"id": "b", "party": "p", "type": "claim", "pins_head": "deadbeefcafe",
                            "supersedes": "ghost"}]}
        self.assertEqual(_find(verify_protocol(cfg), "supersession:b")["state"], CONTRADICTED)

    def test_double_supersede_is_a_fork(self) -> None:
        cfg = {"records": [
            {"id": "a", "party": "p", "type": "claim", "pins_head": "deadbeefcafe"},
            {"id": "b", "party": "p", "type": "claim", "pins_head": "deadbeefcafe", "supersedes": "a"},
            {"id": "c", "party": "p", "type": "claim", "pins_head": "deadbeefcafe", "supersedes": "a"},
        ]}
        result = verify_protocol(cfg)
        self.assertEqual(result["verdict"], CONTRADICTED)
        self.assertTrue(any(f["check"].startswith("supersession:") and f["state"] == CONTRADICTED
                            and "fork" in f["detail"] for f in result["findings"]))

    def test_valid_supersession_confirms(self) -> None:
        cfg = {"records": [
            {"id": "a", "party": "p", "type": "claim", "pins_head": "deadbeefcafe"},
            {"id": "b", "party": "p", "type": "claim", "pins_head": "deadbeefcafe", "supersedes": "a"},
        ]}
        self.assertEqual(_find(verify_protocol(cfg), "supersession:b")["state"], CONFIRMED)

    def test_cycle_is_detected(self) -> None:
        cfg = {"records": [
            {"id": "a", "party": "p", "type": "claim", "pins_head": "deadbeefcafe", "supersedes": "b"},
            {"id": "b", "party": "p", "type": "claim", "pins_head": "deadbeefcafe", "supersedes": "a"},
        ]}
        result = verify_protocol(cfg)
        self.assertEqual(result["verdict"], CONTRADICTED)
        self.assertTrue(any(f["check"] == "supersession:cycle" for f in result["findings"]))

    def test_superseded_stale_head_claim_is_not_reflagged(self) -> None:
        # Self-review fix: the healthy pattern — a claim whose head went stale, later
        # SUPERSEDED by a claim at the current head — must CONFIRM, not CONTRADICT on the
        # historical (now-superseded) record.
        stale = self.head
        (self.root / "a.txt").write_text("two\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "two")
        current = _git(self.root, "rev-parse", "HEAD")
        cfg = {"records": [
            {"id": "c1", "party": "codex", "type": "claim", "pins_head": stale},
            {"id": "c2", "party": "codex", "type": "claim", "pins_head": current, "supersedes": "c1"},
        ]}
        result = verify_protocol(cfg, repo=str(self.root))
        self.assertEqual(result["verdict"], CONFIRMED, result)
        # c1 is superseded -> not currency-checked; c2 (current head) confirms.
        self.assertFalse(any(f["check"] == "exact-head:c1" for f in result["findings"]))
        self.assertEqual(_find(result, "exact-head:c2")["state"], CONFIRMED)

    def test_duplicate_id_is_flagged(self) -> None:
        cfg = {"records": [
            {"id": "dup", "party": "p", "type": "claim", "pins_head": "deadbeefcafe"},
            {"id": "dup", "party": "p", "type": "claim", "pins_head": "deadbeefcafe"},
        ]}
        result = verify_protocol(cfg)
        self.assertEqual(result["verdict"], CONTRADICTED)
        self.assertTrue(any("duplicate record id" in f["detail"] for f in result["findings"]))

    def test_object_id_head_absent_from_repo_is_not_run(self) -> None:
        # Self-review fix: an exact id not present in THIS repo is NOT_RUN, not a false
        # verdict (shallow clone / wrong repo). Isolated so no CONTRADICTED masks it.
        cfg = {"records": [{"id": "c", "party": "p", "type": "claim", "pins_head": "abcdef1234567"}]}
        result = verify_protocol(cfg, repo=str(self.root))
        self.assertEqual(_find(result, "exact-head:c")["state"], NOT_RUN)
        self.assertEqual(result["verdict"], NOT_RUN, result)


class OwnerGateInvariantTests(GitFixture):
    def test_ungated_irreversible_act_is_contradicted(self) -> None:
        cfg = {"records": [{"id": "m", "party": "codex", "type": "act", "irreversible": True}]}
        self.assertEqual(_find(verify_protocol(cfg), "owner-gated:m")["state"], CONTRADICTED)

    def test_gated_irreversible_act_confirms(self) -> None:
        cfg = {"records": [{"id": "m", "party": "owner", "type": "act", "irreversible": True,
                            "owner_authorized": "owner-sig"}]}
        self.assertEqual(_find(verify_protocol(cfg), "owner-gated:m")["state"], CONFIRMED)

    def test_reversible_act_needs_no_gate(self) -> None:
        cfg = {"records": [{"id": "m", "party": "codex", "type": "act"}]}
        result = verify_protocol(cfg)
        self.assertFalse(any(f["check"] == "owner-gated:m" for f in result["findings"]))


class LivenessInvariantTests(GitFixture):
    def _live(self, **cfg) -> dict:
        return verify_protocol(cfg, check_liveness=True)

    def test_single_conserved_baton_is_live(self) -> None:
        result = self._live(initial_holder="codex", records=[
            {"id": "h1", "party": "codex", "type": "handoff", "from": "codex", "to": "claude"},
            {"id": "h2", "party": "claude", "type": "handoff", "from": "claude", "to": "owner"},
        ])
        self.assertEqual(_find(result, "liveness")["state"], CONFIRMED)
        self.assertIn("'owner'", _find(result, "liveness")["detail"])

    def test_forged_transfer_is_stalled(self) -> None:
        # A handoff FROM a party that does not hold the baton.
        result = self._live(initial_holder="codex", records=[
            {"id": "h1", "party": "claude", "type": "handoff", "from": "claude", "to": "owner"},
        ])
        self.assertEqual(_find(result, "liveness")["state"], CONTRADICTED)
        self.assertIn("STALLED", _find(result, "liveness")["detail"])

    def test_dropped_baton_is_stalled(self) -> None:
        result = self._live(initial_holder="codex", records=[
            {"id": "h1", "party": "codex", "type": "handoff", "from": "codex", "to": ""},
        ])
        self.assertEqual(_find(result, "liveness")["state"], CONTRADICTED)

    def test_no_holder_is_stalled(self) -> None:
        result = self._live(records=[{"id": "c", "party": "p", "type": "claim", "pins_head": "deadbeefcafe"}])
        self.assertEqual(_find(result, "liveness")["state"], CONTRADICTED)

    def test_superseded_handoff_is_skipped_in_replay(self) -> None:
        # A superseded handoff is history; replay uses the current tip only.
        result = self._live(initial_holder="codex", records=[
            {"id": "h1", "party": "codex", "type": "handoff", "from": "codex", "to": "wrong"},
            {"id": "h2", "party": "codex", "type": "handoff", "from": "codex", "to": "claude", "supersedes": "h1"},
        ])
        self.assertEqual(_find(result, "liveness")["state"], CONFIRMED)
        self.assertIn("'claude'", _find(result, "liveness")["detail"])


class EmptyProtocolTests(GitFixture):
    def test_no_records_is_not_run(self) -> None:
        self.assertEqual(verify_protocol({"records": []})["verdict"], NOT_RUN)
        self.assertEqual(verify_protocol({})["verdict"], NOT_RUN)


class ProtocolCliTests(GitFixture):
    def _run(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            try:
                code = main(list(argv))
            except SystemExit as exc:
                code = int(exc.code or 0)
        return code, buffer.getvalue()

    def _cfg(self, payload: dict) -> str:
        path = self.root / "protocol.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_cli_confirmed_exit_zero(self) -> None:
        code, out = self._run("protocol", "verify", "--config", self._cfg(self._healthy()),
                              "--repo", str(self.root), "--liveness", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verdict"], CONFIRMED)

    def test_cli_contradicted_exit_one(self) -> None:
        cfg = self._cfg({"records": [{"id": "c", "party": "p", "type": "claim", "pins_head": "main"}]})
        code, _ = self._run("protocol", "verify", "--config", cfg, "--repo", str(self.root))
        self.assertEqual(code, 1)

    def test_cli_empty_exit_two(self) -> None:
        code, _ = self._run("protocol", "verify", "--config", self._cfg({"records": []}))
        self.assertEqual(code, 2)

    def test_ledger_feed_records_binder_derived(self) -> None:
        project = self.root / "proj"
        project.mkdir()
        code, _ = self._run("protocol", "verify", "--config", self._cfg(self._healthy()),
                            "--repo", str(self.root), "--liveness", "--ledger", "--project", str(project))
        self.assertEqual(code, 0)
        rows = read_ledger(project)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "CONFIRMED")
        self.assertEqual(rows[0]["derivation"], "binder")
        self.assertTrue(rows[0]["reproduce"])

    def test_ledger_feed_contradicted_maps_to_ledger_contradicted(self) -> None:
        project = self.root / "proj2"
        project.mkdir()
        cfg = self._cfg({"records": [{"id": "c", "party": "p", "type": "claim", "pins_head": "main"}]})
        code, _ = self._run("protocol", "verify", "--config", cfg, "--repo", str(self.root),
                            "--ledger", "--project", str(project))
        self.assertEqual(code, 1)
        rows = read_ledger(project)
        self.assertEqual(rows[0]["verdict"], "CONTRADICTED")


def _find(result: dict, check: str) -> dict:
    for f in result["findings"]:
        if f["check"] == check:
            return f
    raise AssertionError(f"no finding {check!r} in {[f['check'] for f in result['findings']]}")


if __name__ == "__main__":
    unittest.main()

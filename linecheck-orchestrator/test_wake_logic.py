"""Stdlib-only tests for the orchestrator's wake logic.

Run:  python3 -m unittest test_wake_logic -v
No third-party deps required (wake_logic imports only the stdlib).
"""
import glob
import json
import os
import unittest

from wake_logic import target_lane_for, wake_decision, WAKE_EVENT_TYPES, CLOSE_EVENT_TYPES

# Locate the real ledger by walking up from this file, if we're inside the
# emotivus-forge tree. Returns "" when not found (real-ledger tests then skip).
def _find_ledger() -> str:
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        cand = os.path.join(d, "exchange", "attention")
        if os.path.isdir(cand):
            return cand
        d = os.path.dirname(d)
    return ""

LEDGER = _find_ledger()


class TestTargetLane(unittest.TestCase):
    def test_single_recipient_wins(self):
        self.assertEqual(target_lane_for({"to": ["claude"]}), "claude")

    def test_falls_back_to_expected_response_lane(self):
        env = {"to": [], "expected_response_lane": "exchange/attention/codex"}
        self.assertEqual(target_lane_for(env), "codex")

    def test_recipient_beats_lane_path(self):
        env = {"to": ["claude"], "expected_response_lane": "exchange/attention/codex"}
        self.assertEqual(target_lane_for(env), "claude")

    def test_ambiguous_recipients_unresolved(self):
        self.assertIsNone(target_lane_for({"to": ["claude", "codex"]}))

    def test_unknown_recipient_unresolved(self):
        self.assertIsNone(target_lane_for({"to": ["general"]}))

    def test_empty_envelope_unresolved(self):
        self.assertIsNone(target_lane_for({}))


class TestWakeDecision(unittest.TestCase):
    def test_review_required_wakes_recipient(self):
        d = wake_decision({"event_type": "REVIEW_REQUIRED", "to": ["claude"]})
        self.assertEqual(d, {"action": "wake", "lane": "claude", "event_type": "REVIEW_REQUIRED"})

    def test_ack_required_wakes(self):
        self.assertEqual(wake_decision({"event_type": "ACK_REQUIRED", "to": ["codex"]})["action"], "wake")

    def test_acknowledgement_frees_baton(self):
        d = wake_decision({"event_type": "ACKNOWLEDGEMENT", "to": ["codex"]})
        self.assertEqual(d["action"], "close")

    def test_closed_frees_baton(self):
        self.assertEqual(wake_decision({"event_type": "CLOSED", "to": ["codex"]})["action"], "close")

    def test_wake_type_without_recipient_is_noop(self):
        d = wake_decision({"event_type": "REVIEW_REQUIRED", "to": ["claude", "codex"]})
        self.assertEqual(d["action"], "noop")

    def test_unknown_type_is_noop(self):
        self.assertEqual(wake_decision({"event_type": "MYSTERY", "to": ["claude"]})["action"], "noop")

    def test_wake_and_close_sets_are_disjoint(self):
        self.assertEqual(WAKE_EVENT_TYPES & CLOSE_EVENT_TYPES, set())


@unittest.skipUnless(glob.glob(os.path.join(LEDGER, "*", "*.json")),
                     "real ledger not present (running outside emotivus-forge)")
class TestAgainstRealLedger(unittest.TestCase):
    """Every published envelope must classify cleanly with a known type."""

    def _envelopes(self):
        for f in sorted(glob.glob(os.path.join(LEDGER, "*", "*.json"))):
            with open(f) as fh:
                yield f, json.load(fh)

    def test_all_event_types_known(self):
        for f, env in self._envelopes():
            et = env.get("event_type", "")
            self.assertIn(et, WAKE_EVENT_TYPES | CLOSE_EVENT_TYPES,
                          f"{f}: unknown event_type {et!r}")

    def test_recipient_matches_expected_response_lane(self):
        for f, env in self._envelopes():
            erl = (env.get("expected_response_lane") or "").rsplit("/", 1)[-1]
            if erl in ("claude", "codex"):
                self.assertEqual(target_lane_for(env), erl,
                                 f"{f}: recipient disagrees with expected_response_lane")

    def test_every_envelope_classifies(self):
        for f, env in self._envelopes():
            self.assertIn(wake_decision(env)["action"], {"wake", "close", "noop"})


if __name__ == "__main__":
    unittest.main()

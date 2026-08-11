"""Pure wake-decision logic for the LineCheck orchestrator.

Kept dependency-free (stdlib only) so it can be unit-tested without FastAPI/httpx
and reasoned about in isolation. The orchestrator imports these; all live-truth
decisions (who acts next, wake vs. baton-release) flow through here.
"""
from __future__ import annotations
from typing import Optional

LANES = ["claude", "codex"]

# Per exchange/authority/LINECHECK-CENTRAL-AI-COMMUNICATION-AUTHORITY-v1.md §4:
# these event types require the recipient to take a substantive next turn.
WAKE_EVENT_TYPES = {
    "ACTION_REQUIRED", "REVIEW_REQUIRED", "ACK_REQUIRED",
    "DECISION_REQUIRED", "CORRECTION",
}
# Receipts that END a turn — free the baton, wake no one.
CLOSE_EVENT_TYPES = {"ACKNOWLEDGEMENT", "CLOSED"}


def target_lane_for(envelope: dict) -> Optional[str]:
    """Which lane must ACT because of this envelope.

    The author lane (the path segment) is NOT the actor — the recipient is.
    Prefer the single recipient in `to`; fall back to the basename of
    `expected_response_lane` (e.g. exchange/attention/claude -> claude).
    Returns None when no single lane recipient can be resolved.
    """
    recips = [x for x in (envelope.get("to") or []) if x in LANES]
    if len(recips) == 1:
        return recips[0]
    lane_path = (envelope.get("expected_response_lane") or "").rstrip("/")
    if lane_path:
        base = lane_path.rsplit("/", 1)[-1]
        if base in LANES:
            return base
    return None


def wake_decision(envelope: dict) -> dict:
    """Classify an envelope into an action for the orchestrator.

    Returns {"action": "wake"|"close"|"noop", "lane": <lane|None>, "event_type": str}.
      * wake  -> launch `lane`, grant the turn lease.
      * close -> a receipt; free the baton, launch nothing.
      * noop  -> unknown/unaddressable; mark processed, do nothing.
    """
    etype = envelope.get("event_type", "")
    lane = target_lane_for(envelope)
    if etype in CLOSE_EVENT_TYPES:
        return {"action": "close", "lane": lane, "event_type": etype}
    if etype in WAKE_EVENT_TYPES and lane is not None:
        return {"action": "wake", "lane": lane, "event_type": etype}
    return {"action": "noop", "lane": lane, "event_type": etype}

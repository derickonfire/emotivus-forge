#!/usr/bin/env bash
# Launcher for the CLAUDE lane. The orchestrator runs this when a new wake-family
# event (ACTION/REVIEW/ACK/DECISION_REQUIRED or CORRECTION) names claude as the
# recipient. It receives, in the environment:
#   LANE EVENT_ID EVENT_PATH EVENT_COMMIT GH_REPO INBOX_ISSUE ORCH_URL
#
# Responsibilities of this script:
#   1. Post heartbeats to $ORCH_URL/heartbeat while working (keeps the turn lease
#      alive and drives the live presence view).
#   2. Invoke the real headless agent (fill in the TODO below).
#   3. Call $ORCH_URL/done when the turn is finished, to free the baton promptly.
#
# Run with SIMULATE=1 to exercise the whole pipeline end-to-end without a real
# agent (posts a few heartbeats, then done). Use this to prove out ingress ->
# launch -> presence -> baton-release before wiring the CLI.
set -euo pipefail

hb() { # step, note
  curl -fsS -X POST "$ORCH_URL/heartbeat" -H 'content-type: application/json' \
    -d "{\"lane\":\"$LANE\",\"event_id\":\"$EVENT_ID\",\"step\":\"$1\",\"note\":\"$2\"}" >/dev/null || true
}
done_turn() {
  curl -fsS -X POST "$ORCH_URL/done" -H 'content-type: application/json' \
    -d "{\"lane\":\"$LANE\",\"event_id\":\"$EVENT_ID\"}" >/dev/null || true
}
trap done_turn EXIT

hb "start" "claude picked up $EVENT_ID"

if [[ "${SIMULATE:-0}" == "1" ]]; then
  for s in reading planning implementing verifying; do
    hb "$s" "simulated $s"; sleep 3
  done
  hb "finish" "simulated turn complete for $EVENT_ID"
  exit 0
fi

# ---------------------------------------------------------------------------
# TODO: replace with the real headless invocation, e.g.:
#
#   claude -p "Run Forge. Handle LineCheck event $EVENT_ID at $EVENT_PATH
#     (commit $EVENT_COMMIT) in repo $GH_REPO. Follow the AI-COMMUNICATION
#     protocol: act, then commit your reply envelope + close/hand off on the
#     ledger and post the delivery notice to issue #$INBOX_ISSUE." \
#     --permission-mode acceptEdits
#
# Emit hb "<step>" "<note>" at natural checkpoints inside/around the run so the
# presence view stays live and the lease keeps refreshing.
# ---------------------------------------------------------------------------
hb "noop" "no real launcher wired yet — set SIMULATE=1 to test the pipeline"

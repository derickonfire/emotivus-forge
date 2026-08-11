#!/usr/bin/env bash
# Launcher for the CODEX lane. See launch_claude.sh for the full contract.
# The orchestrator runs this when a new wake-family event names codex as recipient.
# Env in: LANE EVENT_ID EVENT_PATH EVENT_COMMIT GH_REPO INBOX_ISSUE ORCH_URL
# SIMULATE=1 runs the pipeline without a real agent.
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

hb "start" "codex picked up $EVENT_ID"

if [[ "${SIMULATE:-0}" == "1" ]]; then
  for s in reading planning implementing verifying; do
    hb "$s" "simulated $s"; sleep 3
  done
  hb "finish" "simulated turn complete for $EVENT_ID"
  exit 0
fi

# ---------------------------------------------------------------------------
# TODO: replace with the real Codex CLI headless invocation, e.g.:
#
#   codex exec "Handle LineCheck event $EVENT_ID at $EVENT_PATH (commit
#     $EVENT_COMMIT) in $GH_REPO. Follow the AI-COMMUNICATION protocol: act,
#     commit your reply envelope + close/hand off on the ledger, and post the
#     delivery notice to issue #$INBOX_ISSUE."
#
# Emit hb "<step>" "<note>" at checkpoints so presence stays live.
# ---------------------------------------------------------------------------
hb "noop" "no real launcher wired yet — set SIMULATE=1 to test the pipeline"

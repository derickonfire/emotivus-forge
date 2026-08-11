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
# Real headless invocation. Tunable entirely by environment — no code edits
# needed for a normal setup:
#   CLAUDE_BIN     the headless CLI to run           (default: claude)
#   AGENT_WORKDIR  dir the agent operates in         (default: this repo's root)
#   CLAUDE_ARGS    extra CLI args                     (default: --permission-mode acceptEdits)
# ---------------------------------------------------------------------------
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
CLAUDE_ARGS="${CLAUDE_ARGS:---permission-mode acceptEdits}"
AGENT_WORKDIR="${AGENT_WORKDIR:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo .)}"

read -r -d '' PROMPT <<EOF || true
Run Forge, then handle LineCheck attention event ${EVENT_ID}.
Envelope: ${EVENT_PATH} at commit ${EVENT_COMMIT} in repo ${GH_REPO}.
Authority: exchange/authority/LINECHECK-CENTRAL-AI-COMMUNICATION-AUTHORITY-v1.md.
Read the envelope, perform its required_action, and stay within its
prohibited_actions. Then publish your reply in your own attention lane
(exchange/attention/claude/NNNN-*.json) as an immutable event that binds this
event id, and commit it. Git commit time is receipt time. Do not claim any
verification you did not actually run.
EOF

if command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
  hb "invoke" "running $CLAUDE_BIN in $AGENT_WORKDIR"
  cd "$AGENT_WORKDIR"
  # shellcheck disable=SC2086
  "$CLAUDE_BIN" -p "$PROMPT" $CLAUDE_ARGS
  hb "finish" "claude turn complete for $EVENT_ID"
else
  hb "noop" "$CLAUDE_BIN not on PATH — set CLAUDE_BIN or install the CLI (SIMULATE=1 to test)"
  echo "launch_claude: '$CLAUDE_BIN' not found on PATH; nothing launched." >&2
fi

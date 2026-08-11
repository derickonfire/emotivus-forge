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
# Real headless invocation. Tunable entirely by environment — no code edits
# needed for a normal setup:
#   CODEX_BIN      the headless CLI to run           (default: codex)
#   AGENT_WORKDIR  dir the agent operates in         (default: this repo's root)
#   CODEX_ARGS     extra CLI args                     (default: empty)
# ---------------------------------------------------------------------------
CODEX_BIN="${CODEX_BIN:-codex}"
CODEX_ARGS="${CODEX_ARGS:-}"
AGENT_WORKDIR="${AGENT_WORKDIR:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo .)}"

read -r -d '' PROMPT <<EOF || true
Handle LineCheck attention event ${EVENT_ID}.
Envelope: ${EVENT_PATH} at commit ${EVENT_COMMIT} in repo ${GH_REPO}.
Authority: exchange/authority/LINECHECK-CENTRAL-AI-COMMUNICATION-AUTHORITY-v1.md.
Read the envelope, perform its required_action, and stay within its
prohibited_actions. Then publish your reply in your own attention lane
(exchange/attention/codex/NNNN-*.json) as an immutable event that binds this
event id, and commit it. Git commit time is receipt time. Do not claim any
verification you did not actually run.
EOF

if command -v "$CODEX_BIN" >/dev/null 2>&1; then
  hb "invoke" "running $CODEX_BIN in $AGENT_WORKDIR"
  cd "$AGENT_WORKDIR"
  # shellcheck disable=SC2086
  "$CODEX_BIN" exec $CODEX_ARGS "$PROMPT"
  hb "finish" "codex turn complete for $EVENT_ID"
else
  hb "noop" "$CODEX_BIN not on PATH — set CODEX_BIN or install the CLI (SIMULATE=1 to test)"
  echo "launch_codex: '$CODEX_BIN' not found on PATH; nothing launched." >&2
fi

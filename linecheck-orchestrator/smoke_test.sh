#!/usr/bin/env bash
# One-command offline smoke test for the orchestrator.
# Starts the service, runs a SIMULATED claude turn, and shows the presence bus
# updating live — no GitHub App, no Cloudflare, no token required.
#
#   ./smoke_test.sh
#
# Proves: service health, the heartbeat/presence bus, and baton release (/done).
# (The webhook -> lease -> launch path needs a real signed delivery + token, so
#  it is exercised by the unit tests and the live R5 test, not here.)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8787}"
URL="http://127.0.0.1:${PORT}"
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "==> starting orchestrator on ${URL}"
"$PY" -m uvicorn orchestrator:app --host 127.0.0.1 --port "$PORT" >/tmp/orch-smoke.log 2>&1 &
SVC=$!
cleanup() { kill "$SVC" 2>/dev/null || true; }
trap cleanup EXIT

# wait for health
ok=""
for _ in $(seq 1 40); do
  if curl -sf "${URL}/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 0.25
done
[ -n "$ok" ] || { echo "!! service did not come up; log:"; cat /tmp/orch-smoke.log; exit 1; }

echo "==> /health"; curl -s "${URL}/health"; echo

echo "==> running a SIMULATED claude turn (heartbeats every ~3s)"
chmod +x launchers/launch_claude.sh 2>/dev/null || true
SIMULATE=1 LANE=claude EVENT_ID=smoke-1 ORCH_URL="${URL}" ./launchers/launch_claude.sh &
LAUNCH=$!

for i in $(seq 1 6); do
  sleep 2
  echo "--- presence @ ${i}0% ---"
  curl -s "${URL}/presence"; echo
done

wait "$LAUNCH" 2>/dev/null || true
echo "==> final /state (baton should be released, presence alive->recent)"
curl -s "${URL}/state"; echo
echo "==> OK — service, heartbeat/presence bus, and /done all working."

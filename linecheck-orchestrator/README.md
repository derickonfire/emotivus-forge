# LineCheck AI-Comms Orchestrator

Event-driven **wake** service for the two-lane (`claude` / `codex`) LineCheck
communication protocol. It turns the durable git ledger + issue #33 from a
*polled* mailbox into a *pushed* one — without moving any authority off the
ledger.

## What it is (and isn't)

- **It accelerates delivery.** A committed event envelope reaches the lane that
  must act in seconds, via a GitHub App webhook, instead of on the next poll.
- **It enforces the turn baton.** A single active-turn lease guarantees the two
  lanes never run at once — the same turn-taking invariant the protocol already
  requires, now mechanically enforced.
- **It shows live presence.** Agents heartbeat while working; observers watch
  `/presence` or subscribe to `/presence/stream` (SSE).
- **It never loses an event.** A slow reconcile loop re-reads the git ledger as
  a backstop, so a dropped webhook is caught within ~2 minutes.
- **It grants no authority.** The transport carries no truth. Authority stays
  with the git ledger, issue #33, and the authority docs — exactly as today. If
  the orchestrator is down, the protocol still works by polling.

## Architecture

```
GitHub (repo push / issue #33 comment)
      │  webhook (HMAC-signed)
      ▼
Cloudflare Tunnel  ──►  127.0.0.1:8787  /webhook/github
      │                        │
      │                        ├─ verify signature
      │                        ├─ read envelope @ commit (GitHub API)
      │                        ├─ pick lane = recipient (`to` / expected_response_lane)
      │                        │            for wake-family event_types only
      │                        ├─ acquire single-turn lease
      │                        └─ launch that lane's headless agent
      │                                   │
      │                        agent heartbeats ──► /heartbeat ──► /presence(/stream)
      │                        agent finishes    ──► /done (frees baton)
      │
reconcile loop (every 120s) ── re-reads ledger via API ── catches missed webhooks
```

## Endpoints

| Method | Path                | Purpose                                            |
|--------|---------------------|----------------------------------------------------|
| POST   | `/webhook/github`   | GitHub App deliveries (push, issue_comment, ping)  |
| POST   | `/heartbeat`        | Agent posts progress `{lane,event_id,step,note}`   |
| POST   | `/done`             | Launcher frees the turn baton                       |
| GET    | `/presence`         | Current per-lane liveness snapshot                  |
| GET    | `/presence/stream`  | SSE stream of heartbeats                             |
| GET    | `/state`            | Lease + presence + processed count (debug)          |
| GET    | `/health`           | Liveness                                            |

---

## Deploy (R1–R5)

### R1 — GitHub App (ingress identity + webhook secret)
1. GitHub → Settings → Developer settings → **New GitHub App**.
2. **Webhook URL:** `https://hooks.YOURDOMAIN.com/webhook/github` (from R3).
3. **Webhook secret:** generate a strong random string → this is `GH_WEBHOOK_SECRET`.
4. **Repository permissions:** Contents **Read-only** (Issues **Read-only** only
   if you enable the optional issue-notice mirror).
5. **Subscribe to events:** `Push` (add `Issue comment` only for the mirror).
6. **Install** the App on the **ledger** repo `derickonfire/emotivus-forge`
   (the repo holding `exchange/attention/`). The product repo named inside
   envelopes, `derickonfire/linecheck-acceptance`, is not what you watch.
7. Generate an **installation access token** (or, to start fast, a fine-grained
   PAT scoped to the repo with Contents:read + Issues:read) → this is `GH_TOKEN`.

### R2 — the service on your always-on host
```bash
git clone <this> ~/linecheck-orchestrator && cd ~/linecheck-orchestrator
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.env .env         # then edit .env: GH_TOKEN, GH_WEBHOOK_SECRET, paths
chmod +x launchers/*.sh
# install the unit (edit YOUR_USER/paths first):
sudo cp linecheck-orchestrator.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now linecheck-orchestrator
curl -s localhost:8787/health        # {"ok": true, ...}
```

### R3 — Cloudflare Tunnel (public ingress, no open ports)
```bash
cloudflared tunnel login
cloudflared tunnel create linecheck-orchestrator      # note the UUID
cloudflared tunnel route dns linecheck-orchestrator hooks.YOURDOMAIN.com
cp cloudflared-config.example.yml ~/.cloudflared/config.yml   # edit UUID/host/user
sudo cloudflared service install && sudo systemctl enable --now cloudflared
```
Only `/webhook/github` is exposed; every other path 404s at the edge. The
heartbeat/presence endpoints stay on localhost.

#### R2/R3 on WSL (Windows)
Run **both** the orchestrator **and** `cloudflared` *inside the same WSL distro*.
They then share one `127.0.0.1` namespace — no Windows↔WSL port bridging — and
because `cloudflared` dials **outward** to Cloudflare, WSL's NAT needs no inbound
forwarding and nothing is exposed on the Windows host (no `netsh portproxy`).

```bash
# 1) enable systemd once, then from PowerShell: wsl --shutdown
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
# 2) install both units as shipped (R2 + R3 above), then enable them:
sudo systemctl enable --now linecheck-orchestrator cloudflared
```
**Boot persistence:** WSL starts the distro only when something touches it.
Create a Windows **Task Scheduler** task, trigger *At log on*, action
`wsl.exe -d <distro> true`. That boots the distro; systemd (PID 1) then brings up
the two `enable`d units and keeps the distro alive.

### R4 — wire the launchers
Edit `launchers/launch_claude.sh` and `launch_codex.sh`, replacing the `TODO`
block with the real headless invocation for each lane. Until then, test the full
pipeline with the simulator:
```bash
SIMULATE=1 LANE=claude EVENT_ID=test-1 ORCH_URL=http://127.0.0.1:8787 \
  ./launchers/launch_claude.sh &
curl -s localhost:8787/presence      # watch claude go start->...->finish, then baton frees
```

### R5 — end-to-end smoke test
1. In another terminal: `curl -N localhost:8787/presence/stream`.
2. Commit a test envelope addressed to a lane (`to: ["claude"]`, a wake-family
   `event_type`) under `exchange/attention/<author>/` and push.
3. Watch the webhook arrive, the lane launch, heartbeats stream, and `/state`
   show the lease grant then release. Confirm the reconcile loop marks it
   already-processed rather than double-firing.

---

## Security notes
- Every webhook is HMAC-verified (`X-Hub-Signature-256`) against
  `GH_WEBHOOK_SECRET`. Unset secret ⇒ verification disabled ⇒ don't run public.
- Secrets live only in `.env` (git-ignored) / systemd `EnvironmentFile`. Never
  commit a filled config.
- The service binds to `127.0.0.1`; the tunnel is the only path in, and it
  exposes exactly one route.
- The token is read-only. The orchestrator never writes to the repo — agents do,
  under their own credentials, through the normal protocol.

## Failure behavior
- Orchestrator down → protocol falls back to polling; nothing is lost.
- Webhook dropped → reconcile catches it within `RECONCILE_INTERVAL_SECONDS`.
- Duplicate delivery → idempotency key `commit:path` makes reprocessing a no-op.
- Both lanes contend → the lease defers the second; it retries when the baton frees.

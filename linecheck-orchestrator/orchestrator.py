#!/usr/bin/env python3
"""
LineCheck AI-Comms Orchestrator
================================
Event-driven "wake" service for the two-lane (claude/codex) LineCheck comms protocol.

What it does (see LINECHECK-COMMS-UPGRADE-PLAN.md for the full design):
  * Receives GitHub App webhooks (push to the attention ledger + issue-#33 comments),
    HMAC-verified, via a Cloudflare Tunnel -> localhost.
  * On a new event envelope, determines the lane that must act next
    (the recipient in `to` / `expected_response_lane`) for wake-family event types and LAUNCHES
    that lane's headless agent — enforcing a single-active-turn lease so both lanes never
    run at once.
  * Exposes a heartbeat/presence bus (agents POST /heartbeat while working; observers read
    /presence or subscribe to /presence/stream) — this is the live "who's doing what".
  * Runs a slow reconcile loop against the durable git ledger as a rare backstop so a
    missed webhook is never lost.

The transport grants NO authority. It only accelerates delivery. Authority stays with the
git ledger + issue #33 + the authority docs, exactly as today.

Stdlib + FastAPI + httpx only. Python 3.11+ (matches Ubuntu 24.04's 3.12).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from wake_logic import LANES, wake_decision

# --------------------------------------------------------------------------- config
def _env(name: str, default: Optional[str] = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val or ""

# GH_REPO is the LEDGER repo we watch — the one that holds exchange/attention/.
# (An envelope's exact_product_repo, e.g. derickonfire/linecheck-acceptance, is a
#  field INSIDE the envelope and is NOT what the webhook watches.)
GH_REPO            = _env("GH_REPO", "derickonfire/emotivus-forge")
INBOX_ISSUE        = int(_env("INBOX_ISSUE", "0"))  # optional GitHub-issue notice mirror; 0 = disabled
ATTENTION_PREFIX   = _env("ATTENTION_PREFIX", "exchange/attention/")
GH_TOKEN           = _env("GH_TOKEN", required=False)          # App installation token or fine-grained PAT
GH_WEBHOOK_SECRET  = _env("GH_WEBHOOK_SECRET", required=False) # shared secret for HMAC verify
CLAUDE_LAUNCH_CMD  = _env("CLAUDE_LAUNCH_CMD", "")             # e.g. /home/derickonfire/linecheck-orchestrator/launchers/launch_claude.sh
CODEX_LAUNCH_CMD   = _env("CODEX_LAUNCH_CMD", "")
RECONCILE_INTERVAL = int(_env("RECONCILE_INTERVAL_SECONDS", "120"))
HEARTBEAT_STALE    = int(_env("HEARTBEAT_STALE_SECONDS", "45"))
LEASE_DEFAULT      = int(_env("LEASE_DEFAULT_SECONDS", "2100"))  # 35 min, comfortably covers a 30-min task
STATE_DIR          = Path(_env("STATE_DIR", str(Path.home() / ".linecheck-orchestrator")))
PORT               = int(_env("PORT", "8787"))
SELF_URL           = _env("SELF_URL", f"http://127.0.0.1:{PORT}")  # for launchers to post heartbeats back

STATE_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_FILE = STATE_DIR / "processed_events.json"
CURSOR_FILE    = STATE_DIR / "reconcile_cursor.json"

GH_API = "https://api.github.com"

# LANES is imported from wake_logic (single source of truth for lane names).

# --------------------------------------------------------------------------- state
class Orchestrator:
    def __init__(self) -> None:
        self.processed: set[str] = set(json.loads(PROCESSED_FILE.read_text())) if PROCESSED_FILE.exists() else set()
        self.presence: dict[str, dict[str, Any]] = {}       # lane -> latest heartbeat
        self.lease: Optional[dict[str, Any]] = None          # {"lane","event_id","expires"}
        self.lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue] = []

    # ---- idempotency
    def seen(self, key: str) -> bool:
        return key in self.processed

    def mark(self, key: str) -> None:
        self.processed.add(key)
        # keep the file bounded but generous
        if len(self.processed) > 5000:
            self.processed = set(list(self.processed)[-4000:])
        PROCESSED_FILE.write_text(json.dumps(sorted(self.processed)))

    # ---- turn lease (enforced single-active-turn baton)
    def lease_active(self) -> bool:
        return bool(self.lease and self.lease["expires"] > time.time())

    def grant_lease(self, lane: str, event_id: str, seconds: int = LEASE_DEFAULT) -> None:
        self.lease = {"lane": lane, "event_id": event_id, "expires": time.time() + seconds}
        self._log(f"lease granted -> {lane} ({event_id}) for {seconds}s")

    def release_lease(self) -> None:
        if self.lease:
            self._log(f"lease released <- {self.lease['lane']}")
        self.lease = None

    # ---- presence bus
    async def record_heartbeat(self, hb: dict[str, Any]) -> None:
        hb["received_utc"] = _now_iso()
        hb["received_ts"] = time.time()
        self.presence[hb.get("lane", "unknown")] = hb
        for q in list(self._subscribers):
            try:
                q.put_nowait(hb)
            except asyncio.QueueFull:
                pass

    def presence_view(self) -> dict[str, Any]:
        now = time.time()
        out = {}
        for lane, hb in self.presence.items():
            age = now - hb.get("received_ts", 0)
            out[lane] = {**{k: v for k, v in hb.items() if k != "received_ts"},
                         "age_seconds": round(age, 1),
                         "alive": age <= HEARTBEAT_STALE}
        return out

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    @staticmethod
    def _log(msg: str) -> None:
        print(f"[{_now_iso()}] {msg}", flush=True)


ORCH = Orchestrator()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- GitHub helpers
def _gh_headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h


async def gh_get(client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
    r = await client.get(f"{GH_API}{path}", headers=_gh_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


async def fetch_file_at_commit(client: httpx.AsyncClient, path: str, ref: str) -> Optional[dict]:
    """Fetch and JSON-parse a committed envelope at an exact ref. Returns None on non-JSON/missing."""
    try:
        data = await gh_get(client, f"/repos/{GH_REPO}/contents/{path}", params={"ref": ref})
    except httpx.HTTPStatusError:
        return None
    if isinstance(data, dict) and data.get("encoding") == "base64":
        try:
            raw = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(raw)
        except Exception:
            return None
    return None


async def commit_added_event_paths(client: httpx.AsyncClient, sha: str) -> list[str]:
    """Return attention-ledger .json files ADDED by a commit (new events only)."""
    detail = await gh_get(client, f"/repos/{GH_REPO}/commits/{sha}")
    out = []
    for f in detail.get("files", []):
        fn = f.get("filename", "")
        if f.get("status") == "added" and fn.startswith(ATTENTION_PREFIX) and fn.endswith(".json"):
            out.append(fn)
    return out


# --------------------------------------------------------------------------- core: process one event
async def process_event(client: httpx.AsyncClient, path: str, commit: str, source: str) -> dict:
    """Idempotently wake the lane that must act for the event at (path, commit)."""
    key = f"{commit}:{path}"
    async with ORCH.lock:
        if ORCH.seen(key):
            return {"status": "already_processed", "key": key}

        env = await fetch_file_at_commit(client, path, commit)
        if not env:
            return {"status": "skip_unreadable", "key": key}

        event_id = env.get("id", path)
        decision = wake_decision(env)
        etype, lane = decision["event_type"], decision["lane"]

        # Receipts (ACKNOWLEDGEMENT / CLOSED) end a turn: free the baton, no wake.
        if decision["action"] == "close":
            ORCH.release_lease()
            ORCH.mark(key)
            ORCH._log(f"event {event_id}: receipt ({etype}) — baton freed, no wake")
            return {"status": "no_wake", "event_id": event_id, "event_type": etype}

        # Anything not in the wake family, or with no resolvable recipient, is a no-op.
        if decision["action"] != "wake":
            ORCH.mark(key)
            ORCH._log(f"event {event_id}: no wake (type={etype!r}, recipient={lane})")
            return {"status": "no_wake", "event_id": event_id, "event_type": etype, "recipient": lane}

        # Enforced turn: refuse to launch a second lane while another holds an active lease.
        if ORCH.lease_active() and ORCH.lease["lane"] != lane:
            ORCH._log(f"event {event_id}: DEFERRED, lease held by {ORCH.lease['lane']}")
            # Do NOT mark processed — reconcile/next event will retry once the lease frees.
            return {"status": "deferred_lease_held", "event_id": event_id,
                    "holder": ORCH.lease["lane"], "wants": lane}

        ORCH.grant_lease(lane, event_id)
        ORCH.mark(key)
        launched = await launch_lane(lane, event_id, path, commit)
        ORCH._log(f"event {event_id} ({source}): woke {lane} -> {launched['status']}")
        return {"status": "woke", "event_id": event_id, "lane": lane, "launch": launched}


async def launch_lane(lane: str, event_id: str, event_path: str, event_commit: str) -> dict:
    cmd = CLAUDE_LAUNCH_CMD if lane == "claude" else CODEX_LAUNCH_CMD
    if not cmd:
        ORCH._log(f"[launch] no command configured for {lane}; would launch for {event_id}")
        return {"status": "no_launcher_configured", "lane": lane}
    env = {
        **os.environ,
        "LANE": lane,
        "EVENT_ID": event_id,
        "EVENT_PATH": event_path,
        "EVENT_COMMIT": event_commit,
        "GH_REPO": GH_REPO,
        "INBOX_ISSUE": str(INBOX_ISSUE),
        "ORCH_URL": SELF_URL,
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", "-lc", cmd, env=env,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        return {"status": "launched", "pid": proc.pid}
    except Exception as e:  # noqa: BLE001
        ORCH._log(f"[launch] FAILED for {lane}: {e!r}")
        return {"status": "launch_error", "error": str(e)}


# --------------------------------------------------------------------------- reconcile backstop
async def reconcile_loop() -> None:
    await asyncio.sleep(5)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await reconcile_once(client)
            except Exception as e:  # noqa: BLE001
                ORCH._log(f"[reconcile] error: {e!r}")
            await asyncio.sleep(RECONCILE_INTERVAL)


async def reconcile_once(client: httpx.AsyncClient) -> None:
    if not GH_TOKEN:
        return  # can't reach the API without a token; webhook-only mode
    params = {"sha": "main", "path": ATTENTION_PREFIX.rstrip("/"), "per_page": 20}
    commits = await gh_get(client, f"/repos/{GH_REPO}/commits", params=params)
    # oldest-first so events wake in order
    for c in reversed(commits):
        sha = c["sha"]
        for path in await commit_added_event_paths(client, sha):
            res = await process_event(client, path, sha, source="reconcile")
            if res.get("status") == "woke":
                ORCH._log(f"[reconcile] caught missed event: {res}")


# --------------------------------------------------------------------------- FastAPI app
app = FastAPI(title="LineCheck AI-Comms Orchestrator")


@app.on_event("startup")
async def _startup() -> None:
    ORCH._log(f"orchestrator up on :{PORT}  repo={GH_REPO}  reconcile={RECONCILE_INTERVAL}s")
    if not GH_WEBHOOK_SECRET:
        ORCH._log("WARNING: GH_WEBHOOK_SECRET unset — webhook signature verification DISABLED")
    if not GH_TOKEN:
        ORCH._log("WARNING: GH_TOKEN unset — cannot fetch envelopes or reconcile")
    asyncio.create_task(reconcile_loop())


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "utc": _now_iso(), "lease": ORCH.lease,
            "processed": len(ORCH.processed), "lanes": LANES}


@app.get("/state")
async def state() -> dict:
    return {"lease": ORCH.lease, "lease_active": ORCH.lease_active(),
            "presence": ORCH.presence_view(), "processed": len(ORCH.processed)}


def _verify_signature(secret: str, body: bytes, sig_header: str) -> bool:
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={mac}", sig_header)


@app.post("/webhook/github")
async def webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
) -> JSONResponse:
    body = await request.body()
    if GH_WEBHOOK_SECRET and not _verify_signature(GH_WEBHOOK_SECRET, body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="bad signature")
    payload = json.loads(body or b"{}")

    results: list[dict] = []
    async with httpx.AsyncClient() as client:
        if x_github_event == "push":
            for c in payload.get("commits", []):
                sha = c.get("id")
                for path in c.get("added", []):
                    if path.startswith(ATTENTION_PREFIX) and path.endswith(".json"):
                        results.append(await process_event(client, path, sha, source="webhook-push"))
        elif x_github_event == "issue_comment":
            issue = payload.get("issue", {})
            if issue.get("number") == INBOX_ISSUE and payload.get("action") == "created":
                # A #33 delivery notice usually accompanies a commit; reconcile latest to catch it.
                await reconcile_once(client)
                results.append({"status": "reconciled_on_comment"})
        elif x_github_event == "ping":
            results.append({"status": "pong"})

    return JSONResponse({"handled": x_github_event, "results": results})


@app.post("/heartbeat")
async def heartbeat(request: Request) -> dict:
    """Agents POST while working: {lane, event_id, step, total, note}. Off-ledger, advisory."""
    hb = await request.json()
    lane = hb.get("lane")
    if lane not in LANES:
        raise HTTPException(status_code=400, detail="unknown lane")
    await ORCH.record_heartbeat(hb)
    # a heartbeat also refreshes the lease so a live long task doesn't lose its turn
    if ORCH.lease and ORCH.lease["lane"] == lane:
        ORCH.lease["expires"] = time.time() + LEASE_DEFAULT
    return {"ok": True}


@app.post("/done")
async def done(request: Request) -> dict:
    """Launcher calls this when an agent's turn completes, to free the baton promptly."""
    body = await request.json()
    lane = body.get("lane")
    if ORCH.lease and ORCH.lease["lane"] == lane:
        ORCH.release_lease()
    return {"ok": True, "lease": ORCH.lease}


@app.get("/presence")
async def presence() -> dict:
    return ORCH.presence_view()


@app.get("/presence/stream")
async def presence_stream() -> StreamingResponse:
    q = ORCH.subscribe()

    async def gen():
        try:
            # send current snapshot first
            yield f"data: {json.dumps(ORCH.presence_view())}\n\n"
            while True:
                hb = await q.get()
                yield f"data: {json.dumps(hb)}\n\n"
        finally:
            ORCH.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import append_jsonl, read_jsonl, read_jsonl_report, utc_now
from .instance_key import get_or_create_instance_identity, sign_message
from .paths import ForgePaths


# Authority-bearing events are signed with the per-instance key so corroboration can
# tell an in-instance authorization from an imported/fabricated one. The signature is
# excluded from the canonical hash (like event_hash) so adding it does not alter the
# chain: event_hash covers the rest of the event (including key_id), and the signature
# covers event_hash.
SIGNED_KINDS = {"authority-baseline-authorized"}
_CANONICAL_EXCLUDED = {"event_hash", "signature"}


def _canonical_hash(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key not in _CANONICAL_EXCLUDED}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _event_id(kind: str, timestamp: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    return f"{kind}-{timestamp.replace('-', '').replace(':', '')[:15]}-{digest}"


def record_event(project_root: Path, kind: str, payload: dict[str, Any], *, source: str = "forge") -> dict[str, Any]:
    timestamp = utc_now()
    existing = read_jsonl(ForgePaths(project_root).ledger)
    previous_hash = _canonical_hash(existing[-1]) if existing else ""
    event = {
        "schema": 2,
        "id": _event_id(kind, timestamp, payload),
        "utc": timestamp,
        "kind": kind,
        "source": source,
        "previous_event_hash": previous_hash,
        "payload": payload,
    }
    if kind in SIGNED_KINDS:
        identity = get_or_create_instance_identity()
        if identity is not None:
            # key_id is covered by event_hash; the signature covers event_hash.
            event["key_id"] = identity["key_id"]
    event["event_hash"] = _canonical_hash(event)
    if kind in SIGNED_KINDS and event.get("key_id"):
        identity = get_or_create_instance_identity()
        if identity is not None:
            event["signature"] = sign_message(identity["secret"], event["event_hash"])
    append_jsonl(ForgePaths(project_root).ledger, event)
    return event


def read_events(project_root: Path, *, kinds: set[str] | None = None) -> list[dict[str, Any]]:
    events = read_jsonl(ForgePaths(project_root).ledger)
    if kinds is None:
        return events
    return [item for item in events if str(item.get("kind", "")) in kinds]


def verify_ledger_chain(path: Path) -> dict[str, Any]:
    rows, syntax_issues = read_jsonl_report(path)
    issues: list[dict[str, Any]] = [issue.to_dict() for issue in syntax_issues]
    previous_hash = ""
    chained = 0
    for index, row in enumerate(rows, 1):
        actual = str(row.get("event_hash", ""))
        if actual:
            chained += 1
            expected = _canonical_hash(row)
            if actual != expected:
                issues.append({"path": str(path), "line": index, "message": "ledger event hash does not match its content"})
            declared_previous = str(row.get("previous_event_hash", ""))
            if declared_previous != previous_hash:
                issues.append({"path": str(path), "line": index, "message": "ledger previous-event hash does not match the preceding record"})
        previous_hash = _canonical_hash(row)
    return {
        "schema": 1,
        "status": "BLOCKED" if issues else "HEALTHY",
        "records": len(rows),
        "chained_records": chained,
        "issues": issues,
    }

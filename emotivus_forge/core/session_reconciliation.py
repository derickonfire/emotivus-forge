from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .common import utc_now

SESSION_CONTEXT_SCHEMA = "forge-session-context/1"
_FORBIDDEN_RAW_KEYS = {"messages", "transcript", "conversation", "chat", "raw_chat", "raw_transcript"}
# G3 · P4-01 — vendor-neutral continuity. The continuity kernel stores project TRUTH,
# not model instructions. These keys carry model-specific instructions or vendor
# identity that would make the stored digest non-neutral (a different model must be
# able to consume the continuity without inheriting another model's directives).
_FORBIDDEN_INSTRUCTION_KEYS = {
    "system_prompt", "system", "instructions", "model_instructions", "persona",
    "prompt", "prompts", "tools", "functions", "model", "provider", "vendor",
}
_TOKEN = re.compile(r"[A-Za-z0-9_.:/-]+")


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in _TOKEN.findall(str(text)) if len(item) > 2}


def load_session_context(path: str | Path, *, project_root: Path | None = None) -> dict[str, Any]:
    source = Path(path).resolve()
    if project_root is not None:
        root = project_root.resolve()
        if source == root or root in source.parents:
            raise ValueError("Session context must be transient and stored outside the project tree.")
    if not source.is_file():
        raise ValueError(f"Session context file does not exist: {source}")
    raw = source.read_bytes()
    if len(raw) > 256_000:
        raise ValueError("Session context exceeds the 256 KB bounded intake limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Session context must be valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Session context must be a JSON object.")
    if payload.get("schema") != SESSION_CONTEXT_SCHEMA:
        raise ValueError(f"Session context schema must be {SESSION_CONTEXT_SCHEMA}.")
    forbidden = sorted(key for key in payload if key.lower() in _FORBIDDEN_RAW_KEYS)
    if forbidden:
        raise ValueError(
            "Session context must be a distilled digest, not a raw conversation archive; "
            f"remove: {', '.join(forbidden)}."
        )
    instruction_keys = sorted(key for key in payload if key.lower() in _FORBIDDEN_INSTRUCTION_KEYS)
    if instruction_keys:
        raise ValueError(
            "Session context stores project truth, not model instructions or vendor identity; "
            f"the continuity kernel is vendor-neutral, so remove: {', '.join(instruction_keys)}."
        )
    objective = str(payload.get("objective", "")).strip()
    requests = _strings(payload.get("requested_items", []))
    claims = _strings(payload.get("ai_claims", []))
    decisions = _strings(payload.get("decisions", []))
    rejected = _strings(payload.get("rejected_options", []))
    next_action = str(payload.get("next_action", "")).strip()
    if not any((objective, requests, claims, decisions, next_action)):
        raise ValueError("Session context must contain at least one objective, request, claim, decision, or next action.")
    return {
        "schema": 1,
        "source_path": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "objective": objective,
        "requested_items": requests[:50],
        "ai_claims": claims[:50],
        "decisions": decisions[:50],
        "rejected_options": rejected[:50],
        "next_action": next_action,
        "source_kind": str(payload.get("source_kind", "active-ai-distilled")).strip() or "active-ai-distilled",
        "raw_conversation_retained": False,
        "truth_boundary": (
            "This is a transient distilled session digest supplied by the active AI or operator. "
            "Forge does not authenticate the digest, retain raw chat, or treat AI claims as project facts. "
            "The continuity kernel is vendor-neutral: it stores project truth, not model instructions or "
            "vendor identity, so a different model can consume it without inheriting another model's directives."
        ),
    }


def _path_support(text: str, changed_paths: list[str], checked_paths: list[str]) -> dict[str, Any]:
    tokens = _tokens(text)
    changed_hits = [path for path in changed_paths if tokens & _tokens(path)]
    checked_hits = [path for path in checked_paths if tokens & _tokens(path)]
    status = "UNSUPPORTED"
    if checked_hits:
        status = "CHECKED_PATH_MATCH"
    elif changed_hits:
        status = "CHANGED_PATH_MATCH"
    return {
        "text": text,
        "status": status,
        "changed_paths": changed_hits[:12],
        "checked_paths": checked_hits[:12],
        "boundary": "Path-token alignment is orientation evidence only; it does not prove semantic completion.",
    }


def build_session_reconciliation(
    context: dict[str, Any] | None,
    *,
    changes: dict[str, Any] | None = None,
    check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    changes = changes if isinstance(changes, dict) else {}
    check = check if isinstance(check, dict) else {}
    changed_paths = [str(item) for item in changes.get("paths", []) if str(item).strip()]
    checked_paths = [str(item) for item in check.get("checked_paths", []) if str(item).strip()]
    if not context:
        return {
            "schema": 1,
            "status": "NOT_SUPPLIED",
            "objective": "",
            "request_count": 0,
            "claim_count": 0,
            "request_alignment": [],
            "claim_alignment": [],
            "conversation_review": "NOT_AVAILABLE",
            "raw_conversation_retained": False,
            "truth_boundary": "Forge reviewed project state only because no distilled session context was supplied.",
        }
    requests = [str(item) for item in context.get("requested_items", [])]
    claims = [str(item) for item in context.get("ai_claims", [])]
    request_alignment = [_path_support(item, changed_paths, checked_paths) for item in requests]
    claim_alignment = [_path_support(item, changed_paths, checked_paths) for item in claims]
    unsupported_claims = sum(1 for item in claim_alignment if item["status"] == "UNSUPPORTED")
    status = "ALIGNED"
    if unsupported_claims:
        status = "PARTIAL"
    if claims and unsupported_claims == len(claims):
        status = "UNSUPPORTED_CLAIMS"
    return {
        "schema": 1,
        "status": status,
        "objective": str(context.get("objective", "")),
        "request_count": len(requests),
        "claim_count": len(claims),
        "request_alignment": request_alignment,
        "claim_alignment": claim_alignment,
        "decisions": list(context.get("decisions", [])),
        "rejected_options": list(context.get("rejected_options", [])),
        "next_action": str(context.get("next_action", "")),
        "source_sha256": str(context.get("source_sha256", "")),
        "conversation_review": "DISTILLED_CONTEXT_REVIEWED",
        "raw_conversation_retained": False,
        "updated_utc": utc_now(),
        "truth_boundary": (
            "Forge compared a distilled session digest with changed and checked paths. "
            "AI claims remain unverified unless separate code and evidence support them."
        ),
    }


def build_forge_brief(payload: dict[str, Any]) -> dict[str, Any]:
    check = payload.get("check", {}) if isinstance(payload.get("check"), dict) else {}
    changes = payload.get("changes", {}) if isinstance(payload.get("changes"), dict) else {}
    authority = payload.get("authority_baseline", {}) if isinstance(payload.get("authority_baseline"), dict) else {}
    reconciliation = payload.get("session_reconciliation", {}) if isinstance(payload.get("session_reconciliation"), dict) else {}
    evidence = {
        "scoped_check": str(check.get("status", "NOT_RUN")),
        "native_gate": str((check.get("native_gate", {}) if isinstance(check.get("native_gate"), dict) else {}).get("status", "NOT_RUN")),
        "checked_paths": len(check.get("checked_paths", [])) if isinstance(check.get("checked_paths"), list) else 0,
        "findings": len(check.get("findings", [])) if isinstance(check.get("findings"), list) else 0,
    }
    return {
        "schema": 1,
        "mode": "development-sidecar",
        "phase": "passive",
        "active_pass": {
            "completed": True,
            "budget": "bounded-1-to-5-minute-target",
            "phases": ["identity", "continuity", "session-intent", "change-scope", "safe-checks", "reconciliation", "brief"],
        },
        "project": payload.get("project", {}),
        "objective": reconciliation.get("objective") or (payload.get("objective", {}) if isinstance(payload.get("objective"), dict) else {}).get("text", ""),
        "conversation_code_alignment": reconciliation.get("status", "NOT_SUPPLIED"),
        "changed_paths": int(changes.get("count", 0) or 0),
        "authority_status": str(authority.get("status", "NOT_ESTABLISHED")),
        "evidence": evidence,
        "confirmed_complete": [item["text"] for item in reconciliation.get("claim_alignment", []) if isinstance(item, dict) and item.get("status") == "CHECKED_PATH_MATCH"],
        "claimed_not_proven": [item["text"] for item in reconciliation.get("claim_alignment", []) if isinstance(item, dict) and item.get("status") != "CHECKED_PATH_MATCH"],
        "unexpected_changes": int(authority.get("pending_count", 0) or 0),
        "knowledge_gaps": payload.get("attention_items", [])[:8] if isinstance(payload.get("attention_items"), list) else [],
        "exact_next_action": reconciliation.get("next_action") or (payload.get("next_action", {}) if isinstance(payload.get("next_action"), dict) else {}).get("text", ""),
        "sidecar": "Passive until a meaningful checkpoint, package import, migration, unexpected mutation, Session Close, or Ship request.",
        "truth_boundary": "The Forge Brief is an orientation and reconciliation summary, not release authorization or proof of semantic completion.",
    }

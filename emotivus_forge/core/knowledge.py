from __future__ import annotations

import hashlib
import json
from typing import Any

from .common import utc_now
from .models import KnowledgeChange


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _facts(passport: dict[str, Any]) -> dict[str, dict[str, Any]]:
    identity = passport.get("identity", {}) if isinstance(passport.get("identity"), dict) else {}
    orientation = passport.get("orientation", {}) if isinstance(passport.get("orientation"), dict) else {}
    objective = passport.get("objective", {}) if isinstance(passport.get("objective"), dict) else {}
    native_gate = passport.get("native_gate", {}) if isinstance(passport.get("native_gate"), dict) else {}
    canonical = native_gate.get("canonical", {}) if isinstance(native_gate.get("canonical"), dict) else {}
    safety = passport.get("safety", {}) if isinstance(passport.get("safety"), dict) else {}
    private_candidates = safety.get("private_boundary_candidates", []) if isinstance(safety.get("private_boundary_candidates"), list) else []
    facts: dict[str, dict[str, Any]] = {}
    if identity.get("name"):
        facts["identity.name"] = {
            "label": "project identity",
            "value": identity.get("name", ""),
            "status": identity.get("status", "inferred"),
            "support": identity.get("name_source", "directory"),
        }
    stacks = orientation.get("stacks", []) if isinstance(orientation.get("stacks"), list) else []
    if stacks:
        facts["orientation.stacks"] = {
            "label": "observed technology stacks",
            "value": stacks,
            "status": "observed",
            "support": "bounded project snapshot",
        }
    if objective.get("text"):
        facts["objective.current"] = {
            "label": "current objective",
            "value": objective.get("text", ""),
            "status": objective.get("status", "unknown"),
            "support": objective.get("source", ""),
        }
    if canonical:
        facts["native_gate.canonical"] = {
            "label": "canonical native gate",
            "value": canonical.get("source", ""),
            "status": "observed",
            "support": canonical.get("fingerprint", ""),
        }
    if private_candidates:
        facts["safety.private_boundaries"] = {
            "label": "private-boundary candidates",
            "value": sorted(str(item) for item in private_candidates),
            "status": "observed",
            "support": "placeholder-aware bounded filename scan",
        }
    return facts


def update_knowledge_index(existing_passport: dict[str, Any], current_passport: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    previous_index = existing_passport.get("knowledge_index", {}) if isinstance(existing_passport.get("knowledge_index"), dict) else {}
    current_facts = _facts(current_passport)
    now = utc_now()
    index: dict[str, Any] = {}
    added: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []

    for key, fact in current_facts.items():
        value = fact.get("value")
        fingerprint = _fingerprint({"value": value, "support": fact.get("support", "")})
        previous = previous_index.get(key, {}) if isinstance(previous_index.get(key), dict) else {}
        record = {
            "key": key,
            "label": fact.get("label", key),
            "value": value,
            "status": fact.get("status", "observed"),
            "support": fact.get("support", ""),
            "support_fingerprint": fingerprint,
            "first_seen_utc": previous.get("first_seen_utc", now),
            "last_seen_utc": now,
        }
        index[key] = record
        if not previous:
            if value not in ("", [], None):
                added.append(KnowledgeChange(
                    key=key,
                    label=str(record["label"]),
                    status="added",
                    current=value,
                    reason="Forge observed this project fact for the first time.",
                ).to_dict())
        elif previous.get("support_fingerprint") != fingerprint:
            changed.append(KnowledgeChange(
                key=key,
                label=str(record["label"]),
                status="changed",
                previous=previous.get("value"),
                current=value,
                reason="The supporting project evidence changed.",
            ).to_dict())

    for key, previous in previous_index.items():
        if key in current_facts or not isinstance(previous, dict):
            continue
        stale_record = dict(previous)
        stale_record["status"] = "stale"
        stale_record["stale_utc"] = now
        stale_record["stale_reason"] = "The supporting fact was not present in the current bounded observation."
        index[key] = stale_record
        stale.append(KnowledgeChange(
            key=key,
            label=str(previous.get("label", key)),
            status="stale",
            previous=previous.get("value"),
            reason=str(stale_record["stale_reason"]),
        ).to_dict())

    delta = {
        "schema": 1,
        "generated_utc": now,
        "added": added,
        "changed": changed,
        "stale": stale,
        "meaningful_count": len(added) + len(changed) + len(stale),
        "boundary": "Only bounded, supported project facts are compared; absence marks a fact stale rather than false.",
    }
    return index, delta


def summarize_delta(delta: dict[str, Any]) -> str:
    added = len(delta.get("added", [])) if isinstance(delta.get("added"), list) else 0
    changed = len(delta.get("changed", [])) if isinstance(delta.get("changed"), list) else 0
    stale = len(delta.get("stale", [])) if isinstance(delta.get("stale"), list) else 0
    parts: list[str] = []
    if added:
        parts.append(f"learned {added} new project fact{'s' if added != 1 else ''}")
    if changed:
        parts.append(f"updated {changed} supported fact{'s' if changed != 1 else ''}")
    if stale:
        parts.append(f"marked {stale} fact{'s' if stale != 1 else ''} stale")
    return ", ".join(parts)

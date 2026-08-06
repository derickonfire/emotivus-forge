from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .changes import compare_snapshots, snapshot_fingerprint
from .common import utc_now
from .ledger import read_events, record_event, verify_ledger_chain
from .orientation import build_snapshot
from .paths import ForgePaths
from .state import load_settings, load_state, save_state


TRUTH_BOUNDARY = (
    "Forge binds a project-declared authority record to the bounded bytes and metadata present in the project snapshot. "
    "It does not authenticate a human identity, prove authorship, identify which process changed a file, or establish that "
    "the authority substantively reviewed every behavior. A bounded snapshot may rely on size and modification time for "
    "files outside the configured hash budgets; only an exact-strength baseline is eligible for the authority-bound Ship claim."
)


def snapshot_strength(snapshot: dict[str, Any]) -> dict[str, Any]:
    files = snapshot.get("files", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(files, dict):
        files = {}
    unhashed = sorted(
        str(path) for path, item in files.items()
        if not isinstance(item, dict) or not str(item.get("sha256", "")).strip()
    )
    truncated = bool(snapshot.get("truncated")) if isinstance(snapshot, dict) else True
    exact = not truncated and not unhashed
    return {
        "status": "exact" if exact else "bounded",
        "exact": exact,
        "truncated": truncated,
        "file_count": len(files),
        "unhashed_count": len(unhashed),
        "unhashed_paths": unhashed[:50],
        "truth_boundary": (
            "Exact means every observed project file was included and SHA-256 hashed. "
            "Bounded means at least one file was outside the scan or hash budget."
        ),
    }


def _empty_assessment(current_snapshot: dict[str, Any]) -> dict[str, Any]:
    current_strength = snapshot_strength(current_snapshot)
    return {
        "schema": 1,
        "status": "NOT_ESTABLISHED",
        "baseline_id": "",
        "authority": "",
        "reason": "No explicit project-authority baseline has been recorded.",
        "current_fingerprint": snapshot_fingerprint(current_snapshot),
        "baseline_fingerprint": "",
        "pending_count": 0,
        "pending_paths": [],
        "changes": {"status": "unknown", "count": 0, "paths": [], "added": [], "modified": [], "deleted": []},
        "baseline_strength": {"status": "not-established", "exact": False, "truncated": False, "file_count": 0, "unhashed_count": 0, "unhashed_paths": []},
        "current_strength": current_strength,
        "release_eligible": False,
        "quarantined": True,
        "next_action": "Review the current tree, then record an explicit authority baseline using the exact current fingerprint.",
        "truth_boundary": TRUTH_BOUNDARY,
    }


def _corroborate_baseline(project_root: Path | None, record: dict[str, Any]) -> dict[str, Any]:
    """Tie an at-rest 'active' authority baseline to a chain-verified authorization
    event in this instance's own ledger. An imported or hand-edited state can carry
    an internally-consistent baseline; without a matching, chain-verified
    authorization event, Forge must not assert it as an established authority. This
    does not authenticate a human identity (see TRUTH_BOUNDARY) — it corroborates
    that the authorization happened in this instance's tamper-evident history."""
    if project_root is None:
        return {"corroborated": None, "reason": "authorization ledger not consulted (no project context)"}
    baseline_id = str(record.get("baseline_id", "")).strip()
    fingerprint = str(record.get("snapshot_fingerprint", "")).strip()
    chain = verify_ledger_chain(ForgePaths(project_root).ledger)
    if str(chain.get("status", "")) != "HEALTHY":
        return {"corroborated": False, "reason": f"the authorization ledger chain is not verifiable ({len(chain.get('issues', []))} integrity issue(s))"}
    if not baseline_id:
        return {"corroborated": False, "reason": "the baseline record carries no baseline_id to corroborate"}
    for event in read_events(project_root, kinds={"authority-baseline-authorized"}):
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        if str(payload.get("baseline_id", "")) == baseline_id and str(payload.get("snapshot_fingerprint", "")) == fingerprint:
            return {"corroborated": True, "reason": "corroborated by a chain-verified authorization event in this instance's ledger", "authorized_utc": str(event.get("utc", ""))}
    return {"corroborated": False, "reason": "no chain-verified authorization event in this instance's ledger matches this baseline; it was imported or recorded outside this instance"}


def assess_authority_baseline(
    state: dict[str, Any],
    current_snapshot: dict[str, Any],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    record = state.get("authority_baseline", {}) if isinstance(state, dict) else {}
    if not isinstance(record, dict) or str(record.get("status", "")) != "active":
        return _empty_assessment(current_snapshot)

    stored_snapshot = record.get("snapshot", {}) if isinstance(record.get("snapshot"), dict) else {}
    recorded_fingerprint = str(record.get("snapshot_fingerprint", "")).strip()
    calculated_fingerprint = snapshot_fingerprint(stored_snapshot)
    current_fingerprint = snapshot_fingerprint(current_snapshot)
    baseline_strength = snapshot_strength(stored_snapshot)
    current_strength = snapshot_strength(current_snapshot)

    if not recorded_fingerprint or recorded_fingerprint != calculated_fingerprint:
        return {
            "schema": 1,
            "status": "CONTRADICTED",
            "baseline_id": str(record.get("baseline_id", "")),
            "authority": str(record.get("authority", "")),
            "reason": "The stored authority-baseline snapshot no longer matches its recorded fingerprint.",
            "current_fingerprint": current_fingerprint,
            "baseline_fingerprint": recorded_fingerprint,
            "pending_count": 0,
            "pending_paths": [],
            "changes": {"status": "unknown", "count": 0, "paths": [], "added": [], "modified": [], "deleted": []},
            "baseline_strength": baseline_strength,
            "current_strength": current_strength,
            "release_eligible": False,
            "quarantined": True,
            "next_action": "Preserve the current state and investigate authority-baseline state integrity before authorizing any candidate.",
            "truth_boundary": TRUTH_BOUNDARY,
        }

    corroboration = _corroborate_baseline(project_root, record)
    if corroboration.get("corroborated") is False:
        return {
            "schema": 1,
            "status": "UNCORROBORATED",
            "baseline_id": str(record.get("baseline_id", "")),
            "authority": str(record.get("authority", "")),
            "authority_source": str(record.get("authority_source", "project-declared")),
            "authorized_utc": str(record.get("authorized_utc", "")),
            "reason": f"An 'active' authority baseline is on record, but {corroboration.get('reason', 'it could not be corroborated')}. Forge does not assert it as an established authority.",
            "authorization_reason": str(record.get("reason", "")),
            "current_fingerprint": current_fingerprint,
            "baseline_fingerprint": recorded_fingerprint,
            "pending_count": 0,
            "pending_paths": [],
            "changes": {"status": "unknown", "count": 0, "paths": [], "added": [], "modified": [], "deleted": [], "unverified": []},
            "baseline_strength": baseline_strength,
            "current_strength": current_strength,
            "release_eligible": False,
            "quarantined": True,
            "corroboration": corroboration,
            "next_action": "Re-establish authority in this instance: review the current tree and record an explicit authority baseline with --authorize-baseline against the exact current fingerprint. An imported baseline is not authority here.",
            "truth_boundary": TRUTH_BOUNDARY,
        }

    changes = compare_snapshots(stored_snapshot, current_snapshot)
    current = changes.get("count", 0) == 0
    status = "CURRENT" if current else "QUARANTINED"
    release_eligible = bool(current and baseline_strength.get("exact") and current_strength.get("exact"))
    # A count of 0 only proves "unchanged" for files compared by hash. When some
    # files were compared by size+mtime alone, the match is bounded, not proven.
    unverified_paths = list(changes.get("unverified", []))
    change_confidence = "bounded" if unverified_paths else "high"
    if current and unverified_paths:
        reason = (
            f"The current tree matches the explicit authority baseline for all byte-verified files; "
            f"{len(unverified_paths)} file(s) were compared by size and modification time only and are not byte-verified."
        )
    elif current:
        reason = "The current project tree matches the explicit authority baseline."
    else:
        reason = f"{changes.get('count', 0)} path(s) differ from the explicit authority baseline and remain quarantined from authority claims."
    next_action = (
        "Run Check and explicitly checkpoint this unchanged authority-bound tree before Ship."
        if current
        else "Review the quarantined paths, run the required verification, and record a new exact-fingerprint authority baseline only after project-authority approval."
    )
    return {
        "schema": 1,
        "status": status,
        "baseline_id": str(record.get("baseline_id", "")),
        "authority": str(record.get("authority", "")),
        "authority_source": str(record.get("authority_source", "project-declared")),
        "authorized_utc": str(record.get("authorized_utc", "")),
        "reason": reason,
        "authorization_reason": str(record.get("reason", "")),
        "current_fingerprint": current_fingerprint,
        "baseline_fingerprint": recorded_fingerprint,
        "pending_count": int(changes.get("count", 0) or 0),
        "pending_paths": list(changes.get("paths", [])),
        "changes": changes,
        "change_confidence": change_confidence,
        "unverified_paths": unverified_paths[:50],
        "baseline_strength": baseline_strength,
        "current_strength": current_strength,
        "release_eligible": release_eligible,
        "quarantined": not current,
        "corroboration": corroboration,
        "next_action": next_action,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def authorize_current_baseline(
    project_root: Path,
    forge_root: Path,
    *,
    expected_fingerprint: str,
    authority: str,
    reason: str,
    authority_source: str = "project-declared",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    expected_fingerprint = str(expected_fingerprint).strip().lower()
    authority = str(authority).strip()
    reason = str(reason).strip()
    authority_source = str(authority_source).strip() or "project-declared"
    if len(expected_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in expected_fingerprint):
        raise ValueError("--authorize-baseline requires the exact 64-character SHA-256 snapshot fingerprint reported by Check or Resume.")
    if not authority:
        raise ValueError("Baseline authorization requires a non-empty authority.")
    if not reason:
        raise ValueError("Baseline authorization requires a durable reason describing what was reviewed and accepted.")

    settings = load_settings(project_root)
    state = load_state(project_root)
    current_snapshot = build_snapshot(
        project_root,
        forge_root,
        max_files=int(settings.get("adoption_file_budget", 5000)),
        hash_file_limit=int(settings.get("hash_file_limit_bytes", 1_000_000)),
        hash_total_budget=int(settings.get("hash_total_budget_bytes", 8_000_000)),
    )
    actual_fingerprint = snapshot_fingerprint(current_snapshot)
    if actual_fingerprint != expected_fingerprint:
        raise ValueError(
            "The project tree changed after the fingerprint was reviewed; baseline authorization was not recorded. "
            f"Expected {expected_fingerprint}, observed {actual_fingerprint}."
        )

    previous = state.get("authority_baseline", {}) if isinstance(state.get("authority_baseline"), dict) else {}
    previous_snapshot = previous.get("snapshot", {}) if str(previous.get("status", "")) == "active" and isinstance(previous.get("snapshot"), dict) else {}
    accepted_changes = compare_snapshots(previous_snapshot, current_snapshot) if previous_snapshot else {
        "status": "initial-baseline",
        "count": int(current_snapshot.get("file_count", 0) or 0),
        "paths": sorted(current_snapshot.get("files", {})) if isinstance(current_snapshot.get("files"), dict) else [],
        "added": sorted(current_snapshot.get("files", {})) if isinstance(current_snapshot.get("files"), dict) else [],
        "modified": [],
        "deleted": [],
    }
    authorized_utc = utc_now()
    baseline_id = hashlib.sha256(
        json.dumps(
            {
                "fingerprint": actual_fingerprint,
                "authority": authority,
                "reason": reason,
                "authorized_utc": authorized_utc,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]
    strength = snapshot_strength(current_snapshot)
    record = {
        "schema": 1,
        "status": "active",
        "baseline_id": baseline_id,
        "authorized_utc": authorized_utc,
        "authority": authority,
        "authority_source": authority_source,
        "reason": reason,
        "snapshot_fingerprint": actual_fingerprint,
        "snapshot": current_snapshot,
        "strength": strength,
        "supersedes_baseline_id": str(previous.get("baseline_id", "")),
        "accepted_changes": accepted_changes,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    state["authority_baseline"] = record
    # Authorization establishes the current tree as the new observed comparison point, but it does not
    # preserve any earlier passing Check as a candidate checkpoint. The exact tree must be checked again.
    state["snapshot"] = current_snapshot
    last_check = state.get("last_check", {}) if isinstance(state.get("last_check"), dict) else {}
    if last_check:
        last_check = dict(last_check)
        last_check["checkpointed"] = False
        last_check["authority_current"] = False
        last_check["authority_revalidation_required"] = True
        state["last_check"] = last_check
    state["last_operation"] = "authorize-baseline"
    save_state(project_root, state)
    record_event(project_root, "authority-baseline-authorized", {
        "baseline_id": baseline_id,
        "authority": authority,
        "authority_source": authority_source,
        "reason": reason,
        "snapshot_fingerprint": actual_fingerprint,
        "strength": strength,
        "accepted_change_count": accepted_changes.get("count", 0),
        "accepted_paths": accepted_changes.get("paths", []),
        "supersedes_baseline_id": str(previous.get("baseline_id", "")),
        "truth_boundary": TRUTH_BOUNDARY,
    })
    return {
        "schema": 1,
        "status": "AUTHORIZED",
        "baseline_id": baseline_id,
        "authority": authority,
        "authority_source": authority_source,
        "reason": reason,
        "snapshot_fingerprint": actual_fingerprint,
        "strength": strength,
        "accepted_changes": accepted_changes,
        "checkpoint_revalidation_required": True,
        "next_action": "Run Check --checkpoint against the unchanged authority-bound tree before relying on candidate or Ship claims.",
        "truth_boundary": TRUTH_BOUNDARY,
    }

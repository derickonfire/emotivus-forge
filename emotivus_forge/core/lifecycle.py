from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .instance_key import classify_signature
from .ledger import read_events, record_event

LIFECYCLE_STATES = (
    "proposed",
    "active",
    "approval-required",
    "retired",
)

# G3 · P4-03 — explicit component-evolution dispositions. A newer model may retain,
# fold, freeze, retire, or replace a component; the transition is recorded as an
# append-only, chain-verified ledger event so the evolution is auditable.
LIFECYCLE_DISPOSITIONS = ("retain", "fold", "freeze", "retire", "replace")

LIFECYCLE_TRANSITION_TRUTH_BOUNDARY = (
    "A lifecycle transition records a project-authority-declared disposition of a named "
    "component (retain, fold, freeze, retire, replace) with a durable reason. It is an "
    "auditable evolution record, not proof that the successor is correct or that the "
    "declared invariants were actually preserved — invariant verification is a separate step. "
    "A transition is 'instance-bound' only when its event is signed by a key this instance "
    "trusts; an unsigned or imported transition is 'self-consistent' and is not asserted as "
    "authored in this instance."
)


def record_lifecycle_transition(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    """Record an explicit, auditable component lifecycle transition to the ledger."""
    from .lineage import _load_contract  # lazy: lineage imports lifecycle

    raw, _source, relative = _load_contract(project_root, forge_root, source_path, "Lifecycle transition contract")
    if raw.get("schema") != 1:
        raise ValueError("Lifecycle transition contract must use schema 1.")
    component = str(raw.get("component", "")).strip()
    if not component:
        raise ValueError("Lifecycle transition requires a component.")
    disposition = str(raw.get("disposition", "")).strip().lower()
    if disposition not in LIFECYCLE_DISPOSITIONS:
        raise ValueError(f"Lifecycle disposition must be one of: {', '.join(LIFECYCLE_DISPOSITIONS)}.")
    authority = str(raw.get("authority", "owner")).strip() or "owner"
    reason = str(raw.get("reason", "")).strip()
    if not reason:
        raise ValueError("Lifecycle transition requires a durable reason.")
    successor = str(raw.get("successor", "")).strip()
    if disposition in {"fold", "replace"} and not successor:
        raise ValueError(f"A '{disposition}' transition requires a successor component.")
    preserved = [str(item).strip() for item in raw.get("preserved_invariants", []) if str(item).strip()] if isinstance(raw.get("preserved_invariants"), list) else []
    if disposition == "replace" and not preserved:
        raise ValueError("A 'replace' transition must record the invariants that must be preserved.")
    invariant_checks: list[dict[str, str]] = []
    raw_checks = raw.get("invariant_checks", [])
    if raw_checks:
        if not isinstance(raw_checks, list):
            raise ValueError("invariant_checks must be a list of {subject, required_truth_state} objects.")
        for item in raw_checks:
            if not isinstance(item, dict):
                raise ValueError("Each invariant check must be a {subject, required_truth_state} object.")
            subject = str(item.get("subject", "")).strip()
            required = str(item.get("required_truth_state", "")).strip().upper()
            if not subject or not required:
                raise ValueError("Each invariant check needs a non-empty subject and required_truth_state.")
            invariant_checks.append({"subject": subject, "required_truth_state": required})
    event = record_event(project_root, "component-lifecycle-transition", {
        "component": component,
        "disposition": disposition,
        "authority": authority,
        "reason": reason[:500],
        "successor": successor,
        "preserved_invariants": preserved[:50],
        "invariant_checks": invariant_checks[:50],
        "contract_source": relative,
    }, source=authority)
    return {
        "schema": 1,
        "component": component,
        "disposition": disposition,
        "successor": successor,
        "event_id": str(event.get("id", "")),
        "truth_boundary": LIFECYCLE_TRANSITION_TRUTH_BOUNDARY,
    }


LIFECYCLE_INVARIANT_TRUTH_BOUNDARY = (
    "Invariant verification checks that each declared invariant's referenced scoped-Check "
    "subject still holds its required truth-state after a replacement. It verifies only the "
    "structured checks a replace declared against Forge-observable truth; free-text invariants "
    "are recorded but not verified. PRESERVED means the referenced truth still holds, not that "
    "the replacement is correct or complete."
)


def verify_lifecycle_invariants(truth_records: list[dict[str, Any]], project_root: Path) -> dict[str, Any]:
    """Verify each replace transition's structured invariant_checks against current truth.

    A newer model may replace an obsolete component; Forge verifies the invariants the
    replace declared as checkable (subject + required truth-state) against the current
    scoped-Check truth records, and reports preserved vs violated. Free-text invariants
    are recorded but not verified.
    """
    states: dict[str, str] = {}
    for record in truth_records:
        if isinstance(record, dict):
            states[str(record.get("subject", ""))] = str(record.get("truth_state", ""))
    components: dict[str, dict[str, Any]] = {}
    violated_total = 0
    verified_total = 0
    for event in read_events(project_root, kinds={"component-lifecycle-transition"}):
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        checks = payload.get("invariant_checks", []) if isinstance(payload.get("invariant_checks"), list) else []
        if not checks:
            continue
        preserved: list[dict[str, str]] = []
        violated: list[dict[str, str]] = []
        for check in checks:
            subject = str(check.get("subject", ""))
            required = str(check.get("required_truth_state", ""))
            actual = states.get(subject, "ABSENT")
            if actual == required:
                preserved.append({"subject": subject, "truth_state": actual})
            else:
                violated.append({"subject": subject, "required": required, "actual": actual})
        verified_total += len(preserved) + len(violated)
        violated_total += len(violated)
        components[str(payload.get("component", ""))] = {
            "disposition": str(payload.get("disposition", "")),
            "preserved": preserved,
            "violated": violated,
            "unverified_freetext": [str(i) for i in payload.get("preserved_invariants", []) if str(i)],
        }
    status = "NONE" if not components else "VIOLATED" if violated_total else "PRESERVED"
    return {
        "schema": 1,
        "status": status,
        "verified_check_count": verified_total,
        "violated_count": violated_total,
        "components": components,
        "truth_boundary": LIFECYCLE_INVARIANT_TRUTH_BOUNDARY,
    }


def lifecycle_transition_summary(project_root: Path) -> dict[str, Any]:
    """Audit view of recorded component lifecycle transitions, latest per component.

    Each transition is authority-declared, so like authority and provenance it is bound
    to this instance's key: a transition whose event is not signed by a trusted key
    (an unsigned legacy or an imported/fabricated one) is labeled ``self-consistent``,
    never counted as an authentic in-instance record without that label.
    """
    by_disposition: dict[str, int] = {}
    by_binding: dict[str, int] = {}
    components: dict[str, dict[str, Any]] = {}
    events = read_events(project_root, kinds={"component-lifecycle-transition"})
    for event in events:
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        disposition = str(payload.get("disposition", ""))
        by_disposition[disposition] = by_disposition.get(disposition, 0) + 1
        binding = classify_signature(
            str(event.get("event_hash", "")),
            str(event.get("key_id", "")),
            str(event.get("signature", "")),
        )
        binding = "instance-bound" if binding == "instance-bound" else "self-consistent"
        by_binding[binding] = by_binding.get(binding, 0) + 1
        components[str(payload.get("component", ""))] = {
            "disposition": disposition,
            "successor": str(payload.get("successor", "")),
            "binding": binding,
            "utc": str(event.get("utc", "")),
        }
    return {
        "schema": 1,
        "transition_count": len(events),
        "instance_bound_count": by_binding.get("instance-bound", 0),
        "self_consistent_count": by_binding.get("self-consistent", 0),
        "by_disposition": by_disposition,
        "by_binding": by_binding,
        "components": components,
        "truth_boundary": LIFECYCLE_TRANSITION_TRUTH_BOUNDARY,
    }


def fingerprint_bound_status(
    project_root: Path,
    record: dict[str, Any],
    *,
    active_status: str = "active",
    changed_status: str = "approval-required",
    source_key: str = "contract_source",
    fingerprint_key: str = "source_fingerprint",
    missing_reason: str = "The project-owned source is missing.",
    changed_reason: str = "The project-owned source changed after authority approval.",
) -> dict[str, Any]:
    """Return a lifecycle view without mutating the durable record.

    Capabilities, guardrails, and field trials all use the same project-owned,
    fingerprint-bound lifecycle. A changed source never remains silently active.
    """
    result = dict(record)
    current = str(result.get("status", "proposed"))
    if current != active_status:
        normalized = "retired" if current == "retired" else "approval-required" if current in {"reactivation-required", "rerecord-required", "reapproval-required", "approval-required"} else current
        result.setdefault("lifecycle_status", normalized)
        return result
    source = str(result.get(source_key, "")).strip()
    path = project_root.resolve() / source
    if not source or not path.is_file() or path.is_symlink():
        result["status"] = changed_status
        result["lifecycle_status"] = "approval-required"
        result["reason"] = missing_reason
        return result
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != str(result.get(fingerprint_key, "")):
        result["status"] = changed_status
        result["lifecycle_status"] = "approval-required"
        result["reason"] = changed_reason
        result["current_source_fingerprint"] = actual
        return result
    result["lifecycle_status"] = "active"
    return result


def lifecycle_summary(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    attention: list[dict[str, Any]] = []
    for identifier, record in sorted(records.items()):
        status = str(record.get("lifecycle_status", record.get("status", "proposed")))
        counts[status] = counts.get(status, 0) + 1
        if status == "approval-required":
            attention.append({
                "id": identifier,
                "status": status,
                "reason": str(record.get("reason", "Project authority must approve the current source again.")),
            })
    return {
        "schema": 1,
        "counts": counts,
        "attention": attention,
        "truth_boundary": (
            "Lifecycle state describes authority and source currency. It does not prove the contract is correct or complete."
        ),
    }

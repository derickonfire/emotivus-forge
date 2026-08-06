from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

LIFECYCLE_STATES = (
    "proposed",
    "active",
    "approval-required",
    "retired",
)


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

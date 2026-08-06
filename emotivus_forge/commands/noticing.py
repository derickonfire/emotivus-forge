from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.knowledge import summarize_delta
from ..core.notices import issue_notice, silent_notice


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def attach_adopt_notice(payload: dict[str, Any], project_root: Path, actions: list[str] | None = None) -> dict[str, Any]:
    actions = [str(item).strip() for item in (actions or []) if str(item).strip()]
    delta = payload.get("knowledge_delta", {}) if isinstance(payload.get("knowledge_delta"), dict) else {}
    delta_summary = summarize_delta(delta)
    clauses: list[str] = []
    if delta_summary:
        clauses.append(delta_summary)
    if actions:
        clauses.append("recorded " + ", ".join(actions[:4]))
    if not clauses:
        payload["ai_notice"] = silent_notice(category="adopt")
        return payload
    summary = "; ".join(clauses).capitalize() + "."
    payload["ai_notice"] = issue_notice(
        project_root,
        level="notice",
        summary=summary,
        category="adopt",
        event_key=_stable({"delta": delta, "actions": actions}),
        details={"knowledge_delta": delta, "actions": actions},
    )
    return payload


def attach_resume_notice(payload: dict[str, Any], project_root: Path) -> dict[str, Any]:
    items = [item for item in payload.get("attention_items", []) if isinstance(item, dict) and str(item.get("message", "")).strip()]
    reasons = [str(item.get("message", "")).strip() for item in items]
    if not reasons:
        payload["ai_notice"] = silent_notice(category="resume")
        return payload
    counts = payload.get("attention_counts", {}) if isinstance(payload.get("attention_counts"), dict) else {}
    first = items[0]
    summary = reasons[0]
    remaining = len(reasons) - 1
    if remaining:
        summary += (
            f" {counts.get('blocker', 0)} blocker(s) and {counts.get('warning', 0)} warning(s) remain."
            if counts else f" {remaining} additional attention item(s) remain."
        )
    payload["ai_notice"] = issue_notice(
        project_root,
        level="blocker" if str(first.get("severity")) == "blocker" else "warning",
        summary=summary,
        category="resume",
        event_key=_stable({"items": items, "next_action": payload.get("next_action", {})}),
        details={"attention_count": len(reasons), "attention_counts": counts},
    )
    return payload


def attach_check_notice(payload: dict[str, Any], project_root: Path) -> dict[str, Any]:
    status = str(payload.get("status", "UNKNOWN"))
    changes = payload.get("changes", {}) if isinstance(payload.get("changes"), dict) else {}
    plan = payload.get("check_plan", {}) if isinstance(payload.get("check_plan"), dict) else {}
    findings = [item for item in payload.get("findings", []) if isinstance(item, dict)]
    guardrails = payload.get("guardrails", {}) if isinstance(payload.get("guardrails"), dict) else {}
    provenance = payload.get("artifact_provenance", {}) if isinstance(payload.get("artifact_provenance"), dict) else {}
    session = payload.get("session_close", {}) if isinstance(payload.get("session_close"), dict) else {}
    change_id = str(payload.get("change_ledger", {}).get("id", "")) if isinstance(payload.get("change_ledger"), dict) else ""

    if status != "PASS":
        partial = [item for item in guardrails.get("evaluations", []) if isinstance(item, dict) and item.get("status") == "FAIL"]
        if partial:
            missing = [
                str(row.get("id", ""))
                for item in partial
                for row in item.get("missing_surfaces", [])
                if isinstance(row, dict) and str(row.get("id", ""))
            ]
            summary = "Blocked unsafe partial work"
            if missing:
                summary += "; missing " + ", ".join(dict.fromkeys(missing))
            summary += "."
        else:
            summary = f"Scoped Check failed with {len(findings)} finding(s) across {changes.get('count', 0)} changed path(s)."
        level = "blocker"
    elif provenance.get("unregistered_deliverables"):
        count = len(provenance.get("unregistered_deliverables", []))
        summary = f"Found {count} deliverable-shaped artifact(s) outside registered provenance; delivery assurance is unavailable."
        level = "warning"
    elif session:
        bundle = payload.get("continuity_bundle", {}) if isinstance(payload.get("continuity_bundle"), dict) else {}
        summary = (
            f"Closed the session after checking {changes.get('count', 0)} changed path(s); "
            f"preserved the next action: {session.get('next_action', {}).get('text', '')}"
        ).rstrip()
        if bundle.get("status") == "READY":
            summary += "; exported a portable continuity companion"
        summary += "."
        level = "notice"
    elif changes.get("count", 0):
        summary = (
            f"Checked {changes.get('count', 0)} changed path(s) with the {plan.get('profile', 'scoped')} profile; "
            "runtime, deployment, and release assurance were not proven."
        )
        level = "notice"
    else:
        payload["ai_notice"] = silent_notice(category="check")
        return payload

    payload["ai_notice"] = issue_notice(
        project_root,
        level=level,
        summary=summary,
        category="check",
        event_key=_stable({
            "change_id": change_id,
            "status": status,
            "findings": [(item.get("check"), item.get("path"), item.get("line"), item.get("message")) for item in findings],
            "session_event": session.get("event_id", ""),
        }),
        details={
            "change_id": change_id,
            "changed_paths": changes.get("count", 0),
            "profile": plan.get("profile", ""),
            "finding_count": len(findings),
        },
    )
    return payload


def attach_run_notice(payload: dict[str, Any], project_root: Path | None) -> dict[str, Any]:
    if payload.get("status") == "BLOCKED":
        reason = str(payload.get("reason", "Forge blocked the operation."))
        payload["ai_notice"] = issue_notice(
            project_root,
            level="blocker",
            summary=reason,
            category="startup",
            event_key=_stable({"reason": reason, "action": payload.get("action", "")}),
            details={"action": payload.get("action", "")},
            persist=project_root is not None and (project_root / ".forge").is_dir(),
        )
        return payload
    if payload.get("status") == "NEEDS_PROJECT":
        payload["ai_notice"] = {
            "schema": 1,
            "id": "notice-needs-project",
            "level": "warning",
            "summary": str(payload.get("reason", "No project was found.")),
            "category": "startup",
            "speak": True,
            "repeated": False,
            "mode": "standard",
            "details": {},
        }
        return payload
    if payload.get("check") and isinstance(payload.get("check"), dict):
        check = payload["check"]
        notice = check.get("ai_notice")
        if isinstance(notice, dict):
            payload["ai_notice"] = notice
            return payload
        attach_check_notice(check, project_root or Path(str(payload.get("project_root", "."))))
        payload["ai_notice"] = check.get("ai_notice", silent_notice(category="startup"))
        return payload
    delta = payload.get("knowledge_delta", {}) if isinstance(payload.get("knowledge_delta"), dict) else {}
    text = summarize_delta(delta)
    if text and project_root is not None:
        payload["ai_notice"] = issue_notice(
            project_root,
            level="notice",
            summary=text.capitalize() + ".",
            category="adopt",
            event_key=_stable(delta),
            details={"knowledge_delta": delta},
        )
    else:
        payload["ai_notice"] = silent_notice(category="startup")
    return payload

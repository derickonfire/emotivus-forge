from __future__ import annotations

from typing import Any

_MAX_PROMPT_CHARACTERS = 680


def _clean(value: Any, *, limit: int = 260) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    clipped = text[: max(0, limit - 1)].rstrip(" ,;:-")
    return clipped + "…"


def _first_blocker(payload: dict[str, Any]) -> str:
    items = payload.get("attention_items", []) if isinstance(payload.get("attention_items"), list) else []
    for item in items:
        if not isinstance(item, dict) or str(item.get("severity", "")) != "blocker":
            continue
        message = _clean(item.get("message", ""), limit=220)
        if message:
            return message
    check = payload.get("check", {}) if isinstance(payload.get("check"), dict) else {}
    findings = check.get("findings", []) if isinstance(check.get("findings"), list) else []
    for finding in findings:
        if isinstance(finding, dict):
            message = _clean(finding.get("message") or finding.get("reason") or finding.get("detail"), limit=220)
            if message:
                return message
    return _clean(payload.get("reason", ""), limit=220)


def _bounded(text: str) -> str:
    text = " ".join(text.strip().split())
    if len(text) <= _MAX_PROMPT_CHARACTERS:
        return text
    clipped = text[: _MAX_PROMPT_CHARACTERS - 1].rstrip(" ,;:-")
    return clipped + "…"


def build_recommended_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    """Build one copy-ready, non-destructive prompt for the next AI action.

    The prompt is deliberately compact. It points the agent at confirmed project
    truth and authority boundaries without copying detailed evidence into chat.
    """
    status = str(payload.get("status", "UNKNOWN")).upper()
    action = str(payload.get("action", "")).upper()
    objective = payload.get("objective", {}) if isinstance(payload.get("objective"), dict) else {}
    next_action = payload.get("next_action", {}) if isinstance(payload.get("next_action"), dict) else {}
    objective_text = _clean(objective.get("text", ""), limit=260)
    next_action_text = _clean(next_action.get("text", ""), limit=280)
    continuity = payload.get("continuity", {}) if isinstance(payload.get("continuity"), dict) else {}
    continuity_status = str(continuity.get("status", "unknown"))
    forks = payload.get("decision_forks", {}) if isinstance(payload.get("decision_forks"), dict) else {}
    pending_forks = len([item for item in forks.get("pending", []) if isinstance(item, dict)])
    counts = payload.get("attention_counts", {}) if isinstance(payload.get("attention_counts"), dict) else {}
    blockers = int(counts.get("blocker", 0) or 0)
    presentation = payload.get("presentation_profile", {}) if isinstance(payload.get("presentation_profile"), dict) else {}
    authority_baseline = payload.get("authority_baseline", {}) if isinstance(payload.get("authority_baseline"), dict) else {}
    presentation_instruction = _clean(presentation.get("instruction", ""), limit=220)

    if status == "NEEDS_PROJECT":
        prompt = (
            "Place the complete target project beside Forge and run Forge from the project root. "
            "Do not begin project work until Forge can identify and adopt the host project."
        )
        kind = "locate-project"
    elif status in {"BLOCKED", "FAIL"} or blockers:
        blocker = _first_blocker(payload)
        first = "Stop before changing the project."
        if blocker:
            first += f" Resolve this Forge blocker first: {blocker}"
        second = "Then run Forge again and continue only from the confirmed objective and authorized checks."
        prompt = f"{first} {second}"
        kind = "resolve-blocker"
    elif not objective_text:
        prompt = (
            "Orient and read the project freely first — Forge has already surfaced what it is, how to run and "
            "test it, and any hardcoded secrets. Then review the project’s authoritative roadmap and confirm "
            "the current objective before changing code, and run Forge again to continue from it."
        )
        kind = "confirm-objective"
    else:
        target = next_action_text or objective_text
        label = "exact next action" if next_action_text else "confirmed objective"
        first = f"Continue this project from the {label}: {target}"
        safeguards = ["preserve confirmed decisions", "run only authorized checks", "state what remains unverified"]
        if authority_baseline.get("status") in {"NOT_ESTABLISHED", "QUARANTINED", "CONTRADICTED"}:
            safeguards.append("do not treat observed changes as project-authorized until the exact reviewed fingerprint is recorded")
        if pending_forks:
            safeguards.append("do not resolve pending decisions without the required authority")
        if continuity_status in {"not-established", "missing", "stale"} or action in {"ADOPT + RESUME", "SCOPED CHECK + RESUME", "RESUME"}:
            safeguards.append("end the increment with Forge Session Close")
        safeguard_text = "; ".join(safeguards)
        safeguard_text = safeguard_text[:1].upper() + safeguard_text[1:]
        prompt = first.rstrip(".") + ". " + safeguard_text + "."
        if presentation_instruction:
            prompt += " " + presentation_instruction
        kind = "continue-project"

    prompt = _bounded(prompt)
    return {
        "schema": 1,
        "label": "Forge recommends this prompt",
        "text": prompt,
        "copy_ready": True,
        "kind": kind,
        "max_characters": _MAX_PROMPT_CHARACTERS,
        "truth_boundary": (
            "This is bounded workflow guidance derived from Forge's current confirmed objective, exact next action, "
            "attention severity, decision authority, and continuity state. It is not permission to bypass project rules."
        ),
    }

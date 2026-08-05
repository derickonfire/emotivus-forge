from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import AiNotice, NOTICE_LEVELS, NOTICE_MODES
from .state import load_settings, load_state, save_state

_MAX_NOTICE_HISTORY = 100


def _normalize_summary(summary: str) -> str:
    return " ".join(str(summary).strip().split())[:220]


def _notice_id(category: str, summary: str, event_key: str) -> str:
    raw = json.dumps(
        {"category": category, "summary": summary, "event_key": event_key},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "notice-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _mode_allows(mode: str, level: str) -> bool:
    if level == "silent":
        return False
    if mode == "quiet":
        return level in {"warning", "blocker"}
    return level in {"notice", "warning", "blocker"}


def issue_notice(
    project_root: Path | None,
    *,
    level: str,
    summary: str,
    category: str,
    event_key: str,
    details: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    level = level if level in NOTICE_LEVELS else "notice"
    summary = _normalize_summary(summary)
    category = str(category).strip() or "general"
    event_key = str(event_key).strip() or summary
    mode = "standard"
    repeated = False
    notice_id = _notice_id(category, summary, event_key)

    if project_root is not None and (project_root / ".forge").is_dir():
        settings = load_settings(project_root)
        configured = str(settings.get("notice_mode", "standard")).strip().lower()
        mode = configured if configured in NOTICE_MODES else "standard"
        state = load_state(project_root)
        notices = state.get("notices", {}) if isinstance(state.get("notices"), dict) else {}
        history = notices.get("history", []) if isinstance(notices.get("history"), list) else []
        history = [str(item) for item in history if str(item).strip()]
        repeated = notice_id in history
        if persist and not repeated:
            history.append(notice_id)
            notices["history"] = history[-_MAX_NOTICE_HISTORY:]
            notices["last"] = {
                "id": notice_id,
                "level": level,
                "category": category,
                "summary": summary,
            }
            state["notices"] = notices
            save_state(project_root, state)

    speak = bool(summary) and _mode_allows(mode, level) and not repeated
    return AiNotice(
        id=notice_id,
        level=level,
        summary=summary,
        category=category,
        speak=speak,
        repeated=repeated,
        mode=mode,
        details=details or {},
    ).to_dict()


def silent_notice(*, category: str = "none", summary: str = "No meaningful Forge update.") -> dict[str, Any]:
    return AiNotice(
        id=_notice_id(category, summary, "silent"),
        level="silent",
        summary=_normalize_summary(summary),
        category=category,
        speak=False,
    ).to_dict()


def render_notice(notice: dict[str, Any] | None) -> str:
    if not isinstance(notice, dict) or not notice.get("speak"):
        return ""
    summary = _normalize_summary(str(notice.get("summary", "")))
    return f"Forge — {summary}\n" if summary else ""

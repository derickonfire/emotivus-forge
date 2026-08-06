from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, write_json
from .ledger import record_event
from .paths import ForgePaths
from .state import load_settings


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def confirm_project_event(
    project_root: Path,
    forge_root: Path,
    event_id: str,
    evidence_path: str | Path,
    *,
    authority: str = "owner",
    note: str = "",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    event_id = str(event_id).strip()
    authority = str(authority).strip()
    note = str(note).strip()
    if not event_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in event_id):
        raise ValueError("Project event ID may contain only lowercase letters, numbers, hyphens, and underscores.")
    if not authority:
        raise ValueError("Project event confirmation requires authority.")
    path = Path(evidence_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError("Project event evidence must be a project file outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Project event evidence does not exist as a regular file: {path}")
    relative = normalize_rel(path.relative_to(project_root))
    settings = load_settings(project_root)
    events = settings.get("project_events", {})
    if not isinstance(events, dict):
        events = {}
    record = {
        "status": "confirmed",
        "event_id": event_id,
        "confirmed_utc": utc_now(),
        "authority": authority,
        "evidence_path": relative,
        "note": note,
    }
    events[event_id] = record
    settings["project_events"] = events
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "project-event-confirmed", record, source=authority)
    record["ledger_event_id"] = event["id"]
    events[event_id] = record
    settings["project_events"] = events
    write_json(ForgePaths(project_root).settings, settings)
    return record


def project_events(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root.resolve())
    rows = settings.get("project_events", {}) if isinstance(settings, dict) else {}
    if not isinstance(rows, dict):
        return {}
    return {key: value for key, value in rows.items() if isinstance(value, dict)}

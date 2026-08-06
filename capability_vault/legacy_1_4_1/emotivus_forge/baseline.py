from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .utils import read_json, utc_now, write_json

BASELINABLE_SEVERITIES = {"warning", "info"}


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": 1, "created_utc": "", "findings": {}}
    try:
        data = read_json(path)
    except Exception:
        return {"schema": 1, "created_utc": "", "findings": {}}
    if not isinstance(data, dict) or data.get("schema") != 1:
        return {"schema": 1, "created_utc": "", "findings": {}}
    if not isinstance(data.get("findings"), dict):
        data["findings"] = {}
    return data


def write_baseline(path: Path, findings: Iterable[Any], project_fingerprint: str) -> dict[str, Any]:
    recorded: dict[str, dict[str, str]] = {}
    for finding in findings:
        if finding.severity not in BASELINABLE_SEVERITIES:
            continue
        recorded[finding.fingerprint] = {
            "check_id": finding.check_id,
            "path": finding.path,
            "message": finding.message,
            "severity": finding.severity,
        }
    payload = {
        "schema": 1,
        "created_utc": utc_now(),
        "project_fingerprint": project_fingerprint,
        "policy": "Only warning/info findings are baselined. Blockers and errors always remain active.",
        "findings": recorded,
    }
    write_json(path, payload)
    return payload

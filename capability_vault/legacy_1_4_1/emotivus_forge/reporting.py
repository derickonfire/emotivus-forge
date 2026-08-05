from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import write_json


def write_audit_reports(json_path: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    text_path = json_path.with_suffix(".txt")
    write_json(json_path, payload)
    counts = payload.get("counts", {})
    lines = [
        f"Emotivus Forge audit — {payload.get('project', '')}",
        "=" * 64,
        f"Status: {payload.get('status')}",
        f"Tree SHA-256: {payload.get('tree_fingerprint')}",
        f"Adapters: {', '.join(payload.get('adapters', [])) or 'none'}",
        f"Blockers: {counts.get('blocker', 0)} | Errors: {counts.get('error', 0)} | Warnings: {counts.get('warning', 0)}",
        f"New: {counts.get('disposition_new', 0)} | Legacy: {counts.get('disposition_legacy', 0)}",
        "",
    ]
    findings = payload.get("findings", [])
    if not findings:
        lines.append("No findings.")
    for item in findings:
        location = f" [{item['path']}]" if item.get("path") else ""
        lines.append(f"{item['severity'].upper():<8} {item['disposition']:<7} {item['check_id']}{location}")
        lines.append(f"         {item['message']}")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return json_path, text_path

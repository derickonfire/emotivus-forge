from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .learn import approve_learning, list_learning, propose_learning, reject_learning
from .utils import normalize_rel, utc_now

SUPPORTED_EVENTS = {
    "zero-byte-file",
    "hostile-filename",
    "required-artifact",
    "forbidden-artifact",
    "required-content",
    "forbidden-content",
}


def _read_event(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read guardrail event {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("guardrail event must be a JSON object")
    return data


def _learning_input(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type", "")).strip().lower()
    if event_type not in SUPPORTED_EVENTS:
        raise ValueError(f"guardrail type must be one of: {', '.join(sorted(SUPPORTED_EVENTS))}")
    path = normalize_rel(str(event.get("path", "")))
    if not path:
        raise ValueError("guardrail event requires path")
    title = str(event.get("title", "")).strip() or event_type.replace("-", " ").title()
    severity = str(event.get("severity", "error")).strip().lower()
    scope = str(event.get("scope", "project")).strip().lower()
    category = str(event.get("category", "artifact-hygiene")).strip().lower()
    resolution = str(event.get("resolution", "")).strip()
    common = {
        "title": title,
        "symptom": str(event.get("symptom", "")).strip(),
        "root_cause": str(event.get("root_cause", "")).strip(),
        "fix": resolution,
        "severity": severity,
        "scope": scope,
        "category": category,
        "affected_paths": [path],
        "gate": str(event.get("gate", "release")).strip().lower() or "release",
        "notes": f"Generated as a reviewed guardrail proposal at {utc_now()}. It is inactive until explicitly approved.",
    }
    if event_type == "zero-byte-file":
        mode = str(event.get("mode", "must-not-exist")).strip().lower()
        regression = {"kind": "file_nonempty", "path": path} if mode == "must-be-nonempty" else {"kind": "file_not_exists", "path": path}
        invariant = str(event.get("invariant", "")).strip() or (f"{path} must remain non-empty." if mode == "must-be-nonempty" else f"The stray zero-byte artifact {path} must not reappear.")
    elif event_type == "hostile-filename":
        regression = {"kind": "file_not_exists", "path": path}
        invariant = str(event.get("invariant", "")).strip() or f"The hostile or non-portable artifact path {path} must not exist."
    elif event_type == "required-artifact":
        regression = {"kind": "file_exists", "path": path}
        invariant = str(event.get("invariant", "")).strip() or f"The required artifact {path} must exist."
    elif event_type == "forbidden-artifact":
        regression = {"kind": "file_not_exists", "path": path}
        invariant = str(event.get("invariant", "")).strip() or f"The forbidden artifact {path} must not exist."
    elif event_type == "required-content":
        text = str(event.get("text", ""))
        if not text:
            raise ValueError("required-content guardrail requires text")
        regression = {"kind": "file_contains", "path": path, "text": text, "regex": bool(event.get("regex", False))}
        invariant = str(event.get("invariant", "")).strip() or f"{path} must retain the approved required content."
    else:
        text = str(event.get("text", ""))
        if not text:
            raise ValueError("forbidden-content guardrail requires text")
        regression = {"kind": "file_not_contains", "path": path, "text": text, "regex": bool(event.get("regex", False))}
        invariant = str(event.get("invariant", "")).strip() or f"{path} must not contain the rejected content."
    return {**common, "invariant": invariant, "regression": regression}


def propose_guardrail(project_root: Path, forge_root: Path, config: dict[str, Any], input_path: Path) -> dict[str, Any]:
    event = _read_event(input_path)
    payload = _learning_input(event)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle)
        temporary = Path(handle.name)
    try:
        result = propose_learning(project_root, forge_root, config, temporary)
    finally:
        temporary.unlink(missing_ok=True)
    result["guardrail_event"] = event
    result["activation"] = "inactive-until-approved"
    return result


def guardrail_action(project_root: Path, forge_root: Path, config: dict[str, Any], *, action: str, input_path: Path | None = None, proposal_id: str = "", reason: str = "") -> dict[str, Any]:
    if action == "propose":
        if input_path is None:
            raise ValueError("guardrail propose requires --input <event.json>")
        return propose_guardrail(project_root, forge_root, config, input_path)
    if action == "approve":
        if not proposal_id:
            raise ValueError("guardrail approve requires --id <proposal-id>")
        return approve_learning(project_root, config, proposal_id)
    if action == "reject":
        if not proposal_id:
            raise ValueError("guardrail reject requires --id <proposal-id>")
        return reject_learning(project_root, config, proposal_id, reason)
    return list_learning(project_root, config)

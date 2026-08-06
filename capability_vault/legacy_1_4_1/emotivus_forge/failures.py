from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .doctor import run_doctor
from .graph import load_graph
from .utils import utc_now, write_json


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:80] or "check"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _last_green(project_root: Path, config: dict[str, Any], exclude_profile: str = "") -> dict[str, Any] | None:
    reports = project_root / config.get("paths", {}).get("reports", ".forge/reports")
    evidence_dir = project_root / ".forge" / "evidence" / "last-green"
    candidates: list[dict[str, Any]] = []
    for profile in ("quick", "section", "release"):
        for path in (evidence_dir / f"{profile}.json", reports / f"{profile}.json"):
            payload = _read_json(path)
            if payload and payload.get("status") == "PASS":
                candidates.append(payload)
                break
    return max(candidates, key=lambda item: str(item.get("updated_utc", "")), default=None)


def _diff_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    old = previous or {}
    new = current or {}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(path for path in set(old) & set(new) if old[path] != new[path])
    return {"added": added, "modified": modified, "removed": removed}


def _related_graph(graph: dict[str, Any] | None, paths: set[str]) -> dict[str, Any]:
    if not graph:
        return {"nodes": [], "subsystems": []}
    nodes = [node for node in graph.get("nodes", []) if node.get("path") in paths]
    subsystems = sorted({str(node.get("subsystem")) for node in nodes if node.get("subsystem")})
    return {"nodes": nodes[:100], "subsystems": subsystems}


def _related_contracts(project_root: Path, config: dict[str, Any], paths: set[str]) -> list[dict[str, Any]]:
    contract_path = project_root / config.get("learn", {}).get("contracts_path", ".forge/policies/learned-contracts.json")
    payload = _read_json(contract_path)
    if not payload:
        return []
    related = []
    for contract in payload.get("contracts", []):
        affected = set(str(item) for item in contract.get("affected_paths", []))
        if not paths or affected & paths:
            related.append(contract)
    return related[:100]


def write_failure_bundle(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    profile: str,
    result: dict[str, Any],
    current_snapshot: dict[str, Any],
    reproduction_command: list[str],
) -> dict[str, Any]:
    generated = utc_now()
    previous = _last_green(project_root, config, profile)
    previous_snapshot = previous.get("tree_snapshot", {}) if previous else {}
    changes = _diff_snapshots(previous_snapshot, current_snapshot)
    changed_paths = set(changes["added"] + changes["modified"] + changes["removed"])
    graph = load_graph(project_root, config)
    graph_context = _related_graph(graph, changed_paths)
    contracts = _related_contracts(project_root, config, changed_paths)
    doctor = run_doctor(project_root, forge_root, config, write=False)
    check_id = str(result.get("check_id", "check"))
    stamp = generated.replace(":", "").replace("+00:00", "Z").replace("-", "")
    output_dir = project_root / config.get("evidence", {}).get("failure_dir", ".forge/failures") / f"{stamp}-{_safe(profile)}-{_safe(check_id)}"
    payload = {
        "schema": 1,
        "generated_utc": generated,
        "project": config.get("project", {}).get("name", project_root.name),
        "profile": profile,
        "failed_check": result,
        "reproduction_command": reproduction_command,
        "last_green": {
            "exists": bool(previous),
            "note": "" if previous else "No prior green run exists for this project evidence history; the current tree is the initial comparison baseline.",
            "profile": previous.get("profile") if previous else "",
            "updated_utc": previous.get("updated_utc") if previous else "",
            "tree_fingerprint": previous.get("tree_fingerprint") if previous else "",
        },
        "changes_since_last_green": changes,
        "graph_context": graph_context,
        "related_learned_contracts": contracts,
        "environment": {
            "doctor_status": doctor.get("status"),
            "problems": doctor.get("problems", []),
            "layout": doctor.get("layout", []),
        },
        "interpretation_boundary": "Forge assembled deterministic context. AI or human reasoning must interpret root cause and choose the repair.",
    }
    write_json(output_dir / "context.json", payload)
    lines = [
        "# Forge Failure Context", "",
        f"- Project: {payload['project']}",
        f"- Profile: {profile}",
        f"- Check: `{check_id}`",
        f"- Status: **{result.get('status', '')}**",
        f"- Generated: {generated}", "",
        "## Reproduce", "", "```text", " ".join(reproduction_command), "```", "",
        "## What changed since the last green run", "",
    ]
    if not previous:
        lines.extend(["**No prior green run exists for this project evidence history.** The added list represents the initial observed tree, not catastrophic drift.", ""])
    for category in ("added", "modified", "removed"):
        values = changes[category]
        lines.append(f"### {category.title()}")
        lines.extend(f"- `{item}`" for item in values) if values else lines.append("- None recorded")
        lines.append("")
    lines += ["## Affected subsystems", ""]
    lines.extend(f"- {item}" for item in graph_context["subsystems"]) if graph_context["subsystems"] else lines.append("- None mapped")
    lines += ["", "## Learned contracts", ""]
    lines.extend(f"- `{item.get('id')}` — {item.get('invariant', '')}" for item in contracts) if contracts else lines.append("- None directly mapped")
    lines += ["", "## Raw output", "", "```text", str(result.get("output", ""))[-30000:], "```", "", payload["interpretation_boundary"]]
    (output_dir / "context.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"status": "PASS", "directory": str(output_dir), "json": str(output_dir / "context.json"), "markdown": str(output_dir / "context.md")}

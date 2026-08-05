from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .doctor import run_doctor
from .utils import tree_fingerprint, utc_now, write_json


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _last_green(project_root: Path, reports_dir: Path) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for profile in ("quick", "section", "release"):
        data = _read_json(reports_dir / f"{profile}.json")
        if data.get("status") == "PASS":
            candidates.append(data)
    return max(candidates, key=lambda item: str(item.get("updated_utc", "")), default={})


def _objective(project_root: Path, config: dict[str, Any]) -> dict[str, str]:
    continuity = config.get("continuity", {})
    explicit = str(continuity.get("next_action", "")).strip()
    if explicit:
        return {"source": "configuration", "text": explicit}
    sources = continuity.get("objective_sources", ["ACTIVE-BUILD-PROMPT.md", "BACKLOG.md", "ROADMAP.md", "Planning/ACTIVE-BUILD-PROMPT.md"])
    for raw in sources:
        path = project_root / str(raw)
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            cleaned = line.strip().lstrip("#-* ").strip()
            if cleaned:
                return {"source": str(raw), "text": cleaned[:500]}
    return {"source": "", "text": "No declared next action was found."}


def build_brief(project_root: Path, forge_root: Path, config: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
    project_root = project_root.resolve()
    reports_dir = project_root / config.get("paths", {}).get("reports", ".forge/reports")
    last_green = _last_green(project_root, reports_dir)
    current_fingerprint = tree_fingerprint(project_root, config.get("paths", {}).get("exclude", []), forge_root)
    graph = _read_json(project_root / config.get("graph", {}).get("output_dir", ".forge/graph") / "project-graph.json")
    contracts = _read_json(project_root / config.get("learn", {}).get("contracts_path", ".forge/policies/learned-contracts.json"))
    memory_root = project_root / config.get("project_memory", {}).get("root", ".forge/project")
    plans = _read_json(memory_root / "plans.json")
    pivots = _read_json(memory_root / "pivots.json")
    active_plan_id = str(plans.get("active_id", ""))
    active_plan = next((item for item in plans.get("plans", []) if isinstance(item, dict) and item.get("id") == active_plan_id), {})
    active_pivot_id = str(pivots.get("active_id", ""))
    active_pivot = next((item for item in pivots.get("pivots", []) if isinstance(item, dict) and item.get("id") == active_pivot_id), {})
    doctor = run_doctor(project_root, forge_root, config, write=write)
    objective = _objective(project_root, config)
    last_fingerprint = str(last_green.get("tree_fingerprint", ""))
    changed = bool(last_fingerprint and last_fingerprint != current_fingerprint)
    recovery_commands = [
        "python3 Emotivus-Forge/forge.py check . --profile quick",
        "python3 Emotivus-Forge/forge.py resume . --budget compact",
        "python3 Emotivus-Forge/forge.py check . --profile quick --fresh",
    ]
    if doctor["status"] == "PASS":
        recovery_commands.append("python3 Emotivus-Forge/forge.py check . --profile section --fresh")
    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "project": config.get("project", {}).get("name", project_root.name),
        "version": config.get("versioning", {}).get("target_version", ""),
        "forge_version": config.get("forge_version", ""),
        "objective": objective,
        "last_green": {
            "profile": last_green.get("profile", ""),
            "updated_utc": last_green.get("updated_utc", ""),
            "tree_fingerprint": last_fingerprint,
        },
        "source_changed_since_last_green": changed if last_fingerprint else None,
        "current_tree_fingerprint": current_fingerprint,
        "graph": graph.get("summary", {}),
        "active_learned_contracts": len(contracts.get("contracts", [])) if isinstance(contracts.get("contracts", []), list) else 0,
        "active_plan": {"id": active_plan.get("id", ""), "title": active_plan.get("title", ""), "status": active_plan.get("status", "")},
        "active_pivot": {"id": active_pivot.get("id", ""), "title": active_pivot.get("title", ""), "status": active_pivot.get("status", "")},
        "development_mode": config.get("project_memory", {}).get("mode", "development"),
        "workspace": config.get("workspace", {}),
        "work_scope": config.get("work", {}),
        "project_identity": config.get("project", {}).get("identity", ""),
        "doctor_status": doctor["status"],
        "doctor_problems": doctor["problems"],
        "commands_to_green": recovery_commands,
    }
    if write:
        output_dir = project_root / ".forge" / "brief"
        write_json(output_dir / "brief.json", payload)
        lines = [
            "# Forge Brief", "",
            f"- Project: **{payload['project']}**",
            f"- Version: **{payload['version'] or 'unversioned'}**",
            f"- Current objective: {objective['text']}" + (f" (`{objective['source']}`)" if objective['source'] else ""),
            f"- Last green Gate: {payload['last_green']['profile'] or 'none recorded'}" + (f" at {payload['last_green']['updated_utc']}" if payload['last_green']['updated_utc'] else ""),
            f"- Source changed since last green: {payload['source_changed_since_last_green'] if payload['source_changed_since_last_green'] is not None else 'unknown'}",
            f"- Doctor: **{doctor['status']}**",
            f"- Graph nodes/edges: {payload['graph'].get('nodes', 0)} / {payload['graph'].get('edges', 0)}",
            f"- Active learned contracts: {payload['active_learned_contracts']}",
            f"- Active plan: {payload['active_plan']['title'] or 'none'}",
            f"- Active pivot: {payload['active_pivot']['title'] or 'none'}",
            f"- Development mode: {payload['development_mode']}",
            f"- Workspace: {payload['workspace'].get('classification', 'unknown')} ({payload['workspace'].get('confidence', 'low')} confidence)",
            f"- Coding allowed by active scope: {payload['work_scope'].get('coding_allowed', True)}", "",
        ]
        if doctor["problems"]:
            lines += ["## Environment or layout problems", ""] + [f"- {item}" for item in doctor["problems"]] + [""]
        lines += ["## Commands to regain a green state", "", "```bash", *recovery_commands, "```", ""]
        (output_dir / "brief.md").write_text("\n".join(lines), encoding="utf-8")
    return payload

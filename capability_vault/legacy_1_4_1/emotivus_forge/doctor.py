from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .utils import resolve_command, utc_now, write_json


def _version(command: list[str], cwd: Path) -> str:
    try:
        process = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return process.stdout.strip().splitlines()[0] if process.stdout.strip() else ""


def _command_executables(project_root: Path, forge_root: Path, config: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for group in config.get("commands", {}).values():
        for item in group:
            if not isinstance(item, dict) or not isinstance(item.get("command"), list) or not item["command"]:
                continue
            first = resolve_command([str(part) for part in item["command"]], project=project_root, forge=forge_root)[0]
            if first and not Path(first).is_absolute():
                names.add(first)
    return names


def run_doctor(project_root: Path, forge_root: Path, config: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    required: set[str] = set(str(item) for item in config.get("environment", {}).get("required_executables", []) if str(item).strip())
    runtime_map = {"php": "php", "node": "node", "python": "python3"}
    for runtime, executable in runtime_map.items():
        if config.get("runtime", {}).get(runtime, {}).get("required"):
            required.add(executable)
    required.update(_command_executables(project_root, forge_root, config))

    executable_rows: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for name in sorted(required | {"php", "node", "npm", "pnpm", "yarn", "bun", "composer", "python3", "docker", "git"}):
        resolved = shutil.which(name)
        is_required = name in required
        if is_required and not resolved:
            missing_required.append(name)
        probe = [resolved, "--version"] if resolved else []
        if name == "php" and resolved:
            probe = [resolved, "-r", "echo PHP_VERSION;"]
        executable_rows.append({
            "name": name,
            "required": is_required,
            "path": resolved or "",
            "available": bool(resolved),
            "version": _version(probe, project_root) if probe else "",
        })

    env_rows: list[dict[str, Any]] = []
    missing_env: list[str] = []
    for name in sorted(set(str(item) for item in config.get("environment", {}).get("required_env", []) if str(item).strip())):
        present = name in os.environ and os.environ.get(name, "") != ""
        env_rows.append({"name": name, "present": present})
        if not present:
            missing_env.append(name)

    layout_rows: list[dict[str, Any]] = []
    missing_layout: list[str] = []
    for raw in config.get("environment", {}).get("expected_layout", []):
        if isinstance(raw, str):
            entry = {"path": raw, "kind": "either", "required": True}
        elif isinstance(raw, dict):
            entry = {"path": str(raw.get("path", "")), "kind": str(raw.get("kind", "either")), "required": bool(raw.get("required", True))}
        else:
            continue
        if not entry["path"]:
            continue
        candidate = (project_root / entry["path"]).resolve()
        kind = entry["kind"]
        present = candidate.is_file() if kind == "file" else candidate.is_dir() if kind == "directory" else candidate.exists()
        row = {**entry, "resolved": str(candidate), "present": present}
        layout_rows.append(row)
        if entry["required"] and not present:
            missing_layout.append(entry["path"])

    problems = [f"missing required executable: {name}" for name in missing_required]
    problems += [f"missing required environment variable: {name}" for name in missing_env]
    problems += [f"layout mismatch: expected {name}" for name in missing_layout]
    repair = []
    if missing_required:
        repair.append("Install or expose the required executables on PATH: " + ", ".join(missing_required) + ".")
    if missing_env:
        repair.append("Provide the required environment-variable names without storing their secret values in Forge state: " + ", ".join(missing_env) + ".")
    if missing_layout:
        repair.append("Restore or reassemble the declared working layout before running absorbed project commands: " + ", ".join(missing_layout) + ".")

    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "status": "FAIL" if problems else "PASS",
        "project": config.get("project", {}).get("name", project_root.name),
        "executables": executable_rows,
        "environment_variables": env_rows,
        "layout": layout_rows,
        "problems": problems,
        "repair_plan": repair,
        "automatic_repairs_performed": False,
    }
    if write:
        output_dir = project_root / ".forge" / "doctor"
        write_json(output_dir / "doctor.json", payload)
        lines = ["# Forge Doctor", "", f"Status: **{payload['status']}**", "", "Forge Doctor measures the current machine and emits a repair plan. It does not install software, create credentials, or modify services.", ""]
        if problems:
            lines += ["## Problems", ""] + [f"- {item}" for item in problems] + [""]
        if repair:
            lines += ["## Repair plan", ""] + [f"- {item}" for item in repair] + [""]
        lines += ["## Required executables", ""] + [f"- {'✓' if row['available'] else '✗'} {row['name']} — {'required' if row['required'] else 'optional'} — {row['version'] or row['path'] or 'unavailable'}" for row in executable_rows]
        (output_dir / "doctor.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return payload

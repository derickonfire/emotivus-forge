from __future__ import annotations

import json
import shutil
import stat
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .security import has_private_key_bytes, has_secret_assignment_bytes
from .utils import sha256_bytes, sha256_file, utc_now

STATE_ROOTS = (".emotivus-forge.json", "FORGE-AGENT.md", ".forge")
STATE_EXCLUDES = {".forge/legacy-tools", ".forge/lab/workspaces", ".forge/state-backups", ".forge/update/backups", ".forge/update/work", ".forge/update/rollback"}


def _included_state_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for raw in STATE_ROOTS:
        path = project_root / raw
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if not candidate.is_file() or candidate.is_symlink():
                    continue
                relative = candidate.relative_to(project_root).as_posix()
                if any(relative == prefix or relative.startswith(prefix + "/") for prefix in STATE_EXCLUDES):
                    continue
                if relative.startswith(".forge/doctor/remediation/transactions/") and "/backup" in relative:
                    continue
                files.append(candidate)
    return sorted(set(files), key=lambda item: item.relative_to(project_root).as_posix())


def export_state(project_root: Path, config: dict[str, Any], output: Path | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    if output is None:
        output = project_root / "Forge-State.zip"
    elif not output.is_absolute():
        output = project_root / output
    output = output.resolve()
    files = _included_state_files(project_root)
    entries: list[dict[str, Any]] = []
    problems: list[str] = []
    fixture_paths = config.get("security", {}).get("synthetic_fixture_paths", [])
    for path in files:
        relative = path.relative_to(project_root).as_posix()
        data = path.read_bytes()
        if has_private_key_bytes(data, relative, fixture_paths) or has_secret_assignment_bytes(data, relative, fixture_paths):
            problems.append(f"state file may contain secret material: {relative}")
            continue
        entries.append({"path": relative, "bytes": len(data), "sha256": sha256_bytes(data)})
    manifest = {
        "schema": 1,
        "generated_utc": utc_now(),
        "forge_version": __version__,
        "project": config.get("project", {}).get("name", project_root.name),
        "project_identity": config.get("project", {}).get("identity", ""),
        "project_version": config.get("versioning", {}).get("target_version", ""),
        "files": entries,
        "problems": problems,
    }
    if problems:
        return {"status": "FAIL", "output": str(output), "problems": problems, "manifest": manifest, "sha256": ""}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for entry in entries:
            path = project_root / entry["path"]
            info = zipfile.ZipInfo(entry["path"], datetime.now().timetuple()[:6])
            info.external_attr = (stat.S_IMODE(path.stat().st_mode) & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        archive.writestr("FORGE-STATE-MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    temporary.replace(output)
    return {"status": "PASS", "output": str(output), "problems": [], "manifest": manifest, "sha256": sha256_file(output)}


def inspect_state(input_path: Path) -> dict[str, Any]:
    input_path = input_path.resolve()
    with zipfile.ZipFile(input_path) as archive:
        names = archive.namelist()
        if "FORGE-STATE-MANIFEST.json" not in names:
            raise RuntimeError("Forge state archive is missing FORGE-STATE-MANIFEST.json")
        manifest = json.loads(archive.read("FORGE-STATE-MANIFEST.json"))
        problems: list[str] = []
        for entry in manifest.get("files", []):
            path = str(entry.get("path", ""))
            if path not in names:
                problems.append(f"state member missing: {path}")
                continue
            if path.startswith("/") or ".." in Path(path).parts:
                problems.append(f"unsafe state member path: {path}")
                continue
            if sha256_bytes(archive.read(path)) != entry.get("sha256"):
                problems.append(f"state member hash mismatch: {path}")
        extras = sorted(set(names) - {"FORGE-STATE-MANIFEST.json"} - {str(item.get("path")) for item in manifest.get("files", [])})
        if extras:
            problems.append("undeclared state members: " + ", ".join(extras))
    return {"status": "FAIL" if problems else "PASS", "input": str(input_path), "manifest": manifest, "problems": problems}


def adopt_state(project_root: Path, input_path: Path, *, force: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    inspection = inspect_state(input_path)
    if inspection["status"] != "PASS":
        return inspection
    manifest = inspection["manifest"]
    current_config = project_root / ".emotivus-forge.json"
    if current_config.exists() and not force:
        try:
            current = json.loads(current_config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        current_name = str(current.get("project", {}).get("name", ""))
        incoming_name = str(manifest.get("project", ""))
        current_identity = str(current.get("project", {}).get("identity", ""))
        incoming_identity = str(manifest.get("project_identity", ""))
        if current_identity and incoming_identity and current_identity != incoming_identity:
            raise RuntimeError(f"state belongs to project identity {incoming_identity!r}, not {current_identity!r}; use --force only for a declared fork or reviewed recovery")
        if not current_identity and current_name and incoming_name and current_name != incoming_name:
            raise RuntimeError(f"state belongs to project {incoming_name!r}, not {current_name!r}; use --force only after review")
    backup_root = project_root / ".forge" / "state-backups" / utc_now().replace(":", "-")
    for source in _included_state_files(project_root):
        relative = source.relative_to(project_root)
        target = backup_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    with zipfile.ZipFile(input_path) as archive:
        for entry in manifest.get("files", []):
            relative = str(entry["path"])
            target = project_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(relative))
    return {"status": "PASS", "input": str(input_path.resolve()), "adopted_files": len(manifest.get("files", [])), "backup": str(backup_root)}

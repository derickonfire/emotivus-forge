from __future__ import annotations

import fnmatch
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .hygiene import filename_issues, is_allowed_zero_byte, portable_path_key
from .security import has_private_key_bytes, has_secret_assignment_bytes
from .state import export_state
from .utils import sha256_file, utc_now


def _matches(path: str, pattern: str) -> bool:
    pattern = pattern.strip().replace("\\", "/")
    if not pattern:
        return False
    if pattern.endswith("/"):
        prefix = pattern.rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if "/" in pattern:
        return fnmatch.fnmatchcase(path, pattern) or path == pattern or path.startswith(pattern.rstrip("/") + "/")
    return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)


def _excluded(relative: str, patterns: list[str]) -> bool:
    return any(_matches(relative, pattern) for pattern in patterns)


def _collect_internal_source(project_root: Path, config: dict[str, Any], output: Path) -> tuple[list[Path], list[str], list[str]]:
    delivery = config.get("maintenance", {}).get("delivery", {})
    patterns = [str(item) for item in delivery.get("exclude", [])]
    patterns += [
        ".emotivus-forge.json", "FORGE-AGENT.md", "Forge-State*.zip",
        "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ]
    hard = [str(item) for item in config.get("packaging", {}).get("hard_exclude", [])]
    fixture_paths = config.get("security", {}).get("synthetic_fixture_paths", [])
    zero_allow = config.get("packaging", {}).get("zero_byte_allow", [".gitkeep", ".keep"])
    included: list[Path] = []
    excluded: list[str] = []
    problems: list[str] = []
    portable: dict[str, str] = {}
    try:
        output_relative = output.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        output_relative = ""
    for current, dir_names, file_names in os.walk(project_root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(project_root)
        kept: list[str] = []
        for name in sorted(dir_names):
            relative = (relative_dir / name).as_posix()
            if _excluded(relative, patterns):
                excluded.append(relative + "/")
            else:
                kept.append(name)
        dir_names[:] = kept
        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(project_root).as_posix()
            if relative == output_relative or _excluded(relative, patterns):
                excluded.append(relative)
                continue
            if path.is_symlink():
                problems.append(f"symbolic link cannot enter internal delivery: {relative}")
                continue
            if any(_matches(relative, pattern) for pattern in hard):
                problems.append(f"sensitive path cannot enter internal delivery: {relative}")
                continue
            for issue in filename_issues(relative):
                problems.append(f"unsafe or non-portable filename {relative}: {issue}")
            key = portable_path_key(relative)
            if key in portable and portable[key] != relative:
                problems.append(f"cross-platform path collision: {portable[key]} conflicts with {relative}")
            portable[key] = relative
            data = path.read_bytes()
            if len(data) == 0 and not is_allowed_zero_byte(relative, zero_allow):
                problems.append(f"unexpected zero-byte file cannot enter internal delivery: {relative}")
                continue
            if has_private_key_bytes(data, relative, fixture_paths):
                problems.append(f"private-key material found: {relative}")
                continue
            if len(data) <= 5_000_000 and has_secret_assignment_bytes(data, relative, fixture_paths):
                problems.append(f"credential-like literal found: {relative}")
                continue
            included.append(path)
    return sorted(included), sorted(excluded), sorted(set(problems))


def _zip_time(path: Path) -> tuple[int, int, int, int, int, int]:
    dt = datetime.fromtimestamp(path.stat().st_mtime)
    return (min(max(dt.year, 1980), 2107), dt.month, dt.day, dt.hour, dt.minute, dt.second)


def build_internal_delivery(project_root: Path, forge_root: Path, config: dict[str, Any], *, output: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    delivery = config.get("maintenance", {}).get("delivery", {})
    project_name = str(config.get("project", {}).get("name", project_root.name)).strip() or project_root.name
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", project_name).strip("-") or "Project"
    version = str(config.get("versioning", {}).get("package_version") or config.get("versioning", {}).get("target_version") or "dev")
    if output is None:
        pattern = str(delivery.get("internal_output", "deploy/{project}-{version}-Internal.zip"))
        output = project_root / pattern.format(project=safe_name, version=version)
    elif not output.is_absolute():
        output = project_root / output
    output = output.resolve()
    included, excluded, problems = _collect_internal_source(project_root, config, output)
    manifest: dict[str, Any] = {
        "schema": 1,
        "generated_utc": utc_now(),
        "delivery_profile": "internal",
        "project": project_name,
        "project_version": version,
        "source_archive": str(delivery.get("source_archive_name", "Project-Source.zip")),
        "state_archive": str(delivery.get("state_archive_name", "Forge-State.zip")),
        "source_files": [{"path": path.relative_to(project_root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in included],
        "excluded": excluded,
        "problems": problems,
        "restore_order": ["Extract Project-Source.zip.", "Place the resulting project workspace on disk.", "Inspect and adopt Forge-State.zip with the included Emotivus Forge installation."],
    }
    if problems or dry_run:
        return {
            "status": "FAIL" if problems else "PASS",
            "profile": "internal",
            "dry_run": dry_run,
            "output": str(output),
            "sha256": "",
            "included_count": len(included),
            "excluded_count": len(excluded),
            "problems": problems,
            "manifest": manifest,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="forge-internal-delivery-") as temp_dir:
        temp = Path(temp_dir)
        source_zip = temp / manifest["source_archive"]
        state_zip = temp / manifest["state_archive"]
        with zipfile.ZipFile(source_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in included:
                relative = path.relative_to(project_root).as_posix()
                info = zipfile.ZipInfo(f"{safe_name}/{relative}", _zip_time(path))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IMODE(path.stat().st_mode) & 0xFFFF) << 16
                archive.writestr(info, path.read_bytes())
        state = export_state(project_root, config, state_zip)
        if state["status"] != "PASS":
            manifest["problems"] = list(state.get("problems", []))
            return {
                "status": "FAIL", "profile": "internal", "dry_run": False, "output": str(output), "sha256": "",
                "included_count": len(included), "excluded_count": len(excluded), "problems": manifest["problems"], "manifest": manifest,
            }
        manifest["source_archive_sha256"] = sha256_file(source_zip)
        manifest["state_archive_sha256"] = sha256_file(state_zip)
        readme = (
            "EMOTIVUS FORGE INTERNAL DELIVERY\n"
            "================================\n"
            "1. Extract Project-Source.zip.\n"
            "2. Enter the extracted project workspace.\n"
            "3. Inspect Forge-State.zip with: python3 Emotivus-Forge/forge.py adopt . --state <path>\n"
            "4. Adopt it with: The start command validates and adopts the state after review.\n"
            "5. Run Forge Doctor, Brief, and a fresh Quick Gate before editing.\n"
            "This is an internal working delivery, not a production deployment package.\n"
        )
        temporary = output.with_suffix(output.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as outer:
            outer.write(source_zip, manifest["source_archive"])
            outer.write(state_zip, manifest["state_archive"])
            outer.writestr("FORGE-INTERNAL-DELIVERY-MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
            outer.writestr("README-FIRST.txt", readme)
        temporary.replace(output)
    return {
        "status": "PASS",
        "profile": "internal",
        "dry_run": False,
        "output": str(output),
        "sha256": sha256_file(output),
        "included_count": len(included),
        "excluded_count": len(excluded),
        "problems": [],
        "manifest": manifest,
    }

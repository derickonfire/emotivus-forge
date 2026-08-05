from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, sha256_file as _sha256
from .orientation import load_project_ignore, matches_project_ignore

VERSION_RE = re.compile(r"(?<![0-9])([0-9]+\.[0-9]+(?:\.[0-9]+)?)(?![0-9])")
EXCLUDED_PARTS = {".forge", ".git", ".hg", ".svn", "__pycache__", "node_modules"}
MAX_ARCHIVES = 5_000
MAX_MANIFEST_BYTES = 2_000_000

TRUTH_BOUNDARY = (
    "Forge compares exact observed ZIP bytes only when artifacts share the same basename and "
    "declared version. It does not infer that differently named editions are interchangeable, "
    "authenticate authorship, or replace recorded lineage and package-family contracts. Project-owned "
    "`.forgeignore` exclusions are respected and remain outside this observation boundary."
)


def _filename_version(name: str) -> str:
    matches = VERSION_RE.findall(name)
    return matches[-1] if matches else ""


def _manifest_version(path: Path) -> tuple[str, list[str]]:
    problems: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [
                info for info in archive.infolist()
                if not info.is_dir()
                and Path(info.filename.replace("\\", "/")).name in {"FORGE-MANIFEST.json", "MANIFEST.json"}
                and info.file_size <= MAX_MANIFEST_BYTES
            ]
            for info in sorted(candidates, key=lambda item: (Path(item.filename).name != "FORGE-MANIFEST.json", item.filename)):
                try:
                    value = json.loads(archive.read(info).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, KeyError):
                    continue
                if not isinstance(value, dict):
                    continue
                version = str(value.get("version", "")).strip()
                if version:
                    return version, problems
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        problems.append(str(exc))
    return "", problems


def observe_version_collisions(project_root: Path, *, max_archives: int = MAX_ARCHIVES) -> dict[str, Any]:
    root = project_root.resolve()
    artifacts: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []
    project_ignore = load_project_ignore(root)
    for current, dir_names, file_names in os.walk(root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        kept_dirs: list[str] = []
        for name in sorted(dir_names):
            relative_path = relative_dir / name
            relative = normalize_rel(relative_path)
            if any(part in EXCLUDED_PARTS for part in relative_path.parts):
                continue
            if matches_project_ignore(relative, project_ignore, directory=True):
                continue
            kept_dirs.append(name)
        dir_names[:] = kept_dirs
        for name in sorted(file_names):
            if not name.lower().endswith(".zip"):
                continue
            path = current_path / name
            relative_path = path.relative_to(root)
            relative = normalize_rel(relative_path)
            if (
                any(part in EXCLUDED_PARTS for part in relative_path.parts)
                or matches_project_ignore(relative, project_ignore)
                or not path.is_file()
                or path.is_symlink()
            ):
                continue
            if len(artifacts) >= max_archives:
                return {
                    "schema": 1,
                    "status": "BLOCKED",
                    "reason": f"Observed archive count exceeded the bounded limit of {max_archives}.",
                    "artifacts_scanned": len(artifacts),
                    "project_ignore_patterns": project_ignore,
                    "collisions": [],
                    "problems": problems,
                    "truth_boundary": TRUTH_BOUNDARY,
                }
            manifest_version, manifest_problems = _manifest_version(path)
            filename_version = _filename_version(name)
            for problem in manifest_problems:
                problems.append({"path": normalize_rel(relative_path), "problem": problem})
            if manifest_version and filename_version and manifest_version != filename_version:
                problems.append({
                    "path": normalize_rel(relative_path),
                    "problem": f"filename version {filename_version} differs from packaged manifest version {manifest_version}",
                })
            version = manifest_version or filename_version
            if not version:
                continue
            artifacts.append({
                "path": normalize_rel(relative_path),
                "basename": name.casefold(),
                "version": version,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "version_source": "manifest" if manifest_version else "filename",
            })

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for artifact in artifacts:
        groups.setdefault((artifact["basename"], artifact["version"]), []).append(artifact)
    collisions: list[dict[str, Any]] = []
    for (basename, version), rows in sorted(groups.items()):
        digests = {str(row["sha256"]) for row in rows}
        if len(digests) > 1:
            collisions.append({
                "basename": basename,
                "version": version,
                "distinct_sha256_count": len(digests),
                "artifacts": sorted(rows, key=lambda row: row["path"]),
            })
    status = "FAIL" if collisions or problems else "PASS"
    return {
        "schema": 1,
        "status": status,
        "reason": (
            "Observed same-name, same-version ZIP artifacts map to different exact bytes."
            if collisions
            else "Observed versioned ZIP identities are collision-free within the bounded scan."
            if not problems
            else "One or more observed archive identities could not be interpreted consistently."
        ),
        "generated_utc": utc_now(),
        "artifacts_scanned": len(artifacts),
        "identity_groups": len(groups),
        "project_ignore_patterns": project_ignore,
        "collisions": collisions,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }

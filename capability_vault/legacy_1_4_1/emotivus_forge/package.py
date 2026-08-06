from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .security import has_private_key_bytes, has_secret_assignment_bytes
from .hygiene import filename_issues, is_allowed_zero_byte, portable_path_key
from .utils import normalize_rel, sha256_file, tree_fingerprint, utc_now

IMMUTABLE_EXCLUDES = {".git", ".hg", ".svn", ".forge", "deploy", "__pycache__"}
IMMUTABLE_FILES = {".emotivus-forge.json", "FORGE-AGENT.md", ".deployignore"}


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


def _load_ignore_rules(project_root: Path, config: dict[str, Any]) -> list[tuple[str, bool]]:
    rules: list[tuple[str, bool]] = []
    for item in config.get("packaging", {}).get("exclude", []):
        rules.append((str(item), False))
    ignore_name = config.get("paths", {}).get("deploy_ignore", ".deployignore")
    ignore_file = project_root / ignore_name if ignore_name else None
    if ignore_file and ignore_file.is_file():
        for raw in ignore_file.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            negate = stripped.startswith("!")
            if negate:
                stripped = stripped[1:].strip()
            rules.append((stripped, negate))
    return rules


def _excluded(
    path: str,
    is_dir: bool,
    config: dict[str, Any],
    rules: list[tuple[str, bool]],
    forge_relative: str,
    required_files: set[str] | None = None,
) -> tuple[bool, str]:
    parts = Path(path).parts
    if any(part in IMMUTABLE_EXCLUDES for part in parts):
        return True, "immutable"
    if not is_dir and Path(path).name in IMMUTABLE_FILES:
        return True, "immutable-internal"
    if forge_relative and (path == forge_relative or path.startswith(forge_relative + "/")):
        return True, "forge-core"
    required = required_files or set()
    normalized_path = path.rstrip("/")
    required_override = (
        (not is_dir and normalized_path in required)
        or (is_dir and any(item == normalized_path or item.startswith(normalized_path + "/") for item in required))
    )
    for pattern in config.get("packaging", {}).get("immutable_exclude", []):
        candidate = path + ("/" if is_dir else "")
        if _matches(candidate, str(pattern)):
            return True, f"immutable-policy:{pattern}"
    excluded = False
    source = ""
    for pattern, negate in rules:
        if _matches(path + ("/" if is_dir else ""), pattern):
            excluded = not negate
            source = f"ignore:{pattern}"
    if excluded and required_override:
        return False, "required-file-override"
    return excluded, source


def _safe_zip_time(timestamp: float) -> tuple[int, int, int, int, int, int]:
    dt = datetime.fromtimestamp(timestamp)
    return (min(max(dt.year, 1980), 2107), dt.month, dt.day, dt.hour, dt.minute, dt.second)


def collect_package(project_root: Path, forge_root: Path, config: dict[str, Any]) -> tuple[list[Path], list[tuple[str, str]], list[str]]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    try:
        forge_relative = forge_root.relative_to(project_root).as_posix()
    except ValueError:
        forge_relative = ""
    rules = _load_ignore_rules(project_root, config)
    required_files = {normalize_rel(str(item)) for item in config.get("packaging", {}).get("required_files", []) if str(item).strip()}
    hard_patterns = [str(item) for item in config.get("packaging", {}).get("hard_exclude", [])]
    secret_scan = bool(config.get("packaging", {}).get("secret_scan", True))
    included: list[Path] = []
    excluded: list[tuple[str, str]] = []
    problems: list[str] = []
    portable_paths: dict[str, str] = {}

    for current, dir_names, file_names in os.walk(project_root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(project_root)
        kept: list[str] = []
        for name in sorted(dir_names):
            relative = (relative_dir / name).as_posix()
            is_excluded, source = _excluded(relative, True, config, rules, forge_relative, required_files)
            if is_excluded:
                excluded.append((relative + "/", source))
            else:
                kept.append(name)
        dir_names[:] = kept
        for name in sorted(file_names):
            path = current_path / name
            relative_path = path.relative_to(project_root)
            relative = relative_path.as_posix()
            is_excluded, source = _excluded(relative, False, config, rules, forge_relative, required_files)
            if is_excluded:
                excluded.append((relative, source))
                continue
            if path.is_symlink():
                problems.append(f"symbolic link cannot be packaged: {relative}")
                continue
            for issue in filename_issues(relative):
                problems.append(f"unsafe or non-portable filename {relative}: {issue}")
            portable_key = portable_path_key(relative)
            prior = portable_paths.get(portable_key)
            if prior is not None and prior != relative:
                problems.append(f"cross-platform path collision: {prior} conflicts with {relative}")
            else:
                portable_paths[portable_key] = relative
            if any(_matches(relative, pattern) for pattern in hard_patterns):
                problems.append(f"hard-excluded sensitive path would enter package: {relative}")
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                problems.append(f"could not read {relative}: {exc}")
                continue
            zero_allow = config.get("packaging", {}).get("zero_byte_allow", [".gitkeep", ".keep"])
            if len(data) == 0 and not is_allowed_zero_byte(relative, zero_allow):
                problems.append(f"unexpected zero-byte file would enter package: {relative}")
                continue
            fixture_paths = config.get("security", {}).get("synthetic_fixture_paths", [])
            if has_private_key_bytes(data, relative, fixture_paths):
                problems.append(f"private-key material found: {relative}")
                continue
            text_suffixes = {".php", ".phtml", ".inc", ".js", ".mjs", ".cjs", ".json", ".env", ".ini", ".conf", ".yml", ".yaml", ".xml", ".txt", ".md", ".py", ".sh"}
            if secret_scan and len(data) <= 5_000_000 and (path.suffix.lower() in text_suffixes or path.name.startswith(".env")):
                if has_secret_assignment_bytes(data, relative, fixture_paths):
                    problems.append(f"credential-like literal found: {relative}")
                    continue
            included.append(path)

    for required in config.get("packaging", {}).get("required_files", []):
        normalized = normalize_rel(str(required))
        if not any(path.relative_to(project_root).as_posix() == normalized for path in included):
            problems.append(f"required package file is missing or excluded: {normalized}")
    return sorted(included), sorted(excluded), sorted(set(problems))


def build_package(project_root: Path, forge_root: Path, config: dict[str, Any], *, dry_run: bool = False, output: Path | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    project_name = str(config.get("project", {}).get("name", project_root.name)).strip() or project_root.name
    versioning = config.get("versioning", {})
    version = str(versioning.get("package_version") or versioning.get("target_version") or "dev")
    output_pattern = str(config.get("packaging", {}).get("output", "deploy/{project}-{version}.zip"))
    if output is None:
        output = project_root / output_pattern.format(project=re.sub(r"[^A-Za-z0-9._-]+", "-", project_name).strip("-") or "project", version=version)
    elif not output.is_absolute():
        output = project_root / output
    output = output.resolve()

    included, excluded, problems = collect_package(project_root, forge_root, config)
    try:
        output_relative = output.relative_to(project_root).as_posix()
    except ValueError:
        output_relative = ""
    if output_relative:
        kept: list[Path] = []
        for path in included:
            if path.resolve() == output:
                excluded.append((output_relative, "current-package-output"))
            else:
                kept.append(path)
        included = kept

    source_fingerprint = tree_fingerprint(project_root, config.get("paths", {}).get("exclude", []), forge_root)
    proof_path = project_root / str(config.get("release_proof", {}).get("output_dir", ".forge/release-proof")) / "latest.json"
    proof_summary: dict[str, Any] = {}
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        if proof.get("tree_fingerprint") == source_fingerprint:
            proof_summary = {
                "claim_level": proof.get("claim_level", ""),
                "claim_status": proof.get("claim_status", ""),
                "proof_sha256": sha256_file(proof_path),
                "limitations": list(proof.get("limitations", [])) if isinstance(proof.get("limitations"), list) else [],
                "path": str(proof_path.relative_to(project_root)),
            }
    except (OSError, json.JSONDecodeError, ValueError):
        proof_summary = {}

    manifest = {
        "schema": 3,
        "generated_utc": utc_now(),
        "project": project_name,
        "project_identity": config.get("project", {}).get("identity", ""),
        "version": version,
        "evidence_boundary": "deployment-package",
        "source_workspace_classification": config.get("workspace", {}).get("classification", "unknown"),
        "source_root": str(project_root),
        "source_tree_fingerprint": source_fingerprint,
        "release_proof": proof_summary,
        "included_files": [
            {"path": path.relative_to(project_root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in included
        ],
        "excluded_paths": [{"path": path, "reason": reason} for path, reason in sorted(excluded)],
        "problems": problems,
        "dry_run": dry_run,
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    package_hash = ""
    if not problems and not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path in included:
                    relative = path.relative_to(project_root).as_posix()
                    info = zipfile.ZipInfo(relative, _safe_zip_time(path.stat().st_mtime))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = (stat.S_IMODE(path.stat().st_mode) & 0xFFFF) << 16
                    archive.writestr(info, path.read_bytes())
                info = zipfile.ZipInfo("FORGE-DEPLOY-MANIFEST.json", _safe_zip_time(datetime.now().timestamp()))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, manifest_bytes)
            temporary.replace(output)
            package_hash = sha256_file(output)
        finally:
            if temporary.exists():
                temporary.unlink()
    return {
        "status": "FAIL" if problems else "PASS",
        "dry_run": dry_run,
        "output": str(output),
        "sha256": package_hash,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "problems": problems,
        "manifest": manifest,
    }


from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .. import __version__
from .common import sha256_file, utc_now
from .ledger import record_event
from .paths import ForgePaths, STATE_FILE_NAMES
from .session_close import latest_session_close
from .storage import require_healthy_state

_MANIFEST_NAME = "FORGE-CONTINUITY-MANIFEST.json"
_MAX_BUNDLE_BYTES = 50_000_000


def _safe_output_path(project_root: Path, raw: str) -> Path:
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if path.suffix.lower() != ".zip":
        raise ValueError("Continuity bundle path must end in .zip.")
    forge_root = project_root.resolve() / ".forge"
    try:
        path.relative_to(forge_root)
    except ValueError:
        pass
    else:
        raise ValueError("Continuity bundle must remain outside .forge state.")
    if path.exists() and path.is_symlink():
        raise ValueError("Continuity bundle output may not be a symlink.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _project_package(project_root: Path, raw: str) -> tuple[Path | None, dict[str, Any]]:
    if not str(raw).strip():
        return None, {
            "status": "UNBOUND",
            "path": "",
            "sha256": "",
            "contains_forge_state": False,
            "reason": "No development package was supplied; the continuity bundle is not bound to project-package bytes.",
        }
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise ValueError("Development package must resolve to a regular file.")
    if path.suffix.lower() != ".zip":
        raise ValueError("Development package must be a ZIP archive.")
    contains_state = False
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/").lstrip("./")
                parts = PurePosixPath(name).parts
                if ".forge" in parts and any(part in STATE_FILE_NAMES for part in parts):
                    contains_state = True
                    break
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Development package is not a readable ZIP: {exc}") from exc
    return path, {
        "status": "BOUND",
        "path": path.name,
        "sha256": sha256_file(path),
        "contains_forge_state": contains_state,
        "reason": (
            "The development package already embeds Forge continuity; a separate companion remains safer for deployment separation."
            if contains_state else
            "The development package does not embed Forge continuity; this companion bundle supplies the portable handoff."
        ),
    }


def _evidence_result_files(paths: ForgePaths) -> list[Path]:
    if not paths.evidence.is_dir():
        return []
    rows: list[Path] = []
    for path in sorted(paths.evidence.rglob("result.json")):
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 2_000_000:
            rows.append(path)
    return rows[:500]


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def export_continuity_bundle(
    project_root: Path,
    output_path: str,
    *,
    development_package: str = "",
    forge_root: Path | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    require_healthy_state(project_root)
    close = latest_session_close(project_root)
    if close is None:
        raise ValueError("A portable continuity bundle requires at least one completed Forge Session Close.")
    paths = ForgePaths(project_root)
    if forge_root is not None:
        from .resume import build_resume
        build_resume(project_root, forge_root, budget="compact", refresh=True)
    missing = [name for name in STATE_FILE_NAMES if not (paths.root / name).is_file()]
    if missing:
        raise ValueError(f"Portable continuity requires all eight state files; missing: {', '.join(missing)}")
    output = _safe_output_path(project_root, output_path)
    package_path, package_binding = _project_package(project_root, development_package)
    files: list[tuple[str, Path]] = []
    for name in STATE_FILE_NAMES:
        files.append((f".forge/{name}", paths.root / name))
    for path in _evidence_result_files(paths):
        files.append((f".forge/{path.relative_to(paths.root).as_posix()}", path))
    entries = [{
        "path": archive_name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    } for archive_name, path in files]
    state_path = paths.state
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        state = {}
    last_close = close.get("payload", {}) if isinstance(close.get("payload"), dict) else {}
    manifest = {
        "schema": "forge-continuity-bundle/1",
        "forge_version": __version__,
        "generated_utc": utc_now(),
        "project_binding": package_binding,
        "continuity": {
            "session_event_id": str(close.get("id", "")),
            "closed_utc": str(close.get("utc", "")),
            "next_action": str(last_close.get("next_action", {}).get("text", "")) if isinstance(last_close.get("next_action"), dict) else "",
            "snapshot_fingerprint": str(state.get("last_session_close", {}).get("continuity_fingerprint", "")) if isinstance(state.get("last_session_close"), dict) else "",
        },
        "files": entries,
        "privacy_boundary": {
            "included": "Eight top-level Forge state files and bounded result.json evidence manifests.",
            "excluded": "Raw stdout/stderr logs, response bodies, credentials, project source, and deployable application files.",
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temp = output.with_suffix(output.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr(_zip_info(_MANIFEST_NAME), manifest_bytes)
            for archive_name, path in files:
                archive.writestr(_zip_info(archive_name), path.read_bytes())
        os.replace(temp, output)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    result = {
        "schema": 1,
        "status": "READY",
        "bundle": str(output),
        "bundle_sha256": sha256_file(output),
        "state_file_count": 8,
        "evidence_manifest_count": len(files) - 8,
        "project_binding": package_binding,
        "session_event_id": str(close.get("id", "")),
        "raw_logs_included": False,
        "project_source_included": False,
    }
    return result


def _read_bundle(path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("Continuity bundle must resolve to a regular ZIP file.")
    if path.stat().st_size > _MAX_BUNDLE_BYTES:
        raise ValueError("Continuity bundle exceeds the 50 MB import limit.")
    try:
        with zipfile.ZipFile(path) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            if _MANIFEST_NAME not in names:
                raise ValueError("Continuity bundle has no manifest.")
            manifest = json.loads(archive.read(_MANIFEST_NAME).decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("schema") != "forge-continuity-bundle/1":
                raise ValueError("Unsupported continuity bundle schema.")
            contents: dict[str, bytes] = {}
            for info in archive.infolist():
                if info.is_dir() or info.filename == _MANIFEST_NAME:
                    continue
                pure = PurePosixPath(info.filename)
                if pure.is_absolute() or ".." in pure.parts:
                    raise ValueError("Continuity bundle contains an unsafe path.")
                allowed_top = len(pure.parts) >= 2 and pure.parts[0] == ".forge"
                allowed_state = len(pure.parts) == 2 and pure.parts[1] in STATE_FILE_NAMES
                allowed_result = len(pure.parts) >= 4 and pure.parts[1] == "evidence" and pure.name == "result.json"
                if not allowed_top or not (allowed_state or allowed_result):
                    raise ValueError(f"Continuity bundle contains an unsupported file: {info.filename}")
                if info.file_size > 5_000_000:
                    raise ValueError(f"Continuity bundle file exceeds the bounded import limit: {info.filename}")
                contents[info.filename] = archive.read(info)
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"Continuity bundle is not readable: {exc}") from exc
    expected = manifest.get("files", [])
    if not isinstance(expected, list):
        raise ValueError("Continuity bundle manifest files must be an array.")
    expected_map = {str(item.get("path", "")): str(item.get("sha256", "")) for item in expected if isinstance(item, dict)}
    for name, digest in expected_map.items():
        if name not in contents:
            raise ValueError(f"Continuity bundle is missing a manifest file: {name}")
        if hashlib.sha256(contents[name]).hexdigest() != digest:
            raise ValueError(f"Continuity bundle file digest mismatch: {name}")
    required = {f".forge/{name}" for name in STATE_FILE_NAMES}
    if not required.issubset(contents):
        raise ValueError("Continuity bundle does not contain all eight top-level state files.")
    return manifest, contents


def import_continuity_bundle(
    project_root: Path,
    bundle_path: str,
    *,
    development_package: str = "",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    bundle = Path(str(bundle_path)).expanduser()
    if not bundle.is_absolute():
        bundle = project_root / bundle
    bundle = bundle.resolve()
    manifest, contents = _read_bundle(bundle)
    forge_root = project_root / ".forge"
    if forge_root.exists() and any((forge_root / name).exists() for name in STATE_FILE_NAMES):
        raise ValueError("Continuity import refuses to overwrite existing Forge state.")
    binding = manifest.get("project_binding", {}) if isinstance(manifest.get("project_binding"), dict) else {}
    expected_package_digest = str(binding.get("sha256", ""))
    package_check = {"status": "NOT_REQUIRED", "sha256": ""}
    if expected_package_digest:
        if not development_package:
            raise ValueError("This continuity bundle is bound to a development package; supply that package during import.")
        package_path, package_binding = _project_package(project_root, development_package)
        if package_path is None or str(package_binding.get("sha256", "")) != expected_package_digest:
            raise ValueError("Development package digest does not match the continuity bundle binding.")
        package_check = {"status": "MATCH", "sha256": expected_package_digest}
    forge_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        for name, content in contents.items():
            relative = PurePosixPath(name)
            target = project_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            written.append(target)
        require_healthy_state(project_root)
    except BaseException:
        for target in reversed(written):
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        raise
    record_event(project_root, "continuity-bundle-import", {
        "bundle_name": bundle.name,
        "bundle_sha256": sha256_file(bundle),
        "source_forge_version": str(manifest.get("forge_version", "")),
        "project_package_status": package_check["status"],
        "session_event_id": str(manifest.get("continuity", {}).get("session_event_id", "")) if isinstance(manifest.get("continuity"), dict) else "",
    }, source="operator")
    return {
        "schema": 1,
        "status": "IMPORTED",
        "bundle": str(bundle),
        "source_forge_version": str(manifest.get("forge_version", "")),
        "state_file_count": 8,
        "project_package": package_check,
        "raw_logs_imported": False,
    }

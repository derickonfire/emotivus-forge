from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .config import CONFIG_NAME, migrate_config_data, save_config
from .utils import sha256_bytes, sha256_file, utc_now, write_json

UPDATE_ROOT = Path(".forge/update")


def _safe_archive_members(archive: zipfile.ZipFile) -> tuple[str, list[str]]:
    names = archive.namelist()
    if not names:
        raise RuntimeError("incoming Forge archive is empty")
    if len(names) != len(set(names)):
        raise RuntimeError("incoming Forge archive contains duplicate paths")
    roots: set[str] = set()
    files: list[str] = []
    for name in names:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"incoming Forge archive contains unsafe path: {name}")
        if not path.parts:
            continue
        roots.add(path.parts[0])
        if not name.endswith("/"):
            files.append(name)
    if roots != {"Emotivus-Forge"}:
        raise RuntimeError(f"incoming Forge archive must contain one Emotivus-Forge root; found {sorted(roots)}")
    required = {
        "Emotivus-Forge/FORGE-MANIFEST.json",
        "Emotivus-Forge/forge.py",
        "Emotivus-Forge/tools/forge_bootstrap.py",
    }
    missing = sorted(required - set(files))
    if missing:
        raise RuntimeError("incoming Forge archive is incomplete: " + ", ".join(missing))
    return "Emotivus-Forge", files


def _read_incoming(source: Path) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_file():
        raise RuntimeError(f"incoming Forge archive not found: {source}")
    try:
        with zipfile.ZipFile(source) as archive:
            root, files = _safe_archive_members(archive)
            manifest = json.loads(archive.read(f"{root}/FORGE-MANIFEST.json"))
            hashes = {
                name.removeprefix(root + "/"): sha256_bytes(archive.read(name))
                for name in files if name.startswith(root + "/")
            }
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, OSError) as exc:
        raise RuntimeError(f"incoming Forge archive is invalid: {exc}") from exc
    version = str(manifest.get("version", "")).strip()
    if not version:
        raise RuntimeError("incoming Forge manifest has no version")
    return {"source": str(source), "root": root, "manifest": manifest, "version": version, "hashes": hashes, "sha256": sha256_file(source)}


def _current_snapshot(forge_root: Path) -> tuple[str, dict[str, str]]:
    manifest_path = forge_root / "FORGE-MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"installed Forge manifest is unreadable: {exc}") from exc
    version = str(manifest.get("version", "")).strip()
    hashes: dict[str, str] = {}
    for path in sorted(forge_root.rglob("*")):
        if path.is_file() and not path.is_symlink() and not any(part in {".forge", "deploy", "__pycache__"} for part in path.relative_to(forge_root).parts):
            hashes[path.relative_to(forge_root).as_posix()] = sha256_file(path)
    return version, hashes


def _inside_project(project_root: Path, forge_root: Path) -> str:
    try:
        relative = forge_root.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise RuntimeError("Forge Update requires the installed Forge directory to be inside the host project workspace") from exc
    if len(relative.parts) != 1:
        raise RuntimeError("Forge Update requires Forge to be installed as one intact top-level directory")
    return relative.as_posix()


def preview_update(project_root: Path, forge_root: Path, config: dict[str, Any], source: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    folder = _inside_project(project_root, forge_root)
    incoming = _read_incoming(source)
    current_version, current_hashes = _current_snapshot(forge_root)
    preserve = [str(item).strip().strip("/\\") for item in config.get("maintenance", {}).get("update", {}).get("preserve_paths", ["policy-packs"]) if str(item).strip()]
    incoming_hashes = incoming["hashes"]
    all_paths = sorted(set(current_hashes) | set(incoming_hashes))
    changes: list[dict[str, str]] = []
    for path in all_paths:
        preserved = any(path == item or path.startswith(item + "/") for item in preserve)
        if preserved:
            action = "preserve"
        elif path not in current_hashes:
            action = "add"
        elif path not in incoming_hashes:
            action = "remove"
        elif current_hashes[path] != incoming_hashes[path]:
            action = "modify"
        else:
            continue
        changes.append({"path": path, "action": action})
    return {
        "schema": 1,
        "status": "PASS",
        "generated_utc": utc_now(),
        "project": config.get("project", {}).get("name", project_root.name),
        "forge_folder": folder,
        "current_version": current_version,
        "incoming_version": incoming["version"],
        "incoming_archive": incoming["source"],
        "incoming_sha256": incoming["sha256"],
        "preserve_paths": preserve,
        "changes": changes,
        "counts": {key: sum(1 for item in changes if item["action"] == key) for key in ("add", "modify", "remove", "preserve")},
        "post_update_profile": config.get("maintenance", {}).get("update", {}).get("post_update_profile", "quick"),
    }


def _archive_directory(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                archive.write(path, f"Emotivus-Forge/{path.relative_to(root).as_posix()}")
    temporary.replace(output)


def _extract_source(source: Path, destination: Path) -> Path:
    with zipfile.ZipFile(source) as archive:
        _safe_archive_members(archive)
        archive.extractall(destination)
    return destination / "Emotivus-Forge"


def _copy_preserved(current: Path, staged: Path, preserve_paths: list[str]) -> list[str]:
    copied: list[str] = []
    for raw in preserve_paths:
        source = current / raw
        target = staged / raw
        if not source.exists():
            continue
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        copied.append(raw)
    return copied


def _run(command: list[str], cwd: Path, timeout: int = 1800) -> dict[str, Any]:
    try:
        process = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return {"status": "PASS" if process.returncode == 0 else "FAIL", "returncode": process.returncode, "command": command, "output": process.stdout[-20000:].rstrip()}
    except subprocess.TimeoutExpired as exc:
        return {"status": "ERROR", "returncode": None, "command": command, "output": f"timeout after {timeout}s: {exc}"}
    except OSError as exc:
        return {"status": "ERROR", "returncode": None, "command": command, "output": str(exc)}


def _prune_backups(project_root: Path, limit: int) -> None:
    backups = project_root / UPDATE_ROOT / "backups"
    if not backups.is_dir() or limit < 1:
        return
    entries = sorted((path for path in backups.iterdir() if path.is_dir()), key=lambda item: item.name, reverse=True)
    for old in entries[limit:]:
        shutil.rmtree(old, ignore_errors=True)


def apply_update(project_root: Path, forge_root: Path, config: dict[str, Any], source: Path, *, post_profile: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    preview = preview_update(project_root, forge_root, config, source)
    if preview["current_version"] == preview["incoming_version"] and not preview["changes"]:
        return {**preview, "status": "PASS", "action": "no-op", "transaction_id": "", "checks": []}
    transaction_id = utc_now().replace(":", "-") + f"-{preview['incoming_version']}"
    tx_root = project_root / UPDATE_ROOT / "transactions" / transaction_id
    backup_root = project_root / UPDATE_ROOT / "backups" / transaction_id
    work_root = project_root / UPDATE_ROOT / "work" / transaction_id
    tx_root.mkdir(parents=True, exist_ok=False)
    backup_root.mkdir(parents=True, exist_ok=False)
    work_root.mkdir(parents=True, exist_ok=False)
    backup_zip = backup_root / "Emotivus-Forge.zip"
    _archive_directory(forge_root, backup_zip)
    config_path = project_root / CONFIG_NAME
    config_backup = backup_root / CONFIG_NAME
    shutil.copy2(config_path, config_backup)
    staged_parent = work_root / "incoming"
    staged_parent.mkdir()
    staged = _extract_source(source.resolve(), staged_parent)
    preserved = _copy_preserved(forge_root, staged, preview["preserve_paths"])
    previous = work_root / "previous"
    checks: list[dict[str, Any]] = []
    rollback_reason = ""
    try:
        os.replace(forge_root, previous)
        os.replace(staged, forge_root)
        migrated, migrations = migrate_config_data(config)
        migrated["forge_version"] = preview["incoming_version"]
        save_config(project_root, migrated)
        checks.append(_run([sys.executable, str(forge_root / "tools" / "forge_bootstrap.py"), str(forge_root), "--skip-self-test"], project_root, 600))
        checks.append(_run([sys.executable, str(forge_root / "forge.py"), "self-test"], project_root, 2400))
        checks.append(_run([sys.executable, str(forge_root / "forge.py"), "doctor", str(project_root)], project_root, 600))
        profile = post_profile or str(migrated.get("maintenance", {}).get("update", {}).get("post_update_profile", "quick"))
        if profile not in {"quick", "section", "release"}:
            raise RuntimeError(f"unsupported post-update profile: {profile}")
        checks.append(_run([sys.executable, str(forge_root / "forge.py"), "check", str(project_root), "--profile", profile, "--fresh"], project_root, 3600))
        if any(item["status"] != "PASS" for item in checks):
            raise RuntimeError("one or more post-update checks failed")
        shutil.rmtree(previous, ignore_errors=True)
        result_status = "PASS"
        action = "updated"
    except Exception as exc:
        rollback_reason = str(exc)
        if forge_root.exists():
            shutil.rmtree(forge_root, ignore_errors=True)
        if previous.exists():
            os.replace(previous, forge_root)
        shutil.copy2(config_backup, config_path)
        result_status = "FAIL"
        action = "rolled-back"
        migrations = []
    payload = {
        **preview,
        "status": result_status,
        "action": action,
        "transaction_id": transaction_id,
        "backup": str(backup_zip),
        "config_backup": str(config_backup),
        "preserved": preserved,
        "config_migrations": migrations,
        "checks": checks,
        "rollback_reason": rollback_reason,
        "finished_utc": utc_now(),
    }
    write_json(tx_root / "transaction.json", payload)
    limit = int(config.get("maintenance", {}).get("update", {}).get("backup_limit", 5) or 5)
    _prune_backups(project_root, limit)
    shutil.rmtree(work_root, ignore_errors=True)
    return payload


def rollback_update(project_root: Path, forge_root: Path, *, transaction_id: str = "") -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    backups_root = project_root / UPDATE_ROOT / "backups"
    if not transaction_id:
        candidates = sorted((path.name for path in backups_root.iterdir() if path.is_dir()), reverse=True) if backups_root.is_dir() else []
        if not candidates:
            raise RuntimeError("no Forge Update backup is available")
        transaction_id = candidates[0]
    backup_root = backups_root / transaction_id
    archive_path = backup_root / "Emotivus-Forge.zip"
    config_backup = backup_root / CONFIG_NAME
    if not archive_path.is_file() or not config_backup.is_file():
        raise RuntimeError(f"Forge Update backup is incomplete: {transaction_id}")
    work = project_root / UPDATE_ROOT / "rollback" / (utc_now().replace(":", "-") + "-" + transaction_id)
    work.mkdir(parents=True, exist_ok=False)
    restored = _extract_source(archive_path, work)
    displaced = work / "displaced"
    os.replace(forge_root, displaced)
    try:
        os.replace(restored, forge_root)
        shutil.copy2(config_backup, project_root / CONFIG_NAME)
        check = _run([sys.executable, str(forge_root / "tools" / "forge_bootstrap.py"), str(forge_root), "--skip-self-test"], project_root, 600)
        if check["status"] != "PASS":
            raise RuntimeError("restored Forge installation failed bootstrap validation")
        shutil.rmtree(displaced, ignore_errors=True)
        status = "PASS"
        reason = ""
    except Exception as exc:
        if forge_root.exists():
            shutil.rmtree(forge_root, ignore_errors=True)
        if displaced.exists():
            os.replace(displaced, forge_root)
        status = "FAIL"
        reason = str(exc)
        check = {"status": "NOT-RUN", "output": reason}
    payload = {
        "schema": 1,
        "status": status,
        "action": "rollback",
        "transaction_id": transaction_id,
        "backup": str(archive_path),
        "check": check,
        "reason": reason,
        "finished_utc": utc_now(),
    }
    write_json(project_root / UPDATE_ROOT / "rollbacks" / f"{utc_now().replace(':', '-')}-{transaction_id}.json", payload)
    shutil.rmtree(work, ignore_errors=True)
    return payload


def update_action(project_root: Path, forge_root: Path, config: dict[str, Any], *, action: str, source: Path | None = None, transaction_id: str = "", post_profile: str | None = None) -> dict[str, Any]:
    if action == "rollback":
        return rollback_update(project_root, forge_root, transaction_id=transaction_id)
    if source is None:
        raise ValueError(f"update --action {action} requires --source <Emotivus-Forge.zip>")
    if action == "preview":
        payload = preview_update(project_root, forge_root, config, source)
        write_json(project_root.resolve() / UPDATE_ROOT / "latest-preview.json", payload)
        return payload
    if action == "apply":
        return apply_update(project_root, forge_root, config, source, post_profile=post_profile)
    raise ValueError(f"unsupported update action: {action}")

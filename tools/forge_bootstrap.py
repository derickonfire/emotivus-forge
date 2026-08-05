#!/usr/bin/env python3
"""Independent standard-library bootstrap validator for Emotivus Forge.

This file deliberately imports no Emotivus Forge modules. It establishes that a
Forge source tree or distribution archive is structurally intact enough to run
Forge's richer self-hosted certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import signal
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

EXCLUDED_PARTS = {".git", ".forge", "deploy", "__pycache__", ".venv", "venv"}
VERSION_RE = re.compile(r'(?m)^__version__\s*=\s*["\']([^"\']+)["\']')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [name for name in sorted(dirs) if name not in EXCLUDED_PARTS]
        for name in sorted(files):
            path = current_path / name
            relative = path.relative_to(root)
            if not any(part in EXCLUDED_PARTS for part in relative.parts) and path.is_file() and not path.is_symlink():
                yield path


def run_command(command: list[str], cwd: Path, timeout: int, *, nested: bool = False) -> dict[str, object]:
    log = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False, prefix="forge-bootstrap-command-", suffix=".log")
    log_path = Path(log.name)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if nested:
        env["FORGE_BOOTSTRAP_NESTED"] = "1"
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(command, cwd=cwd, text=True, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
        try:
            returncode = process.wait(timeout=timeout)
            status = "PASS" if returncode == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
            try:
                os.killpg(process.pid, signal.SIGTERM)
                returncode = process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    returncode = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    returncode = None
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        log.flush()
        log.seek(0)
        output = log.read()
        return {"command": command, "returncode": returncode, "status": status, "output": output[-30000:].strip()}
    except OSError as exc:
        return {"command": command, "returncode": None, "status": "RUNNER_ERROR", "output": str(exc)}
    finally:
        log.close()
        try:
            log_path.unlink()
        except OSError:
            pass


def validate_tree(root: Path, *, run_self_test: bool) -> tuple[list[str], dict[str, object]]:
    problems: list[str] = []
    manifest_path = root / "FORGE-MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest unreadable: {exc}"], {}

    if manifest.get("forge_schema") != 1:
        problems.append("FORGE-MANIFEST.json must use forge_schema 1")
    if manifest.get("name") != "Emotivus Forge":
        problems.append("manifest name must be Emotivus Forge")
    version = str(manifest.get("version", "")).strip()
    if not version:
        problems.append("manifest version is missing")

    init_path = root / "emotivus_forge" / "__init__.py"
    try:
        match = VERSION_RE.search(init_path.read_text(encoding="utf-8"))
    except OSError as exc:
        match = None
        problems.append(f"could not read version source: {exc}")
    runtime_version = match.group(1) if match else ""
    if not runtime_version:
        problems.append("__version__ was not found in emotivus_forge/__init__.py")
    elif version and runtime_version != version:
        problems.append(f"version mismatch: manifest={version}, runtime={runtime_version}")

    canonical = manifest.get("canonical_paths", [])
    if not isinstance(canonical, list) or not canonical:
        problems.append("canonical_paths must be a non-empty array")
    else:
        for raw in canonical:
            if not isinstance(raw, str) or not raw.strip():
                problems.append("canonical_paths contains an invalid entry")
                continue
            path = root / raw.rstrip("/")
            if raw.endswith("/"):
                if not path.is_dir():
                    problems.append(f"canonical directory missing: {raw}")
            elif not path.is_file():
                problems.append(f"canonical file missing: {raw}")

    compiled = 0
    json_files = 0
    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".py":
            try:
                with tempfile.TemporaryDirectory(prefix="forge-bootstrap-pyc-") as directory:
                    py_compile.compile(str(path), cfile=str(Path(directory) / "check.pyc"), doraise=True)
                compiled += 1
            except py_compile.PyCompileError as exc:
                problems.append(f"python syntax failure in {relative}: {exc.msg}")
        elif path.suffix.lower() == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
                json_files += 1
            except (OSError, json.JSONDecodeError) as exc:
                problems.append(f"invalid JSON in {relative}: {exc}")

    commands: list[dict[str, object]] = []
    command = [sys.executable, "forge.py", "--version"]
    result = run_command(command, root, 60)
    commands.append(result)
    if result["returncode"] != 0 or (version and version not in str(result["output"])):
        problems.append("forge.py --version did not report the manifest version")
    if run_self_test and os.environ.get("FORGE_BOOTSTRAP_NESTED") != "1":
        command = [sys.executable, "forge.py", "self-test"]
        result = run_command(command, root, 1800, nested=True)
        commands.append(result)
        if result["returncode"] != 0:
            problems.append("forge.py self-test failed")

    return problems, {
        "version": version,
        "runtime_version": runtime_version,
        "python_files_compiled": compiled,
        "json_files_validated": json_files,
        "commands": commands,
    }


def validate_archive(archive_path: Path, *, run_self_test: bool) -> tuple[list[str], dict[str, object]]:
    problems: list[str] = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                problems.append("archive contains duplicate paths")
            unsafe = [name for name in names if name.startswith("/") or ".." in Path(name).parts]
            if unsafe:
                problems.append(f"archive contains unsafe paths: {unsafe[:5]}")
            roots = {Path(name).parts[0] for name in names if Path(name).parts}
            if roots != {"Emotivus-Forge"}:
                problems.append(f"archive must contain one Emotivus-Forge root; found {sorted(roots)}")
            with tempfile.TemporaryDirectory(prefix="forge-bootstrap-archive-") as directory:
                archive.extractall(directory)
                tree_problems, details = validate_tree(Path(directory) / "Emotivus-Forge", run_self_test=run_self_test)
                problems.extend(tree_problems)
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"archive unreadable: {exc}"], {}
    return problems, {
        "archive": str(archive_path),
        "archive_sha256": sha256_file(archive_path),
        "archive_entries": len(names) if 'names' in locals() else 0,
        "tree": details if 'details' in locals() else {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--archive", default="", help="Validate a packaged Forge ZIP in addition to the source tree")
    parser.add_argument("--skip-self-test", action="store_true", help="Skip the Forge-owned regression suite")
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    problems, tree = validate_tree(root, run_self_test=not args.skip_self_test)
    archive: dict[str, object] = {}
    if args.archive:
        archive_problems, archive = validate_archive(Path(args.archive).resolve(), run_self_test=not args.skip_self_test)
        problems.extend(archive_problems)
    payload = {
        "schema": 1,
        "validator": "Forge Bootstrap",
        "status": "PASS" if not problems else "FAIL",
        "source_root": str(root),
        "tree": tree,
        "archive": archive,
        "problems": problems,
    }
    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())

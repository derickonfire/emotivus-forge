from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..core.common import normalize_rel, utc_now

_VERSION = re.compile(r"(?<!\d)(\d+)(?:\.(\d+))?(?:\.(\d+))?")
EXACT_PIN = re.compile(r"^\s*[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?\s*$")


def _version_tuple(text: str) -> tuple[int, ...] | None:
    match = _VERSION.search(text)
    if not match:
        return None
    return tuple(int(item) for item in match.groups() if item is not None)


def _exact_pin(text: str) -> tuple[int, ...] | None:
    match = EXACT_PIN.match(text)
    if not match:
        return None
    return tuple(int(item) for item in match.groups() if item is not None)


def _matches_prefix(actual: tuple[int, ...] | None, expected: tuple[int, ...] | None) -> bool | None:
    if not actual or not expected:
        return None
    return actual[:len(expected)] == expected


def _read_text(path: Path, limit: int = 256_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _run(command: list[str], deadline: float) -> dict[str, Any]:
    remaining = max(0.0, deadline - time.monotonic())
    if remaining <= 0:
        return {"status": "SKIPPED", "reason": "runtime budget exhausted", "command": command}
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=min(remaining, 8.0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "ERROR", "reason": str(exc), "command": command}
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "command": command,
        "stdout": stdout[:1000],
        "stderr": stderr[:1000],
    }


def _descriptor_paths(project_root: Path, file_limit: int) -> list[Path]:
    names = {
        ".python-version", ".nvmrc", ".tool-versions", "pyproject.toml", "requirements.txt",
        "package.json", "composer.json", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    }
    rows: list[Path] = []
    for path in sorted(project_root.rglob("*")):
        if len(rows) >= file_limit:
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.relative_to(project_root)
        except ValueError:
            continue
        if any(part in {".forge", ".git", "node_modules", "vendor", "dist", "build", "capability_vault"} for part in relative.parts):
            continue
        if path.name in names:
            rows.append(path)
    return rows


def _finding(severity: str, path: str, message: str, *, declared: str = "", observed: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {
        "check": "capability.doctor",
        "severity": severity,
        "path": path,
        "line": 0,
        "message": message,
    }
    if declared:
        row["declared"] = declared
    if observed:
        row["observed"] = observed
    return row


def _runtime_observation(name: str, executable: str, args: list[str], deadline: float) -> dict[str, Any]:
    found = shutil.which(executable)
    if not found:
        return {"runtime": name, "status": "MISSING", "executable": executable, "version": ""}
    result = _run([found, *args], deadline)
    output = result.get("stdout") or result.get("stderr") or ""
    return {
        "runtime": name,
        "status": result.get("status", "ERROR"),
        "executable": found,
        "version": output.splitlines()[0] if output else "",
        "returncode": result.get("returncode"),
    }


def _python_observations(deadline: float) -> list[dict[str, Any]]:
    """Observe every Python a project might actually be using.

    PATH `python3` is not necessarily the interpreter in use. Inside a virtual
    environment, a pyenv shim, or a pinned toolchain the running interpreter is the real
    one and PATH may resolve to an unrelated system build. Observing only PATH produces a
    false blocker exactly when a project has correctly pinned its runtime.
    """
    rows: list[dict[str, Any]] = []
    running = _run([sys.executable, "--version"], deadline)
    output = running.get("stdout") or running.get("stderr") or ""
    rows.append({
        "runtime": "python", "source": "running-interpreter",
        "status": running.get("status", "ERROR"), "executable": sys.executable,
        "version": output.splitlines()[0] if output else "",
        "returncode": running.get("returncode"),
    })
    path_python = shutil.which("python3")
    if path_python and Path(path_python).resolve() != Path(sys.executable).resolve():
        row = _runtime_observation("python", "python3", ["--version"], deadline)
        row["source"] = "path-python3"
        rows.append(row)
    return rows


def run_doctor(project_root: Path, activation: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    project_root = project_root.resolve()
    contract = activation.get("contract", {}) if isinstance(activation.get("contract"), dict) else {}
    budget = contract.get("budget", {}) if isinstance(contract.get("budget"), dict) else {}
    runtime_seconds = int(budget.get("runtime_seconds", 10))
    file_limit = int(budget.get("file_limit", 40))
    output_limit = int(budget.get("output_characters", 8000))
    deadline = started + runtime_seconds

    descriptors = _descriptor_paths(project_root, file_limit)
    relative_descriptors = [normalize_rel(path.relative_to(project_root)) for path in descriptors]
    needs_python = any(path.name in {".python-version", "pyproject.toml", "requirements.txt"} for path in descriptors)
    needs_node = any(path.name in {".nvmrc", "package.json"} for path in descriptors)
    needs_php = any(path.name == "composer.json" for path in descriptors)

    runtimes: dict[str, dict[str, Any]] = {}
    python_rows: list[dict[str, Any]] = []
    if needs_python:
        python_rows = _python_observations(deadline)
        primary = dict(python_rows[0])
        primary["candidates"] = python_rows
        runtimes["python"] = primary
    if needs_node:
        runtimes["node"] = _runtime_observation("node", "node", ["--version"], deadline)
    if needs_php:
        runtimes["php"] = _runtime_observation("php", "php", ["-v"], deadline)

    findings: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for runtime, row in runtimes.items():
        if row.get("status") == "MISSING":
            findings.append(_finding("warning", ".", f"Declared {runtime} project markers exist, but {runtime} is not available on PATH."))

    for path in descriptors:
        relative = normalize_rel(path.relative_to(project_root))
        text = _read_text(path)
        if path.name == ".python-version":
            declared = text.strip()
            expected = _exact_pin(declared)
            candidates = python_rows or [runtimes.get("python", {})]
            observed = runtimes.get("python", {}).get("version", "")
            match = None
            satisfied_by = None
            for candidate in candidates:
                candidate_match = _matches_prefix(_version_tuple(candidate.get("version", "")), expected)
                if candidate_match is True:
                    match, satisfied_by = True, candidate.get("source") or "path-python3"
                    observed = candidate.get("version", observed)
                    break
                if candidate_match is False and match is None:
                    match = False
            row = {
                "path": relative, "kind": "python-version", "declared": declared,
                "observed": observed, "exact_pin_evaluated": match is not None,
                "candidates": [
                    {"source": c.get("source"), "executable": c.get("executable"), "version": c.get("version")}
                    for c in candidates
                ],
            }
            if satisfied_by:
                row["satisfied_by"] = satisfied_by
            observations.append(row)
            if match is False:
                findings.append(_finding(
                    "blocker", relative,
                    "Exact Python version pin does not match any observed runtime.",
                    declared=declared,
                    observed="; ".join(
                        f"{c.get('source')}={c.get('version')}" for c in candidates if c.get("version")
                    ) or observed,
                ))
        elif path.name == ".nvmrc":
            declared = text.strip()
            expected = _exact_pin(declared)
            observed = runtimes.get("node", {}).get("version", "")
            actual = _version_tuple(observed)
            match = _matches_prefix(actual, expected)
            observations.append({"path": relative, "kind": "node-version", "declared": declared, "observed": observed, "exact_pin_evaluated": match is not None})
            if match is False:
                findings.append(_finding("blocker", relative, "Exact Node version pin does not match the observed runtime.", declared=declared, observed=observed))
        elif path.name == "package.json" and text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            engines = data.get("engines", {}) if isinstance(data, dict) else {}
            declared = str(engines.get("node", "")).strip() if isinstance(engines, dict) else ""
            if declared:
                expected = _exact_pin(declared)
                observed = runtimes.get("node", {}).get("version", "")
                match = _matches_prefix(_version_tuple(observed), expected)
                observations.append({"path": relative, "kind": "package-node-engine", "declared": declared, "observed": observed, "exact_pin_evaluated": match is not None})
                if match is False:
                    findings.append(_finding("blocker", relative, "Exact package.json Node engine pin does not match the observed runtime.", declared=declared, observed=observed))
        elif path.name == "composer.json" and text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            require = data.get("require", {}) if isinstance(data, dict) else {}
            if not isinstance(require, dict):
                continue
            declared_php = str(require.get("php", "")).strip()
            observed_php = runtimes.get("php", {}).get("version", "")
            if declared_php:
                expected = _exact_pin(declared_php)
                match = _matches_prefix(_version_tuple(observed_php), expected)
                observations.append({"path": relative, "kind": "composer-php", "declared": declared_php, "observed": observed_php, "exact_pin_evaluated": match is not None})
                if match is False:
                    findings.append(_finding("blocker", relative, "Exact Composer PHP version pin does not match the observed runtime.", declared=declared_php, observed=observed_php))
            required_extensions = sorted(key[4:].lower() for key in require if isinstance(key, str) and key.lower().startswith("ext-"))
            if required_extensions and runtimes.get("php", {}).get("status") != "MISSING":
                php_path = runtimes.get("php", {}).get("executable", "php")
                modules = _run([php_path, "-m"], deadline)
                installed = {line.strip().lower() for line in str(modules.get("stdout", "")).splitlines() if line.strip()}
                for extension in required_extensions:
                    if extension not in installed:
                        findings.append(_finding("blocker", relative, f"Required PHP extension is not present in the observed CLI runtime: {extension}."))
                observations.append({"path": relative, "kind": "composer-extensions", "declared": required_extensions, "observed_count": len(installed)})

    blocker_count = sum(1 for item in findings if item.get("severity") == "blocker")
    warning_count = sum(1 for item in findings if item.get("severity") == "warning")
    status = "FAIL" if blocker_count else "ATTENTION" if warning_count else "PASS"
    duration_ms = round((time.monotonic() - started) * 1000)
    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "capability_id": "doctor",
        "status": status,
        "mode": "diagnose-only",
        "claim": "Bounded environment diagnosis",
        "contract_source": activation.get("contract_source", ""),
        "contract_fingerprint": activation.get("contract_fingerprint", ""),
        "scope": contract.get("scope", {}),
        "native_advantage": contract.get("native_advantage", {}),
        "budget": {
            "runtime_seconds": runtime_seconds,
            "file_limit": file_limit,
            "output_characters": output_limit,
            "duration_ms": duration_ms,
            "descriptors_observed": len(descriptors),
            "budget_exhausted": time.monotonic() >= deadline,
        },
        "descriptors": relative_descriptors,
        "runtimes": runtimes,
        "observations": observations,
        "findings": findings,
        "actions_taken": [],
        "repairs_allowed": False,
        "legacy_vault_loaded": False,
        "excluded": [
            "automatic repair or installation",
            "production environment equivalence",
            "database state",
            "browser behavior",
            "deployment proof",
            "release assurance",
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) > output_limit:
        payload["observations"] = observations[:5]
        payload["descriptors"] = relative_descriptors[:10]
        payload["output_truncated"] = True
    else:
        payload["output_truncated"] = False
    return payload

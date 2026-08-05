from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .detect import is_forge_project
from .utils import iter_project_files, resolve_command, tree_fingerprint, utc_now, write_json


LAB_EVIDENCE_LEVELS = (
    "process-started",
    "connectivity-smoke",
    "content-readiness",
    "stateful-behavior",
    "environment-backed-behavior",
    "release-equivalent",
)


def default_lab_recipes(project_root: Path, adapters: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    if is_forge_project(project_root):
        recipes.extend([
            {
                "id": "forge-cli-smoke",
                "name": "Forge CLI lifecycle smoke",
                "enabled": True,
                "profiles": ["section"],
                "workspace": "copy",
                "evidence_level": "environment-backed-behavior",
                "evidence_boundary": "disposable-local-environment",
                "surfaces": ["all:cli", "all:entrypoint"],
                "prerequisites": {"executables": ["python"]},
                "setup": [
                    ["{python}", "{workspace}/forge.py", "adopt", "{workspace}", "--name", "Emotivus Forge Lab", "--preset", "prototype"],
                ],
                "start": [],
                "probes": [],
                "verify": [
                    {"command": ["{python}", "{workspace}/forge.py", "--version"], "surface": "forge.py"},
                    ["{python}", "{workspace}/forge.py", "resume", "{workspace}", "--budget", "compact"],
                    ["{python}", "{workspace}/forge.py", "check", "{workspace}", "--profile", "quick"],
                ],
                "teardown": [],
                "startup_timeout": 5,
                "command_timeout": 900,
                "preserve_on_failure": False,
                "include_deployignore": True,
            },
            {
                "id": "forge-docs-smoke",
                "name": "Forge human documentation readiness",
                "enabled": True,
                "profiles": ["release"],
                "workspace": "copy",
                "evidence_level": "content-readiness",
                "evidence_boundary": "disposable-local-environment",
                "surfaces": ["docs-site/index.html"],
                "prerequisites": {"executables": ["python"]},
                "setup": [],
                "start": ["{python}", "-m", "http.server", "{port}", "--bind", "127.0.0.1", "--directory", "{workspace}/docs-site"],
                "probes": [{
                    "url": "http://127.0.0.1:{port}/",
                    "surface": "docs-site/index.html",
                    "expected_status": [200],
                    "expected_content_type": "text/html",
                    "contains": ["Emotivus Forge", "Adopt", "Resume", "Check", "Ship"],
                    "min_bytes": 1000,
                }],
                "verify": [],
                "teardown": [],
                "startup_timeout": 12,
                "command_timeout": 120,
                "preserve_on_failure": False,
            },
            {
                "id": "forge-bootstrap-smoke",
                "name": "Independent Forge bootstrap validator",
                "enabled": True,
                "profiles": ["release"],
                "workspace": "copy",
                "evidence_level": "environment-backed-behavior",
                "evidence_boundary": "disposable-local-environment",
                "surfaces": ["tools/forge_bootstrap.py"],
                "prerequisites": {"executables": ["python"]},
                "setup": [],
                "start": [],
                "probes": [],
                "verify": [{"command": ["{python}", "{workspace}/tools/forge_bootstrap.py", "{workspace}", "--skip-self-test"], "surface": "tools/forge_bootstrap.py"}],
                "teardown": [],
                "startup_timeout": 5,
                "command_timeout": 300,
                "preserve_on_failure": False,
                "include_deployignore": True,
            },
        ])
    has_index_html = any((project_root / name).is_file() for name in ("index.html", "public/index.html"))
    has_index_php = any((project_root / name).is_file() for name in ("index.php", "public/index.php"))
    if has_index_html:
        directory = "{workspace}/public" if (project_root / "public" / "index.html").is_file() else "{workspace}"
        recipes.append({
            "id": "static-smoke",
            "name": "Static HTTP connectivity smoke",
            "enabled": True,
            "profiles": [],
            "workspace": "copy",
            "evidence_level": "connectivity-smoke",
            "evidence_boundary": "disposable-local-environment",
            "surfaces": ["index.html" if directory == "{workspace}" else "public/index.html"],
            "prerequisites": {"executables": ["python"]},
            "setup": [],
            "start": ["{python}", "-m", "http.server", "{port}", "--bind", "127.0.0.1", "--directory", directory],
            "probes": [{"url": "http://127.0.0.1:{port}/", "expected_status": [200], "surface": "index.html" if directory == "{workspace}" else "public/index.html"}],
            "verify": [],
            "teardown": [],
            "startup_timeout": 12,
            "command_timeout": 120,
            "preserve_on_failure": False,
        })
    if "php" in adapters and has_index_php:
        document_root = "{workspace}/public" if (project_root / "public" / "index.php").is_file() else "{workspace}"
        recipes.append({
            "id": "php-smoke",
            "name": "PHP HTTP connectivity smoke",
            "enabled": True,
            "profiles": [],
            "workspace": "copy",
            "evidence_level": "connectivity-smoke",
            "evidence_boundary": "disposable-local-environment",
            "surfaces": ["index.php" if document_root == "{workspace}" else "public/index.php"],
            "prerequisites": {"executables": ["php"]},
            "setup": [],
            "start": ["{php}", "-S", "127.0.0.1:{port}", "-t", document_root],
            "probes": [{"url": "http://127.0.0.1:{port}/", "expected_status": [200, 301, 302], "surface": "index.php" if document_root == "{workspace}" else "public/index.php"}],
            "verify": [],
            "teardown": [],
            "startup_timeout": 15,
            "command_timeout": 120,
            "preserve_on_failure": False,
        })
    return recipes


def plan_labs(project_root: Path, config: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
    lab = config.get("lab", {})
    recipes = [item for item in lab.get("recipes", []) if isinstance(item, dict)]
    payload = {
        "schema": 2,
        "generated_utc": utc_now(),
        "project": config.get("project", {}).get("name", project_root.name),
        "enabled": bool(lab.get("enabled", True)),
        "required_profiles": list(lab.get("required_profiles", [])),
        "recipes": recipes,
        "capabilities": {
            "disposable_workspace": True,
            "http_probes": True,
            "content_assertions": True,
            "negative_body_assertions": True,
            "header_and_content_type_assertions": True,
            "readiness_fingerprints": True,
            "stateful_http_journeys": True,
            "cookie_and_capture_state": True,
            "prerequisite_contracts": True,
            "setup_commands": True,
            "verification_commands": True,
            "teardown_commands": True,
            "container_orchestration": any("docker" in " ".join(item.get("start", [])).lower() for item in recipes),
        },
    }
    if write:
        output_dir = project_root / lab.get("output_dir", ".forge/lab")
        write_json(output_dir / "lab-plan.json", payload)
        _write_plan_markdown(output_dir / "lab-plan.md", payload)
    return payload


def _write_plan_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Forge Lab Plan", "",
        f"- Project: {payload['project']}",
        f"- Enabled: {'yes' if payload['enabled'] else 'no'}",
        f"- Required profiles: {', '.join(payload['required_profiles']) or 'none'}", "",
        "## Recipes", "",
    ]
    for recipe in payload["recipes"]:
        lines.extend([
            f"### {recipe.get('name', recipe.get('id', 'Unnamed recipe'))}",
            f"- ID: `{recipe.get('id', '')}`",
            f"- Enabled: {'yes' if recipe.get('enabled', True) else 'no'}",
            f"- Profiles: {', '.join(recipe.get('profiles', [])) or 'manual only'}",
            f"- Workspace: {recipe.get('workspace', 'copy')}",
            f"- Evidence level: `{_recipe_evidence_level(recipe)}`",
            f"- Evidence boundary: `{recipe.get('evidence_boundary', 'disposable-local-environment')}`",
            f"- Prerequisites: {_prerequisite_count(recipe.get('prerequisites', {}))}",
            f"- HTTP readiness probes: {len(recipe.get('probes', []))}",
            f"- Stateful journey steps: {len(recipe.get('journey', []))}",
            f"- Verification commands: {len(recipe.get('verify', []))}", "",
        ])
    if not payload["recipes"]:
        lines.append("No safe automatic recipe was inferred. Add a project-specific recipe to `.emotivus-forge.json`.")
    lines.extend([
        "",
        "A status-only HTTP probe proves connectivity, not application readiness. Add content, header, JSON, or stateful journey assertions before using a recipe as behavioral evidence.",
        "Forge Lab uses disposable workspaces by default. It does not claim production equivalence; production-host, provider, and real-data checks remain separate release evidence.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _expand(command: list[str], *, project_root: Path, forge_root: Path, workspace: Path, port: int) -> list[str]:
    resolved = resolve_command(command, project=project_root, forge=forge_root)
    replacements = {"{workspace}": str(workspace), "{port}": str(port)}
    return [_multi_replace(part, replacements) for part in resolved]


def _multi_replace(value: str, replacements: dict[str, str]) -> str:
    for key, replacement in replacements.items():
        value = value.replace(key, replacement)
    return value


def _state_replace(value: Any, state: dict[str, str]) -> Any:
    if isinstance(value, str):
        return re.sub(r"\{state:([A-Za-z0-9_.-]+)\}", lambda match: state.get(match.group(1), match.group(0)), value)
    if isinstance(value, list):
        return [_state_replace(item, state) for item in value]
    if isinstance(value, dict):
        return {str(key): _state_replace(item, state) for key, item in value.items()}
    return value


def _copy_workspace(project_root: Path, forge_root: Path, config: dict[str, Any], destination: Path, *, include_deployignore: bool = False) -> int:
    internal_excludes = [
        ".forge", ".git", "deploy", ".emotivus-forge.json", "FORGE-AGENT.md",
        "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ]
    if not include_deployignore:
        internal_excludes.append(".deployignore")
    excludes = list(config.get("paths", {}).get("exclude", [])) + internal_excludes
    copied = 0
    for source in iter_project_files(project_root, excludes, forge_root):
        relative = source.relative_to(project_root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            raise RuntimeError(f"Forge Lab refuses symbolic link: {relative.as_posix()}")
        shutil.copy2(source, target)
        copied += 1
    return copied


def _run_command(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.run(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return {"command": command, "returncode": process.returncode, "status": "PASS" if process.returncode == 0 else "FAIL", "duration_seconds": round(time.monotonic() - started, 3), "output": process.stdout.rstrip()}
    except subprocess.TimeoutExpired as exc:
        return {"command": command, "returncode": None, "status": "TIMEOUT", "duration_seconds": round(time.monotonic() - started, 3), "output": (exc.stdout or "") + "\nCommand timed out."}
    except OSError as exc:
        return {"command": command, "returncode": None, "status": "RUNNER_ERROR", "duration_seconds": round(time.monotonic() - started, 3), "output": str(exc)}


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _surface_values(spec: Any) -> list[str]:
    if not isinstance(spec, dict):
        return []
    raw = spec.get("surfaces", spec.get("surface", []))
    return sorted({item.strip().replace("\\", "/") for item in _list_value(raw) if item.strip()})


def _json_path_value(payload: Any, path: str) -> tuple[bool, Any]:
    current = payload
    if not path:
        return True, current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def _assertion(kind: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"kind": kind, "status": "PASS" if passed else "FAIL", "detail": detail}


def _assert_response(spec: dict[str, Any], *, status: int | None, headers: dict[str, str], body: bytes, final_url: str) -> tuple[list[dict[str, Any]], Any | None]:
    assertions: list[dict[str, Any]] = []
    expected = [int(value) for value in spec.get("expected_status", [200])]
    assertions.append(_assertion("status", status in expected, f"expected {expected}; received {status}"))

    charset = "utf-8"
    content_type_raw = headers.get("content-type", "")
    match = re.search(r"charset=([^;\s]+)", content_type_raw, flags=re.I)
    if match:
        charset = match.group(1).strip('"\'')
    text = body.decode(charset, errors="replace")

    for needle in _list_value(spec.get("contains")):
        assertions.append(_assertion("body_contains", needle in text, f"body contains {needle!r}"))
    for needle in _list_value(spec.get("not_contains")):
        assertions.append(_assertion("body_not_contains", needle not in text, f"body excludes {needle!r}"))
    for pattern in _list_value(spec.get("body_regex")):
        try:
            passed = re.search(pattern, text, flags=re.S) is not None
        except re.error:
            passed = False
        assertions.append(_assertion("body_regex", passed, f"body matches /{pattern}/"))
    for pattern in _list_value(spec.get("not_body_regex")):
        try:
            passed = re.search(pattern, text, flags=re.S) is None
        except re.error:
            passed = False
        assertions.append(_assertion("body_not_regex", passed, f"body does not match /{pattern}/"))

    if "min_bytes" in spec:
        minimum = int(spec.get("min_bytes", 0))
        assertions.append(_assertion("minimum_body_bytes", len(body) >= minimum, f"body bytes {len(body)} >= {minimum}"))
    if "max_bytes" in spec:
        maximum = int(spec.get("max_bytes", 0))
        assertions.append(_assertion("maximum_body_bytes", len(body) <= maximum, f"body bytes {len(body)} <= {maximum}"))

    expected_types = [item.lower() for item in _list_value(spec.get("expected_content_type"))]
    if expected_types:
        actual_type = content_type_raw.split(";", 1)[0].strip().lower()
        assertions.append(_assertion("content_type", actual_type in expected_types, f"expected {expected_types}; received {actual_type!r}"))

    required_headers = spec.get("required_headers", {})
    if isinstance(required_headers, dict):
        for key, expected_value in required_headers.items():
            actual = headers.get(str(key).lower())
            allowed = _list_value(expected_value)
            passed = actual is not None and (not allowed or any(value.lower() in actual.lower() for value in allowed))
            assertions.append(_assertion("required_header", passed, f"header {key!r} contains one of {allowed!r}"))
    for key in _list_value(spec.get("forbidden_headers")):
        assertions.append(_assertion("forbidden_header", key.lower() not in headers, f"header {key!r} is absent"))

    expected_final = str(spec.get("expected_final_url", "")).strip()
    if expected_final:
        assertions.append(_assertion("final_url", final_url == expected_final, f"expected {expected_final!r}; received {final_url!r}"))

    json_payload: Any | None = None
    json_assertions = spec.get("json_assertions", [])
    if json_assertions:
        try:
            json_payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            assertions.append(_assertion("json_parse", False, "response body is valid JSON"))
        else:
            assertions.append(_assertion("json_parse", True, "response body is valid JSON"))
            for rule in json_assertions:
                if not isinstance(rule, dict):
                    continue
                path = str(rule.get("path", ""))
                found, value = _json_path_value(json_payload, path)
                passed = found
                detail = f"JSON path {path!r} exists"
                if "equals" in rule:
                    passed = found and value == rule.get("equals")
                    detail = f"JSON path {path!r} equals {rule.get('equals')!r}"
                elif "contains" in rule:
                    expected_value = rule.get("contains")
                    passed = found and expected_value in value if isinstance(value, (list, str, dict)) else False
                    detail = f"JSON path {path!r} contains {expected_value!r}"
                elif "min_length" in rule:
                    minimum = int(rule.get("min_length", 0))
                    passed = found and hasattr(value, "__len__") and len(value) >= minimum
                    detail = f"JSON path {path!r} length >= {minimum}"
                assertions.append(_assertion("json_value", bool(passed), detail))
    return assertions, json_payload


def _request_payload(spec: dict[str, Any]) -> tuple[bytes | None, dict[str, str], str]:
    headers = {str(key): str(value) for key, value in spec.get("request_headers", {}).items()} if isinstance(spec.get("request_headers", {}), dict) else {}
    method = str(spec.get("method", "")).upper()
    data: bytes | None = None
    if "json" in spec:
        data = json.dumps(spec.get("json"), separators=(",", ":")).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
        method = method or "POST"
    elif "form" in spec and isinstance(spec.get("form"), dict):
        data = urllib.parse.urlencode({str(key): str(value) for key, value in spec["form"].items()}).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        method = method or "POST"
    elif "body" in spec:
        raw = spec.get("body", "")
        data = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
        method = method or "POST"
    return data, headers, method or "GET"


def _probe(spec: dict[str, Any], timeout: int, opener: urllib.request.OpenerDirector | None = None) -> tuple[dict[str, Any], Any | None, str]:
    started = time.monotonic()
    url = str(spec.get("url", ""))
    max_body_bytes = max(1, int(spec.get("max_body_read_bytes", 1_048_576)))
    data, request_headers, method = _request_payload(spec)
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    active_opener = opener or urllib.request.build_opener()
    status: int | None = None
    headers: dict[str, str] = {}
    body = b""
    final_url = url
    error = ""
    try:
        with active_opener.open(request, timeout=timeout) as response:
            status = int(response.status)
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            body = response.read(max_body_bytes + 1)
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        headers = {str(key).lower(): str(value) for key, value in exc.headers.items()}
        body = exc.read(max_body_bytes + 1)
        final_url = exc.geturl()
        error = str(exc)
    except Exception as exc:
        return ({
            "url": url,
            "method": method,
            "status_code": None,
            "status": "FAIL",
            "evidence_level": _probe_evidence_level(spec),
            "duration_seconds": round(time.monotonic() - started, 3),
            "bytes_received": 0,
            "body_truncated": False,
            "body_sha256": "",
            "readiness_fingerprint": "",
            "content_type": "",
            "final_url": url,
            "headers_observed": [],
            "assertions": [],
            "error": str(exc),
        }, None, "")

    truncated = len(body) > max_body_bytes
    if truncated:
        body = body[:max_body_bytes]
    assertions, json_payload = _assert_response(spec, status=status, headers=headers, body=body, final_url=final_url)
    passed = all(item["status"] == "PASS" for item in assertions)
    body_sha256 = hashlib.sha256(body).hexdigest()
    fingerprint_source = json.dumps({
        "status": status,
        "content_type": headers.get("content-type", ""),
        "body_sha256": body_sha256,
        "final_url": final_url,
        "assertions": [(item["kind"], item["status"]) for item in assertions],
    }, sort_keys=True).encode("utf-8")
    readiness_fingerprint = hashlib.sha256(fingerprint_source).hexdigest()
    return ({
        "url": url,
        "method": method,
        "status_code": status,
        "status": "PASS" if passed else "FAIL",
        "evidence_level": _probe_evidence_level(spec),
        "duration_seconds": round(time.monotonic() - started, 3),
        "bytes_received": len(body),
        "body_truncated": truncated,
        "body_sha256": body_sha256,
        "readiness_fingerprint": readiness_fingerprint,
        "content_type": headers.get("content-type", ""),
        "final_url": final_url,
        "headers_observed": sorted(headers),
        "assertions": assertions,
        "error": error,
    }, json_payload, body.decode("utf-8", errors="replace"))


def _probe_evidence_level(spec: dict[str, Any]) -> str:
    assertion_keys = {
        "contains", "not_contains", "body_regex", "not_body_regex", "min_bytes", "max_bytes",
        "expected_content_type", "required_headers", "forbidden_headers", "expected_final_url", "json_assertions",
    }
    return "content-readiness" if any(key in spec for key in assertion_keys) else "connectivity-smoke"


def _recipe_evidence_level(recipe: dict[str, Any]) -> str:
    if recipe.get("journey"):
        inferred = "stateful-behavior"
    else:
        probes = [item for item in recipe.get("probes", []) if isinstance(item, dict)]
        if probes and all(_probe_evidence_level(item) == "content-readiness" for item in probes):
            inferred = "content-readiness"
        elif probes:
            inferred = "connectivity-smoke"
        elif recipe.get("verify"):
            inferred = "environment-backed-behavior"
        else:
            inferred = "process-started"
    explicit = str(recipe.get("evidence_level", "")).strip()
    rank = {level: index for index, level in enumerate(LAB_EVIDENCE_LEVELS)}
    if explicit == "release-equivalent" and recipe.get("release_equivalent") is True and rank.get(inferred, -1) >= rank["content-readiness"]:
        return explicit
    if explicit in rank and rank[explicit] <= rank.get(inferred, 0):
        return explicit
    return inferred


def _prerequisite_count(prerequisites: Any) -> int:
    if not isinstance(prerequisites, dict):
        return 0
    total = 0
    for key in ("executables", "env", "files", "services"):
        value = prerequisites.get(key, [])
        if isinstance(value, list):
            total += len(value)
    return total


def _check_prerequisites(project_root: Path, prerequisites: Any, environment: dict[str, str] | None = None) -> list[dict[str, Any]]:
    if not isinstance(prerequisites, dict):
        return []
    results: list[dict[str, Any]] = []
    active_environment = environment or dict(os.environ)
    for name in _list_value(prerequisites.get("executables")):
        resolved_name = sys_executable_name(name)
        found = shutil.which(resolved_name) is not None
        results.append({"kind": "executable", "name": name, "status": "PASS" if found else "BLOCKED", "detail": f"{resolved_name} {'available' if found else 'not found'}"})
    for name in _list_value(prerequisites.get("env")):
        found = bool(active_environment.get(name))
        results.append({"kind": "environment", "name": name, "status": "PASS" if found else "BLOCKED", "detail": f"environment variable {name} {'present' if found else 'missing'}"})
    for relative in _list_value(prerequisites.get("files")):
        found = (project_root / relative).exists()
        results.append({"kind": "file", "name": relative, "status": "PASS" if found else "BLOCKED", "detail": f"required path {relative} {'present' if found else 'missing'}"})
    for service in prerequisites.get("services", []) if isinstance(prerequisites.get("services", []), list) else []:
        if not isinstance(service, dict):
            continue
        host = str(service.get("host", "127.0.0.1"))
        port = int(service.get("port", 0))
        name = str(service.get("name", f"{host}:{port}"))
        timeout = float(service.get("timeout", 1.0))
        available = False
        detail = "invalid service port"
        if port > 0:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    available = True
                detail = f"service {host}:{port} reachable"
            except OSError as exc:
                detail = f"service {host}:{port} unavailable: {exc}"
        results.append({"kind": "service", "name": name, "status": "PASS" if available else "BLOCKED", "detail": detail})
    return results


def sys_executable_name(name: str) -> str:
    if name == "python":
        return Path(os.sys.executable).name
    return name


def _capture_state(captures: Any, *, text: str, json_payload: Any | None, state: dict[str, str]) -> tuple[list[str], list[str]]:
    captured: list[str] = []
    failures: list[str] = []
    if not isinstance(captures, dict):
        return captured, failures
    for name, rule in captures.items():
        value: Any = None
        found = False
        if isinstance(rule, str):
            match = re.search(rule, text, flags=re.S)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                found = True
        elif isinstance(rule, dict) and "regex" in rule:
            try:
                match = re.search(str(rule.get("regex", "")), text, flags=re.S)
            except re.error:
                match = None
            if match:
                group = int(rule.get("group", 1 if match.groups() else 0))
                value = match.group(group)
                found = True
        elif isinstance(rule, dict) and "json_path" in rule and json_payload is not None:
            found, value = _json_path_value(json_payload, str(rule.get("json_path", "")))
        if found:
            state[str(name)] = str(value)
            captured.append(str(name))
        else:
            failures.append(str(name))
    return captured, failures


def _run_journey(steps: Any, *, port: int, workspace: Path, timeout: int, initial_state: Any = None) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    results: list[dict[str, Any]] = []
    state = {str(key): str(value) for key, value in initial_state.items()} if isinstance(initial_state, dict) else {}
    errors: list[str] = []
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    for index, raw in enumerate(steps if isinstance(steps, list) else []):
        if not isinstance(raw, dict):
            continue
        spec = _state_replace(raw, state)
        spec["url"] = _multi_replace(str(spec.get("url", "")), {"{port}": str(port), "{workspace}": str(workspace)})
        result, json_payload, text = _probe(spec, timeout, opener)
        result["step_id"] = str(raw.get("id", f"step-{index + 1}"))
        result["surface_attestations"] = _surface_values(raw)
        captured, capture_failures = _capture_state(raw.get("capture", {}), text=text, json_payload=json_payload, state=state)
        result["captured_state"] = captured
        if capture_failures:
            result["status"] = "FAIL"
            result["capture_failures"] = capture_failures
        results.append(result)
        if result["status"] != "PASS":
            errors.append(f"journey step failed: {result['step_id']}")
            break
    return results, state, errors


def run_lab(project_root: Path, forge_root: Path, config: dict[str, Any], recipe_id: str, *, preserve: bool | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    lab = config.get("lab", {})
    recipe = next((item for item in lab.get("recipes", []) if isinstance(item, dict) and item.get("id") == recipe_id), None)
    if recipe is None:
        raise RuntimeError(f"unknown Forge Lab recipe: {recipe_id}")
    if not recipe.get("enabled", True):
        raise RuntimeError(f"Forge Lab recipe is disabled: {recipe_id}")

    workspace = Path(tempfile.mkdtemp(prefix=f"forge-lab-{recipe_id}-"))
    port = _free_port()
    env = dict(os.environ)
    env.update({"FORGE_LAB": "1", "FORGE_LAB_PORT": str(port), "FORGE_LAB_WORKSPACE": str(workspace)})
    env.update({str(key): str(value) for key, value in recipe.get("env", {}).items()})
    started_utc = utc_now()
    process: subprocess.Popen[str] | None = None
    service_log = None
    service_log_path = ""
    prerequisite_results = _check_prerequisites(project_root, recipe.get("prerequisites", {}), env)
    setup_results: list[dict[str, Any]] = []
    verify_results: list[dict[str, Any]] = []
    probe_results: list[dict[str, Any]] = []
    journey_results: list[dict[str, Any]] = []
    teardown_results: list[dict[str, Any]] = []
    errors: list[str] = []
    copied = 0
    preserve_failure = recipe.get("preserve_on_failure", False) if preserve is None else preserve
    blocked = any(item["status"] == "BLOCKED" for item in prerequisite_results)
    if blocked:
        errors.append("one or more Lab prerequisites are unavailable")

    try:
        if not blocked:
            if recipe.get("workspace", "copy") == "copy":
                copied = _copy_workspace(project_root, forge_root, config, workspace, include_deployignore=bool(recipe.get("include_deployignore", False)))
            else:
                shutil.rmtree(workspace)
                workspace = project_root

            for raw in recipe.get("setup", []):
                if not isinstance(raw, list) or not raw:
                    continue
                result = _run_command(_expand([str(item) for item in raw], project_root=project_root, forge_root=forge_root, workspace=workspace, port=port), workspace, env, int(recipe.get("command_timeout", 120)))
                setup_results.append(result)
                if result["status"] != "PASS":
                    errors.append("setup command failed")
                    break

            start = recipe.get("start")
            if not errors and isinstance(start, list) and start:
                command = _expand([str(item) for item in start], project_root=project_root, forge_root=forge_root, workspace=workspace, port=port)
                try:
                    service_log = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False, prefix="forge-lab-service-", suffix=".log")
                    service_log_path = service_log.name
                    process = subprocess.Popen(command, cwd=workspace, env=env, text=True, stdout=service_log, stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as exc:
                    errors.append(f"could not start lab service: {exc}")

            if not errors:
                deadline = time.monotonic() + int(recipe.get("startup_timeout", 15))
                probes = [item for item in recipe.get("probes", []) if isinstance(item, dict)]
                if probes:
                    pending = list(enumerate(probes))
                    latest: dict[int, dict[str, Any]] = {}
                    while pending and time.monotonic() < deadline:
                        next_pending: list[tuple[int, dict[str, Any]]] = []
                        for original_index, item in pending:
                            spec = _state_replace(item, {})
                            spec["url"] = _multi_replace(str(spec.get("url", "")), {"{port}": str(port), "{workspace}": str(workspace)})
                            result, _, _ = _probe(spec, min(3, max(1, int(deadline - time.monotonic()))))
                            result["surface_attestations"] = _surface_values(item)
                            latest[original_index] = result
                            if result["status"] != "PASS":
                                next_pending.append((original_index, item))
                        pending = next_pending
                        if pending:
                            if process is not None and process.poll() is not None:
                                break
                            time.sleep(0.25)
                    probe_results = [latest[index] for index in sorted(latest)]
                    if pending:
                        errors.append("one or more HTTP readiness probes failed")
                elif process is not None:
                    time.sleep(0.5)
                    if process.poll() is not None and process.returncode != 0:
                        errors.append("lab service exited before verification")

            if not errors and recipe.get("journey"):
                journey_results, journey_state, journey_errors = _run_journey(
                    recipe.get("journey", []),
                    port=port,
                    workspace=workspace,
                    timeout=int(recipe.get("request_timeout", 10)),
                    initial_state=recipe.get("state", {}),
                )
                errors.extend(journey_errors)
            else:
                journey_state = {}

            if not errors:
                for raw in recipe.get("verify", []):
                    if isinstance(raw, dict):
                        command_raw = raw.get("command", [])
                        attestations = _surface_values(raw)
                    else:
                        command_raw = raw
                        attestations = []
                    if not isinstance(command_raw, list) or not command_raw:
                        continue
                    result = _run_command(_expand([str(item) for item in command_raw], project_root=project_root, forge_root=forge_root, workspace=workspace, port=port), workspace, env, int(recipe.get("command_timeout", 120)))
                    result["surface_attestations"] = attestations
                    verify_results.append(result)
                    if result["status"] != "PASS":
                        errors.append("verification command failed")
                        break
        else:
            journey_state = {}
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        if not blocked:
            for raw in recipe.get("teardown", []):
                if isinstance(raw, list) and raw:
                    teardown_results.append(_run_command(_expand([str(item) for item in raw], project_root=project_root, forge_root=forge_root, workspace=workspace, port=port), workspace, env, int(recipe.get("command_timeout", 120))))

    all_results = setup_results + verify_results + probe_results + journey_results + teardown_results
    if blocked:
        status = "BLOCKED"
    else:
        status = "PASS" if not errors and all(item["status"] == "PASS" for item in all_results) else "FAIL"
    service_output = ""
    if service_log is not None:
        try:
            service_log.flush()
            service_log.seek(0)
            service_output = service_log.read(20_000)
        except Exception:
            service_output = ""
        finally:
            service_log.close()
            if service_log_path:
                try:
                    Path(service_log_path).unlink()
                except OSError:
                    pass
    surface_attestations = sorted({
        token
        for item in probe_results + journey_results + verify_results
        if item.get("status") == "PASS"
        for token in item.get("surface_attestations", [])
        if str(token).strip()
    })
    payload = {
        "schema": 2,
        "forge": "Emotivus Forge",
        "recipe_id": recipe_id,
        "recipe_name": recipe.get("name", recipe_id),
        "status": status,
        "declared_evidence_level": str(recipe.get("evidence_level", "")),
        "evidence_level": _recipe_evidence_level(recipe),
        "evidence_boundary": recipe.get("evidence_boundary", "disposable-local-environment"),
        "surfaces": [str(item) for item in recipe.get("surfaces", [])] if isinstance(recipe.get("surfaces", []), list) else [],
        "surface_attestations": surface_attestations,
        "recipe_fingerprint": hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "tree_fingerprint": tree_fingerprint(project_root, config.get("paths", {}).get("exclude", []), forge_root),
        "claim": _claim_for_level(_recipe_evidence_level(recipe)),
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "workspace": str(workspace),
        "workspace_mode": recipe.get("workspace", "copy"),
        "files_copied": copied,
        "port": port,
        "prerequisite_results": prerequisite_results,
        "setup_results": setup_results,
        "probe_results": probe_results,
        "journey_results": journey_results,
        "journey_state_keys": sorted(journey_state),
        "verify_results": verify_results,
        "teardown_results": teardown_results,
        "service_output": service_output.rstrip(),
        "errors": errors,
        "workspace_preserved": bool(status not in {"PASS", "BLOCKED"} and preserve_failure and workspace != project_root),
    }
    output_dir = project_root / lab.get("output_dir", ".forge/lab") / "reports"
    stamp = started_utc.replace(":", "").replace("-", "").replace("+00:00", "Z")
    report_path = output_dir / f"{recipe_id}-{stamp}.json"
    write_json(report_path, payload)
    _write_lab_report(report_path.with_suffix(".txt"), payload)
    write_json(output_dir / f"{recipe_id}-latest.json", payload)

    if workspace != project_root and not payload["workspace_preserved"]:
        shutil.rmtree(workspace, ignore_errors=True)
        payload["workspace"] = "removed"
    return payload


def _claim_for_level(level: str) -> str:
    claims = {
        "process-started": "The declared process started; no application readiness claim was made.",
        "connectivity-smoke": "The declared endpoint was reachable with an expected transport status; application readiness was not proven.",
        "content-readiness": "The endpoint returned the expected status and declared content/readiness assertions.",
        "stateful-behavior": "The declared ordered journey passed with shared HTTP state and response assertions.",
        "environment-backed-behavior": "The declared behavior passed in an environment whose listed prerequisites were present.",
        "release-equivalent": "The declared behavior passed in a project-approved release-equivalent environment.",
    }
    return claims.get(level, claims["process-started"])


def _write_lab_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"Emotivus Forge Lab — {payload['recipe_name']}", "=" * 64,
        f"Status: {payload['status']}",
        f"Evidence level: {payload['evidence_level']}",
        f"Evidence boundary: {payload['evidence_boundary']}",
        f"Claim: {payload['claim']}",
        f"Workspace mode: {payload['workspace_mode']}",
        f"Files copied: {payload['files_copied']}",
        f"Workspace preserved: {payload['workspace_preserved']}", "",
    ]
    for label, key in (
        ("Prerequisites", "prerequisite_results"),
        ("Setup", "setup_results"),
        ("HTTP readiness probes", "probe_results"),
        ("Stateful journey", "journey_results"),
        ("Verification", "verify_results"),
        ("Teardown", "teardown_results"),
    ):
        lines.append(label)
        lines.append("-" * len(label))
        items = payload[key]
        if not items:
            lines.append("None")
        for item in items:
            subject = item.get("url") or item.get("name") or " ".join(item.get("command", []))
            lines.append(f"{item['status']}: {subject}")
            if item.get("evidence_level"):
                lines.append(f"Evidence: {item['evidence_level']}")
            for assertion in item.get("assertions", []):
                lines.append(f"  {assertion['status']} {assertion['kind']}: {assertion['detail']}")
            if item.get("output"):
                lines.append(item["output"])
            if item.get("detail"):
                lines.append(item["detail"])
            if item.get("error"):
                lines.append(item["error"])
        lines.append("")
    if payload["errors"]:
        lines.extend(["Errors", "------"] + [f"- {item}" for item in payload["errors"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_required_labs(project_root: Path, forge_root: Path, config: dict[str, Any], profile: str) -> tuple[bool, str]:
    lab = config.get("lab", {})
    recipe_ids = [
        str(item.get("id")) for item in lab.get("recipes", [])
        if isinstance(item, dict) and item.get("enabled", True) and profile in item.get("profiles", [])
    ]
    if profile in lab.get("required_profiles", []) and not recipe_ids:
        return False, f"Forge Lab is required for {profile}, but no enabled recipe is assigned to that profile."
    if not recipe_ids:
        return True, "No Forge Lab recipes are required for this profile."
    lines: list[str] = []
    all_ok = True
    minimum_by_profile = lab.get("minimum_evidence_by_profile", {})
    required_level = str(minimum_by_profile.get(profile, "process-started"))
    rank = {level: index for index, level in enumerate(LAB_EVIDENCE_LEVELS)}
    for recipe_id in recipe_ids:
        result = run_lab(project_root, forge_root, config, recipe_id)
        evidence_ok = rank.get(result["evidence_level"], -1) >= rank.get(required_level, 0)
        recipe_ok = result["status"] == "PASS" and evidence_ok
        all_ok = all_ok and recipe_ok
        visible_status = result["status"] if evidence_ok else "BLOCKED"
        lines.append(
            f"{visible_status} {recipe_id}: evidence={result['evidence_level']} (minimum={required_level}), "
            f"probes={len(result['probe_results'])}, journey={len(result['journey_results'])}, verify={len(result['verify_results'])}"
        )
        if not evidence_ok:
            lines.append(
                f"  Lab evidence is too weak for the {profile} profile: {result['evidence_level']} cannot satisfy {required_level}."
            )
        lines.extend(f"  {error}" for error in result["errors"])
        if not recipe_ok:
            break
    return all_ok, "\n".join(lines)

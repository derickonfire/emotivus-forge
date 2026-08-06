from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graph import build_graph, load_graph
from .runtime_contracts import load_runtime_contracts
from .utils import resolve_command, sha256_file, tree_fingerprint, utc_now, write_json

CLAIM_LEVELS = (
    "source-verified",
    "package-verified",
    "entrypoints-executed",
    "upgrade-verified",
    "target-environment-verified",
    "delivery-verified",
    "staging-accepted",
    "production-observed",
)

EVIDENCE_TYPES = {
    "static",
    "unit",
    "integration",
    "entrypoint-execution",
    "browser-behavior",
    "database-upgrade",
    "target-environment",
    "package",
    "delivery-provenance",
    "staging",
    "production-observation",
}

EXECUTION_EVIDENCE = {"entrypoint-execution", "browser-behavior", "integration"}
DELIVERABLE_PATTERNS = (
    "*.zip", "*.tar", "*.tar.gz", "*.tgz", "*.7z",
    "HANDOVER.md", "README-FIRST.md", "README-FIRST.txt",
    "*-CONTEXT.txt", "*-PROJECT-INSTRUCTIONS.txt", "Forge-State*.zip",
)

EXCLUDED_SURFACE_DIRS = {
    ".forge", ".git", "emotivus-forge", "vendor", "node_modules", "tests", "test",
    "tools", "scripts", "migrations", "migration", "includes", "include", "lib", "vendor",
    "cache", "storage", "backups", "backup", "docs", "documentation", "fixtures",
}

NON_EXECUTABLE_ASSET_DIRS = {
    "assets", "asset", "static", "styles", "style", "css", "images", "image",
    "fonts", "font", "media", "icons", "icon", "dist", "build", "coverage",
}

WEB_ROOT_DIRS = {"admin", "public", "api", "pages", "routes", "web", "www", "htdocs"}
WEBHOOK_DIRS = {"webhook", "webhooks", "hook", "hooks", "callback", "callbacks", "receiver", "receivers"}
JOB_DIRS = {"job", "jobs", "cron", "crons", "scheduler", "scheduled", "worker", "workers", "queue", "queues"}
CLI_DIRS = {"bin", "cli", "console", "command", "commands"}
PHP_SUPPORT_NAMES = {
    "autoload.php", "bootstrap.php", "common.php", "config.php", "constants.php",
    "db.php", "database.php", "functions.php", "helpers.php", "init.php",
}


def _hash_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _matches(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/")
    pattern = pattern.strip().replace("\\", "/")
    if not pattern:
        return False
    if pattern.startswith("all:"):
        return False
    return fnmatch.fnmatchcase(path, pattern) or path == pattern or path.startswith(pattern.rstrip("/") + "/")


def _surface_id(kind: str, path: str, name: str = "") -> str:
    raw = f"{kind}\0{path}\0{name}"
    return f"surface:{kind}:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _looks_like_php_surface(relative: str, text: str) -> bool:
    path = Path(relative)
    if path.suffix.lower() not in {".php", ".phtml"}:
        return False
    lower_parts = [part.lower() for part in path.parts[:-1]]
    if any(part in EXCLUDED_SURFACE_DIRS for part in lower_parts):
        return False
    name = path.name.lower()
    if name.startswith(("migrate", "migration", "class.", "interface.", "trait.")):
        return False
    if len(path.parts) > 1 and name in PHP_SUPPORT_NAMES and (not lower_parts or lower_parts[0] not in WEB_ROOT_DIRS):
        return False
    lowered = text[:200_000].lower()
    runtime_markers = (
        "<!doctype", "<html", "<form", "<main", "<body", "header(", "$_get", "$_post",
        "session_start", "json_encode", "http_response_code", "require_login", "require_permission",
    )
    # Root and common web directories are executable by default. Nested PHP elsewhere
    # needs an observable request/response marker.
    return len(path.parts) == 1 or (lower_parts and lower_parts[0] in WEB_ROOT_DIRS) or any(token in lowered for token in runtime_markers)


def _php_surface_kind(relative: str, text: str) -> str:
    path = Path(relative)
    if path.suffix.lower() not in {".php", ".phtml"}:
        return ""
    lower_parts = [part.lower() for part in path.parts[:-1]]
    name = path.name.lower()
    lowered_name = f"{relative} {name}".lower()
    if any(part in WEBHOOK_DIRS for part in lower_parts) or any(token in lowered_name for token in ("webhook", "callback", "inbound", "receiver")):
        return "webhook"
    if any(part in JOB_DIRS for part in lower_parts) or any(token in name for token in ("cron", "schedule", "scheduler", "worker", "queue")):
        return "scheduled-job"
    if any(part in CLI_DIRS for part in lower_parts) or any(token in text for token in ("PHP_SAPI", "$argv", "STDOUT", "STDERR")):
        return "cli"
    if _looks_like_php_surface(relative, text):
        return "api" if (lower_parts and lower_parts[0] == "api") or "application/json" in text.lower() else "browser-page"
    return ""


def _read_text(path: Path, limit: int = 1_000_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _relative_parts(path: str) -> list[str]:
    return [part.lower() for part in Path(path.replace("\\", "/")).parts]


def _is_asset_path(path: str) -> bool:
    parts = _relative_parts(path)
    return any(part in NON_EXECUTABLE_ASSET_DIRS for part in parts[:-1])


def _looks_like_graph_runtime_surface(project_root: Path, node_type: str, path: str, name: str) -> bool:
    """Reject Graph keyword hints that do not identify an executable surface.

    Graph deliberately records broad architectural signals. Release proof must use a
    narrower standard: a source file that merely *mentions* webhooks, cron, SQL, or
    scheduling is not itself a releasable runtime surface.
    """
    if not path or _is_asset_path(path):
        return False
    candidate = project_root / path
    if not candidate.is_file():
        # Route-like virtual nodes are handled separately. Webhook/job nodes must
        # resolve to an executable source file before they become proof obligations.
        return False
    text = _read_text(candidate)
    suffix = candidate.suffix.lower()
    lowered_name = f"{path} {name}".lower()
    if node_type == "entrypoint":
        if suffix in {".js", ".mjs", ".cjs"} and _is_asset_path(path):
            return False
        if suffix in {".php", ".phtml"}:
            return bool(_php_surface_kind(path, text))
        return True
    if node_type == "route":
        parts = _relative_parts(path)
        if any(part in EXCLUDED_SURFACE_DIRS for part in parts[:-1]):
            return False
        if suffix in {".php", ".phtml"}:
            return _looks_like_php_surface(path, text)
        if suffix == ".py":
            # Require observable framework route syntax. Strings containing paths
            # used for state directories or documentation are not web routes.
            return bool(re.search(
                r"(?m)^\s*@(?:\w+\.)?(?:route|get|post|put|patch|delete)\s*\(",
                text,
            ))
        if suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx"}:
            lowered = text.lower()
            return any(token in lowered for token in (".get(", ".post(", ".put(", ".patch(", ".delete(", "router."))
        return False
    if node_type == "webhook":
        named = any(token in lowered_name for token in ("webhook", "callback", "inbound", "receiver"))
        if suffix in {".php", ".phtml"}:
            return bool(named and "<?" in text)
        if suffix == ".py":
            executable = text.startswith("#!") or "if __name__" in text or re.search(r"@\w+\.(?:route|post|put|patch)\s*\(", text)
            return bool(named and executable)
        if suffix in {".js", ".mjs", ".cjs", ".ts"}:
            executable = any(token in text.lower() for token in ("express(", ".post(", "creatserver(", "createServer(".lower()))
            return bool(named and executable)
        return False
    if node_type == "scheduled-job":
        named = any(token in lowered_name for token in ("cron", "schedule", "scheduler", "job", "worker", "queue"))
        if suffix in {".php", ".phtml"}:
            return bool(named and "<?" in text)
        if suffix == ".py":
            return bool(named and (text.startswith("#!") or "if __name__" in text))
        if suffix in {".js", ".mjs", ".cjs", ".ts"}:
            return bool(named and any(token in text.lower() for token in ("setinterval(", "cron", "schedule(", "worker")))
        return False
    if node_type == "cli":
        named = any(part in CLI_DIRS for part in _relative_parts(path)[:-1]) or any(token in lowered_name for token in ("cli", "console", "command"))
        if suffix in {".php", ".phtml"}:
            return bool((named or any(token in text for token in ("PHP_SAPI", "$argv", "STDOUT", "STDERR"))) and "<?" in text)
        if suffix == ".py":
            return bool(named or text.startswith("#!") or "if __name__" in text)
        if suffix in {".js", ".mjs", ".cjs", ".ts", ".sh"}:
            return bool(named or text.startswith("#!"))
        return False
    return False


def discover_surfaces(project_root: Path, forge_root: Path, config: dict[str, Any], graph: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = project_root.resolve()
    graph = graph or load_graph(root, config) or build_graph(root, forge_root, config, write=True)
    surfaces: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(kind: str, path: str, name: str, source: str, confidence: float = 0.8, metadata: dict[str, Any] | None = None) -> None:
        generic_kinds = {"entrypoint", "browser-page"}
        merged_evidence: list[str] = []
        merged_metadata: dict[str, Any] = {}
        merged_confidence = confidence
        same_path = [(key, item) for key, item in surfaces.items() if path and item.get("path") == path and item.get("kind") != "route"]
        same_kind = [(key, item) for key, item in same_path if item.get("kind") == kind]
        if same_kind:
            _, item = same_kind[0]
            if source not in item["evidence"]:
                item["evidence"].append(source)
            item["confidence"] = max(float(item.get("confidence", 0)), confidence)
            item.setdefault("metadata", {}).update(metadata or {})
            return
        if kind in generic_kinds:
            specialized = [(key, item) for key, item in same_path if item.get("kind") not in generic_kinds]
            if specialized:
                _, item = specialized[0]
                if source not in item["evidence"]:
                    item["evidence"].append(source)
                item["confidence"] = max(float(item.get("confidence", 0)), confidence)
                item.setdefault("metadata", {}).update(metadata or {})
                return
            if kind == "entrypoint":
                browser = [(key, item) for key, item in same_path if item.get("kind") == "browser-page"]
                if browser:
                    _, item = browser[0]
                    if source not in item["evidence"]:
                        item["evidence"].append(source)
                    item["confidence"] = max(float(item.get("confidence", 0)), confidence)
                    return
            elif kind == "browser-page":
                for key, item in same_path:
                    if item.get("kind") == "entrypoint":
                        merged_evidence.extend(item.get("evidence", []))
                        merged_metadata.update(item.get("metadata", {}))
                        merged_confidence = max(merged_confidence, float(item.get("confidence", 0)))
                        surfaces.pop(key, None)
        else:
            for key, item in same_path:
                if item.get("kind") in generic_kinds:
                    merged_evidence.extend(item.get("evidence", []))
                    merged_metadata.update(item.get("metadata", {}))
                    merged_confidence = max(merged_confidence, float(item.get("confidence", 0)))
                    surfaces.pop(key, None)
        key = (kind, path, name)
        item = surfaces.setdefault(key, {
            "id": _surface_id(kind, path, name),
            "kind": kind,
            "path": path,
            "name": name or path,
            "confidence": merged_confidence,
            "evidence": [],
            "metadata": {**merged_metadata, **(metadata or {})},
        })
        for prior_source in merged_evidence:
            if prior_source not in item["evidence"]:
                item["evidence"].append(prior_source)
        if source not in item["evidence"]:
            item["evidence"].append(source)
        item["confidence"] = max(float(item.get("confidence", 0)), merged_confidence)

    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type", ""))
        path = str(node.get("path", ""))
        name = str(node.get("name", path))
        path_parts = [part.lower() for part in Path(path).parts]
        if path_parts and path_parts[0] in EXCLUDED_SURFACE_DIRS:
            continue
        if node_type == "entrypoint" and _looks_like_graph_runtime_surface(root, node_type, path, name):
            add("entrypoint", path, name, "Forge Graph entrypoint", 0.95)
        elif node_type == "route" and _looks_like_graph_runtime_surface(root, node_type, path, name):
            add("route", path, name, "Forge Graph route", 0.95)
        elif node_type == "webhook" and _looks_like_graph_runtime_surface(root, node_type, path, name):
            add("webhook", path, name, "Forge Graph webhook", 0.9)
        elif node_type == "scheduled-job" and _looks_like_graph_runtime_surface(root, node_type, path, name):
            add("scheduled-job", path, name, "Forge Graph scheduled job", 0.9)
        elif node_type == "cli" and _looks_like_graph_runtime_surface(root, node_type, path, name):
            add("cli", path, name, "Forge Graph CLI", 0.9)

    excludes = set(str(item).replace("\\", "/").rstrip("/") for item in config.get("paths", {}).get("exclude", []))
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root).as_posix()
        kept = []
        for name in dirs:
            rel = (Path(rel_dir) / name).as_posix() if rel_dir != "." else name
            if name.lower() in EXCLUDED_SURFACE_DIRS or any(rel == item or rel.startswith(item + "/") for item in excludes):
                continue
            kept.append(name)
        dirs[:] = kept
        for name in files:
            path = current_path / name
            rel = path.relative_to(root).as_posix()
            if forge_root.resolve() == path.resolve() or rel.startswith("Emotivus-Forge/"):
                continue
            text = _read_text(path)
            suffix = path.suffix.lower()
            php_kind = _php_surface_kind(rel, text)
            if php_kind:
                kind = php_kind
                add(kind, rel, rel, "PHP executable-surface inference", 0.82, {"dynamic": True})
            elif suffix in {".html", ".htm"} and not any(part.lower() in EXCLUDED_SURFACE_DIRS for part in Path(rel).parts[:-1]):
                add("browser-page", rel, rel, "HTML page inference", 0.85, {"dynamic": False})
            elif suffix == ".py" and (
                text.startswith("#!")
                or bool(re.search(r"(?m)^\s*if\s+__name__\s*==\s*[\"']__main__[\"']\s*:", text))
            ) and not rel.startswith(("tests/", "tools/")):
                add("cli", rel, rel, "Python executable inference", 0.75)
            elif (
                suffix in {".js", ".mjs", ".cjs"}
                and path.name.lower() in {"app.js", "server.js", "main.js", "cli.js"}
                and not _is_asset_path(rel)
            ):
                add("entrypoint", rel, rel, "JavaScript executable inference", 0.75)

    configured = config.get("release_proof", {}).get("surfaces", [])
    if isinstance(configured, list):
        for raw in configured:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind", "entrypoint"))
            path = str(raw.get("path", ""))
            name = str(raw.get("name", path))
            if path or name:
                add(kind, path, name, "project-declared release surface", 1.0, {"required": bool(raw.get("required", True))})

    return sorted(surfaces.values(), key=lambda item: (item["kind"], item["path"], item["name"]))


def _current_gate_results(project_root: Path, config: dict[str, Any], current_fingerprint: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    reports = project_root / config.get("paths", {}).get("reports", ".forge/reports")
    for profile in ("quick", "section", "release"):
        path = reports / f"{profile}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("tree_fingerprint") != current_fingerprint:
            continue
        for item in payload.get("results", []):
            if isinstance(item, dict) and item.get("check_id"):
                results[str(item["check_id"])] = {**item, "profile": profile, "report": str(path)}
    return results


def _normalized_surface_tokens(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return sorted({str(item).strip().replace("\\", "/") for item in raw if str(item).strip()})


def _surface_matches_token(surface: dict[str, Any], token: str) -> bool:
    token = str(token).strip().replace("\\", "/")
    if not token:
        return False
    canonical = f"{surface.get('kind', '')}:{surface.get('path', '')}:{surface.get('name', '')}"
    return token in {str(surface.get("path", "")), str(surface.get("name", "")), canonical}


def _declared_surface_matches(surface: dict[str, Any], pattern: str) -> bool:
    if pattern == "all" or pattern == f"all:{surface['kind']}":
        return True
    return _matches(surface["path"], pattern) or _matches(surface["name"], pattern)


def _command_producers(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    current_fingerprint: str,
    current_results: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    producers: list[dict[str, Any]] = []
    current_results = current_results if current_results is not None else _current_gate_results(project_root, config, current_fingerprint)
    for group, commands in config.get("commands", {}).items():
        if not isinstance(commands, list):
            continue
        for raw in commands:
            if not isinstance(raw, dict):
                continue
            evidence = raw.get("evidence", {}) if isinstance(raw.get("evidence"), dict) else {}
            types = evidence.get("types", evidence.get("type", []))
            if isinstance(types, str):
                types = [types]
            if not isinstance(types, list):
                types = []
            normalized = sorted({str(item) for item in types if str(item) in EVIDENCE_TYPES})
            surfaces = _normalized_surface_tokens(evidence.get("surfaces", []))
            command = [str(item) for item in raw.get("command", [])] if isinstance(raw.get("command"), list) else []
            resolved = resolve_command(command, project=project_root, forge=forge_root) if command else []
            command_raw = "\0".join(resolved) + "\0" + json.dumps(evidence, sort_keys=True)
            command_hash = hashlib.sha256(command_raw.encode("utf-8")).hexdigest()
            check_id = str(raw.get("id", f"command.{group}"))
            observed = current_results.get(check_id, {})
            current_pass = observed.get("status") == "PASS" and observed.get("command_hash") == command_hash
            observed_evidence = observed.get("evidence", {}) if isinstance(observed.get("evidence"), dict) else {}
            producers.append({
                "id": check_id,
                "source": "command",
                "group": str(group),
                "types": normalized,
                "declared_surfaces": surfaces,
                "attested_surfaces": _normalized_surface_tokens(observed_evidence.get("surfaces", [])) if current_pass else [],
                "command": command,
                "command_hash": command_hash,
                "required": bool(raw.get("required", True)),
                "recurring": True,
                "current_pass": current_pass,
                "observed_status": observed.get("status", "NOT-RUN"),
                "evidence_ref": observed.get("report", ""),
            })
    return producers


def _lab_producers(project_root: Path, config: dict[str, Any], current_fingerprint: str) -> list[dict[str, Any]]:
    lab = config.get("lab", {})
    reports_dir = project_root / lab.get("output_dir", ".forge/lab") / "reports"
    level_types = {
        "process-started": [],
        "connectivity-smoke": ["entrypoint-execution"],
        "content-readiness": ["entrypoint-execution", "browser-behavior"],
        "stateful-behavior": ["entrypoint-execution", "browser-behavior", "integration"],
        "environment-backed-behavior": ["entrypoint-execution", "integration"],
        "release-equivalent": ["entrypoint-execution", "browser-behavior", "integration"],
    }
    producers: list[dict[str, Any]] = []
    for recipe in lab.get("recipes", []):
        if not isinstance(recipe, dict) or not recipe.get("enabled", True):
            continue
        recipe_id = str(recipe.get("id", "lab-recipe"))
        latest_path = reports_dir / f"{recipe_id}-latest.json"
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest = {}
        expected_recipe_fingerprint = _hash_json(recipe)
        level = str(latest.get("evidence_level", recipe.get("evidence_level", "process-started")))
        surfaces = _normalized_surface_tokens(recipe.get("surfaces", []))
        current_pass = (
            latest.get("status") == "PASS"
            and latest.get("tree_fingerprint") == current_fingerprint
            and latest.get("recipe_fingerprint") == expected_recipe_fingerprint
        )
        producers.append({
            "id": f"lab:{recipe_id}",
            "source": "lab",
            "types": level_types.get(level, []),
            "declared_surfaces": surfaces,
            "attested_surfaces": _normalized_surface_tokens(latest.get("surface_attestations", [])) if current_pass else [],
            "profiles": [str(item) for item in recipe.get("profiles", [])] if isinstance(recipe.get("profiles"), list) else [],
            "boundary": str(latest.get("evidence_boundary", recipe.get("evidence_boundary", ""))),
            "recurring": True,
            "current_pass": current_pass,
            "observed_status": latest.get("status", "NOT-RUN"),
            "evidence_ref": str(latest_path) if latest else "",
        })
    return producers


def _runtime_producers(project_root: Path, config: dict[str, Any], current_fingerprint: str) -> list[dict[str, Any]]:
    try:
        registry = load_runtime_contracts(project_root, config)
    except RuntimeError:
        return []
    kind_types = {
        "browser": ["browser-behavior", "entrypoint-execution"],
        "migration": ["database-upgrade", "integration"],
        "authorization": ["integration", "browser-behavior"],
        "api": ["integration", "entrypoint-execution"],
        "webhook": ["integration", "entrypoint-execution"],
        "cron": ["integration", "entrypoint-execution"],
        "email": ["integration"], "sms": ["integration"], "upload": ["integration", "browser-behavior"],
        "provider": ["integration"], "resilience": ["integration", "entrypoint-execution"],
    }
    output_dir = project_root / config.get("runtime_proof", {}).get("output_dir", ".forge/runtime") / "reports"
    producers: list[dict[str, Any]] = []
    for contract in registry.get("contracts", []):
        if not isinstance(contract, dict) or not contract.get("enabled", True):
            continue
        surfaces = _normalized_surface_tokens(contract.get("surfaces", []))
        contract_id = str(contract.get("id", "runtime-contract"))
        latest_path = output_dir / f"{contract_id}-latest.json"
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest = {}
        expected_contract_fingerprint = _hash_json(contract)
        current_pass = (
            latest.get("status") == "PASS"
            and latest.get("tree_fingerprint") == current_fingerprint
            and latest.get("contract_fingerprint") == expected_contract_fingerprint
        )
        producers.append({
            "id": contract_id,
            "source": "runtime-contract",
            "kind": str(contract.get("kind", "")),
            "types": kind_types.get(str(contract.get("kind", "")), ["integration"]),
            "declared_surfaces": surfaces,
            "attested_surfaces": _normalized_surface_tokens((latest.get("evidence", {}) if isinstance(latest.get("evidence"), dict) else {}).get("surfaces", [])) if current_pass else [],
            "profiles": [str(item) for item in contract.get("profiles", [])] if isinstance(contract.get("profiles"), list) else [],
            "boundary": str(contract.get("evidence_boundary", "")),
            "recurring": True,
            "current_pass": current_pass,
            "observed_status": latest.get("status", "NOT-RUN"),
            "evidence_ref": str(latest_path) if latest else "",
        })
    return producers


def _producer_covers(producer: dict[str, Any], surface: dict[str, Any]) -> bool:
    declared = producer.get("declared_surfaces", [])
    attested = producer.get("attested_surfaces", [])
    return any(_declared_surface_matches(surface, pattern) for pattern in declared) and any(
        _surface_matches_token(surface, token) for token in attested
    )


def _load_bound_evidence(
    project_root: Path,
    raw: Any,
    current_fingerprint: str,
    current_results: dict[str, dict[str, Any]],
    approved_producers: set[str],
) -> tuple[dict[str, Any], list[str]]:
    if isinstance(raw, dict):
        ref = raw
    elif isinstance(raw, str):
        return {}, ["evidence reference must name both path and current Forge-observed producer"]
    else:
        return {}, ["evidence reference must be an object"]
    rel = str(ref.get("path", "")).strip()
    if not rel:
        return {}, ["evidence reference path is empty"]
    path = project_root / rel
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"evidence reference is missing or invalid: {rel} ({exc})"]
    problems: list[str] = []
    expected_hash = str(ref.get("sha256", ""))
    if expected_hash and sha256_file(path) != expected_hash:
        problems.append(f"evidence file hash does not match its declaration: {rel}")
    if str(payload.get("status", "")).upper() != "PASS":
        problems.append(f"evidence file does not report PASS: {rel}")
    if payload.get("tree_fingerprint") != current_fingerprint:
        problems.append(f"evidence file is stale for the current source tree: {rel}")
    producer_id = str(ref.get("producer", "")).strip()
    if not producer_id:
        problems.append(f"evidence file is not bound to a current Forge-observed producer: {rel}")
    else:
        observed = current_results.get(producer_id, {})
        if producer_id not in approved_producers or observed.get("status") != "PASS":
            problems.append(f"evidence producer is not a current passing registered Gate check: {producer_id}")
        observed_evidence = observed.get("evidence", {}) if isinstance(observed.get("evidence"), dict) else {}
        artifacts = observed_evidence.get("artifacts", []) if isinstance(observed_evidence.get("artifacts"), list) else []
        matching = next((item for item in artifacts if isinstance(item, dict) and str(item.get("path", "")) == rel), None)
        if matching is None:
            problems.append(f"current producer did not record the evidence artifact: {producer_id} -> {rel}")
        elif matching.get("produced_in_run") is not True:
            problems.append(f"evidence artifact was not produced or refreshed by its current producer: {producer_id} -> {rel}")
        elif path.is_file() and str(matching.get("sha256", "")) != sha256_file(path):
            problems.append(f"evidence artifact changed after its producer passed: {rel}")
    return payload if isinstance(payload, dict) else {}, problems


def _target_environment_findings(
    project_root: Path,
    config: dict[str, Any],
    current_fingerprint: str,
    current_results: dict[str, dict[str, Any]],
    approved_producers: set[str],
) -> dict[str, Any]:
    target = config.get("environment", {}).get("target", {})
    declared = bool(
        isinstance(target, dict)
        and (
            any(str(value).strip() for value in (target.get("runtimes", {}) or {}).values())
            or any(str(item).strip() for item in target.get("required_extensions", []) or [])
            or any(str(item).strip() for item in target.get("required_services", []) or [])
            or bool(target.get("evidence"))
        )
    )
    if not declared:
        return {"declared": False, "status": "UNKNOWN", "problems": ["No target environment contract is declared."], "target": {}}
    problems: list[str] = []
    evidence_refs = target.get("evidence", [])
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    observed_runtimes: dict[str, set[str]] = {}
    observed_extensions: set[str] = set()
    observed_services: set[str] = set()
    valid_evidence = 0
    for ref in evidence_refs:
        payload, ref_problems = _load_bound_evidence(project_root, ref, current_fingerprint, current_results, approved_producers)
        problems.extend(ref_problems)
        boundary = str(payload.get("evidence_boundary", ""))
        if payload and not ref_problems and boundary not in {"release-equivalent", "production-observed"}:
            problems.append(f"target environment evidence boundary is too weak: {boundary or '(empty)'}")
        if payload and not ref_problems and boundary in {"release-equivalent", "production-observed"}:
            valid_evidence += 1
            for name, values in (payload.get("runtimes", {}) if isinstance(payload.get("runtimes"), dict) else {}).items():
                if isinstance(values, str):
                    values = [values]
                observed_runtimes.setdefault(str(name), set()).update(str(item) for item in values if str(item))
            observed_extensions.update(str(item) for item in payload.get("extensions", []) if str(item))
            observed_services.update(str(item) for item in payload.get("services", []) if str(item))
    if not valid_evidence:
        problems.append("target environment contract has no current release-equivalent evidence")
    runtimes = target.get("runtimes", {}) if isinstance(target.get("runtimes"), dict) else {}
    for name, required in runtimes.items():
        if str(required) and str(required) not in observed_runtimes.get(str(name), set()):
            problems.append(f"target runtime {name} {required} is not covered by current target evidence")
    required_extensions = {str(item) for item in target.get("required_extensions", []) if str(item)}
    missing_extensions = sorted(required_extensions - observed_extensions)
    if missing_extensions:
        problems.append("required target extensions are not covered by current evidence: " + ", ".join(missing_extensions))
    required_services = {str(item) for item in target.get("required_services", []) if str(item)}
    missing_services = sorted(required_services - observed_services)
    if missing_services:
        problems.append("required target services are not covered by current evidence: " + ", ".join(missing_services))
    return {"declared": True, "status": "PASS" if not problems else "FAIL", "problems": problems, "target": target, "valid_evidence": valid_evidence}


def _deployment_state_findings(
    project_root: Path,
    config: dict[str, Any],
    current_fingerprint: str,
    current_results: dict[str, dict[str, Any]],
    approved_producers: set[str],
) -> dict[str, Any]:
    states = config.get("release_proof", {}).get("deployment_states", [])
    if not isinstance(states, list):
        states = []
    required = [item for item in states if isinstance(item, dict) and item.get("required", True)]
    problems: list[str] = []
    observed: list[dict[str, Any]] = []
    for item in required:
        state_id = str(item.get("id", "unnamed"))
        payload, ref_problems = _load_bound_evidence(project_root, item.get("evidence", ""), current_fingerprint, current_results, approved_producers)
        problems.extend(f"{state_id}: {problem}" for problem in ref_problems)
        expected_state = str(item.get("state", state_id))
        if payload and str(payload.get("deployment_state", expected_state)) != expected_state:
            problems.append(f"{state_id}: evidence describes a different deployment state")
        observed.append({"id": state_id, "evidence": payload})
    return {
        "declared": len(states),
        "required": len(required),
        "applicable": bool(states),
        "status": "PASS" if required and not problems else ("NOT_APPLICABLE" if not states else ("UNKNOWN" if not required else "FAIL")),
        "problems": problems,
        "states": states,
        "observed": observed,
    }


def _detect_recurring_claims(project_root: Path, producers: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    current_types = {
        evidence_type
        for producer in producers
        if producer.get("current_pass")
        for evidence_type in producer.get("types", [])
    }
    typed_patterns: tuple[tuple[re.Pattern[str], set[str], str], ...] = (
        (
            re.compile(r"all\s+(?:\d+|\w+)\s+(?:pages|routes|screens|endpoints).{0,100}(?:executed|rendered|tested|verified)", re.I),
            set(EXECUTION_EVIDENCE),
            "verification claim has no current recurring execution evidence producer",
        ),
        (
            re.compile(r"(?:every|all)\s+(?:page|route|screen|endpoint).{0,100}(?:passes|passed|works|executed|tested|verified)", re.I),
            set(EXECUTION_EVIDENCE),
            "verification claim has no current recurring execution evidence producer",
        ),
        (
            re.compile(r"(?:every|all)\s+(?:upgrade|migration|schema (?:change|step|transition)).{0,100}(?:passes|passed|works|executed|tested|verified)", re.I),
            {"database-upgrade"},
            "upgrade verification claim has no current recurring database-upgrade evidence producer",
        ),
        (
            re.compile(r"(?:production|target (?:host|environment|runtime)).{0,100}(?:matches|matched|passes|passed|works|tested|verified)", re.I),
            {"target-environment"},
            "target-environment verification claim has no current recurring target-environment evidence producer",
        ),
    )
    candidates = {
        "README.md", "HANDOVER.md", "Release/STATE.md", "Release/README.md", "docs/README.md",
    }
    continuity = config.get("continuity", {}) if isinstance(config.get("continuity"), dict) else {}
    objective_sources = continuity.get("objective_sources", [])
    if isinstance(objective_sources, str):
        objective_sources = [objective_sources]
    if isinstance(objective_sources, list):
        candidates.update(str(item).replace("\\", "/") for item in objective_sources if str(item).strip())
    seen: set[tuple[str, str]] = set()
    for rel in sorted(candidates):
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts or rel_path.suffix.lower() not in {".md", ".txt"}:
            continue
        if any(part in {"Emotivus-Forge", ".forge"} for part in rel_path.parts):
            continue
        path = project_root / rel_path
        if not path.is_file():
            continue
        text = _read_text(path, 500_000)
        for pattern, required_types, problem in typed_patterns:
            for match in pattern.finditer(text):
                if current_types & required_types:
                    continue
                claim = match.group(0)[:180]
                key = (rel_path.as_posix(), claim.lower())
                if key in seen:
                    continue
                seen.add(key)
                findings.append({"path": rel_path.as_posix(), "claim": claim, "problem": problem})
    return findings


def load_delivery_manifest(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    rel = str(config.get("delivery_proof", {}).get("manifest_path", ".forge/delivery/delivery-manifest.json"))
    path = project_root / rel
    if not path.is_file():
        return {"schema": 1, "artifacts": [], "final_bundle": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "artifacts": [], "final_bundle": {}, "invalid": True}
    return payload if isinstance(payload, dict) else {"schema": 1, "artifacts": [], "final_bundle": {}, "invalid": True}


def _input_fingerprint(project_root: Path, inputs: list[str]) -> str:
    rows: list[dict[str, Any]] = []
    for raw in sorted(set(inputs)):
        path = project_root / raw
        if path.is_file():
            rows.append({"path": raw, "sha256": sha256_file(path), "bytes": path.stat().st_size})
        elif path.is_dir():
            files = []
            for child in sorted(path.rglob("*")):
                if child.is_file() and "__pycache__" not in child.parts and child.suffix != ".pyc":
                    files.append({"path": child.relative_to(project_root).as_posix(), "sha256": sha256_file(child), "bytes": child.stat().st_size})
            rows.append({"path": raw, "files": files})
        else:
            rows.append({"path": raw, "missing": True})
    return _hash_json(rows)


def _generator_files(project_root: Path, resolved: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in resolved[:5]:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        if candidate.is_file():
            files.append(candidate.resolve())
    return files


def _generator_fingerprint(project_root: Path, resolved: list[str]) -> str:
    rows = []
    for path in _generator_files(project_root, resolved):
        rows.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return _hash_json(rows) if rows else ""


def validate_delivery_provenance(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    delivery = config.get("delivery_proof", {})
    manifest = load_delivery_manifest(project_root, config)
    problems: list[str] = []
    if manifest.get("invalid"):
        problems.append("delivery manifest is invalid JSON")
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
        problems.append("delivery manifest artifacts must be a list")
    declared_paths: set[str] = set()
    role_paths: dict[str, list[str]] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            problems.append("delivery manifest contains a malformed artifact record")
            continue
        path_value = str(item.get("path", ""))
        role = str(item.get("role", ""))
        if not path_value or not role:
            problems.append("every delivered artifact requires path and role")
            continue
        declared_paths.add(path_value)
        role_paths.setdefault(role, []).append(path_value)
        path = project_root / path_value
        if not path.is_file():
            problems.append(f"declared delivered artifact is missing: {path_value}")
            continue
        expected = str(item.get("sha256", ""))
        actual = sha256_file(path)
        if not expected or expected != actual:
            problems.append(f"delivered artifact hash is missing or stale: {path_value}")
        mode = str(item.get("mode", "generated"))
        if mode == "frozen":
            if not str(item.get("freeze_reason", "")).strip():
                problems.append(f"frozen artifact lacks an explicit reason: {path_value}")
        elif mode == "generated":
            generator = item.get("generator", {}) if isinstance(item.get("generator"), dict) else {}
            command = generator.get("command", [])
            if not isinstance(command, list) or not command:
                problems.append(f"generated artifact lacks an executable generator command: {path_value}")
            else:
                resolved = resolve_command([str(part) for part in command], project=project_root, forge=project_root / "Emotivus-Forge")
                files = _generator_files(project_root, resolved)
                if not resolved or not files:
                    problems.append(f"declared generator command cannot be resolved to an executable or script: {path_value}")
                recorded_fingerprint = str(generator.get("fingerprint", ""))
                if not recorded_fingerprint or _generator_fingerprint(project_root, resolved) != recorded_fingerprint:
                    problems.append(f"generator command or implementation changed after artifact generation: {path_value}")
                execution = generator.get("execution", {}) if isinstance(generator.get("execution"), dict) else {}
                if execution.get("status") != "PASS" or execution.get("returncode") != 0:
                    problems.append(f"artifact lacks a successful Forge-observed generator execution: {path_value}")
                if str(execution.get("command_hash", "")) != _hash_json(resolved):
                    problems.append(f"generator execution receipt does not match the declared command: {path_value}")
            inputs = [str(value) for value in item.get("inputs", [])] if isinstance(item.get("inputs"), list) else []
            expected_input = str(item.get("input_fingerprint", ""))
            if not inputs or not expected_input:
                problems.append(f"generated artifact lacks input provenance: {path_value}")
            elif _input_fingerprint(project_root, inputs) != expected_input:
                problems.append(f"generator inputs changed after artifact generation: {path_value}")
        else:
            problems.append(f"unsupported artifact provenance mode {mode!r}: {path_value}")
    for role, paths in role_paths.items():
        if len(paths) > 1:
            current = [item for item in artifacts if isinstance(item, dict) and item.get("role") == role and item.get("status", "current") == "current"]
            if len(current) != 1:
                problems.append(f"delivery role {role!r} has multiple artifacts without one explicit current artifact")

    final = manifest.get("final_bundle", {}) if isinstance(manifest.get("final_bundle"), dict) else {}
    final_declared_path = str(final.get("path", ""))
    scan_roots = delivery.get("scan_roots", ["."])
    if isinstance(scan_roots, str):
        scan_roots = [scan_roots]
    patterns = delivery.get("detect_patterns", list(DELIVERABLE_PATTERNS))
    if isinstance(patterns, str):
        patterns = [patterns]
    manifest_rel = str(delivery.get("manifest_path", ".forge/delivery/delivery-manifest.json"))
    for root_rel in scan_roots if isinstance(scan_roots, list) else ["."]:
        scan_root = project_root / str(root_rel)
        if not scan_root.exists():
            continue
        iterator = scan_root.iterdir() if scan_root.is_dir() else []
        for path in iterator:
            if not path.is_file():
                continue
            rel = path.relative_to(project_root).as_posix()
            if rel == manifest_rel or rel == final_declared_path or rel.startswith("deploy/") or rel.startswith(".forge/"):
                continue
            if any(fnmatch.fnmatchcase(path.name, str(pattern)) for pattern in patterns) and rel not in declared_paths:
                problems.append(f"deliverable-shaped file exists outside the declared delivery manifest: {rel}")

    if artifacts and not final:
        problems.append("final owner-facing delivery bundle has not been built")
    if final:
        final_path = str(final.get("path", ""))
        path = project_root / final_path
        final_file_valid = bool(final_path and path.is_file())
        if not final_file_valid:
            problems.append("final owner-facing delivery bundle is missing")
        elif str(final.get("sha256", "")) != sha256_file(path):
            problems.append("final owner-facing delivery bundle hash is missing or stale")
        members = final.get("members", [])
        if not isinstance(members, list) or sorted(str(item) for item in members) != sorted(declared_paths):
            problems.append("final delivery bundle membership does not match declared artifacts")
        if final_file_valid:
            try:
                with zipfile.ZipFile(path) as archive:
                    names = archive.namelist()
                    if len(names) != len(set(names)):
                        problems.append("final owner-facing delivery bundle contains duplicate archive paths")
                    for item in artifacts:
                        if not isinstance(item, dict):
                            continue
                        member = str(item.get("path", ""))
                        expected = str(item.get("sha256", ""))
                        if not member or member not in names:
                            problems.append(f"final delivery bundle is missing declared artifact bytes: {member or '(empty)'}")
                            continue
                        actual = hashlib.sha256(archive.read(member)).hexdigest()
                        if not expected or actual != expected:
                            problems.append(f"final delivery bundle contains stale artifact bytes: {member}")
            except (OSError, zipfile.BadZipFile, KeyError) as exc:
                problems.append(f"final owner-facing delivery bundle cannot be inspected: {exc}")
    return {
        "status": "PASS" if artifacts and final and not problems else ("UNKNOWN" if not artifacts and not final else "FAIL"),
        "problems": sorted(set(problems)),
        "manifest": manifest,
        "declared_artifacts": len(artifacts),
    }


def record_delivery_artifact(project_root: Path, config: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    path_value = str(record.get("path", ""))
    role = str(record.get("role", ""))
    if not path_value or not role:
        raise RuntimeError("delivery artifact record requires path and role")
    artifact = project_root / path_value
    mode = str(record.get("mode", "generated"))
    if mode == "frozen" and not artifact.is_file():
        raise RuntimeError(f"frozen delivery artifact does not exist: {path_value}")
    item: dict[str, Any] = {
        "id": str(record.get("id") or f"artifact-{hashlib.sha256((role + '\0' + path_value).encode()).hexdigest()[:10]}"),
        "path": path_value,
        "role": role,
        "status": str(record.get("status", "current")),
        "mode": mode,
        "bytes": artifact.stat().st_size if artifact.is_file() else 0,
        "sha256": sha256_file(artifact) if artifact.is_file() else "",
        "recorded_utc": utc_now(),
    }
    if mode == "frozen":
        reason = str(record.get("freeze_reason", "")).strip()
        if not reason:
            raise RuntimeError("frozen artifacts require freeze_reason")
        item["freeze_reason"] = reason
    else:
        command = record.get("generator", {}).get("command", []) if isinstance(record.get("generator"), dict) else record.get("command", [])
        if not isinstance(command, list) or not command:
            raise RuntimeError("generated artifacts require generator.command")
        resolved = resolve_command([str(part) for part in command], project=project_root, forge=project_root / "Emotivus-Forge")
        if not resolved or not _generator_files(project_root, resolved):
            raise RuntimeError("generator command cannot be resolved to an executable or script")
        inputs = [str(value) for value in record.get("inputs", [])] if isinstance(record.get("inputs"), list) else []
        if not inputs:
            raise RuntimeError("generated artifacts require explicit inputs")
        input_fingerprint = _input_fingerprint(project_root, inputs)
        started = utc_now()
        try:
            process = subprocess.run(
                resolved, cwd=project_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=int(record.get("timeout", 600)), check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            output = process.stdout or ""
            returncode = process.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"generator execution failed: {exc}") from exc
        if returncode != 0:
            raise RuntimeError(f"generator command exited {returncode}: {output[-2000:]}")
        if not artifact.is_file():
            raise RuntimeError(f"generator completed but did not produce declared artifact: {path_value}")
        item["bytes"] = artifact.stat().st_size
        item["sha256"] = sha256_file(artifact)
        item["generator"] = {
            "command": [str(part) for part in command],
            "resolved": resolved,
            "fingerprint": _generator_fingerprint(project_root, resolved),
            "execution": {
                "status": "PASS", "returncode": returncode, "started_utc": started, "finished_utc": utc_now(),
                "command_hash": _hash_json(resolved), "output_tail": output[-4000:],
            },
        }
        item["inputs"] = inputs
        item["input_fingerprint"] = input_fingerprint
    manifest = load_delivery_manifest(project_root, config)
    artifacts = [entry for entry in manifest.get("artifacts", []) if isinstance(entry, dict) and entry.get("id") != item["id"] and not (entry.get("role") == role and entry.get("status", "current") == "current" and item["status"] == "current")]
    artifacts.append(item)
    manifest.update({
        "schema": 1,
        "project_identity": config.get("project", {}).get("identity", ""),
        "project_version": config.get("versioning", {}).get("target_version", ""),
        "updated_utc": utc_now(),
        "artifacts": artifacts,
        "final_bundle": {},
    })
    manifest_path = project_root / str(config.get("delivery_proof", {}).get("manifest_path", ".forge/delivery/delivery-manifest.json"))
    write_json(manifest_path, manifest)
    return item


def build_final_delivery(project_root: Path, config: dict[str, Any], output: Path | None = None) -> dict[str, Any]:
    manifest = load_delivery_manifest(project_root, config)
    artifacts = [item for item in manifest.get("artifacts", []) if isinstance(item, dict) and item.get("status", "current") == "current"]
    if not artifacts:
        return {"status": "FAIL", "problems": ["no current delivery artifacts are declared"]}
    problems: list[str] = []
    for item in artifacts:
        path = project_root / str(item.get("path", ""))
        if not path.is_file() or sha256_file(path) != str(item.get("sha256", "")):
            problems.append(f"artifact is missing or stale before final delivery: {item.get('path', '')}")
    if problems:
        return {"status": "FAIL", "problems": problems}
    version = str(config.get("versioning", {}).get("package_version") or config.get("versioning", {}).get("target_version") or "dev")
    project = re.sub(r"[^A-Za-z0-9._-]+", "-", str(config.get("project", {}).get("name", project_root.name))).strip("-") or "Project"
    if output is None:
        pattern = str(config.get("delivery_proof", {}).get("output", "deploy/{project}-{version}-Handoff.zip"))
        output = project_root / pattern.format(project=project, version=version)
    elif not output.is_absolute():
        output = project_root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in sorted(artifacts, key=lambda value: str(value.get("path", ""))):
            path = project_root / str(item["path"])
            archive.write(path, str(item["path"]))
        embedded = dict(manifest)
        embedded["final_bundle"] = {"path": output.relative_to(project_root).as_posix() if output.is_relative_to(project_root) else output.name, "members": sorted(str(item["path"]) for item in artifacts), "generated_utc": utc_now()}
        archive.writestr("FORGE-DELIVERY-MANIFEST.json", json.dumps(embedded, indent=2) + "\n")
    temporary.replace(output)
    final_rel = output.relative_to(project_root).as_posix() if output.is_relative_to(project_root) else str(output)
    manifest["final_bundle"] = {"path": final_rel, "sha256": sha256_file(output), "bytes": output.stat().st_size, "members": sorted(str(item["path"]) for item in artifacts), "generated_utc": utc_now()}
    manifest["updated_utc"] = utc_now()
    manifest_path = project_root / str(config.get("delivery_proof", {}).get("manifest_path", ".forge/delivery/delivery-manifest.json"))
    write_json(manifest_path, manifest)
    validation = validate_delivery_provenance(project_root, config)
    return {"status": "PASS" if validation["status"] == "PASS" else "FAIL", "output": str(output), "sha256": sha256_file(output), "problems": validation["problems"], "manifest": manifest}


def _effective_claim_level(configured: str, surfaces: list[dict[str, Any]], graph: dict[str, Any], config: dict[str, Any]) -> tuple[str, list[str]]:
    configured = configured if configured in CLAIM_LEVELS else "source-verified"
    minimum = "source-verified"
    reasons: list[str] = []
    if not config.get("release_proof", {}).get("auto_minimum", True):
        return configured, reasons
    if config.get("packaging", {}).get("enabled", True):
        minimum = "package-verified"
        reasons.append("packaging is enabled")
    executable = [item for item in surfaces if item.get("kind") in {"browser-page", "route", "api", "webhook", "scheduled-job", "cli", "entrypoint"}]
    if executable:
        minimum = "entrypoints-executed"
        reasons.append(f"{len(executable)} executable or user-facing surface(s) were discovered")
    node_types = graph.get("summary", {}).get("types", {}) if isinstance(graph, dict) else {}
    has_migration_state = bool(
        int(node_types.get("migration", 0) or 0)
        or config.get("versioning", {}).get("migration", {}).get("required")
        or config.get("release_proof", {}).get("deployment_states")
    )
    if has_migration_state:
        minimum = "upgrade-verified"
        reasons.append("persisted database or migration state was detected")
    deployment_target = str(config.get("project", {}).get("deployment_target", "zip"))
    server_side = any(
        item.get("kind") in {"api", "webhook", "scheduled-job"}
        or (item.get("kind") == "browser-page" and bool(item.get("metadata", {}).get("dynamic", True)))
        for item in surfaces
    )
    if server_side and deployment_target not in {"none", "static"}:
        minimum = "target-environment-verified"
        reasons.append(f"server-side software targets {deployment_target or 'a deployment environment'}")
    return CLAIM_LEVELS[max(CLAIM_LEVELS.index(configured), CLAIM_LEVELS.index(minimum))], reasons


def build_release_proof(project_root: Path, forge_root: Path, config: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
    root = project_root.resolve()
    graph = load_graph(root, config) or build_graph(root, forge_root, config, write=True)
    surfaces = discover_surfaces(root, forge_root, config, graph)
    current_fingerprint = tree_fingerprint(root, config.get("paths", {}).get("exclude", []), forge_root)
    current_results = _current_gate_results(root, config, current_fingerprint)
    command_producers = _command_producers(root, forge_root, config, current_fingerprint, current_results)
    approved_artifact_producers = {producer["id"] for producer in command_producers if producer.get("current_pass")}
    producers = command_producers + _lab_producers(root, config, current_fingerprint) + _runtime_producers(root, config, current_fingerprint)
    coverage: list[dict[str, Any]] = []
    for surface in surfaces:
        matched = [producer for producer in producers if _producer_covers(producer, surface)]
        execution = [producer for producer in matched if producer.get("current_pass") and set(producer.get("types", [])) & EXECUTION_EVIDENCE]
        coverage.append({
            "surface": surface,
            "producers": [producer["id"] for producer in matched],
            "current_producers": [producer["id"] for producer in matched if producer.get("current_pass")],
            "evidence_types": sorted({kind for producer in matched for kind in producer.get("types", [])}),
            "recurring_execution_covered": bool(execution),
        })
    uncovered = [item for item in coverage if not item["recurring_execution_covered"]]
    target = _target_environment_findings(root, config, current_fingerprint, current_results, approved_artifact_producers)
    deployment = _deployment_state_findings(root, config, current_fingerprint, current_results, approved_artifact_producers)
    delivery = validate_delivery_provenance(root, config)
    claims = _detect_recurring_claims(root, producers, config)
    configured_claim_level = str(config.get("release_proof", {}).get("claim_level", "source-verified"))
    claim_level, inferred_claim_reasons = _effective_claim_level(configured_claim_level, surfaces, graph, config)
    problems: list[str] = []
    limitations: list[str] = []
    if uncovered:
        limitations.append(f"{len(uncovered)} of {len(coverage)} discovered executable/user-facing surfaces lack recurring execution evidence")
    if not target["declared"]:
        limitations.append("target environment is not declared")
    elif target["status"] != "PASS":
        limitations.extend(target["problems"])
    if deployment.get("applicable") and deployment["status"] != "PASS":
        limitations.append("deployment-state matrix is absent or incomplete")
    if delivery["status"] != "PASS":
        limitations.append("exact owner-facing delivery provenance is not verified")
    if claims:
        limitations.append(f"{len(claims)} documentation verification claim(s) are not backed by registered recurring execution evidence")

    rank = CLAIM_LEVELS.index(claim_level)
    if rank >= CLAIM_LEVELS.index("package-verified") and not config.get("packaging", {}).get("enabled", True):
        problems.append("package-verified or stronger claim requires packaging to be enabled")
    if rank >= CLAIM_LEVELS.index("entrypoints-executed") and surfaces:
        if uncovered:
            problems.append(f"entrypoints-executed claim is unsupported: {len(uncovered)} surface(s) lack recurring execution evidence")
    if rank >= CLAIM_LEVELS.index("upgrade-verified") and deployment["status"] != "PASS":
        problems.extend(deployment["problems"] or ["upgrade-verified claim requires a passed deployment-state matrix"])
    if rank >= CLAIM_LEVELS.index("target-environment-verified") and target["status"] != "PASS":
        problems.extend(target["problems"] or ["target-environment-verified claim requires a complete target environment contract"])
    if rank >= CLAIM_LEVELS.index("delivery-verified") and delivery["status"] != "PASS":
        problems.extend(delivery["problems"] or ["delivery-verified claim requires a verified final owner-facing bundle"])
    if rank >= CLAIM_LEVELS.index("staging-accepted"):
        if not any(producer.get("current_pass") and producer.get("boundary") in {"staging", "release-equivalent", "production-observed"} for producer in producers):
            problems.append("staging-accepted claim requires recurring runtime evidence at staging or stronger boundary")
    if rank >= CLAIM_LEVELS.index("production-observed"):
        if not any(producer.get("current_pass") and ("production-observation" in producer.get("types", []) or producer.get("boundary") == "production-observed") for producer in producers):
            problems.append("production-observed claim requires recurring production-observed evidence")

    dimension_problems: list[str] = []
    if target.get("declared") and target.get("status") == "FAIL":
        dimension_problems.extend(target.get("problems", []))
    if deployment.get("applicable") and deployment.get("status") == "FAIL":
        dimension_problems.extend(deployment.get("problems", []))
    if delivery.get("status") == "FAIL":
        dimension_problems.extend(delivery.get("problems", []) or ["delivery provenance is declared but incomplete"])

    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "project": config.get("project", {}).get("name", root.name),
        "project_identity": config.get("project", {}).get("identity", ""),
        "tree_fingerprint": current_fingerprint,
        "configured_claim_level": configured_claim_level,
        "claim_level": claim_level,
        "inferred_claim_reasons": inferred_claim_reasons,
        "claim_status": "PASS" if not problems else "FAIL",
        "claim_statement": {
            "proven": f"Forge evidence supports the scoped claim: {claim_level}.",
            "not_implied": [item for item in CLAIM_LEVELS[rank + 1:]],
        },
        "surfaces": {"count": len(surfaces), "covered": len(coverage) - len(uncovered), "uncovered": len(uncovered), "items": coverage},
        "evidence_producers": producers,
        "target_environment": target,
        "deployment_states": deployment,
        "delivery_provenance": delivery,
        "unbacked_documentation_claims": claims,
        "problems": sorted(set(problems)),
        "dimension_problems": sorted(set(dimension_problems)),
        "limitations": sorted(set(limitations)),
    }
    if write:
        output_dir = root / str(config.get("release_proof", {}).get("output_dir", ".forge/release-proof"))
        write_json(output_dir / "latest.json", payload)
        _write_markdown(output_dir / "latest.md", payload)
    return payload


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    surfaces = payload["surfaces"]
    lines = [
        "# Forge Release Proof", "",
        f"- Claim: **{payload['claim_level']}**",
        f"- Status: **{payload['claim_status']}**",
        f"- Tree fingerprint: `{payload['tree_fingerprint']}`",
        f"- Surfaces: {surfaces['count']} discovered, {surfaces['covered']} execution-covered, {surfaces['uncovered']} uncovered", "",
        "## What this green result proves", "",
        payload["claim_statement"]["proven"], "",
        "## What it does not imply", "",
    ]
    if payload["claim_statement"]["not_implied"]:
        lines.extend(f"- {item}" for item in payload["claim_statement"]["not_implied"])
    else:
        lines.append("- No stronger predefined claim level remains.")
    lines.extend(["", "## Problems", ""])
    lines.extend(f"- {item}" for item in payload["problems"]) if payload["problems"] else lines.append("- None")
    lines.extend(["", "## Known limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"]) if payload["limitations"] else lines.append("- None")
    lines.extend(["", "## Uncovered surfaces", ""])
    uncovered = [item for item in surfaces["items"] if not item["recurring_execution_covered"]]
    if uncovered:
        for item in uncovered[:300]:
            surface = item["surface"]
            lines.append(f"- `{surface['kind']}` `{surface['path'] or surface['name']}`")
    else:
        lines.append("- None")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

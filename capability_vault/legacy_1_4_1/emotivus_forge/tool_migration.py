from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .detect import is_forge_project
from .utils import declared_paths_fingerprint, iter_project_files, utc_now, write_json

TOOL_DIR_HINTS = {"tools", "tooling", "scripts", "script", "build", "bin", "ci", ".github", ".gitlab", ".circleci", ".claude"}
TOOL_NAME_RE = re.compile(r"(?i)(?:^|[-_.])(check|validate|verify|lint|audit|test|smoke|package|packager|release|deploy|build|scan|quality|graph|architecture|impact|dependency|e2e|regression|defect)(?:[-_.]|$)")
AGENT_FILES = {"AGENTS.md", "CLAUDE.md", "COPILOT.md", "CURSOR.md", ".cursorrules", "PROJECT-INSTRUCTIONS.md"}
CONFIG_NAMES = {
    "package.json", "composer.json", "pyproject.toml", "tox.ini", "pytest.ini", "phpunit.xml", "phpunit.xml.dist",
    ".eslintrc", ".eslintrc.json", "eslint.config.js", "eslint.config.mjs", ".prettierrc", ".prettierrc.json",
    "ruff.toml", ".ruff.toml", "mypy.ini", ".stylelintrc", ".stylelintrc.json", "Makefile", "Taskfile.yml",
    ".gitlab-ci.yml", "Jenkinsfile", "Dockerfile", ".deployignore",
}
CI_PREFIXES = (".github/workflows/", ".circleci/")
TEXT_SUFFIXES = {".py", ".php", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".json", ".yml", ".yaml", ".toml", ".ini", ".md", ".txt"}


@dataclass(frozen=True)
class ToolCandidate:
    path: str
    kind: str
    capabilities: tuple[str, ...]
    recommendation: str
    confidence: str
    reason: str
    absorb_commands: tuple[tuple[str, ...], ...] = ()
    replacement_safe: bool = False
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capabilities"] = list(self.capabilities)
        payload["absorb_commands"] = [list(command) for command in self.absorb_commands]
        payload["evidence"] = list(self.evidence)
        payload["classification"] = self.recommendation
        return payload


def _read_text(path: Path, limit: int = 1_000_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capabilities(path: Path, text: str) -> set[str]:
    lowered = (path.name + "\n" + text[:200_000]).lower()
    caps: set[str] = set()
    probes = {
        "tests": ("pytest", "phpunit", "unittest", "npm test", "run tests", "test runner", "test_"),
        "lint": ("eslint", "ruff", "phpcs", "pylint", "stylelint", "lint"),
        "type-check": ("mypy", "pyright", "phpstan", "psalm", "typescript", "tsc --noemit"),
        "format": ("prettier", "black", "php-cs-fixer", "format"),
        "packaging": ("zipfile", "zip -r", "archive", "deploy package", "package release"),
        "secret-scan": ("private key", "api_key", "client_secret", "secret scan", "credential"),
        "merge-markers": ("<<<<<<<", ">>>>>>>", "merge marker", "conflict marker"),
        "release-version": ("version", "release.json", "changelog", "tag"),
        "deployment": ("deploy", "rsync", "scp", "ftp", "cpanel", "docker push"),
        "documentation": ("docs", "documentation", "readme"),
        "css-wiring": ("css selector", "orphan", "class=", "stylesheet"),
        "security": ("security", "vulnerability", "owasp"),
        "ai-instructions": ("claude", "agent", "copilot", "cursor"),
        "architecture-graph": ("dependency graph", "architecture graph", "import graph", "blast radius", "impact analysis", "madge", "dependency-cruiser", "pydeps"),
        "defect-memory": ("defect ledger", "regression memory", "known defect", "postmortem", "root cause", "invariant"),
        "live-lab": ("playwright", "cypress", "selenium", "puppeteer", "docker compose", "http.server", "php -s", "smoke test", "end-to-end"),
    }
    for capability, tokens in probes.items():
        if any(token in lowered for token in tokens):
            caps.add(capability)
    return caps


def _script_command(relative: str, suffix: str) -> tuple[str, ...] | None:
    if suffix == ".py":
        return ("{python}", "{project}/" + relative)
    if suffix in {".php", ".phtml"}:
        return ("php", "{project}/" + relative)
    if suffix in {".sh", ".bash"}:
        return ("sh", "{project}/" + relative)
    if suffix in {".js", ".mjs", ".cjs"}:
        return ("node", "{project}/" + relative)
    return None


def _node_package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "bun.lock").is_file() or (root / "bun.lockb").is_file():
        return "bun"
    return "npm"


def _package_commands(root: Path, path: Path) -> list[ToolCandidate]:
    relative = path.relative_to(root).as_posix()
    candidates: list[ToolCandidate] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return candidates
    scripts = raw.get("scripts", {}) if isinstance(raw, dict) else {}
    if not isinstance(scripts, dict):
        return candidates
    manager = _node_package_manager(root)
    for name in sorted(scripts):
        lowered = str(name).lower()
        profile = ""
        caps: tuple[str, ...] = ()
        if any(token in lowered for token in ("lint", "check", "typecheck", "type-check", "format:check")):
            profile, caps = "quick", ("lint",)
        elif any(token in lowered for token in ("test", "unit", "spec")) and not any(token in lowered for token in ("e2e", "integration")):
            profile, caps = "section", ("tests",)
        elif any(token in lowered for token in ("e2e", "integration", "build", "release", "verify")):
            profile, caps = "release", ("tests",) if "test" in lowered or "e2e" in lowered or "integration" in lowered else ("packaging",)
        if not profile:
            continue
        if str(name) == "test" and manager in {"npm", "pnpm", "yarn"}:
            package_command = (manager, "test")
        else:
            package_command = (manager, "run", str(name))
        candidates.append(ToolCandidate(
            path=f"{relative}#scripts.{name}",
            kind="package-script",
            capabilities=caps,
            recommendation="absorb",
            confidence="high",
            reason=f"Existing package-manager script can be orchestrated by Forge's {profile} profile without replacing its implementation.",
            absorb_commands=(package_command,),
        ))
    return candidates


def _composer_commands(root: Path, path: Path) -> list[ToolCandidate]:
    relative = path.relative_to(root).as_posix()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = raw.get("scripts", {}) if isinstance(raw, dict) else {}
    if not isinstance(scripts, dict):
        return []
    candidates: list[ToolCandidate] = []
    for name in sorted(scripts):
        lowered = str(name).lower()
        if any(token in lowered for token in ("lint", "check", "analyse", "analyze", "static")):
            profile, caps = "quick", ("lint",)
        elif any(token in lowered for token in ("test", "unit")):
            profile, caps = "section", ("tests",)
        elif any(token in lowered for token in ("build", "release", "verify", "integration")):
            profile, caps = "release", ("packaging",)
        else:
            continue
        candidates.append(ToolCandidate(
            path=f"{relative}#scripts.{name}", kind="composer-script", capabilities=caps,
            recommendation="absorb", confidence="high",
            reason=f"Existing Composer script can be orchestrated by Forge's {profile} profile without replacing its implementation.",
            absorb_commands=(("composer", "run-script", str(name)),),
        ))
    return candidates






ECOSYSTEM_PROFILE_NAMES = {"quick": "quick", "section": "section", "toolset": "section", "release": "release"}
ECOSYSTEM_STATE_KEYWORDS = ("check", "acceptance", "report", "evidence", "coverage", "result")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "tool-ecosystem"


def _embedded_forge_roots(project_root: Path, forge_root: Path) -> dict[str, dict[str, Any]]:
    roots: dict[str, dict[str, Any]] = {}
    for manifest in iter_project_files(
        project_root,
        [".forge", ".git", "node_modules", "vendor", "deploy", "dist", "build"],
        forge_root,
    ):
        if manifest.name != "FORGE-MANIFEST.json":
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or "forge_schema" not in payload:
            continue
        root = manifest.parent.resolve()
        if root == project_root.resolve() or root == forge_root.resolve():
            continue
        try:
            relative = root.relative_to(project_root.resolve()).as_posix()
        except ValueError:
            continue
        roots[relative] = {
            "path": relative,
            "manifest": manifest.relative_to(project_root).as_posix(),
            "name": str(payload.get("name", "Emotivus Forge")),
            "version": str(payload.get("version", "")),
        }
    return roots


def _expand_manifest_paths(project_root: Path, patterns: list[Any]) -> tuple[dict[str, Path], list[str]]:
    files: dict[str, Path] = {}
    problems: list[str] = []
    for raw_value in patterns:
        if not isinstance(raw_value, str) or not raw_value.strip():
            problems.append("canonical_paths contains a non-string or empty entry")
            continue
        raw = raw_value.strip().replace("\\", "/")
        rel = Path(raw.rstrip("/"))
        if rel.is_absolute() or ".." in rel.parts:
            problems.append(f"unsafe canonical path: {raw}")
            continue
        matches: list[Path] = []
        candidate = project_root / rel
        try:
            if raw.endswith("/"):
                if candidate.is_dir():
                    matches = [item for item in candidate.rglob("*") if item.is_file() and not item.is_symlink()]
                else:
                    problems.append(f"required ecosystem directory is missing: {raw}")
            elif any(char in raw for char in "*?["):
                matches = [item for item in project_root.glob(raw) if item.is_file() and not item.is_symlink()]
                if not matches:
                    problems.append(f"ecosystem pattern matched no files: {raw}")
            elif candidate.is_file() and not candidate.is_symlink():
                matches = [candidate]
            elif candidate.is_dir():
                matches = [item for item in candidate.rglob("*") if item.is_file() and not item.is_symlink()]
            else:
                problems.append(f"required ecosystem file is missing: {raw}")
        except OSError as exc:
            problems.append(f"cannot expand ecosystem path {raw}: {exc}")
            continue
        for path in matches:
            try:
                relative = path.resolve().relative_to(project_root.resolve()).as_posix()
            except ValueError:
                problems.append(f"ecosystem path escapes the project root: {path}")
                continue
            if any(part in {".git", "__pycache__"} for part in Path(relative).parts):
                continue
            files[relative] = path
    return files, problems


def _member_role(relative: str, manifest_relative: str) -> str:
    path = Path(relative)
    parts = {part.lower() for part in path.parts}
    lowered = path.name.lower()
    if relative == manifest_relative or lowered in {"release.json", "release_checks.json"} or "manifest" in lowered:
        return "manifest-config"
    if "fixtures" in parts:
        return "fixture"
    if "data" in parts or any(token in lowered for token in ("baseline", "allowlist", "allow", "registry", "scenario", "ownership", "reachability")):
        return "static-dataset"
    if path.parts and path.parts[0].lower() in {"tests", "test"}:
        return "test-source"
    if path.parts and path.parts[0].lower() in TOOL_DIR_HINTS:
        return "tool-source"
    if path.parts and path.parts[0].lower() in {"docs", "planning"} or path.suffix.lower() == ".md":
        return "documentation"
    if path.parts and path.parts[0].lower() in {"includes", "include", "lib", "src"}:
        return "runtime-support"
    if path.name in CONFIG_NAMES or path.name in {".gitignore", ".deployignore"}:
        return "tool-configuration"
    return "supporting-file"


def _parse_manifest_command(value: Any) -> list[str]:
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return [str(item) for item in value]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        return shlex.split(value)
    except ValueError:
        return []


def _generated_state_paths(project_root: Path, member_paths: Iterable[str], payload: dict[str, Any]) -> list[dict[str, Any]]:
    discovered: set[str] = set()
    forge_options = payload.get("forge", {}) if isinstance(payload.get("forge"), dict) else {}
    explicit = forge_options.get("generated_state", [])
    if isinstance(explicit, str):
        explicit = [explicit]
    if isinstance(explicit, list):
        discovered.update(str(item).strip().replace("\\", "/").rstrip("/") for item in explicit if str(item).strip())
    assignment = re.compile(r"(?i)(?:REPORT|OUTPUT|STATE|CACHE)_DIR\s*=\s*['\"]([^'\"]+)['\"]")
    dotted = re.compile(r"(?<![A-Za-z0-9_])(\.[A-Za-z0-9_-]+(?:/[A-Za-z0-9_./{}-]*)?)")
    for relative in member_paths:
        path = project_root / relative
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = _read_text(path, limit=500_000)
        if not text:
            continue
        discovered.update(match.replace("\\", "/").rstrip("/") for match in assignment.findall(text))
        for match in dotted.findall(text):
            lowered = match.lower()
            if any(keyword in lowered for keyword in ECOSYSTEM_STATE_KEYWORDS):
                discovered.add(match.replace("\\", "/").rstrip("/"))
    entries: list[dict[str, Any]] = []
    for raw in sorted(discovered):
        rel = Path(raw)
        if not raw or rel.is_absolute() or ".." in rel.parts or raw.startswith(".forge"):
            continue
        path = project_root / rel
        file_count = 0
        total_bytes = 0
        if path.is_file():
            file_count = 1
            total_bytes = path.stat().st_size
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    file_count += 1
                    total_bytes += child.stat().st_size
        entries.append({"path": rel.as_posix(), "exists": path.exists(), "files": file_count, "bytes": total_bytes})
    return entries


def discover_tool_ecosystems(project_root: Path, forge_root: Path) -> list[dict[str, Any]]:
    project_root = project_root.resolve()
    embedded = _embedded_forge_roots(project_root, forge_root)
    ecosystems: list[dict[str, Any]] = []
    for manifest in iter_project_files(
        project_root,
        [".forge", ".git", "node_modules", "vendor", "deploy", "dist", "build", *embedded.keys()],
        forge_root,
    ):
        if manifest.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("canonical_paths"), list) or not isinstance(payload.get("commands"), dict):
            continue
        if "forge_schema" in payload:
            continue
        manifest_relative = manifest.relative_to(project_root).as_posix()
        expanded, problems = _expand_manifest_paths(project_root, payload.get("canonical_paths", []))
        expanded[manifest_relative] = manifest
        managed_paths = set(expanded)
        bundled_products: list[dict[str, Any]] = []
        bundled_roots: set[str] = set()
        for root_relative, metadata in embedded.items():
            if any(path == root_relative or path.startswith(root_relative + "/") for path in managed_paths):
                nested_paths = sorted(path for path in managed_paths if path == root_relative or path.startswith(root_relative + "/"))
                fingerprint = declared_paths_fingerprint(project_root, nested_paths)
                bundled_products.append({**metadata, "managed_files": len(nested_paths), "fingerprint": fingerprint})
                bundled_roots.add(root_relative)
        members: list[dict[str, Any]] = []
        role_paths: dict[str, list[str]] = {}
        for relative, path in sorted(expanded.items()):
            if any(relative == root or relative.startswith(root + "/") for root in bundled_roots):
                continue
            role = _member_role(relative, manifest_relative)
            role_paths.setdefault(role, []).append(relative)
            try:
                size = path.stat().st_size
                digest = _sha256(path)
            except OSError:
                size = 0
                digest = ""
            members.append({"path": relative, "role": role, "bytes": size, "sha256": digest})
        command_entries: list[dict[str, Any]] = []
        utility_entries: list[dict[str, Any]] = []
        for name, raw_command in payload.get("commands", {}).items():
            command = _parse_manifest_command(raw_command)
            if not command:
                utility_entries.append({"name": str(name), "command": [], "automatic": False, "reason": "command could not be parsed"})
                continue
            contains_placeholder = any("<" in item or ">" in item for item in command)
            profile = ECOSYSTEM_PROFILE_NAMES.get(str(name).lower(), "")
            entry = {"name": str(name), "command": command, "profile": profile, "automatic": bool(profile and not contains_placeholder)}
            if entry["automatic"]:
                command_entries.append(entry)
            else:
                utility_entries.append(entry)
        input_paths = sorted(expanded)
        dataset_paths = sorted(role_paths.get("manifest-config", []) + role_paths.get("static-dataset", []) + role_paths.get("fixture", []))
        input_fingerprint = declared_paths_fingerprint(project_root, input_paths)
        dataset_fingerprint = declared_paths_fingerprint(project_root, dataset_paths)
        delivery_artifacts: list[str] = []
        raw_artifact = payload.get("delivery_artifact")
        if isinstance(raw_artifact, str) and raw_artifact.strip():
            delivery_artifacts.append(raw_artifact.strip().replace("\\", "/"))
        elif isinstance(raw_artifact, list):
            delivery_artifacts.extend(str(item).strip().replace("\\", "/") for item in raw_artifact if str(item).strip())
        name = str(payload.get("name") or payload.get("title") or manifest.stem.replace("-", " ").replace("_", " ").title()).strip()
        ecosystem_id = _slug(name or manifest.stem)
        ecosystems.append({
            "schema": 1,
            "id": ecosystem_id,
            "name": name or ecosystem_id,
            "manifest": manifest_relative,
            "authority": "host-authoritative",
            "status": "ready" if not problems and command_entries else "review",
            "problems": problems + ([] if command_entries else ["manifest provides no safe automatic quick, section, toolset, or release command"]),
            "commands": command_entries,
            "utilities": utility_entries,
            "working_set": {
                "declared_patterns": [str(item) for item in payload.get("canonical_paths", [])],
                "members": members,
                "managed_paths": sorted(managed_paths),
                "input_paths": input_paths,
                "dataset_paths": dataset_paths,
                "role_counts": {role: len(paths) for role, paths in sorted(role_paths.items())},
                "input_fingerprint": input_fingerprint,
                "dataset_fingerprint": dataset_fingerprint,
            },
            "bundled_products": bundled_products,
            "generated_state": _generated_state_paths(project_root, [item["path"] for item in members], payload),
            "delivery_artifacts": sorted(set(delivery_artifacts)),
        })
    return sorted(ecosystems, key=lambda item: (item["manifest"], item["id"]))


def _cli_evidence(path: Path, text: str, hinted_dir: bool) -> tuple[list[str], bool]:
    evidence: list[str] = []
    try:
        mode = path.stat().st_mode
        if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            evidence.append("executable-bit")
    except OSError:
        pass
    first = text.splitlines()[0] if text.splitlines() else ""
    if first.startswith("#!"):
        evidence.append("shebang")
    lowered = text.lower()
    cli_tokens = (
        "argparse", "sys.argv", "process.argv", "$argv", "getopt(", "getopt_long(",
        "if __name__ ==", "exit(", "sys.exit", "process.exit", "stderr", "php_sapi",
    )
    if any(token in lowered for token in cli_tokens):
        evidence.append("cli-semantics")
    if hinted_dir:
        evidence.append("tool-directory")
    if TOOL_NAME_RE.search(path.stem):
        evidence.append("tool-name")
    affirmative = bool(set(evidence) & {"executable-bit", "shebang", "cli-semantics", "tool-directory"})
    return evidence, affirmative


def _php_included_paths(project_root: Path, forge_root: Path, extra_excludes: Iterable[str] = ()) -> set[str]:
    included: set[str] = set()
    pattern = re.compile(r"(?i)\b(?:require|include)(?:_once)?\s*(?:\(\s*)?['\"]([^'\"]+)['\"]")
    excludes = [".forge", ".git", "node_modules", "vendor", "deploy", "dist", "build", *extra_excludes]
    for source in iter_project_files(project_root, excludes, forge_root):
        if source.suffix.lower() not in {".php", ".phtml", ".inc"}:
            continue
        relative_source = source.relative_to(project_root)
        if any(part.lower() in TOOL_DIR_HINTS for part in relative_source.parts[:-1]):
            continue
        text = _read_text(source)
        for match in pattern.finditer(text):
            raw = match.group(1).replace("\\", "/")
            if "$" in raw or raw.startswith(("http://", "https://")):
                continue
            candidates = [(source.parent / raw).resolve(), (project_root / raw.lstrip("/")).resolve()]
            for candidate in candidates:
                try:
                    rel = candidate.relative_to(project_root).as_posix()
                except ValueError:
                    continue
                if candidate.exists():
                    included.add(rel)
                    break
    return included


def _looks_like_web_runtime(relative: str, text: str, included_by_app: bool) -> bool:
    parts = {part.lower() for part in Path(relative).parts[:-1]}
    runtime_dirs = {"app", "public", "admin", "includes", "include", "templates", "views", "controllers", "routes", "pages", "src"}
    lowered = text.lower()
    web_tokens = ("$_get", "$_post", "$_request", "$_session", "session_start(", "<!doctype", "<html", "header(", "setcookie(")
    return included_by_app or bool(parts & runtime_dirs) or any(token in lowered for token in web_tokens)

def _forge_owned_path(relative: str) -> bool:
    return (
        relative in {"forge.py", "forge", "forge.cmd", "FORGE-MANIFEST.json"}
        or relative.startswith("emotivus_forge/")
        or relative.startswith("tests/")
        or relative in {"tools/build_forge_package.py", "tools/forge_bootstrap.py"}
    )

def scan_existing_tools(project_root: Path, forge_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    candidates: list[ToolCandidate] = []
    self_hosting = is_forge_project(project_root)
    ecosystems = discover_tool_ecosystems(project_root, forge_root)
    managed_paths = {
        str(path)
        for ecosystem in ecosystems
        for path in ecosystem.get("working_set", {}).get("managed_paths", [])
    }
    embedded_roots = set(_embedded_forge_roots(project_root, forge_root))
    scan_excludes = [".forge", ".git", "node_modules", "vendor", "deploy", "dist", "build", *sorted(embedded_roots)]
    php_included = _php_included_paths(project_root, forge_root, scan_excludes)
    for path in iter_project_files(project_root, scan_excludes, forge_root):
        relative = path.relative_to(project_root).as_posix()
        if relative in managed_paths:
            continue
        if relative in {"FORGE-AGENT.md", ".emotivus-forge.json"}:
            continue
        if path.name == "package.json":
            candidates.extend(_package_commands(project_root, path))
        elif path.name == "composer.json":
            candidates.extend(_composer_commands(project_root, path))
        parts_lower = {part.lower() for part in Path(relative).parts}
        hinted_dir = bool(parts_lower & TOOL_DIR_HINTS)
        is_ci = relative.startswith(CI_PREFIXES) or path.name in {".gitlab-ci.yml", "Jenkinsfile"}
        is_agent = path.name in AGENT_FILES
        is_config = path.name in CONFIG_NAMES
        script_suffix = path.suffix.lower() in {".py", ".php", ".sh", ".bash", ".js", ".mjs", ".cjs"}
        preliminary_script = script_suffix and (hinted_dir or TOOL_NAME_RE.search(path.stem))
        if not (is_ci or is_agent or is_config or preliminary_script):
            continue
        text = _read_text(path) if path.suffix.lower() in TEXT_SUFFIXES or is_agent or is_config else ""
        evidence, affirmative_tool = _cli_evidence(path, text, hinted_dir)
        web_runtime = _looks_like_web_runtime(relative, text, relative in php_included) if script_suffix else False
        is_script = bool(preliminary_script and (affirmative_tool or TOOL_NAME_RE.search(path.stem)))
        if not (is_ci or is_agent or is_config or is_script):
            continue
        caps = _capabilities(path, text)
        if self_hosting and _forge_owned_path(relative):
            candidates.append(ToolCandidate(
                relative, "forge-core", tuple(sorted(caps)), "retain", "high",
                "This file is part of the active Forge Core implementation or its certification suite. Mirror validates it as Forge itself; it is not a competing project tool."
            ))
            continue
        if is_ci:
            candidates.append(ToolCandidate(relative, "ci-orchestration", tuple(sorted(caps or {"deployment"})), "retain", "high", "CI configuration may call project-specific services and should remain the outer automation layer; Forge can be invoked from it."))
            continue
        if is_agent:
            candidates.append(ToolCandidate(relative, "agent-instructions", tuple(sorted(caps or {"ai-instructions"})), "review", "high", "Human-authored project instructions should be compared and manually merged with the Forge agent contract rather than discarded or executed."))
            continue
        if is_config:
            candidates.append(ToolCandidate(relative, "tool-configuration", tuple(sorted(caps)), "retain", "high", "This configuration defines an underlying tool. Forge should orchestrate it, not replace the tool itself."))
            continue
        command = _script_command(relative, path.suffix.lower())
        replacement_safe = caps == {"merge-markers"} and len(text.splitlines()) <= 180 and affirmative_tool and not web_runtime
        if web_runtime:
            recommendation = "retain"
            reason = "This file appears to be application runtime code or is included by a web entry point; Forge will not register it as a quality command."
            confidence = "high"
        elif replacement_safe:
            recommendation = "replace"
            reason = "This appears to be a narrow CLI merge-marker checker already covered by a non-baselinable Forge blocker. It may be quarantined after review."
            confidence = "high"
        elif caps.intersection({"tests", "lint", "type-check", "format", "css-wiring"}) and command and affirmative_tool:
            recommendation = "absorb"
            reason = "Affirmative CLI/tooling evidence and quality capabilities make this command safe to register while preserving its implementation."
            confidence = "high" if set(evidence) & {"cli-semantics", "shebang", "executable-bit"} else "medium"
        elif caps.intersection({"packaging", "secret-scan", "release-version", "architecture-graph", "defect-memory", "live-lab"}):
            recommendation = "review"
            reason = "This overlaps Forge but may contain project-specific knowledge. Compare behavior before orchestration or replacement."
            confidence = "medium"
        else:
            recommendation = "retain"
            reason = "The file lacks enough affirmative CLI evidence for safe absorption or its purpose is not safely replaceable from static inspection."
            confidence = "medium"
        candidates.append(ToolCandidate(relative, "script", tuple(sorted(caps)), recommendation, confidence, reason, (command,) if recommendation == "absorb" and command else (), replacement_safe, tuple(evidence)))

    deduped: dict[tuple[str, str], ToolCandidate] = {}
    for candidate in candidates:
        deduped[(candidate.path, candidate.kind)] = candidate
    ordered = sorted(deduped.values(), key=lambda item: (item.recommendation, item.path))
    counts = {key: sum(1 for item in ordered if item.recommendation == key) for key in ("absorb", "retain", "review", "replace")}
    return {
        "schema": 2,
        "generated_utc": utc_now(),
        "project_root": str(project_root),
        "counts": counts,
        "ecosystem_count": len(ecosystems),
        "managed_path_count": len(managed_paths),
        "embedded_forge_roots": sorted(embedded_roots),
        "ecosystems": ecosystems,
        "candidates": [item.as_dict() for item in ordered],
    }


def _profile_for(candidate: dict[str, Any]) -> str:
    path = str(candidate.get("path", "")).lower()
    caps = set(candidate.get("capabilities", []))
    if caps.intersection({"lint", "type-check", "format", "merge-markers"}):
        return "quick"
    if "tests" in caps and not any(token in path for token in ("e2e", "integration")):
        return "section"
    return "release"


def _evidence_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    path = str(candidate.get("path", "")).lower()
    caps = {str(item) for item in candidate.get("capabilities", [])}
    types: list[str] = []
    surfaces: list[str] = []
    if caps.intersection({"lint", "type-check", "format", "merge-markers", "css-wiring"}):
        types.append("static")
    if "tests" in caps:
        if any(token in path for token in ("browser", "playwright", "cypress", "selenium", "e2e")):
            types.extend(["browser-behavior", "entrypoint-execution"])
            surfaces.append("all:browser-page")
        elif any(token in path for token in ("page", "route", "render", "execution", "smoke")):
            types.append("entrypoint-execution")
            surfaces.extend(["all:browser-page", "all:route", "all:entrypoint"])
        elif "integration" in path:
            types.append("integration")
        else:
            types.append("unit")
    if any(token in path for token in ("migration", "schema", "upgrade")):
        types.extend(["database-upgrade", "integration"])
    if "packaging" in caps or any(token in path for token in ("package", "deploy", "release")):
        types.append("package")
    return {"types": sorted(set(types)), "surfaces": sorted(set(surfaces))}



def _command_identity(command: Iterable[Any]) -> tuple[str, ...]:
    normalized: list[str] = []
    for index, raw in enumerate(command):
        value = str(raw)
        if index == 0 and Path(value).name.lower() in {"python", "python3", "python.exe", "py"}:
            value = "{python}"
        if value == "--fresh":
            continue
        normalized.append(value)
    return tuple(normalized)


def _adopt_ecosystems(config: dict[str, Any], inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    adopted: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    commands = config.setdefault("commands", {"quick": [], "section": [], "release": []})
    existing_entries: list[tuple[str, dict[str, Any]]] = [
        (profile, item)
        for profile, group in commands.items()
        for item in group
        if isinstance(item, dict) and isinstance(item.get("command"), list)
    ]
    existing_ids = {str(item.get("id")) for _, item in existing_entries}

    for ecosystem in inventory.get("ecosystems", []):
        if not isinstance(ecosystem, dict):
            continue
        ecosystem_id = str(ecosystem.get("id", "tool-ecosystem"))
        registry_path = f".forge/tool-ecosystems/{ecosystem_id}.json"
        registrations: list[dict[str, Any]] = []
        if ecosystem.get("status") != "ready":
            records.append({
                "id": ecosystem_id,
                "name": ecosystem.get("name"),
                "manifest": ecosystem.get("manifest"),
                "authority": "host-authoritative",
                "status": "review",
                "registry": registry_path,
                "problems": list(ecosystem.get("problems", [])),
                "registrations": [],
            })
            continue
        input_paths = [str(item) for item in ecosystem.get("working_set", {}).get("input_paths", [])]
        dataset_sha = str(ecosystem.get("working_set", {}).get("dataset_fingerprint", {}).get("sha256", ""))
        for command_spec in ecosystem.get("commands", []):
            if not isinstance(command_spec, dict) or not command_spec.get("automatic"):
                continue
            command = [str(item) for item in command_spec.get("command", [])]
            profile = str(command_spec.get("profile", ""))
            if not command or profile not in {"quick", "section", "release"}:
                continue
            identity = _command_identity(command)
            matched: tuple[str, dict[str, Any]] | None = next(
                ((existing_profile, item) for existing_profile, item in existing_entries if _command_identity(item.get("command", [])) == identity),
                None,
            )
            lifecycle = {"status": "active", "temporary": False, "replacement_condition": "", "review_on": "tool-manifest-or-working-set-change"}
            if matched is not None:
                existing_profile, entry = matched
                entry.setdefault("source", "adopted-tool-ecosystem")
                entry.setdefault("authority", "host-authoritative")
                entry["ecosystem_id"] = ecosystem_id
                entry["ecosystem_manifest"] = str(ecosystem.get("manifest", ""))
                entry["ecosystem_inputs"] = input_paths
                entry["ecosystem_dataset_sha256"] = dataset_sha
                entry.setdefault("lifecycle", lifecycle)
                registrations.append({
                    "id": entry.get("id"),
                    "profile": existing_profile,
                    "command": entry.get("command"),
                    "status": "adopted-existing-registration",
                })
                continue
            base_name = _slug(str(command_spec.get("name") or profile))
            check_id = f"ecosystem.{ecosystem_id}.{base_name}"
            suffix = 2
            while check_id in existing_ids:
                check_id = f"ecosystem.{ecosystem_id}.{base_name}.{suffix}"
                suffix += 1
            timeout = {"quick": 900, "section": 1800, "release": 3600}[profile]
            entry = {
                "id": check_id,
                "command": command,
                "timeout": timeout,
                "required": True,
                "source": "adopted-tool-ecosystem",
                "capabilities": ["tests", "tool-orchestration"],
                "test_entry_point": True,
                "authority": "host-authoritative",
                "evidence": {"types": [], "surfaces": []},
                "ecosystem_id": ecosystem_id,
                "ecosystem_manifest": str(ecosystem.get("manifest", "")),
                "ecosystem_inputs": input_paths,
                "ecosystem_dataset_sha256": dataset_sha,
                "lifecycle": lifecycle,
            }
            commands.setdefault(profile, []).append(entry)
            existing_entries.append((profile, entry))
            existing_ids.add(check_id)
            registration = {"id": check_id, "profile": profile, "command": command, "status": "registered"}
            registrations.append(registration)
            adopted.append({
                "id": check_id,
                "profile": profile,
                "path": ecosystem.get("manifest"),
                "command": command,
                "authority": "host-authoritative",
                "ecosystem_id": ecosystem_id,
                "lifecycle": lifecycle,
            })
        records.append({
            "id": ecosystem_id,
            "name": ecosystem.get("name"),
            "manifest": ecosystem.get("manifest"),
            "authority": "host-authoritative",
            "status": "active" if registrations else "review",
            "registry": registry_path,
            "input_fingerprint": ecosystem.get("working_set", {}).get("input_fingerprint", {}),
            "dataset_fingerprint": ecosystem.get("working_set", {}).get("dataset_fingerprint", {}),
            "generated_state": ecosystem.get("generated_state", []),
            "bundled_products": ecosystem.get("bundled_products", []),
            "registrations": registrations,
        })
    return adopted, records


def absorb_tools(config: dict[str, Any], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    ecosystem_adopted, ecosystem_records = _adopt_ecosystems(config, inventory)
    absorbed: list[dict[str, Any]] = list(ecosystem_adopted)
    commands = config.setdefault("commands", {"quick": [], "section": [], "release": []})
    existing = {str(item.get("id")) for group in commands.values() for item in group if isinstance(item, dict)}
    existing_commands = {
        tuple(str(part) for part in item.get("command", []))
        for group in commands.values()
        for item in group
        if isinstance(item, dict) and isinstance(item.get("command"), list)
    }
    for candidate in inventory.get("candidates", []):
        if candidate.get("recommendation") != "absorb":
            continue
        for index, command in enumerate(candidate.get("absorb_commands", []), start=1):
            if not isinstance(command, list) or not command:
                continue
            base = re.sub(r"[^a-z0-9]+", ".", str(candidate.get("path", "tool")).lower()).strip(".")
            check_id = f"existing.{base}" + (f".{index}" if index > 1 else "")
            command_tuple = tuple(str(item) for item in command)
            if check_id in existing or command_tuple in existing_commands:
                continue
            profile = _profile_for(candidate)
            capabilities = [str(item) for item in candidate.get("capabilities", [])]
            entry = {
                "id": check_id, "command": list(command_tuple), "timeout": 300,
                "source": "absorbed-existing-tool", "capabilities": capabilities,
                "test_entry_point": "tests" in capabilities,
                "authority": "host-authoritative",
                "evidence": _evidence_for_candidate(candidate),
                "lifecycle": {"status": "active", "temporary": False, "replacement_condition": "", "review_on": "tool-or-scope-change"},
            }
            commands.setdefault(profile, []).append(entry)
            existing.add(check_id)
            existing_commands.add(command_tuple)
            absorbed.append({"id": check_id, "profile": profile, "path": candidate.get("path"), "command": command, "authority": "host-authoritative", "lifecycle": entry["lifecycle"]})
    tool_migration = config.setdefault("tool_migration", {})
    tool_migration["absorbed"] = absorbed
    tool_migration["ecosystems"] = ecosystem_records
    lifecycle = tool_migration.setdefault("lifecycle", [])
    known = {str(item.get("id")) for item in lifecycle if isinstance(item, dict)}
    lifecycle.extend(item for item in absorbed if item["id"] not in known)
    return absorbed


def quarantine_replacements(project_root: Path, inventory: dict[str, Any], *, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise RuntimeError("tool removal requires explicit confirmation; rerun with --confirm-tool-removal")
    project_root = project_root.resolve()
    quarantine_root = project_root / ".forge" / "legacy-tools"
    entries: list[dict[str, Any]] = []
    for candidate in inventory.get("candidates", []):
        if candidate.get("recommendation") != "replace" or not candidate.get("replacement_safe"):
            continue
        raw_path = str(candidate.get("path", ""))
        if "#" in raw_path:
            continue
        source = (project_root / raw_path).resolve()
        try:
            source.relative_to(project_root)
        except ValueError:
            continue
        if not source.is_file():
            continue
        target = quarantine_root / raw_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise RuntimeError(f"quarantine target already exists: {target}")
        before_hash = _sha256(source)
        shutil.move(str(source), str(target))
        entries.append({"original": raw_path, "quarantined": target.relative_to(project_root).as_posix(), "sha256": before_hash})
    manifest = {
        "schema": 1,
        "generated_utc": utc_now(),
        "operation": "quarantine-overlapping-tools",
        "entries": entries,
        "restore": "Move each quarantined file back to its original path after verifying the SHA-256 hash.",
    }
    write_json(quarantine_root / "RESTORE-MANIFEST.json", manifest)
    return manifest


def _member_hashes(ecosystem: dict[str, Any]) -> dict[str, str]:
    members = ecosystem.get("working_set", {}).get("members", [])
    return {str(item.get("path")): str(item.get("sha256", "")) for item in members if isinstance(item, dict) and item.get("path")}


def _ecosystem_lifecycle_events(previous: dict[str, Any] | None, current: dict[str, Any], adopted_ids: set[str]) -> list[dict[str, Any]]:
    ecosystem_id = str(current.get("id", "tool-ecosystem"))
    now = utc_now()
    events: list[dict[str, Any]] = []
    if previous is None:
        events.append({
            "type": "ecosystem-discovered", "utc": now, "ecosystem_id": ecosystem_id,
            "manifest": str(current.get("manifest", "")), "status": str(current.get("status", "")),
            "input_sha256": str(current.get("working_set", {}).get("input_fingerprint", {}).get("sha256", "")),
        })
    else:
        before = _member_hashes(previous)
        after = _member_hashes(current)
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        if changed:
            events.append({
                "type": "ecosystem-inputs-changed", "utc": now, "ecosystem_id": ecosystem_id,
                "changed_paths": changed,
                "previous_input_sha256": str(previous.get("working_set", {}).get("input_fingerprint", {}).get("sha256", "")),
                "input_sha256": str(current.get("working_set", {}).get("input_fingerprint", {}).get("sha256", "")),
                "evidence_disposition": "stale-until-rerun",
            })
        if str(previous.get("status", "")) != str(current.get("status", "")):
            events.append({
                "type": "ecosystem-status-changed", "utc": now, "ecosystem_id": ecosystem_id,
                "previous_status": str(previous.get("status", "")), "status": str(current.get("status", "")),
            })
    if ecosystem_id in adopted_ids:
        events.append({
            "type": "ecosystem-adopted", "utc": now, "ecosystem_id": ecosystem_id,
            "authority": "host-authoritative", "operation": "metadata-and-orchestration-only",
        })
    return events


def write_tool_reports(project_root: Path, inventory: dict[str, Any], absorbed: Iterable[dict[str, Any]] = (), quarantine: dict[str, Any] | None = None) -> dict[str, str]:
    reports = project_root / ".forge" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / "tool-inventory.json"
    write_json(json_path, inventory)

    ecosystems = [item for item in inventory.get("ecosystems", []) if isinstance(item, dict)]
    ecosystem_report = {
        "schema": 1,
        "generated_utc": inventory.get("generated_utc", utc_now()),
        "count": len(ecosystems),
        "ecosystems": ecosystems,
    }
    ecosystem_json = reports / "tool-ecosystems.json"
    write_json(ecosystem_json, ecosystem_report)
    registry_dir = project_root / ".forge" / "tool-ecosystems"
    registry_dir.mkdir(parents=True, exist_ok=True)
    adopted_list = list(absorbed)
    adopted_ids = {str(item.get("ecosystem_id", "")) for item in adopted_list if isinstance(item, dict) and item.get("ecosystem_id")}
    lifecycle_path = registry_dir / "lifecycle.json"
    try:
        lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8")) if lifecycle_path.is_file() else {"schema": 1, "events": []}
    except (OSError, json.JSONDecodeError):
        lifecycle = {"schema": 1, "events": []}
    if not isinstance(lifecycle, dict) or not isinstance(lifecycle.get("events"), list):
        lifecycle = {"schema": 1, "events": []}
    for ecosystem in ecosystems:
        registry_path = registry_dir / f"{ecosystem.get('id', 'tool-ecosystem')}.json"
        try:
            previous = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else None
        except (OSError, json.JSONDecodeError):
            previous = None
        lifecycle["events"].extend(_ecosystem_lifecycle_events(previous if isinstance(previous, dict) else None, ecosystem, adopted_ids))
        write_json(registry_path, ecosystem)
    lifecycle["updated_utc"] = utc_now()
    lifecycle["events"] = lifecycle["events"][-1000:]
    write_json(lifecycle_path, lifecycle)

    text_path = reports / "tool-inventory.txt"
    lines = [
        "EMOTIVUS FORGE — EXISTING TOOL INVENTORY",
        "",
        "Actions are recommendations, not proof that a file is obsolete.",
        "Forge never deletes detected tools automatically.",
        "",
    ]
    if ecosystems:
        lines.extend(["MANIFEST-BACKED TOOL ECOSYSTEMS", ""])
        for ecosystem in ecosystems:
            working = ecosystem.get("working_set", {})
            input_state = working.get("input_fingerprint", {})
            dataset_state = working.get("dataset_fingerprint", {})
            lines.extend([
                f"[ECOSYSTEM:{str(ecosystem.get('status', '')).upper()}] {ecosystem.get('name')} ({ecosystem.get('id')})",
                f"  Manifest: {ecosystem.get('manifest')} | Authority: {ecosystem.get('authority')}",
                f"  Managed paths: {len(working.get('managed_paths', []))} | Indexed members: {len(working.get('members', []))} | Bundled products: {len(ecosystem.get('bundled_products', []))}",
                f"  Full input fingerprint: {input_state.get('sha256', '')} | Dataset fingerprint: {dataset_state.get('sha256', '')}",
                "  Automatic profiles: " + (", ".join(f"{item.get('name')}→{item.get('profile')}" for item in ecosystem.get('commands', [])) or "none"),
                "  Generated state: " + (", ".join(f"{item.get('path')} ({'present' if item.get('exists') else 'not present'})" for item in ecosystem.get('generated_state', [])) or "none detected"),
            ])
            for problem in ecosystem.get("problems", []):
                lines.append(f"  REVIEW: {problem}")
            lines.append("")
        lines.extend(["STANDALONE TOOL CANDIDATES", ""])
    for candidate in inventory.get("candidates", []):
        caps = ", ".join(candidate.get("capabilities", [])) or "unclassified"
        lines.extend([
            f"[{str(candidate.get('recommendation', '')).upper()}] {candidate.get('path')}",
            f"  Kind: {candidate.get('kind')} | Confidence: {candidate.get('confidence')} | Capabilities: {caps}",
            f"  {candidate.get('reason')}",
            "",
        ])
    if not ecosystems and not inventory.get("candidates"):
        lines.append("No existing development or release tooling was detected.")
    text_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    ecosystem_text = reports / "tool-ecosystems.txt"
    ecosystem_lines = [
        "EMOTIVUS FORGE — TOOL ECOSYSTEM REGISTRY",
        "",
        "Forge references host-authoritative working sets in place. It does not copy, flatten, or relocate them.",
        "",
    ]
    for ecosystem in ecosystems:
        working = ecosystem.get("working_set", {})
        ecosystem_lines.extend([
            f"{ecosystem.get('name')} [{ecosystem.get('status')}]",
            f"  Manifest: {ecosystem.get('manifest')}",
            f"  Inputs: {working.get('input_fingerprint', {}).get('files', 0)} files / {working.get('input_fingerprint', {}).get('bytes', 0)} bytes",
            f"  Dataset: {working.get('dataset_fingerprint', {}).get('files', 0)} files / {working.get('dataset_fingerprint', {}).get('bytes', 0)} bytes",
            f"  Registry: .forge/tool-ecosystems/{ecosystem.get('id')}.json",
            "",
        ])
    if not ecosystems:
        ecosystem_lines.append("No manifest-backed tool ecosystem was detected.")
    ecosystem_text.write_text("\n".join(ecosystem_lines).rstrip() + "\n", encoding="utf-8")

    plan_path = project_root / ".forge" / "TOOL-MIGRATION-PLAN.md"
    absorbed_list = adopted_list
    plan = [
        "# Existing Tool Adoption Plan",
        "",
        "Forge treats a mature toolchain as an ecosystem when an authoritative manifest defines its files and commands.",
        "",
        "- **Adopt ecosystem:** register only canonical profile commands, retain every host file in place, index the complete working set, and bind Gate evidence to its current fingerprint.",
        "- **Retain:** the underlying tool, configuration, dataset, and CI layer remain host-authoritative.",
        "- **Absorb standalone:** register a safe command only when it is not already owned by a manifest-backed runner.",
        "- **Review:** overlapping behavior may contain project-specific knowledge and requires comparison.",
        "- **Replace:** only narrow, high-confidence duplication is eligible for reversible quarantine.",
        "",
        "## Safety contract",
        "",
        "Forge does not silently delete, move, rewrite, or duplicate an adopted ecosystem. Generated reports stay in their original directories. The `.forge/tool-ecosystems/` registry contains metadata and hashes, not copied source or datasets.",
        "",
        f"Detected ecosystems: {len(ecosystems)}",
        f"Managed ecosystem paths: {inventory.get('managed_path_count', 0)}",
        f"Standalone candidates: {len(inventory.get('candidates', []))}",
        f"Newly registered commands this run: {len(absorbed_list)}",
        f"Quarantined files this run: {len((quarantine or {}).get('entries', []))}",
        "",
        "Review `.forge/reports/tool-inventory.txt` and `.forge/reports/tool-ecosystems.txt` before changing any existing workflow.",
    ]
    plan_path.write_text("\n".join(plan).rstrip() + "\n", encoding="utf-8")
    return {
        "json": str(json_path),
        "text": str(text_path),
        "ecosystems_json": str(ecosystem_json),
        "ecosystems_text": str(ecosystem_text),
        "registry_dir": str(registry_dir),
        "lifecycle": str(lifecycle_path),
        "plan": str(plan_path),
    }

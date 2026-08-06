from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .baseline import load_baseline
from .learn import evaluate_contracts
from .project_memory import evaluate_project_memory
from .provenance import classify_workspace, packaging_policy_contradictions
from .hygiene import filename_issues, find_merge_markers, is_allowed_zero_byte
from .security import private_key_matches, secret_assignment_matches
from .utils import iter_project_files, normalize_rel, tree_fingerprint, utc_now

TEXT_EXTENSIONS = {
    ".php", ".phtml", ".inc", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    ".css", ".scss", ".sass", ".less", ".html", ".htm", ".xml", ".svg",
    ".json", ".md", ".txt", ".ini", ".conf", ".yml", ".yaml", ".sql", ".sh", ".py",
}
FORBIDDEN_TEMP_SUFFIXES = {".bak", ".orig", ".rej", ".swp", ".swo", ".tmp"}


@dataclass(frozen=True)
class Finding:
    check_id: str
    severity: str
    category: str
    path: str
    message: str
    fingerprint: str
    disposition: str = "NEW"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def make_finding(check_id: str, severity: str, category: str, path: str, message: str) -> Finding:
    stable = f"{check_id}\0{path}\0{message}".encode("utf-8", errors="replace")
    return Finding(check_id, severity, category, path, message, hashlib.sha256(stable).hexdigest())


def _read_text(path: Path, max_bytes: int = 5_000_000) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _run(command: list[str], root: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)


def _css_balance(text: str) -> bool:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", "", text, flags=re.S)
    depth = 0
    for char in text:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def run_audit(project_root: Path, forge_root: Path, config: dict[str, Any], use_baseline: bool = True) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    excludes = set(config.get("paths", {}).get("exclude", []))
    files = list(iter_project_files(project_root, excludes, forge_root))
    adapters = set(config.get("adapters", []))
    findings: list[Finding] = []

    workspace = config.get("workspace") if isinstance(config.get("workspace"), dict) else classify_workspace(project_root, forge_root)
    classification = str(workspace.get("classification", "unknown"))
    if classification in {"deployment-package", "release-candidate"}:
        findings.append(make_finding("workspace.deployment-artifact", "warning", "provenance", "", "This workspace appears to be a deployment artifact, not complete development source. Full development and release certification require the missing authorities."))
    elif classification in {"partial-development-source", "mixed-workspace", "unknown"}:
        findings.append(make_finding("workspace.completeness", "warning", "provenance", "", f"Workspace completeness is {classification}; verify source authority before broad implementation."))
    for contradiction in packaging_policy_contradictions(project_root, config):
        findings.append(make_finding("package.policy-contradiction", "error", "packaging", contradiction.get("source", ""), f"Deployment rule {contradiction.get('rule')} conflicts with {contradiction.get('conflict')}: {contradiction.get('reason')}."))

    for path in files:
        relative = path.relative_to(project_root).as_posix()
        if path.is_symlink():
            findings.append(make_finding("core.symlink", "blocker", "integrity", relative, "Symbolic links are not permitted in the audited source tree."))
            continue
        if path.name in {".DS_Store", "Thumbs.db"} or path.suffix.lower() in FORBIDDEN_TEMP_SUFFIXES:
            findings.append(make_finding("core.temp-file", "warning", "hygiene", relative, "Temporary or editor-generated file is present."))
        for issue in filename_issues(relative):
            findings.append(make_finding("core.hostile-filename", "warning", "hygiene", relative, f"Unsafe or non-portable filename: {issue}."))
        zero_allow = config.get("packaging", {}).get("zero_byte_allow", [".gitkeep", ".keep"])
        try:
            if path.stat().st_size == 0 and not is_allowed_zero_byte(relative, zero_allow):
                findings.append(make_finding("core.zero-byte-file", "warning", "hygiene", relative, "Unexpected zero-byte file is present."))
        except OSError:
            pass

        suffix = path.suffix.lower()
        text = _read_text(path) if suffix in TEXT_EXTENSIONS or path.name.startswith(".env") else None
        if text is not None:
            markers = find_merge_markers(text, suffix)
            if "start" in markers:
                findings.append(make_finding("core.merge-marker-start", "blocker", "integrity", relative, "Unresolved Git conflict start marker found."))
            if "end" in markers:
                findings.append(make_finding("core.merge-marker-end", "blocker", "integrity", relative, "Unresolved Git conflict end marker found."))
            fixture_paths = config.get("security", {}).get("synthetic_fixture_paths", [])
            if private_key_matches(text, relative, fixture_paths):
                findings.append(make_finding("security.private-key", "blocker", "security", relative, "Private-key material is present in source."))
            if secret_assignment_matches(text, relative, fixture_paths):
                is_test_source = any(part.lower() in {"test", "tests", "spec", "specs"} for part in Path(relative).parts[:-1])
                severity = "warning" if is_test_source else "blocker"
                message = (
                    "A credential-like literal appears in test source without a synthetic-fixture declaration."
                    if is_test_source else
                    "A credential-like literal appears to be embedded in source."
                )
                findings.append(make_finding("security.embedded-secret", severity, "security", relative, message))

        if suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(make_finding("syntax.json", "blocker", "syntax", relative, f"Invalid JSON: {exc}"))

    runtime = config.get("runtime", {})
    if "php" in adapters:
        php_binary = shutil.which("php")
        php_required = bool(runtime.get("php", {}).get("required"))
        php_files = [p for p in files if p.suffix.lower() in {".php", ".phtml", ".inc"}]
        if php_binary:
            for path in php_files:
                relative = path.relative_to(project_root).as_posix()
                try:
                    process = _run([php_binary, "-l", str(path)], project_root)
                except subprocess.TimeoutExpired:
                    findings.append(make_finding("syntax.php-timeout", "blocker", "syntax", relative, "PHP lint timed out."))
                    continue
                if process.returncode != 0:
                    summary = process.stdout.strip().splitlines()[-1] if process.stdout.strip() else "PHP syntax error"
                    findings.append(make_finding("syntax.php", "blocker", "syntax", relative, summary))
        elif php_required:
            findings.append(make_finding("runtime.php", "error", "environment", "", "PHP CLI is required but unavailable."))
        else:
            findings.append(make_finding("runtime.php", "warning", "environment", "", "PHP files were detected, but PHP CLI is unavailable; syntax was not executed."))
        expected_php = str(runtime.get("php", {}).get("expected", "")).strip()
        if php_binary and expected_php:
            process = _run([php_binary, "-r", "echo PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION;"], project_root)
            actual = process.stdout.strip()
            if process.returncode != 0 or actual != expected_php:
                findings.append(make_finding("runtime.php-version", "error", "environment", "", f"PHP {expected_php} is required; detected {actual or 'unknown'}."))

    if "javascript" in adapters:
        node_binary = shutil.which("node")
        node_required = bool(runtime.get("node", {}).get("required"))
        js_files = [p for p in files if p.suffix.lower() in {".js", ".mjs", ".cjs"}]
        if node_binary:
            for path in js_files:
                relative = path.relative_to(project_root).as_posix()
                try:
                    process = _run([node_binary, "--check", str(path)], project_root)
                except subprocess.TimeoutExpired:
                    findings.append(make_finding("syntax.javascript-timeout", "blocker", "syntax", relative, "JavaScript syntax check timed out."))
                    continue
                if process.returncode != 0:
                    summary = process.stdout.strip().splitlines()[-1] if process.stdout.strip() else "JavaScript syntax error"
                    findings.append(make_finding("syntax.javascript", "blocker", "syntax", relative, summary))
        elif node_required:
            findings.append(make_finding("runtime.node", "error", "environment", "", "Node.js is required but unavailable."))
        elif js_files:
            findings.append(make_finding("runtime.node", "warning", "environment", "", "JavaScript files were detected, but Node.js is unavailable; syntax was not executed."))
        expected_node = str(runtime.get("node", {}).get("expected", "")).strip().lstrip("v")
        if node_binary and expected_node:
            process = _run([node_binary, "--version"], project_root)
            actual = process.stdout.strip().lstrip("v")
            if process.returncode != 0 or not actual.startswith(expected_node):
                findings.append(make_finding("runtime.node-version", "error", "environment", "", f"Node.js {expected_node} is required; detected {actual or 'unknown'}."))

    if "python" in adapters:
        for path in [p for p in files if p.suffix.lower() == ".py"]:
            relative = path.relative_to(project_root).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, str(path), "exec")
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                findings.append(make_finding("syntax.python", "blocker", "syntax", relative, str(exc)))

        expected_python = str(runtime.get("python", {}).get("expected", "")).strip()
        if expected_python:
            actual_python = f"{os.sys.version_info.major}.{os.sys.version_info.minor}"
            if actual_python != expected_python:
                findings.append(make_finding("runtime.python-version", "error", "environment", "", f"Python {expected_python} is required; detected {actual_python}."))

    if "css" in adapters:
        for path in [p for p in files if p.suffix.lower() == ".css"]:
            text = _read_text(path)
            if text is not None and not _css_balance(text):
                findings.append(make_finding("syntax.css-balance", "blocker", "syntax", path.relative_to(project_root).as_posix(), "CSS braces are unbalanced."))

    packaging = config.get("packaging", {})
    for required in packaging.get("required_files", []):
        candidate = project_root / normalize_rel(str(required))
        if not candidate.is_file():
            findings.append(make_finding("package.required-file", "error", "packaging", normalize_rel(str(required)), "Required deployment file is missing."))

    quality = config.get("quality", {})
    if quality.get("require_tests"):
        declared_tests = [str(item) for item in quality.get("test_entry_points", []) if str(item).strip()]
        command_tests = [
            item for group in config.get("commands", {}).values() for item in group
            if isinstance(item, dict) and (item.get("test_entry_point") or "tests" in item.get("capabilities", []))
        ]
        has_tests = (
            any("test" in part.lower() for path in files for part in path.relative_to(project_root).parts[:-1])
            or any(path.name.lower().startswith("test") for path in files)
            or any((project_root / item).exists() for item in declared_tests)
            or bool(command_tests)
        )
        if not has_tests:
            findings.append(make_finding("quality.tests", "warning", "quality", "", "No conventional tests, declared test entry points, or registered test commands were detected."))
    if quality.get("require_documentation"):
        if not any((project_root / name).is_file() for name in ("README.md", "README.txt", "docs/README.md")):
            findings.append(make_finding("quality.documentation", "warning", "quality", "", "Required project documentation was not found."))
    deploy_ignore = config.get("paths", {}).get("deploy_ignore", ".deployignore")
    if deploy_ignore and not (project_root / deploy_ignore).is_file():
        findings.append(make_finding("package.deployignore", "warning", "packaging", deploy_ignore, "No deployment-ignore file exists; Forge defaults will still apply."))

    if config.get("learn", {}).get("enabled", True):
        for learned in evaluate_contracts(project_root, forge_root, config):
            findings.append(make_finding(learned["check_id"], learned["severity"], learned["category"], learned["path"], learned["message"]))

    for project_finding in evaluate_project_memory(project_root, config):
        findings.append(make_finding(
            project_finding["check_id"], project_finding["severity"], project_finding["category"],
            project_finding["path"], project_finding["message"],
        ))

    baseline_path = project_root / config.get("paths", {}).get("baseline", ".forge/baseline.json")
    baseline = load_baseline(baseline_path) if use_baseline else {"findings": {}}
    known = set(baseline.get("findings", {}))
    classified: list[Finding] = []
    for finding in findings:
        disposition = "LEGACY" if finding.fingerprint in known and finding.severity in {"warning", "info"} and not finding.check_id.startswith(("learn.contract.", "project.")) else "NEW"
        classified.append(Finding(**{**finding.as_dict(), "disposition": disposition}))

    severity_counts = {level: sum(1 for item in classified if item.severity == level) for level in ("blocker", "error", "warning", "info")}
    disposition_counts = {kind: sum(1 for item in classified if item.disposition == kind) for kind in ("NEW", "LEGACY")}
    fail_on_new_warnings = bool(quality.get("fail_on_new_warnings"))
    blocked = severity_counts["blocker"] > 0 or severity_counts["error"] > 0 or (fail_on_new_warnings and any(item.severity == "warning" and item.disposition == "NEW" for item in classified))

    return {
        "schema": 1,
        "generated_utc": utc_now(),
        "project": config.get("project", {}).get("name", project_root.name),
        "project_root": str(project_root),
        "tree_fingerprint": tree_fingerprint(project_root, excludes, forge_root),
        "adapters": sorted(adapters),
        "status": "FAIL" if blocked else "PASS",
        "counts": {**severity_counts, **{f"disposition_{key.lower()}": value for key, value in disposition_counts.items()}},
        "findings": [item.as_dict() for item in sorted(classified, key=lambda x: (x.severity, x.check_id, x.path))],
    }

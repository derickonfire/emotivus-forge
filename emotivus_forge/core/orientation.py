from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Iterator

from .code_orientation import orient_code
from .common import normalize_rel, sha256_file
from .confidentiality_boundary import classify_confidentiality_boundaries
from .paths import IGNORED_DIR_NAMES

STACK_MARKERS: dict[str, tuple[str, ...]] = {
    "php": ("composer.json", "index.php", "artisan"),
    "node": ("package.json",),
    "python": ("pyproject.toml", "requirements.txt", "setup.py", "manage.py"),
    "ruby": ("Gemfile",),
    "go": ("go.mod",),
    "rust": ("Cargo.toml",),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts"),
    "dotnet": ("*.sln", "*.csproj"),
}

EXTENSION_STACKS = {
    ".php": "php", ".js": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".py": "python", ".rb": "ruby", ".go": "go",
    ".rs": "rust", ".java": "java", ".cs": "dotnet", ".html": "html",
    ".css": "css", ".scss": "css", ".sql": "sql", ".sh": "shell",
}

PRIVATE_NAME_HINTS = (
    ".env", "secret", "credential", "private", "backup", "dump", "production",
)


def load_project_ignore(project_root: Path) -> list[str]:
    path = project_root / ".forgeignore"
    if not path.is_file() or path.is_symlink():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    patterns: list[str] = []
    for raw in lines:
        value = raw.strip().replace("\\", "/")
        if not value or value.startswith("#"):
            continue
        while value.startswith("./"):
            value = value[2:]
        value = value.lstrip("/")
        if value and value not in patterns:
            patterns.append(value)
    return patterns


def matches_project_ignore(relative: str, patterns: list[str], *, directory: bool = False) -> bool:
    value = relative.strip("/")
    if not value:
        return False
    candidates = {value, value + "/"}
    if directory:
        candidates.add(value + "/**")
    for pattern in patterns:
        normalized = pattern.rstrip("/")
        if any(fnmatch.fnmatch(candidate, pattern) or fnmatch.fnmatch(candidate, normalized) for candidate in candidates):
            return True
        if directory and normalized.startswith(value + "/"):
            # A child-specific rule does not exclude the parent directory.
            continue
    return False


# Retained for internal compatibility; new cross-module callers use the explicit public name.
_matches_ignore = matches_project_ignore


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def iter_project_files(
    project_root: Path,
    forge_root: Path,
    *,
    max_files: int = 5000,
    max_depth: int = 8,
) -> Iterator[Path]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    emitted = 0
    project_ignore = load_project_ignore(project_root)
    for current, dirs, files in os.walk(project_root):
        current_path = Path(current)
        relative_parts = current_path.relative_to(project_root).parts
        if len(relative_parts) > max_depth:
            dirs[:] = []
            continue
        kept_dirs: list[str] = []
        for name in sorted(dirs):
            candidate = current_path / name
            relative = normalize_rel(candidate.relative_to(project_root))
            if candidate.is_symlink() or name in IGNORED_DIR_NAMES or _is_inside(candidate, forge_root):
                continue
            if matches_project_ignore(relative, project_ignore, directory=True):
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(files):
            path = current_path / name
            relative = normalize_rel(path.relative_to(project_root))
            if path.is_symlink() or _is_inside(path, forge_root):
                continue
            if matches_project_ignore(relative, project_ignore):
                continue
            yield path
            emitted += 1
            if emitted >= max_files:
                return


def _read_project_name(project_root: Path) -> tuple[str, str]:
    candidates = (
        ("package.json", "name"),
        ("composer.json", "name"),
        ("pyproject.toml", "project.name"),
    )
    for filename, key in candidates:
        path = project_root / filename
        if not path.is_file() or path.stat().st_size > 256_000:
            continue
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), filename
        elif filename == "pyproject.toml":
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            in_project = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("["):
                    in_project = stripped == "[project]"
                elif in_project and stripped.startswith("name") and "=" in stripped:
                    value = stripped.split("=", 1)[1].strip().strip("'\"")
                    if value:
                        return value, filename
    gomod = project_root / "go.mod"
    if gomod.is_file() and gomod.stat().st_size <= 256_000:
        try:
            for line in gomod.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("module "):
                    module = stripped[len("module "):].strip()
                    if module:
                        return module.rsplit("/", 1)[-1], "go.mod"
        except (OSError, UnicodeDecodeError):
            pass
    cargo = project_root / "Cargo.toml"
    if cargo.is_file() and cargo.stat().st_size <= 256_000:
        try:
            in_package = False
            for line in cargo.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("["):
                    in_package = stripped == "[package]"
                elif in_package and stripped.startswith("name") and "=" in stripped:
                    value = stripped.split("=", 1)[1].strip().strip("'\"")
                    if value:
                        return value, "Cargo.toml"
        except (OSError, UnicodeDecodeError):
            pass
    for readme in ("README.md", "README.rst", "README.txt", "readme.md", "Readme.md"):
        path = project_root / readme
        if not path.is_file() or path.stat().st_size > 256_000:
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    title = stripped[2:].strip()
                    if title:
                        return title, "README"
                if stripped and not stripped.startswith("#"):
                    break
        except (OSError, UnicodeDecodeError):
            continue
    return project_root.name or "Unnamed project", "directory"


def _read_bounded(path: Path, limit: int = 256_000) -> str:
    try:
        if path.is_file() and path.stat().st_size <= limit:
            return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    return ""


def derive_orientation(project_root: Path, relatives: Iterable[str]) -> dict[str, Any]:
    """Best-effort, bounded first-contact orientation read from the project itself:
    a one-line description, entry points, and run/test commands. Deterministic."""
    rel_set = {relative for relative in relatives}
    names = {Path(relative).name for relative in rel_set}

    def is_prose(text: str) -> bool:
        letters = sum(character.isalpha() for character in text)
        return letters >= 8 and letters / max(1, len(text)) > 0.45

    def toml_value(filename: str, section: str, key: str) -> str:
        in_section = False
        for line in _read_bounded(project_root / filename).splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_section = stripped == section
            elif in_section and stripped.startswith(key) and "=" in stripped:
                value = stripped.split("=", 1)[1].strip().strip("'\"")
                if value:
                    return value[:200]
        return ""

    def json_value(filename: str, key: str) -> str:
        text = _read_bounded(project_root / filename)
        try:
            value = (json.loads(text) if text else {}).get(key, "")
            return str(value).strip()[:200] if isinstance(value, str) else ""
        except (json.JSONDecodeError, ValueError):
            return ""

    description = ""
    for readme in ("README.md", "README.rst", "README.txt", "readme.md", "Readme.md"):
        if readme not in names:
            continue
        for line in _read_bounded(project_root / readme).splitlines():
            raw = line.strip()
            # First real prose line — skip headings, badges, links, HTML, tables, art.
            if not raw or raw.startswith(("#", "!", "[", "<", ">", "---", "===", "```", "|", "=", "*", "-", "(")):
                continue
            if "](" in raw or "<img" in raw or raw.lower().startswith(("http", "see ", "note:")):
                continue
            if is_prose(raw):
                description = raw[:200]
                break
        if description:
            break
    if not description:
        description = (
            json_value("package.json", "description")
            or json_value("composer.json", "description")
            or toml_value("Cargo.toml", "[package]", "description")
            or toml_value("pyproject.toml", "[project]", "description")
        )

    def existing(*candidates: str) -> list[str]:
        return [candidate for candidate in candidates if candidate in rel_set]

    entry_points: list[str] = []
    run = ""
    test = ""
    if "package.json" in names:
        text = _read_bounded(project_root / "package.json")
        try:
            scripts = (json.loads(text) if text else {}).get("scripts", {})
            scripts = scripts if isinstance(scripts, dict) else {}
        except (json.JSONDecodeError, ValueError):
            scripts = {}
        entry_points = existing("index.js", "index.ts", "src/index.js", "src/index.ts", "server.js", "app.js", "main.js", "bin/cli.js")
        run = "npm run dev" if "dev" in scripts else ("npm start" if "start" in scripts else "")
        test = "npm test" if "test" in scripts else ""
    elif "pyproject.toml" in names or "setup.py" in names or "requirements.txt" in names or any(n.endswith(".py") for n in names):
        entry_points = existing("manage.py", "app.py", "main.py", "wsgi.py", "asgi.py", "__main__.py", "src/main.py")
        if "manage.py" in rel_set:
            run = "python manage.py runserver"
        elif "app.py" in rel_set:
            run = "python app.py"
        elif "main.py" in rel_set:
            run = "python main.py"
        if any(n.startswith("test_") or n.endswith("_test.py") for n in names) or "tox.ini" in names or "pytest.ini" in names or "conftest.py" in names:
            test = "pytest"
    elif "go.mod" in names:
        run = "go run ./..."
        test = "go test ./..."
        entry_points = existing("main.go", "cmd/main.go")
    elif "Cargo.toml" in names:
        run = "cargo run" if "src/main.rs" in rel_set else "cargo build"
        test = "cargo test"
        entry_points = existing("src/main.rs", "src/lib.rs")
    elif "composer.json" in names:
        run = "php artisan serve" if "artisan" in names else "php -S localhost:8000"
        test = "vendor/bin/phpunit" if "phpunit.xml" in names or "phpunit.xml.dist" in names else ""
        entry_points = existing("artisan", "public/index.php", "index.php")
    elif any(n.endswith(".html") for n in names) and "package.json" not in names:
        run = "open index.html (static site — no build)" if "index.html" in rel_set else ""
        entry_points = existing("index.html")

    return {
        "description": description,
        "entry_points": entry_points[:6],
        "run": run,
        "test": test,
    }


def build_snapshot(
    project_root: Path,
    forge_root: Path,
    *,
    max_files: int = 5000,
    hash_file_limit: int = 1_000_000,
    hash_total_budget: int = 8_000_000,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    hashed_bytes = 0
    truncated = False
    for index, path in enumerate(iter_project_files(project_root, forge_root, max_files=max_files + 1)):
        if index >= max_files:
            truncated = True
            break
        try:
            stat = path.stat()
        except OSError:
            continue
        relative = normalize_rel(path.relative_to(project_root))
        entry: dict[str, Any] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
        total_bytes += stat.st_size
        if stat.st_size <= hash_file_limit and hashed_bytes + stat.st_size <= hash_total_budget:
            try:
                entry["sha256"] = sha256_file(path)
                hashed_bytes += stat.st_size
            except OSError:
                pass
        files[relative] = entry
    return {
        "schema": 1,
        "files": files,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "hashed_bytes": hashed_bytes,
        "truncated": truncated,
        "limits": {
            "max_files": max_files,
            "hash_file_limit": hash_file_limit,
            "hash_total_budget": hash_total_budget,
        },
    }


def _read_ledger_events(forge_root: Path, *, limit: int = 400) -> list[dict[str, Any]] | None:
    """Return recent ledger events, or None when no readable ledger exists.

    None means unknown, and orientation reports a knowledge gap. It never means "no
    activity", and it is never replaced by a filesystem-timestamp guess.
    """
    try:
        path = Path(forge_root) / "ledger.jsonl"
        if not path.is_file() or path.is_symlink():
            return None
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        return rows[-limit:]
    except (OSError, UnicodeDecodeError):
        return None


def orient_project(project_root: Path, forge_root: Path, settings: dict[str, Any]) -> dict[str, Any]:
    project_root = project_root.resolve()
    snapshot = build_snapshot(
        project_root,
        forge_root,
        max_files=int(settings.get("adoption_file_budget", 5000)),
        hash_file_limit=int(settings.get("hash_file_limit_bytes", 1_000_000)),
        hash_total_budget=int(settings.get("hash_total_budget_bytes", 8_000_000)),
    )
    stacks: set[str] = set()
    for relative in snapshot["files"]:
        path = Path(relative)
        lower_name = path.name.lower()
        for stack, markers in STACK_MARKERS.items():
            if any(path.match(marker) or lower_name == marker.lower() for marker in markers):
                stacks.add(stack)
        stack = EXTENSION_STACKS.get(path.suffix.lower())
        if stack:
            stacks.add(stack)
    safety = classify_confidentiality_boundaries(project_root, snapshot["files"].keys())
    ledger_events = _read_ledger_events(forge_root)
    safety["excluded_directories"] = sorted(IGNORED_DIR_NAMES)
    safety["project_ignore_patterns"] = load_project_ignore(project_root)
    name, name_source = _read_project_name(project_root)
    confidence = "confirmed" if name_source != "directory" else "inferred"
    return {
        "schema": 1,
        "identity": {
            "name": name,
            "name_source": name_source,
            "status": confidence,
            "source_root": ".",
        },
        "stacks": sorted(stacks),
        "brief": derive_orientation(project_root, snapshot["files"].keys()),
        "code_orientation": orient_code(project_root, snapshot["files"].keys(), ledger_events),
        "snapshot": snapshot,
        "safety": safety,
        "unknowns": [
            item for item in (
                "Project scan reached its configured file budget." if snapshot["truncated"] else "",
                "Private-data boundaries require owner confirmation." if safety["private_boundary_candidates"] else "",
            ) if item
        ],
    }

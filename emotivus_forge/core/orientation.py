from __future__ import annotations

import fnmatch
import json
import os
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from .code_orientation import orient_code, SOURCE_SUFFIXES
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
    pom = project_root / "pom.xml"
    if pom.is_file() and pom.stat().st_size <= 256_000:
        try:
            without_parent = re.sub(r"<parent>.*?</parent>", "", pom.read_text(encoding="utf-8"), flags=re.DOTALL)
            name = re.search(r"<name>\s*([^<]+?)\s*</name>", without_parent)
            if name and name.group(1).strip():
                return name.group(1).strip(), "pom.xml"
            artifact = re.search(r"<artifactId>\s*([^<]+?)\s*</artifactId>", without_parent)
            if artifact and artifact.group(1).strip():
                return artifact.group(1).strip(), "pom.xml"
        except (OSError, UnicodeDecodeError):
            pass
    for gemspec in sorted(project_root.glob("*.gemspec")):
        try:
            match = re.search(r"\.name\s*=\s*['\"]([^'\"]+)['\"]", gemspec.read_text(encoding="utf-8"))
            if match and match.group(1).strip():
                return match.group(1).strip(), "gemspec"
        except (OSError, UnicodeDecodeError):
            pass
        return gemspec.stem, "gemspec"
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
    for html in ("index.html", "public/index.html", "src/index.html"):
        path = project_root / html
        if path.is_file() and path.stat().st_size <= 256_000:
            try:
                match = re.search(r"<title>\s*([^<]+?)\s*</title>", path.read_text(encoding="utf-8"), re.IGNORECASE)
                if match and match.group(1).strip():
                    return match.group(1).strip(), "index.html"
            except (OSError, UnicodeDecodeError):
                pass
    return project_root.name or "Unnamed project", "directory"


def _read_bounded(path: Path, limit: int = 256_000) -> str:
    try:
        if path.is_file() and path.stat().st_size <= limit:
            return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    return ""


def _looks_test(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith("test_")
        or lowered.endswith(("_test.py", "_test.go", "_test.js", "_test.ts"))
        or lowered.endswith((".test.js", ".test.ts", ".test.jsx", ".test.tsx", ".spec.js", ".spec.ts", "_spec.rb"))
        or lowered in ("test.js", "test.ts")
    )


def _tidy(text: str) -> str:
    """Trim a one-line description to a word boundary and drop trailing punctuation."""
    text = text.strip()
    if len(text) > 200:
        cut = text.rfind(" ", 0, 200)
        text = text[: cut if cut > 80 else 200].rstrip() + "…"
    return text.rstrip(" :;,-")


_COMMAND_LEAD_RE = re.compile(
    r"^\s*(?:[$>]|#!|(?:npm|npx|pnpm|yarn|pip3?|python3?|ruby|node|deno|bun|go|cargo|make|bundle|php|composer|gradle|mvn|docker|git|rails|rake|flask|django-admin)\b)",
    re.IGNORECASE,
)


def _looks_command(text: str) -> bool:
    """A shell/command line masquerading as a description (e.g. 'npm install && npm
    run wob'). Such a string is an instruction, never an identity, and must not be
    printed as 'What it is'."""
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_COMMAND_LEAD_RE.match(stripped)) or "&&" in stripped or " | " in stripped or stripped.startswith("`")


def _derive_layout(rel_set: set[str]) -> dict[str, Any]:
    """Deterministic project-layout summary from relative paths alone: top-level
    directories, file-type histogram, primary source dir, packages, and tests."""
    top_dirs: "Counter[str]" = Counter()
    ext_hist: "Counter[str]" = Counter()
    dir_src: "Counter[str]" = Counter()
    packages: set[str] = set()
    test_dirs: "Counter[str]" = Counter()
    test_count = 0
    for rel in rel_set:
        parts = PurePosixPath(rel).parts
        if not parts:
            continue
        top = parts[0] if len(parts) > 1 else "(root)"
        top_dirs[top] += 1
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix:
            ext_hist[suffix] += 1
        is_test = _looks_test(parts[-1]) or "tests" in parts or "test" in parts or "spec" in parts
        if is_test:
            test_count += 1
            test_dirs[parts[0]] += 1
        elif suffix in SOURCE_SUFFIXES:
            # Exclude tests so the primary source dir reflects real source, not tests.
            dir_src["/".join(parts[:-1]) or "."] += 1
        if parts[-1] == "__init__.py":
            packages.add("/".join(parts[:-1]))

    def ranked(counter: "Counter[str]") -> list[tuple[str, int]]:
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))

    def source_rank(item: tuple[str, int]) -> tuple[int, str]:
        directory, count = item
        # Prefer conventional source roots over config/vendored dirs at equal weight.
        bonus = 1000 if directory.split("/")[0] in ("src", "app", "lib", "internal", "pkg") else 0
        return (-(count + bonus), directory)

    src_ranked = sorted(dir_src.items(), key=source_rank)
    src_exts = Counter({ext: n for ext, n in ext_hist.items() if ext in SOURCE_SUFFIXES})
    return {
        "top_level": [{"dir": name, "files": n} for name, n in ranked(top_dirs)[:8]],
        "file_types": [{"ext": ext, "count": n} for ext, n in ranked(ext_hist)[:6]],
        "primary_source_dir": src_ranked[0][0] if src_ranked else "",
        "primary_language": ranked(src_exts)[0][0] if src_exts else "",
        "packages": sorted(packages)[:6],
        "tests": {"dir": ranked(test_dirs)[0][0] if test_dirs else "", "count": test_count},
        "file_count": len(rel_set),
    }


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
    description_source = ""
    for readme in ("README.md", "README.rst", "README.txt", "readme.md", "Readme.md"):
        if readme not in names:
            continue
        for line in _read_bounded(project_root / readme).splitlines():
            raw = line.strip()
            # First real prose line — skip headings, badges, links, HTML, tables, art.
            if not raw or raw.startswith(("#", "!", "[", "<", ">", "---", "===", "```", "|", "=", "*", "-", "(")):
                continue
            if "](" in raw or "<img" in raw or raw.lower().startswith(("http", "see ", "note:", "licensed ", "copyright", "spdx")):
                continue
            # A command line is an instruction, not an identity — never a description.
            if _looks_command(raw):
                continue
            if is_prose(raw):
                description = _tidy(raw)
                description_source = readme
                break
        if description:
            break
    if not description:
        for manifest, value in (
            ("package.json", json_value("package.json", "description")),
            ("composer.json", json_value("composer.json", "description")),
            ("Cargo.toml", toml_value("Cargo.toml", "[package]", "description")),
            ("pyproject.toml", toml_value("pyproject.toml", "[project]", "description")),
        ):
            if value and not _looks_command(value):
                description = value
                description_source = manifest
                break

    def existing(*candidates: str) -> list[str]:
        return [candidate for candidate in candidates if candidate in rel_set]

    def scripts_of(filename: str) -> dict[str, Any]:
        text = _read_bounded(project_root / filename)
        try:
            value = (json.loads(text) if text else {}).get("scripts", {})
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    def root_source(suffix: str) -> list[str]:
        return sorted(r for r in rel_set if "/" not in r and r.lower().endswith(suffix) and not _looks_test(r))

    # Rank the primary ecosystem by source-file evidence, with manifest and
    # app-framework boosts, so a polyglot / framework project (Laravel with a Vite
    # package.json, a Java library with a docs site) is not mis-dispatched.
    lang_exts = {
        "python": {".py"},
        "node": {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"},
        "go": {".go"}, "rust": {".rs"}, "java": {".java"}, "ruby": {".rb"}, "php": {".php"},
    }
    manifests = {
        "python": {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "environment.yml"},
        "node": {"package.json"}, "go": {"go.mod"}, "rust": {"Cargo.toml"},
        "java": {"pom.xml", "build.gradle", "build.gradle.kts"},
        "ruby": {"Gemfile", "Rakefile", "config.ru"}, "php": {"composer.json"},
    }
    app_markers = {"python": {"manage.py"}, "php": {"artisan"}, "ruby": {"config.ru"}}
    src_count = {lang: 0 for lang in lang_exts}
    for rel in rel_set:
        parts = PurePosixPath(rel).parts
        if _looks_test(parts[-1]) or any(seg in ("tests", "test", "spec") for seg in parts):
            continue
        suffix = PurePosixPath(rel).suffix.lower()
        for lang, exts in lang_exts.items():
            if suffix in exts:
                src_count[lang] += 1

    def has_manifest(lang: str) -> bool:
        return bool(manifests[lang] & names) or (lang == "ruby" and any(n.endswith(".gemspec") for n in names))

    scores: dict[str, int] = {}
    for lang in lang_exts:
        score = src_count[lang]
        if has_manifest(lang):
            score += 60
        if app_markers.get(lang, set()) & names:
            score += 1000
        if score:
            scores[lang] = score
    primary = max(scores, key=lambda lang: (scores[lang], lang)) if scores else ""

    entry_points: list[str] = []
    run = ""
    test = ""
    if primary == "python":
        entry_points = existing("manage.py", "app.py", "main.py", "wsgi.py", "asgi.py", "__main__.py", "src/main.py")
        run = (
            "python manage.py runserver" if "manage.py" in rel_set
            else "python app.py" if "app.py" in rel_set
            else "python main.py" if "main.py" in rel_set else ""
        )
        if not run and any(n.endswith(".ipynb") for n in names):
            run = "jupyter notebook"
        if (
            any(_looks_test(PurePosixPath(r).name) and r.endswith(".py") for r in rel_set)
            or any("tests" in PurePosixPath(r).parts for r in rel_set)
            or {"tox.ini", "pytest.ini", "conftest.py"} & names
        ):
            test = "pytest"
    elif primary == "node":
        s = scripts_of("package.json")
        entry_points = existing("index.js", "index.ts", "src/index.js", "src/index.ts", "server.js", "app.js", "main.js", "bin/cli.js")
        run = "npm run dev" if "dev" in s else ("npm start" if "start" in s else "")
        test = "npm test" if "test" in s else ""
    elif primary == "go":
        # `go run` only makes sense with an observed main package; a library has
        # none, so it builds and tests instead (mirrors the Rust src/main.rs gate).
        has_main = "main.go" in rel_set or "cmd/main.go" in rel_set
        run = "go run ./..." if has_main else "go build ./..."
        test = "go test ./..."
        entry_points = existing("main.go", "cmd/main.go")
    elif primary == "rust":
        run = "cargo run" if "src/main.rs" in rel_set else "cargo build"
        test = "cargo test"
        entry_points = existing("src/main.rs", "src/lib.rs")
    elif primary == "java":
        run, test = ("mvn compile", "mvn test") if "pom.xml" in names else ("gradle build", "gradle test")
    elif primary == "ruby":
        run = "bundle exec rackup" if "config.ru" in names else "ruby"
        test = "rake test" if "Rakefile" in names else ("bundle exec rspec" if any("spec" in PurePosixPath(r).parts for r in rel_set) else "")
        entry_points = existing("config.ru", "app.rb", "main.rb")
    elif primary == "php":
        s = scripts_of("composer.json")
        if "artisan" in names:
            run, test = "php artisan serve", "php artisan test"
        else:
            run = "php -S localhost:8000"
            test = "composer test" if "test" in s else ("vendor/bin/phpunit" if {"phpunit.xml", "phpunit.xml.dist"} & names else "")
        entry_points = existing("artisan", "public/index.php", "index.php")
    if not primary and any(n.endswith(".html") for n in names):
        run = "open index.html (static site — no build)" if "index.html" in rel_set else ""
        entry_points = existing("index.html")

    return {
        "description": description,
        "description_source": description_source,
        "entry_points": entry_points[:6],
        "run": run,
        "test": test,
        # Run/test commands are derived from manifests and filenames, never executed
        # here; a caller rendering them must present them as inferred, not as fact.
        "commands_tier": "inferred",
        "layout": _derive_layout(rel_set),
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
    # A name scraped from a README heading or an HTML <title>, or fallen back to the
    # directory name, is inferred — not confirmed. "confirmed" is reserved for an
    # owner-recorded identity (passport --record path). A declared manifest name
    # field is observed, a tier below confirmed and above a prose scrape.
    confidence = "inferred" if name_source in {"README", "index.html", "directory"} else "observed"
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

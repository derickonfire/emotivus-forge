from __future__ import annotations

import configparser
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .utils import iter_project_files


@dataclass(frozen=True)
class Detection:
    adapters: tuple[str, ...]
    evidence: dict[str, list[str]]
    existing_project: bool
    package_scripts: tuple[str, ...]
    package_manager: str
    detected_version: str
    version_path: str
    version_regex: str
    identity: str = ""


def detect_identity(root: Path) -> str:
    manifest = root / "FORGE-MANIFEST.json"
    if not manifest.is_file() or not (root / "forge.py").is_file() or not (root / "emotivus_forge" / "__init__.py").is_file():
        return ""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return "emotivus-forge-core" if data.get("name") == "Emotivus Forge" else ""


def is_forge_project(root: Path) -> bool:
    return detect_identity(root.resolve()) == "emotivus-forge-core"


def _version_from_regex(path: Path, pattern: str) -> tuple[str, str, str]:
    if not path.is_file():
        return "", "", ""
    try:
        match = re.search(pattern, path.read_text(encoding="utf-8", errors="replace"), flags=re.M)
    except (OSError, re.error):
        return "", "", ""
    if not match:
        return "", "", ""
    return match.group(1).strip(), path.name, pattern


def _detect_python_version(root: Path) -> tuple[str, str, str]:
    pyproject = root / "pyproject.toml"
    result = _version_from_regex(pyproject, r'(?m)^version\s*=\s*["\']([^"\']+)["\']')
    if result[0]:
        return result[0], "pyproject.toml", result[2]

    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file():
        parser = configparser.ConfigParser()
        try:
            parser.read(setup_cfg, encoding="utf-8")
            version = parser.get("metadata", "version", fallback="").strip()
        except (OSError, configparser.Error):
            version = ""
        if version and not version.startswith("attr:"):
            return version, "setup.cfg", r'(?m)^version\s*=\s*([^\s#]+)'

    setup_py = root / "setup.py"
    result = _version_from_regex(setup_py, r'(?m)\bversion\s*=\s*["\']([^"\']+)["\']')
    if result[0]:
        return result[0], "setup.py", result[2]

    candidates = [root / "__init__.py"] + sorted(root.glob("*/__init__.py"))[:64]
    for candidate in candidates:
        result = _version_from_regex(candidate, r'(?m)^__version__\s*=\s*["\']([^"\']+)["\']')
        if result[0]:
            return result[0], candidate.relative_to(root).as_posix(), result[2]
    return "", "", ""




def _detect_php_version(root: Path) -> tuple[str, str, str]:
    patterns = [
        r"(?mi)\bdefine\(\s*['\"][A-Z0-9_]*VERSION['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
        r"(?mi)\bconst\s+[A-Z0-9_]*VERSION\s*=\s*['\"]([^'\"]+)['\"]",
    ]
    priority: list[Path] = []
    for relative in (
        "app/bootstrap.php", "includes/bootstrap.php", "bootstrap.php", "config.php",
        "app/config.php", "includes/config.php", "version.php",
    ):
        candidate = root / relative
        if candidate.is_file():
            priority.append(candidate)
    seen = {item.resolve() for item in priority}
    for candidate in sorted(root.rglob("*.php")):
        try:
            resolved = candidate.resolve()
            relative = candidate.relative_to(root)
        except (OSError, ValueError):
            continue
        if resolved in seen or any(part in {"vendor", ".forge", "Emotivus-Forge", "node_modules", "deploy"} for part in relative.parts):
            continue
        priority.append(candidate)
        if len(priority) >= 256:
            break
    for candidate in priority:
        for pattern in patterns:
            result = _version_from_regex(candidate, pattern)
            if result[0]:
                return result[0], candidate.relative_to(root).as_posix(), result[2]
    return "", "", ""

def detect_project(root: Path, forge_root: Path | None = None) -> Detection:
    root = root.resolve()
    evidence: dict[str, list[str]] = {
        "php": [], "javascript": [], "css": [], "apache": [],
        "node": [], "python": [],
    }
    meaningful = 0
    for path in iter_project_files(root, [], forge_root):
        relative = path.relative_to(root).as_posix()
        meaningful += 1
        suffix = path.suffix.lower()
        if suffix in {".php", ".phtml", ".inc"}:
            evidence["php"].append(relative)
        if suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}:
            evidence["javascript"].append(relative)
        if suffix in {".css", ".scss", ".sass", ".less"}:
            evidence["css"].append(relative)
        if path.name == ".htaccess" or suffix in {".conf", ".htconf"}:
            evidence["apache"].append(relative)
        if path.name == "package.json":
            evidence["node"].append(relative)
        if suffix == ".py" or path.name in {"pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile"}:
            evidence["python"].append(relative)

    adapters = [name for name, files in evidence.items() if files]
    if "node" in adapters and "javascript" not in adapters:
        adapters.append("javascript")

    scripts: list[str] = []
    package_manager = ""
    package_json = root / "package.json"
    if package_json.is_file():
        package_manager = "npm"
        if (root / "pnpm-lock.yaml").is_file():
            package_manager = "pnpm"
        elif (root / "yarn.lock").is_file():
            package_manager = "yarn"
        elif (root / "bun.lock").is_file() or (root / "bun.lockb").is_file():
            package_manager = "bun"

    detected_version = ""
    version_path = ""
    version_regex = ""
    if package_json.is_file():
        try:
            raw = json.loads(package_json.read_text(encoding="utf-8"))
            package_scripts = raw.get("scripts", {}) if isinstance(raw, dict) else {}
            if isinstance(package_scripts, dict):
                scripts = sorted(str(key) for key in package_scripts)
            version = raw.get("version") if isinstance(raw, dict) else None
            if isinstance(version, str) and version.strip():
                detected_version = version.strip()
                version_path = "package.json"
                version_regex = r'"version"\s*:\s*"([^"]+)"'
        except (OSError, json.JSONDecodeError):
            pass

    if not detected_version:
        composer = root / "composer.json"
        if composer.is_file():
            try:
                raw = json.loads(composer.read_text(encoding="utf-8"))
                version = raw.get("version") if isinstance(raw, dict) else None
                if isinstance(version, str) and version.strip():
                    detected_version = version.strip()
                    version_path = "composer.json"
                    version_regex = r'"version"\s*:\s*"([^"]+)"'
            except (OSError, json.JSONDecodeError):
                pass

    if not detected_version and evidence.get("php"):
        detected_version, version_path, version_regex = _detect_php_version(root)

    if not detected_version:
        detected_version, version_path, version_regex = _detect_python_version(root)

    return Detection(
        adapters=tuple(sorted(set(adapters))),
        evidence={key: values[:12] for key, values in evidence.items() if values},
        existing_project=meaningful > 0,
        package_scripts=tuple(scripts),
        package_manager=package_manager,
        detected_version=detected_version,
        version_path=version_path,
        version_regex=version_regex,
        identity=detect_identity(root),
    )

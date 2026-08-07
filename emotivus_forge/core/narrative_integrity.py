from __future__ import annotations

import glob
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .common import sha256_file as _sha256
from .state import CORE_STATE_SCHEMA, SETTINGS_SCHEMA

VERSION_TITLE_RE = re.compile(r"^#(?: Emotivus)? Forge ([0-9]+\.[0-9]+(?:\.[0-9]+)?)", re.MULTILINE)

TRUTH_BOUNDARY = (
    "Narrative integrity checks declared version, regression, state-schema, required-path, roadmap, "
    "and website-download relationships in the Forge distribution. Passing does not prove the prose "
    "is complete, the software is correct, the artifacts were authored by a particular person, or "
    "the release is authorized."
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _required_paths(root: Path, manifest: dict[str, Any], key: str) -> list[str]:
    problems: list[str] = []
    rows = manifest.get(key, [])
    if not isinstance(rows, list):
        return [f"FORGE-MANIFEST {key} must be an array"]
    if len(rows) != len(set(str(row) for row in rows)):
        problems.append(f"FORGE-MANIFEST {key} contains duplicate entries")
    for raw in rows:
        pattern = str(raw).replace("\\", "/")
        if not pattern or pattern.startswith("/") or ".." in Path(pattern).parts:
            problems.append(f"FORGE-MANIFEST {key} contains unsafe path: {pattern!r}")
            continue
        candidate = root / pattern.rstrip("/")
        if pattern.endswith("/"):
            if not candidate.is_dir():
                problems.append(f"required directory is missing: {pattern}")
        elif any(char in pattern for char in "*?["):
            if not glob.glob(str(root / pattern), recursive=True):
                problems.append(f"required pattern matched no files: {pattern}")
        elif not candidate.is_file():
            problems.append(f"required file is missing: {pattern}")
    return problems


def _checksum_bindings(downloads: Path) -> list[str]:
    problems: list[str] = []
    checksum_path = downloads / "SHA256SUMS.txt"
    if not checksum_path.is_file():
        return ["docs-site/downloads/SHA256SUMS.txt is missing"]
    declared: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            problems.append(f"invalid SHA256SUMS row: {line}")
            continue
        declared[parts[1].strip()] = parts[0].lower()
    for name in ("RUN-FORGE.zip", "RELEASE-NOTES.md"):
        path = downloads / name
        if not path.is_file():
            problems.append(f"docs-site download is missing: {name}")
            continue
        if declared.get(name) != _sha256(path):
            problems.append(f"docs-site checksum does not bind current bytes: {name}")
    return problems


def _zip_manifest_version(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [info.filename for info in archive.infolist() if Path(info.filename).name == "FORGE-MANIFEST.json"]
            if len(names) != 1:
                return ""
            value = json.loads(archive.read(names[0]).decode("utf-8"))
            return str(value.get("version", "")) if isinstance(value, dict) else ""
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
        return ""


def check_narrative_integrity(root: Path) -> dict[str, Any]:
    root = root.resolve()
    problems: list[str] = []
    try:
        manifest = _json(root / "FORGE-MANIFEST.json")
        product = _json(root / "FORGE-PRODUCT.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return {"schema": 1, "status": "FAIL", "problems": [str(exc)], "truth_boundary": TRUTH_BOUNDARY}

    version = str(product.get("version", "")).strip()
    if str(manifest.get("version", "")).strip() != version:
        problems.append("FORGE-MANIFEST version differs from FORGE-PRODUCT version")
    init_match = re.search(r'__version__\s*=\s*"([^"]+)"', (root / "emotivus_forge" / "__init__.py").read_text(encoding="utf-8"))
    if not init_match or init_match.group(1) != version:
        problems.append("emotivus_forge.__version__ differs from FORGE-PRODUCT version")

    state = manifest.get("state_schema", {}) if isinstance(manifest.get("state_schema"), dict) else {}
    if state.get("file_count") != 8 or len(state.get("files", [])) != 8:
        problems.append("FORGE-MANIFEST must declare exactly eight top-level state files")
    if state.get("settings_schema") != SETTINGS_SCHEMA:
        problems.append("FORGE-MANIFEST settings schema differs from the runtime constant")
    if state.get("core_state_schema") != CORE_STATE_SCHEMA:
        problems.append("FORGE-MANIFEST core state schema differs from the runtime constant")

    for key in ("canonical_paths", "public_paths"):
        problems.extend(_required_paths(root, manifest, key))
    edition = str(manifest.get("edition", "development")).strip() or "development"

    # Version-title consistency across the narrative surfaces. The exact
    # regression/module COUNT is deliberately not asserted here (0.574 anti-bloat):
    # it was a hand-maintained integer copied across CERTIFICATION, README, the
    # manifest, and a test, and it silently drifted in ungated copies. The live count
    # is reported by the self-test runner straight from the actual suite — always
    # accurate, zero maintenance — so prose describes the suite qualitatively and no
    # surface has to be kept in numeric lockstep.
    if edition != "public":
        cert_text = (root / "CERTIFICATION.md").read_text(encoding="utf-8")
        cert_title = VERSION_TITLE_RE.search(cert_text)
        if not cert_title or cert_title.group(1) != version:
            problems.append("CERTIFICATION title version differs from FORGE-PRODUCT version")

    readme_text = (root / "README.md").read_text(encoding="utf-8")
    readme_title = re.search(r"^# Emotivus Forge ([0-9]+\.[0-9]+(?:\.[0-9]+)?)", readme_text, re.MULTILINE)
    if not readme_title or readme_title.group(1) != version:
        problems.append("README title version differs from FORGE-PRODUCT version")

    if edition != "public":
        implementation = (root / "IMPLEMENTATION-REPORT.md").read_text(encoding="utf-8")
        implementation_title = VERSION_TITLE_RE.search(implementation)
        if not implementation_title or implementation_title.group(1) != version:
            problems.append("IMPLEMENTATION-REPORT title version differs from FORGE-PRODUCT version")

    try:
        from tools.check_progress_status import check_progress
        progress = check_progress(root)
        if progress.get("status") != "PASS":
            problems.extend(f"progress: {item}" for item in progress.get("problems", []))
    except Exception as exc:
        problems.append(f"progress integrity could not run: {exc}")

    if edition != "public":
        downloads = root / "docs-site" / "downloads"
        problems.extend(_checksum_bindings(downloads))
        public_zip = downloads / "RUN-FORGE.zip"
        if public_zip.is_file() and _zip_manifest_version(public_zip) != version:
            problems.append("docs-site RUN-FORGE.zip packaged version differs from FORGE-PRODUCT version")
        release_notes = downloads / "RELEASE-NOTES.md"
        if release_notes.is_file() and version not in release_notes.read_text(encoding="utf-8"):
            problems.append("docs-site release notes do not name the current version")

    return {
        "schema": 1,
        "status": "PASS" if not problems else "FAIL",
        "version": version,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }

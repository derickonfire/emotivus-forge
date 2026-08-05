from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .common import utc_now
from .changes import snapshot_fingerprint

DOC_NAMES = {
    "readme", "roadmap", "backlog", "changelog", "contributing", "license",
    "certification", "implementation-report", "public-release-notice",
}
WEB_PARTS = {"website", "web", "public", "static", "assets", "docs-site", "frontend", "client"}
TEST_PARTS = {"test", "tests", "spec", "specs", "fixtures"}
RELEASE_PARTS = {"release", "releases", "deploy", "deployment", "packaging"}
CONFIG_NAMES = {
    "package.json", "composer.json", "pyproject.toml", "requirements.txt", "makefile",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", ".htaccess", "php.ini",
}


def _parts(relative: str) -> tuple[str, ...]:
    return tuple(part.lower() for part in Path(relative).parts)


def _stem(relative: str) -> str:
    return Path(relative).stem.lower()


def classify_path(relative: str, *, deleted: bool = False) -> dict[str, Any]:
    path = Path(relative)
    parts = _parts(relative)
    suffix = path.suffix.lower()
    name = path.name.lower()
    stem = _stem(relative)
    surfaces: set[str] = set()
    dimensions: set[str] = set()

    is_test = bool(TEST_PARTS.intersection(parts)) or name.startswith("test_") or name.endswith("_test.py")
    is_release = bool(RELEASE_PARTS.intersection(parts)) or stem in {"changelog", "release-notes", "sha256sums"}
    is_web_path = bool(WEB_PARTS.intersection(parts))
    is_database = suffix == ".sql" or "migration" in parts or "migrations" in parts or "schema" in stem
    is_docs = (
        suffix in {".md", ".rst", ".adoc"}
        or stem in DOC_NAMES
        or "docs" in parts
        or "documentation" in parts
    ) and not is_web_path

    if is_release:
        surfaces.add("release")
        dimensions.add("release-metadata")
    if is_test:
        surfaces.add("verification")
        dimensions.add("verification")
    if is_database:
        surfaces.add("database")
        dimensions.update({"data-state", "runtime-contract"})
    elif is_docs:
        surfaces.add("documentation")
        dimensions.add("documentation")
    elif suffix in {".html", ".htm", ".css", ".scss", ".sass"} or is_web_path:
        surfaces.add("website")
        dimensions.add("presentation" if suffix in {".css", ".scss", ".sass"} else "application")
    elif suffix in {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}:
        surfaces.add("frontend")
        dimensions.add("application")
    elif suffix in {".py", ".php", ".rb", ".go", ".rs", ".java", ".cs", ".sh"}:
        surfaces.add("backend" if not is_test else "verification")
        dimensions.add("application" if not is_test else "verification")
    elif suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml"} or name in CONFIG_NAMES:
        surfaces.add("configuration")
        dimensions.add("configuration")
    else:
        surfaces.add("project")
        dimensions.add("project-structure")

    if deleted:
        dimensions.add("deletion")

    return {
        "path": relative,
        "surfaces": sorted(surfaces),
        "dimensions": sorted(dimensions),
        "deleted": deleted,
    }


def _required_checks(paths: list[dict[str, Any]]) -> list[dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}

    def add(identifier: str, reason: str) -> None:
        selected.setdefault(identifier, {"id": identifier, "reason": reason})

    for item in paths:
        relative = str(item.get("path", ""))
        suffix = Path(relative).suffix.lower()
        if item.get("deleted"):
            add("core.change-reconciliation", "Deleted paths must remain reconciled against the observed checkpoint.")
            continue
        add("core.merge-marker", "Changed readable text must not contain unresolved merge markers.")
        if suffix == ".json":
            add("core.json-syntax", "Changed JSON must parse.")
        if suffix == ".py":
            add("core.python-syntax", "Changed Python must compile.")
        if suffix in {".html", ".htm"}:
            add("core.html-local-assets", "Changed HTML must not reference missing local assets.")
        if suffix in {".css", ".scss", ".sass"}:
            add("core.css-structure", "Changed stylesheet structure must have balanced blocks and closed comments/strings.")
        if suffix in {".md", ".rst", ".adoc"}:
            add("core.markdown-local-links", "Changed documentation must not introduce missing local link targets.")
    return [selected[key] for key in sorted(selected)]


def build_check_plan(changes: dict[str, Any]) -> dict[str, Any]:
    deleted = set(changes.get("observed", {}).get("deleted", [])) if isinstance(changes.get("observed"), dict) else set()
    path_rows = [classify_path(relative, deleted=relative in deleted) for relative in changes.get("paths", [])]
    surfaces = sorted({surface for row in path_rows for surface in row["surfaces"]})
    dimensions = sorted({dimension for row in path_rows for dimension in row["dimensions"]})
    by_surface: dict[str, list[str]] = defaultdict(list)
    for row in path_rows:
        for surface in row["surfaces"]:
            by_surface[surface].append(row["path"])

    if not path_rows:
        profile = "none"
        native_policy = {
            "selection": "not-required",
            "reason": "No canonical observed changed paths were detected.",
            "full_suite_automatic": False,
        }
    elif set(surfaces).issubset({"documentation", "release"}) and not {"application", "configuration", "data-state", "runtime-contract"}.intersection(dimensions):
        profile = "documentation"
        native_policy = {
            "selection": "not-recommended",
            "reason": "Documentation/release-metadata changes receive scoped content checks; the full native suite is not selected automatically.",
            "full_suite_automatic": False,
        }
    elif set(surfaces).issubset({"website", "frontend"}) and not {"data-state", "runtime-contract"}.intersection(dimensions):
        profile = "website"
        native_policy = {
            "selection": "scoped-native-if-project-contract-exists",
            "reason": "Website changes receive website-scoped Forge checks. A full native suite runs only when explicitly requested; a project-declared website gate may be added later.",
            "full_suite_automatic": False,
        }
    else:
        profile = "application"
        native_policy = {
            "selection": "recommended-explicit",
            "reason": "Application, configuration, verification, deletion, or data-state changes should use the owner-approved native gate when available.",
            "full_suite_automatic": False,
        }

    return {
        "schema": 1,
        "profile": profile,
        "affected_surfaces": surfaces,
        "impact_dimensions": dimensions,
        "paths_by_surface": {key: sorted(set(value)) for key, value in sorted(by_surface.items())},
        "required_checks": _required_checks(path_rows),
        "native_gate_policy": native_policy,
        "confidence": changes.get("confidence", "unknown"),
        "no_numeric_impact_score": True,
    }


def build_change_record(
    changes: dict[str, Any],
    plan: dict[str, Any],
    previous_snapshot: dict[str, Any],
    authority_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_snapshot = changes.get("current_snapshot", {}) if isinstance(changes.get("current_snapshot"), dict) else {}
    baseline_fingerprint = snapshot_fingerprint(previous_snapshot)
    current_fingerprint = snapshot_fingerprint(current_snapshot)
    canonical = {
        "baseline": baseline_fingerprint,
        "current": current_fingerprint,
        "paths": list(changes.get("paths", [])),
    }
    change_id = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]
    authority_baseline = authority_baseline if isinstance(authority_baseline, dict) else {}
    return {
        "schema": 1,
        "id": change_id,
        "recorded_utc": utc_now(),
        "source": "observed-checkpoint-reconciliation",
        "authoritative": True,
        "authoritative_scope": "change-detection-only",
        "owner_authorized": authority_baseline.get("status") == "CURRENT",
        "authority_baseline_id": str(authority_baseline.get("baseline_id", "")),
        "authority_quarantined": bool(authority_baseline.get("quarantined", True)),
        "truth_boundary": "This change record is canonical for bounded path reconciliation only. It does not prove project-authority acceptance, file authorship, or release approval.",
        "status": changes.get("status", "unknown"),
        "count": changes.get("count", 0),
        "paths": list(changes.get("paths", [])),
        "observed": changes.get("observed", {}),
        "supplied": changes.get("supplied", {}),
        "baseline_fingerprint": baseline_fingerprint,
        "current_fingerprint": current_fingerprint,
        "confidence": changes.get("confidence", "unknown"),
        "plan": plan,
    }

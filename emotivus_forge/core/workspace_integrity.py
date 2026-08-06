from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .common import normalize_rel, utc_now, sha256_file as _sha256_file
from .state import load_state, save_state

WORKSPACE_INTEGRITY_SCHEMA = 1
DEFAULT_MAX_FILES = 50_000
DEFAULT_MAX_TOTAL_BYTES = 2_000_000_000
EXCLUDED_PARTS = {
    ".forge", ".git", ".hg", ".svn", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules",
}

TRUTH_BOUNDARY = (
    "Forge content-addresses the observed regular files and symlink targets in the bounded "
    "workspace, excluding Forge state and common generated dependency/cache trees. A current "
    "seal candidate proves only that those observed bytes did not drift after the passing "
    "checkpoint; it does not authenticate the writer, prove semantic correctness, or replace "
    "exact-package certification."
)


def _excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def fingerprint_workspace(
    project_root: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    root = project_root.resolve()
    rows: list[tuple[str, str, int, str]] = []
    total_bytes = 0
    for current, dir_names, file_names in os.walk(root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        dir_names[:] = [
            name for name in sorted(dir_names)
            if not _excluded(relative_dir / name)
        ]
        for name in sorted(file_names):
            path = current_path / name
            relative_path = path.relative_to(root)
            if _excluded(relative_path):
                continue
            relative = normalize_rel(relative_path)
            if path.is_symlink():
                target = os.readlink(path)
                encoded = target.encode("utf-8", errors="surrogateescape")
                rows.append((relative, "symlink", len(encoded), hashlib.sha256(encoded).hexdigest()))
                total_bytes += len(encoded)
            elif path.is_file():
                size = path.stat().st_size
                total_bytes += size
                rows.append((relative, "file", size, _sha256_file(path)))
            else:
                continue
            if len(rows) > max_files:
                raise ValueError(
                    f"Workspace integrity exceeded the {max_files} file limit; no exact seal candidate was recorded."
                )
            if total_bytes > max_total_bytes:
                raise ValueError(
                    f"Workspace integrity exceeded the {max_total_bytes} byte limit; no exact seal candidate was recorded."
                )
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "schema": WORKSPACE_INTEGRITY_SCHEMA,
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
        "file_count": len(rows),
        "total_bytes": total_bytes,
        "excluded_parts": sorted(EXCLUDED_PARTS),
        "generated_utc": utc_now(),
        "truth_boundary": TRUTH_BOUNDARY,
    }


def start_workspace_observation(project_root: Path) -> dict[str, Any]:
    state = load_state(project_root)
    observed = fingerprint_workspace(project_root)
    state["workspace_integrity"] = {
        "schema": WORKSPACE_INTEGRITY_SCHEMA,
        "status": "OBSERVING",
        "session_start": observed,
        "seal_candidate": {},
        "last_assessment": {},
        "truth_boundary": TRUTH_BOUNDARY,
    }
    save_state(project_root, state)
    return state["workspace_integrity"]


def checkpoint_workspace(project_root: Path) -> dict[str, Any]:
    state = load_state(project_root)
    observed = fingerprint_workspace(project_root)
    current = state.get("workspace_integrity", {}) if isinstance(state.get("workspace_integrity"), dict) else {}
    record = {
        "schema": WORKSPACE_INTEGRITY_SCHEMA,
        "status": "CANDIDATE_CURRENT",
        "session_start": current.get("session_start", {}),
        "seal_candidate": observed,
        "last_assessment": {
            "status": "CURRENT",
            "assessed_utc": utc_now(),
            "expected_fingerprint": observed["fingerprint"],
            "observed_fingerprint": observed["fingerprint"],
        },
        "truth_boundary": TRUTH_BOUNDARY,
    }
    state["workspace_integrity"] = record
    save_state(project_root, state)
    return record


def assess_workspace_integrity(project_root: Path) -> dict[str, Any]:
    state = load_state(project_root)
    record = state.get("workspace_integrity", {}) if isinstance(state.get("workspace_integrity"), dict) else {}
    candidate = record.get("seal_candidate", {}) if isinstance(record.get("seal_candidate"), dict) else {}
    expected = str(candidate.get("fingerprint", ""))
    if not expected:
        return {
            "schema": WORKSPACE_INTEGRITY_SCHEMA,
            "status": "NOT_ESTABLISHED",
            "reason": "No passing Check checkpoint has recorded an exact workspace seal candidate.",
            "truth_boundary": TRUTH_BOUNDARY,
        }
    observed = fingerprint_workspace(project_root)
    status = "CURRENT" if observed["fingerprint"] == expected else "DRIFTED"
    return {
        "schema": WORKSPACE_INTEGRITY_SCHEMA,
        "status": status,
        "reason": (
            "The bounded workspace exactly matches the passing Check seal candidate."
            if status == "CURRENT"
            else "Workspace bytes changed after the passing Check seal candidate was recorded."
        ),
        "expected_fingerprint": expected,
        "observed_fingerprint": observed["fingerprint"],
        "expected_file_count": candidate.get("file_count", 0),
        "observed_file_count": observed.get("file_count", 0),
        "expected_total_bytes": candidate.get("total_bytes", 0),
        "observed_total_bytes": observed.get("total_bytes", 0),
        "assessed_utc": utc_now(),
        "truth_boundary": TRUTH_BOUNDARY,
    }


def persist_workspace_assessment(project_root: Path, assessment: dict[str, Any]) -> None:
    state = load_state(project_root)
    record = state.get("workspace_integrity", {}) if isinstance(state.get("workspace_integrity"), dict) else {}
    record = dict(record)
    record["schema"] = WORKSPACE_INTEGRITY_SCHEMA
    record["status"] = assessment.get("status", "UNKNOWN")
    record["last_assessment"] = dict(assessment)
    record["truth_boundary"] = TRUTH_BOUNDARY
    state["workspace_integrity"] = record
    save_state(project_root, state)


def require_current_seal_candidate(project_root: Path) -> dict[str, Any]:
    assessment = assess_workspace_integrity(project_root)
    persist_workspace_assessment(project_root, assessment)
    if assessment.get("status") != "CURRENT":
        raise ValueError(str(assessment.get("reason", "Workspace integrity is not current.")))
    return assessment


def fingerprint_selection(root: Path, files: Iterable[Path]) -> dict[str, Any]:
    root = root.resolve()
    rows: list[tuple[str, int, str]] = []
    for path in sorted((item.resolve() for item in files), key=lambda item: item.as_posix()):
        try:
            relative = normalize_rel(path.relative_to(root))
        except ValueError as exc:
            raise ValueError(f"Selected build source escaped the package root: {path}") from exc
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Selected build source is not a regular file: {relative}")
        rows.append((relative, path.stat().st_size, _sha256_file(path)))
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
        "file_count": len(rows),
        "total_bytes": sum(row[1] for row in rows),
        "files": {row[0]: {"size": row[1], "sha256": row[2]} for row in rows},
    }


def require_selection_unchanged(root: Path, files: Iterable[Path], expected: dict[str, Any]) -> dict[str, Any]:
    observed = fingerprint_selection(root, files)
    if observed.get("fingerprint") != expected.get("fingerprint"):
        raise ValueError("Selected package source bytes drifted during the build; output was not published.")
    return observed

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .state import load_settings

IDENTITY_SCHEMA = 1


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Project identity requires {label}.")
    return text


def _source_path(project_root: Path, forge_root: Path, raw_path: str | Path) -> tuple[Path, str]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError("Project identity must be a regular project file outside .forge.")
    if _inside(path, forge_root.resolve()):
        raise ValueError("Project identity cannot come from the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Project identity file does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def validate_project_identity(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source_path(project_root, forge_root, source_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Project identity is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != IDENTITY_SCHEMA:
        raise ValueError("Project identity must be an object using schema 1.")
    identity_id = _required(raw.get("identity_id", "project"), "identity_id")
    authority = _required(raw.get("authority"), "authority")
    build_id = _required(raw.get("build_id"), "build_id")
    release_train = str(raw.get("release_train", "")).strip()
    components_raw = raw.get("components")
    if not isinstance(components_raw, dict) or not components_raw:
        raise ValueError("Project identity requires at least one component.")
    components: dict[str, Any] = {}
    for component_id, item in sorted(components_raw.items()):
        cid = _required(component_id, "component id")
        if not isinstance(item, dict):
            raise ValueError(f"Component {cid} must be an object.")
        version = item.get("version")
        if version is not None:
            version = _required(version, f"components.{cid}.version")
        status = str(item.get("status", "present" if version is not None else "absent")).strip().lower()
        if status not in {"present", "absent", "planned"}:
            raise ValueError(f"Component {cid} status must be present, absent, or planned.")
        if status == "present" and version is None:
            raise ValueError(f"Present component {cid} requires a version.")
        if status == "absent" and version is not None:
            raise ValueError(f"Absent component {cid} must use null, never a placeholder version.")
        contracts_raw = item.get("contracts", {})
        if not isinstance(contracts_raw, dict):
            raise ValueError(f"Component {cid} contracts must be an object.")
        contracts = {str(key): _required(value, f"components.{cid}.contracts.{key}") for key, value in sorted(contracts_raw.items())}
        components[cid] = {"status": status, "version": version, "contracts": contracts}
    monotonic_raw = raw.get("monotonic", {})
    if not isinstance(monotonic_raw, dict):
        raise ValueError("Project identity monotonic values must be an object.")
    monotonic: dict[str, int] = {}
    for key, value in sorted(monotonic_raw.items()):
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Monotonic identity {key} must be a non-negative integer.")
        monotonic[str(key)] = value
    baseline_raw = raw.get("baseline", {})
    if not isinstance(baseline_raw, dict):
        raise ValueError("Project identity baseline must be an object.")
    baseline = {
        "build_id": str(baseline_raw.get("build_id", "")).strip(),
        "source": str(baseline_raw.get("source", "")).strip(),
        "confirmed_utc": str(baseline_raw.get("confirmed_utc", "")).strip(),
    }
    literal_policy_raw = raw.get("literal_policy", {})
    if not isinstance(literal_policy_raw, dict):
        raise ValueError("Project identity literal_policy must be an object.")
    scan_paths_raw = literal_policy_raw.get("scan_paths", [])
    exception_paths_raw = literal_policy_raw.get("exception_paths", [])
    if not isinstance(scan_paths_raw, list) or not isinstance(exception_paths_raw, list):
        raise ValueError("literal_policy scan_paths and exception_paths must be arrays.")
    scan_paths = [normalize_rel(str(item).strip().lstrip("/")) for item in scan_paths_raw if str(item).strip()]
    exception_paths = [normalize_rel(str(item).strip().lstrip("/")) for item in exception_paths_raw if str(item).strip()]
    file_limit = literal_policy_raw.get("file_limit", 200)
    if not isinstance(file_limit, int) or not 1 <= file_limit <= 2000:
        raise ValueError("literal_policy.file_limit must be an integer from 1 to 2000.")
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    identity = {
        "schema": IDENTITY_SCHEMA,
        "identity_id": identity_id,
        "authority": authority,
        "release_train": release_train,
        "build_id": build_id,
        "components": components,
        "monotonic": monotonic,
        "baseline": baseline,
        "literal_policy": {"scan_paths": scan_paths, "exception_paths": exception_paths, "file_limit": file_limit},
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "identity": identity,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _assert_monotonic(previous: dict[str, Any], current: dict[str, Any]) -> None:
    previous_values = previous.get("identity", {}).get("monotonic", {}) if isinstance(previous.get("identity"), dict) else {}
    current_values = current.get("monotonic", {}) if isinstance(current, dict) else {}
    if not isinstance(previous_values, dict) or not isinstance(current_values, dict):
        return
    for key, old in previous_values.items():
        new = current_values.get(key)
        if isinstance(old, int) and isinstance(new, int) and new < old:
            raise ValueError(f"Monotonic identity {key} cannot decrease from {old} to {new}.")


def record_project_identity(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_project_identity(project_root, forge_root, source_path)
    settings = load_settings(project_root)
    previous = settings.get("project_identity", {}) if isinstance(settings.get("project_identity"), dict) else {}
    _assert_monotonic(previous, validated["identity"])
    record = {
        "status": "active",
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "identity": validated["identity"],
    }
    settings["project_identity"] = record
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "project-identity-recorded", {
        "identity_id": validated["identity"]["identity_id"],
        "build_id": validated["identity"]["build_id"],
        "release_train": validated["identity"]["release_train"],
        "components": validated["identity"]["components"],
        "monotonic": validated["identity"]["monotonic"],
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
    }, source=validated["identity"]["authority"])
    record["event_id"] = event["id"]
    settings["project_identity"] = record
    write_json(ForgePaths(project_root).settings, settings)
    return record


def project_identity_record(project_root: Path) -> dict[str, Any]:
    settings = load_settings(project_root.resolve())
    raw = settings.get("project_identity", {}) if isinstance(settings, dict) else {}
    if not isinstance(raw, dict) or not raw:
        return {}
    return fingerprint_bound_status(
        project_root.resolve(), raw,
        changed_status="approval-required",
        missing_reason="The owner-controlled project identity source is missing.",
        changed_reason="The owner-controlled project identity changed and must be recorded again.",
    )


def current_build_id(project_root: Path) -> str:
    """Active-lifecycle build_id for the project, or "" when not active/recorded.

    Shared truth-boundary read routed through project identity so the release
    services (package, proof, distribution) no longer each re-implement it.
    """
    record = project_identity_record(project_root)
    if record.get("lifecycle_status") != "active":
        return ""
    identity = record.get("identity", {}) if isinstance(record.get("identity"), dict) else {}
    return str(identity.get("build_id", "")).strip()


def project_identity_summary(project_root: Path) -> dict[str, Any]:
    record = project_identity_record(project_root)
    if not record:
        return {
            "schema": 1,
            "status": "not-recorded",
            "component_count": 0,
            "present_components": 0,
            "build_id": "",
            "release_train": "",
            "attention": [],
            "truth_boundary": "Forge never chooses project versions or component identities.",
        }
    identity = record.get("identity", {}) if isinstance(record.get("identity"), dict) else {}
    components = identity.get("components", {}) if isinstance(identity.get("components"), dict) else {}
    attention = [str(record.get("reason", ""))] if record.get("status") != "active" and record.get("reason") else []
    return {
        "schema": 1,
        "status": record.get("status", "unknown"),
        "build_id": identity.get("build_id", ""),
        "release_train": identity.get("release_train", ""),
        "component_count": len(components),
        "present_components": sum(1 for item in components.values() if isinstance(item, dict) and item.get("status") == "present"),
        "components": components,
        "monotonic": identity.get("monotonic", {}),
        "baseline": identity.get("baseline", {}),
        "contract_source": record.get("contract_source", ""),
        "attention": attention,
        "truth_boundary": identity.get("truth_boundary", "Forge never chooses project versions or component identities."),
    }


def _matches(relative: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return relative == prefix or relative.startswith(prefix + "/")
    return False


def detect_identity_literal_copies(project_root: Path, forge_root: Path) -> dict[str, Any]:
    record = project_identity_record(project_root)
    if not record or record.get("status") != "active":
        return {"schema": 1, "status": "NOT_CONFIGURED", "scanned_files": 0, "findings": []}
    identity = record.get("identity", {}) if isinstance(record.get("identity"), dict) else {}
    policy = identity.get("literal_policy", {}) if isinstance(identity.get("literal_policy"), dict) else {}
    scan_patterns = policy.get("scan_paths", []) if isinstance(policy.get("scan_paths"), list) else []
    if not scan_patterns:
        return {"schema": 1, "status": "NOT_CONFIGURED", "scanned_files": 0, "findings": [], "reason": "No literal scan paths are declared."}
    exceptions = policy.get("exception_paths", []) if isinstance(policy.get("exception_paths"), list) else []
    exceptions = [*exceptions, str(record.get("contract_source", ""))]
    values: dict[str, str] = {}
    build_id = str(identity.get("build_id", "")).strip()
    if len(build_id) >= 3:
        values["build_id"] = build_id
    components = identity.get("components", {}) if isinstance(identity.get("components"), dict) else {}
    for component_id, item in components.items():
        if isinstance(item, dict) and item.get("status") == "present":
            version = str(item.get("version", "")).strip()
            if len(version) >= 3:
                values[f"component:{component_id}"] = version
    findings: list[dict[str, Any]] = []
    scanned = 0
    file_limit = int(policy.get("file_limit", 200))
    text_suffixes = {".py", ".php", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".sh", ".cmd", ".md", ".txt"}
    for current, dirs, files in os.walk(project_root.resolve()):
        current_path = Path(current)
        dirs[:] = [name for name in sorted(dirs) if name not in {".forge", ".git", "__pycache__"} and not (current_path / name).is_symlink()]
        if current_path == forge_root.resolve() or forge_root.resolve() in current_path.parents:
            dirs[:] = []
            continue
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink() or path.suffix.lower() not in text_suffixes:
                continue
            relative = normalize_rel(path.relative_to(project_root))
            if not any(_matches(relative, pattern) for pattern in scan_patterns):
                continue
            if any(_matches(relative, pattern) for pattern in exceptions if pattern):
                continue
            scanned += 1
            if scanned > file_limit:
                return {
                    "schema": 1, "status": "TRUNCATED", "scanned_files": file_limit, "findings": findings,
                    "reason": f"Identity literal scan reached the project-owned file limit of {file_limit}.",
                }
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for label, value in values.items():
                if value in content:
                    findings.append({
                        "check": "core.identity-single-source",
                        "severity": "warning",
                        "path": relative,
                        "line": 0,
                        "message": f"Owner-declared identity literal {label} is copied into this configured scan path; derive it from the canonical identity or record an explicit exception.",
                    })
    return {
        "schema": 1,
        "status": "WARN" if findings else "PASS",
        "scanned_files": scanned,
        "findings": findings,
        "truth_boundary": (
            "This check finds exact copied identity literals only in project-owned scan paths. It does not prove all identity consumers derive values correctly."
        ),
    }

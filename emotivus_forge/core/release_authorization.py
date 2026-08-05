from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .release_package import evaluate_release_package, release_package_records
from .state import load_settings

RELEASE_AUTHORIZATION_SCHEMA = 1
RELEASE_DECISION = "authorize-public-release"


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Release authorization requires {label}.")
    return text


def _identifier(value: Any, label: str) -> str:
    text = _required(value, label)
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in text):
        raise ValueError(f"{label} may contain only lowercase letters, numbers, hyphens, and underscores.")
    return text


def _parse_utc(value: Any, label: str) -> datetime:
    text = _required(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Release authorization {label} must be timezone-aware ISO 8601.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Release authorization {label} must be timezone-aware ISO 8601.")
    return parsed.astimezone(timezone.utc)


def _source(project_root: Path, forge_root: Path, raw: str | Path) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError("Release authorization must be a project-owned file outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Release authorization does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _current_exact_package(project_root: Path, package_id: str) -> dict[str, Any]:
    records = release_package_records(project_root)
    record = records.get(package_id, {}) if isinstance(records, dict) else {}
    if not isinstance(record, dict) or record.get("lifecycle_status") != "active":
        raise ValueError(f"Release authorization requires an active release package record: {package_id}")
    evaluation = evaluate_release_package(project_root)
    final_package = evaluation.get("final_package", {}) if isinstance(evaluation.get("final_package"), dict) else {}
    if evaluation.get("release_package_id") != package_id or final_package.get("status") != "PASS":
        raise ValueError("Release authorization requires a current exact final-package binding.")
    return final_package


def validate_release_authorization(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    source, source_rel = _source(project_root, forge_root, source_path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Release authorization is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != RELEASE_AUTHORIZATION_SCHEMA:
        raise ValueError("Release authorization must be an object using schema 1.")

    authorization_id = _identifier(raw.get("release_authorization_id"), "release_authorization_id")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    authority_source = _required(raw.get("authority_source"), "authority_source", minimum=4)
    package_id = _identifier(raw.get("release_package_id"), "release_package_id")
    final_package = _current_exact_package(project_root, package_id)
    decision = _required(raw.get("decision"), "decision")
    if decision != RELEASE_DECISION:
        raise ValueError(f"Release authorization decision must be {RELEASE_DECISION!r}.")

    package_sha256 = str(raw.get("package_sha256", "")).strip().lower()
    if len(package_sha256) != 64 or any(char not in "0123456789abcdef" for char in package_sha256):
        raise ValueError("Release authorization package_sha256 must be an exact lowercase SHA-256 digest.")
    package_bytes = raw.get("package_bytes")
    if isinstance(package_bytes, bool) or not isinstance(package_bytes, int) or package_bytes <= 0:
        raise ValueError("Release authorization package_bytes must be a positive integer.")
    build_id = _required(raw.get("build_id"), "build_id")
    if package_sha256 != str(final_package.get("artifact_sha256", "")):
        raise ValueError("Release authorization package_sha256 does not match the current exact final package.")
    if package_bytes != int(final_package.get("artifact_bytes", 0) or 0):
        raise ValueError("Release authorization package_bytes does not match the current exact final package.")
    if build_id != str(final_package.get("build_id", "")):
        raise ValueError("Release authorization build_id does not match the current exact final package.")

    authorized = _parse_utc(raw.get("authorized_utc"), "authorized_utc")
    valid_until = _parse_utc(raw.get("valid_until_utc"), "valid_until_utc")
    now = datetime.now(timezone.utc)
    if authorized > now:
        raise ValueError("Release authorization authorized_utc cannot be in the future.")
    if valid_until <= now:
        raise ValueError("Release authorization valid_until_utc must be in the future when recorded.")
    if valid_until <= authorized:
        raise ValueError("Release authorization valid_until_utc must be after authorized_utc.")

    channels_raw = raw.get("authorized_channels")
    if not isinstance(channels_raw, list) or not channels_raw:
        raise ValueError("Release authorization authorized_channels must be a non-empty array.")
    channels: list[str] = []
    for value in channels_raw:
        channel = _required(value, "authorized_channels item", minimum=3)
        if channel not in channels:
            channels.append(channel)

    conditions_raw = raw.get("conditions", [])
    if not isinstance(conditions_raw, list):
        raise ValueError("Release authorization conditions must be an array.")
    conditions = [str(item).strip() for item in conditions_raw if str(item).strip()][:50]
    rationale = _required(raw.get("rationale"), "rationale", minimum=40)
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=60)

    contract = {
        "schema": 1,
        "release_authorization_id": authorization_id,
        "title": title,
        "authority": authority,
        "authority_source": authority_source,
        "release_package_id": package_id,
        "package_sha256": package_sha256,
        "package_bytes": package_bytes,
        "build_id": build_id,
        "decision": decision,
        "authorized_utc": authorized.isoformat().replace("+00:00", "Z"),
        "valid_until_utc": valid_until.isoformat().replace("+00:00", "Z"),
        "authorized_channels": channels,
        "conditions": conditions,
        "rationale": rationale,
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "contract_source": source_rel,
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def record_release_authorization(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_release_authorization(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.setdefault("release_authorizations", {})
    if not isinstance(records, dict):
        records = {}
        settings["release_authorizations"] = records
    for identifier, existing in records.items():
        if identifier == contract["release_authorization_id"] or not isinstance(existing, dict) or existing.get("status") == "retired":
            continue
        raise ValueError(f"Only one active release authorization may exist; retire {identifier} first.")
    record = {
        "status": "active",
        "recorded_utc": utc_now(),
        "contract": contract,
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
    }
    records[contract["release_authorization_id"]] = record
    settings["release_authorizations"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "release-authorization-recorded", {
        "release_authorization_id": contract["release_authorization_id"],
        "release_package_id": contract["release_package_id"],
        "package_sha256": contract["package_sha256"],
        "package_bytes": contract["package_bytes"],
        "build_id": contract["build_id"],
        "authorized_channels": contract["authorized_channels"],
        "valid_until_utc": contract["valid_until_utc"],
        "contract_fingerprint": validated["contract_fingerprint"],
    }, source=contract["authority"])
    record["event_id"] = event["id"]
    records[contract["release_authorization_id"]] = record
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_release_authorization(project_root: Path, authorization_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("Release authorization retirement requires a reason.")
    settings = load_settings(project_root.resolve())
    records = settings.get("release_authorizations", {})
    if not isinstance(records, dict) or authorization_id not in records:
        raise ValueError(f"Unknown release authorization record: {authorization_id}")
    record = dict(records[authorization_id])
    record.update({"status": "retired", "retired_utc": utc_now(), "retirement_reason": reason.strip(), "retired_by": authority})
    records[authorization_id] = record
    settings["release_authorizations"] = records
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "release-authorization-retired", {"release_authorization_id": authorization_id, "reason": reason.strip()}, source=authority)
    return record


def release_authorization_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root.resolve()).get("release_authorizations", {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for identifier, value in raw.items():
        if not isinstance(value, dict):
            continue
        result[str(identifier)] = fingerprint_bound_status(
            project_root.resolve(), value,
            changed_status="approval-required",
            missing_reason="The release authorization source is missing.",
            changed_reason="The release authorization source changed and the exact package must be authorized again.",
        )
    return result


def evaluate_release_authorization(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    active = [record for record in release_authorization_records(project_root).values() if record.get("status") != "retired"]
    if not active:
        return {"schema": 1, "status": "NOT_RUN", "reason": "No active exact-package release authorization is recorded.", "truth_boundary": "Release authorization has not been recorded."}
    if len(active) > 1:
        return {"schema": 1, "status": "FAIL", "reason": "Multiple active release authorizations are present.", "truth_boundary": "Exactly one current exact-package authorization is required."}
    record = active[0]
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    if record.get("lifecycle_status") != "active":
        return {"schema": 1, "status": "FAIL", "release_authorization_id": contract.get("release_authorization_id", ""), "reason": str(record.get("reason", "Release authorization authority is not current.")), "truth_boundary": str(contract.get("truth_boundary", "Release authorization authority is not current."))}

    package_id = str(contract.get("release_package_id", ""))
    evaluation = evaluate_release_package(project_root)
    final_package = evaluation.get("final_package", {}) if isinstance(evaluation.get("final_package"), dict) else {}
    reasons: list[str] = []
    if evaluation.get("release_package_id") != package_id or final_package.get("status") != "PASS":
        reasons.append("The authorized exact final package is no longer current.")
    for key, expected in (
        ("package_sha256", final_package.get("artifact_sha256", "")),
        ("package_bytes", final_package.get("artifact_bytes", 0)),
        ("build_id", final_package.get("build_id", "")),
    ):
        if contract.get(key) != expected:
            reasons.append(f"Release authorization {key} no longer matches the exact final package.")
    try:
        valid_until = _parse_utc(contract.get("valid_until_utc"), "valid_until_utc")
        if valid_until <= datetime.now(timezone.utc):
            reasons.append("Release authorization has expired.")
    except ValueError as exc:
        reasons.append(str(exc))
    if contract.get("decision") != RELEASE_DECISION:
        reasons.append("Release authorization decision is not authorize-public-release.")
    return {
        "schema": 1,
        "status": "PASS" if not reasons else "FAIL",
        "release_authorization_id": contract.get("release_authorization_id", ""),
        "release_package_id": package_id,
        "package_sha256": contract.get("package_sha256", ""),
        "package_bytes": contract.get("package_bytes", 0),
        "build_id": contract.get("build_id", ""),
        "authority": contract.get("authority", ""),
        "authority_source": contract.get("authority_source", ""),
        "authorized_channels": contract.get("authorized_channels", []),
        "valid_until_utc": contract.get("valid_until_utc", ""),
        "conditions": contract.get("conditions", []),
        "reasons": reasons,
        "reason": "The project-declared authority explicitly authorized the exact current final package for the named channels." if not reasons else "; ".join(reasons),
        "truth_boundary": str(contract.get("truth_boundary", "Release authorization remains bounded.")),
    }


def release_authorization_summary(project_root: Path) -> dict[str, Any]:
    result = evaluate_release_authorization(project_root)
    return {
        "schema": 1,
        "status": result.get("status", "NOT_RUN"),
        "release_authorization_id": result.get("release_authorization_id", ""),
        "release_package_id": result.get("release_package_id", ""),
        "valid_until_utc": result.get("valid_until_utc", ""),
        "authorized_channel_count": len(result.get("authorized_channels", [])) if isinstance(result.get("authorized_channels"), list) else 0,
        "truth_boundary": "Compact exact-package authorization status only; Forge does not authenticate the declaring human or prove substantive review quality.",
    }

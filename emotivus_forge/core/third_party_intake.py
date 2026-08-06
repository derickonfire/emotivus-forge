from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .common import normalize_rel, read_json, sha256_file, utc_now, write_json
from .ledger import record_event
from .paths import ForgePaths
from .state import load_settings

THIRD_PARTY_INTAKE_SCHEMA = 1
CLASSIFICATIONS = {"adapt", "reimplement", "design-reference", "reject"}
DISTRIBUTIONS = {"public", "development-only", "reference-only", "rejected"}
STAGES = {"reviewed", "planned", "implemented", "rejected"}
DEPENDENCY_TYPES = {"standard-library", "runtime", "build", "test", "generated", "external-binary", "service", "none"}
TRUTH_BOUNDARY = (
    "Forge verifies the exact reviewed upstream archive and declared source members, records license, dependency, behavior, test, "
    "security, distribution, and retirement declarations, and checks that the complete upstream archive is not absorbed into the project tree. "
    "It does not provide legal advice, prove code correctness or security, verify undeclared transitive dependencies, or authorize release."
)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Third-party intake requires {label}.")
    return text


def _digest(value: Any, label: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be an exact lowercase SHA-256 digest.")
    return text


def _project_file(project_root: Path, forge_root: Path, raw_path: str | Path, label: str) -> tuple[Path, str]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError(f"{label} must be a regular project file outside .forge.")
    if _inside(path, forge_root.resolve()):
        raise ValueError(f"{label} cannot come from the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _external_archive(project_root: Path, forge_root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if _inside(path, project_root) or _inside(path, forge_root.resolve()):
        raise ValueError("The complete upstream archive must remain external to both the project tree and Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Third-party source archive does not exist as a regular file: {path}")
    return path


def _safe_member(raw: Any) -> str:
    value = str(raw or "").replace("\\", "/")
    pure = PurePosixPath(value)
    if not value or value.startswith("/") or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Unsafe upstream ZIP member path: {raw}")
    normalized = "/".join(part for part in pure.parts if part not in {"", "."})
    if not normalized:
        raise ValueError("Upstream ZIP member path cannot be empty.")
    return normalized


def _archive_members(path: Path) -> dict[str, dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Third-party source archive is not a readable ZIP: {path.name}") from exc
    members: dict[str, dict[str, Any]] = {}
    raw_names: set[str] = set()
    with archive:
        for info in archive.infolist():
            raw = info.filename.replace("\\", "/")
            if raw in raw_names:
                raise ValueError(f"Third-party source archive contains duplicate raw member name: {raw}")
            raw_names.add(raw)
            if info.is_dir():
                continue
            name = _safe_member(raw)
            if info.flag_bits & 0x1:
                raise ValueError(f"Third-party source archive contains encrypted member: {name}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                raise ValueError(f"Third-party source archive contains symlink member: {name}")
            digest = hashlib.sha256()
            length = 0
            with archive.open(info, "r") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
                    length += len(chunk)
            if name in members:
                raise ValueError(f"Third-party source archive normalizes multiple members to: {name}")
            members[name] = {"sha256": digest.hexdigest(), "bytes": length}
    return members


def _strings(raw: Any, label: str, *, minimum_items: int = 1) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be an array.")
    values: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in values:
            values.append(text)
    if len(values) < minimum_items:
        raise ValueError(f"{label} requires at least {minimum_items} item(s).")
    return values


def _dependencies(raw: Any, candidate_id: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError(f"Candidate {candidate_id} dependency_closure must be an array, including an explicit none entry when empty.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Candidate {candidate_id} dependency {index} must be an object.")
        dep_type = str(item.get("type", "")).strip().lower()
        if dep_type not in DEPENDENCY_TYPES:
            raise ValueError(f"Candidate {candidate_id} dependency type must be one of: {', '.join(sorted(DEPENDENCY_TYPES))}")
        row = {
            "name": _required(item.get("name"), f"candidate {candidate_id} dependency name"),
            "type": dep_type,
            "version": str(item.get("version", "")).strip(),
            "license": str(item.get("license", "")).strip(),
            "required": bool(item.get("required", True)),
            "note": str(item.get("note", "")).strip(),
        }
        rows.append(row)
    if not rows:
        raise ValueError(f"Candidate {candidate_id} must explicitly declare dependency closure; use one type=none entry when empty.")
    return rows


def _candidate(raw: Any, members: dict[str, dict[str, Any]], seen: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Each third-party candidate must be an object.")
    candidate_id = _required(raw.get("candidate_id"), "candidate_id")
    if candidate_id in seen:
        raise ValueError(f"Duplicate third-party candidate ID: {candidate_id}")
    seen.add(candidate_id)
    classification = str(raw.get("classification", "")).strip().lower()
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"Candidate {candidate_id} classification must be one of: {', '.join(sorted(CLASSIFICATIONS))}")
    stage = str(raw.get("stage", "planned")).strip().lower()
    if stage not in STAGES:
        raise ValueError(f"Candidate {candidate_id} stage must be one of: {', '.join(sorted(STAGES))}")
    distribution = str(raw.get("distribution", "")).strip().lower()
    if distribution not in DISTRIBUTIONS:
        raise ValueError(f"Candidate {candidate_id} distribution must be one of: {', '.join(sorted(DISTRIBUTIONS))}")
    if classification == "reject" and (distribution != "rejected" or stage != "rejected"):
        raise ValueError(f"Rejected candidate {candidate_id} must use stage=rejected and distribution=rejected.")
    if stage == "rejected" and classification != "reject":
        raise ValueError(f"Candidate {candidate_id} with stage=rejected must use classification=reject.")
    if classification == "design-reference" and distribution not in {"reference-only", "development-only"}:
        raise ValueError(f"Design-reference candidate {candidate_id} cannot be distributed as public code.")

    file_rows: list[dict[str, Any]] = []
    files_raw = raw.get("upstream_files", [])
    if not isinstance(files_raw, list):
        raise ValueError(f"Candidate {candidate_id} upstream_files must be an array.")
    for index, item in enumerate(files_raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Candidate {candidate_id} upstream file {index} must be an object.")
        path = _safe_member(item.get("path"))
        member = members.get(path)
        if member is None:
            raise ValueError(f"Candidate {candidate_id} upstream member is missing from the exact archive: {path}")
        expected_sha = _digest(item.get("sha256"), f"candidate {candidate_id} upstream file {path} sha256")
        expected_bytes = item.get("bytes")
        if expected_sha != member["sha256"] or not isinstance(expected_bytes, int) or expected_bytes != member["bytes"]:
            raise ValueError(f"Candidate {candidate_id} upstream member identity does not match archive bytes: {path}")
        file_rows.append({"path": path, **member})
    if classification in {"adapt", "reimplement"} and not file_rows:
        raise ValueError(f"Candidate {candidate_id} requires exact upstream file identities.")

    attribution = str(raw.get("attribution_notice", "")).strip()
    modified_files = _strings(raw.get("forge_files", []), f"candidate {candidate_id} forge_files", minimum_items=0)
    original_tests = _strings(raw.get("original_tests", []), f"candidate {candidate_id} original_tests", minimum_items=0)
    forge_tests = _strings(raw.get("forge_tests", []), f"candidate {candidate_id} forge_tests", minimum_items=0)
    if classification == "adapt":
        if len(attribution) < 20:
            raise ValueError(f"Adapted candidate {candidate_id} requires a durable attribution_notice.")
        if not modified_files or not original_tests or not forge_tests:
            raise ValueError(f"Adapted candidate {candidate_id} requires Forge files, upstream tests, and Forge-specific regressions.")

    return {
        "candidate_id": candidate_id,
        "classification": classification,
        "stage": stage,
        "distribution": distribution,
        "intended_capability": _required(raw.get("intended_capability"), f"candidate {candidate_id} intended_capability", minimum=8),
        "mission_fit": _required(raw.get("mission_fit"), f"candidate {candidate_id} mission_fit", minimum=20),
        "upstream_files": sorted(file_rows, key=lambda row: row["path"]),
        "dependency_closure": _dependencies(raw.get("dependency_closure"), candidate_id),
        "retained_behaviors": _strings(raw.get("retained_behaviors", []), f"candidate {candidate_id} retained_behaviors"),
        "changed_behaviors": _strings(raw.get("changed_behaviors", []), f"candidate {candidate_id} changed_behaviors"),
        "trust_semantic_differences": _strings(raw.get("trust_semantic_differences", []), f"candidate {candidate_id} trust_semantic_differences"),
        "security_review": _required(raw.get("security_review"), f"candidate {candidate_id} security_review", minimum=30),
        "confidentiality_review": _required(raw.get("confidentiality_review"), f"candidate {candidate_id} confidentiality_review", minimum=30),
        "original_tests": original_tests,
        "forge_tests": forge_tests,
        "forge_files": modified_files,
        "attribution_notice": attribution,
        "update_retirement_procedure": _required(raw.get("update_retirement_procedure"), f"candidate {candidate_id} update_retirement_procedure", minimum=20),
    }


def validate_third_party_intake(project_root: Path, forge_root: Path, contract_path: str | Path, source_archive_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve(); forge_root = forge_root.resolve()
    source, relative = _project_file(project_root, forge_root, contract_path, "Third-party intake contract")
    upstream = _external_archive(project_root, forge_root, source_archive_path)
    raw = read_json(source, None, strict=False)
    if not isinstance(raw, dict) or raw.get("schema") != THIRD_PARTY_INTAKE_SCHEMA:
        raise ValueError("Third-party intake contract must be valid UTF-8 JSON using schema 1.")

    observed_sha = sha256_file(upstream)
    observed_bytes = upstream.stat().st_size
    declared_name = _required(raw.get("upstream_archive_name"), "upstream_archive_name")
    if upstream.name != declared_name:
        raise ValueError(f"Upstream archive filename does not match contract: expected {declared_name}, observed {upstream.name}.")
    if observed_sha != _digest(raw.get("upstream_archive_sha256"), "upstream_archive_sha256"):
        raise ValueError("Upstream archive SHA-256 does not match the reviewed bytes.")
    if raw.get("upstream_archive_bytes") != observed_bytes:
        raise ValueError("Upstream archive byte length does not match the reviewed bytes.")
    members = _archive_members(upstream)

    license_raw = raw.get("license")
    if not isinstance(license_raw, dict):
        raise ValueError("Third-party intake requires a license object.")
    license_path = _safe_member(license_raw.get("upstream_file"))
    license_member = members.get(license_path)
    if license_member is None:
        raise ValueError("Declared upstream license file is missing from the exact source archive.")
    if license_member["sha256"] != _digest(license_raw.get("sha256"), "license.sha256"):
        raise ValueError("Declared upstream license digest does not match the exact source archive.")

    candidates_raw = raw.get("candidates")
    if not isinstance(candidates_raw, list) or not candidates_raw:
        raise ValueError("Third-party intake requires at least one candidate.")
    seen: set[str] = set()
    candidates = [_candidate(item, members, seen) for item in candidates_raw]
    intake = {
        "schema": 1,
        "intake_id": _required(raw.get("intake_id"), "intake_id"),
        "authority": _required(raw.get("authority"), "authority"),
        "upstream_project": _required(raw.get("upstream_project"), "upstream_project"),
        "upstream_version": _required(raw.get("upstream_version"), "upstream_version"),
        "upstream_archive_name": declared_name,
        "upstream_archive_sha256": observed_sha,
        "upstream_archive_bytes": observed_bytes,
        "upstream_member_count": len(members),
        "license": {
            "spdx": _required(license_raw.get("spdx"), "license.spdx"),
            "copyright": _required(license_raw.get("copyright"), "license.copyright"),
            "upstream_file": license_path,
            "sha256": license_member["sha256"],
            "bytes": license_member["bytes"],
            "notice_file": str(license_raw.get("notice_file", "")).strip(),
        },
        "full_source_distribution": str(raw.get("full_source_distribution", "")).strip().lower(),
        "candidates": sorted(candidates, key=lambda row: row["candidate_id"]),
        "truth_boundary": _required(raw.get("truth_boundary"), "truth_boundary", minimum=40),
    }
    if intake["full_source_distribution"] != "external-only":
        raise ValueError("Third-party intake requires full_source_distribution=external-only.")
    encoded = json.dumps(intake, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "intake": intake,
        "contract_source": relative,
        "source_fingerprint": sha256_file(source),
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "source_archive_verified_at_recording": True,
    }


def record_third_party_intake(project_root: Path, forge_root: Path, contract_path: str | Path, source_archive_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_third_party_intake(project_root, forge_root, contract_path, source_archive_path)
    intake = validated["intake"]
    settings = load_settings(project_root)
    records = settings.get("third_party_intakes", {}) if isinstance(settings.get("third_party_intakes"), dict) else {}
    intake_id = intake["intake_id"]
    previous = records.get(intake_id)
    if isinstance(previous, dict) and previous.get("status") == "active":
        raise ValueError(f"Third-party intake {intake_id} is already active; retire it before recording a replacement.")
    record = {
        "status": "active",
        "recorded_utc": utc_now(),
        "contract_source": validated["contract_source"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_archive_verified_at_recording": True,
        "intake": intake,
    }
    records[intake_id] = record
    settings["third_party_intakes"] = records
    controls = settings.get("third_party_control_paths", []) if isinstance(settings.get("third_party_control_paths"), list) else []
    if validated["contract_source"] not in controls:
        controls.append(validated["contract_source"])
    settings["third_party_control_paths"] = sorted(set(controls))
    lineage_controls = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    if validated["contract_source"] not in lineage_controls:
        lineage_controls.append(validated["contract_source"])
    settings["lineage_control_paths"] = sorted(set(lineage_controls))
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "third-party-intake-recorded", {
        "intake_id": intake_id,
        "upstream_project": intake["upstream_project"],
        "upstream_version": intake["upstream_version"],
        "upstream_archive_sha256": intake["upstream_archive_sha256"],
        "candidate_count": len(intake["candidates"]),
        "adapt_count": sum(1 for item in intake["candidates"] if item["classification"] == "adapt"),
        "implemented_count": sum(1 for item in intake["candidates"] if item["stage"] == "implemented"),
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
    }, source=intake["authority"])
    record["event_id"] = event["id"]
    records[intake_id] = record
    settings["third_party_intakes"] = records
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_third_party_intake(project_root: Path, intake_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    project_root = project_root.resolve()
    intake_id = _required(intake_id, "intake_id")
    reason = _required(reason, "retirement reason", minimum=10)
    settings = load_settings(project_root)
    records = settings.get("third_party_intakes", {}) if isinstance(settings.get("third_party_intakes"), dict) else {}
    current = records.get(intake_id)
    if not isinstance(current, dict):
        raise ValueError(f"Unknown third-party intake: {intake_id}")
    if current.get("status") == "retired":
        raise ValueError(f"Third-party intake {intake_id} is already retired.")
    retired = dict(current)
    retired.update({"status": "retired", "retired_utc": utc_now(), "retirement_reason": reason, "retired_by": authority})
    records[intake_id] = retired
    settings["third_party_intakes"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "third-party-intake-retired", {"intake_id": intake_id, "reason": reason}, source=authority)
    retired["retirement_event_id"] = event["id"]
    records[intake_id] = retired
    settings["third_party_intakes"] = records
    write_json(ForgePaths(project_root).settings, settings)
    return retired


def assess_third_party_intakes(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    settings = load_settings(project_root)
    records = settings.get("third_party_intakes", {}) if isinstance(settings.get("third_party_intakes"), dict) else {}
    active: list[dict[str, Any]] = []
    attention: list[dict[str, str]] = []
    for intake_id, record in sorted(records.items()):
        if not isinstance(record, dict) or record.get("status") != "active":
            continue
        source = project_root / str(record.get("contract_source", ""))
        if not source.is_file() or source.is_symlink():
            attention.append({"intake_id": intake_id, "reason": "The intake contract source is missing."})
            continue
        if sha256_file(source) != str(record.get("source_fingerprint", "")):
            attention.append({"intake_id": intake_id, "reason": "The intake contract source changed and must be recorded again."})
            continue
        intake = record.get("intake", {}) if isinstance(record.get("intake"), dict) else {}
        archive_name = str(intake.get("upstream_archive_name", ""))
        archive_sha = str(intake.get("upstream_archive_sha256", ""))
        absorbed_paths: list[str] = []
        if archive_name:
            for path in project_root.rglob(archive_name):
                if ".forge" in path.parts or not path.is_file() or path.is_symlink():
                    continue
                try:
                    relative = normalize_rel(path.relative_to(project_root))
                except ValueError:
                    continue
                if sha256_file(path) == archive_sha:
                    absorbed_paths.append(relative)
        if absorbed_paths:
            attention.append({"intake_id": intake_id, "reason": f"The complete upstream archive was absorbed into the project tree: {', '.join(absorbed_paths)}"})
        active.append({
            "intake_id": intake_id,
            "upstream_project": str(intake.get("upstream_project", "")),
            "upstream_version": str(intake.get("upstream_version", "")),
            "candidate_count": len(intake.get("candidates", [])) if isinstance(intake.get("candidates"), list) else 0,
            "adapt_count": sum(1 for item in intake.get("candidates", []) if isinstance(item, dict) and item.get("classification") == "adapt") if isinstance(intake.get("candidates"), list) else 0,
            "implemented_count": sum(1 for item in intake.get("candidates", []) if isinstance(item, dict) and item.get("stage") == "implemented") if isinstance(intake.get("candidates"), list) else 0,
            "contract_source": str(record.get("contract_source", "")),
            "archive_sha256": archive_sha,
        })
    status = "NOT_DECLARED" if not active and not attention else "ATTENTION" if attention else "CURRENT"
    reason = (
        "No third-party capability intake is recorded."
        if status == "NOT_DECLARED"
        else f"{len(attention)} third-party intake record(s) require attention."
        if status == "ATTENTION"
        else "All active third-party intake contracts match their recorded bytes and no exact upstream archive is present in the project tree."
    )
    return {
        "schema": 1,
        "status": status,
        "reason": reason,
        "active_count": len(active),
        "candidate_count": sum(int(item.get("candidate_count", 0)) for item in active),
        "adapt_count": sum(int(item.get("adapt_count", 0)) for item in active),
        "implemented_count": sum(int(item.get("implemented_count", 0)) for item in active),
        "active": active,
        "attention": attention,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def third_party_intake_summary(project_root: Path) -> dict[str, Any]:
    return assess_third_party_intakes(project_root)

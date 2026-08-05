from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .common import normalize_rel, sha256_file, utc_now, write_json
from .confidentiality_boundary import (
    PRIVATE_KEY_RE,
    SECRET_ASSIGNMENT_RE,
    SENSITIVE_PATH_PATTERNS,
    TEMPLATE_MARKERS,
    looks_like_placeholder,
)
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .project_identity import project_identity_record
from .provenance import evaluate_artifact_provenance, provenance_records
from .state import load_settings

RELEASE_PACKAGE_SCHEMA = 1
REVIEW_RECEIPT_SCHEMA = 1
ALLOWED_REVIEW_TYPES = (
    "security",
    "privacy",
    "accessibility",
    "compatibility",
    "installation",
    "upgrade",
    "rollback",
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
        raise ValueError(f"Release package contract requires {label}.")
    return text


def _source_path(project_root: Path, forge_root: Path, raw_path: str | Path) -> tuple[Path, str]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError("Release package contract must be a regular project file outside .forge.")
    if _inside(path, forge_root.resolve()):
        raise ValueError("Release package contract cannot come from the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Release package contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _project_file(project_root: Path, raw: str, *, label: str, require: bool = True) -> tuple[Path, str]:
    relative = normalize_rel(str(raw or "").strip().lstrip("/"))
    if not relative:
        raise ValueError(f"Release package contract requires {label}.")
    path = (project_root / relative).resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError(f"Release package {label} must remain inside the project and outside .forge.")
    if path.is_symlink():
        raise ValueError(f"Release package {label} cannot be a symlink: {relative}")
    if require and not path.is_file():
        raise ValueError(f"Release package {label} does not exist: {relative}")
    return path, relative


def _current_build_id(project_root: Path) -> str:
    record = project_identity_record(project_root)
    if record.get("lifecycle_status") != "active":
        return ""
    identity = record.get("identity", {}) if isinstance(record.get("identity"), dict) else {}
    return str(identity.get("build_id", "")).strip()


def _sanitize_scan(scan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    max_entries = scan.get("max_entries", 5000)
    max_entry_bytes = scan.get("max_entry_bytes", 2_000_000)
    max_total_text_bytes = scan.get("max_total_text_bytes", 10_000_000)
    if not isinstance(max_entries, int) or not 1 <= max_entries <= 50_000:
        raise ValueError("release scan max_entries must be an integer from 1 to 50000.")
    if not isinstance(max_entry_bytes, int) or not 1024 <= max_entry_bytes <= 20_000_000:
        raise ValueError("release scan max_entry_bytes must be an integer from 1024 to 20000000.")
    if not isinstance(max_total_text_bytes, int) or not 1024 <= max_total_text_bytes <= 100_000_000:
        raise ValueError("release scan max_total_text_bytes must be an integer from 1024 to 100000000.")
    paths = scan.get("forbidden_path_patterns", [])
    if not isinstance(paths, list):
        raise ValueError("release scan forbidden_path_patterns must be an array.")
    path_patterns = [str(item).strip() for item in paths if str(item).strip()]
    literals_raw = scan.get("forbidden_literals", [])
    if not isinstance(literals_raw, list):
        raise ValueError("release scan forbidden_literals must be an array.")
    private_literals: list[dict[str, Any]] = []
    public_literals: list[dict[str, Any]] = []
    labels: set[str] = set()
    for item in literals_raw:
        if not isinstance(item, dict):
            raise ValueError("Each forbidden literal must be an object with label and value.")
        label = _required(item.get("label"), "scan.forbidden_literals.label")
        value = _required(item.get("value"), f"scan.forbidden_literals[{label}].value", minimum=3)
        if label in labels:
            raise ValueError(f"Duplicate forbidden literal label: {label}")
        labels.add(label)
        case_sensitive = bool(item.get("case_sensitive", False))
        private_literals.append({"label": label, "value": value, "case_sensitive": case_sensitive})
        public_literals.append({
            "label": label,
            "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            "case_sensitive": case_sensitive,
        })
    public = {
        "max_entries": max_entries,
        "max_entry_bytes": max_entry_bytes,
        "max_total_text_bytes": max_total_text_bytes,
        "forbidden_path_patterns": path_patterns,
        "forbidden_literals": public_literals,
        "allow_template_paths": bool(scan.get("allow_template_paths", True)),
    }
    return public, private_literals


def validate_release_package_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    source, source_rel = _source_path(project_root, forge_root, source_path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Release package contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != RELEASE_PACKAGE_SCHEMA:
        raise ValueError("Release package contract must be an object using schema 1.")
    package_id = _required(raw.get("release_package_id"), "release_package_id")
    title = _required(raw.get("title", package_id), "title")
    authority = _required(raw.get("authority"), "authority")
    artifact, artifact_rel = _project_file(project_root, _required(raw.get("artifact_path"), "artifact_path"), label="artifact_path")
    if artifact.suffix.lower() != ".zip" or not zipfile.is_zipfile(artifact):
        raise ValueError("Release package certification currently supports valid ZIP artifacts only.")
    provenance_id = _required(raw.get("artifact_provenance_id"), "artifact_provenance_id")
    expected_build_id = _required(raw.get("expected_build_id"), "expected_build_id")
    current_build_id = _current_build_id(project_root)
    if not current_build_id:
        raise ValueError("Release package certification requires a current owner-controlled project identity.")
    if expected_build_id != current_build_id:
        raise ValueError(f"Release package expected_build_id {expected_build_id} does not match current build_id {current_build_id}.")
    scan_raw = raw.get("scan", {})
    if not isinstance(scan_raw, dict):
        raise ValueError("Release package scan must be an object.")
    public_scan, private_literals = _sanitize_scan(scan_raw)
    required_reviews_raw = raw.get("required_review_types", list(ALLOWED_REVIEW_TYPES))
    if not isinstance(required_reviews_raw, list):
        raise ValueError("required_review_types must be an array.")
    required_reviews: list[str] = []
    for item in required_reviews_raw:
        review_type = str(item).strip().lower()
        if review_type not in ALLOWED_REVIEW_TYPES:
            raise ValueError(f"Unsupported review type: {review_type}")
        if review_type not in required_reviews:
            required_reviews.append(review_type)
    receipt_paths_raw = raw.get("review_receipts", [])
    if not isinstance(receipt_paths_raw, list):
        raise ValueError("review_receipts must be an array of project-relative JSON paths.")
    receipt_paths: list[str] = []
    for item in receipt_paths_raw:
        _path, relative = _project_file(project_root, str(item), label="review_receipt", require=False)
        if relative not in receipt_paths:
            receipt_paths.append(relative)
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=40)
    contract = {
        "schema": 1,
        "release_package_id": package_id,
        "title": title,
        "authority": authority,
        "artifact_path": artifact_rel,
        "artifact_provenance_id": provenance_id,
        "expected_build_id": expected_build_id,
        "scan": public_scan,
        "required_review_types": required_reviews,
        "review_receipts": receipt_paths,
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "contract_source": source_rel,
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "artifact_sha256": sha256_file(artifact),
        "artifact_bytes": artifact.stat().st_size,
        "observed_build_id": current_build_id,
        "private_literals": private_literals,
    }


def record_release_package(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_release_package_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.setdefault("release_packages", {})
    if not isinstance(records, dict):
        records = {}
        settings["release_packages"] = records
    for identifier, existing in records.items():
        if str(identifier) == contract["release_package_id"] or not isinstance(existing, dict) or existing.get("status") == "retired":
            continue
        raise ValueError(f"Only one active release package may be certified at a time; retire {identifier} first.")
    record = {
        "status": "active",
        "recorded_utc": utc_now(),
        "contract": contract,
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "artifact_sha256": validated["artifact_sha256"],
        "artifact_bytes": validated["artifact_bytes"],
        "observed_build_id": validated["observed_build_id"],
    }
    records[contract["release_package_id"]] = record
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "release-package-recorded", {
        "release_package_id": contract["release_package_id"],
        "artifact_path": contract["artifact_path"],
        "artifact_sha256": validated["artifact_sha256"],
        "artifact_bytes": validated["artifact_bytes"],
        "expected_build_id": contract["expected_build_id"],
        "artifact_provenance_id": contract["artifact_provenance_id"],
        "required_review_types": contract["required_review_types"],
        "forbidden_literal_labels": [item["label"] for item in contract["scan"]["forbidden_literals"]],
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
    }, source=contract["authority"])
    record["event_id"] = event["id"]
    records[contract["release_package_id"]] = record
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_release_package(project_root: Path, package_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("Release package retirement requires a reason.")
    settings = load_settings(project_root.resolve())
    records = settings.get("release_packages", {})
    if not isinstance(records, dict) or package_id not in records:
        raise ValueError(f"Unknown release package record: {package_id}")
    record = dict(records[package_id])
    record.update({"status": "retired", "retired_utc": utc_now(), "retirement_reason": reason.strip(), "retired_by": authority})
    records[package_id] = record
    settings["release_packages"] = records
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "release-package-retired", {"release_package_id": package_id, "reason": reason.strip()}, source=authority)
    return record


def release_package_records(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root.resolve())
    raw = settings.get("release_packages", {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for identifier, value in raw.items():
        if not isinstance(value, dict):
            continue
        result[str(identifier)] = fingerprint_bound_status(
            project_root.resolve(), value,
            changed_status="approval-required",
            missing_reason="The release package contract is missing.",
            changed_reason="The release package contract changed and must be recorded again.",
        )
    return result


def _load_private_literals(project_root: Path, record: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    source = project_root / str(record.get("contract_source", ""))
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
        scan = raw.get("scan", {}) if isinstance(raw, dict) else {}
        _public, private = _sanitize_scan(scan if isinstance(scan, dict) else {})
        return private, ""
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [], str(exc)


def _is_template_path(relative: str) -> bool:
    lowered = relative.lower()
    return any(marker in lowered for marker in TEMPLATE_MARKERS)


def _sensitive_path(relative: str, extra_patterns: list[str]) -> bool:
    lowered = relative.lower()
    name = PurePosixPath(lowered).name
    patterns = list(SENSITIVE_PATH_PATTERNS) + extra_patterns
    return any(fnmatch.fnmatch(lowered, pattern.lower()) or fnmatch.fnmatch(name, pattern.lower()) for pattern in patterns)


def _zip_entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return (mode & 0o170000) == 0o120000


def _safe_zip_name(raw: str) -> str:
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return ""
    return str(path)


def _scan_zip(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    artifact_rel = str(contract.get("artifact_path", ""))
    artifact = project_root / artifact_rel
    scan = contract.get("scan", {}) if isinstance(contract.get("scan"), dict) else {}
    max_entries = int(scan.get("max_entries", 5000))
    max_entry_bytes = int(scan.get("max_entry_bytes", 2_000_000))
    max_total_text_bytes = int(scan.get("max_total_text_bytes", 10_000_000))
    extra_patterns = [str(item) for item in scan.get("forbidden_path_patterns", []) if str(item)]
    allow_templates = bool(scan.get("allow_template_paths", True))
    private_literals, literal_error = _load_private_literals(project_root, record)
    findings: list[dict[str, Any]] = []
    scanned_entries = 0
    text_entries = 0
    total_text_bytes = 0
    truncated = False
    if literal_error:
        findings.append({"kind": "contract", "path": str(record.get("contract_source", ".")), "message": f"Cannot load confidentiality literals: {literal_error}"})
    try:
        with zipfile.ZipFile(artifact) as archive:
            infos = archive.infolist()
            if len(infos) > max_entries:
                truncated = True
            for info in infos[:max_entries]:
                scanned_entries += 1
                name = _safe_zip_name(info.filename)
                if not name:
                    findings.append({"kind": "unsafe-entry", "path": info.filename, "message": "Archive entry is absolute, empty, or contains traversal segments."})
                    continue
                if info.flag_bits & 0x1:
                    findings.append({"kind": "encrypted-entry", "path": name, "message": "Encrypted archive entries cannot be certified."})
                    continue
                if _zip_entry_is_symlink(info):
                    findings.append({"kind": "symlink-entry", "path": name, "message": "Symlink archive entries are outside the bounded confidentiality model."})
                    continue
                if info.is_dir():
                    continue
                template = _is_template_path(name)
                if _sensitive_path(name, extra_patterns) and not (allow_templates and template):
                    findings.append({"kind": "sensitive-path", "path": name, "message": "Sensitive live path is present in the final package."})
                if info.file_size > max_entry_bytes:
                    continue
                if total_text_bytes + info.file_size > max_total_text_bytes:
                    truncated = True
                    continue
                try:
                    raw = archive.read(info)
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    findings.append({"kind": "unreadable-entry", "path": name, "message": f"Archive entry could not be read: {exc}"})
                    continue
                total_text_bytes += len(raw)
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                text_entries += 1
                if PRIVATE_KEY_RE.search(text):
                    findings.append({"kind": "private-key", "path": name, "message": "Private-key material marker is present."})
                for match in SECRET_ASSIGNMENT_RE.finditer(text):
                    if not looks_like_placeholder(match.group("value")):
                        findings.append({"kind": "secret-assignment", "path": name, "message": f"A non-placeholder value is assigned to {match.group('name')}."})
                for item in private_literals:
                    needle = str(item["value"])
                    haystack = text if bool(item.get("case_sensitive")) else text.lower()
                    target = needle if bool(item.get("case_sensitive")) else needle.lower()
                    if target in haystack:
                        findings.append({"kind": "forbidden-literal", "path": name, "label": item["label"], "message": f"Owner-declared contamination term {item['label']} is present."})
    except (OSError, zipfile.BadZipFile) as exc:
        return {
            "status": "FAIL",
            "complete": False,
            "findings": [{"kind": "archive", "path": artifact_rel, "message": f"Final package is not readable as ZIP: {exc}"}],
            "scanned_entries": 0,
            "text_entries": 0,
            "total_text_bytes": 0,
            "values_retained": False,
        }
    status = "FAIL" if findings else "PARTIAL" if truncated else "PASS"
    return {
        "status": status,
        "complete": not truncated,
        "findings": findings,
        "scanned_entries": scanned_entries,
        "text_entries": text_entries,
        "total_text_bytes": total_text_bytes,
        "entry_limit": max_entries,
        "text_byte_limit": max_total_text_bytes,
        "values_retained": False,
        "truth_boundary": "The bounded scan checks archive structure, sensitive paths, private-key markers, non-placeholder secret assignments, and owner-declared literal contamination. It does not prove absence of every possible secret or confidential fact.",
    }


def _evaluate_provenance(project_root: Path, record: dict[str, Any], artifact_sha256: str) -> tuple[str, str]:
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    provenance_id = str(contract.get("artifact_provenance_id", ""))
    provenance = provenance_records(project_root).get(provenance_id, {})
    if not provenance:
        return "NOT_RUN", f"Artifact provenance {provenance_id} is not recorded."
    if provenance.get("lifecycle_status") != "active":
        return "FAIL", f"Artifact provenance {provenance_id} is not current."
    provenance_contract = provenance.get("contract", {}) if isinstance(provenance.get("contract"), dict) else {}
    if str(provenance_contract.get("artifact_path", "")) != str(contract.get("artifact_path", "")):
        return "FAIL", "Registered provenance describes a different artifact path."
    if str(provenance.get("artifact_sha256", "")) != artifact_sha256:
        return "FAIL", "Registered provenance is not bound to the current final-package bytes."

    current = evaluate_artifact_provenance(project_root)
    evaluation = next(
        (
            item
            for item in current.get("evaluations", [])
            if isinstance(item, dict) and str(item.get("provenance_id", "")) == provenance_id
        ),
        None,
    )
    if not evaluation:
        return "FAIL", f"Artifact provenance {provenance_id} could not be evaluated against current inputs."
    if str(evaluation.get("status", "")) != "CURRENT":
        reasons = evaluation.get("reasons", []) if isinstance(evaluation.get("reasons"), list) else []
        detail = "; ".join(str(reason) for reason in reasons if str(reason).strip()) or str(evaluation.get("reason", "provenance is not current"))
        return "FAIL", f"Artifact provenance {provenance_id} is stale: {detail}."
    return "PASS", "Current artifact provenance is bound to the same exact package bytes, inputs, generator source, and declared baseline."


def _review_receipt(project_root: Path, relative: str, package_sha256: str, build_id: str) -> dict[str, Any]:
    path = project_root / relative
    if not path.is_file() or path.is_symlink():
        return {"status": "NOT_RUN", "path": relative, "reason": "Review receipt is missing."}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "path": relative, "reason": f"Review receipt is invalid JSON: {exc}"}
    if not isinstance(raw, dict) or raw.get("schema") != REVIEW_RECEIPT_SCHEMA:
        return {"status": "FAIL", "path": relative, "reason": "Review receipt must use schema 1."}
    review_type = str(raw.get("review_type", "")).strip().lower()
    if review_type not in ALLOWED_REVIEW_TYPES:
        return {"status": "FAIL", "path": relative, "reason": f"Unsupported review type {review_type or 'missing'}."}
    if str(raw.get("status", "")).strip().upper() != "PASS":
        return {"status": "FAIL", "path": relative, "review_type": review_type, "reason": "Review receipt does not report PASS."}
    if str(raw.get("package_sha256", "")).strip() != package_sha256:
        return {"status": "FAIL", "path": relative, "review_type": review_type, "reason": "Review receipt is bound to different package bytes."}
    if str(raw.get("candidate_build_id", "")).strip() != build_id:
        return {"status": "FAIL", "path": relative, "review_type": review_type, "reason": "Review receipt is bound to a different candidate build ID."}
    authority = str(raw.get("authority", "")).strip()
    reviewed_utc = str(raw.get("reviewed_utc", "")).strip()
    evidence_rel = normalize_rel(str(raw.get("evidence_path", "")).strip().lstrip("/"))
    expected_evidence_sha = str(raw.get("evidence_sha256", "")).strip()
    if not authority or not reviewed_utc or not evidence_rel or not expected_evidence_sha:
        return {"status": "FAIL", "path": relative, "review_type": review_type, "reason": "Review receipt lacks authority, timestamp, evidence path, or evidence digest."}
    evidence = (project_root / evidence_rel).resolve()
    if not _inside(evidence, project_root) or _inside(evidence, project_root / ".forge") or not evidence.is_file() or evidence.is_symlink():
        return {"status": "FAIL", "path": relative, "review_type": review_type, "reason": "Review evidence file is missing or outside the project boundary."}
    actual_evidence_sha = sha256_file(evidence)
    if actual_evidence_sha != expected_evidence_sha:
        return {"status": "FAIL", "path": relative, "review_type": review_type, "reason": "Review evidence bytes changed after the receipt was issued."}
    limitations = raw.get("limitations", [])
    if not isinstance(limitations, list):
        limitations = []
    return {
        "status": "PASS",
        "path": relative,
        "review_type": review_type,
        "review_id": str(raw.get("review_id", "")),
        "authority": authority,
        "reviewed_utc": reviewed_utc,
        "evidence_path": evidence_rel,
        "evidence_sha256": actual_evidence_sha,
        "limitations": [str(item) for item in limitations[:20]],
    }


def evaluate_release_package(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    active = [record for record in release_package_records(project_root).values() if record.get("status") != "retired"]
    if not active:
        return {
            "schema": 1,
            "status": "NOT_RUN",
            "final_package": {"status": "NOT_RUN", "reason": "No active release package contract is recorded."},
            "confidentiality": {"status": "NOT_RUN", "findings": [], "values_retained": False},
            "public_reviews": {"status": "NOT_RUN", "required": [], "receipts": []},
            "truth_boundary": "No exact final package is registered for Ship assessment.",
        }
    record = active[0]
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    package_id = str(contract.get("release_package_id", "release-package"))
    if record.get("lifecycle_status") != "active":
        return {
            "schema": 1,
            "status": "FAIL",
            "release_package_id": package_id,
            "final_package": {"status": "FAIL", "reason": str(record.get("reason", "Release package authority is not current."))},
            "confidentiality": {"status": "NOT_RUN", "findings": [], "values_retained": False},
            "public_reviews": {"status": "NOT_RUN", "required": contract.get("required_review_types", []), "receipts": []},
            "truth_boundary": str(contract.get("truth_boundary", "Release package authority is not current.")),
        }
    artifact_rel = str(contract.get("artifact_path", ""))
    artifact = project_root / artifact_rel
    build_id = _current_build_id(project_root)
    reasons: list[str] = []
    actual_sha = sha256_file(artifact) if artifact.is_file() and not artifact.is_symlink() else ""
    if not actual_sha:
        reasons.append("Final package is missing or not a regular file.")
    elif actual_sha != str(record.get("artifact_sha256", "")):
        reasons.append("Final package bytes changed after authority recorded the package.")
    if build_id != str(contract.get("expected_build_id", "")):
        reasons.append(f"Current build ID {build_id or 'unknown'} does not match expected {contract.get('expected_build_id', '')}.")
    provenance_status, provenance_reason = _evaluate_provenance(project_root, record, actual_sha)
    if provenance_status != "PASS":
        reasons.append(provenance_reason)
    final_status = "PASS" if not reasons else "FAIL" if actual_sha else "NOT_RUN"
    final_package = {
        "status": final_status,
        "release_package_id": package_id,
        "artifact_path": artifact_rel,
        "artifact_sha256": actual_sha,
        "recorded_artifact_sha256": record.get("artifact_sha256", ""),
        "artifact_bytes": artifact.stat().st_size if artifact.is_file() else 0,
        "build_id": build_id,
        "expected_build_id": contract.get("expected_build_id", ""),
        "provenance_status": provenance_status,
        "provenance_reason": provenance_reason,
        "reasons": reasons,
    }
    confidentiality = _scan_zip(project_root, record) if final_status == "PASS" else {"status": "NOT_RUN", "findings": [], "values_retained": False, "reason": "Final package binding must pass before confidentiality screening."}
    receipts = [_review_receipt(project_root, relative, actual_sha, build_id) for relative in contract.get("review_receipts", [])]
    by_type: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        review_type = str(receipt.get("review_type", ""))
        if review_type and review_type not in by_type:
            by_type[review_type] = receipt
    required = [str(item) for item in contract.get("required_review_types", [])]
    missing = [item for item in required if item not in by_type]
    failed = [item for item in required if item in by_type and by_type[item].get("status") != "PASS"]
    if final_status != "PASS" or confidentiality.get("status") != "PASS":
        reviews_status = "NOT_RUN"
    elif failed:
        reviews_status = "FAIL"
    elif missing:
        reviews_status = "PARTIAL"
    else:
        reviews_status = "PASS"
    public_reviews = {
        "status": reviews_status,
        "required": required,
        "passed": sorted(item for item in required if item in by_type and by_type[item].get("status") == "PASS"),
        "missing": missing,
        "failed": failed,
        "receipts": receipts,
        "truth_boundary": "Review receipts prove only that named authorities recorded bounded reviews against the exact package and evidence bytes. Forge does not perform or independently validate the substantive review methodology.",
    }
    overall = "FAIL" if final_status == "FAIL" or confidentiality.get("status") == "FAIL" or reviews_status == "FAIL" else "PASS" if final_status == confidentiality.get("status") == reviews_status == "PASS" else "PARTIAL"
    return {
        "schema": 1,
        "status": overall,
        "release_package_id": package_id,
        "final_package": final_package,
        "confidentiality": confidentiality,
        "public_reviews": public_reviews,
        "truth_boundary": str(contract.get("truth_boundary", "Release certification remains bounded.")),
    }


def release_package_summary(project_root: Path) -> dict[str, Any]:
    evaluation = evaluate_release_package(project_root)
    final_package = evaluation.get("final_package", {}) if isinstance(evaluation.get("final_package"), dict) else {}
    confidentiality = evaluation.get("confidentiality", {}) if isinstance(evaluation.get("confidentiality"), dict) else {}
    reviews = evaluation.get("public_reviews", {}) if isinstance(evaluation.get("public_reviews"), dict) else {}
    return {
        "schema": 1,
        "status": evaluation.get("status", "NOT_RUN"),
        "final_package": final_package.get("status", "NOT_RUN"),
        "confidentiality": confidentiality.get("status", "NOT_RUN"),
        "public_reviews": reviews.get("status", "NOT_RUN"),
        "review_ratio": f"{len(reviews.get('passed', []))}/{len(reviews.get('required', []))}",
        "finding_count": len(confidentiality.get("findings", [])) if isinstance(confidentiality.get("findings"), list) else 0,
        "truth_boundary": "Compact release-package status only; package hashes, scan findings, and review evidence remain local.",
    }

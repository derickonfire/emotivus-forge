from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .common import normalize_rel, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths, IGNORED_DIR_NAMES
from .project_identity import project_identity_record
from .state import load_settings

PROVENANCE_SCHEMA = 1
DELIVERABLE_SUFFIXES = (".zip", ".tar", ".tgz", ".tar.gz", ".whl", ".jar", ".war", ".apk", ".aab")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Artifact provenance requires {label}.")
    return text


def _project_file(project_root: Path, raw: str, *, label: str) -> tuple[Path, str]:
    relative = normalize_rel(raw.strip().lstrip("/"))
    if not relative:
        raise ValueError(f"Artifact provenance requires {label}.")
    path = (project_root / relative).resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError(f"Artifact provenance {label} must remain inside the project and outside .forge.")
    if path.is_symlink():
        raise ValueError(f"Artifact provenance {label} cannot be a symlink: {relative}")
    return path, relative


def _expand_inputs(project_root: Path, patterns: list[str], *, file_limit: int) -> list[tuple[Path, str]]:
    found: dict[str, Path] = {}
    for raw in patterns:
        pattern = normalize_rel(str(raw).strip().lstrip("/"))
        if not pattern:
            continue
        candidates: list[Path]
        if any(token in pattern for token in "*?["):
            candidates = list(project_root.glob(pattern))
        else:
            candidates = [project_root / pattern]
        for candidate in candidates:
            if candidate.is_dir() and not candidate.is_symlink():
                for child in candidate.rglob("*"):
                    if child.is_file() and not child.is_symlink():
                        rel = normalize_rel(child.relative_to(project_root))
                        if any(part in IGNORED_DIR_NAMES for part in Path(rel).parts):
                            continue
                        found[rel] = child
            elif candidate.is_file() and not candidate.is_symlink():
                resolved = candidate.resolve()
                if not _inside(resolved, project_root) or _inside(resolved, project_root / ".forge"):
                    raise ValueError(f"Artifact provenance input escapes the project: {pattern}")
                rel = normalize_rel(resolved.relative_to(project_root))
                if not any(part in IGNORED_DIR_NAMES for part in Path(rel).parts):
                    found[rel] = resolved
    if not found:
        raise ValueError("Artifact provenance input_paths did not resolve any regular project files.")
    if len(found) > file_limit:
        raise ValueError(f"Artifact provenance resolved {len(found)} input files, above file_limit {file_limit}.")
    return [(path, rel) for rel, path in sorted(found.items())]


def _manifest(rows: list[tuple[Path, str]]) -> tuple[list[dict[str, Any]], str]:
    manifest = [{"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size} for path, rel in rows]
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return manifest, hashlib.sha256(encoded).hexdigest()


def _source_path(project_root: Path, forge_root: Path, raw_path: str | Path) -> tuple[Path, str]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError("Artifact provenance contract must be a regular project file outside .forge.")
    if _inside(path, forge_root.resolve()):
        raise ValueError("Artifact provenance contract cannot come from the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Artifact provenance contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def validate_provenance_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    source, source_rel = _source_path(project_root, forge_root, source_path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Artifact provenance contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != PROVENANCE_SCHEMA:
        raise ValueError("Artifact provenance contract must be an object using schema 1.")
    provenance_id = _required(raw.get("provenance_id"), "provenance_id")
    title = _required(raw.get("title", provenance_id), "title")
    authority = _required(raw.get("authority"), "authority")
    artifact_path, artifact_rel = _project_file(project_root, _required(raw.get("artifact_path"), "artifact_path"), label="artifact_path")
    if not artifact_path.is_file():
        raise ValueError(f"Artifact provenance artifact does not exist: {artifact_rel}")
    generator = raw.get("generator")
    if not isinstance(generator, dict):
        raise ValueError("Artifact provenance generator must be an object.")
    command = _required(generator.get("command"), "generator.command")
    generator_paths_raw = generator.get("source_paths", [])
    if not isinstance(generator_paths_raw, list):
        raise ValueError("Artifact provenance generator.source_paths must be an array.")
    generator_paths = [normalize_rel(str(item).strip().lstrip("/")) for item in generator_paths_raw if str(item).strip()]
    input_paths_raw = raw.get("input_paths")
    if not isinstance(input_paths_raw, list) or not input_paths_raw:
        raise ValueError("Artifact provenance input_paths must be a non-empty array.")
    input_paths = [normalize_rel(str(item).strip().lstrip("/")) for item in input_paths_raw if str(item).strip()]
    file_limit = raw.get("file_limit", 1000)
    if not isinstance(file_limit, int) or not 1 <= file_limit <= 10000:
        raise ValueError("Artifact provenance file_limit must be an integer from 1 to 10000.")
    baseline_build_id = str(raw.get("baseline_build_id", "")).strip()
    deliverable = bool(raw.get("deliverable", True))
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    contract = {
        "schema": 1,
        "provenance_id": provenance_id,
        "title": title,
        "authority": authority,
        "artifact_path": artifact_rel,
        "generator": {"command": command, "source_paths": generator_paths},
        "input_paths": input_paths,
        "file_limit": file_limit,
        "baseline_build_id": baseline_build_id,
        "deliverable": deliverable,
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    inputs = _expand_inputs(project_root, input_paths, file_limit=file_limit)
    if any(relative == artifact_rel for _path, relative in inputs):
        raise ValueError("Artifact provenance input_paths cannot include the output artifact itself.")
    input_manifest, input_digest = _manifest(inputs)
    generator_manifest: list[dict[str, Any]] = []
    generator_digest = ""
    if generator_paths:
        generator_rows = _expand_inputs(project_root, generator_paths, file_limit=min(file_limit, 200))
        generator_manifest, generator_digest = _manifest(generator_rows)
    identity = project_identity_record(project_root)
    current_baseline = ""
    if identity.get("lifecycle_status") == "active":
        identity_data = identity.get("identity", {}) if isinstance(identity.get("identity"), dict) else {}
        baseline = identity_data.get("baseline", {}) if isinstance(identity_data.get("baseline"), dict) else {}
        current_baseline = str(baseline.get("build_id", "")).strip()
    if baseline_build_id and not current_baseline:
        raise ValueError("Artifact provenance baseline_build_id requires a current owner-declared project baseline.")
    if baseline_build_id and baseline_build_id != current_baseline:
        raise ValueError(f"Artifact provenance baseline {baseline_build_id} does not match current owner-declared baseline {current_baseline}.")
    return {
        "contract": contract,
        "contract_source": source_rel,
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "artifact_sha256": sha256_file(artifact_path),
        "artifact_bytes": artifact_path.stat().st_size,
        "input_manifest": input_manifest,
        "input_digest": input_digest,
        "generator_manifest": generator_manifest,
        "generator_digest": generator_digest,
        "observed_baseline_build_id": current_baseline,
    }


def record_artifact_provenance(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_provenance_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.setdefault("artifact_provenance", {})
    if not isinstance(records, dict):
        records = {}
        settings["artifact_provenance"] = records
    for existing_id, existing in records.items():
        if str(existing_id) == contract["provenance_id"] or not isinstance(existing, dict) or existing.get("status") == "retired":
            continue
        existing_contract = existing.get("contract", {}) if isinstance(existing.get("contract"), dict) else {}
        if str(existing_contract.get("artifact_path", "")) == contract["artifact_path"]:
            raise ValueError(f"Artifact {contract['artifact_path']} already has active provenance record {existing_id}.")
    record = {
        "status": "active",
        "recorded_utc": utc_now(),
        **validated,
    }
    records[contract["provenance_id"]] = record
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "artifact-provenance-recorded", {
        "provenance_id": contract["provenance_id"],
        "title": contract["title"],
        "artifact_path": contract["artifact_path"],
        "artifact_sha256": validated["artifact_sha256"],
        "input_digest": validated["input_digest"],
        "generator_digest": validated["generator_digest"],
        "baseline_build_id": contract["baseline_build_id"],
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
    }, source=contract["authority"])
    record["event_id"] = event["id"]
    records[contract["provenance_id"]] = record
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_artifact_provenance(project_root: Path, provenance_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("Artifact provenance retirement requires a reason.")
    settings = load_settings(project_root.resolve())
    records = settings.get("artifact_provenance", {})
    if not isinstance(records, dict) or provenance_id not in records:
        raise ValueError(f"Unknown artifact provenance record: {provenance_id}")
    record = dict(records[provenance_id])
    record.update({"status": "retired", "retired_utc": utc_now(), "retirement_reason": reason.strip(), "retired_by": authority})
    records[provenance_id] = record
    settings["artifact_provenance"] = records
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "artifact-provenance-retired", {"provenance_id": provenance_id, "reason": reason.strip()}, source=authority)
    return record


def provenance_records(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root.resolve())
    raw = settings.get("artifact_provenance", {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for identifier, value in raw.items():
        if not isinstance(value, dict):
            continue
        result[str(identifier)] = fingerprint_bound_status(
            project_root.resolve(), value,
            changed_status="approval-required",
            missing_reason="The artifact provenance contract is missing.",
            changed_reason="The artifact provenance contract changed and must be recorded again.",
        )
    return result


def _current_manifest(project_root: Path, contract: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    try:
        rows = _expand_inputs(project_root, list(contract.get("input_paths", [])), file_limit=int(contract.get("file_limit", 1000)))
        manifest, digest = _manifest(rows)
        return manifest, digest, ""
    except ValueError as exc:
        return [], "", str(exc)


def _current_generator_manifest(project_root: Path, contract: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    generator = contract.get("generator", {}) if isinstance(contract.get("generator"), dict) else {}
    paths = generator.get("source_paths", []) if isinstance(generator.get("source_paths"), list) else []
    if not paths:
        return [], "", ""
    try:
        rows = _expand_inputs(project_root, [str(item) for item in paths], file_limit=200)
        manifest, digest = _manifest(rows)
        return manifest, digest, ""
    except ValueError as exc:
        return [], "", str(exc)


def _current_baseline(project_root: Path) -> str:
    identity = project_identity_record(project_root)
    if identity.get("lifecycle_status") != "active":
        return ""
    data = identity.get("identity", {}) if isinstance(identity.get("identity"), dict) else {}
    baseline = data.get("baseline", {}) if isinstance(data.get("baseline"), dict) else {}
    return str(baseline.get("build_id", "")).strip()


def _looks_deliverable(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in DELIVERABLE_SUFFIXES)


def _scan_delivery_perimeter(project_root: Path, registered: set[str], *, file_limit: int = 5000) -> dict[str, Any]:
    results: list[str] = []
    scanned = 0
    truncated = False
    for current, dirs, files in os.walk(project_root):
        base = Path(current)
        dirs[:] = [name for name in dirs if name not in IGNORED_DIR_NAMES and not (base / name).is_symlink()]
        for name in files:
            scanned += 1
            if scanned > file_limit:
                truncated = True
                break
            path = base / name
            if path.is_symlink() or not _looks_deliverable(path):
                continue
            rel = normalize_rel(path.relative_to(project_root))
            if rel not in registered:
                results.append(rel)
        if truncated:
            break
    return {"unregistered": sorted(results), "scanned_files": min(scanned, file_limit), "file_limit": file_limit, "truncated": truncated}


def find_unregistered_deliverables(project_root: Path, registered: set[str], *, file_limit: int = 5000) -> list[str]:
    return list(_scan_delivery_perimeter(project_root, registered, file_limit=file_limit)["unregistered"])


def evaluate_artifact_provenance(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    registered: set[str] = set()
    active = 0
    for provenance_id, record in sorted(provenance_records(project_root).items()):
        if record.get("status") == "retired":
            continue
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        artifact_rel = str(contract.get("artifact_path", ""))
        if artifact_rel:
            registered.add(artifact_rel)
        if record.get("lifecycle_status") != "active":
            evaluations.append({"provenance_id": provenance_id, "title": contract.get("title", provenance_id), "artifact_path": artifact_rel, "status": "APPROVAL_REQUIRED", "reason": record.get("reason", "Authority approval is not current.")})
            findings.append({"check": "core.artifact-provenance", "severity": "blocker", "path": record.get("contract_source", "."), "line": 0, "message": f"Artifact provenance {provenance_id} is not current: {record.get('reason', 'authority approval required')}"})
            continue
        active += 1
        reasons: list[str] = []
        artifact = project_root / artifact_rel
        actual_artifact = sha256_file(artifact) if artifact.is_file() and not artifact.is_symlink() else ""
        if not actual_artifact:
            reasons.append("artifact is missing or not a regular file")
        elif actual_artifact != str(record.get("artifact_sha256", "")):
            reasons.append("artifact bytes changed after provenance was recorded")
        _manifest_now, input_digest, input_error = _current_manifest(project_root, contract)
        if input_error:
            reasons.append(input_error)
        elif input_digest != str(record.get("input_digest", "")):
            reasons.append("declared inputs changed after artifact generation was recorded")
        _generator_now, generator_digest, generator_error = _current_generator_manifest(project_root, contract)
        if generator_error:
            reasons.append(generator_error)
        elif str(record.get("generator_digest", "")) and generator_digest != str(record.get("generator_digest", "")):
            reasons.append("generator source changed after artifact generation was recorded")
        expected_baseline = str(contract.get("baseline_build_id", "")).strip()
        current_baseline = _current_baseline(project_root)
        if expected_baseline and current_baseline != expected_baseline:
            reasons.append(f"current owner-declared baseline is {current_baseline or 'unknown'}, expected {expected_baseline}")
        status = "STALE" if reasons else "CURRENT"
        evaluations.append({
            "provenance_id": provenance_id,
            "title": contract.get("title", provenance_id),
            "artifact_path": artifact_rel,
            "status": status,
            "reasons": reasons,
            "artifact_sha256": actual_artifact,
            "recorded_artifact_sha256": record.get("artifact_sha256", ""),
            "input_digest": input_digest,
            "recorded_input_digest": record.get("input_digest", ""),
            "baseline_build_id": expected_baseline,
            "generator_command": contract.get("generator", {}).get("command", "") if isinstance(contract.get("generator"), dict) else "",
        })
        for reason in reasons:
            findings.append({"check": "core.artifact-provenance", "severity": "blocker", "path": artifact_rel or ".", "line": 0, "message": f"Artifact provenance {provenance_id} is stale: {reason}."})
    perimeter = _scan_delivery_perimeter(project_root, registered)
    unregistered = perimeter["unregistered"]
    perimeter_findings = [{"check": "core.delivery-perimeter", "severity": "warning", "path": path, "line": 0, "message": "Deliverable-shaped artifact has no registered generator/input provenance; delivery assurance is unavailable."} for path in unregistered]
    if perimeter["truncated"]:
        perimeter_findings.append({"check": "core.delivery-perimeter", "severity": "warning", "path": ".", "line": 0, "message": f"Delivery-perimeter scan reached its {perimeter['file_limit']}-file budget; unregistered-artifact coverage is incomplete."})
    return {
        "schema": 1,
        "status": "FAIL" if findings else "WARN" if perimeter_findings else "PASS",
        "active_count": active,
        "evaluations": evaluations,
        "findings": findings + perimeter_findings,
        "blocking_findings": findings,
        "perimeter_findings": perimeter_findings,
        "unregistered_deliverables": unregistered,
        "perimeter_scan": perimeter,
        "truth_boundary": "Recorded provenance binds current artifact bytes to authority-declared generator, inputs, and baseline observations. It does not prove the declared generator actually ran, the artifact works, or deployment succeeded.",
    }


def provenance_summary(project_root: Path) -> dict[str, Any]:
    active = 0
    attention = 0
    retired = 0
    for record in provenance_records(project_root).values():
        if record.get("status") == "retired":
            retired += 1
        elif record.get("lifecycle_status") == "active":
            active += 1
        else:
            attention += 1
    registered = {
        str(record.get("contract", {}).get("artifact_path", ""))
        for record in provenance_records(project_root).values()
        if isinstance(record.get("contract"), dict) and record.get("status") != "retired"
    }
    perimeter = _scan_delivery_perimeter(project_root, {item for item in registered if item})
    unregistered = perimeter["unregistered"]
    return {
        "schema": 1,
        "active": active,
        "attention": attention,
        "retired": retired,
        "unregistered_deliverables": len(unregistered),
        "unregistered_examples": unregistered[:3],
        "perimeter_truncated": perimeter["truncated"],
        "truth_boundary": "This compact summary reports provenance registration and source currency; exact digests and evaluation details remain local and are checked during Check.",
    }

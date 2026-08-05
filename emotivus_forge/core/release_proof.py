from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .common import normalize_rel, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .project_identity import project_identity_record
from .release_package import evaluate_release_package, release_package_records
from .state import load_settings

RELEASE_PROOF_SCHEMA = 1
RELEASE_PROOF_RECEIPT_SCHEMA = 1
REQUIRED_DOMAINS = (
    "security",
    "privacy",
    "accessibility",
    "compatibility",
    "installation",
    "upgrade",
    "rollback",
    "runtime",
    "deployment",
)
ALLOWED_SURFACE_KINDS = (
    "entrypoint",
    "interface",
    "artifact",
    "installer",
    "migration",
    "persisted-state",
    "documentation",
    "release-channel",
)
ALLOWED_EVIDENCE_TIERS = (
    "static",
    "unit",
    "integration",
    "entrypoint-execution",
    "browser",
    "device",
    "staging",
    "production",
    "manual-review",
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
        raise ValueError(f"Release Proof requires {label}.")
    return text


def _identifier(value: Any, label: str) -> str:
    text = _required(value, label)
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in text):
        raise ValueError(f"{label} may contain only lowercase letters, numbers, hyphens, and underscores.")
    return text


def _source(project_root: Path, forge_root: Path, raw: str | Path, label: str) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError(f"{label} must be a project-owned file outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _project_path(project_root: Path, raw: Any, label: str, *, require: bool) -> tuple[Path, str]:
    relative = normalize_rel(_required(raw, label).lstrip("/"))
    path = (project_root / relative).resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError(f"{label} must remain inside the project and outside .forge.")
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink: {relative}")
    if require and not path.is_file():
        raise ValueError(f"{label} does not exist: {relative}")
    return path, relative


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _active_release_package(project_root: Path, package_id: str) -> dict[str, Any]:
    records = release_package_records(project_root)
    record = records.get(package_id, {}) if isinstance(records, dict) else {}
    if not isinstance(record, dict) or record.get("lifecycle_status") != "active":
        raise ValueError(f"Release Proof requires an active release package record: {package_id}")
    evaluation = evaluate_release_package(project_root)
    final_package = evaluation.get("final_package", {}) if isinstance(evaluation.get("final_package"), dict) else {}
    if evaluation.get("release_package_id") != package_id or final_package.get("status") != "PASS":
        raise ValueError("Release Proof requires a current exact final-package binding before its assurance map is recorded.")
    return record


def _current_build_id(project_root: Path) -> str:
    record = project_identity_record(project_root)
    if record.get("lifecycle_status") != "active":
        return ""
    identity = record.get("identity", {}) if isinstance(record.get("identity"), dict) else {}
    return str(identity.get("build_id", "")).strip()


def _package_members(project_root: Path, package_id: str) -> tuple[set[str], dict[str, Any]]:
    evaluation = evaluate_release_package(project_root)
    final_package = evaluation.get("final_package", {}) if isinstance(evaluation.get("final_package"), dict) else {}
    if evaluation.get("release_package_id") != package_id or final_package.get("status") != "PASS":
        return set(), final_package
    artifact = project_root / str(final_package.get("artifact_path", ""))
    try:
        with zipfile.ZipFile(artifact) as archive:
            return {info.filename for info in archive.infolist() if not info.is_dir()}, final_package
    except (OSError, zipfile.BadZipFile):
        return set(), final_package


def _safe_member(value: Any, label: str) -> str:
    member = str(value or "").strip().replace("\\", "/")
    pure = PurePosixPath(member)
    if not member or pure.is_absolute() or ".." in pure.parts or member.endswith("/"):
        raise ValueError(f"{label} must be an exact safe ZIP member path.")
    return pure.as_posix()


def validate_release_proof_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    source, source_rel = _source(project_root, forge_root, source_path, "Release Proof contract")
    raw = _read_json(source, "Release Proof contract")
    if raw.get("schema") != RELEASE_PROOF_SCHEMA:
        raise ValueError("Release Proof contract must use schema 1.")
    proof_id = _identifier(raw.get("release_proof_id"), "release_proof_id")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    package_id = _identifier(raw.get("release_package_id"), "release_package_id")
    _active_release_package(project_root, package_id)
    members, _final = _package_members(project_root, package_id)

    surfaces_raw = raw.get("surfaces")
    if not isinstance(surfaces_raw, list) or not surfaces_raw:
        raise ValueError("Release Proof surfaces must be a non-empty array.")
    surfaces: list[dict[str, Any]] = []
    surface_ids: set[str] = set()
    for index, item in enumerate(surfaces_raw):
        if not isinstance(item, dict):
            raise ValueError("Each Release Proof surface must be an object.")
        surface_id = _identifier(item.get("surface_id"), f"surfaces[{index}].surface_id")
        if surface_id in surface_ids:
            raise ValueError(f"Duplicate Release Proof surface_id: {surface_id}")
        surface_ids.add(surface_id)
        kind = str(item.get("kind", "")).strip()
        if kind not in ALLOWED_SURFACE_KINDS:
            raise ValueError(f"Unsupported Release Proof surface kind: {kind}")
        description = _required(item.get("description"), f"surfaces[{surface_id}].description", minimum=12)
        members_raw = item.get("package_members")
        if not isinstance(members_raw, list) or not members_raw:
            raise ValueError(f"Release Proof surface {surface_id} requires package_members.")
        surface_members: list[str] = []
        for raw_member in members_raw:
            member = _safe_member(raw_member, f"surfaces[{surface_id}].package_members")
            if member not in members:
                raise ValueError(f"Release Proof surface {surface_id} names a member absent from the exact package: {member}")
            if member not in surface_members:
                surface_members.append(member)
        surfaces.append({
            "surface_id": surface_id,
            "kind": kind,
            "description": description,
            "package_members": surface_members,
        })

    obligations_raw = raw.get("obligations")
    if not isinstance(obligations_raw, list):
        raise ValueError("Release Proof obligations must be an array.")
    obligations: list[dict[str, Any]] = []
    obligation_ids: set[str] = set()
    obligation_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(obligations_raw):
        if not isinstance(item, dict):
            raise ValueError("Each Release Proof obligation must be an object.")
        obligation_id = _identifier(item.get("obligation_id"), f"obligations[{index}].obligation_id")
        if obligation_id in obligation_ids:
            raise ValueError(f"Duplicate Release Proof obligation_id: {obligation_id}")
        obligation_ids.add(obligation_id)
        domain_id = str(item.get("domain_id", "")).strip()
        if domain_id not in REQUIRED_DOMAINS:
            raise ValueError(f"Unsupported Release Proof domain: {domain_id}")
        description = _required(item.get("description"), f"obligations[{obligation_id}].description", minimum=12)
        listed_surfaces = item.get("surface_ids")
        if not isinstance(listed_surfaces, list) or not listed_surfaces:
            raise ValueError(f"Release Proof obligation {obligation_id} requires surface_ids.")
        normalized_surfaces: list[str] = []
        for value in listed_surfaces:
            surface_id = _identifier(value, f"obligations[{obligation_id}].surface_ids")
            if surface_id not in surface_ids:
                raise ValueError(f"Release Proof obligation {obligation_id} references unknown surface {surface_id}.")
            if surface_id not in normalized_surfaces:
                normalized_surfaces.append(surface_id)
        tiers_raw = item.get("accepted_evidence_tiers")
        if not isinstance(tiers_raw, list) or not tiers_raw:
            raise ValueError(f"Release Proof obligation {obligation_id} requires accepted_evidence_tiers.")
        tiers: list[str] = []
        for value in tiers_raw:
            tier = str(value).strip()
            if tier not in ALLOWED_EVIDENCE_TIERS:
                raise ValueError(f"Unsupported Release Proof evidence tier: {tier}")
            if tier not in tiers:
                tiers.append(tier)
        _receipt, receipt_rel = _project_path(project_root, item.get("receipt_path"), f"obligations[{obligation_id}].receipt_path", require=False)
        obligation = {
            "obligation_id": obligation_id,
            "domain_id": domain_id,
            "description": description,
            "surface_ids": normalized_surfaces,
            "accepted_evidence_tiers": tiers,
            "require_independent_reviewer": bool(item.get("require_independent_reviewer", False)),
            "receipt_path": receipt_rel,
        }
        obligations.append(obligation)
        obligation_by_id[obligation_id] = obligation

    domains_raw = raw.get("domains")
    if not isinstance(domains_raw, list):
        raise ValueError("Release Proof domains must be an array.")
    domains: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    referenced_obligations: set[str] = set()
    for index, item in enumerate(domains_raw):
        if not isinstance(item, dict):
            raise ValueError("Each Release Proof domain must be an object.")
        domain_id = str(item.get("domain_id", "")).strip()
        if domain_id not in REQUIRED_DOMAINS:
            raise ValueError(f"Unsupported Release Proof domain: {domain_id}")
        if domain_id in seen_domains:
            raise ValueError(f"Duplicate Release Proof domain: {domain_id}")
        seen_domains.add(domain_id)
        applicability = str(item.get("applicability", "")).strip()
        if applicability not in {"required", "not-applicable"}:
            raise ValueError(f"Release Proof domain {domain_id} applicability must be required or not-applicable.")
        rationale = _required(item.get("rationale"), f"domains[{domain_id}].rationale", minimum=20)
        listed = item.get("obligation_ids", [])
        if not isinstance(listed, list):
            raise ValueError(f"Release Proof domain {domain_id} obligation_ids must be an array.")
        normalized_ids: list[str] = []
        for value in listed:
            obligation_id = _identifier(value, f"domains[{domain_id}].obligation_ids")
            obligation = obligation_by_id.get(obligation_id)
            if not obligation or obligation.get("domain_id") != domain_id:
                raise ValueError(f"Release Proof domain {domain_id} references an unknown or differently scoped obligation: {obligation_id}")
            if obligation_id in referenced_obligations:
                raise ValueError(f"Release Proof obligation {obligation_id} is assigned more than once.")
            referenced_obligations.add(obligation_id)
            normalized_ids.append(obligation_id)
        if applicability == "required" and not normalized_ids:
            raise ValueError(f"Required Release Proof domain {domain_id} must name at least one obligation.")
        if applicability == "not-applicable" and normalized_ids:
            raise ValueError(f"Not-applicable Release Proof domain {domain_id} cannot name obligations.")
        domains.append({
            "domain_id": domain_id,
            "applicability": applicability,
            "rationale": rationale,
            "obligation_ids": normalized_ids,
        })
    missing_domains = [domain for domain in REQUIRED_DOMAINS if domain not in seen_domains]
    if missing_domains:
        raise ValueError(f"Release Proof must explicitly classify every required domain; missing: {', '.join(missing_domains)}")
    unassigned = sorted(obligation_ids - referenced_obligations)
    if unassigned:
        raise ValueError(f"Release Proof obligations are not assigned to domains: {', '.join(unassigned)}")
    covered_surfaces = {surface_id for obligation in obligations for surface_id in obligation["surface_ids"]}
    uncovered = sorted(surface_ids - covered_surfaces)
    if uncovered:
        raise ValueError(f"Every declared Release Proof surface must be covered by an obligation; uncovered: {', '.join(uncovered)}")

    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=80)
    contract = {
        "schema": 1,
        "release_proof_id": proof_id,
        "title": title,
        "authority": authority,
        "release_package_id": package_id,
        "surfaces": surfaces,
        "domains": domains,
        "obligations": obligations,
        "truth_boundary": truth_boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "contract_source": source_rel,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def record_release_proof(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_release_proof_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.setdefault("release_proofs", {})
    if not isinstance(records, dict):
        records = {}
        settings["release_proofs"] = records
    for identifier, existing in records.items():
        if identifier == contract["release_proof_id"] or not isinstance(existing, dict) or existing.get("status") == "retired":
            continue
        raise ValueError(f"Only one active Release Proof may be recorded at a time; retire {identifier} first.")
    record = {
        "status": "active",
        "recorded_utc": utc_now(),
        "contract": contract,
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
    }
    records[contract["release_proof_id"]] = record
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "release-proof-recorded", {
        "release_proof_id": contract["release_proof_id"],
        "release_package_id": contract["release_package_id"],
        "surface_count": len(contract["surfaces"]),
        "required_domain_count": len([item for item in contract["domains"] if item["applicability"] == "required"]),
        "not_applicable_domain_count": len([item for item in contract["domains"] if item["applicability"] == "not-applicable"]),
        "obligation_count": len(contract["obligations"]),
        "contract_source": validated["contract_source"],
        "contract_fingerprint": validated["contract_fingerprint"],
    }, source=contract["authority"])
    record["event_id"] = event["id"]
    records[contract["release_proof_id"]] = record
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_release_proof(project_root: Path, proof_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("Release Proof retirement requires a reason.")
    settings = load_settings(project_root.resolve())
    records = settings.get("release_proofs", {})
    if not isinstance(records, dict) or proof_id not in records:
        raise ValueError(f"Unknown Release Proof record: {proof_id}")
    record = dict(records[proof_id])
    record.update({"status": "retired", "retired_utc": utc_now(), "retirement_reason": reason.strip(), "retired_by": authority})
    records[proof_id] = record
    settings["release_proofs"] = records
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "release-proof-retired", {"release_proof_id": proof_id, "reason": reason.strip()}, source=authority)
    return record


def release_proof_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root.resolve()).get("release_proofs", {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for identifier, value in raw.items():
        if not isinstance(value, dict):
            continue
        result[str(identifier)] = fingerprint_bound_status(
            project_root.resolve(), value,
            changed_status="approval-required",
            missing_reason="The Release Proof contract is missing.",
            changed_reason="The Release Proof contract changed and must be recorded again.",
        )
    return result


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _receipt_evaluation(project_root: Path, contract: dict[str, Any], obligation: dict[str, Any], final_package: dict[str, Any]) -> dict[str, Any]:
    relative = str(obligation.get("receipt_path", ""))
    path = project_root / relative
    base = {
        "obligation_id": obligation.get("obligation_id", ""),
        "domain_id": obligation.get("domain_id", ""),
        "receipt_path": relative,
    }
    if not path.is_file() or path.is_symlink():
        return {**base, "status": "NOT_RUN", "reasons": ["Required Release Proof receipt is missing."]}
    try:
        raw = _read_json(path, f"Release Proof receipt {relative}")
    except ValueError as exc:
        return {**base, "status": "FAIL", "reasons": [str(exc)]}
    reasons: list[str] = []
    if raw.get("schema") != RELEASE_PROOF_RECEIPT_SCHEMA:
        reasons.append("Release Proof receipt must use schema 1.")
    for key, expected in (
        ("release_proof_id", contract.get("release_proof_id", "")),
        ("obligation_id", obligation.get("obligation_id", "")),
        ("release_package_id", contract.get("release_package_id", "")),
        ("package_sha256", final_package.get("artifact_sha256", "")),
        ("package_bytes", final_package.get("artifact_bytes", 0)),
        ("build_id", final_package.get("build_id", "")),
    ):
        if raw.get(key) != expected:
            reasons.append(f"Release Proof receipt {key} does not match the exact final package or obligation.")
    if raw.get("verdict") != "PASS":
        reasons.append("Release Proof receipt verdict must be PASS.")
    observed = _parse_utc(raw.get("observed_utc"))
    valid_until = _parse_utc(raw.get("valid_until_utc"))
    now = datetime.now(timezone.utc)
    if observed is None:
        reasons.append("Release Proof receipt observed_utc must be timezone-aware ISO 8601.")
    elif observed > now:
        reasons.append("Release Proof receipt observed_utc cannot be in the future.")
    if valid_until is None:
        reasons.append("Release Proof receipt valid_until_utc must be timezone-aware ISO 8601.")
    elif valid_until <= now:
        reasons.append("Release Proof receipt is expired.")
    elif observed is not None and valid_until <= observed:
        reasons.append("Release Proof receipt valid_until_utc must be after observed_utc.")
    tier = str(raw.get("evidence_tier", "")).strip()
    if tier not in obligation.get("accepted_evidence_tiers", []):
        reasons.append("Release Proof receipt evidence_tier is not accepted by the obligation.")
    if len(str(raw.get("method", "")).strip()) < 20:
        reasons.append("Release Proof receipt method is too brief to identify what was assessed.")
    receipt_surfaces = raw.get("surface_ids")
    if not isinstance(receipt_surfaces, list):
        reasons.append("Release Proof receipt surface_ids must be an array.")
        receipt_surfaces = []
    missing_surfaces = [item for item in obligation.get("surface_ids", []) if item not in receipt_surfaces]
    if missing_surfaces:
        reasons.append(f"Release Proof receipt omits required surface IDs: {', '.join(missing_surfaces)}")
    reviewer = raw.get("reviewer")
    if not isinstance(reviewer, dict):
        reasons.append("Release Proof receipt reviewer must be an object.")
        reviewer = {}
    if not str(reviewer.get("authority", "")).strip() or not str(reviewer.get("role", "")).strip():
        reasons.append("Release Proof receipt reviewer requires authority and role.")
    if obligation.get("require_independent_reviewer") and reviewer.get("independent") is not True:
        reasons.append("Release Proof obligation requires an independent reviewer receipt.")
    artifacts = raw.get("evidence_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        reasons.append("Release Proof receipt requires at least one evidence_artifact.")
        artifacts = []
    artifact_results: list[dict[str, Any]] = []
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            reasons.append(f"Release Proof evidence_artifacts[{index}] must be an object.")
            continue
        try:
            evidence_path, evidence_rel = _project_path(project_root, item.get("path"), f"evidence_artifacts[{index}].path", require=True)
        except ValueError as exc:
            reasons.append(str(exc))
            continue
        actual_sha = sha256_file(evidence_path)
        actual_bytes = evidence_path.stat().st_size
        expected_sha = str(item.get("sha256", "")).strip().lower()
        expected_bytes = item.get("bytes")
        artifact_reasons: list[str] = []
        if actual_sha != expected_sha:
            artifact_reasons.append("sha256 mismatch")
        if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or actual_bytes != expected_bytes:
            artifact_reasons.append("byte-length mismatch")
        if artifact_reasons:
            reasons.append(f"Release Proof evidence artifact {evidence_rel}: {', '.join(artifact_reasons)}.")
        artifact_results.append({"path": evidence_rel, "sha256": actual_sha, "bytes": actual_bytes, "status": "PASS" if not artifact_reasons else "FAIL"})
    if len(str(raw.get("truth_boundary", "")).strip()) < 40:
        reasons.append("Release Proof receipt requires a bounded truth_boundary.")
    return {
        **base,
        "status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "evidence_tier": tier,
        "reviewer_independent": reviewer.get("independent") is True,
        "evidence_artifacts": artifact_results,
        "limitations": [str(item) for item in raw.get("limitations", [])[:20]] if isinstance(raw.get("limitations"), list) else [],
    }


def evaluate_release_proof(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    active = [record for record in release_proof_records(project_root).values() if record.get("status") != "retired"]
    if not active:
        return {
            "schema": 1,
            "status": "NOT_RUN",
            "surface_count": 0,
            "obligation_count": 0,
            "passed_obligations": 0,
            "required_domains": [],
            "not_applicable_domains": [],
            "reason": "No active bounded Release Proof contract is recorded.",
            "truth_boundary": "Release Proof has not been configured.",
        }
    record = active[0]
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    proof_id = str(contract.get("release_proof_id", "release-proof"))
    if record.get("lifecycle_status") != "active":
        return {
            "schema": 1,
            "status": "FAIL",
            "release_proof_id": proof_id,
            "surface_count": len(contract.get("surfaces", [])),
            "obligation_count": len(contract.get("obligations", [])),
            "passed_obligations": 0,
            "required_domains": [],
            "not_applicable_domains": [],
            "reason": str(record.get("reason", "Release Proof authority is not current.")),
            "truth_boundary": str(contract.get("truth_boundary", "Release Proof authority is not current.")),
        }
    package_eval = evaluate_release_package(project_root)
    final_package = package_eval.get("final_package", {}) if isinstance(package_eval.get("final_package"), dict) else {}
    package_id = str(contract.get("release_package_id", ""))
    package_current = package_eval.get("release_package_id") == package_id and final_package.get("status") == "PASS"
    members, _ = _package_members(project_root, package_id) if package_current else (set(), final_package)
    surface_results: list[dict[str, Any]] = []
    for surface in contract.get("surfaces", []):
        if not isinstance(surface, dict):
            continue
        missing = [member for member in surface.get("package_members", []) if member not in members]
        surface_results.append({
            "surface_id": surface.get("surface_id", ""),
            "status": "PASS" if package_current and not missing else "FAIL" if package_current else "NOT_RUN",
            "missing_members": missing,
        })
    receipts = [
        _receipt_evaluation(project_root, contract, obligation, final_package)
        for obligation in contract.get("obligations", []) if isinstance(obligation, dict)
    ] if package_current else []
    passed = [item for item in receipts if item.get("status") == "PASS"]
    missing = [item for item in receipts if item.get("status") == "NOT_RUN"]
    failed = [item for item in receipts if item.get("status") == "FAIL"]
    required_domains = [item.get("domain_id") for item in contract.get("domains", []) if isinstance(item, dict) and item.get("applicability") == "required"]
    not_applicable = [item.get("domain_id") for item in contract.get("domains", []) if isinstance(item, dict) and item.get("applicability") == "not-applicable"]
    if not package_current:
        status = "NOT_RUN" if final_package.get("status") == "NOT_RUN" else "FAIL"
        reason = "The exact final package must be current before Release Proof receipts can be assessed."
    elif any(item.get("status") == "FAIL" for item in surface_results) or failed:
        status = "FAIL"
        reason = "One or more declared release surfaces or package-bound assurance receipts are contradicted, stale, expired, or invalid."
    elif missing:
        status = "PARTIAL"
        reason = "One or more required package-bound Release Proof receipts have not been supplied."
    elif receipts and len(passed) == len(receipts):
        status = "PASS"
        reason = "Every declared release surface is present and every required assurance obligation has a current exact-package receipt."
    else:
        status = "PARTIAL"
        reason = "Release Proof is configured but has no complete required assurance receipt set."
    return {
        "schema": 1,
        "status": status,
        "release_proof_id": proof_id,
        "release_package_id": package_id,
        "surface_count": len(surface_results),
        "surfaces": surface_results,
        "required_domains": required_domains,
        "not_applicable_domains": not_applicable,
        "obligation_count": len(contract.get("obligations", [])),
        "passed_obligations": len(passed),
        "missing_obligations": [item.get("obligation_id", "") for item in missing],
        "failed_obligations": [item.get("obligation_id", "") for item in failed],
        "receipts": receipts,
        "reason": reason,
        "truth_boundary": str(contract.get("truth_boundary", "Release Proof remains bounded to declared surfaces, domains, receipts, package bytes, and evidence artifacts.")),
    }


def release_proof_summary(project_root: Path) -> dict[str, Any]:
    evaluation = evaluate_release_proof(project_root)
    return {
        "schema": 1,
        "status": evaluation.get("status", "NOT_RUN"),
        "surface_count": evaluation.get("surface_count", 0),
        "domain_ratio": f"{len(evaluation.get('required_domains', [])) + len(evaluation.get('not_applicable_domains', []))}/{len(REQUIRED_DOMAINS)}",
        "obligation_ratio": f"{evaluation.get('passed_obligations', 0)}/{evaluation.get('obligation_count', 0)}",
        "truth_boundary": "Compact Release Proof status only; detailed receipts, evidence artifacts, limitations, and exclusions remain local.",
    }

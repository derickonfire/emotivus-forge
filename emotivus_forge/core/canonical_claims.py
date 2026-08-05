from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .project_identity import project_identity_record
from .provenance import provenance_records
from .state import load_settings

CLAIMS_SCHEMA = 1
CLAIM_KINDS = {"identity-text", "archive-membership", "migration-effects", "evidence-identity"}
DDL = re.compile(r"\b(?:CREATE|ALTER|DROP|TRUNCATE|RENAME)\s+(?:TABLE|DATABASE|SCHEMA|INDEX|VIEW|TRIGGER|PROCEDURE|FUNCTION)\b", re.IGNORECASE)
DML = re.compile(r"\b(?:INSERT\s+INTO|UPDATE\s+[A-Za-z_`]|DELETE\s+FROM|REPLACE\s+INTO)\b", re.IGNORECASE)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Canonical claim contract requires {label}.")
    return text


def _safe_source(project_root: Path, forge_root: Path, raw: str | Path) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError("Canonical claim contracts must be project-owned files outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Canonical claim contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _safe_relative(project_root: Path, raw: Any, label: str) -> str:
    relative = normalize_rel(_required(raw, label).lstrip("/"))
    target = (project_root / relative).resolve()
    if relative in {"", "."} or relative.startswith("../") or not _inside(target, project_root) or _inside(target, project_root / ".forge"):
        raise ValueError(f"{label} must remain inside the project and outside .forge.")
    return relative


def _identity_lookup(project_root: Path, field: str) -> tuple[bool, str]:
    record = project_identity_record(project_root)
    if record.get("lifecycle_status") != "active":
        return False, ""
    current: Any = record.get("identity", {})
    for part in field.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, ""
    if current is None:
        return False, ""
    if isinstance(current, (dict, list)):
        return True, json.dumps(current, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return True, str(current)


def validate_canonical_claims_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _safe_source(project_root, forge_root, source_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Canonical claim contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != CLAIMS_SCHEMA:
        raise ValueError("Canonical claim contract must be an object using schema 1.")
    claim_set_id = _required(raw.get("claim_set_id"), "claim_set_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in claim_set_id):
        raise ValueError("claim_set_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    claims_raw = raw.get("claims")
    if not isinstance(claims_raw, list) or not claims_raw:
        raise ValueError("Canonical claim contract requires a non-empty claims array.")
    claims: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(claims_raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"claims[{index}] must be an object.")
        claim_id = _required(item.get("id"), f"claims[{index}].id")
        if claim_id in ids:
            raise ValueError(f"Duplicate canonical claim id: {claim_id}")
        ids.add(claim_id)
        kind = _required(item.get("kind"), f"claims[{index}].kind")
        if kind not in CLAIM_KINDS:
            raise ValueError(f"Unsupported canonical claim kind: {kind}")
        source = _safe_relative(project_root, item.get("source_path"), f"claims[{index}].source_path")
        claim_text = _required(item.get("claim_text"), f"claims[{index}].claim_text")
        row: dict[str, Any] = {"id": claim_id, "kind": kind, "source_path": source, "claim_text": claim_text}
        if kind in {"identity-text", "evidence-identity"}:
            row["identity_field"] = _required(item.get("identity_field"), f"claims[{index}].identity_field")
            row["text_template"] = _required(item.get("text_template", "{value}"), f"claims[{index}].text_template")
            if "{value}" not in row["text_template"]:
                raise ValueError(f"claims[{index}].text_template must contain {{value}}.")
        elif kind == "archive-membership":
            row["provenance_id"] = _required(item.get("provenance_id"), f"claims[{index}].provenance_id")
            row["member"] = normalize_rel(_required(item.get("member"), f"claims[{index}].member").lstrip("/"))
            expectation = str(item.get("expect", "present")).strip()
            if expectation not in {"present", "absent"}:
                raise ValueError(f"claims[{index}].expect must be present or absent.")
            row["expect"] = expectation
        elif kind == "migration-effects":
            row["migration_path"] = _safe_relative(project_root, item.get("migration_path"), f"claims[{index}].migration_path")
            expectation = str(item.get("expect", "ddl-present")).strip()
            if expectation not in {"ddl-present", "ddl-none", "dml-present", "dml-none"}:
                raise ValueError(f"claims[{index}].expect must be ddl-present, ddl-none, dml-present, or dml-none.")
            row["expect"] = expectation
        claims.append(row)
    verification_boundary = _required(raw.get("verification_boundary"), "verification_boundary", minimum=30)
    contract = {"schema": CLAIMS_SCHEMA, "claim_set_id": claim_set_id, "title": title, "authority": authority, "claims": claims, "verification_boundary": verification_boundary}
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"contract": contract, "source": relative, "contract_fingerprint": hashlib.sha256(canonical).hexdigest(), "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest()}


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(project_root, record, changed_status="approval-required", missing_reason="The project-owned canonical-claim source is missing.", changed_reason="The project-owned canonical-claim source changed after authority approval.")


def canonical_claim_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("canonical_claims", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_canonical_claims(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_canonical_claims_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.get("canonical_claims", {})
    if not isinstance(records, dict):
        records = {}
    record = {"status": "active", "lifecycle_status": "active", "claim_set_id": contract["claim_set_id"], "recorded_utc": utc_now(), "contract_source": validated["source"], "contract_fingerprint": validated["contract_fingerprint"], "source_fingerprint": validated["source_fingerprint"], "contract": contract}
    records[contract["claim_set_id"]] = record
    settings["canonical_claims"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "canonical-claims-recorded", {"claim_set_id": contract["claim_set_id"], "title": contract["title"], "authority": contract["authority"], "claim_count": len(contract["claims"]), "verification_boundary": contract["verification_boundary"]}, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_canonical_claims(project_root: Path, claim_set_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("canonical_claims", {})
    if not isinstance(records, dict) or claim_set_id not in records or not isinstance(records[claim_set_id], dict):
        raise ValueError(f"Canonical claim set is not recorded: {claim_set_id}")
    record = dict(records[claim_set_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[claim_set_id] = record
    settings["canonical_claims"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "canonical-claims-retired", {"claim_set_id": claim_set_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _read_text(path: Path) -> tuple[str, str]:
    try:
        if not path.is_file() or path.is_symlink():
            return "", "source is missing or is not a regular file"
        return path.read_text(encoding="utf-8"), ""
    except (OSError, UnicodeDecodeError):
        return "", "source is not readable UTF-8 text"


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s*(?://|#|--).*?$", " ", text)
    text = re.sub(r"(?m)(?<!:)//.*?$", " ", text)
    return text


def _evaluate_claim(project_root: Path, claim: dict[str, Any], provenance: dict[str, dict[str, Any]]) -> tuple[bool, str, dict[str, Any]]:
    source_path = project_root / str(claim.get("source_path", ""))
    source_text, source_error = _read_text(source_path)
    if source_error:
        return False, source_error, {}
    claim_text = str(claim.get("claim_text", ""))
    if claim_text not in source_text:
        return False, "declared canonical claim text is absent from its source", {}
    kind = str(claim.get("kind", ""))
    if kind in {"identity-text", "evidence-identity"}:
        found, value = _identity_lookup(project_root, str(claim.get("identity_field", "")))
        if not found or not value:
            return False, "current owner-declared identity field is unavailable", {}
        expected = str(claim.get("text_template", "{value}")).replace("{value}", value)
        return expected in source_text, f"canonical source does not contain current identity text {expected!r}", {"expected_text": expected}
    if kind == "archive-membership":
        provenance_id = str(claim.get("provenance_id", ""))
        record = provenance.get(provenance_id, {}) if isinstance(provenance.get(provenance_id), dict) else {}
        if not record:
            return False, "referenced artifact provenance is not recorded", {}
        if record.get("lifecycle_status") != "active":
            return False, "referenced artifact provenance is not current", {}
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        artifact = project_root / str(contract.get("artifact_path", ""))
        try:
            with zipfile.ZipFile(artifact) as archive:
                members = {normalize_rel(info.filename).lstrip("/") for info in archive.infolist() if not info.is_dir()}
        except (OSError, zipfile.BadZipFile):
            return False, "referenced artifact is not a readable ZIP archive", {}
        member = str(claim.get("member", ""))
        present = member in members
        expected_present = str(claim.get("expect", "present")) == "present"
        return present == expected_present, f"archive member {member!r} is {'present' if present else 'absent'}, contradicting the canonical claim", {"member": member, "observed_present": present}
    if kind == "migration-effects":
        migration = project_root / str(claim.get("migration_path", ""))
        migration_text, migration_error = _read_text(migration)
        if migration_error:
            return False, migration_error, {}
        stripped = _strip_comments(migration_text)
        has_ddl = bool(DDL.search(stripped))
        has_dml = bool(DML.search(stripped))
        expectation = str(claim.get("expect", "ddl-present"))
        observed = {"ddl-present": has_ddl, "ddl-none": not has_ddl, "dml-present": has_dml, "dml-none": not has_dml}[expectation]
        return observed, f"migration effect is ddl={has_ddl}, dml={has_dml}, contradicting expected {expectation}", {"has_ddl": has_ddl, "has_dml": has_dml}
    return False, "unsupported canonical claim kind", {}


def evaluate_canonical_claims(project_root: Path) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    active_count = 0
    claim_count = 0
    provenance = provenance_records(project_root)
    for claim_set_id, record in sorted(canonical_claim_records(project_root).items()):
        if record.get("status") == "retired":
            continue
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        source = str(record.get("contract_source", ""))
        if record.get("lifecycle_status") != "active":
            evaluations.append({"claim_set_id": claim_set_id, "title": contract.get("title", claim_set_id), "status": "APPROVAL_REQUIRED", "reason": record.get("reason", "Authority approval is not current."), "contract_source": source, "claims": []})
            findings.append({"check": "core.canonical-claims", "severity": "blocker", "path": source or ".", "line": 0, "message": f"Canonical claim set {claim_set_id} is not current: {record.get('reason', 'authority approval required')}"})
            continue
        active_count += 1
        rows: list[dict[str, Any]] = []
        failed = False
        for claim in contract.get("claims", []):
            if not isinstance(claim, dict):
                continue
            claim_count += 1
            passed, reason, evidence = _evaluate_claim(project_root, claim, provenance)
            rows.append({"id": claim.get("id", ""), "kind": claim.get("kind", ""), "source_path": claim.get("source_path", ""), "status": "PASS" if passed else "FAIL", "reason": "" if passed else reason, "evidence": evidence})
            if not passed:
                failed = True
                findings.append({"check": "core.canonical-claims", "severity": "blocker", "path": claim.get("source_path", source or "."), "line": 0, "message": f"Canonical claim {claim_set_id}/{claim.get('id', 'claim')} failed: {reason}."})
        evaluations.append({"claim_set_id": claim_set_id, "title": contract.get("title", claim_set_id), "status": "FAIL" if failed else "PASS", "contract_source": source, "claims": rows, "verification_boundary": contract.get("verification_boundary", "")})
    return {"schema": 1, "status": "FAIL" if findings else "PASS", "active_count": active_count, "claim_count": claim_count, "evaluations": evaluations, "findings": findings, "truth_boundary": "Canonical claims evaluate explicit authority-recorded statements against current identity, registered ZIP membership, migration effects, or evidence identity. Forge does not infer arbitrary prose meaning or prove the broader release correct."}


def canonical_claims_summary(project_root: Path) -> dict[str, Any]:
    active = 0
    attention = 0
    retired = 0
    claims = 0
    for record in canonical_claim_records(project_root).values():
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        if record.get("status") == "retired":
            retired += 1
        elif record.get("lifecycle_status") == "active":
            active += 1
            claims += len(contract.get("claims", [])) if isinstance(contract.get("claims"), list) else 0
        else:
            attention += 1
    return {"schema": 1, "active": active, "attention": attention, "retired": retired, "claims": claims, "truth_boundary": "The summary reports authority and source currency only; Check evaluates each explicit claim."}

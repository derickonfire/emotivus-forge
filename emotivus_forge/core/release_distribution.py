from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .project_identity import project_identity_record
from .release_package import evaluate_release_package, release_package_records
from .remote_release import validate_remote_verification, verify_remote_channels
from .state import load_settings

DISTRIBUTION_SCHEMA = 1
PUBLIC_KEY_SCHEMA = 1
CHANNEL_MANIFEST_SCHEMA = 1
CHANNEL_RECEIPT_SCHEMA = 1
ALGORITHM = "rsa-pkcs1v15-sha256"
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Release distribution requires {label}.")
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


def _relative_file(project_root: Path, forge_root: Path, raw: Any, label: str) -> str:
    _, relative = _source(project_root, forge_root, _required(raw, label), label)
    return relative


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _current_build_id(project_root: Path) -> str:
    record = project_identity_record(project_root)
    if record.get("lifecycle_status") != "active":
        return ""
    identity = record.get("identity", {}) if isinstance(record.get("identity"), dict) else {}
    return str(identity.get("build_id", "")).strip()


def _active_release_package(project_root: Path, package_id: str) -> dict[str, Any]:
    records = release_package_records(project_root)
    record = records.get(package_id, {}) if isinstance(records, dict) else {}
    if not isinstance(record, dict) or record.get("lifecycle_status") != "active":
        raise ValueError(f"Release distribution requires an active release package record: {package_id}")
    return record


def _validate_public_key(path: Path) -> dict[str, Any]:
    raw = _read_json(path, "RSA public key")
    if raw.get("schema") != PUBLIC_KEY_SCHEMA or raw.get("algorithm") != ALGORITHM:
        raise ValueError("RSA public key must use schema 1 and rsa-pkcs1v15-sha256.")
    key_id = _identifier(raw.get("key_id"), "public key key_id")
    modulus_hex = _required(raw.get("modulus_hex"), "public key modulus_hex", minimum=512).lower()
    try:
        modulus = int(modulus_hex, 16)
    except ValueError as exc:
        raise ValueError("public key modulus_hex must be hexadecimal.") from exc
    exponent = raw.get("public_exponent", 65537)
    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 3 or exponent % 2 == 0:
        raise ValueError("public key public_exponent must be an odd integer of at least 3.")
    if modulus.bit_length() < 2048:
        raise ValueError("RSA public key modulus must be at least 2048 bits.")
    canonical = json.dumps({
        "schema": 1,
        "algorithm": ALGORITHM,
        "key_id": key_id,
        "modulus_hex": modulus_hex,
        "public_exponent": exponent,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "key_id": key_id,
        "modulus": modulus,
        "public_exponent": exponent,
        "fingerprint": hashlib.sha256(canonical).hexdigest(),
    }


def _read_signature(path: Path) -> bytes:
    try:
        text = "".join(path.read_text(encoding="ascii").split())
        signature = base64.b64decode(text, validate=True)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Detached signature must be base64 text: {path}") from exc
    if not signature:
        raise ValueError(f"Detached signature is empty: {path}")
    return signature


def read_rsa_public_key(path: Path) -> dict[str, Any]:
    """Read and validate a public verification key; private key material is unsupported."""
    return _validate_public_key(path)


def read_detached_signature(path: Path) -> bytes:
    """Read one base64 detached signature without retaining secret material."""
    return _read_signature(path)


def verify_rsa_pkcs1v15_sha256(subject: bytes, signature: bytes, modulus: int, exponent: int) -> bool:
    size = (modulus.bit_length() + 7) // 8
    if size < 256 or len(signature) != size:
        return False
    signature_int = int.from_bytes(signature, "big")
    if signature_int <= 0 or signature_int >= modulus:
        return False
    encoded = pow(signature_int, exponent, modulus).to_bytes(size, "big")
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(subject).digest()
    padding_length = size - len(digest_info) - 3
    if padding_length < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def _signature_contract(project_root: Path, forge_root: Path, value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    algorithm = str(value.get("algorithm", "")).strip()
    if algorithm != ALGORITHM:
        raise ValueError(f"{label}.algorithm must be {ALGORITHM}.")
    return {
        "algorithm": algorithm,
        "public_key_path": _relative_file(project_root, forge_root, value.get("public_key_path"), f"{label}.public_key_path"),
        "signature_path": _relative_file(project_root, forge_root, value.get("signature_path"), f"{label}.signature_path"),
    }


def validate_release_distribution(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    source, relative = _source(project_root, forge_root, source_path, "Release distribution contract")
    raw = _read_json(source, "Release distribution contract")
    if raw.get("schema") != DISTRIBUTION_SCHEMA:
        raise ValueError("Release distribution contract must use schema 1.")
    distribution_id = _identifier(raw.get("distribution_id"), "distribution_id")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    release_package_id = _identifier(raw.get("release_package_id"), "release_package_id")
    _active_release_package(project_root, release_package_id)
    artifact_signature = _signature_contract(project_root, forge_root, raw.get("artifact_signature"), "artifact_signature")
    channel_manifest_path = _relative_file(project_root, forge_root, raw.get("channel_manifest_path"), "channel_manifest_path")
    manifest_signature = _signature_contract(project_root, forge_root, raw.get("channel_manifest_signature"), "channel_manifest_signature")
    channels_raw = raw.get("required_channels")
    if not isinstance(channels_raw, list) or not channels_raw:
        raise ValueError("required_channels must be a non-empty array.")
    required_channels: list[str] = []
    for item in channels_raw:
        channel_id = _identifier(item, "required channel id")
        if channel_id not in required_channels:
            required_channels.append(channel_id)
    receipts_raw = raw.get("channel_receipts")
    if not isinstance(receipts_raw, list) or not receipts_raw:
        raise ValueError("channel_receipts must be a non-empty array.")
    channel_receipts = [
        _relative_file(project_root, forge_root, item, "channel receipt")
        for item in receipts_raw
    ]
    remote_verification = None
    if raw.get("remote_verification") is not None:
        remote_verification = validate_remote_verification(raw.get("remote_verification"))
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=60)
    contract = {
        "schema": 1,
        "distribution_id": distribution_id,
        "title": title,
        "authority": authority,
        "release_package_id": release_package_id,
        "artifact_signature": artifact_signature,
        "channel_manifest_path": channel_manifest_path,
        "channel_manifest_signature": manifest_signature,
        "required_channels": required_channels,
        "channel_receipts": channel_receipts,
        "remote_verification": remote_verification,
        "truth_boundary": truth_boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(
        project_root,
        record,
        changed_status="approval-required",
        missing_reason="The project-owned release distribution contract is missing.",
        changed_reason="The project-owned release distribution contract changed after authority approval.",
    )


def release_distribution_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("release_distributions", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_release_distribution(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_release_distribution(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.get("release_distributions", {})
    if not isinstance(records, dict):
        records = {}
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "distribution_id": contract["distribution_id"],
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[contract["distribution_id"]] = record
    settings["release_distributions"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "release-distribution-recorded", {
        "distribution_id": contract["distribution_id"],
        "release_package_id": contract["release_package_id"],
        "required_channels": contract["required_channels"],
        "signature_algorithm": ALGORITHM,
        "truth_boundary": contract["truth_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_release_distribution(project_root: Path, distribution_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("release_distributions", {})
    if not isinstance(records, dict) or distribution_id not in records or not isinstance(records[distribution_id], dict):
        raise ValueError(f"Release distribution is not recorded: {distribution_id}")
    record = dict(records[distribution_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[distribution_id] = record
    settings["release_distributions"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "release-distribution-retired", {"distribution_id": distribution_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _verify_signature(project_root: Path, subject: Path, signature_spec: dict[str, Any]) -> dict[str, Any]:
    if not subject.is_file() or subject.is_symlink():
        return {"status": "NOT_RUN", "reason": f"Signed subject is missing: {normalize_rel(subject.relative_to(project_root)) if _inside(subject, project_root) else subject.name}"}
    key_path = project_root / str(signature_spec.get("public_key_path", ""))
    signature_path = project_root / str(signature_spec.get("signature_path", ""))
    try:
        key = _validate_public_key(key_path)
        signature = _read_signature(signature_path)
    except ValueError as exc:
        return {"status": "FAIL", "reason": str(exc)}
    verified = verify_rsa_pkcs1v15_sha256(subject.read_bytes(), signature, key["modulus"], key["public_exponent"])
    return {
        "status": "PASS" if verified else "FAIL",
        "reason": "Detached RSA signature verifies against the exact current bytes." if verified else "Detached RSA signature does not verify against the exact current bytes.",
        "algorithm": ALGORITHM,
        "key_id": key["key_id"],
        "public_key_fingerprint": key["fingerprint"],
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
        "subject_sha256": sha256_file(subject),
    }


def _channel_receipt(project_root: Path, relative: str, *, distribution_id: str, release_package_id: str, build_id: str, artifact_sha: str, manifest_sha: str, manifest_channels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    path = project_root / relative
    try:
        raw = _read_json(path, "Channel receipt")
    except ValueError as exc:
        return {"status": "FAIL", "path": relative, "reason": str(exc)}
    reasons: list[str] = []
    if raw.get("schema") != CHANNEL_RECEIPT_SCHEMA:
        reasons.append("Channel receipt must use schema 1.")
    channel_id = str(raw.get("channel_id", "")).strip()
    if str(raw.get("distribution_id", "")) != distribution_id:
        reasons.append("Channel receipt distribution_id does not match.")
    if str(raw.get("release_package_id", "")) != release_package_id:
        reasons.append("Channel receipt release_package_id does not match.")
    if str(raw.get("build_id", "")) != build_id:
        reasons.append("Channel receipt build_id does not match the current identity.")
    if str(raw.get("artifact_sha256", "")) != artifact_sha:
        reasons.append("Channel receipt artifact digest does not match the exact package.")
    if str(raw.get("manifest_sha256", "")) != manifest_sha:
        reasons.append("Channel receipt manifest digest does not match.")
    if str(raw.get("status", "")) != "published":
        reasons.append("Channel receipt status must be published.")
    uri = str(raw.get("published_uri", "")).strip()
    if not uri.startswith("https://"):
        reasons.append("Channel receipt published_uri must use https://.")
    manifest_row = manifest_channels.get(channel_id, {})
    if not manifest_row:
        reasons.append("Channel receipt is not declared by the signed channel manifest.")
    elif str(manifest_row.get("artifact_sha256", "")) != artifact_sha or str(manifest_row.get("artifact_uri", "")) != uri:
        reasons.append("Channel receipt does not match the signed channel manifest.")
    evidence_rel = str(raw.get("evidence_path", "")).strip()
    evidence_sha = str(raw.get("evidence_sha256", "")).strip()
    evidence = project_root / evidence_rel if evidence_rel else Path()
    if not evidence_rel or not _inside(evidence, project_root) or _inside(evidence, project_root / ".forge") or not evidence.is_file() or evidence.is_symlink():
        reasons.append("Channel receipt evidence_path is missing or unsafe.")
    elif sha256_file(evidence) != evidence_sha:
        reasons.append("Channel receipt evidence digest is stale or incorrect.")
    return {
        "status": "PASS" if not reasons else "FAIL",
        "path": relative,
        "channel_id": channel_id,
        "published_uri": uri,
        "source": str(raw.get("source", "")),
        "verification_tier": str(raw.get("verification_tier", "")),
        "reason": "Project-owned publication receipt matches the signed manifest and exact package." if not reasons else " ".join(reasons),
    }


def evaluate_release_distribution(project_root: Path, *, perform_remote: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    records = release_distribution_records(project_root)
    active = [row for row in records.values() if row.get("lifecycle_status") == "active"]
    if not active:
        return {
            "schema": 1,
            "status": "NOT_RUN",
            "signatures": {"status": "NOT_RUN"},
            "channels": {"status": "NOT_RUN", "required": [], "passed": [], "receipts": []},
            "truth_boundary": "No release distribution contract is active.",
        }
    record = active[0]
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    if record.get("lifecycle_status") != "active" or record.get("status") != "active":
        return {
            "schema": 1,
            "status": "FAIL",
            "distribution_id": contract.get("distribution_id", ""),
            "signatures": {"status": "FAIL", "reason": str(record.get("reason", "Release distribution authority is not current."))},
            "channels": {"status": "NOT_RUN", "required": contract.get("required_channels", []), "passed": [], "receipts": []},
            "truth_boundary": str(contract.get("truth_boundary", "Release distribution authority is not current.")),
        }
    package_eval = evaluate_release_package(project_root)
    final_package = package_eval.get("final_package", {}) if isinstance(package_eval.get("final_package"), dict) else {}
    if final_package.get("status") != "PASS" or str(package_eval.get("release_package_id", "")) != str(contract.get("release_package_id", "")):
        return {
            "schema": 1,
            "status": "NOT_RUN",
            "distribution_id": contract.get("distribution_id", ""),
            "signatures": {"status": "NOT_RUN", "reason": "The exact final-package claim must pass before signatures are assessed."},
            "channels": {"status": "NOT_RUN", "required": contract.get("required_channels", []), "passed": [], "receipts": []},
            "truth_boundary": str(contract.get("truth_boundary", "Release distribution remains bounded.")),
        }
    artifact_path = project_root / str(final_package.get("artifact_path", ""))
    manifest_path = project_root / str(contract.get("channel_manifest_path", ""))
    artifact_signature = _verify_signature(project_root, artifact_path, contract.get("artifact_signature", {}))
    manifest_signature = _verify_signature(project_root, manifest_path, contract.get("channel_manifest_signature", {}))
    signature_status = "PASS" if artifact_signature.get("status") == manifest_signature.get("status") == "PASS" else "FAIL"
    signatures = {
        "status": signature_status,
        "artifact": artifact_signature,
        "channel_manifest": manifest_signature,
        "truth_boundary": "Forge verifies detached RSA signatures against exact local bytes and project-owned public keys. Forge never accesses or stores private signing keys.",
    }
    if signature_status != "PASS":
        return {
            "schema": 1,
            "status": "FAIL",
            "distribution_id": contract.get("distribution_id", ""),
            "signatures": signatures,
            "channels": {"status": "NOT_RUN", "required": contract.get("required_channels", []), "passed": [], "receipts": []},
            "truth_boundary": str(contract.get("truth_boundary", "Release distribution remains bounded.")),
        }
    try:
        manifest = _read_json(manifest_path, "Signed channel manifest")
    except ValueError as exc:
        return {
            "schema": 1,
            "status": "FAIL",
            "distribution_id": contract.get("distribution_id", ""),
            "signatures": signatures,
            "channels": {"status": "FAIL", "required": contract.get("required_channels", []), "passed": [], "receipts": [], "reason": str(exc)},
            "truth_boundary": str(contract.get("truth_boundary", "Release distribution remains bounded.")),
        }
    reasons: list[str] = []
    build_id = _current_build_id(project_root)
    artifact_sha = str(final_package.get("artifact_sha256", ""))
    artifact_signature_path = project_root / str(contract.get("artifact_signature", {}).get("signature_path", ""))
    if manifest.get("schema") != CHANNEL_MANIFEST_SCHEMA:
        reasons.append("Signed channel manifest must use schema 1.")
    if str(manifest.get("distribution_id", "")) != str(contract.get("distribution_id", "")):
        reasons.append("Signed channel manifest distribution_id does not match.")
    if str(manifest.get("release_package_id", "")) != str(contract.get("release_package_id", "")):
        reasons.append("Signed channel manifest release_package_id does not match.")
    if str(manifest.get("build_id", "")) != build_id:
        reasons.append("Signed channel manifest build_id does not match current identity.")
    if str(manifest.get("artifact_sha256", "")) != artifact_sha:
        reasons.append("Signed channel manifest artifact digest does not match the exact package.")
    if str(manifest.get("signature_sha256", "")) != sha256_file(artifact_signature_path):
        reasons.append("Signed channel manifest signature digest does not match the detached artifact signature file.")
    channels_raw = manifest.get("channels")
    if not isinstance(channels_raw, list):
        reasons.append("Signed channel manifest channels must be an array.")
        channels_raw = []
    manifest_channels = {
        str(row.get("channel_id", "")): row
        for row in channels_raw
        if isinstance(row, dict) and str(row.get("channel_id", "")).strip()
    }
    manifest_sha = sha256_file(manifest_path)
    receipts = [
        _channel_receipt(
            project_root,
            relative,
            distribution_id=str(contract.get("distribution_id", "")),
            release_package_id=str(contract.get("release_package_id", "")),
            build_id=build_id,
            artifact_sha=artifact_sha,
            manifest_sha=manifest_sha,
            manifest_channels=manifest_channels,
        )
        for relative in contract.get("channel_receipts", [])
    ]
    by_id = {str(row.get("channel_id", "")): row for row in receipts if isinstance(row, dict)}
    required = [str(item) for item in contract.get("required_channels", [])]
    missing = [channel_id for channel_id in required if channel_id not in by_id]
    failed = [channel_id for channel_id in required if channel_id in by_id and by_id[channel_id].get("status") != "PASS"]
    passed = [channel_id for channel_id in required if channel_id in by_id and by_id[channel_id].get("status") == "PASS"]
    if reasons or failed:
        channel_status = "FAIL"
    elif missing:
        channel_status = "PARTIAL"
    else:
        channel_status = "PASS"
    channels = {
        "status": channel_status,
        "required": required,
        "passed": passed,
        "missing": missing,
        "failed": failed,
        "receipts": receipts,
        "manifest_sha256": manifest_sha,
        "reasons": reasons,
        "truth_boundary": "A passing channel result proves that signed local distribution metadata and project-owned publication receipts agree with the exact package. It does not independently prove remote availability, CDN integrity, or future channel contents.",
    }
    remote_contract = contract.get("remote_verification") if isinstance(contract.get("remote_verification"), dict) else None
    if channel_status != "PASS":
        remote_channels = {
            "status": "NOT_RUN",
            "configured": bool(remote_contract),
            "attempted": False,
            "required": required,
            "passed": [],
            "failed": [],
            "blocked": [],
            "evaluations": [],
            "reason": "Signed local channel binding must pass before remote retrieval is attempted.",
            "truth_boundary": str((remote_contract or {}).get("truth_boundary", "Remote verification is not configured.")),
        }
    elif not remote_contract:
        remote_channels = {
            "status": "NOT_RUN",
            "configured": False,
            "attempted": False,
            "required": required,
            "passed": [],
            "failed": [],
            "blocked": [],
            "evaluations": [],
            "reason": "No authority-approved remote release verification contract is recorded.",
            "truth_boundary": "Local signed metadata and publication receipts do not independently prove remote artifact availability.",
        }
    elif not perform_remote:
        remote_channels = {
            "status": "NOT_RUN",
            "configured": True,
            "attempted": False,
            "required": required,
            "passed": [],
            "failed": [],
            "blocked": [],
            "evaluations": [],
            "reason": "Live remote retrieval is intentionally deferred to an explicit Ship assessment.",
            "truth_boundary": str(remote_contract.get("truth_boundary", "Remote verification remains bounded.")),
        }
    else:
        remote_channels = verify_remote_channels(
            manifest_channels,
            required,
            expected_sha256=artifact_sha,
            expected_bytes=int(final_package.get("artifact_bytes", 0)),
            contract=remote_contract,
        )
    local_status = "PASS" if signature_status == channel_status == "PASS" else "FAIL" if "FAIL" in {signature_status, channel_status} else "PARTIAL"
    if perform_remote and remote_contract and remote_channels.get("status") in {"FAIL", "BLOCKED"}:
        overall = "FAIL"
    else:
        overall = local_status
    return {
        "schema": 1,
        "status": overall,
        "distribution_id": contract.get("distribution_id", ""),
        "release_package_id": contract.get("release_package_id", ""),
        "signatures": signatures,
        "channels": channels,
        "remote_channels": remote_channels,
        "truth_boundary": str(contract.get("truth_boundary", "Release distribution remains bounded.")),
    }


def release_distribution_summary(project_root: Path) -> dict[str, Any]:
    evaluation = evaluate_release_distribution(project_root)
    signatures = evaluation.get("signatures", {}) if isinstance(evaluation.get("signatures"), dict) else {}
    channels = evaluation.get("channels", {}) if isinstance(evaluation.get("channels"), dict) else {}
    remote = evaluation.get("remote_channels", {}) if isinstance(evaluation.get("remote_channels"), dict) else {}
    return {
        "schema": 1,
        "status": evaluation.get("status", "NOT_RUN"),
        "signatures": signatures.get("status", "NOT_RUN"),
        "channels": channels.get("status", "NOT_RUN"),
        "channel_ratio": f"{len(channels.get('passed', []))}/{len(channels.get('required', []))}",
        "remote_channels": remote.get("status", "NOT_RUN"),
        "remote_configured": bool(remote.get("configured", False)),
        "truth_boundary": "Compact signature, channel-manifest, and remote-verification configuration status only; keys, signatures, receipts, observations, and evidence remain local.",
    }

#!/usr/bin/env python3
"""Standalone verifier for one extracted Forge owner-attestation ceremony kit.

The runner accepts public-key material and detached signatures only. It never
accepts, generates, opens, copies, or retains a private key.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

KIT_SCHEMA = "forge-owner-attestation-kit/1"
REQUEST_SCHEMA = "forge-owner-attestation-request/1"
RECEIPT_SCHEMA = "forge-owner-attestation-receipt/1"
RETURN_SCHEMA = "forge-external-evidence-return/1"
BUILD_SUBJECT = "emotivus-forge-build-manifest"
ALGORITHM = "rsa-pkcs1v15-sha256"
DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
TRUTH_BOUNDARY = (
    "A completed receipt proves only that the supplied RSA public key verifies a detached signature "
    "over the exact build-manifest bytes precommitted by this exact kit, and that those manifest bytes "
    "bind the observed package and packaged Forge-manifest bytes. The kit does not authenticate the "
    "human controller of the key, prove private-key custody, prove source reproducibility, authorize "
    "release, or retain private-key material."
)


class RunnerError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"{label} must be a JSON object")
    return value


def is_hex_digest(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text.lower())


def safe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return bool(normalized) and not normalized.startswith("/") and ".." not in path.parts


def member_is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def locate_root() -> Path:
    root = Path(__file__).resolve().parent
    if not (root / "MANIFEST.json").is_file():
        raise RunnerError("run-attestation.py must be executed from an extracted Forge attestation kit")
    return root


def packaged_manifest_identity(package: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(package) as archive:
            candidates = [
                info for info in archive.infolist()
                if not info.is_dir() and PurePosixPath(info.filename).name == "FORGE-MANIFEST.json"
            ]
            if len(candidates) != 1:
                raise RunnerError("package must contain exactly one FORGE-MANIFEST.json")
            content = archive.read(candidates[0])
            value = json.loads(content.decode("utf-8"))
            member_count = sum(1 for info in archive.infolist() if not info.is_dir())
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise RunnerError(f"package Forge manifest is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError("package Forge manifest must be a JSON object")
    return {
        "sha256": sha256_bytes(content),
        "bytes": len(content),
        "version": str(value.get("version", "")).strip(),
        "edition": str(value.get("edition", "development")).strip() or "development",
        "member_count": member_count,
    }


def validate_build_binding(package: Path, build_manifest: Path) -> dict[str, Any]:
    manifest = read_json(build_manifest, "build manifest")
    if manifest.get("schema") != 2 or manifest.get("subject") != BUILD_SUBJECT:
        raise RunnerError("attestation kits require Forge build-manifest schema 2")
    if manifest.get("signature_algorithm") != ALGORITHM:
        raise RunnerError(f"build manifest signature algorithm must be {ALGORITHM}")
    if manifest.get("private_key_retained") is not False or manifest.get("release_authorized") is not False:
        raise RunnerError("build manifest must preserve private_key_retained false and release_authorized false")
    if not package.is_file() or package.is_symlink():
        raise RunnerError("bound package is not one regular file")
    if manifest.get("package_sha256") != sha256_file(package):
        raise RunnerError("build manifest package digest differs from the exact package")
    if manifest.get("package_bytes") != package.stat().st_size:
        raise RunnerError("build manifest package byte length differs from the exact package")
    packaged = packaged_manifest_identity(package)
    if manifest.get("package_member_count") != packaged["member_count"]:
        raise RunnerError("build manifest package member count differs from the exact package")
    if manifest.get("version") != packaged["version"] or manifest.get("edition") != packaged["edition"]:
        raise RunnerError("build manifest version or edition differs from the packaged Forge manifest")
    if manifest.get("packaged_forge_manifest_sha256") != packaged["sha256"]:
        raise RunnerError("build manifest packaged Forge-manifest digest differs")
    if manifest.get("packaged_forge_manifest_bytes") != packaged["bytes"]:
        raise RunnerError("build manifest packaged Forge-manifest byte length differs")
    return manifest


def validate_public_key(path: Path) -> dict[str, Any]:
    raw = read_json(path, "RSA public key")
    allowed = {"schema", "algorithm", "key_id", "modulus_hex", "public_exponent"}
    if set(raw) - allowed:
        raise RunnerError(f"RSA public key contains unsupported fields: {sorted(set(raw) - allowed)}")
    if raw.get("schema") != 1 or raw.get("algorithm") != ALGORITHM:
        raise RunnerError("RSA public key must use schema 1 and rsa-pkcs1v15-sha256")
    key_id = str(raw.get("key_id", "")).strip()
    if not key_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in key_id):
        raise RunnerError("RSA public key key_id must use lowercase letters, digits, hyphens, or underscores")
    modulus_hex = str(raw.get("modulus_hex", "")).strip().lower()
    if len(modulus_hex) < 512:
        raise RunnerError("RSA public key modulus must be at least 2048 bits")
    try:
        modulus = int(modulus_hex, 16)
    except ValueError as exc:
        raise RunnerError("RSA public key modulus_hex must be hexadecimal") from exc
    exponent = raw.get("public_exponent", 65537)
    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 3 or exponent % 2 == 0:
        raise RunnerError("RSA public key public_exponent must be an odd integer of at least 3")
    if modulus.bit_length() < 2048:
        raise RunnerError("RSA public key modulus must be at least 2048 bits")
    canonical = json.dumps({
        "schema": 1,
        "algorithm": ALGORITHM,
        "key_id": key_id,
        "modulus_hex": modulus_hex,
        "public_exponent": exponent,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "key_id": key_id,
        "modulus": modulus,
        "public_exponent": exponent,
        "fingerprint": sha256_bytes(canonical),
        "canonical": canonical,
    }


def read_signature(path: Path) -> bytes:
    try:
        text = "".join(path.read_text(encoding="ascii").split())
        signature = base64.b64decode(text, validate=True)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RunnerError(f"detached signature must be non-empty base64 text: {exc}") from exc
    if not signature:
        raise RunnerError("detached signature is empty")
    return signature


def verify_signature(subject: bytes, signature: bytes, modulus: int, exponent: int) -> bool:
    size = (modulus.bit_length() + 7) // 8
    if size < 256 or len(signature) != size:
        return False
    signature_int = int.from_bytes(signature, "big")
    if signature_int <= 0 or signature_int >= modulus:
        return False
    encoded = pow(signature_int, exponent, modulus).to_bytes(size, "big")
    digest_info = DIGEST_INFO_PREFIX + hashlib.sha256(subject).digest()
    padding_length = size - len(digest_info) - 3
    if padding_length < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def verify_kit(root: Path) -> dict[str, Any]:
    manifest = read_json(root / "MANIFEST.json", "kit manifest")
    problems: list[str] = []
    if manifest.get("schema") != KIT_SCHEMA:
        problems.append("kit manifest schema differs")
    if manifest.get("attestation_status") != "NOT_RUN":
        problems.append("unexecuted kit must remain NOT_RUN")
    if manifest.get("owner_key_precommitted") is not False:
        problems.append("unexecuted kit must not claim a precommitted owner key")
    if manifest.get("private_key_retained") is not False or manifest.get("release_authorized") is not False:
        problems.append("kit truth flags differ")
    payloads = manifest.get("payloads")
    if not isinstance(payloads, list) or not payloads:
        problems.append("kit payload inventory is missing")
        payloads = []
    declared: set[str] = set()
    for item in payloads:
        if not isinstance(item, dict):
            problems.append("kit payload entry is not an object")
            continue
        relative = str(item.get("path", ""))
        declared.add(relative)
        path = root / relative
        if not safe_member(relative) or relative == "MANIFEST.json":
            problems.append(f"invalid kit payload path: {relative!r}")
        elif not path.is_file() or path.is_symlink():
            problems.append(f"kit payload missing: {relative}")
        else:
            if sha256_file(path) != item.get("sha256"):
                problems.append(f"kit payload digest differs: {relative}")
            if path.stat().st_size != item.get("bytes"):
                problems.append(f"kit payload byte length differs: {relative}")
    immutable_roots = {PurePosixPath(path).parts[0] for path in declared if PurePosixPath(path).parts}
    actual = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.name == "MANIFEST.json":
            continue
        relative = path.relative_to(root).as_posix()
        parts = PurePosixPath(relative).parts
        if parts and parts[0] in immutable_roots:
            actual.add(relative)
    if actual != declared:
        problems.append("kit immutable payload inventory differs from extracted files")
    package_ref = manifest.get("package") if isinstance(manifest.get("package"), dict) else {}
    build_ref = manifest.get("build_manifest") if isinstance(manifest.get("build_manifest"), dict) else {}
    package = root / str(package_ref.get("path", ""))
    build_manifest = root / str(build_ref.get("path", ""))
    try:
        build = validate_build_binding(package, build_manifest)
        if package_ref.get("sha256") != sha256_file(package) or package_ref.get("bytes") != package.stat().st_size:
            problems.append("kit package identity differs")
        if build_ref.get("sha256") != sha256_file(build_manifest) or build_ref.get("bytes") != build_manifest.stat().st_size:
            problems.append("kit build-manifest identity differs")
        if build.get("version") != manifest.get("forge_version") or build.get("edition") != manifest.get("edition"):
            problems.append("kit version or edition differs from build manifest")
    except RunnerError as exc:
        problems.append(str(exc))
    expected_id = sha256_bytes(canonical_bytes({
        "schema": KIT_SCHEMA,
        "package_sha256": package_ref.get("sha256"),
        "build_manifest_sha256": build_ref.get("sha256"),
        "forge_version": manifest.get("forge_version"),
        "edition": manifest.get("edition"),
        "payloads": [
            {"path": item.get("path"), "sha256": item.get("sha256"), "bytes": item.get("bytes")}
            for item in sorted(payloads, key=lambda row: str(row.get("path", ""))) if isinstance(item, dict)
        ],
    }))
    if manifest.get("kit_id") != expected_id:
        problems.append("kit identity differs from its exact payloads")
    return {
        "schema": 1,
        "status": "PASS" if not problems else "FAIL",
        "kit_id": manifest.get("kit_id", ""),
        "forge_version": manifest.get("forge_version", ""),
        "edition": manifest.get("edition", ""),
        "attestation_status": manifest.get("attestation_status", ""),
        "private_key_retained": False,
        "release_authorized": False,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def load_verified_kit() -> tuple[Path, dict[str, Any]]:
    root = locate_root()
    result = verify_kit(root)
    if result["status"] != "PASS":
        raise RunnerError(f"attestation kit verification failed: {result['problems']}")
    return root, read_json(root / "MANIFEST.json", "kit manifest")


def prepare(public_key_path: Path, output_dir: Path) -> dict[str, Any]:
    root, kit = load_verified_kit()
    key = validate_public_key(public_key_path.resolve())
    output_dir = output_dir.resolve()
    try:
        relative_output = output_dir.relative_to(root)
    except ValueError:
        relative_output = None
    if relative_output is not None and relative_output.parts:
        immutable_roots = {PurePosixPath(item["path"]).parts[0] for item in kit.get("payloads", []) if isinstance(item, dict) and PurePosixPath(str(item.get("path", ""))).parts}
        if relative_output.parts[0] in immutable_roots or relative_output.parts[0] == "MANIFEST.json":
            raise RunnerError("ceremony output directory cannot overlap immutable kit payloads")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RunnerError("ceremony output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    key_path = output_dir / "owner-public-key.json"
    key_path.write_bytes(key["canonical"])
    package = kit["package"]
    build_manifest = kit["build_manifest"]
    identity = {
        "kit_id": kit["kit_id"],
        "package_sha256": package["sha256"],
        "build_manifest_sha256": build_manifest["sha256"],
        "public_key_fingerprint": key["fingerprint"],
        "public_key_sha256": sha256_file(key_path),
    }
    ceremony_id = sha256_bytes(canonical_bytes(identity))
    request = {
        "schema": REQUEST_SCHEMA,
        "ceremony_id": ceremony_id,
        "status": "AWAITING_SIGNATURE",
        "signature_status": "NOT_RUN",
        "kit_id": kit["kit_id"],
        "forge_version": kit["forge_version"],
        "edition": kit["edition"],
        "package": dict(package),
        "build_manifest": dict(build_manifest),
        "signing_subject": {
            "path": build_manifest["path"],
            "sha256": build_manifest["sha256"],
            "bytes": build_manifest["bytes"],
            "algorithm": ALGORITHM,
        },
        "expected_public_key": {
            "key_id": key["key_id"],
            "fingerprint": key["fingerprint"],
            "sha256": sha256_file(key_path),
            "path": "owner-public-key.json",
        },
        "private_key_retained": False,
        "owner_identity_authenticated": False,
        "release_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    (output_dir / "attestation-request.json").write_bytes(pretty_bytes(request))
    instructions = f"""# External signing step\n\nCeremony ID: `{ceremony_id}`\n\nSign the exact kit file `{build_manifest['path']}` outside Forge using the private key corresponding to `owner-public-key.json` and RSA PKCS#1 v1.5 with SHA-256. Return only a base64 detached signature.\n\nForge does not accept or retain the private key. A verified signature does not authorize release.\n"""
    (output_dir / "SIGNING-INSTRUCTIONS.md").write_text(instructions, encoding="utf-8")
    return {
        "schema": 1,
        "status": "PASS",
        "attestation_status": "AWAITING_SIGNATURE",
        "ceremony_id": ceremony_id,
        "request": str(output_dir / "attestation-request.json"),
        "public_key_fingerprint": key["fingerprint"],
        "private_key_retained": False,
        "release_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def validate_request(root: Path, kit: dict[str, Any], ceremony_dir: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    request_path = ceremony_dir / "attestation-request.json"
    request = read_json(request_path, "attestation request")
    if request.get("schema") != REQUEST_SCHEMA or request.get("status") != "AWAITING_SIGNATURE":
        raise RunnerError("attestation request is not one supported awaiting-signature request")
    if request.get("kit_id") != kit.get("kit_id"):
        raise RunnerError("attestation request belongs to a different kit")
    if request.get("package") != kit.get("package") or request.get("build_manifest") != kit.get("build_manifest"):
        raise RunnerError("attestation request package or manifest identity differs from the kit")
    if request.get("private_key_retained") is not False or request.get("release_authorized") is not False:
        raise RunnerError("attestation request truth flags differ")
    key_ref = request.get("expected_public_key") if isinstance(request.get("expected_public_key"), dict) else {}
    key_path = ceremony_dir / str(key_ref.get("path", ""))
    key = validate_public_key(key_path)
    if key_ref.get("key_id") != key["key_id"] or key_ref.get("fingerprint") != key["fingerprint"]:
        raise RunnerError("attestation request expected public key differs from the supplied public key")
    if key_ref.get("sha256") != sha256_file(key_path):
        raise RunnerError("attestation request public-key bytes differ")
    identity = {
        "kit_id": kit["kit_id"],
        "package_sha256": kit["package"]["sha256"],
        "build_manifest_sha256": kit["build_manifest"]["sha256"],
        "public_key_fingerprint": key["fingerprint"],
        "public_key_sha256": sha256_file(key_path),
    }
    if request.get("ceremony_id") != sha256_bytes(canonical_bytes(identity)):
        raise RunnerError("attestation ceremony identity differs from its precommitted inputs")
    return request, key, key_path


def finalize(ceremony_dir: Path, signature_path: Path) -> dict[str, Any]:
    root, kit = load_verified_kit()
    ceremony_dir = ceremony_dir.resolve()
    request, key, _ = validate_request(root, kit, ceremony_dir)
    signature_path = signature_path.resolve()
    if not signature_path.is_file():
        return {
            "schema": 1,
            "status": "NOT_RUN",
            "attestation_status": "NOT_RUN",
            "ceremony_id": request.get("ceremony_id", ""),
            "problems": ["detached signature was not supplied"],
            "private_key_retained": False,
            "release_authorized": False,
            "truth_boundary": TRUTH_BOUNDARY,
        }
    signature = read_signature(signature_path)
    subject = root / kit["build_manifest"]["path"]
    if not verify_signature(subject.read_bytes(), signature, key["modulus"], key["public_exponent"]):
        raise RunnerError("detached signature does not verify against the exact precommitted build-manifest bytes")
    stored_signature = ceremony_dir / "detached-signature.b64"
    stored_signature.write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")
    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "ceremony_id": request["ceremony_id"],
        "kit_id": kit["kit_id"],
        "forge_version": kit["forge_version"],
        "edition": kit["edition"],
        "package": dict(kit["package"]),
        "build_manifest": dict(kit["build_manifest"]),
        "public_key": {
            "key_id": key["key_id"],
            "fingerprint": key["fingerprint"],
            "sha256": request["expected_public_key"]["sha256"],
        },
        "signature": {
            "algorithm": ALGORITHM,
            "sha256": sha256_bytes(signature),
            "bytes": len(signature),
            "path": "detached-signature.b64",
        },
        "attestation_status": "VERIFIED",
        "cryptographic_verification": "PASS",
        "private_key_retained": False,
        "owner_identity_authenticated": False,
        "release_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    receipt_id = sha256_bytes(canonical_bytes(receipt_core))
    receipt = {**receipt_core, "receipt_id": receipt_id}
    (ceremony_dir / "attestation-receipt.json").write_bytes(pretty_bytes(receipt))
    return {
        "schema": 1,
        "status": "PASS",
        "attestation_status": "VERIFIED",
        "ceremony_id": request["ceremony_id"],
        "receipt_id": receipt_id,
        "receipt": str(ceremony_dir / "attestation-receipt.json"),
        "public_key_fingerprint": key["fingerprint"],
        "private_key_retained": False,
        "owner_identity_authenticated": False,
        "release_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def verify_receipt(ceremony_dir: Path) -> dict[str, Any]:
    root, kit = load_verified_kit()
    ceremony_dir = ceremony_dir.resolve()
    request, key, _ = validate_request(root, kit, ceremony_dir)
    receipt = read_json(ceremony_dir / "attestation-receipt.json", "attestation receipt")
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("attestation_status") != "VERIFIED":
        raise RunnerError("attestation receipt is not one verified schema-1 receipt")
    signature_ref = receipt.get("signature") if isinstance(receipt.get("signature"), dict) else {}
    signature_path = ceremony_dir / str(signature_ref.get("path", ""))
    signature = read_signature(signature_path)
    subject = root / kit["build_manifest"]["path"]
    problems: list[str] = []
    if receipt.get("ceremony_id") != request.get("ceremony_id") or receipt.get("kit_id") != kit.get("kit_id"):
        problems.append("receipt ceremony or kit identity differs")
    if receipt.get("package") != kit.get("package") or receipt.get("build_manifest") != kit.get("build_manifest"):
        problems.append("receipt package or build-manifest identity differs")
    public_ref = receipt.get("public_key") if isinstance(receipt.get("public_key"), dict) else {}
    if public_ref.get("fingerprint") != key["fingerprint"] or public_ref.get("key_id") != key["key_id"]:
        problems.append("receipt public-key identity differs")
    if signature_ref.get("sha256") != sha256_bytes(signature) or signature_ref.get("bytes") != len(signature):
        problems.append("receipt signature identity differs")
    if not verify_signature(subject.read_bytes(), signature, key["modulus"], key["public_exponent"]):
        problems.append("receipt signature no longer verifies")
    if receipt.get("private_key_retained") is not False or receipt.get("owner_identity_authenticated") is not False or receipt.get("release_authorized") is not False:
        problems.append("receipt truth flags differ")
    core = dict(receipt)
    receipt_id = str(core.pop("receipt_id", ""))
    if receipt_id != sha256_bytes(canonical_bytes(core)):
        problems.append("receipt identity differs from its exact content")
    return {
        "schema": 1,
        "status": "PASS" if not problems else "FAIL",
        "attestation_status": "VERIFIED" if not problems else "INVALID",
        "ceremony_id": request.get("ceremony_id", ""),
        "receipt_id": receipt_id,
        "public_key_fingerprint": key["fingerprint"],
        "private_key_retained": False,
        "owner_identity_authenticated": False,
        "release_authorized": False,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }



def _return_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def _kit_archive_identity(path: Path, kit: dict[str, Any]) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise RunnerError("original attestation kit archive must be one regular ZIP file")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or any(not safe_member(name) for name in names):
            raise RunnerError("original attestation kit archive has unsafe or duplicate members")
        manifests = [info for info in infos if not info.is_dir() and PurePosixPath(info.filename).name == "MANIFEST.json"]
        if len(manifests) != 1:
            raise RunnerError("original attestation kit archive must contain one MANIFEST.json")
        archived = json.loads(archive.read(manifests[0]).decode("utf-8"))
        member_count = sum(1 for info in infos if not info.is_dir())
    if not isinstance(archived, dict) or archived.get("kit_id") != kit.get("kit_id"):
        raise RunnerError("original attestation kit archive differs from the extracted kit")
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "member_count": member_count,
        "kit_id": kit["kit_id"],
        "forge_version": kit["forge_version"],
        "schema": kit["schema"],
    }


def package_return(ceremony_dir: Path, kit_archive: Path, output: Path) -> dict[str, Any]:
    root, kit = load_verified_kit()
    verification = verify_receipt(ceremony_dir)
    if verification.get("status") != "PASS":
        raise RunnerError(f"attestation receipt is not returnable: {verification.get('problems', [])}")
    ceremony_dir = ceremony_dir.resolve()
    required = {
        "attestation-request.json",
        "owner-public-key.json",
        "detached-signature.b64",
        "attestation-receipt.json",
    }
    actual = {path.name for path in ceremony_dir.iterdir() if path.is_file()}
    if not required.issubset(actual):
        raise RunnerError(f"attestation return is missing required files: {sorted(required - actual)}")
    for path in ceremony_dir.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if any(token in lower for token in ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".p12", ".pfx", ".key", "private-key")) and "public-key" not in lower:
            raise RunnerError(f"private-key-like file is forbidden in returned evidence: {path.name}")
        content = path.read_bytes()
        if any(marker in content for marker in (
            b"-----BEGIN " + b"PRIVATE KEY-----", b"-----BEGIN RSA " + b"PRIVATE KEY-----",
            b"-----BEGIN EC " + b"PRIVATE KEY-----", b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
            b"-----BEGIN ENCRYPTED " + b"PRIVATE KEY-----",
        )):
            raise RunnerError(f"private-key material is forbidden in returned evidence: {path.name}")
    request = read_json(ceremony_dir / "attestation-request.json", "attestation request")
    receipt = read_json(ceremony_dir / "attestation-receipt.json", "attestation receipt")
    kit_ref = _kit_archive_identity(kit_archive, kit)
    payload_bytes = {
        f"ceremony/{name}": (ceremony_dir / name).read_bytes()
        for name in sorted(required)
    }
    payloads = [
        {"path": name, "sha256": sha256_bytes(content), "bytes": len(content)}
        for name, content in sorted(payload_bytes.items())
    ]
    truth = (
        "This return bundle proves only that exact files from one completed attestation ceremony were "
        "packaged against the named sealed kit. It does not authenticate the human key controller, "
        "prove private-key custody, authorize release, or establish release readiness."
    )
    core = {
        "schema": RETURN_SCHEMA,
        "kind": "owner-attestation",
        "kit": kit_ref,
        "subject": {
            "ceremony_id": request["ceremony_id"],
            "receipt_id": receipt["receipt_id"],
            "package_sha256": kit["package"]["sha256"],
            "build_manifest_sha256": kit["build_manifest"]["sha256"],
            "public_key_fingerprint": receipt["public_key"]["fingerprint"],
        },
        "workflow_status": "VERIFIED",
        "claim_scope": "exact-detached-signature-over-one-build-manifest",
        "payloads": payloads,
        "owner_identity_authenticated": False,
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "truth_boundary": truth,
    }
    manifest = {**core, "return_id": sha256_bytes(canonical_bytes(core))}
    root_name = f"Forge-Evidence-Return-{kit['forge_version']}-owner-attestation"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, content in sorted(payload_bytes.items()):
            archive.writestr(_return_zip_info(f"{root_name}/{relative}"), content)
        archive.writestr(_return_zip_info(f"{root_name}/MANIFEST.json"), pretty_bytes(manifest))
    temporary.replace(output)
    return {
        "schema": 1,
        "status": "PASS",
        "kind": "owner-attestation",
        "return_id": manifest["return_id"],
        "output": str(output),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "owner_identity_authenticated": False,
        "release_authorized": False,
        "truth_boundary": truth,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--public-key", type=Path, required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--ceremony-dir", type=Path, required=True)
    finalize_parser.add_argument("--signature", type=Path, required=True)
    receipt_parser = sub.add_parser("verify-receipt")
    receipt_parser.add_argument("--ceremony-dir", type=Path, required=True)
    return_parser = sub.add_parser("package-return")
    return_parser.add_argument("--ceremony-dir", type=Path, required=True)
    return_parser.add_argument("--kit-archive", type=Path, required=True)
    return_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify_kit(locate_root())
        elif args.command == "prepare":
            result = prepare(args.public_key, args.output_dir)
        elif args.command == "finalize":
            result = finalize(args.ceremony_dir, args.signature)
        elif args.command == "verify-receipt":
            result = verify_receipt(args.ceremony_dir)
        else:
            result = package_return(args.ceremony_dir, args.kit_archive, args.output)
    except (RunnerError, OSError, ValueError, zipfile.BadZipFile) as exc:
        result = {
            "schema": 1,
            "status": "FAIL",
            "attestation_status": "NOT_RUN",
            "problems": [str(exc)],
            "private_key_retained": False,
            "release_authorized": False,
            "truth_boundary": TRUTH_BOUNDARY,
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

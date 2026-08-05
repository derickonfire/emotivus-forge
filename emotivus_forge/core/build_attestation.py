from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .release_distribution import (
    ALGORITHM, read_detached_signature, read_rsa_public_key, verify_rsa_pkcs1v15_sha256,
)

BUILD_MANIFEST_SCHEMA = 2
LEGACY_BUILD_MANIFEST_SCHEMA = 1
SUBJECT = "emotivus-forge-build-manifest"

TRUTH_BOUNDARY = (
    "A passing attestation verifies that an external RSA key signed the exact build-manifest bytes "
    "and that those bytes bind the observed package digest, byte length, packaged Forge-manifest "
    "digest, packaged version, edition, and declared source-selection fingerprint. Forge does not "
    "access or retain a private key, authenticate the human controller of the public key, prove that "
    "the declared source produced the package, or authorize release."
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _packaged_manifest_identity(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [
                info for info in archive.infolist()
                if not info.is_dir() and PurePosixPath(info.filename).name == "FORGE-MANIFEST.json"
            ]
            if len(candidates) != 1:
                raise ValueError("build package must contain exactly one FORGE-MANIFEST.json")
            content = archive.read(candidates[0])
            value = json.loads(content.decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise ValueError(f"build package Forge manifest is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("build package Forge manifest must be a JSON object")
    version = str(value.get("version", "")).strip()
    edition = str(value.get("edition", "development")).strip() or "development"
    if not version:
        raise ValueError("build package Forge manifest does not declare a version")
    if edition not in {"public", "development"}:
        raise ValueError("build package Forge manifest edition must be public or development")
    return {
        "path": candidates[0].filename,
        "version": version,
        "edition": edition,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _packaged_version(path: Path) -> str:
    try:
        return str(_packaged_manifest_identity(path).get("version", ""))
    except ValueError:
        return ""


def _member_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(1 for info in archive.infolist() if not info.is_dir())


def build_manifest_payload(
    package_path: Path,
    *,
    version: str,
    edition: str,
    source_fingerprint: str,
    source_file_count: int,
    forge_manifest_sha256: str,
) -> dict[str, Any]:
    package_path = package_path.resolve()
    if edition not in {"public", "development"}:
        raise ValueError("build edition must be public or development")
    if not package_path.is_file() or package_path.is_symlink():
        raise ValueError("build package must be a regular file")
    if len(source_fingerprint) != 64 or len(forge_manifest_sha256) != 64:
        raise ValueError("source and Forge manifest fingerprints must be full SHA-256 digests")
    packaged = _packaged_manifest_identity(package_path)
    if packaged["version"] != str(version):
        raise ValueError("build package version does not match the requested build version")
    if packaged["edition"] != edition:
        raise ValueError("build package edition does not match the requested build edition")
    return {
        "schema": BUILD_MANIFEST_SCHEMA,
        "subject": SUBJECT,
        "signature_algorithm": ALGORITHM,
        "version": str(version),
        "edition": edition,
        "package_sha256": _sha256(package_path),
        "package_bytes": package_path.stat().st_size,
        "package_member_count": _member_count(package_path),
        "source_selection_sha256": source_fingerprint,
        "source_file_count": int(source_file_count),
        # Retained for schema-1 compatibility: this is the project-source manifest digest.
        "forge_manifest_sha256": forge_manifest_sha256,
        "packaged_forge_manifest_sha256": packaged["sha256"],
        "packaged_forge_manifest_bytes": packaged["bytes"],
        "private_key_retained": False,
        "release_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def write_build_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def read_build_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"build manifest is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("build manifest must be a JSON object")
    forbidden = [key for key in value if "private" in str(key).casefold() and key != "private_key_retained"]
    if forbidden:
        raise ValueError(f"build manifest must not contain private-key material fields: {sorted(forbidden)}")
    schema = value.get("schema")
    if schema not in {LEGACY_BUILD_MANIFEST_SCHEMA, BUILD_MANIFEST_SCHEMA} or value.get("subject") != SUBJECT:
        raise ValueError("build manifest must use the Forge build-manifest schema 1 or 2")
    if value.get("signature_algorithm") != ALGORITHM:
        raise ValueError(f"build manifest signature_algorithm must be {ALGORITHM}")
    if value.get("private_key_retained") is not False:
        raise ValueError("build manifest must explicitly state private_key_retained false")
    if value.get("release_authorized") is not False:
        raise ValueError("build attestation cannot claim release authorization")
    digest_keys = ["package_sha256", "source_selection_sha256", "forge_manifest_sha256"]
    if schema == BUILD_MANIFEST_SCHEMA:
        digest_keys.append("packaged_forge_manifest_sha256")
    for key in digest_keys:
        digest = str(value.get(key, ""))
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
            raise ValueError(f"build manifest {key} must be a full SHA-256 digest")
    number_keys = ["package_bytes", "package_member_count", "source_file_count"]
    if schema == BUILD_MANIFEST_SCHEMA:
        number_keys.append("packaged_forge_manifest_bytes")
    for key in number_keys:
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError(f"build manifest {key} must be a positive integer")
    if value.get("edition") not in {"public", "development"}:
        raise ValueError("build manifest edition must be public or development")
    if len(str(value.get("truth_boundary", ""))) < 100:
        raise ValueError("build manifest requires an explicit truth boundary")
    return value


def _read_manifest(path: Path) -> dict[str, Any]:
    """Compatibility alias retained for internal callers from prior builds."""
    return read_build_manifest(path)


def verify_build_attestation(
    package_path: Path,
    build_manifest_path: Path,
    public_key_path: Path,
    signature_path: Path,
    *,
    expected_source_fingerprint: str = "",
    expected_public_key_fingerprint: str = "",
) -> dict[str, Any]:
    package_path = package_path.resolve()
    build_manifest_path = build_manifest_path.resolve()
    public_key_path = public_key_path.resolve()
    signature_path = signature_path.resolve()
    problems: list[str] = []
    try:
        manifest = read_build_manifest(build_manifest_path)
        key = read_rsa_public_key(public_key_path)
        signature = read_detached_signature(signature_path)
    except ValueError as exc:
        return {"schema": 2, "status": "FAIL", "problems": [str(exc)], "truth_boundary": TRUTH_BOUNDARY}

    packaged: dict[str, Any] = {}
    if not package_path.is_file() or package_path.is_symlink():
        problems.append("build package is not a regular file")
    else:
        if manifest.get("package_sha256") != _sha256(package_path):
            problems.append("build manifest package_sha256 does not match the exact package bytes")
        if manifest.get("package_bytes") != package_path.stat().st_size:
            problems.append("build manifest package_bytes does not match the exact package bytes")
        try:
            if manifest.get("package_member_count") != _member_count(package_path):
                problems.append("build manifest package_member_count does not match the exact package")
            packaged = _packaged_manifest_identity(package_path)
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            problems.append(str(exc))
        if packaged:
            if manifest.get("version") != packaged.get("version"):
                problems.append("build manifest version does not match the packaged Forge manifest")
            if manifest.get("edition") != packaged.get("edition"):
                problems.append("build manifest edition does not match the packaged Forge manifest")
            if manifest.get("schema") == BUILD_MANIFEST_SCHEMA:
                if manifest.get("packaged_forge_manifest_sha256") != packaged.get("sha256"):
                    problems.append("build manifest packaged_forge_manifest_sha256 does not match the exact packaged Forge manifest bytes")
                if manifest.get("packaged_forge_manifest_bytes") != packaged.get("bytes"):
                    problems.append("build manifest packaged_forge_manifest_bytes does not match the exact packaged Forge manifest bytes")
    if expected_source_fingerprint and manifest.get("source_selection_sha256") != expected_source_fingerprint:
        problems.append("build manifest source-selection fingerprint differs from the expected current source")
    if expected_public_key_fingerprint and key.get("fingerprint") != expected_public_key_fingerprint:
        problems.append("public key fingerprint differs from the precommitted expected key")

    verified = verify_rsa_pkcs1v15_sha256(
        build_manifest_path.read_bytes(), signature, key["modulus"], key["public_exponent"]
    )
    if not verified:
        problems.append("detached signature does not verify against the exact build-manifest bytes")

    return {
        "schema": 2,
        "status": "PASS" if not problems else "FAIL",
        "build_manifest_schema": manifest.get("schema"),
        "version": manifest.get("version"),
        "edition": manifest.get("edition"),
        "package_sha256": manifest.get("package_sha256"),
        "build_manifest_sha256": _sha256(build_manifest_path),
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
        "public_key_id": key["key_id"],
        "public_key_fingerprint": key["fingerprint"],
        "source_selection_sha256": manifest.get("source_selection_sha256"),
        "packaged_forge_manifest_sha256": packaged.get("sha256", ""),
        "packaged_manifest_verified": bool(packaged) and (
            manifest.get("schema") == LEGACY_BUILD_MANIFEST_SCHEMA
            or manifest.get("packaged_forge_manifest_sha256") == packaged.get("sha256")
        ),
        "private_key_retained": False,
        "release_authorized": False,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }

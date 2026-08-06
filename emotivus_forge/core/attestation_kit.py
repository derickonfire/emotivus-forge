"""Deterministic portable ceremony kits for optional external build attestation."""
from __future__ import annotations

from .common import (
    canonical_bytes as _canonical_bytes,
    pretty_bytes as _pretty_bytes,
    sha256_bytes as _sha256_bytes,
    sha256_file as _sha256_file,
    safe_member as _safe_member,
    member_is_symlink as _member_is_symlink,
    zip_info as _zip_info,
    verify_archive_hygiene,
)

import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .build_attestation import BUILD_MANIFEST_SCHEMA, read_build_manifest

KIT_SCHEMA = "forge-owner-attestation-kit/1"
KIT_ROOT_PREFIX = "Forge-Attestation-Kit-"

TRUTH_BOUNDARY = (
    "This deterministic archive is a signing and verification aid for one exact Forge package and "
    "one exact schema-2 build manifest. Building, copying, extracting, or verifying the kit is not "
    "an attestation. The kit contains no private key, performs no signing, authenticates no human "
    "identity or key custody, proves no source reproducibility, and never authorizes release. "
    "Attestation remains NOT_RUN until an external detached signature is supplied and verified."
)


class AttestationKitError(ValueError):
    """Raised when one portable attestation kit cannot be trusted."""




def _packaged_manifest(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise AttestationKitError("build package contains duplicate member names")
            if any(not _safe_member(name) for name in names):
                raise AttestationKitError("build package contains unsafe member paths")
            if any(info.flag_bits & 0x1 for info in infos):
                raise AttestationKitError("build package contains encrypted members")
            if any(_member_is_symlink(info) for info in infos):
                raise AttestationKitError("build package contains symbolic-link members")
            manifests = [
                info for info in infos
                if not info.is_dir() and PurePosixPath(info.filename).name == "FORGE-MANIFEST.json"
            ]
            if len(manifests) != 1:
                raise AttestationKitError("build package must contain exactly one FORGE-MANIFEST.json")
            content = archive.read(manifests[0])
            value = json.loads(content.decode("utf-8"))
            member_count = sum(1 for info in infos if not info.is_dir())
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise AttestationKitError(f"build package is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise AttestationKitError("packaged Forge manifest must be a JSON object")
    version = str(value.get("version", "")).strip()
    edition = str(value.get("edition", "development")).strip() or "development"
    if not version or edition not in {"public", "development"}:
        raise AttestationKitError("packaged Forge manifest version or edition is invalid")
    return {
        "sha256": _sha256_bytes(content),
        "bytes": len(content),
        "version": version,
        "edition": edition,
        "member_count": member_count,
    }


def _validate_binding(package: Path, build_manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package.resolve()
    build_manifest_path = build_manifest_path.resolve()
    if not package.is_file() or package.is_symlink():
        raise AttestationKitError("attestation package must be one regular ZIP file")
    manifest = read_build_manifest(build_manifest_path)
    if manifest.get("schema") != BUILD_MANIFEST_SCHEMA:
        raise AttestationKitError("portable attestation kits require Forge build-manifest schema 2")
    packaged = _packaged_manifest(package)
    if manifest.get("package_sha256") != _sha256_file(package):
        raise AttestationKitError("build manifest package digest differs from the exact package")
    if manifest.get("package_bytes") != package.stat().st_size:
        raise AttestationKitError("build manifest package byte length differs from the exact package")
    if manifest.get("package_member_count") != packaged["member_count"]:
        raise AttestationKitError("build manifest member count differs from the exact package")
    if manifest.get("version") != packaged["version"] or manifest.get("edition") != packaged["edition"]:
        raise AttestationKitError("build manifest version or edition differs from the packaged Forge manifest")
    if manifest.get("packaged_forge_manifest_sha256") != packaged["sha256"]:
        raise AttestationKitError("build manifest packaged Forge-manifest digest differs")
    if manifest.get("packaged_forge_manifest_bytes") != packaged["bytes"]:
        raise AttestationKitError("build manifest packaged Forge-manifest byte length differs")
    return manifest, packaged


def _readme(version: str, edition: str, package_name: str, manifest_name: str) -> bytes:
    return f"""# Forge {version} owner-attestation ceremony kit

This archive is bound to one exact `{edition}` package and its exact schema-2 build manifest.
It contains no private key and cannot sign anything.

- Package: `{package_name}`
- Build manifest: `{manifest_name}`
- Initial attestation status: **NOT_RUN**
- Owner key precommitted: **false**
- Release authorized: **false**

## Verify the extracted kit

```text
python run-attestation.py verify
```

## Prepare with the owner's public key only

```text
python run-attestation.py prepare --public-key owner-public-key.json --output-dir ceremony
```

The preparation step precommits the exact public-key fingerprint and writes signing instructions.
The corresponding private key must remain outside Forge and outside this kit.

## Finalize after external signing

Return one base64 detached RSA PKCS#1 v1.5 SHA-256 signature over the exact build-manifest bytes,
then run:

```text
python run-attestation.py finalize --ceremony-dir ceremony --signature returned-signature.b64
python run-attestation.py verify-receipt --ceremony-dir ceremony
```

A cryptographic PASS does not authenticate the human controller of the key, prove custody,
authorize release, or claim release readiness.
""".encode("utf-8")


def _template_public_key() -> bytes:
    return _pretty_bytes({
        "schema": 1,
        "algorithm": "rsa-pkcs1v15-sha256",
        "key_id": "replace-with-owner-key-id",
        "modulus_hex": "REPLACE_WITH_AT_LEAST_2048_BIT_PUBLIC_MODULUS_HEX",
        "public_exponent": 65537,
    })


def _kit_id(version: str, edition: str, package: dict[str, Any], build_manifest: dict[str, Any], payloads: list[dict[str, Any]]) -> str:
    identity = {
        "schema": KIT_SCHEMA,
        "forge_version": version,
        "edition": edition,
        "package_sha256": package["sha256"],
        "build_manifest_sha256": build_manifest["sha256"],
        "payloads": [
            {"path": item["path"], "sha256": item["sha256"], "bytes": item["bytes"]}
            for item in sorted(payloads, key=lambda row: row["path"])
        ],
    }
    return _sha256_bytes(_canonical_bytes(identity))


def build_owner_attestation_kit(
    forge_root: Path,
    package_path: Path,
    build_manifest_path: Path,
    output: Path,
    *,
    runner_path: Path | None = None,
) -> dict[str, Any]:
    forge_root = forge_root.resolve()
    package_path = package_path.resolve()
    build_manifest_path = build_manifest_path.resolve()
    output = output.resolve()
    runner_path = (runner_path or (forge_root / "tools" / "portable_attestation_runner.py")).resolve()
    if not runner_path.is_file():
        raise AttestationKitError("portable attestation runner does not exist")
    manifest, packaged = _validate_binding(package_path, build_manifest_path)
    try:
        source = json.loads((forge_root / "FORGE-MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttestationKitError(f"source FORGE-MANIFEST.json is invalid: {exc}") from exc
    source_version = str(source.get("version", "")).strip() if isinstance(source, dict) else ""
    if source_version != packaged["version"]:
        raise AttestationKitError("bound package version differs from the source version")

    version = packaged["version"]
    edition = packaged["edition"]
    root_name = f"{KIT_ROOT_PREFIX}{version}-{edition}"
    package_ref = {
        "path": f"package/{package_path.name}",
        "filename": package_path.name,
        "sha256": _sha256_file(package_path),
        "bytes": package_path.stat().st_size,
        "member_count": packaged["member_count"],
    }
    manifest_ref = {
        "path": f"manifest/{build_manifest_path.name}",
        "filename": build_manifest_path.name,
        "sha256": _sha256_file(build_manifest_path),
        "bytes": build_manifest_path.stat().st_size,
        "schema": manifest["schema"],
    }
    payload_bytes = {
        "README.md": _readme(version, edition, package_path.name, build_manifest_path.name),
        "run-attestation.py": runner_path.read_bytes(),
        package_ref["path"]: package_path.read_bytes(),
        manifest_ref["path"]: build_manifest_path.read_bytes(),
        "templates/owner-public-key.template.json": _template_public_key(),
        "templates/detached-signature.template.b64": b"REPLACE_WITH_BASE64_DETACHED_SIGNATURE\n",
    }
    payloads = [
        {"path": path, "sha256": _sha256_bytes(content), "bytes": len(content)}
        for path, content in sorted(payload_bytes.items())
    ]
    kit_id = _kit_id(version, edition, package_ref, manifest_ref, payloads)
    kit_manifest = {
        "schema": KIT_SCHEMA,
        "kit_id": kit_id,
        "forge_version": version,
        "edition": edition,
        "attestation_status": "NOT_RUN",
        "owner_key_precommitted": False,
        "private_key_retained": False,
        "owner_identity_authenticated": False,
        "release_authorized": False,
        "package": package_ref,
        "build_manifest": manifest_ref,
        "payloads": payloads,
        "truth_boundary": TRUTH_BOUNDARY,
    }

    observed = {
        str(package_path): _sha256_file(package_path),
        str(build_manifest_path): _sha256_file(build_manifest_path),
        str(runner_path): _sha256_file(runner_path),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, content in sorted(payload_bytes.items()):
                archive.writestr(_zip_info(f"{root_name}/{relative}"), content)
            archive.writestr(_zip_info(f"{root_name}/MANIFEST.json"), _pretty_bytes(kit_manifest))
        if any(_sha256_file(Path(path)) != digest for path, digest in observed.items()):
            raise AttestationKitError("attestation kit inputs drifted during construction")
        temporary.replace(output)
        verification = verify_owner_attestation_kit(output)
        if verification.get("status") != "PASS":
            raise AttestationKitError(f"built attestation kit failed verification: {verification['problems']}")
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "status": "PASS",
        "path": str(output),
        "sha256": _sha256_file(output),
        "bytes": output.stat().st_size,
        "member_count": len(payload_bytes) + 1,
        "kit_id": kit_id,
        "forge_version": version,
        "edition": edition,
        "attestation_status": "NOT_RUN",
        "private_key_retained": False,
        "release_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def verify_owner_attestation_kit(path: Path) -> dict[str, Any]:
    path = path.resolve()
    problems: list[str] = []
    manifest: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            names, root_name, manifest_name, manifest = verify_archive_hygiene(archive, problems)
            if manifest:
                if manifest.get("schema") != KIT_SCHEMA:
                    problems.append("kit manifest schema differs")
                if manifest.get("attestation_status") != "NOT_RUN":
                    problems.append("kit manifest must remain NOT_RUN")
                if manifest.get("owner_key_precommitted") is not False:
                    problems.append("kit must not claim an owner key was precommitted")
                if manifest.get("private_key_retained") is not False or manifest.get("release_authorized") is not False:
                    problems.append("kit truth flags differ")
                payloads = manifest.get("payloads")
                if not isinstance(payloads, list) or not payloads:
                    problems.append("kit payload inventory is missing")
                    payloads = []
                declared: set[str] = set()
                normalized: list[dict[str, Any]] = []
                for item in payloads:
                    if not isinstance(item, dict):
                        problems.append("kit payload entry must be an object")
                        continue
                    relative = str(item.get("path", ""))
                    declared.add(relative)
                    full_name = f"{root_name}/{relative}"
                    if not _safe_member(relative) or relative == "MANIFEST.json":
                        problems.append(f"invalid kit payload path: {relative!r}")
                        continue
                    if full_name not in names:
                        problems.append(f"declared kit payload is missing: {relative}")
                        continue
                    content = archive.read(full_name)
                    digest = _sha256_bytes(content)
                    if digest != item.get("sha256"):
                        problems.append(f"kit payload digest differs: {relative}")
                    if len(content) != item.get("bytes"):
                        problems.append(f"kit payload byte length differs: {relative}")
                    normalized.append({"path": relative, "sha256": digest, "bytes": len(content)})
                actual = {
                    str(PurePosixPath(name).relative_to(root_name)) for name in names
                    if name != manifest_name
                }
                if actual != declared:
                    problems.append("kit payload inventory differs from archive members")
                package_ref = manifest.get("package") if isinstance(manifest.get("package"), dict) else {}
                build_ref = manifest.get("build_manifest") if isinstance(manifest.get("build_manifest"), dict) else {}
                package_name = f"{root_name}/{package_ref.get('path', '')}"
                build_name = f"{root_name}/{build_ref.get('path', '')}"
                if package_name not in names or build_name not in names:
                    problems.append("bound package or build manifest is missing")
                else:
                    from tempfile import TemporaryDirectory
                    with TemporaryDirectory() as temp:
                        temp_root = Path(temp)
                        package_path = temp_root / package_ref.get("filename", "package.zip")
                        build_path = temp_root / build_ref.get("filename", "build.json")
                        package_path.write_bytes(archive.read(package_name))
                        build_path.write_bytes(archive.read(build_name))
                        try:
                            build_manifest, packaged = _validate_binding(package_path, build_path)
                            if build_manifest.get("version") != manifest.get("forge_version"):
                                problems.append("kit version differs from build manifest")
                            if build_manifest.get("edition") != manifest.get("edition"):
                                problems.append("kit edition differs from build manifest")
                            if package_ref.get("sha256") != _sha256_file(package_path) or package_ref.get("bytes") != package_path.stat().st_size:
                                problems.append("kit package identity differs")
                            if build_ref.get("sha256") != _sha256_file(build_path) or build_ref.get("bytes") != build_path.stat().st_size:
                                problems.append("kit build-manifest identity differs")
                            if package_ref.get("member_count") != packaged.get("member_count"):
                                problems.append("kit package member count differs")
                        except (AttestationKitError, ValueError) as exc:
                            problems.append(str(exc))
                if normalized and package_ref and build_ref:
                    expected_id = _kit_id(
                        str(manifest.get("forge_version", "")),
                        str(manifest.get("edition", "")),
                        package_ref,
                        build_ref,
                        normalized,
                    )
                    if manifest.get("kit_id") != expected_id:
                        problems.append("kit identity differs from its exact payloads")
    except (OSError, zipfile.BadZipFile) as exc:
        problems.append(f"archive is not a readable ZIP: {exc}")
    return {
        "status": "PASS" if not problems else "FAIL",
        "path": str(path),
        "sha256": _sha256_file(path) if path.is_file() else "",
        "bytes": path.stat().st_size if path.is_file() else 0,
        "forge_version": str(manifest.get("forge_version", "")) if manifest else "",
        "edition": str(manifest.get("edition", "")) if manifest else "",
        "kit_id": str(manifest.get("kit_id", "")) if manifest else "",
        "attestation_status": str(manifest.get("attestation_status", "")) if manifest else "",
        "private_key_retained": False,
        "release_authorized": False,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }

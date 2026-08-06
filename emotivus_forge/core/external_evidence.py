"""Exact returned-evidence bundle verification and bounded adjudication.

Forge reviews one returned workflow against its original sealed kit, but never promotes
technical integrity into human identity, administrative independence, provider authenticity,
release authorization, or release readiness.
"""
from __future__ import annotations

from .common import (
    canonical_bytes,
    pretty_bytes,
    sha256_bytes,
    sha256_file,
    safe_member,
    member_is_symlink,
    ZIP_TIMESTAMP,
)

import base64
import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .attestation_kit import verify_owner_attestation_kit
from .build_attestation import verify_build_attestation
from .continuity_benchmark import compare_arms, record_run, verify_task_immutable
from .evidence_kit import verify_portable_evidence_kit

RETURN_SCHEMA = "forge-external-evidence-return/1"
REVIEW_SCHEMA = "forge-external-evidence-review/1"
MAX_RETURN_MEMBERS = 16
MAX_RETURN_MEMBER_BYTES = 8 * 1024 * 1024
MAX_RETURN_TOTAL_BYTES = 24 * 1024 * 1024

KINDS = ("owner-attestation", "independent-writer", "matched-handoff")
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN RSA " + b"PRIVATE KEY-----",
    b"-----BEGIN EC " + b"PRIVATE KEY-----",
    b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
    b"-----BEGIN DSA " + b"PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED " + b"PRIVATE KEY-----",
)
SUSPICIOUS_PRIVATE_NAMES = (
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".p12", ".pfx", ".key", "private-key",
)

RETURN_TRUTH_BOUNDARY = (
    "A returned-evidence review verifies exact files, declared workflow semantics, and the original "
    "sealed kit identity. It does not authenticate a human, prove private-key custody, prove separate "
    "administrative control, verify provider billing records, generalize a benchmark sample, authorize "
    "release, or establish release readiness."
)


class ExternalEvidenceError(ValueError):
    """Raised when a returned evidence bundle cannot be trusted."""


def _single_root(names: Iterable[str]) -> str:
    roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
    if len(roots) != 1:
        raise ExternalEvidenceError("return archive must contain exactly one root directory")
    return next(iter(roots))


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalEvidenceError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ExternalEvidenceError(f"{label} must contain one JSON object")
    return value


def _archive_identity(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise ExternalEvidenceError("sealed kit must be one regular ZIP file")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ExternalEvidenceError("sealed kit contains duplicate member names")
            if any(not safe_member(name) for name in names):
                raise ExternalEvidenceError("sealed kit contains unsafe member paths")
            if any(info.flag_bits & 0x1 for info in infos):
                raise ExternalEvidenceError("sealed kit contains encrypted members")
            if any(member_is_symlink(info) for info in infos):
                raise ExternalEvidenceError("sealed kit contains symbolic-link members")
            manifests = [info for info in infos if not info.is_dir() and PurePosixPath(info.filename).name == "MANIFEST.json"]
            if len(manifests) != 1:
                raise ExternalEvidenceError("sealed kit must contain exactly one MANIFEST.json")
            manifest = json.loads(archive.read(manifests[0]).decode("utf-8"))
            member_count = sum(1 for info in infos if not info.is_dir())
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalEvidenceError(f"sealed kit is invalid: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ExternalEvidenceError("sealed kit manifest must be a JSON object")
    return {
        "filename": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "member_count": member_count,
        "kit_id": str(manifest.get("kit_id", "")),
        "forge_version": str(manifest.get("forge_version", "")),
        "schema": str(manifest.get("schema", "")),
        "manifest": manifest,
    }


def _extract_return(path: Path, destination: Path) -> tuple[Path, dict[str, Any], dict[str, bytes]]:
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise ExternalEvidenceError("returned evidence must be one regular ZIP file")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > MAX_RETURN_MEMBERS:
                raise ExternalEvidenceError("return archive exceeds the member-count budget")
            if len(names) != len(set(names)):
                raise ExternalEvidenceError("return archive contains duplicate member names")
            if any(not safe_member(name) for name in names):
                raise ExternalEvidenceError("return archive contains unsafe member paths")
            if any(info.flag_bits & 0x1 for info in infos):
                raise ExternalEvidenceError("return archive contains encrypted members")
            if any(member_is_symlink(info) for info in infos):
                raise ExternalEvidenceError("return archive contains symbolic-link members")
            if any(not info.is_dir() and info.file_size > MAX_RETURN_MEMBER_BYTES for info in infos):
                raise ExternalEvidenceError("return archive contains an oversized member")
            total = sum(info.file_size for info in infos if not info.is_dir())
            if total > MAX_RETURN_TOTAL_BYTES:
                raise ExternalEvidenceError("return archive exceeds the uncompressed-byte budget")
            if any(info.date_time != ZIP_TIMESTAMP for info in infos):
                raise ExternalEvidenceError("return archive timestamps are not deterministic")
            root_name = _single_root(names)
            payloads: dict[str, bytes] = {}
            for info in infos:
                if info.is_dir():
                    continue
                relative = PurePosixPath(info.filename).relative_to(root_name).as_posix()
                payloads[relative] = archive.read(info)
            archive.extractall(destination)
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ExternalEvidenceError(f"return archive is invalid: {exc}") from exc
    root = destination / root_name
    manifest = _read_json(root / "MANIFEST.json", "return manifest")
    return root, manifest, payloads


def _validate_payload_inventory(manifest: dict[str, Any], payloads: dict[str, bytes], expected: set[str]) -> list[str]:
    problems: list[str] = []
    rows = manifest.get("payloads")
    if not isinstance(rows, list):
        return ["return manifest payload inventory is missing"]
    declared: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            problems.append("return payload entry is not an object")
            continue
        relative = str(row.get("path", ""))
        if relative in declared:
            problems.append(f"return payload is declared twice: {relative}")
        declared[relative] = row
    actual = set(payloads) - {"MANIFEST.json"}
    if set(declared) != actual:
        if set(declared) - actual:
            problems.append(f"declared return payloads are missing: {sorted(set(declared) - actual)}")
        if actual - set(declared):
            problems.append(f"undeclared return payloads are present: {sorted(actual - set(declared))}")
    if actual != expected:
        if expected - actual:
            problems.append(f"required workflow payloads are missing: {sorted(expected - actual)}")
        if actual - expected:
            problems.append(f"workflow payload allowlist was exceeded: {sorted(actual - expected)}")
    for relative, row in declared.items():
        content = payloads.get(relative)
        if content is None:
            continue
        if row.get("sha256") != sha256_bytes(content):
            problems.append(f"return payload digest differs: {relative}")
        if row.get("bytes") != len(content):
            problems.append(f"return payload byte length differs: {relative}")
    return problems


def _private_material_problems(payloads: dict[str, bytes]) -> list[str]:
    problems: list[str] = []
    for relative, content in payloads.items():
        lower = relative.lower()
        if any(token in lower for token in SUSPICIOUS_PRIVATE_NAMES) and "public-key" not in lower:
            problems.append(f"private-key-like filename is not admissible: {relative}")
        if any(marker in content for marker in PRIVATE_KEY_MARKERS):
            problems.append(f"private-key material marker detected: {relative}")
    return problems


def _return_identity_core(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": manifest.get("schema"),
        "kind": manifest.get("kind"),
        "kit": manifest.get("kit"),
        "subject": manifest.get("subject"),
        "workflow_status": manifest.get("workflow_status"),
        "claim_scope": manifest.get("claim_scope"),
        "payloads": manifest.get("payloads"),
        "owner_identity_authenticated": manifest.get("owner_identity_authenticated"),
        "independent_evidence_claimed": manifest.get("independent_evidence_claimed"),
        "release_authorized": manifest.get("release_authorized"),
        "truth_boundary": manifest.get("truth_boundary"),
    }


def _common_return_problems(manifest: dict[str, Any], kit: dict[str, Any], kind: str) -> list[str]:
    problems: list[str] = []
    if manifest.get("schema") != RETURN_SCHEMA:
        problems.append("return manifest schema differs")
    if manifest.get("kind") != kind:
        problems.append("return workflow kind differs")
    kit_ref = manifest.get("kit") if isinstance(manifest.get("kit"), dict) else {}
    for key in ("sha256", "bytes", "member_count", "kit_id", "forge_version", "schema"):
        if kit_ref.get(key) != kit.get(key):
            problems.append(f"return sealed-kit {key} differs")
    if manifest.get("return_id") != sha256_bytes(canonical_bytes(_return_identity_core(manifest))):
        problems.append("return identity differs from exact manifest content")
    if manifest.get("owner_identity_authenticated") is not False:
        problems.append("return bundle claims authenticated owner identity")
    if manifest.get("independent_evidence_claimed") is not False:
        problems.append("return bundle claims independent evidence")
    if manifest.get("release_authorized") is not False:
        problems.append("return bundle claims release authorization")
    return problems


def _json_payload(root: Path, relative: str) -> dict[str, Any]:
    return _read_json(root / relative, relative)


def _review_attestation(root: Path, manifest: dict[str, Any], kit_path: Path, kit: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    expected = {
        "ceremony/attestation-request.json",
        "ceremony/owner-public-key.json",
        "ceremony/detached-signature.b64",
        "ceremony/attestation-receipt.json",
    }
    problems: list[str] = []
    request = _json_payload(root, "ceremony/attestation-request.json")
    receipt = _json_payload(root, "ceremony/attestation-receipt.json")
    subject = manifest.get("subject") if isinstance(manifest.get("subject"), dict) else {}
    kit_manifest = kit["manifest"]
    if request.get("kit_id") != kit["kit_id"] or receipt.get("kit_id") != kit["kit_id"]:
        problems.append("attestation request or receipt belongs to a different kit")
    if request.get("ceremony_id") != receipt.get("ceremony_id") or subject.get("ceremony_id") != receipt.get("ceremony_id"):
        problems.append("attestation ceremony identity differs")
    if subject.get("receipt_id") != receipt.get("receipt_id"):
        problems.append("attestation return receipt identity differs")
    core = dict(receipt)
    receipt_id = str(core.pop("receipt_id", ""))
    if receipt_id != sha256_bytes(canonical_bytes(core)):
        problems.append("attestation receipt identity differs from its exact content")
    for flag in ("private_key_retained", "owner_identity_authenticated", "release_authorized"):
        if request.get(flag) is not False or receipt.get(flag) is not False:
            problems.append(f"attestation {flag} truth flag differs")
    with tempfile.TemporaryDirectory() as temp:
        kit_extract = Path(temp) / "kit"
        with zipfile.ZipFile(kit_path) as archive:
            archive.extractall(kit_extract)
        roots = [path for path in kit_extract.iterdir() if path.is_dir()]
        if len(roots) != 1:
            problems.append("attestation kit extraction did not produce one root")
        else:
            kit_root = roots[0]
            package = kit_root / str(kit_manifest.get("package", {}).get("path", ""))
            build_manifest = kit_root / str(kit_manifest.get("build_manifest", {}).get("path", ""))
            public_key_path = root / "ceremony/owner-public-key.json"
            verification = verify_build_attestation(
                package,
                build_manifest,
                public_key_path,
                root / "ceremony/detached-signature.b64",
            )
            if verification.get("status") != "PASS":
                problems.extend(f"build attestation: {item}" for item in verification.get("problems", []))
            key_raw = _read_json(public_key_path, "owner public key")
            canonical_key = json.dumps({
                "schema": 1,
                "algorithm": "rsa-pkcs1v15-sha256",
                "key_id": str(key_raw.get("key_id", "")).strip(),
                "modulus_hex": str(key_raw.get("modulus_hex", "")).strip().lower(),
                "public_exponent": key_raw.get("public_exponent", 65537),
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            accepted_fingerprints = {
                sha256_bytes(canonical_key),
                sha256_bytes(canonical_key + b"\n"),  # sealed 0.546 portable profile
            }
            if subject.get("public_key_fingerprint") not in accepted_fingerprints:
                problems.append("attestation public-key fingerprint differs from supported canonical profiles")
            if verification.get("public_key_fingerprint") != sha256_bytes(canonical_key):
                problems.append("core public-key fingerprint differs from normalized canonical bytes")
    evidence = {
        "subject_id": str(receipt.get("ceremony_id", "")),
        "workflow_status": "VERIFIED" if not problems else "INVALID",
        "adjudication_status": "VERIFIED_CRYPTOGRAPHIC_RECEIPT" if not problems else "REJECTED",
        "claim_scope": "exact-detached-signature-over-one-build-manifest",
        "technical_integrity": "PASS" if not problems else "FAIL",
        "owner_identity": "NOT_AUTHENTICATED",
        "administrative_independence": "NOT_APPLICABLE",
        "provider_report_authenticity": "NOT_APPLICABLE",
    }
    return problems, evidence


def _review_writer(root: Path, manifest: dict[str, Any], kit: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    problems: list[str] = []
    plan = _json_payload(root, "writer/plan.json")
    step = _json_payload(root, "writer/writer-step.json")
    receipt = _json_payload(root, "writer/independent-writer-receipt.json")
    ship = _json_payload(root, "writer/ship-result.json")
    before = (root / "writer/target-before.bin").read_bytes()
    after = (root / "writer/target-after.bin").read_bytes()
    kit_manifest = kit["manifest"]
    runtime = kit_manifest.get("runtime", {}) if isinstance(kit_manifest.get("runtime"), dict) else {}
    for value in (plan, step, receipt):
        if value.get("kit_id") != kit["kit_id"]:
            problems.append("writer record belongs to a different kit")
        if value.get("forge_version") != kit["forge_version"]:
            problems.append("writer record Forge version differs")
        if value.get("runtime_sha256") != runtime.get("sha256"):
            problems.append("writer record runtime digest differs")
    for key in ("challenge",):
        if plan.get(key) != step.get(key) or plan.get(key) != receipt.get(key):
            problems.append(f"writer {key} differs across protocol records")
    if plan.get("target_before_sha256") != sha256_bytes(before):
        problems.append("writer before-target digest differs")
    if step.get("target_before_sha256") != sha256_bytes(before):
        problems.append("writer step before-target digest differs")
    if step.get("target_after_sha256") != sha256_bytes(after):
        problems.append("writer after-target digest differs")
    mutation = receipt.get("mutation") if isinstance(receipt.get("mutation"), dict) else {}
    if mutation.get("before_sha256") != sha256_bytes(before) or mutation.get("after_sha256") != sha256_bytes(after):
        problems.append("writer receipt mutation identity differs")
    if before == after:
        problems.append("writer target bytes did not change")
    forge_result = receipt.get("forge_result") if isinstance(receipt.get("forge_result"), dict) else {}
    if forge_result.get("workspace_integrity_status") != "DRIFTED" or forge_result.get("release_ready") is not False:
        problems.append("writer receipt does not preserve the required DRIFTED release refusal")
    if ship.get("workspace_integrity", {}).get("status") != "DRIFTED" or ship.get("release_ready") is not False:
        problems.append("raw Ship result does not preserve the required DRIFTED release refusal")
    if forge_result.get("workspace_integrity_status") != ship.get("workspace_integrity", {}).get("status"):
        problems.append("writer receipt and raw Ship result differ")
    review = receipt.get("review") if isinstance(receipt.get("review"), dict) else {}
    separation = receipt.get("separation") if isinstance(receipt.get("separation"), dict) else {}
    if review.get("accepted") is not True or not str(review.get("reviewer", "")).strip():
        problems.append("writer candidate lacks named accepted review")
    if separation.get("distinct_process_invocations_observed") is not True:
        problems.append("writer candidate did not observe distinct process invocations")
    if separation.get("distinct_named_operators_asserted") is not True:
        problems.append("writer candidate did not assert distinct named operators")
    if separation.get("administrative_independence_authenticated") is not False:
        problems.append("writer candidate claims authenticated administrative independence")
    if receipt.get("status") != "PASS" or receipt.get("candidate_classification") != "REVIEWED-CANDIDATE":
        problems.append("writer receipt is not one reviewed passing candidate")
    if receipt.get("independent_evidence_claimed") is not False or receipt.get("release_authorized") is not False:
        problems.append("writer receipt truth flags differ")
    subject = manifest.get("subject") if isinstance(manifest.get("subject"), dict) else {}
    if subject.get("challenge") != plan.get("challenge"):
        problems.append("writer return subject differs")
    evidence = {
        "subject_id": str(plan.get("challenge", "")),
        "workflow_status": "PASS" if not problems else "INVALID",
        "adjudication_status": "VERIFIED_REVIEWED_CANDIDATE" if not problems else "REJECTED",
        "claim_scope": "one-exact-runtime-post-checkpoint-drift-candidate",
        "technical_integrity": "PASS" if not problems else "FAIL",
        "owner_identity": "NOT_APPLICABLE",
        "administrative_independence": "NOT_AUTHENTICATED",
        "provider_report_authenticity": "NOT_APPLICABLE",
    }
    return problems, evidence


def _review_benchmark(root: Path, manifest: dict[str, Any], kit: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    problems: list[str] = []
    packet = _json_payload(root, "benchmark/packet.json")
    forge_raw = _json_payload(root, "benchmark/forge-run.json")
    control_raw = _json_payload(root, "benchmark/control-run.json")
    result = _json_payload(root, "benchmark/comparison.json")
    kit_manifest = kit["manifest"]
    runtime = kit_manifest.get("runtime", {}) if isinstance(kit_manifest.get("runtime"), dict) else {}
    task = packet.get("task") if isinstance(packet.get("task"), dict) else {}
    if packet.get("kit_id") != kit["kit_id"] or result.get("kit_id") != kit["kit_id"]:
        problems.append("benchmark records belong to a different kit")
    if packet.get("runtime", {}).get("sha256") != runtime.get("sha256") or result.get("runtime_sha256") != runtime.get("sha256"):
        problems.append("benchmark runtime identity differs")
    if not verify_task_immutable(task):
        problems.append("benchmark task identity is stale")
    try:
        runs = [record_run(forge_raw), record_run(control_raw)]
        comparison = compare_arms(runs)
    except ValueError as exc:
        problems.append(f"benchmark run record is inadmissible: {exc}")
        comparison = {}
    if comparison.get("status") != "PAIRED":
        problems.append("benchmark records are not one admissibly paired sample")
    if comparison.get("workspace_isolation", {}).get("isolated") is not True:
        problems.append("benchmark workspaces are not isolated")
    if result.get("comparison") != comparison:
        problems.append("benchmark comparison differs from independently recomputed result")
    for key in ("task_id", "provider", "model"):
        expected = task.get("task_id") if key == "task_id" else packet.get(key)
        if result.get(key) != expected:
            problems.append(f"benchmark result {key} differs")
    if result.get("independent_evidence_claimed") is not False or result.get("release_authorized") is not False:
        problems.append("benchmark result truth flags differ")
    subject = manifest.get("subject") if isinstance(manifest.get("subject"), dict) else {}
    subject_core = {
        "task_id": task.get("task_id"),
        "runtime_sha256": runtime.get("sha256"),
        "provider": packet.get("provider"),
        "model": packet.get("model"),
    }
    expected_subject_id = sha256_bytes(canonical_bytes(subject_core))
    if subject.get("subject_id") != expected_subject_id:
        problems.append("benchmark return subject identity differs")
    evidence = {
        "subject_id": expected_subject_id,
        "workflow_status": "PAIRED" if not problems else "INVALID",
        "adjudication_status": "VERIFIED_PAIRED_SAMPLE" if not problems else "REJECTED",
        "claim_scope": "one-exact-task-provider-model-paired-sample",
        "technical_integrity": "PASS" if not problems else "FAIL",
        "owner_identity": "NOT_APPLICABLE",
        "administrative_independence": "NOT_AUTHENTICATED",
        "provider_report_authenticity": "NOT_AUTHENTICATED",
    }
    return problems, evidence


def verify_review_receipt(value_or_path: dict[str, Any] | Path) -> dict[str, Any]:
    value = _read_json(value_or_path, "review receipt") if isinstance(value_or_path, Path) else dict(value_or_path)
    problems: list[str] = []
    if value.get("schema") != REVIEW_SCHEMA:
        problems.append("review schema differs")
    core = dict(value)
    review_id = str(core.pop("review_id", ""))
    if review_id != sha256_bytes(canonical_bytes(core)):
        problems.append("review identity differs from exact content")
    if value.get("release_authorized") is not False or value.get("release_ready") is not False:
        problems.append("review claims release authority or readiness")
    if value.get("owner_identity_authenticated") is not False or value.get("independent_evidence_claimed") is not False:
        problems.append("review overclaims identity or independence")
    return {"status": "PASS" if not problems else "FAIL", "review_id": review_id, "problems": problems}


def _duplicate_status(subject_id: str, submission_id: str, prior_reviews: Iterable[Path]) -> tuple[str, list[str]]:
    valid: list[dict[str, Any]] = []
    problems: list[str] = []
    for path in prior_reviews:
        try:
            value = _read_json(path, f"prior review {path}")
            verification = verify_review_receipt(value)
        except ExternalEvidenceError as exc:
            problems.append(str(exc))
            continue
        if verification["status"] != "PASS":
            problems.extend(f"invalid prior review {path}: {item}" for item in verification["problems"])
            continue
        valid.append(value)
    if any(value.get("submission_id") == submission_id for value in valid):
        return "DUPLICATE_EXACT", problems
    if any(value.get("subject_id") == subject_id for value in valid):
        return "CONFLICTING_SUBMISSION", problems
    return "FIRST_SEEN", problems


def review_external_evidence(
    kit_path: Path,
    return_path: Path,
    *,
    reviewer: str,
    prior_reviews: Iterable[Path] = (),
) -> dict[str, Any]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ExternalEvidenceError("a named technical reviewer assertion is required")
    kit = _archive_identity(kit_path)
    kit_schema = kit["schema"]
    if kit_schema == "forge-owner-attestation-kit/1":
        kind = "owner-attestation"
        kit_verification = verify_owner_attestation_kit(kit_path)
    elif kit_schema == "forge-portable-evidence-kit/1":
        kind = ""
        kit_verification = verify_portable_evidence_kit(kit_path)
    else:
        raise ExternalEvidenceError("sealed kit schema is not supported for returned-evidence review")
    problems: list[str] = []
    if kit_verification.get("status") != "PASS":
        problems.extend(f"sealed kit: {item}" for item in kit_verification.get("problems", []))
    with tempfile.TemporaryDirectory() as temp:
        root, manifest, payloads = _extract_return(return_path, Path(temp))
        manifest_kind = str(manifest.get("kind", ""))
        if kind and manifest_kind != kind:
            problems.append("return kind does not match the sealed attestation kit")
        if not kind:
            if manifest_kind not in {"independent-writer", "matched-handoff"}:
                problems.append("return kind does not match the sealed evidence kit")
            kind = manifest_kind
        problems.extend(_common_return_problems(manifest, kit, kind))
        expected_by_kind = {
            "owner-attestation": {
                "ceremony/attestation-request.json", "ceremony/owner-public-key.json",
                "ceremony/detached-signature.b64", "ceremony/attestation-receipt.json",
            },
            "independent-writer": {
                "writer/plan.json", "writer/writer-step.json", "writer/independent-writer-receipt.json",
                "writer/ship-result.json", "writer/target-before.bin", "writer/target-after.bin",
            },
            "matched-handoff": {
                "benchmark/packet.json", "benchmark/forge-run.json", "benchmark/control-run.json",
                "benchmark/comparison.json",
            },
        }
        problems.extend(_validate_payload_inventory(manifest, payloads, expected_by_kind.get(kind, set())))
        problems.extend(_private_material_problems(payloads))
        evidence: dict[str, Any] = {
            "subject_id": "",
            "workflow_status": "INVALID",
            "adjudication_status": "REJECTED",
            "claim_scope": "none",
            "technical_integrity": "FAIL",
            "owner_identity": "NOT_AUTHENTICATED",
            "administrative_independence": "NOT_AUTHENTICATED",
            "provider_report_authenticity": "NOT_AUTHENTICATED",
        }
        if not problems:
            if kind == "owner-attestation":
                workflow_problems, evidence = _review_attestation(root, manifest, kit_path, kit)
            elif kind == "independent-writer":
                workflow_problems, evidence = _review_writer(root, manifest, kit)
            elif kind == "matched-handoff":
                workflow_problems, evidence = _review_benchmark(root, manifest, kit)
            else:
                workflow_problems = ["unsupported return kind"]
            problems.extend(workflow_problems)
        return_id = str(manifest.get("return_id", ""))
    submission_core = {
        "kind": kind,
        "kit_sha256": kit["sha256"],
        "return_sha256": sha256_file(return_path),
        "return_id": return_id,
    }
    submission_id = sha256_bytes(canonical_bytes(submission_core))
    duplicate_status, prior_problems = _duplicate_status(str(evidence.get("subject_id", "")), submission_id, prior_reviews)
    problems.extend(prior_problems)
    status = "PASS" if not problems else "FAIL"
    review_core = {
        "schema": REVIEW_SCHEMA,
        "status": status,
        "kind": kind,
        "reviewer_assertion": reviewer,
        "reviewer_identity_authenticated": False,
        "kit": {key: kit[key] for key in ("filename", "sha256", "bytes", "member_count", "kit_id", "forge_version", "schema")},
        "return_bundle": {
            "filename": return_path.name,
            "sha256": sha256_file(return_path),
            "bytes": return_path.stat().st_size,
            "return_id": return_id,
        },
        "subject_id": str(evidence.get("subject_id", "")),
        "submission_id": submission_id,
        "duplicate_status": duplicate_status,
        "workflow_status": evidence.get("workflow_status"),
        "adjudication_status": evidence.get("adjudication_status") if status == "PASS" else "REJECTED",
        "claim_scope": evidence.get("claim_scope") if status == "PASS" else "none",
        "technical_integrity": evidence.get("technical_integrity") if status == "PASS" else "FAIL",
        "owner_identity": evidence.get("owner_identity"),
        "administrative_independence": evidence.get("administrative_independence"),
        "provider_report_authenticity": evidence.get("provider_report_authenticity"),
        "problems": sorted(set(problems)),
        "private_key_retained": False,
        "owner_identity_authenticated": False,
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "release_ready": False,
        "truth_boundary": RETURN_TRUTH_BOUNDARY,
    }
    return {**review_core, "review_id": sha256_bytes(canonical_bytes(review_core))}


def write_review_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(pretty_bytes(value))
    temporary.replace(path)

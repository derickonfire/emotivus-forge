"""Deterministic portable execution kits for evidence that must occur elsewhere.

A kit binds instructions and runners to one exact public Forge runtime. It is an
execution aid, not evidence. Building or verifying a kit never upgrades a benchmark,
field trial, release claim, or authorization state.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .continuity_benchmark import define_task, verify_task_immutable

KIT_SCHEMA = "forge-portable-evidence-kit/1"
KIT_ROOT_PREFIX = "Forge-Evidence-Kit-"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

TRUTH_BOUNDARY = (
    "This deterministic archive is an execution aid bound to one exact public Forge runtime. "
    "Creating, copying, extracting, or verifying the kit is not independent evidence, does not "
    "authenticate an operator or reviewer, does not prove another operating system was used, does "
    "not supply provider token reports, and does not authorize release. Evidence remains NOT_RUN "
    "until completed external receipts satisfy the named protocol and are reviewed separately."
)


class EvidenceKitError(ValueError):
    """Raised when a portable evidence kit cannot be trusted."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_hex_digest(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text.lower())


def _safe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return bool(normalized) and not normalized.startswith("/") and ".." not in path.parts


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def runtime_identity(path: Path) -> dict[str, Any]:
    """Return exact identity and hygiene facts for one public runtime ZIP."""
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise EvidenceKitError("public runtime must be one regular ZIP file")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise EvidenceKitError("public runtime contains duplicate member names")
            if any(not _safe_member(name) for name in names):
                raise EvidenceKitError("public runtime contains an unsafe member path")
            if any(info.flag_bits & 0x1 for info in infos):
                raise EvidenceKitError("public runtime contains encrypted members")
            if any(_zip_member_is_symlink(info) for info in infos):
                raise EvidenceKitError("public runtime contains symbolic-link members")
            manifests = [
                info for info in infos
                if not info.is_dir() and PurePosixPath(info.filename).name == "FORGE-MANIFEST.json"
            ]
            if len(manifests) != 1:
                raise EvidenceKitError("public runtime must contain exactly one FORGE-MANIFEST.json")
            try:
                manifest = json.loads(archive.read(manifests[0]).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise EvidenceKitError(f"public runtime manifest is invalid: {exc}") from exc
            if not isinstance(manifest, dict) or not str(manifest.get("version", "")).strip():
                raise EvidenceKitError("public runtime manifest does not declare a version")
            edition = str(manifest.get("edition", "public")).strip() or "public"
            if edition != "public":
                raise EvidenceKitError("portable evidence kits require the public runtime edition")
            member_count = sum(1 for info in infos if not info.is_dir())
    except (OSError, zipfile.BadZipFile) as exc:
        raise EvidenceKitError(f"public runtime is not a readable ZIP: {exc}") from exc
    return {
        "filename": path.name,
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
        "member_count": member_count,
        "version": str(manifest["version"]).strip(),
        "edition": "public",
    }


def load_benchmark_task(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceKitError(f"benchmark task is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise EvidenceKitError("benchmark task must be a JSON object")
    sealed = raw if raw.get("schema") == "forge-benchmark-task/1" else define_task(raw)
    if not verify_task_immutable(sealed):
        raise EvidenceKitError("benchmark task identity does not match its canonical content")
    return sealed


def _readme(version: str, runtime: dict[str, Any], task_id: str) -> bytes:
    return f"""# Forge {version} portable evidence kit

This archive is bound to the exact public runtime below. It is an execution aid, not evidence.

- Runtime: `{runtime['filename']}`
- Runtime SHA-256: `{runtime['sha256']}`
- Runtime bytes: `{runtime['bytes']}`
- Benchmark task ID: `{task_id}`
- Initial evidence status: **NOT_RUN**
- Release authorized: **false**

## Verify after extraction

```text
python run-evidence.py verify
```

## Two-operator writer trial

Run these as separate invocations. The tool records operator assertions and process/environment
metadata but does not authenticate independence.

```text
python run-evidence.py prepare-writer --workspace trial --controller CONTROLLER_NAME --controller-assertion \"separately controlled\"
python run-evidence.py writer --workspace trial --writer WRITER_NAME --writer-assertion \"separately controlled\"
python run-evidence.py finish-writer --workspace trial --reviewer REVIEWER_NAME --accepted
```

## Matched handoff benchmark

```text
python run-evidence.py prepare-benchmark --output-dir benchmark --provider PROVIDER --model MODEL
# Complete benchmark/forge-run.json and benchmark/control-run.json using provider-reported exact tokens.
python run-evidence.py finalize-benchmark --packet-dir benchmark
```

A generated packet, template, or local PASS is not independent evidence. Preserve exact receipts,
provider reports, named review, and the original kit archive for later admissibility review.
""".encode("utf-8")


def _run_template(task_id: str, arm: str, runtime: dict[str, Any], workspace: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "arm": arm,
        "parent_sha256": runtime["sha256"],
        "provider": "FILL_FROM_PROVIDER",
        "model": "FILL_FROM_PROVIDER",
        "workspace": workspace,
        "exact_input_tokens": None,
        "exact_output_tokens": None,
        "exact_cost": None,
        "token_source": "provider-reported",
        "human_review": {"reviewer": "", "accepted": False},
    }


def _kit_identifier(runtime: dict[str, Any], task: dict[str, Any], payloads: list[dict[str, Any]]) -> str:
    identity = {
        "schema": KIT_SCHEMA,
        "runtime_sha256": runtime["sha256"],
        "runtime_bytes": runtime["bytes"],
        "runtime_version": runtime["version"],
        "task_id": task["task_id"],
        "payloads": [
            {"path": item["path"], "sha256": item["sha256"], "bytes": item["bytes"]}
            for item in sorted(payloads, key=lambda row: row["path"])
        ],
    }
    return hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def build_portable_evidence_kit(
    forge_root: Path,
    runtime_zip: Path,
    output: Path,
    *,
    runner_path: Path | None = None,
    task_path: Path | None = None,
) -> dict[str, Any]:
    """Build and verify one deterministic runtime-bound evidence kit."""
    forge_root = forge_root.resolve()
    runtime_zip = runtime_zip.resolve()
    output = output.resolve()
    runner_path = (runner_path or (forge_root / "tools" / "portable_evidence_runner.py")).resolve()
    task_path = (task_path or (forge_root / "examples" / "cold-session-resume.task.json")).resolve()
    if not runner_path.is_file() or not task_path.is_file():
        raise EvidenceKitError("evidence kit runner and benchmark task must exist")

    try:
        source_manifest = json.loads((forge_root / "FORGE-MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceKitError(f"source FORGE-MANIFEST.json is invalid: {exc}") from exc
    runtime = runtime_identity(runtime_zip)
    source_version = str(source_manifest.get("version", "")).strip() if isinstance(source_manifest, dict) else ""
    if runtime["version"] != source_version:
        raise EvidenceKitError("public runtime version does not match the source version")
    task = load_benchmark_task(task_path)

    observed_inputs = {
        str(runner_path): _sha256_file(runner_path),
        str(task_path): _sha256_file(task_path),
        str(runtime_zip): runtime["sha256"],
    }
    root_name = f"{KIT_ROOT_PREFIX}{runtime['version']}"
    payload_bytes: dict[str, bytes] = {
        "README.md": _readme(runtime["version"], runtime, task["task_id"]),
        "run-evidence.py": runner_path.read_bytes(),
        f"runtime/{runtime['filename']}": runtime_zip.read_bytes(),
        "tasks/cold-session-resume.task.json": _pretty_bytes(task),
        "templates/forge-run.json": _pretty_bytes(
            _run_template(task["task_id"], "forge", runtime, "forge-arm-workspace")
        ),
        "templates/control-run.json": _pretty_bytes(
            _run_template(task["task_id"], "control", runtime, "control-arm-workspace")
        ),
    }
    payloads = [
        {"path": path, "sha256": _sha256_bytes(content), "bytes": len(content)}
        for path, content in sorted(payload_bytes.items())
    ]
    manifest = {
        "schema": KIT_SCHEMA,
        "forge_version": runtime["version"],
        "kit_id": _kit_identifier(runtime, task, payloads),
        "evidence_status": "NOT_RUN",
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "private_key_retained": False,
        "runtime": runtime,
        "benchmark_task": {
            "task_id": task["task_id"],
            "schema": task["schema"],
            "path": "tasks/cold-session-resume.task.json",
        },
        "workflows": {
            "independent_writer": {
                "status": "NOT_RUN",
                "steps": ["prepare-writer", "writer", "finish-writer"],
                "independence_authentication": "not-provided",
            },
            "matched_handoff": {
                "status": "NOT_RUN",
                "steps": ["prepare-benchmark", "finalize-benchmark"],
                "provider_tokens": "required-exact-provider-reported",
                "named_human_review": "required",
            },
        },
        "payloads": payloads,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    payload_bytes["MANIFEST.json"] = _pretty_bytes(manifest)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, content in sorted(payload_bytes.items()):
                archive.writestr(_zip_info(f"{root_name}/{relative}"), content)
        current_inputs = {
            str(runner_path): _sha256_file(runner_path),
            str(task_path): _sha256_file(task_path),
            str(runtime_zip): _sha256_file(runtime_zip),
        }
        if current_inputs != observed_inputs:
            raise EvidenceKitError("evidence kit inputs drifted during construction")
        verification = verify_portable_evidence_kit(temporary)
        if verification["status"] != "PASS":
            raise EvidenceKitError(f"built evidence kit failed verification: {verification['problems']}")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": "PASS",
        "path": str(output),
        "sha256": _sha256_file(output),
        "bytes": output.stat().st_size,
        "member_count": len(payload_bytes),
        "kit_id": manifest["kit_id"],
        "forge_version": runtime["version"],
        "runtime": runtime,
        "evidence_status": "NOT_RUN",
        "release_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def verify_portable_evidence_kit(path: Path) -> dict[str, Any]:
    """Verify archive hygiene, declared payloads, task identity, and runtime binding."""
    path = path.resolve()
    problems: list[str] = []
    manifest: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos if not info.is_dir()]
            if len(names) != len(set(names)):
                problems.append("archive contains duplicate member names")
            if any(not _safe_member(name) for name in names):
                problems.append("archive contains unsafe member paths")
            if any(info.flag_bits & 0x1 for info in infos):
                problems.append("archive contains encrypted members")
            if any(_zip_member_is_symlink(info) for info in infos):
                problems.append("archive contains symbolic-link members")
            if any(info.date_time != ZIP_TIMESTAMP for info in infos):
                problems.append("archive member timestamps are not deterministic")
            roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
            if len(roots) != 1:
                problems.append("archive must contain exactly one top-level kit directory")
                root_name = ""
            else:
                root_name = next(iter(roots))
            manifest_name = f"{root_name}/MANIFEST.json" if root_name else ""
            if not manifest_name or manifest_name not in names:
                problems.append("archive does not contain MANIFEST.json at the kit root")
            else:
                try:
                    loaded = json.loads(archive.read(manifest_name).decode("utf-8"))
                    manifest = loaded if isinstance(loaded, dict) else {}
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    problems.append(f"MANIFEST.json is invalid: {exc}")
            if manifest:
                if manifest.get("schema") != KIT_SCHEMA:
                    problems.append("manifest schema is not forge-portable-evidence-kit/1")
                if manifest.get("evidence_status") != "NOT_RUN":
                    problems.append("kit manifest must remain NOT_RUN")
                if manifest.get("independent_evidence_claimed") is not False:
                    problems.append("kit manifest must not claim independent evidence")
                if manifest.get("release_authorized") is not False:
                    problems.append("kit manifest must not claim release authorization")
                if manifest.get("private_key_retained") is not False:
                    problems.append("kit manifest must state private_key_retained false")
                if len(str(manifest.get("truth_boundary", ""))) < 200:
                    problems.append("kit truth boundary is missing or too weak")
                payloads = manifest.get("payloads")
                if not isinstance(payloads, list) or not payloads:
                    problems.append("kit manifest payloads must be a non-empty array")
                    payloads = []
                declared_paths: set[str] = set()
                normalized_payloads: list[dict[str, Any]] = []
                for item in payloads:
                    if not isinstance(item, dict):
                        problems.append("kit payload entry must be an object")
                        continue
                    relative = str(item.get("path", ""))
                    declared_paths.add(relative)
                    full_name = f"{root_name}/{relative}"
                    if not _safe_member(relative) or relative == "MANIFEST.json":
                        problems.append(f"kit payload path is invalid: {relative!r}")
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
                    normalized_payloads.append({"path": relative, "sha256": digest, "bytes": len(content)})
                actual_relative = {
                    str(PurePosixPath(name).relative_to(root_name)) for name in names
                    if name != manifest_name
                }
                if actual_relative != declared_paths:
                    missing = sorted(declared_paths - actual_relative)
                    extra = sorted(actual_relative - declared_paths)
                    if missing:
                        problems.append(f"declared payload paths missing from archive: {missing}")
                    if extra:
                        problems.append(f"undeclared payload paths present in archive: {extra}")
                runtime = manifest.get("runtime")
                if not isinstance(runtime, dict):
                    problems.append("kit manifest runtime identity is missing")
                else:
                    runtime_name = f"{root_name}/runtime/{runtime.get('filename', '')}"
                    if runtime_name not in names:
                        problems.append("bound public runtime is missing from the kit")
                    else:
                        runtime_bytes = archive.read(runtime_name)
                        if _sha256_bytes(runtime_bytes) != runtime.get("sha256"):
                            problems.append("bound public runtime digest differs")
                        if len(runtime_bytes) != runtime.get("bytes"):
                            problems.append("bound public runtime byte length differs")
                        try:
                            from io import BytesIO
                            with zipfile.ZipFile(BytesIO(runtime_bytes)) as runtime_archive:
                                manifests = [
                                    info for info in runtime_archive.infolist()
                                    if not info.is_dir() and PurePosixPath(info.filename).name == "FORGE-MANIFEST.json"
                                ]
                                if len(manifests) != 1:
                                    problems.append("bound runtime has an invalid manifest count")
                                else:
                                    runtime_manifest = json.loads(runtime_archive.read(manifests[0]).decode("utf-8"))
                                    if str(runtime_manifest.get("version", "")) != str(manifest.get("forge_version", "")):
                                        problems.append("bound runtime version differs from kit version")
                        except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
                            problems.append(f"bound runtime could not be verified: {exc}")
                task_ref = manifest.get("benchmark_task")
                if not isinstance(task_ref, dict):
                    problems.append("benchmark task reference is missing")
                else:
                    task_name = f"{root_name}/{task_ref.get('path', '')}"
                    if task_name not in names:
                        problems.append("benchmark task payload is missing")
                    else:
                        try:
                            task = json.loads(archive.read(task_name).decode("utf-8"))
                            if not isinstance(task, dict) or not verify_task_immutable(task):
                                problems.append("benchmark task identity is not current")
                            elif task.get("task_id") != task_ref.get("task_id"):
                                problems.append("benchmark task ID differs from the manifest")
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            problems.append(f"benchmark task payload is invalid: {exc}")
                if (
                    isinstance(runtime, dict)
                    and normalized_payloads
                    and 'task' in locals()
                    and isinstance(task, dict)
                    and task.get("task_id")
                ):
                    expected_id = _kit_identifier(runtime, task, normalized_payloads)
                    if manifest.get("kit_id") != expected_id:
                        problems.append("kit identity differs from its exact runtime, task, or payloads")
    except (OSError, zipfile.BadZipFile) as exc:
        problems.append(f"archive is not a readable ZIP: {exc}")
    return {
        "status": "PASS" if not problems else "FAIL",
        "path": str(path),
        "sha256": _sha256_file(path) if path.is_file() else "",
        "bytes": path.stat().st_size if path.is_file() else 0,
        "forge_version": str(manifest.get("forge_version", "")) if manifest else "",
        "kit_id": str(manifest.get("kit_id", "")) if manifest else "",
        "evidence_status": str(manifest.get("evidence_status", "")) if manifest else "",
        "release_authorized": manifest.get("release_authorized") if manifest else None,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .common import normalize_rel, read_json, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .lineage import exact_zip_tree, lineage_records
from .paths import ForgePaths
from .state import load_settings

PACKAGE_FAMILY_SCHEMA = 1
PACKAGE_ROLES = {
    "full-site", "toolset", "changed-files", "development", "website",
    "evidence", "continuity", "runtime", "outer-bundle", "other",
}
PACKAGE_FAMILY_TRUTH_BOUNDARY = (
    "Forge verifies exact ZIP bytes, normalized archive trees, declared package-family relationships, embedded outer-bundle members, "
    "and deterministic changed-files reconstruction against one exact parent and result tree. It does not execute the application, "
    "prove semantic merge correctness, establish deployment safety, or infer that an undeclared artifact belongs to the family."
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
        raise ValueError(f"Package family requires {label}.")
    return text


def _digest(value: Any, label: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be an exact lowercase SHA-256 digest.")
    return text


def _project_file(project_root: Path, forge_root: Path, raw: Any, label: str) -> tuple[Path, str]:
    path = Path(_required(raw, label))
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError(f"{label} must be a regular project file outside .forge.")
    if _inside(path, forge_root.resolve()):
        raise ValueError(f"{label} cannot come from the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _safe_member(raw: str) -> str:
    value = str(raw or "").replace("\\", "/")
    pure = PurePosixPath(value)
    if not value or value.startswith("/") or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Outer bundle member path is unsafe: {raw}")
    normalized = "/".join(part for part in pure.parts if part not in {"", "."})
    if not normalized:
        raise ValueError("Outer bundle member path is empty.")
    return normalized


def _active_lineage(project_root: Path, lineage_id: str) -> dict[str, Any]:
    record = lineage_records(project_root).get(lineage_id)
    if not isinstance(record, dict) or str(record.get("status", "")) != "active":
        raise ValueError(f"Package family lineage is not active: {lineage_id}")
    return record


def _artifact(project_root: Path, forge_root: Path, raw: Any, seen: set[str]) -> tuple[dict[str, Any], dict[str, Any], Path]:
    if not isinstance(raw, dict):
        raise ValueError("Each package-family artifact must be an object.")
    artifact_id = _required(raw.get("artifact_id"), "artifact.artifact_id")
    if artifact_id in seen:
        raise ValueError(f"Package-family artifact ID is duplicated: {artifact_id}")
    seen.add(artifact_id)
    role = str(raw.get("role", "other")).strip().lower()
    if role not in PACKAGE_ROLES:
        raise ValueError(f"Unsupported package-family artifact role: {role}")
    path, relative = _project_file(project_root, forge_root, raw.get("path"), f"artifact {artifact_id} path")
    expected_sha = _digest(raw.get("sha256"), f"artifact {artifact_id} sha256")
    expected_bytes = raw.get("bytes")
    if not isinstance(expected_bytes, int) or expected_bytes < 1:
        raise ValueError(f"Artifact {artifact_id} bytes must be a positive integer.")
    observed_sha = sha256_file(path)
    observed_bytes = path.stat().st_size
    if observed_sha != expected_sha or observed_bytes != expected_bytes:
        raise ValueError(f"Artifact {artifact_id} exact ZIP identity does not match the contract.")
    strip_prefix = normalize_rel(str(raw.get("strip_prefix", ""))).strip("/")
    tree = exact_zip_tree(path, strip_prefix=strip_prefix)
    expected_tree = _digest(raw.get("tree_sha256"), f"artifact {artifact_id} tree_sha256")
    expected_count = raw.get("tree_file_count")
    if tree["tree_sha256"] != expected_tree or not isinstance(expected_count, int) or tree["file_count"] != expected_count:
        raise ValueError(f"Artifact {artifact_id} normalized tree identity does not match its ZIP bytes.")
    normalized = {
        "artifact_id": artifact_id,
        "role": role,
        "path": relative,
        "sha256": observed_sha,
        "bytes": observed_bytes,
        "strip_prefix": strip_prefix,
        "tree_sha256": tree["tree_sha256"],
        "tree_file_count": tree["file_count"],
        "tree_total_bytes": tree["total_bytes"],
    }
    return normalized, tree, path


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    before_files = before.get("files", {}) if isinstance(before.get("files"), dict) else {}
    after_files = after.get("files", {}) if isinstance(after.get("files"), dict) else {}
    before_paths, after_paths = set(before_files), set(after_files)
    return {
        "added": sorted(after_paths - before_paths),
        "deleted": sorted(before_paths - after_paths),
        "modified": sorted(
            path for path in before_paths & after_paths
            if before_files[path] != after_files[path]
        ),
    }


def _canonical_tree(files: dict[str, dict[str, Any]]) -> tuple[str, int, int]:
    rows = []
    total = 0
    for path in sorted(files):
        size = int(files[path].get("size", 0) or 0)
        digest = _digest(files[path].get("sha256"), f"reconstructed member {path} digest")
        rows.append((path, size, digest))
        total += size
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(rows), total


def _validate_outer_bundles(raw_rows: Any, artifacts: dict[str, dict[str, Any]], paths: dict[str, Path]) -> list[dict[str, Any]]:
    if raw_rows in (None, []):
        return []
    if not isinstance(raw_rows, list):
        raise ValueError("outer_bundles must be an array.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"outer_bundles[{index}] must be an object.")
        outer_id = _required(raw.get("artifact_id"), f"outer_bundles[{index}].artifact_id")
        if outer_id in seen:
            raise ValueError(f"Outer bundle is declared twice: {outer_id}")
        seen.add(outer_id)
        outer = artifacts.get(outer_id)
        if not outer or outer.get("role") != "outer-bundle":
            raise ValueError(f"Outer bundle artifact must be recorded with role outer-bundle: {outer_id}")
        members_raw = raw.get("members")
        if not isinstance(members_raw, list) or not members_raw:
            raise ValueError(f"Outer bundle {outer_id} requires at least one embedded member.")
        verified: list[dict[str, str]] = []
        with zipfile.ZipFile(paths[outer_id]) as archive:
            names = [info.filename.replace("\\", "/") for info in archive.infolist() if not info.is_dir()]
            if len(names) != len(set(names)):
                raise ValueError(f"Outer bundle {outer_id} contains duplicate raw member names.")
            for member in members_raw:
                if not isinstance(member, dict):
                    raise ValueError(f"Outer bundle {outer_id} member declarations must be objects.")
                child_id = _required(member.get("artifact_id"), "outer bundle child artifact_id")
                child = artifacts.get(child_id)
                if not child or child_id == outer_id:
                    raise ValueError(f"Outer bundle {outer_id} references an invalid child artifact: {child_id}")
                member_path = _safe_member(member.get("member_path"))
                try:
                    info = archive.getinfo(member_path)
                except KeyError as exc:
                    raise ValueError(f"Outer bundle {outer_id} is missing declared member {member_path}.") from exc
                if info.flag_bits & 0x1:
                    raise ValueError(f"Outer bundle member is encrypted: {member_path}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and stat.S_ISLNK(mode):
                    raise ValueError(f"Outer bundle member is a symlink: {member_path}")
                digest = hashlib.sha256()
                length = 0
                with archive.open(info, "r") as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
                        length += len(chunk)
                if digest.hexdigest() != child["sha256"] or length != child["bytes"]:
                    raise ValueError(f"Outer bundle {outer_id} member {member_path} does not equal artifact {child_id}.")
                verified.append({"artifact_id": child_id, "member_path": member_path})
        result.append({"artifact_id": outer_id, "members": sorted(verified, key=lambda row: row["artifact_id"])})
    return result


def _validate_deltas(raw_rows: Any, artifacts: dict[str, dict[str, Any]], trees: dict[str, dict[str, Any]], paths: dict[str, Path]) -> list[dict[str, Any]]:
    if raw_rows in (None, []):
        return []
    if not isinstance(raw_rows, list):
        raise ValueError("deltas must be an array.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"deltas[{index}] must be an object.")
        delta_id = _required(raw.get("delta_id"), f"deltas[{index}].delta_id")
        if delta_id in seen:
            raise ValueError(f"Delta ID is duplicated: {delta_id}")
        seen.add(delta_id)
        parent_id = _required(raw.get("parent_artifact_id"), f"delta {delta_id} parent_artifact_id")
        package_id = _required(raw.get("delta_artifact_id"), f"delta {delta_id} delta_artifact_id")
        result_id = _required(raw.get("result_artifact_id"), f"delta {delta_id} result_artifact_id")
        if parent_id not in artifacts or package_id not in artifacts or result_id not in artifacts:
            raise ValueError(f"Delta {delta_id} references an unrecorded artifact.")
        if artifacts[package_id]["role"] != "changed-files":
            raise ValueError(f"Delta artifact {package_id} must use role changed-files.")
        payload_prefix = normalize_rel(str(raw.get("payload_prefix", ""))).strip("/")
        control_paths_raw = raw.get("control_paths", [])
        if not isinstance(control_paths_raw, list):
            raise ValueError(f"Delta {delta_id} control_paths must be an array.")
        control_paths = sorted({normalize_rel(str(value)).strip("/") for value in control_paths_raw if str(value).strip()})
        payload_tree = exact_zip_tree(paths[package_id], strip_prefix=payload_prefix, exclude_paths=control_paths)
        parent_tree, final_tree = trees[parent_id], trees[result_id]
        actual = _diff(parent_tree, final_tree)
        expected_added = sorted({normalize_rel(str(v)).strip("/") for v in raw.get("added_paths", [])})
        expected_modified = sorted({normalize_rel(str(v)).strip("/") for v in raw.get("modified_paths", [])})
        expected_deleted = sorted({normalize_rel(str(v)).strip("/") for v in raw.get("deleted_paths", [])})
        renames_raw = raw.get("renamed_paths", [])
        if not isinstance(renames_raw, list):
            raise ValueError(f"Delta {delta_id} renamed_paths must be an array.")
        renames: list[dict[str, str]] = []
        rename_from: set[str] = set()
        rename_to: set[str] = set()
        for row in renames_raw:
            if not isinstance(row, dict):
                raise ValueError(f"Delta {delta_id} rename rows must be objects.")
            old = normalize_rel(_required(row.get("from"), f"delta {delta_id} rename.from")).strip("/")
            new = normalize_rel(_required(row.get("to"), f"delta {delta_id} rename.to")).strip("/")
            if old in rename_from or new in rename_to:
                raise ValueError(f"Delta {delta_id} repeats a rename source or destination.")
            rename_from.add(old); rename_to.add(new)
            renames.append({"from": old, "to": new})
        if expected_added != sorted(set(actual["added"]) - rename_to):
            raise ValueError(f"Delta {delta_id} added_paths do not match the exact parent-to-result tree difference.")
        if expected_modified != actual["modified"]:
            raise ValueError(f"Delta {delta_id} modified_paths do not match the exact parent-to-result tree difference.")
        if expected_deleted != sorted(set(actual["deleted"]) - rename_from):
            raise ValueError(f"Delta {delta_id} deleted_paths do not match the exact parent-to-result tree difference.")
        parent_files = parent_tree.get("files", {}) if isinstance(parent_tree.get("files"), dict) else {}
        result_files = final_tree.get("files", {}) if isinstance(final_tree.get("files"), dict) else {}
        for row in renames:
            if row["from"] not in actual["deleted"] or row["to"] not in actual["added"]:
                raise ValueError(f"Delta {delta_id} rename is not an exact deleted-to-added path transition.")
            if parent_files.get(row["from"]) != result_files.get(row["to"]):
                raise ValueError(f"Delta {delta_id} rename bytes differ; declare it as delete plus add instead.")
        required_payload = set(expected_added) | set(expected_modified) | rename_to
        payload_files = payload_tree.get("files", {}) if isinstance(payload_tree.get("files"), dict) else {}
        if set(payload_files) != required_payload:
            missing = sorted(required_payload - set(payload_files))
            extra = sorted(set(payload_files) - required_payload)
            raise ValueError(f"Delta {delta_id} payload paths do not exactly match required changed bytes; missing={missing}, extra={extra}.")
        for changed_path in required_payload:
            if payload_files.get(changed_path) != result_files.get(changed_path):
                raise ValueError(f"Delta {delta_id} payload bytes do not match result artifact path: {changed_path}")
        reconstructed = {path: dict(value) for path, value in parent_files.items()}
        for path in set(expected_deleted) | rename_from:
            reconstructed.pop(path, None)
        for path, value in payload_files.items():
            reconstructed[path] = dict(value)
        digest, count, total = _canonical_tree(reconstructed)
        if digest != final_tree["tree_sha256"] or count != final_tree["file_count"]:
            raise ValueError(f"Delta {delta_id} does not reconstruct the exact result tree.")
        result.append({
            "delta_id": delta_id,
            "parent_artifact_id": parent_id,
            "delta_artifact_id": package_id,
            "result_artifact_id": result_id,
            "payload_prefix": payload_prefix,
            "control_paths": control_paths,
            "added_paths": expected_added,
            "modified_paths": expected_modified,
            "deleted_paths": expected_deleted,
            "renamed_paths": sorted(renames, key=lambda row: (row["from"], row["to"])),
            "reconstructed_tree_sha256": digest,
            "reconstructed_tree_file_count": count,
            "reconstructed_tree_total_bytes": total,
        })
    return result


def validate_package_family(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve(); forge_root = forge_root.resolve()
    source, relative = _project_file(project_root, forge_root, source_path, "Package-family contract")
    raw = read_json(source, None, strict=False)
    if not isinstance(raw, dict):
        raise ValueError("Package-family contract must be valid UTF-8 JSON containing one object.")
    if raw.get("schema") != PACKAGE_FAMILY_SCHEMA:
        raise ValueError("Package-family contract must use schema 1.")
    family_id = _required(raw.get("family_id"), "family_id")
    authority = _required(raw.get("authority"), "authority")
    lineage_id = _required(raw.get("lineage_id"), "lineage_id")
    lineage = _active_lineage(project_root, lineage_id)
    release_version = _required(raw.get("release_version"), "release_version")
    build_id = _required(raw.get("build_id"), "build_id")
    if release_version != str(lineage.get("declared_version", "")) or build_id != str(lineage.get("build_id", "")):
        raise ValueError("Package family release version/build ID do not match the active lineage.")
    raw_artifacts = raw.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ValueError("Package family requires at least one exact ZIP artifact.")
    seen: set[str] = set(); artifacts: dict[str, dict[str, Any]] = {}; trees: dict[str, dict[str, Any]] = {}; paths: dict[str, Path] = {}
    controls = [relative]
    for row in raw_artifacts:
        normalized, tree, path = _artifact(project_root, forge_root, row, seen)
        artifacts[normalized["artifact_id"]] = normalized; trees[normalized["artifact_id"]] = tree; paths[normalized["artifact_id"]] = path
        controls.append(normalized["path"])
    result_candidates = [artifact for artifact in artifacts.values() if artifact["tree_sha256"] == str(lineage.get("current_tree_sha256", ""))]
    if not result_candidates:
        raise ValueError("Package family contains no artifact whose normalized tree equals the active lineage tree.")
    outer = _validate_outer_bundles(raw.get("outer_bundles"), artifacts, paths)
    deltas = _validate_deltas(raw.get("deltas"), artifacts, trees, paths)
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    normalized = {
        "schema": 1,
        "family_id": family_id,
        "authority": authority,
        "lineage_id": lineage_id,
        "release_version": release_version,
        "build_id": build_id,
        "artifacts": [artifacts[key] for key in sorted(artifacts)],
        "lineage_result_artifact_ids": sorted(row["artifact_id"] for row in result_candidates),
        "outer_bundles": outer,
        "deltas": deltas,
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "family": normalized,
        "contract_source": relative,
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "control_paths": sorted(set(controls)),
    }


def record_package_family(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_package_family(project_root, forge_root, source_path)
    family = validated["family"]
    settings = load_settings(project_root)
    records = settings.get("package_families", {}) if isinstance(settings.get("package_families"), dict) else {}
    family_id = family["family_id"]
    if family_id in records and str(records[family_id].get("status", "")) != "retired":
        raise ValueError(f"Package family ID is already recorded: {family_id}")
    active = [key for key, value in records.items() if isinstance(value, dict) and str(value.get("lineage_id", "")) == family["lineage_id"] and str(value.get("status", "")) == "active"]
    if active:
        raise ValueError("A package family is already active for this lineage. Retire it first: " + ", ".join(sorted(active)))
    record = {**family, "status": "active", "recorded_utc": utc_now(), "contract_source": validated["contract_source"], "source_fingerprint": validated["source_fingerprint"], "contract_fingerprint": validated["contract_fingerprint"], "control_paths": validated["control_paths"]}
    records[family_id] = record
    controls = settings.get("package_family_control_paths", []) if isinstance(settings.get("package_family_control_paths"), list) else []
    lineage_controls = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    for path in validated["control_paths"]:
        if path not in controls: controls.append(path)
        if path not in lineage_controls: lineage_controls.append(path)
    settings["package_families"] = records; settings["package_family_control_paths"] = sorted(controls); settings["lineage_control_paths"] = sorted(lineage_controls)
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "package-family-recorded", {"family_id": family_id, "lineage_id": family["lineage_id"], "artifact_count": len(family["artifacts"]), "delta_count": len(family["deltas"]), "outer_bundle_count": len(family["outer_bundles"]), "truth_boundary": PACKAGE_FAMILY_TRUTH_BOUNDARY}, source=family["authority"])
    record["event_id"] = event["id"]; records[family_id] = record; settings["package_families"] = records; write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_package_family(project_root: Path, family_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    project_root = project_root.resolve(); family_id = str(family_id).strip(); reason = str(reason).strip(); authority = str(authority).strip()
    if len(reason) < 20: raise ValueError("Package family retirement requires a durable reason of at least 20 characters.")
    if not authority: raise ValueError("Package family retirement requires authority.")
    settings = load_settings(project_root); records = settings.get("package_families", {}) if isinstance(settings.get("package_families"), dict) else {}
    record = records.get(family_id)
    if not isinstance(record, dict) or str(record.get("status", "")) != "active": raise ValueError(f"Active package family is not recorded: {family_id}")
    updated = dict(record); updated.update({"status": "retired", "retired_utc": utc_now(), "retired_reason": reason, "retired_by": authority})
    records[family_id] = updated; settings["package_families"] = records; write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "package-family-retired", {"family_id": family_id, "lineage_id": updated.get("lineage_id", ""), "reason": reason}, source=authority)
    return updated


def package_family_summary(project_root: Path, forge_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    settings = load_settings(project_root)
    records = settings.get("package_families", {}) if isinstance(settings.get("package_families"), dict) else {}
    lineages = lineage_records(project_root)
    active_lineages = [(key, value) for key, value in lineages.items() if isinstance(value, dict) and str(value.get("status", "")) == "active"]
    if len(active_lineages) != 1:
        return {"schema": 1, "status": "BLOCKED" if active_lineages else "NOT_DECLARED", "reason": "Package-family identity requires exactly one active lineage.", "active_family_id": "", "truth_boundary": PACKAGE_FAMILY_TRUTH_BOUNDARY}
    lineage_id = active_lineages[0][0]
    current: list[tuple[str, dict[str, Any]]] = []
    for family_id, stored in records.items():
        if not isinstance(stored, dict) or str(stored.get("status", "")) != "active" or str(stored.get("lineage_id", "")) != lineage_id:
            continue
        bound = fingerprint_bound_status(project_root, stored, active_status="active", changed_status="approval-required", missing_reason="The package-family contract source is missing.", changed_reason="The package-family contract changed and must be recorded again.")
        if str(bound.get("lifecycle_status", "")) != "active":
            current.append((str(family_id), bound)); continue
        try:
            validated = validate_package_family(project_root, forge_root, str(stored.get("contract_source", "")))
        except ValueError as exc:
            contradicted = dict(bound); contradicted["lifecycle_status"] = "contradicted"; contradicted["reason"] = str(exc); current.append((str(family_id), contradicted)); continue
        if validated["contract_fingerprint"] != str(stored.get("contract_fingerprint", "")):
            changed = dict(bound); changed["lifecycle_status"] = "approval-required"; changed["reason"] = "The normalized package family changed and must be recorded again."; current.append((str(family_id), changed)); continue
        current.append((str(family_id), dict(bound)))
    if not current:
        return {"schema": 1, "status": "NOT_DECLARED", "reason": "The active lineage has no exact package-family contract.", "active_lineage_id": lineage_id, "active_family_id": "", "next_action": "Record one package-family contract in a separate Adopt operation.", "truth_boundary": PACKAGE_FAMILY_TRUTH_BOUNDARY}
    if len(current) != 1:
        return {"schema": 1, "status": "CONTRADICTED", "reason": "More than one package family is active for the current lineage.", "active_lineage_id": lineage_id, "active_family_id": "", "truth_boundary": PACKAGE_FAMILY_TRUTH_BOUNDARY}
    family_id, record = current[0]
    if str(record.get("lifecycle_status", "active")) != "active":
        return {"schema": 1, "status": "CONTRADICTED", "reason": str(record.get("reason", "The package family is stale or contradicted.")), "active_lineage_id": lineage_id, "active_family_id": family_id, "truth_boundary": PACKAGE_FAMILY_TRUTH_BOUNDARY}
    return {"schema": 1, "status": "CURRENT", "reason": "Exact package bytes, package-family relationships, outer-bundle members, and declared delta reconstructions are current.", "active_lineage_id": lineage_id, "active_family_id": family_id, "artifact_count": len(record.get("artifacts", [])), "delta_count": len(record.get("deltas", [])), "outer_bundle_count": len(record.get("outer_bundles", [])), "lineage_result_artifact_ids": record.get("lineage_result_artifact_ids", []), "truth_boundary": PACKAGE_FAMILY_TRUTH_BOUNDARY}

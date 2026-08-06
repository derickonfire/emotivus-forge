from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .common import normalize_rel, read_json, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .orientation import iter_project_files
from .paths import ForgePaths
from .state import load_settings

LINEAGE_SCHEMA = 1
MERGE_CANDIDATE_SCHEMA = 1
MAX_TREE_FILES = 20_000
MAX_TREE_BYTES = 4_000_000_000
MAX_ARCHIVE_MEMBER_BYTES = 1_000_000_000

LINEAGE_TRUTH_BOUNDARY = (
    "Forge proves equality or inequality of the supplied package bytes and normalized regular-file tree bytes. "
    "It does not prove authorship, legal ownership, semantic compatibility, merge correctness, or that a display version is unique outside the recorded project history."
)
MERGE_TRUTH_BOUNDARY = (
    "A merge-candidate record preserves exact ancestry claims and path-level byte differences. It does not apply the branch, "
    "choose conflict resolutions, establish feature correctness, or authorize the resulting project tree."
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
        raise ValueError(f"Lineage contract requires {label}.")
    return text


def _hex_digest(value: Any, label: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be an exact lowercase SHA-256 digest.")
    return text


def _project_file(project_root: Path, forge_root: Path, raw_path: str | Path, label: str) -> tuple[Path, str]:
    path = Path(raw_path)
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


def _canonical_tree(manifest: dict[str, dict[str, Any]]) -> tuple[str, int, int]:
    rows: list[tuple[str, int, str]] = []
    total_bytes = 0
    for relative in sorted(manifest):
        item = manifest[relative]
        size = int(item.get("size", 0) or 0)
        digest = _hex_digest(item.get("sha256", ""), f"Tree member {relative} digest")
        rows.append((relative, size, digest))
        total_bytes += size
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(rows), total_bytes


def exact_directory_tree(
    project_root: Path,
    forge_root: Path,
    *,
    exclude_paths: Iterable[str] = (),
    max_files: int = MAX_TREE_FILES,
    max_total_bytes: int = MAX_TREE_BYTES,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    excluded = {normalize_rel(value).strip("/") for value in exclude_paths if normalize_rel(value).strip("/")}
    manifest: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for index, path in enumerate(iter_project_files(project_root, forge_root, max_files=max_files + 1, max_depth=32)):
        if index >= max_files:
            raise ValueError(f"Exact tree identity exceeds the bounded file limit of {max_files} files.")
        relative = normalize_rel(path.relative_to(project_root))
        if relative in excluded:
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ValueError(f"Exact tree identity could not stat {relative}: {exc}") from exc
        if size < 0 or total_bytes + size > max_total_bytes:
            raise ValueError(f"Exact tree identity exceeds the bounded byte limit of {max_total_bytes} bytes.")
        try:
            digest = sha256_file(path)
        except OSError as exc:
            raise ValueError(f"Exact tree identity could not hash {relative}: {exc}") from exc
        manifest[relative] = {"size": size, "sha256": digest}
        total_bytes += size
    tree_sha256, file_count, canonical_bytes = _canonical_tree(manifest)
    return {
        "schema": 1,
        "tree_sha256": tree_sha256,
        "file_count": file_count,
        "total_bytes": canonical_bytes,
        "files": manifest,
        "excluded_control_paths": sorted(excluded),
        "exact": True,
        "normalization": "sorted UTF-8 relative paths + byte length + SHA-256; mtimes and ZIP metadata excluded",
    }


def _safe_archive_name(raw_name: str) -> str:
    value = raw_name.replace("\\", "/")
    pure = PurePosixPath(value)
    if not value or value.startswith("/") or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Archive contains an unsafe member path: {raw_name}")
    normalized = "/".join(part for part in pure.parts if part not in {"", "."})
    if not normalized:
        raise ValueError(f"Archive contains an empty member path: {raw_name}")
    return normalized


def exact_zip_tree(
    archive_path: Path,
    *,
    strip_prefix: str = "",
    exclude_paths: Iterable[str] = (),
    max_files: int = MAX_TREE_FILES,
    max_total_bytes: int = MAX_TREE_BYTES,
) -> dict[str, Any]:
    strip = normalize_rel(strip_prefix).strip("/")
    excluded = {normalize_rel(value).strip("/") for value in exclude_paths if normalize_rel(value).strip("/")}
    manifest: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    seen_raw: set[str] = set()
    try:
        handle = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Lineage package is not a readable ZIP archive: {archive_path.name}: {exc}") from exc
    with handle:
        infos = handle.infolist()
        for info in infos:
            raw_name = _safe_archive_name(info.filename)
            if raw_name in seen_raw:
                raise ValueError(f"Archive contains duplicate member name: {raw_name}")
            seen_raw.add(raw_name)
            if info.flag_bits & 0x1:
                raise ValueError(f"Archive contains encrypted member: {raw_name}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                raise ValueError(f"Archive contains a symbolic-link member: {raw_name}")
            if info.is_dir() or raw_name.endswith("/"):
                continue
            if strip:
                if raw_name == strip:
                    raise ValueError(f"Archive strip_prefix points to a file, not a directory: {strip}")
                prefix = strip + "/"
                if not raw_name.startswith(prefix):
                    raise ValueError(f"Archive member {raw_name} is outside declared strip_prefix {strip}.")
                relative = raw_name[len(prefix):]
            else:
                relative = raw_name
            relative = normalize_rel(relative).strip("/")
            if not relative or relative in excluded:
                continue
            if relative in manifest:
                raise ValueError(f"Archive normalization creates duplicate project path: {relative}")
            if len(manifest) >= max_files:
                raise ValueError(f"Archive tree identity exceeds the bounded file limit of {max_files} files.")
            if info.file_size < 0 or info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                raise ValueError(f"Archive member exceeds the bounded per-file limit: {relative}")
            if total_bytes + info.file_size > max_total_bytes:
                raise ValueError(f"Archive tree identity exceeds the bounded byte limit of {max_total_bytes} bytes.")
            digest = hashlib.sha256()
            read_bytes = 0
            try:
                with handle.open(info, "r") as member:
                    while chunk := member.read(1024 * 1024):
                        digest.update(chunk)
                        read_bytes += len(chunk)
                        if read_bytes > info.file_size or read_bytes > MAX_ARCHIVE_MEMBER_BYTES:
                            raise ValueError(f"Archive member expanded beyond its declared bounded size: {relative}")
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ValueError(f"Could not read archive member {relative}: {exc}") from exc
            if read_bytes != info.file_size:
                raise ValueError(f"Archive member byte length contradicted ZIP metadata: {relative}")
            manifest[relative] = {"size": read_bytes, "sha256": digest.hexdigest()}
            total_bytes += read_bytes
    tree_sha256, file_count, canonical_bytes = _canonical_tree(manifest)
    return {
        "schema": 1,
        "tree_sha256": tree_sha256,
        "file_count": file_count,
        "total_bytes": canonical_bytes,
        "files": manifest,
        "strip_prefix": strip,
        "excluded_control_paths": sorted(excluded),
        "exact": True,
        "normalization": "sorted UTF-8 relative paths + uncompressed byte length + SHA-256; ZIP metadata excluded",
    }


def _archive_identity(
    project_root: Path,
    forge_root: Path,
    raw: Any,
    label: str,
) -> tuple[dict[str, Any], str]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object.")
    path, relative = _project_file(project_root, forge_root, _required(raw.get("path"), f"{label}.path"), label)
    expected_sha = _hex_digest(raw.get("sha256"), f"{label}.sha256")
    expected_bytes = raw.get("bytes")
    if not isinstance(expected_bytes, int) or expected_bytes < 1:
        raise ValueError(f"{label}.bytes must be a positive integer.")
    actual_bytes = path.stat().st_size
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha or actual_bytes != expected_bytes:
        raise ValueError(
            f"{label} exact package identity does not match. Expected {expected_sha}/{expected_bytes}, "
            f"observed {actual_sha}/{actual_bytes}."
        )
    strip_prefix = str(raw.get("strip_prefix", "")).strip()
    tree = exact_zip_tree(path, strip_prefix=strip_prefix)
    expected_tree = _hex_digest(raw.get("tree_sha256"), f"{label}.tree_sha256")
    expected_count = raw.get("tree_file_count")
    if tree["tree_sha256"] != expected_tree:
        raise ValueError(f"{label} normalized tree digest does not match the archive bytes.")
    if not isinstance(expected_count, int) or expected_count < 0 or expected_count != tree["file_count"]:
        raise ValueError(f"{label}.tree_file_count does not match the archive tree.")
    result = {
        "path": relative,
        "sha256": actual_sha,
        "bytes": actual_bytes,
        "declared_version": _required(raw.get("declared_version"), f"{label}.declared_version"),
        "build_id": _required(raw.get("build_id"), f"{label}.build_id"),
        "strip_prefix": tree["strip_prefix"],
        "tree_sha256": tree["tree_sha256"],
        "tree_file_count": tree["file_count"],
        "tree_total_bytes": tree["total_bytes"],
    }
    return result, relative


def _load_contract(project_root: Path, forge_root: Path, source_path: str | Path, label: str) -> tuple[dict[str, Any], Path, str]:
    path, relative = _project_file(project_root, forge_root, source_path, label)
    raw = read_json(path, None, strict=False)
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be valid UTF-8 JSON containing one object.")
    return raw, path, relative


def _diff_manifests(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = before.get("files", {}) if isinstance(before.get("files"), dict) else {}
    after_files = after.get("files", {}) if isinstance(after.get("files"), dict) else {}
    before_paths = set(before_files)
    after_paths = set(after_files)
    added = sorted(after_paths - before_paths)
    deleted = sorted(before_paths - after_paths)
    modified = sorted(
        path for path in before_paths & after_paths
        if before_files[path].get("sha256") != after_files[path].get("sha256")
        or int(before_files[path].get("size", 0) or 0) != int(after_files[path].get("size", 0) or 0)
    )
    deleted_by_digest: dict[tuple[str, int], list[str]] = {}
    for path in deleted:
        item = before_files[path]
        deleted_by_digest.setdefault((str(item.get("sha256", "")), int(item.get("size", 0) or 0)), []).append(path)
    added_by_digest: dict[tuple[str, int], list[str]] = {}
    for path in added:
        item = after_files[path]
        added_by_digest.setdefault((str(item.get("sha256", "")), int(item.get("size", 0) or 0)), []).append(path)
    renames: list[dict[str, str]] = []
    for key in sorted(set(deleted_by_digest) & set(added_by_digest)):
        old_paths = deleted_by_digest[key]
        new_paths = added_by_digest[key]
        if len(old_paths) == 1 and len(new_paths) == 1:
            renames.append({"from": old_paths[0], "to": new_paths[0], "sha256": key[0]})
    return {
        "count": len(added) + len(deleted) + len(modified),
        "added": added,
        "deleted": deleted,
        "modified": modified,
        "renamed": renames,
        "paths": sorted(set(added) | set(deleted) | set(modified)),
    }


def validate_lineage_contract(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    raw, source, relative = _load_contract(project_root, forge_root, source_path, "Lineage contract")
    if raw.get("schema") != LINEAGE_SCHEMA:
        raise ValueError("Lineage contract must use schema 1.")
    lineage_id = _required(raw.get("lineage_id"), "lineage_id")
    authority = _required(raw.get("authority"), "authority")
    declared_version = _required(raw.get("declared_version"), "declared_version")
    build_id = _required(raw.get("build_id"), "build_id")
    relationship = str(raw.get("relationship", "continuation")).strip().lower()
    if relationship not in {"initial", "continuation", "fork", "supersession"}:
        raise ValueError("Lineage relationship must be initial, continuation, fork, or supersession.")
    parent_raw = raw.get("parent")
    parent: dict[str, Any] = {}
    parent_path = ""
    if relationship == "initial":
        if parent_raw is not None and parent_raw != {}:
            raise ValueError("An initial lineage must not declare a parent package.")
    else:
        parent, parent_path = _archive_identity(project_root, forge_root, parent_raw, "Lineage parent package")
    current_raw = raw.get("current")
    if not isinstance(current_raw, dict):
        raise ValueError("Lineage contract requires current tree identity.")
    expected_current_tree = _hex_digest(current_raw.get("tree_sha256"), "current.tree_sha256")
    expected_current_count = current_raw.get("tree_file_count")
    if not isinstance(expected_current_count, int) or expected_current_count < 0:
        raise ValueError("current.tree_file_count must be a non-negative integer.")
    exclusions = [relative]
    if parent_path:
        exclusions.append(parent_path)
    settings = load_settings(project_root)
    control_paths = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    current_tree = exact_directory_tree(project_root, forge_root, exclude_paths=[*control_paths, *exclusions])
    if current_tree["tree_sha256"] != expected_current_tree or current_tree["file_count"] != expected_current_count:
        raise ValueError(
            "The current project tree does not match the lineage contract. "
            f"Expected {expected_current_tree}/{expected_current_count}, observed "
            f"{current_tree['tree_sha256']}/{current_tree['file_count']}."
        )
    collision = raw.get("collision_declaration", {})
    if collision is None:
        collision = {}
    if not isinstance(collision, dict):
        raise ValueError("collision_declaration must be an object when present.")
    collision_type = str(collision.get("type", "")).strip().lower()
    if collision_type and collision_type not in {"fork", "supersession"}:
        raise ValueError("collision_declaration.type must be fork or supersession.")
    collision_reason = str(collision.get("reason", "")).strip()
    collides_with_raw = collision.get("collides_with", [])
    if not isinstance(collides_with_raw, list):
        raise ValueError("collision_declaration.collides_with must be an array.")
    collides_with = sorted({_required(value, "collision_declaration.collides_with item") for value in collides_with_raw})
    if collision_type and (len(collision_reason) < 20 or not collides_with):
        raise ValueError("An explicit collision declaration requires a durable reason and at least one colliding lineage ID.")
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    normalized = {
        "schema": LINEAGE_SCHEMA,
        "lineage_id": lineage_id,
        "authority": authority,
        "declared_version": declared_version,
        "build_id": build_id,
        "relationship": relationship,
        "parent": parent,
        "current": {
            "tree_sha256": current_tree["tree_sha256"],
            "tree_file_count": current_tree["file_count"],
            "tree_total_bytes": current_tree["total_bytes"],
        },
        "collision_declaration": {
            "type": collision_type,
            "reason": collision_reason,
            "collides_with": collides_with,
        },
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": normalized,
        "contract_source": relative,
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "current_manifest": current_tree,
        "excluded_control_paths": exclusions,
    }


def record_project_lineage(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_lineage_contract(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    control_paths = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    for path in validated["excluded_control_paths"]:
        if path not in control_paths:
            control_paths.append(path)
    settings["lineage_control_paths"] = sorted(control_paths)
    records = settings.get("project_lineages", {}) if isinstance(settings.get("project_lineages"), dict) else {}
    lineage_id = contract["lineage_id"]
    if lineage_id in records and str(records[lineage_id].get("status", "")) != "retired":
        raise ValueError(f"Lineage ID is already recorded: {lineage_id}")
    collisions = [
        existing_id for existing_id, existing in records.items()
        if isinstance(existing, dict)
        and str(existing.get("declared_version", "")) == contract["declared_version"]
        and str(existing.get("current_tree_sha256", "")) != contract["current"]["tree_sha256"]
        and str(existing.get("status", "")) != "retired"
    ]
    declaration = contract.get("collision_declaration", {})
    declared_collision_ids = set(declaration.get("collides_with", [])) if isinstance(declaration, dict) else set()
    if collisions and (not declaration.get("type") or not set(collisions).issubset(declared_collision_ids)):
        raise ValueError(
            "The declared version already maps to a different exact tree. Record an explicit fork or supersession "
            f"collision declaration covering: {', '.join(sorted(collisions))}."
        )
    previous_active = [
        existing_id for existing_id, existing in records.items()
        if isinstance(existing, dict) and str(existing.get("status", "")) == "active"
    ]
    if len(previous_active) > 1:
        raise ValueError("Project lineage state is contradicted: more than one active lineage exists.")
    recorded_utc = utc_now()
    record = {
        "schema": 1,
        "status": "active",
        "recorded_utc": recorded_utc,
        "lineage_id": lineage_id,
        "authority": contract["authority"],
        "declared_version": contract["declared_version"],
        "build_id": contract["build_id"],
        "relationship": contract["relationship"],
        "parent": contract["parent"],
        "current_tree_sha256": contract["current"]["tree_sha256"],
        "current_tree_file_count": contract["current"]["tree_file_count"],
        "current_tree_total_bytes": contract["current"]["tree_total_bytes"],
        "contract_source": validated["contract_source"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "excluded_control_paths": validated["excluded_control_paths"],
        "collision_declaration": contract["collision_declaration"],
        "supersedes_lineage_ids": previous_active,
        "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
    }
    for existing_id in previous_active:
        existing = dict(records[existing_id])
        existing["status"] = "superseded"
        existing["superseded_utc"] = recorded_utc
        existing["superseded_by"] = lineage_id
        records[existing_id] = existing
    records[lineage_id] = record
    settings["project_lineages"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "project-lineage-recorded", {
        "lineage_id": lineage_id,
        "declared_version": contract["declared_version"],
        "build_id": contract["build_id"],
        "relationship": contract["relationship"],
        "parent_package_sha256": contract["parent"].get("sha256", ""),
        "parent_tree_sha256": contract["parent"].get("tree_sha256", ""),
        "current_tree_sha256": contract["current"]["tree_sha256"],
        "collides_with": collisions,
        "collision_declaration": contract["collision_declaration"],
        "supersedes_lineage_ids": previous_active,
        "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
    }, source=contract["authority"])
    record["event_id"] = event["id"]
    records[lineage_id] = record
    settings["project_lineages"] = records
    write_json(ForgePaths(project_root).settings, settings)
    return record


def lineage_records(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root.resolve())
    raw = settings.get("project_lineages", {}) if isinstance(settings.get("project_lineages"), dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for identifier, record in raw.items():
        if not isinstance(record, dict):
            continue
        if str(record.get("status", "")) == "active":
            result[str(identifier)] = fingerprint_bound_status(
                project_root.resolve(), record,
                changed_status="approval-required",
                missing_reason="The project-lineage contract source is missing.",
                changed_reason="The project-lineage contract changed and must be recorded again.",
            )
        else:
            result[str(identifier)] = dict(record)
    return result


def assess_project_lineage(project_root: Path, forge_root: Path) -> dict[str, Any]:
    records = lineage_records(project_root)
    active = [(identifier, record) for identifier, record in records.items() if str(record.get("status", "")) in {"active", "approval-required"}]
    collisions: dict[str, list[str]] = {}
    by_version: dict[str, dict[str, list[str]]] = {}
    for identifier, record in records.items():
        if str(record.get("status", "")) == "retired":
            continue
        version = str(record.get("declared_version", ""))
        tree = str(record.get("current_tree_sha256", ""))
        by_version.setdefault(version, {}).setdefault(tree, []).append(identifier)
    for version, trees in by_version.items():
        if version and len(trees) > 1:
            collisions[version] = sorted(identifier for ids in trees.values() for identifier in ids)
    if not active:
        return {
            "schema": 1,
            "status": "NOT_RECORDED",
            "active_lineage_id": "",
            "declared_version": "",
            "build_id": "",
            "current_tree_sha256": "",
            "version_collisions": collisions,
            "working_tree_current": False,
            "quarantined": True,
            "reason": "No exact project lineage has been recorded.",
            "next_action": "Record an exact initial or parent-bound project lineage before relying on continuation ancestry.",
            "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
        }
    if len(active) != 1:
        return {
            "schema": 1,
            "status": "CONTRADICTED",
            "active_lineage_id": "",
            "version_collisions": collisions,
            "working_tree_current": False,
            "quarantined": True,
            "reason": f"Project lineage state contains {len(active)} active or approval-required records.",
            "next_action": "Preserve state and reconcile the lineage registry before adopting or shipping another tree.",
            "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
        }
    identifier, record = active[0]
    if str(record.get("status", "")) != "active":
        return {
            "schema": 1,
            "status": "APPROVAL_REQUIRED",
            "active_lineage_id": identifier,
            "declared_version": record.get("declared_version", ""),
            "build_id": record.get("build_id", ""),
            "current_tree_sha256": record.get("current_tree_sha256", ""),
            "version_collisions": collisions,
            "working_tree_current": False,
            "quarantined": True,
            "reason": str(record.get("reason", "The lineage source requires renewed authority.")),
            "next_action": "Restore or intentionally re-record the exact lineage contract before relying on ancestry claims.",
            "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
        }
    try:
        settings = load_settings(project_root)
        control_paths = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
        current = exact_directory_tree(project_root, forge_root, exclude_paths=[*record.get("excluded_control_paths", []), *control_paths])
    except ValueError as exc:
        return {
            "schema": 1,
            "status": "BLOCKED",
            "active_lineage_id": identifier,
            "declared_version": record.get("declared_version", ""),
            "build_id": record.get("build_id", ""),
            "current_tree_sha256": record.get("current_tree_sha256", ""),
            "version_collisions": collisions,
            "working_tree_current": False,
            "quarantined": True,
            "reason": str(exc),
            "next_action": "Resolve the exact tree-identity blockage before relying on lineage state.",
            "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
        }
    matches = current["tree_sha256"] == str(record.get("current_tree_sha256", ""))
    status = "CURRENT" if matches else "WORKING_CHANGES"
    return {
        "schema": 1,
        "status": status,
        "active_lineage_id": identifier,
        "declared_version": record.get("declared_version", ""),
        "build_id": record.get("build_id", ""),
        "parent": record.get("parent", {}),
        "recorded_tree_sha256": record.get("current_tree_sha256", ""),
        "current_tree_sha256": current["tree_sha256"],
        "current_tree_file_count": current["file_count"],
        "version_collisions": collisions,
        "working_tree_current": matches,
        "quarantined": not matches,
        "reason": (
            "The current exact normalized project tree matches the active lineage record."
            if matches else "The working tree differs from the active lineage and remains ordinary unrecorded development state."
        ),
        "next_action": (
            "Continue from this exact lineage or record incoming work as a merge candidate before applying it."
            if matches else "Run scoped checks, review the resulting exact tree, then record a new parent-bound lineage before release claims."
        ),
        "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
    }


def validate_merge_candidate(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    raw, source, relative = _load_contract(project_root, forge_root, source_path, "Merge-candidate contract")
    if raw.get("schema") != MERGE_CANDIDATE_SCHEMA:
        raise ValueError("Merge-candidate contract must use schema 1.")
    candidate_id = _required(raw.get("candidate_id"), "candidate_id")
    authority = _required(raw.get("authority"), "authority")
    declared_version = _required(raw.get("declared_version"), "declared_version")
    build_id = _required(raw.get("build_id"), "build_id")
    parent, parent_path = _archive_identity(project_root, forge_root, raw.get("parent"), "Merge candidate parent package")
    incoming, incoming_path = _archive_identity(project_root, forge_root, raw.get("incoming"), "Merge candidate incoming package")
    if parent["sha256"] == incoming["sha256"]:
        raise ValueError("Merge candidate parent and incoming package identities must differ.")
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    normalized = {
        "schema": 1,
        "candidate_id": candidate_id,
        "authority": authority,
        "declared_version": declared_version,
        "build_id": build_id,
        "parent": parent,
        "incoming": incoming,
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": normalized,
        "contract_source": relative,
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "parent_manifest": exact_zip_tree(project_root / parent_path, strip_prefix=parent["strip_prefix"]),
        "incoming_manifest": exact_zip_tree(project_root / incoming_path, strip_prefix=incoming["strip_prefix"]),
        "excluded_control_paths": [relative, parent_path, incoming_path],
    }


def record_merge_candidate(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_merge_candidate(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    candidates = settings.get("merge_candidates", {}) if isinstance(settings.get("merge_candidates"), dict) else {}
    candidate_id = contract["candidate_id"]
    if candidate_id in candidates and str(candidates[candidate_id].get("status", "")) not in {"rejected", "retired"}:
        raise ValueError(f"Merge candidate ID is already recorded: {candidate_id}")
    records = lineage_records(project_root)
    active = [(identifier, record) for identifier, record in records.items() if str(record.get("status", "")) == "active"]
    if len(active) != 1:
        raise ValueError("Merge candidate recording requires one current active exact project lineage.")
    active_id, active_record = active[0]
    control_paths = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    candidate_controls = [*control_paths, *validated["excluded_control_paths"]]
    authority_tree = exact_directory_tree(
        project_root,
        forge_root,
        exclude_paths=[*active_record.get("excluded_control_paths", []), *candidate_controls],
    )
    recorded_authority_tree = str(active_record.get("current_tree_sha256", ""))
    lineage = {
        "active_lineage_id": active_id,
        "declared_version": active_record.get("declared_version", ""),
        "recorded_tree_sha256": recorded_authority_tree,
    }
    if authority_tree["tree_sha256"] != recorded_authority_tree:
        raise ValueError("Control-file exclusions changed the authority tree identity while recording the merge candidate.")
    parent_matches_authority = contract["parent"]["tree_sha256"] == recorded_authority_tree
    candidate_status = "lineage-matched-candidate" if parent_matches_authority else "merge-candidate"
    same_version_collision = (
        contract["declared_version"] == str(lineage.get("declared_version", ""))
        and contract["incoming"]["tree_sha256"] != recorded_authority_tree
    )
    parent_to_incoming = _diff_manifests(validated["parent_manifest"], validated["incoming_manifest"])
    authority_to_incoming = _diff_manifests(authority_tree, validated["incoming_manifest"])
    recorded_utc = utc_now()
    record = {
        "schema": 1,
        "status": candidate_status,
        "lifecycle_status": "active",
        "recorded_utc": recorded_utc,
        "candidate_id": candidate_id,
        "authority": contract["authority"],
        "declared_version": contract["declared_version"],
        "build_id": contract["build_id"],
        "authority_lineage_id": lineage["active_lineage_id"],
        "authority_tree_sha256": recorded_authority_tree,
        "parent_matches_authority": parent_matches_authority,
        "same_version_collision": same_version_collision,
        "parent": contract["parent"],
        "incoming": contract["incoming"],
        "parent_to_incoming": parent_to_incoming,
        "authority_to_incoming": authority_to_incoming,
        "contract_source": validated["contract_source"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "resolution": {},
        "truth_boundary": MERGE_TRUTH_BOUNDARY,
    }
    candidates[candidate_id] = record
    for path in validated["excluded_control_paths"]:
        if path not in control_paths:
            control_paths.append(path)
    settings["lineage_control_paths"] = sorted(control_paths)
    settings["merge_candidates"] = candidates
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "merge-candidate-recorded", {
        "candidate_id": candidate_id,
        "status": candidate_status,
        "authority_lineage_id": lineage["active_lineage_id"],
        "authority_tree_sha256": recorded_authority_tree,
        "parent_tree_sha256": contract["parent"]["tree_sha256"],
        "incoming_tree_sha256": contract["incoming"]["tree_sha256"],
        "parent_matches_authority": parent_matches_authority,
        "same_version_collision": same_version_collision,
        "parent_to_incoming_count": parent_to_incoming["count"],
        "authority_to_incoming_count": authority_to_incoming["count"],
        "truth_boundary": MERGE_TRUTH_BOUNDARY,
    }, source=contract["authority"])
    record["event_id"] = event["id"]
    candidates[candidate_id] = record
    settings["merge_candidates"] = candidates
    write_json(ForgePaths(project_root).settings, settings)
    return record


def merge_candidate_records(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root.resolve())
    raw = settings.get("merge_candidates", {}) if isinstance(settings.get("merge_candidates"), dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for identifier, record in raw.items():
        if not isinstance(record, dict):
            continue
        if str(record.get("status", "")) in {"merge-candidate", "lineage-matched-candidate"}:
            result[str(identifier)] = fingerprint_bound_status(
                project_root.resolve(), record,
                active_status=str(record.get("status", "")),
                changed_status="approval-required",
                missing_reason="The merge-candidate contract source is missing.",
                changed_reason="The merge-candidate contract changed and must be recorded again.",
            )
        else:
            result[str(identifier)] = dict(record)
    return result


def resolve_merge_candidate(
    project_root: Path,
    candidate_id: str,
    decision: str,
    reason: str,
    *,
    authority: str = "owner",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    candidate_id = str(candidate_id).strip()
    decision = str(decision).strip().lower()
    reason = str(reason).strip()
    authority = str(authority).strip()
    if decision not in {"approved-for-reconciliation", "rejected"}:
        raise ValueError("Merge-candidate decision must be approved-for-reconciliation or rejected.")
    if len(reason) < 20:
        raise ValueError("Merge-candidate resolution requires a durable reason of at least 20 characters.")
    if not authority:
        raise ValueError("Merge-candidate resolution requires a non-empty authority.")
    settings = load_settings(project_root)
    candidates = settings.get("merge_candidates", {}) if isinstance(settings.get("merge_candidates"), dict) else {}
    record = candidates.get(candidate_id)
    if not isinstance(record, dict):
        raise ValueError(f"Merge candidate is not recorded: {candidate_id}")
    if str(record.get("status", "")) not in {"merge-candidate", "lineage-matched-candidate"}:
        raise ValueError(f"Merge candidate is not unresolved: {candidate_id}")
    current = merge_candidate_records(project_root).get(candidate_id, {})
    if str(current.get("lifecycle_status", "")) != "active":
        raise ValueError("Merge-candidate source changed or disappeared; re-record it before resolution.")
    resolved_utc = utc_now()
    updated = dict(record)
    updated["status"] = decision
    updated["lifecycle_status"] = "retired"
    updated["resolution"] = {
        "decision": decision,
        "reason": reason,
        "authority": authority,
        "resolved_utc": resolved_utc,
        "does_not_authorize_tree": True,
    }
    candidates[candidate_id] = updated
    settings["merge_candidates"] = candidates
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "merge-candidate-resolved", {
        "candidate_id": candidate_id,
        "decision": decision,
        "reason": reason,
        "authority": authority,
        "incoming_tree_sha256": updated.get("incoming", {}).get("tree_sha256", "") if isinstance(updated.get("incoming"), dict) else "",
        "does_not_authorize_tree": True,
        "truth_boundary": MERGE_TRUTH_BOUNDARY,
    }, source=authority)
    return updated


def lineage_summary(project_root: Path, forge_root: Path) -> dict[str, Any]:
    assessment = assess_project_lineage(project_root, forge_root)
    candidates = merge_candidate_records(project_root)
    unresolved = [
        record for record in candidates.values()
        if str(record.get("status", "")) in {"merge-candidate", "lineage-matched-candidate", "approval-required"}
    ]
    unmatched = [record for record in unresolved if record.get("parent_matches_authority") is False]
    collisions = [record for record in unresolved if record.get("same_version_collision") is True]
    return {
        "schema": 1,
        "status": assessment.get("status", "NOT_RECORDED"),
        "active_lineage_id": assessment.get("active_lineage_id", ""),
        "declared_version": assessment.get("declared_version", ""),
        "build_id": assessment.get("build_id", ""),
        "current_tree_sha256": assessment.get("current_tree_sha256", ""),
        "recorded_tree_sha256": assessment.get("recorded_tree_sha256", ""),
        "version_collision_count": len(assessment.get("version_collisions", {})),
        "unresolved_candidate_count": len(unresolved),
        "unmatched_parent_count": len(unmatched),
        "same_version_candidate_collision_count": len(collisions),
        "candidate_ids": sorted(str(record.get("candidate_id", "")) for record in unresolved if record.get("candidate_id")),
        "quarantined": bool(assessment.get("quarantined")) or bool(unmatched),
        "reason": assessment.get("reason", ""),
        "next_action": assessment.get("next_action", ""),
        "truth_boundary": LINEAGE_TRUTH_BOUNDARY,
    }

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, read_json, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .lineage import exact_directory_tree, exact_zip_tree, lineage_records
from .paths import ForgePaths
from .state import load_settings

MIGRATION_CATALOG_SCHEMA = 1
MIGRATION_TRUTH_BOUNDARY = (
    "Forge verifies exact migration source bytes, sequence labels, semantic IDs, recorded lineage binding, and supplied applied-ledger testimony. "
    "It does not execute migrations, inspect a live database unless project-owned evidence is supplied, prove upgrade safety, or replace rollback testing."
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
        raise ValueError(f"Migration catalog requires {label}.")
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


def _lineage_record(project_root: Path, lineage_id: str) -> dict[str, Any]:
    records = lineage_records(project_root)
    record = records.get(lineage_id)
    if not isinstance(record, dict):
        raise ValueError(f"Migration catalog lineage is not recorded: {lineage_id}")
    return record


def _source_identity(
    project_root: Path,
    forge_root: Path,
    raw: Any,
    *,
    lineage: dict[str, Any],
    contract_relative: str,
    extra_controls: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    if not isinstance(raw, dict):
        raise ValueError("Migration catalog requires source object.")
    kind = str(raw.get("kind", "project-tree")).strip().lower()
    if kind not in {"project-tree", "zip"}:
        raise ValueError("Migration source.kind must be project-tree or zip.")
    controls = [contract_relative, *(extra_controls or [])]
    if kind == "project-tree":
        settings = load_settings(project_root)
        controls.extend(str(item) for item in settings.get("migration_control_paths", []) if str(item).strip())
        controls.extend(str(item) for item in settings.get("lineage_control_paths", []) if str(item).strip())
        tree = exact_directory_tree(project_root, forge_root, exclude_paths=controls)
        recorded = str(lineage.get("current_tree_sha256", ""))
        if tree["tree_sha256"] != recorded:
            raise ValueError(
                "The current project tree does not match the lineage bound to this migration catalog. "
                f"Expected {recorded}, observed {tree['tree_sha256']}."
            )
        return {
            "kind": "project-tree",
            "tree_sha256": tree["tree_sha256"],
            "tree_file_count": tree["file_count"],
            "tree_total_bytes": tree["total_bytes"],
        }, tree["files"], controls

    package = raw.get("package")
    if not isinstance(package, dict):
        raise ValueError("Migration ZIP source requires source.package.")
    package_path, package_relative = _project_file(project_root, forge_root, package.get("path"), "source.package.path")
    controls.append(package_relative)
    expected_sha = _digest(package.get("sha256"), "source.package.sha256")
    expected_bytes = package.get("bytes")
    if not isinstance(expected_bytes, int) or expected_bytes < 1:
        raise ValueError("source.package.bytes must be a positive integer.")
    observed_sha = sha256_file(package_path)
    observed_bytes = package_path.stat().st_size
    if observed_sha != expected_sha or observed_bytes != expected_bytes:
        raise ValueError("Migration source package exact identity does not match the catalog.")
    strip_prefix = normalize_rel(str(package.get("strip_prefix", ""))).strip("/")
    tree = exact_zip_tree(package_path, strip_prefix=strip_prefix)
    expected_tree = _digest(package.get("tree_sha256"), "source.package.tree_sha256")
    expected_count = package.get("tree_file_count")
    if not isinstance(expected_count, int) or expected_count < 0:
        raise ValueError("source.package.tree_file_count must be a non-negative integer.")
    if tree["tree_sha256"] != expected_tree or tree["file_count"] != expected_count:
        raise ValueError("Migration source package tree identity does not match the catalog.")
    if tree["tree_sha256"] != str(lineage.get("current_tree_sha256", "")):
        raise ValueError("Migration source package tree does not match the recorded lineage tree.")
    return {
        "kind": "zip",
        "package": {
            "path": package_relative,
            "sha256": observed_sha,
            "bytes": observed_bytes,
            "strip_prefix": strip_prefix,
            "tree_sha256": tree["tree_sha256"],
            "tree_file_count": tree["file_count"],
            "tree_total_bytes": tree["total_bytes"],
        },
        "tree_sha256": tree["tree_sha256"],
        "tree_file_count": tree["file_count"],
        "tree_total_bytes": tree["total_bytes"],
    }, tree["files"], controls


def _normalize_entries(raw_entries: Any, source_files: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("Tracked migration catalogs require at least one entry.")
    result: list[dict[str, Any]] = []
    seen_sequences: set[str] = set()
    seen_semantics: set[str] = set()
    seen_paths: set[str] = set()
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Migration entry {index} must be an object.")
        sequence = _required(raw.get("sequence"), f"entries[{index}].sequence")
        semantic_id = _required(raw.get("semantic_id"), f"entries[{index}].semantic_id", minimum=3)
        path = normalize_rel(_required(raw.get("path"), f"entries[{index}].path")).strip("/")
        body_sha256 = _digest(raw.get("body_sha256"), f"entries[{index}].body_sha256")
        description = _required(raw.get("description"), f"entries[{index}].description", minimum=10)
        if sequence in seen_sequences:
            raise ValueError(f"Migration sequence is duplicated within one lineage catalog: {sequence}")
        if semantic_id in seen_semantics:
            raise ValueError(f"Migration semantic_id is duplicated within one lineage catalog: {semantic_id}")
        if path in seen_paths:
            raise ValueError(f"Migration path is duplicated within one lineage catalog: {path}")
        source = source_files.get(path)
        if not isinstance(source, dict):
            raise ValueError(f"Migration source path is absent from the exact lineage tree: {path}")
        if str(source.get("sha256", "")) != body_sha256:
            raise ValueError(f"Migration body digest does not match exact source bytes: {path}")
        result.append({
            "sequence": sequence,
            "semantic_id": semantic_id,
            "path": path,
            "body_sha256": body_sha256,
            "bytes": int(source.get("size", 0) or 0),
            "description": description,
        })
        seen_sequences.add(sequence)
        seen_semantics.add(semantic_id)
        seen_paths.add(path)
    return sorted(result, key=lambda item: (str(item["sequence"]), str(item["semantic_id"])))


def _normalize_observation(project_root: Path, forge_root: Path, raw: Any) -> tuple[dict[str, Any], list[str]]:
    if raw is None or raw == {}:
        return {}, []
    if not isinstance(raw, dict):
        raise ValueError("applied_observation must be an object when present.")
    evidence_path, relative = _project_file(project_root, forge_root, raw.get("evidence_path"), "applied_observation.evidence_path")
    expected_sha = _digest(raw.get("evidence_sha256"), "applied_observation.evidence_sha256")
    if sha256_file(evidence_path) != expected_sha:
        raise ValueError("Applied migration observation evidence digest does not match.")
    observed_utc = _required(raw.get("observed_utc"), "applied_observation.observed_utc")
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list):
        raise ValueError("applied_observation.entries must be an array.")
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(entries_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Applied migration entry {index} must be an object.")
        sequence = _required(item.get("sequence"), f"applied_observation.entries[{index}].sequence")
        if sequence in seen:
            raise ValueError(f"Applied migration observation repeats sequence {sequence}.")
        semantic_id = str(item.get("semantic_id", "")).strip()
        body = str(item.get("body_sha256", "")).strip().lower()
        if body:
            body = _digest(body, f"applied_observation.entries[{index}].body_sha256")
        entries.append({"sequence": sequence, "semantic_id": semantic_id, "body_sha256": body})
        seen.add(sequence)
    return {
        "evidence_path": relative,
        "evidence_sha256": expected_sha,
        "observed_utc": observed_utc,
        "entries": entries,
        "truth_boundary": _required(raw.get("truth_boundary"), "applied_observation.truth_boundary", minimum=30),
    }, [relative]


def _normalize_reconciliations(raw: Any, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if raw is None or raw == []:
        return []
    if not isinstance(raw, list):
        raise ValueError("reconciliations must be an array.")
    by_sequence = {str(item["sequence"]): item for item in entries}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Reconciliation {index} must be an object.")
        identifier = _required(item.get("reconciliation_id"), f"reconciliations[{index}].reconciliation_id")
        if identifier in seen:
            raise ValueError(f"Reconciliation ID is duplicated: {identifier}")
        collision_sequences_raw = item.get("collision_sequences")
        lineage_ids_raw = item.get("lineage_ids")
        if not isinstance(collision_sequences_raw, list) or not collision_sequences_raw:
            raise ValueError("Reconciliation requires collision_sequences.")
        if not isinstance(lineage_ids_raw, list) or len(lineage_ids_raw) < 2:
            raise ValueError("Reconciliation requires at least two lineage_ids.")
        collision_sequences = sorted({_required(value, "collision sequence") for value in collision_sequences_raw})
        lineage_ids = sorted({_required(value, "reconciliation lineage_id") for value in lineage_ids_raw})
        strategy = str(item.get("strategy", "")).strip().lower()
        if strategy != "append-after-highest":
            raise ValueError("Migration reconciliation strategy must be append-after-highest.")
        new_sequence = _required(item.get("new_sequence"), "reconciliation.new_sequence")
        semantic_id = _required(item.get("semantic_id"), "reconciliation.semantic_id", minimum=3)
        source = by_sequence.get(new_sequence)
        if not source or source.get("semantic_id") != semantic_id:
            raise ValueError("Reconciliation new_sequence and semantic_id must identify an entry in the active catalog.")
        reason = _required(item.get("reason"), "reconciliation.reason", minimum=20)
        result.append({
            "reconciliation_id": identifier,
            "collision_sequences": collision_sequences,
            "lineage_ids": lineage_ids,
            "strategy": strategy,
            "new_sequence": new_sequence,
            "semantic_id": semantic_id,
            "body_sha256": source["body_sha256"],
            "reason": reason,
        })
        seen.add(identifier)
    return sorted(result, key=lambda item: str(item["reconciliation_id"]))


def validate_migration_catalog(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    source, relative = _project_file(project_root, forge_root, source_path, "Migration catalog")
    raw = read_json(source, None, strict=False)
    if not isinstance(raw, dict):
        raise ValueError("Migration catalog must be valid UTF-8 JSON containing one object.")
    if raw.get("schema") != MIGRATION_CATALOG_SCHEMA:
        raise ValueError("Migration catalog must use schema 1.")
    inventory_id = _required(raw.get("inventory_id"), "inventory_id")
    authority = _required(raw.get("authority"), "authority")
    lineage_id = _required(raw.get("lineage_id"), "lineage_id")
    lineage = _lineage_record(project_root, lineage_id)
    engine = _required(raw.get("engine"), "engine")
    mode = str(raw.get("mode", "tracked")).strip().lower()
    if mode not in {"tracked", "none"}:
        raise ValueError("Migration catalog mode must be tracked or none.")
    pre_controls: list[str] = []
    observation_raw = raw.get("applied_observation")
    if isinstance(observation_raw, dict) and str(observation_raw.get("evidence_path", "")).strip():
        _, observation_relative = _project_file(
            project_root, forge_root, observation_raw.get("evidence_path"), "applied_observation.evidence_path"
        )
        pre_controls.append(observation_relative)
    source_identity, source_files, controls = _source_identity(
        project_root, forge_root, raw.get("source", {}), lineage=lineage,
        contract_relative=relative, extra_controls=pre_controls,
    )
    if mode == "none":
        entries: list[dict[str, Any]] = []
        if raw.get("entries") is not None and raw.get("entries") != []:
            raise ValueError("A no-migrations catalog must not contain migration entries.")
        no_migrations_reason = _required(raw.get("no_migrations_reason"), "no_migrations_reason", minimum=20)
    else:
        entries = _normalize_entries(raw.get("entries"), source_files)
        no_migrations_reason = ""
    observation, observation_controls = _normalize_observation(project_root, forge_root, raw.get("applied_observation"))
    controls.extend(observation_controls)
    reconciliations = _normalize_reconciliations(raw.get("reconciliations"), entries)
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    normalized = {
        "schema": MIGRATION_CATALOG_SCHEMA,
        "inventory_id": inventory_id,
        "authority": authority,
        "lineage_id": lineage_id,
        "declared_version": str(lineage.get("declared_version", "")),
        "build_id": str(lineage.get("build_id", "")),
        "engine": engine,
        "mode": mode,
        "source": source_identity,
        "entries": entries,
        "no_migrations_reason": no_migrations_reason,
        "applied_observation": observation,
        "reconciliations": reconciliations,
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "catalog": normalized,
        "contract_source": relative,
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "control_paths": sorted(set(controls)),
    }


def record_migration_catalog(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_migration_catalog(project_root, forge_root, source_path)
    catalog = validated["catalog"]
    settings = load_settings(project_root)
    records = settings.get("migration_catalogs", {}) if isinstance(settings.get("migration_catalogs"), dict) else {}
    inventory_id = catalog["inventory_id"]
    if inventory_id in records and str(records[inventory_id].get("status", "")) != "retired":
        raise ValueError(f"Migration catalog ID is already recorded: {inventory_id}")
    active_for_lineage = [
        key for key, value in records.items()
        if isinstance(value, dict)
        and str(value.get("lineage_id", "")) == catalog["lineage_id"]
        and str(value.get("status", "")) == "active"
    ]
    if active_for_lineage:
        raise ValueError(
            "A migration catalog is already active for this lineage. Retire it before recording a replacement: "
            + ", ".join(sorted(active_for_lineage))
        )
    recorded_utc = utc_now()
    record = {
        **catalog,
        "status": "active",
        "recorded_utc": recorded_utc,
        "contract_source": validated["contract_source"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "control_paths": validated["control_paths"],
    }
    records[inventory_id] = record
    controls = settings.get("migration_control_paths", []) if isinstance(settings.get("migration_control_paths"), list) else []
    lineage_controls = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    for path in validated["control_paths"]:
        if path not in controls:
            controls.append(path)
        if path not in lineage_controls:
            lineage_controls.append(path)
    settings["migration_catalogs"] = records
    settings["migration_control_paths"] = sorted(controls)
    settings["lineage_control_paths"] = sorted(lineage_controls)
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "migration-catalog-recorded", {
        "inventory_id": inventory_id,
        "lineage_id": catalog["lineage_id"],
        "engine": catalog["engine"],
        "mode": catalog["mode"],
        "entry_count": len(catalog["entries"]),
        "source_tree_sha256": catalog["source"]["tree_sha256"],
        "truth_boundary": MIGRATION_TRUTH_BOUNDARY,
    }, source=catalog["authority"])
    record["event_id"] = event["id"]
    records[inventory_id] = record
    settings["migration_catalogs"] = records
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_migration_catalog(project_root: Path, inventory_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    project_root = project_root.resolve()
    inventory_id = str(inventory_id).strip()
    reason = str(reason).strip()
    authority = str(authority).strip()
    if len(reason) < 20:
        raise ValueError("Migration catalog retirement requires a durable reason of at least 20 characters.")
    if not authority:
        raise ValueError("Migration catalog retirement requires authority.")
    settings = load_settings(project_root)
    records = settings.get("migration_catalogs", {}) if isinstance(settings.get("migration_catalogs"), dict) else {}
    record = records.get(inventory_id)
    if not isinstance(record, dict) or str(record.get("status", "")) != "active":
        raise ValueError(f"Active migration catalog is not recorded: {inventory_id}")
    updated = dict(record)
    updated["status"] = "retired"
    updated["retired_utc"] = utc_now()
    updated["retired_reason"] = reason
    updated["retired_by"] = authority
    records[inventory_id] = updated
    settings["migration_catalogs"] = records
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "migration-catalog-retired", {
        "inventory_id": inventory_id,
        "lineage_id": updated.get("lineage_id", ""),
        "reason": reason,
    }, source=authority)
    return updated


def _current_records(project_root: Path, forge_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root)
    raw = settings.get("migration_catalogs", {}) if isinstance(settings.get("migration_catalogs"), dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for inventory_id, stored in raw.items():
        if not isinstance(stored, dict):
            continue
        if str(stored.get("status", "")) != "active":
            result[str(inventory_id)] = dict(stored)
            continue
        bound = fingerprint_bound_status(
            project_root, stored,
            active_status="active",
            changed_status="approval-required",
            missing_reason="The migration catalog contract source is missing.",
            changed_reason="The migration catalog contract changed and must be recorded again.",
        )
        if str(bound.get("lifecycle_status", "")) != "active":
            result[str(inventory_id)] = bound
            continue
        try:
            validated = validate_migration_catalog(project_root, forge_root, str(stored.get("contract_source", "")))
        except ValueError as exc:
            contradicted = dict(bound)
            contradicted["status"] = "active"
            contradicted["lifecycle_status"] = "contradicted"
            contradicted["reason"] = str(exc)
            result[str(inventory_id)] = contradicted
            continue
        if validated["contract_fingerprint"] != str(stored.get("contract_fingerprint", "")):
            changed = dict(bound)
            changed["status"] = "active"
            changed["lifecycle_status"] = "approval-required"
            changed["reason"] = "The normalized migration catalog changed and must be recorded again."
            result[str(inventory_id)] = changed
            continue
        result[str(inventory_id)] = dict(bound)
    return result


def _collision_rows(records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    sequence_map: dict[tuple[str, str], list[dict[str, str]]] = {}
    semantic_map: dict[tuple[str, str], list[dict[str, str]]] = {}
    for inventory_id, record in records.items():
        if str(record.get("status", "")) != "active" or str(record.get("lifecycle_status", "active")) != "active":
            continue
        if str(record.get("mode", "")) != "tracked":
            continue
        engine = str(record.get("engine", ""))
        lineage_id = str(record.get("lineage_id", ""))
        for entry in record.get("entries", []) if isinstance(record.get("entries"), list) else []:
            if not isinstance(entry, dict):
                continue
            row = {
                "inventory_id": inventory_id,
                "lineage_id": lineage_id,
                "sequence": str(entry.get("sequence", "")),
                "semantic_id": str(entry.get("semantic_id", "")),
                "body_sha256": str(entry.get("body_sha256", "")),
                "path": str(entry.get("path", "")),
            }
            sequence_map.setdefault((engine, row["sequence"]), []).append(row)
            semantic_map.setdefault((engine, row["semantic_id"]), []).append(row)
    collisions: list[dict[str, Any]] = []
    for (engine, sequence), rows in sorted(sequence_map.items()):
        identities = {(row["semantic_id"], row["body_sha256"]) for row in rows}
        if len(identities) > 1:
            collisions.append({
                "kind": "sequence-number-collision",
                "engine": engine,
                "sequence": sequence,
                "lineage_ids": sorted({row["lineage_id"] for row in rows}),
                "rows": rows,
            })
    for (engine, semantic_id), rows in sorted(semantic_map.items()):
        bodies = {row["body_sha256"] for row in rows}
        if len(bodies) > 1:
            collisions.append({
                "kind": "semantic-body-collision",
                "engine": engine,
                "semantic_id": semantic_id,
                "lineage_ids": sorted({row["lineage_id"] for row in rows}),
                "rows": rows,
            })
    return collisions


def _reconciliation_covers(collision: dict[str, Any], active: dict[str, Any], all_records: dict[str, dict[str, Any]]) -> bool:
    collision_lineages = set(collision.get("lineage_ids", []))
    sequence = str(collision.get("sequence", ""))
    for row in active.get("reconciliations", []) if isinstance(active.get("reconciliations"), list) else []:
        if not isinstance(row, dict):
            continue
        if sequence and sequence not in set(row.get("collision_sequences", [])):
            continue
        if not collision_lineages.issubset(set(row.get("lineage_ids", []))):
            continue
        new_sequence = str(row.get("new_sequence", ""))
        other_numeric = [
            int(str(entry.get("sequence")))
            for record in all_records.values()
            if str(record.get("status", "")) == "active"
            for entry in (record.get("entries", []) if isinstance(record.get("entries"), list) else [])
            if str(entry.get("sequence", "")).isdigit()
            and not (record is active and str(entry.get("sequence", "")) == new_sequence)
        ]
        highest_other = max(other_numeric) if other_numeric else None
        if highest_other is not None and new_sequence.isdigit() and int(new_sequence) <= highest_other:
            continue
        return True
    return False


def _applied_statuses(active: dict[str, Any]) -> dict[str, Any]:
    if str(active.get("mode", "")) == "none":
        return {"status": "not-applicable", "counts": {}, "entries": []}
    observation = active.get("applied_observation", {}) if isinstance(active.get("applied_observation"), dict) else {}
    observed_rows = observation.get("entries", []) if isinstance(observation.get("entries"), list) else []
    observed = {str(item.get("sequence", "")): item for item in observed_rows if isinstance(item, dict)}
    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for entry in active.get("entries", []) if isinstance(active.get("entries"), list) else []:
        if not isinstance(entry, dict):
            continue
        sequence = str(entry.get("sequence", ""))
        actual = observed.get(sequence)
        if actual is None:
            state = "not-applied"
        elif not str(actual.get("semantic_id", "")) or not str(actual.get("body_sha256", "")):
            state = "number-present-body-unknown"
        elif str(actual.get("semantic_id")) == str(entry.get("semantic_id")) and str(actual.get("body_sha256")) == str(entry.get("body_sha256")):
            state = "applied-and-matching"
        else:
            state = "number-collision"
        rows.append({"sequence": sequence, "semantic_id": str(entry.get("semantic_id", "")), "state": state})
        counts[state] = counts.get(state, 0) + 1
    overall = "not-observed" if not observation else "matching"
    if counts.get("number-collision", 0):
        overall = "contradicted"
    elif counts.get("number-present-body-unknown", 0):
        overall = "body-unknown"
    elif counts.get("not-applied", 0):
        overall = "incomplete"
    return {"status": overall, "counts": counts, "entries": rows, "observation": observation}


def migration_identity_summary(project_root: Path, forge_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    records = _current_records(project_root, forge_root)
    lineages = lineage_records(project_root)
    active_lineages = [
        (identifier, record) for identifier, record in lineages.items()
        if isinstance(record, dict) and str(record.get("status", "")) == "active"
    ]
    if not active_lineages:
        return {
            "schema": 1,
            "status": "NOT_DECLARED",
            "reason": "Migration identity cannot be recorded until one exact project lineage is active.",
            "active_inventory_id": "",
            "unresolved_collision_count": 0,
            "next_action": "Record exact project lineage, then record a migration catalog or explicit no-migrations declaration.",
            "truth_boundary": MIGRATION_TRUTH_BOUNDARY,
        }
    if len(active_lineages) > 1:
        return {
            "schema": 1,
            "status": "BLOCKED",
            "reason": "Migration identity requires exactly one active project lineage; multiple active lineages are contradictory.",
            "active_inventory_id": "",
            "unresolved_collision_count": 0,
            "truth_boundary": MIGRATION_TRUTH_BOUNDARY,
        }
    active_lineage_id = active_lineages[0][0]
    active_catalogs = [
        (identifier, record) for identifier, record in records.items()
        if str(record.get("lineage_id", "")) == active_lineage_id and str(record.get("status", "")) == "active"
    ]
    if not active_catalogs:
        return {
            "schema": 1,
            "status": "NOT_DECLARED",
            "reason": "The active project lineage has no exact migration catalog or explicit no-migrations declaration.",
            "active_lineage_id": active_lineage_id,
            "active_inventory_id": "",
            "catalog_count": len(records),
            "unresolved_collision_count": 0,
            "next_action": "Record a migration catalog for the active lineage in a separate Adopt operation.",
            "truth_boundary": MIGRATION_TRUTH_BOUNDARY,
        }
    if len(active_catalogs) > 1:
        return {
            "schema": 1,
            "status": "CONTRADICTED",
            "reason": "More than one migration catalog is active for the current lineage.",
            "active_lineage_id": active_lineage_id,
            "active_inventory_id": "",
            "catalog_count": len(records),
            "unresolved_collision_count": 0,
            "truth_boundary": MIGRATION_TRUTH_BOUNDARY,
        }
    active_id, active = active_catalogs[0]
    if str(active.get("lifecycle_status", "active")) != "active":
        return {
            "schema": 1,
            "status": "CONTRADICTED",
            "reason": str(active.get("reason", "The active migration catalog is stale or contradicted.")),
            "active_lineage_id": active_lineage_id,
            "active_inventory_id": active_id,
            "catalog_count": len(records),
            "unresolved_collision_count": 0,
            "truth_boundary": MIGRATION_TRUTH_BOUNDARY,
        }
    collisions = _collision_rows(records)
    unresolved = [row for row in collisions if not _reconciliation_covers(row, active, records)]
    applied = _applied_statuses(active)
    if unresolved:
        status = "RECONCILIATION_REQUIRED"
        reason = f"{len(unresolved)} migration sequence or semantic-body collision(s) require append-after-highest reconciliation."
    elif collisions:
        status = "CURRENT_WITH_RECONCILIATION"
        reason = "Migration identities are exact and every known cross-lineage collision has an append-after-highest reconciliation entry."
    else:
        status = "CURRENT"
        reason = "The active lineage has an exact migration catalog with no known sequence or semantic-body collisions."
    if applied.get("status") == "contradicted":
        status = "CONTRADICTED"
        reason = "The supplied applied-migration observation contains a same-number/different-body collision."
    return {
        "schema": 1,
        "status": status,
        "reason": reason,
        "active_lineage_id": active_lineage_id,
        "active_inventory_id": active_id,
        "engine": active.get("engine", ""),
        "mode": active.get("mode", ""),
        "entry_count": len(active.get("entries", [])) if isinstance(active.get("entries"), list) else 0,
        "catalog_count": len([value for value in records.values() if str(value.get("status", "")) == "active"]),
        "collision_count": len(collisions),
        "unresolved_collision_count": len(unresolved),
        "collisions": collisions,
        "unresolved_collisions": unresolved,
        "applied_observation": applied,
        "next_action": (
            "Record append-after-highest reconciliation entries for every collision."
            if unresolved else
            "Replace or correct the contradicted applied-migration observation."
            if applied.get("status") == "contradicted" else
            "Run migration and upgrade evidence through the persisted-state proof layers."
        ),
        "truth_boundary": MIGRATION_TRUTH_BOUNDARY,
    }

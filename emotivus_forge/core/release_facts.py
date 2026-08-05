from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from .. import __version__
from .common import normalize_rel, read_json, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .lineage import exact_zip_tree, lineage_records
from .migration_identity import migration_identity_summary
from .package_family import package_family_summary, validate_package_family
from .paths import ForgePaths
from .state import CORE_STATE_SCHEMA, SETTINGS_SCHEMA, load_settings
from .surface_coverage import surface_coverage_summary

RELEASE_FACTS_SCHEMA = 1
FACT_SOURCES = {
    "lineage.id", "lineage.version", "lineage.build_id", "lineage.tree_sha256",
    "migration.catalog_id", "migration.status", "migration.count", "migration.max_sequence", "migration.unresolved_collision_count",
    "package.family_id", "package.result_artifact_id", "package.result_sha256", "package.result_bytes", "package.result_tree_sha256", "package.artifact_count",
    "surface.inventory_id", "surface.status", "surface.coverage_status", "surface.count", "surface.complete_count", "surface.gap_count",
    "native.status", "native.validity", "native.regression_count",
    "forge.version", "forge.settings_schema", "forge.core_state_schema", "literal",
}
RELEASE_FACTS_TRUTH_BOUNDARY = (
    "Forge resolves a bounded set of exact release facts from current recorded project state and compares project-declared visible document fields inside one exact package artifact. "
    "Forge does not understand arbitrary prose, infer undocumented facts, prove substantive correctness, authenticate the declaring authority, or guarantee that unscanned documents contain no stale statements."
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
        raise ValueError(f"Release facts require {label}.")
    return text


def _project_file(project_root: Path, forge_root: Path, raw: Any, label: str) -> tuple[Path, str]:
    path = Path(_required(raw, label))
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError(f"{label} must be a project-owned regular file outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _active_lineage(project_root: Path, lineage_id: str) -> dict[str, Any]:
    record = lineage_records(project_root).get(lineage_id)
    if not isinstance(record, dict) or str(record.get("status", "")) != "active":
        raise ValueError(f"Release facts lineage is not active: {lineage_id}")
    return record


def _active_family(project_root: Path, forge_root: Path, family_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = package_family_summary(project_root, forge_root)
    if str(summary.get("status", "")) != "CURRENT" or str(summary.get("active_family_id", "")) != family_id:
        raise ValueError("Release facts require the current exact package family.")
    records = load_settings(project_root).get("package_families", {})
    stored = records.get(family_id) if isinstance(records, dict) else None
    if not isinstance(stored, dict) or str(stored.get("status", "")) != "active":
        raise ValueError(f"Active package family is not recorded: {family_id}")
    validated = validate_package_family(project_root, forge_root, str(stored.get("contract_source", "")))
    return stored, validated["family"]


def _artifact(project_root: Path, family: dict[str, Any], artifact_id: str) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    artifacts = family.get("artifacts", []) if isinstance(family.get("artifacts"), list) else []
    artifact = next((row for row in artifacts if isinstance(row, dict) and str(row.get("artifact_id", "")) == artifact_id), None)
    if not isinstance(artifact, dict):
        raise ValueError(f"Release facts artifact is not in the active package family: {artifact_id}")
    path = (project_root / str(artifact.get("path", ""))).resolve()
    tree = exact_zip_tree(path, strip_prefix=str(artifact.get("strip_prefix", "")))
    if tree["tree_sha256"] != str(artifact.get("tree_sha256", "")):
        raise ValueError("Release facts artifact tree no longer matches the package family.")
    return artifact, path, tree


def _zip_texts(path: Path, strip_prefix: str) -> dict[str, str]:
    prefix = normalize_rel(strip_prefix).strip("/")
    result: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = normalize_rel(info.filename).strip("/")
            if prefix:
                if name == prefix:
                    continue
                marker = prefix + "/"
                if not name.startswith(marker):
                    continue
                name = name[len(marker):]
            if not name:
                continue
            if info.file_size > 5_000_000:
                continue
            try:
                result[name] = archive.read(info).decode("utf-8")
            except UnicodeDecodeError:
                continue
    return result


def _native_facts(project_root: Path) -> dict[str, Any]:
    passport = read_json(ForgePaths(project_root).passport, {}, strict=False)
    evidence = passport.get("evidence", {}) if isinstance(passport, dict) and isinstance(passport.get("evidence"), dict) else {}
    native = evidence.get("native_gate", {}) if isinstance(evidence.get("native_gate"), dict) else {}
    count = native.get("regression_count", native.get("assertion_count", native.get("check_count", 0)))
    try:
        count = int(count or 0)
    except (TypeError, ValueError):
        count = 0
    return {"status": str(native.get("status", "NOT_RUN")), "validity": str(native.get("validity", "unknown")), "regression_count": count}


def _resolve_sources(project_root: Path, forge_root: Path, lineage: dict[str, Any], family: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    migration = migration_identity_summary(project_root, forge_root)
    surface = surface_coverage_summary(project_root, forge_root)
    native = _native_facts(project_root)
    migrations = migration.get("migrations", []) if isinstance(migration.get("migrations"), list) else []
    sequences = [int(row.get("sequence", 0) or 0) for row in migrations if isinstance(row, dict)]
    counts = surface.get("coverage_counts", {}) if isinstance(surface.get("coverage_counts"), dict) else {}
    total = int(surface.get("surface_count", 0) or 0)
    complete = int(counts.get("complete", 0) or 0)
    return {
        "lineage.id": str(lineage.get("lineage_id", "")),
        "lineage.version": str(lineage.get("declared_version", "")),
        "lineage.build_id": str(lineage.get("build_id", "")),
        "lineage.tree_sha256": str(lineage.get("current", {}).get("tree_sha256", "")) if isinstance(lineage.get("current"), dict) else "",
        "migration.catalog_id": str(migration.get("active_catalog_id", "")),
        "migration.status": str(migration.get("status", "NOT_DECLARED")),
        "migration.count": int(migration.get("migration_count", len(migrations)) or 0),
        "migration.max_sequence": max(sequences, default=0),
        "migration.unresolved_collision_count": int(migration.get("unresolved_collision_count", 0) or 0),
        "package.family_id": str(family.get("family_id", "")),
        "package.result_artifact_id": str(artifact.get("artifact_id", "")),
        "package.result_sha256": str(artifact.get("sha256", "")),
        "package.result_bytes": int(artifact.get("bytes", 0) or 0),
        "package.result_tree_sha256": str(artifact.get("tree_sha256", "")),
        "package.artifact_count": len(family.get("artifacts", [])) if isinstance(family.get("artifacts"), list) else 0,
        "surface.inventory_id": str(surface.get("active_inventory_id", "")),
        "surface.status": str(surface.get("status", "NOT_DECLARED")),
        "surface.coverage_status": str(surface.get("coverage_status", "NOT_RUN")),
        "surface.count": total,
        "surface.complete_count": complete,
        "surface.gap_count": max(0, total - complete),
        "native.status": native["status"],
        "native.validity": native["validity"],
        "native.regression_count": native["regression_count"],
        "forge.version": __version__,
        "forge.settings_schema": SETTINGS_SCHEMA,
        "forge.core_state_schema": CORE_STATE_SCHEMA,
    }


def _render(value: Any, format_name: str) -> str:
    if format_name == "plain":
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
    if format_name == "json":
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if format_name == "lower":
        return str(value).lower()
    if format_name == "upper":
        return str(value).upper()
    raise ValueError(f"Unsupported release fact format: {format_name}")


def validate_release_facts(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve(); forge_root = forge_root.resolve()
    source, relative = _project_file(project_root, forge_root, source_path, "Release facts contract")
    raw = read_json(source, None, strict=False)
    if not isinstance(raw, dict) or raw.get("schema") != RELEASE_FACTS_SCHEMA:
        raise ValueError("Release facts contract must be valid UTF-8 JSON using schema 1.")
    fact_set_id = _required(raw.get("fact_set_id"), "fact_set_id")
    authority = _required(raw.get("authority"), "authority")
    lineage_id = _required(raw.get("lineage_id"), "lineage_id")
    lineage = _active_lineage(project_root, lineage_id)
    release_version = _required(raw.get("release_version"), "release_version")
    build_id = _required(raw.get("build_id"), "build_id")
    if release_version != str(lineage.get("declared_version", "")) or build_id != str(lineage.get("build_id", "")):
        raise ValueError("Release facts version/build do not match the active lineage.")
    family_id = _required(raw.get("package_family_id"), "package_family_id")
    _, family = _active_family(project_root, forge_root, family_id)
    if str(family.get("lineage_id", "")) != lineage_id:
        raise ValueError("Release facts lineage does not match the active package family.")
    artifact_id = _required(raw.get("source_artifact_id"), "source_artifact_id")
    artifact, artifact_path, tree = _artifact(project_root, family, artifact_id)
    if artifact_id not in set(str(value) for value in family.get("lineage_result_artifact_ids", [])):
        raise ValueError("Release facts source artifact must normalize to the active lineage result tree.")
    source_values = _resolve_sources(project_root, forge_root, lineage, family, artifact)
    facts_raw = raw.get("facts")
    if not isinstance(facts_raw, list) or not facts_raw:
        raise ValueError("Release facts require a non-empty facts array.")
    facts: list[dict[str, Any]] = []
    values: dict[str, Any] = {}
    seen: set[str] = set()
    for index, item in enumerate(facts_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"facts[{index}] must be an object.")
        fact_id = _required(item.get("fact_id"), f"facts[{index}].fact_id")
        if fact_id in seen:
            raise ValueError(f"Release fact ID is duplicated: {fact_id}")
        fact_source = _required(item.get("source"), f"fact {fact_id} source")
        if fact_source not in FACT_SOURCES:
            raise ValueError(f"Unsupported release fact source for {fact_id}: {fact_source}")
        value = item.get("value") if fact_source == "literal" else source_values[fact_source]
        if value is None or isinstance(value, (dict, list)) and not value:
            raise ValueError(f"Release fact {fact_id} resolved to an empty value.")
        format_name = str(item.get("format", "plain")).strip().lower()
        rendered = _render(value, format_name)
        facts.append({"fact_id": fact_id, "source": fact_source, "value": value, "format": format_name, "rendered": rendered})
        values[fact_id] = rendered; seen.add(fact_id)
    texts = _zip_texts(artifact_path, str(artifact.get("strip_prefix", "")))
    documents_raw = raw.get("documents")
    if not isinstance(documents_raw, list) or not documents_raw:
        raise ValueError("Release facts require at least one exact packaged document.")
    documents: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    covered: set[str] = set()
    for index, item in enumerate(documents_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"documents[{index}] must be an object.")
        path = normalize_rel(_required(item.get("path"), f"documents[{index}].path").lstrip("/"))
        text = texts.get(path)
        if text is None:
            raise ValueError(f"Release facts document is missing or not UTF-8 text in the exact artifact: {path}")
        assertions = item.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise ValueError(f"Release facts document {path} requires assertions.")
        document_checks: list[dict[str, Any]] = []
        for aindex, assertion in enumerate(assertions, start=1):
            if not isinstance(assertion, dict):
                raise ValueError(f"{path} assertions[{aindex}] must be an object.")
            fact_id = _required(assertion.get("fact_id"), f"{path} assertions[{aindex}].fact_id")
            if fact_id not in values:
                raise ValueError(f"{path} references unknown release fact: {fact_id}")
            prefix = str(assertion.get("prefix", ""))
            suffix = str(assertion.get("suffix", ""))
            if not prefix or not suffix:
                raise ValueError(f"{path} assertion {fact_id} requires non-empty prefix and suffix.")
            expected = values[fact_id]
            start = 0; observed: list[str] = []
            while True:
                left = text.find(prefix, start)
                if left < 0:
                    break
                value_start = left + len(prefix)
                right = text.find(suffix, value_start)
                if right < 0:
                    observed.append("<missing-suffix>"); break
                observed.append(text[value_start:right])
                start = right + len(suffix)
            required_count = int(assertion.get("occurrences", 1) or 1)
            status = "PASS" if len(observed) == required_count and all(value == expected for value in observed) else "FAIL"
            detail = {"fact_id": fact_id, "status": status, "expected": expected, "observed": observed, "occurrences": len(observed), "required_occurrences": required_count}
            document_checks.append(detail); checks.append({"path": path, **detail}); covered.add(fact_id)
        forbidden = [str(value) for value in item.get("forbidden_literals", [])] if isinstance(item.get("forbidden_literals", []), list) else []
        forbidden_hits = sorted(value for value in forbidden if value and value in text)
        if forbidden_hits:
            checks.append({"path": path, "fact_id": "forbidden-literals", "status": "FAIL", "expected": "absent", "observed": forbidden_hits, "occurrences": len(forbidden_hits), "required_occurrences": 0})
        documents.append({"path": path, "assertions": document_checks, "forbidden_literals": forbidden, "forbidden_hits": forbidden_hits})
    uncovered = sorted(set(values) - covered)
    if uncovered:
        raise ValueError("Every declared release fact must be checked in at least one exact packaged document: " + ", ".join(uncovered))
    failed = [row for row in checks if row["status"] != "PASS"]
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    normalized = {
        "schema": 1, "fact_set_id": fact_set_id, "authority": authority,
        "lineage_id": lineage_id, "release_version": release_version, "build_id": build_id,
        "package_family_id": family_id, "source_artifact_id": artifact_id,
        "source_artifact_sha256": artifact["sha256"], "source_artifact_bytes": artifact["bytes"], "source_tree_sha256": tree["tree_sha256"],
        "facts": facts, "documents": documents, "check_count": len(checks), "failed_count": len(failed), "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "facts": normalized, "checks": checks, "contract_source": relative,
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "control_paths": [relative],
    }


def record_release_facts(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_release_facts(project_root, forge_root, source_path)
    facts = validated["facts"]
    if facts["failed_count"]:
        raise ValueError(f"Release facts contain {facts['failed_count']} stale or contradictory packaged document assertion(s).")
    settings = load_settings(project_root)
    records = settings.get("release_facts", {}) if isinstance(settings.get("release_facts"), dict) else {}
    fact_set_id = facts["fact_set_id"]
    if fact_set_id in records and str(records[fact_set_id].get("status", "")) != "retired":
        raise ValueError(f"Release fact set ID is already recorded: {fact_set_id}")
    active = [key for key, value in records.items() if isinstance(value, dict) and str(value.get("lineage_id", "")) == facts["lineage_id"] and str(value.get("status", "")) == "active"]
    if active:
        raise ValueError("A release fact set is already active for this lineage. Retire it first: " + ", ".join(sorted(active)))
    record = {**facts, "status": "active", "recorded_utc": utc_now(), "contract_source": validated["contract_source"], "source_fingerprint": validated["source_fingerprint"], "contract_fingerprint": validated["contract_fingerprint"], "control_paths": validated["control_paths"]}
    records[fact_set_id] = record
    controls = settings.get("release_fact_control_paths", []) if isinstance(settings.get("release_fact_control_paths"), list) else []
    lineage_controls = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    for path in validated["control_paths"]:
        if path not in controls: controls.append(path)
        if path not in lineage_controls: lineage_controls.append(path)
    settings["release_facts"] = records; settings["release_fact_control_paths"] = sorted(controls); settings["lineage_control_paths"] = sorted(lineage_controls)
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "release-facts-recorded", {"fact_set_id": fact_set_id, "lineage_id": facts["lineage_id"], "fact_count": len(facts["facts"]), "document_count": len(facts["documents"]), "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}, source=facts["authority"])
    record["event_id"] = event["id"]; records[fact_set_id] = record; settings["release_facts"] = records; write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_release_facts(project_root: Path, fact_set_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = str(reason).strip(); authority = str(authority).strip()
    if len(reason) < 20: raise ValueError("Release facts retirement requires a durable reason of at least 20 characters.")
    if not authority: raise ValueError("Release facts retirement requires authority.")
    settings = load_settings(project_root); records = settings.get("release_facts", {}) if isinstance(settings.get("release_facts"), dict) else {}
    record = records.get(fact_set_id)
    if not isinstance(record, dict) or str(record.get("status", "")) != "active": raise ValueError(f"Active release fact set is not recorded: {fact_set_id}")
    updated = dict(record); updated.update({"status": "retired", "retired_utc": utc_now(), "retired_reason": reason, "retired_by": authority})
    records[fact_set_id] = updated; settings["release_facts"] = records; write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "release-facts-retired", {"fact_set_id": fact_set_id, "lineage_id": updated.get("lineage_id", ""), "reason": reason}, source=authority)
    return updated


def release_facts_summary(project_root: Path, forge_root: Path) -> dict[str, Any]:
    settings = load_settings(project_root); records = settings.get("release_facts", {}) if isinstance(settings.get("release_facts"), dict) else {}
    active_lineages = [(key, value) for key, value in lineage_records(project_root).items() if isinstance(value, dict) and str(value.get("status", "")) == "active"]
    if len(active_lineages) != 1:
        return {"schema": 1, "status": "BLOCKED" if active_lineages else "NOT_DECLARED", "reason": "Release facts require exactly one active lineage.", "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}
    lineage_id = active_lineages[0][0]
    active = [(key, value) for key, value in records.items() if isinstance(value, dict) and str(value.get("status", "")) == "active" and str(value.get("lineage_id", "")) == lineage_id]
    if not active:
        return {"schema": 1, "status": "NOT_DECLARED", "reason": "The active lineage has no authoritative exact-package release fact set.", "active_lineage_id": lineage_id, "next_action": "Record one release facts contract in a separate Adopt operation.", "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}
    if len(active) != 1:
        return {"schema": 1, "status": "CONTRADICTED", "reason": "More than one release fact set is active for the current lineage.", "active_lineage_id": lineage_id, "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}
    fact_set_id, stored = active[0]
    bound = fingerprint_bound_status(project_root, stored, active_status="active", changed_status="approval-required", missing_reason="The release facts contract source is missing.", changed_reason="The release facts contract changed and must be recorded again.")
    if str(bound.get("lifecycle_status", "active")) != "active":
        return {"schema": 1, "status": "CONTRADICTED", "reason": str(bound.get("reason", "The release facts contract is stale.")), "active_lineage_id": lineage_id, "active_fact_set_id": fact_set_id, "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}
    try:
        validated = validate_release_facts(project_root, forge_root, str(stored.get("contract_source", "")))
    except ValueError as exc:
        return {"schema": 1, "status": "CONTRADICTED", "reason": str(exc), "active_lineage_id": lineage_id, "active_fact_set_id": fact_set_id, "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}
    if validated["contract_fingerprint"] != str(stored.get("contract_fingerprint", "")):
        return {"schema": 1, "status": "STALE", "reason": "Resolved release facts or exact packaged document values changed and must be recorded again.", "active_lineage_id": lineage_id, "active_fact_set_id": fact_set_id, "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}
    facts = validated["facts"]
    if facts["failed_count"]:
        return {"schema": 1, "status": "CONTRADICTED", "reason": f"{facts['failed_count']} exact packaged release-fact assertion(s) are stale or contradictory.", "active_lineage_id": lineage_id, "active_fact_set_id": fact_set_id, "fact_count": len(facts["facts"]), "document_count": len(facts["documents"]), "check_count": facts["check_count"], "failed_count": facts["failed_count"], "checks": validated["checks"], "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}
    return {"schema": 1, "status": "CURRENT", "reason": f"All {facts['check_count']} declared visible release-fact assertion(s) match current canonical values inside the exact package artifact.", "active_lineage_id": lineage_id, "active_fact_set_id": fact_set_id, "package_family_id": facts["package_family_id"], "source_artifact_id": facts["source_artifact_id"], "fact_count": len(facts["facts"]), "document_count": len(facts["documents"]), "check_count": facts["check_count"], "failed_count": 0, "facts": facts["facts"], "truth_boundary": RELEASE_FACTS_TRUTH_BOUNDARY}

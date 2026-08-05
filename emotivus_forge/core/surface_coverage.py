from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import normalize_rel, read_json, sha256_file, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .lineage import exact_zip_tree, lineage_records
from .package_family import package_family_summary, validate_package_family
from .paths import ForgePaths
from .state import load_settings

SURFACE_COVERAGE_SCHEMA = 1
SURFACE_TYPES = {"route", "journey", "api", "worker", "installation", "admin", "other"}
EVIDENCE_TIERS = (
    "source-exists",
    "static-inspected",
    "database-executed",
    "authenticated-executed",
    "browser-tested",
    "device-tested",
    "staging-tested",
    "production-observed",
)
EVIDENCE_RESULTS = {"PASS", "FAIL", "BLOCKED"}
SURFACE_COVERAGE_TRUTH_BOUNDARY = (
    "Forge verifies an exact project-owned surface inventory against one exact result artifact and maps immutable scoped receipts to explicit evidence tiers. "
    "A higher tier never silently fills lower tiers, route existence never proves user-flow execution, and Forge does not run a database, authenticate a user, "
    "drive a browser or device, deploy the application, establish reviewer competence, or decide whether project-declared coverage requirements are sufficient."
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
        raise ValueError(f"Surface coverage requires {label}.")
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


def _parse_time(value: Any, label: str) -> datetime:
    text = _required(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp with timezone.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _active_lineage(project_root: Path, lineage_id: str) -> dict[str, Any]:
    record = lineage_records(project_root).get(lineage_id)
    if not isinstance(record, dict) or str(record.get("status", "")) != "active":
        raise ValueError(f"Surface coverage lineage is not active: {lineage_id}")
    return record


def _active_family(project_root: Path, forge_root: Path, family_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = package_family_summary(project_root, forge_root)
    if str(summary.get("status", "")) != "CURRENT":
        raise ValueError("Surface coverage requires one current exact package family.")
    if str(summary.get("active_family_id", "")) != family_id:
        raise ValueError("Surface coverage package_family_id does not match the active package family.")
    settings = load_settings(project_root)
    records = settings.get("package_families", {}) if isinstance(settings.get("package_families"), dict) else {}
    stored = records.get(family_id)
    if not isinstance(stored, dict) or str(stored.get("status", "")) != "active":
        raise ValueError(f"Active package family is not recorded: {family_id}")
    validated = validate_package_family(project_root, forge_root, str(stored.get("contract_source", "")))
    return stored, validated["family"]


def _source_artifact(project_root: Path, family: dict[str, Any], artifact_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts = family.get("artifacts", []) if isinstance(family.get("artifacts"), list) else []
    artifact = next((row for row in artifacts if isinstance(row, dict) and str(row.get("artifact_id", "")) == artifact_id), None)
    if not isinstance(artifact, dict):
        raise ValueError(f"Surface coverage source artifact is not in the active family: {artifact_id}")
    if artifact_id not in set(str(value) for value in family.get("lineage_result_artifact_ids", [])):
        raise ValueError("Surface coverage source artifact must normalize to the active lineage result tree.")
    path = (project_root / str(artifact.get("path", ""))).resolve()
    tree = exact_zip_tree(path, strip_prefix=str(artifact.get("strip_prefix", "")))
    if tree["tree_sha256"] != str(artifact.get("tree_sha256", "")):
        raise ValueError("Surface coverage source artifact tree no longer matches the package family.")
    return artifact, tree


def _string_list(raw: Any, label: str, *, minimum: int = 0) -> list[str]:
    if not isinstance(raw, list) or len(raw) < minimum:
        raise ValueError(f"{label} must be an array with at least {minimum} item(s).")
    values = [_required(value, label) for value in raw]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} contains duplicates.")
    return sorted(values)


def _normalize_surfaces(raw: Any, artifact_files: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("Surface coverage requires at least one declared surface.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"surfaces[{index}] must be an object.")
        surface_id = _required(item.get("surface_id"), f"surfaces[{index}].surface_id")
        if surface_id in seen:
            raise ValueError(f"Surface ID is duplicated: {surface_id}")
        kind = str(item.get("type", "")).strip().lower()
        if kind not in SURFACE_TYPES:
            raise ValueError(f"Unsupported surface type for {surface_id}: {kind}")
        title = _required(item.get("title"), f"surface {surface_id} title", minimum=3)
        audiences = _string_list(item.get("audiences", []), f"surface {surface_id} audiences", minimum=1)
        entrypoints = _string_list(item.get("entrypoints", []), f"surface {surface_id} entrypoints", minimum=0)
        steps = _string_list(item.get("steps", []), f"surface {surface_id} steps", minimum=0)
        if kind == "journey":
            if not steps:
                raise ValueError(f"Journey surface {surface_id} requires steps.")
        elif not entrypoints:
            raise ValueError(f"Surface {surface_id} requires at least one exact artifact entrypoint.")
        for path in entrypoints:
            normalized = normalize_rel(path).strip("/")
            if not normalized or normalized != path or normalized not in artifact_files:
                raise ValueError(f"Surface {surface_id} entrypoint is not present in the exact source artifact: {path}")
        required_tier = str(item.get("required_tier", "")).strip().lower()
        if required_tier not in EVIDENCE_TIERS:
            raise ValueError(f"Surface {surface_id} required_tier is unsupported: {required_tier}")
        route = str(item.get("route", "")).strip()
        if kind == "route" and not route.startswith("/"):
            raise ValueError(f"Route surface {surface_id} requires an absolute application route beginning with /.")
        result.append({
            "surface_id": surface_id,
            "type": kind,
            "title": title,
            "audiences": audiences,
            "entrypoints": entrypoints,
            "steps": steps,
            "route": route,
            "required_tier": required_tier,
            "scope": _required(item.get("scope"), f"surface {surface_id} scope", minimum=10),
        })
        seen.add(surface_id)
    ids = {row["surface_id"] for row in result}
    for row in result:
        unknown = sorted(set(row["steps"]) - ids)
        if unknown:
            raise ValueError(f"Journey surface {row['surface_id']} references unknown steps: {', '.join(unknown)}")
        if row["surface_id"] in row["steps"]:
            raise ValueError(f"Journey surface {row['surface_id']} cannot include itself as a step.")
    return sorted(result, key=lambda row: row["surface_id"])


def _normalize_receipts(
    project_root: Path,
    forge_root: Path,
    raw: Any,
    *,
    surface_ids: set[str],
    family_id: str,
    artifact_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if raw in (None, []):
        return [], []
    if not isinstance(raw, list):
        raise ValueError("receipts must be an array.")
    result: list[dict[str, Any]] = []
    controls: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"receipts[{index}] must be an object.")
        receipt_id = _required(item.get("receipt_id"), f"receipts[{index}].receipt_id")
        if receipt_id in seen:
            raise ValueError(f"Surface evidence receipt ID is duplicated: {receipt_id}")
        covered = _string_list(item.get("surface_ids", []), f"receipt {receipt_id} surface_ids", minimum=1)
        unknown = sorted(set(covered) - surface_ids)
        if unknown:
            raise ValueError(f"Receipt {receipt_id} references unknown surfaces: {', '.join(unknown)}")
        tier = str(item.get("tier", "")).strip().lower()
        if tier not in EVIDENCE_TIERS or tier == "source-exists":
            raise ValueError(f"Receipt {receipt_id} tier must be an executed or reviewed tier above source-exists.")
        result_value = str(item.get("result", "")).strip().upper()
        if result_value not in EVIDENCE_RESULTS:
            raise ValueError(f"Receipt {receipt_id} result must be PASS, FAIL, or BLOCKED.")
        if str(item.get("package_family_id", "")).strip() != family_id or str(item.get("source_artifact_id", "")).strip() != artifact_id:
            raise ValueError(f"Receipt {receipt_id} is not bound to the active surface package family and source artifact.")
        evidence_path, relative = _project_file(project_root, forge_root, item.get("evidence_path"), f"receipt {receipt_id} evidence_path")
        expected_sha = _digest(item.get("evidence_sha256"), f"receipt {receipt_id} evidence_sha256")
        expected_bytes = item.get("evidence_bytes")
        if not isinstance(expected_bytes, int) or expected_bytes < 1:
            raise ValueError(f"Receipt {receipt_id} evidence_bytes must be a positive integer.")
        if sha256_file(evidence_path) != expected_sha or evidence_path.stat().st_size != expected_bytes:
            raise ValueError(f"Receipt {receipt_id} immutable evidence identity does not match.")
        observed = _parse_time(item.get("observed_utc"), f"receipt {receipt_id} observed_utc")
        expires = _parse_time(item.get("expires_utc"), f"receipt {receipt_id} expires_utc")
        if expires <= observed:
            raise ValueError(f"Receipt {receipt_id} expires_utc must be after observed_utc.")
        result.append({
            "receipt_id": receipt_id,
            "surface_ids": covered,
            "tier": tier,
            "result": result_value,
            "package_family_id": family_id,
            "source_artifact_id": artifact_id,
            "environment": _required(item.get("environment"), f"receipt {receipt_id} environment", minimum=3),
            "method": _required(item.get("method"), f"receipt {receipt_id} method", minimum=10),
            "reviewer": _required(item.get("reviewer"), f"receipt {receipt_id} reviewer", minimum=3),
            "observed_utc": observed.isoformat(),
            "expires_utc": expires.isoformat(),
            "evidence_path": relative,
            "evidence_sha256": expected_sha,
            "evidence_bytes": expected_bytes,
            "limitations": _required(item.get("limitations"), f"receipt {receipt_id} limitations", minimum=10),
            "truth_boundary": _required(item.get("truth_boundary"), f"receipt {receipt_id} truth_boundary", minimum=20),
        })
        controls.append(relative)
        seen.add(receipt_id)
    return sorted(result, key=lambda row: row["receipt_id"]), controls


def _coverage_matrix(surfaces: list[dict[str, Any]], receipts: list[dict[str, Any]], *, now: datetime | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    current = now or datetime.now(timezone.utc)
    order = {tier: index for index, tier in enumerate(EVIDENCE_TIERS)}
    rows: list[dict[str, Any]] = []
    counts = {"complete": 0, "gap": 0, "failed": 0, "blocked": 0, "stale": 0}
    for surface in surfaces:
        surface_id = surface["surface_id"]
        tier_rows: dict[str, str] = {"source-exists": "PASS"}
        receipt_ids: list[str] = []
        for receipt in receipts:
            if surface_id not in receipt["surface_ids"]:
                continue
            receipt_ids.append(receipt["receipt_id"])
            expires = _parse_time(receipt["expires_utc"], f"receipt {receipt['receipt_id']} expires_utc")
            state = "STALE" if expires <= current else receipt["result"]
            existing = tier_rows.get(receipt["tier"])
            priority = {"FAIL": 4, "BLOCKED": 3, "STALE": 2, "PASS": 1}
            if existing is None or priority.get(state, 0) > priority.get(existing, 0):
                tier_rows[receipt["tier"]] = state
        required = surface["required_tier"]
        required_state = tier_rows.get(required, "NOT_RUN")
        if required_state == "PASS":
            coverage = "COMPLETE"; counts["complete"] += 1
        elif required_state == "FAIL":
            coverage = "FAILED"; counts["failed"] += 1
        elif required_state == "BLOCKED":
            coverage = "BLOCKED"; counts["blocked"] += 1
        elif required_state == "STALE":
            coverage = "STALE"; counts["stale"] += 1
        else:
            coverage = "GAP"; counts["gap"] += 1
        passed = [tier for tier, state in tier_rows.items() if state == "PASS"]
        highest = max(passed, key=lambda tier: order[tier]) if passed else "none"
        rows.append({
            "surface_id": surface_id,
            "type": surface["type"],
            "title": surface["title"],
            "required_tier": required,
            "required_tier_status": required_state,
            "coverage_status": coverage,
            "highest_explicit_pass_tier": highest,
            "tier_statuses": {tier: tier_rows.get(tier, "NOT_RUN") for tier in EVIDENCE_TIERS},
            "receipt_ids": sorted(receipt_ids),
        })
    return rows, counts


def validate_surface_coverage(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve(); forge_root = forge_root.resolve()
    source, relative = _project_file(project_root, forge_root, source_path, "Surface coverage contract")
    raw = read_json(source, None, strict=False)
    if not isinstance(raw, dict):
        raise ValueError("Surface coverage contract must be valid UTF-8 JSON containing one object.")
    if raw.get("schema") != SURFACE_COVERAGE_SCHEMA:
        raise ValueError("Surface coverage contract must use schema 1.")
    inventory_id = _required(raw.get("inventory_id"), "inventory_id")
    authority = _required(raw.get("authority"), "authority")
    lineage_id = _required(raw.get("lineage_id"), "lineage_id")
    lineage = _active_lineage(project_root, lineage_id)
    family_id = _required(raw.get("package_family_id"), "package_family_id")
    _, family = _active_family(project_root, forge_root, family_id)
    if str(family.get("lineage_id", "")) != lineage_id:
        raise ValueError("Surface coverage lineage does not match the active package family lineage.")
    release_version = _required(raw.get("release_version"), "release_version")
    build_id = _required(raw.get("build_id"), "build_id")
    if release_version != str(lineage.get("declared_version", "")) or build_id != str(lineage.get("build_id", "")):
        raise ValueError("Surface coverage release version/build ID do not match the active lineage.")
    source_artifact_id = _required(raw.get("source_artifact_id"), "source_artifact_id")
    artifact, tree = _source_artifact(project_root, family, source_artifact_id)
    surfaces = _normalize_surfaces(raw.get("surfaces"), tree.get("files", {}))
    receipts, evidence_controls = _normalize_receipts(
        project_root, forge_root, raw.get("receipts"),
        surface_ids={row["surface_id"] for row in surfaces},
        family_id=family_id, artifact_id=source_artifact_id,
    )
    matrix, counts = _coverage_matrix(surfaces, receipts)
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=30)
    normalized = {
        "schema": 1,
        "inventory_id": inventory_id,
        "authority": authority,
        "lineage_id": lineage_id,
        "release_version": release_version,
        "build_id": build_id,
        "package_family_id": family_id,
        "source_artifact_id": source_artifact_id,
        "source_artifact_sha256": artifact["sha256"],
        "source_artifact_bytes": artifact["bytes"],
        "source_tree_sha256": artifact["tree_sha256"],
        "surfaces": surfaces,
        "receipts": receipts,
        "coverage_matrix": matrix,
        "coverage_counts": counts,
        "truth_boundary": truth_boundary,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "inventory": normalized,
        "contract_source": relative,
        "source_fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "contract_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "control_paths": sorted(set([relative, *evidence_controls])),
    }


def record_surface_coverage(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_surface_coverage(project_root, forge_root, source_path)
    inventory = validated["inventory"]
    settings = load_settings(project_root)
    records = settings.get("surface_coverages", {}) if isinstance(settings.get("surface_coverages"), dict) else {}
    inventory_id = inventory["inventory_id"]
    if inventory_id in records and str(records[inventory_id].get("status", "")) != "retired":
        raise ValueError(f"Surface coverage inventory ID is already recorded: {inventory_id}")
    active = [key for key, value in records.items() if isinstance(value, dict) and str(value.get("lineage_id", "")) == inventory["lineage_id"] and str(value.get("status", "")) == "active"]
    if active:
        raise ValueError("A surface coverage inventory is already active for this lineage. Retire it first: " + ", ".join(sorted(active)))
    record = {
        **inventory,
        "status": "active",
        "recorded_utc": utc_now(),
        "contract_source": validated["contract_source"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "control_paths": validated["control_paths"],
    }
    records[inventory_id] = record
    controls = settings.get("surface_coverage_control_paths", []) if isinstance(settings.get("surface_coverage_control_paths"), list) else []
    lineage_controls = settings.get("lineage_control_paths", []) if isinstance(settings.get("lineage_control_paths"), list) else []
    for path in validated["control_paths"]:
        if path not in controls:
            controls.append(path)
        if path not in lineage_controls:
            lineage_controls.append(path)
    settings["surface_coverages"] = records
    settings["surface_coverage_control_paths"] = sorted(controls)
    settings["lineage_control_paths"] = sorted(lineage_controls)
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "surface-coverage-recorded", {
        "inventory_id": inventory_id,
        "lineage_id": inventory["lineage_id"],
        "surface_count": len(inventory["surfaces"]),
        "receipt_count": len(inventory["receipts"]),
        "complete_count": inventory["coverage_counts"]["complete"],
        "truth_boundary": SURFACE_COVERAGE_TRUTH_BOUNDARY,
    }, source=inventory["authority"])
    record["event_id"] = event["id"]
    records[inventory_id] = record
    settings["surface_coverages"] = records
    write_json(ForgePaths(project_root).settings, settings)
    return record


def retire_surface_coverage(project_root: Path, inventory_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    project_root = project_root.resolve(); inventory_id = str(inventory_id).strip(); reason = str(reason).strip(); authority = str(authority).strip()
    if len(reason) < 20:
        raise ValueError("Surface coverage retirement requires a durable reason of at least 20 characters.")
    if not authority:
        raise ValueError("Surface coverage retirement requires authority.")
    settings = load_settings(project_root)
    records = settings.get("surface_coverages", {}) if isinstance(settings.get("surface_coverages"), dict) else {}
    record = records.get(inventory_id)
    if not isinstance(record, dict) or str(record.get("status", "")) != "active":
        raise ValueError(f"Active surface coverage inventory is not recorded: {inventory_id}")
    updated = dict(record)
    updated.update({"status": "retired", "retired_utc": utc_now(), "retired_reason": reason, "retired_by": authority})
    records[inventory_id] = updated
    settings["surface_coverages"] = records
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "surface-coverage-retired", {"inventory_id": inventory_id, "lineage_id": updated.get("lineage_id", ""), "reason": reason}, source=authority)
    return updated


def surface_coverage_summary(project_root: Path, forge_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    settings = load_settings(project_root)
    records = settings.get("surface_coverages", {}) if isinstance(settings.get("surface_coverages"), dict) else {}
    active_lineages = [(key, value) for key, value in lineage_records(project_root).items() if isinstance(value, dict) and str(value.get("status", "")) == "active"]
    if len(active_lineages) != 1:
        return {"schema": 1, "status": "BLOCKED" if active_lineages else "NOT_DECLARED", "reason": "Surface coverage requires exactly one active lineage.", "truth_boundary": SURFACE_COVERAGE_TRUTH_BOUNDARY}
    lineage_id = active_lineages[0][0]
    current: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []
    for inventory_id, stored in records.items():
        if not isinstance(stored, dict) or str(stored.get("status", "")) != "active" or str(stored.get("lineage_id", "")) != lineage_id:
            continue
        bound = fingerprint_bound_status(project_root, stored, active_status="active", changed_status="approval-required", missing_reason="The surface coverage contract source is missing.", changed_reason="The surface coverage contract changed and must be recorded again.")
        if str(bound.get("lifecycle_status", "")) != "active":
            current.append((str(inventory_id), bound, None)); continue
        try:
            validated = validate_surface_coverage(project_root, forge_root, str(stored.get("contract_source", "")))
        except ValueError as exc:
            contradicted = dict(bound); contradicted["lifecycle_status"] = "contradicted"; contradicted["reason"] = str(exc)
            current.append((str(inventory_id), contradicted, None)); continue
        if validated["contract_fingerprint"] != str(stored.get("contract_fingerprint", "")):
            changed = dict(bound); changed["lifecycle_status"] = "approval-required"; changed["reason"] = "The normalized surface coverage changed and must be recorded again."
            current.append((str(inventory_id), changed, validated["inventory"])); continue
        current.append((str(inventory_id), dict(bound), validated["inventory"]))
    if not current:
        return {"schema": 1, "status": "NOT_DECLARED", "reason": "The active lineage has no exact surface-to-evidence inventory.", "active_lineage_id": lineage_id, "next_action": "Record one surface coverage contract in a separate Adopt operation.", "truth_boundary": SURFACE_COVERAGE_TRUTH_BOUNDARY}
    if len(current) != 1:
        return {"schema": 1, "status": "CONTRADICTED", "reason": "More than one surface coverage inventory is active for the current lineage.", "active_lineage_id": lineage_id, "truth_boundary": SURFACE_COVERAGE_TRUTH_BOUNDARY}
    inventory_id, bound, inventory = current[0]
    if str(bound.get("lifecycle_status", "active")) != "active" or not isinstance(inventory, dict):
        return {"schema": 1, "status": "CONTRADICTED", "reason": str(bound.get("reason", "The surface coverage inventory is stale or contradicted.")), "active_lineage_id": lineage_id, "active_inventory_id": inventory_id, "truth_boundary": SURFACE_COVERAGE_TRUTH_BOUNDARY}
    counts = inventory.get("coverage_counts", {}) if isinstance(inventory.get("coverage_counts"), dict) else {}
    total = len(inventory.get("surfaces", []))
    complete = int(counts.get("complete", 0) or 0)
    gaps = total - complete
    coverage_status = "COMPLETE" if gaps == 0 else "GAPS"
    return {
        "schema": 1,
        "status": "CURRENT",
        "coverage_status": coverage_status,
        "reason": (
            f"All {total} declared surfaces have current explicit evidence at their project-required tier."
            if coverage_status == "COMPLETE"
            else f"The exact inventory is current, but {gaps} of {total} surface(s) lack current PASS evidence at their project-required tier."
        ),
        "active_lineage_id": lineage_id,
        "active_inventory_id": inventory_id,
        "package_family_id": inventory.get("package_family_id", ""),
        "source_artifact_id": inventory.get("source_artifact_id", ""),
        "surface_count": total,
        "receipt_count": len(inventory.get("receipts", [])),
        "coverage_counts": counts,
        "coverage_matrix": inventory.get("coverage_matrix", []),
        "truth_boundary": SURFACE_COVERAGE_TRUTH_BOUNDARY,
    }

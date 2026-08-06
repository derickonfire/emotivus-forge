from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, unique_strings, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .state import load_settings

RELATIONSHIP_SCHEMA = 1
RELATIONSHIP_KINDS = {
    "entrypoint-include",
    "import",
    "behavior-binding",
    "resource-consumer",
    "decision-path",
    "migration-effect",
    "test-covers",
}
PROPAGATION_MODES = {"source-to-target", "target-to-source", "bidirectional"}

KIND_DEFAULTS: dict[str, dict[str, list[str]]] = {
    "entrypoint-include": {"surfaces": ["runtime"], "dimensions": ["application", "relationship"]},
    "import": {"surfaces": ["application"], "dimensions": ["application", "relationship"]},
    "behavior-binding": {"surfaces": ["frontend", "behavior"], "dimensions": ["application", "relationship"]},
    "resource-consumer": {"surfaces": ["resource-usage"], "dimensions": ["relationship"]},
    "decision-path": {"surfaces": ["governance"], "dimensions": ["decision", "relationship"]},
    "migration-effect": {"surfaces": ["database"], "dimensions": ["data-state", "runtime-contract", "relationship"]},
    "test-covers": {"surfaces": ["verification"], "dimensions": ["verification", "relationship"]},
}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Relationship contract requires {label}.")
    return text


def _safe_source(project_root: Path, forge_root: Path, raw: str | Path) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError("Relationship contracts must be project-owned files outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Relationship contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _safe_pattern(raw: Any, label: str) -> str:
    pattern = normalize_rel(_required(raw, label).lstrip("/"))
    if pattern in {"", "."} or pattern.startswith("../") or "/../" in f"/{pattern}/":
        raise ValueError(f"{label} must remain inside the project.")
    if pattern.startswith(".forge/") or pattern == ".forge":
        raise ValueError(f"{label} must remain outside .forge.")
    return pattern


def _normalize_endpoint(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object.")
    role = _required(raw.get("role"), f"{label}.role")
    patterns = raw.get("path_patterns")
    if not isinstance(patterns, list) or not patterns:
        raise ValueError(f"{label}.path_patterns must be a non-empty array.")
    normalized = [_safe_pattern(item, f"{label}.path_patterns") for item in unique_strings(patterns)]
    if not normalized:
        raise ValueError(f"{label}.path_patterns must contain at least one unique path pattern.")
    return {
        "role": role,
        "path_patterns": normalized,
        "required": bool(raw.get("required", True)),
    }


def validate_relationship_contract(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _safe_source(project_root, forge_root.resolve(), contract_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Relationship contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != RELATIONSHIP_SCHEMA:
        raise ValueError("Relationship contract must be an object using schema 1.")
    set_id = _required(raw.get("relationship_set_id"), "relationship_set_id")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in set_id):
        raise ValueError("relationship_set_id may contain only lowercase letters, numbers, hyphens, and underscores.")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    rationale = _required(raw.get("rationale"), "rationale", minimum=20)
    boundary = _required(raw.get("verification_boundary"), "verification_boundary", minimum=20)
    evidence_paths = raw.get("evidence_paths", [])
    if not isinstance(evidence_paths, list) or not evidence_paths:
        raise ValueError("Relationship contract requires evidence_paths as a non-empty array.")
    normalized_evidence: list[str] = []
    for item in unique_strings(evidence_paths):
        relative_evidence = _safe_pattern(item, "evidence path")
        target = (project_root / relative_evidence).resolve()
        if not _inside(target, project_root) or _inside(target, project_root / ".forge") or not target.exists():
            raise ValueError(f"Relationship evidence path does not exist inside the project: {relative_evidence}")
        normalized_evidence.append(relative_evidence)

    rows = raw.get("relationships")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Relationship contract requires at least one relationship.")
    relationships: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(rows, 1):
        if not isinstance(item, dict):
            raise ValueError(f"relationships[{index}] must be an object.")
        relation_id = _required(item.get("id"), f"relationships[{index}].id")
        if relation_id in ids:
            raise ValueError(f"Duplicate relationship id: {relation_id}")
        ids.add(relation_id)
        kind = _required(item.get("kind"), f"relationships[{index}].kind")
        if kind not in RELATIONSHIP_KINDS:
            raise ValueError(f"Unsupported relationship kind: {kind}")
        propagation = str(item.get("propagation", "bidirectional")).strip()
        if propagation not in PROPAGATION_MODES:
            raise ValueError(f"relationships[{index}].propagation must be source-to-target, target-to-source, or bidirectional.")
        source = _normalize_endpoint(item.get("source"), f"relationships[{index}].source")
        targets_raw = item.get("targets")
        if not isinstance(targets_raw, list) or not targets_raw:
            raise ValueError(f"relationships[{index}].targets must be a non-empty array.")
        targets = [_normalize_endpoint(value, f"relationships[{index}].targets[{target_index}]") for target_index, value in enumerate(targets_raw, 1)]
        reason = _required(item.get("reason"), f"relationships[{index}].reason", minimum=12)
        surfaces = unique_strings(item.get("affected_surfaces", [])) if isinstance(item.get("affected_surfaces", []), list) else []
        dimensions = unique_strings(item.get("impact_dimensions", [])) if isinstance(item.get("impact_dimensions", []), list) else []
        required_checks = unique_strings(item.get("required_checks", [])) if isinstance(item.get("required_checks", []), list) else []
        relationships.append({
            "id": relation_id,
            "kind": kind,
            "source": source,
            "targets": targets,
            "propagation": propagation,
            "reason": reason,
            "affected_surfaces": surfaces,
            "impact_dimensions": dimensions,
            "required_checks": required_checks,
        })

    contract = {
        "schema": RELATIONSHIP_SCHEMA,
        "relationship_set_id": set_id,
        "title": title,
        "authority": authority,
        "rationale": rationale,
        "evidence_paths": normalized_evidence,
        "relationships": relationships,
        "verification_boundary": boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(
        project_root,
        record,
        changed_status="approval-required",
        missing_reason="The project-owned relationship source is missing.",
        changed_reason="The project-owned relationship contract changed after authority approval.",
    )


def relationship_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("relationship_sets", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_relationship_set(project_root: Path, forge_root: Path, contract_path: str | Path) -> dict[str, Any]:
    validated = validate_relationship_contract(project_root, forge_root, contract_path)
    contract = validated["contract"]
    set_id = contract["relationship_set_id"]
    settings = load_settings(project_root)
    records = settings.get("relationship_sets", {})
    if not isinstance(records, dict):
        records = {}
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "relationship_set_id": set_id,
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[set_id] = record
    settings["relationship_sets"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "relationship-set-recorded", {
        "relationship_set_id": set_id,
        "title": contract["title"],
        "authority": contract["authority"],
        "contract_source": validated["source"],
        "relationship_count": len(contract["relationships"]),
        "verification_boundary": contract["verification_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_relationship_set(project_root: Path, set_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("relationship_sets", {})
    if not isinstance(records, dict) or set_id not in records or not isinstance(records[set_id], dict):
        raise ValueError(f"Relationship set is not recorded: {set_id}")
    record = dict(records[set_id])
    record.update({"status": "retired", "lifecycle_status": "retired", "retired_utc": utc_now(), "retired_by": authority, "reason": reason})
    records[set_id] = record
    settings["relationship_sets"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "relationship-set-retired", {"relationship_set_id": set_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _candidate_paths(project_root: Path, *, limit: int = 5000) -> tuple[list[str], bool]:
    values: list[str] = []
    bounded = False
    for path in sorted(project_root.rglob("*"), key=lambda item: item.as_posix()):
        try:
            relative = normalize_rel(path.relative_to(project_root))
        except ValueError:
            continue
        if not relative or relative == ".forge" or relative.startswith(".forge/"):
            continue
        if any(part in {".git", "__pycache__", "node_modules", "vendor"} for part in Path(relative).parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        values.append(relative)
        if len(values) >= limit:
            bounded = True
            break
    return values, bounded


def _matches(paths: list[str], patterns: list[str]) -> list[str]:
    return sorted({path for path in paths if any(fnmatch.fnmatch(path, pattern) for pattern in patterns)})


def _endpoint_matches(all_paths: list[str], endpoint: dict[str, Any]) -> list[str]:
    patterns = endpoint.get("path_patterns", []) if isinstance(endpoint.get("path_patterns"), list) else []
    return _matches(all_paths, [str(value) for value in patterns])


def _changed_matches(changed_paths: list[str], endpoint: dict[str, Any]) -> list[str]:
    patterns = endpoint.get("path_patterns", []) if isinstance(endpoint.get("path_patterns"), list) else []
    return _matches(changed_paths, [str(value) for value in patterns])


def evaluate_relationships(project_root: Path, changed_paths: list[str]) -> dict[str, Any]:
    records = relationship_records(project_root)
    if not records:
        return {
            "schema": 1, "status": "NOT_CONFIGURED", "active_count": 0, "attention_count": 0,
            "impact_count": 0, "related_path_count": 0, "evaluations": [], "impacts": [],
            "findings": [], "scan_bounded": False,
            "truth_boundary": "No project-owned relationship sets are recorded.",
        }
    all_paths, bounded = _candidate_paths(project_root)
    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    impacts: list[dict[str, Any]] = []
    active_count = 0
    attention_count = 0

    for set_id, record in sorted(records.items()):
        lifecycle_status = str(record.get("lifecycle_status", record.get("status", "unknown")))
        contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
        if lifecycle_status == "retired":
            continue
        if lifecycle_status != "active":
            attention_count += 1
            evaluations.append({
                "relationship_set_id": set_id,
                "status": "APPROVAL_REQUIRED",
                "reason": str(record.get("reason", "Relationship contract requires renewed authority.")),
                "relationship_count": len(contract.get("relationships", [])) if isinstance(contract.get("relationships"), list) else 0,
            })
            findings.append({
                "check": "core.relationship-current",
                "severity": "blocker",
                "path": str(record.get("contract_source", ".")),
                "line": 0,
                "message": f"Relationship set {set_id} requires renewed authority: {record.get('reason', 'contract is not current')}",
            })
            continue
        active_count += 1
        set_impacts: list[dict[str, Any]] = []
        stale_relations = 0
        for relation in contract.get("relationships", []):
            if not isinstance(relation, dict):
                continue
            source = relation.get("source", {}) if isinstance(relation.get("source"), dict) else {}
            targets = [item for item in relation.get("targets", []) if isinstance(item, dict)] if isinstance(relation.get("targets"), list) else []
            source_paths = _endpoint_matches(all_paths, source)
            target_groups = [
                {"role": target.get("role", "target"), "paths": _endpoint_matches(all_paths, target), "required": bool(target.get("required", True))}
                for target in targets
            ]
            missing_roles: list[str] = []
            if bool(source.get("required", True)) and not source_paths:
                missing_roles.append(str(source.get("role", "source")))
            for group in target_groups:
                if group["required"] and not group["paths"]:
                    missing_roles.append(str(group["role"]))
            if missing_roles:
                stale_relations += 1
                findings.append({
                    "check": "core.relationship-current",
                    "severity": "blocker",
                    "path": str(record.get("contract_source", ".")),
                    "line": 0,
                    "message": f"Relationship {set_id}/{relation.get('id', 'relationship')} has no current path for required role(s): {', '.join(missing_roles)}.",
                })

            source_changed = _changed_matches(changed_paths, source)
            target_changed_groups = [
                {**group, "changed": _changed_matches(changed_paths, target)}
                for group, target in zip(target_groups, targets)
            ]
            target_changed = sorted({path for group in target_changed_groups for path in group["changed"]})
            propagation = str(relation.get("propagation", "bidirectional"))
            trigger_paths: list[str] = []
            related_paths: list[str] = []
            if propagation in {"source-to-target", "bidirectional"} and source_changed:
                trigger_paths.extend(source_changed)
                related_paths.extend(path for group in target_groups for path in group["paths"])
            if propagation in {"target-to-source", "bidirectional"} and target_changed:
                trigger_paths.extend(target_changed)
                related_paths.extend(source_paths)
            trigger_paths = sorted(set(trigger_paths))
            related_paths = sorted(set(related_paths) - set(changed_paths))
            if not trigger_paths:
                continue
            kind = str(relation.get("kind", "relationship"))
            defaults = KIND_DEFAULTS.get(kind, {"surfaces": ["project"], "dimensions": ["relationship"]})
            surfaces = sorted(set(defaults["surfaces"]) | set(str(value) for value in relation.get("affected_surfaces", []) if str(value).strip()))
            dimensions = sorted(set(defaults["dimensions"]) | set(str(value) for value in relation.get("impact_dimensions", []) if str(value).strip()))
            impact = {
                "relationship_set_id": set_id,
                "relationship_id": str(relation.get("id", "")),
                "kind": kind,
                "reason": str(relation.get("reason", "")),
                "trigger_paths": trigger_paths,
                "related_paths": related_paths,
                "affected_surfaces": surfaces,
                "impact_dimensions": dimensions,
                "required_checks": [str(value) for value in relation.get("required_checks", []) if str(value).strip()],
                "verification_boundary": str(contract.get("verification_boundary", "")),
            }
            impacts.append(impact)
            set_impacts.append(impact)
        evaluations.append({
            "relationship_set_id": set_id,
            "status": "STALE" if stale_relations else ("IMPACTED" if set_impacts else "CURRENT"),
            "relationship_count": len(contract.get("relationships", [])) if isinstance(contract.get("relationships"), list) else 0,
            "impact_count": len(set_impacts),
            "stale_relationship_count": stale_relations,
            "contract_source": record.get("contract_source", ""),
        })

    blocking = [item for item in findings if item.get("severity") == "blocker"]
    return {
        "schema": 1,
        "status": "FAIL" if blocking else ("IMPACTED" if impacts else "PASS"),
        "active_count": active_count,
        "attention_count": attention_count,
        "impact_count": len(impacts),
        "related_path_count": len({path for item in impacts for path in item.get("related_paths", [])}),
        "evaluations": evaluations,
        "impacts": impacts,
        "findings": findings,
        "scan_bounded": bounded,
        "truth_boundary": "Only authority-recorded relationships are traversed. Related paths are impact context, not claims that those paths changed or that runtime behavior is correct.",
    }


def augment_check_plan(plan: dict[str, Any], relationship_result: dict[str, Any]) -> dict[str, Any]:
    augmented = dict(plan)
    impacts = [item for item in relationship_result.get("impacts", []) if isinstance(item, dict)] if isinstance(relationship_result, dict) else []
    if not impacts:
        augmented["relationship_impacts"] = []
        augmented["related_paths"] = []
        return augmented
    surfaces = set(str(value) for value in augmented.get("affected_surfaces", []) if str(value).strip())
    dimensions = set(str(value) for value in augmented.get("impact_dimensions", []) if str(value).strip())
    related_paths: set[str] = set()
    required: dict[str, dict[str, str]] = {
        str(item.get("id", "")): dict(item)
        for item in augmented.get("required_checks", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    compact_impacts: list[dict[str, Any]] = []
    for impact in impacts:
        surfaces.update(str(value) for value in impact.get("affected_surfaces", []) if str(value).strip())
        dimensions.update(str(value) for value in impact.get("impact_dimensions", []) if str(value).strip())
        related_paths.update(str(value) for value in impact.get("related_paths", []) if str(value).strip())
        for check_id in impact.get("required_checks", []):
            check_id = str(check_id).strip()
            if check_id:
                required.setdefault(check_id, {"id": check_id, "reason": f"Required by confirmed relationship {impact.get('relationship_id', '')}: {impact.get('reason', '')}"})
        compact_impacts.append({
            "relationship_set_id": impact.get("relationship_set_id", ""),
            "relationship_id": impact.get("relationship_id", ""),
            "kind": impact.get("kind", ""),
            "trigger_paths": list(impact.get("trigger_paths", [])),
            "related_paths": list(impact.get("related_paths", [])),
            "reason": impact.get("reason", ""),
        })
    augmented["affected_surfaces"] = sorted(surfaces)
    augmented["impact_dimensions"] = sorted(dimensions)
    augmented["required_checks"] = [required[key] for key in sorted(required)]
    augmented["relationship_impacts"] = compact_impacts
    augmented["related_paths"] = sorted(related_paths)
    if {"database", "runtime", "application"}.intersection(surfaces) or {"data-state", "runtime-contract"}.intersection(dimensions):
        augmented["profile"] = "application"
        augmented["native_gate_policy"] = {
            "selection": "recommended-explicit",
            "reason": "Confirmed project relationships connect the changed surface to application, runtime, or data-state behavior; use the owner-approved native gate when available.",
            "full_suite_automatic": False,
        }
    return augmented

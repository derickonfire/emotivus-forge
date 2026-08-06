from __future__ import annotations

from typing import Any

from .common import utc_now


def effective_native_validity(native_evidence: dict[str, Any], current_tree_fingerprint: str) -> str:
    """Native evidence validity, downgraded to stale when the source tree changed.

    DG-8: imported native evidence is bound to the tree fingerprint it was captured
    against. If the current tree differs, the evidence no longer describes the current
    project and must not read as 'current' — regardless of the stored validity, which
    is only flipped by recorded change plans.
    """
    if not isinstance(native_evidence, dict):
        return "unknown"
    stored = str(native_evidence.get("validity", "current"))
    recorded = str(native_evidence.get("source_tree_fingerprint", ""))
    if recorded and current_tree_fingerprint and recorded != str(current_tree_fingerprint):
        return "stale-source-changed"
    return stored

TYPE_TARGETS: dict[str, set[str]] = {
    "browser": {"website", "frontend"},
    "ui": {"website", "frontend"},
    "e2e": {"website", "frontend", "backend"},
    "frontend": {"website", "frontend"},
    "migration": {"database"},
    "database": {"database"},
    "schema": {"database"},
    "runtime": {"backend", "configuration", "database"},
    "environment": {"configuration", "backend"},
    "deployment": {"release", "configuration", "backend", "website"},
    "static": {"backend", "frontend", "website", "verification"},
    "unit": {"backend", "frontend", "verification"},
    "integration": {"backend", "frontend", "database", "verification"},
    "native": {"backend", "frontend", "website", "database", "configuration", "verification"},
    "documentation": {"documentation"},
}


def _record_targets(record: dict[str, Any]) -> set[str]:
    evidence_type = str(record.get("type", "native")).strip().lower()
    targets = set(TYPE_TARGETS.get(evidence_type, set()))
    surfaces = record.get("surfaces", [])
    if isinstance(surfaces, str):
        surfaces = [surfaces]
    if isinstance(surfaces, list):
        for surface in surfaces:
            normalized = str(surface).strip().lower()
            if normalized in {"website", "frontend", "backend", "database", "configuration", "documentation", "release", "verification"}:
                targets.add(normalized)
    return targets


def _affected(record: dict[str, Any], changed_surfaces: set[str], dimensions: set[str]) -> bool:
    targets = _record_targets(record)
    if targets.intersection(changed_surfaces):
        return True
    evidence_type = str(record.get("type", "native")).strip().lower()
    if evidence_type in {"migration", "database", "schema", "runtime"} and not ({"database", "backend", "configuration"} & changed_surfaces):
        return False
    if evidence_type in {"browser", "ui", "frontend"} and not ({"website", "frontend"} & changed_surfaces):
        return False
    if evidence_type == "documentation" and "documentation" not in changed_surfaces:
        return False
    if not targets:
        return bool({"application", "data-state", "runtime-contract", "configuration", "deletion"}.intersection(dimensions))
    return False


def invalidate_connected_evidence(passport: dict[str, Any], plan: dict[str, Any], change_id: str) -> dict[str, Any]:
    changed_surfaces = set(plan.get("affected_surfaces", []))
    dimensions = set(plan.get("impact_dimensions", []))
    if not changed_surfaces:
        return {
            "status": "none",
            "change_id": change_id,
            "invalidated_count": 0,
            "invalidated_ids": [],
            "preserved_ids": [],
            "reason": "No canonical observed changed surfaces were detected.",
        }

    evidence = passport.get("evidence", {}) if isinstance(passport.get("evidence"), dict) else {}
    native = evidence.get("native_gate", {}) if isinstance(evidence.get("native_gate"), dict) else {}
    records = native.get("records", []) if isinstance(native.get("records"), list) else []
    invalidated: list[str] = []
    preserved: list[str] = []

    if records:
        for record in records:
            if not isinstance(record, dict):
                continue
            identifier = str(record.get("id", "unnamed"))
            if _affected(record, changed_surfaces, dimensions):
                record["validity"] = "stale"
                record["invalidated_by_change"] = change_id
                record["invalidated_utc"] = utc_now()
                invalidated.append(identifier)
            else:
                record.setdefault("validity", "current")
                preserved.append(identifier)
        native["validity"] = "stale" if invalidated and not preserved else "partially-stale" if invalidated else "current"
    elif native:
        synthetic = {
            "id": "native_gate",
            "type": (native.get("evidence_types") or ["native"])[0] if isinstance(native.get("evidence_types"), list) else "native",
            "surfaces": native.get("surfaces", []),
        }
        if _affected(synthetic, changed_surfaces, dimensions):
            native["validity"] = "stale"
            native["invalidated_by_change"] = change_id
            native["invalidated_utc"] = utc_now()
            invalidated.append("native_gate")
        else:
            native.setdefault("validity", "current")
            preserved.append("native_gate")

    if native:
        evidence["native_gate"] = native
        passport["evidence"] = evidence

    coverage = passport.get("surface_coverage", {}) if isinstance(passport.get("surface_coverage"), dict) else {}
    coverage_type = {"id": "surface_coverage", "type": "browser" if coverage.get("surfaces") else "native", "surfaces": coverage.get("surfaces", [])}
    if coverage and _affected(coverage_type, changed_surfaces, dimensions):
        coverage["validity"] = "stale"
        coverage["invalidated_by_change"] = change_id
        coverage["invalidated_utc"] = utc_now()
    elif coverage:
        coverage.setdefault("validity", "current")
    if coverage:
        passport["surface_coverage"] = coverage

    return {
        "status": "invalidated" if invalidated else "preserved",
        "change_id": change_id,
        "invalidated_count": len(invalidated),
        "invalidated_ids": sorted(set(invalidated)),
        "preserved_ids": sorted(set(preserved)),
        "reason": "Only evidence connected to affected surfaces was invalidated.",
    }

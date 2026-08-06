from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .. import __version__
from .authority_registry import load_or_discover_authorities
from .authority_baseline import assess_authority_baseline
from .common import read_json, utc_now, write_json
from .capabilities import capability_summary
from .ledger import record_event
from .knowledge import update_knowledge_index
from .guardrails import guardrail_summary
from .field_trials import field_trial_summary
from .native_tools import load_or_discover_native_tools
from .orientation import orient_project
from .paths import ForgePaths
from .self_currency import assess_self_currency
from .project_identity import project_identity_summary
from .lineage import lineage_summary
from .migration_identity import migration_identity_summary
from .package_family import package_family_summary
from .surface_coverage import surface_coverage_summary
from .release_facts import release_facts_summary
from .continuity_register import continuity_register_summary
from .third_party_intake import third_party_intake_summary
from .state import CORE_STATE_SCHEMA, ensure_settings, load_state, migrate_legacy_state, save_state
from .telemetry import record_metric


def build_passport(project_root: Path, forge_root: Path, *, name: str = "", refresh: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    project_root = project_root.resolve()
    migration = migrate_legacy_state(project_root)
    settings = ensure_settings(project_root)
    orientation = orient_project(project_root, forge_root, settings)
    if name.strip():
        orientation["identity"] = {
            "name": name.strip(),
            "name_source": "owner",
            "status": "confirmed",
            "source_root": ".",
        }
    authorities = load_or_discover_authorities(project_root, forge_root, refresh=refresh, settings=settings)
    native_tools = load_or_discover_native_tools(project_root, refresh=refresh)
    objective = authorities.get("objective", {})
    uncertainties = list(orientation.get("unknowns", []))
    confirmation = authorities.get("confirmation", {})
    if isinstance(confirmation, dict) and confirmation.get("required"):
        uncertainties.append(str(confirmation.get("reason", "Authority confirmation is required.")))
    approval = native_tools.get("approval", {})
    if isinstance(approval, dict) and approval.get("status") in {"required", "reapproval-required"}:
        canonical = native_tools.get("canonical", {})
        source = canonical.get("source", "detected native gate") if isinstance(canonical, dict) else "detected native gate"
        if approval.get("status") == "reapproval-required":
            uncertainties.append(f"Reconfirm the execution mode for {source}: its registered fingerprint is missing or changed.")
        else:
            uncertainties.append(f"Select whether {source} is Forge-authorized, owner-only, external-CI, or evidence-import-only.")
    paths = ForgePaths(project_root)
    existing_passport = read_json(paths.passport, {})
    existing_evidence = existing_passport.get("evidence", {}) if isinstance(existing_passport, dict) else {}
    existing_coverage = existing_passport.get("surface_coverage", {}) if isinstance(existing_passport, dict) else {}
    passport = {
        "schema": 1,
        "forge_version": __version__,
        "generated_utc": utc_now(),
        "identity": orientation["identity"],
        "orientation": {
            "stacks": orientation["stacks"],
            "source_root": ".",
            "files_observed": orientation["snapshot"]["file_count"],
            "scan_truncated": orientation["snapshot"]["truncated"],
            "brief": orientation.get("brief", {}),
            "layout": orientation.get("brief", {}).get("layout", {}),
            "central_files": [
                row.get("path", "")
                for row in orientation.get("code_orientation", {}).get("centrality", {}).get("top", [])[:3]
                if isinstance(row, dict) and row.get("path")
            ],
            "status": "observed",
        },
        "objective": objective,
        "governance": authorities.get("governance", []),
        "native_gate": {
            "verification_status": native_tools.get("verification_status", "unknown"),
            "canonical": native_tools.get("canonical"),
            "ecosystem": native_tools.get("ecosystem", {}),
            "approval": native_tools.get("approval"),
        },
        "evidence": existing_evidence if isinstance(existing_evidence, dict) else {},
        "surface_coverage": existing_coverage if isinstance(existing_coverage, dict) else {},
        "safety": orientation["safety"],
        "knowledge_statuses": ["observed", "inferred", "confirmed", "contradicted", "stale"],
        "uncertainties": uncertainties,
        "maturity": "Orientation",
        "scope": {
            "included": ["project identity", "likely stack", "authority candidates", "current objective", "canonical native quality ecosystem", "placeholder-aware safety boundaries", "authority-recorded atomic and event guardrails", "owner-controlled multi-component identity", "project-local field-validation plans", "minimal file snapshot", "advanced capability activation status and recommendations"],
            "excluded": ["deep Graph", "Lab", "runtime proof", "release proof", "deployment proof", "automatic environment repair", "tool absorption", "implicit capability activation"],
        },
    }
    knowledge_index, knowledge_delta = update_knowledge_index(existing_passport if isinstance(existing_passport, dict) else {}, passport)
    passport["knowledge_index"] = knowledge_index
    passport["knowledge_delta"] = knowledge_delta
    passport["project_identity"] = project_identity_summary(project_root)
    passport["project_lineage"] = lineage_summary(project_root, forge_root)
    passport["migration_identity"] = migration_identity_summary(project_root, forge_root)
    passport["package_family"] = package_family_summary(project_root, forge_root)
    passport["surface_coverage_contract"] = surface_coverage_summary(project_root, forge_root)
    passport["release_facts"] = release_facts_summary(project_root, forge_root)
    passport["continuity_register"] = continuity_register_summary(project_root)
    passport["third_party_intakes"] = third_party_intake_summary(project_root)
    passport["guardrails"] = guardrail_summary(project_root)
    passport["field_trials"] = field_trial_summary(project_root)
    passport["advanced_capabilities"] = capability_summary(project_root, passport)
    passport["self_currency"] = assess_self_currency(project_root, passport, authorities, native_tools)
    for item in passport["self_currency"].get("attention", []):
        if str(item) not in passport["uncertainties"]:
            passport["uncertainties"].append(str(item))
    write_json(paths.passport, passport)
    state = load_state(project_root)
    prior_snapshot = state.get("snapshot", {}) if isinstance(state.get("snapshot"), dict) else {}
    first_adoption = not bool(prior_snapshot.get("files"))
    observed_checkpoint = orientation["snapshot"] if first_adoption else prior_snapshot
    authority_baseline = assess_authority_baseline(state, orientation["snapshot"])
    passport["authority_baseline"] = {
        "status": authority_baseline.get("status", "NOT_ESTABLISHED"),
        "baseline_id": authority_baseline.get("baseline_id", ""),
        "authority": authority_baseline.get("authority", ""),
        "pending_count": authority_baseline.get("pending_count", 0),
        "baseline_strength": authority_baseline.get("baseline_strength", {}).get("status", "not-established") if isinstance(authority_baseline.get("baseline_strength"), dict) else "not-established",
        "truth_boundary": authority_baseline.get("truth_boundary", ""),
    }
    state.update({
        "schema": CORE_STATE_SCHEMA,
        "created_utc": state.get("created_utc", utc_now()),
        "adopted_utc": state.get("adopted_utc", utc_now()),
        "last_adopt_refresh_utc": utc_now(),
        "forge_version": __version__,
        # Adopt refreshes orientation and authority records, but never rewrites an existing
        # observed checkpoint. Only a passing Check --checkpoint or explicit baseline
        # authorization may move this comparison point.
        "snapshot": observed_checkpoint,
        "last_observed_snapshot": orientation["snapshot"],
        "last_operation": "adopt",
        "last_check": state.get("last_check", {}),
        "authority_baseline": state.get("authority_baseline", {
            "schema": 1,
            "status": "not-established",
            "reason": "No explicit project-authority baseline has been recorded.",
        }),
        "migration": state.get("migration", migration.get("state", {}).get("migration", {})),
        "knowledge": {
            "last_delta": knowledge_delta,
            "stale_keys": [item.get("key", "") for item in knowledge_delta.get("stale", []) if isinstance(item, dict)],
        },
    })
    save_state(project_root, state)
    record_event(project_root, "adopt", {
        "identity": passport["identity"],
        "objective": passport["objective"],
        "files_observed": passport["orientation"]["files_observed"],
        "uncertainty_count": len(uncertainties),
        "scope": passport["scope"],
        "observed_checkpoint_preserved": not first_adoption,
        "authority_baseline_status": authority_baseline.get("status", "NOT_ESTABLISHED"),
        "knowledge_delta": {
            "added": len(knowledge_delta.get("added", [])),
            "changed": len(knowledge_delta.get("changed", [])),
            "stale": len(knowledge_delta.get("stale", [])),
        },
        "self_currency_status": passport["self_currency"].get("status", "UNKNOWN"),
        "project_lineage_status": passport["project_lineage"].get("status", "NOT_RECORDED"),
        "merge_candidate_count": passport["project_lineage"].get("unresolved_candidate_count", 0),
        "migration_identity_status": passport["migration_identity"].get("status", "NOT_DECLARED"),
        "migration_collision_count": passport["migration_identity"].get("unresolved_collision_count", 0),
        "continuity_register_status": passport["continuity_register"].get("status", "NOT_DECLARED"),
        "continuity_fact_count": passport["continuity_register"].get("fact_count", 0),
        "continuity_open_gap_count": passport["continuity_register"].get("open_gap_count", 0),
        "third_party_intake_status": passport["third_party_intakes"].get("status", "NOT_DECLARED"),
        "third_party_candidate_count": passport["third_party_intakes"].get("candidate_count", 0),
    })
    record_metric(project_root, "adopt", {
        "duration_ms": round((time.monotonic() - started) * 1000),
        "files_scanned": orientation["snapshot"]["file_count"],
        "state_files": 8,
        "scan_truncated": orientation["snapshot"]["truncated"],
    })
    return passport

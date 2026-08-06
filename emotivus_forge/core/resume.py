from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .authority_registry import load_or_discover_authorities
from .authority_baseline import assess_authority_baseline
from .change_ledger import build_check_plan
from .relationships import evaluate_relationships, augment_check_plan
from .capabilities import capability_summary
from .changes import change_count_phrase, detect_changes, snapshot_fingerprint
from .evidence_validity import effective_native_validity
from .decision_forks import analyze_decision_forks
from .guardrails import guardrail_summary
from .ledger_assertions import ledger_assertion_summary
from .check_qualification import check_qualification_summary
from .provenance import provenance_summary
from .deployable_boundary import deployable_boundary_summary
from .canonical_claims import canonical_claims_summary
from .runtime_matrix import runtime_matrix_summary
from .state_transitions import state_transition_summary
from .release_package import release_package_summary
from .presentation_profile import presentation_profile_summary
from .release_distribution import release_distribution_summary
from .cold_session_validation import cold_session_summary
from .release_proof import release_proof_summary
from .release_authorization import release_authorization_summary
from .field_trials import field_trial_summary
from .common import read_json, utc_now, write_text_atomic
from .native_tools import load_or_discover_native_tools
from .paths import ForgePaths
from .session_close import assess_continuity, latest_session_close
from .self_currency import assess_self_currency
from .project_identity import project_identity_summary
from .lineage import lineage_summary
from .migration_identity import migration_identity_summary
from .package_family import package_family_summary
from .surface_coverage import surface_coverage_summary
from .release_facts import release_facts_summary
from .continuity_register import continuity_register_summary
from .third_party_intake import third_party_intake_summary
from .bounded_retrieval import retrieve_continuity
from .sidecar import update_sidecar_status
from .state import load_settings, load_state
from .telemetry import record_metric, summarize_telemetry

BUDGET_LIMITS = {"compact": 6, "standard": 12, "full": 30}


def _governance_rules(authorities: dict[str, Any], limit: int) -> list[str]:
    rows: list[str] = []
    for group in authorities.get("governance", []):
        if not isinstance(group, dict):
            continue
        source = str(group.get("source", ""))
        rules = group.get("rules", [])
        if not isinstance(rules, list):
            continue
        for rule in rules:
            value = str(rule).strip()
            if value and value not in rows:
                rows.append(f"{value} ({source})" if source else value)
            if len(rows) >= limit:
                return rows
    return rows


def _append_items(lines: list[str], title: str, items: list[str], limit: int) -> None:
    if not items:
        return
    lines.extend(["", f"### {title}"])
    lines.extend(f"- {item}" for item in items[:limit])
    if len(items) > limit:
        lines.append(f"- … {len(items) - limit} more")


def build_resume(project_root: Path, forge_root: Path, *, budget: str = "compact", refresh: bool = True, query: str = "") -> dict[str, Any]:
    started = time.monotonic()
    project_root = project_root.resolve()
    paths = ForgePaths(project_root)
    passport = read_json(paths.passport, {})
    if not isinstance(passport, dict) or passport.get("schema") != 1:
        raise RuntimeError("Project has not been adopted by this Forge core.")
    settings = load_settings(project_root)
    state = load_state(project_root)
    authorities = load_or_discover_authorities(project_root, forge_root, refresh=refresh, settings=settings)
    native_tools = load_or_discover_native_tools(project_root, refresh=refresh)
    self_currency = assess_self_currency(project_root, passport, authorities, native_tools)
    changes = detect_changes(project_root, forge_root, state.get("snapshot", {}), settings)
    authority_baseline = assess_authority_baseline(state, changes["current_snapshot"], project_root=project_root)
    relationships = evaluate_relationships(project_root, changes["paths"])
    current_check_plan = augment_check_plan(build_check_plan(changes), relationships)
    continuity = assess_continuity(project_root, current_snapshot=changes["current_snapshot"])
    decision_forks = analyze_decision_forks(project_root, forge_root, authorities=authorities, changes=changes)
    capabilities = capability_summary(project_root, passport)
    project_identity = project_identity_summary(project_root)
    project_lineage = lineage_summary(project_root, forge_root)
    migration_identity = migration_identity_summary(project_root, forge_root)
    package_family = package_family_summary(project_root, forge_root)
    surface_coverage = surface_coverage_summary(project_root, forge_root)
    release_facts = release_facts_summary(project_root, forge_root)
    continuity_register = continuity_register_summary(project_root)
    third_party_intakes = third_party_intake_summary(project_root)
    guardrails = guardrail_summary(project_root)
    ledger_assertions = ledger_assertion_summary(project_root)
    check_qualifications = check_qualification_summary(project_root)
    provenance = provenance_summary(project_root)
    deployable_boundaries = deployable_boundary_summary(project_root)
    canonical_claims = canonical_claims_summary(project_root)
    runtime_matrices = runtime_matrix_summary(project_root)
    state_transitions = state_transition_summary(project_root)
    release_package = release_package_summary(project_root)
    presentation_profile = presentation_profile_summary(project_root)
    release_distribution = release_distribution_summary(project_root)
    cold_session = cold_session_summary(project_root)
    release_proof = release_proof_summary(project_root)
    release_authorization = release_authorization_summary(project_root)
    field_trials = field_trial_summary(project_root)
    knowledge_delta = passport.get("knowledge_delta", {}) if isinstance(passport.get("knowledge_delta"), dict) else {}
    close_event = latest_session_close(project_root)
    close_payload = close_event.get("payload", {}) if isinstance(close_event, dict) else {}
    if not isinstance(close_payload, dict):
        close_payload = {}
    limit = BUDGET_LIMITS.get(budget, BUDGET_LIMITS["compact"])
    objective = authorities.get("objective", passport.get("objective", {}))
    objective_text = str(objective.get("text", "")).strip() if isinstance(objective, dict) else ""
    close_next = close_payload.get("next_action", {}) if isinstance(close_payload.get("next_action"), dict) else {}
    close_next_text = str(close_next.get("text", "")).strip()
    next_action = close_next_text or objective_text or "Confirm the project’s exact next action and record it in an authoritative project file."
    retrieval_query = str(query or "").strip() or " ".join(value for value in (objective_text, next_action) if value).strip()
    compact_mode = budget == "compact"
    retrieval_budget = 3 if compact_mode else min(limit, 8)
    retrieval = retrieve_continuity(project_root, retrieval_query, result_budget=retrieval_budget, relationship_depth=1)
    next_action_source = (
        f"session-close:{close_event.get('id', '')}" if close_next_text and isinstance(close_event, dict)
        else str(objective.get("source", "")) if isinstance(objective, dict)
        else ""
    )
    sidecar = update_sidecar_status(
        project_root,
        mode="development-sidecar",
        operation="resume",
        work_scope=next_action,
        authority_status=str(authority_baseline.get("status", "NOT_ESTABLISHED")),
        unexpected_mutations=int(authority_baseline.get("pending_count", 0) or 0),
    )
    rules = _governance_rules(authorities, limit)
    canonical = native_tools.get("canonical") if isinstance(native_tools, dict) else None
    approval = native_tools.get("approval", {}) if isinstance(native_tools, dict) else {}
    uncertainties = list(passport.get("uncertainties", []))[:limit]
    completed = [str(item) for item in close_payload.get("completed_work", []) if str(item).strip()]
    close_changed = [str(item) for item in close_payload.get("changed_files", []) if str(item).strip()]
    decisions = [item for item in close_payload.get("decisions", []) if isinstance(item, dict)]
    owner_facts = [item for item in close_payload.get("owner_facts", []) if isinstance(item, dict)]
    risks = [str(item) for item in close_payload.get("unresolved_risks", []) if str(item).strip()]
    checks = close_payload.get("checks", {}) if isinstance(close_payload.get("checks"), dict) else {}
    governing_decisions = decision_forks.get("governing_decisions", []) if isinstance(decision_forks, dict) else []
    native_evidence_for_reuse = passport.get("evidence", {}).get("native_gate", {}) if isinstance(passport.get("evidence"), dict) else {}
    native_records = native_evidence_for_reuse.get("records", []) if isinstance(native_evidence_for_reuse, dict) else []
    evidence_records_reused = sum(
        1 for item in native_records
        if isinstance(item, dict) and str(item.get("validity", "current")) == "current"
    )
    cached_records_reused = (
        (1 if objective_text else 0)
        + (1 if isinstance(canonical, dict) else 0)
        + (1 if close_event else 0)
        + len(rules)
        + len(governing_decisions)
        + (1 if project_identity.get("status") == "active" else 0)
        + (1 if project_lineage.get("status") == "CURRENT" else 0)
        + int(project_lineage.get("unresolved_candidate_count", 0))
        + (1 if migration_identity.get("status") not in {"NOT_DECLARED", "BLOCKED"} else 0)
        + int(migration_identity.get("unresolved_collision_count", 0))
        + (1 if package_family.get("status") == "CURRENT" else 0)
        + (1 if surface_coverage.get("status") == "CURRENT" else 0)
        + (1 if continuity_register.get("status") == "CURRENT" else 0)
        + int(continuity_register.get("fact_count", 0))
        + int(third_party_intakes.get("candidate_count", 0))
        + int(retrieval.get("result_count", 0))
        + len(capabilities.get("active", []))
        + len(guardrails.get("active", []))
        + len(ledger_assertions.get("active", []))
        + int(check_qualifications.get("active", 0))
        + int(provenance.get("active", 0))
        + int(deployable_boundaries.get("active", 0))
        + int(canonical_claims.get("active", 0))
        + int(runtime_matrices.get("active", 0))
        + int(state_transitions.get("active", 0))
        + int(relationships.get("active_count", 0))
        + len(field_trials.get("active", []))
        + int(presentation_profile.get("active", 0))
        + (1 if release_distribution.get("status") != "NOT_RUN" else 0)
        + (1 if cold_session.get("status") != "NOT_RUN" else 0)
        + (1 if release_proof.get("status") != "NOT_RUN" else 0)
        + (1 if release_authorization.get("status") != "NOT_RUN" else 0)
    )
    telemetry = summarize_telemetry(
        project_root,
        current_cached_records=cached_records_reused,
        current_evidence_records_reused=evidence_records_reused,
    )
    if continuity_register.get("status") == "CURRENT":
        continuity_governance_line = (
            f"- **Continuity governance:** CURRENT; {continuity_register.get('fact_count', 0)} fact(s), "
            f"{continuity_register.get('open_gap_count', 0)} gap(s); sidecar {sidecar.get('mode', 'development-sidecar')}; "
            f"mutations {sidecar.get('unexpected_mutations', 0)}."
        )
    else:
        continuity_governance_line = ""
    lines = [
        f"# Forge Resume — {passport.get('identity', {}).get('name', project_root.name)}",
        "",
        "## Owner summary",
        f"- **Current objective{'' if str(objective.get('status', '')).lower() == 'confirmed' else ' (derived, unconfirmed)'}:** {objective_text or 'Not yet confirmed.'}",
        f"- **Exact next action:** {next_action}",
        f"- **Continuity:** {continuity.get('status', 'unknown')} — {continuity.get('reason', '')}",
        continuity_governance_line,
        f"- **Observed changes:** {change_count_phrase(changes)}.",
        f"- **Authority:** {authority_baseline.get('status', 'NOT_ESTABLISHED')}; {authority_baseline.get('pending_count', 0)} quarantined.",
        f"- **Forge maturity:** {passport.get('maturity', 'Orientation')}.",
        f"- **Bounded retrieval:** {retrieval.get('result_count', 0)}/{retrieval.get('candidate_count', 0)} traceable record(s) selected.",
        f"- **Decision forks:** {len(decision_forks.get('pending', []))} pending; {len(decision_forks.get('contradictions', []))} contradiction warning(s).",
        f"- **Project identity:** {project_identity.get('status', 'not-recorded')}; build `{project_identity.get('build_id', '') or 'not recorded'}`; {project_identity.get('present_components', 0)}/{project_identity.get('component_count', 0)} component(s) present.",
        f"- **Lineage:** {project_lineage.get('status', 'NOT_RECORDED')}; {project_lineage.get('unresolved_candidate_count', 0)} pending branch candidate(s).",
        f"- **Migration identity:** {migration_identity.get('status', 'NOT_DECLARED')}; {migration_identity.get('entry_count', 0)} tracked migration(s); {migration_identity.get('unresolved_collision_count', 0)} unresolved collision(s).",
        f"- **Package family:** {package_family.get('status', 'NOT_DECLARED')}; {package_family.get('artifact_count', 0)} artifact(s); {package_family.get('delta_count', 0)} proven delta(s); {package_family.get('outer_bundle_count', 0)} outer bundle(s).",
        f"- **Advanced capabilities:** {len(capabilities.get('active', []))} active; {len(capabilities.get('recommendations', []))} recommendation(s); vault loaded: no.",
        f"- **Atomic safety guardrails:** {len(guardrails.get('active', []))} active; {len(guardrails.get('attention', []))} require attention.",
        f"- **Ledger assertions:** {len(ledger_assertions.get('active', []))} active; {len(ledger_assertions.get('attention', []))} require attention.",
        f"- **Check qualification:** {check_qualifications.get('active', 0)} current qualification(s), backed by {check_qualifications.get('negative_cases', 0)} recorded known-bad case(s); {check_qualifications.get('attention', 0)} require attention.",
        f"- **Artifact provenance:** {provenance.get('active', 0)} active; {provenance.get('attention', 0)} require authority attention; {provenance.get('unregistered_deliverables', 0)} unregistered deliverable-shaped file(s).",
        f"- **Deployable boundaries:** {deployable_boundaries.get('active', 0)} active; {deployable_boundaries.get('attention', 0)} require authority attention; {deployable_boundaries.get('delta_artifacts', 0)} registered delta artifact(s).",
        f"- **Canonical claims:** {canonical_claims.get('active', 0)} active set(s); {canonical_claims.get('claims', 0)} explicit claim(s); {canonical_claims.get('attention', 0)} require authority attention.",
        f"- **Runtime-state matrices:** {runtime_matrices.get('active', 0)} active; {runtime_matrices.get('scenarios', 0)} declared scenario(s); {runtime_matrices.get('attention', 0)} require authority attention.",
        f"- **Persisted-state transitions:** {state_transitions.get('active', 0)} active plan(s); {state_transitions.get('transitions', 0)} transition(s); {state_transitions.get('coverage_requirements', 0)} coverage requirement(s); {state_transitions.get('semantic_states', 0)} semantic state definition(s); {state_transitions.get('rollback_availability', 0)} require rollback availability and {state_transitions.get('rollback_drill', 0)} require a drill; {state_transitions.get('attention', 0)} require authority attention.",
        f"- **Final release package:** {release_package.get('final_package', 'NOT_RUN')}; confidentiality {release_package.get('confidentiality', 'NOT_RUN')}; public reviews {release_package.get('review_ratio', '0/0')} ({release_package.get('public_reviews', 'NOT_RUN')}).",
        f"- **Confirmed relationships:** {relationships.get('active_count', 0)} active set(s); {relationships.get('impact_count', 0)} current impact(s); {relationships.get('related_path_count', 0)} related path(s); {relationships.get('attention_count', 0)} require authority attention.",
        f"- **Field validation:** {len(field_trials.get('active', []))} active trial(s); {field_trials.get('total_observations', 0)} recorded observation(s).",
        f"- **Knowledge delta:** {knowledge_delta.get('meaningful_count', 0)} newly learned, changed, or stale supported fact(s).",
        f"- **Forge self-currency:** {self_currency.get('status', 'UNKNOWN')}; {self_currency.get('summary', {}).get('unresolved_count', 0)} unresolved truth-state record(s).",
    ]
    lines = [line for line in lines if line]
    if compact_mode:
        omit_prefixes: set[str] = set()
        if not capabilities.get("active") and not capabilities.get("recommendations"):
            omit_prefixes.add("- **Advanced capabilities:")
        if not guardrails.get("active") and not guardrails.get("attention"):
            omit_prefixes.add("- **Atomic safety guardrails:")
        if not ledger_assertions.get("active") and not ledger_assertions.get("attention"):
            omit_prefixes.add("- **Ledger assertions:")
        if not check_qualifications.get("active") and not check_qualifications.get("attention") and not check_qualifications.get("negative_cases"):
            omit_prefixes.add("- **Check qualification:")
        if not provenance.get("active") and not provenance.get("attention") and not provenance.get("unregistered_deliverables"):
            omit_prefixes.add("- **Artifact provenance:")
        if not deployable_boundaries.get("active") and not deployable_boundaries.get("attention") and not deployable_boundaries.get("delta_artifacts"):
            omit_prefixes.add("- **Deployable boundaries:")
        if not canonical_claims.get("active") and not canonical_claims.get("claims") and not canonical_claims.get("attention"):
            omit_prefixes.add("- **Canonical claims:")
        if not runtime_matrices.get("active") and not runtime_matrices.get("scenarios") and not runtime_matrices.get("attention"):
            omit_prefixes.add("- **Runtime-state matrices:")
        if not state_transitions.get("active") and not state_transitions.get("transitions") and not state_transitions.get("attention"):
            omit_prefixes.add("- **Persisted-state transitions:")
        if not relationships.get("active_count") and not relationships.get("impact_count") and not relationships.get("attention_count"):
            omit_prefixes.add("- **Confirmed relationships:")
        if not field_trials.get("active") and not field_trials.get("total_observations"):
            omit_prefixes.add("- **Field validation:")
        # Lazy governance: an undeclared contract carries no signal on first contact.
        # Collapse the empty base governance lines so the digest stays dense and
        # token-light; they reappear the moment a project actually declares them.
        if project_identity.get("status", "not-recorded") == "not-recorded":
            omit_prefixes.add("- **Project identity:")
        if project_lineage.get("status", "NOT_RECORDED") == "NOT_RECORDED":
            omit_prefixes.add("- **Lineage:")
        if migration_identity.get("status", "NOT_DECLARED") == "NOT_DECLARED":
            omit_prefixes.add("- **Migration identity:")
        if package_family.get("status", "NOT_DECLARED") == "NOT_DECLARED":
            omit_prefixes.add("- **Package family:")
        if release_package.get("final_package", "NOT_RUN") == "NOT_RUN" and release_package.get("confidentiality", "NOT_RUN") == "NOT_RUN":
            omit_prefixes.add("- **Final release package:")
        lines = [line for line in lines if not any(line.startswith(prefix) for prefix in omit_prefixes)]
    if third_party_intakes.get("status") != "NOT_DECLARED":
        lines.append(
            f"- **Third-party intake:** {third_party_intakes.get('status', 'NOT_DECLARED')}; "
            f"{third_party_intakes.get('candidate_count', 0)} candidate(s), {third_party_intakes.get('adapt_count', 0)} adapted."
        )
    if surface_coverage.get("status") != "NOT_DECLARED":
        complete_surfaces = surface_coverage.get("coverage_counts", {}).get("complete", 0) if isinstance(surface_coverage.get("coverage_counts"), dict) else 0
        lines.append(f"- **Surface evidence:** {surface_coverage.get('status', 'NOT_DECLARED')}/{surface_coverage.get('coverage_status', 'NOT_RUN')}; {complete_surfaces}/{surface_coverage.get('surface_count', 0)} complete.")
    if release_facts.get("status") != "NOT_DECLARED":
        lines.append(f"- **Release facts:** {release_facts.get('status', 'NOT_DECLARED')}; {release_facts.get('check_count', 0)} visible assertion(s), {release_facts.get('failed_count', 0)} stale or contradictory.")
    if release_distribution.get("status") != "NOT_RUN":
        lines.append(f"- **Release distribution:** signatures {release_distribution.get('signatures', 'NOT_RUN')}; channels {release_distribution.get('channel_ratio', '0/0')} ({release_distribution.get('channels', 'NOT_RUN')}).")
    if release_proof.get("status") != "NOT_RUN":
        lines.append(f"- **Release Proof:** {release_proof.get('surface_count', 0)} surface(s); domains {release_proof.get('domain_ratio', '0/9')}; obligations {release_proof.get('obligation_ratio', '0/0')} ({release_proof.get('status', 'NOT_RUN')}).")
    if cold_session.get("status") != "NOT_RUN":
        lines.append(f"- **Cold-session validation:** {cold_session.get('pair_ratio', '0/0')} human pair(s); {cold_session.get('model_ratio', '0/0')} model(s); {cold_session.get('task_ratio', '0/0')} task packet(s); {cold_session.get('fixture_pairs', 0)} fixture pair(s) excluded; {cold_session.get('status', 'NOT_RUN')}.")
    if release_authorization.get("status") != "NOT_RUN":
        lines.append(f"- **Exact-package release authorization:** {release_authorization.get('status', 'NOT_RUN')}; {release_authorization.get('authorized_channel_count', 0)} named channel(s); valid until {release_authorization.get('valid_until_utc', 'unknown')}.")
    if presentation_profile.get("instruction"):
        lines.append(f"- **Cross-model presentation:** {presentation_profile.get('instruction')}")
    if close_event:
        lines.append(
            f"- **Last session:** {close_payload.get('session_type', 'unclassified')} closed {close_event.get('utc', '')}; "
            f"{len(completed)} completed item(s), {len(risks)} unresolved risk(s)."
        )
    else:
        lines.append("- **Last session:** No Session Close is recorded yet.")
    lines.extend([
        "",
        "## Builder detail",
        f"- **Likely stack:** {', '.join(passport.get('orientation', {}).get('stacks', [])) or 'Unknown'}",
        f"- **Change confidence:** {changes.get('confidence', 'unknown')}",
        f"- **Current Check profile:** {current_check_plan.get('profile', 'none')}; affected surfaces: {', '.join(current_check_plan.get('affected_surfaces', [])) or 'none'}.",
        f"- **Relationship-aware scope:** {relationships.get('impact_count', 0)} confirmed impact(s); related paths are context only and are not counted as changed.",
        f"- **Continuity confidence:** {continuity.get('confidence', 'unknown')}",
    ])
    _brief = passport.get("orientation", {}).get("brief", {}) if isinstance(passport.get("orientation"), dict) else {}
    _orient_lines: list[str] = []
    if _brief.get("description"):
        _src = _brief.get("description_source", "")
        _tag = f"derived from {_src}, unverified" if _src else "derived, unverified"
        _orient_lines.append(f"- **What it may be ({_tag}):** {_brief['description']}")
    if _brief.get("entry_points"):
        _orient_lines.append(f"- **Entry points (inferred):** {', '.join(_brief['entry_points'])}")
    if _brief.get("run"):
        _orient_lines.append(f"- **Run (inferred, not executed):** `{_brief['run']}`")
    if _brief.get("test"):
        _orient_lines.append(f"- **Test (inferred, not executed):** `{_brief['test']}`")
    _layout = _brief.get("layout", {}) if isinstance(_brief.get("layout"), dict) else {}
    if _layout.get("top_level"):
        _dirs = ", ".join(f"{row['dir']}/ ({row['files']})" for row in _layout["top_level"][:5])
        _orient_lines.append(f"- **Layout:** {_dirs}")
    if _layout.get("primary_source_dir"):
        _tests = _layout.get("tests", {}) if isinstance(_layout.get("tests"), dict) else {}
        _orient_lines.append(
            f"- **Source:** `{_layout['primary_source_dir']}` ({_layout.get('primary_language', '')}); "
            f"tests in `{_tests.get('dir', '?')}` ({_tests.get('count', 0)})"
        )
    if _orient_lines:
        lines.extend(["", "### First-contact orientation", *_orient_lines])
    delta_rows: list[tuple[str, dict[str, Any]]] = []
    for delta_kind in ("added", "changed", "stale"):
        rows = knowledge_delta.get(delta_kind, []) if isinstance(knowledge_delta.get(delta_kind), list) else []
        delta_rows.extend((delta_kind, item) for item in rows if isinstance(item, dict))
    if delta_rows:
        lines.extend(["", "### What Forge learned or revised"] )
        for delta_kind, item in delta_rows[:limit]:
            label = item.get("label", item.get("key", "project fact"))
            if delta_kind == "added":
                lines.append(f"- **Learned:** {label} → `{item.get('current', '')}`")
            elif delta_kind == "changed":
                lines.append(f"- **Updated:** {label} → `{item.get('current', '')}` (previously `{item.get('previous', '')}`)")
            else:
                lines.append(f"- **Marked stale:** {label} — {item.get('reason', 'support is no longer current')}")
        if len(delta_rows) > limit:
            lines.append(f"- … {len(delta_rows) - limit} more knowledge change(s)")

    if authority_baseline.get("pending_paths"):
        lines.append("- **Authority-quarantined paths:**")
        for path in authority_baseline.get("pending_paths", [])[:limit]:
            lines.append(f"  - `{path}`")
        if len(authority_baseline.get("pending_paths", [])) > limit:
            lines.append(f"  - … {len(authority_baseline.get('pending_paths', [])) - limit} more path(s)")
    if changes["paths"]:
        lines.append("- **Currently observed changed paths:**")
        for path in changes["paths"][:limit]:
            lines.append(f"  - `{path}`")
        if len(changes["paths"]) > limit:
            lines.append(f"  - … {len(changes['paths']) - limit} more path(s)")
    if close_event:
        summary = str(close_payload.get("summary", "")).strip()
        if summary:
            lines.append(f"- **Last session summary:** {summary}")
        if close_changed:
            lines.append(f"- **Files recorded at Session Close:** {len(close_changed)}")
        if checks:
            lines.append(
                f"- **Last recorded Check:** {checks.get('claim', 'Scoped Check')} — {checks.get('status', 'UNKNOWN')}; "
                f"{checks.get('finding_count', 0)} finding(s); native gate {checks.get('native_gate_status', 'NOT_RUN')}; "
                f"{checks.get('truth_summary', {}).get('unresolved_count', 0) if isinstance(checks.get('truth_summary'), dict) else 0} unresolved truth-state record(s); "
                f"qualified native checks: {checks.get('check_qualification', {}).get('qualified_ratio', '0/0') if isinstance(checks.get('check_qualification'), dict) else '0/0'}; "
                f"checkpointed: {'yes' if checks.get('checkpointed') else 'no'}."
            )
    if isinstance(canonical, dict):
        style = canonical.get("verification_style", "project verification")
        lines.append(
            f"- **Canonical native gate:** `{canonical.get('source', '')}` "
            f"({approval.get('execution_mode', 'unassigned')}; {approval.get('status', 'required')}; {style})"
        )
        ecosystem = native_tools.get("ecosystem", {}) if isinstance(native_tools, dict) else {}
        members = ecosystem.get("members", []) if isinstance(ecosystem, dict) else []
        if members:
            lines.append(f"- **Native quality ecosystem:** {len(members)} subordinate or alternate member(s), catalogued but not absorbed.")
    else:
        lines.append("- **Canonical native gate:** None yet.")
    native_evidence = passport.get("evidence", {}).get("native_gate", {}) if isinstance(passport.get("evidence"), dict) else {}
    if isinstance(native_evidence, dict) and native_evidence.get("status"):
        lines.append(
            f"- **Latest native evidence:** {native_evidence.get('status')} with {native_evidence.get('entry_count', 0)} structured marker(s); "
            f"validity: {effective_native_validity(native_evidence, snapshot_fingerprint(changes['current_snapshot']))}; "
            f"truth: {native_evidence.get('truth', {}).get('truth_state', 'UNKNOWN') if isinstance(native_evidence.get('truth'), dict) else 'UNKNOWN'}; "
            f"tier: {native_evidence.get('verification_tier', 'sandbox')}."
        )
    runtime_proof_evidence = passport.get("evidence", {}).get("runtime_proof", {}) if isinstance(passport.get("evidence"), dict) else {}
    if isinstance(runtime_proof_evidence, dict) and runtime_proof_evidence.get("status"):
        counts = runtime_proof_evidence.get("counts", {}) if isinstance(runtime_proof_evidence.get("counts"), dict) else {}
        lines.append(
            f"- **Latest runtime recipes:** {runtime_proof_evidence.get('status')} across {runtime_proof_evidence.get('recipe_count', 0)} recipe(s); "
            f"{counts.get('PASS', 0)} passed, {counts.get('FAIL', 0)} failed, {counts.get('BLOCKED', 0)} blocked. "
            "HTTP content only; browser behavior and release readiness remain unproven."
        )
    last_check = state.get("last_check", {}) if isinstance(state.get("last_check"), dict) else {}
    last_matrix = last_check.get("runtime_state_matrices", {}) if isinstance(last_check.get("runtime_state_matrices"), dict) else {}
    if last_matrix:
        lines.append(
            f"- **Latest runtime-state matrix:** {last_matrix.get('status', 'UNKNOWN')}; "
            f"{last_matrix.get('confirmed_count', 0)} confirmed, {last_matrix.get('not_run_count', 0)} not run. "
            "Candidate, baseline, prior-state identity, migration bytes, and same-Check HTTP evidence only; Forge did not deploy or migrate."
        )
    coverage = passport.get("surface_coverage", {})
    if isinstance(coverage, dict) and coverage.get("status"):
        surfaces = coverage.get("surfaces", [])
        lines.append(f"- **Reported surface coverage:** {', '.join(surfaces) if surfaces else 'Unknown; native gate supplied no surface markers.'}")
    _append_items(lines, "Completed in the last session", completed, limit)
    decision_lines = [
        f"{str(item.get('text', '')).strip()} — **Rationale:** {str(item.get('rationale', '')).strip()}"
        for item in decisions
        if str(item.get("text", "")).strip()
    ]
    _append_items(lines, "Durable decisions", decision_lines, limit)
    fact_lines = [
        f"{str(item.get('text', '')).strip()} — **Design impact:** {str(item.get('impact', '')).strip()}"
        for item in owner_facts
        if str(item.get("text", "")).strip()
    ]
    _append_items(lines, "Owner-confirmed project facts", fact_lines, limit)
    continuity_facts = [item for item in continuity_register.get("facts", []) if isinstance(item, dict)]
    continuity_gaps = [item for item in continuity_register.get("gaps", []) if isinstance(item, dict) and item.get("status") == "open"]
    priority_order = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    continuity_gaps.sort(key=lambda item: (priority_order.get(str(item.get("priority", "medium")), 9), str(item.get("gap_id", ""))))
    if compact_mode:
        if continuity_facts:
            top = continuity_facts[0]
            lines.extend([
                "", "### Governed continuity facts",
                f"- {len(continuity_facts)} current; top: `{top.get('key', top.get('fact_id', 'fact'))}` [{top.get('trust', 'unknown')}].",
            ])
        if continuity_gaps:
            top = continuity_gaps[0]
            lines.extend([
                "", "### Known continuity gaps",
                f"- {len(continuity_gaps)} open; top: {top.get('priority', 'medium').upper()} `{top.get('gap_id', 'gap')}`.",
            ])
        if retrieval.get("results"):
            selected_ids = ", ".join(f"`{item.get('stable_id', '')}`" for item in retrieval.get("results", [])[:2])
            lines.extend([
                "", "### Traceable bounded retrieval",
                f"- {retrieval.get('result_count', 0)}/{retrieval.get('candidate_count', 0)} selected: {selected_ids}.",
                "- Orientation only; retrieval never changes authority.",
            ])
    else:
        if continuity_facts:
            lines.extend(["", "### Governed continuity facts"])
            fact_limit = min(limit, 3)
            for item in continuity_facts[:fact_limit]:
                rendered = str(item.get("value", ""))
                if len(rendered) > 180:
                    rendered = rendered[:179] + "…"
                lines.append(f"- **{item.get('key', item.get('fact_id', 'fact'))}** [{item.get('trust', 'unknown')}]: {rendered}")
            if len(continuity_facts) > fact_limit:
                lines.append(f"- … {len(continuity_facts) - fact_limit} more governed fact(s)")
        if continuity_gaps:
            lines.extend(["", "### Known continuity gaps"])
            gap_limit = min(limit, 3)
            for item in continuity_gaps[:gap_limit]:
                question = str(item.get("question", ""))
                if len(question) > 180:
                    question = question[:179] + "…"
                scopes = ", ".join(item.get("blocking_scopes", [])) or "informational"
                lines.append(f"- **{item.get('priority', 'medium').upper()} · {item.get('gap_id', 'gap')}**: {question} (blocks: {scopes})")
            if len(continuity_gaps) > gap_limit:
                lines.append(f"- … {len(continuity_gaps) - gap_limit} more open gap(s)")
        if retrieval.get("results"):
            lines.extend(["", "### Traceable bounded retrieval"])
            for item in retrieval.get("results", [])[: min(limit, 6)]:
                label = str(item.get("key") or item.get("text") or item.get("question") or item.get("stable_id", "record"))
                if len(label) > 180:
                    label = label[:179] + "…"
                lines.append(
                    f"- **{item.get('stable_id', '')}** [{item.get('trust', 'unknown')}; "
                    f"{item.get('support_status', 'unknown')}]: {label}"
                )
                reasons = ", ".join(item.get("selection_reasons", [])[:3])
                if reasons:
                    lines.append(f"  - Selected by: {reasons}")
            lines.append("- Orientation only; retrieval ranking does not change authority or support validity.")
    _append_items(lines, "Unresolved risks", risks, limit)
    pending_forks = decision_forks.get("pending", []) if isinstance(decision_forks, dict) else []
    if pending_forks:
        lines.extend(["", "### Pending decision forks"])
        for fork in pending_forks[:limit]:
            lines.append(f"- **{fork.get('title', fork.get('id', 'Decision fork'))}** (`{fork.get('id', '')}`)")
            lines.append(f"  - Constraint: {fork.get('existing_constraint', '')}")
            lines.append(f"  - Requested capability: {fork.get('requested_capability', '')}")
            lines.append(f"  - Recommendation: `{fork.get('recommendation', {}).get('option_id', '')}` — {fork.get('recommendation', {}).get('reason', '')}")
            lines.append(f"  - Required authority: {fork.get('required_authority', '')}")
            for option in fork.get('options', []):
                if isinstance(option, dict):
                    lines.append(f"  - Option `{option.get('id', '')}`: {option.get('label', '')}")
    governing = governing_decisions
    if governing:
        lines.extend(["", "### Governing decisions"])
        for item in governing[:limit]:
            accepted = item.get('accepted_option', {}) if isinstance(item.get('accepted_option'), dict) else {}
            rejected = [str(row.get('id', '')) for row in item.get('rejected_options', []) if isinstance(row, dict)]
            lines.append(f"- **{item.get('title', item.get('fork_id', 'Decision'))}** (`{item.get('fork_id', '')}`): accepted `{accepted.get('id', '')}` — {accepted.get('label', '')}")
            lines.append(f"  - Rationale: {item.get('rationale', '')}")
            lines.append(f"  - Authority: {item.get('authority', '')}; decision event: `{item.get('event_id', '')}`")
            if rejected:
                lines.append(f"  - Rejected options: {', '.join(f'`{value}`' for value in rejected)}")
    contradictions = decision_forks.get("contradictions", []) if isinstance(decision_forks, dict) else []
    if contradictions:
        lines.extend(["", "### Decision contradiction warnings"])
        for item in contradictions[:limit]:
            lines.append(f"- **{item.get('fork_id', 'decision')}**: {item.get('message', '')}")
            if item.get('paths'):
                lines.append(f"  - Observed paths: {', '.join(f'`{path}`' for path in item.get('paths', []))}")
    active_guardrails = guardrails.get("active", []) if isinstance(guardrails, dict) else []
    guardrail_attention = guardrails.get("attention", []) if isinstance(guardrails, dict) else []
    if active_guardrails:
        lines.extend(["", "### Active atomic safety guardrails and event obligations"])
        for item in active_guardrails[:limit]:
            surface_ids = [str(row.get("id", "")) for row in item.get("required_surfaces", []) if isinstance(row, dict)]
            if item.get("mode") == "event-obligation":
                lines.append(
                    f"- **{item.get('title', item.get('guardrail_id', 'Guardrail'))}** (`{item.get('guardrail_id', '')}`): "
                    f"temporary window closes at `{item.get('event_id', '')}`; revisit {', '.join(f'`{value}`' for value in surface_ids) or 'declared surfaces'}."
                )
                lines.append(f"  - Unsafe after closure: {item.get('unsafe_after_close', '')}")
            else:
                lines.append(
                    f"- **{item.get('title', item.get('guardrail_id', 'Guardrail'))}** (`{item.get('guardrail_id', '')}`): "
                    f"must land across {', '.join(f'`{value}`' for value in surface_ids) or 'declared surfaces'} as one canonical observed change set."
                )
                lines.append(f"  - Unsafe partial state: {item.get('unsafe_partial_state', '')}")
            lines.append(f"  - Verification boundary: {item.get('verification_boundary', '')}")
            lines.append(f"  - Authority: {item.get('authority', '')}; contract: `{item.get('contract_source', '')}`")
    if guardrail_attention:
        lines.extend(["", "### Guardrail attention"])
        for item in guardrail_attention[:limit]:
            lines.append(
                f"- **{item.get('title', item.get('guardrail_id', 'Guardrail'))}** (`{item.get('guardrail_id', '')}`): "
                f"{item.get('reason', 'Record the project-owned contract again before related work continues.')}"
            )
    active_trials = field_trials.get("active", []) if isinstance(field_trials, dict) else []
    trial_attention = field_trials.get("attention", []) if isinstance(field_trials, dict) else []
    if active_trials:
        lines.extend(["", "### Active field-validation trials"])
        for item in active_trials[:limit]:
            objective_rate = item.get("objective_recovery", {}).get("positive_rate") if isinstance(item.get("objective_recovery"), dict) else None
            authority_rate = item.get("authority_discovery", {}).get("positive_rate") if isinstance(item.get("authority_discovery"), dict) else None
            lines.append(
                f"- **{item.get('title', item.get('trial_id', 'Field trial'))}** (`{item.get('trial_id', '')}`): "
                f"{item.get('observation_count', 0)}/{item.get('minimum_observations', 0)} observation(s); {item.get('sample_status', 'unknown')}."
            )
            if objective_rate is not None or authority_rate is not None:
                lines.append(
                    "  - Observed correct-rate: "
                    f"objective {objective_rate if objective_rate is not None else 'not measured'}; "
                    f"authority {authority_rate if authority_rate is not None else 'not measured'}."
                )
            lines.append(f"  - Truth boundary: {item.get('truth_boundary', field_trials.get('truth_boundary', 'Project-local sample only.'))}")
    if trial_attention:
        lines.extend(["", "### Field-validation attention"])
        for item in trial_attention[:limit]:
            lines.append(
                f"- **{item.get('title', item.get('trial_id', 'Field trial'))}** (`{item.get('trial_id', '')}`): "
                "the project-owned trial contract is missing or changed; record the current contract again before adding observations."
            )
    recommendations = capabilities.get("recommendations", []) if isinstance(capabilities, dict) else []
    active_capabilities = capabilities.get("active", []) if isinstance(capabilities, dict) else []
    capability_attention = capabilities.get("attention", []) if isinstance(capabilities, dict) else []
    if active_capabilities:
        lines.extend(["", "### Active advanced capabilities"])
        for item in active_capabilities[:limit]:
            lines.append(
                f"- **{item.get('name', item.get('capability_id', 'Capability'))}**: `{item.get('status', '')}`; "
                f"operation `{item.get('operation', '')}`; contract `{item.get('contract_source', '')}`."
            )
    if capability_attention:
        lines.extend(["", "### Capability activation attention"])
        for item in capability_attention[:limit]:
            lines.append(
                f"- **{item.get('name', item.get('capability_id', 'Capability'))}**: `{item.get('status', '')}`. "
                "Reactivate through Adopt with a current project-owned contract."
            )
    if recommendations:
        lines.extend(["", "### Capability recommendations"])
        for item in recommendations[:limit]:
            lines.append(f"- **{item.get('capability_id', 'capability')}**: {item.get('reason', '')}")
            if item.get("activation"):
                lines.append(f"  - Activation path: `{item.get('activation')}`")
    if rules:
        lines.extend(["", "### Governing rules"])
        lines.extend(f"- {rule}" for rule in rules)
    if uncertainties:
        lines.extend(["", "### Unresolved uncertainty"])
        lines.extend(f"- {item}" for item in uncertainties)
    observed_telemetry = telemetry.get("observed", {}) if isinstance(telemetry, dict) else {}
    exact_telemetry = telemetry.get("exact_provider", {}) if isinstance(telemetry, dict) else {}
    benchmark = telemetry.get("benchmark", {}) if isinstance(telemetry, dict) else {}
    break_even = benchmark.get("break_even", {}) if isinstance(benchmark, dict) else {}
    lines.extend([
        "",
        "## Efficiency telemetry",
        f"- **Initialization overhead observed:** {observed_telemetry.get('initialization_duration_ms', 0)} ms for the first Adopt recorded locally.",
        f"- **Current continuity reuse:** {cached_records_reused} cached project record(s) and {evidence_records_reused} current evidence record(s) reused.",
        f"- **Exact provider-token sessions supplied:** {exact_telemetry.get('session_count', 0)}; total {exact_telemetry.get('total_tokens', 0)} token(s).",
        "- **Current Resume token estimate:** __RESUME_TOKEN_ESTIMATE__ (heuristic characters/4; not provider measurement and not savings).",
        "- **Context economics:** this Resume is ~__RESUME_TOKEN_ESTIMATE__ tokens; reading the whole project is ~__REPO_TOKENS__ tokens (__CONTEXT_RATIO__). A trustworthy Resume is only a saving when the model can act from it without re-reading the tree.",
        f"- **Controlled benchmark:** {break_even.get('status', 'insufficient-pairs')} — {break_even.get('conclusion', 'Break-even is not established.')}",
        f"- **Suitability:** {telemetry.get('suitability', 'Break-even remains unknown.')}" if isinstance(telemetry, dict) else "- **Suitability:** Break-even remains unknown.",
        "",
        "## Expert evidence references",
        "- `.forge/passport.json` — identity, scope, maturity, and uncertainty",
        "- `.forge/authorities.json` — ranked authority candidates and objective provenance",
        "- `.forge/native-tools.json` — native gate candidates and approval state",
        "- `.forge/ledger.jsonl` — append-only project continuity history, including Session Close and field observations",
        "- `.forge/settings.json` — bounded settings and project-owned contracts, including lineage and merge-candidate records",
        "- `.forge/state.json` — observed checkpoint, explicit authority baseline, last Check, and latest Session Close reference",
        "- `.forge/evidence/native-gate/` — raw native output and parsed evidence, created only after explicit execution",
        "- Runtime-proof response bodies are never stored; only bounded assertion results and response digests are retained in Passport/Ledger references",
        "",
        "## Scope boundary",
        "This Resume does not claim runtime, browser, database, deployment, migration, or release assurance.",
    ])
    markdown = "\n".join(lines).rstrip() + "\n"
    placeholder = "__RESUME_TOKEN_ESTIMATE__"
    repo_tokens = max(1, round(int(changes.get("current_snapshot", {}).get("total_bytes", 0)) / 4))
    measured = markdown.replace(placeholder, "0").replace("__REPO_TOKENS__", "0").replace("__CONTEXT_RATIO__", "0")
    heuristic_tokens = max(1, round(len(measured) / 4))
    ratio = repo_tokens / heuristic_tokens
    if ratio >= 1.5:
        ratio_text = f"~{ratio:.0f}x lighter than reading the whole project"
    elif ratio >= 0.7:
        ratio_text = "about the same size as reading the project"
    else:
        ratio_text = f"~{1 / ratio:.0f}x heavier than the project itself — Forge overhead exceeds the read at this size"
    markdown = (
        markdown.replace(placeholder, str(heuristic_tokens))
        .replace("__REPO_TOKENS__", f"{repo_tokens:,}")
        .replace("__CONTEXT_RATIO__", ratio_text)
    )
    telemetry = summarize_telemetry(
        project_root,
        current_resume_characters=len(markdown),
        current_cached_records=cached_records_reused,
        current_evidence_records_reused=evidence_records_reused,
    )
    write_text_atomic(paths.resume, markdown)
    attention_items: list[dict[str, str]] = []

    def add_attention(severity: str, category: str, message: str) -> None:
        clean = str(message).strip()
        if not clean or any(item["message"] == clean for item in attention_items):
            return
        attention_items.append({"severity": severity, "category": category, "message": clean})

    for uncertainty in uncertainties:
        add_attention("warning", "uncertainty", str(uncertainty))
    if not objective_text:
        # A missing objective blocks changes and Ship, not orientation. On a clean
        # read-only first contact, keep it a warning so Forge orients instead of
        # blocking; it becomes a blocker once there are changes to govern.
        add_attention(
            "blocker" if changes.get("count", 0) else "warning",
            "objective",
            "Current objective is not confirmed.",
        )
    if continuity.get("status") == "stale":
        add_attention("warning", "continuity", str(continuity.get("reason", "Continuity requires attention.")))
    if authority_baseline.get("status") == "NOT_ESTABLISHED":
        add_attention("warning", "authority-baseline", "No authority baseline; Ship authority unavailable.")
    elif authority_baseline.get("status") == "QUARANTINED":
        add_attention("warning", "authority-baseline", f"{authority_baseline.get('pending_count', 0)} path(s) differ from the explicit authority baseline and remain quarantined until reviewed and reauthorized.")
    elif authority_baseline.get("status") == "CONTRADICTED":
        add_attention("blocker", "authority-baseline", "The stored authority-baseline fingerprint contradicts its snapshot; preserve state and investigate before authorizing a candidate.")
    elif not authority_baseline.get("release_eligible"):
        add_attention("warning", "authority-baseline", "The authority baseline is current but bounded rather than exact; it cannot support the authority-bound Ship claim.")
    if project_lineage.get("status") in {"CONTRADICTED", "APPROVAL_REQUIRED", "BLOCKED"}:
        add_attention("blocker", "lineage", str(project_lineage.get("reason", "Project lineage requires authority attention.")))
    elif project_lineage.get("status") == "NOT_RECORDED":
        add_attention("warning", "lineage", "No exact parent/tree lineage is recorded; continuation ancestry and same-version collision detection are unavailable.")
    elif project_lineage.get("same_version_candidate_collision_count", 0):
        add_attention("blocker", "lineage", "An unresolved incoming branch reuses the active display version for different exact tree bytes.")
    elif project_lineage.get("unmatched_parent_count", 0):
        add_attention("warning", "lineage", "One or more incoming branches have a parent that does not match the active authority lineage and remain quarantined.")
    if migration_identity.get("status") in {"CONTRADICTED", "BLOCKED"}:
        add_attention("blocker", "migration-identity", str(migration_identity.get("reason", "Migration identity is contradicted.")))
    elif migration_identity.get("status") == "RECONCILIATION_REQUIRED":
        add_attention("blocker", "migration-identity", str(migration_identity.get("reason", "Migration sequence collisions require reconciliation.")))
    elif migration_identity.get("status") == "NOT_DECLARED":
        add_attention("warning", "migration-identity", "Record an exact migration catalog or explicit no-migrations declaration for the active lineage.")
    elif migration_identity.get("applied_observation", {}).get("status") in {"body-unknown", "incomplete"}:
        add_attention("warning", "migration-identity", "Applied migration testimony is incomplete or does not bind every sequence to semantic and body identity.")
    if package_family.get("status") in {"CONTRADICTED", "BLOCKED"}:
        add_attention("blocker", "package-family", str(package_family.get("reason", "Package-family applicability is contradicted.")))
    elif package_family.get("status") == "NOT_DECLARED":
        add_attention("warning", "package-family", "Record exact package-family, outer-bundle, and changed-files applicability proof for the active lineage.")
    if surface_coverage.get("status") in {"CONTRADICTED", "BLOCKED"}:
        add_attention("blocker", "surface-coverage", str(surface_coverage.get("reason", "Surface-to-evidence coverage is contradicted.")))
    elif surface_coverage.get("status") == "NOT_DECLARED":
        add_attention("warning", "surface-coverage", "Record an exact surface inventory and evidence-tier map for the active package family.")
    elif surface_coverage.get("coverage_status") != "COMPLETE":
        add_attention("warning", "surface-coverage", str(surface_coverage.get("reason", "Declared surfaces still have evidence gaps.")))
    if risks:
        add_attention("warning", "risk", "The latest Session Close contains unresolved risks.")
    if checks.get("status") in {"FAIL", "ERROR", "BLOCKED"}:
        add_attention("blocker", "verification", "The latest recorded Check did not pass.")
    if decision_forks.get("pending"):
        add_attention("blocker", "decision", "A high-impact decision fork requires authority before implementation continues.")
    if decision_forks.get("contradictions"):
        add_attention("blocker", "decision", "Observed work may contradict a confirmed governing decision.")
    if capability_attention:
        add_attention("warning", "capability", "An advanced capability activation contract is missing or changed and requires explicit reactivation.")
    if guardrail_attention:
        add_attention("blocker", "guardrail", "An authority-recorded guardrail contract is missing or changed and must be recorded again before related work continues.")
    if ledger_assertions.get("attention"):
        add_attention("blocker", "ledger", "An authority-recorded Ledger assertion is missing or changed and requires renewed approval.")
    if check_qualifications.get("attention", 0):
        add_attention("warning", "qualification", "One or more check qualifications are stale because their check source, contract, or negative-test evidence changed.")
    if provenance.get("attention", 0):
        add_attention("warning", "provenance", "One or more artifact provenance contracts changed or disappeared and require renewed authority.")
    if provenance.get("unregistered_deliverables", 0):
        add_attention("warning", "delivery", "Deliverable-shaped files exist outside registered artifact provenance; delivery assurance is unavailable.")
    if deployable_boundaries.get("attention", 0):
        add_attention("warning", "delivery", "One or more deployable-boundary contracts changed or disappeared and require renewed authority.")
    if canonical_claims.get("attention", 0):
        add_attention("warning", "claims", "One or more canonical-claim contracts changed or disappeared and require renewed authority.")
    if relationships.get("attention_count", 0):
        add_attention("warning", "relationships", "One or more confirmed relationship sets changed, disappeared, or lost a required endpoint and require authority attention.")
    if trial_attention:
        add_attention("warning", "field-trial", "A field-validation trial contract is missing or changed and must be recorded again before new observations are accepted.")
    if presentation_profile.get("attention", 0):
        add_attention("warning", "presentation", "The project-owned presentation profile changed or disappeared and requires renewed authority.")
    if release_distribution.get("status") in {"FAIL", "PARTIAL"}:
        add_attention("warning", "release-distribution", "Signed artifact or release-channel distribution evidence is incomplete or stale.")
    if release_proof.get("status") in {"FAIL", "PARTIAL"}:
        add_attention("warning", "release-proof", "The bounded exact-package release-surface assurance map is incomplete, stale, expired, or contradicted.")
    if cold_session.get("status") in {"FAIL", "PARTIAL"}:
        add_attention("warning", "cold-session", "Matched cold-session validation is incomplete or outside the owner-approved thresholds.")
    if continuity_register.get("status") in {"APPROVAL_REQUIRED", "STALE"}:
        add_attention("warning", "continuity-register", str(continuity_register.get("reason", "The governed continuity register requires attention.")))
    for gap in continuity_register.get("gaps", []):
        if not isinstance(gap, dict) or gap.get("status") != "open":
            continue
        if gap.get("priority") == "blocker" and ({"resume", "check"} & set(gap.get("blocking_scopes", []))):
            add_attention("blocker", "continuity-gap", f"{gap.get('gap_id', 'continuity gap')}: {gap.get('question', '')}")
    if knowledge_delta.get("stale"):
        add_attention("warning", "knowledge", "One or more previously supported project facts are stale and should be confirmed before relying on them.")
    for reason in self_currency.get("attention", []):
        text = str(reason)
        severity = "blocker" if "objective" in text.casefold() and "no explicit" in text.casefold() else "warning"
        add_attention(severity, "self-currency", text)
    order = {"blocker": 0, "warning": 1, "notice": 2}
    attention_items.sort(key=lambda item: (order.get(item["severity"], 9), item["category"], item["message"]))
    attention_reasons = [item["message"] for item in attention_items]
    attention_counts = {
        "blocker": sum(1 for item in attention_items if item["severity"] == "blocker"),
        "warning": sum(1 for item in attention_items if item["severity"] == "warning"),
        "notice": sum(1 for item in attention_items if item["severity"] == "notice"),
    }
    record_metric(project_root, "resume", {
        "duration_ms": round((time.monotonic() - started) * 1000),
        "budget": budget,
        "output_characters": len(markdown),
        "output_characters_source": "observed",
        "resume_token_estimate": heuristic_tokens,
        "resume_token_estimate_source": "heuristic-characters-divided-by-four",
        "cached_records_reused": cached_records_reused,
        "evidence_records_reused": evidence_records_reused,
        "changes": changes["count"],
        "authority_baseline_status": authority_baseline.get("status", "NOT_ESTABLISHED"),
        "authority_quarantined_paths": authority_baseline.get("pending_count", 0),
        "continuity_status": continuity.get("status", "unknown"),
        "session_close_present": bool(close_event),
        "self_currency_status": self_currency.get("status", "UNKNOWN"),
        "truth_unresolved": self_currency.get("summary", {}).get("unresolved_count", 0),
        "active_relationship_sets": relationships.get("active_count", 0),
        "retrieval_candidates": retrieval.get("candidate_count", 0),
        "retrieval_results": retrieval.get("result_count", 0),
        "relationship_impacts": relationships.get("impact_count", 0),
        "related_paths": relationships.get("related_path_count", 0),
    })
    return {
        "schema": 1,
        "generated_utc": utc_now(),
        "status": "ATTENTION" if attention_reasons else "READY",
        "objective": objective,
        "next_action": {"text": next_action, "source": next_action_source},
        "changes": changes,
        "authority_baseline": authority_baseline,
        "check_plan": current_check_plan,
        "continuity": continuity,
        "session_close": close_payload if close_event else {},
        "decision_forks": decision_forks,
        "advanced_capabilities": capabilities,
        "project_identity": project_identity,
        "project_lineage": project_lineage,
        "migration_identity": migration_identity,
        "package_family": package_family,
        "surface_coverage": surface_coverage,
        "release_facts": release_facts,
        "continuity_register": continuity_register,
        "third_party_intakes": third_party_intakes,
        "bounded_retrieval": retrieval,
        "sidecar": sidecar,
        "guardrails": guardrails,
        "ledger_assertions": ledger_assertions,
        "check_qualifications": check_qualifications,
        "artifact_provenance": provenance,
        "deployable_boundaries": deployable_boundaries,
        "canonical_claims": canonical_claims,
        "relationships": {
            "status": relationships.get("status", "NOT_CONFIGURED"),
            "active_count": relationships.get("active_count", 0),
            "attention_count": relationships.get("attention_count", 0),
            "impact_count": relationships.get("impact_count", 0),
            "related_path_count": relationships.get("related_path_count", 0),
            "scan_bounded": relationships.get("scan_bounded", False),
            "truth_boundary": relationships.get("truth_boundary", ""),
        },
        "field_trials": field_trials,
        "presentation_profile": presentation_profile,
        "release_distribution": release_distribution,
        "release_proof": release_proof,
        "cold_session_validation": cold_session,
        "knowledge_delta": knowledge_delta,
        "self_currency": self_currency,
        "truth_summary": self_currency.get("summary", {}),
        "telemetry": telemetry,
        "attention_reasons": attention_reasons,
        "attention_items": attention_items,
        "attention_counts": attention_counts,
        "uncertainties": uncertainties,
        "markdown": markdown,
        "output": str(paths.resume),
    }

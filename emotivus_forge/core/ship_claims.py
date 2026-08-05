from __future__ import annotations

from pathlib import Path
from typing import Any

from .authority_registry import load_or_discover_authorities
from .authority_baseline import assess_authority_baseline
from .changes import detect_changes
from .common import read_json
from .native_tools import load_or_discover_native_tools
from .paths import ForgePaths
from .self_currency import assess_self_currency
from .session_close import assess_continuity
from .state import is_adopted, load_settings, load_state
from .state_transitions import state_transition_summary
from .release_package import evaluate_release_package
from .release_distribution import evaluate_release_distribution
from .cold_session_validation import evaluate_cold_session_validation
from .release_proof import evaluate_release_proof
from .release_authorization import evaluate_release_authorization
from .lineage import lineage_summary
from .migration_identity import migration_identity_summary
from .package_family import package_family_summary
from .surface_coverage import surface_coverage_summary
from .release_facts import release_facts_summary
from .continuity_register import continuity_register_summary


CLAIM_ORDER = (
    "continuity-ready",
    "checkpointed-candidate",
    "authority-recorded-candidate",
    "lineage-identified-candidate",
    "migration-history-identified-candidate",
    "package-family-identified-candidate",
    "surface-coverage-mapped-candidate",
    "native-verified-candidate",
    "release-facts-current-candidate",
    "runtime-content-verified",
    "persisted-state-assured",
    "final-package-bound",
    "confidentiality-screened",
    "public-release-reviewed",
    "artifact-signature-verified",
    "release-channel-bound",
    "remote-channel-verified",
    "release-proof-validated",
    "cold-session-validated",
    "owner-release-authorized",
    "release-ready",
)


def _requirement(requirement_id: str, status: str, reason: str) -> dict[str, str]:
    return {"requirement_id": requirement_id, "status": status, "reason": reason}


def _rollup(rows: list[dict[str, str]]) -> str:
    statuses = [str(row.get("status", "UNKNOWN")) for row in rows]
    if any(value in {"FAIL", "BLOCKED"} for value in statuses):
        return "FAIL"
    if statuses and all(value == "PASS" for value in statuses):
        return "PASS"
    if statuses and all(value == "NOT_RUN" for value in statuses):
        return "NOT_RUN"
    return "PARTIAL"


def _level(level_id: str, title: str, claim: str, rows: list[dict[str, str]], exclusions: list[str]) -> dict[str, Any]:
    return {
        "level_id": level_id,
        "title": title,
        "status": _rollup(rows),
        "claim": claim,
        "requirements": rows,
        "exclusions": exclusions,
    }


def _ratio_all_qualified(value: Any) -> tuple[bool, int, int]:
    text = str(value or "0/0").strip()
    try:
        left, right = (int(part) for part in text.split("/", 1))
    except (TypeError, ValueError):
        return False, 0, 0
    return right > 0 and left == right, left, right


def assess_ship_claims(project_root: Path, forge_root: Path, *, perform_remote: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    if not is_adopted(project_root):
        levels = [
            _level(
                "continuity-ready",
                "Continuity ready",
                "Forge has enough current continuity to guide a new development session.",
                [_requirement("project-adopted", "NOT_RUN", "The project has not been adopted by Forge.")],
                ["code correctness", "verification", "release readiness"],
            )
        ]
        for level_id, title in (
            ("checkpointed-candidate", "Checkpointed candidate"),
            ("authority-recorded-candidate", "Authority-recorded candidate"),
            ("lineage-identified-candidate", "Lineage-identified candidate"),
            ("migration-history-identified-candidate", "Migration-history identified candidate"),
            ("package-family-identified-candidate", "Package-family identified candidate"),
            ("surface-coverage-mapped-candidate", "Surface-coverage mapped candidate"),
            ("native-verified-candidate", "Native-verified candidate"),
            ("release-facts-current-candidate", "Release facts current candidate"),
            ("runtime-content-verified", "Runtime-content verified"),
            ("persisted-state-assured", "Persisted-state assured"),
            ("final-package-bound", "Final package bound"),
            ("confidentiality-screened", "Confidentiality screened"),
            ("public-release-reviewed", "Public release reviewed"),
            ("artifact-signature-verified", "Artifact signature verified"),
            ("release-channel-bound", "Release channel bound"),
            ("remote-channel-verified", "Remote channel verified"),
            ("release-proof-validated", "Release Proof validated"),
            ("cold-session-validated", "Cold-session validated"),
            ("owner-release-authorized", "Owner release authorized"),
        ):
            levels.append(_level(level_id, title, "No claim is available before adoption.", [_requirement("prior-level", "NOT_RUN", "Continuity is not established.")], ["all project and release claims"]))
        levels.append(_level(
            "release-ready",
            "Release ready",
            "No release-ready claim is available before adoption.",
            [_requirement("project-adopted", "NOT_RUN", "The project has not been adopted by Forge.")],
            ["all project and release claims"],
        ))
        return _result(levels)

    paths = ForgePaths(project_root)
    passport = read_json(paths.passport, {})
    authorities = read_json(paths.authorities, {})
    native_tools = read_json(paths.native_tools, {})
    if not isinstance(passport, dict):
        passport = {}
    if not isinstance(authorities, dict):
        authorities = load_or_discover_authorities(project_root, forge_root, refresh=False)
    if not isinstance(native_tools, dict):
        native_tools = load_or_discover_native_tools(project_root, forge_root, refresh=False)
    state = load_state(project_root)
    settings = load_settings(project_root)
    current_snapshot = state.get("snapshot", {}) if isinstance(state.get("snapshot"), dict) else {}
    changes = detect_changes(project_root, forge_root, current_snapshot, settings)
    authority_baseline = assess_authority_baseline(state, changes.get("current_snapshot", {}))
    project_lineage = lineage_summary(project_root, forge_root)
    migration_identity = migration_identity_summary(project_root, forge_root)
    package_family = package_family_summary(project_root, forge_root)
    surface_coverage = surface_coverage_summary(project_root, forge_root)
    release_facts = release_facts_summary(project_root, forge_root)
    continuity_register = continuity_register_summary(project_root)
    continuity = assess_continuity(project_root, current_snapshot=changes.get("current_snapshot", {}))
    currency = assess_self_currency(project_root, passport, authorities, native_tools)
    last_check = state.get("last_check", {}) if isinstance(state.get("last_check"), dict) else {}

    continuity_rows = [
        _requirement("project-adopted", "PASS", "The eight-file Forge continuity state exists."),
        _requirement(
            "continuity-current",
            "PASS" if continuity.get("status") == "current" else "NOT_RUN" if continuity.get("status") == "not-established" else "FAIL",
            str(continuity.get("reason", "Continuity status is unavailable.")),
        ),
        _requirement(
            "forge-self-currency",
            "PASS" if currency.get("status") == "PASS" else "FAIL",
            "Forge's objective, authority, native-tool, and evidence records describe the current project." if currency.get("status") == "PASS" else "Forge self-currency has unresolved or stale records.",
        ),
        _requirement(
            "continuity-register-current",
            "PASS" if continuity_register.get("status") == "CURRENT" else "NOT_RUN" if continuity_register.get("status") == "NOT_DECLARED" else "FAIL",
            str(continuity_register.get("reason", "No governed continuity register assessment is available.")),
        ),
        _requirement(
            "ship-blocking-knowledge-gaps-resolved",
            "PASS" if continuity_register.get("status") == "CURRENT" and int(continuity_register.get("ship_blocking_gap_count", 0) or 0) == 0 else "NOT_RUN" if continuity_register.get("status") == "NOT_DECLARED" else "FAIL",
            "No open knowledge gap is explicitly scoped to block Ship or release."
            if continuity_register.get("status") == "CURRENT" and int(continuity_register.get("ship_blocking_gap_count", 0) or 0) == 0
            else f"{continuity_register.get('ship_blocking_gap_count', 0)} open knowledge gap(s) explicitly block Ship or release."
            if continuity_register.get("status") == "CURRENT"
            else "A current governed continuity register is required before Ship can assess blocking knowledge gaps.",
        ),
    ]
    levels = [
        _level(
            "continuity-ready",
            "Continuity ready",
            "Forge can guide a new session from current authority and continuity records.",
            continuity_rows,
            ["code correctness", "native verification", "runtime behavior", "release readiness"],
        )
    ]

    truth = last_check.get("truth_summary", {}) if isinstance(last_check.get("truth_summary"), dict) else {}
    unresolved_rows = truth.get("unresolved", []) if isinstance(truth.get("unresolved"), list) else []
    checkpoint_blockers = [
        row for row in unresolved_rows
        if isinstance(row, dict)
        and not str(row.get("subject", "")).startswith("native-gate.")
        and not str(row.get("subject", "")).startswith("authority-baseline.")
        and str(row.get("truth_state", "")) in {"UNKNOWN", "BLOCKED_ATTEMPTED", "BLOCKED_UNATTEMPTED", "STALE", "CONTRADICTED"}
    ]
    checkpoint_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Continuity-ready claim is required first."),
        _requirement("last-check-pass", "PASS" if last_check.get("status") == "PASS" else "NOT_RUN", "The latest scoped Check must pass."),
        _requirement("checkpointed", "PASS" if last_check.get("checkpointed") is True else "NOT_RUN", "The passing Check must explicitly checkpoint the observed candidate."),
        _requirement("candidate-unchanged", "PASS" if changes.get("count") == 0 else "FAIL", "No project paths changed after the checkpoint." if changes.get("count") == 0 else f"{changes.get('count', 0)} path(s) changed after the checkpoint."),
        _requirement("checkpoint-truth-resolved", "PASS" if not checkpoint_blockers else "FAIL", "No checkpoint-relevant stale, contradicted, blocked, or unknown truth records remain; native verification is assessed at the next claim level." if not checkpoint_blockers else f"The checkpoint has {len(checkpoint_blockers)} checkpoint-relevant unresolved truth-state record(s)."),
    ]
    levels.append(_level(
        "checkpointed-candidate",
        "Checkpointed candidate",
        "The current observed tree matches a passing explicit Forge checkpoint.",
        checkpoint_rows,
        ["project-authority acceptance", "complete native coverage", "runtime behavior", "deployment", "release readiness"],
    ))

    authority_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Checkpointed-candidate claim is required first."),
        _requirement(
            "explicit-authority-baseline",
            "PASS" if authority_baseline.get("status") == "CURRENT" else "NOT_RUN" if authority_baseline.get("status") == "NOT_ESTABLISHED" else "FAIL",
            str(authority_baseline.get("reason", "No authority-baseline assessment is available.")),
        ),
        _requirement(
            "exact-authority-snapshot",
            "PASS" if authority_baseline.get("release_eligible") else "NOT_RUN" if authority_baseline.get("status") == "NOT_ESTABLISHED" else "FAIL",
            "The current authority baseline includes every observed path and SHA-256 hashes every included file."
            if authority_baseline.get("release_eligible") else "The authority baseline is missing, quarantined, contradicted, or bounded by scan/hash budgets.",
        ),
        _requirement(
            "check-after-authorization",
            "PASS" if last_check.get("authority_current") is True and str(last_check.get("authority_baseline_id", "")) == str(authority_baseline.get("baseline_id", "")) and last_check.get("checkpointed") is True else "NOT_RUN",
            "The latest passing checkpoint was recorded after the current authority baseline and against the same unchanged tree."
            if last_check.get("authority_current") is True and str(last_check.get("authority_baseline_id", "")) == str(authority_baseline.get("baseline_id", "")) and last_check.get("checkpointed") is True else "Run a passing Check --checkpoint after recording the current authority baseline.",
        ),
    ]
    levels.append(_level(
        "authority-recorded-candidate",
        "Authority-recorded candidate",
        "The exact current project tree matches an explicit project-authority baseline and was checkpointed by a later passing Check.",
        authority_rows,
        ["authenticated human identity", "file authorship", "substantive review quality", "native coverage", "runtime behavior", "release readiness"],
    ))

    lineage_status = str(project_lineage.get("status", "NOT_RECORDED"))
    lineage_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Authority-recorded-candidate claim is required first."),
        _requirement(
            "exact-project-lineage",
            "PASS" if lineage_status == "CURRENT" else "NOT_RUN" if lineage_status == "NOT_RECORDED" else "FAIL",
            str(project_lineage.get("reason", "No exact project lineage assessment is available.")),
        ),
        _requirement(
            "no-unresolved-same-version-branch",
            "PASS" if int(project_lineage.get("same_version_candidate_collision_count", 0) or 0) == 0 else "FAIL",
            "No unresolved incoming branch reuses the active display version for different exact tree bytes."
            if int(project_lineage.get("same_version_candidate_collision_count", 0) or 0) == 0
            else f"{project_lineage.get('same_version_candidate_collision_count', 0)} unresolved same-version branch collision(s) remain quarantined.",
        ),
    ]
    levels.append(_level(
        "lineage-identified-candidate",
        "Lineage-identified candidate",
        "The authority-recorded candidate has an exact parent/package/tree lineage and no unresolved same-version incoming-branch collision.",
        lineage_rows,
        ["authorship", "semantic merge compatibility", "migration correctness", "substantive review quality", "release readiness"],
    ))

    migration_status = str(migration_identity.get("status", "NOT_DECLARED"))
    applied_status = str(migration_identity.get("applied_observation", {}).get("status", "not-observed"))
    migration_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Lineage-identified-candidate claim is required first."),
        _requirement(
            "exact-migration-catalog",
            "PASS" if migration_status in {"CURRENT", "CURRENT_WITH_RECONCILIATION"} else "NOT_RUN" if migration_status == "NOT_DECLARED" else "FAIL",
            str(migration_identity.get("reason", "No exact migration identity assessment is available.")),
        ),
        _requirement(
            "no-unresolved-migration-collision",
            "PASS" if int(migration_identity.get("unresolved_collision_count", 0) or 0) == 0 else "FAIL",
            "No same-number/different-body or same-semantic/different-body collision remains unresolved."
            if int(migration_identity.get("unresolved_collision_count", 0) or 0) == 0
            else f"{migration_identity.get('unresolved_collision_count', 0)} migration identity collision(s) require append-after-highest reconciliation.",
        ),
        _requirement(
            "applied-ledger-not-contradicted",
            "PASS" if applied_status not in {"contradicted", "body-unknown"} else "FAIL",
            "Any supplied applied-migration testimony does not contradict the exact catalog."
            if applied_status not in {"contradicted", "body-unknown"}
            else f"Applied migration testimony is {applied_status}; sequence-only or mismatched-body records cannot support this claim.",
        ),
    ]
    levels.append(_level(
        "migration-history-identified-candidate",
        "Migration-history identified candidate",
        "The exact project lineage has an exact migration catalog or explicit no-migrations declaration, with known sequence/body collisions structurally reconciled.",
        migration_rows,
        ["migration execution", "live database correctness", "upgrade-path success", "rollback correctness", "deployment state", "release readiness"],
    ))

    package_status = str(package_family.get("status", "NOT_DECLARED"))
    package_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Migration-history-identified-candidate claim is required first."),
        _requirement(
            "exact-package-family",
            "PASS" if package_status == "CURRENT" else "NOT_RUN" if package_status == "NOT_DECLARED" else "FAIL",
            str(package_family.get("reason", "No exact package-family assessment is available.")),
        ),
        _requirement(
            "lineage-result-artifact",
            "PASS" if package_status == "CURRENT" and bool(package_family.get("lineage_result_artifact_ids")) else "NOT_RUN" if package_status == "NOT_DECLARED" else "FAIL",
            "At least one exact family artifact normalizes to the active lineage tree." if package_status == "CURRENT" else "No current exact result artifact is bound to the active lineage.",
        ),
    ]
    levels.append(_level(
        "package-family-identified-candidate",
        "Package-family identified candidate",
        "The migration-identified candidate belongs to one exact package family whose declared outer bundles and changed-files deltas are byte-bound and reconstructible.",
        package_rows,
        ["application execution", "semantic patch correctness", "undeclared artifacts", "deployment safety", "release readiness"],
    ))

    surface_status = str(surface_coverage.get("status", "NOT_DECLARED"))
    coverage_status = str(surface_coverage.get("coverage_status", "NOT_RUN"))
    surface_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Package-family-identified-candidate claim is required first."),
        _requirement(
            "exact-surface-inventory",
            "PASS" if surface_status == "CURRENT" else "NOT_RUN" if surface_status == "NOT_DECLARED" else "FAIL",
            str(surface_coverage.get("reason", "No exact surface-to-evidence inventory is available.")),
        ),
        _requirement(
            "project-required-surface-evidence",
            "PASS" if surface_status == "CURRENT" and coverage_status == "COMPLETE" else "NOT_RUN" if surface_status == "NOT_DECLARED" else "FAIL",
            "Every declared surface has current explicit PASS evidence at its project-required tier."
            if surface_status == "CURRENT" and coverage_status == "COMPLETE"
            else str(surface_coverage.get("reason", "Declared surfaces still have evidence gaps.")),
        ),
    ]
    levels.append(_level(
        "surface-coverage-mapped-candidate",
        "Surface-coverage mapped candidate",
        "The exact package-family candidate has a current project-owned surface inventory whose declared routes and journeys are joined to explicit evidence tiers without inferred coverage.",
        surface_rows,
        ["undeclared surfaces", "evidence tiers not explicitly receipted", "reviewer competence", "database, browser, device, staging, production, or deployment behavior beyond the exact receipts", "release readiness"],
    ))

    native_evidence = passport.get("evidence", {}).get("native_gate", {}) if isinstance(passport.get("evidence"), dict) else {}
    native_status = str(native_evidence.get("status", "NOT_RUN")) if isinstance(native_evidence, dict) else "NOT_RUN"
    native_validity = str(native_evidence.get("validity", "unknown")) if isinstance(native_evidence, dict) else "unknown"
    qualified, qualified_count, qualification_total = _ratio_all_qualified(
        last_check.get("check_qualification", {}).get("qualified_ratio", "0/0") if isinstance(last_check.get("check_qualification"), dict) else "0/0"
    )
    native_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Surface-coverage-mapped-candidate claim is required first."),
        _requirement("native-gate-pass", "PASS" if native_status == "PASS" and native_validity == "current" else "NOT_RUN" if native_status in {"", "NOT_RUN"} else "FAIL", "Current candidate-bound native evidence reports PASS." if native_status == "PASS" and native_validity == "current" else f"Native evidence is {native_status} with validity {native_validity}."),
        _requirement("native-checks-qualified", "PASS" if qualified else "NOT_RUN" if qualification_total == 0 else "FAIL", f"{qualified_count}/{qualification_total} native evidence checks are qualified against current known-bad cases."),
    ]
    levels.append(_level(
        "native-verified-candidate",
        "Native-verified candidate",
        "The checkpointed candidate has current native evidence and current detector qualification evidence.",
        native_rows,
        ["browser behavior unless explicitly covered", "deployment", "persisted-state transition correctness", "release readiness"],
    ))

    release_fact_status = str(release_facts.get("status", "NOT_DECLARED"))
    release_fact_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Native-verified-candidate claim is required first."),
        _requirement(
            "authoritative-visible-release-facts",
            "PASS" if release_fact_status == "CURRENT" else "NOT_RUN" if release_fact_status == "NOT_DECLARED" else "FAIL",
            str(release_facts.get("reason", "No authoritative exact-package release fact assessment is available.")),
        ),
        _requirement(
            "no-stale-declared-document-values",
            "PASS" if release_fact_status == "CURRENT" and int(release_facts.get("failed_count", 0) or 0) == 0 else "NOT_RUN" if release_fact_status == "NOT_DECLARED" else "FAIL",
            f"All {release_facts.get('check_count', 0)} declared visible fact assertion(s) match current canonical values inside the exact package."
            if release_fact_status == "CURRENT" else str(release_facts.get("reason", "Declared release documents contain stale or contradictory facts.")),
        ),
    ]
    levels.append(_level(
        "release-facts-current-candidate",
        "Release facts current candidate",
        "The native-verified exact package has one current project-owned fact source whose declared visible document fields match current lineage, migration, package, surface, native, schema, and literal values.",
        release_fact_rows,
        ["arbitrary prose not declared in the contract", "substantive correctness", "reviewer competence", "undeclared documents", "release readiness"],
    ))

    runtime = last_check.get("runtime_proof", {}) if isinstance(last_check.get("runtime_proof"), dict) else {}
    runtime_counts = runtime.get("counts", {}) if isinstance(runtime.get("counts"), dict) else {}
    runtime_pass = runtime.get("status") == "PASS" and int(runtime.get("recipe_count", 0) or 0) > 0 and int(runtime_counts.get("FAIL", 0) or 0) == 0 and int(runtime_counts.get("BLOCKED", 0) or 0) == 0
    runtime_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Release-facts-current-candidate claim is required first."),
        _requirement("runtime-content-proof", "PASS" if runtime_pass else "NOT_RUN" if int(runtime.get("recipe_count", 0) or 0) == 0 else "FAIL", "At least one current content-aware Runtime Proof recipe passed." if runtime_pass else "No current passing content-aware runtime recipe supports this candidate."),
    ]
    levels.append(_level(
        "runtime-content-verified",
        "Runtime-content verified",
        "The native-verified candidate also produced the expected bounded HTTP content in the recorded environment tier.",
        runtime_rows,
        ["JavaScript execution unless separately proven", "visual layout", "accessibility", "hidden database state", "release readiness"],
    ))

    transition_last = last_check.get("state_transitions", {}) if isinstance(last_check.get("state_transitions"), dict) else {}
    transition_summary = state_transition_summary(project_root)
    active_transitions = int(transition_last.get("transition_count", 0) or 0)
    coverage_required = int(transition_last.get("coverage_required_count", 0) or 0)
    coverage_confirmed = int(transition_last.get("coverage_confirmed_count", 0) or 0)
    rollback_required = int(transition_summary.get("rollback_required", 0) or 0)
    rollback_drill_required = int(transition_summary.get("rollback_drill", 0) or 0)
    transition_complete = (
        transition_last.get("status") == "PASS"
        and active_transitions > 0
        and int(transition_last.get("confirmed_count", 0) or 0) == active_transitions
        and int(transition_last.get("not_run_count", 0) or 0) == 0
        and int(transition_last.get("partial_plan_count", 0) or 0) == 0
        and (coverage_required == 0 or coverage_confirmed == coverage_required)
    )
    rollback_complete = (
        int(transition_last.get("rollback_availability_confirmed_count", 0) or 0) >= rollback_required
        and int(transition_last.get("rollback_drill_confirmed_count", 0) or 0) >= rollback_drill_required
        and int(transition_last.get("rollback_correctness_confirmed_count", 0) or 0) >= rollback_drill_required
    )
    state_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Runtime-content-verified claim is required first."),
        _requirement("transition-coverage", "PASS" if transition_complete else "NOT_RUN" if active_transitions == 0 else "FAIL", "All declared transitions and coverage requirements are confirmed." if transition_complete else "Persisted-state transition coverage is absent, partial, stale, or failing."),
        _requirement("rollback-evidence", "PASS" if rollback_complete else "FAIL", "All declared rollback availability, drill, and restored-state requirements are confirmed." if rollback_complete else "Required rollback availability, drill, or restored-state evidence is incomplete."),
    ]
    levels.append(_level(
        "persisted-state-assured",
        "Persisted-state assured",
        "The runtime-verified candidate has complete project-declared transition coverage and required rollback evidence.",
        state_rows,
        ["undeclared production data shapes", "operator behavior", "security review", "public release readiness"],
    ))

    release_evaluation = evaluate_release_package(project_root)
    final_package = release_evaluation.get("final_package", {}) if isinstance(release_evaluation.get("final_package"), dict) else {}
    final_status = str(final_package.get("status", "NOT_RUN"))
    final_reason = "; ".join(str(item) for item in final_package.get("reasons", []) if str(item)) or str(final_package.get("reason", "No exact final package is registered."))
    package_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Persisted-state-assured claim is required first."),
        _requirement("exact-final-package", final_status, "The exact final ZIP, current owner build identity, and registered artifact provenance agree." if final_status == "PASS" else final_reason),
    ]
    levels.append(_level(
        "final-package-bound",
        "Final package bound",
        "The persisted-state-assured candidate is bound to one exact final ZIP and current artifact provenance.",
        package_rows,
        ["confidentiality completeness", "substantive public reviews", "artifact signing", "release readiness"],
    ))

    confidentiality = release_evaluation.get("confidentiality", {}) if isinstance(release_evaluation.get("confidentiality"), dict) else {}
    confidentiality_status = str(confidentiality.get("status", "NOT_RUN"))
    finding_count = len(confidentiality.get("findings", [])) if isinstance(confidentiality.get("findings"), list) else 0
    confidentiality_reason = (
        "The exact package passed the complete bounded confidentiality and contamination scan without retaining secret values or response bodies."
        if confidentiality_status == "PASS"
        else f"Confidentiality scan is {confidentiality_status}; {finding_count} finding(s) are recorded locally."
    )
    confidentiality_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Final-package-bound claim is required first."),
        _requirement("confidentiality-scan", confidentiality_status, confidentiality_reason),
    ]
    levels.append(_level(
        "confidentiality-screened",
        "Confidentiality screened",
        "The exact final package passed the bounded complete confidentiality and contamination scan.",
        confidentiality_rows,
        ["undetectable secrets", "semantic confidentiality judgment", "legal privacy compliance", "artifact signing", "release readiness"],
    ))

    reviews = release_evaluation.get("public_reviews", {}) if isinstance(release_evaluation.get("public_reviews"), dict) else {}
    reviews_status = str(reviews.get("status", "NOT_RUN"))
    passed_reviews = len(reviews.get("passed", [])) if isinstance(reviews.get("passed"), list) else 0
    required_reviews = len(reviews.get("required", [])) if isinstance(reviews.get("required"), list) else 0
    review_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Confidentiality-screened claim is required first."),
        _requirement("public-review-receipts", reviews_status, f"{passed_reviews}/{required_reviews} required project-owned public-review receipts are current for the exact package."),
    ]
    levels.append(_level(
        "public-release-reviewed",
        "Public release reviewed",
        "The exact screened package has current project-owned public-review receipts for every required review category.",
        review_rows,
        ["independent validation of review methodology", "remote channel availability", "matched cold-session validation", "release readiness"],
    ))

    distribution = evaluate_release_distribution(project_root, perform_remote=perform_remote)
    signatures = distribution.get("signatures", {}) if isinstance(distribution.get("signatures"), dict) else {}
    signature_status = str(signatures.get("status", "NOT_RUN"))
    signature_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Public-release-reviewed claim is required first."),
        _requirement("detached-signatures", signature_status, "Detached RSA signatures verify for the exact package and signed channel manifest." if signature_status == "PASS" else str(signatures.get("reason", "Signed exact artifacts are not current."))),
    ]
    levels.append(_level(
        "artifact-signature-verified",
        "Artifact signature verified",
        "The exact final package and its channel manifest have current detached signatures verified against project-owned public keys.",
        signature_rows,
        ["private-key custody", "signer identity beyond the recorded public key", "remote channel availability", "release readiness"],
    ))

    channels = distribution.get("channels", {}) if isinstance(distribution.get("channels"), dict) else {}
    channel_status = str(channels.get("status", "NOT_RUN"))
    channel_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Artifact-signature-verified claim is required first."),
        _requirement("signed-channel-manifest", channel_status, f"{len(channels.get('passed', []))}/{len(channels.get('required', []))} required channel receipt(s) match the signed manifest and exact package."),
    ]
    levels.append(_level(
        "release-channel-bound",
        "Release channel bound",
        "Signed local distribution metadata and project-owned publication receipts agree with the exact package.",
        channel_rows,
        ["independent remote availability", "CDN cache integrity", "future channel contents", "release readiness"],
    ))

    remote = distribution.get("remote_channels", {}) if isinstance(distribution.get("remote_channels"), dict) else {}
    remote_status = str(remote.get("status", "NOT_RUN"))
    remote_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Release-channel-bound claim is required first."),
        _requirement(
            "fresh-remote-artifact-retrieval",
            remote_status,
            (
                f"{len(remote.get('passed', []))}/{len(remote.get('required', []))} required channel artifact(s) were freshly retrieved over HTTPS and matched the exact package bytes."
                if remote_status == "PASS" else str(remote.get("reason", "Independent remote verification did not run."))
            ),
        ),
    ]
    levels.append(_level(
        "remote-channel-verified",
        "Remote channel verified",
        "Every required signed-manifest channel freshly returned bytes identical to the exact final package through a bounded HTTPS retrieval.",
        remote_rows,
        ["future channel contents", "continuous CDN integrity", "private-key custody", "substantive release review quality", "release readiness"],
    ))

    release_proof = evaluate_release_proof(project_root)
    proof_status = str(release_proof.get("status", "NOT_RUN"))
    proof_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Remote-channel-verified claim is required first."),
        _requirement(
            "bounded-release-proof",
            proof_status,
            (
                f"{release_proof.get('passed_obligations', 0)}/{release_proof.get('obligation_count', 0)} required assurance obligation(s) are current across {release_proof.get('surface_count', 0)} declared exact-package surface(s)."
                if proof_status == "PASS" else str(release_proof.get("reason", "Bounded Release Proof is not current."))
            ),
        ),
    ]
    levels.append(_level(
        "release-proof-validated",
        "Release Proof validated",
        "Every declared exact-package release surface has current bounded assurance evidence or an explicit project-owned not-applicable classification across all required domains.",
        proof_rows,
        ["undeclared release surfaces", "substantive correctness beyond recorded methods", "future evidence validity", "owner release authorization", "release readiness"],
    ))

    cold = evaluate_cold_session_validation(project_root)
    cold_status = str(cold.get("status", "NOT_RUN"))
    cold_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Release-proof-validated claim is required first."),
        _requirement("matched-cold-session-evidence", cold_status, f"{cold.get('pair_count', 0)}/{cold.get('minimum_pairs', 0)} human-reviewed matched pair(s), {cold.get('model_count', 0)}/{cold.get('minimum_models', 0)} model(s), {cold.get('task_packet_count', 0)}/{cold.get('minimum_distinct_task_packets', 0)} task packet(s), and {cold.get('host_baseline_count', 0)}/{cold.get('minimum_distinct_host_baselines', 0)} host baseline(s); controlled fixtures excluded from coverage."),
    ]
    levels.append(_level(
        "cold-session-validated",
        "Cold-session validated",
        "One exact Forge runtime and one exact host package have sufficient current human-reviewed, arm-equivalent matched fresh-agent evidence within the recorded thresholds.",
        cold_rows,
        ["authenticated reviewer identity", "independently proven session isolation", "universal causal proof", "all project types", "all providers or models", "commercial value", "release readiness"],
    ))
    authorization = evaluate_release_authorization(project_root)
    authorization_status = str(authorization.get("status", "NOT_RUN"))
    authorization_rows = [
        _requirement("prior-level", "PASS" if levels[-1]["status"] == "PASS" else "FAIL", "Cold-session-validated claim is required first."),
        _requirement(
            "exact-package-owner-authorization",
            authorization_status,
            str(authorization.get("reason", "No current exact-package release authorization is recorded.")),
        ),
    ]
    levels.append(_level(
        "owner-release-authorized",
        "Owner release authorized",
        "A project-declared authority explicitly authorized the exact current final package for the named release channels within a bounded validity window.",
        authorization_rows,
        ["authenticated human identity", "authorship", "review competence", "future package or channel state", "universal correctness"],
    ))
    levels.append(_release_ready_level(levels[-1], release_evaluation, distribution, release_proof, cold, authorization))
    return _result(levels)


def _release_ready_level(prior_level: dict[str, Any], release_evaluation: dict[str, Any], distribution: dict[str, Any] | None = None, release_proof: dict[str, Any] | None = None, cold: dict[str, Any] | None = None, authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    distribution = distribution or {}
    release_proof = release_proof or {}
    cold = cold or {}
    authorization = authorization or {}
    prior_pass = prior_level.get("status") == "PASS"
    rows = [
        _requirement("prior-level", "PASS" if prior_pass else "FAIL", "Every cumulative lower Ship claim, including exact-package owner authorization, must pass first."),
        _requirement("exact-final-package-current", "PASS" if release_evaluation.get("final_package", {}).get("status") == "PASS" else "FAIL", "The exact final package binding remains current."),
        _requirement("bounded-release-proof", "PASS" if release_proof.get("status") == "PASS" else "FAIL", "Bounded Release Proof is current for every declared exact-package surface and required assurance domain." if release_proof.get("status") == "PASS" else "Bounded Release Proof is not current."),
        _requirement("matched-cold-session-evidence", "PASS" if cold.get("status") == "PASS" else "FAIL", "The configured matched cold-session evidence threshold is current." if cold.get("status") == "PASS" else "Matched cold-session evidence is not sufficient or current."),
        _requirement(
            "independent-release-channel-verification",
            "PASS" if isinstance(distribution.get("remote_channels"), dict) and distribution.get("remote_channels", {}).get("status") == "PASS" else "FAIL",
            "Fresh remote artifact retrieval matched every required channel to the exact package." if isinstance(distribution.get("remote_channels"), dict) and distribution.get("remote_channels", {}).get("status") == "PASS" else "Independent remote artifact retrieval is not current for every required channel.",
        ),
        _requirement("owner-release-authorization", "PASS" if authorization.get("status") == "PASS" else "FAIL", str(authorization.get("reason", "Exact-package owner release authorization is not current."))),
    ]
    return _level(
        "release-ready",
        "Release ready",
        "All project-declared cumulative release requirements are current and a project-declared authority explicitly authorized the exact final package for the named channels.",
        rows,
        ["authenticated human identity", "universal correctness", "future package or channel integrity", "undeclared requirements", "legal approval outside project authority"],
    )


def _result(levels: list[dict[str, Any]]) -> dict[str, Any]:
    highest = "none"
    for item in levels:
        if item.get("level_id") == "release-ready":
            break
        if item.get("status") == "PASS":
            highest = str(item.get("level_id", "none"))
        else:
            break
    counts = {"PASS": 0, "PARTIAL": 0, "NOT_RUN": 0, "FAIL": 0}
    for item in levels:
        value = str(item.get("status", "PARTIAL"))
        counts[value] = counts.get(value, 0) + 1
    release_ready = bool(levels and levels[-1].get("level_id") == "release-ready" and levels[-1].get("status") == "PASS")
    return {
        "schema": 4,
        "highest_supported_claim": highest,
        "levels": levels,
        "counts": counts,
        "release_ready": release_ready,
        "truth_boundary": "Claim levels are cumulative evidence summaries. Release-ready means only that every project-declared bounded requirement is current and project-declared authority explicitly authorized the exact package; Forge does not authenticate the human, prove universal correctness, or guarantee future package or channel state.",
    }

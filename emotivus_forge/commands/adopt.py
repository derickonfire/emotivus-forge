from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.authority_registry import confirm_authorities
from ..core.authority_baseline import authorize_current_baseline
from ..core.capabilities import activate_capability, deactivate_capability
from ..core.decision_forks import resolve_decision_fork
from ..core.field_trials import record_trial, retire_trial
from ..core.guardrails import record_guardrail, retire_guardrail
from ..core.handoff import import_continuity_bundle
from ..core.ledger_assertions import record_ledger_assertion, retire_ledger_assertion
from ..core.check_qualification import record_check_qualification, retire_check_qualification
from ..core.provenance import record_artifact_provenance, retire_artifact_provenance
from ..core.deployable_boundary import record_deployable_boundary, retire_deployable_boundary
from ..core.canonical_claims import record_canonical_claims, retire_canonical_claims
from ..core.relationships import record_relationship_set, retire_relationship_set
from ..core.runtime_matrix import record_runtime_matrix, retire_runtime_matrix
from ..core.state_transitions import record_state_transition, retire_state_transition
from ..core.release_package import record_release_package, retire_release_package
from ..core.presentation_profile import record_presentation_profile, retire_presentation_profile
from ..core.release_distribution import record_release_distribution, retire_release_distribution
from ..core.cold_session_validation import record_cold_session_validation, retire_cold_session_validation
from ..core.release_proof import record_release_proof, retire_release_proof
from ..core.release_authorization import record_release_authorization, retire_release_authorization
from ..core.native_tools import approve_native_tool, set_native_execution_mode
from ..core.project_identity import record_project_identity
from ..core.lineage import record_project_lineage, record_merge_candidate, resolve_merge_candidate
from ..core.migration_identity import record_migration_catalog, retire_migration_catalog
from ..core.package_family import record_package_family, retire_package_family
from ..core.surface_coverage import record_surface_coverage, retire_surface_coverage
from ..core.release_facts import record_release_facts, retire_release_facts
from ..core.continuity_register import record_continuity_register, retire_continuity_register
from ..core.third_party_intake import record_third_party_intake, retire_third_party_intake
from ..core.project_events import confirm_project_event
from ..core.passport import build_passport
from ..core.resume import build_resume
from ..core.storage import state_transaction
from .common import print_json, render_adopt
from .noticing import attach_adopt_notice


def _handle_collaboration_enrollment(args: Any) -> int:
    import json as _json

    from ..core.instance_key import (
        _collaboration_file,
        enroll_collaboration_secret,
        generate_collaboration_secret,
    )

    if getattr(args, "generate_collaboration_secret", False):
        identity = generate_collaboration_secret()
        if identity is None:
            print("Could not write the collaboration secret: the Forge home is not writable.")
            return 1
        print("Generated and enrolled a collaboration secret in this Forge home.")
        print(f"  file:   {_collaboration_file()}")
        print(f"  key_id: {identity['key_id']}")
        print("Distribute this file OUT-OF-BAND to each trusted party's Forge home (same")
        print("keys/collaboration.json path) — never through a project repo. Authorizations")
        print("recorded by any enrolled party are then mutually instance-bound.")
        return 0

    source = str(getattr(args, "enroll_collaboration_secret", "")).strip()
    secret = source
    candidate = Path(source)
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8").strip()
        try:
            parsed = _json.loads(text)
            secret = str(parsed.get("secret", "")).strip() if isinstance(parsed, dict) else text
        except (ValueError, _json.JSONDecodeError):
            secret = text
    identity = enroll_collaboration_secret(secret)
    if identity is None:
        print("Could not enroll the collaboration secret (empty secret or Forge home not writable).")
        return 1
    print("Enrolled the shared collaboration secret in this Forge home.")
    print(f"  key_id: {identity['key_id']}")
    print("Authorizations recorded here are now mutually instance-bound with every party")
    print("holding the same secret.")
    return 0


def handle_adopt(args: Any, parser: Any, forge_root: Path) -> int:
    if getattr(args, "generate_collaboration_secret", False) or str(getattr(args, "enroll_collaboration_secret", "")).strip():
        return _handle_collaboration_enrollment(args)
    root = Path(args.project).resolve()
    actions: list[str] = []
    if args.continuity_development_package and not args.import_continuity:
        parser.error("--continuity-development-package requires --import-continuity")
    if args.baseline_reason and not args.authorize_baseline:
        parser.error("--baseline-reason requires --authorize-baseline")
    if args.baseline_authority_source != "project-declared" and not args.authorize_baseline:
        parser.error("--baseline-authority-source requires --authorize-baseline")
    if args.merge_candidate_reason and not args.resolve_merge_candidate:
        parser.error("--merge-candidate-reason requires --resolve-merge-candidate")
    lineage_operations = sum(bool(value) for value in (args.record_lineage, args.record_merge_candidate, args.resolve_merge_candidate))
    migration_operations = sum(bool(value) for value in (args.record_migration_catalog, args.retire_migration_catalog))
    package_family_operations = sum(bool(value) for value in (args.record_package_family, args.retire_package_family))
    surface_coverage_operations = sum(bool(value) for value in (args.record_surface_coverage, args.retire_surface_coverage))
    release_facts_operations = sum(bool(value) for value in (args.record_release_facts, args.retire_release_facts))
    continuity_register_operations = sum(bool(value) for value in (args.record_continuity_register, args.retire_continuity_register))
    third_party_operations = sum(bool(value) for value in (args.record_third_party_intake, args.retire_third_party_intake))
    if lineage_operations > 1:
        parser.error("Lineage recording, merge-candidate recording, and merge-candidate resolution must be separate Adopt operations")
    if migration_operations > 1:
        parser.error("Migration catalog recording and retirement must be separate Adopt operations")
    if package_family_operations > 1:
        parser.error("Package-family recording and retirement must be separate Adopt operations")
    if surface_coverage_operations > 1:
        parser.error("Surface coverage recording and retirement must be separate Adopt operations")
    if release_facts_operations > 1:
        parser.error("Release facts recording and retirement must be separate Adopt operations")
    if continuity_register_operations > 1:
        parser.error("Continuity register recording and retirement must be separate Adopt operations")
    if third_party_operations > 1:
        parser.error("Third-party intake recording and retirement must be separate Adopt operations")
    if args.migration_catalog_reason and not args.retire_migration_catalog:
        parser.error("--migration-catalog-reason requires --retire-migration-catalog")
    if args.package_family_reason and not args.retire_package_family:
        parser.error("--package-family-reason requires --retire-package-family")
    if args.surface_coverage_reason and not args.retire_surface_coverage:
        parser.error("--surface-coverage-reason requires --retire-surface-coverage")
    if args.release_facts_reason and not args.retire_release_facts:
        parser.error("--release-facts-reason requires --retire-release-facts")
    if args.continuity_register_reason and not args.retire_continuity_register:
        parser.error("--continuity-register-reason requires --retire-continuity-register")
    if bool(args.record_third_party_intake) != bool(args.third_party_source):
        parser.error("--record-third-party-intake and --third-party-source must be used together")
    if args.third_party_intake_reason and not args.retire_third_party_intake:
        parser.error("--third-party-intake-reason requires --retire-third-party-intake")
    with state_transaction(root, validate_existing=(root / ".forge").is_dir()):
        if args.import_continuity:
            try:
                import_continuity_bundle(
                    root,
                    args.import_continuity,
                    development_package=args.continuity_development_package,
                )
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("portable continuity import")
        role_confirmations: dict[str, str] = {}
        for raw in args.confirm_authority:
            if "=" not in raw:
                parser.error("--confirm-authority must use KIND=PATH")
            kind, source = raw.split("=", 1)
            role_confirmations[kind.strip()] = source.strip()
        if args.confirm_objective or role_confirmations:
            confirm_authorities(
                root, forge_root,
                objective=args.confirm_objective,
                objective_source=args.objective_source,
                roles=role_confirmations,
            )
            actions.append("project authority")
        if args.approve_native and args.native_mode:
            parser.error("Use either --approve-native or --native-mode, not both")
        if args.native_invocation and not (args.approve_native or args.native_mode):
            parser.error("--native-invocation requires --native-mode or --approve-native")
        if args.approve_native:
            try:
                approve_native_tool(
                    root,
                    "" if args.approve_native == "canonical" else args.approve_native,
                    args.native_invocation,
                )
            except RuntimeError as exc:
                parser.error(str(exc))
            actions.append("native gate mode forge-authorized")
        elif args.native_mode:
            candidate = "" if args.native_candidate == "canonical" else args.native_candidate
            try:
                set_native_execution_mode(root, args.native_mode, candidate, args.native_invocation)
            except RuntimeError as exc:
                parser.error(str(exc))
            actions.append(f"native gate mode {args.native_mode}")
        if bool(args.activate_capability) != bool(args.capability_contract):
            parser.error("--activate-capability and --capability-contract must be used together")
        if bool(args.deactivate_capability) != bool(args.deactivation_reason):
            parser.error("--deactivate-capability requires --deactivation-reason, and vice versa")
        if args.activate_capability and args.deactivate_capability:
            parser.error("Capability activation and deactivation must be separate Adopt operations")
        if bool(args.confirm_project_event) != bool(args.project_event_evidence):
            parser.error("--confirm-project-event and --project-event-evidence must be used together")
        if bool(args.retire_guardrail) != bool(args.guardrail_reason):
            parser.error("--retire-guardrail requires --guardrail-reason, and vice versa")
        if bool(args.retire_field_trial) != bool(args.field_trial_reason):
            parser.error("--retire-field-trial requires --field-trial-reason, and vice versa")
        if bool(args.retire_ledger_assertion) != bool(args.ledger_assertion_reason):
            parser.error("--retire-ledger-assertion requires --ledger-assertion-reason, and vice versa")
        if bool(args.retire_check_qualification) != bool(args.check_qualification_reason):
            parser.error("--retire-check-qualification requires --check-qualification-reason, and vice versa")
        if bool(args.retire_artifact_provenance) != bool(args.artifact_provenance_reason):
            parser.error("--retire-artifact-provenance requires --artifact-provenance-reason, and vice versa")
        if bool(args.retire_deployable_boundary) != bool(args.deployable_boundary_reason):
            parser.error("--retire-deployable-boundary requires --deployable-boundary-reason, and vice versa")
        if bool(args.retire_canonical_claims) != bool(args.canonical_claims_reason):
            parser.error("--retire-canonical-claims requires --canonical-claims-reason, and vice versa")
        if bool(args.retire_relationship_set) != bool(args.relationship_set_reason):
            parser.error("--retire-relationship-set requires --relationship-set-reason, and vice versa")
        if bool(args.retire_runtime_matrix) != bool(args.runtime_matrix_reason):
            parser.error("--retire-runtime-matrix requires --runtime-matrix-reason, and vice versa")
        if bool(args.retire_state_transition) != bool(args.state_transition_reason):
            parser.error("--retire-state-transition requires --state-transition-reason, and vice versa")
        if bool(args.retire_release_package) != bool(args.release_package_reason):
            parser.error("--retire-release-package requires --release-package-reason, and vice versa")
        if bool(args.retire_presentation_profile) != bool(args.presentation_profile_reason):
            parser.error("--retire-presentation-profile requires --presentation-profile-reason, and vice versa")
        if bool(args.retire_release_distribution) != bool(args.release_distribution_reason):
            parser.error("--retire-release-distribution requires --release-distribution-reason, and vice versa")
        if bool(args.retire_cold_session_validation) != bool(args.cold_session_validation_reason):
            parser.error("--retire-cold-session-validation requires --cold-session-validation-reason, and vice versa")
        if bool(args.retire_release_proof) != bool(args.release_proof_reason):
            parser.error("--retire-release-proof requires --release-proof-reason, and vice versa")
        if bool(args.retire_release_authorization) != bool(args.release_authorization_reason):
            parser.error("--retire-release-authorization requires --release-authorization-reason, and vice versa")
        if args.record_release_authorization and args.retire_release_authorization:
            parser.error("Recording and retiring release authorization must be separate Adopt operations")
        if args.activate_capability:
            try:
                activate_capability(root, forge_root, args.activate_capability, args.capability_contract)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append(f"{args.activate_capability} activation")
        if args.deactivate_capability:
            try:
                deactivate_capability(root, args.deactivate_capability, args.deactivation_reason)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append(f"{args.deactivate_capability} deactivation")
        if args.record_identity:
            try:
                record_project_identity(root, forge_root, args.record_identity)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("project identity")
        if args.record_lineage:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-lineage must be a separate Adopt operation so exact ancestry cannot be hidden inside unrelated changes")
            try:
                record_project_lineage(root, forge_root, args.record_lineage)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("exact project lineage")
        if args.record_merge_candidate:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-merge-candidate must be a separate Adopt operation so incoming branch quarantine cannot be hidden inside unrelated changes")
            try:
                record_merge_candidate(root, forge_root, args.record_merge_candidate)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("merge candidate quarantine")
        if args.resolve_merge_candidate:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--resolve-merge-candidate must be a separate Adopt operation")
            if "=" not in args.resolve_merge_candidate:
                parser.error("--resolve-merge-candidate must use CANDIDATE_ID=DECISION")
            candidate_id, decision = (part.strip() for part in args.resolve_merge_candidate.split("=", 1))
            if not candidate_id or not decision:
                parser.error("--resolve-merge-candidate must use CANDIDATE_ID=DECISION")
            if not args.merge_candidate_reason.strip():
                parser.error("--resolve-merge-candidate requires --merge-candidate-reason")
            try:
                resolve_merge_candidate(
                    root, candidate_id, decision, args.merge_candidate_reason,
                    authority=args.merge_candidate_authority,
                )
            except ValueError as exc:
                parser.error(str(exc))
            actions.append(f"merge candidate {decision}")
        if args.record_migration_catalog:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-migration-catalog must be a separate Adopt operation so migration identity cannot be hidden inside unrelated changes")
            try:
                record_migration_catalog(root, forge_root, args.record_migration_catalog)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("migration identity catalog")
        if args.retire_migration_catalog:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--retire-migration-catalog must be a separate Adopt operation")
            if not args.migration_catalog_reason.strip():
                parser.error("--retire-migration-catalog requires --migration-catalog-reason")
            try:
                retire_migration_catalog(
                    root, args.retire_migration_catalog, args.migration_catalog_reason,
                    authority=args.migration_catalog_authority,
                )
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("migration catalog retirement")
        if args.record_package_family:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-package-family must be a separate Adopt operation so package applicability cannot be hidden inside unrelated changes")
            try:
                record_package_family(root, forge_root, args.record_package_family)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("package-family applicability")
        if args.retire_package_family:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--retire-package-family must be a separate Adopt operation")
            if not args.package_family_reason.strip():
                parser.error("--retire-package-family requires --package-family-reason")
            try:
                retire_package_family(root, args.retire_package_family, args.package_family_reason, authority=args.package_family_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("package-family retirement")
        if args.record_surface_coverage:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-surface-coverage must be a separate Adopt operation so route existence cannot be hidden inside unrelated evidence claims")
            try:
                record_surface_coverage(root, forge_root, args.record_surface_coverage)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("surface-to-evidence coverage")
        if args.retire_surface_coverage:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--retire-surface-coverage must be a separate Adopt operation")
            if not args.surface_coverage_reason.strip():
                parser.error("--retire-surface-coverage requires --surface-coverage-reason")
            try:
                retire_surface_coverage(root, args.retire_surface_coverage, args.surface_coverage_reason, authority=args.surface_coverage_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("surface coverage retirement")
        if args.record_release_facts:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-release-facts must be a separate Adopt operation so stale documentation cannot be hidden inside unrelated changes")
            try:
                record_release_facts(root, forge_root, args.record_release_facts)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("authoritative release facts")
        if args.retire_release_facts:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--retire-release-facts must be a separate Adopt operation")
            if not args.release_facts_reason.strip():
                parser.error("--retire-release-facts requires --release-facts-reason")
            try:
                retire_release_facts(root, args.retire_release_facts, args.release_facts_reason, authority=args.release_facts_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("release facts retirement")
        if args.record_continuity_register:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-continuity-register must be a separate Adopt operation so durable facts cannot be hidden inside unrelated changes")
            try:
                record_continuity_register(root, forge_root, args.record_continuity_register)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("governed continuity register")
        if args.retire_continuity_register:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--retire-continuity-register must be a separate Adopt operation")
            if not args.continuity_register_reason.strip():
                parser.error("--retire-continuity-register requires --continuity-register-reason")
            try:
                retire_continuity_register(root, args.retire_continuity_register, args.continuity_register_reason, authority=args.continuity_register_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("continuity register retirement")
        if args.record_third_party_intake:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-third-party-intake must be a separate Adopt operation so provenance cannot be hidden inside unrelated changes")
            try:
                record_third_party_intake(root, forge_root, args.record_third_party_intake, args.third_party_source)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("third-party capability intake")
        if args.retire_third_party_intake:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--retire-third-party-intake must be a separate Adopt operation")
            if not args.third_party_intake_reason.strip():
                parser.error("--retire-third-party-intake requires --third-party-intake-reason")
            try:
                retire_third_party_intake(root, args.retire_third_party_intake, args.third_party_intake_reason, authority=args.third_party_intake_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("third-party capability intake retirement")
        if args.confirm_project_event:
            try:
                confirm_project_event(
                    root, forge_root, args.confirm_project_event, args.project_event_evidence,
                    authority=args.project_event_authority, note=args.project_event_note,
                )
            except ValueError as exc:
                parser.error(str(exc))
            actions.append(f"project event {args.confirm_project_event}")
        for guardrail_path in args.record_guardrail:
            try:
                record_guardrail(root, forge_root, guardrail_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("safety guardrail")
        if args.retire_guardrail:
            try:
                retire_guardrail(root, args.retire_guardrail, args.guardrail_reason, authority=args.guardrail_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("guardrail retirement")
        for assertion_path in args.record_ledger_assertion:
            try:
                record_ledger_assertion(root, forge_root, assertion_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("Ledger assertion")
        if args.retire_ledger_assertion:
            try:
                retire_ledger_assertion(root, args.retire_ledger_assertion, args.ledger_assertion_reason, authority=args.ledger_assertion_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("Ledger assertion retirement")
        for qualification_path in args.record_check_qualification:
            try:
                record_check_qualification(root, forge_root, qualification_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("check qualification")
        if args.retire_check_qualification:
            try:
                retire_check_qualification(root, args.retire_check_qualification, args.check_qualification_reason, authority=args.check_qualification_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("check qualification retirement")
        for provenance_path in args.record_artifact_provenance:
            try:
                record_artifact_provenance(root, forge_root, provenance_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("artifact provenance")
        if getattr(args, "record_lifecycle_transition", ""):
            from ..core.lifecycle import record_lifecycle_transition
            try:
                record_lifecycle_transition(root, forge_root, args.record_lifecycle_transition)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("component lifecycle transition")
        if args.retire_artifact_provenance:
            try:
                retire_artifact_provenance(root, args.retire_artifact_provenance, args.artifact_provenance_reason, authority=args.artifact_provenance_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("artifact provenance retirement")
        for boundary_path in args.record_deployable_boundary:
            try:
                record_deployable_boundary(root, forge_root, boundary_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("deployable boundary")
        if args.retire_deployable_boundary:
            try:
                retire_deployable_boundary(root, args.retire_deployable_boundary, args.deployable_boundary_reason, authority=args.deployable_boundary_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("deployable-boundary retirement")
        for claims_path in args.record_canonical_claims:
            try:
                record_canonical_claims(root, forge_root, claims_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("canonical claims")
        if args.retire_canonical_claims:
            try:
                retire_canonical_claims(root, args.retire_canonical_claims, args.canonical_claims_reason, authority=args.canonical_claims_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("canonical-claims retirement")
        for relationship_path in args.record_relationship_set:
            try:
                record_relationship_set(root, forge_root, relationship_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("confirmed relationship set")
        if args.retire_relationship_set:
            try:
                retire_relationship_set(root, args.retire_relationship_set, args.relationship_set_reason, authority=args.relationship_set_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("relationship-set retirement")
        for matrix_path in args.record_runtime_matrix:
            try:
                record_runtime_matrix(root, forge_root, matrix_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("runtime-state matrix")
        if args.retire_runtime_matrix:
            try:
                retire_runtime_matrix(root, args.retire_runtime_matrix, args.runtime_matrix_reason, authority=args.runtime_matrix_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("runtime-state matrix retirement")
        for transition_path in args.record_state_transition:
            try:
                record_state_transition(root, forge_root, transition_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("persisted-state transition plan")
        if args.retire_state_transition:
            try:
                retire_state_transition(root, args.retire_state_transition, args.state_transition_reason, authority=args.state_transition_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("persisted-state transition retirement")
        for release_package_path in args.record_release_package:
            try:
                record_release_package(root, forge_root, release_package_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("final release package")
        if args.retire_release_package:
            try:
                retire_release_package(root, args.retire_release_package, args.release_package_reason, authority=args.release_package_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("final release package retirement")
        for profile_path in args.record_presentation_profile:
            try:
                record_presentation_profile(root, forge_root, profile_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("cross-model presentation profile")
        if args.retire_presentation_profile:
            try:
                retire_presentation_profile(root, args.retire_presentation_profile, args.presentation_profile_reason, authority=args.presentation_profile_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("presentation-profile retirement")
        for distribution_path in args.record_release_distribution:
            try:
                record_release_distribution(root, forge_root, distribution_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("signed release distribution")
        if args.retire_release_distribution:
            try:
                retire_release_distribution(root, args.retire_release_distribution, args.release_distribution_reason, authority=args.release_distribution_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("release-distribution retirement")
        for validation_path in args.record_cold_session_validation:
            try:
                record_cold_session_validation(root, forge_root, validation_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("cold-session validation")
        if args.retire_cold_session_validation:
            try:
                retire_cold_session_validation(root, args.retire_cold_session_validation, args.cold_session_validation_reason, authority=args.cold_session_validation_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("cold-session validation retirement")
        for release_proof_path in args.record_release_proof:
            try:
                record_release_proof(root, forge_root, release_proof_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("bounded Release Proof")
        if args.retire_release_proof:
            try:
                retire_release_proof(root, args.retire_release_proof, args.release_proof_reason, authority=args.release_proof_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("Release Proof retirement")
        if args.record_release_authorization:
            if actions or args.name.strip() or args.authorize_baseline:
                parser.error("--record-release-authorization must be a separate Adopt operation so release authority cannot be hidden inside unrelated changes")
            try:
                record_release_authorization(root, forge_root, args.record_release_authorization)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("exact-package release authorization")
        if args.retire_release_authorization:
            try:
                retire_release_authorization(root, args.retire_release_authorization, args.release_authorization_reason, authority=args.release_authorization_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("release authorization retirement")
        for trial_path in args.record_field_trial:
            try:
                record_trial(root, forge_root, trial_path)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("field trial")
        if args.retire_field_trial:
            try:
                retire_trial(root, args.retire_field_trial, args.field_trial_reason, authority=args.field_trial_authority)
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("field-trial retirement")
        baseline_authorization = None
        if args.authorize_baseline:
            if actions or args.resolve_fork or args.name.strip():
                parser.error("--authorize-baseline must be a separate Adopt operation so authority cannot be hidden inside unrelated configuration changes")
            if not args.baseline_reason.strip():
                parser.error("--authorize-baseline requires --baseline-reason")
            if not (root / ".forge" / "state.json").is_file():
                parser.error("Adopt the project first, review the reported fingerprint, then authorize the baseline in a separate Adopt operation")
            try:
                baseline_authorization = authorize_current_baseline(
                    root,
                    forge_root,
                    expected_fingerprint=args.authorize_baseline,
                    authority=args.baseline_authority,
                    reason=args.baseline_reason,
                    authority_source=args.baseline_authority_source,
                )
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("explicit authority baseline")
        payload = build_passport(root, forge_root, name=args.name, refresh=True)
        if baseline_authorization is not None:
            payload["baseline_authorization"] = baseline_authorization
        if (args.fork_rationale or args.fork_authority != "owner") and not args.resolve_fork:
            parser.error("--fork-rationale and --fork-authority require --resolve-fork")
        if args.resolve_fork:
            if "=" not in args.resolve_fork:
                parser.error("--resolve-fork must use FORK_ID=OPTION_ID")
            fork_id, option_id = (part.strip() for part in args.resolve_fork.split("=", 1))
            if not fork_id or not option_id:
                parser.error("--resolve-fork must use FORK_ID=OPTION_ID")
            if not args.fork_rationale.strip():
                parser.error("--resolve-fork requires --fork-rationale")
            try:
                payload["decision_fork_resolution"] = resolve_decision_fork(
                    root, forge_root,
                    fork_id=fork_id, option_id=option_id,
                    rationale=args.fork_rationale, authority=args.fork_authority,
                )
            except ValueError as exc:
                parser.error(str(exc))
            actions.append("governing decision")
        resume = build_resume(root, forge_root, budget="compact", refresh=False)
        payload["resume"] = resume.get("output", "")
        attach_adopt_notice(payload, root, actions)
    print_json(payload) if args.json else print(render_adopt(payload, root), end="")
    return 0

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .commands.adopt import handle_adopt
from .commands.bind import handle_bind
from .commands.check import handle_check
from .commands.ledger import handle_ledger
from .commands.public import (
    handle_advanced,
    handle_help,
    handle_resume,
    handle_run,
    handle_self_test,
    handle_ship,
)
from .core.capabilities import CAPABILITY_CATALOG
from .core.common import ForgeStateError
from .core.session_close import SESSION_TYPES
from .core.native_tools import EXECUTION_MODES
from .core.truth_ledger import VERDICTS
from .core.storage import ForgeLockError


def _forge_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=os.environ.get("FORGE_INVOKED_AS", "forge").strip() or "forge",
        description="Bounded project intelligence: Run Forge · Check · Ship, with advanced Adopt and Resume",
        epilog="Run Forge with no command for a bounded active orientation and reconciliation pass, followed by passive sidecar mode.",
    )
    parser.add_argument("--version", action="version", version=f"Emotivus Forge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="{help,adopt,resume,check,ship}")

    p_run = sub.add_parser("run", help=argparse.SUPPRESS)
    p_run.add_argument("project", nargs="?", default=".")
    p_run.add_argument("--budget", choices=("compact", "standard", "full"), default="compact")
    p_run.add_argument("--session-context", default="", metavar="PATH", help="Transient distilled current-session digest; raw transcripts are rejected and not retained")
    p_run.add_argument("--read-only", action="store_true", help="Bounded read-only consultation: read the project bytes but write NOTHING into the project tree (transient state goes to a disposable directory outside it)")
    p_run.add_argument("--close", default="", metavar="PATH", help="Leave the session in one command: a JSON session-close digest (session_type, summary, completed_work, next_action, optional export_continuity_path). Records a durable Session Close and refreshes continuity through Run Forge itself")
    p_run.add_argument("--json", action="store_true")

    p_help = sub.add_parser("help", help="Inspect Forge state and recommend the exact next command")
    p_help.add_argument("topic", nargs="?", choices=("adopt", "resume", "check", "ship", "advanced"))
    p_help.add_argument("--project", default=".")
    p_help.add_argument("--json", action="store_true")

    p_adopt = sub.add_parser("adopt", help="Create or refresh the minimal Project Passport")
    p_adopt.add_argument("project", nargs="?", default=".")
    p_adopt.add_argument("--generate-collaboration-secret", action="store_true", help="Create and enroll a shared collaboration secret in this Forge home (outside any project) for the owner to distribute out-of-band to trusted peers")
    p_adopt.add_argument("--enroll-collaboration-secret", default="", metavar="PATH_OR_HEX", help="Enroll a shared collaboration secret (a keys/collaboration.json file, a file of raw hex, or an inline hex secret) so peers' authorizations are mutually instance-bound")
    p_adopt.add_argument("--name", default="")
    p_adopt.add_argument("--authorize-baseline", default="", metavar="SNAPSHOT_SHA256", help="Explicitly authorize the current project tree using the exact fingerprint reported by Check or Resume; must be a separate Adopt operation")
    p_adopt.add_argument("--baseline-reason", default="", help="Required durable explanation of what project authority reviewed and accepted")
    p_adopt.add_argument("--baseline-authority", default="owner", help="Project-declared authority recording the baseline; Forge does not authenticate the human identity")
    p_adopt.add_argument("--baseline-authority-source", default="project-declared", help="Source or process through which baseline authority was recorded")
    p_adopt.add_argument("--confirm-objective", default="", help="Record the owner-confirmed current objective")
    p_adopt.add_argument("--objective-source", default="owner", help="Source path for the confirmed objective, or owner")
    p_adopt.add_argument("--confirm-authority", action="append", default=[], metavar="KIND=PATH", help="Confirm an authority role; repeat as needed")
    p_adopt.add_argument("--approve-native", nargs="?", const="canonical", default="", metavar="CANDIDATE_ID", help="Backward-compatible alias for --native-mode forge-authorized")
    p_adopt.add_argument("--native-mode", choices=EXECUTION_MODES, default="", help="Record who may execute the canonical native gate or whether Forge only imports evidence")
    p_adopt.add_argument("--native-candidate", default="canonical", metavar="CANDIDATE_ID", help="Canonical or named candidate for --native-mode")
    p_adopt.add_argument("--native-invocation", default="", metavar="PATH", help="Project-owned exact command, arguments, working directory, environment overrides, and expected check coverage")
    p_adopt.add_argument("--import-continuity", default="", metavar="PATH", help="Import a validated companion Forge continuity bundle into a project with no existing Forge state")
    p_adopt.add_argument("--continuity-development-package", default="", metavar="PATH", help="Development package bound to --import-continuity, when the bundle requires one")
    p_adopt.add_argument("--resolve-fork", default="", metavar="FORK_ID=OPTION_ID", help="Resolve an evidenced decision fork through the confirmed authority path")
    p_adopt.add_argument("--fork-rationale", default="", help="Required rationale for --resolve-fork")
    p_adopt.add_argument("--fork-authority", default="owner", help="Authority recording the decision; defaults to owner")
    p_adopt.add_argument("--activate-capability", choices=tuple(CAPABILITY_CATALOG), default="", help="Explicitly activate a capability with a project-owned contract")
    p_adopt.add_argument("--capability-contract", default="", metavar="PATH", help="Project-owned JSON activation contract for --activate-capability")
    p_adopt.add_argument("--deactivate-capability", choices=tuple(CAPABILITY_CATALOG), default="", help="Deactivate a previously active capability")
    p_adopt.add_argument("--deactivation-reason", default="", help="Required durable reason for --deactivate-capability")
    p_adopt.add_argument("--record-identity", default="", metavar="PATH", help="Record the owner-controlled multi-component project identity")
    p_adopt.add_argument("--record-lineage", default="", metavar="PATH", help="Record exact parent-package and normalized current-tree lineage; must be a separate Adopt operation")
    p_adopt.add_argument("--record-merge-candidate", default="", metavar="PATH", help="Quarantine an incoming package with exact parent/incoming ancestry and three-way path inventories; must be a separate Adopt operation")
    p_adopt.add_argument("--resolve-merge-candidate", default="", metavar="CANDIDATE_ID=DECISION", help="Resolve a quarantined branch as approved-for-reconciliation or rejected; never authorizes the resulting tree")
    p_adopt.add_argument("--merge-candidate-reason", default="", help="Required durable reason for --resolve-merge-candidate")
    p_adopt.add_argument("--merge-candidate-authority", default="owner", help="Project-declared authority resolving a merge candidate")
    p_adopt.add_argument("--record-migration-catalog", default="", metavar="PATH", help="Record exact migration sequence, semantic-ID, body-digest, lineage, and optional applied-ledger identity; must be separate")
    p_adopt.add_argument("--retire-migration-catalog", default="", metavar="INVENTORY_ID", help="Retire an active migration catalog")
    p_adopt.add_argument("--migration-catalog-reason", default="", help="Required durable reason for --retire-migration-catalog")
    p_adopt.add_argument("--migration-catalog-authority", default="owner", help="Project-declared authority retiring a migration catalog")
    p_adopt.add_argument("--record-package-family", default="", metavar="PATH", help="Record exact package-family, outer-bundle, and changed-files applicability proof; must be separate")
    p_adopt.add_argument("--retire-package-family", default="", metavar="FAMILY_ID", help="Retire an active package-family contract")
    p_adopt.add_argument("--package-family-reason", default="", help="Required durable reason for --retire-package-family")
    p_adopt.add_argument("--package-family-authority", default="owner", help="Project-declared authority retiring a package family")
    p_adopt.add_argument("--record-surface-coverage", default="", metavar="PATH", help="Record an exact user-facing surface inventory and explicit evidence-tier map; must be separate")
    p_adopt.add_argument("--retire-surface-coverage", default="", metavar="INVENTORY_ID", help="Retire an active surface coverage inventory")
    p_adopt.add_argument("--surface-coverage-reason", default="", help="Required durable reason for --retire-surface-coverage")
    p_adopt.add_argument("--surface-coverage-authority", default="owner", help="Project-declared authority retiring a surface coverage inventory")
    p_adopt.add_argument("--record-release-facts", default="", metavar="PATH", help="Record canonical exact-package release facts and visible document assertions; must be separate")
    p_adopt.add_argument("--retire-release-facts", default="", metavar="FACT_SET_ID", help="Retire an active release fact set")
    p_adopt.add_argument("--release-facts-reason", default="", help="Required durable reason for --retire-release-facts")
    p_adopt.add_argument("--release-facts-authority", default="owner", help="Project-declared authority retiring a release fact set")
    p_adopt.add_argument("--record-continuity-register", default="", metavar="PATH", help="Record a trust-ranked continuity fact and knowledge-gap register; must be separate")
    p_adopt.add_argument("--retire-continuity-register", default="", metavar="REGISTER_ID", help="Retire the active continuity register")
    p_adopt.add_argument("--continuity-register-reason", default="", help="Required durable reason for --retire-continuity-register")
    p_adopt.add_argument("--continuity-register-authority", default="owner", help="Project-declared authority retiring a continuity register")
    p_adopt.add_argument("--record-third-party-intake", default="", metavar="PATH", help="Record an exact third-party capability intake contract; must be separate")
    p_adopt.add_argument("--third-party-source", default="", metavar="ZIP", help="External exact upstream source ZIP required by --record-third-party-intake")
    p_adopt.add_argument("--retire-third-party-intake", default="", metavar="INTAKE_ID", help="Retire a recorded third-party capability intake")
    p_adopt.add_argument("--third-party-intake-reason", default="", help="Required durable reason for --retire-third-party-intake")
    p_adopt.add_argument("--third-party-intake-authority", default="owner", help="Project-declared authority retiring a third-party intake")
    p_adopt.add_argument("--confirm-project-event", default="", metavar="EVENT_ID", help="Confirm an observable project event that may close a temporary change window")
    p_adopt.add_argument("--project-event-evidence", default="", metavar="PATH", help="Required project evidence for --confirm-project-event")
    p_adopt.add_argument("--project-event-authority", default="owner", help="Authority confirming --confirm-project-event")
    p_adopt.add_argument("--project-event-note", default="", help="Optional concise note for --confirm-project-event")
    p_adopt.add_argument("--record-guardrail", action="append", default=[], metavar="PATH", help="Record a project-owned atomic or event-triggered safety guardrail; repeat as needed")
    p_adopt.add_argument("--retire-guardrail", default="", metavar="GUARDRAIL_ID", help="Retire a recorded guardrail through the authority path")
    p_adopt.add_argument("--guardrail-reason", default="", help="Required reason for --retire-guardrail")
    p_adopt.add_argument("--guardrail-authority", default="owner", help="Authority retiring the guardrail; recording authority comes from the project-owned contract")
    p_adopt.add_argument("--record-ledger-assertion", action="append", default=[], metavar="PATH", help="Record an authority-owned deterministic Ledger assertion; repeat as needed")
    p_adopt.add_argument("--retire-ledger-assertion", default="", metavar="ASSERTION_ID", help="Retire a recorded Ledger assertion")
    p_adopt.add_argument("--ledger-assertion-reason", default="", help="Required reason for --retire-ledger-assertion")
    p_adopt.add_argument("--ledger-assertion-authority", default="owner", help="Authority retiring the Ledger assertion")
    p_adopt.add_argument("--record-check-qualification", action="append", default=[], metavar="PATH", help="Record evidence that a check failed on known-bad input; repeat as needed")
    p_adopt.add_argument("--retire-check-qualification", default="", metavar="QUALIFICATION_ID", help="Retire a recorded check qualification")
    p_adopt.add_argument("--check-qualification-reason", default="", help="Required reason for --retire-check-qualification")
    p_adopt.add_argument("--check-qualification-authority", default="owner", help="Authority retiring the check qualification")
    p_adopt.add_argument("--record-artifact-provenance", action="append", default=[], metavar="PATH", help="Record project-owned artifact generator, input, baseline, and digest provenance; repeat as needed")
    p_adopt.add_argument("--record-lifecycle-transition", default="", metavar="PATH", help="Record an explicit, auditable component lifecycle transition (retain/fold/freeze/retire/replace) from a project-owned contract; a fold/replace names the successor, a replace records the invariants to preserve")
    p_adopt.add_argument("--retire-artifact-provenance", default="", metavar="PROVENANCE_ID", help="Retire a recorded artifact provenance contract")
    p_adopt.add_argument("--artifact-provenance-reason", default="", help="Required reason for --retire-artifact-provenance")
    p_adopt.add_argument("--artifact-provenance-authority", default="owner", help="Authority retiring the artifact provenance record")
    p_adopt.add_argument("--record-deployable-boundary", action="append", default=[], metavar="PATH", help="Record a project-owned changed-file delivery-role and delta-boundary contract; repeat as needed")
    p_adopt.add_argument("--retire-deployable-boundary", default="", metavar="BOUNDARY_ID", help="Retire a recorded deployable-boundary contract")
    p_adopt.add_argument("--deployable-boundary-reason", default="", help="Required reason for --retire-deployable-boundary")
    p_adopt.add_argument("--deployable-boundary-authority", default="owner", help="Authority retiring the deployable-boundary record")
    p_adopt.add_argument("--record-canonical-claims", action="append", default=[], metavar="PATH", help="Record explicit owner-facing claims to verify against current identity, packages, migrations, or evidence; repeat as needed")
    p_adopt.add_argument("--retire-canonical-claims", default="", metavar="CLAIM_SET_ID", help="Retire a recorded canonical-claim set")
    p_adopt.add_argument("--canonical-claims-reason", default="", help="Required reason for --retire-canonical-claims")
    p_adopt.add_argument("--canonical-claims-authority", default="owner", help="Authority retiring the canonical-claim set")
    p_adopt.add_argument("--record-relationship-set", action="append", default=[], metavar="PATH", help="Record project-owned confirmed relationships for impact propagation; repeat as needed")
    p_adopt.add_argument("--retire-relationship-set", default="", metavar="RELATIONSHIP_SET_ID", help="Retire a recorded relationship set")
    p_adopt.add_argument("--relationship-set-reason", default="", help="Required reason for --retire-relationship-set")
    p_adopt.add_argument("--relationship-set-authority", default="owner", help="Authority retiring the relationship set")
    p_adopt.add_argument("--record-runtime-matrix", action="append", default=[], metavar="PATH", help="Record a project-owned candidate/environment/persisted-state deployment matrix; repeat as needed")
    p_adopt.add_argument("--retire-runtime-matrix", default="", metavar="MATRIX_ID", help="Retire a recorded runtime-state matrix")
    p_adopt.add_argument("--runtime-matrix-reason", default="", help="Required reason for --retire-runtime-matrix")
    p_adopt.add_argument("--runtime-matrix-authority", default="owner", help="Authority retiring the runtime-state matrix")
    p_adopt.add_argument("--record-state-transition", action="append", default=[], metavar="PATH", help="Record project-owned persisted-state transition, deployment-receipt, and rollback expectations; repeat as needed")
    p_adopt.add_argument("--retire-state-transition", default="", metavar="PLAN_ID", help="Retire a recorded persisted-state transition plan")
    p_adopt.add_argument("--state-transition-reason", default="", help="Required reason for --retire-state-transition")
    p_adopt.add_argument("--state-transition-authority", default="owner", help="Authority retiring the persisted-state transition plan")
    p_adopt.add_argument("--record-release-package", action="append", default=[], metavar="PATH", help="Record the exact final ZIP, confidentiality scan policy, provenance, identity, and public-review receipt contract; repeat as needed")
    p_adopt.add_argument("--retire-release-package", default="", metavar="RELEASE_PACKAGE_ID", help="Retire the active exact final-package certification contract")
    p_adopt.add_argument("--release-package-reason", default="", help="Required reason for --retire-release-package")
    p_adopt.add_argument("--release-package-authority", default="owner", help="Authority retiring the final-package certification record")
    p_adopt.add_argument("--record-presentation-profile", action="append", default=[], metavar="PATH", help="Record a project-owned cross-model presentation contract; repeat as needed")
    p_adopt.add_argument("--retire-presentation-profile", default="", metavar="PROFILE_ID", help="Retire the active presentation profile")
    p_adopt.add_argument("--presentation-profile-reason", default="", help="Required reason for --retire-presentation-profile")
    p_adopt.add_argument("--presentation-profile-authority", default="owner", help="Authority retiring the presentation profile")
    p_adopt.add_argument("--record-release-distribution", action="append", default=[], metavar="PATH", help="Record detached-signature and release-channel manifest verification; repeat as needed")
    p_adopt.add_argument("--retire-release-distribution", default="", metavar="DISTRIBUTION_ID", help="Retire a release distribution contract")
    p_adopt.add_argument("--release-distribution-reason", default="", help="Required reason for --retire-release-distribution")
    p_adopt.add_argument("--release-distribution-authority", default="owner", help="Authority retiring the release distribution contract")
    p_adopt.add_argument("--record-cold-session-validation", action="append", default=[], metavar="PATH", help="Record matched fresh-agent comparison evidence requirements; repeat as needed")
    p_adopt.add_argument("--retire-cold-session-validation", default="", metavar="VALIDATION_ID", help="Retire a cold-session validation contract")
    p_adopt.add_argument("--cold-session-validation-reason", default="", help="Required reason for --retire-cold-session-validation")
    p_adopt.add_argument("--cold-session-validation-authority", default="owner", help="Authority retiring the cold-session validation contract")
    p_adopt.add_argument("--record-release-proof", action="append", default=[], metavar="PATH", help="Record a bounded exact-package release-surface assurance contract; repeat as needed")
    p_adopt.add_argument("--retire-release-proof", default="", metavar="RELEASE_PROOF_ID", help="Retire a bounded Release Proof contract")
    p_adopt.add_argument("--release-proof-reason", default="", help="Required reason for --retire-release-proof")
    p_adopt.add_argument("--release-proof-authority", default="owner", help="Authority retiring the bounded Release Proof contract")
    p_adopt.add_argument("--record-release-authorization", default="", metavar="PATH", help="Record a separate project-declared authorization for one exact final package")
    p_adopt.add_argument("--retire-release-authorization", default="", metavar="AUTHORIZATION_ID", help="Retire an exact-package release authorization")
    p_adopt.add_argument("--release-authorization-reason", default="", help="Required reason for --retire-release-authorization")
    p_adopt.add_argument("--release-authorization-authority", default="owner", help="Authority retiring the exact-package release authorization")
    p_adopt.add_argument("--record-field-trial", action="append", default=[], metavar="PATH", help="Record a project-owned field-validation trial plan; repeat as needed")
    p_adopt.add_argument("--retire-field-trial", default="", metavar="TRIAL_ID", help="Retire a recorded field-validation trial")
    p_adopt.add_argument("--field-trial-reason", default="", help="Required reason for --retire-field-trial")
    p_adopt.add_argument("--field-trial-authority", default="owner", help="Authority retiring the field-validation trial")
    p_adopt.add_argument("--json", action="store_true")

    p_resume = sub.add_parser("resume", help="Generate the layered continuation packet")
    p_resume.add_argument("project", nargs="?", default=".")
    p_resume.add_argument("--budget", choices=("compact", "standard", "full"), default="compact")
    p_resume.add_argument("--query", default="", help="Optional bounded continuity retrieval focus; does not alter authority or project state")
    p_resume.add_argument("--read-only", action="store_true", help="Bounded read-only consultation: read the project bytes but write NOTHING into the project tree (transient state goes to a disposable directory outside it)")
    p_resume.add_argument("--json", action="store_true")

    p_check = sub.add_parser("check", help="Run explicit changed-file scoped checks")
    p_check.add_argument("project", nargs="?", default=".")
    p_check.add_argument("--changed", action="append", default=[], help="Externally supplied changed path; repeat as needed")
    p_check.add_argument("--run-native", action="store_true", help="Run the canonical gate only when its execution mode is forge-authorized")
    p_check.add_argument("--import-native-evidence", default="", metavar="PATH", help="Import structured owner or external-CI evidence bound to the current native-gate fingerprint")
    p_check.add_argument("--checkpoint", action="store_true", help="Accept the current snapshot after a passing scoped Check")
    p_check.add_argument("--close-session", action="store_true", help="Record a durable Session Close after this Check")
    p_check.add_argument("--session-type", choices=SESSION_TYPES, default="code-increment", help="Classify the completed session")
    p_check.add_argument("--summary", default="", help="Brief session summary")
    p_check.add_argument("--completed", action="append", default=[], help="Completed work item; repeat as needed")
    p_check.add_argument("--decision", action="append", default=[], metavar="DECISION::RATIONALE", help="Accepted decision with rationale; repeat as needed")
    p_check.add_argument("--owner-fact", action="append", default=[], metavar="FACT::IMPACT", help="Owner-provided project fact and its design impact; repeat as needed")
    p_check.add_argument("--risk", action="append", default=[], help="Unresolved risk; repeat as needed")
    p_check.add_argument("--next-action", default="", help="Exact next action required when closing the session")
    p_check.add_argument("--provider", default="", help="Provider name for exact provider-reported token counts")
    p_check.add_argument("--provider-input-tokens", type=int, default=None, help="Exact provider-reported input tokens for this session")
    p_check.add_argument("--provider-output-tokens", type=int, default=None, help="Exact provider-reported output tokens for this session")
    p_check.add_argument("--retry-count", type=int, default=0, help="Observed task retries during this session")
    p_check.add_argument("--correction-count", type=int, default=0, help="Observed material corrections during this session")
    p_check.add_argument("--session-output-characters", type=int, default=None, help="Observed assistant output characters, when available")
    p_check.add_argument("--benchmark-id", default="", help="Matched benchmark identifier; requires exact provider token counts")
    p_check.add_argument("--benchmark-arm", choices=("with-forge", "without-forge"), default="", help="Matched benchmark arm")
    p_check.add_argument("--run-capability", action="append", choices=tuple(CAPABILITY_CATALOG), default=[], help="Run an explicitly activated advanced capability; repeat as needed")
    p_check.add_argument("--runtime-state-evidence", action="append", default=[], metavar="PATH", help="Import owner or external-CI scenario evidence bound to a recorded runtime-state matrix; repeat as needed")
    p_check.add_argument("--state-transition-evidence", action="append", default=[], metavar="PATH", help="Import owner or external-CI persisted-state transition, deployment-receipt, and rollback evidence; repeat as needed")
    p_check.add_argument("--field-observation", default="", metavar="PATH", help="Record one project-owned field observation with Session Close")
    p_check.add_argument("--export-continuity", default="", metavar="PATH", help="After Session Close, export a separate portable Forge continuity companion ZIP")
    p_check.add_argument("--development-package", default="", metavar="PATH", help="Optional development-package ZIP whose digest will be bound to --export-continuity")
    p_check.add_argument("--json", action="store_true")

    p_ship = sub.add_parser("ship", help="Run comprehensive release assurance when activated")
    p_ship.add_argument("project", nargs="?", default=".")
    p_ship.add_argument("--json", action="store_true")

    p_bind = sub.add_parser("bind", help="Deterministic G1 binders (advisory, read-only): release-truth · gate-coverage · gate-diff")
    bind_sub = p_bind.add_subparsers(dest="binder", required=True, metavar="{release-truth,gate-coverage,gate-diff}")
    b_rt = bind_sub.add_parser("release-truth", help="Bind accepted-vs-candidate release truth to the accepted source commit")
    b_rt.add_argument("--repo", required=True)
    b_rt.add_argument("--head", required=True)
    b_rt.add_argument("--config", required=True)
    b_rt.add_argument("--json", action="store_true")
    b_gc = bind_sub.add_parser("gate-coverage", help="Report checks present in the tree but not invoked by the declared gate")
    b_gc.add_argument("--repo", required=True)
    b_gc.add_argument("--head", required=True)
    b_gc.add_argument("--config", required=True)
    b_gc.add_argument("--json", action="store_true")
    b_gd = bind_sub.add_parser("gate-diff", help="Certify a gate-script change removed no assertion and added no SKIP path")
    b_gd.add_argument("--repo", required=True)
    b_gd.add_argument("--base", required=True)
    b_gd.add_argument("--head", required=True)
    b_gd.add_argument("--config", required=True)
    b_gd.add_argument("--json", action="store_true")

    p_ledger = sub.add_parser("ledger", help="Append-only witness truth ledger: append · supersede · verify · show")
    ledger_sub = p_ledger.add_subparsers(dest="ledger_command", required=True, metavar="{append,supersede,verify,show}")

    def _add_claim_flags(target: argparse.ArgumentParser) -> None:
        target.add_argument("--project", default=".")
        target.add_argument("--claim", required=True, help="The claim being recorded")
        target.add_argument("--verdict", required=True, choices=sorted(VERDICTS), help="Verdict of the claim against ground truth")
        target.add_argument("--subject", default="project", help="Subject the claim is about (default: project)")
        target.add_argument("--source", default="", help="Where the claim was made (doc, bus message, checkpoint)")
        target.add_argument("--source-ref", dest="source_ref", default="", help="Exact reference for the source (SHA, line, id)")
        target.add_argument("--gt-kind", default="", help="Ground-truth binding kind (e.g. git-rev-list, sha256, blob-identity)")
        target.add_argument("--gt-pointer", default="", help="Ground-truth target (command, path, object)")
        target.add_argument("--gt-observed", default="", help="What the ground truth actually showed")
        target.add_argument("--method", default="", help="How the verdict was reached (reproduce command)")
        target.add_argument("--observer", default="forge-observer", help="Who recorded the entry")
        target.add_argument("--note", default="", help="Optional durable note")
        target.add_argument("--json", action="store_true")

    l_append = ledger_sub.add_parser("append", help="Record a claim -> ground-truth -> verdict entry")
    _add_claim_flags(l_append)
    l_supersede = ledger_sub.add_parser("supersede", help="Append a new verdict that supersedes a prior entry (never edits it)")
    l_supersede.add_argument("--target", required=True, help="Id of the current-tip entry being superseded")
    _add_claim_flags(l_supersede)
    l_verify = ledger_sub.add_parser("verify", help="Prove chain integrity (exit 0 HEALTHY, 1 BLOCKED)")
    l_verify.add_argument("--project", default=".")
    l_verify.add_argument("--json", action="store_true")
    l_show = ledger_sub.add_parser("show", help="Current verdict per claim-lineage, with history and verdict flips")
    l_show.add_argument("--project", default=".")
    l_show.add_argument("--json", action="store_true")

    p_advanced = sub.add_parser("advanced", help=argparse.SUPPRESS)
    p_advanced.add_argument("--project", default=".")
    p_advanced.add_argument("--json", action="store_true")
    sub.add_parser("self-test", help=argparse.SUPPRESS)
    return parser


def _render_operational_block(exc: Exception, *, json_output: bool) -> None:
    payload: dict[str, Any] = {
        "schema": 1,
        "status": "BLOCKED",
        "claim": "Forge operation blocked",
        "reason": str(exc),
        "preservation": "Existing Forge state was preserved and was not replaced with defaults.",
        "ai_notice": {
            "schema": 1,
            "id": "notice-state-integrity-blocked",
            "level": "blocker",
            "summary": str(exc),
            "category": "state-integrity",
            "speak": True,
            "repeated": False,
            "mode": "standard",
            "details": {},
        },
    }
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("FORGE BLOCKED — STATE OR OPERATION INTEGRITY")
        print(str(exc))
        print("Existing Forge state was preserved and was not replaced with defaults.")
        print()
        print(f"Forge — {exc}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["run"]
    elif argv[0] in {"--budget", "--json", "--session-context"}:
        argv = ["run", *argv]
    parser = _build_parser()
    args = parser.parse_args(argv)
    forge_root = _forge_root()
    try:
        if args.command == "run":
            return handle_run(args, forge_root)
        if args.command == "help":
            return handle_help(args, forge_root)
        if args.command == "adopt":
            return handle_adopt(args, parser, forge_root)
        if args.command == "resume":
            return handle_resume(args, forge_root)
        if args.command == "check":
            return handle_check(args, parser, forge_root)
        if args.command == "bind":
            return handle_bind(args, parser, forge_root)
        if args.command == "ledger":
            return handle_ledger(args, parser, forge_root)
        if args.command == "ship":
            return handle_ship(args, forge_root)
        if args.command == "advanced":
            return handle_advanced(args)
        if args.command == "self-test":
            return handle_self_test(forge_root)
    except (ForgeStateError, ForgeLockError, ValueError) as exc:
        _render_operational_block(exc, json_output=bool(getattr(args, "json", False)))
        return 1
    return 2

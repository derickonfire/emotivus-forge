from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.session_close import parse_durable_pairs
from ..core.handoff import export_continuity_bundle
from ..core.storage import state_transaction
from ..core.telemetry import normalize_interaction_telemetry
from ..core.sidecar import update_sidecar_status
from ..services.scoped_check import render_check, run_scoped_check
from .common import append_notice, print_json
from .noticing import attach_check_notice


def handle_check(args: Any, parser: Any, forge_root: Path) -> int:
    session_fields_used = bool(
        args.summary or args.completed or args.decision or args.owner_fact or args.risk or args.next_action
        or args.session_type != "code-increment"
    )
    telemetry_fields_used = bool(
        args.provider or args.provider_input_tokens is not None or args.provider_output_tokens is not None
        or args.retry_count or args.correction_count or args.session_output_characters is not None
        or args.benchmark_id or args.benchmark_arm
    )
    if args.run_native and args.import_native_evidence:
        parser.error("Use either --run-native or --import-native-evidence, not both")
    if args.field_observation and not args.close_session:
        parser.error("--field-observation requires --close-session")
    if args.export_continuity and not args.close_session:
        parser.error("--export-continuity requires --close-session")
    if args.development_package and not args.export_continuity:
        parser.error("--development-package requires --export-continuity")
    if (session_fields_used or telemetry_fields_used) and not args.close_session:
        parser.error("Session Close and interaction telemetry fields require --close-session")
    if args.close_session and not args.next_action.strip():
        parser.error("--close-session requires --next-action")
    try:
        decisions = parse_durable_pairs(args.decision, label="decision", detail_label="rationale")
        owner_facts = parse_durable_pairs(args.owner_fact, label="owner fact", detail_label="impact")
    except ValueError as exc:
        parser.error(str(exc))
    close_data = None
    if args.close_session:
        try:
            interaction_telemetry = normalize_interaction_telemetry(
                provider=args.provider,
                provider_input_tokens=args.provider_input_tokens,
                provider_output_tokens=args.provider_output_tokens,
                retry_count=args.retry_count,
                correction_count=args.correction_count,
                session_output_characters=args.session_output_characters,
                benchmark_id=args.benchmark_id,
                benchmark_arm=args.benchmark_arm,
            )
        except ValueError as exc:
            parser.error(str(exc))
        close_data = {
            "session_type": args.session_type,
            "summary": args.summary,
            "completed_work": args.completed,
            "decisions": decisions,
            "owner_facts": owner_facts,
            "unresolved_risks": args.risk,
            "next_action": args.next_action,
            "interaction_telemetry": interaction_telemetry,
            "field_observation_path": args.field_observation,
        }
    root = Path(args.project).resolve()
    with state_transaction(root):
        payload = run_scoped_check(
            root, forge_root,
            supplied_paths=args.changed,
            run_native=args.run_native,
            import_native_evidence_path=args.import_native_evidence,
            checkpoint=args.checkpoint,
            session_close_data=close_data,
            requested_capabilities=args.run_capability,
            runtime_state_evidence_paths=args.runtime_state_evidence,
            state_transition_evidence_paths=args.state_transition_evidence,
        )
        authority = payload.get("authority_baseline", {}) if isinstance(payload.get("authority_baseline"), dict) else {}
        changes = payload.get("changes", {}) if isinstance(payload.get("changes"), dict) else {}
        sidecar = update_sidecar_status(
            root,
            mode="evidence-analysis" if args.close_session and args.session_type == "audit" else "development-sidecar",
            operation="check",
            work_scope=args.next_action.strip() if args.close_session else str(payload.get("claim", "Scoped Check")),
            authority_status=str(authority.get("status", "")),
            unexpected_mutations=int(authority.get("pending_count", changes.get("count", 0)) or 0),
            check_status=str(payload.get("status", "UNKNOWN")),
        )
        payload["sidecar"] = sidecar
    if args.export_continuity:
        try:
            payload["continuity_bundle"] = export_continuity_bundle(
                root,
                args.export_continuity,
                development_package=args.development_package,
                forge_root=forge_root,
            )
        except ValueError as exc:
            parser.error(str(exc))
    attach_check_notice(payload, root)
    print_json(payload) if args.json else print(append_notice(render_check(payload), payload), end="")
    return 0 if payload.get("status") == "PASS" else 1

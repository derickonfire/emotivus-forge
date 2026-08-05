from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.common import utc_now
from ..core.ledger import record_event
from ..core.ship_claims import assess_ship_claims
from ..core.sidecar import update_sidecar_status
from ..core.workspace_integrity import assess_workspace_integrity, persist_workspace_assessment
from ..core.artifact_collision import observe_version_collisions


def ship_project(project_root: Path, forge_root: Path | None = None) -> dict[str, Any]:
    forge_root = (forge_root or Path(__file__).resolve().parents[2]).resolve()
    workspace_integrity = (
        assess_workspace_integrity(project_root)
        if (project_root / ".forge").is_dir()
        else {"status": "NOT_ESTABLISHED", "reason": "Project is not adopted."}
    )
    if (project_root / ".forge").is_dir():
        persist_workspace_assessment(project_root, workspace_integrity)
    artifact_collisions = observe_version_collisions(project_root)
    claims = assess_ship_claims(project_root, forge_root, perform_remote=True)
    highest = str(claims.get("highest_supported_claim", "none"))
    integrity_current = workspace_integrity.get("status") == "CURRENT"
    collisions_clear = artifact_collisions.get("status") == "PASS"
    release_ready = claims.get("release_ready") is True and integrity_current and collisions_clear
    payload = {
        "schema": 4,
        "generated_utc": utc_now(),
        "status": "PASS" if release_ready else "BLOCKED",
        "claim": (
            "Every project-declared cumulative release requirement is current and the exact final package has a current project-declared release authorization."
            if release_ready else "Ship remains blocked; bounded claim readiness was assessed."
        ),
        "reason": (
            "Forge validated the complete bounded claim ladder through exact-package owner release authorization. This does not authenticate the human, prove universal correctness, or guarantee future channel state."
            if release_ready else "Forge can report the highest evidence-supported lower claim, but release-ready requires every exact-package requirement, sufficient real field evidence, and a current separate exact-package release authorization."
        ),
        "highest_supported_claim": highest,
        "claim_readiness": claims,
        "workspace_integrity": workspace_integrity,
        "artifact_version_collisions": artifact_collisions,
        "required_before_activation": [] if release_ready else ([
            "a current passing-Check workspace seal candidate with no subsequent content drift"
        ] if not integrity_current else []) + ([
            "resolution of every observed same-name, same-version, different-byte ZIP collision"
        ] if not collisions_clear else []) + [
            "current exact final-package binding, complete bounded confidentiality screening, and public-review receipts",
            "current bounded Release Proof across every declared exact-package surface and required assurance domain",
            "current detached signatures and signed release-channel manifests",
            "sufficient matched cold-session comparative validation",
            "current independent remote release-channel verification for every required signed-manifest channel",
            "a separate current project-declared authorization bound to the exact package, build, and named release channels",
        ],
        "project_level_success": release_ready,
        "release_ready": release_ready,
    }
    if (project_root / ".forge").is_dir():
        record_event(project_root, "ship-readiness-assessed", {
            "highest_supported_claim": highest,
            "release_ready": release_ready,
            "level_statuses": {str(item.get("level_id")): str(item.get("status")) for item in claims.get("levels", []) if isinstance(item, dict)},
        })
        payload["sidecar"] = update_sidecar_status(
            project_root,
            mode="release-assessment",
            operation="ship",
            work_scope="Assess the exact package claim ladder.",
            ship_status="READY" if release_ready else "BLOCKED",
            ship_active=False,
        )
    return payload


def render_ship(payload: dict[str, Any]) -> str:
    readiness = payload.get("claim_readiness", {}) if isinstance(payload.get("claim_readiness"), dict) else {}
    lines = [
        "FORGE SHIP — READY" if payload.get("release_ready") else "FORGE SHIP — BLOCKED",
        str(payload.get("claim", "Ship is unavailable.")),
        f"Highest supported claim: {payload.get('highest_supported_claim', 'none')}",
        "Claim ladder:",
        f"Workspace seal candidate: {payload.get('workspace_integrity', {}).get('status', 'NOT_ESTABLISHED')}",
        f"Observed artifact collisions: {payload.get('artifact_version_collisions', {}).get('status', 'NOT_RUN')}",
    ]
    for item in readiness.get("levels", []):
        if not isinstance(item, dict):
            continue
        lines.append(f"  - {item.get('title', item.get('level_id', 'claim'))}: {item.get('status', 'UNKNOWN')}")
        for requirement in item.get("requirements", []):
            if isinstance(requirement, dict) and requirement.get("status") != "PASS":
                lines.append(f"      {requirement.get('status', 'UNKNOWN')}: {requirement.get('reason', '')}")
    if payload.get("release_ready"):
        lines.extend([
            "Bounded release-ready claim: PASS",
            "This does not authenticate the human, prove universal correctness, or guarantee future package or channel state.",
        ])
    else:
        lines.extend([
            "Release requirements still missing:",
            *[f"  - {item}" for item in payload.get("required_before_activation", [])],
            "A passing lower claim is not release readiness.",
        ])
    return "\n".join(lines).rstrip() + "\n"

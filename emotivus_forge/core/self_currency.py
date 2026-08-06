from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from .. import __version__
from .common import normalize_rel, sha256_file
from .evidence_validity import effective_native_validity
from .orientation import load_project_ignore
from .project_identity import project_identity_record
from .truth import TruthRecord, summarize_truth_records


def _ignored(relative: str, patterns: list[str]) -> bool:
    value = relative.strip("/")
    return any(
        fnmatch.fnmatch(value, pattern)
        or fnmatch.fnmatch(value + "/", pattern)
        or fnmatch.fnmatch(value, pattern.rstrip("/"))
        for pattern in patterns
    )


def _source_record(project_root: Path, source: str, *, subject: str, ignore: list[str]) -> dict[str, Any]:
    value = normalize_rel(source)
    if not value or value in {"owner", "migration", "inline"}:
        return TruthRecord(
            subject=subject,
            truth_state="CONFIRMED" if value == "owner" else "UNKNOWN",
            result="CURRENT" if value == "owner" else "UNKNOWN",
            verification_tier="static",
            attempted=False,
            reason="Owner-confirmed source does not require a project path." if value == "owner" else "No project source is registered.",
            source=value,
        ).to_dict()
    path = project_root / value
    if not path.is_file() or path.is_symlink():
        return TruthRecord(
            subject=subject,
            truth_state="STALE",
            result="MISSING",
            verification_tier="static",
            attempted=True,
            reason="The registered project source does not resolve to a readable regular file.",
            source=value,
        ).to_dict()
    if _ignored(value, ignore):
        return TruthRecord(
            subject=subject,
            truth_state="CONTRADICTED",
            result="EXCLUDED",
            verification_tier="static",
            attempted=True,
            reason="The registered source is excluded by .forgeignore and cannot support current Forge knowledge.",
            source=value,
        ).to_dict()
    return TruthRecord(
        subject=subject,
        truth_state="OBSERVED",
        result="CURRENT",
        verification_tier="static",
        attempted=True,
        reason="The registered source exists inside the active project scan boundary.",
        source=value,
    ).to_dict()


def assess_self_currency(
    project_root: Path,
    passport: dict[str, Any],
    authorities: dict[str, Any],
    native_registry: dict[str, Any],
    *,
    current_tree_fingerprint: str = "",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    ignore = load_project_ignore(project_root)
    records: list[dict[str, Any]] = []

    objective = authorities.get("objective", {}) if isinstance(authorities.get("objective"), dict) else {}
    objective_source = str(objective.get("source", ""))
    objective_text = str(objective.get("text", "")).strip()
    if not objective_text and isinstance(passport.get("objective"), dict):
        # Preserve the last adopted support long enough to identify it as stale rather
        # than silently converting a disappeared source into an unrelated unknown.
        prior_objective = passport["objective"]
        objective_source = str(prior_objective.get("source", objective_source))
        objective_text = str(prior_objective.get("text", objective_text)).strip()
    objective_record = _source_record(project_root, objective_source, subject="continuity.objective", ignore=ignore)
    if not objective_text:
        objective_record.update({
            "truth_state": "UNKNOWN",
            "result": "UNRESOLVED",
            "reason": "Forge has no explicit current objective; continuity is not ready to guide a cold session.",
        })
    records.append(objective_record)

    identity_record = project_identity_record(project_root)
    if identity_record:
        identity_source = str(identity_record.get("contract_source", ""))
        identity_status = str(identity_record.get("status", "unknown"))
        records.append(TruthRecord(
            subject="project.identity",
            truth_state="CONFIRMED" if identity_status == "active" else "STALE",
            result="CURRENT" if identity_status == "active" else "APPROVAL_REQUIRED",
            verification_tier="static",
            attempted=True,
            reason=(
                "The owner-controlled multi-component identity is fingerprint-bound to its current source."
                if identity_status == "active" else str(identity_record.get("reason", "Project identity requires renewed authority."))
            ),
            source=identity_source,
        ).to_dict())

    recorded_forge_version = str(passport.get("forge_version", "")).strip()
    records.append(TruthRecord(
        subject="forge.runtime-version",
        truth_state="OBSERVED" if recorded_forge_version == __version__ else "STALE",
        result="CURRENT" if recorded_forge_version == __version__ else "MISMATCH",
        verification_tier="static",
        attempted=True,
        reason=(
            "The Project Passport was generated by the running Forge version."
            if recorded_forge_version == __version__
            else f"The Project Passport records Forge {recorded_forge_version or 'unknown'} while the running build is {__version__}."
        ),
        source=".forge/passport.json",
    ).to_dict())

    canonical = native_registry.get("canonical") if isinstance(native_registry.get("canonical"), dict) else None
    approval = native_registry.get("approval", {}) if isinstance(native_registry.get("approval"), dict) else {}
    if canonical:
        source_file = str(canonical.get("source", "")).split("#", 1)[0]
        source_record = _source_record(project_root, source_file, subject="native-gate.source", ignore=ignore)
        records.append(source_record)
        current_fingerprint = str(canonical.get("fingerprint", ""))
        approved_fingerprint = str(approval.get("approved_fingerprint", ""))
        approval_status = str(approval.get("status", "required"))
        execution_mode = str(approval.get("execution_mode", "unassigned"))
        current_policy = (
            approval_status in {"approved", "registered"}
            and execution_mode != "unassigned"
            and bool(approved_fingerprint)
            and current_fingerprint == approved_fingerprint
        )
        records.append(TruthRecord(
            subject="native-gate.approval",
            truth_state="CONFIRMED" if current_policy else "STALE" if approved_fingerprint else "UNKNOWN",
            result="CURRENT" if current_policy else "REAPPROVAL_REQUIRED" if approved_fingerprint else "UNASSIGNED",
            verification_tier="static",
            attempted=True,
            reason=(
                f"The project-owned native-gate execution mode `{execution_mode}` is bound to the current fingerprint."
                if current_policy
                else "The native gate has no current fingerprint-bound execution mode."
            ),
            source=source_file,
        ).to_dict())
    else:
        records.append(TruthRecord(
            subject="native-gate.source",
            truth_state="UNKNOWN",
            result="NOT_REGISTERED",
            verification_tier="static",
            attempted=True,
            reason="No canonical native quality ecosystem was detected.",
        ).to_dict())

    evidence = passport.get("evidence", {}) if isinstance(passport.get("evidence"), dict) else {}
    native_evidence = evidence.get("native_gate", {}) if isinstance(evidence.get("native_gate"), dict) else {}
    if native_evidence:
        validity = effective_native_validity(native_evidence, current_tree_fingerprint)
        records.append(TruthRecord(
            subject="native-gate.evidence",
            truth_state="STALE" if "stale" in validity else "OBSERVED",
            result=validity.upper().replace("-", "_"),
            verification_tier=str(native_evidence.get("verification_tier", "sandbox")),
            attempted=True,
            reason="Recorded native evidence is connected to the current source snapshot." if "stale" not in validity else "Recorded native evidence was invalidated by connected project changes.",
            source=str(native_evidence.get("raw_result", ".forge/evidence/native-gate")),
        ).to_dict())
    else:
        records.append(TruthRecord(
            subject="native-gate.evidence",
            truth_state="NOT_RUN",
            result="ABSENT",
            verification_tier="sandbox",
            attempted=False,
            reason="No native-gate evidence has been recorded for this project.",
        ).to_dict())

    summary = summarize_truth_records(records)
    material_subjects = {"continuity.objective", "forge.runtime-version", "native-gate.approval", "project.identity"}
    severe = [
        row for row in records
        if row.get("truth_state") == "CONTRADICTED"
        and (str(row.get("subject", "")) in material_subjects or str(row.get("subject", "")).startswith("native-gate"))
    ]
    stale = [
        row for row in records
        if row.get("truth_state") in {"STALE", "UNKNOWN"}
        and str(row.get("subject", "")) in material_subjects
    ]
    # Missing native tooling or evidence remains visible in the truth summary, but does
    # not make a project noisy merely because it has no native gate yet.
    status = "FAIL" if severe else "WARN" if stale else "PASS"
    attention = [
        str(row.get("reason", "")) for row in [*severe, *stale]
        if str(row.get("reason", ""))
    ]
    return {
        "schema": 1,
        "status": status,
        "truth_state": "OBSERVED",
        "verification_tier": "static",
        "records": records,
        "summary": summary,
        "attention": attention[:12],
        "claim": "Forge self-currency compares its own continuity and native-evidence references with the current project boundary.",
        "exclusions": [
            "semantic correctness of project documents",
            "runtime or deployment truth",
            "whether an owner-confirmed objective is strategically correct",
        ],
    }

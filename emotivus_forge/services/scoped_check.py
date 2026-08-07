from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..core.change_ledger import build_change_record, build_check_plan
from ..core.authority_baseline import assess_authority_baseline
from ..core.capabilities import CAPABILITY_CATALOG, require_active_capability
from ..core.changes import change_count_phrase, detect_changes, snapshot_fingerprint
from ..core.common import read_json, utc_now, write_json
from ..core.evidence_validity import invalidate_connected_evidence
from ..core.guardrails import evaluate_guardrails
from ..core.ledger_assertions import evaluate_ledger_assertions
from ..core.lifecycle import verify_lifecycle_invariants
from ..core.check_qualification import qualify_evidence_records
from ..core.provenance import evaluate_artifact_provenance
from ..core.deployable_boundary import evaluate_deployable_boundaries
from ..core.canonical_claims import evaluate_canonical_claims
from ..core.relationships import evaluate_relationships, augment_check_plan
from ..core.runtime_matrix import evaluate_runtime_matrices
from ..core.state_transitions import evaluate_state_transitions
from ..core.ledger import record_event
from ..core.native_tools import load_or_discover_native_tools
from ..core.paths import ForgePaths
from ..core.self_currency import assess_self_currency
from ..core.project_identity import detect_identity_literal_copies
from ..core.lineage import lineage_summary
from ..core.migration_identity import migration_identity_summary
from ..core.package_family import package_family_summary
from ..core.surface_coverage import surface_coverage_summary
from ..core.truth import TruthRecord, summarize_truth_records
from ..core.state import load_settings, load_state, save_state
from ..core.telemetry import record_metric
from ..core.workspace_integrity import fingerprint_workspace, TRUTH_BOUNDARY as WORKSPACE_TRUTH_BOUNDARY
from .native_gate import import_native_evidence, run_native_gate

TEXT_SUFFIXES = {
    ".py", ".php", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".html", ".htm",
    ".md", ".rst", ".adoc", ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ".sql", ".sh",
}
MERGE_START = re.compile(r"^\s*<{7}(?:\s|$)")
MERGE_MIDDLE = re.compile(r"^\s*={7}(?:\s|$)")
MERGE_END = re.compile(r"^\s*>{7}(?:\s|$)")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")
REMOTE_SCHEMES = {"http", "https", "mailto", "tel", "data", "javascript"}


class _LocalAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        wanted = {"href"} if tag.lower() == "link" else {"src"} if tag.lower() in {"script", "img", "source", "video", "audio", "iframe"} else set()
        if not wanted:
            return
        for key, value in attrs:
            if key.lower() in wanted and value:
                self.references.append((value.strip(), self.getpos()[0]))


def _read_text(path: Path, limit: int = 2_000_000) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _local_target(project_root: Path, source: Path, raw: str) -> Path | None:
    if not raw or raw.startswith("#") or raw.startswith("//") or any(token in raw for token in ("{{", "}}", "<%", "%>")):
        return None
    parsed = urlsplit(raw)
    if parsed.scheme.lower() in REMOTE_SCHEMES or parsed.netloc:
        return None
    clean = parsed.path
    if not clean:
        return None
    return project_root / clean.lstrip("/") if clean.startswith("/") else source.parent / clean


def _css_structure_findings(relative: str, text: str) -> list[dict[str, Any]]:
    depth = 0
    line = 1
    string_quote = ""
    comment = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if char == "\n":
            line += 1
        if comment:
            if char == "*" and nxt == "/":
                comment = False
                index += 2
                continue
            index += 1
            continue
        if string_quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == string_quote:
                string_quote = ""
            index += 1
            continue
        if char == "/" and nxt == "*":
            comment = True
            index += 2
            continue
        if char in {"'", '"'}:
            string_quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return [{
                    "check": "core.css-structure", "severity": "blocker", "path": relative,
                    "line": line, "message": "Stylesheet contains an unmatched closing brace.",
                }]
        index += 1
    if comment:
        return [{"check": "core.css-structure", "severity": "blocker", "path": relative, "line": line, "message": "Stylesheet comment is not closed."}]
    if string_quote:
        return [{"check": "core.css-structure", "severity": "blocker", "path": relative, "line": line, "message": "Stylesheet string is not closed."}]
    if depth:
        return [{"check": "core.css-structure", "severity": "blocker", "path": relative, "line": line, "message": "Stylesheet contains an unmatched opening brace."}]
    return []


def _check_path(project_root: Path, relative: str) -> tuple[list[dict[str, Any]], list[str]]:
    path = project_root / relative
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        return [], []
    text = _read_text(path)
    if text is None:
        return [], []
    findings: list[dict[str, Any]] = []
    executed = ["core.merge-marker"]
    for number, line in enumerate(text.splitlines(), 1):
        if MERGE_START.match(line) or MERGE_MIDDLE.match(line) or MERGE_END.match(line):
            findings.append({
                "check": "core.merge-marker", "severity": "blocker", "path": relative,
                "line": number, "message": "Unresolved merge marker found.",
            })
    suffix = path.suffix.lower()
    if suffix == ".json":
        executed.append("core.json-syntax")
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            findings.append({
                "check": "core.json-syntax", "severity": "blocker", "path": relative,
                "line": exc.lineno, "message": f"Invalid JSON: {exc.msg}",
            })
    elif suffix == ".py":
        executed.append("core.python-syntax")
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            findings.append({
                "check": "core.python-syntax", "severity": "blocker", "path": relative,
                "line": exc.lineno or 0, "message": f"Python syntax error: {exc.msg}",
            })
    elif suffix in {".html", ".htm"}:
        executed.append("core.html-local-assets")
        parser = _LocalAssetParser()
        try:
            parser.feed(text)
            parser.close()
        except Exception as exc:  # HTMLParser exceptions are rare but must remain bounded.
            findings.append({
                "check": "core.html-local-assets", "severity": "blocker", "path": relative,
                "line": 0, "message": f"HTML could not be parsed: {exc}",
            })
        for raw, line in parser.references:
            target = _local_target(project_root, path, raw)
            if target is not None and not target.exists():
                findings.append({
                    "check": "core.html-local-assets", "severity": "blocker", "path": relative,
                    "line": line, "message": f"Missing local asset target: {raw}",
                })
    elif suffix in {".css", ".scss"}:
        executed.append("core.css-structure")
        findings.extend(_css_structure_findings(relative, text))
    elif suffix in {".md", ".rst", ".adoc"}:
        executed.append("core.markdown-local-links")
        for match in MARKDOWN_LINK.finditer(text):
            raw = match.group(1).strip("<>")
            target = _local_target(project_root, path, raw)
            if target is not None and not target.exists():
                line = text.count("\n", 0, match.start()) + 1
                findings.append({
                    "check": "core.markdown-local-links", "severity": "blocker", "path": relative,
                    "line": line, "message": f"Missing local documentation target: {raw}",
                })
    return findings, sorted(set(executed))


def _update_passport_native_evidence(project_root: Path, passport: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("status") not in {"PASS", "FAIL", "ERROR"}:
        return
    evidence = result.get("evidence", {}) if isinstance(result.get("evidence"), dict) else {}
    raw = result.get("raw_evidence", {}) if isinstance(result.get("raw_evidence"), dict) else {}
    records = result.get("evidence_records", []) if isinstance(result.get("evidence_records"), list) else []
    normalized_records = []
    for item in records:
        if not isinstance(item, dict):
            continue
        normalized_records.append({
            "id": str(item.get("id", "")),
            "status": str(item.get("status", "UNKNOWN")),
            "type": str(item.get("type", "native")),
            "surfaces": list(item.get("surfaces", [])) if isinstance(item.get("surfaces"), list) else [],
            "validity": "current",
            "truth_state": str(item.get("truth_state", "OBSERVED")),
            "verification_tier": str(item.get("verification_tier", "sandbox")),
            "attempted": bool(item.get("attempted", True)),
        })
    passport_evidence = passport.get("evidence", {})
    if not isinstance(passport_evidence, dict):
        passport_evidence = {}
    passport_evidence["native_gate"] = {
        "status": result.get("status"),
        "returncode": result.get("returncode"),
        "entry_count": evidence.get("entry_count", 0),
        "status_counts": evidence.get("status_counts", {}),
        "evidence_types": evidence.get("evidence_types", []),
        "surfaces": evidence.get("surfaces", []),
        "records": normalized_records,
        "validity": "current",
        # DG-8: persist the source tree fingerprint so readers (resume, self-currency)
        # can downgrade this evidence to stale once the project tree changes.
        "source_tree_fingerprint": str(result.get("source_tree_fingerprint", "")),
        "raw_result": raw.get("result", ""),
        "truth": result.get("truth", {}),
        "truth_summary": evidence.get("truth_summary", {}),
        "verification_tier": str(result.get("truth", {}).get("verification_tier", "sandbox")) if isinstance(result.get("truth"), dict) else "sandbox",
        "updated_utc": utc_now(),
    }
    passport["evidence"] = passport_evidence
    passport["surface_coverage"] = {
        "status": evidence.get("coverage_status", "unknown"),
        "surfaces": evidence.get("surfaces", []),
        "source": "native-gate-structured-evidence" if evidence.get("surfaces") else "native-gate-result-without-surface-markers",
        "validity": "current",
        "raw_result": raw.get("result", ""),
        "verification_tier": str(result.get("truth", {}).get("verification_tier", "sandbox")) if isinstance(result.get("truth"), dict) else "sandbox",
        "truth_state": str(result.get("truth", {}).get("truth_state", "OBSERVED")) if isinstance(result.get("truth"), dict) else "OBSERVED",
    }
    write_json(ForgePaths(project_root).passport, passport)


def run_scoped_check(
    project_root: Path,
    forge_root: Path,
    *,
    supplied_paths: list[str] | None = None,
    run_native: bool = False,
    import_native_evidence_path: str = "",
    checkpoint: bool = False,
    session_close_data: dict[str, Any] | None = None,
    requested_capabilities: list[str] | None = None,
    runtime_state_evidence_paths: list[str] | None = None,
    state_transition_evidence_paths: list[str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    project_root = project_root.resolve()
    paths = ForgePaths(project_root)
    passport = read_json(paths.passport, {})
    if not isinstance(passport, dict) or passport.get("schema") != 1:
        raise RuntimeError("Project has not been adopted by this Forge core.")
    settings = load_settings(project_root)
    state = load_state(project_root)
    previous_snapshot = state.get("snapshot", {}) if isinstance(state.get("snapshot"), dict) else {}
    changes = detect_changes(project_root, forge_root, previous_snapshot, settings, supplied_paths=supplied_paths)
    authority_baseline = assess_authority_baseline(state, changes["current_snapshot"], project_root=project_root)
    project_lineage = lineage_summary(project_root, forge_root)
    migration_identity = migration_identity_summary(project_root, forge_root)
    package_family = package_family_summary(project_root, forge_root)
    surface_coverage_contract = surface_coverage_summary(project_root, forge_root)
    relationship_impacts = evaluate_relationships(project_root, changes["paths"])
    plan = augment_check_plan(build_check_plan(changes), relationship_impacts)
    change_record = build_change_record(changes, plan, previous_snapshot, authority_baseline)

    evidence_invalidation = invalidate_connected_evidence(passport, plan, change_record["id"])
    write_json(paths.passport, passport)

    # Native verification is intentionally first when the owner explicitly requests it.
    native_registry = load_or_discover_native_tools(project_root, refresh=True)
    native_result: dict[str, Any] = {
        "status": "NOT_RUN",
        "reason": "Native gate execution was not requested.",
        "command": [],
        "returncode": None,
        "execution_mode": str(native_registry.get("approval", {}).get("execution_mode", "unassigned")) if isinstance(native_registry.get("approval"), dict) else "unassigned",
        "execution_authority": "",
        "evidence": {"entry_count": 0, "surfaces": [], "coverage_status": "unknown"},
        "evidence_records": [],
        "raw_evidence": {},
        "truth": TruthRecord(
            subject="native-gate.execution", truth_state="NOT_RUN", result="NOT_RUN",
            verification_tier="sandbox", attempted=False,
            reason="Native gate execution was not requested.",
        ).to_dict(),
    }
    execution_order: list[str] = []
    if run_native:
        execution_order.append("project-native-gate")
        native_result = run_native_gate(project_root, native_registry, int(settings.get("native_gate_timeout_seconds", 180)))
        _update_passport_native_evidence(project_root, passport, native_result)
    elif import_native_evidence_path:
        execution_order.append("project-native-evidence-import")
        native_result = import_native_evidence(
            project_root, native_registry, import_native_evidence_path,
            source_tree_fingerprint=snapshot_fingerprint(changes["current_snapshot"]),
        )
        _update_passport_native_evidence(project_root, passport, native_result)

    from ..core.authority_registry import load_or_discover_authorities
    authorities = load_or_discover_authorities(project_root, forge_root, refresh=True, settings=settings)
    self_currency = assess_self_currency(project_root, passport, authorities, native_registry, current_tree_fingerprint=snapshot_fingerprint(changes["current_snapshot"]))

    findings: list[dict[str, Any]] = []
    relationship_configured = bool(
        relationship_impacts.get("active_count", 0)
        or relationship_impacts.get("attention_count", 0)
    )
    if relationship_configured:
        execution_order.append("forge-confirmed-relationships")
    findings.extend(
        item for item in relationship_impacts.get("findings", []) if isinstance(item, dict)
    )
    for reason in self_currency.get("attention", []):
        findings.append({
            "check": "core.self-currency",
            "severity": "blocker" if self_currency.get("status") == "FAIL" else "warning",
            "path": ".forge",
            "line": 0,
            "message": str(reason),
        })
    checked_paths: list[str] = []
    executed_checks: set[str] = set()
    if relationship_configured:
        executed_checks.add("core.confirmed-relationships")
    identity_literals = detect_identity_literal_copies(project_root, forge_root)
    if identity_literals.get("status") != "NOT_CONFIGURED":
        execution_order.append("forge-identity-single-source")
        executed_checks.add("core.identity-single-source")
        findings.extend(item for item in identity_literals.get("findings", []) if isinstance(item, dict))
    guardrails = evaluate_guardrails(project_root, changes["paths"])
    if guardrails.get("active_count", 0):
        execution_order.append("forge-safety-guardrails")
        executed_checks.add("core.safety-guardrails")
        findings.extend(item for item in guardrails.get("findings", []) if isinstance(item, dict))
    ledger_assertions = evaluate_ledger_assertions(project_root)
    if ledger_assertions.get("evaluations"):
        execution_order.append("forge-ledger-assertions")
        executed_checks.add("core.ledger-assertions")
        findings.extend(item for item in ledger_assertions.get("findings", []) if isinstance(item, dict))
    provenance = evaluate_artifact_provenance(project_root)
    if provenance.get("evaluations") or provenance.get("unregistered_deliverables"):
        execution_order.append("forge-artifact-provenance")
        if provenance.get("evaluations"):
            executed_checks.add("core.artifact-provenance")
        if provenance.get("unregistered_deliverables"):
            executed_checks.add("core.delivery-perimeter")
        findings.extend(item for item in provenance.get("findings", []) if isinstance(item, dict))
    deployable_boundaries = evaluate_deployable_boundaries(project_root, changes["paths"])
    if deployable_boundaries.get("active_count", 0) or deployable_boundaries.get("evaluations"):
        execution_order.append("forge-deployable-boundary")
        executed_checks.add("core.deployable-boundary")
        findings.extend(item for item in deployable_boundaries.get("findings", []) if isinstance(item, dict))
    canonical_claims = evaluate_canonical_claims(project_root)
    if canonical_claims.get("active_count", 0) or canonical_claims.get("evaluations"):
        execution_order.append("forge-canonical-claims")
        executed_checks.add("core.canonical-claims")
        findings.extend(item for item in canonical_claims.get("findings", []) if isinstance(item, dict))
    check_qualification = qualify_evidence_records(
        project_root,
        native_result.get("evidence_records", []) if isinstance(native_result.get("evidence_records"), list) else [],
    )
    if check_qualification.get("evidence_check_count", 0):
        execution_order.append("forge-check-qualification")
    capability_results: list[dict[str, Any]] = []
    requested = list(dict.fromkeys(requested_capabilities or []))
    for capability_id in requested:
        execution_order.append(f"forge-capability:{capability_id}")
        try:
            activation = require_active_capability(project_root, capability_id, "check")
        except (RuntimeError, ValueError) as exc:
            result = {
                "capability_id": capability_id,
                "status": "BLOCKED",
                "reason": str(exc),
                "legacy_vault_loaded": False,
                "findings": [{
                    "check": f"capability.{capability_id}", "severity": "blocker", "path": ".", "line": 0,
                    "message": str(exc),
                }],
            }
        else:
            if capability_id == "doctor":
                from .doctor import run_doctor  # Lazy import only after an active current contract is proven.
                result = run_doctor(project_root, activation)
            elif capability_id == "runtime-proof":
                from .runtime_proof import run_runtime_proof  # Lazy import only after an active current contract is proven.
                result = run_runtime_proof(project_root, activation)
                passport_evidence = passport.get("evidence", {}) if isinstance(passport.get("evidence"), dict) else {}
                passport_evidence["runtime_proof"] = {
                    "status": result.get("status", "UNKNOWN"),
                    "recipe_count": result.get("recipe_count", 0),
                    "counts": result.get("counts", {}),
                    "truth_records": result.get("truth_records", []),
                    "updated_utc": utc_now(),
                    "truth_boundary": result.get("truth_boundary", ""),
                }
                passport["evidence"] = passport_evidence
                write_json(paths.passport, passport)
            else:
                result = {
                    "capability_id": capability_id,
                    "status": "BLOCKED",
                    "reason": f"{CAPABILITY_CATALOG.get(capability_id, {}).get('name', capability_id)} has no active implementation.",
                    "legacy_vault_loaded": False,
                    "findings": [{
                        "check": f"capability.{capability_id}", "severity": "blocker", "path": ".", "line": 0,
                        "message": "The requested capability has no certified active implementation.",
                    }],
                }
        capability_results.append(result)
        findings.extend(item for item in result.get("findings", []) if isinstance(item, dict))
        executed_checks.add(f"capability.{capability_id}")
    runtime_matrices = evaluate_runtime_matrices(
        project_root, forge_root, capability_results, runtime_state_evidence_paths or []
    )
    if runtime_matrices.get("findings") or runtime_state_evidence_paths:
        execution_order.append("forge-runtime-state-matrix")
        executed_checks.add("core.runtime-state-matrix")
    findings.extend(item for item in runtime_matrices.get("findings", []) if isinstance(item, dict))
    state_transitions = evaluate_state_transitions(
        project_root, forge_root, capability_results, state_transition_evidence_paths or []
    )
    if state_transitions.get("findings") or state_transition_evidence_paths:
        execution_order.append("forge-state-transition")
        executed_checks.add("core.state-transition")
    findings.extend(item for item in state_transitions.get("findings", []) if isinstance(item, dict))
    if changes["paths"]:
        execution_order.append(f"forge-{plan.get('profile', 'scoped')}-checks")
    for relative in changes["paths"]:
        path = project_root / relative
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            checked_paths.append(relative)
            path_findings, path_checks = _check_path(project_root, relative)
            findings.extend(path_findings)
            executed_checks.update(path_checks)

    authority_status = str(authority_baseline.get("status", "NOT_ESTABLISHED"))
    authority_truth_state = (
        "CONFIRMED" if authority_status == "CURRENT"
        else "OBSERVED" if authority_status == "QUARANTINED"
        else "CONTRADICTED" if authority_status == "CONTRADICTED"
        else "UNKNOWN"
    )
    authority_result = "PASS" if authority_status == "CURRENT" else "WARN" if authority_status == "QUARANTINED" else "FAIL" if authority_status == "CONTRADICTED" else "UNKNOWN"
    if authority_status == "CONTRADICTED":
        findings.append({
            "severity": "blocker",
            "check": "core.authority-baseline-integrity",
            "path": ".forge/state.json",
            "line": 1,
            "message": str(authority_baseline.get("reason", "Authority-baseline state is contradicted.")),
        })
        executed_checks.add("core.authority-baseline-integrity")
    lineage_status = str(project_lineage.get("status", "NOT_RECORDED"))
    if lineage_status in {"CONTRADICTED", "APPROVAL_REQUIRED", "BLOCKED"}:
        findings.append({
            "severity": "blocker",
            "check": "core.project-lineage-integrity",
            "path": ".forge/settings.json",
            "line": 1,
            "message": str(project_lineage.get("reason", "Project lineage is contradicted or stale.")),
        })
        executed_checks.add("core.project-lineage-integrity")
    elif int(project_lineage.get("same_version_candidate_collision_count", 0) or 0) > 0:
        findings.append({
            "severity": "warning",
            "check": "core.project-lineage-collision",
            "path": ".forge/settings.json",
            "line": 1,
            "message": "An incoming quarantined branch reuses the active display version for different exact tree bytes.",
        })
        executed_checks.add("core.project-lineage-collision")
    migration_status = str(migration_identity.get("status", "NOT_DECLARED"))
    if migration_status in {"CONTRADICTED", "BLOCKED", "RECONCILIATION_REQUIRED"}:
        findings.append({
            "severity": "blocker",
            "check": "core.migration-identity",
            "path": ".forge/settings.json",
            "line": 1,
            "message": str(migration_identity.get("reason", "Migration identity is contradicted or requires reconciliation.")),
        })
        executed_checks.add("core.migration-identity")
    elif migration_status == "NOT_DECLARED":
        findings.append({
            "severity": "warning",
            "check": "core.migration-identity",
            "path": ".forge/settings.json",
            "line": 1,
            "message": "No exact migration catalog or explicit no-migrations declaration is recorded for the active lineage.",
        })
        executed_checks.add("core.migration-identity")
    truth_records: list[dict[str, Any]] = [TruthRecord(
        subject="observed-change-reconciliation", truth_state="OBSERVED", result="PASS",
        verification_tier="static", attempted=True,
        reason=f"Compared the current bounded project snapshot with the observed checkpoint; {changes['count']} path(s) changed. This is change-detection authority only, not project-authority acceptance.",
        source=".forge/state.json",
    ).to_dict(), TruthRecord(
        subject="authority-baseline.current-tree",
        truth_state=authority_truth_state,
        result=authority_result,
        verification_tier="static",
        attempted=authority_status != "NOT_ESTABLISHED",
        reason=str(authority_baseline.get("reason", "Authority-baseline status is unavailable.")),
        source=".forge/state.json",
        exclusions=("human identity authentication", "file authorship", "substantive code review", "release readiness"),
    ).to_dict(), TruthRecord(
        subject="project-lineage.current-tree",
        truth_state=("CONFIRMED" if lineage_status == "CURRENT" else "OBSERVED" if lineage_status in {"WORKING_CHANGES", "NOT_RECORDED"} else "CONTRADICTED"),
        result=("PASS" if lineage_status == "CURRENT" else "WARN" if lineage_status in {"WORKING_CHANGES", "NOT_RECORDED"} else "FAIL"),
        verification_tier="static",
        attempted=lineage_status != "NOT_RECORDED",
        reason=str(project_lineage.get("reason", "Exact project lineage is unavailable.")),
        source=".forge/settings.json",
        exclusions=("authorship", "semantic compatibility", "merge correctness", "release authorization"),
    ).to_dict(), TruthRecord(
        subject="migration-identity.current-lineage",
        truth_state=(
            "CONFIRMED" if migration_status in {"CURRENT", "CURRENT_WITH_RECONCILIATION"}
            else "OBSERVED" if migration_status == "NOT_DECLARED"
            else "CONTRADICTED"
        ),
        result=(
            "PASS" if migration_status in {"CURRENT", "CURRENT_WITH_RECONCILIATION"}
            else "WARN" if migration_status == "NOT_DECLARED"
            else "FAIL"
        ),
        verification_tier="static",
        attempted=migration_status != "NOT_DECLARED",
        reason=str(migration_identity.get("reason", "Migration identity is unavailable.")),
        source=".forge/settings.json",
        exclusions=("live database execution", "upgrade safety", "rollback correctness", "deployment state"),
    ).to_dict()]
    for check_id in sorted(executed_checks):
        matching_findings = [
            item for item in findings
            if str(item.get("check", "")) == check_id
            or (check_id == "core.safety-guardrails" and str(item.get("check", "")) in {"core.atomic-guardrail", "core.event-obligation", "core.guardrail-current"})
            or (check_id == "core.ledger-assertions" and str(item.get("check", "")) == "core.ledger-assertions")
            or (check_id == "core.deployable-boundary" and str(item.get("check", "")) == "core.deployable-boundary")
            or (check_id == "core.canonical-claims" and str(item.get("check", "")) == "core.canonical-claims")
            or (check_id == "core.confirmed-relationships" and str(item.get("check", "")) in {"core.relationship-current", "core.confirmed-relationships"})
            or (check_id == "core.runtime-state-matrix" and str(item.get("check", "")) == "core.runtime-state-matrix")
            or (check_id == "core.state-transition" and str(item.get("check", "")) == "core.state-transition")
        ]
        check_failed = any(item.get("severity") == "blocker" for item in matching_findings)
        check_warned = any(item.get("severity") == "warning" for item in matching_findings)
        check_result = "FAIL" if check_failed else ("WARN" if check_warned else "PASS")
        truth_records.append(TruthRecord(
            subject=check_id, truth_state="OBSERVED", result=check_result,
            verification_tier="sandbox" if check_id.startswith("capability.doctor") else "static",
            attempted=True,
            reason="The listed Forge check executed against the canonical observed changed surface; authority acceptance is evaluated separately.",
        ).to_dict())
    for provenance_row in provenance.get("evaluations", []):
        if not isinstance(provenance_row, dict):
            continue
        p_status = str(provenance_row.get("status", "UNKNOWN"))
        p_bound = str(provenance_row.get("binding", "")) == "instance-bound"
        # CONFIRMED requires the provenance recording to be instance-bound, not merely
        # a byte-match against a record an imported package could have authored.
        current_confirmed = p_status == "CURRENT" and p_bound
        truth_records.append(TruthRecord(
            subject=f"artifact-provenance:{provenance_row.get('provenance_id', 'unknown')}",
            truth_state="CONFIRMED" if current_confirmed else "STALE" if p_status == "STALE" else "OBSERVED",
            result="PASS" if p_status == "CURRENT" else "FAIL" if p_status == "STALE" else "UNKNOWN",
            verification_tier="static",
            attempted=True,
            reason=(
                "Current artifact bytes, declared inputs, generator source, contract, and baseline match the authority-recorded digests, corroborated by an instance-bound provenance event."
                if current_confirmed else
                "Current artifact bytes match the recorded digests, but the provenance recording is not instance-bound (unsigned or imported); it is not asserted as authenticated provenance."
                if p_status == "CURRENT" else "; ".join(str(item) for item in provenance_row.get("reasons", []) if str(item)) or str(provenance_row.get("reason", "Artifact provenance requires authority attention."))
            ),
            source=str(provenance_row.get("artifact_path", "")),
            exclusions=("declared generator execution", "artifact behavior", "delivery", "deployment", "release readiness"),
        ).to_dict())
    for unregistered_path in provenance.get("unregistered_deliverables", []):
        truth_records.append(TruthRecord(
            subject=f"delivery-perimeter:{unregistered_path}", truth_state="UNKNOWN", result="UNKNOWN",
            verification_tier="static", attempted=True,
            reason="A deliverable-shaped artifact was observed without registered provenance; delivery assurance is unavailable.",
            source=str(unregistered_path),
        ).to_dict())
    for boundary_row in deployable_boundaries.get("evaluations", []):
        if not isinstance(boundary_row, dict):
            continue
        b_status = str(boundary_row.get("status", "UNKNOWN"))
        truth_records.append(TruthRecord(
            subject=f"deployable-boundary:{boundary_row.get('boundary_id', 'unknown')}",
            truth_state="CONFIRMED" if b_status == "PASS" else "STALE" if b_status in {"FAIL", "APPROVAL_REQUIRED"} else "UNKNOWN",
            result="PASS" if b_status == "PASS" else "FAIL" if b_status in {"FAIL", "APPROVAL_REQUIRED"} else "UNKNOWN",
            verification_tier="static", attempted=True,
            reason=("The canonical observed changed set was classified without overlap and registered delta artifacts matched their allowed changed-path set and baseline." if b_status == "PASS" else str(boundary_row.get("reason", "Deployable boundary requires attention."))),
            source=str(boundary_row.get("contract_source", "")),
            exclusions=("deployment", "artifact behavior", "release readiness"),
        ).to_dict())
    for claims_row in canonical_claims.get("evaluations", []):
        if not isinstance(claims_row, dict):
            continue
        c_status = str(claims_row.get("status", "UNKNOWN"))
        truth_records.append(TruthRecord(
            subject=f"canonical-claims:{claims_row.get('claim_set_id', 'unknown')}",
            truth_state="CONFIRMED" if c_status == "PASS" else "CONTRADICTED" if c_status == "FAIL" else "STALE",
            result="PASS" if c_status == "PASS" else "FAIL",
            verification_tier="static", attempted=True,
            reason=("All explicit authority-recorded canonical claims matched their current deterministic evidence." if c_status == "PASS" else str(claims_row.get("reason", "One or more canonical claims contradict current evidence."))),
            source=str(claims_row.get("contract_source", "")),
            exclusions=("arbitrary prose interpretation", "release correctness", "deployment"),
        ).to_dict())
    for relationship_row in relationship_impacts.get("evaluations", []):
        if not isinstance(relationship_row, dict):
            continue
        r_status = str(relationship_row.get("status", "UNKNOWN"))
        truth_records.append(TruthRecord(
            subject=f"confirmed-relationships:{relationship_row.get('relationship_set_id', 'unknown')}",
            truth_state=(
                "CONFIRMED" if r_status in {"CURRENT", "IMPACTED"}
                else "STALE" if r_status in {"STALE", "APPROVAL_REQUIRED"}
                else "UNKNOWN"
            ),
            result=(
                "PASS" if r_status in {"CURRENT", "IMPACTED"}
                else "FAIL" if r_status in {"STALE", "APPROVAL_REQUIRED"}
                else "UNKNOWN"
            ),
            verification_tier="static",
            attempted=True,
            reason=(
                f"Traversed {relationship_row.get('impact_count', 0)} impact(s) from the current authority-recorded relationship set."
                if r_status in {"CURRENT", "IMPACTED"}
                else str(relationship_row.get("reason", "The relationship set requires authority attention or has missing required endpoints."))
            ),
            source=str(relationship_row.get("contract_source", "")),
            exclusions=("unrecorded relationships", "runtime reachability", "behavioral correctness", "proof that related paths changed"),
        ).to_dict())
    for qualification in check_qualification.get("records", []):
        if not isinstance(qualification, dict):
            continue
        q_status = str(qualification.get("qualification_status", "unqualified"))
        q_state = "CONFIRMED" if q_status == "qualified" else "STALE" if q_status == "stale" else "UNKNOWN"
        q_result = "PASS" if q_status == "qualified" else "UNKNOWN"
        truth_records.append(TruthRecord(
            subject=f"check-qualification:{qualification.get('check_id', 'unknown')}",
            truth_state=q_state,
            result=q_result,
            verification_tier=str(qualification.get("verification_tier", "sandbox")),
            attempted=q_status == "qualified",
            reason=(
                f"Recorded {qualification.get('negative_case_count', 0)} known-bad case(s) failed under the current check-source fingerprint."
                if q_status == "qualified" else str(qualification.get("reason", "No current negative-test qualification exists."))
            ),
            source=str(qualification.get("qualification_id", "")),
            exclusions=tuple(str(item) for item in qualification.get("limitations", []) if str(item).strip()),
        ).to_dict())
    for matrix_row in runtime_matrices.get("evaluations", []):
        if not isinstance(matrix_row, dict):
            continue
        for scenario in matrix_row.get("scenarios", []):
            if not isinstance(scenario, dict):
                continue
            status_value = str(scenario.get("status", "UNKNOWN"))
            truth_records.append(TruthRecord(
                subject=f"runtime-state:{matrix_row.get('matrix_id', 'unknown')}:{scenario.get('scenario_id', 'unknown')}",
                truth_state=str(scenario.get("truth_state", "UNKNOWN")),
                result=status_value,
                verification_tier=str(scenario.get("verification_tier", "sandbox")),
                attempted=status_value != "NOT_RUN",
                reason=(
                    "Authority-bound deployment and migration evidence matched the recorded candidate, baseline, prior-state identity, current migration bytes, and same-Check runtime recipes."
                    if status_value == "PASS" else str(scenario.get("reason", "No runtime-state evidence was supplied."))
                ),
                source=str(scenario.get("evidence_source", matrix_row.get("contract_source", ""))),
                exclusions=tuple(str(item) for item in scenario.get("exclusions", []) if str(item).strip()),
            ).to_dict())
    for plan_row in state_transitions.get("evaluations", []):
        if not isinstance(plan_row, dict):
            continue
        for transition in plan_row.get("transitions", []):
            if not isinstance(transition, dict):
                continue
            status_value = str(transition.get("status", "UNKNOWN"))
            rollback = transition.get("rollback", {}) if isinstance(transition.get("rollback"), dict) else {}
            truth_records.append(TruthRecord(
                subject=f"state-transition:{plan_row.get('plan_id', 'unknown')}:{transition.get('transition_id', 'unknown')}",
                truth_state=str(transition.get("truth_state", "UNKNOWN")),
                result=status_value,
                verification_tier=str(transition.get("verification_tier", "sandbox")),
                attempted=status_value != "NOT_RUN",
                reason=(
                    "Authority-bound state snapshots, safe semantic validators, exact deployment artifact receipt, migration evidence, same-Check runtime proof, and the declared rollback availability or drill evidence matched the recorded transition."
                    if status_value == "PASS" else str(transition.get("reason", "No persisted-state transition evidence was supplied."))
                ),
                source=str(transition.get("evidence_source", plan_row.get("contract_source", ""))),
                exclusions=tuple(str(item) for item in transition.get("exclusions", []) if str(item).strip()) + (("rollback not required",) if rollback.get("required") is False else ()),
            ).to_dict())
    for capability_result in capability_results:
        if not isinstance(capability_result, dict):
            continue
        truth_records.extend(
            row for row in capability_result.get("truth_records", []) if isinstance(row, dict)
        )
    native_truth = native_result.get("truth", {}) if isinstance(native_result.get("truth"), dict) else {}
    if native_truth:
        truth_records.append(native_truth)
    truth_records.extend(
        row for row in self_currency.get("records", []) if isinstance(row, dict)
    )
    truth_summary = summarize_truth_records(truth_records)

    lifecycle_invariants = verify_lifecycle_invariants(truth_records, project_root)
    for component, detail in lifecycle_invariants.get("components", {}).items():
        for violation in detail.get("violated", []):
            findings.append({
                "check": "core.lifecycle-invariant",
                "severity": "warning",
                "path": ".",
                "line": 0,
                "message": (
                    f"Replaced component '{component}' declared invariant "
                    f"{violation['subject']}={violation['required']}, but the current truth-state is {violation['actual']}."
                ),
            })

    blocked = any(item.get("severity") == "blocker" for item in findings) or native_result["status"] in {"BLOCKED", "FAIL", "ERROR"}
    aggregate_eligible = authority_status != "NOT_ESTABLISHED"
    if blocked:
        status = "FAIL"
    elif not aggregate_eligible:
        status = "NOT_RUN"
    else:
        status = "PASS"
    aggregate_eligibility = {
        "schema": 1,
        "status": "ELIGIBLE" if aggregate_eligible else "NOT_ELIGIBLE",
        "reason": (
            "An explicit project-authority baseline exists, so the bounded aggregate Check may report PASS or FAIL."
            if aggregate_eligible
            else "No explicit project-authority baseline exists. Forge preserved observed sub-check results, but the aggregate scoped Check is NOT_RUN and cannot checkpoint or satisfy Ship."
        ),
        "resolving_artifact": ".forge/state.json",
        "resolving_command": (
            "forge check ."
            if aggregate_eligible
            else f"forge adopt . --authorize-baseline {authority_baseline.get('current_fingerprint', '')} --baseline-reason \"Reviewed and accepted this exact tree.\"; forge check . --checkpoint"
        ),
        "truth_boundary": (
            "Aggregate eligibility is a project-authority precondition. Individual observed checks may still execute and fail before a baseline exists, "
            "but their absence of blockers cannot become a top-level PASS."
        ),
    }
    workspace_integrity = {
        "status": "NOT_ESTABLISHED",
        "reason": "A passing checkpointed Check is required before a workspace seal candidate exists.",
        "truth_boundary": WORKSPACE_TRUTH_BOUNDARY,
    }
    if checkpoint and status == "PASS":
        state["snapshot"] = changes["current_snapshot"]
        candidate = fingerprint_workspace(project_root)
        existing_workspace = state.get("workspace_integrity", {}) if isinstance(state.get("workspace_integrity"), dict) else {}
        state["workspace_integrity"] = {
            "schema": 1,
            "status": "CANDIDATE_CURRENT",
            "session_start": existing_workspace.get("session_start", {}),
            "seal_candidate": candidate,
            "last_assessment": {
                "status": "CURRENT",
                "assessed_utc": utc_now(),
                "expected_fingerprint": candidate["fingerprint"],
                "observed_fingerprint": candidate["fingerprint"],
            },
            "truth_boundary": WORKSPACE_TRUTH_BOUNDARY,
        }
        workspace_integrity = {
            "status": "CURRENT",
            "fingerprint": candidate["fingerprint"],
            "file_count": candidate["file_count"],
            "total_bytes": candidate["total_bytes"],
            "truth_boundary": WORKSPACE_TRUTH_BOUNDARY,
        }
    state["change_ledger"] = {
        key: value for key, value in change_record.items()
        if key not in {"observed", "supplied"}
    }
    state["last_operation"] = "check"
    state["last_check"] = {
        "utc": utc_now(),
        "status": status,
        "change_id": change_record["id"],
        "changed_paths": changes["paths"],
        "profile": plan["profile"],
        "affected_surfaces": plan["affected_surfaces"],
        "executed_checks": sorted(executed_checks),
        "scope": "observed-change-ledger + surface-scoped-forge-checks" + (" + confirmed-relationship-impact" if relationship_impacts.get("active_count", 0) else "") + (" + authority-recorded-safety-guardrails" if guardrails.get("active_count", 0) else "") + (" + active-ledger-assertions" if ledger_assertions.get("evaluations") else "") + (" + approved-native-gate-first" if run_native else "") + (" + imported-native-evidence" if import_native_evidence_path else "") + (" + artifact-provenance-and-delivery-perimeter" if provenance.get("evaluations") or provenance.get("unregistered_deliverables") else "") + (" + deployable-boundary" if deployable_boundaries.get("active_count", 0) else "") + (" + canonical-claims" if canonical_claims.get("active_count", 0) else "") + (" + check-qualification-mapping" if check_qualification.get("evidence_check_count", 0) else "") + (" + explicitly-activated-capabilities" if requested else "") + (" + runtime-state-deployment-matrix" if runtime_matrices.get("evaluations") or runtime_state_evidence_paths else ""),
        "checkpointed": bool(checkpoint and status == "PASS"),
        "workspace_integrity": workspace_integrity,
        "authority_current": bool(authority_baseline.get("status") == "CURRENT"),
        "authority_release_eligible": bool(authority_baseline.get("release_eligible")),
        "authority_baseline_id": str(authority_baseline.get("baseline_id", "")),
        "authority_snapshot_fingerprint": str(authority_baseline.get("baseline_fingerprint", "")),
        "authority_pending_count": int(authority_baseline.get("pending_count", 0) or 0),
        "authority_revalidation_required": False,
        "truth_summary": truth_summary,
        "self_currency_status": self_currency.get("status", "UNKNOWN"),
        "ledger_assertions": {"status": ledger_assertions.get("status", "PASS"), "active_count": ledger_assertions.get("active_count", 0)},
        "check_qualification": {"counts": check_qualification.get("counts", {}), "qualified_ratio": check_qualification.get("qualified_ratio", "0/0")},
        "artifact_provenance": {"status": provenance.get("status", "PASS"), "active_count": provenance.get("active_count", 0), "unregistered_deliverables": len(provenance.get("unregistered_deliverables", []))},
        "deployable_boundaries": {"status": deployable_boundaries.get("status", "PASS"), "active_count": deployable_boundaries.get("active_count", 0), "unclassified_count": deployable_boundaries.get("unclassified_count", 0)},
        "canonical_claims": {"status": canonical_claims.get("status", "PASS"), "active_count": canonical_claims.get("active_count", 0), "claim_count": canonical_claims.get("claim_count", 0)},
        "relationships": {"status": relationship_impacts.get("status", "NOT_CONFIGURED"), "active_count": relationship_impacts.get("active_count", 0), "impact_count": relationship_impacts.get("impact_count", 0), "related_path_count": relationship_impacts.get("related_path_count", 0)},
        "runtime_state_matrices": {"status": runtime_matrices.get("status", "PASS"), "active_count": runtime_matrices.get("active_count", 0), "scenario_count": runtime_matrices.get("scenario_count", 0), "confirmed_count": runtime_matrices.get("confirmed_count", 0), "not_run_count": runtime_matrices.get("not_run_count", 0)},
        "state_transitions": {"status": state_transitions.get("status", "PASS"), "active_count": state_transitions.get("active_count", 0), "transition_count": state_transitions.get("transition_count", 0), "confirmed_count": state_transitions.get("confirmed_count", 0), "partial_plan_count": state_transitions.get("partial_plan_count", 0), "rollback_confirmed_count": state_transitions.get("rollback_confirmed_count", 0), "rollback_availability_confirmed_count": state_transitions.get("rollback_availability_confirmed_count", 0), "rollback_drill_confirmed_count": state_transitions.get("rollback_drill_confirmed_count", 0), "rollback_correctness_confirmed_count": state_transitions.get("rollback_correctness_confirmed_count", 0), "coverage_required_count": state_transitions.get("coverage_required_count", 0), "coverage_confirmed_count": state_transitions.get("coverage_confirmed_count", 0), "coverage_not_run_count": state_transitions.get("coverage_not_run_count", 0), "coverage_partial_count": state_transitions.get("coverage_partial_count", 0), "not_run_count": state_transitions.get("not_run_count", 0)},
        "runtime_proof": next(({
            "status": item.get("status", "UNKNOWN"),
            "recipe_count": item.get("recipe_count", 0),
            "counts": item.get("counts", {}),
        } for item in capability_results if isinstance(item, dict) and item.get("capability_id") == "runtime-proof"), {}),
    }
    save_state(project_root, state)

    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "status": status,
        "claim": {"PASS": "Scoped Check PASS", "FAIL": "Scoped Check FAIL", "NOT_RUN": "Scoped Check NOT_RUN"}.get(status, f"Scoped Check {status}"),
        "reason": (
            "One or more bounded checks found a blocker."
            if status == "FAIL"
            else aggregate_eligibility["reason"]
            if status == "NOT_RUN"
            else "The authority-eligible bounded scoped Check completed without a blocker."
        ),
        "aggregate_eligibility": aggregate_eligibility,
        "claim_scope": {
            "included": [
                "canonical observed-checkpoint change reconciliation",
                f"{plan['profile']} surface selection",
                "only the listed Forge checks on canonically observed changed readable files",
            ] + (["authority-recorded relationships used to expand affected surfaces, related-path context, and required checks"] if relationship_impacts.get("active_count", 0) else []) + (["configured owner-declared identity literal scan"] if identity_literals.get("status") != "NOT_CONFIGURED" else []) + (["authority-recorded atomic and event-triggered guardrails evaluated against the canonical observed change set"] if guardrails.get("active_count", 0) else []) + (["authority-recorded deterministic Ledger assertions re-evaluated"] if ledger_assertions.get("evaluations") else []) + (["owner-approved native project gate executed first"] if run_native else []) + (["registered artifact bytes checked against recorded inputs, generator source, and baseline; unregistered delivery-shaped files surfaced"] if provenance.get("evaluations") or provenance.get("unregistered_deliverables") else []) + (["canonical observed changed paths classified by project-owned delivery role and registered delta ZIPs checked against allowed paths and baseline"] if deployable_boundaries.get("active_count", 0) else []) + (["explicit authority-recorded canonical claims checked against current identity, package membership, migration effects, or evidence identity"] if canonical_claims.get("active_count", 0) else []) + (["native evidence qualification mapped to current negative-test records"] if check_qualification.get("evidence_check_count", 0) else []) + (["only explicitly requested capabilities with current activation contracts"] if requested else []) + (["authority-bound runtime-state scenarios checked against the exact recorded candidate, baseline, prior persisted-state identity, current migration bytes, supplied owner/CI testimony, and same-Check runtime recipes"] if runtime_matrices.get("evaluations") or runtime_state_evidence_paths else []) + (["authority-bound persisted-state transitions checked against before/after fixtures, exact deployment artifact receipts, migration evidence, same-Check runtime proof, and required rollback receipts"] if state_transitions.get("evaluations") or state_transition_evidence_paths else []),
            "excluded": [
                "externally supplied paths not corroborated by the observed checkpoint",
                "unchanged files not selected by an explicitly run native gate",
                "browser behavior unless an executed native evidence marker proves it",
                "database state and migrations unless an executed native evidence marker proves them",
                "deployment environment",
                "runtime compatibility unless an executed native evidence marker proves it",
                "release assurance",
                "automatic repair, installation, or environment mutation",
                "feature correctness or completion merely because all guardrail surfaces changed",
                "complete defect coverage merely because a check has recorded negative-test qualification",
                "proof that the declared generator actually ran, artifact behavior, deployment, or delivery correctness merely because provenance is current",
                "deployment or release correctness merely because changed paths are delivery-classified or a delta path set matches",
                "arbitrary prose interpretation beyond explicit project-owned canonical-claim contracts",
                "relationships not explicitly recorded by project authority, runtime reachability, or proof that related paths actually execute together",
                "proof that Forge performed deployment, restored persisted state, executed migrations, or validated data correctness merely because a runtime-state scenario is confirmed",
                "proof that Forge performed or safely automated deployment, migration, state restoration, rollback, arbitrary validation code, or hidden-data inspection merely because a persisted-state transition is confirmed",
                "proof that a route or user journey executed merely because it exists in an exact package or appears in a project-owned surface map",
                "vaulted legacy capability code",
            ],
            "project_level_success": False,
            "authority_boundary": authority_baseline.get("truth_boundary", ""),
            "truth_boundary": "Each result is labeled as observed, confirmed, inferred, unknown, not run, blocked after an attempt, blocked without an attempt, stale, or contradicted. Unrun checks remain unrun; one blocker never explains another result.",
        },
        "change_ledger": {key: value for key, value in change_record.items() if key not in {"current_snapshot"}},
        "changes": {key: value for key, value in changes.items() if key != "current_snapshot"},
        "authority_baseline": authority_baseline,
        "project_lineage": project_lineage,
        "migration_identity": migration_identity,
        "package_family": package_family,
        "surface_coverage_contract": surface_coverage_contract,
        "check_plan": plan,
        "execution_order": execution_order,
        "executed_checks": sorted(executed_checks),
        "checked_paths": checked_paths,
        "findings": findings,
        "evidence_invalidation": evidence_invalidation,
        "native_gate": native_result,
        "identity_literals": identity_literals,
        "guardrails": guardrails,
        "ledger_assertions": ledger_assertions,
        "check_qualification": check_qualification,
        "artifact_provenance": provenance,
        "deployable_boundaries": deployable_boundaries,
        "canonical_claims": canonical_claims,
        "relationships": relationship_impacts,
        "runtime_state_matrices": runtime_matrices,
        "state_transitions": state_transitions,
        "capabilities": capability_results,
        "checkpointed": bool(checkpoint and status == "PASS"),
        "workspace_integrity": workspace_integrity,
        "truth_records": truth_records,
        "truth_summary": truth_summary,
        "lifecycle_invariants": lifecycle_invariants,
        "self_currency": self_currency,
        "full_log": ".forge/ledger.jsonl",
    }
    record_event(project_root, "change-accounting", change_record)
    record_event(project_root, "check", {
        "status": status,
        "claim": payload["claim"],
        "change_id": change_record["id"],
        "change_source": change_record["source"],
        "changed_paths": changes["paths"],
        "rejected_supplied_paths": changes["supplied"]["rejected"],
        "project_lineage": {
            "status": project_lineage.get("status", "NOT_RECORDED"),
            "active_lineage_id": project_lineage.get("active_lineage_id", ""),
            "unresolved_candidate_count": project_lineage.get("unresolved_candidate_count", 0),
            "same_version_candidate_collision_count": project_lineage.get("same_version_candidate_collision_count", 0),
        },
        "migration_identity": {
            "status": migration_identity.get("status", "NOT_DECLARED"),
            "active_inventory_id": migration_identity.get("active_inventory_id", ""),
            "entry_count": migration_identity.get("entry_count", 0),
            "unresolved_collision_count": migration_identity.get("unresolved_collision_count", 0),
            "applied_observation_status": migration_identity.get("applied_observation", {}).get("status", "not-observed"),
        },
        "authority_baseline": {
            "status": authority_baseline.get("status", "NOT_ESTABLISHED"),
            "baseline_id": authority_baseline.get("baseline_id", ""),
            "pending_count": authority_baseline.get("pending_count", 0),
            "release_eligible": authority_baseline.get("release_eligible", False),
        },
        "profile": plan["profile"],
        "affected_surfaces": plan["affected_surfaces"],
        "impact_dimensions": plan["impact_dimensions"],
        "executed_checks": sorted(executed_checks),
        "execution_order": execution_order,
        "findings": findings,
        "evidence_invalidation": evidence_invalidation,
        "native_gate_status": native_result["status"],
        "native_evidence": native_result.get("evidence", {}),
        "native_evidence_ref": native_result.get("raw_evidence", {}).get("result", "") if isinstance(native_result.get("raw_evidence"), dict) else "",
        "identity_literals": {"status": identity_literals.get("status", "NOT_CONFIGURED"), "scanned_files": identity_literals.get("scanned_files", 0), "finding_count": len(identity_literals.get("findings", []))},
        "guardrails": {
            "status": guardrails.get("status", "PASS"),
            "active_count": guardrails.get("active_count", 0),
            "triggered_count": guardrails.get("triggered_count", 0),
            "evaluations": guardrails.get("evaluations", []),
            "truth_boundary": guardrails.get("truth_boundary", ""),
        },
        "ledger_assertions": {
            "status": ledger_assertions.get("status", "PASS"),
            "active_count": ledger_assertions.get("active_count", 0),
            "evaluations": ledger_assertions.get("evaluations", []),
            "truth_boundary": ledger_assertions.get("truth_boundary", ""),
        },
        "check_qualification": {
            "counts": check_qualification.get("counts", {}),
            "qualified_ratio": check_qualification.get("qualified_ratio", "0/0"),
            "truth_boundary": check_qualification.get("truth_boundary", ""),
        },
        "artifact_provenance": {
            "status": provenance.get("status", "PASS"),
            "active_count": provenance.get("active_count", 0),
            "evaluations": provenance.get("evaluations", []),
            "unregistered_deliverables": provenance.get("unregistered_deliverables", []),
            "truth_boundary": provenance.get("truth_boundary", ""),
        },
        "deployable_boundaries": {
            "status": deployable_boundaries.get("status", "PASS"),
            "active_count": deployable_boundaries.get("active_count", 0),
            "classified_count": deployable_boundaries.get("classified_count", 0),
            "unclassified_count": deployable_boundaries.get("unclassified_count", 0),
            "overlap_count": deployable_boundaries.get("overlap_count", 0),
            "evaluations": deployable_boundaries.get("evaluations", []),
            "truth_boundary": deployable_boundaries.get("truth_boundary", ""),
        },
        "canonical_claims": {
            "status": canonical_claims.get("status", "PASS"),
            "active_count": canonical_claims.get("active_count", 0),
            "claim_count": canonical_claims.get("claim_count", 0),
            "evaluations": canonical_claims.get("evaluations", []),
            "truth_boundary": canonical_claims.get("truth_boundary", ""),
        },
        "runtime_state_matrices": {
            "status": runtime_matrices.get("status", "PASS"),
            "active_count": runtime_matrices.get("active_count", 0),
            "scenario_count": runtime_matrices.get("scenario_count", 0),
            "confirmed_count": runtime_matrices.get("confirmed_count", 0),
            "not_run_count": runtime_matrices.get("not_run_count", 0),
            "evaluations": runtime_matrices.get("evaluations", []),
            "truth_boundary": runtime_matrices.get("truth_boundary", ""),
        },
        "state_transitions": {
            "status": state_transitions.get("status", "PASS"),
            "active_count": state_transitions.get("active_count", 0),
            "transition_count": state_transitions.get("transition_count", 0),
            "confirmed_count": state_transitions.get("confirmed_count", 0),
            "partial_plan_count": state_transitions.get("partial_plan_count", 0),
            "rollback_confirmed_count": state_transitions.get("rollback_confirmed_count", 0),
            "rollback_availability_confirmed_count": state_transitions.get("rollback_availability_confirmed_count", 0),
            "rollback_drill_confirmed_count": state_transitions.get("rollback_drill_confirmed_count", 0),
            "rollback_correctness_confirmed_count": state_transitions.get("rollback_correctness_confirmed_count", 0),
            "coverage_required_count": state_transitions.get("coverage_required_count", 0),
            "coverage_confirmed_count": state_transitions.get("coverage_confirmed_count", 0),
            "coverage_not_run_count": state_transitions.get("coverage_not_run_count", 0),
            "coverage_partial_count": state_transitions.get("coverage_partial_count", 0),
            "not_run_count": state_transitions.get("not_run_count", 0),
            "evaluations": state_transitions.get("evaluations", []),
            "truth_boundary": state_transitions.get("truth_boundary", ""),
        },
        "relationships": {
            "status": relationship_impacts.get("status", "NOT_CONFIGURED"),
            "active_count": relationship_impacts.get("active_count", 0),
            "impact_count": relationship_impacts.get("impact_count", 0),
            "related_path_count": relationship_impacts.get("related_path_count", 0),
            "impacts": relationship_impacts.get("impacts", []),
            "truth_boundary": relationship_impacts.get("truth_boundary", ""),
        },
        "capabilities": [{
            "capability_id": item.get("capability_id", ""),
            "status": item.get("status", "UNKNOWN"),
            "mode": item.get("mode", ""),
            "contract_fingerprint": item.get("contract_fingerprint", ""),
            "legacy_vault_loaded": False,
        } for item in capability_results],
        "scope": payload["claim_scope"],
        "truth_summary": truth_summary,
        "self_currency_status": self_currency.get("status", "UNKNOWN"),
    })
    record_metric(project_root, "check", {
        "duration_ms": round((time.monotonic() - started) * 1000),
        "change_id": change_record["id"],
        "changed_paths": changes["count"],
        "profile": plan["profile"],
        "affected_surfaces": len(plan["affected_surfaces"]),
        "checked_paths": len(checked_paths),
        "executed_checks": len(executed_checks),
        "findings": len(findings),
        "invalidated_evidence": evidence_invalidation["invalidated_count"],
        "native_gate": native_result["status"],
        "requested_capabilities": len(requested),
        "capability_findings": sum(len(item.get("findings", [])) for item in capability_results),
        "active_guardrails": guardrails.get("active_count", 0),
        "triggered_guardrails": guardrails.get("triggered_count", 0),
        "guardrail_findings": len(guardrails.get("findings", [])),
        "active_ledger_assertions": ledger_assertions.get("active_count", 0),
        "ledger_assertion_findings": len(ledger_assertions.get("findings", [])),
        "qualified_native_checks": check_qualification.get("counts", {}).get("qualified", 0) if isinstance(check_qualification.get("counts"), dict) else 0,
        "unqualified_native_checks": check_qualification.get("counts", {}).get("unqualified", 0) if isinstance(check_qualification.get("counts"), dict) else 0,
        "active_artifact_provenance": provenance.get("active_count", 0),
        "stale_artifact_provenance": len(provenance.get("blocking_findings", [])),
        "unregistered_deliverables": len(provenance.get("unregistered_deliverables", [])),
        "active_deployable_boundaries": deployable_boundaries.get("active_count", 0),
        "unclassified_changed_paths": deployable_boundaries.get("unclassified_count", 0),
        "active_canonical_claim_sets": canonical_claims.get("active_count", 0),
        "canonical_claim_count": canonical_claims.get("claim_count", 0),
        "active_relationship_sets": relationship_impacts.get("active_count", 0),
        "relationship_impacts": relationship_impacts.get("impact_count", 0),
        "related_paths": relationship_impacts.get("related_path_count", 0),
        "active_runtime_state_matrices": runtime_matrices.get("active_count", 0),
        "confirmed_runtime_state_scenarios": runtime_matrices.get("confirmed_count", 0),
        "active_state_transition_plans": state_transitions.get("active_count", 0),
        "confirmed_state_transitions": state_transitions.get("confirmed_count", 0),
        "confirmed_rollbacks": state_transitions.get("rollback_confirmed_count", 0),
        "status": status,
    })
    if session_close_data is not None:
        from ..core.session_close import close_session
        payload["session_close"] = close_session(
            project_root,
            forge_root,
            check_payload=payload,
            current_snapshot=changes["current_snapshot"],
            **session_close_data,
        )
        from ..core.resume import build_resume
        refreshed = build_resume(project_root, forge_root, budget="compact", refresh=True)
        payload["session_close"]["resume_refreshed"] = True
        payload["session_close"]["resume_path"] = str(project_root / ".forge" / "resume.md")
        payload["session_close"]["resume_status"] = refreshed.get("status", "ATTENTION")
    return payload


def render_check(payload: dict[str, Any]) -> str:
    changes = payload.get("changes", {})
    plan = payload.get("check_plan", {}) if isinstance(payload.get("check_plan"), dict) else {}
    ledger = payload.get("change_ledger", {}) if isinstance(payload.get("change_ledger"), dict) else {}
    lines = [
        f"FORGE {payload.get('claim', 'Scoped Check')}",
        f"Observed change set: {change_count_phrase(changes)} · {ledger.get('id', 'unknown')}",
        f"Profile: {plan.get('profile', 'unknown')}",
        f"Affected surfaces: {', '.join(plan.get('affected_surfaces', [])) or 'none'}",
        f"Checked paths: {len(payload.get('checked_paths', []))}",
        f"Forge checks: {', '.join(payload.get('executed_checks', [])) or 'none'}",
    ]
    if payload.get("status") == "NOT_RUN":
        eligibility = payload.get("aggregate_eligibility", {}) if isinstance(payload.get("aggregate_eligibility"), dict) else {}
        lines.append(f"Aggregate eligibility: {eligibility.get('status', 'NOT_ELIGIBLE')}")
        if payload.get("reason"):
            lines.append(f"Reason: {payload.get('reason')}")
        if eligibility.get("resolving_command"):
            lines.append(f"Resolve with: {eligibility.get('resolving_command')}")
    truth_summary = payload.get("truth_summary", {}) if isinstance(payload.get("truth_summary"), dict) else {}
    state_counts = truth_summary.get("state_counts", {}) if isinstance(truth_summary.get("state_counts"), dict) else {}
    if truth_summary:
        state_text = ", ".join(f"{key} {value}" for key, value in state_counts.items()) or "none"
        lines.append(f"Truth states: {state_text}; highest observed tier: {truth_summary.get('highest_observed_tier', 'static')}")
    authority = payload.get("authority_baseline", {}) if isinstance(payload.get("authority_baseline"), dict) else {}
    if authority:
        strength = authority.get("baseline_strength", {}) if isinstance(authority.get("baseline_strength"), dict) else {}
        lines.append(
            f"Authority baseline: {authority.get('status', 'NOT_ESTABLISHED')} · "
            f"{authority.get('pending_count', 0)} quarantined path(s) · strength {strength.get('status', 'not-established')}"
        )
        if authority.get("status") in {"NOT_ESTABLISHED", "QUARANTINED"}:
            lines.append(f"Review fingerprint: {authority.get('current_fingerprint', 'unavailable')}")
            lines.append(f"  - {authority.get('next_action', '')}")
        elif authority.get("status") == "CONTRADICTED":
            lines.append(f"  - {authority.get('next_action', '')}")
    currency = payload.get("self_currency", {}) if isinstance(payload.get("self_currency"), dict) else {}
    if currency:
        lines.append(f"Forge self-currency: {currency.get('status', 'UNKNOWN')}")
    rejected = changes.get("supplied", {}).get("rejected", []) if isinstance(changes, dict) else []
    if rejected:
        lines.append(f"Rejected supplied paths: {len(rejected)}")
        lines.extend(f"  - {item.get('path')}: {item.get('reason')}" for item in rejected[:8])
    for finding in payload.get("findings", [])[:20]:
        lines.append(f"{finding.get('severity', 'finding').upper()}: {finding.get('path')}:{finding.get('line')} — {finding.get('message')}")
    invalidation = payload.get("evidence_invalidation", {}) if isinstance(payload.get("evidence_invalidation"), dict) else {}
    lines.append(f"Evidence invalidated: {invalidation.get('invalidated_count', 0)} connected record(s)")
    guardrails = payload.get("guardrails", {}) if isinstance(payload.get("guardrails"), dict) else {}
    if guardrails.get("active_count", 0):
        lines.append(f"Atomic guardrails: {guardrails.get('status', 'UNKNOWN')} · {guardrails.get('triggered_count', 0)} triggered")
        for item in guardrails.get("evaluations", [])[:8]:
            if isinstance(item, dict) and item.get("status") not in {"NOT_APPLICABLE"}:
                missing = [str(row.get("id", "")) for row in item.get("missing_surfaces", []) if isinstance(row, dict)]
                suffix = f" · missing: {', '.join(missing)}" if missing else ""
                lines.append(f"  - {item.get('guardrail_id', 'guardrail')}: {item.get('status', 'UNKNOWN')}{suffix}")
    ledger_assertions = payload.get("ledger_assertions", {}) if isinstance(payload.get("ledger_assertions"), dict) else {}
    if ledger_assertions.get("evaluations"):
        lines.append(f"Ledger assertions: {ledger_assertions.get('status', 'UNKNOWN')} · {ledger_assertions.get('active_count', 0)} active")
        for item in ledger_assertions.get("evaluations", [])[:6]:
            if isinstance(item, dict) and item.get("status") != "PASS":
                lines.append(f"  - {item.get('assertion_id', 'assertion')}: {item.get('status', 'UNKNOWN')}")
    provenance = payload.get("artifact_provenance", {}) if isinstance(payload.get("artifact_provenance"), dict) else {}
    if provenance.get("evaluations") or provenance.get("unregistered_deliverables"):
        lines.append(f"Artifact provenance: {provenance.get('status', 'UNKNOWN')} · {provenance.get('active_count', 0)} active · {len(provenance.get('unregistered_deliverables', []))} unregistered deliverable(s)")
    boundaries = payload.get("deployable_boundaries", {}) if isinstance(payload.get("deployable_boundaries"), dict) else {}
    if boundaries.get("active_count", 0) or boundaries.get("evaluations"):
        lines.append(f"Deployable boundaries: {boundaries.get('status', 'UNKNOWN')} · {boundaries.get('classified_count', 0)} classified · {boundaries.get('unclassified_count', 0)} unclassified · {boundaries.get('overlap_count', 0)} overlap")
    claims = payload.get("canonical_claims", {}) if isinstance(payload.get("canonical_claims"), dict) else {}
    if claims.get("active_count", 0) or claims.get("evaluations"):
        lines.append(f"Canonical claims: {claims.get('status', 'UNKNOWN')} · {claims.get('claim_count', 0)} explicit claim(s)")
    relationships = payload.get("relationships", {}) if isinstance(payload.get("relationships"), dict) else {}
    if relationships.get("active_count", 0) or relationships.get("attention_count", 0):
        lines.append(
            f"Confirmed relationships: {relationships.get('status', 'UNKNOWN')} · "
            f"{relationships.get('impact_count', 0)} impact(s) · "
            f"{relationships.get('related_path_count', 0)} related path(s)"
        )
        for item in relationships.get("impacts", [])[:6]:
            if isinstance(item, dict):
                lines.append(
                    f"  - {item.get('relationship_id', 'relationship')} ({item.get('kind', 'relationship')}): "
                    f"{len(item.get('trigger_paths', []))} trigger path(s), {len(item.get('related_paths', []))} related path(s)"
                )
    qualification = payload.get("check_qualification", {}) if isinstance(payload.get("check_qualification"), dict) else {}
    if qualification.get("evidence_check_count", 0):
        counts = qualification.get("counts", {}) if isinstance(qualification.get("counts"), dict) else {}
        lines.append(
            f"Check qualification: {qualification.get('qualified_ratio', '0/0')} qualified; "
            f"{counts.get('unqualified', 0)} unqualified; {counts.get('stale', 0)} stale"
        )
    native = payload.get("native_gate", {})
    if isinstance(native, dict):
        lines.append(f"Native gate: {native.get('status', 'NOT_RUN')}")
        evidence = native.get("evidence", {}) if isinstance(native.get("evidence"), dict) else {}
        if evidence.get("entry_count"):
            lines.append(f"Structured native evidence: {evidence.get('entry_count')} marker(s)")
        if evidence.get("surfaces"):
            lines.append(f"Reported surfaces: {', '.join(evidence.get('surfaces', []))}")
        raw = native.get("raw_evidence", {}) if isinstance(native.get("raw_evidence"), dict) else {}
        if raw.get("result"):
            lines.append(f"Raw native evidence: .forge/{raw.get('result')}")
    runtime_matrices = payload.get("runtime_state_matrices", {}) if isinstance(payload.get("runtime_state_matrices"), dict) else {}
    if runtime_matrices.get("active_count", 0) or runtime_matrices.get("evaluations"):
        lines.append(
            f"Runtime-state matrix: {runtime_matrices.get('status', 'UNKNOWN')} · "
            f"{runtime_matrices.get('confirmed_count', 0)} confirmed · {runtime_matrices.get('not_run_count', 0)} not run"
        )
        for matrix in runtime_matrices.get("evaluations", [])[:4]:
            if not isinstance(matrix, dict):
                continue
            for scenario in matrix.get("scenarios", [])[:4]:
                if isinstance(scenario, dict):
                    lines.append(
                        f"  - {matrix.get('matrix_id', 'matrix')}/{scenario.get('scenario_id', 'scenario')}: "
                        f"{scenario.get('status', 'UNKNOWN')} at {scenario.get('deployment_stage', 'declared-stage')}"
                    )
    state_transitions = payload.get("state_transitions", {}) if isinstance(payload.get("state_transitions"), dict) else {}
    if state_transitions.get("active_count", 0) or state_transitions.get("evaluations"):
        lines.append(
            f"Persisted-state transitions: {state_transitions.get('status', 'UNKNOWN')} · "
            f"{state_transitions.get('confirmed_count', 0)} confirmed · "
            f"{state_transitions.get('partial_plan_count', 0)} partial plan(s) · "
            f"{state_transitions.get('coverage_confirmed_count', 0)}/{state_transitions.get('coverage_required_count', 0)} coverage requirement(s) confirmed · "
            f"{state_transitions.get('rollback_availability_confirmed_count', 0)} rollback-available · "
            f"{state_transitions.get('rollback_drill_confirmed_count', 0)} rollback-drilled · "
            f"{state_transitions.get('not_run_count', 0)} not run"
        )
        for plan in state_transitions.get("evaluations", [])[:4]:
            if not isinstance(plan, dict):
                continue
            for transition in plan.get("transitions", [])[:4]:
                if isinstance(transition, dict):
                    rollback = transition.get("rollback", {}) if isinstance(transition.get("rollback"), dict) else {}
                    lines.append(
                        f"  - {plan.get('plan_id', 'plan')}/{transition.get('transition_id', 'transition')}: "
                        f"{transition.get('status', 'UNKNOWN')} · rollback {rollback.get('status', 'NOT_REQUIRED')}"
                    )
    capabilities = payload.get("capabilities", []) if isinstance(payload.get("capabilities"), list) else []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        lines.append(
            f"Capability {capability.get('capability_id', 'unknown')}: {capability.get('status', 'UNKNOWN')}"
            + (f" ({capability.get('mode')})" if capability.get('mode') else "")
        )
        if capability.get("reason"):
            lines.append(f"  - {capability.get('reason')}")
        budget = capability.get("budget", {}) if isinstance(capability.get("budget"), dict) else {}
        if budget:
            observed_units = (
                f"{capability.get('recipe_count', 0)} recipe(s)"
                if capability.get("capability_id") == "runtime-proof"
                else f"{budget.get('descriptors_observed', 0)} descriptor(s)"
            )
            lines.append(
                f"  - Budget: {budget.get('duration_ms', 0)} ms used; {observed_units}; "
                f"exhausted: {'yes' if budget.get('budget_exhausted') else 'no'}"
            )
        if capability.get("capability_id") == "runtime-proof":
            counts = capability.get("counts", {}) if isinstance(capability.get("counts"), dict) else {}
            lines.append(
                f"  - HTTP recipes: {counts.get('PASS', 0)} passed; {counts.get('FAIL', 0)} failed; {counts.get('BLOCKED', 0)} blocked"
            )
            lines.append("  - JavaScript, visual layout, authentication, and database state: not proven")
        lines.append("  - Repairs: prohibited")
    bundle = payload.get("continuity_bundle", {}) if isinstance(payload.get("continuity_bundle"), dict) else {}
    if bundle:
        binding = bundle.get("project_binding", {}) if isinstance(bundle.get("project_binding"), dict) else {}
        lines.append(
            f"Portable continuity: {bundle.get('status', 'UNKNOWN')} · {Path(str(bundle.get('bundle', ''))).name} · "
            f"project package {binding.get('status', 'UNBOUND')}"
        )
        lines.append("  - Includes eight state files and bounded evidence manifests; excludes raw logs and project source")
    session = payload.get("session_close", {}) if isinstance(payload.get("session_close"), dict) else {}
    if session:
        lines.extend([
            f"Session Close: {session.get('status', 'UNKNOWN')} ({session.get('session_type', 'unknown')})",
            f"Exact next action: {session.get('next_action', {}).get('text', '')}",
            f"Continuity event: {session.get('event_id', '')}",
        ])
        preflight = session.get("preflight", {}) if isinstance(session.get("preflight"), dict) else {}
        if preflight:
            lines.append(f"Session Close preflight: {preflight.get('status', 'UNKNOWN')}")
            for warning in preflight.get("warnings", [])[:4]:
                lines.append(f"  - WARNING: {warning}")
    lines.extend([
        f"Native selection: {plan.get('native_gate_policy', {}).get('selection', 'unknown')}",
        "Full log: .forge/ledger.jsonl",
        "Excludes: unproven runtime, browser, database, deployment, migration, and release assurance.",
        (
            "This is not a project-level or release-level PASS."
            if payload.get("status") == "PASS"
            else "No project-level or release-level PASS was produced."
        ),
    ])
    return "\n".join(lines).rstrip() + "\n"

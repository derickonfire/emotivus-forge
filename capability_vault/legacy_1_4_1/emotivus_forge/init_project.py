from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import run_audit
from .baseline import write_baseline
from .config import CONFIG_NAME, default_config, save_config
from .detect import detect_project
from .graph import build_graph
from .brief import build_brief
from .project_memory import initialize_project_memory
from .provenance import build_source_completeness, classify_workspace, infer_runtime_requirements, infer_work_scope, packaging_policy_contradictions, write_provenance_reports
from .doctor import run_doctor
from .lab import plan_labs
from .runtime_contracts import initialize_runtime_contracts, plan_runtime_proof
from .reporting import write_audit_reports
from .setup import apply_setup, collect_guided_answers, write_setup_artifacts
from .tool_migration import absorb_tools, quarantine_replacements, scan_existing_tools, write_tool_reports
from .utils import write_json


def _write_agent_file(project_root: Path) -> Path:
    path = project_root / "FORGE-AGENT.md"
    if path.exists():
        return path
    path.write_text(
        """# Emotivus Forge Agent Contract

Forge is a separate project-intelligence and assurance layer. Do not merge Forge Core into application runtime directories.

Before changing code:
- Run `python3 Emotivus-Forge/forge.py adopt .`.
- Read `.forge/AI-BOOTSTRAP-PROMPT.md`, `.emotivus-forge.json`, the latest project context packet, and the host project's named source-of-truth files.
- Keep first-contact existing-tool handling in audit mode.

During implementation:
- Use the Project Passport and durable records for bounded work and deliberate product pivots.
- Run `forge resume . --budget compact` before loading unrelated history.
- Run `forge check . --profile quick` at save points and `forge check . --profile section` after completed work areas.
- Never weaken, suppress, delete, or baseline a blocker merely to obtain a pass.
- Preserve existing host tests, migration harnesses, browser suites, security tools, and CI unless reviewed evidence supports a change.
- Convert confirmed defects into reviewed durable contracts; prefer behavior, security, data integrity, and compatibility over exact source shape.

Before release:
- Run `forge ship .` for production delivery. Use advanced delivery commands only for specialized internal handoffs or portable-state export.
- Never deploy Forge Core, `.forge/`, Forge configuration, credentials, tests, or internal evidence.

Forge remembers, measures, enforces, and evidences. The active AI or human interprets and repairs. Conserve tokens through minimum sufficient verified context, never through missing critical information.
""",
        encoding="utf-8",
    )
    return path


def _write_deployignore(project_root: Path, forge_folder: str) -> Path:
    path = project_root / ".deployignore"
    additions = [
        forge_folder + "/", ".forge/", ".emotivus-forge.json", "FORGE-AGENT.md", "Forge-State*.zip",
        "tests/", "docs/", ".git/", "*.log", "*.tmp", "*.bak", ".DS_Store", "Thumbs.db",
    ]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else ["# Emotivus Forge deployment exclusions", ""]
    for item in additions:
        if item not in lines:
            lines.append(item)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path




def _write_host_isolation(project_root: Path, forge_folder: str) -> dict[str, str]:
    state = project_root / ".forge"
    payload = {
        "schema": 1,
        "mode": "host",
        "forge_paths": [forge_folder, ".forge"],
        "recommended_exclusions": {
            "documentation_scanners": [forge_folder + "/", ".forge/"],
            "test_discovery": [forge_folder + "/tests/", ".forge/"],
            "static_analysis": [forge_folder + "/", ".forge/"],
            "secret_scanners": [forge_folder + "/tests/fixtures/", ".forge/"],
            "deployment_packagers": [forge_folder + "/", ".forge/", ".emotivus-forge.json", "FORGE-AGENT.md", "Forge-State*.zip"],
        },
        "note": "Forge excludes itself from Forge host-mode scans automatically. Mature host tools may still require their own scoped exclusions; prove those exclusions still fail on a deliberate host violation.",
    }
    json_path = state / "HOST-SCANNER-EXCLUSIONS.json"
    write_json(json_path, payload)
    md_path = state / "HOST-SCANNER-EXCLUSIONS.md"
    md_path.write_text(
        "# Host Scanner Isolation\n\n"
        "Forge Core remains a separate assurance layer and is automatically excluded from Forge host-mode scanning. "
        "Existing project scanners may still walk the entire tree. Exclude the Forge installation and `.forge/` from host documentation, test-discovery, static-analysis, license, and packaging scans where appropriate.\n\n"
        "Do not add a broad skip without proving the host checker still fails on a deliberate real violation.\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}


def _write_ai_bootstrap(project_root: Path, forge_folder: str) -> Path:
    path = project_root / ".forge" / "AI-BOOTSTRAP-PROMPT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# AI Bootstrap Prompt — Emotivus Forge

```text
Treat `{forge_folder}/` as a separate project-intelligence and assurance layer. Do not merge it into application source.

Before editing:
1. Confirm the project and `{forge_folder}/` are fully extracted.
2. Read `{forge_folder}/docs/AI-AGENT-INSTRUCTIONS.md` and `FORGE-AGENT.md` when present.
3. Run `python3 {forge_folder}/forge.py adopt .`. Use `--guided` or a supplied answers file when initialization is required.
4. Keep existing-tool handling in audit mode until recommendations are reviewed.
5. Run `python3 {forge_folder}/forge.py resume . --budget compact` and read only the canonical sources relevant to the current request.
6. Resolve Forge blockers and environment or layout problems before coding. Do not weaken a rule merely to proceed.
7. Keep the Project Passport objective, decisions, risks, and next action current as work changes.
8. Use the Resume packet and Check during work. Run Ship for fresh release verification, confidentiality scanning, and packaging.
9. Use `python3 {forge_folder}/forge.py help --project .` whenever the correct next command is unclear.
10. Preserve the latest Project Passport and Resume packet before handing the project to another session.

Forge gathers and preserves deterministic evidence. Use active reasoning to interpret and repair the project. Conserve tokens through precise context, never by omitting critical facts.
```
"""
    path.write_text(content, encoding="utf-8")
    return path


def _write_learning_seed(project_root: Path, config: dict[str, Any]) -> Path:
    learn = config.get("learn", {})
    contracts_path = project_root / learn.get("contracts_path", ".forge/policies/learned-contracts.json")
    if not contracts_path.exists():
        write_json(contracts_path, {"schema": 1, "updated_utc": "", "contracts": []})
    proposals = project_root / learn.get("proposals_dir", ".forge/learn/proposals")
    proposals.mkdir(parents=True, exist_ok=True)
    example = proposals.parent / "defect-input.example.json"
    if not example.exists():
        write_json(example, {
            "title": "Example confirmed defect",
            "invariant": "Describe the behavior that must remain true after the fix.",
            "symptom": "Describe what users or systems observed.",
            "root_cause": "Describe the verified technical cause.",
            "fix": "Describe the approved correction.",
            "severity": "error",
            "category": "behavior",
            "scope": "project",
            "affected_paths": ["path/to/file"],
            "gate": "section",
            "regression": {
                "kind": "file_contains",
                "path": "path/to/file",
                "text": "durable contract token",
                "regex": False
            }
        })
    return contracts_path


def _write_initialization_summary(project_root: Path, config: dict[str, Any], audit: dict[str, Any], tools: dict[str, Any], absorbed_count: int, quarantined_count: int, graph: dict[str, Any], lab_plan: dict[str, Any]) -> Path:
    path = project_root / ".forge" / "INITIALIZATION-SUMMARY.md"
    counts = audit.get("counts", {})
    versioning = config.get("versioning", {})
    lines = [
        "# Emotivus Forge Initialization", "",
        f"- Project: {config.get('project', {}).get('name', project_root.name)}",
        f"- Project kind: {config.get('project', {}).get('kind', '')}",
        f"- Adapters: {', '.join(config.get('adapters', [])) or 'none yet'}",
        f"- Assurance preset: {config.get('project', {}).get('risk_preset', '')}",
        f"- Deployment target: {config.get('project', {}).get('deployment_target', '')}",
        f"- Version baseline: {versioning.get('baseline_version', '')}",
        f"- Version target: {versioning.get('target_version', '')}",
        f"- Active blockers/errors: {counts.get('blocker', 0) + counts.get('error', 0)}",
        f"- Existing tools detected: {len(tools.get('candidates', []))}",
        f"- Existing commands adopted: {absorbed_count}",
        f"- Overlapping tools quarantined: {quarantined_count}",
        f"- Forge Graph nodes/edges: {graph.get('summary', {}).get('nodes', 0)} / {graph.get('summary', {}).get('edges', 0)}",
        f"- Forge Lab recipes: {len(lab_plan.get('recipes', []))}", "",
        "## Review first", "",
        "1. `.forge/reports/initial-audit-classified.txt`",
        "2. `.forge/graph/project-graph.md`",
        "3. `.forge/lab/lab-plan.md`",
        "4. `.forge/runtime/runtime-proof-plan.md`",
        "5. `.forge/reports/tool-inventory.txt`",
        "6. `.forge/TOOL-MIGRATION-PLAN.md`",
        "7. `.emotivus-forge.json`", "",
        "Blockers and errors were never baselined. Forge Learn proposals are never activated automatically. Quarantined tools remain recoverable through `.forge/legacy-tools/RESTORE-MANIFEST.json`.", "",
        "## Commands", "", "```bash",
        "python3 Emotivus-Forge/forge.py resume . --budget compact",
        "python3 Emotivus-Forge/forge.py check . --changed path/to/file --profile quick",
        "python3 Emotivus-Forge/forge.py check . --profile quick --fresh",
        "python3 Emotivus-Forge/forge.py check . --profile section --fresh",
        "python3 Emotivus-Forge/forge.py help --project .",
        "python3 Emotivus-Forge/forge.py ship . --dry-run",
        "python3 Emotivus-Forge/forge.py ship .", "```",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def initialize_project(
    project_root: Path,
    forge_root: Path,
    *,
    name: str = "",
    force: bool = False,
    setup_answers: dict[str, Any] | None = None,
    guided: bool = False,
    tool_action: str = "",
    confirm_tool_removal: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    config_path = project_root / CONFIG_NAME
    if config_path.exists() and not force:
        raise RuntimeError(f"{CONFIG_NAME} already exists; use --force only when deliberately regenerating it")

    detection = detect_project(project_root, forge_root)
    try:
        forge_folder = forge_root.relative_to(project_root).parts[0]
    except (ValueError, IndexError):
        forge_folder = forge_root.name
    config = default_config(name.strip() or project_root.name, detection, forge_folder)
    answers = dict(setup_answers or {})
    if name.strip():
        answers["project_name"] = name.strip()
    if tool_action:
        answers["existing_tools"] = tool_action
    if guided:
        guided_answers = collect_guided_answers(config, detection, project_root)
        guided_answers.update({key: value for key, value in answers.items() if value not in (None, "")})
        answers = guided_answers
    config, decisions = apply_setup(config, detection, project_root, answers)

    inventory = scan_existing_tools(project_root, forge_root)
    absorbed: list[dict[str, Any]] = []
    quarantine: dict[str, Any] | None = None
    mode = decisions["existing_tools"]
    if mode in {"adopt", "absorb", "remove"}:
        absorbed = absorb_tools(config, inventory)
    if mode == "remove":
        quarantine = quarantine_replacements(project_root, inventory, confirmed=confirm_tool_removal)
        config["tool_migration"]["quarantined"] = list(quarantine.get("entries", []))
    config["tool_migration"]["inventory_counts"] = inventory.get("counts", {})

    workspace = classify_workspace(project_root, forge_root)
    runtime_requirements = infer_runtime_requirements(project_root)
    scope = infer_work_scope(project_root, config.get("continuity", {}).get("objective_sources", []))
    source_completeness = build_source_completeness(project_root, forge_root, workspace)
    config["workspace"] = workspace
    config["source_completeness"] = {
        "manifest": ".forge/provenance/development-source-manifest.json",
        "status": source_completeness["status"],
        "reconstruction": source_completeness["reconstruction_evidence"],
    }
    config["project"]["workspace_classification"] = workspace["classification"]
    config["runtime_requirements"] = runtime_requirements
    for runtime_name, item in runtime_requirements.items():
        expected = str(item.get("expected", "")).strip()
        if expected and runtime_name in config.get("runtime", {}) and not str(config["runtime"][runtime_name].get("expected", "")).strip():
            config["runtime"][runtime_name]["expected"] = expected
    config["work"] = {"mode": scope["mode"], "coding_allowed": scope["coding_allowed"], "scope_source": scope["source"], "reason": scope["reason"], "confidence": scope["confidence"]}
    config["project_memory"]["mode"] = scope["mode"]
    config["project_memory"]["scope"] = {"coding_allowed": scope["coding_allowed"], "source": scope["source"], "reason": scope["reason"]}
    config["packaging_policy"] = {"contradictions": packaging_policy_contradictions(project_root, config)}

    save_config(project_root, config)
    _write_deployignore(project_root, forge_folder)
    _write_agent_file(project_root)
    isolation_artifacts = _write_host_isolation(project_root, forge_folder) if not config.get("project", {}).get("self_hosting") else {}
    bootstrap_prompt = _write_ai_bootstrap(project_root, forge_folder)
    tool_reports = write_tool_reports(project_root, inventory, absorbed, quarantine)
    setup_artifacts = write_setup_artifacts(project_root, config, decisions)
    provenance_artifacts = write_provenance_reports(project_root, workspace, runtime_requirements, scope, source_completeness)
    contracts_path = _write_learning_seed(project_root, config)
    project_memory = initialize_project_memory(project_root, config)
    graph = build_graph(project_root, forge_root, config, write=bool(config.get("graph", {}).get("enabled", True)))
    lab_plan = plan_labs(project_root, config, write=bool(config.get("lab", {}).get("enabled", True)))
    runtime_contracts_path = initialize_runtime_contracts(project_root, config)
    runtime_plan = plan_runtime_proof(project_root, forge_root, config, write=bool(config.get("runtime_proof", {}).get("enabled", True)))

    audit = run_audit(project_root, forge_root, config, use_baseline=False)
    reports_dir = project_root / config["paths"]["reports"]
    write_audit_reports(reports_dir / "initial-audit.json", audit)
    baseline_path = project_root / config["paths"]["baseline"]
    baseline_items = [type("FindingView", (), item) for item in audit["findings"]] if decisions["baseline_existing_advisories"] else []
    write_baseline(baseline_path, baseline_items, audit["tree_fingerprint"])
    final_audit = run_audit(project_root, forge_root, config, use_baseline=True)
    write_audit_reports(reports_dir / "initial-audit-classified.json", final_audit)
    quarantined_count = len((quarantine or {}).get("entries", []))
    summary_path = _write_initialization_summary(project_root, config, final_audit, inventory, len(absorbed), quarantined_count, graph, lab_plan)
    doctor = run_doctor(project_root, forge_root, config, write=True)
    brief = build_brief(project_root, forge_root, config, write=True)

    return {
        "status": "INITIALIZED",
        "project": config["project"]["name"],
        "config": str(config_path),
        "adapters": config["adapters"],
        "preset": decisions["preset"],
        "tool_action": mode,
        "tool_candidates": len(inventory.get("candidates", [])),
        "absorbed_commands": len(absorbed),
        "quarantined_files": quarantined_count,
        "graph_nodes": graph.get("summary", {}).get("nodes", 0),
        "graph_edges": graph.get("summary", {}).get("edges", 0),
        "learned_contracts": str(contracts_path),
        "project_memory": project_memory,
        "lab_recipes": len(lab_plan.get("recipes", [])),
        "runtime_contracts": len(runtime_plan.get("contracts", [])),
        "runtime_contracts_path": str(runtime_contracts_path),
        "runtime_gaps": len(runtime_plan.get("gaps", [])),
        "baseline_count": len([item for item in audit["findings"] if item["severity"] in {"warning", "info"}]) if decisions["baseline_existing_advisories"] else 0,
        "active_blockers": final_audit["counts"]["blocker"] + final_audit["counts"]["error"],
        "initial_audit_status": final_audit["status"],
        "summary": str(summary_path),
        "setup_artifacts": setup_artifacts,
        "provenance_artifacts": provenance_artifacts,
        "workspace_classification": workspace["classification"],
        "work_mode": scope["mode"],
        "coding_allowed": scope["coding_allowed"],
        "tool_reports": tool_reports,
        "isolation_artifacts": isolation_artifacts,
        "ai_bootstrap_prompt": str(bootstrap_prompt),
        "doctor_status": doctor["status"],
        "brief": str(project_root / ".forge" / "brief" / "brief.md"),
    }

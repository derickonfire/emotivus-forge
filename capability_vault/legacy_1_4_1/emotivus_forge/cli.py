from __future__ import annotations

import argparse
import copy
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from . import __version__
from .audit import run_audit
from .brief import build_brief
from .doctor import run_doctor
from .evidence import list_evidence, show_evidence
from .remediation import remediation_action
from .baseline import write_baseline
from .config import load_config, save_config
from .detect import detect_project
from .graph import analyze_impact, build_graph
from .guardrails import guardrail_action
from .lab import plan_labs, run_lab
from .runtime_contracts import plan_runtime_proof, run_runtime_contract
from .learn import approve_learning, list_learning, propose_learning, reject_learning
from .mirror import run_mirror
from .init_project import initialize_project
from .package import build_package
from .delivery import build_internal_delivery
from .release_proof import CLAIM_LEVELS, build_release_proof, build_final_delivery, record_delivery_artifact, validate_delivery_provenance
from .reporting import write_audit_reports
from .runner import run_profile
from .setup import load_answers
from .state import adopt_state, export_state, inspect_state
from .tool_migration import absorb_tools, quarantine_replacements, scan_existing_tools, write_tool_reports
from .update import update_action
from .ci_bridge import ci_action
from .confidentiality import scan_confidentiality
from .utils import resolve_command
from .provenance import build_source_completeness, classify_workspace, infer_runtime_requirements, infer_work_scope, packaging_policy_contradictions, write_provenance_reports
from .project_memory import (
    build_context_packet, initialize_project_memory, ledger_action, plan_action,
    pivot_action, project_status,
)
from .passport import build_project_passport, build_resume_packet, check_project, ship_project
from .guidance import build_help_guide, render_help_guide
from .startup import run_forge, render_run_summary
from .selftest import run_self_tests


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2))


def _format_self_test_summary(payload: dict[str, object]) -> str:
    status = str(payload.get("status", "UNKNOWN"))
    if status == "LIST":
        shards = payload.get("shards", [])
        rows = [f"FORGE SELF-TEST SHARDS — {payload.get('total', 0)}"]
        if isinstance(shards, list):
            rows.extend(f"  {item.get('shard_id', 'unknown')}" for item in shards if isinstance(item, dict))
        return "\n".join(rows)
    completed = int(payload.get("completed_count", 0) or 0)
    total = int(payload.get("total_count", 0) or 0)
    remaining = int(payload.get("remaining_count", max(0, total - completed)) or 0)
    rows = [f"FORGE SELF-TEST: {status} — {completed}/{total} completed; {remaining} remaining"]
    halt = str(payload.get("halt_reason", "") or "")
    if halt:
        rows.append(f"Reason: {halt}")
    resume = str(payload.get("resume_command", "") or "")
    if resume:
        rows.append(f"Resume: {resume}")
    scope = payload.get("scope", {})
    if isinstance(scope, dict) and scope.get("id") not in {None, "", "full"}:
        rows.append(f"Scope: {scope.get('id')}")
    results = payload.get("results", [])
    if isinstance(results, list):
        blocking = next((item for item in reversed(results) if isinstance(item, dict) and item.get("status") not in {"PASS"}), None)
        if blocking:
            rows.append(f"Blocked at: {blocking.get('shard_id', 'unknown')} ({blocking.get('status', 'UNKNOWN')})")
            output = str(blocking.get("output", "") or "").splitlines()
            if output:
                rows.append("Last output:")
                rows.extend(f"  {line}" for line in output[-12:])
    rows.append("Evidence: self/.runtime/self-test-latest.json")
    return "\n".join(rows)


def _run_self_tests(
    forge_root: Path,
    *,
    resume: bool = False,
    fresh: bool = False,
    only: list[str] | None = None,
    budget_seconds: int = 0,
    per_shard_timeout: int | None = None,
    list_only: bool = False,
    json_output: bool = False,
) -> int:
    payload = run_self_tests(
        forge_root, resume=resume, fresh=fresh, only=only,
        budget_seconds=budget_seconds, per_shard_timeout=per_shard_timeout,
        list_only=list_only,
    )
    if json_output:
        _print_json(payload)
    else:
        print(_format_self_test_summary(payload))
    if payload["status"] in {"PASS", "LIST"}:
        return 0
    if payload["status"] == "INCOMPLETE":
        return 3
    return 1


def _serve_docs(forge_root: Path, port: int) -> int:
    docs_root = forge_root / "docs-site"
    if not (docs_root / "index.html").is_file():
        raise RuntimeError("docs-site/index.html is missing")
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=str(docs_root), **kwargs)
    with socketserver.TCPServer(("127.0.0.1", port), handler) as server:
        print(f"Emotivus Forge documentation: http://127.0.0.1:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nDocumentation server stopped.")
    return 0


def _tool_action(value: str) -> str:
    """Normalize the legacy absorb verb to the ecosystem-oriented adopt mode."""
    return "adopt" if value == "absorb" else value


def _advanced_catalog() -> dict[str, object]:
    """Describe the expert surface without making it part of normal onboarding."""
    return {
        "schema": 1,
        "status": "PASS",
        "message": "Forge has five public commands: Help, Adopt, Resume, Check, and Ship.",
        "categories": [
            {
                "name": "Project diagnostics",
                "commands": [
                    "forge graph <project>",
                    "forge doctor <project>",
                    "forge project record <project> --action list",
                    "forge project context <project> --mode task",
                ],
            },
            {
                "name": "Assurance diagnostics",
                "commands": [
                    "forge lab <project> --action plan",
                    "forge release-proof <project>",
                    "forge evidence <project> --action list",
                    "forge confidentiality <project>",
                ],
            },
            {
                "name": "Forge maintenance",
                "commands": [
                    "forge docs --serve",
                    "forge update <project> --action preview --source <forge.zip>",
                    "forge self-test --resume --budget-seconds 30",
                ],
            },
        ],
        "compatibility": {
            "note": "1.3.x command routes remain callable during the 1.4 transition but are not part of the public product model.",
            "routes": ["understand", "change", "prove", "init", "verify", "package"],
        },
    }


def _print_advanced_catalog(payload: dict[str, object]) -> None:
    print("Forge advanced controls")
    print("Normal work uses: help, adopt, resume, check, ship.\n")
    for category in payload["categories"]:  # type: ignore[index]
        print(f"{category['name']}:" )  # type: ignore[index]
        for command in category["commands"]:  # type: ignore[index]
            print(f"  {command}")
        print()
    print("Compatibility routes remain available during the 1.4 transition.")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["run"]
    command_name = os.environ.get("FORGE_INVOKED_AS", "forge").strip() or "forge"
    parser = argparse.ArgumentParser(
        prog=command_name,
        description="Five commands. One Project Passport. Any coding AI.",
        epilog=f"Start with `{command_name} help`. Normal workflow: help → adopt → resume → check → ship.",
    )
    parser.add_argument("--version", action="version", version=f"Emotivus Forge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="{help,adopt,resume,check,ship}")

    # Natural-language launcher behind “Run Forge.” It is hidden because the
    # public product still has exactly five commands: Help, Adopt, Resume, Check, Ship.
    p_run = sub.add_parser("run", help=argparse.SUPPRESS)
    p_run.add_argument("project", nargs="?", default=".")
    p_run.add_argument("--profile", choices=("quick",), default="quick")
    p_run.add_argument("--budget", choices=("compact", "standard", "full"), default="compact")
    p_run.add_argument("--json", action="store_true")

    # Five public commands: one guided entry point and four project outcomes.
    p_help = sub.add_parser("help", help="Explain Forge, inspect current state, and recommend the exact next command")
    p_help.add_argument("topic", nargs="?", choices=("adopt", "resume", "check", "ship", "advanced"), default=None)
    p_help.add_argument("--project", default=".", help="Project to inspect when no topic is supplied")
    p_help.add_argument("--json", action="store_true", help="Print machine-readable guidance")

    # Four public outcomes. Existing named capabilities remain available as advanced compatibility commands.
    p_adopt = sub.add_parser("adopt", help="Build or refresh the Project Passport for an existing project")
    p_adopt.add_argument("project", nargs="?", default=".")
    p_adopt.add_argument("--name", default="")
    p_adopt.add_argument("--guided", action="store_true")
    p_adopt.add_argument("--answers", default="")
    p_adopt.add_argument("--preset", choices=("prototype", "balanced", "strict", "legacy"), default="")
    p_adopt.add_argument("--deployment", choices=("auto", "zip", "cpanel", "container", "static", "none"), default="")
    p_adopt.add_argument("--versioning", choices=("auto", "semver", "calendar", "none"), default="")
    p_adopt.add_argument("--state", default="", help="Optional Forge-State.zip to adopt before building the passport")
    p_adopt.add_argument("--force-state", action="store_true")

    p_resume_public = sub.add_parser("resume", help="Create the minimum sufficient continuation packet for the next AI or human")
    p_resume_public.add_argument("project", nargs="?", default=".")
    p_resume_public.add_argument("--budget", choices=("compact", "standard", "full"), default="compact")
    p_resume_public.add_argument("--refresh", action="store_true", help="Refresh the project graph before creating the packet")

    p_ship = sub.add_parser("ship", help="Run release proof and build the exact deployment ZIP with a Proof Card")
    p_ship.add_argument("project", nargs="?", default=".")
    p_ship.add_argument("--output", default="")
    p_ship.add_argument("--dry-run", action="store_true")
    p_ship.add_argument("--development", action="store_true", help="Allow an explicitly non-production development artifact")

    # Compatibility cores. They remain callable for 1.3.x users but are deliberately
    # absent from the normal interface and marketing model.
    p_understand = sub.add_parser("understand", help=argparse.SUPPRESS)
    understand_sub = p_understand.add_subparsers(dest="understand_area", required=True, metavar="{start,brief,graph,ledger,context,doctor}")
    pu_start = understand_sub.add_parser("start", help="Initialize or resume a project safely")
    pu_start.add_argument("project", nargs="?", default=".")
    pu_start.add_argument("--name", default="")
    pu_start.add_argument("--guided", action="store_true")
    pu_start.add_argument("--answers", default="")
    pu_start.add_argument("--preset", choices=("prototype", "balanced", "strict", "legacy"), default="")
    pu_start.add_argument("--deployment", choices=("auto", "zip", "cpanel", "container", "static", "none"), default="")
    pu_start.add_argument("--versioning", choices=("auto", "semver", "calendar", "none"), default="")
    pu_start.add_argument("--state", default="", help="Optional Forge-State.zip to inspect and adopt before resuming")
    pu_start.add_argument("--force-state", action="store_true")
    pu_brief = understand_sub.add_parser("brief", help="Show the current objective, last green state, risks, and next commands")
    pu_brief.add_argument("project", nargs="?", default=".")
    pu_brief.add_argument("--budget", choices=("compact", "standard", "full"), default="compact")
    pu_graph = understand_sub.add_parser("graph", help="Map project architecture, dependencies, routes, tests, and integrations")
    pu_graph.add_argument("project", nargs="?", default=".")
    pu_ledger = understand_sub.add_parser("ledger", help="Maintain durable decisions, requirements, defects, artifacts, and release records")
    pu_ledger.add_argument("project", nargs="?", default=".")
    pu_ledger.add_argument("--action", choices=("add", "list", "show", "accept", "reject", "resolve", "supersede", "retire"), default="list")
    pu_ledger.add_argument("--input", default="")
    pu_ledger.add_argument("--id", default="")
    pu_ledger.add_argument("--reason", default="")
    pu_context = understand_sub.add_parser("context", help="Generate minimum sufficient verified context for an AI or human")
    pu_context.add_argument("project", nargs="?", default=".")
    pu_context.add_argument("--mode", choices=("cold", "task", "subsystem", "failure", "release", "pivot"), default="cold")
    pu_context.add_argument("--budget", choices=("compact", "standard", "full"), default="standard")
    pu_context.add_argument("--plan", default="")
    pu_context.add_argument("--subsystem", default="")
    pu_context.add_argument("--failure", default="")
    pu_context.add_argument("--pivot", default="")
    pu_doctor = understand_sub.add_parser("doctor", help="Inspect environment, runtime, services, layout, and reversible repair proposals")
    pu_doctor.add_argument("project", nargs="?", default=".")
    pu_doctor.add_argument("--action", choices=("inspect", "propose", "list", "apply", "rollback"), default="inspect")
    pu_doctor.add_argument("--id", default="")
    pu_doctor.add_argument("--transaction", default="")
    pu_doctor.add_argument("--confirm", action="store_true")

    p_change = sub.add_parser("change", help=argparse.SUPPRESS)
    change_sub = p_change.add_subparsers(dest="change_area", required=True, metavar="{plan,impact,pivot,learn,guardrail}")
    pc_plan = change_sub.add_parser("plan", help="Create and manage bounded implementation plans and quality targets")
    pc_plan.add_argument("project", nargs="?", default=".")
    pc_plan.add_argument("--action", choices=("create", "update", "list", "show", "activate", "complete", "supersede", "cancel"), default="list")
    pc_plan.add_argument("--input", default="")
    pc_plan.add_argument("--id", default="")
    pc_plan.add_argument("--reason", default="")
    pc_impact = change_sub.add_parser("impact", help="Calculate blast radius, targeted tests, and live verification needs")
    pc_impact.add_argument("project", nargs="?", default=".")
    pc_impact.add_argument("--changed", action="append", required=True)
    pc_impact.add_argument("--depth", type=int, default=None)
    pc_pivot = change_sub.add_parser("pivot", help="Manage major architectural or product changes without freezing obsolete implementation")
    pc_pivot.add_argument("project", nargs="?", default=".")
    pc_pivot.add_argument("--action", choices=("create", "list", "show", "assess", "classify", "activate", "mode", "complete", "restore", "cancel"), default="list")
    pc_pivot.add_argument("--input", default="")
    pc_pivot.add_argument("--id", default="")
    pc_pivot.add_argument("--reason", default="")
    pc_pivot.add_argument("--mode", choices=("exploration", "transition", "development", "release"), default="")
    pc_pivot.add_argument("--confirm", action="store_true", help="Confirm restoration of pre-pivot assurance state")
    pc_learn = change_sub.add_parser("learn", help="Turn confirmed defects into reviewed permanent project memory")
    pc_learn.add_argument("project", nargs="?", default=".")
    pc_learn.add_argument("--action", choices=("propose", "approve", "reject", "list"), default="list")
    pc_learn.add_argument("--input", default="")
    pc_learn.add_argument("--id", default="")
    pc_learn.add_argument("--reason", default="")
    pc_guard = change_sub.add_parser("guardrail", help="Propose and approve narrow structural protections from resolved anomalies")
    pc_guard.add_argument("project", nargs="?", default=".")
    pc_guard.add_argument("--action", choices=("propose", "approve", "reject", "list"), default="list")
    pc_guard.add_argument("--input", default="")
    pc_guard.add_argument("--id", default="")
    pc_guard.add_argument("--reason", default="")

    p_prove = sub.add_parser("prove", help=argparse.SUPPRESS)
    prove_sub = p_prove.add_subparsers(dest="prove_area", required=True, metavar="{gate,coverage,lab,evidence,deliver,mirror,ci,confidentiality}")
    pp_gate = prove_sub.add_parser("gate", help="Run Quick, Section, or Release proof")
    pp_gate.add_argument("project", nargs="?", default=".")
    pp_gate.add_argument("--level", choices=("quick", "section", "release"), default="quick")
    pp_gate.add_argument("--resume", action="store_true")
    pp_gate.add_argument("--fresh", action="store_true")
    pp_gate.add_argument("--only", action="append", default=[])
    pp_gate.add_argument("--allow-anomaly", action="append", default=[])
    pp_coverage = prove_sub.add_parser("coverage", help="Inspect the joined release claim, surface coverage, environments, states, and delivery provenance")
    pp_coverage.add_argument("project", nargs="?", default=".")
    pp_lab = prove_sub.add_parser("lab", help="Plan or run disposable behavioral verification environments")
    pp_lab.add_argument("project", nargs="?", default=".")
    pp_lab.add_argument("--action", choices=("plan", "list", "run", "contracts", "contract"), default="plan")
    pp_lab.add_argument("--recipe", default="")
    pp_lab.add_argument("--contract", default="")
    pp_lab.add_argument("--preserve", action="store_true")
    pp_evidence = prove_sub.add_parser("evidence", help="List or inspect Gate, execution-history, and failure evidence")
    pp_evidence.add_argument("project", nargs="?", default=".")
    pp_evidence.add_argument("--action", choices=("list", "show"), default="list")
    pp_evidence.add_argument("--id", default="")
    pp_deliver = prove_sub.add_parser("deliver", help="Create a deployment, internal working delivery, or portable state archive")
    pp_deliver.add_argument("project", nargs="?", default=".")
    pp_deliver.add_argument("--profile", choices=("deployment", "internal", "state", "handoff"), default="deployment")
    pp_deliver.add_argument("--dry-run", action="store_true")
    pp_deliver.add_argument("--development", action="store_true")
    pp_deliver.add_argument("--output", default="")
    pp_deliver.add_argument("--action", choices=("build", "record", "verify"), default="build")
    pp_deliver.add_argument("--input", default="", help="JSON provenance record for handoff artifact registration")
    pp_mirror = prove_sub.add_parser("mirror", help="Run Forge's mandatory self-hosted production certification")
    pp_mirror.add_argument("project", nargs="?", default=".")
    pp_mirror.add_argument("--baseline", required=True)
    pp_mirror.add_argument("--release", required=True)
    pp_mirror.add_argument("--output", default="")
    pp_mirror.add_argument("--public-output", default="")
    pp_mirror.add_argument("--changed", action="append", default=[])
    pp_mirror.add_argument("--preserve-workspace", action="store_true")
    pp_ci = prove_sub.add_parser("ci", help="Preview or write a CI bridge that invokes Forge proof")
    pp_ci.add_argument("project", nargs="?", default=".")
    pp_ci.add_argument("--action", choices=("preview", "write"), default="preview")
    pp_ci.add_argument("--provider", choices=("github", "gitlab", "shell", "cpanel"), required=True)
    pp_ci.add_argument("--force", action="store_true")
    pp_conf = prove_sub.add_parser("confidentiality", help="Verify metadata-only boundaries and scan for secret or private-project contamination")
    pp_conf.add_argument("project", nargs="?", default=".")
    pp_conf.add_argument("--policy", default="", help="Optional external denylist policy; the policy is never copied into Forge state or packages")



    # Lean public workflow. Detailed legacy commands remain available as advanced aliases.
    p_start = sub.add_parser("start", help=argparse.SUPPRESS)
    p_start.add_argument("project", nargs="?", default=".")
    p_start.add_argument("--name", default="")
    p_start.add_argument("--guided", action="store_true")
    p_start.add_argument("--answers", default="")
    p_start.add_argument("--preset", choices=("prototype", "balanced", "strict", "legacy"), default="")
    p_start.add_argument("--deployment", choices=("auto", "zip", "cpanel", "container", "static", "none"), default="")
    p_start.add_argument("--versioning", choices=("auto", "semver", "calendar", "none"), default="")
    p_start.add_argument("--state", default="", help="Optional Forge-State.zip to inspect and adopt before resuming")
    p_start.add_argument("--force-state", action="store_true")

    p_project = sub.add_parser("project", help=argparse.SUPPRESS)
    project_sub = p_project.add_subparsers(dest="project_area", required=True, metavar="{status,plan,record,context,pivot}")
    pp_status = project_sub.add_parser("status", help="Show a compact, token-aware current project packet")
    pp_status.add_argument("project", nargs="?", default=".")
    pp_status.add_argument("--budget", choices=("compact", "standard", "full"), default="compact")
    pp_plan = project_sub.add_parser("plan", help="Create and manage bounded implementation plans")
    pp_plan.add_argument("project", nargs="?", default=".")
    pp_plan.add_argument("--action", choices=("create", "list", "show", "activate", "complete", "supersede", "cancel"), default="list")
    pp_plan.add_argument("--input", default="")
    pp_plan.add_argument("--id", default="")
    pp_plan.add_argument("--reason", default="")
    pp_record = project_sub.add_parser("record", help="Maintain durable decisions, requirements, defects, and source-of-truth records")
    pp_record.add_argument("project", nargs="?", default=".")
    pp_record.add_argument("--action", choices=("add", "list", "show", "accept", "reject", "resolve", "supersede", "retire"), default="list")
    pp_record.add_argument("--input", default="")
    pp_record.add_argument("--id", default="")
    pp_record.add_argument("--reason", default="")
    pp_context = project_sub.add_parser("context", help="Generate minimum sufficient verified context for an AI or human")
    pp_context.add_argument("project", nargs="?", default=".")
    pp_context.add_argument("--mode", choices=("cold", "task", "subsystem", "failure", "release", "pivot"), default="cold")
    pp_context.add_argument("--budget", choices=("compact", "standard", "full"), default="standard")
    pp_context.add_argument("--plan", default="")
    pp_context.add_argument("--subsystem", default="")
    pp_context.add_argument("--failure", default="")
    pp_context.add_argument("--pivot", default="")
    pp_pivot = project_sub.add_parser("pivot", help="Manage major changes without freezing obsolete architecture")
    pp_pivot.add_argument("project", nargs="?", default=".")
    pp_pivot.add_argument("--action", choices=("create", "list", "show", "assess", "classify", "activate", "complete", "cancel"), default="list")
    pp_pivot.add_argument("--input", default="")
    pp_pivot.add_argument("--id", default="")
    pp_pivot.add_argument("--reason", default="")

    p_verify = sub.add_parser("verify", help=argparse.SUPPRESS)
    p_verify.add_argument("project", nargs="?", default=".")
    p_verify.add_argument("--level", choices=("quick", "section", "release"), default="quick")
    p_verify.add_argument("--resume", action="store_true")
    p_verify.add_argument("--fresh", action="store_true")
    p_verify.add_argument("--only", action="append", default=[])
    p_verify.add_argument("--allow-anomaly", action="append", default=[])

    p_deliver = sub.add_parser("deliver", help=argparse.SUPPRESS)
    p_deliver.add_argument("project", nargs="?", default=".")
    p_deliver.add_argument("--profile", choices=("deployment", "internal", "state", "handoff"), default="deployment")
    p_deliver.add_argument("--dry-run", action="store_true")
    p_deliver.add_argument("--development", action="store_true")
    p_deliver.add_argument("--output", default="")
    p_deliver.add_argument("--action", choices=("build", "record", "verify"), default="build")
    p_deliver.add_argument("--input", default="")

    p_maintain = sub.add_parser("maintain", help=argparse.SUPPRESS)
    maintain_sub = p_maintain.add_subparsers(dest="maintain_area", required=True, metavar="{doctor,update,ci,tools}")
    pm_doctor = maintain_sub.add_parser("doctor", help="Inspect or apply one reviewed reversible environment repair")
    pm_doctor.add_argument("project", nargs="?", default=".")
    pm_doctor.add_argument("--action", choices=("inspect", "propose", "list", "apply", "rollback"), default="inspect")
    pm_doctor.add_argument("--id", default="")
    pm_doctor.add_argument("--transaction", default="")
    pm_doctor.add_argument("--confirm", action="store_true")
    pm_update = maintain_sub.add_parser("update", help="Preview, apply, or roll back a Forge update")
    pm_update.add_argument("project", nargs="?", default=".")
    pm_update.add_argument("--action", choices=("preview", "apply", "rollback"), default="preview")
    pm_update.add_argument("--source", default="")
    pm_update.add_argument("--transaction", default="")
    pm_update.add_argument("--post-profile", choices=("quick", "section", "release"), default="")
    pm_ci = maintain_sub.add_parser("ci", help="Preview or write a CI bridge")
    pm_ci.add_argument("project", nargs="?", default=".")
    pm_ci.add_argument("--action", choices=("preview", "write"), default="preview")
    pm_ci.add_argument("--provider", choices=("github", "gitlab", "shell", "cpanel"), required=True)
    pm_ci.add_argument("--force", action="store_true")
    pm_tools = maintain_sub.add_parser("tools", help="Audit, adopt, or reversibly quarantine existing tool ecosystems")
    pm_tools.add_argument("project", nargs="?", default=".")
    pm_tools.add_argument("--action", choices=("audit", "adopt", "absorb", "remove"), default="audit")
    pm_tools.add_argument("--confirm-tool-removal", action="store_true")

    p_init = sub.add_parser("init", help=argparse.SUPPRESS)
    p_init.add_argument("project", nargs="?", default=".")
    p_init.add_argument("--name", default="")
    p_init.add_argument("--guided", action="store_true", help="Run the interactive initial configuration")
    p_init.add_argument("--answers", default="", help="JSON file containing initial-run answers")
    p_init.add_argument("--preset", choices=("prototype", "balanced", "strict", "legacy"), default="")
    p_init.add_argument("--deployment", choices=("auto", "zip", "cpanel", "container", "static", "none"), default="")
    p_init.add_argument("--versioning", choices=("auto", "semver", "calendar", "none"), default="")
    p_init.add_argument("--tool-action", choices=("audit", "adopt", "absorb", "remove"), default="")
    p_init.add_argument("--confirm-tool-removal", action="store_true", help="Allow eligible overlapping tools to be moved into reversible quarantine")
    p_init.add_argument("--force", action="store_true")

    p_detect = sub.add_parser("detect", help=argparse.SUPPRESS)
    p_detect.add_argument("project", nargs="?", default=".")

    p_brief = sub.add_parser("brief", help=argparse.SUPPRESS)
    p_brief.add_argument("project", nargs="?", default=".")

    p_doctor = sub.add_parser("doctor", help=argparse.SUPPRESS)
    p_doctor.add_argument("project", nargs="?", default=".")
    p_doctor.add_argument("--action", choices=("inspect", "propose", "list", "apply", "rollback"), default="inspect")
    p_doctor.add_argument("--id", default="", help="Remediation proposal ID")
    p_doctor.add_argument("--transaction", default="", help="Remediation transaction ID")
    p_doctor.add_argument("--confirm", action="store_true", help="Confirm one reviewed reversible repair")

    p_update = sub.add_parser("update", help=argparse.SUPPRESS)
    p_update.add_argument("project", nargs="?", default=".")
    p_update.add_argument("--action", choices=("preview", "apply", "rollback"), default="preview")
    p_update.add_argument("--source", default="", help="Incoming Emotivus Forge distribution ZIP")
    p_update.add_argument("--transaction", default="", help="Backup transaction ID for rollback")
    p_update.add_argument("--post-profile", choices=("quick", "section", "release"), default="")

    p_ci = sub.add_parser("ci", help=argparse.SUPPRESS)
    p_ci.add_argument("project", nargs="?", default=".")
    p_ci.add_argument("--action", choices=("preview", "write"), default="preview")
    p_ci.add_argument("--provider", choices=("github", "gitlab", "shell", "cpanel"), required=True)
    p_ci.add_argument("--force", action="store_true", help="Back up and replace an existing generated target after review")

    p_state = sub.add_parser("state", help=argparse.SUPPRESS)
    p_state.add_argument("project", nargs="?", default=".")
    p_state.add_argument("--action", choices=("export", "inspect", "adopt"), default="export")
    p_state.add_argument("--input", default="")
    p_state.add_argument("--output", default="")
    p_state.add_argument("--force", action="store_true")

    p_graph = sub.add_parser("graph", help=argparse.SUPPRESS)
    p_graph.add_argument("project", nargs="?", default=".")

    p_impact = sub.add_parser("impact", help=argparse.SUPPRESS)
    p_impact.add_argument("project", nargs="?", default=".")
    p_impact.add_argument("--changed", action="append", default=[])
    p_impact.add_argument("--depth", type=int, default=None)

    p_learn = sub.add_parser("learn", help=argparse.SUPPRESS)
    p_learn.add_argument("project", nargs="?", default=".")
    p_learn.add_argument("--action", choices=("propose", "approve", "reject", "list"), default="list")
    p_learn.add_argument("--input", default="")
    p_learn.add_argument("--id", default="")
    p_learn.add_argument("--reason", default="")

    p_guardrail = sub.add_parser("guardrail", help=argparse.SUPPRESS)
    p_guardrail.add_argument("project", nargs="?", default=".")
    p_guardrail.add_argument("--action", choices=("propose", "approve", "reject", "list"), default="list")
    p_guardrail.add_argument("--input", default="")
    p_guardrail.add_argument("--id", default="")
    p_guardrail.add_argument("--reason", default="")

    p_lab = sub.add_parser("lab", help=argparse.SUPPRESS)
    p_lab.add_argument("project", nargs="?", default=".")
    p_lab.add_argument("--action", choices=("plan", "run", "list", "contracts", "contract"), default="plan")
    p_lab.add_argument("--recipe", default="")
    p_lab.add_argument("--contract", default="")
    p_lab.add_argument("--preserve", action="store_true")

    p_tools = sub.add_parser("tools", help=argparse.SUPPRESS)
    p_tools.add_argument("project", nargs="?", default=".")
    p_tools.add_argument("--action", choices=("audit", "adopt", "absorb", "remove"), default="audit")
    p_tools.add_argument("--confirm-tool-removal", action="store_true")

    p_confidentiality = sub.add_parser("confidentiality", help=argparse.SUPPRESS)
    p_confidentiality.add_argument("project", nargs="?", default=".")
    p_confidentiality.add_argument("--policy", default="")

    p_audit = sub.add_parser("audit", help=argparse.SUPPRESS)
    p_audit.add_argument("project", nargs="?", default=".")
    p_audit.add_argument("--no-baseline", action="store_true")

    p_baseline = sub.add_parser("baseline", help=argparse.SUPPRESS)
    p_baseline.add_argument("project", nargs="?", default=".")

    p_check = sub.add_parser("check", help="Detect changes, calculate impact, invalidate stale evidence, and run the required proof")
    p_check.add_argument("project", nargs="?", default=".")
    p_check.add_argument("--profile", choices=("quick", "section", "release", "toolset"), default="quick")
    p_check.add_argument("--resume", action="store_true")
    p_check.add_argument("--fresh", action="store_true")
    p_check.add_argument("--only", action="append", default=[])
    p_check.add_argument("--allow-anomaly", action="append", default=[], help="Explicitly accept one reviewed blocking anomaly by check ID")
    p_check.add_argument("--changed", action="append", default=[], help="Optional changed path when external edits are known")

    p_package = sub.add_parser("package", help=argparse.SUPPRESS)
    p_package.add_argument("project", nargs="?", default=".")
    p_package.add_argument("--profile", choices=("deployment", "internal"), default="deployment")
    p_package.add_argument("--dry-run", action="store_true")
    p_package.add_argument("--development", action="store_true", help="Explicitly allow a non-frozen development package")
    p_package.add_argument("--output", default="")

    p_mirror = sub.add_parser("mirror", help=argparse.SUPPRESS)
    p_mirror.add_argument("project", nargs="?", default=".")
    p_mirror.add_argument("--baseline", required=True, help="Previously released Forge version")
    p_mirror.add_argument("--release", required=True, help="Forge version being certified")
    p_mirror.add_argument("--output", default="")
    p_mirror.add_argument("--public-output", default="")
    p_mirror.add_argument("--changed", action="append", default=[])
    p_mirror.add_argument("--preserve-workspace", action="store_true")

    p_docs = sub.add_parser("docs", help=argparse.SUPPRESS)
    p_docs.add_argument("--serve", action="store_true")
    p_docs.add_argument("--port", type=int, default=8765)

    p_self_test = sub.add_parser("self-test", help=argparse.SUPPRESS)
    p_self_test.add_argument("--resume", action="store_true")
    p_self_test.add_argument("--fresh", action="store_true")
    p_self_test.add_argument("--only", action="append", default=[])
    p_self_test.add_argument("--budget-seconds", type=int, default=0, help="Pause cleanly after this wall-clock budget; 0 means no overall budget")
    p_self_test.add_argument("--per-shard-timeout", type=int, default=0, help="Override the timeout for each isolated test shard")
    p_self_test.add_argument("--list", action="store_true", help="List isolated test shards without running them")
    p_self_test.add_argument("--json", action="store_true", help="Print the complete machine-readable evidence payload")
    sub.add_parser("list-adapters", help=argparse.SUPPRESS)

    p_advanced = sub.add_parser("advanced", help=argparse.SUPPRESS)
    p_advanced.add_argument("--json", action="store_true", help="Print the expert command catalog as JSON")

    public_commands = {"help", "adopt", "resume", "check", "ship"}
    sub._choices_actions[:] = [action for action in sub._choices_actions if action.dest in public_commands]

    args = parser.parse_args(argv)
    forge_root = Path(__file__).resolve().parents[1]


    if args.command == "help":
        if args.topic == "advanced":
            payload = _advanced_catalog()
            if args.json:
                _print_json(payload)
            else:
                _print_advanced_catalog(payload)
            return 0
        payload = build_help_guide(Path(args.project), forge_root, topic=args.topic or "")
        if args.json:
            _print_json(payload)
        else:
            print(render_help_guide(payload), end="")
        return 0

    if args.command == "advanced":
        payload = _advanced_catalog()
        if args.json:
            _print_json(payload)
        else:
            _print_advanced_catalog(payload)
        return 0

    # Normalize the three public cores onto stable internal commands. This keeps
    # scripts and established projects compatible without exposing a bloated top level.
    if args.command == "understand":
        mapping = {
            "start": ("start", None), "brief": ("project", "status"),
            "graph": ("graph", None), "ledger": ("project", "record"),
            "context": ("project", "context"), "doctor": ("maintain", "doctor"),
        }
        args.command, area = mapping[args.understand_area]
        if args.command == "project":
            args.project_area = area
        elif args.command == "maintain":
            args.maintain_area = area
    elif args.command == "change":
        mapping = {
            "plan": ("project", "plan"), "impact": ("impact", None),
            "pivot": ("project", "pivot"), "learn": ("learn", None),
            "guardrail": ("guardrail", None),
        }
        args.command, area = mapping[args.change_area]
        if args.command == "project":
            args.project_area = area
    elif args.command == "prove":
        mapping = {
            "gate": ("verify", None), "coverage": ("release-proof", None), "lab": ("lab", None),
            "evidence": ("evidence", None), "deliver": ("deliver", None),
            "mirror": ("mirror", None), "ci": ("maintain", "ci"),
            "confidentiality": ("confidentiality", None),
        }
        args.command, area = mapping[args.prove_area]
        if args.command == "maintain":
            args.maintain_area = area
    elif args.command == "update":
        args.command = "maintain"
        args.maintain_area = "update"

    try:

        if args.command == "run":
            payload = run_forge(
                Path(args.project), forge_root,
                check_profile=args.profile, resume_budget=args.budget,
            )
            if args.json:
                _print_json(payload)
            else:
                print(render_run_summary(payload), end="")
            if payload.get("status") == "NEEDS_PROJECT":
                return 2
            return 1 if payload.get("status") == "BLOCKED" else 0

        if args.command == "adopt":
            root = Path(args.project).resolve()
            if args.state:
                inspection = inspect_state(Path(args.state))
                if inspection["status"] != "PASS":
                    _print_json(inspection)
                    return 1
                adopt_state(root, Path(args.state), force=args.force_state)
            initialized: dict[str, object] = {}
            if not (root / ".emotivus-forge.json").is_file():
                answers = load_answers(Path(args.answers)) if args.answers else {}
                for key in ("preset", "deployment", "versioning"):
                    value = getattr(args, key)
                    if value:
                        answers[key] = value
                initialized = initialize_project(
                    root, forge_root, name=args.name, setup_answers=answers,
                    guided=args.guided, tool_action="audit",
                )
            config = load_config(root)
            passport = build_project_passport(
                root, forge_root, config, refresh_graph=True, refresh_proof=True,
                checkpoint=True, checkpoint_kind="adopted",
            )
            _print_json({
                "status": "ADOPTED",
                "project": passport["identity"],
                "health": {
                    "doctor": passport["safety"]["doctor_status"],
                    "release_claim": passport["evidence"]["claim_status"],
                    "uncertainties": len(passport["uncertainties"]),
                },
                "passport": passport["output"],
                "passport_markdown": passport["markdown"],
                "initialized": bool(initialized),
                "next_action": passport["next_action"],
            })
            return 0

        if args.command == "resume":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = build_resume_packet(root, forge_root, config, budget=args.budget, refresh=args.refresh)
            _print_json({
                "status": "PASS",
                "project": payload["project"],
                "objective": payload["objective"],
                "changes": payload["changes"],
                "uncertainties": payload["uncertainties"],
                "evidence": payload["evidence"],
                "next_action": payload["next_action"],
                "output": payload["output"],
                "markdown": payload["markdown"],
                "estimated_tokens": payload["estimated_tokens"],
                "token_limit": payload["token_limit"],
                "token_efficiency": payload["token_efficiency"],
            })
            return 0

        if args.command == "check":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = check_project(
                root, forge_root, config, profile=args.profile, changed_paths=args.changed,
                fresh=args.fresh or not args.resume, resume=args.resume, only=args.only,
                allow_anomaly=args.allow_anomaly,
            )
            _print_json(payload)
            return 0 if payload["status"] == "PASS" else 1

        if args.command == "ship":
            root = Path(args.project).resolve()
            config = load_config(root)
            output = Path(args.output) if args.output else None
            payload = ship_project(
                root, forge_root, config, output=output, dry_run=args.dry_run,
                development=args.development,
            )
            _print_json(payload)
            return 0 if payload["status"] == "PASS" else 1

        if args.command == "start":
            root = Path(args.project).resolve()
            if args.state:
                inspection = inspect_state(Path(args.state))
                if inspection["status"] != "PASS":
                    _print_json(inspection)
                    return 1
                adopt_state(root, Path(args.state), force=args.force_state)
            config_path = root / ".emotivus-forge.json"
            if not config_path.is_file():
                answers = load_answers(Path(args.answers)) if args.answers else {}
                for key in ("preset", "deployment", "versioning"):
                    value = getattr(args, key)
                    if value:
                        answers[key] = value
                payload = initialize_project(
                    root, forge_root, name=args.name, setup_answers=answers,
                    guided=args.guided, tool_action="audit",
                )
                _print_json({
                    "status": payload["status"], "project": payload["project"],
                    "initial_audit_status": payload["initial_audit_status"],
                    "doctor_status": payload["doctor_status"], "brief": payload["brief"],
                    "workspace_classification": payload.get("workspace_classification", "unknown"),
                    "work_mode": payload.get("work_mode", "development"),
                    "coding_allowed": payload.get("coding_allowed", True),
                    "next": "python3 Emotivus-Forge/forge.py resume . --budget compact",
                })
                return 0 if payload["initial_audit_status"] == "PASS" else 1
            config = load_config(root)
            workspace = classify_workspace(root, forge_root)
            runtime_requirements = infer_runtime_requirements(root)
            scope = infer_work_scope(root, config.get("continuity", {}).get("objective_sources", []))
            source_completeness = build_source_completeness(root, forge_root, workspace)
            config["workspace"] = workspace
            config["project"]["workspace_classification"] = workspace["classification"]
            config["runtime_requirements"] = runtime_requirements
            config["source_completeness"] = {"manifest": ".forge/provenance/development-source-manifest.json", "status": source_completeness["status"], "reconstruction": source_completeness["reconstruction_evidence"]}
            for runtime_name, item in runtime_requirements.items():
                expected = str(item.get("expected", "")).strip()
                if expected and runtime_name in config.get("runtime", {}) and not str(config["runtime"][runtime_name].get("expected", "")).strip():
                    config["runtime"][runtime_name]["expected"] = expected
            config["work"] = {"mode": scope["mode"], "coding_allowed": scope["coding_allowed"], "scope_source": scope["source"], "reason": scope["reason"], "confidence": scope["confidence"]}
            config["project_memory"]["mode"] = scope["mode"]
            config["project_memory"]["scope"] = {"coding_allowed": scope["coding_allowed"], "source": scope["source"], "reason": scope["reason"]}
            config["packaging_policy"] = {"contradictions": packaging_policy_contradictions(root, config)}
            save_config(root, config)
            write_provenance_reports(root, workspace, runtime_requirements, scope, source_completeness)
            initialize_project_memory(root, config)
            inventory = scan_existing_tools(root, forge_root)
            reports = write_tool_reports(root, inventory, [], None)
            doctor = run_doctor(root, forge_root, config, write=True)
            build_graph(root, forge_root, config, write=True)
            status = project_status(root, forge_root, config, budget="compact")
            _print_json({
                "status": "PASS" if doctor["status"] == "PASS" else "ATTENTION",
                "project": status.get("project", {}), "counts": status.get("counts", {}),
                "doctor_status": doctor["status"], "doctor_problems": doctor.get("problems", []),
                "context": status, "tool_reports": reports,
                "workspace_classification": workspace["classification"],
                "work_mode": scope["mode"], "coding_allowed": scope["coding_allowed"],
            })
            return 0 if doctor["status"] == "PASS" else 1
        if args.command == "project":
            root = Path(args.project).resolve()
            config = load_config(root)
            initialize_project_memory(root, config)
            if args.project_area == "status":
                payload = project_status(root, forge_root, config, budget=args.budget)
            elif args.project_area == "plan":
                payload = plan_action(
                    root, forge_root, config, action=args.action,
                    input_path=Path(args.input) if args.input else None,
                    item_id=args.id, reason=args.reason,
                )
            elif args.project_area == "record":
                payload = ledger_action(
                    root, config, action=args.action,
                    input_path=Path(args.input) if args.input else None,
                    item_id=args.id, reason=args.reason,
                )
            elif args.project_area == "context":
                payload = build_context_packet(
                    root, forge_root, config, mode=args.mode, budget=args.budget,
                    plan_id=args.plan, subsystem=args.subsystem, failure_id=args.failure,
                    pivot_id=args.pivot, write=True,
                )
            else:
                payload = pivot_action(
                    root, forge_root, config, action=args.action,
                    input_path=Path(args.input) if args.input else None,
                    item_id=args.id, reason=args.reason,
                    mode=getattr(args, "mode", ""), confirmed=getattr(args, "confirm", False),
                )
                save_config(root, config)
            _print_json(payload)
            return 0
        if args.command == "verify":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = run_profile(root, forge_root, config, args.level, resume=args.resume, fresh=args.fresh, only=args.only, allow_anomaly=args.allow_anomaly)
            _print_json({"status": payload["status"], "level": args.level, "completed": payload["completed_count"], "remaining": payload["remaining_count"]})
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "deliver":
            root = Path(args.project).resolve()
            config = load_config(root)
            output = Path(args.output) if args.output else None
            if args.profile == "state":
                payload = export_state(root, config, output)
                _print_json(payload)
                return 0 if payload["status"] == "PASS" else 1
            if args.profile == "handoff":
                if args.action == "record":
                    if not args.input:
                        raise ValueError("handoff record requires --input <artifact-record.json>")
                    record = json.loads(Path(args.input).read_text(encoding="utf-8"))
                    payload = {"status": "PASS", "artifact": record_delivery_artifact(root, config, record)}
                elif args.action == "verify":
                    payload = validate_delivery_provenance(root, config)
                else:
                    configured_claim = str(config.get("release_proof", {}).get("claim_level", "source-verified"))
                    preflight_config = copy.deepcopy(config)
                    if configured_claim in CLAIM_LEVELS and CLAIM_LEVELS.index(configured_claim) >= CLAIM_LEVELS.index("delivery-verified"):
                        preflight_config.setdefault("release_proof", {})["claim_level"] = "target-environment-verified"
                    gate = run_profile(root, forge_root, preflight_config, "release", fresh=True)
                    if gate["status"] != "PASS":
                        _print_json({"status": "BLOCKED", "reason": "The pre-delivery release quality gate did not pass.", "gate": gate})
                        return 1
                    payload = build_final_delivery(root, config, output)
                    if payload.get("status") == "PASS":
                        final_gate = run_profile(root, forge_root, config, "release", fresh=True)
                        if final_gate["status"] != "PASS":
                            payload = {**payload, "status": "BLOCKED", "reason": "The final owner-facing delivery was built, but the exact final release claim did not pass.", "gate": final_gate}
                        else:
                            payload["gate"] = {"status": final_gate["status"], "claim_level": build_release_proof(root, forge_root, config, write=True)["claim_level"]}
                _print_json(payload)
                return 0 if payload.get("status") == "PASS" else 1
            gate_profile = "section" if args.profile == "internal" or args.development else "release"
            gate = run_profile(root, forge_root, config, gate_profile, fresh=True)
            if gate["status"] != "PASS":
                _print_json({"status": "BLOCKED", "reason": f"The {gate_profile} quality gate did not pass."})
                return 1
            if args.profile == "internal":
                payload = build_internal_delivery(root, forge_root, config, dry_run=args.dry_run, output=output)
            else:
                payload = build_package(root, forge_root, config, dry_run=args.dry_run, output=output)
                payload["profile"] = "deployment"
            _print_json({key: payload.get(key) for key in ("status", "profile", "dry_run", "output", "sha256", "included_count", "excluded_count", "problems")})
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "maintain":
            root = Path(args.project).resolve()
            config = load_config(root)
            if args.maintain_area == "doctor":
                payload = remediation_action(root, forge_root, config, action=args.action, proposal_id=args.id, transaction_id=args.transaction, confirmed=args.confirm)
                _print_json(payload)
                return 0 if args.action in {"propose", "list"} or payload["status"] == "PASS" else 1
            if args.maintain_area == "update":
                payload = update_action(root, forge_root, config, action=args.action, source=Path(args.source) if args.source else None, transaction_id=args.transaction, post_profile=args.post_profile or None)
                _print_json(payload)
                return 0 if payload["status"] == "PASS" else 1
            if args.maintain_area == "ci":
                payload = ci_action(root, config, action=args.action, provider=args.provider, force=args.force)
                if args.action == "write":
                    save_config(root, config)
                _print_json(payload)
                return 0 if payload["status"] == "PASS" else 1
            inventory = scan_existing_tools(root, forge_root)
            action = _tool_action(args.action)
            absorbed: list[dict[str, object]] = []
            quarantine = None
            if action in {"adopt", "remove"}:
                absorbed = absorb_tools(config, inventory)
            if action == "remove":
                quarantine = quarantine_replacements(root, inventory, confirmed=args.confirm_tool_removal)
                config.setdefault("tool_migration", {})["quarantined"] = quarantine.get("entries", [])
            config.setdefault("tool_migration", {})["mode"] = action
            config["tool_migration"]["inventory_counts"] = inventory.get("counts", {})
            save_config(root, config)
            reports = write_tool_reports(root, inventory, absorbed, quarantine)
            _print_json({"status": "PASS", "action": action, "requested_action": args.action, "counts": inventory["counts"], "absorbed": len(absorbed), "quarantined": len((quarantine or {}).get("entries", [])), "reports": reports})
            return 0
        if args.command == "init":
            answers = load_answers(Path(args.answers)) if args.answers else {}
            for key in ("preset", "deployment", "versioning"):
                value = getattr(args, key)
                if value:
                    answers[key] = value
            payload = initialize_project(
                Path(args.project), forge_root, name=args.name, force=args.force,
                setup_answers=answers, guided=args.guided, tool_action=args.tool_action,
                confirm_tool_removal=args.confirm_tool_removal,
            )
            _print_json(payload)
            return 0 if payload["initial_audit_status"] == "PASS" else 1
        if args.command == "detect":
            detection = detect_project(Path(args.project), forge_root)
            root = Path(args.project).resolve()
            _print_json({"adapters": detection.adapters, "existing_project": detection.existing_project, "identity": detection.identity, "evidence": detection.evidence, "package_scripts": detection.package_scripts, "package_manager": detection.package_manager, "detected_version": detection.detected_version, "version_path": detection.version_path, "workspace": classify_workspace(root, forge_root), "runtime_requirements": infer_runtime_requirements(root), "work_scope": infer_work_scope(root)})
            return 0
        if args.command == "brief":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = build_brief(root, forge_root, config, write=True)
            _print_json(payload)
            return 0 if payload["doctor_status"] == "PASS" else 1
        if args.command == "doctor":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = remediation_action(
                root, forge_root, config, action=args.action,
                proposal_id=args.id, transaction_id=args.transaction, confirmed=args.confirm,
            )
            _print_json(payload)
            if args.action in {"propose", "list"}:
                return 0
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "update":
            root = Path(args.project).resolve()
            config = load_config(root)
            source = Path(args.source) if args.source else None
            payload = update_action(
                root, forge_root, config, action=args.action, source=source,
                transaction_id=args.transaction, post_profile=args.post_profile or None,
            )
            _print_json(payload)
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "ci":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = ci_action(root, config, action=args.action, provider=args.provider, force=args.force)
            if args.action == "write":
                save_config(root, config)
            _print_json(payload)
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "state":
            root = Path(args.project).resolve()
            if args.action == "inspect":
                if not args.input:
                    raise ValueError("state --action inspect requires --input <Forge-State.zip>")
                payload = inspect_state(Path(args.input))
            elif args.action == "adopt":
                if not args.input:
                    raise ValueError("state --action adopt requires --input <Forge-State.zip>")
                payload = adopt_state(root, Path(args.input), force=args.force)
            else:
                config = load_config(root)
                output = Path(args.output) if args.output else None
                payload = export_state(root, config, output)
            _print_json(payload)
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "release-proof":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = build_release_proof(root, forge_root, config, write=True)
            _print_json({
                "status": payload["claim_status"],
                "claim_level": payload["claim_level"],
                "surfaces": {key: payload["surfaces"][key] for key in ("count", "covered", "uncovered")},
                "target_environment": payload["target_environment"]["status"],
                "deployment_states": payload["deployment_states"]["status"],
                "delivery_provenance": payload["delivery_provenance"]["status"],
                "problems": sorted(set(payload["problems"] + payload.get("dimension_problems", []))),
                "claim_problems": payload["problems"],
                "limitations": payload["limitations"],
                "report": str(root / config.get("release_proof", {}).get("output_dir", ".forge/release-proof") / "latest.json"),
            })
            return 0 if payload["claim_status"] == "PASS" else 1
        if args.command == "graph":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = build_graph(root, forge_root, config, write=True)
            _print_json({"status": "PASS", "nodes": payload["summary"]["nodes"], "edges": payload["summary"]["edges"], "subsystems": payload["summary"]["subsystems"], "report": str(root / config.get("graph", {}).get("output_dir", ".forge/graph") / "project-graph.json")})
            return 0
        if args.command == "impact":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = analyze_impact(root, forge_root, config, args.changed, depth=args.depth, write=True)
            _print_json({"status": "PASS", "risk": payload["risk"], "changed_paths": payload["changed_paths"], "impacted_nodes": len(payload["impacted_nodes"]), "targeted_tests": payload["targeted_tests"], "recommended_live_checks": payload["recommended_live_checks"]})
            return 0
        if args.command == "learn":
            root = Path(args.project).resolve()
            config = load_config(root)
            if args.action == "propose":
                if not args.input:
                    raise ValueError("learn --action propose requires --input <defect.json>")
                payload = propose_learning(root, forge_root, config, Path(args.input))
            elif args.action == "approve":
                if not args.id:
                    raise ValueError("learn --action approve requires --id <proposal-id>")
                payload = approve_learning(root, config, args.id)
            elif args.action == "reject":
                if not args.id:
                    raise ValueError("learn --action reject requires --id <proposal-id>")
                payload = reject_learning(root, config, args.id, args.reason)
            else:
                payload = list_learning(root, config)
            _print_json(payload)
            return 0
        if args.command == "guardrail":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = guardrail_action(
                root, forge_root, config, action=args.action,
                input_path=Path(args.input) if args.input else None,
                proposal_id=args.id, reason=args.reason,
            )
            _print_json(payload)
            return 0
        if args.command == "lab":
            root = Path(args.project).resolve()
            config = load_config(root)
            if args.action in {"plan", "list"}:
                payload = plan_labs(root, config, write=args.action == "plan")
                _print_json({"status": "PASS", "enabled": payload["enabled"], "required_profiles": payload["required_profiles"], "recipes": [{"id": item.get("id"), "name": item.get("name"), "profiles": item.get("profiles", [])} for item in payload["recipes"]]})
                return 0
            if args.action == "contracts":
                payload = plan_runtime_proof(root, forge_root, config, write=True)
                _print_json({"status": "PASS", "contracts": payload["contracts"], "gaps": payload["gaps"], "recommendations": payload["recommendations"]})
                return 0
            if args.action == "contract":
                if not args.contract:
                    raise ValueError("lab --action contract requires --contract <id>")
                payload = run_runtime_contract(root, forge_root, config, args.contract)
                _print_json({"status": payload["status"], "contract": payload["contract_id"], "kind": payload["kind"], "boundary": payload["evidence_boundary"], "problems": payload["problems"]})
                return 0 if payload["status"] == "PASS" else 1
            if not args.recipe:
                raise ValueError("lab --action run requires --recipe <id>")
            payload = run_lab(root, forge_root, config, args.recipe, preserve=args.preserve)
            _print_json({"status": payload["status"], "recipe": payload["recipe_id"], "probes": payload["probe_results"], "errors": payload["errors"], "workspace_preserved": payload["workspace_preserved"]})
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "evidence":
            root = Path(args.project).resolve()
            config = load_config(root)
            if args.action == "show":
                if not args.id:
                    raise ValueError("prove evidence --action show requires --id")
                payload = show_evidence(root, config, args.id)
            else:
                payload = list_evidence(root, config)
            _print_json(payload)
            return 0 if payload.get("status") == "PASS" else 1
        if args.command == "tools":
            root = Path(args.project).resolve()
            config = load_config(root)
            inventory = scan_existing_tools(root, forge_root)
            action = _tool_action(args.action)
            absorbed: list[dict[str, object]] = []
            quarantine = None
            if action in {"adopt", "remove"}:
                absorbed = absorb_tools(config, inventory)
            if action == "remove":
                quarantine = quarantine_replacements(root, inventory, confirmed=args.confirm_tool_removal)
                config.setdefault("tool_migration", {})["quarantined"] = quarantine.get("entries", [])
            config.setdefault("tool_migration", {})["mode"] = action
            config["tool_migration"]["inventory_counts"] = inventory.get("counts", {})
            save_config(root, config)
            reports = write_tool_reports(root, inventory, absorbed, quarantine)
            _print_json({"status": "PASS", "action": action, "requested_action": args.action, "counts": inventory["counts"], "absorbed": len(absorbed), "quarantined": len((quarantine or {}).get("entries", [])), "reports": reports})
            return 0
        if args.command == "confidentiality":
            root = Path(args.project).resolve()
            config = load_config(root) if (root / ".emotivus-forge.json").is_file() else {}
            policy_env = str(config.get("confidentiality", {}).get("private_policy_env", "FORGE_PRIVATE_POLICY")) if config else "FORGE_PRIVATE_POLICY"
            policy = args.policy or os.environ.get(policy_env, "")
            policy_path = Path(policy).resolve() if policy else None
            output_dir = str(config.get("confidentiality", {}).get("report_dir", ".forge/confidentiality")) if config else ".forge/confidentiality"
            payload = scan_confidentiality(root, policy_path=policy_path, write=True, output_dir=output_dir, scan_archives=bool(config.get("confidentiality", {}).get("scan_archives", True)) if config else True)
            _print_json({"status": payload["status"], "files_scanned": payload["files_scanned"], "archive_members_scanned": payload["archive_members_scanned"], "findings": payload["findings"], "report": payload.get("report", "")})
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "audit":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = run_audit(root, forge_root, config, use_baseline=not args.no_baseline)
            path = root / config["paths"]["reports"] / "audit.json"
            write_audit_reports(path, payload)
            _print_json({"status": payload["status"], "counts": payload["counts"], "report": str(path)})
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "baseline":
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = run_audit(root, forge_root, config, use_baseline=False)
            learned_violations = [item for item in payload.get("findings", []) if str(item.get("check_id", "")).startswith("learn.contract.")]
            if payload["counts"]["blocker"] or payload["counts"]["error"] or learned_violations:
                _print_json({"status": "BLOCKED", "reason": "Blockers, errors, and learned-contract violations cannot be baselined.", "counts": payload["counts"], "learned_contract_violations": len(learned_violations)})
                return 1
            baseline_path = root / config["paths"]["baseline"]
            baseline = write_baseline(baseline_path, [SimpleNamespace(**item) for item in payload["findings"]], payload["tree_fingerprint"])
            _print_json({"status": "PASS", "baseline": str(baseline_path), "accepted_findings": len(baseline["findings"])})
            return 0
        if args.command == "check":
            if args.profile == "toolset":
                return _run_self_tests(forge_root)
            root = Path(args.project).resolve()
            config = load_config(root)
            payload = run_profile(root, forge_root, config, args.profile, resume=args.resume, fresh=args.fresh, only=args.only, allow_anomaly=args.allow_anomaly)
            _print_json({"status": payload["status"], "profile": args.profile, "completed": payload["completed_count"], "remaining": payload["remaining_count"]})
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "package":
            root = Path(args.project).resolve()
            config = load_config(root)
            if args.profile == "internal":
                gate_profile = "section"
            else:
                gate_profile = "section" if args.development else "release"
            gate = run_profile(root, forge_root, config, gate_profile, fresh=True)
            if gate["status"] != "PASS":
                _print_json({"status": "BLOCKED", "reason": f"The {gate_profile} quality gate did not pass.", "report": str(root / config["paths"]["reports"] / f"{gate_profile}.json")})
                return 1
            output = Path(args.output) if args.output else None
            if args.profile == "internal":
                payload = build_internal_delivery(root, forge_root, config, dry_run=args.dry_run, output=output)
            else:
                payload = build_package(root, forge_root, config, dry_run=args.dry_run, output=output)
                payload["profile"] = "deployment"
            _print_json({key: payload[key] for key in ("status", "profile", "dry_run", "output", "sha256", "included_count", "excluded_count", "problems")})
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "mirror":
            output = Path(args.output) if args.output else None
            public_output = Path(args.public_output) if args.public_output else None
            payload = run_mirror(
                Path(args.project), baseline_version=args.baseline, release_version=args.release,
                output=output, public_output=public_output, changed_paths=args.changed,
                preserve_workspace=args.preserve_workspace,
            )
            _print_json({
                "status": payload["status"], "system": payload["system"],
                "baseline": payload["baseline_version"], "release": payload["release_version"],
                "archive": payload["archive"], "sha256": payload["archive_sha256"],
                "public_archive": payload.get("public_archive", ""), "public_sha256": payload.get("public_archive_sha256", ""),
                "stages": [{"id": item["id"], "status": item["status"], "summary": item.get("summary", "")} for item in payload["stages"]],
                "problems": payload["problems"],
            })
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "docs":
            if args.serve:
                return _serve_docs(forge_root, args.port)
            path = (forge_root / "docs-site" / "index.html").resolve()
            _print_json({"status": "PASS", "path": str(path), "uri": path.as_uri(), "serve": f"python3 {forge_root / 'forge.py'} docs --serve --port {args.port}"})
            return 0
        if args.command == "self-test":
            return _run_self_tests(
                forge_root, resume=args.resume, fresh=args.fresh, only=args.only,
                budget_seconds=max(0, args.budget_seconds),
                per_shard_timeout=args.per_shard_timeout or None, list_only=args.list,
                json_output=args.json,
            )
        if args.command == "list-adapters":
            adapters = []
            for path in sorted((forge_root / "adapters").glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                adapters.append({"id": data.get("id"), "name": data.get("name"), "checks": data.get("checks", [])})
            _print_json(adapters)
            return 0
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FORGE: BLOCKED — {exc}", file=sys.stderr)
        return 2
    return 2

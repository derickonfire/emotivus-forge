#!/usr/bin/env python3
"""Generate deterministic static and command-path reachability for Forge's active runtime.

The map is evidence for reduction planning. It is deliberately conservative:
static reachability over-approximates imports, while command tracing records only
functions actually executed in bounded neutral fixtures. Neither result proves a
module is safe to remove by itself.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

SCHEMA = 1
PUBLIC_COMMANDS = ("run", "help", "adopt", "resume", "check", "ship")
ENTRY_FILES = ("forge.py", "frg.py")
ALLOWED_CLASSIFICATIONS = {
    "G1_PROJECT_TRUTH",
    "G2_SESSION_CONTINUITY",
    "G3_EVOLUTION_KERNEL",
    "SHARED_RUNTIME",
    "WEB_DOCUMENTATION",
    "TESTING",
    "PACKAGING",
    "MIGRATION",
    "REFERENCE",
    "UNCLASSIFIED",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _module_name(root: Path, path: Path) -> str | None:
    relative = path.relative_to(root)
    if relative.parts[0] != "emotivus_forge" or path.suffix != ".py":
        return None
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_inventory(root: Path) -> tuple[dict[str, Path], dict[str, str]]:
    modules: dict[str, Path] = {}
    path_to_module: dict[str, str] = {}
    for path in sorted((root / "emotivus_forge").rglob("*.py")):
        module = _module_name(root, path)
        if module is None:
            continue
        modules[module] = path
        path_to_module[path.relative_to(root).as_posix()] = module
    return modules, path_to_module


def _resolve_from(current: str, level: int, name: str | None) -> str:
    package = current.split(".")[:-1]
    if level:
        trim = max(level - 1, 0)
        if trim:
            package = package[:-trim]
        prefix = package
    else:
        prefix = []
    if name:
        prefix = [*prefix, *name.split(".")]
    return ".".join(prefix)


def _internal_imports(module: str, path: Path, module_names: set[str]) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(module, node.level, node.module)
            candidates = [base]
            for alias in node.names:
                if alias.name != "*":
                    candidates.append(f"{base}.{alias.name}" if base else alias.name)
        else:
            continue
        for candidate in candidates:
            parts = candidate.split(".")
            while parts:
                value = ".".join(parts)
                if value in module_names:
                    imports.add(value)
                    break
                parts.pop()
    imports.discard(module)
    return imports


def _closure(graph: dict[str, set[str]], roots: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    queue = deque(sorted(set(roots)))
    while queue:
        module = queue.popleft()
        if module in seen:
            continue
        seen.add(module)
        queue.extend(sorted(graph.get(module, set()) - seen))
    return seen


def _classify_module(module: str) -> list[str]:
    leaf = module.rsplit(".", 1)[-1]
    values: set[str] = set()
    if module in {"emotivus_forge", "emotivus_forge.cli", "emotivus_forge.commands", "emotivus_forge.commands.public", "emotivus_forge.commands.adopt", "emotivus_forge.commands.check", "emotivus_forge.commands.common", "emotivus_forge.commands.noticing"}:
        values.add("G2_SESSION_CONTINUITY")
    if leaf in {
        "startup", "orientation", "resume", "handoff", "session_close", "session_reconciliation",
        "session_adapters", "sidecar", "recommended_prompt", "guidance", "passport", "knowledge",
    }:
        values.add("G2_SESSION_CONTINUITY")
    if leaf in {
        "project_identity", "authority_baseline", "authority_registry", "lineage", "artifact_collision",
        "attestation_kit", "evidence_kit", "external_evidence", "build_attestation", "decision_forks",
        "native_invocation", "code_orientation",
        "changes", "change_ledger", "workspace_integrity", "truth", "semantic_state", "evidence_validity",
        "external_evidence", "browser_evidence", "build_attestation", "release_authorization", "release_facts",
        "release_package", "release_distribution", "release_proof", "remote_release", "package_family",
        "provenance", "deployable_boundary", "runtime_matrix", "state_transitions", "ship_claims",
        "surface_coverage", "canonical_claims", "relationships", "ledger", "ledger_assertions",
        "check_qualification", "field_trials", "cold_session_validation", "guardrails", "project_events",
        "secret_screening", "confidentiality_boundary", "narrative_integrity", "self_currency",
    }:
        values.add("G1_PROJECT_TRUTH")
    if leaf in {
        "continuity_register", "continuity_benchmark", "bounded_retrieval", "migration_identity",
        "lifecycle", "capabilities", "third_party_intake", "presentation_profile",
    }:
        values.add("G3_EVOLUTION_KERNEL")
    if module == "emotivus_forge.core":
        values.add("SHARED_RUNTIME")
    if module == "emotivus_forge.services":
        values.add("SHARED_RUNTIME")
    if module.startswith("emotivus_forge.services"):
        if leaf in {"ship", "runtime_proof", "scoped_check", "native_gate"}:
            values.add("G1_PROJECT_TRUTH")
        if leaf == "doctor":
            values.add("G2_SESSION_CONTINUITY")
    if leaf in {"common", "models", "paths", "state", "storage", "telemetry", "notices", "native_tools"}:
        values.add("SHARED_RUNTIME")
    return sorted(values or {"UNCLASSIFIED"})


def _classify_top_level(path: str) -> list[str]:
    first = path.split("/", 1)[0]
    if first in {"emotivus_forge", "forge.py", "frg.py", "forge", "frg", "forge.cmd", "frg.cmd"}:
        return ["SHARED_RUNTIME"]
    if first in {"docs-site"}:
        return ["WEB_DOCUMENTATION"]
    if first in {"tests"}:
        return ["TESTING"]
    if first in {"tools", "release"}:
        return ["PACKAGING"]
    if first in {"examples", "policy-packs", "adapters", "THIRD-PARTY-LICENSES"}:
        return ["MIGRATION", "REFERENCE"]
    if first in {"capability_vault", "research"}:
        return ["REFERENCE"]
    if first in {"docs", "planning"} or path.endswith(".md"):
        return ["REFERENCE"]
    if first in {"FORGE-MANIFEST.json", "FORGE-PRODUCT.json", "CONFIDENTIALITY-POLICY.json", ".forgeignore", ".deployignore"}:
        return ["PACKAGING", "G1_PROJECT_TRUTH"]
    return ["UNCLASSIFIED"]


def _script_import_roots(root: Path, paths: Iterable[Path], module_names: set[str]) -> set[str]:
    roots: set[str] = set()
    for path in sorted(set(paths)):
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                candidates = [node.module, *[f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*"]]
            for candidate in candidates:
                parts = candidate.split(".")
                while parts:
                    value = ".".join(parts)
                    if value in module_names:
                        roots.add(value)
                        break
                    parts.pop()
    return roots


def _add_parent_packages(values: set[str], module_names: set[str]) -> set[str]:
    expanded = set(values)
    for value in list(values):
        parts = value.split(".")
        for index in range(1, len(parts)):
            parent = ".".join(parts[:index])
            if parent in module_names:
                expanded.add(parent)
    return expanded


def _classify_actual_top_level(name: str) -> tuple[list[str], str]:
    mapping: dict[str, tuple[list[str], str]] = {
        "emotivus_forge": (["G1_PROJECT_TRUTH", "G2_SESSION_CONTINUITY", "G3_EVOLUTION_KERNEL"], "KEEP"),
        "forge.py": (["G2_SESSION_CONTINUITY"], "KEEP"),
        "frg.py": (["G2_SESSION_CONTINUITY"], "KEEP"),
        "forge": (["G2_SESSION_CONTINUITY"], "KEEP"),
        "frg": (["G2_SESSION_CONTINUITY"], "KEEP"),
        "forge.cmd": (["G2_SESSION_CONTINUITY"], "KEEP"),
        "frg.cmd": (["G2_SESSION_CONTINUITY"], "KEEP"),
        "docs-site": (["WEB_DOCUMENTATION"], "KEEP"),
        "tests": (["TESTING"], "KEEP"),
        "tools": (["PACKAGING", "TESTING"], "KEEP"),
        "release": (["PACKAGING", "REFERENCE"], "KEEP"),
        "adapters": (["MIGRATION", "G3_EVOLUTION_KERNEL"], "KEEP"),
        "examples": (["MIGRATION", "REFERENCE"], "REFERENCE"),
        "policy-packs": (["G1_PROJECT_TRUTH", "MIGRATION"], "KEEP"),
        "capability_vault": (["REFERENCE", "MIGRATION"], "FREEZE"),
        "research": (["REFERENCE"], "REFERENCE"),
        "docs": (["REFERENCE", "WEB_DOCUMENTATION"], "REDUCE"),
        "planning": (["REFERENCE", "G3_EVOLUTION_KERNEL"], "KEEP"),
        ".forgeignore": (["G1_PROJECT_TRUTH", "PACKAGING"], "KEEP"),
        ".deployignore": (["PACKAGING"], "KEEP"),
        "FORGE-MANIFEST.json": (["G1_PROJECT_TRUTH", "PACKAGING"], "KEEP"),
        "FORGE-PRODUCT.json": (["G1_PROJECT_TRUTH", "G2_SESSION_CONTINUITY", "G3_EVOLUTION_KERNEL", "WEB_DOCUMENTATION"], "KEEP"),
        "CONFIDENTIALITY-POLICY.json": (["G1_PROJECT_TRUTH", "PACKAGING"], "KEEP"),
        "ROADMAP.md": (["G3_EVOLUTION_KERNEL", "WEB_DOCUMENTATION"], "KEEP"),
        "PROGRESS-STATUS.md": (["G3_EVOLUTION_KERNEL", "WEB_DOCUMENTATION"], "KEEP"),
        "README.md": (["WEB_DOCUMENTATION", "G2_SESSION_CONTINUITY"], "KEEP"),
        "CLAUDE.md": (["G2_SESSION_CONTINUITY", "REFERENCE"], "KEEP"),
        "RUN-FORGE.md": (["G2_SESSION_CONTINUITY", "WEB_DOCUMENTATION"], "KEEP"),
        "CHANGELOG.md": (["REFERENCE", "G3_EVOLUTION_KERNEL"], "KEEP"),
        "CERTIFICATION.md": (["G1_PROJECT_TRUTH", "REFERENCE"], "KEEP"),
        "IMPLEMENTATION-REPORT.md": (["REFERENCE"], "REFERENCE"),
        "PUBLIC-RELEASE-NOTICE.md": (["G1_PROJECT_TRUTH", "WEB_DOCUMENTATION"], "KEEP"),
        "THIRD-PARTY-LICENSES": (["REFERENCE", "MIGRATION"], "KEEP"),
        "THIRD-PARTY-NOTICES.md": (["REFERENCE", "MIGRATION"], "KEEP"),
        "LICENSE-INTERNAL.md": (["REFERENCE"], "KEEP"),
        ".gitignore": (["PACKAGING", "REFERENCE"], "KEEP"),
        ".gitattributes": (["PACKAGING", "REFERENCE"], "KEEP"),
        "FORGE-2029-VERDICT.md": (["G3_EVOLUTION_KERNEL", "REFERENCE"], "KEEP"),
        "ROADMAP-2029.md": (["G3_EVOLUTION_KERNEL", "WEB_DOCUMENTATION"], "KEEP"),
        "DEVELOPMENT-ROADMAP.md": (["G3_EVOLUTION_KERNEL", "WEB_DOCUMENTATION"], "KEEP"),
    }
    return mapping.get(name, (["UNCLASSIFIED"], "REVIEW"))


def _top_level_inventory(root: Path, public_files: set[str], development_files: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        # Version-control and Forge runtime metadata are environmental, not
        # shipped runtime surface. They are skipped exactly like `.forge` state
        # and build output rather than classified as project artifacts.
        if path.name in {".forge", "Emotivus-Forge", "__pycache__", "deploy", ".git", ".github"}:
            continue
        if path.is_dir():
            files = [item for item in path.rglob("*") if item.is_file()]
        elif path.is_file():
            files = [path]
        else:
            continue
        relatives = [item.relative_to(root).as_posix() for item in files]
        classifications, disposition = _classify_actual_top_level(path.name)
        rows.append({
            "path": path.name + ("/" if path.is_dir() else ""),
            "kind": "directory" if path.is_dir() else "file",
            "file_count": len(files),
            "bytes": sum(item.stat().st_size for item in files),
            "development": any(relative in development_files for relative in relatives),
            "public": any(relative in public_files for relative in relatives),
            "classifications": classifications,
            "disposition": disposition,
        })
    return rows


def _trace_script(root: Path, command: str) -> str:
    return r'''
import contextlib, io, json, pathlib, shutil, sys, tempfile
root=pathlib.Path(sys.argv[1]).resolve(); command=sys.argv[2]
sys.path.insert(0,str(root))
from emotivus_forge import cli
with tempfile.TemporaryDirectory(prefix='forge-reachability-') as d:
    project=pathlib.Path(d)/'project'; project.mkdir(); (project/'README.md').write_text('# Neutral fixture\n',encoding='utf-8'); (project/'ROADMAP.md').write_text('# Objective\nMap runtime reachability.\n',encoding='utf-8')
    def invoke(argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try: return cli.main(argv)
            except SystemExit as exc: return int(exc.code or 0)
    if command in {'resume','check','ship'}:
        invoke(['adopt',str(project),'--confirm-objective','Map runtime reachability.','--objective-source','ROADMAP.md','--json'])
    calls=[]
    def profile(frame,event,arg):
        if event!='call': return profile
        try: path=pathlib.Path(frame.f_code.co_filename).resolve()
        except Exception: return profile
        try: rel=path.relative_to(root).as_posix()
        except ValueError: return profile
        if rel.endswith('.py'):
            calls.append((rel,frame.f_code.co_name))
        return profile
    argv={
      'run':['run',str(project),'--json'],
      'help':['help','--project',str(project),'--json'],
      'adopt':['adopt',str(project),'--confirm-objective','Map runtime reachability.','--objective-source','ROADMAP.md','--json'],
      'resume':['resume',str(project),'--json'],
      'check':['check',str(project),'--json'],
      'ship':['ship',str(project),'--json'],
    }[command]
    sys.setprofile(profile)
    code=invoke(argv)
    sys.setprofile(None)
    unique=sorted(set(calls))
    print(json.dumps({'command':command,'exit_code':code,'calls':[{'path':p,'function':f} for p,f in unique]},sort_keys=True))
'''


def _dynamic_trace(root: Path, command: str, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-c", _trace_script(root, command), str(root), command],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or not lines:
        return {
            "command": command,
            "trace_status": "NOT_RUN",
            "process_returncode": completed.returncode,
            "reason": (completed.stderr or completed.stdout or "trace produced no result")[-1000:],
            "modules": [],
            "functions": [],
        }
    payload = json.loads(lines[-1])
    functions = payload.get("calls", [])
    modules = sorted({item["path"] for item in functions})
    return {
        "command": command,
        "trace_status": "OBSERVED",
        "command_exit_code": payload.get("exit_code"),
        "modules": modules,
        "functions": functions,
        "truth_boundary": "Observed in one bounded neutral fixture; absence from this trace does not prove dead code.",
    }


def _manifest_paths(root: Path) -> tuple[list[str], list[str]]:
    value = json.loads((root / "FORGE-MANIFEST.json").read_text(encoding="utf-8"))
    canonical = value.get("canonical_paths", [])
    public = value.get("public_paths", [])
    return [str(item) for item in canonical], [str(item) for item in public]


def _expand_manifest_files(root: Path, patterns: Iterable[str]) -> set[str]:
    files: set[str] = set()
    for raw in patterns:
        value = str(raw)
        target = root / value.rstrip("/")
        if value.endswith("/") and target.is_dir():
            files.update(path.relative_to(root).as_posix() for path in target.rglob("*") if path.is_file())
        elif target.is_file():
            files.add(target.relative_to(root).as_posix())
        else:
            files.update(path.relative_to(root).as_posix() for path in root.glob(value) if path.is_file())
    return files


def generate(root: Path, *, run_dynamic: bool = True, timeout: int = 45) -> dict[str, Any]:
    root = root.resolve()
    modules, path_to_module = _module_inventory(root)
    module_names = set(modules)
    graph = {name: _internal_imports(name, path, module_names) for name, path in modules.items()}
    cli_roots = {"emotivus_forge.cli"}
    tool_files = list((root / "tools").glob("*.py"))
    standalone_roots = _script_import_roots(root, tool_files, module_names)
    test_files = list((root / "tests").glob("test_*.py"))
    verification_roots = _script_import_roots(root, test_files, module_names)
    cli_reachable = _add_parent_packages(_closure(graph, cli_roots), module_names)
    standalone_reachable = _add_parent_packages(_closure(graph, standalone_roots), module_names)
    verification_reachable = _add_parent_packages(_closure(graph, verification_roots), module_names)
    reachable = cli_reachable | standalone_reachable | verification_reachable
    unreachable = sorted(module_names - reachable)
    command_traces = [_dynamic_trace(root, command, timeout) for command in PUBLIC_COMMANDS] if run_dynamic else []
    observed_by_command: dict[str, list[str]] = {}
    for trace in command_traces:
        observed_modules = []
        for path in trace.get("modules", []):
            module = path_to_module.get(path)
            if module:
                observed_modules.append(module)
        observed_by_command[str(trace.get("command"))] = sorted(set(observed_modules))
    command_membership: dict[str, list[str]] = defaultdict(list)
    for command, names in observed_by_command.items():
        for name in names:
            command_membership[name].append(command)
    module_rows = []
    for name, path in sorted(modules.items()):
        relative = path.relative_to(root).as_posix()
        module_rows.append({
            "module": name,
            "path": relative,
            "sha256": _sha256(path),
            "active_reachable": name in reachable,
            "ordinary_cli_reachable": name in cli_reachable,
            "standalone_tool_reachable": name in standalone_reachable,
            "verification_reachable": name in verification_reachable,
            "observed_commands": sorted(command_membership.get(name, [])),
            "imports": sorted(graph.get(name, set())),
            "classifications": _classify_module(name),
        })
    canonical, public = _manifest_paths(root)
    development_files = _expand_manifest_files(root, canonical)
    public_files = _expand_manifest_files(root, public)
    top_level_inventory = _top_level_inventory(root, public_files, development_files)
    top_level_paths = []
    for path in sorted(set(canonical) | set(public)):
        top_level_paths.append({
            "path": path,
            "development": path in canonical,
            "public": path in public,
            "classifications": _classify_top_level(path),
        })
    unclassified_modules = [row["module"] for row in module_rows if row["classifications"] == ["UNCLASSIFIED"]]
    payload = {
        "schema": SCHEMA,
        "forge_version": json.loads((root / "FORGE-PRODUCT.json").read_text(encoding="utf-8")).get("version", ""),
        "entry_files": list(ENTRY_FILES),
        "static_entry_modules": {
            "ordinary_cli": sorted(cli_roots),
            "standalone_tools": sorted(standalone_roots),
            "verification": sorted(verification_roots),
        },
        "module_count": len(module_rows),
        "static_reachable_count": len(reachable),
        "ordinary_cli_reachable_count": len(cli_reachable),
        "standalone_tool_reachable_count": len(standalone_reachable),
        "verification_reachable_count": len(verification_reachable),
        "static_unreachable_count": len(unreachable),
        "static_unreachable_modules": unreachable,
        "unclassified_modules": unclassified_modules,
        "modules": module_rows,
        "commands": command_traces,
        "manifest_paths": top_level_paths,
        "top_level_inventory": top_level_inventory,
        "unclassified_top_level_paths": [row["path"] for row in top_level_inventory if row["classifications"] == ["UNCLASSIFIED"]],
        "truth_boundary": {
            "static": "Static imports conservatively show possible module loading; dynamic imports and data-driven loading require separate review.",
            "command": "Command traces show functions executed in bounded neutral fixtures; unobserved code is not automatically removable.",
            "removal": "No module is removal-authorized solely by this report. Removal requires path classification, tests, exact package rebuild, and retained-behavior verification.",
        },
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["report_sha256"] = hashlib.sha256(canonical_json).hexdigest()
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Active Runtime Reachability and Classification",
        "",
        f"**Forge version:** {payload['forge_version']}  ",
        f"**Modules inventoried:** {payload['module_count']}  ",
        f"**Statically reachable:** {payload['static_reachable_count']}  ",
        f"**Statically unreachable:** {payload['static_unreachable_count']}  ",
        f"**Report SHA-256:** `{payload['report_sha256']}`",
        "",
        "## Command observations",
        "",
        "| Command | Trace | Exit | Modules observed |",
        "|---|---|---:|---:|",
    ]
    for trace in payload.get("commands", []):
        lines.append(f"| `{trace['command']}` | {trace['trace_status']} | {trace.get('command_exit_code','—')} | {len(trace.get('modules',[]))} |")
    lines.extend(["", "## Module classification", "", "| Module | Static | Observed commands | Classification |", "|---|---|---|---|"])
    for row in payload["modules"]:
        commands = ", ".join(row["observed_commands"]) or "—"
        classes = ", ".join(row["classifications"])
        lines.append(f"| `{row['module']}` | {'active' if row['active_reachable'] else 'unreachable'} | {commands} | {classes} |")
    lines.extend(["", "## Active top-level path classification", "", "| Path | Files | Dev | Public | Disposition | Classification |", "|---|---:|---:|---:|---|---|"])
    for row in payload["top_level_inventory"]:
        lines.append(f"| `{row['path']}` | {row['file_count']} | {'yes' if row['development'] else 'no'} | {'yes' if row['public'] else 'no'} | {row['disposition']} | {', '.join(row['classifications'])} |")
    lines.extend(["", "## Manifest path classification", "", "| Path pattern | Dev | Public | Classification |", "|---|---:|---:|---|"])
    for row in payload["manifest_paths"]:
        lines.append(f"| `{row['path']}` | {'yes' if row['development'] else 'no'} | {'yes' if row['public'] else 'no'} | {', '.join(row['classifications'])} |")
    lines.extend([
        "",
        "## Reduction decision boundary",
        "",
        "This report authorizes **classification and review only**. Static non-reachability or absence from a bounded command trace does not, by itself, authorize deletion. A removal must also preserve tests, package boundaries, migrations, historical truth, and the four-page website pipeline.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json-output", default="planning/ACTIVE-RUNTIME-REACHABILITY.json")
    parser.add_argument("--markdown-output", default="planning/ACTIVE-RUNTIME-REACHABILITY.md")
    parser.add_argument("--no-dynamic", action="store_true")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    payload = generate(root, run_dynamic=not args.no_dynamic, timeout=args.timeout)
    json_path = Path(args.json_output)
    if not json_path.is_absolute():
        json_path = root / json_path
    md_path = Path(args.markdown_output)
    if not md_path.is_absolute():
        md_path = root / md_path
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "status": "PASS" if not payload["unclassified_modules"] and not payload["unclassified_top_level_paths"] else "ATTENTION",
        "module_count": payload["module_count"],
        "static_reachable_count": payload["static_reachable_count"],
        "static_unreachable_count": payload["static_unreachable_count"],
        "unclassified_modules": payload["unclassified_modules"],
        "unclassified_top_level_paths": payload["unclassified_top_level_paths"],
        "json": str(json_path),
        "markdown": str(md_path),
        "report_sha256": payload["report_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

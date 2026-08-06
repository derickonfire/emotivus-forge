from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .detect import Detection
from .lab import default_lab_recipes
from .utils import utc_now, write_json

PRESETS = ("prototype", "balanced", "strict", "legacy")
DEPLOYMENTS = ("auto", "zip", "cpanel", "container", "static", "none")
VERSIONING_MODES = ("auto", "semver", "calendar", "none")
REQUIREMENT_MODES = ("auto", "required", "optional")
WARNING_MODES = ("allow", "fail")
BASELINE_MODES = ("auto", "yes", "no")
EXISTING_TOOL_MODES = ("audit", "adopt", "absorb", "remove")
GRAPH_MODES = ("auto", "on", "off")
LEARN_MODES = ("on", "off")
LAB_MODES = ("plan", "required", "off")
LIVE_CHECKS = (
    "browser", "accessibility", "database", "migration", "cron", "email", "sms",
    "api", "authentication", "payments", "uploads", "hosting",
)


def _choice(value: Any, allowed: tuple[str, ...], field: str, default: str) -> str:
    normalized = str(value or default).strip().lower()
    if field == "existing_tools" and normalized == "absorb":
        normalized = "adopt"
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(allowed)}")
    return normalized


def _bool_mode(value: Any, field: str, default: str = "auto") -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return _choice(value, BASELINE_MODES, field, default)


def _unique_strings(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    if not isinstance(values, list):
        raise ValueError("list-valued setup fields must be arrays or comma-separated strings")
    result: list[str] = []
    for item in values:
        value = str(item).strip().replace("\\", "/")
        if value and value not in result:
            result.append(value)
    return result


def infer_deployment(project_root: Path, detection: Detection) -> str:
    if any((project_root / item).is_file() for item in ("Dockerfile", "docker-compose.yml", "compose.yml")):
        return "container"
    if "apache" in detection.adapters:
        return "cpanel"
    if not {"php", "python", "node"}.intersection(detection.adapters) and {"javascript", "css"}.intersection(detection.adapters):
        return "static"
    return "zip"


def normalize_answers(answers: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(answers or {})
    normalized = {
        "project_name": str(raw.get("project_name", "")).strip(),
        "preset": _choice(raw.get("preset"), PRESETS, "preset", "balanced"),
        "deployment": _choice(raw.get("deployment"), DEPLOYMENTS, "deployment", "auto"),
        "versioning": _choice(raw.get("versioning"), VERSIONING_MODES, "versioning", "auto"),
        "tests": _choice(raw.get("tests"), REQUIREMENT_MODES, "tests", "auto"),
        "documentation": _choice(raw.get("documentation"), REQUIREMENT_MODES, "documentation", "auto"),
        "warnings": _choice(raw.get("warnings"), WARNING_MODES, "warnings", "allow"),
        "baseline": _bool_mode(raw.get("baseline"), "baseline", "auto"),
        "existing_tools": _choice(raw.get("existing_tools"), EXISTING_TOOL_MODES, "existing_tools", "audit"),
        "graph": _choice(raw.get("graph"), GRAPH_MODES, "graph", "auto"),
        "learn": _choice(raw.get("learn"), LEARN_MODES, "learn", "on"),
        "lab": _choice(raw.get("lab"), LAB_MODES, "lab", "plan"),
        "required_files": _unique_strings(raw.get("required_files")),
        "live_checks": _unique_strings(raw.get("live_checks")),
        "test_entry_points": _unique_strings(raw.get("test_entry_points")),
        "required_executables": _unique_strings(raw.get("required_executables")),
        "required_env": _unique_strings(raw.get("required_env")),
        "expected_layout": raw.get("expected_layout", []),
        "objective_sources": _unique_strings(raw.get("objective_sources")),
        "next_action": str(raw.get("next_action", "")).strip(),
    }
    invalid_live = sorted(set(normalized["live_checks"]) - set(LIVE_CHECKS))
    if invalid_live:
        raise ValueError(f"unsupported live checks: {', '.join(invalid_live)}")
    if normalized["expected_layout"] and not isinstance(normalized["expected_layout"], list):
        raise ValueError("expected_layout must be an array")
    custom_commands = raw.get("commands", {})
    if custom_commands and not isinstance(custom_commands, dict):
        raise ValueError("commands must be an object with quick, section, and release arrays")
    normalized["commands"] = custom_commands if isinstance(custom_commands, dict) else {}
    custom_recipes = raw.get("lab_recipes", [])
    if custom_recipes and not isinstance(custom_recipes, list):
        raise ValueError("lab_recipes must be an array")
    normalized["lab_recipes"] = custom_recipes if isinstance(custom_recipes, list) else []
    return normalized


def load_answers(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read setup answers {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("setup answers must be a JSON object")
    return normalize_answers(data)


def apply_setup(config: dict[str, Any], detection: Detection, project_root: Path, answers: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = normalize_answers(answers)
    preset = normalized["preset"]
    deployment = infer_deployment(project_root, detection) if normalized["deployment"] == "auto" else normalized["deployment"]
    if normalized["project_name"]:
        config["project"]["name"] = normalized["project_name"]
    config["project"]["risk_preset"] = preset
    config["project"]["deployment_target"] = deployment

    preset_defaults = {
        "prototype": {"tests": False, "docs": False, "warnings": False, "baseline": True, "strict_runtime": False},
        "balanced": {"tests": detection.existing_project, "docs": False, "warnings": False, "baseline": detection.existing_project, "strict_runtime": False},
        "strict": {"tests": True, "docs": True, "warnings": True, "baseline": False, "strict_runtime": True},
        "legacy": {"tests": False, "docs": False, "warnings": False, "baseline": True, "strict_runtime": False},
    }[preset]
    config["quality"]["require_tests"] = preset_defaults["tests"] if normalized["tests"] == "auto" else normalized["tests"] == "required"
    config["quality"]["require_documentation"] = preset_defaults["docs"] if normalized["documentation"] == "auto" else normalized["documentation"] == "required"
    config["quality"]["fail_on_new_warnings"] = normalized["warnings"] == "fail" or preset_defaults["warnings"]
    config["quality"]["test_entry_points"] = normalized["test_entry_points"]

    for runtime_name in ("php", "node", "python"):
        detected = runtime_name in detection.adapters or (runtime_name == "node" and "javascript" in detection.adapters)
        if runtime_name in config.get("runtime", {}):
            config["runtime"][runtime_name]["required"] = bool(detected and preset_defaults["strict_runtime"]) or bool(config["runtime"][runtime_name].get("required"))

    versioning_mode = normalized["versioning"]
    if versioning_mode == "none":
        config["versioning"]["enabled"] = False
        config["versioning"]["status"] = "development"
    else:
        config["versioning"]["enabled"] = True
        config["versioning"]["strategy"] = versioning_mode
        if versioning_mode == "semver" and config["versioning"].get("target_version") in {"", "unversioned"}:
            config["versioning"].update({"baseline_version": "0.0.0", "target_version": "0.1.0", "package_version": "0.1.0"})
        elif versioning_mode == "calendar" and config["versioning"].get("target_version") in {"", "unversioned"}:
            date_version = utc_now()[:10].replace("-", ".")
            config["versioning"].update({"baseline_version": "0.0.0", "target_version": date_version, "package_version": date_version})

    packaging = config["packaging"]
    packaging["enabled"] = deployment != "none"
    packaging["target"] = deployment
    required_files = list(packaging.get("required_files", []))
    for item in normalized["required_files"]:
        if item not in required_files:
            required_files.append(item)
    if deployment == "container" and (project_root / "Dockerfile").is_file() and "Dockerfile" not in required_files:
        required_files.append("Dockerfile")
    if deployment == "cpanel" and (project_root / ".htaccess").is_file() and ".htaccess" not in required_files:
        required_files.append(".htaccess")
    packaging["required_files"] = required_files

    for group in ("quick", "section", "release"):
        additions = normalized["commands"].get(group, []) if isinstance(normalized["commands"], dict) else []
        if not isinstance(additions, list):
            raise ValueError(f"commands.{group} must be an array")
        existing_ids = {str(item.get("id")) for item in config.get("commands", {}).get(group, []) if isinstance(item, dict)}
        for item in additions:
            if not isinstance(item, dict) or not isinstance(item.get("command"), list) or not item.get("command"):
                raise ValueError(f"commands.{group} entries require an id and non-empty command array")
            check_id = str(item.get("id", "")).strip()
            if not check_id:
                raise ValueError(f"commands.{group} entries require a non-empty id")
            if check_id not in existing_ids:
                capabilities = [str(value) for value in item.get("capabilities", [])] if isinstance(item.get("capabilities", []), list) else []
                config["commands"][group].append({
                    "id": check_id, "command": [str(value) for value in item["command"]],
                    "timeout": int(item.get("timeout", 300)), "capabilities": capabilities,
                    "test_entry_point": bool(item.get("test_entry_point", "tests" in capabilities)),
                })
                existing_ids.add(check_id)

    graph_mode = normalized["graph"]
    config["graph"]["enabled"] = graph_mode != "off"
    config["learn"]["enabled"] = normalized["learn"] == "on"
    lab_mode = normalized["lab"]
    config["lab"]["enabled"] = lab_mode != "off"
    inferred_recipes = default_lab_recipes(project_root, detection.adapters) if config["lab"]["enabled"] else []
    config["lab"]["recipes"] = inferred_recipes + [item for item in normalized["lab_recipes"] if isinstance(item, dict)]
    config["lab"]["required_profiles"] = ["release"] if lab_mode == "required" else []
    if lab_mode == "required":
        for recipe in config["lab"]["recipes"]:
            profiles = list(recipe.get("profiles", []))
            if "release" not in profiles:
                profiles.append("release")
            recipe["profiles"] = profiles

    baseline_existing = preset_defaults["baseline"] if normalized["baseline"] == "auto" else normalized["baseline"] == "yes"
    configured_utc = utc_now()
    config["initialization"] = {"configured_utc": configured_utc, "preset": preset, "baseline_existing_advisories": baseline_existing, "answers_schema": 3}
    config["verification"] = {"live_checks": normalized["live_checks"], "static_limit_notice": True}
    config["tool_migration"] = {"mode": normalized["existing_tools"], "absorbed": [], "ecosystems": [], "quarantined": []}
    config.setdefault("environment", {}).update({
        "required_executables": normalized["required_executables"],
        "required_env": normalized["required_env"],
        "expected_layout": normalized["expected_layout"],
    })
    if normalized["objective_sources"]:
        config.setdefault("continuity", {})["objective_sources"] = normalized["objective_sources"]
    config.setdefault("continuity", {})["next_action"] = normalized["next_action"]
    decisions = {
        "schema": 3,
        "configured_utc": configured_utc,
        "project_name": config["project"]["name"],
        "existing_project": detection.existing_project,
        "detected_identity": detection.identity,
        "detected_adapters": list(detection.adapters),
        "preset": preset,
        "deployment": deployment,
        "versioning": versioning_mode,
        "tests_required": config["quality"]["require_tests"],
        "documentation_required": config["quality"]["require_documentation"],
        "fail_on_new_warnings": config["quality"]["fail_on_new_warnings"],
        "baseline_existing_advisories": baseline_existing,
        "existing_tools": normalized["existing_tools"],
        "graph": graph_mode,
        "learn": normalized["learn"],
        "lab": lab_mode,
        "lab_recipes": [item.get("id") for item in config["lab"]["recipes"]],
        "required_files": required_files,
        "live_checks": normalized["live_checks"],
        "test_entry_points": normalized["test_entry_points"],
        "required_executables": normalized["required_executables"],
        "required_env": normalized["required_env"],
        "expected_layout": normalized["expected_layout"],
        "objective_sources": config.get("continuity", {}).get("objective_sources", []),
        "next_action": normalized["next_action"],
    }
    return config, decisions


def _ask_choice(prompt: str, choices: tuple[str, ...], default: str, input_fn: Callable[[str], str]) -> str:
    display = "/".join(choices)
    while True:
        answer = input_fn(f"{prompt} [{display}] ({default}): ").strip().lower()
        value = answer or default
        if value in choices:
            return value
        print(f"Choose one of: {', '.join(choices)}")


def _ask_csv(prompt: str, default: list[str], input_fn: Callable[[str], str]) -> list[str]:
    suffix = ", ".join(default) if default else "none"
    answer = input_fn(f"{prompt} (comma-separated; default: {suffix}): ").strip()
    return default if not answer else _unique_strings(answer)


def collect_guided_answers(config: dict[str, Any], detection: Detection, project_root: Path, input_fn: Callable[[str], str] = input) -> dict[str, Any]:
    detected_deployment = infer_deployment(project_root, detection)
    default_name = str(config.get("project", {}).get("name", project_root.name))
    name = input_fn(f"Project name ({default_name}): ").strip() or default_name
    preset = _ask_choice("Assurance preset", PRESETS, "balanced", input_fn)
    deployment = _ask_choice("Deployment target", DEPLOYMENTS, detected_deployment, input_fn)
    versioning = _ask_choice("Versioning strategy", VERSIONING_MODES, "auto", input_fn)
    tests = _ask_choice("Tests", REQUIREMENT_MODES, "auto", input_fn)
    documentation = _ask_choice("Documentation", REQUIREMENT_MODES, "auto", input_fn)
    warnings = _ask_choice("New warnings", WARNING_MODES, "fail" if preset == "strict" else "allow", input_fn)
    baseline = _ask_choice("Baseline inherited warnings/info", BASELINE_MODES, "no" if preset == "strict" else "auto", input_fn)
    existing_tools = _ask_choice("Existing development tools", EXISTING_TOOL_MODES, "audit", input_fn)
    graph = _ask_choice("Forge Graph architecture mapping", GRAPH_MODES, "auto", input_fn)
    learn = _ask_choice("Forge Learn defect memory", LEARN_MODES, "on", input_fn)
    lab = _ask_choice("Forge Lab disposable verification", LAB_MODES, "plan", input_fn)
    required_files = _ask_csv("Required files in every deployment package", [], input_fn)
    live_checks = _ask_csv("Live systems Forge should place on the verification checklist", [], input_fn)
    test_entry_points = _ask_csv("Non-conventional test entry points", [], input_fn)
    required_executables = _ask_csv("Additional required executables", [], input_fn)
    required_env = _ask_csv("Required environment-variable names (never values)", [], input_fn)
    expected_layout = _ask_csv("Required files or sibling paths for the working layout", [], input_fn)
    next_action = input_fn("Declared next action (optional): ").strip()
    return normalize_answers({
        "project_name": name, "preset": preset, "deployment": deployment, "versioning": versioning,
        "tests": tests, "documentation": documentation, "warnings": warnings, "baseline": baseline,
        "existing_tools": existing_tools, "graph": graph, "learn": learn, "lab": lab,
        "required_files": required_files, "live_checks": live_checks,
        "test_entry_points": test_entry_points, "required_executables": required_executables,
        "required_env": required_env, "expected_layout": expected_layout, "next_action": next_action,
    })


def write_setup_artifacts(project_root: Path, config: dict[str, Any], decisions: dict[str, Any]) -> dict[str, str]:
    state = project_root / ".forge"
    state.mkdir(parents=True, exist_ok=True)
    decisions_path = state / "SETUP-DECISIONS.json"
    write_json(decisions_path, decisions)
    plan_path = state / "INITIAL-RUN-PLAN.md"
    plan_lines = [
        "# Emotivus Forge Initial-Run Plan", "",
        f"- Project: {decisions['project_name']}",
        f"- Assurance preset: {decisions['preset']}",
        f"- Deployment target: {decisions['deployment']}",
        f"- Versioning strategy: {decisions['versioning']}",
        f"- Tests required: {'yes' if decisions['tests_required'] else 'no'}",
        f"- Documentation required: {'yes' if decisions['documentation_required'] else 'no'}",
        f"- New warnings fail the gate: {'yes' if decisions['fail_on_new_warnings'] else 'no'}",
        f"- Existing advisories baselined: {'yes' if decisions['baseline_existing_advisories'] else 'no'}",
        f"- Existing-tool action: {decisions['existing_tools']}",
        f"- Forge Graph: {decisions['graph']}",
        f"- Forge Learn: {decisions['learn']}",
        f"- Forge Lab: {decisions['lab']} ({', '.join(decisions['lab_recipes']) or 'no inferred recipes'})",
        f"- Required package files: {', '.join(decisions['required_files']) or 'none'}",
        f"- Declared test entry points: {', '.join(decisions.get('test_entry_points', [])) or 'none'}",
        f"- Required executables: {', '.join(decisions.get('required_executables', [])) or 'inferred'}",
        f"- Expected working layout: {', '.join(str(item) for item in decisions.get('expected_layout', [])) or 'none'}",
        f"- Declared next action: {decisions.get('next_action') or 'not set'}", "",
        "## First execution", "",
        "1. Review `.emotivus-forge.json`, `.forge/SETUP-DECISIONS.json`, and `.forge/TOOL-MIGRATION-PLAN.md`.",
        "2. Review `.forge/graph/project-graph.md` and correct important mapping gaps.",
        "3. Resolve every blocker and error in `.forge/reports/initial-audit-classified.txt`.",
        "4. Verify absorbed commands before relying on them; inspect quarantined files before final retirement.",
        "5. Run Forge Graph impact analysis before broad or high-risk changes.",
        "6. Convert confirmed defects into reviewed Forge Learn proposals.",
        "7. Exercise inferred Forge Lab recipes and customize them before making one a release requirement.",
        "8. Freeze release metadata, run a fresh release profile, and package only after it passes.", "",
        "```bash",
        "python3 Emotivus-Forge/forge.py resume . --budget compact",
        "python3 Emotivus-Forge/forge.py help --project .",
        "python3 Emotivus-Forge/forge.py check . --changed path/to/file --profile quick",
        "python3 Emotivus-Forge/forge.py check . --profile quick --fresh",
        "python3 Emotivus-Forge/forge.py check . --profile section --fresh",
        "python3 Emotivus-Forge/forge.py ship . --dry-run", "```",
    ]
    plan_path.write_text("\n".join(plan_lines).rstrip() + "\n", encoding="utf-8")
    live_path = state / "LIVE-VERIFICATION-CHECKLIST.md"
    labels = {
        "browser": "Verify primary user journeys in supported desktop and mobile browsers.",
        "accessibility": "Run keyboard, focus, screen-reader, contrast, and zoom checks against the deployed interface.",
        "database": "Exercise real reads, writes, transactions, constraints, backups, and rollback behavior.",
        "migration": "Run the migration on a staging copy, verify idempotency, and prove rollback or recovery.",
        "cron": "Confirm the scheduler invokes the intended command at the intended timezone and records failures.",
        "email": "Send and receive a real message; verify authentication, deliverability, templates, and failure handling.",
        "sms": "Send a real message; verify consent, sender identity, delivery callbacks, limits, and failure handling.",
        "api": "Exercise authenticated success, invalid input, timeout, rate-limit, and provider-error paths.",
        "authentication": "Verify login, logout, reset, session expiry, permissions, lockout, and recovery behavior.",
        "payments": "Use provider test mode to verify success, failure, cancellation, webhook, refund, and reconciliation paths.",
        "uploads": "Upload allowed and disallowed files; verify size, type, storage, rendering, access control, and deletion.",
        "hosting": "Verify rewrites, headers, TLS, caching, compression, permissions, logging, and environment variables on the target host.",
    }
    selected = decisions.get("live_checks", [])
    live_lines = ["# Live Verification Checklist", "", "Forge static checks and disposable labs cannot prove every behavior that depends on production hosting, external providers, real data, or scheduled infrastructure.", ""]
    if selected:
        live_lines.extend(f"- [ ] **{item}** — {labels[item]}" for item in selected)
    else:
        live_lines.append("No live systems were selected during setup. Add project-specific checks before release when applicable.")
    live_path.write_text("\n".join(live_lines).rstrip() + "\n", encoding="utf-8")
    return {"decisions": str(decisions_path), "plan": str(plan_path), "live_checklist": str(live_path)}

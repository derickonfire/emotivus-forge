from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .graph import build_graph, load_graph
from .utils import resolve_command, tree_fingerprint, utc_now, write_json

RUNTIME_CONTRACT_SCHEMA = 1
RUNTIME_EVIDENCE_SCHEMA = 1
EVIDENCE_BOUNDARIES = (
    "static-source",
    "local-process",
    "disposable-local-environment",
    "sandbox",
    "staging",
    "release-equivalent",
    "production-observed",
)

DEFAULT_REQUIRED_CATEGORIES: dict[str, tuple[str, ...]] = {
    "authorization": (
        "allowed-access",
        "denied-access",
        "direct-access-deny",
        "denied-mutation",
        "csrf",
        "explicit-deny",
        "privilege-management",
        "session-revocation",
    ),
    "migration": (
        "ordered-chain",
        "predecessor-availability",
        "first-run",
        "idempotency",
        "data-preservation",
        "package-inclusion",
    ),
    "browser": (
        "critical-journey",
        "responsive",
        "accessibility",
        "error-state",
    ),
    "api": (
        "success",
        "invalid-input",
        "authorization-failure",
        "provider-failure",
    ),
    "webhook": (
        "valid-delivery",
        "invalid-signature",
        "replay-or-idempotency",
        "provider-failure",
    ),
    "cron": (
        "scheduled-success",
        "reentry-or-idempotency",
        "failure-path",
    ),
    "email": ("success", "provider-failure", "redaction"),
    "sms": ("success", "provider-failure", "redaction"),
    "upload": (
        "valid-upload",
        "authorization-failure",
        "invalid-type",
        "size-limit",
        "path-safety",
    ),
    "provider": ("success", "authentication-failure", "timeout-or-retry", "provider-failure"),
    "resilience": (
        "target-mismatch-visible",
        "actionable-message",
        "no-secret-leak",
        "recovery-path",
        "repair-surface",
        "useful-logging",
    ),
}


def _contracts_path(project_root: Path, config: dict[str, Any]) -> Path:
    runtime = config.get("runtime_proof", {})
    return project_root / runtime.get("contracts_path", ".forge/contracts/runtime-contracts.json")


def load_runtime_contracts(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    path = _contracts_path(project_root, config)
    if not path.is_file():
        return {"schema": RUNTIME_CONTRACT_SCHEMA, "updated_utc": "", "contracts": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read runtime contracts: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != RUNTIME_CONTRACT_SCHEMA:
        raise RuntimeError("runtime contracts file has an unsupported schema")
    contracts = payload.get("contracts", [])
    if not isinstance(contracts, list):
        raise RuntimeError("runtime contracts must contain a contracts list")
    return payload


def initialize_runtime_contracts(project_root: Path, config: dict[str, Any]) -> Path:
    path = _contracts_path(project_root, config)
    if not path.exists():
        write_json(path, {"schema": RUNTIME_CONTRACT_SCHEMA, "updated_utc": "", "contracts": []})
    return path


def _boundary_rank(value: str) -> int:
    try:
        return EVIDENCE_BOUNDARIES.index(value)
    except ValueError:
        return -1


def _contract_fingerprint(contract: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _required_categories(contract: dict[str, Any]) -> list[str]:
    configured = contract.get("required_categories")
    if isinstance(configured, list):
        return [str(item) for item in configured if str(item).strip()]
    return list(DEFAULT_REQUIRED_CATEGORIES.get(str(contract.get("kind", "")), ()))


def _expected_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    value = contract.get("expected_cases", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)([\"\']?(?:client_secret|api[_-]?key|access[_-]?token|refresh[_-]?token|password|webhook_secret)[\"\']?\s*[=:]\s*[\"\']?)[^\"\'\s,;}\]]+"),
)


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if re.search(r"(?i)(secret|password|token|api[_-]?key|credential)", str(key)) and isinstance(item, str):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _redact_value(item)
        return result
    return value


def _environment_signature() -> str:
    return f"{platform.system()}|{platform.machine()}|py{platform.python_version()}"


def analyze_migration_chain(contract: dict[str, Any], project_root: Path | None = None) -> dict[str, Any]:
    migrations = [item for item in contract.get("migrations", []) if isinstance(item, dict)]
    ids = [str(item.get("id", "")) for item in migrations]
    problems: list[dict[str, str]] = []
    if not migrations:
        problems.append({"code": "migration.empty", "message": "migration contract declares no migrations"})
        return {"status": "FAIL", "order": [], "problems": problems, "provided": []}
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        problems.append({"code": "migration.ids", "message": "migration IDs must be non-empty and unique"})

    by_id = {str(item.get("id", "")): item for item in migrations if str(item.get("id", ""))}
    initial = {str(item) for item in contract.get("initial_schema", [])}
    providers: dict[str, list[str]] = defaultdict(list)
    for item in migrations:
        mid = str(item.get("id", ""))
        for produced in item.get("provides", []) if isinstance(item.get("provides"), list) else []:
            providers[str(produced)].append(mid)
    for token, owners in providers.items():
        if len(owners) > 1:
            problems.append({"code": "migration.duplicate-provider", "message": f"schema capability {token!r} is provided by multiple migrations: {', '.join(owners)}"})

    incoming: dict[str, set[str]] = {mid: set() for mid in by_id}
    outgoing: dict[str, set[str]] = {mid: set() for mid in by_id}
    for mid, item in by_id.items():
        for dep in item.get("requires_migrations", []) if isinstance(item.get("requires_migrations"), list) else []:
            dep = str(dep)
            if dep not in by_id:
                problems.append({"code": "migration.missing-predecessor", "message": f"{mid} requires missing migration {dep}"})
                continue
            incoming[mid].add(dep)
            outgoing[dep].add(mid)
        for token in item.get("requires", []) if isinstance(item.get("requires"), list) else []:
            token = str(token)
            if token in initial:
                continue
            owners = providers.get(token, [])
            if not owners:
                problems.append({"code": "migration.missing-schema-predecessor", "message": f"{mid} requires schema capability {token!r}, but no included predecessor provides it"})
                continue
            for owner in owners:
                if owner == mid:
                    problems.append({"code": "migration.self-dependency", "message": f"{mid} requires {token!r} that it also claims to provide"})
                    continue
                incoming[mid].add(owner)
                outgoing[owner].add(mid)
                provider = by_id[owner]
                if bool(item.get("included_in_delivery", True)) and not bool(provider.get("included_in_delivery", True)):
                    problems.append({"code": "migration.excluded-predecessor", "message": f"{mid} is shipped but depends on excluded predecessor {owner} for {token!r}"})
        path = str(item.get("path", ""))
        if project_root is not None and path and not (project_root / path).is_file():
            problems.append({"code": "migration.missing-file", "message": f"migration file is missing: {path}"})

    queue = deque(sorted(mid for mid, deps in incoming.items() if not deps))
    order: list[str] = []
    remaining = {mid: set(deps) for mid, deps in incoming.items()}
    while queue:
        mid = queue.popleft()
        order.append(mid)
        for child in sorted(outgoing.get(mid, set())):
            remaining[child].discard(mid)
            if not remaining[child] and child not in order and child not in queue:
                queue.append(child)
    if len(order) != len(by_id):
        cyclic = sorted(mid for mid in by_id if mid not in order)
        problems.append({"code": "migration.cycle", "message": "migration dependency cycle or unresolved predecessor: " + ", ".join(cyclic)})

    provided = sorted(initial | set(providers))
    return {"status": "PASS" if not problems else "FAIL", "order": order, "problems": problems, "provided": provided}


def validate_runtime_contract(contract: dict[str, Any], project_root: Path | None = None) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    contract_id = str(contract.get("id", "")).strip()
    kind = str(contract.get("kind", "")).strip()
    if not contract_id:
        problems.append({"code": "contract.id", "message": "runtime contract ID is required"})
    if kind not in DEFAULT_REQUIRED_CATEGORIES:
        problems.append({"code": "contract.kind", "message": f"unsupported runtime contract kind: {kind or '(empty)'}"})
    boundary = str(contract.get("evidence_boundary", "")).strip()
    if boundary not in EVIDENCE_BOUNDARIES:
        problems.append({"code": "contract.boundary", "message": f"unsupported evidence boundary: {boundary or '(empty)'}"})
    profiles = contract.get("profiles", [])
    if not isinstance(profiles, list) or any(str(item) not in {"quick", "section", "release"} for item in profiles):
        problems.append({"code": "contract.profiles", "message": "profiles must contain only quick, section, or release"})
    command = contract.get("command")
    if not isinstance(command, list) or not command:
        problems.append({"code": "contract.command", "message": "runtime contract requires a project-owned executable command"})
    required = _required_categories(contract)
    if not required:
        problems.append({"code": "contract.coverage", "message": "runtime contract must declare required evidence categories"})
    expected_cases = _expected_cases(contract)
    expected_ids = [str(item.get("id", "")).strip() for item in expected_cases]
    if any(not item for item in expected_ids) or len(expected_ids) != len(set(expected_ids)):
        problems.append({"code": "contract.expected-cases", "message": "expected_cases IDs must be non-empty and unique"})
    expected_categories = {str(item.get("category", "")) for item in expected_cases}
    unknown_expected = sorted(expected_categories - set(required))
    if unknown_expected:
        problems.append({"code": "contract.expected-category", "message": "expected_cases use categories outside required coverage: " + ", ".join(unknown_expected)})
    if kind == "authorization":
        actors = contract.get("actors", [])
        if not isinstance(actors, list) or len(actors) < 2:
            problems.append({"code": "authorization.actors", "message": "authorization proof requires at least two actor identities or roles"})
            actors = []
        actor_set = {str(item) for item in actors}
        if "privilege-management" not in required:
            problems.append({"code": "authorization.privilege-management", "message": "authorization proof must cover who may grant, revoke, or escalate privileges"})
        if "session-revocation" not in required:
            problems.append({"code": "authorization.session-revocation", "message": "authorization proof must cover immediate access loss after suspension or permission revocation"})
        if not expected_cases:
            problems.append({"code": "authorization.matrix", "message": "authorization proof requires explicit expected_cases for actor, action, target, and expected outcome"})
        for item in expected_cases:
            category = str(item.get("category", ""))
            actor = str(item.get("actor", ""))
            if category in {"privilege-management", "session-revocation", "denied-mutation", "direct-access-deny"}:
                for field in ("actor", "action", "expected"):
                    if not str(item.get(field, "")).strip():
                        problems.append({"code": "authorization.matrix-case", "message": f"authorization case {item.get('id', '(unnamed)')} requires {field}"})
            if category == "privilege-management" and not str(item.get("target", "")).strip():
                problems.append({"code": "authorization.matrix-target", "message": f"privilege-management case {item.get('id', '(unnamed)')} requires a target such as self, peer, superior, or role"})
            if actor and actor_set and actor not in actor_set:
                problems.append({"code": "authorization.matrix-actor", "message": f"authorization case {item.get('id', '(unnamed)')} uses undeclared actor {actor}"})
        for category in ("privilege-management", "session-revocation"):
            if category not in expected_categories:
                problems.append({"code": f"authorization.{category}-case", "message": f"authorization proof requires at least one explicit {category} case"})
    if kind == "migration":
        analysis = analyze_migration_chain(contract, project_root)
        problems.extend(analysis["problems"])
    if kind == "browser":
        journeys = contract.get("journeys", [])
        if not isinstance(journeys, list) or not journeys:
            problems.append({"code": "browser.journeys", "message": "browser proof requires at least one declared critical journey"})
        viewports = contract.get("viewports", [])
        if not isinstance(viewports, list) or not viewports:
            problems.append({"code": "browser.viewports", "message": "browser proof requires declared viewport coverage"})
    return problems


def _detect_runtime_tools(project_root: Path) -> dict[str, list[str]]:
    tools: dict[str, list[str]] = {"browser": [], "database": [], "service": []}
    package = project_root / "package.json"
    if package.is_file():
        try:
            payload = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        combined = json.dumps({"scripts": payload.get("scripts", {}), "dependencies": payload.get("dependencies", {}), "devDependencies": payload.get("devDependencies", {})}).lower()
        for name in ("playwright", "cypress", "puppeteer", "selenium", "webdriverio"):
            if name in combined:
                tools["browser"].append(name)
    for name, category in (
        ("playwright.config.ts", "browser"), ("playwright.config.js", "browser"),
        ("cypress.config.ts", "browser"), ("cypress.config.js", "browser"),
        ("docker-compose.yml", "database"), ("compose.yml", "database"),
        ("docker-compose.yaml", "database"), ("compose.yaml", "database"),
    ):
        if (project_root / name).is_file():
            tools[category].append(name)
    for path in project_root.glob("**/*"):
        if not path.is_file() or len(path.parts) - len(project_root.parts) > 4:
            continue
        lower = path.name.lower()
        if lower in {"phpunit.xml", "phpunit.xml.dist", "pytest.ini", "tox.ini"}:
            tools["service"].append(path.relative_to(project_root).as_posix())
    return {key: sorted(set(values)) for key, values in tools.items()}


def _detect_recommendations(graph: dict[str, Any]) -> list[dict[str, Any]]:
    facts = graph.get("facts", {}) if isinstance(graph, dict) else {}
    recommendations: list[dict[str, Any]] = []
    def add(kind: str, reason: str, priority: str = "recommended") -> None:
        recommendations.append({"kind": kind, "priority": priority, "reason": reason})
    if facts.get("authentication_flows") or facts.get("authorization_surfaces"):
        add("authorization", "Authentication, permissions, roles, or access-control surfaces were detected.", "high")
    if facts.get("database_artifacts"):
        add("migration", "Database or migration artifacts were detected.", "high")
    if facts.get("webhooks"):
        add("webhook", "Webhook handlers or signature indicators were detected.")
    if facts.get("cron_jobs"):
        add("cron", "Scheduled jobs or worker indicators were detected.")
    if facts.get("upload_flows"):
        add("upload", "Upload or multipart handling was detected.")
    if facts.get("external_hosts"):
        add("provider", "External provider hosts were detected.")
    if facts.get("routes") or facts.get("browser_surfaces"):
        add("browser", "User-facing routes or browser surfaces were detected.")
    return recommendations


def plan_runtime_proof(project_root: Path, forge_root: Path, config: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
    runtime = config.get("runtime_proof", {})
    registry = load_runtime_contracts(project_root, config)
    graph = load_graph(project_root, config) or build_graph(project_root, forge_root, config, write=True)
    contracts: list[dict[str, Any]] = []
    enabled_kinds: set[str] = set()
    for raw in registry.get("contracts", []):
        if not isinstance(raw, dict):
            continue
        problems = validate_runtime_contract(raw, project_root)
        item = {
            "id": str(raw.get("id", "")),
            "title": str(raw.get("title", raw.get("id", ""))),
            "kind": str(raw.get("kind", "")),
            "enabled": bool(raw.get("enabled", True)),
            "profiles": list(raw.get("profiles", [])) if isinstance(raw.get("profiles"), list) else [],
            "evidence_boundary": str(raw.get("evidence_boundary", "")),
            "required_categories": _required_categories(raw),
            "fingerprint": _contract_fingerprint(raw),
            "status": "READY" if not problems else "INVALID",
            "problems": problems,
        }
        contracts.append(item)
        if item["enabled"] and item["status"] == "READY":
            enabled_kinds.add(item["kind"])
    recommendations = _detect_recommendations(graph)
    gaps = [item for item in recommendations if item["kind"] not in enabled_kinds]
    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "project": config.get("project", {}).get("name", project_root.name),
        "contracts_path": str(_contracts_path(project_root, config).relative_to(project_root)),
        "contracts": contracts,
        "recommendations": recommendations,
        "gaps": gaps,
        "evidence_boundaries": list(EVIDENCE_BOUNDARIES),
        "required_kinds_by_profile": runtime.get("required_kinds_by_profile", {}),
        "minimum_boundary_by_profile": runtime.get("minimum_boundary_by_profile", {}),
        "detected_runtime_tools": _detect_runtime_tools(project_root),
    }
    if write:
        output = project_root / runtime.get("output_dir", ".forge/runtime")
        write_json(output / "runtime-proof-plan.json", payload)
        _write_plan_markdown(output / "runtime-proof-plan.md", payload)
    return payload


def _write_plan_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Forge Runtime Proof Plan", "",
        f"- Project: {payload['project']}",
        f"- Contracts: {len(payload['contracts'])}",
        f"- Uncovered recommendations: {len(payload['gaps'])}",
        f"- Browser tools detected: {', '.join(payload.get('detected_runtime_tools', {}).get('browser', [])) or 'none'}", "",
        "## Contracts", "",
    ]
    if not payload["contracts"]:
        lines.append("No runtime contracts are registered yet.")
    for item in payload["contracts"]:
        lines.extend([
            f"### {item['title']}",
            f"- ID: `{item['id']}`",
            f"- Kind: `{item['kind']}`",
            f"- Status: **{item['status']}**",
            f"- Boundary: `{item['evidence_boundary']}`",
            f"- Required categories: {', '.join(item['required_categories']) or 'none'}",
        ])
        for problem in item["problems"]:
            lines.append(f"- Problem: {problem['message']}")
        lines.append("")
    lines.extend(["## Recommended coverage", ""])
    if not payload["recommendations"]:
        lines.append("No runtime-contract category was inferred from the current Graph.")
    for item in payload["recommendations"]:
        marker = "MISSING" if item in payload["gaps"] else "COVERED"
        lines.append(f"- **{marker} / {item['kind']}** — {item['reason']}")
    lines.extend([
        "",
        "Runtime contracts are project-owned executable proofs. Forge validates coverage, evidence boundaries, contract fingerprints, and results; it does not invent application-specific behavior.",
        "Authorization contracts must prove permission administration and immediate revocation, not only route visibility. Migration contracts must prove predecessor availability, ordered execution, idempotency, data preservation, and delivery inclusion.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _parse_evidence(output: str) -> dict[str, Any] | None:
    marker = "FORGE_RUNTIME_EVIDENCE="
    for line in reversed(output.splitlines()):
        if line.startswith(marker):
            try:
                value = json.loads(line[len(marker):])
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _execute_contract_command(project_root: Path, forge_root: Path, contract: dict[str, Any], timeout: int) -> tuple[int | None, str, str]:
    command = resolve_command([str(item) for item in contract.get("command", [])], project=project_root, forge=forge_root)
    fingerprint = _contract_fingerprint(contract)
    env = {
        **os.environ,
        "FORGE_RUNTIME_CONTRACT": str(contract.get("id", "")),
        "FORGE_RUNTIME_CONTRACT_FINGERPRINT": fingerprint,
        "FORGE_RUNTIME_EVIDENCE_BOUNDARY": str(contract.get("evidence_boundary", "")),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    handle = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False, prefix="forge-runtime-", suffix=".log")
    path = handle.name
    try:
        try:
            process = subprocess.run(command, cwd=project_root, env=env, text=True, stdout=handle, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            returncode: int | None = process.returncode
            error = ""
        except subprocess.TimeoutExpired:
            returncode = None
            error = f"runtime contract exceeded timeout of {timeout} seconds"
        except OSError as exc:
            returncode = None
            error = f"could not start runtime contract command: {exc}"
        handle.flush(); handle.seek(0)
        output = handle.read()
        return returncode, output, error
    finally:
        handle.close()
        try:
            Path(path).unlink()
        except OSError:
            pass


def _validate_evidence_payload(contract: dict[str, Any], evidence: dict[str, Any] | None) -> tuple[str, list[str], dict[str, Any]]:
    problems: list[str] = []
    if evidence is None:
        return "ERROR", ["runtime contract did not emit parseable JSON evidence"], {}
    if evidence.get("schema") != RUNTIME_EVIDENCE_SCHEMA:
        problems.append("runtime evidence schema is unsupported")
    if str(evidence.get("contract_id", "")) != str(contract.get("id", "")):
        problems.append("runtime evidence contract_id does not match the declared contract")
    if str(evidence.get("kind", "")) != str(contract.get("kind", "")):
        problems.append("runtime evidence kind does not match the declared contract")
    expected_fingerprint = _contract_fingerprint(contract)
    if str(evidence.get("contract_fingerprint", "")) != expected_fingerprint:
        problems.append("runtime evidence contract_fingerprint is missing or stale")
    if str(evidence.get("evidence_boundary", "")) != str(contract.get("evidence_boundary", "")):
        problems.append("runtime evidence boundary does not match the declared contract")
    declared_surfaces = contract.get("surfaces", [])
    if isinstance(declared_surfaces, str):
        declared_surfaces = [declared_surfaces]
    declared_surfaces = [str(item).strip().replace("\\", "/") for item in declared_surfaces if str(item).strip()] if isinstance(declared_surfaces, list) else []
    attested_surfaces = evidence.get("surfaces", [])
    if isinstance(attested_surfaces, str):
        attested_surfaces = [attested_surfaces]
    if not isinstance(attested_surfaces, list):
        problems.append("runtime evidence surfaces must be a list")
        attested_surfaces = []
    normalized_attestations = sorted({str(item).strip().replace("\\", "/") for item in attested_surfaces if str(item).strip()})
    evidence["surfaces"] = normalized_attestations
    if declared_surfaces and not normalized_attestations:
        problems.append("runtime contract declared surfaces but emitted no observed surface attestations")
    cases = evidence.get("cases", [])
    if not isinstance(cases, list):
        problems.append("runtime evidence cases must be a list")
        cases = []
    required = set(_required_categories(contract))
    present_pass = {
        str(item.get("category", "")) for item in cases
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "PASS"
    }
    allowed_na = set(str(item) for item in contract.get("allow_not_applicable", []) if str(item))
    present_na = {
        str(item.get("category", "")) for item in cases
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "NOT_APPLICABLE" and str(item.get("reason", "")).strip()
    }
    case_map = {str(item.get("id", "")): item for item in cases if isinstance(item, dict) and str(item.get("id", ""))}
    for expected_case in _expected_cases(contract):
        case_id = str(expected_case.get("id", ""))
        actual = case_map.get(case_id)
        if actual is None:
            problems.append(f"declared runtime case is missing: {case_id}")
            continue
        for field in ("category", "actor", "action", "target", "resource", "expected"):
            declared = expected_case.get(field)
            if declared not in (None, "") and actual.get(field) != declared:
                problems.append(f"runtime case {case_id} does not match declared {field}")
        if str(actual.get("status", "")).upper() != "PASS":
            problems.append(f"declared runtime case did not pass: {case_id}")
    missing = sorted(required - present_pass - (allowed_na & present_na))
    if missing:
        problems.append("required evidence categories are missing or not passing: " + ", ".join(missing))
    bad_cases = [
        str(item.get("id", item.get("category", "unnamed"))) for item in cases
        if isinstance(item, dict) and str(item.get("status", "")).upper() in {"FAIL", "ERROR", "BLOCKED", "SKIP", "NOT-RUN"}
    ]
    if bad_cases:
        problems.append("runtime evidence contains non-passing required cases: " + ", ".join(bad_cases))
    declared_status = str(evidence.get("status", "")).upper()
    if declared_status != "PASS":
        problems.append(f"runtime evidence declared status {declared_status or '(empty)'}")
    return ("PASS" if not problems else "FAIL"), problems, evidence


def run_runtime_contract(project_root: Path, forge_root: Path, config: dict[str, Any], contract_id: str) -> dict[str, Any]:
    registry = load_runtime_contracts(project_root, config)
    contract = next((item for item in registry.get("contracts", []) if isinstance(item, dict) and item.get("id") == contract_id), None)
    if contract is None:
        raise RuntimeError(f"unknown runtime contract: {contract_id}")
    validation = validate_runtime_contract(contract, project_root)
    started = utc_now()
    if validation or not contract.get("enabled", True):
        status = "BLOCKED"
        returncode = None
        output = ""
        evidence: dict[str, Any] = {}
        problems = [item["message"] for item in validation] or ["runtime contract is disabled"]
    else:
        returncode, output, startup_error = _execute_contract_command(project_root, forge_root, contract, int(contract.get("timeout", 900)))
        evidence = _parse_evidence(output) or {}
        status, problems, evidence = _validate_evidence_payload(contract, evidence or None)
        if startup_error:
            status = "ERROR"; problems.insert(0, startup_error)
        elif returncode != 0:
            status = "FAIL"; problems.insert(0, f"runtime contract command exited {returncode}")
    payload = {
        "schema": 1,
        "contract_id": contract_id,
        "title": contract.get("title", contract_id),
        "kind": contract.get("kind", ""),
        "status": status,
        "contract_fingerprint": _contract_fingerprint(contract),
        "tree_fingerprint": tree_fingerprint(project_root, config.get("paths", {}).get("exclude", []), forge_root),
        "evidence_boundary": contract.get("evidence_boundary", ""),
        "environment_signature": _environment_signature(),
        "started_utc": started,
        "finished_utc": utc_now(),
        "returncode": returncode,
        "required_categories": _required_categories(contract),
        "problems": [_redact_text(str(item)) for item in problems],
        "evidence": _redact_value(evidence),
        "output": _redact_text(output[-20_000:]),
    }
    runtime = config.get("runtime_proof", {})
    output_dir = project_root / runtime.get("output_dir", ".forge/runtime") / "reports"
    stamp = started.replace(":", "").replace("-", "").replace("+00:00", "Z")
    write_json(output_dir / f"{contract_id}-{stamp}.json", payload)
    write_json(output_dir / f"{contract_id}-latest.json", payload)
    _write_contract_report(output_dir / f"{contract_id}-{stamp}.txt", payload)
    return payload


def _write_contract_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"Emotivus Forge Runtime Contract — {payload['title']}", "=" * 72,
        f"Status: {payload['status']}",
        f"Kind: {payload['kind']}",
        f"Boundary: {payload['evidence_boundary']}",
        f"Environment: {payload.get('environment_signature', '')}",
        f"Contract fingerprint: {payload['contract_fingerprint']}",
        f"Required categories: {', '.join(payload['required_categories'])}", "",
    ]
    if payload["problems"]:
        lines.extend(["Problems", "--------"] + [f"- {item}" for item in payload["problems"]] + [""])
    cases = payload.get("evidence", {}).get("cases", []) if isinstance(payload.get("evidence"), dict) else []
    lines.extend(["Cases", "-----"])
    if not cases:
        lines.append("No structured cases were emitted.")
    for item in cases:
        if isinstance(item, dict):
            lines.append(f"{item.get('status', '')}: {item.get('id', item.get('category', 'unnamed'))} [{item.get('category', '')}]")
            if item.get("detail"):
                lines.append(f"  {item['detail']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_required_runtime_contracts(project_root: Path, forge_root: Path, config: dict[str, Any], profile: str) -> tuple[bool, str]:
    runtime = config.get("runtime_proof", {})
    if not runtime.get("enabled", True):
        return True, "Runtime contract proof is disabled."
    registry = load_runtime_contracts(project_root, config)
    contracts = [
        item for item in registry.get("contracts", [])
        if isinstance(item, dict) and item.get("enabled", True) and profile in item.get("profiles", [])
    ]
    required_kinds = set(str(item) for item in runtime.get("required_kinds_by_profile", {}).get(profile, []))
    present_kinds = set(str(item.get("kind", "")) for item in contracts)
    missing_kinds = sorted(required_kinds - present_kinds)
    if missing_kinds:
        return False, "Required runtime contract kinds are missing for this profile: " + ", ".join(missing_kinds)
    if not contracts:
        return True, "No runtime contracts are assigned to this profile."
    minimum = str(runtime.get("minimum_boundary_by_profile", {}).get(profile, "local-process"))
    lines: list[str] = []
    all_ok = True
    for contract in contracts:
        boundary = str(contract.get("evidence_boundary", ""))
        boundary_ok = _boundary_rank(boundary) >= _boundary_rank(minimum)
        result = run_runtime_contract(project_root, forge_root, config, str(contract.get("id", "")))
        ok = result["status"] == "PASS" and boundary_ok
        all_ok = all_ok and ok
        lines.append(f"{'PASS' if ok else 'BLOCKED'} {result['contract_id']}: kind={result['kind']}, boundary={boundary} (minimum={minimum})")
        if not boundary_ok:
            lines.append("  Evidence boundary is weaker than this Gate requires.")
        lines.extend(f"  {item}" for item in result["problems"])
        if not ok:
            break
    return all_ok, "\n".join(lines)

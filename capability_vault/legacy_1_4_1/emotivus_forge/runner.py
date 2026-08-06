from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .audit import run_audit
from .doctor import run_doctor
from .evidence import evaluate_anomaly, parse_command_evidence, record_execution
from .failures import write_failure_bundle
from .graph import build_graph, load_graph
from .lab import run_required_labs
from .runtime_contracts import run_required_runtime_contracts
from .package import build_package
from .project_memory import validate_project_release
from .release import validate_release
from .release_proof import build_release_proof
from .reporting import write_audit_reports
from .utils import declared_paths_fingerprint, resolve_command, sha256_file, tree_fingerprint, tree_snapshot, utc_now, write_json


@dataclass(frozen=True)
class Check:
    check_id: str
    category: str
    timeout: int
    command: tuple[str, ...] = ()
    internal: str = ""
    required: bool = True
    evidence_spec: dict[str, Any] = field(default_factory=dict)

    @property
    def command_hash(self) -> str:
        raw = "\0".join(self.command) if self.command else self.internal
        raw += "\0" + json.dumps(self.evidence_spec, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class Result:
    check_id: str
    category: str
    command: list[str]
    command_hash: str
    status: str
    returncode: int | None
    duration_seconds: float
    started_utc: str
    finished_utc: str
    output: str
    required: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)
    anomaly: dict[str, Any] = field(default_factory=dict)
    failure_bundle: dict[str, Any] = field(default_factory=dict)
    error_kind: str = ""
    resumed: bool = False


def _evidence_artifact_state(project_root: Path, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_paths = spec.get("artifacts", []) if isinstance(spec, dict) else []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, list):
        return {}
    state: dict[str, dict[str, Any]] = {}
    for raw in raw_paths:
        rel = str(raw).strip().replace("\\", "/")
        rel_path = Path(rel)
        if not rel or rel_path.is_absolute() or ".." in rel_path.parts:
            continue
        path = project_root / rel_path
        if path.is_file():
            stat = path.stat()
            state[rel_path.as_posix()] = {
                "exists": True,
                "sha256": sha256_file(path),
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        else:
            state[rel_path.as_posix()] = {"exists": False}
    return state


def _capture_evidence_artifacts(
    project_root: Path,
    spec: dict[str, Any],
    evidence: dict[str, Any],
    before_state: dict[str, dict[str, Any]],
) -> None:
    raw_paths = spec.get("artifacts", []) if isinstance(spec, dict) else []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, list):
        raw_paths = []
    captured: list[dict[str, Any]] = []
    problems: list[str] = []
    for raw in raw_paths:
        rel = str(raw).strip().replace("\\", "/")
        rel_path = Path(rel)
        if not rel or rel_path.is_absolute() or ".." in rel_path.parts:
            problems.append(f"declared evidence artifact path is unsafe: {rel or '(empty)'}")
            continue
        normalized = rel_path.as_posix()
        path = project_root / rel_path
        if not path.is_file():
            problems.append(f"declared evidence artifact was not produced: {rel}")
            continue
        stat = path.stat()
        digest = sha256_file(path)
        previous = before_state.get(normalized, {"exists": False})
        produced_in_run = (
            not previous.get("exists", False)
            or str(previous.get("sha256", "")) != digest
            or int(previous.get("bytes", -1)) != stat.st_size
            or int(previous.get("mtime_ns", -1)) != stat.st_mtime_ns
        )
        captured.append({
            "path": normalized,
            "sha256": digest,
            "bytes": stat.st_size,
            "produced_in_run": produced_in_run,
        })
    evidence["artifacts"] = captured
    if problems:
        evidence.setdefault("problems", []).extend(problems)
        evidence["complete"] = False
        if bool(spec.get("artifacts_required", True)) and evidence.get("status") == "PASS":
            evidence["status"] = "ERROR"


def _run_process(check: Check, project_root: Path) -> Result:
    started = utc_now()
    before = time.monotonic()
    output = ""
    returncode: int | None = None
    log_path = ""
    log_handle = None
    error_kind = ""
    ecosystem_state = check.evidence_spec.get("tool_ecosystem", {}) if isinstance(check.evidence_spec, dict) else {}
    missing_inputs = ecosystem_state.get("missing", []) if isinstance(ecosystem_state, dict) else []
    unsafe_inputs = ecosystem_state.get("unsafe", []) if isinstance(ecosystem_state, dict) else []
    if missing_inputs or unsafe_inputs:
        problems = [f"tool ecosystem input is missing: {item}" for item in missing_inputs]
        problems.extend(f"tool ecosystem input path is unsafe: {item}" for item in unsafe_inputs)
        evidence = parse_command_evidence("", None, {"protocol": "exit-code"})
        evidence["problems"].extend(problems)
        evidence["complete"] = False
        evidence["status"] = "ERROR"
        return Result(
            check.check_id, check.category, list(check.command), check.command_hash, "ERROR", None,
            round(time.monotonic() - before, 3), started, utc_now(), "\n".join(problems), check.required,
            evidence=evidence, error_kind="tool-ecosystem-inputs",
        )
    artifact_before = _evidence_artifact_state(project_root, check.evidence_spec)
    try:
        log_handle = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False, prefix="forge-check-", suffix=".log")
        log_path = log_handle.name
        process = subprocess.Popen(
            list(check.command), cwd=project_root, text=True, stdout=log_handle, stderr=subprocess.STDOUT,
            start_new_session=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except OSError as exc:
        if log_handle is not None:
            log_handle.close()
        evidence = parse_command_evidence("", None, {"protocol": "exit-code"})
        evidence["problems"].append(f"could not start command: {exc}")
        return Result(check.check_id, check.category, list(check.command), check.command_hash, "ERROR", None, round(time.monotonic() - before, 3), started, utc_now(), f"Could not start command: {exc}", check.required, evidence, error_kind="startup")
    status = "ERROR"
    try:
        returncode = process.wait(timeout=check.timeout)
    except subprocess.TimeoutExpired:
        error_kind = "timeout"
        try:
            os.killpg(process.pid, signal.SIGTERM)
            returncode = process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                returncode = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                returncode = None
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if log_handle is not None:
            try:
                log_handle.flush()
                log_handle.seek(0)
                output = log_handle.read()
            finally:
                log_handle.close()
        if log_path:
            try:
                Path(log_path).unlink()
            except OSError:
                pass
    if error_kind == "timeout":
        evidence = parse_command_evidence(output, returncode, check.evidence_spec)
        _capture_evidence_artifacts(project_root, check.evidence_spec, evidence, artifact_before)
        evidence["problems"].append(f"command exceeded timeout of {check.timeout} seconds")
        status = "ERROR"
    else:
        evidence = parse_command_evidence(output, returncode, check.evidence_spec)
        _capture_evidence_artifacts(project_root, check.evidence_spec, evidence, artifact_before)
        status = evidence["status"]
    return Result(
        check.check_id, check.category, list(check.command), check.command_hash, status, returncode,
        round(time.monotonic() - before, 3), started, utc_now(), output.rstrip(), check.required,
        evidence=evidence, error_kind=error_kind,
    )


def _internal_result(check: Check, callback: Callable[[], tuple[bool, str]]) -> Result:
    started = utc_now()
    before = time.monotonic()
    error_kind = ""
    try:
        ok, output = callback()
        status = "PASS" if ok else "FAIL"
        returncode = 0 if ok else 1
    except Exception as exc:
        status = "ERROR"
        output = f"{type(exc).__name__}: {exc}"
        returncode = None
        error_kind = "exception"
    evidence = {
        "schema": 1, "protocol": "internal", "source": "internal", "status": status,
        "explicit_status": status, "allow_skip": False, "complete": True,
        "counts": {"assertions": None, "skips": None, "migrations": None, "executed": 1},
        "problems": [],
    }
    return Result(check.check_id, check.category, [], check.command_hash, status, returncode, round(time.monotonic() - before, 3), started, utc_now(), output, check.required, evidence=evidence, error_kind=error_kind)


def _needs_environment_preflight(config: dict[str, Any]) -> bool:
    environment = config.get("environment", {})
    return bool(environment.get("required_executables") or environment.get("required_env") or environment.get("expected_layout"))


def build_plan(project_root: Path, forge_root: Path, config: dict[str, Any], profile: str) -> list[Check]:
    profile_data = config.get("profiles", {}).get(profile)
    if not isinstance(profile_data, dict):
        raise RuntimeError(f"unknown profile: {profile}")
    checks: list[Check] = []
    if profile_data.get("audit"):
        checks.append(Check("core.audit", "audit", 600, internal="audit"))
    if _needs_environment_preflight(config):
        checks.append(Check("environment.preflight", "environment", 60, internal="environment"))
    graph_config = config.get("graph", {})
    if graph_config.get("enabled", True) and profile in graph_config.get("refresh_profiles", []):
        checks.append(Check("graph.refresh", "architecture", 600, internal="graph"))
    if profile_data.get("release_gate"):
        checks.append(Check("project.readiness", "project-truth", 30, internal="project-release"))
        checks.append(Check("release.metadata", "release", 30, internal="release"))
    seen_commands: set[tuple[str, ...]] = set()
    covered_groups: set[str] = set()
    for group in profile_data.get("commands", []):
        if group in covered_groups:
            continue
        for raw in config.get("commands", {}).get(group, []):
            if not isinstance(raw, dict):
                continue
            command = raw.get("command")
            if not isinstance(command, list) or not command:
                continue
            resolved_command = tuple(resolve_command([str(item) for item in command], project=project_root, forge=forge_root))
            if resolved_command in seen_commands:
                continue
            seen_commands.add(resolved_command)
            evidence_spec = dict(raw.get("evidence", {})) if isinstance(raw.get("evidence"), dict) else {}
            ecosystem_inputs = raw.get("ecosystem_inputs", [])
            if isinstance(ecosystem_inputs, list) and ecosystem_inputs:
                ecosystem_state = declared_paths_fingerprint(project_root, [str(item) for item in ecosystem_inputs])
                evidence_spec["tool_ecosystem"] = {
                    "id": str(raw.get("ecosystem_id", "")),
                    "manifest": str(raw.get("ecosystem_manifest", "")),
                    **ecosystem_state,
                }
            checks.append(Check(
                str(raw.get("id") or f"command.{group}.{len(checks)}"),
                f"command:{group}",
                int(raw.get("timeout", 300)),
                resolved_command,
                required=bool(raw.get("required", True)),
                evidence_spec=evidence_spec,
            ))
            covers = raw.get("covers_groups", [])
            if isinstance(covers, list):
                covered_groups.update(str(item) for item in covers)
    lab_config = config.get("lab", {})
    has_profile_recipe = any(
        isinstance(item, dict) and item.get("enabled", True) and profile in item.get("profiles", [])
        for item in lab_config.get("recipes", [])
    )
    if lab_config.get("enabled", True) and (profile in lab_config.get("required_profiles", []) or has_profile_recipe):
        checks.append(Check(f"lab.{profile}", "live-verification", 1200, internal=f"lab:{profile}"))
    runtime_config = config.get("runtime_proof", {})
    runtime_registry = project_root / runtime_config.get("contracts_path", ".forge/contracts/runtime-contracts.json")
    has_profile_contract = False
    if runtime_registry.is_file():
        try:
            runtime_payload = json.loads(runtime_registry.read_text(encoding="utf-8"))
            has_profile_contract = any(
                isinstance(item, dict) and item.get("enabled", True) and profile in item.get("profiles", [])
                for item in runtime_payload.get("contracts", [])
            )
        except (OSError, json.JSONDecodeError):
            has_profile_contract = True
    required_runtime_kinds = runtime_config.get("required_kinds_by_profile", {}).get(profile, [])
    if runtime_config.get("enabled", True) and (has_profile_contract or required_runtime_kinds):
        checks.append(Check(f"runtime.{profile}", "runtime-contract", 1800, internal=f"runtime:{profile}"))
    if profile_data.get("package_dry_run"):
        checks.append(Check("package.dry-run", "package", 600, internal="package"))
    if profile_data.get("release_gate") and config.get("release_proof", {}).get("enabled", True):
        checks.append(Check("release.proof", "release-coverage", 120, internal="release-proof"))
    ids = [item.check_id for item in checks]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate check IDs in project configuration")
    if not checks:
        raise RuntimeError(f"profile {profile} produced no checks")
    return checks


def _load_resume(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _graph_node_count(project_root: Path, config: dict[str, Any]) -> int:
    graph = load_graph(project_root, config)
    return int(graph.get("summary", {}).get("nodes", 0)) if graph else 0


def _result_blocks(result: Result) -> bool:
    if result.status in {"FAIL", "ERROR"}:
        return True
    if result.status == "SKIP" and result.required and not result.evidence.get("allow_skip", False):
        return True
    return False


def run_profile(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    profile: str,
    *,
    resume: bool = False,
    fresh: bool = False,
    only: list[str] | None = None,
    allow_anomaly: list[str] | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    checks = build_plan(project_root, forge_root, config, profile)
    if only:
        checks = [check for check in checks if any(check.check_id.startswith(prefix) for prefix in only)]
        if not checks:
            raise RuntimeError("--only filters matched no checks")
    allowed_anomalies = set(allow_anomaly or [])
    excludes = config.get("paths", {}).get("exclude", [])
    fingerprint = tree_fingerprint(project_root, excludes, forge_root)
    snapshot = tree_snapshot(project_root, excludes, forge_root)
    reports_dir = project_root / config.get("paths", {}).get("reports", ".forge/reports")
    report_path = reports_dir / f"{profile}.json"
    previous = None if fresh else _load_resume(report_path) if resume else None
    previous_map = {item.get("check_id"): item for item in previous.get("results", [])} if previous and previous.get("tree_fingerprint") == fingerprint and previous.get("profile") == profile else {}

    results: list[Result] = []
    started = utc_now()
    for check in checks:
        cached = previous_map.get(check.check_id)
        if cached and cached.get("status") == "PASS" and cached.get("command_hash") == check.command_hash:
            results.append(Result(
                check_id=check.check_id, category=check.category, command=cached.get("command", []),
                command_hash=check.command_hash, status="PASS", returncode=cached.get("returncode"),
                duration_seconds=float(cached.get("duration_seconds", 0)), started_utc=cached.get("started_utc", started),
                finished_utc=cached.get("finished_utc", started), output=cached.get("output", ""),
                required=bool(cached.get("required", check.required)), evidence=cached.get("evidence", {}),
                anomaly=cached.get("anomaly", {}), failure_bundle=cached.get("failure_bundle", {}), resumed=True,
            ))
            continue

        if check.internal == "audit":
            def audit_cb() -> tuple[bool, str]:
                payload = run_audit(project_root, forge_root, config, use_baseline=True)
                audit_path = reports_dir / f"{profile}-audit.json"
                write_audit_reports(audit_path, payload)
                lines = [f"Audit status: {payload['status']}", f"Findings: {len(payload['findings'])}"]
                for finding in payload["findings"]:
                    lines.append(f"{finding['severity'].upper()} {finding['disposition']} {finding['check_id']} {finding.get('path', '')}: {finding['message']}")
                return payload["status"] == "PASS", "\n".join(lines)
            result = _internal_result(check, audit_cb)
        elif check.internal == "environment":
            def environment_cb() -> tuple[bool, str]:
                payload = run_doctor(project_root, forge_root, config, write=True)
                output = f"Forge Doctor status: {payload['status']}"
                if payload.get("problems"):
                    output += "\n" + "\n".join(payload["problems"])
                return payload["status"] == "PASS", output
            result = _internal_result(check, environment_cb)
        elif check.internal == "graph":
            def graph_cb() -> tuple[bool, str]:
                payload = build_graph(project_root, forge_root, config, write=True)
                summary = payload.get("summary", {})
                return True, f"Forge Graph refreshed: nodes={summary.get('nodes', 0)}, edges={summary.get('edges', 0)}, subsystems={len(summary.get('subsystems', {}))}"
            result = _internal_result(check, graph_cb)
        elif check.internal == "project-release":
            result = _internal_result(check, lambda: (not (problems := validate_project_release(project_root, config)), "Project truth is release-ready." if not problems else "\n".join(problems)))
        elif check.internal == "release":
            result = _internal_result(check, lambda: (not (problems := validate_release(project_root, config)), "Release metadata valid." if not problems else "\n".join(problems)))
        elif check.internal == "release-proof":
            def release_proof_cb() -> tuple[bool, str]:
                payload = build_release_proof(project_root, forge_root, config, write=True)
                lines = [
                    f"Release claim: {payload['claim_level']}",
                    f"Claim status: {payload['claim_status']}",
                    f"Surfaces: {payload['surfaces']['count']} discovered; {payload['surfaces']['covered']} recurring-execution covered; {payload['surfaces']['uncovered']} uncovered",
                ]
                if payload['problems']:
                    lines.extend(payload['problems'])
                if payload['limitations']:
                    lines.append("Known limitations:")
                    lines.extend(f"- {item}" for item in payload['limitations'])
                return payload['claim_status'] == 'PASS', "\n".join(lines)
            result = _internal_result(check, release_proof_cb)
        elif check.internal.startswith("lab:"):
            lab_profile = check.internal.split(":", 1)[1]
            result = _internal_result(check, lambda: run_required_labs(project_root, forge_root, config, lab_profile))
        elif check.internal.startswith("runtime:"):
            runtime_profile = check.internal.split(":", 1)[1]
            result = _internal_result(check, lambda: run_required_runtime_contracts(project_root, forge_root, config, runtime_profile))
        elif check.internal == "package":
            def package_cb() -> tuple[bool, str]:
                payload = build_package(project_root, forge_root, config, dry_run=True)
                output = f"Package dry-run: {payload['status']}\nIncluded: {payload['included_count']}\nExcluded: {payload['excluded_count']}"
                if payload["problems"]:
                    output += "\n" + "\n".join(payload["problems"])
                return payload["status"] == "PASS", output
            result = _internal_result(check, package_cb)
        else:
            result = _run_process(check, project_root)

        graph_nodes = _graph_node_count(project_root, config)
        result.anomaly = evaluate_anomaly(
            project_root, config, check_id=check.check_id, command_hash=check.command_hash,
            command=list(check.command), duration_seconds=result.duration_seconds, status=result.status,
            evidence=result.evidence, graph_nodes=graph_nodes,
        )
        if result.anomaly.get("requires_override"):
            if check.check_id in allowed_anomalies:
                result.anomaly["override"] = {"accepted": True, "reason": "explicit CLI override", "recorded_utc": utc_now()}
            else:
                result.status = "ERROR"
                result.error_kind = "anomaly-evidence"
                result.output = (result.output + "\n" if result.output else "") + "Forge blocked this check because execution evidence regressed during an anomalous run. Re-run with --allow-anomaly " + check.check_id + " only after reviewing the evidence."
        record_execution(
            project_root, config, check_id=check.check_id, command_hash=check.command_hash,
            command=list(check.command), duration_seconds=result.duration_seconds, status=result.status,
            evidence=result.evidence, graph_nodes=graph_nodes,
        )

        if _result_blocks(result):
            reproduction = [
                os.sys.executable, str(forge_root / "forge.py"), "check", str(project_root),
                "--profile", profile, "--fresh", "--only", check.check_id,
            ]
            result.failure_bundle = write_failure_bundle(
                project_root, forge_root, config, profile=profile, result=asdict(result),
                current_snapshot=snapshot, reproduction_command=reproduction,
            )
        results.append(result)

        payload = _payload(profile, config, fingerprint, snapshot, started, checks, results)
        write_json(report_path, payload)
        _write_text_report(report_path.with_suffix(".txt"), payload)
        if _result_blocks(result):
            break

    payload = _payload(profile, config, fingerprint, snapshot, started, checks, results)
    write_json(report_path, payload)
    _write_text_report(report_path.with_suffix(".txt"), payload)
    if payload["status"] == "PASS":
        write_json(project_root / ".forge" / "evidence" / "last-green" / f"{profile}.json", payload)
    return payload


def _payload(profile: str, config: dict[str, Any], fingerprint: str, snapshot: dict[str, Any], started: str, checks: list[Check], results: list[Result]) -> dict[str, Any]:
    result_map = {item.check_id: item for item in results}
    matrix: list[dict[str, Any]] = []
    for check in checks:
        item = result_map.get(check.check_id)
        matrix.append({
            "check_id": check.check_id,
            "category": check.category,
            "required": check.required,
            "status": item.status if item else "NOT_RUN",
        })
    status_counts = {status: sum(1 for item in matrix if item["status"] == status) for status in ("PASS", "FAIL", "SKIP", "ERROR", "NOT_RUN")}
    blocking = any(
        item.status in {"FAIL", "ERROR"} or (item.status == "SKIP" and item.required and not item.evidence.get("allow_skip", False))
        for item in results
    )
    complete = status_counts["NOT_RUN"] == 0
    status = "FAIL" if blocking else "INCOMPLETE" if not complete else "PASS"
    anomalies = [asdict(item) for item in results if item.anomaly.get("detected")]
    return {
        "schema": 2,
        "forge": "Emotivus Forge",
        "profile": profile,
        "project": config.get("project", {}).get("name", ""),
        "project_identity": config.get("project", {}).get("identity", ""),
        "workspace_classification": config.get("workspace", {}).get("classification", "unknown"),
        "work_mode": config.get("work", {}).get("mode", config.get("project_memory", {}).get("mode", "development")),
        "evidence_boundary": "source-tree",
        "status": status,
        "tree_fingerprint": fingerprint,
        "tree_snapshot": snapshot,
        "started_utc": started,
        "updated_utc": utc_now(),
        "required_check_ids": [check.check_id for check in checks],
        "completed_count": len(results),
        "remaining_count": len(checks) - len(results),
        "status_counts": status_counts,
        "result_matrix": matrix,
        "anomaly_count": len(anomalies),
        "results": [asdict(item) for item in results],
    }


def _write_text_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"Emotivus Forge checks — {payload['profile']}", "=" * 64,
        f"Project: {payload.get('project', '')}", f"Status: {payload['status']}",
        f"Tree SHA-256: {payload['tree_fingerprint']}",
        f"Completed: {payload['completed_count']} / {len(payload['required_check_ids'])}",
        "States: " + " | ".join(f"{key}={value}" for key, value in payload.get("status_counts", {}).items()),
        f"Execution anomalies: {payload.get('anomaly_count', 0)}", "",
    ]
    result_map = {item["check_id"]: item for item in payload["results"]}
    for check_id in payload["required_check_ids"]:
        item = result_map.get(check_id)
        if item is None:
            lines.append(f"{'NOT_RUN':<16} {'-':>9}  {check_id}")
        else:
            suffix = " (resumed)" if item.get("resumed") else ""
            if item.get("anomaly", {}).get("detected"):
                suffix += " [ANOMALY_WARNING]"
            lines.append(f"{item['status']:<16} {item['duration_seconds']:>8.3f}s  {check_id}{suffix}")
    failures = [item for item in payload["results"] if item["status"] in {"FAIL", "ERROR"} or (item["status"] == "SKIP" and item.get("required", True) and not item.get("evidence", {}).get("allow_skip", False))]
    if failures:
        lines.extend(["", "Failure output", "--------------"])
        for item in failures:
            lines.extend([f"[{item['check_id']}]", item.get("output", ""), ""])
            if item.get("failure_bundle", {}).get("directory"):
                lines.append(f"Context bundle: {item['failure_bundle']['directory']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

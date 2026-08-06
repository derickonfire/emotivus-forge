from __future__ import annotations

import json
import platform
import re
import statistics
from pathlib import Path
from typing import Any

from .utils import utc_now, write_json

ALLOWED_STATUSES = {"PASS", "FAIL", "SKIP", "ERROR"}
STATUS_RE = re.compile(r"(?m)^FORGE_STATUS:\s*(PASS|FAIL|SKIP|ERROR)\s*$")
SURFACE_RE = re.compile(r"(?m)^FORGE_SURFACE:\s*(\S(?:.*\S)?)\s*$")
COUNT_PATTERNS = {
    "assertions": re.compile(r"(?m)^FORGE_ASSERTIONS:\s*(\d+)\s*$"),
    "skips": re.compile(r"(?m)^FORGE_SKIPS:\s*(\d+)\s*$"),
    "migrations": re.compile(r"(?m)^FORGE_MIGRATIONS:\s*(\d+)\s*$"),
    "executed": re.compile(r"(?m)^FORGE_EXECUTED:\s*(\d+)\s*$"),
}


def parse_command_evidence(output: str, returncode: int | None, spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec if isinstance(spec, dict) else {}
    protocol = str(spec.get("protocol", "exit-code")).strip().lower() or "exit-code"
    required = bool(spec.get("required", False))
    allow_skip = bool(spec.get("allow_skip", False))
    counts: dict[str, int | None] = {}
    for name, pattern in COUNT_PATTERNS.items():
        match = pattern.search(output)
        counts[name] = int(match.group(1)) if match else None

    explicit_status = None
    match = STATUS_RE.search(output)
    if match:
        explicit_status = match.group(1)
    surfaces = sorted({match.group(1).strip().replace("\\", "/") for match in SURFACE_RE.finditer(output) if match.group(1).strip()})

    problems: list[str] = []
    source = "exit-code"
    if protocol == "markers" or required:
        source = "markers"
        if explicit_status is None:
            status = "ERROR"
            problems.append("required FORGE_STATUS evidence marker is missing")
        else:
            status = explicit_status
    else:
        status = "PASS" if returncode == 0 else "FAIL"
        if explicit_status is not None:
            source = "markers+exit-code"
            status = explicit_status

    if status not in ALLOWED_STATUSES:
        status = "ERROR"
        problems.append("command produced an unsupported status")
    if explicit_status == "PASS" and returncode not in {0, None}:
        status = "ERROR"
        problems.append("command claimed PASS but returned a non-zero exit code")
    if explicit_status in {"FAIL", "ERROR"} and returncode == 0:
        problems.append("command returned zero while explicitly reporting failure")
    if status == "SKIP" and not allow_skip:
        problems.append("command reported SKIP but this check does not allow skipping")

    required_fields = [str(item) for item in spec.get("required_fields", []) if str(item)]
    for field in required_fields:
        if field == "status" and explicit_status is None:
            if "required FORGE_STATUS evidence marker is missing" not in problems:
                problems.append("required status evidence is missing")
        elif field in counts and counts[field] is None:
            problems.append(f"required {field} evidence is missing")

    complete = not any("missing" in problem for problem in problems)
    if required and not complete:
        status = "ERROR"
    return {
        "schema": 1,
        "protocol": protocol,
        "source": source,
        "status": status,
        "explicit_status": explicit_status or "",
        "allow_skip": allow_skip,
        "complete": complete,
        "counts": counts,
        "surfaces": surfaces,
        "problems": problems,
    }


def environment_signature(command: list[str]) -> str:
    executable = command[0] if command else "internal"
    return f"{platform.system()}|{platform.machine()}|py{platform.python_version()}|{executable}"


def _history_path(project_root: Path, config: dict[str, Any]) -> Path:
    return project_root / config.get("evidence", {}).get("history_path", ".forge/evidence/execution-history.json")


def load_history(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    path = _history_path(project_root, config)
    if not path.is_file():
        return {"schema": 1, "updated_utc": utc_now(), "runs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "updated_utc": utc_now(), "runs": []}
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return {"schema": 1, "updated_utc": utc_now(), "runs": []}
    return data


def evaluate_anomaly(
    project_root: Path,
    config: dict[str, Any],
    *,
    check_id: str,
    command_hash: str,
    command: list[str],
    duration_seconds: float,
    status: str,
    evidence: dict[str, Any],
    graph_nodes: int,
) -> dict[str, Any]:
    anomaly_config = config.get("evidence", {}).get("anomaly", {})
    if not anomaly_config.get("enabled", True) or status not in {"PASS", "SKIP"}:
        return {"detected": False}
    history = load_history(project_root, config)
    signature = environment_signature(command)
    comparable = [
        item for item in history.get("runs", [])
        if item.get("check_id") == check_id
        and item.get("command_hash") == command_hash
        and item.get("environment_signature") == signature
        and item.get("status") == "PASS"
    ]
    min_samples = int(anomaly_config.get("minimum_samples", 3))
    if len(comparable) < min_samples:
        return {"detected": False, "sample_count": len(comparable), "minimum_samples": min_samples}

    durations = [float(item.get("duration_seconds", 0)) for item in comparable if float(item.get("duration_seconds", 0)) > 0]
    if len(durations) < min_samples:
        return {"detected": False, "sample_count": len(durations), "minimum_samples": min_samples}
    median_duration = statistics.median(durations)
    deviations = [abs(value - median_duration) for value in durations]
    mad = statistics.median(deviations) if deviations else 0.0
    ratio = float(anomaly_config.get("fast_ratio", 0.6))
    tolerance = max(4 * mad, median_duration * 0.2)
    fast_threshold = max(median_duration * ratio, median_duration - tolerance)
    suspicious_fast = duration_seconds < fast_threshold

    current_counts = evidence.get("counts", {}) if isinstance(evidence, dict) else {}
    deltas: list[str] = []
    for name in ("assertions", "migrations", "executed"):
        historical = [item.get("evidence", {}).get("counts", {}).get(name) for item in comparable]
        historical = [int(value) for value in historical if isinstance(value, int)]
        current = current_counts.get(name)
        if historical and isinstance(current, int) and current < statistics.median(historical):
            deltas.append(f"{name} dropped from historical median {statistics.median(historical):g} to {current}")
    historical_skips = [item.get("evidence", {}).get("counts", {}).get("skips") for item in comparable]
    historical_skips = [int(value) for value in historical_skips if isinstance(value, int)]
    current_skips = current_counts.get("skips")
    if isinstance(current_skips, int) and current_skips > (max(historical_skips) if historical_skips else 0):
        deltas.append(f"skips increased to {current_skips}")

    historical_nodes = [int(item.get("graph_nodes", 0)) for item in comparable if int(item.get("graph_nodes", 0)) > 0]
    graph_stable = not historical_nodes or graph_nodes >= statistics.median(historical_nodes) * 0.95
    evidence_problem = bool(deltas) or not evidence.get("complete", True) or (status == "SKIP" and not evidence.get("allow_skip", False))
    detected = suspicious_fast or evidence_problem
    blocking = detected and evidence_problem and graph_stable
    return {
        "detected": detected,
        "blocking": blocking,
        "kind": "execution-evidence-anomaly" if evidence_problem else "execution-time-anomaly",
        "sample_count": len(comparable),
        "median_seconds": round(median_duration, 3),
        "mad_seconds": round(mad, 3),
        "fast_threshold_seconds": round(fast_threshold, 3),
        "current_seconds": round(duration_seconds, 3),
        "suspiciously_fast": suspicious_fast,
        "graph_stable": graph_stable,
        "evidence_deltas": deltas,
        "requires_override": blocking,
    }


def record_execution(
    project_root: Path,
    config: dict[str, Any],
    *,
    check_id: str,
    command_hash: str,
    command: list[str],
    duration_seconds: float,
    status: str,
    evidence: dict[str, Any],
    graph_nodes: int,
) -> None:
    history = load_history(project_root, config)
    history.setdefault("runs", []).append({
        "recorded_utc": utc_now(),
        "check_id": check_id,
        "command_hash": command_hash,
        "environment_signature": environment_signature(command),
        "duration_seconds": duration_seconds,
        "status": status,
        "evidence": evidence,
        "graph_nodes": graph_nodes,
    })
    max_entries = int(config.get("evidence", {}).get("history_limit", 500))
    history["runs"] = history["runs"][-max_entries:]
    history["updated_utc"] = utc_now()
    write_json(_history_path(project_root, config), history)


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def list_evidence(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Return a compact index of recorded proof without interpreting it."""
    project_root = project_root.resolve()
    reports_dir = project_root / config.get("paths", {}).get("reports", ".forge/reports")
    failure_dir = project_root / config.get("evidence", {}).get("failure_dir", ".forge/failures")
    history = load_history(project_root, config)
    gates: list[dict[str, Any]] = []
    for profile in ("quick", "section", "release"):
        payload = _safe_read_json(reports_dir / f"{profile}.json")
        if payload:
            gates.append({
                "id": f"gate:{profile}",
                "profile": profile,
                "status": payload.get("status", ""),
                "updated_utc": payload.get("updated_utc", payload.get("generated_utc", "")),
                "completed": payload.get("completed_count", ""),
                "remaining": payload.get("remaining_count", ""),
                "path": str(reports_dir / f"{profile}.json"),
            })
    failures: list[dict[str, Any]] = []
    if failure_dir.is_dir():
        for directory in sorted((item for item in failure_dir.iterdir() if item.is_dir()), reverse=True):
            payload = _safe_read_json(directory / "context.json")
            if not payload:
                continue
            failed = payload.get("failed_check", {}) if isinstance(payload.get("failed_check"), dict) else {}
            failures.append({
                "id": directory.name,
                "status": failed.get("status", ""),
                "profile": payload.get("profile", ""),
                "check_id": failed.get("check_id", ""),
                "generated_utc": payload.get("generated_utc", ""),
                "path": str(directory / "context.json"),
            })
    runtime_reports: list[dict[str, Any]] = []
    runtime_dir = project_root / config.get("runtime_proof", {}).get("output_dir", ".forge/runtime") / "reports"
    if runtime_dir.is_dir():
        for path in sorted(runtime_dir.glob("*-latest.json")):
            payload = _safe_read_json(path)
            if not payload:
                continue
            runtime_reports.append({
                "id": f"runtime:{payload.get('contract_id', path.stem.replace('-latest', ''))}",
                "contract_id": payload.get("contract_id", ""),
                "kind": payload.get("kind", ""),
                "status": payload.get("status", ""),
                "evidence_boundary": payload.get("evidence_boundary", ""),
                "finished_utc": payload.get("finished_utc", ""),
                "path": str(path),
            })
    release_proofs: list[dict[str, Any]] = []
    proof_path = project_root / str(config.get("release_proof", {}).get("output_dir", ".forge/release-proof")) / "latest.json"
    proof_payload = _safe_read_json(proof_path)
    if proof_payload:
        release_proofs.append({
            "id": "release-proof:latest",
            "status": proof_payload.get("claim_status", ""),
            "claim_level": proof_payload.get("claim_level", ""),
            "generated_utc": proof_payload.get("generated_utc", ""),
            "surface_count": proof_payload.get("surfaces", {}).get("count", "") if isinstance(proof_payload.get("surfaces"), dict) else "",
            "path": str(proof_path),
        })
    delivery_proofs: list[dict[str, Any]] = []
    delivery_path = project_root / str(config.get("delivery_proof", {}).get("manifest_path", ".forge/delivery/delivery-manifest.json"))
    delivery_payload = _safe_read_json(delivery_path)
    if delivery_payload:
        final = delivery_payload.get("final_bundle", {}) if isinstance(delivery_payload.get("final_bundle"), dict) else {}
        delivery_proofs.append({
            "id": "delivery-proof:manifest",
            "status": "RECORDED",
            "artifact_count": len(delivery_payload.get("artifacts", [])) if isinstance(delivery_payload.get("artifacts"), list) else 0,
            "final_bundle": final.get("path", ""),
            "updated_utc": delivery_payload.get("updated_utc", ""),
            "path": str(delivery_path),
        })
    runs = history.get("runs", []) if isinstance(history.get("runs"), list) else []
    return {
        "status": "PASS",
        "gates": gates,
        "runtime_contracts": runtime_reports,
        "release_proofs": release_proofs,
        "delivery_proofs": delivery_proofs,
        "failure_bundles": failures[:50],
        "execution_history": {
            "run_count": len(runs),
            "latest": runs[-20:],
            "path": str(_history_path(project_root, config)),
        },
        "interpretation_boundary": "Forge records evidence. AI or human reasoning interprets cause and chooses repairs.",
    }


def show_evidence(project_root: Path, config: dict[str, Any], evidence_id: str) -> dict[str, Any]:
    """Read one declared evidence object by a non-traversing identifier."""
    project_root = project_root.resolve()
    identifier = evidence_id.strip()
    if not identifier or identifier in {".", ".."} or "/" in identifier or "\\" in identifier:
        raise ValueError("evidence ID must be a single recorded identifier")
    reports_dir = project_root / config.get("paths", {}).get("reports", ".forge/reports")
    if identifier.startswith("gate:"):
        profile = identifier.split(":", 1)[1]
        if profile not in {"quick", "section", "release"}:
            raise ValueError("unknown Gate evidence ID")
        path = reports_dir / f"{profile}.json"
    elif identifier.startswith("runtime:"):
        contract_id = identifier.split(":", 1)[1]
        if not contract_id or not all(ch.isalnum() or ch in "-_." for ch in contract_id):
            raise ValueError("invalid runtime contract evidence ID")
        path = project_root / config.get("runtime_proof", {}).get("output_dir", ".forge/runtime") / "reports" / f"{contract_id}-latest.json"
    elif identifier == "release-proof:latest":
        path = project_root / str(config.get("release_proof", {}).get("output_dir", ".forge/release-proof")) / "latest.json"
    elif identifier == "delivery-proof:manifest":
        path = project_root / str(config.get("delivery_proof", {}).get("manifest_path", ".forge/delivery/delivery-manifest.json"))
    else:
        path = project_root / config.get("evidence", {}).get("failure_dir", ".forge/failures") / identifier / "context.json"
    payload = _safe_read_json(path)
    if payload is None:
        raise RuntimeError(f"evidence was not found or is malformed: {identifier}")
    return {"status": "PASS", "id": identifier, "path": str(path), "evidence": payload}

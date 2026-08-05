#!/usr/bin/env python3
"""Run portable Forge evidence-kit workflows after extracting the kit archive.

This runner is intentionally standalone. It verifies the extracted kit before using the
bound runtime, then creates candidate receipts without promoting them to independent
proof or release authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

KIT_SCHEMA = "forge-portable-evidence-kit/1"
WRITER_PLAN_SCHEMA = "forge-independent-writer-plan/1"
WRITER_STEP_SCHEMA = "forge-independent-writer-step/1"
WRITER_RECEIPT_SCHEMA = "forge-independent-writer-receipt/1"
BENCHMARK_PACKET_SCHEMA = "forge-handoff-benchmark-packet/1"
BENCHMARK_RESULT_SCHEMA = "forge-handoff-benchmark-result/1"
RETURN_SCHEMA = "forge-external-evidence-return/1"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

RUNNER_TRUTH_BOUNDARY = (
    "This runner verifies exact local bytes and records operator-supplied identities, process and "
    "environment metadata, provider token reports, and reviewer decisions. It does not authenticate "
    "people, prove separate administrative control, prove a remote or different operating system, "
    "verify provider billing data, establish causality, generalize beyond the recorded sample, or "
    "authorize release."
)


class RunnerError(ValueError):
    """Raised when an execution packet or receipt cannot be trusted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"{path} must contain one JSON object")
    return value


def environment_record() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "process_id": os.getpid(),
        "user_assertion": os.environ.get("USERNAME") or os.environ.get("USER") or "not-reported",
    }


def kit_root_from_script() -> Path:
    root = Path(__file__).resolve().parent
    if not (root / "MANIFEST.json").is_file():
        raise RunnerError("run-evidence.py must be executed from an extracted Forge evidence kit")
    return root


def verify_extracted_kit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = read_json(root / "MANIFEST.json")
    problems: list[str] = []
    if manifest.get("schema") != KIT_SCHEMA:
        problems.append("manifest schema differs")
    if manifest.get("evidence_status") != "NOT_RUN":
        problems.append("kit evidence status is not NOT_RUN")
    if manifest.get("independent_evidence_claimed") is not False:
        problems.append("kit claims independent evidence")
    if manifest.get("release_authorized") is not False:
        problems.append("kit claims release authorization")
    if manifest.get("private_key_retained") is not False:
        problems.append("kit does not state private_key_retained false")
    payloads = manifest.get("payloads")
    if not isinstance(payloads, list) or not payloads:
        problems.append("manifest payload list is missing")
        payloads = []
    declared: set[str] = set()
    for row in payloads:
        if not isinstance(row, dict):
            problems.append("payload entry is not an object")
            continue
        relative = str(row.get("path", ""))
        declared.add(relative)
        path = root / relative
        try:
            path.relative_to(root)
        except ValueError:
            problems.append(f"payload escapes kit root: {relative}")
            continue
        if not path.is_file() or path.is_symlink():
            problems.append(f"payload is missing or not regular: {relative}")
            continue
        if sha256_file(path) != row.get("sha256"):
            problems.append(f"payload digest differs: {relative}")
        if path.stat().st_size != row.get("bytes"):
            problems.append(f"payload byte length differs: {relative}")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if actual != declared:
        if declared - actual:
            problems.append(f"declared payloads missing: {sorted(declared - actual)}")
        if actual - declared:
            problems.append(f"undeclared payloads present: {sorted(actual - declared)}")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        problems.append("runtime identity missing")
    else:
        runtime_path = root / "runtime" / str(runtime.get("filename", ""))
        if not runtime_path.is_file():
            problems.append("bound runtime ZIP missing")
        elif sha256_file(runtime_path) != runtime.get("sha256"):
            problems.append("bound runtime digest differs")
    return {
        "status": "PASS" if not problems else "FAIL",
        "kit_id": str(manifest.get("kit_id", "")),
        "forge_version": str(manifest.get("forge_version", "")),
        "runtime": runtime if isinstance(runtime, dict) else {},
        "problems": problems,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }


def require_verified_kit(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    verification = verify_extracted_kit(root)
    if verification["status"] != "PASS":
        raise RunnerError(f"evidence kit verification failed: {verification['problems']}")
    return read_json(root / "MANIFEST.json"), verification


def _safe_extract_runtime(runtime_zip: Path, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(runtime_zip) as archive:
        names = [info.filename for info in archive.infolist()]
        if len(names) != len(set(names)):
            raise RunnerError("runtime ZIP contains duplicate member names")
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            parts = PurePosixPath(normalized).parts
            if normalized.startswith("/") or ".." in parts or info.flag_bits & 0x1:
                raise RunnerError(f"runtime ZIP contains an unsafe member: {info.filename}")
        archive.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1 or not (roots[0] / "forge.py").is_file():
        raise RunnerError("runtime ZIP did not extract to one Forge runtime directory")
    return roots[0]


def _run_json(command: list[str], *, cwd: Path, allowed_codes: set[int] | None = None) -> tuple[int, dict[str, Any]]:
    allowed_codes = allowed_codes or {0}
    process = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=300, check=False)
    if process.returncode not in allowed_codes:
        detail = (process.stderr or process.stdout).strip()
        raise RunnerError(f"command failed with exit {process.returncode}: {detail[-1000:]}")
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RunnerError(f"command did not return JSON: {process.stdout[-1000:]}") from exc
    if not isinstance(payload, dict):
        raise RunnerError("command JSON result must be an object")
    return process.returncode, payload


def _runtime_path(root: Path, manifest: dict[str, Any]) -> Path:
    runtime = manifest["runtime"]
    return root / "runtime" / runtime["filename"]


def prepare_writer(root: Path, workspace: Path, controller: str, assertion: str) -> dict[str, Any]:
    manifest, _ = require_verified_kit(root)
    controller = controller.strip()
    assertion = assertion.strip()
    if not controller or not assertion:
        raise RunnerError("controller and controller assertion are required")
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RunnerError("writer-trial workspace must be new or empty")
    workspace.mkdir(parents=True, exist_ok=True)
    runtime_root = _safe_extract_runtime(_runtime_path(root, manifest), workspace / "runtime-extracted")
    project = workspace / "neutral-project"
    project.mkdir()
    (project / ".forgeignore").write_text("Emotivus-Forge/\nprotocol/\n", encoding="utf-8")
    (project / "index.php").write_text("<?php echo 'neutral-before-writer';\n", encoding="utf-8")
    (project / "BACKLOG.md").write_text(
        "# Portable neutral trial\n\n## The next action\n\n- Detect an external mutation after a passing checkpoint.\n",
        encoding="utf-8",
    )
    shutil.copytree(runtime_root, project / "Emotivus-Forge")
    runtime_forge = project / "Emotivus-Forge" / "forge.py"
    objective = "Detect and refuse a separately executed mutation after a passing checkpoint."
    _run_json(
        [sys.executable, str(runtime_forge), "adopt", str(project), "--confirm-objective", objective,
         "--objective-source", "BACKLOG.md", "--json"],
        cwd=project,
    )
    check_returncode, observed = _run_json(
        [sys.executable, str(runtime_forge), "check", str(project), "--json"],
        cwd=project,
        allowed_codes={1},
    )
    if check_returncode != 1 or observed.get("status") != "NOT_RUN":
        raise RunnerError(
            "the neutral writer trial must begin with an unbaselined NOT_RUN observation before authority is recorded"
        )
    fingerprint = str(observed.get("authority_baseline", {}).get("current_fingerprint", ""))
    if len(fingerprint) != 64:
        raise RunnerError("the unbaselined observation did not report one exact tree fingerprint")
    _run_json(
        [
            sys.executable,
            str(runtime_forge),
            "adopt",
            str(project),
            "--authorize-baseline",
            fingerprint,
            "--baseline-reason",
            "Controller reviewed the exact neutral pre-writer tree for this bounded trial.",
            "--json",
        ],
        cwd=project,
    )
    _, checkpoint = _run_json(
        [sys.executable, str(runtime_forge), "check", str(project), "--checkpoint", "--json"],
        cwd=project,
    )
    if checkpoint.get("status") != "PASS":
        raise RunnerError(f"checkpoint did not pass after explicit authority: {checkpoint.get('reason', checkpoint.get('status'))}")
    target = project / "index.php"
    (workspace / "protocol").mkdir(parents=True, exist_ok=True)
    (workspace / "protocol" / "target-before.bin").write_bytes(target.read_bytes())
    plan = {
        "schema": WRITER_PLAN_SCHEMA,
        "status": "READY_FOR_WRITER",
        "created_utc": utc_now(),
        "kit_id": manifest["kit_id"],
        "forge_version": manifest["forge_version"],
        "runtime_sha256": manifest["runtime"]["sha256"],
        "runtime_bytes": manifest["runtime"]["bytes"],
        "challenge": secrets.token_hex(24),
        "controller": controller,
        "controller_assertion": assertion,
        "controller_environment": environment_record(),
        "project_relative": "neutral-project",
        "target_relative": "index.php",
        "target_before_sha256": sha256_file(target),
        "pre_authority_check_status": observed.get("status"),
        "authority_fingerprint": fingerprint,
        "checkpoint_status": checkpoint.get("status"),
        "checkpoint_workspace_fingerprint": checkpoint.get("workspace_integrity", {}).get(
            "observed_fingerprint", checkpoint.get("checkpoint", {}).get("fingerprint", "")
        ),
        "evidence_status": "NOT_RUN",
        "release_authorized": False,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }
    write_json(workspace / "protocol" / "plan.json", plan)
    result = {
        "status": "READY_FOR_WRITER",
        "workspace": str(workspace),
        "plan": str(workspace / "protocol" / "plan.json"),
        "target": str(target),
        "kit_id": manifest["kit_id"],
        "next_action": "A separately invoked writer must run the writer step.",
        "evidence_status": "NOT_RUN",
        "release_authorized": False,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }
    write_json(workspace / "protocol" / "prepare-result.json", result)
    return result


def run_writer(workspace: Path, writer: str, assertion: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    plan = read_json(workspace / "protocol" / "plan.json")
    if plan.get("schema") != WRITER_PLAN_SCHEMA or plan.get("status") != "READY_FOR_WRITER":
        raise RunnerError("writer trial plan is not ready for the writer step")
    writer = writer.strip()
    assertion = assertion.strip()
    if not writer or not assertion:
        raise RunnerError("writer and writer assertion are required")
    target = workspace / str(plan["project_relative"]) / str(plan["target_relative"])
    if not target.is_file() or sha256_file(target) != plan.get("target_before_sha256"):
        raise RunnerError("writer target does not match the checkpoint-bound pre-mutation bytes")
    content = f"<?php echo 'portable-writer-{str(plan['challenge'])[:16]}';\n"
    before = sha256_file(target)
    target.write_text(content, encoding="utf-8")
    after = sha256_file(target)
    if after == before:
        raise RunnerError("writer mutation did not change the target digest")
    (workspace / "protocol" / "target-after.bin").write_bytes(target.read_bytes())
    receipt = {
        "schema": WRITER_STEP_SCHEMA,
        "status": "MUTATION_COMPLETE",
        "completed_utc": utc_now(),
        "kit_id": plan["kit_id"],
        "forge_version": plan["forge_version"],
        "runtime_sha256": plan["runtime_sha256"],
        "challenge": plan["challenge"],
        "writer": writer,
        "writer_assertion": assertion,
        "writer_environment": environment_record(),
        "target_relative": plan["target_relative"],
        "target_before_sha256": before,
        "target_after_sha256": after,
        "evidence_status": "CANDIDATE",
        "release_authorized": False,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }
    write_json(workspace / "protocol" / "writer-step.json", receipt)
    return receipt


def finish_writer(workspace: Path, reviewer: str, accepted: bool) -> dict[str, Any]:
    workspace = workspace.resolve()
    plan = read_json(workspace / "protocol" / "plan.json")
    writer = read_json(workspace / "protocol" / "writer-step.json")
    if plan.get("schema") != WRITER_PLAN_SCHEMA or writer.get("schema") != WRITER_STEP_SCHEMA:
        raise RunnerError("writer protocol files use an unsupported schema")
    for key in ("kit_id", "forge_version", "runtime_sha256", "challenge"):
        if writer.get(key) != plan.get(key):
            raise RunnerError(f"writer receipt {key} differs from the controller plan")
    target = workspace / str(plan["project_relative"]) / str(plan["target_relative"])
    if not target.is_file() or sha256_file(target) != writer.get("target_after_sha256"):
        raise RunnerError("writer target no longer matches the writer receipt")
    reviewer = reviewer.strip()
    if not reviewer:
        raise RunnerError("a named reviewer is required")
    project = workspace / str(plan["project_relative"])
    runtime_forge = project / "Emotivus-Forge" / "forge.py"
    returncode, ship = _run_json(
        [sys.executable, str(runtime_forge), "ship", str(project), "--json"],
        cwd=project,
        allowed_codes={0, 1},
    )
    write_json(workspace / "protocol" / "ship-result.json", ship)
    workspace_status = str(ship.get("workspace_integrity", {}).get("status", "UNKNOWN"))
    detector_passed = returncode == 1 and workspace_status == "DRIFTED" and ship.get("release_ready") is False
    controller_pid = plan.get("controller_environment", {}).get("process_id")
    writer_pid = writer.get("writer_environment", {}).get("process_id")
    distinct_invocations = bool(controller_pid and writer_pid and controller_pid != writer_pid)
    distinct_named_operators = str(plan.get("controller", "")) != str(writer.get("writer", ""))
    reviewed_candidate = detector_passed and accepted and distinct_invocations and distinct_named_operators
    receipt = {
        "schema": WRITER_RECEIPT_SCHEMA,
        "status": "PASS" if detector_passed else "FAIL",
        "completed_utc": utc_now(),
        "kit_id": plan["kit_id"],
        "forge_version": plan["forge_version"],
        "runtime_sha256": plan["runtime_sha256"],
        "runtime_bytes": plan["runtime_bytes"],
        "challenge": plan["challenge"],
        "controller": {
            "name": plan["controller"],
            "assertion": plan["controller_assertion"],
            "environment": plan["controller_environment"],
        },
        "writer": {
            "name": writer["writer"],
            "assertion": writer["writer_assertion"],
            "environment": writer["writer_environment"],
        },
        "review": {"reviewer": reviewer, "accepted": accepted},
        "separation": {
            "distinct_process_invocations_observed": distinct_invocations,
            "distinct_named_operators_asserted": distinct_named_operators,
            "administrative_independence_authenticated": False,
            "another_operating_system_required_by_protocol": True,
        },
        "mutation": {
            "target_relative": plan["target_relative"],
            "before_sha256": writer["target_before_sha256"],
            "after_sha256": writer["target_after_sha256"],
        },
        "forge_result": {
            "ship_returncode": returncode,
            "workspace_integrity_status": workspace_status,
            "release_ready": ship.get("release_ready"),
            "reason": ship.get("reason", ""),
        },
        "candidate_classification": "REVIEWED-CANDIDATE" if reviewed_candidate else "INADMISSIBLE",
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }
    write_json(workspace / "protocol" / "independent-writer-receipt.json", receipt)
    return receipt


def _benchmark_prompt(task: dict[str, Any], *, arm: str, runtime: dict[str, Any]) -> str:
    content = task["content"]
    intro = (
        "Use the exact Forge runtime in this kit before beginning the task. Run Forge from the isolated arm workspace."
        if arm == "forge"
        else "Do not use Forge, Forge state, or Forge-generated continuity material in this isolated control arm."
    )
    criteria = "\n".join(f"- {item}" for item in content["success_criteria"])
    return f"""# Matched handoff arm — {arm}

{intro}

## Exact parent runtime

- SHA-256: `{runtime['sha256']}`
- Bytes: `{runtime['bytes']}`
- Version: `{runtime['version']}`

## Task

{content['instruction']}

## Success criteria

{criteria}

## Turn budget

{content['turns']}

After the run, copy provider-reported exact input and output token counts into the arm JSON file.
A named human reviewer must set `accepted` to true only after reviewing the work against every criterion.
"""


def prepare_benchmark(root: Path, output_dir: Path, provider: str, model: str) -> dict[str, Any]:
    manifest, _ = require_verified_kit(root)
    provider = provider.strip()
    model = model.strip()
    if not provider or not model:
        raise RunnerError("provider and model are required")
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RunnerError("benchmark output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    task_path = root / str(manifest["benchmark_task"]["path"])
    task = read_json(task_path)
    runtime = manifest["runtime"]
    forge_workspace = (output_dir / "forge-arm-workspace").resolve()
    control_workspace = (output_dir / "control-arm-workspace").resolve()
    forge_workspace.mkdir()
    control_workspace.mkdir()
    base = {
        "task_id": task["task_id"],
        "parent_sha256": runtime["sha256"],
        "provider": provider,
        "model": model,
        "exact_input_tokens": None,
        "exact_output_tokens": None,
        "exact_cost": None,
        "token_source": "provider-reported",
        "human_review": {"reviewer": "", "accepted": False},
    }
    forge_run = {**base, "arm": "forge", "workspace": str(forge_workspace)}
    control_run = {**base, "arm": "control", "workspace": str(control_workspace)}
    packet = {
        "schema": BENCHMARK_PACKET_SCHEMA,
        "status": "NOT_RUN",
        "created_utc": utc_now(),
        "kit_id": manifest["kit_id"],
        "forge_version": manifest["forge_version"],
        "runtime": runtime,
        "task": task,
        "provider": provider,
        "model": model,
        "arms": {
            "forge": {"workspace": str(forge_workspace), "run_record": "forge-run.json"},
            "control": {"workspace": str(control_workspace), "run_record": "control-run.json"},
        },
        "evidence_status": "NOT_RUN",
        "release_authorized": False,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }
    write_json(output_dir / "packet.json", packet)
    write_json(output_dir / "forge-run.json", forge_run)
    write_json(output_dir / "control-run.json", control_run)
    (output_dir / "FORGE-ARM.md").write_text(_benchmark_prompt(task, arm="forge", runtime=runtime), encoding="utf-8")
    (output_dir / "CONTROL-ARM.md").write_text(_benchmark_prompt(task, arm="control", runtime=runtime), encoding="utf-8")
    return {
        "status": "NOT_RUN",
        "packet_dir": str(output_dir),
        "kit_id": manifest["kit_id"],
        "task_id": task["task_id"],
        "provider": provider,
        "model": model,
        "next_action": "Run both isolated arms, enter exact provider tokens and named accepted review, then finalize.",
        "release_authorized": False,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }


def _load_benchmark_module(root: Path, manifest: dict[str, Any]):
    runtime_zip = _runtime_path(root, manifest)
    temporary = tempfile.TemporaryDirectory()
    extracted = Path(temporary.name)
    runtime_root = _safe_extract_runtime(runtime_zip, extracted / "runtime")
    sys.path.insert(0, str(runtime_root))
    try:
        from emotivus_forge.core import continuity_benchmark
    except Exception:
        temporary.cleanup()
        raise
    return continuity_benchmark, temporary, runtime_root


def finalize_benchmark(root: Path, packet_dir: Path) -> dict[str, Any]:
    manifest, _ = require_verified_kit(root)
    packet_dir = packet_dir.resolve()
    packet = read_json(packet_dir / "packet.json")
    if packet.get("schema") != BENCHMARK_PACKET_SCHEMA or packet.get("status") != "NOT_RUN":
        raise RunnerError("benchmark packet is not an unexecuted supported packet")
    if packet.get("kit_id") != manifest.get("kit_id"):
        raise RunnerError("benchmark packet was created by a different evidence kit")
    if packet.get("runtime", {}).get("sha256") != manifest.get("runtime", {}).get("sha256"):
        raise RunnerError("benchmark packet runtime differs from the current kit")
    forge_raw = read_json(packet_dir / "forge-run.json")
    control_raw = read_json(packet_dir / "control-run.json")
    expected = {
        "task_id": packet["task"]["task_id"],
        "parent_sha256": packet["runtime"]["sha256"],
        "provider": packet["provider"],
        "model": packet["model"],
    }
    for label, raw, arm in (("forge", forge_raw, "forge"), ("control", control_raw, "control")):
        for key, value in expected.items():
            if raw.get(key) != value:
                raise RunnerError(f"{label} run {key} differs from the sealed packet")
        if raw.get("arm") != arm:
            raise RunnerError(f"{label} run arm differs from the sealed packet")
        expected_workspace = packet["arms"][arm]["workspace"]
        if raw.get("workspace") != expected_workspace:
            raise RunnerError(f"{label} run workspace differs from the sealed packet")
    module, temporary, runtime_root = _load_benchmark_module(root, manifest)
    try:
        if not module.verify_task_immutable(packet["task"]):
            raise RunnerError("benchmark packet task identity is stale")
        runs = [module.record_run(forge_raw), module.record_run(control_raw)]
        comparison = module.compare_arms(runs)
    finally:
        try:
            sys.path.remove(str(runtime_root))
        except ValueError:
            pass
        temporary.cleanup()
    if comparison.get("status") != "PAIRED":
        raise RunnerError(f"benchmark arms are not admissibly paired: {comparison}")
    if comparison.get("workspace_isolation", {}).get("isolated") is not True:
        raise RunnerError("benchmark arm workspaces are not isolated")
    result = {
        "schema": BENCHMARK_RESULT_SCHEMA,
        "status": "PAIRED",
        "completed_utc": utc_now(),
        "kit_id": manifest["kit_id"],
        "forge_version": manifest["forge_version"],
        "runtime_sha256": manifest["runtime"]["sha256"],
        "task_id": packet["task"]["task_id"],
        "provider": packet["provider"],
        "model": packet["model"],
        "comparison": comparison,
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "truth_boundary": RUNNER_TRUTH_BOUNDARY,
    }
    write_json(packet_dir / "comparison.json", result)
    return result



def _return_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def _kit_archive_identity(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise RunnerError("original evidence kit archive must be one regular ZIP file")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise RunnerError("original evidence kit archive contains duplicate members")
        for name in names:
            normalized = name.replace("\\", "/")
            if normalized.startswith("/") or ".." in PurePosixPath(normalized).parts:
                raise RunnerError("original evidence kit archive contains unsafe members")
        manifests = [info for info in infos if not info.is_dir() and PurePosixPath(info.filename).name == "MANIFEST.json"]
        if len(manifests) != 1:
            raise RunnerError("original evidence kit archive must contain one MANIFEST.json")
        archived = json.loads(archive.read(manifests[0]).decode("utf-8"))
        member_count = sum(1 for info in infos if not info.is_dir())
    if not isinstance(archived, dict) or archived.get("kit_id") != manifest.get("kit_id"):
        raise RunnerError("original evidence kit archive differs from the extracted kit")
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "member_count": member_count,
        "kit_id": manifest["kit_id"],
        "forge_version": manifest["forge_version"],
        "schema": manifest["schema"],
    }


def _scan_return_sources(paths: list[Path]) -> None:
    for path in paths:
        lower = path.name.lower()
        if any(token in lower for token in ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".p12", ".pfx", ".key", "private-key")) and "public-key" not in lower:
            raise RunnerError(f"private-key-like file is forbidden in returned evidence: {path.name}")
        content = path.read_bytes()
        if any(marker in content for marker in (
            b"-----BEGIN " + b"PRIVATE KEY-----", b"-----BEGIN RSA " + b"PRIVATE KEY-----",
            b"-----BEGIN EC " + b"PRIVATE KEY-----", b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
            b"-----BEGIN ENCRYPTED " + b"PRIVATE KEY-----",
        )):
            raise RunnerError(f"private-key material is forbidden in returned evidence: {path.name}")


def _write_return_bundle(
    output: Path,
    *,
    manifest: dict[str, Any],
    payload_bytes: dict[str, bytes],
) -> dict[str, Any]:
    root_name = f"Forge-Evidence-Return-{manifest['kit']['forge_version']}-{manifest['kind']}"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, content in sorted(payload_bytes.items()):
            archive.writestr(_return_zip_info(f"{root_name}/{relative}"), content)
        archive.writestr(_return_zip_info(f"{root_name}/MANIFEST.json"), pretty_bytes(manifest))
    temporary.replace(output)
    return {
        "status": "PASS",
        "kind": manifest["kind"],
        "return_id": manifest["return_id"],
        "output": str(output),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "truth_boundary": manifest["truth_boundary"],
    }


def package_writer_return(root: Path, workspace: Path, kit_archive: Path, output: Path) -> dict[str, Any]:
    manifest, _ = require_verified_kit(root)
    workspace = workspace.resolve()
    protocol = workspace / "protocol"
    mapping = {
        "writer/plan.json": protocol / "plan.json",
        "writer/writer-step.json": protocol / "writer-step.json",
        "writer/independent-writer-receipt.json": protocol / "independent-writer-receipt.json",
        "writer/ship-result.json": protocol / "ship-result.json",
        "writer/target-before.bin": protocol / "target-before.bin",
        "writer/target-after.bin": protocol / "target-after.bin",
    }
    missing = [relative for relative, path in mapping.items() if not path.is_file()]
    if missing:
        raise RunnerError(f"writer return is missing required files: {missing}")
    _scan_return_sources(list(mapping.values()))
    plan = read_json(protocol / "plan.json")
    step = read_json(protocol / "writer-step.json")
    receipt = read_json(protocol / "independent-writer-receipt.json")
    ship = read_json(protocol / "ship-result.json")
    if receipt.get("status") != "PASS" or receipt.get("candidate_classification") != "REVIEWED-CANDIDATE":
        raise RunnerError("writer return requires one reviewed passing candidate")
    if receipt.get("kit_id") != manifest.get("kit_id") or plan.get("kit_id") != manifest.get("kit_id"):
        raise RunnerError("writer return belongs to a different evidence kit")
    if ship.get("workspace_integrity", {}).get("status") != "DRIFTED" or ship.get("release_ready") is not False:
        raise RunnerError("writer return does not preserve the required DRIFTED Ship refusal")
    before = (protocol / "target-before.bin").read_bytes()
    after = (protocol / "target-after.bin").read_bytes()
    if sha256_bytes(before) != plan.get("target_before_sha256") or sha256_bytes(after) != step.get("target_after_sha256") or before == after:
        raise RunnerError("writer return target identities differ")
    payload_bytes = {relative: path.read_bytes() for relative, path in mapping.items()}
    payloads = [{"path": name, "sha256": sha256_bytes(content), "bytes": len(content)} for name, content in sorted(payload_bytes.items())]
    truth = (
        "This return bundle preserves one reviewed local writer candidate against one exact runtime. "
        "It does not authenticate operator identities or administrative independence, prove another "
        "operating system, authorize release, or establish release readiness."
    )
    core = {
        "schema": RETURN_SCHEMA,
        "kind": "independent-writer",
        "kit": _kit_archive_identity(kit_archive, manifest),
        "subject": {"challenge": plan["challenge"], "runtime_sha256": manifest["runtime"]["sha256"]},
        "workflow_status": "PASS",
        "claim_scope": "one-exact-runtime-post-checkpoint-drift-candidate",
        "payloads": payloads,
        "owner_identity_authenticated": False,
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "truth_boundary": truth,
    }
    return _write_return_bundle(output, manifest={**core, "return_id": sha256_bytes(canonical_bytes(core))}, payload_bytes=payload_bytes)


def package_benchmark_return(root: Path, packet_dir: Path, kit_archive: Path, output: Path) -> dict[str, Any]:
    manifest, _ = require_verified_kit(root)
    packet_dir = packet_dir.resolve()
    mapping = {
        "benchmark/packet.json": packet_dir / "packet.json",
        "benchmark/forge-run.json": packet_dir / "forge-run.json",
        "benchmark/control-run.json": packet_dir / "control-run.json",
        "benchmark/comparison.json": packet_dir / "comparison.json",
    }
    missing = [relative for relative, path in mapping.items() if not path.is_file()]
    if missing:
        raise RunnerError(f"benchmark return is missing required files: {missing}")
    _scan_return_sources(list(mapping.values()))
    packet = read_json(packet_dir / "packet.json")
    forge_raw = read_json(packet_dir / "forge-run.json")
    control_raw = read_json(packet_dir / "control-run.json")
    result = read_json(packet_dir / "comparison.json")
    if packet.get("kit_id") != manifest.get("kit_id") or result.get("kit_id") != manifest.get("kit_id"):
        raise RunnerError("benchmark return belongs to a different evidence kit")
    module, temporary, runtime_root = _load_benchmark_module(root, manifest)
    try:
        if not module.verify_task_immutable(packet.get("task", {})):
            raise RunnerError("benchmark return task identity is stale")
        comparison = module.compare_arms([module.record_run(forge_raw), module.record_run(control_raw)])
    finally:
        try:
            sys.path.remove(str(runtime_root))
        except ValueError:
            pass
        temporary.cleanup()
    if comparison.get("status") != "PAIRED" or result.get("comparison") != comparison:
        raise RunnerError("benchmark return does not contain one exact recomputable paired result")
    payload_bytes = {relative: path.read_bytes() for relative, path in mapping.items()}
    payloads = [{"path": name, "sha256": sha256_bytes(content), "bytes": len(content)} for name, content in sorted(payload_bytes.items())]
    subject_core = {
        "task_id": packet["task"]["task_id"],
        "runtime_sha256": manifest["runtime"]["sha256"],
        "provider": packet["provider"],
        "model": packet["model"],
    }
    truth = (
        "This return bundle preserves one exact paired benchmark sample with named accepted review and "
        "provider-reported token assertions. It does not authenticate the provider report or reviewer, "
        "prove operator independence, generalize the sample, authorize release, or establish release readiness."
    )
    core = {
        "schema": RETURN_SCHEMA,
        "kind": "matched-handoff",
        "kit": _kit_archive_identity(kit_archive, manifest),
        "subject": {**subject_core, "subject_id": sha256_bytes(canonical_bytes(subject_core))},
        "workflow_status": "PAIRED",
        "claim_scope": "one-exact-task-provider-model-paired-sample",
        "payloads": payloads,
        "owner_identity_authenticated": False,
        "independent_evidence_claimed": False,
        "release_authorized": False,
        "truth_boundary": truth,
    }
    return _write_return_bundle(output, manifest={**core, "return_id": sha256_bytes(canonical_bytes(core))}, payload_bytes=payload_bytes)

def _print(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify")

    prepare = subparsers.add_parser("prepare-writer")
    prepare.add_argument("--workspace", required=True)
    prepare.add_argument("--controller", required=True)
    prepare.add_argument("--controller-assertion", required=True)

    writer = subparsers.add_parser("writer")
    writer.add_argument("--workspace", required=True)
    writer.add_argument("--writer", required=True)
    writer.add_argument("--writer-assertion", required=True)

    finish = subparsers.add_parser("finish-writer")
    finish.add_argument("--workspace", required=True)
    finish.add_argument("--reviewer", required=True)
    finish.add_argument("--accepted", action="store_true")

    benchmark = subparsers.add_parser("prepare-benchmark")
    benchmark.add_argument("--output-dir", required=True)
    benchmark.add_argument("--provider", required=True)
    benchmark.add_argument("--model", required=True)

    finalize = subparsers.add_parser("finalize-benchmark")
    finalize.add_argument("--packet-dir", required=True)

    writer_return = subparsers.add_parser("package-writer-return")
    writer_return.add_argument("--workspace", required=True)
    writer_return.add_argument("--kit-archive", required=True)
    writer_return.add_argument("--output", required=True)

    benchmark_return = subparsers.add_parser("package-benchmark-return")
    benchmark_return.add_argument("--packet-dir", required=True)
    benchmark_return.add_argument("--kit-archive", required=True)
    benchmark_return.add_argument("--output", required=True)

    args = parser.parse_args()
    try:
        root = kit_root_from_script()
        if args.command == "verify":
            result = verify_extracted_kit(root)
        elif args.command == "prepare-writer":
            result = prepare_writer(root, Path(args.workspace), args.controller, args.controller_assertion)
        elif args.command == "writer":
            result = run_writer(Path(args.workspace), args.writer, args.writer_assertion)
        elif args.command == "finish-writer":
            result = finish_writer(Path(args.workspace), args.reviewer, args.accepted)
        elif args.command == "prepare-benchmark":
            result = prepare_benchmark(root, Path(args.output_dir), args.provider, args.model)
        elif args.command == "finalize-benchmark":
            result = finalize_benchmark(root, Path(args.packet_dir))
        elif args.command == "package-writer-return":
            result = package_writer_return(root, Path(args.workspace), Path(args.kit_archive), Path(args.output))
        elif args.command == "package-benchmark-return":
            result = package_benchmark_return(root, Path(args.packet_dir), Path(args.kit_archive), Path(args.output))
        else:  # pragma: no cover - argparse enforces this boundary.
            raise RunnerError(f"unsupported command: {args.command}")
        _print(result)
        return 0 if result.get("status") not in {"FAIL"} else 1
    except (ValueError, OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        _print({"status": "FAIL", "error": str(exc), "truth_boundary": RUNNER_TRUTH_BOUNDARY})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

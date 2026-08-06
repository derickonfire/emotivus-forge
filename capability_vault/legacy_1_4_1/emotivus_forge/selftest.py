from __future__ import annotations

import ast
import hashlib
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .utils import utc_now, write_json

RUNTIME_DIR = Path("self/.runtime")
STATE_FILE = RUNTIME_DIR / "self-test-progress.json"
LATEST_FILE = RUNTIME_DIR / "self-test-latest.json"
LOCK_ROOT_NAME = "emotivus-forge-runtime"
BUDGET_CLEANUP_RESERVE_SECONDS = 2.0
MIN_SHARD_START_SECONDS = 5.0
_ACTIVE_PROCESS: subprocess.Popen[str] | None = None


@dataclass(frozen=True)
class TestShard:
    shard_id: str
    suite_id: str
    command: tuple[str, ...]
    timeout: int


@dataclass
class ShardResult:
    shard_id: str
    suite_id: str
    status: str
    returncode: int | None
    duration_seconds: float
    started_utc: str
    finished_utc: str
    output: str
    timeout_seconds: int
    resumed: bool = False
    reason: str = ""


def _source_fingerprint(forge_root: Path) -> str:
    """Fingerprint the self-test authority without depending on Git."""
    digest = hashlib.sha256()
    excluded_parts = {"__pycache__", ".runtime", ".forge", "deploy", ".git"}
    included_suffixes = {".py", ".json", ".md", ".toml", ".ini"}
    for path in sorted(forge_root.rglob("*")):
        if not path.is_file() or any(part in excluded_parts for part in path.relative_to(forge_root).parts):
            continue
        if path.suffix.lower() not in included_suffixes and path.name not in {"forge", "forge.cmd"}:
            continue
        relative = path.relative_to(forge_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


def discover_unittest_methods(path: Path) -> dict[str, list[str]]:
    """Return concrete unittest.TestCase methods in deterministic source order."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    discovered: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_case = any(
            (isinstance(base, ast.Name) and base.id == "TestCase")
            or (isinstance(base, ast.Attribute) and base.attr == "TestCase")
            for base in node.bases
        )
        if not is_case:
            continue
        methods = [
            child.name for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_")
        ]
        if methods:
            discovered[node.name] = methods
    return discovered


def discover_unittest_classes(path: Path) -> list[str]:
    """Return concrete unittest.TestCase class names in source order."""
    return list(discover_unittest_methods(path))


def build_shards(forge_root: Path, manifest: dict[str, Any], *, only: list[str] | None = None, per_shard_timeout: int | None = None) -> list[TestShard]:
    suites = manifest.get("self_tests", [])
    if not isinstance(suites, list) or not suites:
        raise RuntimeError("no self-test suites are declared")
    filters = [item.strip() for item in (only or []) if item.strip()]
    shards: list[TestShard] = []
    for raw in suites:
        if not isinstance(raw, dict):
            raise RuntimeError("malformed self-test entry")
        suite_id = str(raw.get("id", "unnamed"))
        timeout = int(per_shard_timeout or raw.get("timeout", 90))
        mode = str(raw.get("mode", "command"))
        if mode == "unittest-class-shards":
            source = forge_root / str(raw.get("path", ""))
            module = str(raw.get("module", "")).strip()
            if not source.is_file() or not module:
                raise RuntimeError(f"self-test suite {suite_id} has an invalid unittest shard declaration")
            methods_per_shard = max(1, int(raw.get("methods_per_shard", 8)))
            for class_name, methods in discover_unittest_methods(source).items():
                chunks = [methods[index:index + methods_per_shard] for index in range(0, len(methods), methods_per_shard)]
                for chunk_index, chunk in enumerate(chunks, start=1):
                    suffix = "" if len(chunks) == 1 else f"[{chunk_index}/{len(chunks)}]"
                    shard_id = f"{suite_id}:{class_name}{suffix}"
                    if filters and not any(shard_id.startswith(prefix) or class_name.startswith(prefix) for prefix in filters):
                        continue
                    targets = tuple(f"{module}.{class_name}.{method}" for method in chunk)
                    shards.append(TestShard(
                        shard_id=shard_id,
                        suite_id=suite_id,
                        command=(sys.executable, "-m", "emotivus_forge.test_shard_runner", *targets),
                        timeout=timeout,
                    ))
            continue
        command = raw.get("command")
        if not isinstance(command, list) or not command:
            raise RuntimeError(f"self-test suite {suite_id} has no command")
        resolved = []
        for item in command:
            value = str(item).replace("{python}", sys.executable).replace("{forge}", str(forge_root)).replace("{project}", str(forge_root))
            resolved.append(value)
        if filters and not any(suite_id.startswith(prefix) for prefix in filters):
            continue
        shards.append(TestShard(suite_id, suite_id, tuple(resolved), timeout))
    if filters and not shards:
        raise RuntimeError("--only filters matched no self-test shards")
    if not shards:
        raise RuntimeError("self-test declaration produced no shards")
    return shards


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def _run_shard(shard: TestShard, forge_root: Path, *, effective_timeout: float, budget_limited: bool) -> ShardResult:
    global _ACTIVE_PROCESS
    started_utc = utc_now()
    started = time.monotonic()
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    kwargs: dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {"creationflags": creationflags}
    process: subprocess.Popen[str] | None = None
    status = "ERROR"
    reason = "startup"
    returncode: int | None = None
    output = ""
    # A regular temporary file is intentional. PIPE + communicate can outlive
    # the shard when a detached descendant inherits stdout. Reading a regular
    # file never waits for every descendant to close its inherited descriptor.
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as capture:
        try:
            process = subprocess.Popen(
                list(shard.command), cwd=forge_root, text=True,
                stdout=capture, stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                **kwargs,
            )
            _ACTIVE_PROCESS = process
        except OSError as exc:
            output = str(exc)
        else:
            try:
                returncode = process.wait(timeout=max(0.1, effective_timeout))
                status = "PASS" if returncode == 0 else "FAIL"
                reason = ""
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process)
                returncode = process.poll()
                status = "BUDGET_EXPIRED" if budget_limited else "TIMEOUT"
                reason = "overall-budget" if budget_limited else "shard-timeout"
            finally:
                if _ACTIVE_PROCESS is process:
                    _ACTIVE_PROCESS = None
            capture.flush()
            capture.seek(0)
            output = capture.read()
    return ShardResult(
        shard.shard_id, shard.suite_id, status, returncode,
        round(time.monotonic() - started, 3), started_utc, utc_now(), output.rstrip(),
        shard.timeout, reason=reason,
    )



def _scope_id(only: list[str] | None) -> str:
    filters = sorted(item.strip() for item in (only or []) if item.strip())
    if not filters:
        return "full"
    digest = hashlib.sha256("\0".join(filters).encode("utf-8")).hexdigest()[:12]
    return f"only-{digest}"


def _state_path(forge_root: Path, only: list[str] | None) -> Path:
    scope = _scope_id(only)
    if scope == "full":
        return forge_root / STATE_FILE
    return forge_root / RUNTIME_DIR / f"self-test-progress-{scope}.json"


def _resume_command(only: list[str] | None) -> str:
    command = ["python3", "forge.py", "self-test", "--resume"]
    for item in (only or []):
        value = item.strip()
        if value:
            command.extend(["--only", value])
    return " ".join(command)


def _load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}




def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _run_lock_path(forge_root: Path) -> Path:
    key = hashlib.sha256(str(forge_root.resolve()).encode("utf-8")).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / LOCK_ROOT_NAME / f"self-test-{key}.runlock"


def _lock_owner_path(path: Path) -> Path:
    return path / "owner.json"


def _acquire_run_lock(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}-{time.time_ns()}"
    for _ in range(3):
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            owner = _lock_owner_path(path)
            existing = _load_state(owner)
            pid = int(existing.get("pid", 0) or 0)
            if pid and _pid_is_alive(pid):
                raise RuntimeError(
                    f"Forge self-test is already running as PID {pid}. "
                    "Wait for it to finish or stop that process before starting another run."
                )
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                continue
            if age < 5:
                raise RuntimeError("Forge self-test execution ownership is currently being initialized.")
            shutil.rmtree(path, ignore_errors=True)
            continue
        write_json(_lock_owner_path(path), {"pid": os.getpid(), "token": token, "started_utc": utc_now()})
        return token
    raise RuntimeError("could not acquire the Forge self-test execution lock")


def _release_run_lock(path: Path, token: str) -> None:
    owner = _lock_owner_path(path)
    existing = _load_state(owner)
    if existing.get("token") != token:
        return
    try:
        owner.unlink()
    except FileNotFoundError:
        pass
    try:
        path.rmdir()
    except (FileNotFoundError, OSError):
        pass


def _termination_handler(signum: int, _frame: Any) -> None:
    process = _ACTIVE_PROCESS
    if process is not None:
        _terminate_process_tree(process)
    raise SystemExit(128 + signum)


def _install_termination_handlers() -> dict[int, Any]:
    if threading.current_thread() is not threading.main_thread():
        return {}
    previous: dict[int, Any] = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, _termination_handler)
    return previous


def _restore_termination_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _run_self_tests_unlocked(
    forge_root: Path,
    *,
    resume: bool = False,
    fresh: bool = False,
    only: list[str] | None = None,
    budget_seconds: int = 0,
    per_shard_timeout: int | None = None,
    list_only: bool = False,
) -> dict[str, Any]:
    forge_root = forge_root.resolve()
    manifest_path = forge_root / "FORGE-MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read manifest: {exc}") from exc
    shards = build_shards(forge_root, manifest, only=only, per_shard_timeout=per_shard_timeout)
    if list_only:
        return {
            "schema": 1, "status": "LIST", "shards": [asdict(item) for item in shards],
            "total": len(shards),
        }

    runtime_dir = forge_root / RUNTIME_DIR
    runtime_dir.mkdir(parents=True, exist_ok=True)
    state_path = _state_path(forge_root, only)
    latest_path = forge_root / LATEST_FILE
    fingerprint = _source_fingerprint(forge_root)
    prior = {} if fresh or not resume else _load_state(state_path)
    prior_results = {
        str(item.get("shard_id")): item for item in prior.get("results", [])
        if isinstance(item, dict)
    } if prior.get("source_fingerprint") == fingerprint else {}

    started_utc = utc_now()
    started = time.monotonic()
    results: list[ShardResult] = []
    halt_reason = ""
    for index, shard in enumerate(shards, start=1):
        cached = prior_results.get(shard.shard_id)
        if cached and cached.get("status") == "PASS":
            results.append(ShardResult(
                shard.shard_id, shard.suite_id, "PASS", cached.get("returncode", 0),
                float(cached.get("duration_seconds", 0)), str(cached.get("started_utc", started_utc)),
                str(cached.get("finished_utc", started_utc)), str(cached.get("output", "")),
                shard.timeout, resumed=True,
            ))
            print(f"SELF-TEST {index}/{len(shards)} PASS (resumed) — {shard.shard_id}", flush=True)
            continue

        elapsed = time.monotonic() - started
        remaining_budget = float(budget_seconds) - elapsed if budget_seconds > 0 else None
        if remaining_budget is not None:
            usable_budget = remaining_budget - BUDGET_CLEANUP_RESERVE_SECONDS
            if usable_budget < MIN_SHARD_START_SECONDS:
                halt_reason = "overall-budget"
                break
        else:
            usable_budget = None
        effective_timeout = float(shard.timeout)
        budget_limited = False
        if usable_budget is not None and usable_budget < effective_timeout:
            effective_timeout = max(0.1, usable_budget)
            budget_limited = True

        print(f"SELF-TEST {index}/{len(shards)} RUN — {shard.shard_id}", flush=True)
        result = _run_shard(shard, forge_root, effective_timeout=effective_timeout, budget_limited=budget_limited)
        if result.status == "BUDGET_EXPIRED":
            halt_reason = "overall-budget"
            print(f"SELF-TEST {index}/{len(shards)} PAUSED — execution budget reached", flush=True)
            break
        results.append(result)
        print(f"SELF-TEST {index}/{len(shards)} {result.status} — {shard.shard_id} ({result.duration_seconds:.3f}s)", flush=True)

        payload = _payload(fingerprint, started_utc, shards, results, budget_seconds, halt_reason, only=only)
        write_json(state_path, payload)
        write_json(latest_path, payload)
        if result.status != "PASS":
            halt_reason = result.reason or result.status.lower()
            break

    payload = _payload(fingerprint, started_utc, shards, results, budget_seconds, halt_reason, only=only)
    write_json(state_path, payload)
    write_json(latest_path, payload)
    return payload


def run_self_tests(
    forge_root: Path,
    *,
    resume: bool = False,
    fresh: bool = False,
    only: list[str] | None = None,
    budget_seconds: int = 0,
    per_shard_timeout: int | None = None,
    list_only: bool = False,
) -> dict[str, Any]:
    forge_root = forge_root.resolve()
    if list_only:
        return _run_self_tests_unlocked(
            forge_root, resume=resume, fresh=fresh, only=only, budget_seconds=budget_seconds,
            per_shard_timeout=per_shard_timeout, list_only=True,
        )
    lock_path = _run_lock_path(forge_root)
    token = _acquire_run_lock(lock_path)
    previous_handlers = _install_termination_handlers()
    try:
        return _run_self_tests_unlocked(
            forge_root, resume=resume, fresh=fresh, only=only, budget_seconds=budget_seconds,
            per_shard_timeout=per_shard_timeout, list_only=False,
        )
    finally:
        process = _ACTIVE_PROCESS
        if process is not None:
            _terminate_process_tree(process)
        _restore_termination_handlers(previous_handlers)
        _release_run_lock(lock_path, token)


def _payload(
    fingerprint: str,
    started_utc: str,
    shards: list[TestShard],
    results: list[ShardResult],
    budget_seconds: int,
    halt_reason: str,
    *,
    only: list[str] | None = None,
) -> dict[str, Any]:
    by_id = {item.shard_id: item for item in results}
    matrix = []
    for shard in shards:
        result = by_id.get(shard.shard_id)
        matrix.append({
            "shard_id": shard.shard_id,
            "suite_id": shard.suite_id,
            "status": result.status if result else "NOT_RUN",
            "timeout_seconds": shard.timeout,
        })
    blocking = any(item.status in {"FAIL", "ERROR", "TIMEOUT"} for item in results)
    complete = len(results) == len(shards)
    status = "FAIL" if blocking else "PASS" if complete else "INCOMPLETE"
    passed = sum(1 for item in results if item.status == "PASS")
    return {
        "schema": 1,
        "status": status,
        "source_fingerprint": fingerprint,
        "started_utc": started_utc,
        "updated_utc": utc_now(),
        "budget_seconds": budget_seconds,
        "scope": {"id": _scope_id(only), "only": [item for item in (only or []) if item.strip()]},
        "halt_reason": halt_reason,
        "completed_count": len(results),
        "remaining_count": len(shards) - len(results),
        "passed_count": passed,
        "total_count": len(shards),
        "resume_command": _resume_command(only) if status == "INCOMPLETE" else "",
        "matrix": matrix,
        "results": [asdict(item) for item in results],
    }

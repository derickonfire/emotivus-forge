from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ..core.capabilities import public_capability_catalog
from ..core.guidance import build_help, render_help
from ..core.notices import render_notice
from ..core.paths import redirect_state
from ..core.resume import build_resume
from ..core.startup import render_run, resolve_project_root, run_forge
from ..core.storage import state_transaction
from ..services.ship import render_ship, ship_project
from .common import append_notice, print_json
from .noticing import attach_resume_notice, attach_run_notice


READ_ONLY_LIMITATIONS = (
    "Read-only consultation: Forge read the project bytes but wrote nothing into the "
    "project tree; any transient state was written to a disposable directory outside it "
    "and discarded. Advisory only, never acceptance evidence."
)


@contextmanager
def _read_only_state(target: Path) -> Iterator[None]:
    """Run a command against ``target`` while writing no state into its tree.

    The project's existing ``.forge`` (if any) is mirrored into a disposable
    directory outside both repositories so continuity/stale-evidence/handoff reads
    stay faithful, then every state write is redirected there and discarded.
    """
    target = target.resolve()
    tmp = Path(tempfile.mkdtemp(prefix="forge-readonly-"))
    try:
        source_state = target / ".forge"
        alt_state = tmp / ".forge"
        if source_state.is_dir():
            shutil.copytree(source_state, alt_state)
        with redirect_state(target, alt_state):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _mark_read_only(payload: Any) -> None:
    """Annotate the payload so the read-only, advisory-only bound is explicit."""
    if isinstance(payload, dict):
        payload["read_only"] = True
        payload["read_only_limitations"] = READ_ONLY_LIMITATIONS


def handle_run(args: Any, forge_root: Path) -> int:
    requested = Path(args.project)
    resolved, entries = resolve_project_root(requested, forge_root)
    if getattr(args, "read_only", False):
        # Bounded read-only consultation: no lock, no state written into the project.
        project = resolved if entries else requested
        with _read_only_state(project.resolve()):
            payload = run_forge(project, forge_root, budget=args.budget, session_context_path=getattr(args, "session_context", ""))
            attach_run_notice(payload, project if entries else None)
        _mark_read_only(payload)
        print_json(payload) if args.json else print(append_notice(render_run(payload), payload), end="")
        return 1 if payload.get("status") in {"BLOCKED", "NEEDS_PROJECT"} else 0
    if not entries:
        payload = run_forge(requested, forge_root, budget=args.budget, session_context_path=getattr(args, "session_context", ""))
    else:
        with state_transaction(resolved, validate_existing=(resolved / ".forge").is_dir()):
            payload = run_forge(resolved, forge_root, budget=args.budget, session_context_path=getattr(args, "session_context", ""))
            attach_run_notice(payload, resolved)
    if not isinstance(payload.get("ai_notice"), dict):
        attach_run_notice(payload, resolved if entries else None)
    print_json(payload) if args.json else print(append_notice(render_run(payload), payload), end="")
    return 1 if payload.get("status") in {"BLOCKED", "NEEDS_PROJECT"} else 0


def handle_help(args: Any, forge_root: Path) -> int:
    payload = build_help(Path(args.project), forge_root, args.topic)
    print_json(payload) if args.json else print(render_help(payload), end="")
    return 0


def handle_resume(args: Any, forge_root: Path) -> int:
    root = Path(args.project).resolve()
    if getattr(args, "read_only", False):
        with _read_only_state(root):
            payload = build_resume(root, forge_root, budget=args.budget, query=getattr(args, "query", ""))
            attach_resume_notice(payload, root)
        _mark_read_only(payload)
    else:
        with state_transaction(root):
            payload = build_resume(root, forge_root, budget=args.budget, query=getattr(args, "query", ""))
            attach_resume_notice(payload, root)
    print_json(payload) if args.json else print(append_notice(payload["markdown"], payload), end="")
    return 0


def handle_ship(args: Any, forge_root: Path) -> int:
    root = Path(args.project).resolve()
    payload = ship_project(root, forge_root)
    release_ready = payload.get("release_ready") is True
    # Ship is explicit and evidence-bounded; readiness and blockers must not share the same notice truth state.
    from ..core.notices import issue_notice
    payload["ai_notice"] = issue_notice(
        root if (root / ".forge").is_dir() else None,
        level="notice" if release_ready else "blocker",
        summary=str(payload.get("reason", "Ship readiness was assessed.")),
        category="ship",
        event_key="release-ready" if release_ready else str(payload.get("reason", "ship-blocked")),
        persist=(root / ".forge").is_dir(),
    )
    print_json(payload) if args.json else print(append_notice(render_ship(payload), payload), end="")
    return 0 if release_ready else 1


def handle_advanced(args: Any) -> int:
    root = Path(args.project).resolve()
    payload = public_capability_catalog(root)
    if args.json:
        print_json(payload)
    else:
        print(payload["message"])
        for item in payload.get("capabilities", []):
            if isinstance(item, dict):
                print(f"- {item.get('name')}: {item.get('status')} — {item.get('trigger')}")
    return 0


_SELF_TEST_CHILD = r"""
import os
import sys
import traceback
import unittest

code = 1
try:
    suite = unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
    code = 0 if result.wasSuccessful() else 1
except BaseException:
    traceback.print_exc()
finally:
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        # A completed unittest result is the certification boundary. Avoid an
        # interpreter-shutdown stall from a test-owned non-daemon thread; the
        # parent then clears any remaining descendants in this process group.
        os._exit(code)
"""


def _stop_self_test_group(process: subprocess.Popen[str], *, grace_seconds: float = 1.0) -> None:
    """Bounded cleanup for the isolated test process and every descendant."""
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        elif process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # The caller reports the timeout; cleanup itself must never become
            # a second unbounded wait.
            pass
    finally:
        if os.name != "nt":
            # The direct child may already have exited while a descendant
            # remains in its fresh group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def _run_self_test_module(module: str, forge_root: Path, environment: dict[str, str]) -> dict[str, Any]:
    command = [sys.executable, "-c", _SELF_TEST_CHILD, module]
    logged = ""
    result_code = 1
    timed_out = False
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=forge_root,
            env=environment,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
        try:
            result_code = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            timed_out = True
            _stop_self_test_group(process)
            result_code = 1
        else:
            _stop_self_test_group(process)
        log.flush()
        log.seek(0)
        logged = log.read()
    match = re.findall(r"Ran (\d+) tests?", logged)
    count = int(match[-1]) if match else 0
    detail = logged.strip().splitlines()[-1] if logged.strip() else f"exit {result_code}"
    return {
        "module": module,
        "count": count,
        "returncode": result_code,
        "timed_out": timed_out,
        "detail": detail,
    }


def handle_self_test(forge_root: Path) -> int:
    """Run focused regression modules in bounded fresh process groups."""
    test_dir = forge_root / "tests"
    modules = [f"tests.{path.stem}" for path in sorted(test_dir.glob("test_*.py"))]
    if not modules:
        print("Forge self-test: FAIL — no focused regression modules were found.")
        return 1

    environment = os.environ.copy()
    python_path = [str(test_dir), str(forge_root)]
    if environment.get("PYTHONPATH"):
        python_path.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_path)

    # Certification favors deterministic module isolation over parallel speed.
    # Several HTTP-heavy modules are individually safe but can interfere when
    # their child servers overlap. Run each module in a fresh process group,
    # report it immediately, and clean descendants before starting the next.
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    total = 0
    for module in modules:
        try:
            item = _run_self_test_module(module, forge_root, environment)
        except Exception as exc:  # defensive runner boundary
            item = {"module": module, "count": 0, "returncode": 1, "timed_out": False, "detail": str(exc)}
        results.append(item)
        total += int(item.get("count", 0))
        module = str(item.get("module", "unknown"))
        if item.get("timed_out"):
            failures.append(f"{module}: timed out after 300 seconds")
            print(f"FAIL {module} — timeout")
        elif int(item.get("returncode", 1)) != 0:
            detail = str(item.get("detail", "failed"))
            failures.append(f"{module}: {detail}")
            print(f"FAIL {module} — {detail}")
        else:
            print(f"PASS {module} — {int(item.get('count', 0))}")

    if failures:
        print(f"Forge self-test: FAIL — {total} regressions completed across {len(modules)} isolated modules.")
        for failure in failures:
            print(f"- {failure}")
        return 1
    from ..core.narrative_integrity import check_narrative_integrity
    narrative = check_narrative_integrity(forge_root, observed_regressions=total, observed_modules=len(modules))
    if narrative.get("status") != "PASS":
        print(f"Forge self-test: FAIL — {total} regressions passed, but narrative integrity failed.")
        for problem in narrative.get("problems", []):
            print(f"- {problem}")
        return 1
    print("PASS narrative-integrity — distribution relationships are current")
    print(f"Forge self-test: PASS — {total} focused regressions across {len(modules)} isolated modules.")
    return 0


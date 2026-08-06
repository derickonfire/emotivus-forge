from __future__ import annotations

import hashlib
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .config import load_config, save_config
from .detect import is_forge_project
from .graph import analyze_impact, build_graph
from .init_project import initialize_project
from .lab import plan_labs
from .runner import run_profile
from .tool_migration import scan_existing_tools
from .utils import utc_now, write_json

MIRROR_EXCLUDES = {".git", ".forge", "deploy", "__pycache__", ".venv", "venv"}


def _acquire_mirror_lock(source_root: Path, release_version: str) -> Path:
    lock_path = source_root / "deploy" / "mirror" / ".mirror.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pid": os.getpid(), "release_version": release_version, "started_utc": utc_now()}
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        try:
            existing = lock_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            existing = "unreadable"
        raise RuntimeError(f"another or interrupted Forge Mirror owns {lock_path}; review active processes and remove the lock deliberately. Existing lock: {existing}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.write("\n")
    return lock_path


def _release_mirror_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_source(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in MIRROR_EXCLUDES or name.endswith(".pyc")}
    shutil.copytree(source, destination, ignore=ignore)


def _run(command: list[str], cwd: Path, timeout: int = 1800) -> dict[str, Any]:
    log = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False, prefix="forge-mirror-command-", suffix=".log")
    log_path = Path(log.name)
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command, cwd=cwd, text=True, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        try:
            returncode = process.wait(timeout=timeout)
            status = "PASS" if returncode == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
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
        log.flush()
        log.seek(0)
        output = log.read()
        return {"command": command, "returncode": returncode, "status": status, "output": output[-30000:].rstrip()}
    except OSError as exc:
        return {"command": command, "returncode": None, "status": "RUNNER_ERROR", "output": str(exc)}
    finally:
        log.close()
        try:
            log_path.unlink()
        except OSError:
            pass


def _validate_archive_shape(archive_path: Path) -> list[str]:
    problems: list[str] = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"distribution archive unreadable: {exc}"]
    if len(names) != len(set(names)):
        problems.append("distribution archive contains duplicate paths")
    roots = {Path(name).parts[0] for name in names if Path(name).parts}
    if roots != {"Emotivus-Forge"}:
        problems.append(f"distribution archive must contain one Emotivus-Forge root; found {sorted(roots)}")
    forbidden = [name for name in names if any(part in {".forge", ".git", "deploy", "__pycache__"} for part in Path(name).parts)]
    if forbidden:
        problems.append(f"distribution contains forbidden internal paths: {forbidden[:10]}")
    return problems


def _write_text_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "EMOTIVUS FORGE MIRROR", "=" * 72,
        f"Status: {payload['status']}",
        f"Release: {payload['release_version']}",
        f"Baseline: {payload['baseline_version']}",
        f"Started: {payload['started_utc']}",
        f"Finished: {payload['finished_utc']}", "",
        "Stages", "------",
    ]
    for stage in payload["stages"]:
        lines.append(f"{stage['status']:<8} {stage['id']}")
        if stage.get("summary"):
            lines.append(f"         {stage['summary']}")
    if payload.get("problems"):
        lines.extend(["", "Problems", "--------"])
        lines.extend(f"- {item}" for item in payload["problems"])
    if payload.get("archive"):
        lines.extend(["", "Development distribution", "------------------------", f"Archive: {payload['archive']}", f"SHA-256: {payload.get('archive_sha256', '')}"])
    if payload.get("public_archive"):
        lines.extend(["", "Public distribution", "-------------------", f"Archive: {payload['public_archive']}", f"SHA-256: {payload.get('public_archive_sha256', '')}"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")



def configure_mirror_contract(config: dict[str, Any], baseline_version: str, release_version: str) -> dict[str, Any]:
    """Apply Forge's version-controlled self-hosting contract to an initialized config."""
    config["project"].update({"identity": "emotivus-forge-core", "self_hosting": True})
    config["versioning"].update({
        "enabled": True, "status": "release", "strategy": "semver",
        "baseline_version": baseline_version, "target_version": release_version,
        "package_version": release_version, "package_version_rule": "same",
        "source": {"path": "emotivus_forge/__init__.py", "regex": r"(?m)^__version__\s*=\s*[\"']([^\"']+)[\"']"},
    })
    config["learn"]["contracts_path"] = "self/learned-contracts.json"
    config["commands"]["quick"] = [{
        "id": "mirror.bootstrap",
        "command": ["{python}", "{project}/tools/forge_bootstrap.py", "{project}", "--skip-self-test"],
        "timeout": 300,
        "evidence": {"types": ["static"], "surfaces": []},
    }]
    config["commands"]["section"] = [{
        "id": "mirror.self-test",
        "command": ["{python}", "{project}/forge.py", "self-test"],
        "timeout": 1800,
        "evidence": {"types": ["unit", "integration"], "surfaces": []},
    }]
    config["commands"]["release"] = []
    config["release_proof"].update({
        "enabled": True,
        "claim_level": "entrypoints-executed",
        "auto_minimum": True,
    })
    # Mirror is staged. The Section Gate proves the complete regression suite once;
    # the Release Gate consumes that evidence and performs release-only verification.
    config["profiles"]["release"]["commands"] = ["quick", "release"]
    config["lab"]["required_profiles"] = ["release"]
    for recipe in config["lab"].get("recipes", []):
        recipe_id = str(recipe.get("id", ""))
        if recipe_id == "forge-cli-smoke":
            recipe["profiles"] = ["section"]
        elif recipe_id in {"forge-docs-smoke", "forge-bootstrap-smoke"}:
            recipe["profiles"] = ["release"]
    config["packaging"]["required_files"] = ["README.md", "FORGE-MANIFEST.json", "LICENSE-INTERNAL.md"]
    return config

def run_mirror(
    source_root: Path,
    *,
    baseline_version: str,
    release_version: str,
    output: Path | None = None,
    public_output: Path | None = None,
    changed_paths: list[str] | None = None,
    preserve_workspace: bool = False,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    if not is_forge_project(source_root):
        raise RuntimeError("Forge Mirror can run only against an Emotivus Forge Core source tree")
    if not baseline_version.strip() or not release_version.strip():
        raise ValueError("Mirror requires both baseline_version and release_version")
    if baseline_version == release_version:
        raise ValueError("Mirror release_version must differ from baseline_version")

    lock_path = _acquire_mirror_lock(source_root, release_version)
    started = utc_now()
    stages: list[dict[str, Any]] = []
    problems: list[str] = []
    workspace_parent = Path(tempfile.mkdtemp(prefix="forge-mirror-"))
    workspace = workspace_parent / "Emotivus-Forge"
    archive_path = output.resolve() if output else source_root / "deploy" / f"Emotivus-Forge-{release_version}-Development.zip"
    public_archive_path = public_output.resolve() if public_output else source_root / "deploy" / f"Emotivus-Forge-{release_version}.zip"

    def stage(stage_id: str, status: str, summary: str = "", details: Any = None) -> None:
        stages.append({"id": stage_id, "status": status, "summary": summary, "details": details})
        print(f"MIRROR {status:<8} {stage_id} — {summary}", flush=True)
        if status != "PASS":
            problems.append(f"{stage_id}: {summary}")

    try:
        bootstrap = _run([sys.executable, "tools/forge_bootstrap.py", ".", "--skip-self-test"], source_root, 300)
        stage("bootstrap.source", bootstrap["status"], "independent source validation passed" if bootstrap["status"] == "PASS" else (bootstrap["output"].splitlines()[-1] if bootstrap["output"] else "source bootstrap failed"), bootstrap)
        if bootstrap["status"] != "PASS":
            raise RuntimeError("source bootstrap failed")

        _copy_source(source_root, workspace)
        init_payload = initialize_project(
            workspace, workspace, name="Emotivus Forge", force=False,
            setup_answers={
                "preset": "strict", "deployment": "zip", "versioning": "semver",
                "tests": "required", "documentation": "required", "warnings": "fail",
                "baseline": "no", "existing_tools": "audit", "graph": "on",
                "learn": "on", "lab": "required",
                "required_files": ["README.md", "FORGE-MANIFEST.json", "LICENSE-INTERNAL.md"],
            },
        )
        stage("mirror.initialize", "PASS" if init_payload["initial_audit_status"] == "PASS" else "FAIL", f"adapters={','.join(init_payload['adapters'])}; labs={init_payload['lab_recipes']}", init_payload)
        if init_payload["initial_audit_status"] != "PASS":
            raise RuntimeError("self initialization audit failed")

        config = configure_mirror_contract(load_config(workspace), baseline_version, release_version)
        save_config(workspace, config)

        inventory = scan_existing_tools(workspace, workspace)
        competing = [item for item in inventory.get("candidates", []) if item.get("kind") == "forge-core" and item.get("recommendation") != "retain"]
        stage("mirror.tool-identity", "PASS" if not competing else "FAIL", f"forge-owned candidates retained={sum(1 for i in inventory.get('candidates', []) if i.get('kind') == 'forge-core')}", competing)
        if competing:
            raise RuntimeError("Forge Core was classified as competing tooling")

        graph = build_graph(workspace, workspace, config, write=True)
        stage("mirror.graph", "PASS", f"nodes={graph['summary']['nodes']}; edges={graph['summary']['edges']}", graph["summary"])
        impact_inputs = changed_paths or [
            "forge.py", "FORGE-MANIFEST.json", "emotivus_forge/cli.py",
            "emotivus_forge/mirror.py", "emotivus_forge/audit.py", "emotivus_forge/package.py",
        ]
        impact = analyze_impact(workspace, workspace, config, impact_inputs, write=True)
        stage("mirror.impact", "PASS", f"risk={impact['risk'].get('level', 'unknown')} score={impact['risk'].get('score', 0)}; impacted={len(impact['impacted_nodes'])}", {"risk": impact["risk"], "targeted_tests": impact["targeted_tests"]})

        lab_plan = plan_labs(workspace, config, write=True)
        required_ids = {"forge-cli-smoke", "forge-docs-smoke", "forge-bootstrap-smoke"}
        planned_ids = {str(item.get("id")) for item in lab_plan.get("recipes", [])}
        missing_labs = sorted(required_ids - planned_ids)
        stage("mirror.lab-plan", "PASS" if not missing_labs else "FAIL", f"recipes={sorted(planned_ids)}", missing_labs)
        if missing_labs:
            raise RuntimeError("self Lab recipes are missing")

        for profile in ("quick", "section", "release"):
            result = run_profile(workspace, workspace, config, profile, fresh=True)
            stage(f"gate.{profile}", result["status"], f"completed={result['completed_count']}/{len(result['required_check_ids'])}", result)
            if result["status"] != "PASS":
                raise RuntimeError(f"{profile} gate failed")

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        build = _run([sys.executable, "tools/build_forge_package.py", ".", "--output", str(archive_path)], source_root, 600)
        shape_problems = _validate_archive_shape(archive_path) if build["status"] == "PASS" else ["distribution build failed"]
        stage("distribution.build", "PASS" if build["status"] == "PASS" and not shape_problems else "FAIL", f"archive={archive_path}", {"build": build, "shape_problems": shape_problems})
        if build["status"] != "PASS" or shape_problems:
            raise RuntimeError("distribution build or shape validation failed")

        archive_bootstrap = _run([sys.executable, "tools/forge_bootstrap.py", ".", "--archive", str(archive_path)], source_root, 2400)
        stage("bootstrap.archive", archive_bootstrap["status"], "development archive extraction and self-test", archive_bootstrap)
        if archive_bootstrap["status"] != "PASS":
            raise RuntimeError("development archive bootstrap failed")

        public_archive_path.parent.mkdir(parents=True, exist_ok=True)
        public_build = _run([
            sys.executable, "tools/build_forge_package.py", ".", "--edition", "public", "--output", str(public_archive_path)
        ], source_root, 600)
        public_shape = _validate_archive_shape(public_archive_path) if public_build["status"] == "PASS" else ["public distribution build failed"]
        public_bootstrap = _run([
            sys.executable, "tools/forge_bootstrap.py", ".", "--archive", str(public_archive_path)
        ], source_root, 2400) if not public_shape else {"status": "SKIP", "output": "public shape failed"}
        public_status = "PASS" if public_build["status"] == "PASS" and not public_shape and public_bootstrap["status"] == "PASS" else "FAIL"
        stage("distribution.public", public_status, f"public_archive={public_archive_path}", {
            "build": public_build, "shape_problems": public_shape, "bootstrap": public_bootstrap,
        })
        if public_status != "PASS":
            raise RuntimeError("public distribution failed")

        with tempfile.TemporaryDirectory(prefix="forge-mirror-consumer-") as consumer_dir:
            consumer = Path(consumer_dir)
            fixture = consumer / "fixture-project"
            fixture.mkdir()
            with zipfile.ZipFile(public_archive_path) as archive:
                archive.extractall(fixture)
            extracted = fixture / "Emotivus-Forge"
            (fixture / "index.html").write_text("<!doctype html><title>Forge fixture</title>\n", encoding="utf-8")
            init_result = _run([sys.executable, str(extracted / "forge.py"), "start", str(fixture), "--preset", "prototype", "--deployment", "static", "--versioning", "none"], fixture, 600)
            context_result = _run([sys.executable, str(extracted / "forge.py"), "project", "context", str(fixture), "--mode", "cold", "--budget", "compact"], fixture, 600) if init_result["status"] == "PASS" else {"status": "SKIP", "output": "initialization failed"}
            quick_result = _run([sys.executable, str(extracted / "forge.py"), "verify", str(fixture), "--level", "quick", "--fresh"], fixture, 600) if context_result["status"] == "PASS" else {"status": "SKIP", "output": "context generation failed"}
            doctor_result = _run([sys.executable, str(extracted / "forge.py"), "maintain", "doctor", str(fixture), "--action", "propose"], fixture, 600) if quick_result["status"] == "PASS" else {"status": "SKIP", "output": "quick gate failed"}
            ci_result = _run([sys.executable, str(extracted / "forge.py"), "maintain", "ci", str(fixture), "--provider", "shell", "--action", "preview"], fixture, 600) if quick_result["status"] == "PASS" else {"status": "SKIP", "output": "quick gate failed"}
            delivery_result = _run([sys.executable, str(extracted / "forge.py"), "deliver", str(fixture), "--profile", "internal", "--dry-run"], fixture, 1200) if quick_result["status"] == "PASS" else {"status": "SKIP", "output": "quick gate failed"}
            update_result = _run([sys.executable, str(extracted / "forge.py"), "maintain", "update", str(fixture), "--action", "preview", "--source", str(public_archive_path)], fixture, 600) if quick_result["status"] == "PASS" else {"status": "SKIP", "output": "quick gate failed"}
            results = {"start": init_result, "context": context_result, "quick": quick_result, "doctor": doctor_result, "ci": ci_result, "internal_delivery": delivery_result, "update_preview": update_result}
            status = "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL"
            stage("consumer.acceptance", status, "extracted Forge initialized, checked, maintained, and packaged a fresh neutral project", results)
            if status != "PASS":
                raise RuntimeError("consumer acceptance failed")

    except Exception as exc:
        if not problems or not problems[-1].endswith(str(exc)):
            problems.append(str(exc))
    finally:
        if not preserve_workspace:
            shutil.rmtree(workspace_parent, ignore_errors=True)

    status = "PASS" if not problems and stages and all(item["status"] == "PASS" for item in stages) else "FAIL"
    payload = {
        "schema": 1,
        "system": "Forge Mirror",
        "status": status,
        "baseline_version": baseline_version,
        "release_version": release_version,
        "source_root": str(source_root),
        "workspace": str(workspace_parent) if preserve_workspace else "removed",
        "archive": str(archive_path) if archive_path.is_file() else "",
        "archive_sha256": _sha256(archive_path) if archive_path.is_file() else "",
        "public_archive": str(public_archive_path) if public_archive_path.is_file() else "",
        "public_archive_sha256": _sha256(public_archive_path) if public_archive_path.is_file() else "",
        "started_utc": started,
        "finished_utc": utc_now(),
        "stages": stages,
        "problems": problems,
    }
    report_dir = source_root / "deploy" / "mirror"
    write_json(report_dir / f"Forge-Mirror-{release_version}.json", payload)
    _write_text_report(report_dir / f"Forge-Mirror-{release_version}.txt", payload)
    _release_mirror_lock(lock_path)
    return payload

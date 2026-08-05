#!/usr/bin/env python3
"""Run deterministic public-neutral integrity campaigns against the current Forge source."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from emotivus_forge.core.artifact_collision import observe_version_collisions  # noqa: E402
from emotivus_forge.core.authority_baseline import authorize_current_baseline  # noqa: E402
from emotivus_forge.core.common import utc_now  # noqa: E402
from emotivus_forge.core.passport import build_passport  # noqa: E402
from emotivus_forge.services.scoped_check import run_scoped_check  # noqa: E402
from emotivus_forge.services.ship import ship_project  # noqa: E402

SCHEMA = "forge-integrity-campaign/1"
TRUTH_BOUNDARY = (
    "These are controlled synthetic public-neutral filesystem campaigns in one local environment. "
    "They demonstrate the observed detector and refusal behavior for the exact tested source. They "
    "do not authenticate a writer, prove all operating systems or filesystems, establish production "
    "correctness, exercise owner key custody, or authorize release."
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture(root: Path) -> None:
    (root / "index.php").write_text("<?php echo 'neutral';\n", encoding="utf-8")
    (root / "BACKLOG.md").write_text(
        "# Backlog\n\n## The next action\n\n- Run the controlled integrity scenario.\n",
        encoding="utf-8",
    )


def _zip(path: Path, version: str, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Neutral/FORGE-MANIFEST.json", json.dumps({"version": version}))
        archive.writestr("Neutral/payload.txt", payload)


def _writer_process(signal: Path, target: Path, content: str) -> subprocess.Popen[str]:
    code = (
        "import pathlib,sys,time\n"
        "signal=pathlib.Path(sys.argv[1]); target=pathlib.Path(sys.argv[2]); content=sys.argv[3]\n"
        "deadline=time.monotonic()+15\n"
        "while not signal.exists() and time.monotonic()<deadline: time.sleep(0.005)\n"
        "if not signal.exists(): raise SystemExit(4)\n"
        "target.write_text(content,encoding='utf-8')\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code, str(signal), str(target), content],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_writer(process: subprocess.Popen[str]) -> dict[str, Any]:
    stdout, stderr = process.communicate(timeout=20)
    return {"returncode": process.returncode, "stdout": stdout.strip(), "stderr": stderr.strip()}


def _scenario(
    scenario_id: str,
    expected: str,
    observed: str,
    passed: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "expected": expected,
        "observed": observed,
        "status": "PASS" if passed else "FAIL",
        "evidence": evidence,
    }


def concurrent_writer_after_checkpoint(forge_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _fixture(root)
        build_passport(root, forge_root)
        observed_check = run_scoped_check(root, forge_root)
        if observed_check.get("status") != "NOT_RUN":
            raise RuntimeError("the campaign must observe an unbaselined NOT_RUN before recording authority")
        authority_fingerprint = str(observed_check.get("authority_baseline", {}).get("current_fingerprint", ""))
        authorize_current_baseline(
            root,
            forge_root,
            expected_fingerprint=authority_fingerprint,
            authority="owner",
            reason="Reviewed the exact neutral pre-writer campaign tree.",
        )
        signal = root / ".writer-go"
        writer = _writer_process(signal, root / "index.php", "<?php echo 'external-writer';\n")
        check = run_scoped_check(root, forge_root, checkpoint=True)
        signal.write_text("go\n", encoding="utf-8")
        writer_result = _wait_writer(writer)
        ship = ship_project(root, forge_root)
        observed = str(ship.get("workspace_integrity", {}).get("status", "UNKNOWN"))
        passed = (
            check.get("status") == "PASS"
            and writer_result["returncode"] == 0
            and observed == "DRIFTED"
            and ship.get("release_ready") is False
        )
        return _scenario(
            "external-writer-after-checkpoint",
            "DRIFTED",
            observed,
            passed,
            {
                "pre_authority_status": observed_check.get("status", "UNKNOWN"),
                "authority_fingerprint": authority_fingerprint,
                "checkpoint_status": check.get("status", "UNKNOWN"),
                "writer_process_returncode": writer_result["returncode"],
                "release_ready": bool(ship.get("release_ready", False)),
                "expected_fingerprint": ship.get("workspace_integrity", {}).get("expected_fingerprint", ""),
                "observed_fingerprint": ship.get("workspace_integrity", {}).get("observed_fingerprint", ""),
            },
        )


def _load_builder(forge_root: Path) -> Any:
    path = forge_root / "tools" / "build_forge_package.py"
    spec = importlib.util.spec_from_file_location("forge_campaign_build_package", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load deterministic package builder.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package_source_drift_before_publication(forge_root: Path) -> dict[str, Any]:
    builder = _load_builder(forge_root)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "target.txt"
        target.write_text("selected-before-build\n", encoding="utf-8")
        (root / "README.md").write_text("neutral campaign\n", encoding="utf-8")
        (root / "CONFIDENTIALITY-POLICY.json").write_text(json.dumps({
            "forbidden_terms": [],
            "forbidden_sha256": [],
            "forbidden_path_patterns": [],
            "allow_paths": [],
        }, indent=2) + "\n", encoding="utf-8")
        (root / "FORGE-MANIFEST.json").write_text(json.dumps({
            "forge_schema": 1,
            "version": "9.9.9",
            "archive_root": "Neutral",
            "canonical_paths": [
                "CONFIDENTIALITY-POLICY.json", "FORGE-MANIFEST.json", "README.md", "target.txt"
            ],
            "public_paths": [
                "CONFIDENTIALITY-POLICY.json", "FORGE-MANIFEST.json", "README.md", "target.txt"
            ],
        }, indent=2) + "\n", encoding="utf-8")
        output = root / "RUN-NEUTRAL-9.9.9.zip"
        signal = root / ".writer-go"
        writer = _writer_process(signal, target, "changed-before-publication\n")
        callback_called = False

        def before_publish(*_args: Any) -> None:
            nonlocal callback_called
            callback_called = True
            signal.write_text("go\n", encoding="utf-8")
            result = _wait_writer(writer)
            if result["returncode"] != 0:
                raise RuntimeError(f"synthetic writer failed with {result['returncode']}")

        error = ""
        try:
            builder.build_package(
                root,
                output=output,
                edition="public",
                before_publish=before_publish,
            )
            observed = "PUBLISHED"
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            error = str(exc)
            observed = "BLOCKED"
        if writer.poll() is None:
            writer.kill()
            writer.communicate()
        passed = (
            callback_called
            and observed == "BLOCKED"
            and "drifted during the build" in error
            and not output.exists()
            and not output.with_suffix(output.suffix + ".tmp").exists()
        )
        return _scenario(
            "package-source-drift-before-publication",
            "BLOCKED",
            observed,
            passed,
            {
                "before_publish_boundary_reached": callback_called,
                "error_descriptor": error,
                "final_output_exists": output.exists(),
                "temporary_output_exists": output.with_suffix(output.suffix + ".tmp").exists(),
            },
        )


def rival_same_version_artifacts(_forge_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = root / "candidate-a" / "RUN-FORGE-9.9.9.zip"
        second = root / "candidate-b" / "RUN-FORGE-9.9.9.zip"
        _zip(first, "9.9.9", "first candidate")
        _zip(second, "9.9.9", "rival candidate")
        result = observe_version_collisions(root)
        collision = result.get("collisions", [{}])[0] if result.get("collisions") else {}
        observed = str(result.get("status", "UNKNOWN"))
        passed = observed == "FAIL" and collision.get("distinct_sha256_count") == 2
        return _scenario(
            "same-name-same-version-rival-artifacts",
            "FAIL",
            observed,
            passed,
            {
                "distinct_sha256_count": collision.get("distinct_sha256_count", 0),
                "artifact_sha256": sorted([_sha256(first), _sha256(second)]),
            },
        )


def filename_manifest_disagreement(_forge_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        artifact = root / "RUN-FORGE-9.9.9.zip"
        _zip(artifact, "9.9.10", "mismatch")
        result = observe_version_collisions(root)
        observed = str(result.get("status", "UNKNOWN"))
        problems = result.get("problems", [])
        passed = observed == "FAIL" and any("differs" in str(item.get("problem", "")) for item in problems)
        return _scenario(
            "filename-manifest-version-disagreement",
            "FAIL",
            observed,
            passed,
            {"problems": problems},
        )


def quarantine_recovery(_forge_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = root / "candidate-a" / "RUN-FORGE-9.9.9.zip"
        second = root / "candidate-b" / "RUN-FORGE-9.9.9.zip"
        _zip(first, "9.9.9", "first candidate")
        _zip(second, "9.9.9", "rival candidate")
        before = observe_version_collisions(root)
        quarantine = root / ".forge" / "quarantine" / "artifact-collisions"
        quarantine.mkdir(parents=True)
        quarantined = quarantine / f"{_sha256(second)}.zip"
        shutil.move(str(second), quarantined)
        after = observe_version_collisions(root)
        observed = str(after.get("status", "UNKNOWN"))
        passed = before.get("status") == "FAIL" and observed == "PASS" and quarantined.is_file()
        return _scenario(
            "explicit-collision-quarantine-recovery",
            "PASS",
            observed,
            passed,
            {
                "status_before_quarantine": before.get("status", "UNKNOWN"),
                "quarantined_sha256": _sha256(quarantined),
                "active_artifacts_scanned_after": after.get("artifacts_scanned", 0),
            },
        )


def project_ignore_boundary(_forge_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".forgeignore").write_text("reference/**\n", encoding="utf-8")
        _zip(root / "reference" / "a" / "RUN-FORGE-9.9.9.zip", "9.9.9", "first")
        _zip(root / "reference" / "b" / "RUN-FORGE-9.9.9.zip", "9.9.9", "second")
        result = observe_version_collisions(root)
        observed = str(result.get("status", "UNKNOWN"))
        passed = observed == "PASS" and result.get("artifacts_scanned") == 0
        return _scenario(
            "project-ignore-bounds-artifact-observation",
            "PASS",
            observed,
            passed,
            {
                "artifacts_scanned": result.get("artifacts_scanned", -1),
                "project_ignore_patterns": result.get("project_ignore_patterns", []),
            },
        )


SCENARIOS: tuple[Callable[[Path], dict[str, Any]], ...] = (
    concurrent_writer_after_checkpoint,
    package_source_drift_before_publication,
    rival_same_version_artifacts,
    filename_manifest_disagreement,
    quarantine_recovery,
    project_ignore_boundary,
)


def run_campaign(forge_root: Path = ROOT) -> dict[str, Any]:
    forge_root = forge_root.resolve()
    manifest = json.loads((forge_root / "FORGE-MANIFEST.json").read_text(encoding="utf-8"))
    scenarios: list[dict[str, Any]] = []
    for function in SCENARIOS:
        try:
            scenarios.append(function(forge_root))
        except Exception as exc:  # Campaign receipts must retain the failed scenario rather than abort silently.
            scenarios.append(_scenario(function.__name__, "PASS", "ERROR", False, {
                "error_type": type(exc).__name__,
                "error_descriptor": str(exc),
            }))
    passed = sum(item["status"] == "PASS" for item in scenarios)
    status = "PASS" if passed == len(scenarios) else "FAIL"
    return {
        "schema": SCHEMA,
        "campaign_id": f"workspace-and-artifact-integrity-{manifest.get('version', 'unknown')}",
        "forge_version": str(manifest.get("version", "")),
        "generated_utc": utc_now(),
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "fixture_policy": {
            "public_neutral": True,
            "real_user_or_project_data": False,
            "external_writer_processes": True,
            "private_key_material": False,
        },
        "summary": {
            "status": status,
            "passed": passed,
            "failed": len(scenarios) - passed,
            "total": len(scenarios),
        },
        "scenarios": scenarios,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(ROOT))
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = run_campaign(Path(args.root))
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = Path(args.root).resolve() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["summary"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from emotivus_forge.core.handoff import export_continuity_bundle, import_continuity_bundle
from emotivus_forge.core.native_tools import load_or_discover_native_tools, set_native_execution_mode
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.paths import STATE_FILE_NAMES
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class NativeInvocationAndHandoffTests(ForgeTestCase):
    def _gate(self, root: Path, *, include_beta: bool = True) -> Path:
        (root / "tools").mkdir(exist_ok=True)
        gate = root / "tools" / "run_all_checks.sh"
        rows = [
            "#!/usr/bin/env sh",
            "[ \"$1\" = \".\" ] || { echo wrong-argument >&2; exit 9; }",
            "[ \"$FORGE_TEST_MODE\" = \"1\" ] || { echo wrong-environment >&2; exit 8; }",
            "echo 'FORGE_EVIDENCE {\"id\":\"group.alpha\",\"status\":\"PASS\",\"surface\":\"core\"}'",
        ]
        if include_beta:
            rows.append("echo 'FORGE_EVIDENCE {\"id\":\"group.beta\",\"status\":\"PASS\",\"surface\":\"delivery\"}'")
        rows.append("exit 0")
        gate.write_text("\n".join(rows) + "\n", encoding="utf-8")
        gate.chmod(0o755)
        return gate

    def _invocation(self, root: Path, *, expected: list[str] | None = None, cwd: str = ".") -> Path:
        path = root / "forge-native-invocation.json"
        checks = expected if expected is not None else ["group.alpha", "group.beta"]
        path.write_text(json.dumps({
            "schema": "forge-native-invocation/1",
            "authority": "owner",
            "candidate_id": "canonical",
            "argv": ["bash", "tools/run_all_checks.sh", "."],
            "working_directory": cwd,
            "environment": {"FORGE_TEST_MODE": "1"},
            "expected_checks": checks,
            "expected_count": len(checks),
            "coverage_policy": "exact",
            "timeout_seconds": 30,
            "verification_tier": "sandbox",
            "rationale": "The project owner approved this exact native gate invocation and declared its complete group coverage.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def _close_session(self, root: Path) -> dict:
        return run_scoped_check(root, FORGE_ROOT, session_close_data={
            "session_type": "code-increment",
            "summary": "Prepared a portable development handoff.",
            "completed_work": ["Recorded current project continuity."],
            "decisions": [],
            "owner_facts": [],
            "unresolved_risks": ["Runtime and deployment remain unverified."],
            "next_action": "Continue the next approved roadmap item.",
            "interaction_telemetry": {},
            "field_observation_path": "",
        })

    def test_exact_invocation_binds_arguments_cwd_environment_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._gate(root)
            contract = self._invocation(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "forge-authorized", invocation_contract_path=contract.name)
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            native = payload["native_gate"]
            self.assertEqual(native["status"], "PASS")
            self.assertEqual(native["command"], ["bash", "tools/run_all_checks.sh", "."])
            self.assertEqual(native["working_directory"], ".")
            self.assertEqual(native["environment_overrides"], ["FORGE_TEST_MODE"])
            self.assertEqual(native["coverage"]["status"], "complete")
            self.assertEqual(native["coverage"]["observed_count"], 2)

    def test_zero_exit_with_missing_approved_group_fails_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._gate(root, include_beta=False)
            contract = self._invocation(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "forge-authorized", invocation_contract_path=contract.name)
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(payload["native_gate"]["returncode"], 0)
            self.assertEqual(payload["native_gate"]["status"], "FAIL")
            self.assertEqual(payload["native_gate"]["coverage"]["missing_checks"], ["group.beta"])
            self.assertIn("coverage incomplete", payload["native_gate"]["reason"].lower())

    def test_forge_authorized_mode_requires_exact_invocation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._gate(root)
            build_passport(root, FORGE_ROOT)
            with self.assertRaisesRegex(RuntimeError, "requires --native-invocation"):
                set_native_execution_mode(root, "forge-authorized")

    def test_changed_invocation_contract_requires_reapproval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._gate(root)
            contract = self._invocation(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "forge-authorized", invocation_contract_path=contract.name)
            value = json.loads(contract.read_text(encoding="utf-8"))
            value["argv"].append("extra")
            contract.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            refreshed = load_or_discover_native_tools(root, refresh=True)
            self.assertEqual(refreshed["approval"]["status"], "reapproval-required")
            self.assertEqual(refreshed["approval"]["invocation_status"], "stale")

    def test_imported_evidence_is_bound_to_invocation_and_complete_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._gate(root)
            contract = self._invocation(root)
            build_passport(root, FORGE_ROOT)
            registry = set_native_execution_mode(root, "owner-only", invocation_contract_path=contract.name)
            approval = registry["approval"]
            canonical = registry["canonical"]
            evidence = root / "owner-evidence.json"
            evidence.write_text(json.dumps({
                "schema": "forge-native-evidence/1",
                "candidate_id": canonical["id"],
                "gate_fingerprint": canonical["fingerprint"],
                "invocation_fingerprint": approval["approved_invocation_fingerprint"],
                "execution_authority": "owner",
                "verification_tier": "sandbox",
                "status": "PASS",
                "returncode": 0,
                "entries": [{"id": "group.alpha", "status": "PASS"}],
            }, indent=2) + "\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT, import_native_evidence_path=evidence.name)
            self.assertEqual(payload["native_gate"]["status"], "FAIL")
            self.assertEqual(payload["native_gate"]["coverage"]["missing_checks"], ["group.beta"])

    def test_sensitive_environment_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._gate(root)
            contract = self._invocation(root)
            value = json.loads(contract.read_text(encoding="utf-8"))
            value["environment"] = {"API_TOKEN": "do-not-store"}
            contract.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            with self.assertRaisesRegex(RuntimeError, "secret-shaped"):
                set_native_execution_mode(root, "forge-authorized", invocation_contract_path=contract.name)

    def test_continuity_bundle_requires_session_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            with self.assertRaisesRegex(ValueError, "Session Close"):
                export_continuity_bundle(root, "Forge-Continuity.zip", forge_root=FORGE_ROOT)

    def test_continuity_bundle_is_separate_bounded_and_package_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._close_session(root)
            package = root / "Development.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("project/index.php", "<?php echo 'ok';\n")
            result = export_continuity_bundle(root, "Forge-Continuity.zip", development_package=package.name, forge_root=FORGE_ROOT)
            self.assertEqual(result["status"], "READY")
            self.assertEqual(result["state_file_count"], 8)
            self.assertEqual(result["project_binding"]["status"], "BOUND")
            self.assertFalse(result["raw_logs_included"])
            with zipfile.ZipFile(result["bundle"]) as archive:
                names = set(archive.namelist())
                self.assertTrue({f".forge/{name}" for name in STATE_FILE_NAMES}.issubset(names))
                self.assertFalse(any(name.endswith("stdout.log") or name.endswith("stderr.log") for name in names))
                manifest = json.loads(archive.read("FORGE-CONTINUITY-MANIFEST.json"))
                self.assertEqual(manifest["project_binding"]["sha256"], result["project_binding"]["sha256"])

    def test_continuity_bundle_import_restores_state_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            self._fixture(source)
            build_passport(source, FORGE_ROOT)
            self._close_session(source)
            package = Path(directory) / "Development.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("project/index.php", "<?php echo 'ok';\n")
            exported = export_continuity_bundle(source, str(Path(directory) / "Forge-Continuity.zip"), development_package=str(package), forge_root=FORGE_ROOT)

            target = Path(directory) / "target"
            target.mkdir()
            self._fixture(target)
            imported = import_continuity_bundle(target, exported["bundle"], development_package=str(package))
            self.assertEqual(imported["status"], "IMPORTED")
            self.assertEqual(imported["state_file_count"], 8)
            self.assertEqual(len([name for name in STATE_FILE_NAMES if (target / ".forge" / name).is_file()]), 8)
            resume = build_resume(target, FORGE_ROOT)
            self.assertIn("Continue the next approved roadmap item", resume["markdown"])

    def test_bound_continuity_bundle_rejects_wrong_development_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            self._fixture(source)
            build_passport(source, FORGE_ROOT)
            self._close_session(source)
            package = Path(directory) / "Development.zip"
            wrong = Path(directory) / "Wrong.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("project/index.php", "one")
            with zipfile.ZipFile(wrong, "w") as archive:
                archive.writestr("project/index.php", "two")
            exported = export_continuity_bundle(source, str(Path(directory) / "Forge-Continuity.zip"), development_package=str(package), forge_root=FORGE_ROOT)
            target = Path(directory) / "target"
            target.mkdir()
            self._fixture(target)
            with self.assertRaisesRegex(ValueError, "digest does not match"):
                import_continuity_bundle(target, exported["bundle"], development_package=str(wrong))


if __name__ == "__main__":
    unittest.main()

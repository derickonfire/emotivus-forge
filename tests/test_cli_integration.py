from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from emotivus_forge.core.paths import STATE_FILE_NAMES
from tests.support import FORGE_ROOT, ForgeTestCase


class CliIntegrationTests(ForgeTestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(FORGE_ROOT / "forge.py"), *args],
            cwd=str(FORGE_ROOT),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_cli_supports_project_paths_with_spaces_and_clean_json_stdout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forge path with spaces ") as directory:
            root = Path(directory)
            self._fixture(root)
            result = self._run("run", str(root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertIn("ai_notice", payload)
            actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_cli_returns_nonzero_and_machine_readable_block_on_corrupt_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            first = self._run("run", str(root), "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            state = root / ".forge" / "state.json"
            state.write_text("{broken", encoding="utf-8")
            result = self._run("run", str(root), "--json")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertEqual(state.read_text(encoding="utf-8"), "{broken")

    def test_cli_records_owner_only_native_mode_and_imports_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "tools").mkdir()
            gate = root / "tools" / "run_all_checks.sh"
            gate.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            gate.chmod(0o755)
            first = self._run("run", str(root), "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            invocation = self._native_invocation_contract(root, expected_checks=["gate.all"])
            mode = self._run("adopt", str(root), "--native-mode", "owner-only", "--native-invocation", invocation.name, "--json")
            self.assertEqual(mode.returncode, 0, mode.stderr)
            registry = json.loads((root / ".forge" / "native-tools.json").read_text(encoding="utf-8"))
            canonical = registry["canonical"]
            evidence = root / "owner-native-evidence.json"
            evidence.write_text(json.dumps({
                "schema": "forge-native-evidence/1",
                "candidate_id": canonical["id"],
                "gate_fingerprint": canonical["fingerprint"],
                "invocation_fingerprint": registry["approval"]["approved_invocation_fingerprint"],
                "execution_authority": "owner",
                "executed_utc": "2026-08-01T16:00:00-04:00",
                "verification_tier": "sandbox",
                "status": "PASS",
                "returncode": 0,
                "entries": [{"id": "gate.all", "status": "PASS"}],
            }) + "\n", encoding="utf-8")
            checked = self._run("check", str(root), "--import-native-evidence", evidence.name, "--json")
            self.assertEqual(checked.returncode, 1, checked.stderr)
            payload = json.loads(checked.stdout)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertTrue(payload["native_gate"]["imported"])
            self.assertEqual(payload["native_gate"]["execution_mode"], "owner-only")

    def test_cli_rejects_simultaneous_native_execution_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            first = self._run("run", str(root), "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            result = self._run("check", str(root), "--run-native", "--import-native-evidence", "evidence.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("either --run-native or --import-native-evidence", result.stderr)

    def test_cli_no_command_options_support_transient_session_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            root = Path(directory)
            self._fixture(root)
            json.dump({
                "schema": "forge-session-context/1",
                "objective": "Inspect the current project.",
                "requested_items": ["Inspect app.py"],
                "ai_claims": [],
                "next_action": "Continue the scoped work."
            }, handle)
            handle.flush()
            context = Path(handle.name)
            try:
                result = self._run("--session-context", str(context), str(root), "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["active_pass"]["status"], "COMPLETE")
                self.assertEqual(payload["session_reconciliation"]["conversation_review"], "DISTILLED_CONTEXT_REVIEWED")
            finally:
                context.unlink(missing_ok=True)

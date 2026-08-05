from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.authority_registry import load_or_discover_authorities
from emotivus_forge.core.native_tools import load_or_discover_native_tools, set_native_execution_mode
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.session_close import assess_continuity
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class ObjectiveAndNativeAuthorityTests(ForgeTestCase):
    def _native_gate(self, root: Path) -> Path:
        (root / "tools").mkdir(exist_ok=True)
        gate = root / "tools" / "run_all_checks.sh"
        gate.write_text(
            "#!/usr/bin/env sh\n"
            "echo 'FORGE_EVIDENCE {\"id\":\"unit.core\",\"status\":\"PASS\",\"surface\":\"core\"}'\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gate.chmod(0o755)
        return gate

    def _evidence(self, root: Path, *, authority: str = "owner", fingerprint: str = "") -> Path:
        registry = load_or_discover_native_tools(root, refresh=True)
        canonical = registry["canonical"]
        path = root / "native-evidence.json"
        path.write_text(json.dumps({
            "schema": "forge-native-evidence/1",
            "candidate_id": canonical["id"],
            "gate_fingerprint": fingerprint or canonical["fingerprint"],
            "invocation_fingerprint": registry["approval"].get("approved_invocation_fingerprint", ""),
            "execution_authority": authority,
            "executed_utc": "2026-08-01T16:00:00-04:00",
            "verification_tier": "sandbox",
            "status": "PASS",
            "returncode": 0,
            "entries": [
                {"id": "unit.core", "status": "PASS", "type": "unit", "surfaces": ["core"]}
            ],
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def test_redirect_objective_follows_linked_ordered_roadmap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Planning").mkdir()
            (root / "BACKLOG.md").write_text(
                "# Backlog\n\n## THE NEXT ACTION\n\n"
                "See `Planning/ROADMAP-ORDER.md` for the full ordered plan. Short\n",
                encoding="utf-8",
            )
            (root / "Planning" / "ROADMAP-ORDER.md").write_text(
                "# Roadmap order\n\n"
                "1. Prior defect — BUILT\n"
                "2. Version decision — CLOSED\n"
                "3. Build the approved creation workflow (R-103).\n"
                "4. Add the optional preview surface.\n",
                encoding="utf-8",
            )
            registry = load_or_discover_authorities(root, FORGE_ROOT, refresh=True)
            objective = registry["objective"]
            self.assertEqual(objective["text"], "Build the approved creation workflow (R-103).")
            self.assertEqual(objective["source"], "Planning/ROADMAP-ORDER.md")
            self.assertEqual(objective["resolution_method"], "authority-link")
            self.assertEqual(objective["linked_from"], "BACKLOG.md")
            self.assertEqual(registry["confirmation"]["required"], False)
            self.assertEqual(len(registry["rejected_objectives"]), 1)

    def test_unresolved_fragment_is_rejected_instead_of_becoming_objective(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "BACKLOG.md").write_text(
                "## THE NEXT ACTION\n\nSee `Planning/MISSING.md` for the full ordered plan. Short\n",
                encoding="utf-8",
            )
            registry = load_or_discover_authorities(root, FORGE_ROOT, refresh=True)
            self.assertEqual(registry["objective"]["text"], "")
            self.assertTrue(registry["confirmation"]["required"])
            self.assertIn("rejected", registry["confirmation"]["reason"].lower())

    def test_first_adoption_continuity_is_not_established_not_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            continuity = assess_continuity(root)
            self.assertEqual(continuity["status"], "not-established")
            resume = build_resume(root, FORGE_ROOT)
            self.assertEqual(resume["continuity"]["status"], "not-established")
            self.assertNotIn("Session Close", " ".join(resume["attention_reasons"]))

    def test_owner_only_mode_never_executes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._native_gate(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "owner-only", invocation_contract_path=self._native_invocation_contract(root, expected_checks=["unit.core"]).name)
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(payload["native_gate"]["status"], "BLOCKED")
            self.assertEqual(payload["native_gate"]["execution_mode"], "owner-only")
            self.assertIn("may not execute", payload["native_gate"]["reason"])

    def test_owner_only_mode_imports_owner_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._native_gate(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "owner-only", invocation_contract_path=self._native_invocation_contract(root, expected_checks=["unit.core"]).name)
            evidence = self._evidence(root, authority="owner")
            payload = run_scoped_check(root, FORGE_ROOT, import_native_evidence_path=evidence.name)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["native_gate"]["status"], "PASS")
            self.assertTrue(payload["native_gate"]["imported"])
            self.assertEqual(payload["native_gate"]["execution_authority"], "owner")
            self.assertIn("project-native-evidence-import", payload["execution_order"])
            self.assertTrue((root / ".forge" / payload["native_gate"]["raw_evidence"]["result"]).is_file())

    def test_owner_only_rejects_external_ci_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._native_gate(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "owner-only", invocation_contract_path=self._native_invocation_contract(root, expected_checks=["unit.core"]).name)
            evidence = self._evidence(root, authority="external-ci")
            payload = run_scoped_check(root, FORGE_ROOT, import_native_evidence_path=evidence.name)
            self.assertEqual(payload["native_gate"]["status"], "BLOCKED")
            self.assertIn("owner", payload["native_gate"]["reason"].lower())

    def test_external_ci_mode_imports_ci_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._native_gate(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "external-ci", invocation_contract_path=self._native_invocation_contract(root, expected_checks=["unit.core"]).name)
            evidence = self._evidence(root, authority="external-ci")
            payload = run_scoped_check(root, FORGE_ROOT, import_native_evidence_path=evidence.name)
            self.assertEqual(payload["native_gate"]["status"], "PASS")
            self.assertEqual(payload["native_gate"]["execution_mode"], "external-ci")

    def test_import_rejects_stale_gate_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._native_gate(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "evidence-import-only", invocation_contract_path=self._native_invocation_contract(root, expected_checks=["unit.core"]).name)
            evidence = self._evidence(root, authority="owner", fingerprint="0" * 64)
            payload = run_scoped_check(root, FORGE_ROOT, import_native_evidence_path=evidence.name)
            self.assertEqual(payload["native_gate"]["status"], "BLOCKED")
            self.assertIn("fingerprint", payload["native_gate"]["reason"].lower())

    def test_native_mode_requires_reapproval_when_gate_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            gate = self._native_gate(root)
            build_passport(root, FORGE_ROOT)
            set_native_execution_mode(root, "owner-only", invocation_contract_path=self._native_invocation_contract(root, expected_checks=["unit.core"]).name)
            gate.write_text("#!/usr/bin/env sh\necho changed\n", encoding="utf-8")
            registry = load_or_discover_native_tools(root, refresh=True)
            self.assertEqual(registry["approval"]["status"], "reapproval-required")
            self.assertEqual(registry["approval"]["execution_mode"], "owner-only")

    def test_attention_items_are_prioritized_by_severity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo 'ok';\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            resume = build_resume(root, FORGE_ROOT)
            self.assertEqual(resume["attention_items"][0]["severity"], "blocker")
            self.assertEqual(resume["attention_items"][0]["category"], "objective")
            self.assertGreaterEqual(resume["attention_counts"]["blocker"], 1)

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.check_qualification import (
    check_qualification_summary,
    record_check_qualification,
    retire_check_qualification,
)
from emotivus_forge.core.ledger_assertions import (
    ledger_assertion_summary,
    record_ledger_assertion,
    retire_ledger_assertion,
    validate_ledger_assertion_contract,
)
from emotivus_forge.core.native_tools import approve_canonical_native_tool
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.paths import STATE_FILE_NAMES
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class LedgerAssertionAndQualificationTests(ForgeTestCase):
    def _assertion_contract(self, root: Path, *, expected: str = "enabled") -> Path:
        (root / "DECISIONS.md").write_text(
            "# Decision\n\nThe feature flag remains enabled after the resolved defect.\n",
            encoding="utf-8",
        )
        (root / "config.json").write_text(json.dumps({"feature": {"status": expected}}) + "\n", encoding="utf-8")
        contract = root / "forge-ledger-assertion.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "assertion_id": "resolved-feature-state",
            "title": "Resolved feature state remains enforced",
            "authority": "owner",
            "record_type": "resolved-defect",
            "rationale": "A defect marked resolved must not silently regress while the Ledger continues to present it as trusted project truth.",
            "evidence_paths": ["DECISIONS.md"],
            "assertions": [
                {"id": "config-value", "kind": "json-equals", "path": "config.json", "key": "feature.status", "value": "enabled"},
                {"id": "decision-text", "kind": "file-contains", "path": "DECISIONS.md", "text": "remains enabled"},
            ],
            "verification_boundary": "These deterministic assertions prove only the recorded values and text, not complete feature behavior or release readiness.",
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def _native_fixture(self, root: Path) -> tuple[Path, Path]:
        (root / "tools").mkdir(exist_ok=True)
        gate = root / "tools" / "run_all_checks.sh"
        gate.write_text(
            "#!/usr/bin/env sh\n"
            "echo 'FORGE_CHECK|id=membership-active|status=PASS|type=integration|surface=data|tier=sandbox'\n",
            encoding="utf-8",
        )
        evidence = root / "qualification-negative-case.txt"
        evidence.write_text(
            "fixture=membership-without-active-filter\nexpected=FAIL\nobserved=FAIL\n",
            encoding="utf-8",
        )
        contract = root / "forge-check-qualification.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "qualification_id": "membership-active-negative-proof",
            "check_id": "membership-active",
            "authority": "owner",
            "check_source": "tools/run_all_checks.sh",
            "verification_tier": "sandbox",
            "negative_cases": [{
                "id": "missing-membership-active",
                "description": "A known-bad membership query omits the active membership constraint.",
                "expected_result": "FAIL",
                "observed_result": "FAIL",
                "evidence_path": "qualification-negative-case.txt",
                "observed_utc": "2026-08-01T12:00:00-04:00",
            }],
            "limitations": ["The qualification covers one known-bad query shape and does not prove complete SQL parsing."],
            "scanned_surface_count": 19,
            "truth_boundary": "Qualification proves the current check source was observed rejecting the recorded known-bad input; it does not prove complete defect coverage.",
        }, indent=2) + "\n", encoding="utf-8")
        return gate, contract

    def test_ledger_assertion_passes_and_preserves_eight_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._assertion_contract(root)
            build_passport(root, FORGE_ROOT)
            record_ledger_assertion(root, FORGE_ROOT, contract)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["ledger_assertions"]["status"], "PASS")
            self.assertEqual(payload["ledger_assertions"]["active_count"], 1)
            build_resume(root, FORGE_ROOT, budget="compact")
            actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_resolved_defect_assertion_reopens_when_current_tree_contradicts_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._assertion_contract(root)
            build_passport(root, FORGE_ROOT)
            record_ledger_assertion(root, FORGE_ROOT, contract)
            (root / "config.json").write_text('{"feature":{"status":"disabled"}}\n', encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["ledger_assertions"]["status"], "FAIL")
            self.assertTrue(any("resolved-feature-state/config-value" in item["message"] for item in payload["findings"]))

    def test_changed_assertion_contract_requires_renewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._assertion_contract(root)
            build_passport(root, FORGE_ROOT)
            record_ledger_assertion(root, FORGE_ROOT, contract)
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("not current" in item["message"] for item in payload["findings"]))

    def test_retired_assertion_remains_in_history_but_stops_enforcing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._assertion_contract(root)
            build_passport(root, FORGE_ROOT)
            record_ledger_assertion(root, FORGE_ROOT, contract)
            retire_ledger_assertion(root, "resolved-feature-state", "The owner replaced this rule with a newer project decision.")
            (root / "config.json").write_text('{"feature":{"status":"disabled"}}\n', encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            summary = ledger_assertion_summary(root)
            self.assertEqual(summary["retired_count"], 1)

    def test_native_green_is_explicitly_unqualified_without_negative_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            self._native_fixture(root)
            build_passport(root, FORGE_ROOT)
            approve_canonical_native_tool(root, self._native_invocation_contract(root, expected_checks=["membership-active"]).name)
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["native_gate"]["status"], "PASS")
            self.assertEqual(payload["check_qualification"]["counts"]["unqualified"], 1)
            self.assertEqual(payload["check_qualification"]["qualified_ratio"], "0/1")
            truth = next(item for item in payload["truth_records"] if item["subject"] == "check-qualification:membership-active")
            self.assertEqual(truth["truth_state"], "UNKNOWN")

    def test_negative_test_record_qualifies_current_native_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            _, contract = self._native_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_check_qualification(root, FORGE_ROOT, contract)
            approve_canonical_native_tool(root, self._native_invocation_contract(root, expected_checks=["membership-active"]).name)
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(payload["check_qualification"]["counts"]["qualified"], 1)
            self.assertEqual(payload["check_qualification"]["qualified_ratio"], "1/1")
            row = payload["check_qualification"]["records"][0]
            self.assertEqual(row["negative_case_count"], 1)
            self.assertEqual(row["scanned_surface_count"], 19)
            truth = next(item for item in payload["truth_records"] if item["subject"] == "check-qualification:membership-active")
            self.assertEqual(truth["truth_state"], "CONFIRMED")

    def test_check_source_change_makes_qualification_stale_without_relabeling_native_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            gate, contract = self._native_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_check_qualification(root, FORGE_ROOT, contract)
            approve_canonical_native_tool(root, self._native_invocation_contract(root, expected_checks=["membership-active"]).name)
            gate.write_text(gate.read_text(encoding="utf-8") + "# changed source\n", encoding="utf-8")
            approve_canonical_native_tool(root, self._native_invocation_contract(root, expected_checks=["membership-active"]).name)
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(payload["native_gate"]["status"], "PASS")
            self.assertEqual(payload["check_qualification"]["counts"]["stale"], 1)
            truth = next(item for item in payload["truth_records"] if item["subject"] == "check-qualification:membership-active")
            self.assertEqual(truth["truth_state"], "STALE")

    def test_resume_uses_compact_counts_not_negative_case_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            _, contract = self._native_fixture(root)
            assertion = self._assertion_contract(root)
            build_passport(root, FORGE_ROOT)
            record_check_qualification(root, FORGE_ROOT, contract)
            record_ledger_assertion(root, FORGE_ROOT, assertion)
            resume = build_resume(root, FORGE_ROOT, budget="compact")
            text = resume["markdown"]
            self.assertIn("Ledger assertions:** 1 active", text)
            self.assertIn("Check qualification:** 1 current qualification", text)
            self.assertNotIn("membership query omits", text)
            self.assertLess(len(text), 12000)


    def test_zip_assertion_detects_prohibited_delivery_prefix(self) -> None:
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "DECISIONS.md").write_text(
                "# Delivery rule\n\nDevelopment tooling must not ship.\n",
                encoding="utf-8",
            )
            archive = root / "Changed Files.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("public/index.php", "ok")
                output.writestr("tools/audit.py", "no")
            contract = root / "delivery-assertion.json"
            contract.write_text(json.dumps({
                "schema": 1,
                "assertion_id": "delivery-no-tools",
                "title": "Delivery archive excludes project tooling",
                "authority": "owner",
                "record_type": "release-rule",
                "rationale": "The deployable changed-files archive must remain a strict delivery subset and must not carry development tooling.",
                "evidence_paths": ["DECISIONS.md"],
                "assertions": [{"id": "exclude-tools", "kind": "zip-excludes-prefix", "path": "Changed Files.zip", "prefix": "tools"}],
                "verification_boundary": "This assertion checks archive membership only and does not prove the archive is complete, deployable, or based on the live baseline.",
            }, indent=2) + "\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            record_ledger_assertion(root, FORGE_ROOT, contract)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("prohibited prefix" in item["message"] for item in payload["findings"]))

    def test_changed_negative_case_evidence_makes_qualification_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            _, contract = self._native_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_check_qualification(root, FORGE_ROOT, contract)
            approve_canonical_native_tool(root, self._native_invocation_contract(root, expected_checks=["membership-active"]).name)
            (root / "qualification-negative-case.txt").write_text("changed evidence\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(payload["check_qualification"]["counts"]["stale"], 1)

    def test_assertion_targets_cannot_escape_project_or_enter_forge_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            (root / "DECISIONS.md").write_text(
                "# Decision\n\nState internals are not assertion targets.\n",
                encoding="utf-8",
            )
            contract = root / "unsafe-assertion.json"
            contract.write_text(json.dumps({
                "schema": 1,
                "assertion_id": "unsafe-target",
                "title": "Unsafe internal state assertion target",
                "authority": "owner",
                "record_type": "project-rule",
                "rationale": "Project assertions must not create a route to inspect or manipulate Forge internal state files.",
                "evidence_paths": ["DECISIONS.md"],
                "assertions": [{"id": "state", "kind": "path-exists", "path": ".forge/state.json"}],
                "verification_boundary": "This fixture exists only to prove the project-boundary validation blocks unsafe assertion targets.",
            }, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_ledger_assertion_contract(root, FORGE_ROOT, contract)

    def test_retired_qualification_is_not_used_for_current_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            _, contract = self._native_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_check_qualification(root, FORGE_ROOT, contract)
            retire_check_qualification(root, "membership-active-negative-proof", "The project replaced this check with a new implementation.")
            approve_canonical_native_tool(root, self._native_invocation_contract(root, expected_checks=["membership-active"]).name)
            payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
            self.assertEqual(payload["check_qualification"]["counts"]["unqualified"], 1)
            summary = check_qualification_summary(root)
            self.assertEqual(summary["retired"], 1)

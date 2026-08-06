from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.capabilities import activate_capability, capability_activations
from emotivus_forge.core.field_trials import record_trial, trial_records
from emotivus_forge.core.guardrails import guardrail_records, record_guardrail, retire_guardrail
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.project_events import confirm_project_event
from emotivus_forge.core.project_identity import project_identity_record, project_identity_summary, record_project_identity
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.state import load_settings
from emotivus_forge.services.scoped_check import run_scoped_check

from tests.support import FORGE_ROOT, ForgeTestCase


class IdentityEventLifecycleTests(ForgeTestCase):
    def test_multi_component_identity_preserves_absent_components_and_compact_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_project_identity(root, FORGE_ROOT, self._project_identity_contract(root))
            build_passport(root, FORGE_ROOT)
            summary = project_identity_summary(root)
            self.assertEqual(summary["status"], "active")
            self.assertEqual(summary["component_count"], 3)
            self.assertEqual(summary["present_components"], 2)
            self.assertIsNone(summary["components"]["player"]["version"])
            resume = build_resume(root, FORGE_ROOT)
            self.assertIn("2/3 component(s) present", resume["markdown"])
            self.assertNotIn("android_version_code", resume["markdown"])

    def test_monotonic_identity_value_cannot_decrease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            path = self._project_identity_contract(root, version_code=26080102)
            record_project_identity(root, FORGE_ROOT, path)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["monotonic"]["android_version_code"] = 26080101
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot decrease"):
                record_project_identity(root, FORGE_ROOT, path)

    def test_changed_identity_source_requires_renewed_authority_and_self_currency_warns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            path = self._project_identity_contract(root)
            record_project_identity(root, FORGE_ROOT, path)
            build_passport(root, FORGE_ROOT)
            path.write_text(path.read_text(encoding="utf-8") + " \n", encoding="utf-8")
            self.assertEqual(project_identity_record(root)["status"], "approval-required")
            resume = build_resume(root, FORGE_ROOT)
            self.assertEqual(resume["self_currency"]["status"], "WARN")
            identity_truth = next(row for row in resume["self_currency"]["records"] if row["subject"] == "project.identity")
            self.assertEqual(identity_truth["truth_state"], "STALE")

    def test_event_obligation_is_dormant_before_confirmed_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._event_guardrail_contract(root)
            build_passport(root, FORGE_ROOT)
            record_guardrail(root, FORGE_ROOT, contract)
            result = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["guardrails"]["evaluations"][0]["status"], "WAITING_FOR_EVENT")

    def test_confirmed_event_closes_free_change_window_and_blocks_missing_obligations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._event_guardrail_contract(root)
            build_passport(root, FORGE_ROOT)
            record_guardrail(root, FORGE_ROOT, contract)
            evidence = root / "domain-confirmed.md"
            evidence.write_text("# Domain confirmed\n\nThe owner confirmed example.test.\n", encoding="utf-8")
            confirm_project_event(root, FORGE_ROOT, "production-domain-confirmed", evidence)
            result = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(result["status"], "FAIL")
            evaluation = result["guardrails"]["evaluations"][0]
            self.assertEqual(evaluation["status"], "FAIL")
            self.assertEqual([row["id"] for row in evaluation["missing_surfaces"]], ["runtime-config", "operator-docs"])
            self.assertTrue(any(row["check"] == "core.event-obligation" for row in result["findings"]))
            guardrail_truth = next(row for row in result["truth_records"] if row["subject"] == "core.safety-guardrails")
            self.assertEqual(guardrail_truth["result"], "FAIL")

    def test_event_obligation_requires_authority_review_after_all_paths_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._event_guardrail_contract(root)
            build_passport(root, FORGE_ROOT)
            record_guardrail(root, FORGE_ROOT, contract)
            evidence = root / "domain-confirmed.md"
            evidence.write_text("# Domain confirmed\n\nThe owner confirmed example.test.\n", encoding="utf-8")
            confirm_project_event(root, FORGE_ROOT, "production-domain-confirmed", evidence)
            (root / "config" / "cors.json").write_text('{"origins":["https://example.test"]}\n', encoding="utf-8")
            (root / "docs" / "deployment.md").write_text("# Deployment\n\nUse https://example.test.\n", encoding="utf-8")
            result = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["guardrails"]["evaluations"][0]["status"], "AUTHORITY_REVIEW_REQUIRED")
            retire_guardrail(root, "domain-window", "The confirmed domain replaced every temporary placeholder after review.")
            result = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(result["status"], "NOT_RUN")

    def test_shared_fingerprint_lifecycle_applies_to_capability_guardrail_and_trial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            doctor = self._doctor_contract(root)
            guardrail = self._atomic_guardrail_contract(root)
            trial = self._field_trial_contract(root)
            activate_capability(root, FORGE_ROOT, "doctor", doctor)
            record_guardrail(root, FORGE_ROOT, guardrail)
            record_trial(root, FORGE_ROOT, trial)
            doctor.write_text(doctor.read_text(encoding="utf-8") + " \n", encoding="utf-8")
            guardrail.write_text(guardrail.read_text(encoding="utf-8") + " \n", encoding="utf-8")
            trial.write_text(trial.read_text(encoding="utf-8") + " \n", encoding="utf-8")
            self.assertEqual(capability_activations(root)["doctor"]["lifecycle_status"], "approval-required")
            self.assertEqual(guardrail_records(root)["dietary-labels-atomic"]["lifecycle_status"], "approval-required")
            self.assertEqual(trial_records(root)["continuity-trial"]["lifecycle_status"], "approval-required")


    def test_configured_identity_literal_scan_warns_on_copied_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "tools").mkdir()
            identity_path = self._project_identity_contract(root)
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            identity["literal_policy"] = {"scan_paths": ["tools/**"], "exception_paths": [], "file_limit": 20}
            identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
            (root / "tools" / "package.py").write_text('TARGET_VERSION = "0.3.0"\n', encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            record_project_identity(root, FORGE_ROOT, identity_path)
            build_passport(root, FORGE_ROOT)
            result = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["identity_literals"]["status"], "WARN")
            self.assertTrue(any(row["check"] == "core.identity-single-source" for row in result["findings"]))
            identity_truth = next(row for row in result["truth_records"] if row["subject"] == "core.identity-single-source")
            self.assertEqual(identity_truth["result"], "WARN")

    def test_identity_literal_exception_suppresses_intentional_history_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "docs").mkdir()
            identity_path = self._project_identity_contract(root)
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            identity["literal_policy"] = {"scan_paths": ["docs/**"], "exception_paths": ["docs/history.md"], "file_limit": 20}
            identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
            (root / "docs" / "history.md").write_text("Server 0.3.0 shipped previously.\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            record_project_identity(root, FORGE_ROOT, identity_path)
            build_passport(root, FORGE_ROOT)
            result = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(result["identity_literals"]["status"], "PASS")
            self.assertEqual(result["identity_literals"]["findings"], [])

    def test_identity_and_project_events_do_not_add_top_level_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_project_identity(root, FORGE_ROOT, self._project_identity_contract(root))
            evidence = root / "domain-confirmed.md"
            evidence.write_text("confirmed\n", encoding="utf-8")
            confirm_project_event(root, FORGE_ROOT, "production-domain-confirmed", evidence)
            build_resume(root, FORGE_ROOT)
            settings = load_settings(root)
            self.assertIn("project_identity", settings)
            self.assertIn("production-domain-confirmed", settings["project_events"])
            top_level = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(len(top_level), 8)

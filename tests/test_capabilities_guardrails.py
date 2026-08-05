from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from emotivus_forge.core.authority_registry import confirm_authorities, load_or_discover_authorities
from emotivus_forge.core.changes import detect_changes
from emotivus_forge.core.capabilities import activate_capability, capability_activations, validate_activation_contract
from emotivus_forge.core.decision_forks import analyze_decision_forks, resolve_decision_fork
from emotivus_forge.core.guardrails import guardrail_records, record_guardrail
from emotivus_forge.core.field_trials import (
    field_trial_summary, record_observation, record_trial, retire_trial, trial_records, validate_observation,
)
from emotivus_forge.core.confidentiality_boundary import classify_confidentiality_boundaries
from emotivus_forge.core.guidance import build_help
from emotivus_forge.core.native_tools import approve_canonical_native_tool, load_or_discover_native_tools
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.paths import STATE_FILE_NAMES
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.session_close import close_session, parse_durable_pairs
from emotivus_forge.core.startup import run_forge
from emotivus_forge.core.state import load_settings, load_state
from emotivus_forge.core.telemetry import (
    normalize_interaction_telemetry, record_interaction_session, summarize_telemetry,
)
from emotivus_forge.services.scoped_check import run_scoped_check
from emotivus_forge.services.ship import ship_project
from tests.support import FORGE_ROOT, ForgeTestCase


class CapabilityAndGuardrailTests(ForgeTestCase):
    def test_doctor_is_inactive_by_default_and_not_imported_by_ordinary_check(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / ".python-version").write_text(f"{sys.version_info.major}.{sys.version_info.minor}\n", encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                sys.modules.pop("emotivus_forge.services.doctor", None)
                ordinary = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(ordinary["status"], "NOT_RUN")
                self.assertNotIn("emotivus_forge.services.doctor", sys.modules)
                blocked = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["doctor"])
                self.assertEqual(blocked["status"], "FAIL")
                self.assertEqual(blocked["capabilities"][0]["status"], "BLOCKED")
                self.assertNotIn("emotivus_forge.services.doctor", sys.modules)
                self.assertFalse(any("capability_vault" in str(getattr(module, "__file__", "")) for module in sys.modules.values()))

    def test_doctor_activation_contract_enables_explicit_diagnose_only_check(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / ".python-version").write_text(f"{sys.version_info.major}.{sys.version_info.minor}\n", encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                contract = self._doctor_contract(root)
                activation = activate_capability(root, FORGE_ROOT, "doctor", contract)
                self.assertEqual(activation["status"], "active")
                payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["doctor"])
                doctor = payload["capabilities"][0]
                self.assertEqual(payload["status"], "NOT_RUN")
                self.assertEqual(doctor["status"], "PASS")
                self.assertEqual(doctor["mode"], "diagnose-only")
                self.assertEqual(doctor["actions_taken"], [])
                self.assertFalse(doctor["repairs_allowed"])
                self.assertFalse(doctor["legacy_vault_loaded"])
                self.assertIn("emotivus_forge.services.doctor", sys.modules)
                build_resume(root, FORGE_ROOT)
                actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
                self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_doctor_runtime_and_file_budgets_are_enforced(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / ".python-version").write_text(f"{sys.version_info.major}.{sys.version_info.minor}\n", encoding="utf-8")
                for index in range(6):
                    nested = root / f"module-{index}"
                    nested.mkdir()
                    (nested / "requirements.txt").write_text("example==1.0\n", encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                contract = self._doctor_contract(root, runtime_seconds=1, file_limit=2)
                activate_capability(root, FORGE_ROOT, "doctor", contract)
                payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["doctor"])
                budget = payload["capabilities"][0]["budget"]
                self.assertLessEqual(budget["descriptors_observed"], 2)
                self.assertLess(budget["duration_ms"], 3000)
                self.assertEqual(payload["capabilities"][0]["actions_taken"], [])

    def test_doctor_contract_change_requires_explicit_reactivation_before_import(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / ".python-version").write_text(f"{sys.version_info.major}.{sys.version_info.minor}\n", encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                contract = self._doctor_contract(root)
                activate_capability(root, FORGE_ROOT, "doctor", contract)
                contract.write_text(contract.read_text(encoding="utf-8") + " \n", encoding="utf-8")
                sys.modules.pop("emotivus_forge.services.doctor", None)
                states = capability_activations(root)
                self.assertEqual(states["doctor"]["status"], "reactivation-required")
                payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["doctor"])
                self.assertEqual(payload["status"], "FAIL")
                self.assertEqual(payload["capabilities"][0]["status"], "BLOCKED")
                self.assertNotIn("emotivus_forge.services.doctor", sys.modules)

    def test_resume_recommends_doctor_for_durable_environment_risk_without_activation(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                check = run_scoped_check(root, FORGE_ROOT)
                close_session(
                    root, FORGE_ROOT,
                    session_type="audit",
                    next_action="Confirm the production runtime version and required extensions.",
                    unresolved_risks=["The local and target environment may use different PHP extensions."],
                    check_payload=check,
                )
                resume = build_resume(root, FORGE_ROOT)
                recommendations = resume["advanced_capabilities"]["recommendations"]
                self.assertEqual(recommendations[0]["capability_id"], "doctor")
                self.assertEqual(recommendations[0]["status"], "recommended-not-active")
                self.assertIn("Capability recommendations", resume["markdown"])
                self.assertEqual(capability_activations(root), {})

    def test_vaulted_capability_cannot_be_activated_without_certified_implementation(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                contract = self._doctor_contract(root)
                with self.assertRaises(ValueError):
                    validate_activation_contract(root, FORGE_ROOT, "graph", contract)

    def test_atomic_guardrail_records_without_new_state_files_and_resume_preserves_boundary(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._atomic_guardrail_contract(root)
                build_passport(root, FORGE_ROOT)
                record = record_guardrail(root, FORGE_ROOT, contract)
                self.assertEqual(record["status"], "active")
                self.assertTrue(record["event_id"])
                self.assertEqual(guardrail_records(root)["dietary-labels-atomic"]["status"], "active")
                resume = build_resume(root, FORGE_ROOT)
                self.assertIn("Active atomic safety guardrails", resume["markdown"])
                self.assertIn("does not prove the labels are correct", resume["markdown"])
                actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
                self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_atomic_guardrail_blocks_partial_guarded_change(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._atomic_guardrail_contract(root)
                build_passport(root, FORGE_ROOT)
                record_guardrail(root, FORGE_ROOT, contract)
                (root / "admin" / "editor.php").write_text("<?php echo 'labels';\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["status"], "FAIL")
                evaluation = payload["guardrails"]["evaluations"][0]
                self.assertEqual(evaluation["status"], "FAIL")
                self.assertEqual(
                    [item["id"] for item in evaluation["missing_surfaces"]],
                    ["storage", "public-display"],
                )
                finding = next(item for item in payload["findings"] if item["check"] == "core.atomic-guardrail")
                self.assertIn("one atomic change set", finding["message"])
                self.assertIn("false dietary claim", evaluation["unsafe_partial_state"].casefold())

    def test_atomic_guardrail_allows_declared_surface_set_without_claiming_feature_completion(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._atomic_guardrail_contract(root)
                build_passport(root, FORGE_ROOT)
                record_guardrail(root, FORGE_ROOT, contract)
                (root / "migrations" / "001_labels.sql").write_text("ALTER TABLE items ADD dietary TEXT;\n", encoding="utf-8")
                (root / "admin" / "editor.php").write_text("<?php echo 'label controls';\n", encoding="utf-8")
                (root / "public" / "menu.php").write_text("<?php echo 'dietary labels';\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["status"], "NOT_RUN")
                evaluation = payload["guardrails"]["evaluations"][0]
                self.assertEqual(evaluation["status"], "PASS")
                self.assertEqual(evaluation["missing_surfaces"], [])
                self.assertIn(
                    "feature correctness or completion merely because all guardrail surfaces changed",
                    payload["claim_scope"]["excluded"],
                )
                self.assertIn("does not prove feature correctness", payload["guardrails"]["truth_boundary"])

    def test_atomic_guardrail_does_not_block_unrelated_change(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._atomic_guardrail_contract(root)
                build_passport(root, FORGE_ROOT)
                record_guardrail(root, FORGE_ROOT, contract)
                (root / "BACKLOG.md").write_text("# Backlog\n\n## THE NEXT ACTION\n\n- Update wording.\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["status"], "NOT_RUN")
                self.assertEqual(payload["guardrails"]["evaluations"][0]["status"], "NOT_APPLICABLE")

    def test_changed_guardrail_contract_requires_rerecord_before_related_work(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._atomic_guardrail_contract(root)
                build_passport(root, FORGE_ROOT)
                record_guardrail(root, FORGE_ROOT, contract)
                contract.write_text(contract.read_text(encoding="utf-8") + " \n", encoding="utf-8")
                (root / "public" / "menu.php").write_text("<?php echo 'labels changed';\n", encoding="utf-8")
                self.assertEqual(guardrail_records(root)["dietary-labels-atomic"]["status"], "rerecord-required")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["status"], "FAIL")
                self.assertEqual(payload["guardrails"]["evaluations"][0]["status"], "BLOCKED")
                self.assertTrue(any(item["check"] == "core.guardrail-current" for item in payload["findings"]))



class DoctorRuntimeResolutionTests(ForgeTestCase):
    """Doctor must judge the interpreter a project is actually using.

    Regression for a defect found only by executing the suite under a second Python
    version: doctor resolved `python3` on PATH and ignored the running interpreter, so a
    correctly pinned project inside a venv or pyenv shim drew a false blocker.
    """

    def _payload(self, root: Path) -> dict:
        from emotivus_forge.services.doctor import run_doctor
        contract = {"contract": {"budget": {"runtime_seconds": 5, "file_limit": 20, "output_characters": 6000}}}
        return run_doctor(root, contract)

    def test_running_interpreter_is_observed_not_only_path(self) -> None:
        from emotivus_forge.services import doctor
        rows = doctor._python_observations(time.monotonic() + 5)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["source"], "running-interpreter")
        self.assertEqual(Path(rows[0]["executable"]).resolve(), Path(sys.executable).resolve())

    def test_pin_matching_the_running_interpreter_raises_no_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".python-version").write_text(
                f"{sys.version_info.major}.{sys.version_info.minor}\n", encoding="utf-8")
            blockers = [f for f in self._payload(root)["findings"] if f["severity"] == "blocker"]
            self.assertEqual(blockers, [], "a pin matching the running interpreter must not block")

    def test_pin_matching_no_observed_runtime_still_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".python-version").write_text("2.6\n", encoding="utf-8")
            blockers = [f for f in self._payload(root)["findings"] if f["severity"] == "blocker"]
            self.assertEqual(len(blockers), 1)
            self.assertIn("any observed runtime", blockers[0]["message"])

    def test_observation_names_which_runtime_satisfied_the_pin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".python-version").write_text(
                f"{sys.version_info.major}.{sys.version_info.minor}\n", encoding="utf-8")
            rows = [o for o in self._payload(root)["observations"] if o["kind"] == "python-version"]
            self.assertEqual(rows[0]["satisfied_by"], "running-interpreter")
            self.assertTrue(rows[0]["candidates"])

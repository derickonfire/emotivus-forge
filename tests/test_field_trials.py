from __future__ import annotations

import json
import sys
import tempfile
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


class FieldTrialTests(ForgeTestCase):
    def test_field_trial_records_without_new_state_files_and_resume_reports_sample_boundary(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._field_trial_contract(root)
                build_passport(root, FORGE_ROOT)
                record = record_trial(root, FORGE_ROOT, contract)
                self.assertEqual(record["status"], "active")
                self.assertEqual(trial_records(root)["continuity-trial"]["status"], "active")
                resume = build_resume(root, FORGE_ROOT)
                self.assertIn("Active field-validation trials", resume["markdown"])
                self.assertIn("0/3 observation(s)", resume["markdown"])
                self.assertIn("not independent proof of causality", resume["markdown"])
                actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
                self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_field_observation_is_linked_to_session_close_and_aggregated(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._field_trial_contract(root, minimum_observations=1)
                build_passport(root, FORGE_ROOT)
                record_trial(root, FORGE_ROOT, contract)
                observation = self._field_observation(root, "obs-001")
                check = run_scoped_check(root, FORGE_ROOT)
                closed = close_session(
                    root, FORGE_ROOT,
                    session_type="audit",
                    next_action="Run the next controlled field scenario.",
                    check_payload=check,
                    field_observation_path=str(observation),
                )
                self.assertEqual(closed["field_observation"]["observation_id"], "obs-001")
                self.assertEqual(closed["field_observation"]["session_event_id"], closed["event_id"])
                summary = field_trial_summary(root)["active"][0]
                self.assertEqual(summary["sample_status"], "minimum-met")
                self.assertEqual(summary["objective_recovery"]["positive_rate"], 1.0)
                self.assertEqual(summary["doctor_recommendation"]["matrix"]["true_positive"], 1)
                self.assertEqual(summary["guardrail_trigger"]["matrix"]["true_positive"], 1)

    def test_field_observation_rejects_unknown_model_or_scenario(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._field_trial_contract(root)
                build_passport(root, FORGE_ROOT)
                record_trial(root, FORGE_ROOT, contract)
                bad_model = self._field_observation(root, "obs-bad-model", model="UnknownModel")
                with self.assertRaisesRegex(ValueError, "not declared"):
                    validate_observation(root, FORGE_ROOT, bad_model)
                bad_scenario = self._field_observation(root, "obs-bad-scenario", scenario="release-packaging")
                with self.assertRaisesRegex(ValueError, "not declared"):
                    validate_observation(root, FORGE_ROOT, bad_scenario)

    def test_changed_field_trial_contract_blocks_new_observation_until_rerecorded(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._field_trial_contract(root)
                build_passport(root, FORGE_ROOT)
                record_trial(root, FORGE_ROOT, contract)
                contract.write_text(contract.read_text(encoding="utf-8") + " \n", encoding="utf-8")
                self.assertEqual(trial_records(root)["continuity-trial"]["status"], "rerecord-required")
                observation = self._field_observation(root, "obs-stale")
                with self.assertRaisesRegex(ValueError, "not active"):
                    validate_observation(root, FORGE_ROOT, observation)
                resume = build_resume(root, FORGE_ROOT)
                self.assertIn("Field-validation attention", resume["markdown"])

    def test_duplicate_field_observation_id_is_rejected(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._field_trial_contract(root)
                build_passport(root, FORGE_ROOT)
                record_trial(root, FORGE_ROOT, contract)
                observation = self._field_observation(root, "obs-duplicate")
                first = record_observation(root, FORGE_ROOT, observation, session_event_id="session-a")
                self.assertEqual(first["observation_id"], "obs-duplicate")
                with self.assertRaisesRegex(ValueError, "already exists"):
                    record_observation(root, FORGE_ROOT, observation, session_event_id="session-b")

    def test_field_trial_aggregate_exposes_false_positives_and_false_negatives_without_generalizing(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._field_trial_contract(root, minimum_observations=3)
                build_passport(root, FORGE_ROOT)
                record_trial(root, FORGE_ROOT, contract)
                observations = [
                    self._field_observation(root, "obs-matrix-1", doctor_truth="needed", doctor_result="recommended", guardrail_truth="should-trigger", guardrail_result="triggered", minutes=4),
                    self._field_observation(root, "obs-matrix-2", doctor_truth="not-needed", doctor_result="recommended", guardrail_truth="should-not-trigger", guardrail_result="triggered", minutes=8),
                    self._field_observation(root, "obs-matrix-3", doctor_truth="needed", doctor_result="not-recommended", guardrail_truth="should-trigger", guardrail_result="not-triggered", minutes=12),
                ]
                for index, observation in enumerate(observations, start=1):
                    record_observation(root, FORGE_ROOT, observation, session_event_id=f"session-{index}")
                summary = field_trial_summary(root)["active"][0]
                self.assertEqual(summary["sample_status"], "minimum-met")
                self.assertEqual(summary["time_to_meaningful_work"]["median_minutes"], 8.0)
                self.assertEqual(summary["doctor_recommendation"]["matrix"]["false_positive"], 1)
                self.assertEqual(summary["doctor_recommendation"]["matrix"]["false_negative"], 1)
                self.assertEqual(summary["guardrail_trigger"]["matrix"]["false_positive"], 1)
                self.assertEqual(summary["guardrail_trigger"]["matrix"]["false_negative"], 1)
                self.assertIn("not independent proof of causality", summary["truth_boundary"])

    def test_retired_field_trial_preserves_observations_but_rejects_new_ones(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                contract = self._field_trial_contract(root, minimum_observations=1)
                build_passport(root, FORGE_ROOT)
                record_trial(root, FORGE_ROOT, contract)
                first = self._field_observation(root, "obs-before-retire")
                record_observation(root, FORGE_ROOT, first, session_event_id="session-before")
                retired = retire_trial(root, "continuity-trial", "The bounded trial is complete.", authority="owner")
                self.assertEqual(retired["status"], "retired")
                summary = field_trial_summary(root)
                self.assertEqual(summary["retired"][0]["observation_count"], 1)
                second = self._field_observation(root, "obs-after-retire")
                with self.assertRaisesRegex(ValueError, "not active"):
                    validate_observation(root, FORGE_ROOT, second)


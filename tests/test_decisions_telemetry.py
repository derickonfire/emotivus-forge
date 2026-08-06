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


class DecisionAndTelemetryTests(ForgeTestCase):
    def test_resume_detects_date_only_vs_exact_time_fork_before_implementation(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._deadline_fork_fixture(root)
                build_passport(root, FORGE_ROOT)
                resume = build_resume(root, FORGE_ROOT)
                pending = resume["decision_forks"]["pending"]
                self.assertEqual([item["id"] for item in pending], ["deadline-precision"])
                fork = pending[0]
                self.assertEqual(fork["recommendation"]["option_id"], "add-optional-exact-time")
                self.assertEqual(fork["required_authority"], "product owner or confirmed architecture-decision authority")
                self.assertIn("Pending decision forks", resume["markdown"])
                self.assertEqual(resume["status"], "ATTENTION")

    def test_decision_resolution_records_accepted_and_rejected_options(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._deadline_fork_fixture(root)
                build_passport(root, FORGE_ROOT)
                resolution = resolve_decision_fork(
                    root, FORGE_ROOT,
                    fork_id="deadline-precision",
                    option_id="add-optional-exact-time",
                    rationale="Represent exact deadlines honestly without inventing times for historical records.",
                    authority="owner",
                )
                self.assertEqual(resolution["accepted_option"]["id"], "add-optional-exact-time")
                self.assertEqual(
                    sorted(item["id"] for item in resolution["rejected_options"]),
                    ["coerce-exact-presets-to-dates", "preserve-date-only"],
                )
                ledger = (root / ".forge" / "ledger.jsonl").read_text(encoding="utf-8")
                self.assertIn('"kind":"decision-fork-resolution"', ledger)
                self.assertIn("coerce-exact-presets-to-dates", ledger)
                resume = build_resume(root, FORGE_ROOT)
                self.assertEqual(resume["decision_forks"]["pending"], [])
                self.assertIn("Governing decisions", resume["markdown"])
                self.assertIn("Represent exact deadlines honestly", resume["markdown"])

    def test_governing_decision_persists_after_triggering_requirement_is_removed(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._deadline_fork_fixture(root)
                build_passport(root, FORGE_ROOT)
                resolve_decision_fork(
                    root, FORGE_ROOT,
                    fork_id="deadline-precision", option_id="add-optional-exact-time",
                    rationale="Preserve compatibility while adding truthful precision.", authority="owner",
                )
                (root / "requirements.md").write_text("# Requirements\n\nKeep follow-up scheduling documented.\n", encoding="utf-8")
                analysis = analyze_decision_forks(root, FORGE_ROOT)
                self.assertEqual(analysis["pending"], [])
                self.assertEqual(analysis["governing_decisions"][0]["fork_id"], "deadline-precision")
                self.assertEqual(analysis["governing_decisions"][0]["accepted_option"]["id"], "add-optional-exact-time")

    def test_resume_warns_when_changed_work_contradicts_confirmed_decision(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._deadline_fork_fixture(root)
                build_passport(root, FORGE_ROOT)
                resolve_decision_fork(
                    root, FORGE_ROOT,
                    fork_id="deadline-precision", option_id="add-optional-exact-time",
                    rationale="Exact presets require exact storage.", authority="owner",
                )
                (root / "followup.html").write_text(
                    '<label>15 Minutes <input type="date" name="due_date"></label>\n'
                    '<!-- Map 15-minute to today; round the deadline to the date. -->\n',
                    encoding="utf-8",
                )
                resume = build_resume(root, FORGE_ROOT)
                warnings = resume["decision_forks"]["contradictions"]
                self.assertEqual(len(warnings), 1)
                self.assertIn("contradicting the confirmed optional exact-time decision", warnings[0]["message"])
                self.assertIn("Decision contradiction warnings", resume["markdown"])

    def test_cross_model_resume_context_is_stable_and_model_neutral(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._deadline_fork_fixture(root)
                build_passport(root, FORGE_ROOT)
                resolve_decision_fork(
                    root, FORGE_ROOT,
                    fork_id="deadline-precision", option_id="preserve-date-only",
                    rationale="The owner declined minute-level deadlines for this project.", authority="owner",
                )
                first = build_resume(root, FORGE_ROOT, budget="compact")["markdown"]
                second = build_resume(root, FORGE_ROOT, budget="compact")["markdown"]
                self.assertEqual(first, second)
                self.assertIn("preserve-date-only", first)
                self.assertIn("Rejected options", first)
                self.assertNotIn("Claude", first)
                self.assertNotIn("ChatGPT", first)

    def test_single_precision_model_does_not_create_a_false_fork(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "requirements.md").write_text("# Requirements\n\nDeadlines use calendar dates only.\n", encoding="utf-8")
                (root / "form.html").write_text('<input type="date" name="due_date">\n', encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                analysis = analyze_decision_forks(root, FORGE_ROOT)
                self.assertEqual(analysis["pending"], [])

    def test_resume_estimate_is_explicitly_heuristic_not_provider_measurement(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                resume = build_resume(root, FORGE_ROOT)
                self.assertIn("heuristic characters/4; not provider measurement and not savings", resume["markdown"])
                latest_metric = json.loads((root / ".forge" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()[-1])
                self.assertIn("resume_token_estimate", latest_metric)
                self.assertEqual(latest_metric["resume_token_estimate_source"], "heuristic-characters-divided-by-four")
                self.assertNotIn("estimated_tokens", latest_metric)

    def test_provider_tokens_require_complete_named_exact_counts(self) -> None:
            with self.assertRaises(ValueError):
                normalize_interaction_telemetry(provider="Example", provider_input_tokens=10)
            with self.assertRaises(ValueError):
                normalize_interaction_telemetry(provider_input_tokens=10, provider_output_tokens=5)
            telemetry = normalize_interaction_telemetry(
                provider="Example Provider", provider_input_tokens=100, provider_output_tokens=25,
            )
            self.assertEqual(telemetry["exact_provider_tokens"]["source"], "provider-reported")
            self.assertEqual(telemetry["exact_provider_tokens"]["total_tokens"], 125)

    def test_session_close_records_exact_provider_metrics_and_observed_retries(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                check = run_scoped_check(root, FORGE_ROOT)
                telemetry = normalize_interaction_telemetry(
                    provider="Example Provider", provider_input_tokens=120, provider_output_tokens=30,
                    retry_count=2, correction_count=1, session_output_characters=900,
                )
                closed = close_session(
                    root, FORGE_ROOT, session_type="code-increment", next_action="Run the next fixture.",
                    check_payload=check, interaction_telemetry=telemetry,
                )
                self.assertEqual(closed["interaction_telemetry"]["exact_provider_tokens"]["total_tokens"], 150)
                summary = summarize_telemetry(root)
                self.assertEqual(summary["exact_provider"]["total_tokens"], 150)
                self.assertEqual(summary["observed"]["recorded_retry_count"], 2)
                self.assertEqual(summary["observed"]["recorded_correction_count"], 1)

    def test_break_even_remains_unknown_without_three_matched_exact_pairs(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                summary = summarize_telemetry(root)
                self.assertEqual(summary["benchmark"]["break_even"]["status"], "insufficient-pairs")
                self.assertIn("small one-off task", summary["suitability"])
                self.assertIn("No workspace-byte compression", summary["truth_boundary"])

    def test_three_matched_benchmark_pairs_measure_exact_in_sample_delta(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                for index in range(3):
                    for arm, total in (("with-forge", 700), ("without-forge", 1000)):
                        telemetry = normalize_interaction_telemetry(
                            provider="Example Provider",
                            provider_input_tokens=total - 100,
                            provider_output_tokens=100,
                            benchmark_id=f"matched-{index}", benchmark_arm=arm,
                        )
                        record_interaction_session(root, telemetry, session_event_id=f"event-{index}-{arm}")
                summary = summarize_telemetry(root)
                result = summary["benchmark"]["break_even"]
                self.assertEqual(result["status"], "observed-in-sample")
                self.assertEqual(result["observed_pairs"], 3)
                self.assertEqual(result["aggregate_token_delta"], 900)
                self.assertIn("not a universal savings claim", result["conclusion"])

    def test_cross_provider_benchmark_pair_is_rejected(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                with_forge = normalize_interaction_telemetry(
                    provider="Provider A", provider_input_tokens=500, provider_output_tokens=100,
                    benchmark_id="matched-provider", benchmark_arm="with-forge",
                )
                without_forge = normalize_interaction_telemetry(
                    provider="Provider B", provider_input_tokens=700, provider_output_tokens=100,
                    benchmark_id="matched-provider", benchmark_arm="without-forge",
                )
                record_interaction_session(root, with_forge, session_event_id="with")
                record_interaction_session(root, without_forge, session_event_id="without")
                summary = summarize_telemetry(root)
                self.assertEqual(summary["benchmark"]["pairs"], [])
                self.assertEqual(summary["benchmark"]["rejected_comparisons"][0]["reason"], "provider-mismatch")
                self.assertEqual(summary["benchmark"]["break_even"]["status"], "insufficient-pairs")

    def test_benchmark_requires_exact_provider_measurement(self) -> None:
            with self.assertRaises(ValueError):
                normalize_interaction_telemetry(benchmark_id="trial", benchmark_arm="with-forge")
            with self.assertRaises(ValueError):
                normalize_interaction_telemetry(
                    provider="Example", provider_input_tokens=10, provider_output_tokens=2,
                    benchmark_id="trial", benchmark_arm="invalid-arm",
                )

    def test_resume_reports_current_reuse_without_changing_between_repeated_reads(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                first = build_resume(root, FORGE_ROOT)
                second = build_resume(root, FORGE_ROOT)
                self.assertEqual(first["markdown"], second["markdown"])
                self.assertIn("## Efficiency telemetry", first["markdown"])
                self.assertIn("Break-even is not established", first["markdown"])
                self.assertGreaterEqual(first["telemetry"]["observed"]["current_cached_records_reused"], 1)


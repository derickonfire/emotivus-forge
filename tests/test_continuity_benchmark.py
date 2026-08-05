from __future__ import annotations

from emotivus_forge.core import continuity_benchmark as cb
from tests.support import ForgeTestCase

PARENT = "a" * 64
TASK = {
    "name": "resume-after-cold-start",
    "instruction": "Resume the project and state the next action.",
    "success_criteria": ["names the correct next action", "cites exact parent package"],
    "turns": 3,
}


def _run(arm: str, **overrides: object) -> dict[str, object]:
    base = {
        "task_id": "t1", "arm": arm, "parent_sha256": PARENT,
        "provider": "acme", "model": "acme-1",
        "workspace": f"/tmp/ws-{arm}",
        "exact_input_tokens": 100, "exact_output_tokens": 50,
        "human_review": {"reviewer": "owner", "accepted": True},
    }
    base.update(overrides)
    return base


class ContinuityBenchmarkTests(ForgeTestCase):
    def test_task_identity_is_content_addressed(self) -> None:
        sealed = cb.define_task(TASK)
        self.assertEqual(len(sealed["task_id"]), 64)
        self.assertTrue(cb.verify_task_immutable(sealed))

    def test_changing_any_field_yields_a_different_task_not_an_edit(self) -> None:
        first = cb.define_task(TASK)
        altered = dict(TASK); altered["turns"] = 4
        second = cb.define_task(altered)
        self.assertNotEqual(first["task_id"], second["task_id"])

    def test_tampered_task_content_fails_immutability_check(self) -> None:
        sealed = cb.define_task(TASK)
        sealed["content"]["instruction"] = "something else"
        self.assertFalse(cb.verify_task_immutable(sealed))

    def test_incomplete_task_definitions_are_rejected(self) -> None:
        for missing in ("name", "instruction", "success_criteria", "turns"):
            partial = dict(TASK); partial.pop(missing)
            with self.assertRaises(cb.BenchmarkError):
                cb.define_task(partial)

    def test_task_requires_positive_turns_and_real_criteria(self) -> None:
        with self.assertRaises(cb.BenchmarkError):
            cb.define_task({**TASK, "turns": 0})
        with self.assertRaises(cb.BenchmarkError):
            cb.define_task({**TASK, "success_criteria": [""]})

    def test_run_requires_exact_provider_token_counts(self) -> None:
        with self.assertRaises(cb.BenchmarkError):
            cb.record_run(_run(cb.FORGE_ARM, exact_input_tokens="about 100"))
        with self.assertRaises(cb.BenchmarkError):
            cb.record_run(_run(cb.FORGE_ARM, exact_output_tokens=-1))

    def test_estimated_token_source_is_rejected_outright(self) -> None:
        with self.assertRaises(cb.BenchmarkError):
            cb.record_run(_run(cb.FORGE_ARM, token_source="heuristic-characters-divided-by-four"))

    def test_boolean_tokens_are_not_accepted_as_integers(self) -> None:
        with self.assertRaises(cb.BenchmarkError):
            cb.record_run(_run(cb.FORGE_ARM, exact_input_tokens=True))

    def test_run_requires_a_full_parent_digest(self) -> None:
        with self.assertRaises(cb.BenchmarkError):
            cb.record_run(_run(cb.FORGE_ARM, parent_sha256="abc123"))

    def test_unknown_arm_is_rejected(self) -> None:
        with self.assertRaises(cb.BenchmarkError):
            cb.record_run(_run("experimental"))

    def test_run_without_human_review_is_recorded_but_inadmissible(self) -> None:
        record = cb.record_run(_run(cb.FORGE_ARM, human_review={}))
        self.assertFalse(record["admissible"])
        self.assertIn("human review", record["admissibility_reason"])

    def test_review_must_be_accepted_not_merely_present(self) -> None:
        record = cb.record_run(_run(cb.FORGE_ARM, human_review={"reviewer": "owner", "accepted": False}))
        self.assertFalse(record["admissible"])

    def test_shared_workspaces_are_reported_as_collisions(self) -> None:
        runs = [cb.record_run(_run(cb.FORGE_ARM, workspace="/tmp/same")),
                cb.record_run(_run(cb.CONTROL_ARM, workspace="/tmp/same"))]
        isolation = cb.check_workspace_isolation(runs)
        self.assertFalse(isolation["isolated"])
        self.assertEqual(len(isolation["collisions"]), 1)

    def test_zero_runs_reports_not_run_never_a_tie(self) -> None:
        result = cb.compare_arms([])
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertEqual(result["pairs"], [])
        self.assertIn("never a tie", result["truth_boundary"])

    def test_only_one_arm_reports_incomplete_not_a_result(self) -> None:
        result = cb.compare_arms([cb.record_run(_run(cb.FORGE_ARM))])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["unpaired"][0]["missing_arm"], cb.CONTROL_ARM)

    def test_matched_arms_pair_and_report_token_delta(self) -> None:
        runs = [cb.record_run(_run(cb.FORGE_ARM, exact_input_tokens=100, exact_output_tokens=50)),
                cb.record_run(_run(cb.CONTROL_ARM, exact_input_tokens=200, exact_output_tokens=80))]
        result = cb.compare_arms(runs)
        self.assertEqual(result["status"], "PAIRED")
        pair = result["pairs"][0]
        self.assertEqual(pair["forge_total_tokens"], 150)
        self.assertEqual(pair["control_total_tokens"], 280)
        self.assertEqual(pair["token_delta"], -130)

    def test_runs_on_different_models_never_pair(self) -> None:
        runs = [cb.record_run(_run(cb.FORGE_ARM, model="acme-1")),
                cb.record_run(_run(cb.CONTROL_ARM, model="acme-2"))]
        result = cb.compare_arms(runs)
        self.assertEqual(result["pairs"], [])
        self.assertEqual(len(result["unpaired"]), 2)

    def test_runs_against_different_parents_never_pair(self) -> None:
        runs = [cb.record_run(_run(cb.FORGE_ARM, parent_sha256="a" * 64)),
                cb.record_run(_run(cb.CONTROL_ARM, parent_sha256="b" * 64))]
        self.assertEqual(cb.compare_arms(runs)["pairs"], [])

    def test_inadmissible_runs_are_excluded_and_listed(self) -> None:
        runs = [cb.record_run(_run(cb.FORGE_ARM)),
                cb.record_run(_run(cb.CONTROL_ARM, human_review={}))]
        result = cb.compare_arms(runs)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(len(result["inadmissible_runs"]), 1)
        self.assertEqual(result["runs_admissible"], 1)

    def test_comparison_reports_workspace_isolation(self) -> None:
        runs = [cb.record_run(_run(cb.FORGE_ARM, workspace="/tmp/x")),
                cb.record_run(_run(cb.CONTROL_ARM, workspace="/tmp/x"))]
        self.assertFalse(cb.compare_arms(runs)["workspace_isolation"]["isolated"])

    def test_declared_suite_is_not_an_executed_suite(self) -> None:
        suite = cb.define_suite("continuity-100", [TASK], 100)
        self.assertEqual(suite["execution_status"], "NOT_RUN")
        self.assertEqual(suite["sessions_recorded"], 0)
        self.assertTrue(suite["declared_not_executed"])
        self.assertIn("never achievement", suite["truth_boundary"])

    def test_suite_rejects_duplicate_and_empty_task_sets(self) -> None:
        with self.assertRaises(cb.BenchmarkError):
            cb.define_suite("empty", [], 100)
        with self.assertRaises(cb.BenchmarkError):
            cb.define_suite("dupe", [TASK, dict(TASK)], 100)

    def test_suite_identity_is_stable_and_content_addressed(self) -> None:
        first = cb.define_suite("continuity-1000", [TASK], 1000)
        second = cb.define_suite("continuity-1000", [TASK], 1000)
        third = cb.define_suite("continuity-1000", [TASK], 100)
        self.assertEqual(first["suite_id"], second["suite_id"])
        self.assertNotEqual(first["suite_id"], third["suite_id"])

    def test_results_are_deterministic(self) -> None:
        runs = [cb.record_run(_run(cb.FORGE_ARM)), cb.record_run(_run(cb.CONTROL_ARM))]
        self.assertEqual(cb.compare_arms(runs), cb.compare_arms(list(reversed(runs))))

    def test_harness_persists_nothing_itself(self) -> None:
        from pathlib import Path
        source = Path(cb.__file__).read_text(encoding="utf-8")
        for forbidden in ("write_text", "write_json", "open(", "mkdir"):
            self.assertNotIn(forbidden, source, "the harness must not write state itself")

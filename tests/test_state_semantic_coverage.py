from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from emotivus_forge.core.capabilities import activate_capability
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.project_identity import record_project_identity
from emotivus_forge.core.state_transitions import record_state_transition
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = ("<main>Semantic transition ready</main>" + "x" * 200).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class SemanticStateCoverageTests(ForgeTestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _base(self, root: Path) -> dict[str, Path]:
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        record_project_identity(root, FORGE_ROOT, self._project_identity_contract(root))
        (root / "fixtures").mkdir()
        before = root / "fixtures" / "before.json"
        after = root / "fixtures" / "after.json"
        before.write_text(json.dumps({"schema": 42, "rows": [{"id": 1, "status": "active"}]}, sort_keys=True) + "\n")
        after.write_text(json.dumps({"schema": 43, "rows": [{"id": 1, "status": "active", "archived_at": None}]}, sort_keys=True) + "\n")
        migration = root / "migration.sql"
        migration.write_text("ALTER TABLE tasks ADD archived_at DATETIME NULL;\n")
        artifact = root / "candidate.zip"
        artifact.write_bytes(b"semantic candidate")
        recipe = root / "semantic.runtime.json"
        recipe.write_text(json.dumps({
            "schema": 1,
            "recipe_id": "semantic-home",
            "title": "Semantic transition response",
            "verification_tier": "staging",
            "request": {"url": self.origin + "/", "method": "GET", "timeout_seconds": 2, "max_response_bytes": 4096, "headers": {"Accept": "text/html"}},
            "assertions": {"status_in": [200], "content_type_in": ["text/html"], "min_bytes": 100, "must_contain": ["Semantic transition ready"], "must_not_contain": ["Fatal error"]},
            "exclusions": ["browser execution", "database semantics", "release readiness"],
        }, indent=2) + "\n")
        (root / "need.md").write_text("# Runtime need\n\nVerify bounded content.\n")
        activation = root / "runtime.activation.json"
        activation.write_text(json.dumps({
            "schema": 1,
            "capability_id": "runtime-proof",
            "authority": "owner",
            "trigger": {"description": "State transition requires bounded HTTP evidence.", "evidence_paths": ["need.md"]},
            "scope": {"included": ["declared response"], "excluded": ["deployment", "database contents", "release readiness"]},
            "budget": {"runtime_seconds": 5, "file_limit": 4, "output_characters": 8000},
            "focused_regressions": ["runtime-proof.inactive-by-default", "runtime-proof.explicit-contract", "runtime-proof.content-aware", "runtime-proof.tiny-error-page-fails", "runtime-proof.host-bound", "runtime-proof.budget-bound", "runtime-proof.contract-change-requires-reactivation"],
            "native_advantage": {"status": "distinct-value", "explanation": "Bounded HTTP content proof without deployment claims."},
            "runtime_proof": {"allowed_origins": [self.origin], "recipe_paths": [recipe.name]},
            "allow_repairs": False,
        }, indent=2) + "\n")
        activate_capability(root, FORGE_ROOT, "runtime-proof", activation)
        return {"before": before, "after": after, "migration": migration, "artifact": artifact}

    def _state(self, state_id: str, description: str, fixture: str, *, semantic: bool = False) -> dict:
        state = {"state_id": state_id, "description": description, "fixture_path": fixture}
        if semantic:
            state.update({
                "comparison_mode": "semantic",
                "semantic_validators": [
                    {"validator_id": "schema-current", "kind": "json-value-equals", "path": "schema", "expected": 43},
                    {"validator_id": "has-rows", "kind": "json-array-count", "path": "rows", "minimum": 1},
                    {"validator_id": "unique-ids", "kind": "json-array-unique", "path": "rows", "field": "id"},
                    {"validator_id": "required-fields", "kind": "json-array-all-have-fields", "path": "rows", "fields": ["id", "status"]},
                    {"validator_id": "no-deleted", "kind": "json-array-none-equals", "path": "rows", "field": "status", "value": "deleted"},
                ],
            })
        return state

    def _transition(self, transition_id: str, files: dict[str, Path], *, semantic_after: bool = False, rollback: str = "none") -> dict:
        return {
            "transition_id": transition_id,
            "target_environment": "neutral-staging",
            "deployment_stage": "staging",
            "verification_tier": "staging",
            "baseline_field": "baseline.build_id",
            "before_state": self._state("schema-42", "Controlled prior state for this scenario.", "fixtures/before.json"),
            "expected_after_state": self._state("schema-43", "Expected state after the declared transition.", "fixtures/after.json", semantic=semantic_after),
            "deployment_artifact_path": files["artifact"].name,
            "migration_paths": [files["migration"].name],
            "runtime_recipe_ids": ["semantic-home"],
            "evidence_authorities": ["owner", "external-ci"],
            "rollback": {"requirement": rollback, "restored_state_id": "schema-42", "runtime_recipe_ids": ["semantic-home"] if rollback == "drill" else []},
            "exclusions": ["production traffic", "hidden database contents", "automatic deployment", "release readiness"],
        }

    def _plan(self, root: Path, transitions: list[dict], coverage: list[dict] | None = None) -> dict:
        path = root / "transition-plan.json"
        path.write_text(json.dumps({
            "schema": 2,
            "plan_id": "semantic-transition-plan",
            "title": "Semantic transition and explicit coverage plan",
            "authority": "owner",
            "candidate_fields": ["build_id", "components.server.version"],
            "transitions": transitions,
            "coverage_requirements": coverage or [],
            "verification_boundary": "This plan validates bounded JSON snapshot invariants and declared coverage without executing deployment, migration, restoration, rollback, arbitrary project code, or release certification.",
        }, indent=2) + "\n")
        return record_state_transition(root, FORGE_ROOT, path)

    def _evidence(self, root: Path, plan: dict, files: dict[str, Path], transition_id: str, observed_after: Path, *, rollback: str = "none") -> Path:
        transition = next(row for row in plan["contract"]["transitions"] if row["transition_id"] == transition_id)
        evidence_dir = root / f"evidence-{transition_id}"
        evidence_dir.mkdir()
        before = evidence_dir / "before.json"
        after = evidence_dir / "after.json"
        before.write_bytes(files["before"].read_bytes())
        after.write_bytes(observed_after.read_bytes())
        receipt = evidence_dir / "deploy.json"
        receipt.write_text(json.dumps({
            "schema": 1, "kind": "deployment-receipt", "candidate_binding": plan["contract"]["candidate_binding"],
            "target_environment": transition["target_environment"], "deployment_stage": transition["deployment_stage"],
            "baseline_value": transition["baseline_value"], "artifact_path": files["artifact"].name,
            "artifact_sha256": hashlib.sha256(files["artifact"].read_bytes()).hexdigest(), "result": "PASS", "observed_utc": "2026-08-01T22:00:00Z",
        }, indent=2) + "\n")
        rollback_payload: dict[str, object] = {}
        if rollback == "availability":
            available = evidence_dir / "rollback-available.json"
            available.write_text(json.dumps({
                "schema": 1, "kind": "rollback-availability-receipt", "candidate_binding": plan["contract"]["candidate_binding"],
                "target_environment": transition["target_environment"], "deployment_stage": transition["deployment_stage"],
                "baseline_value": transition["baseline_value"], "result": "PASS", "rollback_method": "restore bounded fixture snapshot", "observed_utc": "2026-08-01T22:01:00Z",
            }, indent=2) + "\n")
            rollback_payload = {"availability_receipt_path": str(available.relative_to(root))}
        evidence = root / f"evidence-{transition_id}.json"
        evidence.write_text(json.dumps({
            "schema": 1,
            "plan_id": plan["contract"]["plan_id"],
            "transition_id": transition_id,
            "authority": "external-ci",
            "candidate_binding": plan["contract"]["candidate_binding"],
            "target_environment": transition["target_environment"],
            "deployment_stage": transition["deployment_stage"],
            "baseline_value": transition["baseline_value"],
            "transition_result": "PASS",
            "before_snapshot_path": str(before.relative_to(root)),
            "after_snapshot_path": str(after.relative_to(root)),
            "deployment_receipt_path": str(receipt.relative_to(root)),
            "migration_results": [{"path": files["migration"].name, "sha256": hashlib.sha256(files["migration"].read_bytes()).hexdigest(), "status": "PASS"}],
            "rollback": rollback_payload,
        }, indent=2) + "\n")
        return evidence

    def test_semantic_snapshot_accepts_nonidentical_valid_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self._base(root)
            observed = root / "observed-after.json"
            observed.write_text(json.dumps({"schema": 43, "rows": [{"id": 1, "status": "active", "extra": True}, {"id": 2, "status": "archived"}]}) + "\n")
            plan = self._plan(root, [self._transition("legacy-populated", files, semantic_after=True)])
            evidence = self._evidence(root, plan, files, "legacy-populated", observed)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "NOT_RUN")
            row = payload["state_transitions"]["evaluations"][0]["transitions"][0]
            self.assertEqual(row["after_snapshot"]["semantic"]["status"], "PASS")
            self.assertNotEqual(row["after_snapshot"]["sha256"], plan["contract"]["transitions"][0]["expected_after_state"]["fixture"]["sha256"])

    def test_semantic_snapshot_duplicate_identifier_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self._base(root)
            observed = root / "bad-after.json"
            observed.write_text(json.dumps({"schema": 43, "rows": [{"id": 1, "status": "active"}, {"id": 1, "status": "archived"}]}) + "\n")
            plan = self._plan(root, [self._transition("legacy-populated", files, semantic_after=True)])
            evidence = self._evidence(root, plan, files, "legacy-populated", observed)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("semantic validation" in row["message"] for row in payload["findings"]))

    def test_declared_coverage_remains_partial_when_one_transition_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self._base(root)
            transitions = [self._transition("fresh-empty", files), self._transition("legacy-populated", files)]
            coverage = [{"coverage_id": "minimum-upgrade-matrix", "description": "Both fresh and legacy persisted-state paths must be observed.", "mode": "all", "transition_ids": ["fresh-empty", "legacy-populated"]}]
            plan = self._plan(root, transitions, coverage)
            evidence = self._evidence(root, plan, files, "fresh-empty", files["after"])
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "NOT_RUN")
            evaluation = payload["state_transitions"]["evaluations"][0]
            self.assertEqual(evaluation["status"], "PARTIAL")
            self.assertEqual(evaluation["coverage"]["partial_count"], 1)
            self.assertEqual(payload["state_transitions"]["not_run_count"], 1)

    def test_coverage_passes_only_when_all_required_transitions_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self._base(root)
            transitions = [self._transition("fresh-empty", files), self._transition("legacy-populated", files)]
            coverage = [{"coverage_id": "minimum-upgrade-matrix", "description": "Both fresh and legacy persisted-state paths must be observed.", "mode": "all", "transition_ids": ["fresh-empty", "legacy-populated"]}]
            plan = self._plan(root, transitions, coverage)
            evidence = [self._evidence(root, plan, files, transition_id, files["after"]) for transition_id in ("fresh-empty", "legacy-populated")]
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(path) for path in evidence])
            evaluation = payload["state_transitions"]["evaluations"][0]
            self.assertEqual(evaluation["status"], "PASS")
            self.assertEqual(evaluation["coverage"]["confirmed_count"], 1)

    def test_availability_only_rollback_is_distinct_from_drill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self._base(root)
            plan = self._plan(root, [self._transition("availability-only", files, rollback="availability")])
            evidence = self._evidence(root, plan, files, "availability-only", files["after"], rollback="availability")
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "NOT_RUN")
            rollback = payload["state_transitions"]["evaluations"][0]["transitions"][0]["rollback"]
            self.assertEqual(rollback["availability_status"], "PASS")
            self.assertEqual(rollback["drill_status"], "NOT_REQUIRED")
            self.assertEqual(rollback["post_rollback_correctness"], "NOT_REQUIRED")

    def test_availability_requirement_without_receipt_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self._base(root)
            plan = self._plan(root, [self._transition("availability-only", files, rollback="availability")])
            evidence = self._evidence(root, plan, files, "availability-only", files["after"])
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("availability receipt" in row["message"] for row in payload["findings"]))

    def test_semantic_mode_requires_validators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self._base(root)
            transition = self._transition("invalid-semantic", files)
            transition["expected_after_state"]["comparison_mode"] = "semantic"
            with self.assertRaisesRegex(ValueError, "requires semantic_validators"):
                self._plan(root, [transition])


if __name__ == "__main__":
    unittest.main()


class AdditionalSemanticValidatorTests(unittest.TestCase):
    def test_array_values_in_and_reference_integrity_pass(self) -> None:
        from emotivus_forge.core.semantic_state import evaluate_semantic_validators, validate_semantic_validators
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps({
                "groups": [{"id": 1}, {"id": 2}],
                "memberships": [
                    {"group_id": 1, "status": "active"},
                    {"group_id": 2, "status": "inactive"},
                ],
            }) + "\n", encoding="utf-8")
            validators = validate_semantic_validators([
                {"validator_id": "membership-statuses", "kind": "json-array-values-in", "path": "memberships", "field": "status", "allowed": ["active", "inactive"]},
                {"validator_id": "membership-groups", "kind": "json-array-references-exist", "path": "memberships", "field": "group_id", "target_path": "groups", "target_field": "id"},
            ], "semantic_validators")
            result = evaluate_semantic_validators(path, validators)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["passed"], 2)

    def test_dangling_reference_and_unknown_value_fail(self) -> None:
        from emotivus_forge.core.semantic_state import evaluate_semantic_validators, validate_semantic_validators
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps({
                "groups": [{"id": 1}],
                "memberships": [{"group_id": 9, "status": "mystery"}],
            }) + "\n", encoding="utf-8")
            validators = validate_semantic_validators([
                {"validator_id": "membership-statuses", "kind": "json-array-values-in", "path": "memberships", "field": "status", "allowed": ["active", "inactive"]},
                {"validator_id": "membership-groups", "kind": "json-array-references-exist", "path": "memberships", "field": "group_id", "target_path": "groups", "target_field": "id"},
            ], "semantic_validators")
            result = evaluate_semantic_validators(path, validators)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["failed"], 2)

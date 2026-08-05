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
from emotivus_forge.core.paths import STATE_FILE_NAMES
from emotivus_forge.core.project_identity import record_project_identity
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.state_transitions import (
    record_state_transition,
    retire_state_transition,
    state_transition_records,
)
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = ("<!doctype html><html><body><main id='app'>Transition candidate ready</main>" + "x" * 200 + "</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class PersistedStateTransitionTests(ForgeTestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _setup(self, root: Path, *, rollback_required: bool = True) -> tuple[dict, Path, Path, Path, Path, Path]:
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        record_project_identity(root, FORGE_ROOT, self._project_identity_contract(root))

        (root / "fixtures").mkdir()
        before = root / "fixtures" / "before-state.json"
        after = root / "fixtures" / "after-state.json"
        before.write_text(json.dumps({"schema": 42, "rows": [{"id": 1, "status": "active"}]}, sort_keys=True) + "\n", encoding="utf-8")
        after.write_text(json.dumps({"schema": 43, "rows": [{"id": 1, "status": "active", "archived_at": None}]}, sort_keys=True) + "\n", encoding="utf-8")

        (root / "migrations").mkdir()
        migration = root / "migrations" / "043_upgrade.sql"
        migration.write_text("ALTER TABLE tasks ADD COLUMN archived_at DATETIME NULL;\n", encoding="utf-8")
        artifact = root / "candidate-package.zip"
        artifact.write_bytes(b"neutral candidate package bytes")

        recipe = root / "transition.runtime.json"
        recipe.write_text(json.dumps({
            "schema": 1,
            "recipe_id": "transition-homepage",
            "title": "Transition candidate renders expected application content",
            "verification_tier": "staging",
            "request": {
                "url": self.origin + "/",
                "method": "GET",
                "timeout_seconds": 2,
                "max_response_bytes": 4096,
                "headers": {"Accept": "text/html"},
            },
            "assertions": {
                "status_in": [200],
                "content_type_in": ["text/html"],
                "min_bytes": 100,
                "must_contain": ["Transition candidate ready"],
                "must_not_contain": ["Fatal error", "Traceback"],
            },
            "exclusions": ["JavaScript execution", "visual layout", "database semantics", "release readiness"],
        }, indent=2) + "\n", encoding="utf-8")
        (root / "runtime-proof-need.md").write_text("# Runtime proof\n\nConfirm the transition candidate response.\n", encoding="utf-8")
        activation = root / "runtime-proof.activation.json"
        activation.write_text(json.dumps({
            "schema": 1,
            "capability_id": "runtime-proof",
            "authority": "owner",
            "trigger": {"description": "The transition needs bounded content-aware HTTP evidence.", "evidence_paths": ["runtime-proof-need.md"]},
            "scope": {"included": ["declared transition HTTP response"], "excluded": ["deployment execution", "database semantics", "release readiness"]},
            "budget": {"runtime_seconds": 5, "file_limit": 4, "output_characters": 8000},
            "focused_regressions": [
                "runtime-proof.inactive-by-default", "runtime-proof.explicit-contract", "runtime-proof.content-aware",
                "runtime-proof.tiny-error-page-fails", "runtime-proof.host-bound", "runtime-proof.budget-bound",
                "runtime-proof.contract-change-requires-reactivation",
            ],
            "native_advantage": {"status": "distinct-value", "explanation": "This verifies bounded transition HTTP content without replacing deployment or database assurance."},
            "runtime_proof": {"allowed_origins": [self.origin], "recipe_paths": [recipe.name]},
            "allow_repairs": False,
        }, indent=2) + "\n", encoding="utf-8")
        activate_capability(root, FORGE_ROOT, "runtime-proof", activation)

        contract_path = root / "state-transition-plan.json"
        contract_path.write_text(json.dumps({
            "schema": 1,
            "plan_id": "staging-schema-transition",
            "title": "Staging persisted-state transition and bounded rollback",
            "authority": "owner",
            "candidate_fields": ["build_id", "components.server.version"],
            "transitions": [{
                "transition_id": "schema-42-to-43",
                "target_environment": "neutral-staging",
                "deployment_stage": "staging",
                "verification_tier": "staging",
                "baseline_field": "baseline.build_id",
                "before_state": {
                    "state_id": "schema-42",
                    "description": "Controlled fixture representing the prior persisted state.",
                    "fixture_path": "fixtures/before-state.json",
                },
                "expected_after_state": {
                    "state_id": "schema-43",
                    "description": "Expected fixture after applying the declared migration.",
                    "fixture_path": "fixtures/after-state.json",
                },
                "deployment_artifact_path": artifact.name,
                "migration_paths": ["migrations/043_upgrade.sql"],
                "runtime_recipe_ids": ["transition-homepage"],
                "evidence_authorities": ["owner", "external-ci"],
                "rollback": {
                    "required": rollback_required,
                    "restored_state_id": "schema-42",
                    "runtime_recipe_ids": ["transition-homepage"] if rollback_required else [],
                },
                "exclusions": ["production traffic", "hidden data semantics", "automatic deployment", "release readiness"],
            }],
            "verification_boundary": "This plan binds external snapshots and receipts to exact candidate, artifact, migration, and runtime evidence without claiming Forge performs deployment, migration, restoration, rollback, or semantic data validation.",
        }, indent=2) + "\n", encoding="utf-8")
        plan = record_state_transition(root, FORGE_ROOT, contract_path)
        return plan, before, after, migration, artifact, contract_path

    def _evidence(self, root: Path, plan: dict, before: Path, after: Path, migration: Path, artifact: Path, *, rollback: bool = True, after_snapshot: Path | None = None, artifact_sha: str | None = None) -> Path:
        transition = plan["contract"]["transitions"][0]
        evidence_dir = root / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        before_copy = evidence_dir / "before-observed.json"
        after_copy = evidence_dir / "after-observed.json"
        before_copy.write_bytes(before.read_bytes())
        after_copy.write_bytes((after_snapshot or after).read_bytes())
        deployment_receipt = evidence_dir / "deployment-receipt.json"
        deployment_receipt.write_text(json.dumps({
            "schema": 1,
            "kind": "deployment-receipt",
            "candidate_binding": plan["contract"]["candidate_binding"],
            "target_environment": transition["target_environment"],
            "deployment_stage": transition["deployment_stage"],
            "baseline_value": transition["baseline_value"],
            "artifact_path": artifact.name,
            "artifact_sha256": artifact_sha or hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "result": "PASS",
            "observed_utc": "2026-08-01T22:00:00Z",
        }, indent=2) + "\n", encoding="utf-8")
        rollback_payload: dict[str, object] = {}
        if rollback:
            restored = evidence_dir / "restored-observed.json"
            restored.write_bytes(before.read_bytes())
            rollback_receipt = evidence_dir / "rollback-receipt.json"
            rollback_receipt.write_text(json.dumps({
                "schema": 1,
                "kind": "rollback-receipt",
                "candidate_binding": plan["contract"]["candidate_binding"],
                "target_environment": transition["target_environment"],
                "deployment_stage": transition["deployment_stage"],
                "baseline_value": transition["baseline_value"],
                "from_state_id": transition["expected_after_state"]["state_id"],
                "restored_state_id": transition["before_state"]["state_id"],
                "result": "PASS",
                "observed_utc": "2026-08-01T22:05:00Z",
            }, indent=2) + "\n", encoding="utf-8")
            rollback_payload = {
                "result": "PASS",
                "restored_snapshot_path": str(restored.relative_to(root)),
                "receipt_path": str(rollback_receipt.relative_to(root)),
            }
        evidence = root / "state-transition-evidence.json"
        evidence.write_text(json.dumps({
            "schema": 1,
            "plan_id": plan["contract"]["plan_id"],
            "transition_id": transition["transition_id"],
            "authority": "external-ci",
            "candidate_binding": plan["contract"]["candidate_binding"],
            "target_environment": transition["target_environment"],
            "deployment_stage": transition["deployment_stage"],
            "baseline_value": transition["baseline_value"],
            "transition_result": "PASS",
            "before_snapshot_path": str(before_copy.relative_to(root)),
            "after_snapshot_path": str(after_copy.relative_to(root)),
            "deployment_receipt_path": str(deployment_receipt.relative_to(root)),
            "migration_results": [{"path": "migrations/043_upgrade.sql", "status": "PASS", "sha256": hashlib.sha256(migration.read_bytes()).hexdigest()}],
            "rollback": rollback_payload,
        }, indent=2) + "\n", encoding="utf-8")
        return evidence

    def test_transition_without_evidence_remains_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup(root)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["state_transitions"]["not_run_count"], 1)
            self.assertEqual(payload["state_transitions"]["confirmed_count"], 0)

    def test_valid_transition_and_rollback_evidence_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, before, after, migration, artifact, _ = self._setup(root)
            evidence = self._evidence(root, plan, before, after, migration, artifact)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "NOT_RUN")
            summary = payload["state_transitions"]
            self.assertEqual(summary["confirmed_count"], 1)
            self.assertEqual(summary["rollback_confirmed_count"], 1)
            row = summary["evaluations"][0]["transitions"][0]
            self.assertEqual(row["rollback"]["status"], "PASS")
            self.assertNotIn("body", json.dumps(payload).casefold())

    def test_after_state_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, before, after, migration, artifact, _ = self._setup(root)
            wrong = root / "wrong-after.json"
            wrong.write_text('{"schema":43,"rows":[]}\n', encoding="utf-8")
            evidence = self._evidence(root, plan, before, after, migration, artifact, after_snapshot=wrong)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("after-state snapshot" in item["message"] for item in payload["findings"]))

    def test_required_rollback_missing_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, before, after, migration, artifact, _ = self._setup(root)
            evidence = self._evidence(root, plan, before, after, migration, artifact, rollback=False)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("rollback evidence" in item["message"] for item in payload["findings"]))

    def test_stale_deployment_artifact_receipt_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, before, after, migration, artifact, _ = self._setup(root)
            evidence = self._evidence(root, plan, before, after, migration, artifact, artifact_sha="0" * 64)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("artifact digest" in item["message"] for item in payload["findings"]))

    def test_bound_input_change_requires_rerecord(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, before, _, _, _, _ = self._setup(root)
            before.write_text('{"changed":true}\n', encoding="utf-8")
            record = state_transition_records(root)["staging-schema-transition"]
            self.assertEqual(record["lifecycle_status"], "approval-required")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("Bound transition input changed" in item["message"] for item in payload["findings"]))

    def test_resume_is_compact_and_uses_existing_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, before, after, migration, artifact, _ = self._setup(root)
            evidence = self._evidence(root, plan, before, after, migration, artifact)
            run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], state_transition_evidence_paths=[str(evidence)])
            resume = build_resume(root, FORGE_ROOT)
            self.assertIn("Persisted-state transitions", resume["markdown"])
            self.assertNotIn("deployment_receipt_sha256", resume["markdown"])
            self.assertLess(len(resume["markdown"]), 6500)
            actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_retired_transition_stops_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup(root)
            retire_state_transition(root, "staging-schema-transition", "This transition is superseded by a new target-state plan.")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["state_transitions"]["active_count"], 0)
            self.assertEqual(state_transition_records(root)["staging-schema-transition"]["status"], "retired")


if __name__ == "__main__":
    unittest.main()

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
from emotivus_forge.core.runtime_matrix import (
    record_runtime_matrix,
    retire_runtime_matrix,
    runtime_matrix_records,
)
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = ("<!doctype html><html><body><main id='app'>Expected candidate</main>" + "x" * 180 + "</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class RuntimeStateMatrixTests(ForgeTestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _setup(self, root: Path, *, recipe_tier: str = "staging") -> tuple[Path, Path, dict]:
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        identity_path = self._project_identity_contract(root)
        identity = record_project_identity(root, FORGE_ROOT, identity_path)
        (root / "migrations").mkdir(exist_ok=True)
        migration = root / "migrations" / "043_upgrade.sql"
        migration.write_text("ALTER TABLE tasks ADD COLUMN archived_at DATETIME NULL;\n", encoding="utf-8")
        recipe = root / "candidate.runtime.json"
        recipe.write_text(json.dumps({
            "schema": 1,
            "recipe_id": "candidate-homepage",
            "title": "Candidate homepage renders expected application content",
            "verification_tier": recipe_tier,
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
                "must_contain": ["Expected candidate"],
                "must_not_contain": ["Fatal error", "Traceback"],
            },
            "exclusions": ["JavaScript execution", "visual layout", "database correctness", "release readiness"],
        }, indent=2) + "\n", encoding="utf-8")
        (root / "runtime-proof-need.md").write_text("# Runtime proof\n\nConfirm the candidate response.\n", encoding="utf-8")
        activation = root / "runtime-proof.activation.json"
        activation.write_text(json.dumps({
            "schema": 1,
            "capability_id": "runtime-proof",
            "authority": "owner",
            "trigger": {"description": "The exact candidate needs bounded content-aware HTTP evidence.", "evidence_paths": ["runtime-proof-need.md"]},
            "scope": {"included": ["declared candidate HTTP response"], "excluded": ["deployment execution", "database state", "release readiness"]},
            "budget": {"runtime_seconds": 5, "file_limit": 4, "output_characters": 8000},
            "focused_regressions": [
                "runtime-proof.inactive-by-default", "runtime-proof.explicit-contract", "runtime-proof.content-aware",
                "runtime-proof.tiny-error-page-fails", "runtime-proof.host-bound", "runtime-proof.budget-bound",
                "runtime-proof.contract-change-requires-reactivation",
            ],
            "native_advantage": {"status": "distinct-value", "explanation": "This verifies bounded candidate HTTP content without replacing deployment or browser assurance."},
            "runtime_proof": {"allowed_origins": [self.origin], "recipe_paths": [recipe.name]},
            "allow_repairs": False,
        }, indent=2) + "\n", encoding="utf-8")
        activate_capability(root, FORGE_ROOT, "runtime-proof", activation)
        matrix_path = root / "runtime-state-matrix.json"
        matrix_path.write_text(json.dumps({
            "schema": 1,
            "matrix_id": "staging-upgrade",
            "title": "Staging upgrade from the current persisted baseline",
            "authority": "owner",
            "candidate_fields": ["build_id", "components.server.version"],
            "scenarios": [{
                "scenario_id": "upgrade-current-state",
                "target_environment": "neutral-staging",
                "deployment_stage": "staging",
                "verification_tier": "staging",
                "prior_state": {"state_id": "schema-42-copy", "description": "A controlled copy of the current persisted schema and representative records.", "source": "owner"},
                "baseline_field": "baseline.build_id",
                "migration_mode": "upgrade",
                "migration_paths": ["migrations/043_upgrade.sql"],
                "runtime_recipe_ids": ["candidate-homepage"],
                "evidence_authorities": ["owner", "external-ci"],
                "exclusions": ["production traffic", "data completeness", "rollback", "browser JavaScript", "release readiness"],
            }],
            "verification_boundary": "This matrix binds external deployment and migration testimony to the exact recorded candidate, prior-state identity, baseline, migration bytes, and same-Check runtime evidence without claiming Forge performed those operations.",
        }, indent=2) + "\n", encoding="utf-8")
        matrix = record_runtime_matrix(root, FORGE_ROOT, matrix_path)
        return migration, matrix_path, matrix

    def _evidence(self, root: Path, matrix: dict, migration: Path, **overrides: object) -> Path:
        scenario = matrix["contract"]["scenarios"][0]
        raw = {
            "schema": 1,
            "matrix_id": matrix["contract"]["matrix_id"],
            "scenario_id": scenario["scenario_id"],
            "authority": "external-ci",
            "candidate_binding": matrix["contract"]["candidate_binding"],
            "target_environment": scenario["target_environment"],
            "deployment_stage": scenario["deployment_stage"],
            "prior_state_id": scenario["prior_state"]["state_id"],
            "baseline_value": scenario["baseline_value"],
            "deployment_result": "PASS",
            "migration_results": [{"path": "migrations/043_upgrade.sql", "status": "PASS", "sha256": hashlib.sha256(migration.read_bytes()).hexdigest()}],
            "observed_utc": "2026-08-01T20:00:00Z",
        }
        raw.update(overrides)
        path = root / "runtime-state-evidence.json"
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        return path

    def test_matrix_without_evidence_remains_not_run_and_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup(root)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["runtime_state_matrices"]["not_run_count"], 1)
            self.assertEqual(payload["runtime_state_matrices"]["confirmed_count"], 0)

    def test_valid_external_evidence_and_same_check_runtime_recipe_confirm_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration, _, matrix = self._setup(root)
            evidence = self._evidence(root, matrix, migration)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], runtime_state_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["capabilities"][0]["status"], "PASS")
            scenario = payload["runtime_state_matrices"]["evaluations"][0]["scenarios"][0]
            self.assertEqual(scenario["truth_state"], "CONFIRMED")
            self.assertEqual(scenario["status"], "PASS")
            self.assertEqual(scenario["deployment_stage"], "staging")
            self.assertNotIn("body", json.dumps(payload).casefold())

    def test_evidence_without_same_check_runtime_recipe_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration, _, matrix = self._setup(root)
            evidence = self._evidence(root, matrix, migration)
            payload = run_scoped_check(root, FORGE_ROOT, runtime_state_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("not executed" in item["message"] for item in payload["findings"]))

    def test_candidate_binding_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration, _, matrix = self._setup(root)
            evidence = self._evidence(root, matrix, migration, candidate_binding={"build_id": "different"})
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], runtime_state_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("candidate binding" in item["message"] for item in payload["findings"]))

    def test_migration_change_requires_matrix_rerecord(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration, _, _ = self._setup(root)
            migration.write_text(migration.read_text(encoding="utf-8") + "-- changed\n", encoding="utf-8")
            record = runtime_matrix_records(root)["staging-upgrade"]
            self.assertEqual(record["lifecycle_status"], "approval-required")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("Migration input changed" in item["message"] for item in payload["findings"]))

    def test_lower_tier_runtime_recipe_cannot_support_staging_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration, _, matrix = self._setup(root, recipe_tier="sandbox")
            evidence = self._evidence(root, matrix, migration)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], runtime_state_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("tier is below" in item["message"] for item in payload["findings"]))

    def test_unpermitted_evidence_authority_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration, _, matrix = self._setup(root)
            evidence = self._evidence(root, matrix, migration, authority="forge")
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], runtime_state_evidence_paths=[str(evidence)])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("authority" in item["message"] for item in payload["findings"]))

    def test_resume_is_compact_and_matrix_uses_existing_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            migration, _, matrix = self._setup(root)
            evidence = self._evidence(root, matrix, migration)
            run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"], runtime_state_evidence_paths=[str(evidence)])
            resume = build_resume(root, FORGE_ROOT)
            self.assertIn("Runtime-state matrices", resume["markdown"])
            self.assertIn("Latest runtime-state matrix", resume["markdown"])
            self.assertNotIn("evidence_sha256", resume["markdown"])
            self.assertLess(len(resume["markdown"]), 6000)
            actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_retired_matrix_stops_evaluation_but_preserves_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup(root)
            retire_runtime_matrix(root, "staging-upgrade", "This scenario is superseded by a new target environment.")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["runtime_state_matrices"]["active_count"], 0)
            self.assertEqual(runtime_matrix_records(root)["staging-upgrade"]["status"], "retired")


if __name__ == "__main__":
    unittest.main()

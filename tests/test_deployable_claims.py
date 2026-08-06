from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from emotivus_forge.core.canonical_claims import record_canonical_claims, retire_canonical_claims
from emotivus_forge.core.deployable_boundary import record_deployable_boundary, retire_deployable_boundary
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.paths import STATE_FILE_NAMES
from emotivus_forge.core.project_identity import record_project_identity
from emotivus_forge.core.provenance import record_artifact_provenance
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class DeployableBoundaryAndCanonicalClaimTests(ForgeTestCase):
    def _setup_delivery_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        self._fixture(root)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "dist").mkdir()
        (root / "release").mkdir()
        (root / "migrations").mkdir()
        (root / "src" / "app.php").write_text("<?php echo 'v1';\n", encoding="utf-8")
        (root / "tests" / "debug.php").write_text("<?php echo 'test';\n", encoding="utf-8")
        (root / "migrations" / "current.sql").write_text("-- no schema change\n", encoding="utf-8")
        (root / "release" / "STATE.md").write_text(
            "# State\n\nBuild: 2026-08-01.1\nThe current migration makes no schema change.\nThe delta excludes tests.\n",
            encoding="utf-8",
        )
        (root / "release" / "EVIDENCE.txt").write_text("Evidence for build 2026-08-01.1\n", encoding="utf-8")
        identity = self._project_identity_contract(root)
        artifact = root / "dist" / "changed.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.write(root / "src" / "app.php", "src/app.php")
        provenance = root / "forge-delta-provenance.json"
        provenance.write_text(json.dumps({
            "schema": 1,
            "provenance_id": "changed-delta",
            "title": "Changed deployable delta",
            "authority": "owner",
            "artifact_path": "dist/changed.zip",
            "generator": {"command": "python tools/build_delta.py", "source_paths": []},
            "input_paths": ["src/app.php"],
            "file_limit": 20,
            "baseline_build_id": "2026-07-31.2",
            "deliverable": True,
            "truth_boundary": "This records current package bytes and declared inputs; it does not prove deployment, generator execution, or runtime behavior.",
        }, indent=2) + "\n", encoding="utf-8")
        boundary = root / "forge-deployable-boundary.json"
        boundary.write_text(json.dumps({
            "schema": 1,
            "boundary_id": "release-boundary",
            "title": "Release delivery roles",
            "authority": "owner",
            "strict_unclassified": True,
            "roles": [
                {"role": "deployable", "patterns": ["src/**", "index.php"]},
                {"role": "development-only", "patterns": ["tests/**", "forge-*.json", "BACKLOG.md"]},
                {"role": "release-artifact", "patterns": ["dist/**", "release/**", "migrations/**"]},
                {"role": "prohibited", "patterns": ["secrets/**"]},
            ],
            "blocked_from_delivery": ["development-only", "prohibited"],
            "delta_artifacts": [{
                "id": "changed-files",
                "provenance_id": "changed-delta",
                "mode": "exact",
                "allowed_roles": ["deployable"],
                "computed_for_baseline_build_id": "2026-07-31.2",
                "member_prefix": "",
            }],
            "verification_boundary": "This classifies the canonical observed changed set and compares registered delta members; it does not prove deployment or release readiness.",
        }, indent=2) + "\n", encoding="utf-8")
        claims = root / "forge-canonical-claims.json"
        claims.write_text(json.dumps({
            "schema": 1,
            "claim_set_id": "release-truth",
            "title": "Owner-facing release truth",
            "authority": "owner",
            "claims": [
                {"id": "build-id", "kind": "identity-text", "source_path": "release/STATE.md", "claim_text": "Build:", "identity_field": "build_id", "text_template": "Build: {value}"},
                {"id": "migration-ddl", "kind": "migration-effects", "source_path": "release/STATE.md", "claim_text": "The current migration makes no schema change.", "migration_path": "migrations/current.sql", "expect": "ddl-none"},
                {"id": "delta-excludes-tests", "kind": "archive-membership", "source_path": "release/STATE.md", "claim_text": "The delta excludes tests.", "provenance_id": "changed-delta", "member": "tests/debug.php", "expect": "absent"},
                {"id": "evidence-build", "kind": "evidence-identity", "source_path": "release/EVIDENCE.txt", "claim_text": "Evidence for build", "identity_field": "build_id", "text_template": "Evidence for build {value}"},
            ],
            "verification_boundary": "These explicit claims are checked against current deterministic evidence; arbitrary prose and overall release correctness remain outside scope.",
        }, indent=2) + "\n", encoding="utf-8")
        return identity, provenance, boundary, claims

    def _adopt_all(self, root: Path) -> tuple[Path, Path, Path, Path]:
        identity, provenance, boundary, claims = self._setup_delivery_fixture(root)
        build_passport(root, FORGE_ROOT)
        record_project_identity(root, FORGE_ROOT, identity)
        record_artifact_provenance(root, FORGE_ROOT, provenance)
        record_deployable_boundary(root, FORGE_ROOT, boundary)
        record_canonical_claims(root, FORGE_ROOT, claims)
        return identity, provenance, boundary, claims

    def _change_deployable_and_refresh_delta(self, root: Path, provenance: Path) -> None:
        (root / "src" / "app.php").write_text("<?php echo 'v2';\n", encoding="utf-8")
        with zipfile.ZipFile(root / "dist" / "changed.zip", "w") as archive:
            archive.write(root / "src" / "app.php", "src/app.php")
        record_artifact_provenance(root, FORGE_ROOT, provenance)

    def test_exact_delta_matches_authoritative_deployable_changed_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _identity, provenance, _boundary, _claims = self._adopt_all(root)
            self._change_deployable_and_refresh_delta(root, provenance)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["deployable_boundaries"]["status"], "PASS")
            delta = payload["deployable_boundaries"]["evaluations"][0]["delta_artifacts"][0]
            self.assertEqual(delta["expected_count"], 1)
            self.assertEqual(delta["actual_count"], 1)
            self.assertEqual(delta["missing_paths"], [])
            self.assertEqual(delta["extra_paths"], [])

    def test_delta_with_development_only_path_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _identity, provenance, _boundary, _claims = self._adopt_all(root)
            (root / "src" / "app.php").write_text("<?php echo 'v2';\n", encoding="utf-8")
            with zipfile.ZipFile(root / "dist" / "changed.zip", "w") as archive:
                archive.write(root / "src" / "app.php", "src/app.php")
                archive.write(root / "tests" / "debug.php", "tests/debug.php")
            record_artifact_provenance(root, FORGE_ROOT, provenance)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("blocked delivery roles" in item["message"] for item in payload["findings"]))

    def test_unclassified_and_overlapping_changed_paths_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _identity, provenance, boundary, _claims = self._adopt_all(root)
            raw = json.loads(boundary.read_text(encoding="utf-8"))
            raw["roles"].append({"role": "second-deployable", "patterns": ["src/**"]})
            boundary.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            record_deployable_boundary(root, FORGE_ROOT, boundary)
            (root / "src" / "app.php").write_text("<?php echo 'v2';\n", encoding="utf-8")
            (root / "unknown.bin").write_bytes(b"x")
            with zipfile.ZipFile(root / "dist" / "changed.zip", "w") as archive:
                archive.write(root / "src" / "app.php", "src/app.php")
            record_artifact_provenance(root, FORGE_ROOT, provenance)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertGreater(payload["deployable_boundaries"]["overlap_count"], 0)
            self.assertGreater(payload["deployable_boundaries"]["unclassified_count"], 0)

    def test_delta_baseline_mismatch_blocks_even_when_members_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity, provenance, _boundary, _claims = self._adopt_all(root)
            self._change_deployable_and_refresh_delta(root, provenance)
            raw = json.loads(identity.read_text(encoding="utf-8"))
            raw["build_id"] = "2026-08-01.2"
            raw["baseline"]["build_id"] = "2026-08-01.1"
            raw["monotonic"]["android_version_code"] += 1
            identity.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            record_project_identity(root, FORGE_ROOT, identity)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("does not match current owner-declared baseline" in item["message"] for item in payload["findings"]))

    def test_canonical_claims_pass_against_current_identity_package_migration_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_all(root)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["canonical_claims"]["status"], "PASS")
            self.assertEqual(payload["canonical_claims"]["claim_count"], 4)

    def test_migration_claim_contradiction_blocks_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_all(root)
            (root / "migrations" / "current.sql").write_text("CREATE TABLE example (id INT);\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("migration effect" in item["message"] for item in payload["findings"]))

    def test_stale_identity_and_package_membership_claims_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _identity, provenance, _boundary, _claims = self._adopt_all(root)
            state = root / "release" / "STATE.md"
            state.write_text(state.read_text(encoding="utf-8").replace("Build: 2026-08-01.1", "Build: 2026-07-31.9"), encoding="utf-8")
            with zipfile.ZipFile(root / "dist" / "changed.zip", "w") as archive:
                archive.write(root / "src" / "app.php", "src/app.php")
                archive.write(root / "tests" / "debug.php", "tests/debug.php")
            record_artifact_provenance(root, FORGE_ROOT, provenance)
            payload = run_scoped_check(root, FORGE_ROOT)
            messages = "\n".join(item["message"] for item in payload["findings"])
            self.assertIn("current identity text", messages)
            self.assertIn("archive member", messages)

    def test_contract_changes_require_renewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _identity, _provenance, boundary, claims = self._adopt_all(root)
            boundary.write_text(boundary.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            claims.write_text(claims.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            messages = "\n".join(item["message"] for item in payload["findings"])
            self.assertIn("Deployable boundary", messages)
            self.assertIn("Canonical claim set", messages)

    def test_retired_contracts_preserve_history_without_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _identity, _provenance, _boundary, _claims = self._adopt_all(root)
            retire_deployable_boundary(root, "release-boundary", "The delta workflow was retired.")
            retire_canonical_claims(root, "release-truth", "The release documents were retired.")
            (root / "unknown.bin").write_bytes(b"x")
            (root / "migrations" / "current.sql").write_text("CREATE TABLE example (id INT);\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["deployable_boundaries"]["active_count"], 0)
            self.assertEqual(payload["canonical_claims"]["active_count"], 0)

    def test_resume_is_compact_and_eight_file_boundary_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_all(root)
            resume = build_resume(root, FORGE_ROOT, budget="compact")
            markdown = resume["markdown"]
            self.assertIn("Deployable boundaries:", markdown)
            self.assertIn("Canonical claims:", markdown)
            self.assertNotIn("missing_paths", markdown)
            self.assertNotIn("computed_for_baseline_build_id", markdown)
            actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(actual, sorted(STATE_FILE_NAMES))

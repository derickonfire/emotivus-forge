from __future__ import annotations

import io
import json
import tempfile
import hashlib
import zipfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.lineage import exact_directory_tree, exact_zip_tree, record_project_lineage
from emotivus_forge.core.migration_identity import record_migration_catalog
from emotivus_forge.core.package_family import record_package_family
from emotivus_forge.core.surface_coverage import record_surface_coverage
from emotivus_forge.core.release_facts import record_release_facts
from emotivus_forge.core.continuity_register import record_continuity_register
from emotivus_forge.core.authority_baseline import authorize_current_baseline
from emotivus_forge.core.session_close import close_session
from emotivus_forge.core.state import load_state, save_state
from emotivus_forge.services.scoped_check import run_scoped_check
from emotivus_forge.services.ship import render_ship, ship_project
from emotivus_forge.commands.public import handle_ship
from emotivus_forge.core.ship_claims import _release_ready_level
from tests.support import FORGE_ROOT, ForgeTestCase


class ShipClaimLevelTests(ForgeTestCase):
    def _continuity_current(self, root: Path) -> None:
        contract = root / "continuity-register.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "register_id": "neutral-continuity",
            "authority": "owner",
            "supersedes_register_id": "",
            "facts": [{
                "fact_id": "mission",
                "key": "project.mission",
                "value": "Maintain the neutral verification fixture.",
                "trust": "owner-declared",
                "rationale": "The fixture requires one stable declared mission for continuity readiness.",
                "impact": "Guides the next bounded test step.",
                "change_reason": "",
                "support": [{"kind": "contract-declaration", "note": "The test owner declares this neutral fixture mission."}],
                "truth_boundary": "This declaration governs only the neutral fixture mission and proves no implementation behavior."
            }],
            "gaps": [],
            "retired_fact_keys": [],
            "retired_gap_ids": [],
            "truth_boundary": "This register governs compact fixture continuity and grants no release authority."
        }, indent=2) + "\n", encoding="utf-8")
        record_continuity_register(root, FORGE_ROOT, contract)

    def _checkpointed(self, root: Path) -> None:
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        self._continuity_current(root)
        observed = run_scoped_check(root, FORGE_ROOT)
        self.assertEqual(observed["status"], "NOT_RUN")
        authorize_current_baseline(
            root,
            FORGE_ROOT,
            expected_fingerprint=observed["authority_baseline"]["current_fingerprint"],
            authority="owner",
            reason="Reviewed the exact neutral candidate tree before checkpointing.",
        )
        check = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
        self.assertEqual(check["status"], "PASS")
        close_session(
            root,
            FORGE_ROOT,
            session_type="code-increment",
            next_action="Continue the next bounded increment.",
            completed_work=["Established a neutral candidate checkpoint."],
            decisions=[],
            owner_facts=[],
            unresolved_risks=[],
            check_payload=check,
            current_snapshot=load_state(root)["snapshot"],
        )


    def _authority_checkpointed(self, root: Path) -> None:
        self._fixture(root)
        (root / "RELEASE.md").write_text("# Release\n\nVersion: **1.0.0**\n\nSettings schema: **18**\n", encoding="utf-8")
        build_passport(root, FORGE_ROOT)
        lineage_path = root / "project-lineage.json"
        current = exact_directory_tree(root, FORGE_ROOT, exclude_paths=[lineage_path.name])
        lineage_path.write_text(json.dumps({
            "schema": 1,
            "lineage_id": "neutral-authority-lineage",
            "authority": "owner",
            "declared_version": "1.0.0",
            "build_id": "neutral-authority-build",
            "relationship": "initial",
            "parent": None,
            "current": {
                "tree_sha256": current["tree_sha256"],
                "tree_file_count": current["file_count"],
            },
            "collision_declaration": {},
            "truth_boundary": "The owner declares the initial exact tree; Forge verifies current bytes but not authorship or semantic correctness.",
        }, indent=2) + "\n", encoding="utf-8")
        record_project_lineage(root, FORGE_ROOT, lineage_path)
        migration_path = root / "forge-migrations.json"
        migration_path.write_text(json.dumps({
            "schema": 1,
            "inventory_id": "neutral-no-migrations",
            "authority": "owner",
            "lineage_id": "neutral-authority-lineage",
            "engine": "none",
            "mode": "none",
            "source": {"kind": "project-tree"},
            "entries": [],
            "no_migrations_reason": "This neutral fixture has no persisted schema migration surface.",
            "applied_observation": {},
            "reconciliations": [],
            "truth_boundary": "Forge verifies the explicit no-migrations declaration but does not infer future database behavior or release safety.",
        }, indent=2) + "\n", encoding="utf-8")
        record_migration_catalog(root, FORGE_ROOT, migration_path)
        result_zip = root / "neutral-result.zip"
        with zipfile.ZipFile(result_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("Project/index.php", (root / "index.php").read_bytes())
            archive.writestr("Project/BACKLOG.md", (root / "BACKLOG.md").read_bytes())
            archive.writestr("Project/RELEASE.md", (root / "RELEASE.md").read_bytes())
        result_tree = exact_zip_tree(result_zip, strip_prefix="Project")
        family_path = root / "forge-package-family.json"
        family_path.write_text(json.dumps({
            "schema": 1,
            "family_id": "neutral-package-family",
            "authority": "owner",
            "lineage_id": "neutral-authority-lineage",
            "release_version": "1.0.0",
            "build_id": "neutral-authority-build",
            "artifacts": [{
                "artifact_id": "result",
                "role": "full-site",
                "path": result_zip.name,
                "sha256": hashlib.sha256(result_zip.read_bytes()).hexdigest(),
                "bytes": result_zip.stat().st_size,
                "strip_prefix": "Project",
                "tree_sha256": result_tree["tree_sha256"],
                "tree_file_count": result_tree["file_count"],
            }],
            "outer_bundles": [],
            "deltas": [],
            "truth_boundary": "Forge verifies this exact neutral package family but does not execute the application or prove release safety.",
        }, indent=2) + "\n", encoding="utf-8")
        record_package_family(root, FORGE_ROOT, family_path)
        surface_path = root / "forge-surface-coverage.json"
        surface_path.write_text(json.dumps({
            "schema": 1,
            "inventory_id": "neutral-surface-map",
            "authority": "owner",
            "lineage_id": "neutral-authority-lineage",
            "release_version": "1.0.0",
            "build_id": "neutral-authority-build",
            "package_family_id": "neutral-package-family",
            "source_artifact_id": "result",
            "surfaces": [{
                "surface_id": "neutral-home",
                "type": "route",
                "title": "Neutral home route",
                "audiences": ["tester"],
                "entrypoints": ["index.php"],
                "steps": [],
                "route": "/index.php",
                "required_tier": "source-exists",
                "scope": "The exact neutral home route in the result artifact.",
            }],
            "receipts": [],
            "truth_boundary": "Forge proves only that the declared route exists in the exact result artifact; no database, authentication, browser, device, staging, production, or deployment behavior is implied.",
        }, indent=2) + "\n", encoding="utf-8")
        record_surface_coverage(root, FORGE_ROOT, surface_path)
        self._continuity_current(root)
        observed = run_scoped_check(root, FORGE_ROOT)
        authorize_current_baseline(
            root,
            FORGE_ROOT,
            expected_fingerprint=observed["authority_baseline"]["current_fingerprint"],
            authority="owner",
            reason="Reviewed and accepted the exact neutral candidate tree.",
        )
        check = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
        self.assertEqual(check["status"], "PASS")
        close_session(
            root,
            FORGE_ROOT,
            session_type="code-increment",
            next_action="Continue the next bounded increment.",
            completed_work=["Established an authority-recorded neutral candidate checkpoint."],
            decisions=[],
            owner_facts=[],
            unresolved_risks=[],
            check_payload=check,
            current_snapshot=load_state(root)["snapshot"],
        )

    def test_ship_before_adoption_reports_no_supported_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            payload = ship_project(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertEqual(payload["highest_supported_claim"], "none")
            self.assertFalse((root / ".forge").exists())

    def test_checkpointed_project_requires_and_reports_authority_recorded_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._checkpointed(root)
            payload = ship_project(root, FORGE_ROOT)
            levels = {item["level_id"]: item for item in payload["claim_readiness"]["levels"]}
            self.assertEqual(levels["continuity-ready"]["status"], "PASS")
            self.assertEqual(levels["checkpointed-candidate"]["status"], "PASS")
            self.assertEqual(levels["authority-recorded-candidate"]["status"], "PASS")
            self.assertEqual(levels["native-verified-candidate"]["status"], "FAIL")
            self.assertEqual(payload["highest_supported_claim"], "authority-recorded-candidate")
            self.assertFalse(payload["release_ready"])

    def test_project_change_after_checkpoint_removes_candidate_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._checkpointed(root)
            (root / "index.php").write_text("<?php echo 'later change';\n", encoding="utf-8")
            payload = ship_project(root, FORGE_ROOT)
            levels = {item["level_id"]: item for item in payload["claim_readiness"]["levels"]}
            self.assertEqual(levels["checkpointed-candidate"]["status"], "FAIL")
            self.assertEqual(payload["highest_supported_claim"], "none")

    def test_native_and_runtime_claims_require_current_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._authority_checkpointed(root)
            passport_path = root / ".forge" / "passport.json"
            passport = json.loads(passport_path.read_text(encoding="utf-8"))
            passport.setdefault("evidence", {})["native_gate"] = {
                "status": "PASS",
                "validity": "current",
                "entry_count": 1,
                "verification_tier": "sandbox",
            }
            passport_path.write_text(json.dumps(passport, indent=2) + "\n", encoding="utf-8")
            state = load_state(root)
            state["last_check"]["check_qualification"] = {"counts": {"qualified": 1}, "qualified_ratio": "1/1"}
            state["last_check"]["runtime_proof"] = {"status": "PASS", "recipe_count": 1, "counts": {"PASS": 1, "FAIL": 0, "BLOCKED": 0}}
            state["last_check"]["truth_summary"] = {"schema": 1, "unresolved_count": 0, "unresolved": [], "state_counts": {"CONFIRMED": 1}}
            save_state(root, state)
            with patch("emotivus_forge.core.ship_claims.release_facts_summary", return_value={
                "status": "CURRENT", "reason": "Declared release facts are current.", "check_count": 2, "failed_count": 0,
            }):
                payload = ship_project(root, FORGE_ROOT)
            levels = {item["level_id"]: item for item in payload["claim_readiness"]["levels"]}
            self.assertEqual(levels["authority-recorded-candidate"]["status"], "PASS")
            self.assertEqual(levels["native-verified-candidate"]["status"], "PASS")
            self.assertEqual(levels["release-facts-current-candidate"]["status"], "PASS")
            self.assertEqual(levels["runtime-content-verified"]["status"], "PASS")
            self.assertEqual(payload["highest_supported_claim"], "runtime-content-verified")

    def test_release_ready_level_requires_complete_bounded_inputs(self) -> None:
        level = _release_ready_level(
            {"status": "PASS"},
            {"final_package": {"status": "PASS"}},
            {"remote_channels": {"status": "PASS"}},
            {"status": "PASS"},
            {"status": "PASS"},
            {"status": "PASS", "reason": "Exact-package authorization is current."},
        )
        self.assertEqual(level["status"], "PASS")
        self.assertEqual(level["level_id"], "release-ready")
        self.assertIn("authenticated human identity", level["exclusions"])

    def test_release_ready_is_blocked_without_complete_current_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._checkpointed(root)
            payload = ship_project(root, FORGE_ROOT)
            release = payload["claim_readiness"]["levels"][-1]
            self.assertEqual(release["level_id"], "release-ready")
            self.assertEqual(release["status"], "FAIL")
            self.assertIn("A passing lower claim is not release readiness", render_ship(payload))

    def test_public_ship_handler_returns_success_for_bounded_release_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "status": "PASS",
                "release_ready": True,
                "reason": "Complete bounded claim ladder is current.",
                "claim": "Bounded release-ready claim is current.",
                "highest_supported_claim": "release-ready",
                "claim_readiness": {"levels": [{"level_id": "release-ready", "title": "Release ready", "status": "PASS", "requirements": []}]},
                "required_before_activation": [],
            }
            output = io.StringIO()
            with patch("emotivus_forge.commands.public.ship_project", return_value=payload), redirect_stdout(output):
                code = handle_ship(SimpleNamespace(project=str(root), json=False), FORGE_ROOT)
            self.assertEqual(code, 0)
            self.assertIn("FORGE SHIP — READY", output.getvalue())
            self.assertEqual(payload["ai_notice"]["level"], "notice")

    def test_public_ship_handler_returns_blocked_exit_for_incomplete_ladder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "status": "BLOCKED",
                "release_ready": False,
                "reason": "Exact-package authorization is missing.",
                "claim": "Ship remains blocked.",
                "highest_supported_claim": "cold-session-validated",
                "claim_readiness": {"levels": []},
                "required_before_activation": ["Record exact-package authorization."],
            }
            output = io.StringIO()
            with patch("emotivus_forge.commands.public.ship_project", return_value=payload), redirect_stdout(output):
                code = handle_ship(SimpleNamespace(project=str(root), json=False), FORGE_ROOT)
            self.assertEqual(code, 1)
            self.assertIn("FORGE SHIP — BLOCKED", output.getvalue())
            self.assertEqual(payload["ai_notice"]["level"], "blocker")



if __name__ == "__main__":
    unittest.main()

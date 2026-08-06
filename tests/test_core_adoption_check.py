from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from emotivus_forge.core.authority_registry import confirm_authorities, load_or_discover_authorities
from emotivus_forge.core.authority_baseline import authorize_current_baseline
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


class CoreAdoptionAndCheckTests(ForgeTestCase):
    def test_first_run_creates_only_minimal_state_and_recovers_explicit_objective(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                payload = run_forge(root, FORGE_ROOT)
                self.assertEqual(payload["action"], "ADOPT + RESUME")
                self.assertEqual(payload["objective"]["text"], "Add a login screen.")
                actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
                self.assertEqual(actual, sorted(STATE_FILE_NAMES))
                self.assertEqual(len(actual), 8)
                self.assertFalse(any("capability_vault" in str(getattr(module, "__file__", "")) for module in sys.modules.values()))

    def test_help_does_not_load_services_or_vault(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                for name in list(sys.modules):
                    if name.startswith("emotivus_forge.services"):
                        del sys.modules[name]
                payload = build_help(root, FORGE_ROOT)
                self.assertEqual(payload["recommended_command"], "adopt")
                self.assertFalse(any(name.startswith("emotivus_forge.services") for name in sys.modules))
                self.assertFalse(any("capability_vault" in str(getattr(module, "__file__", "")) for module in sys.modules.values()))

    def test_native_gate_is_detected_but_not_approved_or_executed(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "tools").mkdir()
                gate = root / "tools" / "run_all_checks.sh"
                gate.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
                passport = build_passport(root, FORGE_ROOT)
                self.assertEqual(passport["native_gate"]["canonical"]["source"], "tools/run_all_checks.sh")
                self.assertEqual(passport["native_gate"]["approval"]["status"], "required")
                self.assertFalse((root / "ran.txt").exists())

    def test_approved_native_gate_can_run_explicitly(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "tools").mkdir()
                gate = root / "tools" / "run_all_checks.sh"
                gate.write_text(
                    "#!/usr/bin/env sh\n"
                    "echo 'FORGE_CHECK|id=native-pass|status=PASS|type=integration|surface=web'\n",
                    encoding="utf-8",
                )
                gate.chmod(0o755)
                build_passport(root, FORGE_ROOT)
                invocation = self._native_invocation_contract(root, expected_checks=["native-pass"])
                approve_canonical_native_tool(root, invocation.name)
                payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
                self.assertEqual(payload["native_gate"]["status"], "PASS")
                self.assertEqual(payload["native_gate"]["evidence"]["entry_count"], 1)
                self.assertEqual(payload["native_gate"]["evidence"]["surfaces"], ["web"])
                stdout_ref = payload["native_gate"]["raw_evidence"]["stdout"]
                self.assertIn("native-pass", (root / ".forge" / stdout_ref).read_text(encoding="utf-8"))
                passport = json.loads((root / ".forge" / "passport.json").read_text(encoding="utf-8"))
                self.assertEqual(passport["surface_coverage"]["surfaces"], ["web"])

    def test_unbaselined_scoped_observations_are_explicitly_not_project_level(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "index.php").write_text("<?php echo 'changed';\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["status"], "NOT_RUN")
                self.assertEqual(payload["claim"], "Scoped Check NOT_RUN")
                self.assertFalse(payload["claim_scope"]["project_level_success"])
                self.assertIn("release assurance", payload["claim_scope"]["excluded"])

    def test_change_reconciliation_rejects_unknown_supplied_paths(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                payload = run_scoped_check(root, FORGE_ROOT, supplied_paths=["missing.php"])
                self.assertEqual(payload["changes"]["count"], 0)
                self.assertEqual(payload["changes"]["supplied"]["accepted"], [])
                self.assertEqual(payload["changes"]["supplied"]["rejected"][0]["path"], "missing.php")

    def test_merge_markers_block_scoped_check(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "index.php").write_text("<<<<<<< HEAD\nconflict\n=======\nother\n>>>>>>> branch\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["status"], "FAIL")
                self.assertTrue(any(item["check"] == "core.merge-marker" for item in payload["findings"]))

    def test_legacy_migration_preserves_confirmed_records_without_deletion(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / ".forge" / "passport").mkdir(parents=True)
                (root / ".forge" / "passport" / "passport.json").write_text(
                    json.dumps({"identity": {"name": "Legacy Fixture"}, "objective": {"text": "Old objective"}}),
                    encoding="utf-8",
                )
                (root / ".forge" / "project").mkdir(parents=True)
                legacy_ledger = {
                    "schema": 1,
                    "entries": [
                        {"id": "decision-1", "type": "decision", "title": "Use SQLite", "status": "accepted", "rationale": "Portable fixture"},
                        {"id": "draft-1", "type": "note", "title": "Draft", "status": "pending"},
                    ],
                }
                (root / ".forge" / "project" / "ledger.json").write_text(json.dumps(legacy_ledger), encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                ledger_text = (root / ".forge" / "ledger.jsonl").read_text(encoding="utf-8")
                self.assertIn("Use SQLite", ledger_text)
                self.assertNotIn('"title":"Draft"', ledger_text)
                self.assertTrue((root / ".forge" / "passport" / "passport.json").is_file())
                state = load_state(root)
                self.assertEqual(state["migration"]["from"], "1.4.1-dev")
                self.assertTrue(state["migration"]["legacy_state_retained"])

    def test_resume_reports_changes_without_advancing_snapshot(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "index.php").write_text("<?php echo 'changed';\n", encoding="utf-8")
                first = build_resume(root, FORGE_ROOT)
                second = build_resume(root, FORGE_ROOT)
                self.assertEqual(first["changes"]["count"], 1)
                self.assertEqual(second["changes"]["count"], 1)

    def test_checkpoint_advances_snapshot_only_after_pass(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "index.php").write_text("<?php echo 'changed';\n", encoding="utf-8")
                observed = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(observed["status"], "NOT_RUN")
                authorize_current_baseline(
                    root,
                    FORGE_ROOT,
                    expected_fingerprint=observed["authority_baseline"]["current_fingerprint"],
                    authority="owner",
                    reason="Reviewed the exact changed tree for checkpoint testing.",
                )
                payload = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
                self.assertEqual(payload["status"], "PASS")
                changes = detect_changes(root, FORGE_ROOT, load_state(root)["snapshot"], load_settings(root))
                self.assertEqual(changes["count"], 0)

    def test_ship_is_blocked_until_assurance_capabilities_are_activated(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                payload = ship_project(root)
                self.assertEqual(payload["status"], "BLOCKED")
                self.assertFalse(payload["project_level_success"])
                self.assertIn("Release Proof", " ".join(payload["required_before_activation"]))

    def test_owner_confirmation_resolves_conflicting_objectives_and_persists(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "index.php").write_text("<?php echo 'ok';\n", encoding="utf-8")
                (root / "ROADMAP.md").write_text(
                    "# Roadmap\n\n## Next Action\n\n- Build alpha.\n",
                    encoding="utf-8",
                )
                (root / "BACKLOG.md").write_text(
                    "# Backlog\n\n## THE NEXT ACTION\n\n- Build beta.\n",
                    encoding="utf-8",
                )
                first = build_passport(root, FORGE_ROOT)
                self.assertTrue(any("Conflicting objective" in item for item in first["uncertainties"]))
                confirm_authorities(root, FORGE_ROOT, objective="Build the confirmed path.", objective_source="owner")
                second = build_passport(root, FORGE_ROOT)
                self.assertEqual(second["objective"]["text"], "Build the confirmed path.")
                self.assertEqual(second["objective"]["status"], "confirmed")
                third = load_or_discover_authorities(root, FORGE_ROOT, refresh=True)
                self.assertEqual(third["objective"]["text"], "Build the confirmed path.")
                self.assertIn("authority-confirmation", (root / ".forge" / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_archived_objective_does_not_outrank_active_record(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "archive").mkdir()
                (root / "archive" / "ROADMAP.md").write_text(
                    "## THE NEXT ACTION\n\n- Old action.\n",
                    encoding="utf-8",
                )
                (root / "BACKLOG.md").write_text(
                    "## THE NEXT ACTION\n\n- Active action.\n",
                    encoding="utf-8",
                )
                registry = load_or_discover_authorities(root, FORGE_ROOT, refresh=True)
                self.assertEqual(registry["objective"]["text"], "Active action.")
                archived = next(item for item in registry["candidates"] if item["path"] == "archive/ROADMAP.md")
                self.assertEqual(archived["lifecycle"], "archived")

    def test_native_gate_is_registered_as_one_ecosystem(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "tools").mkdir()
                (root / "tests").mkdir()
                member = root / "tests" / "verify_fixture.py"
                member.write_text("print('ok')\n", encoding="utf-8")
                gate = root / "tools" / "run_all_checks.sh"
                gate.write_text(
                    "#!/usr/bin/env sh\npython3 tests/verify_fixture.py\n",
                    encoding="utf-8",
                )
                registry = load_or_discover_native_tools(root, refresh=True)
                self.assertEqual(registry["verification_status"], "existing-project-verification-detected")
                self.assertEqual(registry["canonical"]["verification_style"], "project-orchestrator")
                sources = [item["source"] for item in registry["ecosystem"]["members"]]
                self.assertIn("tests/verify_fixture.py", sources)
                self.assertIn("not absorbed", registry["ecosystem"]["policy"])

    def test_native_gate_change_requires_reapproval(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "tools").mkdir()
                gate = root / "tools" / "run_all_checks.sh"
                gate.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                invocation = self._native_invocation_contract(root, expected_count=1)
                approve_canonical_native_tool(root, invocation.name)
                self.assertEqual(load_or_discover_native_tools(root, refresh=True)["approval"]["status"], "approved")
                gate.write_text("#!/usr/bin/env sh\necho changed\n", encoding="utf-8")
                refreshed = load_or_discover_native_tools(root, refresh=True)
                self.assertEqual(refreshed["approval"]["status"], "reapproval-required")
                blocked = run_scoped_check(root, FORGE_ROOT, run_native=True)
                self.assertEqual(blocked["native_gate"]["status"], "BLOCKED")

    def test_zero_exit_with_structured_failure_is_not_a_pass(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "tools").mkdir()
                gate = root / "tools" / "run_all_checks.sh"
                gate.write_text(
                    "#!/usr/bin/env sh\n"
                    "echo 'FORGE_EVIDENCE {\"id\":\"browser.home\",\"status\":\"FAIL\",\"type\":\"browser\",\"surface\":\"home\"}'\n"
                    "exit 0\n",
                    encoding="utf-8",
                )
                gate.chmod(0o755)
                build_passport(root, FORGE_ROOT)
                invocation = self._native_invocation_contract(root, expected_checks=["browser.home"])
                approve_canonical_native_tool(root, invocation.name)
                payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
                self.assertEqual(payload["status"], "FAIL")
                self.assertEqual(payload["native_gate"]["status"], "FAIL")
                self.assertIn("zero exit code", payload["native_gate"]["reason"])

    def test_placeholder_templates_are_distinguished_without_echoing_secrets(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                placeholder = root / ".env.example"
                placeholder.write_text("API_KEY=your_api_key_here\n", encoding="utf-8")
                live = root / ".env"
                secret_value = "sk_live_very_private_value_123456"
                live.write_text(f"API_KEY={secret_value}\n", encoding="utf-8")
                result = classify_confidentiality_boundaries(root, [".env.example", ".env"])
                self.assertIn(".env.example", result["placeholder_template_candidates"])
                self.assertIn(".env", result["private_boundary_candidates"])
                serialized = json.dumps(result)
                self.assertNotIn(secret_value, serialized)
                self.assertFalse(result["secret_material_candidates"][0]["values_retained"])

    def test_help_routes_to_adopt_when_confirmation_is_pending(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "tools").mkdir()
                (root / "tools" / "run_all_checks.sh").write_text(
                    "#!/usr/bin/env sh\nexit 0\n",
                    encoding="utf-8",
                )
                build_passport(root, FORGE_ROOT)
                payload = build_help(root, FORGE_ROOT)
                self.assertEqual(payload["project_state"], "NEEDS_CONFIRMATION")
                self.assertEqual(payload["recommended_command"], "adopt")

    def test_session_close_captures_handoff_without_adding_state_files(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                build_resume(root, FORGE_ROOT)
                observed = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(observed["status"], "NOT_RUN")
                authorize_current_baseline(
                    root,
                    FORGE_ROOT,
                    expected_fingerprint=observed["authority_baseline"]["current_fingerprint"],
                    authority="owner",
                    reason="Reviewed the exact starting tree before the session increment.",
                )
                (root / "index.php").write_text("<?php echo 'increment';\n", encoding="utf-8")
                payload = run_scoped_check(
                    root,
                    FORGE_ROOT,
                    checkpoint=True,
                    session_close_data={
                        "session_type": "code-increment",
                        "summary": "Implemented the bounded login increment.",
                        "completed_work": ["Added the login route.", "Added the login route."],
                        "decisions": [{"text": "Keep authentication local-first.", "rationale": "Avoid a new hosted dependency."}],
                        "owner_facts": [{"text": "The project must remain portable.", "impact": "Do not require Git or a hosted service."}],
                        "unresolved_risks": ["Browser behavior has not been verified."],
                        "next_action": "Run the login flow in a browser fixture.",
                    },
                )
                self.assertEqual(payload["status"], "PASS")
                self.assertEqual(payload["session_close"]["status"], "CLOSED")
                self.assertEqual(payload["session_close"]["changed_files"], ["index.php"])
                self.assertEqual(len(payload["session_close"]["completed_work"]), 1)
                actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
                self.assertEqual(actual, sorted(STATE_FILE_NAMES))
                passport = json.loads((root / ".forge" / "passport.json").read_text(encoding="utf-8"))
                self.assertEqual(passport["maturity"], "Working familiarity")
                resume = build_resume(root, FORGE_ROOT)
                self.assertEqual(resume["next_action"]["text"], "Run the login flow in a browser fixture.")
                self.assertEqual(resume["continuity"]["status"], "current")
                self.assertIn("Keep authentication local-first", resume["markdown"])
                self.assertIn("Browser behavior has not been verified", resume["markdown"])

    def test_resume_marks_continuity_stale_after_post_close_change(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                run_scoped_check(
                    root,
                    FORGE_ROOT,
                    checkpoint=True,
                    session_close_data={
                        "session_type": "decision-checkpoint",
                        "next_action": "Implement the approved login layout.",
                    },
                )
                (root / "index.php").write_text("<?php echo 'changed later';\n", encoding="utf-8")
                resume = build_resume(root, FORGE_ROOT)
                self.assertEqual(resume["continuity"]["status"], "stale")
                self.assertEqual(resume["status"], "ATTENTION")
                self.assertIn("changed after the latest Session Close", resume["continuity"]["reason"])

    def test_session_close_requires_an_exact_next_action(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                with self.assertRaisesRegex(ValueError, "exact next action"):
                    close_session(root, FORGE_ROOT, session_type="audit", next_action="")

    def test_durable_pair_parser_requires_rationale_or_impact(self) -> None:
            self.assertEqual(
                parse_durable_pairs(["Use SQLite::Portable and inspectable"], label="decision", detail_label="rationale"),
                [{"text": "Use SQLite", "rationale": "Portable and inspectable"}],
            )
            with self.assertRaisesRegex(ValueError, "TEXT::RATIONALE"):
                parse_durable_pairs(["Use SQLite"], label="decision", detail_label="rationale")

    def test_failed_check_can_close_with_failure_and_risk_preserved(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "index.php").write_text("<<<<<<< HEAD\nconflict\n=======\nother\n>>>>>>> branch\n", encoding="utf-8")
                payload = run_scoped_check(
                    root,
                    FORGE_ROOT,
                    session_close_data={
                        "session_type": "audit",
                        "unresolved_risks": ["Resolve the merge conflict before implementation continues."],
                        "next_action": "Resolve the merge conflict in index.php.",
                    },
                )
                self.assertEqual(payload["status"], "FAIL")
                self.assertEqual(payload["session_close"]["checks"]["status"], "FAIL")
                resume = build_resume(root, FORGE_ROOT)
                self.assertIn("Resolve the merge conflict before implementation continues", resume["markdown"])
                self.assertIn("latest recorded Check did not pass", " ".join(resume["attention_reasons"]))

    def test_supplied_unchanged_path_cannot_manufacture_change_or_impact(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                payload = run_scoped_check(root, FORGE_ROOT, supplied_paths=["index.php"])
                self.assertEqual(payload["changes"]["count"], 0)
                self.assertEqual(payload["check_plan"]["profile"], "none")
                self.assertEqual(payload["check_plan"]["impact_dimensions"], [])
                self.assertEqual(payload["change_ledger"]["status"], "unchanged")
                self.assertTrue(payload["changes"]["supplied"]["rejected"])
                self.assertIn("cannot create it", payload["changes"]["supplied"]["rejected"][0]["reason"])

    def test_documentation_change_uses_documentation_profile_without_full_suite(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "BACKLOG.md").write_text("# Backlog\n\n## THE NEXT ACTION\n\n- Document the API.\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["check_plan"]["profile"], "documentation")
                self.assertEqual(payload["check_plan"]["affected_surfaces"], ["documentation"])
                self.assertEqual(payload["check_plan"]["native_gate_policy"]["selection"], "not-recommended")
                self.assertFalse(payload["check_plan"]["native_gate_policy"]["full_suite_automatic"])
                self.assertTrue(payload["check_plan"]["no_numeric_impact_score"])

    def test_website_only_change_runs_website_scoped_checks_not_native_suite(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "assets").mkdir()
                css = root / "assets" / "styles.css"
                css.write_text("body { margin: 0; }\n", encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                css.write_text("body { margin: 0;\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["check_plan"]["profile"], "website")
                self.assertIn("core.css-structure", payload["executed_checks"])
                self.assertEqual(payload["native_gate"]["status"], "NOT_RUN")
                self.assertEqual(payload["status"], "FAIL")
                self.assertTrue(any(item["check"] == "core.css-structure" for item in payload["findings"]))

    def test_html_website_check_rejects_missing_local_asset(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "website").mkdir()
                page = root / "website" / "index.html"
                asset = root / "website" / "styles.css"
                asset.write_text("body { margin: 0; }\n", encoding="utf-8")
                page.write_text('<link rel="stylesheet" href="styles.css">\n', encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                page.write_text('<link rel="stylesheet" href="missing.css">\n', encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                self.assertEqual(payload["check_plan"]["profile"], "website")
                self.assertTrue(any(item["check"] == "core.html-local-assets" for item in payload["findings"]))

    def test_css_change_invalidates_browser_evidence_but_preserves_migration_and_runtime(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                (root / "assets").mkdir()
                css = root / "assets" / "styles.css"
                css.write_text("body { margin: 0; }\n", encoding="utf-8")
                build_passport(root, FORGE_ROOT)
                passport_path = root / ".forge" / "passport.json"
                passport = json.loads(passport_path.read_text(encoding="utf-8"))
                passport["evidence"] = {"native_gate": {
                    "status": "PASS",
                    "validity": "current",
                    "records": [
                        {"id": "migration.upgrade", "status": "PASS", "type": "migration", "surfaces": ["database"], "validity": "current"},
                        {"id": "runtime.php", "status": "PASS", "type": "runtime", "surfaces": ["backend"], "validity": "current"},
                        {"id": "browser.home", "status": "PASS", "type": "browser", "surfaces": ["home"], "validity": "current"},
                    ],
                }}
                passport["surface_coverage"] = {"status": "reported", "surfaces": ["home"], "validity": "current"}
                passport_path.write_text(json.dumps(passport, indent=2) + "\n", encoding="utf-8")
                css.write_text("body { margin: 1rem; }\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                refreshed = json.loads(passport_path.read_text(encoding="utf-8"))
                records = {item["id"]: item for item in refreshed["evidence"]["native_gate"]["records"]}
                self.assertEqual(records["browser.home"]["validity"], "stale")
                self.assertEqual(records["migration.upgrade"]["validity"], "current")
                self.assertEqual(records["runtime.php"]["validity"], "current")
                self.assertEqual(payload["evidence_invalidation"]["invalidated_ids"], ["browser.home"])

    def test_requested_native_gate_executes_before_distinct_forge_checks(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "index.php").write_text("<?php echo 'changed';\n", encoding="utf-8")
                order: list[str] = []

                def fake_native(*args: object, **kwargs: object) -> dict[str, object]:
                    order.append("native")
                    return {
                        "status": "PASS", "reason": "", "command": ["native"], "returncode": 0,
                        "evidence": {"entry_count": 0, "surfaces": [], "coverage_status": "unknown", "status_counts": {}, "evidence_types": []},
                        "evidence_records": [], "raw_evidence": {},
                    }

                def fake_forge(*args: object, **kwargs: object) -> tuple[list[dict[str, object]], list[str]]:
                    order.append("forge")
                    return [], ["core.merge-marker"]

                with patch.dict(run_scoped_check.__globals__, {"run_native_gate": fake_native, "_check_path": fake_forge}):
                    payload = run_scoped_check(root, FORGE_ROOT, run_native=True)
                self.assertEqual(order, ["native", "forge"])
                self.assertEqual(payload["execution_order"], ["project-native-gate", "forge-application-checks"])

    def test_authoritative_change_record_is_persisted_in_existing_state_and_ledger(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._fixture(root)
                build_passport(root, FORGE_ROOT)
                (root / "index.php").write_text("<?php echo 'ledger';\n", encoding="utf-8")
                payload = run_scoped_check(root, FORGE_ROOT)
                state = load_state(root)
                self.assertEqual(state["change_ledger"]["id"], payload["change_ledger"]["id"])
                self.assertEqual(state["change_ledger"]["paths"], ["index.php"])
                ledger = (root / ".forge" / "ledger.jsonl").read_text(encoding="utf-8")
                self.assertIn('"kind":"change-accounting"', ledger)
                self.assertIn(payload["change_ledger"]["id"], ledger)


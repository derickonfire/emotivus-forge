from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from emotivus_forge.audit import run_audit
from emotivus_forge.config import default_config, load_config, save_config
from emotivus_forge.detect import detect_project
from emotivus_forge.init_project import initialize_project
from emotivus_forge.graph import analyze_impact, build_graph
from emotivus_forge.lab import default_lab_recipes, run_lab, run_required_labs
from emotivus_forge.runtime_contracts import (
    DEFAULT_REQUIRED_CATEGORIES, analyze_migration_chain, initialize_runtime_contracts, plan_runtime_proof,
    run_required_runtime_contracts, run_runtime_contract, validate_runtime_contract, _contract_fingerprint,
)
from emotivus_forge.learn import approve_learning, list_learning, propose_learning
from emotivus_forge.package import build_package
from emotivus_forge.release import validate_release
from emotivus_forge.tool_migration import absorb_tools, quarantine_replacements, scan_existing_tools, write_tool_reports
from emotivus_forge.setup import normalize_answers
from emotivus_forge.security import private_key_matches, secret_assignment_matches
from emotivus_forge.confidentiality import scan_confidentiality, scan_zip_archive
from emotivus_forge.mirror import configure_mirror_contract, _acquire_mirror_lock, _release_mirror_lock
from emotivus_forge.brief import build_brief
from emotivus_forge.doctor import run_doctor
from emotivus_forge.state import adopt_state, export_state, inspect_state
from emotivus_forge.runner import Check, build_plan, run_profile
from emotivus_forge.evidence import list_evidence, record_execution
from emotivus_forge.guardrails import guardrail_action
from emotivus_forge.config import migrate_config_file, migrate_config_data, CURRENT_CONFIG_SCHEMA
from emotivus_forge.remediation import remediation_action
from emotivus_forge.ci_bridge import ci_action
from emotivus_forge.delivery import build_internal_delivery
from emotivus_forge.update import apply_update, preview_update, rollback_update
from emotivus_forge.provenance import classify_workspace, infer_runtime_requirements, infer_work_scope, packaging_policy_contradictions
from emotivus_forge.release_proof import (
    build_final_delivery, build_release_proof, discover_surfaces,
    record_delivery_artifact, validate_delivery_provenance,
)
from emotivus_forge.utils import resolve_command, sha256_file, tree_fingerprint, write_json
from emotivus_forge.project_memory import (
    build_context_packet, initialize_project_memory, ledger_action, plan_action,
    pivot_action, validate_project_release,
)
from emotivus_forge.passport import build_project_passport, build_resume_packet, check_project
from emotivus_forge.selftest import _run_lock_path, build_shards, discover_unittest_classes, run_self_tests
from emotivus_forge.cli import _format_self_test_summary

FORGE_ROOT = Path(__file__).resolve().parents[1]


class ForgeDetectionTests(unittest.TestCase):
    def test_detects_multiple_stacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo 'ok';", encoding="utf-8")
            (root / "main.js").write_text("console.log('ok');", encoding="utf-8")
            (root / "style.css").write_text("body { margin: 0; }", encoding="utf-8")
            (root / ".htaccess").write_text("Options -Indexes\n", encoding="utf-8")
            detection = detect_project(root, FORGE_ROOT)
            self.assertEqual(set(detection.adapters), {"apache", "css", "javascript", "php"})

    def test_detects_package_version_and_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"version": "2.4.1", "scripts": {"lint": "eslint .", "test": "node test.js"}}), encoding="utf-8")
            detection = detect_project(root, FORGE_ROOT)
            self.assertEqual(detection.detected_version, "2.4.1")
            self.assertEqual(set(detection.package_scripts), {"lint", "test"})
            self.assertIn("node", detection.adapters)

    def test_detects_node_package_manager_from_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint ."}}), encoding="utf-8")
            (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            detection = detect_project(root, FORGE_ROOT)
            self.assertEqual(detection.package_manager, "pnpm")
            from emotivus_forge.config import default_config
            config = default_config("Fixture", detection)
            self.assertEqual(config["commands"]["quick"][0]["command"], ["pnpm", "run", "lint"])


class ForgeInitializationTests(unittest.TestCase):
    def test_existing_advisories_become_legacy_but_blockers_do_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo 'ok';", encoding="utf-8")
            payload = initialize_project(root, FORGE_ROOT, name="Fixture")
            self.assertEqual(payload["status"], "INITIALIZED")
            baseline = json.loads((root / ".forge" / "baseline.json").read_text())
            self.assertTrue(any(item["check_id"] == "quality.tests" for item in baseline["findings"].values()))
            (root / "conflict.txt").write_text("<<<<<<< HEAD\n", encoding="utf-8")
            config = load_config(root)
            audit = run_audit(root, FORGE_ROOT, config, use_baseline=True)
            conflict = next(item for item in audit["findings"] if item["check_id"] == "core.merge-marker-start")
            self.assertEqual(conflict["disposition"], "NEW")
            self.assertEqual(conflict["severity"], "blocker")
            self.assertEqual(audit["status"], "FAIL")

    def test_merge_marker_literals_inside_checker_code_are_not_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools" / "checker.py").write_text("print('<<<<<<<')\nprint('>>>>>>>')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype"})
            audit = run_audit(root, FORGE_ROOT, load_config(root), use_baseline=True)
            ids = {item["check_id"] for item in audit["findings"]}
            self.assertNotIn("core.merge-marker-start", ids)
            self.assertNotIn("core.merge-marker-end", ids)

    def test_strict_setup_does_not_baseline_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            payload = initialize_project(root, FORGE_ROOT, setup_answers={"preset": "strict"})
            baseline = json.loads((root / ".forge" / "baseline.json").read_text())
            self.assertEqual(baseline["findings"], {})
            self.assertEqual(payload["initial_audit_status"], "FAIL")
            decisions = json.loads((root / ".forge" / "SETUP-DECISIONS.json").read_text())
            self.assertFalse(decisions["baseline_existing_advisories"])
            self.assertTrue(decisions["tests_required"])

    def test_initialization_records_tool_migration_and_live_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"existing_tools": "audit", "live_checks": ["browser", "api"]})
            decisions = json.loads((root / ".forge" / "SETUP-DECISIONS.json").read_text())
            self.assertEqual(decisions["existing_tools"], "audit")
            checklist = (root / ".forge" / "LIVE-VERIFICATION-CHECKLIST.md").read_text()
            self.assertIn("browser", checklist)
            self.assertIn("api", checklist)
            self.assertTrue((root / ".forge" / "TOOL-MIGRATION-PLAN.md").is_file())

    def test_neutral_policy_pack_boundary_is_empty(self) -> None:
        entries = [path for path in (FORGE_ROOT / "policy-packs").iterdir() if path.name != "README.md"]
        self.assertEqual(entries, [])


class ForgeToolMigrationTests(unittest.TestCase):
    def test_inventory_detects_package_scripts_ci_and_quality_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint .", "build": "vite build"}}), encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "check_routes.py").write_text("print('route check')\n", encoding="utf-8")
            inventory = scan_existing_tools(root, FORGE_ROOT)
            paths = {item["path"] for item in inventory["candidates"]}
            self.assertIn("package.json#scripts.lint", paths)
            self.assertIn("package.json#scripts.build", paths)
            self.assertIn(".github/workflows/ci.yml", paths)
            self.assertIn("tools/check_routes.py", paths)

    def test_absorb_registers_safe_commands_without_removing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}), encoding="utf-8")
            (root / "tools").mkdir()
            script = root / "tools" / "check_routes.py"
            script.write_text("# lint routes\nprint('ok')\n", encoding="utf-8")
            detection = detect_project(root, FORGE_ROOT)
            from emotivus_forge.config import default_config
            config = default_config("Fixture", detection)
            inventory = scan_existing_tools(root, FORGE_ROOT)
            absorbed = absorb_tools(config, inventory)
            self.assertTrue(script.is_file())
            self.assertGreaterEqual(len(absorbed), 2)
            all_commands = [item["command"] for group in config["commands"].values() for item in group]
            self.assertIn(["npm", "run", "build"], all_commands)
            self.assertIn(["{python}", "{project}/tools/check_routes.py"], all_commands)

    def test_absorb_detects_composer_quality_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "composer.json").write_text(json.dumps({"scripts": {"analyse": "phpstan analyse", "test": "phpunit"}}), encoding="utf-8")
            from emotivus_forge.config import default_config
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            inventory = scan_existing_tools(root, FORGE_ROOT)
            absorbed = absorb_tools(config, inventory)
            commands = [item["command"] for group in config["commands"].values() for item in group]
            self.assertIn(["composer", "run-script", "analyse"], commands)
            self.assertIn(["composer", "run-script", "test"], commands)
            self.assertEqual(len(absorbed), 2)

    def test_absorb_does_not_duplicate_default_npm_lint_or_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint .", "test": "node test.js"}}), encoding="utf-8")
            from emotivus_forge.config import default_config
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            absorbed = absorb_tools(config, scan_existing_tools(root, FORGE_ROOT))
            self.assertEqual(absorbed, [])
            commands = [tuple(item["command"]) for group in config["commands"].values() for item in group]
            self.assertEqual(commands.count(("npm", "run", "lint")), 1)
            self.assertEqual(commands.count(("npm", "test")), 1)

    def _write_manifest_ecosystem(self, root: Path, *, unsafe: bool = False) -> None:
        (root / "tools" / "data").mkdir(parents=True)
        (root / "tests" / "fixtures").mkdir(parents=True)
        (root / "tools" / "run_quality.py").write_text(
            "#!/usr/bin/env python3\nREPORT_DIR = '.quality-reports'\nprint('PASS')\n",
            encoding="utf-8",
        )
        (root / "tools" / "check_leaf.py").write_text(
            "#!/usr/bin/env python3\n# lint leaf\nprint('PASS')\n",
            encoding="utf-8",
        )
        (root / "tools" / "data" / "rules.json").write_text('{"rule":"required"}\n', encoding="utf-8")
        (root / "tests" / "fixtures" / "broken.txt").write_text("fixture\n", encoding="utf-8")
        (root / "Emotivus-Forge" / "emotivus_forge").mkdir(parents=True)
        (root / "Emotivus-Forge" / "FORGE-MANIFEST.json").write_text(
            json.dumps({"forge_schema": 1, "name": "Emotivus Forge", "version": "0.9.0"}), encoding="utf-8"
        )
        (root / "Emotivus-Forge" / "emotivus_forge" / "audit.py").write_text("# lint\nprint('PASS')\n", encoding="utf-8")
        canonical = [
            "tools/", "tests/fixtures/", "Emotivus-Forge/**",
        ]
        if unsafe:
            canonical.append("../outside.json")
        (root / "TOOLSET-MANIFEST.json").write_text(json.dumps({
            "name": "Neutral Quality Suite",
            "canonical_paths": canonical,
            "commands": {
                "quick": "python3 tools/run_quality.py --profile quick",
                "section": "python3 tools/run_quality.py --profile section",
                "toolset": "python3 tools/run_quality.py --profile toolset --jobs 4",
                "release": "python3 tools/run_quality.py --profile release --fresh",
                "resume": "python3 tools/run_quality.py --profile <profile> --resume",
            },
            "delivery_artifact": "Quality-Toolset.zip",
        }, indent=2), encoding="utf-8")

    def test_manifest_ecosystem_indexes_full_working_set_and_suppresses_leaf_absorption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_manifest_ecosystem(root)
            inventory = scan_existing_tools(root, FORGE_ROOT)
            self.assertEqual(inventory["schema"], 2)
            self.assertEqual(inventory["ecosystem_count"], 1)
            ecosystem = inventory["ecosystems"][0]
            self.assertEqual(ecosystem["status"], "ready")
            self.assertIn("tools/data/rules.json", ecosystem["working_set"]["dataset_paths"])
            self.assertIn("tests/fixtures/broken.txt", ecosystem["working_set"]["dataset_paths"])
            self.assertEqual(ecosystem["bundled_products"][0]["path"], "Emotivus-Forge")
            candidate_paths = {item["path"] for item in inventory["candidates"]}
            self.assertNotIn("tools/check_leaf.py", candidate_paths)
            self.assertFalse(any(path.startswith("Emotivus-Forge/") for path in candidate_paths))

    def test_ecosystem_adoption_registers_only_canonical_profiles_and_reuses_stricter_existing_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_manifest_ecosystem(root)
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            config["commands"]["quick"] = [{
                "id": "host.quick",
                "command": ["python3", "tools/run_quality.py", "--profile", "quick", "--fresh"],
                "timeout": 300,
            }]
            inventory = scan_existing_tools(root, FORGE_ROOT)
            absorbed = absorb_tools(config, inventory)
            commands = [item for group in config["commands"].values() for item in group]
            self.assertEqual(len(commands), 4)
            self.assertEqual(sum(1 for item in commands if "check_leaf.py" in " ".join(item["command"])), 0)
            self.assertEqual(len(absorbed), 3)
            existing = next(item for item in commands if item["id"] == "host.quick")
            self.assertEqual(existing["ecosystem_id"], "neutral-quality-suite")
            self.assertIn("tools/data/rules.json", existing["ecosystem_inputs"])
            self.assertEqual(config["tool_migration"]["ecosystems"][0]["status"], "active")

    def test_ecosystem_dataset_change_invalidates_command_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_manifest_ecosystem(root)
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            absorb_tools(config, scan_existing_tools(root, FORGE_ROOT))
            before = next(check.command_hash for check in build_plan(root, FORGE_ROOT, config, "quick") if check.check_id.startswith("ecosystem."))
            (root / "tools" / "data" / "rules.json").write_text('{"rule":"changed"}\n', encoding="utf-8")
            after = next(check.command_hash for check in build_plan(root, FORGE_ROOT, config, "quick") if check.check_id.startswith("ecosystem."))
            self.assertNotEqual(before, after)

    def test_missing_adopted_ecosystem_input_blocks_before_command_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_manifest_ecosystem(root)
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            absorb_tools(config, scan_existing_tools(root, FORGE_ROOT))
            (root / "tools" / "data" / "rules.json").unlink()
            payload = run_profile(root, FORGE_ROOT, config, "quick", fresh=True, only=["ecosystem."])
            self.assertEqual(payload["status"], "FAIL")
            result = payload["results"][0]
            self.assertEqual(result["error_kind"], "tool-ecosystem-inputs")
            self.assertIn("tools/data/rules.json", result["output"])

    def test_ecosystem_registry_references_generated_state_without_copying_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_manifest_ecosystem(root)
            (root / ".quality-reports").mkdir()
            report = root / ".quality-reports" / "quick.json"
            report.write_text('{"status":"PASS"}\n', encoding="utf-8")
            inventory = scan_existing_tools(root, FORGE_ROOT)
            generated = inventory["ecosystems"][0]["generated_state"]
            self.assertTrue(any(item["path"] == ".quality-reports" and item["exists"] for item in generated))
            paths = write_tool_reports(root, inventory)
            self.assertTrue(Path(paths["ecosystems_json"]).is_file())
            self.assertTrue((root / ".forge" / "tool-ecosystems" / "neutral-quality-suite.json").is_file())
            self.assertTrue(report.is_file())
            self.assertFalse((root / ".forge" / "tool-ecosystems" / "quick.json").exists())

    def test_unsafe_manifest_path_requires_review_and_is_not_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_manifest_ecosystem(root, unsafe=True)
            inventory = scan_existing_tools(root, FORGE_ROOT)
            ecosystem = inventory["ecosystems"][0]
            self.assertEqual(ecosystem["status"], "review")
            self.assertTrue(any("unsafe canonical path" in item for item in ecosystem["problems"]))
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            self.assertEqual(absorb_tools(config, inventory), [])
            self.assertEqual(sum(len(group) for group in config["commands"].values()), 0)

    def test_adopt_is_canonical_and_absorb_remains_a_legacy_alias(self) -> None:
        self.assertEqual(normalize_answers({"existing_tools": "adopt"})["existing_tools"], "adopt")
        self.assertEqual(normalize_answers({"existing_tools": "absorb"})["existing_tools"], "adopt")

    def test_remove_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools" / "check_merge_markers.py").write_text("print('<<<<<<<')\nprint('>>>>>>>')\n", encoding="utf-8")
            inventory = scan_existing_tools(root, FORGE_ROOT)
            with self.assertRaises(RuntimeError):
                quarantine_replacements(root, inventory, confirmed=False)

    def test_confirmed_remove_is_reversible_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            source = root / "tools" / "check_merge_markers.py"
            source.write_text("# merge marker checker\nprint('<<<<<<<')\nprint('>>>>>>>')\n", encoding="utf-8")
            inventory = scan_existing_tools(root, FORGE_ROOT)
            candidate = next(item for item in inventory["candidates"] if item["path"] == "tools/check_merge_markers.py")
            self.assertEqual(candidate["recommendation"], "replace")
            result = quarantine_replacements(root, inventory, confirmed=True)
            self.assertFalse(source.exists())
            quarantined = root / result["entries"][0]["quarantined"]
            self.assertTrue(quarantined.is_file())
            restore = json.loads((root / ".forge" / "legacy-tools" / "RESTORE-MANIFEST.json").read_text())
            self.assertEqual(restore["entries"][0]["original"], "tools/check_merge_markers.py")
            self.assertEqual(len(restore["entries"][0]["sha256"]), 64)

    def test_normal_initialization_only_audits_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            source = root / "tools" / "check_merge_markers.py"
            source.write_text("print('<<<<<<<')\nprint('>>>>>>>')\n", encoding="utf-8")
            payload = initialize_project(root, FORGE_ROOT)
            self.assertTrue(source.is_file())
            self.assertEqual(payload["tool_action"], "audit")
            self.assertEqual(payload["quarantined_files"], 0)


class ForgePackagingTests(unittest.TestCase):
    def test_package_excludes_forge_and_contains_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="Fixture")
            config = load_config(root)
            output = root / "out.zip"
            result = build_package(root, FORGE_ROOT, config, output=output)
            self.assertEqual(result["status"], "PASS", result["problems"])
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn("index.html", names)
            self.assertIn("FORGE-DEPLOY-MANIFEST.json", names)
            self.assertNotIn(".emotivus-forge.json", names)
            self.assertNotIn(".deployignore", names)
            self.assertFalse(any(name.startswith(".forge/") for name in names))
            second = build_package(root, FORGE_ROOT, config, output=output)
            self.assertEqual(second["status"], "PASS")
            with zipfile.ZipFile(output) as archive:
                self.assertNotIn("out.zip", archive.namelist())

    def test_negated_sensitive_file_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="Fixture")
            # forge: synthetic-secret — this literal exists only to prove package blocking.
            (root / ".env").write_text("API_KEY='actual-secret-value'\n", encoding="utf-8")
            with (root / ".deployignore").open("a", encoding="utf-8") as handle:
                handle.write("!.env\n")
            config = load_config(root)
            config["packaging"]["required_files"] = [".env"]
            result = build_package(root, FORGE_ROOT, config, dry_run=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("hard-excluded" in problem or "credential" in problem or "missing or excluded" in problem for problem in result["problems"]))


    def test_required_file_under_ordinary_excluded_directory_is_packaged_without_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo 'ok';", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "RELEASE-CLAIMS.md").write_text("required release instructions\n", encoding="utf-8")
            (root / "docs" / "INTERNAL-NOTES.md").write_text("internal only\n", encoding="utf-8")
            initialize_project(
                root, FORGE_ROOT,
                setup_answers={
                    "preset": "strict",
                    "versioning": "none",
                    "required_files": ["docs/RELEASE-CLAIMS.md"],
                },
            )
            config = load_config(root)
            result = build_package(root, FORGE_ROOT, config, dry_run=True)
            included = {item["path"] for item in result["manifest"]["included_files"]}
            self.assertEqual(result["status"], "PASS", result["problems"])
            self.assertIn("docs/RELEASE-CLAIMS.md", included)
            self.assertNotIn("docs/INTERNAL-NOTES.md", included)
            self.assertEqual(packaging_policy_contradictions(root, config), [])


class ForgeWorkflowTests(unittest.TestCase):
    def test_python_audit_does_not_write_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="Python Fixture")
            config = load_config(root)
            audit = run_audit(root, FORGE_ROOT, config, use_baseline=True)
            self.assertEqual(audit["status"], "PASS")
            self.assertFalse(any(path.name == "__pycache__" for path in root.rglob("__pycache__")))

    def test_resume_reuses_pass_only_when_tree_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("one", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="Resume Fixture")
            first = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "check", str(root), "--profile", "quick"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(first.returncode, 0, first.stdout)
            second = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "check", str(root), "--profile", "quick", "--resume"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(second.returncode, 0, second.stdout)
            report = json.loads((root / ".forge" / "reports" / "quick.json").read_text())
            self.assertTrue(report["results"][0]["resumed"])
            (root / "index.html").write_text("two", encoding="utf-8")
            third = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "check", str(root), "--profile", "quick", "--resume"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(third.returncode, 0, third.stdout)
            report = json.loads((root / ".forge" / "reports" / "quick.json").read_text())
            self.assertFalse(report["results"][0]["resumed"])

    def test_baseline_command_refuses_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="Baseline Fixture")
            (root / "broken.txt").write_text(">>>>>>> branch\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "baseline", str(root)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("cannot be baselined", result.stdout)

    def test_package_command_requires_frozen_release_unless_development_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="Package Gate")
            blocked = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "package", str(root), "--dry-run"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(blocked.returncode, 1, blocked.stdout)
            self.assertIn("release quality gate", blocked.stdout)
            development = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "package", str(root), "--development", "--dry-run"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(development.returncode, 0, development.stdout)

    def test_answers_file_cli_configures_tool_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            answers = root / "answers.json"
            answers.write_text(json.dumps({"preset": "prototype", "existing_tools": "audit", "versioning": "none"}), encoding="utf-8")
            result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "init", str(root), "--answers", str(answers)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(result.returncode, 0, result.stdout)
            config = load_config(root)
            self.assertEqual(config["tool_migration"]["mode"], "audit")
            self.assertFalse(config["versioning"]["enabled"])

    def test_runner_does_not_wait_for_descendant_output_handles(self) -> None:
        import time
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="Descendant Fixture", setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            config["commands"]["quick"] = [{
                "id": "spawn.descendant",
                "command": ["{python}", "-c", "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)']); print('parent done')"],
                "timeout": 5
            }]
            from emotivus_forge.runner import run_profile
            before = time.monotonic()
            result = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            elapsed = time.monotonic() - before
            self.assertEqual(result["status"], "PASS", result)
            self.assertLess(elapsed, 4.0)


class ForgeReleaseTests(unittest.TestCase):
    def test_generic_version_source_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "version.txt").write_text("APP_VERSION=3.7.1\n", encoding="utf-8")
            config = {
                "versioning": {
                    "enabled": True, "status": "release", "baseline_version": "3.7.0", "target_version": "3.7.1",
                    "package_version": "371", "package_version_rule": "remove_dots",
                    "source": {"path": "version.txt", "regex": r"APP_VERSION=([^\s]+)"},
                    "migration": {"required": False, "path": ""},
                }
            }
            self.assertEqual(validate_release(root, config), [])
            config["versioning"]["target_version"] = "3.7.2"
            self.assertTrue(any("runtime version" in item for item in validate_release(root, config)))




class ForgePassportTests(unittest.TestCase):
    def test_passport_tracks_changes_without_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text("print('one')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            first = build_project_passport(root, FORGE_ROOT, config, refresh_graph=True, refresh_proof=True, checkpoint=True, checkpoint_kind="adopted")
            self.assertEqual(first["changes"]["count"], 0)
            source.write_text("print('two')\n", encoding="utf-8")
            resumed = build_resume_packet(root, FORGE_ROOT, config, budget="compact")
            self.assertEqual(resumed["changes"]["modified"], ["app.py"])
            self.assertTrue((root / ".forge" / "passport" / "passport.json").is_file())
            self.assertTrue((root / ".forge" / "passport" / "resume.md").is_file())

    def test_check_records_impact_and_advances_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text("print('one')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            build_project_passport(root, FORGE_ROOT, config, refresh_graph=True, refresh_proof=True, checkpoint=True, checkpoint_kind="adopted")
            source.write_text("print('two')\n", encoding="utf-8")
            payload = check_project(root, FORGE_ROOT, config, profile="quick")
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["changes"]["modified"], ["app.py"])
            after = build_project_passport(root, FORGE_ROOT, config)
            self.assertEqual(after["changes"]["count"], 0)

    def test_public_help_exposes_only_pivot_workflow(self) -> None:
        result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "--help"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(result.returncode, 0, result.stdout)
        for command in ("help", "adopt", "resume", "check", "ship"):
            self.assertIn(command, result.stdout)
        self.assertNotIn("Understand the project", result.stdout)

    def test_help_is_read_only_and_recommends_adopt_then_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text("print('one')\n", encoding="utf-8")
            first = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "help", "--project", str(root), "--json"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(first.returncode, 0, first.stdout)
            first_payload = json.loads(first.stdout)
            self.assertEqual(first_payload["project_state"]["state"], "NOT_ADOPTED")
            self.assertEqual(first_payload["project_state"]["next_action"]["command"], "forge adopt .")
            self.assertFalse((root / ".forge").exists())

            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            build_project_passport(root, FORGE_ROOT, config, refresh_graph=True, refresh_proof=True, checkpoint=True, checkpoint_kind="adopted")
            source.write_text("print('two')\n", encoding="utf-8")
            changed = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "help", "--project", str(root), "--json"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(changed.returncode, 0, changed.stdout)
            changed_payload = json.loads(changed.stdout)
            self.assertEqual(changed_payload["project_state"]["state"], "CHANGED")
            self.assertEqual(changed_payload["project_state"]["changes"]["modified"], ["app.py"])
            self.assertEqual(changed_payload["project_state"]["next_action"]["command"], "forge check . --profile quick")


    def test_resume_reports_measured_token_efficiency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "large_module.py").write_text("value = 'continuity'\n" * 12000, encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            build_project_passport(root, FORGE_ROOT, config, refresh_graph=True, refresh_proof=True, checkpoint=True, checkpoint_kind="adopted")
            packet = build_resume_packet(root, FORGE_ROOT, config, budget="compact")
            efficiency = packet["token_efficiency"]
            self.assertEqual(packet["token_limit"], 1200)
            self.assertLessEqual(packet["estimated_tokens"], packet["token_limit"] )
            self.assertGreater(efficiency["project_token_equivalent_estimate"], packet["estimated_tokens"] )
            self.assertGreater(efficiency["estimated_tokens_avoided"], 0)
            self.assertGreater(efficiency["estimated_context_reduction_percent"], 0)
            self.assertIn("Heuristic", efficiency["method"] )

    def test_frg_optional_launcher_preserves_the_five_command_interface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('alias')\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "frg.py"), "help", "--project", str(root), "--json"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["command_name"], "frg")
            self.assertEqual(payload["project_state"]["next_action"]["command"], "frg adopt .")
            self.assertEqual(payload["workflow"][0]["command"], "frg help")
            self.assertTrue((FORGE_ROOT / "frg").is_file())
            self.assertTrue((FORGE_ROOT / "frg.cmd").is_file())

    def test_running_forge_without_arguments_refuses_to_adopt_forge_core_without_host(self) -> None:
        result = subprocess.run(
            [sys.executable, str(FORGE_ROOT / "forge.py")],
            cwd=FORGE_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("FORGE NOT STARTED", result.stdout)
        self.assertIn("No host-project files", result.stdout)
        self.assertFalse((FORGE_ROOT / ".forge").exists())

    def test_running_forge_without_arguments_adopts_then_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('hello')\n", encoding="utf-8")
            first = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py")],
                cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(first.returncode, 0, first.stdout)
            self.assertIn("Action:  ADOPT + RESUME", first.stdout)
            self.assertTrue((root / ".forge" / "passport" / "passport.md").is_file())
            self.assertTrue((root / ".forge" / "passport" / "resume.md").is_file())
            second = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py")],
                cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(second.returncode, 0, second.stdout)
            self.assertIn("Action:  RESUME", second.stdout)
            self.assertNotIn("Action:  ADOPT + RESUME", second.stdout)

    def test_running_forge_without_arguments_checks_changed_paths_without_shipping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "app.py"
            source.write_text("print('one')\n", encoding="utf-8")
            subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py")],
                cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
            )
            source.write_text("print('two')\n", encoding="utf-8")
            changed = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py")],
                cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(changed.returncode, 0, changed.stdout)
            self.assertIn("Action:  CHECK + RESUME", changed.stdout)
            payload = json.loads((root / ".forge" / "passport" / "run-latest.json").read_text())
            self.assertEqual(payload["changes"]["modified"], ["app.py"] )
            self.assertFalse(payload["safety"]["ship_invoked"] )
            self.assertFalse((root / "deploy").exists())

class ForgeDocumentationTests(unittest.TestCase):
    def test_human_documentation_site_is_self_contained(self) -> None:
        index = FORGE_ROOT / "docs-site" / "index.html"
        css = FORGE_ROOT / "docs-site" / "assets" / "styles.css"
        script = FORGE_ROOT / "docs-site" / "assets" / "app.js"
        self.assertTrue(index.is_file())
        self.assertTrue(css.is_file())
        self.assertTrue(script.is_file())
        text = index.read_text(encoding="utf-8")
        self.assertIn("Project Passport", text)
        self.assertIn("Help", text)
        self.assertIn("1.4.1-dev", text)
        self.assertIn("Run Forge", text)
        self.assertIn("Five commands", text)
        self.assertIn("forge.emotivus.com", text)
        self.assertIn("Tempered Continuity", (FORGE_ROOT / "docs" / "BRAND-IDENTITY.md").read_text(encoding="utf-8"))
        self.assertNotIn("http://", text)
        self.assertIn("https://forge.emotivus.com", text)

    def test_public_website_has_release_bound_pages_and_download_contract(self) -> None:
        product = json.loads((FORGE_ROOT / "FORGE-PRODUCT.json").read_text(encoding="utf-8"))
        self.assertEqual(product["website"]["base_url"], "https://forge.emotivus.com")
        for relative in (
            "index.html", "run/index.html", "docs/index.html", "roadmap/index.html",
            "trust/index.html", "changelog/index.html", "robots.txt", "sitemap.xml",
            "site.webmanifest", "assets/forge-mark.svg", "assets/favicon.svg",
        ):
            self.assertTrue((FORGE_ROOT / "docs-site" / relative).is_file(), relative)
        run_page = (FORGE_ROOT / "docs-site" / "run" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Run Forge.", run_page)
        self.assertIn("RUN-FORGE.zip", run_page)
        self.assertIn("never automatically", run_page)
        sitemap = (FORGE_ROOT / "docs-site" / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://forge.emotivus.com/run/", sitemap)

    def test_setup_example_is_valid_and_neutral(self) -> None:
        example = FORGE_ROOT / "examples" / "forge-setup.example.json"
        payload = json.loads(example.read_text(encoding="utf-8"))
        self.assertEqual(payload["existing_tools"], "audit")
        self.assertEqual(payload["deployment"], "auto")
        self.assertEqual(payload["required_files"], [])

    def test_docs_cli_returns_local_path(self) -> None:
        result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "docs"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(Path(payload["path"]).is_file())
        self.assertTrue(payload["uri"].startswith("file:"))


class ForgeManifestTests(unittest.TestCase):
    def test_manifest_is_neutral_and_complete(self) -> None:
        manifest = json.loads((FORGE_ROOT / "FORGE-MANIFEST.json").read_text())
        self.assertEqual(manifest["forge_schema"], 1)
        self.assertEqual(manifest["version"], "1.4.1-dev")
        paths = manifest["canonical_paths"]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertIn("forge.py", paths)
        self.assertIn("frg.py", paths)
        self.assertIn("frg", paths)
        self.assertIn("frg.cmd", paths)
        self.assertIn("emotivus_forge/", paths)
        self.assertIn("docs-site/", paths)
        self.assertIn("planning/", paths)
        self.assertIn("release/", paths)
        self.assertIn("policy-packs/", paths)
        self.assertIn("self/", paths)
        self.assertEqual(manifest["website"]["base_url"], "https://forge.emotivus.com")

    def test_public_distribution_is_lean_and_bootstrap_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "Emotivus-Forge-1.4.1-dev.zip"
            built = subprocess.run([
                sys.executable, str(FORGE_ROOT / "tools" / "build_forge_package.py"), str(FORGE_ROOT),
                "--edition", "public", "--output", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(built.returncode, 0, built.stdout)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("Emotivus-Forge/README.md", names)
                self.assertIn("Emotivus-Forge/RUN-FORGE.md", names)
                self.assertIn("Emotivus-Forge/docs/WHY-FORGE.md", names)
                self.assertNotIn("Emotivus-Forge/IMPLEMENTATION-REPORT.md", names)
                self.assertNotIn("Emotivus-Forge/CERTIFICATION.md", names)
                self.assertNotIn("Emotivus-Forge/ROADMAP.md", names)
                self.assertFalse(any(name.startswith("Emotivus-Forge/self/.runtime/") for name in names))
                manifest = json.loads(archive.read("Emotivus-Forge/FORGE-MANIFEST.json"))
                self.assertEqual(manifest["edition"], "public")
                self.assertEqual(manifest["version"], "1.4.1-dev")
            checked = subprocess.run([
                sys.executable, str(FORGE_ROOT / "tools" / "forge_bootstrap.py"), str(FORGE_ROOT),
                "--archive", str(output), "--skip-self-test",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(checked.returncode, 0, checked.stdout)

    def test_distribution_confidentiality_policy_is_generic_and_source_scan_passes(self) -> None:
        policy_path = FORGE_ROOT / "CONFIDENTIALITY-POLICY.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        for key in (
            "forbidden_terms",
            "forbidden_sha256",
            "forbidden_normalized_sha256",
            "forbidden_path_patterns",
        ):
            self.assertEqual(policy.get(key, []), [], f"public policy must not embed private values: {key}")
        payload = scan_confidentiality(FORGE_ROOT, policy_path=policy_path, write=False)
        self.assertEqual(payload["status"], "PASS", payload["findings"])


class ForgeGraphTests(unittest.TestCase):
    def test_graph_maps_routes_dependencies_environment_and_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "routes.js").write_text("import './service.js';\napp.get('/health', handler);\nconst key = process.env.API_KEY;\nfetch('https://api.vendor.test/v1');\n", encoding="utf-8")
            (root / "src" / "service.js").write_text("export const handler = () => 'ok';\n", encoding="utf-8")
            (root / "tests" / "routes.test.js").write_text("import '../src/routes.js';\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            graph = build_graph(root, FORGE_ROOT, load_config(root), write=True)
            self.assertIn("/health", graph["facts"]["routes"])
            self.assertIn("API_KEY", graph["facts"]["environment_variables"])
            self.assertIn("api.vendor.test", graph["facts"]["external_hosts"])
            edge_types = {edge["type"] for edge in graph["edges"]}
            self.assertIn("depends-on", edge_types)
            self.assertIn("tests", edge_types)

    def test_impact_returns_targeted_tests_and_live_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "client.js").write_text("fetch('https://api.vendor.test/v1');\n", encoding="utf-8")
            (root / "tests" / "client.test.js").write_text("import '../src/client.js';\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            impact = analyze_impact(root, FORGE_ROOT, load_config(root), ["src/client.js"])
            self.assertIn("tests/client.test.js", impact["targeted_tests"])
            self.assertIn("api", impact["recommended_live_checks"])
            self.assertIn(impact["risk"]["level"], {"low", "medium", "high", "critical"})

    def test_graph_cli_writes_human_and_machine_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "graph", str(root)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue((root / ".forge" / "graph" / "project-graph.json").is_file())
            self.assertTrue((root / ".forge" / "graph" / "project-graph.md").is_file())


class ForgeLearnTests(unittest.TestCase):
    def _proposal(self, root: Path, regression: dict[str, object], severity: str = "error") -> dict[str, object]:
        defect = root / "defect.json"
        defect.write_text(json.dumps({
            "title": "Required public marker",
            "invariant": "The public marker must remain present.",
            "severity": severity,
            "category": "behavior",
            "affected_paths": ["index.html"],
            "regression": regression,
        }), encoding="utf-8")
        return propose_learning(root, FORGE_ROOT, load_config(root), defect)

    def test_proposal_is_inactive_until_approved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            self._proposal(root, {"kind": "file_contains", "path": "index.html", "text": "missing-marker"})
            audit = run_audit(root, FORGE_ROOT, load_config(root), use_baseline=True)
            self.assertFalse(any(item["check_id"].startswith("learn.contract.") for item in audit["findings"]))

    def test_approved_contract_fails_when_invariant_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("required-marker", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            proposed = self._proposal(root, {"kind": "file_contains", "path": "index.html", "text": "required-marker"})
            approve_learning(root, load_config(root), proposed["proposal"]["id"])
            (root / "index.html").write_text("removed", encoding="utf-8")
            audit = run_audit(root, FORGE_ROOT, load_config(root), use_baseline=True)
            self.assertEqual(audit["status"], "FAIL")
            self.assertTrue(any(item["check_id"].startswith("learn.contract.") for item in audit["findings"]))

    def test_learned_warning_cannot_be_hidden_by_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            proposed = self._proposal(root, {"kind": "file_contains", "path": "index.html", "text": "missing-marker"}, severity="warning")
            approve_learning(root, load_config(root), proposed["proposal"]["id"])
            result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "baseline", str(root)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("learned-contract", result.stdout)

    def test_command_contract_is_registered_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            proposed = self._proposal(root, {"kind": "command", "command": ["{python}", "-c", "print('ok')"]})
            proposal_id = proposed["proposal"]["id"]
            approve_learning(root, load_config(root), proposal_id)
            approve_learning(root, load_config(root), proposal_id)
            config = load_config(root)
            learned = [item for group in config["commands"].values() for item in group if item.get("learned_contract") == proposal_id]
            self.assertEqual(len(learned), 1)
            self.assertEqual(len(list_learning(root, config)["contracts"]), 1)


class ForgeLabTests(unittest.TestCase):
    def test_initialization_infers_static_smoke_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none", "lab": "plan"})
            config = load_config(root)
            self.assertIn("static-smoke", [item["id"] for item in config["lab"]["recipes"]])
            self.assertTrue((root / ".forge" / "lab" / "lab-plan.json").is_file())

    def test_static_lab_runs_in_disposable_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none", "lab": "plan"})
            result = run_lab(root, FORGE_ROOT, load_config(root), "static-smoke")
            self.assertEqual(result["status"], "PASS", result["errors"])
            self.assertEqual(result["workspace"], "removed")
            self.assertEqual(result["probe_results"][0]["status_code"], 200)

    def test_required_lab_fails_without_assigned_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none", "lab": "plan"})
            config = load_config(root)
            config["lab"]["required_profiles"] = ["release"]
            ok, message = run_required_labs(root, FORGE_ROOT, config, "release")
            self.assertFalse(ok)
            self.assertIn("no enabled recipe", message)

    def test_lab_copy_excludes_forge_internal_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none", "lab": "plan"})
            config = load_config(root)
            recipe = next(item for item in config["lab"]["recipes"] if item["id"] == "static-smoke")
            recipe["verify"] = [["{python}", "-c", "from pathlib import Path; import sys; w=Path(r'{workspace}'); sys.exit(1 if (w/'.emotivus-forge.json').exists() or (w/'FORGE-AGENT.md').exists() or (w/'.forge').exists() else 0)"]]
            result = run_lab(root, FORGE_ROOT, config, "static-smoke")
            self.assertEqual(result["status"], "PASS", result["errors"])


class ForgeIntelligenceSetupTests(unittest.TestCase):
    def test_setup_records_graph_learn_and_lab_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none", "graph": "on", "learn": "on", "lab": "required"})
            decisions = json.loads((root / ".forge" / "SETUP-DECISIONS.json").read_text())
            self.assertEqual(decisions["schema"], 3)
            self.assertEqual(decisions["graph"], "on")
            self.assertEqual(decisions["learn"], "on")
            self.assertEqual(decisions["lab"], "required")
            self.assertIn("release", load_config(root)["lab"]["required_profiles"])

    def test_section_profile_refreshes_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "check", str(root), "--profile", "section"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(result.returncode, 0, result.stdout)
            report = json.loads((root / ".forge" / "reports" / "section.json").read_text())
            self.assertIn("graph.refresh", report["required_check_ids"])

    def test_tool_inventory_recognizes_graph_and_lab_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools" / "architecture_graph.py").write_text("# dependency graph and blast radius\n", encoding="utf-8")
            (root / "tools" / "e2e_smoke.py").write_text("# playwright smoke test\n", encoding="utf-8")
            inventory = scan_existing_tools(root, FORGE_ROOT)
            capabilities = {cap for item in inventory["candidates"] for cap in item["capabilities"]}
            self.assertIn("architecture-graph", capabilities)
            self.assertIn("live-lab", capabilities)


class ForgeMirrorFoundationTests(unittest.TestCase):
    def test_detects_forge_identity_and_python_dunder_version(self) -> None:
        detection = detect_project(FORGE_ROOT, FORGE_ROOT)
        self.assertEqual(detection.identity, "emotivus-forge-core")
        self.assertEqual(detection.detected_version, "1.4.1-dev")
        self.assertEqual(detection.version_path, "emotivus_forge/__init__.py")

    def test_detector_definition_is_not_private_key_material(self) -> None:
        source = 'MARKER = "-----BEGIN PRIVATE KEY-----"\n'
        self.assertEqual(private_key_matches(source, "checker.py"), [])

    def test_real_pem_block_is_private_key_material(self) -> None:
        source = "-----BEGIN PRIVATE KEY-----\n" + ("A" * 64) + "\n-----END PRIVATE KEY-----"
        self.assertTrue(private_key_matches(source, "secret.pem"))

    def test_synthetic_secret_annotation_suppresses_only_declared_fixture(self) -> None:
        declared = "# forge: synthetic-secret\nAPI_KEY='fixture-secret-1234'\n"
        undeclared = "API_KEY='fixture-secret-1234'\n"
        self.assertEqual(secret_assignment_matches(declared, "tests/test_security.py"), [])
        self.assertTrue(secret_assignment_matches(undeclared, "app.py"))

    def test_forge_owned_tools_are_retained_during_self_inventory(self) -> None:
        inventory = scan_existing_tools(FORGE_ROOT, FORGE_ROOT)
        owned = [item for item in inventory["candidates"] if item["kind"] == "forge-core"]
        self.assertTrue(owned)
        self.assertTrue(all(item["recommendation"] == "retain" for item in owned))

    def test_forge_self_labs_are_inferred(self) -> None:
        recipes = default_lab_recipes(FORGE_ROOT, ["python", "javascript", "css"])
        ids = {item["id"] for item in recipes}
        self.assertTrue({"forge-cli-smoke", "forge-docs-smoke", "forge-bootstrap-smoke"}.issubset(ids))

    def test_forge_cli_lab_checks_lifecycle_without_repeating_full_self_test(self) -> None:
        recipe = next(item for item in default_lab_recipes(FORGE_ROOT, ["python"]) if item["id"] == "forge-cli-smoke")
        setup_commands = [" ".join(command) for command in recipe["setup"]]
        commands = [" ".join(item.get("command", [])) if isinstance(item, dict) else " ".join(item) for item in recipe["verify"]]
        self.assertTrue(any(" adopt " in f" {command} " for command in setup_commands))
        self.assertTrue(any("--version" in command for command in commands))
        self.assertTrue(any("resume" in command for command in commands))
        self.assertTrue(any("check" in command for command in commands))
        self.assertFalse(any("self-test" in command for command in commands))

    def test_forge_bootstrap_lab_does_not_repeat_full_self_test(self) -> None:
        recipe = next(item for item in default_lab_recipes(FORGE_ROOT, ["python"]) if item["id"] == "forge-bootstrap-smoke")
        commands = [" ".join(item.get("command", [])) if isinstance(item, dict) else " ".join(item) for item in recipe["verify"]]
        self.assertTrue(any("--skip-self-test" in command for command in commands))

    def test_mirror_contract_runs_section_regressions_once(self) -> None:
        detection = detect_project(FORGE_ROOT, FORGE_ROOT)
        config = default_config("Emotivus Forge", detection)
        config["lab"]["recipes"] = default_lab_recipes(FORGE_ROOT, detection.adapters)
        configured = configure_mirror_contract(config, "1.0.2", "1.0.3")
        self.assertEqual(configured["profiles"]["section"]["commands"], ["quick", "section"])
        self.assertEqual(configured["profiles"]["release"]["commands"], ["quick", "release"])
        cli_recipe = next(item for item in configured["lab"]["recipes"] if item["id"] == "forge-cli-smoke")
        self.assertEqual(cli_recipe["profiles"], ["section"])

    def test_independent_bootstrap_validator_passes_source_tree(self) -> None:
        result = subprocess.run(
            [sys.executable, str(FORGE_ROOT / "tools" / "forge_bootstrap.py"), str(FORGE_ROOT), "--skip-self-test"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_self_contracts_are_valid_and_active(self) -> None:
        contracts = json.loads((FORGE_ROOT / "self" / "learned-contracts.json").read_text(encoding="utf-8"))
        self.assertEqual(contracts["schema"], 1)
        self.assertGreaterEqual(len(contracts["contracts"]), 4)
        self.assertTrue(all(item["active"] for item in contracts["contracts"]))

    def test_mirror_rejects_non_forge_project(self) -> None:
        from emotivus_forge.mirror import run_mirror
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                run_mirror(root, baseline_version="1.0.2", release_version="1.0.3")

    def test_mirror_lock_blocks_concurrent_or_interrupted_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = _acquire_mirror_lock(root, "1.0.5")
            try:
                with self.assertRaises(RuntimeError):
                    _acquire_mirror_lock(root, "1.0.5")
            finally:
                _release_mirror_lock(lock)
            self.assertFalse(lock.exists())


class ForgeFirstContactTests(unittest.TestCase):
    def test_detects_plain_php_define_version_without_inventing_npm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            (root / "app" / "bootstrap.php").write_text("<?php define('LC_VERSION', '0.19.26');\n", encoding="utf-8")
            detection = detect_project(root, FORGE_ROOT)
            self.assertEqual(detection.detected_version, "0.19.26")
            self.assertEqual(detection.version_path, "app/bootstrap.php")
            self.assertEqual(detection.package_manager, "")

    def test_real_project_checker_docstring_does_not_trigger_conflict_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools" / "php_structural_check.py").write_text(
                '"""Examples:\n    <<<<<<< HEAD\n======= alone is not proof\n>>>>>>> branch\n"""\nprint("ok")\n',
                encoding="utf-8",
            )
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            audit = run_audit(root, FORGE_ROOT, load_config(root), use_baseline=True)
            ids = {item["check_id"] for item in audit["findings"]}
            self.assertNotIn("core.merge-marker-start", ids)
            self.assertNotIn("core.merge-marker-end", ids)
            (root / "broken.php").write_text("<<<<<<< HEAD\n<?php echo 'x';\n", encoding="utf-8")
            audit = run_audit(root, FORGE_ROOT, load_config(root), use_baseline=True)
            self.assertIn("core.merge-marker-start", {item["check_id"] for item in audit["findings"]})

    def test_application_php_is_never_recommended_for_absorption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            (root / "app" / "bootstrap.php").write_text("<?php function run_tests(){ return true; }\n", encoding="utf-8")
            (root / "admin.php").write_text("<?php require 'app/bootstrap.php'; session_start(); echo '<html>';\n", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "run_all_checks.sh").write_text("#!/bin/sh\n# run tests\nexit 0\n", encoding="utf-8")
            inventory = scan_existing_tools(root, FORGE_ROOT)
            by_path = {item["path"]: item for item in inventory["candidates"]}
            self.assertNotIn("admin.php", by_path)
            if "app/bootstrap.php" in by_path:
                self.assertEqual(by_path["app/bootstrap.php"]["classification"], "retain")
            self.assertEqual(by_path["tools/run_all_checks.sh"]["classification"], "absorb")
            self.assertTrue(all(item["classification"] == item["recommendation"] for item in inventory["candidates"]))

    def test_absorbed_nonconventional_test_command_satisfies_test_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo 'ok';\n", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "smoke.php").write_text("<?php // phpunit test runner assertions\nexit(0);\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "balanced", "existing_tools": "absorb", "versioning": "none"})
            config = load_config(root)
            self.assertTrue(any(item.get("test_entry_point") for group in config["commands"].values() for item in group))
            audit = run_audit(root, FORGE_ROOT, config, use_baseline=False)
            self.assertNotIn("quality.tests", {item["check_id"] for item in audit["findings"]})

    def test_init_writes_separate_layer_bootstrap_and_host_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            prompt = (root / ".forge" / "AI-BOOTSTRAP-PROMPT.md").read_text(encoding="utf-8")
            self.assertIn("Do not merge", prompt)
            isolation = json.loads((root / ".forge" / "HOST-SCANNER-EXCLUSIONS.json").read_text(encoding="utf-8"))
            self.assertEqual(isolation["mode"], "host")
            self.assertIn(".forge", isolation["forge_paths"])


class ForgeContinuityTests(unittest.TestCase):
    def test_doctor_reports_environment_and_layout_without_repairing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={
                "preset": "prototype", "versioning": "none",
                "required_executables": ["definitely-not-a-real-forge-runtime"],
                "required_env": ["FORGE_MISSING_TEST_ENV"],
                "expected_layout": ["../Planning"],
            })
            payload = run_doctor(root, FORGE_ROOT, load_config(root), write=True)
            self.assertEqual(payload["status"], "FAIL")
            self.assertFalse(payload["automatic_repairs_performed"])
            self.assertTrue(any("layout mismatch" in item for item in payload["problems"]))

    def test_brief_reports_objective_and_last_green_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none", "next_action": "Build the scheduling view"})
            result = subprocess.run([sys.executable, str(FORGE_ROOT / "forge.py"), "check", str(root), "--profile", "quick"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(result.returncode, 0, result.stdout)
            payload = build_brief(root, FORGE_ROOT, load_config(root), write=True)
            self.assertEqual(payload["objective"]["text"], "Build the scheduling view")
            self.assertEqual(payload["last_green"]["profile"], "quick")
            self.assertTrue((root / ".forge" / "brief" / "brief.md").is_file())

    def test_portable_state_exports_validates_and_adopts_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as other_directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, name="State Fixture", setup_answers={"preset": "prototype", "versioning": "none"})
            exported = export_state(root, load_config(root))
            self.assertEqual(exported["status"], "PASS", exported)
            archive = Path(exported["output"])
            self.assertEqual(inspect_state(archive)["status"], "PASS")
            other = Path(other_directory)
            (other / "index.html").write_text("ok", encoding="utf-8")
            adopted = adopt_state(other, archive, force=True)
            self.assertEqual(adopted["status"], "PASS")
            self.assertTrue((other / ".emotivus-forge.json").is_file())


class ForgeArtifactHygieneTests(unittest.TestCase):
    def test_zero_byte_and_hostile_filename_block_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            (root / '"').write_bytes(b"")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            payload = build_package(root, FORGE_ROOT, load_config(root), dry_run=True)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("filename" in item for item in payload["problems"]))
            self.assertTrue(any("zero-byte" in item for item in payload["problems"]))

    def test_declared_empty_placeholder_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            (root / ".gitkeep").write_bytes(b"")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            payload = build_package(root, FORGE_ROOT, load_config(root), dry_run=True)
            self.assertEqual(payload["status"], "PASS", payload["problems"])

    def test_case_insensitive_path_collision_blocks_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Readme.txt").write_text("one", encoding="utf-8")
            (root / "README.txt").write_text("two", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            payload = build_package(root, FORGE_ROOT, load_config(root), dry_run=True)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("cross-platform path collision" in item for item in payload["problems"]))

    def test_unicode_normalization_path_collision_blocks_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "caf\u00e9.txt").write_text("one", encoding="utf-8")
            (root / "cafe\u0301.txt").write_text("two", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            payload = build_package(root, FORGE_ROOT, load_config(root), dry_run=True)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("cross-platform path collision" in item for item in payload["problems"]))


class ForgeEvidenceAndGuardrailTests(unittest.TestCase):
    def _project(self, root: Path) -> dict:
        (root / "index.html").write_text("ok\n", encoding="utf-8")
        initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
        return load_config(root)

    def test_required_marker_protocol_rejects_missing_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            script = root / "check.py"
            script.write_text("print('ran but emitted no protocol')\n", encoding="utf-8")
            config["commands"]["quick"] = [{
                "id": "fixture.marker-required",
                "command": [sys.executable, str(script)],
                "evidence": {"protocol": "markers", "required": True, "required_fields": ["status"]},
            }]
            save_config(root, config)
            payload = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            result = next(item for item in payload["results"] if item["check_id"] == "fixture.marker-required")
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(payload["status_counts"]["ERROR"], 1)
            self.assertTrue(result["failure_bundle"]["json"])

    def test_runner_records_surface_attestations_and_bound_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            script = root / "observe.py"
            artifact = root / ".forge" / "runtime" / "target.json"
            script.write_text(
                "from pathlib import Path\n"
                f"path = Path({str(artifact)!r})\n"
                "path.parent.mkdir(parents=True, exist_ok=True)\n"
                "path.write_text('{\"status\": \"PASS\"}', encoding='utf-8')\n"
                "print('FORGE_SURFACE: index.html')\n",
                encoding="utf-8",
            )
            config["commands"]["quick"] = [{
                "id": "fixture.observe",
                "command": [sys.executable, str(script)],
                "evidence": {
                    "types": ["entrypoint-execution", "target-environment"],
                    "surfaces": ["index.html"],
                    "artifacts": [".forge/runtime/target.json"],
                },
            }]
            save_config(root, config)
            payload = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            result = next(item for item in payload["results"] if item["check_id"] == "fixture.observe")
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(result["evidence"]["surfaces"], ["index.html"])
            recorded = result["evidence"]["artifacts"][0]
            self.assertEqual(recorded["path"], ".forge/runtime/target.json")
            self.assertEqual(recorded["sha256"], sha256_file(artifact))

    def test_required_evidence_artifact_missing_turns_pass_into_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            script = root / "observe.py"
            script.write_text("print('FORGE_SURFACE: index.html')\n", encoding="utf-8")
            config["commands"]["quick"] = [{
                "id": "fixture.missing-artifact",
                "command": [sys.executable, str(script)],
                "evidence": {"artifacts": [".forge/runtime/missing.json"]},
            }]
            save_config(root, config)
            payload = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            result = next(item for item in payload["results"] if item["check_id"] == "fixture.missing-artifact")
            self.assertEqual(result["status"], "ERROR")
            self.assertTrue(any("declared evidence artifact was not produced" in item for item in result["evidence"]["problems"]))

    def test_skip_is_distinct_and_requires_explicit_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            script = root / "skip.py"
            script.write_text("print('FORGE_STATUS: SKIP')\nprint('FORGE_SKIPS: 1')\n", encoding="utf-8")
            command = {
                "id": "fixture.skip",
                "command": [sys.executable, str(script)],
                "evidence": {"protocol": "markers", "required": True, "required_fields": ["status", "skips"]},
            }
            config["commands"]["quick"] = [command]
            save_config(root, config)
            blocked = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            result = next(item for item in blocked["results"] if item["check_id"] == "fixture.skip")
            self.assertEqual(result["status"], "SKIP")
            self.assertEqual(blocked["status"], "FAIL")
            command["evidence"]["allow_skip"] = True
            save_config(root, config)
            allowed = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            self.assertEqual(allowed["status"], "PASS")
            self.assertEqual(allowed["status_counts"]["SKIP"], 1)

    def test_result_matrix_records_not_run_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            fail = root / "fail.py"
            later = root / "later.py"
            fail.write_text("raise SystemExit(1)\n", encoding="utf-8")
            later.write_text("print('should not run')\n", encoding="utf-8")
            config["commands"]["quick"] = [
                {"id": "fixture.fail", "command": [sys.executable, str(fail)]},
                {"id": "fixture.later", "command": [sys.executable, str(later)]},
            ]
            save_config(root, config)
            payload = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            matrix = {item["check_id"]: item["status"] for item in payload["result_matrix"]}
            self.assertEqual(matrix["fixture.fail"], "FAIL")
            self.assertEqual(matrix["fixture.later"], "NOT_RUN")
            self.assertEqual(payload["status_counts"]["NOT_RUN"], 1)

    def test_expected_layout_fails_before_absorbed_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            marker = root / "executed.txt"
            command = root / "command.py"
            command.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n", encoding="utf-8")
            config["environment"]["expected_layout"] = [{"path": "../Planning", "kind": "directory", "required": True}]
            config["commands"]["quick"] = [{"id": "fixture.command", "command": [sys.executable, str(command)]}]
            save_config(root, config)
            payload = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["result_matrix"][1]["check_id"], "environment.preflight")
            self.assertEqual(payload["result_matrix"][1]["status"], "FAIL")
            self.assertFalse(marker.exists())

    def test_failure_bundle_lists_changes_since_last_green(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            script = root / "quality.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            config["commands"]["quick"] = [{"id": "fixture.quality", "command": [sys.executable, str(script)]}]
            save_config(root, config)
            green = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            self.assertEqual(green["status"], "PASS")
            script.write_text("raise SystemExit(1)\n", encoding="utf-8")
            failed = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            result = next(item for item in failed["results"] if item["check_id"] == "fixture.quality")
            context = json.loads(Path(result["failure_bundle"]["json"]).read_text(encoding="utf-8"))
            self.assertIn("quality.py", context["changes_since_last_green"]["modified"])
            self.assertIn("interpretation_boundary", context)

    def test_execution_evidence_anomaly_blocks_until_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            script = root / "measured.py"
            script.write_text(
                "print('FORGE_STATUS: PASS')\nprint('FORGE_ASSERTIONS: 10')\nprint('FORGE_MIGRATIONS: 0')\nprint('FORGE_SKIPS: 0')\n",
                encoding="utf-8",
            )
            raw = {
                "id": "fixture.measured",
                "command": [sys.executable, str(script)],
                "evidence": {"protocol": "markers", "required": True, "required_fields": ["status", "assertions", "migrations", "skips"]},
            }
            config["commands"]["quick"] = [raw]
            save_config(root, config)
            check = Check(raw["id"], "command:quick", 300, tuple(raw["command"]), evidence_spec=raw["evidence"])
            historical_evidence = {
                "complete": True, "allow_skip": False,
                "counts": {"assertions": 100, "migrations": 5, "skips": 0, "executed": 1},
            }
            for duration in (10.0, 10.2, 9.8):
                record_execution(root, config, check_id=check.check_id, command_hash=check.command_hash, command=list(check.command), duration_seconds=duration, status="PASS", evidence=historical_evidence, graph_nodes=0)
            blocked = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            result = next(item for item in blocked["results"] if item["check_id"] == raw["id"])
            self.assertEqual(result["status"], "ERROR")
            self.assertTrue(result["anomaly"]["requires_override"])
            self.assertTrue(result["anomaly"]["evidence_deltas"])
            allowed = run_profile(root, FORGE_ROOT, config, "quick", fresh=True, allow_anomaly=[raw["id"]])
            result = next(item for item in allowed["results"] if item["check_id"] == raw["id"])
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["anomaly"]["override"]["accepted"])

    def test_guardrail_proposal_is_reviewed_before_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            event = root / "guardrail-event.json"
            event.write_text(json.dumps({
                "type": "zero-byte-file",
                "path": "stray-file",
                "symptom": "A zero-byte artifact entered a prior package.",
                "root_cause": "A packaging step created an unintended file.",
                "resolution": "The stray artifact was removed.",
            }), encoding="utf-8")
            proposed = guardrail_action(root, FORGE_ROOT, config, action="propose", input_path=event)
            proposal_id = proposed["proposal"]["id"]
            self.assertEqual(proposed["activation"], "inactive-until-approved")
            (root / "stray-file").write_bytes(b"")
            before = run_audit(root, FORGE_ROOT, config, use_baseline=False)
            self.assertNotIn(f"learn.contract.{proposal_id}", {item["check_id"] for item in before["findings"]})
            guardrail_action(root, FORGE_ROOT, config, action="approve", proposal_id=proposal_id)
            after = run_audit(root, FORGE_ROOT, config, use_baseline=False)
            self.assertIn(f"learn.contract.{proposal_id}", {item["check_id"] for item in after["findings"]})


class ForgeMaintenanceAndDistributionTests(unittest.TestCase):
    def _config(self, root: Path) -> dict:
        (root / "index.html").write_text("<!doctype html><title>Fixture</title>\n", encoding="utf-8")
        initialize_project(root, FORGE_ROOT, name="Fixture", setup_answers={"preset": "prototype", "deployment": "static", "versioning": "none"})
        return load_config(root)

    def _fake_forge(self, root: Path, version: str, *, pass_checks: bool = True) -> Path:
        forge = root / "Emotivus-Forge"
        (forge / "tools").mkdir(parents=True)
        (forge / "policy-packs").mkdir()
        (forge / "FORGE-MANIFEST.json").write_text(json.dumps({"forge_schema": 1, "version": version}), encoding="utf-8")
        result = 0 if pass_checks else 1
        (forge / "forge.py").write_text(
            "import sys\n"
            f"raise SystemExit({result} if len(sys.argv) > 1 and sys.argv[1] == 'self-test' else 0)\n",
            encoding="utf-8",
        )
        (forge / "tools" / "forge_bootstrap.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        return forge

    def _archive_forge(self, forge: Path, output: Path) -> None:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(forge.rglob("*")):
                if path.is_file():
                    archive.write(path, f"Emotivus-Forge/{path.relative_to(forge).as_posix()}")

    def test_schema_one_config_migrates_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            config["schema"] = 1
            config.pop("maintenance", None)
            (root / ".emotivus-forge.json").write_text(json.dumps(config), encoding="utf-8")
            migrated, migrations, backup = migrate_config_file(root, write=True)
            self.assertEqual(migrated["schema"], CURRENT_CONFIG_SCHEMA)
            self.assertEqual(migrations[0]["id"], "maintenance-and-distribution")
            self.assertTrue(Path(backup).is_file())
            self.assertIn("delivery", migrated["maintenance"])

    def test_doctor_repair_requires_confirmation_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            config["environment"]["expected_layout"] = [{
                "path": "Planning", "kind": "directory", "required": True,
                "repair": {"type": "create-directory", "reason": "Restore planning root"},
            }]
            save_config(root, config)
            proposals = remediation_action(root, FORGE_ROOT, config, action="propose")
            proposal_id = proposals["proposals"][0]["id"]
            with self.assertRaises(RuntimeError):
                remediation_action(root, FORGE_ROOT, config, action="apply", proposal_id=proposal_id)
            applied = remediation_action(root, FORGE_ROOT, config, action="apply", proposal_id=proposal_id, confirmed=True)
            self.assertEqual(applied["status"], "PASS")
            self.assertTrue((root / "Planning").is_dir())
            rolled = remediation_action(root, FORGE_ROOT, config, action="rollback", transaction_id=applied["transaction_id"])
            self.assertEqual(rolled["status"], "PASS")
            self.assertFalse((root / "Planning").exists())

    def test_ci_bridge_previews_and_backs_up_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            preview = ci_action(root, config, action="preview", provider="github")
            self.assertEqual(preview["files"][0]["action"], "create")
            written = ci_action(root, config, action="write", provider="github")
            self.assertIn(".github/workflows/emotivus-forge.yml", written["written"])
            target = root / ".github" / "workflows" / "emotivus-forge.yml"
            target.write_text("custom workflow\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                ci_action(root, config, action="write", provider="github")
            forced = ci_action(root, config, action="write", provider="github", force=True)
            self.assertTrue(forced["backups"])
            self.assertIn("Forge Section Gate", target.read_text(encoding="utf-8"))

    def test_internal_delivery_pairs_source_and_forge_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            installed = root / "Emotivus-Forge"
            installed.mkdir()
            (installed / "forge.py").write_text("print('forge')\n", encoding="utf-8")
            (root / "Planning").mkdir()
            (root / "Planning" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
            output = root / "internal.zip"
            result = build_internal_delivery(root, installed, config, output=output)
            self.assertEqual(result["status"], "PASS")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {"Project-Source.zip", "Forge-State.zip", "FORGE-INTERNAL-DELIVERY-MANIFEST.json", "README-FIRST.txt"})
                source_bytes = archive.read("Project-Source.zip")
            nested = root / "source.zip"
            nested.write_bytes(source_bytes)
            with zipfile.ZipFile(nested) as source:
                names = source.namelist()
                self.assertTrue(any(name.endswith("/Emotivus-Forge/forge.py") for name in names))
                self.assertFalse(any("/.forge/" in name for name in names))
                self.assertTrue(any(name.endswith("/Planning/ROADMAP.md") for name in names))

    def test_update_preserves_private_pack_and_rolls_back_failed_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = self._fake_forge(root, "1.0.5")
            (current / "policy-packs" / "private.json").write_text("{}\n", encoding="utf-8")
            detection = detect_project(root, current)
            config = default_config("Fixture", detection)
            save_config(root, config)
            incoming_root = root / "incoming-source"
            incoming = self._fake_forge(incoming_root, "1.0.6", pass_checks=True)
            archive = root / "incoming.zip"
            self._archive_forge(incoming, archive)
            preview = preview_update(root, current, config, archive)
            self.assertEqual(preview["incoming_version"], "1.0.6")
            applied = apply_update(root, current, config, archive, post_profile="quick")
            self.assertEqual(applied["status"], "PASS")
            self.assertTrue((current / "policy-packs" / "private.json").is_file())
            self.assertEqual(json.loads((current / "FORGE-MANIFEST.json").read_text())["version"], "1.0.6")
            rolled = rollback_update(root, current, transaction_id=applied["transaction_id"])
            self.assertEqual(rolled["status"], "PASS")
            self.assertEqual(json.loads((current / "FORGE-MANIFEST.json").read_text())["version"], "1.0.5")

    def test_update_automatically_restores_previous_installation_when_checks_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = self._fake_forge(root, "1.0.5")
            config = default_config("Fixture", detect_project(root, current))
            save_config(root, config)
            incoming = self._fake_forge(root / "bad-source", "1.0.6", pass_checks=False)
            archive = root / "bad.zip"
            self._archive_forge(incoming, archive)
            result = apply_update(root, current, config, archive, post_profile="quick")
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["action"], "rolled-back")
            self.assertEqual(json.loads((current / "FORGE-MANIFEST.json").read_text())["version"], "1.0.5")


class ForgeProjectIntelligenceTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict:
        (root / "app.py").write_text("__version__ = '0.2.0'\nprint('ok')\n", encoding="utf-8")
        (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        initialize_project(root, FORGE_ROOT, name="Project Intelligence", setup_answers={"preset": "prototype"})
        return load_config(root)

    def test_initialization_creates_one_project_memory_layer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            self.assertEqual(config["schema"], CURRENT_CONFIG_SCHEMA)
            self.assertEqual(CURRENT_CONFIG_SCHEMA, 10)
            self.assertTrue((root / ".forge" / "project" / "plans.json").is_file())
            self.assertTrue((root / ".forge" / "project" / "ledger.json").is_file())
            self.assertTrue((root / ".forge" / "project" / "pivots.json").is_file())

    def test_public_help_is_consolidated_and_advanced_aliases_still_work(self) -> None:
        help_result = subprocess.run(
            [sys.executable, str(FORGE_ROOT / "forge.py"), "--help"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stdout)
        for command in ("help", "adopt", "resume", "check", "ship"):
            self.assertIn(command, help_result.stdout)
        for hidden in ("understand", "change", "prove", "update", "docs", "start", "project", "verify", "deliver", "maintain", "mirror"):
            self.assertNotRegex(help_result.stdout, rf"^\s+{hidden}\s", msg=help_result.stdout)
        self.assertNotIn("==SUPPRESS==", help_result.stdout)

        advanced = subprocess.run(
            [sys.executable, str(FORGE_ROOT / "forge.py"), "help", "advanced"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(advanced.returncode, 0, advanced.stdout)
        self.assertIn("Project diagnostics", advanced.stdout)
        self.assertIn("Assurance diagnostics", advanced.stdout)

        for core in ("understand", "change", "prove"):
            result = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), core, "--help"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            legacy = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "init", str(root), "--preset", "prototype"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(legacy.returncode, 0, legacy.stdout)

    def test_plan_ledger_and_compact_context_share_canonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            plan_input = root / "plan.json"
            plan_input.write_text(json.dumps({
                "title": "Improve greeting",
                "objective": "Change greeting behavior without adding a framework.",
                "expected_files": ["app.py"],
                "completion_criteria": ["Greeting remains deterministic"],
                "tests": ["quick gate"],
                "quality_targets": {"security": "preserve", "user_experience": "improve"},
                "standards_refs": ["LEDGER-ACCESSIBILITY", "LEDGER-SECURITY"],
            }), encoding="utf-8")
            created = plan_action(root, FORGE_ROOT, config, action="create", input_path=plan_input)
            plan_id = created["plan"]["id"]
            plan_action(root, FORGE_ROOT, config, action="activate", item_id=plan_id)
            record_input = root / "record.json"
            record_input.write_text(json.dumps({
                "type": "decision", "title": "Remain framework neutral",
                "summary": "Do not add a framework until one is required.", "applies_to": ["app.py"],
            }), encoding="utf-8")
            ledger_action(root, config, action="add", input_path=record_input)
            packet = build_context_packet(root, FORGE_ROOT, config, mode="task", budget="compact", plan_id=plan_id)
            self.assertEqual(packet["active_plan"]["id"], plan_id)
            self.assertEqual(packet["active_plan"]["quality_targets"]["security"], "preserve")
            self.assertEqual(packet["active_plan"]["quality_targets"]["user_experience"], "improve")
            self.assertIn("performance", packet["active_plan"]["quality_targets"])
            self.assertEqual(packet["active_plan"]["standards_refs"], ["LEDGER-ACCESSIBILITY", "LEDGER-SECURITY"])
            self.assertEqual(len(packet["records"]), 1)
            self.assertTrue(packet["within_budget"])
            self.assertLessEqual(packet["estimated_tokens"], packet["token_limit"])
            self.assertTrue(Path(packet["output"]).is_file())

    def test_artifact_acceptance_requires_canonical_source_of_truth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            input_path = root / "artifact.json"
            input_path.write_text(json.dumps({
                "type": "artifact", "title": "Detached session plan", "summary": "A reviewed session upload.",
                "status": "accepted"
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                ledger_action(root, config, action="add", input_path=input_path)
            input_path.write_text(json.dumps({
                "type": "artifact", "title": "Archived session plan", "summary": "A reviewed session upload.",
                "status": "accepted", "canonical_ref": "Planning/ACTIVE.md"
            }), encoding="utf-8")
            result = ledger_action(root, config, action="add", input_path=input_path)
            self.assertEqual(result["entry"]["canonical_ref"], "Planning/ACTIVE.md")

    def test_pivot_requires_classification_and_replacement_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            contracts_path = root / config["learn"]["contracts_path"]
            contracts_path.write_text(json.dumps({"schema": 1, "contracts": [{
                "id": "C-PLAYER", "title": "Player input", "invariant": "Player input remains configurable.",
                "active": True, "status": "active", "category": "behavior", "affected_paths": ["app.py"],
                "severity": "error", "regression": {"kind": "manual"}
            }]}), encoding="utf-8")
            pivot_input = root / "pivot.json"
            pivot_input.write_text(json.dumps({
                "title": "Replace application architecture", "objective": "Replace the current runtime while preserving player input.",
                "changed_paths": ["app.py"], "enduring_obligations": ["Configurable player input"]
            }), encoding="utf-8")
            created = pivot_action(root, FORGE_ROOT, config, action="create", input_path=pivot_input)
            pivot_id = created["pivot"]["id"]
            assessed = pivot_action(root, FORGE_ROOT, config, action="assess", item_id=pivot_id)
            self.assertEqual(assessed["pivot"]["contract_dispositions"]["C-PLAYER"], "review")
            with self.assertRaises(RuntimeError):
                pivot_action(root, FORGE_ROOT, config, action="activate", item_id=pivot_id)
            contracts = json.loads(contracts_path.read_text(encoding="utf-8"))
            contracts["contracts"].append({
                "id": "C-PLAYER-NEXT", "title": "Replacement player input", "invariant": "New player input remains configurable.",
                "active": True, "status": "active", "category": "behavior", "affected_paths": ["new-runtime.py"],
                "severity": "error", "regression": {"kind": "manual"}
            })
            contracts_path.write_text(json.dumps(contracts), encoding="utf-8")
            classification = root / "classification.json"
            classification.write_text(json.dumps({"contracts": {"C-PLAYER": {
                "disposition": "replace", "reason": "Old runtime is being retired", "successor": "C-PLAYER-NEXT"
            }}}), encoding="utf-8")
            pivot_action(root, FORGE_ROOT, config, action="classify", item_id=pivot_id, input_path=classification)
            active = pivot_action(root, FORGE_ROOT, config, action="activate", item_id=pivot_id)
            self.assertEqual(active["project_mode"], "exploration")
            self.assertTrue(active["pivot"]["checkpoint"]["source_tree_fingerprint"])
            self.assertTrue(validate_project_release(root, config))
            with self.assertRaises(RuntimeError):
                pivot_action(root, FORGE_ROOT, config, action="complete", item_id=pivot_id)
            all_quality = {name: [f"manual:{name}-verified"] for name in (
                "security", "reliability", "performance", "efficiency", "accessibility",
                "user_experience", "maintainability", "compatibility", "privacy",
            )}
            classification.write_text(json.dumps({
                "replacement_evidence": {"C-PLAYER": ["manual:player-input-verified"]},
                "quality_evidence": all_quality,
            }), encoding="utf-8")
            pivot_action(root, FORGE_ROOT, config, action="classify", item_id=pivot_id, input_path=classification)
            for target in ("transition", "development", "release"):
                pivot_action(root, FORGE_ROOT, config, action="mode", item_id=pivot_id, mode=target)
            reports = root / config["paths"]["reports"]
            reports.mkdir(parents=True, exist_ok=True)
            (reports / "release.json").write_text(json.dumps({"status": "PASS", "tree_fingerprint": ""}), encoding="utf-8")
            complete = pivot_action(root, FORGE_ROOT, config, action="complete", item_id=pivot_id, reason="Replacement verified")
            self.assertEqual(complete["project_mode"], "development")
            updated_contracts = json.loads(contracts_path.read_text(encoding="utf-8"))["contracts"]
            old = next(item for item in updated_contracts if item["id"] == "C-PLAYER")
            self.assertEqual(old["status"], "superseded")
            self.assertEqual(old["superseded_by"], "C-PLAYER-NEXT")
            self.assertEqual(validate_project_release(root, config), [])

    def test_portable_state_includes_project_memory_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            build_context_packet(root, FORGE_ROOT, config, mode="cold", budget="compact")
            output = root / "Forge-State.zip"
            result = export_state(root, config, output)
            self.assertEqual(result["status"], "PASS", result)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn(".forge/project/plans.json", names)
                self.assertIn(".forge/project/ledger.json", names)
                self.assertIn(".forge/project/pivots.json", names)
                self.assertIn(".forge/context/latest-cold.json", names)

    def test_active_exploration_pivot_blocks_release_not_development(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            pivot_input = root / "pivot.json"
            pivot_input.write_text(json.dumps({
                "title": "Engine rewrite", "objective": "Replace the engine without freezing experimentation.",
                "changed_paths": ["app.py"],
            }), encoding="utf-8")
            pivot_id = pivot_action(root, FORGE_ROOT, config, action="create", input_path=pivot_input)["pivot"]["id"]
            pivot_action(root, FORGE_ROOT, config, action="assess", item_id=pivot_id)
            pivot_action(root, FORGE_ROOT, config, action="activate", item_id=pivot_id)
            self.assertTrue(any("exploration mode" in item for item in validate_project_release(root, config)))
            quick = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            self.assertEqual(quick["status"], "PASS", quick)

    def test_three_core_commands_route_to_real_internal_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            start = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "understand", "start", str(root), "--preset", "prototype"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(start.returncode, 0, start.stdout)
            brief = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "understand", "brief", str(root)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(brief.returncode, 0, brief.stdout)
            gate = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "prove", "gate", str(root), "--level", "quick", "--fresh"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(gate.returncode, 0, gate.stdout)
            evidence = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "prove", "evidence", str(root)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(evidence.returncode, 0, evidence.stdout)
            payload = json.loads(evidence.stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertTrue(any(item["id"] == "gate:quick" for item in payload["gates"]))

    def test_release_gate_contains_project_truth_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            config["versioning"]["status"] = "release"
            config["versioning"]["baseline_version"] = "0.1.0"
            config["versioning"]["target_version"] = "0.2.0"
            config["versioning"]["package_version"] = "0.2.0"
            config["project_memory"]["traceability"]["release_requires_active_plan"] = True
            save_config(root, config)
            result = run_profile(root, FORGE_ROOT, load_config(root), "release", fresh=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["results"][0]["check_id"], "core.audit")
            self.assertIn("project.active-plan-required", result["results"][0]["output"])



if __name__ == "__main__":
    unittest.main(verbosity=2)


class ForgeProvenanceAndScopeTests(unittest.TestCase):
    def test_classifies_deployment_package_and_complete_development_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "DEPLOY-MANIFEST.txt").write_text("index.php sha256=abc\n", encoding="utf-8")
            (root / "index.php").write_text("<?php echo 'ok';", encoding="utf-8")
            deployment = classify_workspace(root, FORGE_ROOT)
            self.assertEqual(deployment["classification"], "deployment-package")
            self.assertIn("full-development", deployment["restricted_activities"])
            for name in ("Planning", "Release", "tests", "tools"):
                (root / name).mkdir()
            development = classify_workspace(root, FORGE_ROOT)
            self.assertEqual(development["classification"], "development-source")
            (root / "DEPLOY-MANIFEST.txt").unlink()
            development = classify_workspace(root, FORGE_ROOT)
            self.assertEqual(development["classification"], "development-source")

    def test_runtime_requirements_are_inferred_from_canonical_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "composer.json").write_text(json.dumps({"config": {"platform": {"php": "8.4.2"}}}), encoding="utf-8")
            (root / "package.json").write_text(json.dumps({"engines": {"node": ">=22"}}), encoding="utf-8")
            (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n', encoding="utf-8")
            result = infer_runtime_requirements(root)
            self.assertEqual(result["php"]["expected"], "8.4")
            self.assertEqual(result["node"]["expected"], "22.0")
            self.assertEqual(result["python"]["expected"], "3.12")

    def test_acceptance_scope_blocks_development_plan_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Planning").mkdir()
            (root / "Planning" / "ACTIVE-BUILD-PROMPT.md").write_text("The source implementation is complete. There is no additional approved coding scope. Continue staging acceptance only.", encoding="utf-8")
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            self.assertEqual(config["work"]["mode"], "acceptance")
            self.assertFalse(config["work"]["coding_allowed"])
            plan_input = root / "plan.json"
            plan_input.write_text(json.dumps({"title": "Add feature", "objective": "Add unapproved feature", "work_type": "development"}), encoding="utf-8")
            created = plan_action(root, FORGE_ROOT, config, action="create", input_path=plan_input)
            with self.assertRaises(RuntimeError):
                plan_action(root, FORGE_ROOT, config, action="activate", item_id=created["plan"]["id"])

    def test_packaging_policy_contradiction_detects_prior_manifest_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".deployignore").write_text("docs/\n", encoding="utf-8")
            (root / "DEPLOY-MANIFEST.txt").write_text("docs/ARCHITECTURE.md | abc | 10\n", encoding="utf-8")
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            problems = packaging_policy_contradictions(root, config)
            self.assertTrue(any(item["rule"] == "docs/" for item in problems))

    def test_initialization_records_identity_provenance_and_portable_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            payload = initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            self.assertTrue(config["project"]["identity"])
            self.assertEqual(config["schema"], CURRENT_CONFIG_SCHEMA)
            self.assertIn("workspace_classification", payload)
            self.assertTrue((root / ".forge" / "provenance" / "development-source-manifest.json").is_file())
            brief = (root / ".forge" / "brief" / "brief.md").read_text(encoding="utf-8")
            self.assertIn("python3 Emotivus-Forge/forge.py resume . --budget compact", brief)
            self.assertIn("python3 Emotivus-Forge/forge.py check . --profile quick", brief)
            self.assertNotIn("understand doctor", brief)
            self.assertNotIn(str(root), brief)

    def test_graph_records_subsystem_confidence_and_accepts_corrections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "features").mkdir()
            (root / "features" / "accounts.php").write_text("<?php function login_user() {}", encoding="utf-8")
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            config["graph"]["classification"]["corrections"] = {"features": "gameplay"}
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            node = next(item for item in graph["nodes"] if item.get("path") == "features/accounts.php")
            self.assertEqual(node["subsystem"], "gameplay")
            self.assertEqual(node["metadata"]["subsystem_confidence"], 1.0)

    def test_host_command_coverage_avoids_duplicate_group_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            command = [sys.executable, "-c", "print('FORGE_STATUS: PASS')"]
            config["commands"]["quick"] = [{"id": "host.full", "command": command, "covers_groups": ["section"], "evidence": {"protocol": "markers", "required": True, "required_fields": ["status"]}}]
            config["commands"]["section"] = [{"id": "host.section", "command": command}]
            save_config(root, config)
            from emotivus_forge.runner import build_plan
            checks = build_plan(root, FORGE_ROOT, config, "section")
            ids = [item.check_id for item in checks]
            self.assertIn("host.full", ids)
            self.assertNotIn("host.section", ids)


    def test_portable_state_rejects_different_project_identity(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir)
            second = Path(second_dir)
            (first / "index.html").write_text("one", encoding="utf-8")
            (second / "index.html").write_text("two", encoding="utf-8")
            initialize_project(first, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            initialize_project(second, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            state = export_state(first, load_config(first), first / "Forge-State.zip")
            self.assertEqual(state["status"], "PASS")
            with self.assertRaises(RuntimeError):
                adopt_state(second, first / "Forge-State.zip")

    def test_first_failure_bundle_explains_initial_tree_without_prior_green(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            config["commands"]["quick"] = [{"id": "forced.failure", "command": [sys.executable, "-c", "raise SystemExit(1)"]}]
            save_config(root, config)
            result = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            failure = next(item for item in result["results"] if item["check_id"] == "forced.failure")
            context = json.loads(Path(failure["failure_bundle"]["json"]).read_text(encoding="utf-8"))
            self.assertFalse(context["last_green"]["exists"])
            self.assertIn("No prior green run", context["last_green"]["note"])

    def test_deployment_manifest_labels_evidence_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            result = build_package(root, FORGE_ROOT, config, dry_run=True)
            self.assertEqual(result["manifest"]["evidence_boundary"], "deployment-package")
            self.assertEqual(result["manifest"]["project_identity"], config["project"]["identity"])

    def test_all_generated_guidance_uses_canonical_portable_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            packet = build_context_packet(root, FORGE_ROOT, config, mode="cold", budget="compact", write=True)
            markdown_guidance = "\n".join([
                (root / ".forge" / "INITIAL-RUN-PLAN.md").read_text(encoding="utf-8"),
                (root / ".forge" / "INITIALIZATION-SUMMARY.md").read_text(encoding="utf-8"),
                (root / ".forge" / "AI-BOOTSTRAP-PROMPT.md").read_text(encoding="utf-8"),
            ])
            retrieval_guidance = json.dumps(packet.get("retrieval", {}))
            guidance = markdown_guidance + "\n" + retrieval_guidance
            self.assertIn("forge.py adopt .", guidance)
            self.assertIn("forge.py resume . --budget compact", guidance)
            self.assertIn("forge.py check . --profile quick --fresh", guidance)
            self.assertIn("forge.py ship .", guidance)
            self.assertNotIn("forge.py understand ", guidance)
            self.assertNotIn("forge.py change ", guidance)
            self.assertNotIn("forge.py prove ", guidance)
            self.assertNotIn("project status", guidance)
            self.assertNotIn(str(root), guidance)
            self.assertIn(str(root), str(packet.get("output", "")))


class ForgeControlledChangeTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict:
        (root / "app.py").write_text("print('v1')\n", encoding="utf-8")
        (root / "README.md").write_text("# Pivot Fixture\n", encoding="utf-8")
        initialize_project(root, FORGE_ROOT, name="Controlled Change", setup_answers={"preset": "prototype", "versioning": "none"})
        return load_config(root)

    def test_schema_four_migrates_to_controlled_change_schema(self) -> None:
        detection = detect_project(Path(tempfile.mkdtemp()), FORGE_ROOT)
        config = default_config("Migration", detection)
        config["schema"] = 4
        config["project_memory"].pop("pivot", None)
        config["project_memory"]["traceability"].pop("release_requires_quality_coverage", None)
        migrated, records = migrate_config_data(config)
        self.assertEqual(migrated["schema"], CURRENT_CONFIG_SCHEMA)
        self.assertTrue(migrated["project_memory"]["pivot"]["require_release_gate_on_complete"])
        self.assertTrue(migrated["project_memory"]["traceability"]["release_requires_quality_coverage"])
        self.assertTrue(any(item["id"] == "controlled-change-and-pivot-lifecycle" for item in records))
        self.assertTrue(any(item["id"] == "lab-truthfulness-and-cache-hygiene" for item in records))

    def test_standard_ledger_record_requires_versioned_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            record = root / "standard.json"
            record.write_text(json.dumps({"type": "standard", "title": "Accessibility", "summary": "Use the current project accessibility standard."}), encoding="utf-8")
            with self.assertRaises(ValueError):
                ledger_action(root, config, action="add", input_path=record)
            record.write_text(json.dumps({
                "type": "standard", "title": "Accessibility", "summary": "Use the current project accessibility standard.",
                "source": "https://example.invalid/accessibility", "version": "2026.1", "authority": "Project owner",
                "scope": ["public UI"], "reviewed_utc": "2026-07-29T00:00:00+00:00"
            }), encoding="utf-8")
            added = ledger_action(root, config, action="add", input_path=record)
            self.assertEqual(added["entry"]["type"], "standard")
            self.assertEqual(added["entry"]["standard"]["version"], "2026.1")

    def test_plan_cannot_complete_until_declared_quality_evidence_is_covered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            plan_input = root / "plan.json"
            plan_input.write_text(json.dumps({
                "title": "Modernize interaction", "objective": "Improve the interaction without lowering quality.",
                "completion_criteria": ["Interaction is verified"],
                "quality_targets": {name: "verify" for name in (
                    "security", "reliability", "performance", "efficiency", "accessibility",
                    "user_experience", "maintainability", "compatibility", "privacy"
                )}
            }), encoding="utf-8")
            created = plan_action(root, FORGE_ROOT, config, action="create", input_path=plan_input)
            plan_id = created["plan"]["id"]
            plan_action(root, FORGE_ROOT, config, action="activate", item_id=plan_id)
            with self.assertRaises(RuntimeError):
                plan_action(root, FORGE_ROOT, config, action="complete", item_id=plan_id)
            update = root / "plan-update.json"
            update.write_text(json.dumps({"quality_evidence": {
                name: [f"manual:{name}-verified"] for name in (
                    "security", "reliability", "performance", "efficiency", "accessibility",
                    "user_experience", "maintainability", "compatibility", "privacy"
                )
            }}), encoding="utf-8")
            updated = plan_action(root, FORGE_ROOT, config, action="update", item_id=plan_id, input_path=update)
            self.assertEqual(updated["plan"]["quality_coverage"]["status"], "covered")
            completed = plan_action(root, FORGE_ROOT, config, action="complete", item_id=plan_id)
            self.assertEqual(completed["plan"]["status"], "complete")

    def test_pivot_separates_enduring_and_architecture_bound_obligations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            pivot_input = root / "pivot.json"
            pivot_input.write_text(json.dumps({
                "title": "2D to 3D", "objective": "Replace rendering architecture while preserving player outcomes.",
                "changed_paths": ["app.py"],
                "obligations": [
                    {"id": "OBL-CONTROLS", "title": "Controls remain configurable", "kind": "behavior", "stability": "enduring"},
                    {"id": "OBL-RENDERER", "title": "Use the 2D renderer", "kind": "architecture", "stability": "architecture-bound"}
                ]
            }), encoding="utf-8")
            pivot_id = pivot_action(root, FORGE_ROOT, config, action="create", input_path=pivot_input)["pivot"]["id"]
            assessed = pivot_action(root, FORGE_ROOT, config, action="assess", item_id=pivot_id)
            self.assertEqual(assessed["pivot"]["obligation_dispositions"]["OBL-CONTROLS"], "retain")
            self.assertEqual(assessed["pivot"]["disposition_details"]["OBL-RENDERER"]["suggested"], "retire")
            classification = root / "classification.json"
            classification.write_text(json.dumps({"obligations": {
                "OBL-RENDERER": {"disposition": "retire", "reason": "The new 3D renderer replaces the obsolete implementation."}
            }}), encoding="utf-8")
            pivot_action(root, FORGE_ROOT, config, action="classify", item_id=pivot_id, input_path=classification)
            active = pivot_action(root, FORGE_ROOT, config, action="activate", item_id=pivot_id)
            self.assertEqual(active["pivot"]["obligation_dispositions"]["OBL-CONTROLS"], "retain")
            self.assertEqual(active["pivot"]["obligation_dispositions"]["OBL-RENDERER"], "retire")

    def test_pivot_modes_require_quality_and_replacement_evidence_before_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            pivot_input = root / "pivot.json"
            pivot_input.write_text(json.dumps({"title": "Engine transition", "objective": "Move to a new engine.", "changed_paths": ["app.py"]}), encoding="utf-8")
            pivot_id = pivot_action(root, FORGE_ROOT, config, action="create", input_path=pivot_input)["pivot"]["id"]
            pivot_action(root, FORGE_ROOT, config, action="assess", item_id=pivot_id)
            pivot_action(root, FORGE_ROOT, config, action="activate", item_id=pivot_id)
            pivot_action(root, FORGE_ROOT, config, action="mode", item_id=pivot_id, mode="transition")
            pivot_action(root, FORGE_ROOT, config, action="mode", item_id=pivot_id, mode="development")
            with self.assertRaises(RuntimeError):
                pivot_action(root, FORGE_ROOT, config, action="mode", item_id=pivot_id, mode="release")
            coverage = root / "coverage.json"
            coverage.write_text(json.dumps({"quality_evidence": {
                name: [f"manual:{name}"] for name in (
                    "security", "reliability", "performance", "efficiency", "accessibility",
                    "user_experience", "maintainability", "compatibility", "privacy"
                )
            }}), encoding="utf-8")
            pivot_action(root, FORGE_ROOT, config, action="classify", item_id=pivot_id, input_path=coverage)
            released = pivot_action(root, FORGE_ROOT, config, action="mode", item_id=pivot_id, mode="release")
            self.assertEqual(released["project_mode"], "release")

    def test_pre_pivot_checkpoint_restores_assurance_state_but_not_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            original = root / "decision.json"
            original.write_text(json.dumps({"type": "decision", "title": "Original", "summary": "Original decision"}), encoding="utf-8")
            original_id = ledger_action(root, config, action="add", input_path=original)["entry"]["id"]
            pivot_input = root / "pivot.json"
            pivot_input.write_text(json.dumps({"title": "Reversible experiment", "objective": "Test a new architecture."}), encoding="utf-8")
            pivot_id = pivot_action(root, FORGE_ROOT, config, action="create", input_path=pivot_input)["pivot"]["id"]
            pivot_action(root, FORGE_ROOT, config, action="assess", item_id=pivot_id)
            classification = root / "retain-original.json"
            classification.write_text(json.dumps({"records": {original_id: "retain"}}), encoding="utf-8")
            pivot_action(root, FORGE_ROOT, config, action="classify", item_id=pivot_id, input_path=classification)
            pivot_action(root, FORGE_ROOT, config, action="activate", item_id=pivot_id)
            (root / "app.py").write_text("print('changed source')\n", encoding="utf-8")
            later = root / "later.json"
            later.write_text(json.dumps({"type": "decision", "title": "Later", "summary": "Decision created during pivot"}), encoding="utf-8")
            ledger_action(root, config, action="add", input_path=later)
            restored = pivot_action(root, FORGE_ROOT, config, action="restore", item_id=pivot_id, reason="Experiment cancelled", confirmed=True)
            entries = ledger_action(root, config, action="list")["entries"]
            self.assertEqual([item["id"] for item in entries], [original_id])
            self.assertIn("changed source", (root / "app.py").read_text(encoding="utf-8"))
            self.assertFalse(restored["pivot"]["restoration"]["source_restored"])

    def test_context_packet_exposes_pivot_mode_and_quality_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._fixture(root)
            pivot_input = root / "pivot.json"
            pivot_input.write_text(json.dumps({"title": "Context pivot", "objective": "Expose bounded pivot state."}), encoding="utf-8")
            pivot_id = pivot_action(root, FORGE_ROOT, config, action="create", input_path=pivot_input)["pivot"]["id"]
            pivot_action(root, FORGE_ROOT, config, action="assess", item_id=pivot_id)
            pivot_action(root, FORGE_ROOT, config, action="activate", item_id=pivot_id)
            packet = build_context_packet(root, FORGE_ROOT, config, mode="pivot", budget="compact", pivot_id=pivot_id)
            self.assertEqual(packet["active_pivot"]["mode"], "exploration")
            self.assertTrue(packet["active_pivot"]["transition_plan_id"])
            self.assertIn("quality_coverage", packet["active_plan"])


class ForgeLabTruthfulnessTests(unittest.TestCase):
    def _config(self, root: Path) -> dict:
        (root / "index.html").write_text("ok\n", encoding="utf-8")
        detection = detect_project(root, FORGE_ROOT)
        return default_config("Lab Fixture", detection)

    def test_status_200_error_body_cannot_satisfy_content_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("This site is not configured yet.\n", encoding="utf-8")
            config = default_config("False Green Fixture", detect_project(root, FORGE_ROOT))
            config["lab"]["recipes"] = [{
                "id": "readiness",
                "name": "Application readiness",
                "enabled": True,
                "workspace": "copy",
                "evidence_level": "content-readiness",
                "start": ["{python}", "-m", "http.server", "{port}", "--bind", "127.0.0.1", "--directory", "{workspace}"],
                "probes": [{
                    "url": "http://127.0.0.1:{port}/",
                    "expected_status": [200],
                    "expected_content_type": "text/html",
                    "contains": "Expected Product",
                    "not_contains": "This site is not configured yet.",
                    "min_bytes": 100,
                }],
                "startup_timeout": 2,
            }]
            failed = run_lab(root, FORGE_ROOT, config, "readiness")
            self.assertEqual(failed["status"], "FAIL")
            self.assertEqual(failed["evidence_level"], "content-readiness")
            assertions = failed["probe_results"][0]["assertions"]
            self.assertTrue(any(item["kind"] == "body_not_contains" and item["status"] == "FAIL" for item in assertions))
            self.assertTrue(any(item["kind"] == "body_contains" and item["status"] == "FAIL" for item in assertions))

            (root / "index.html").write_text("<html><title>Expected Product</title><body>Expected Product ready.</body></html>" + (" " * 100), encoding="utf-8")
            passed = run_lab(root, FORGE_ROOT, config, "readiness")
            self.assertEqual(passed["status"], "PASS")
            self.assertTrue(passed["probe_results"][0]["readiness_fingerprint"])

    def test_status_only_release_lab_is_too_weak_for_release_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("reachable\n", encoding="utf-8")
            config = default_config("Status Fixture", detect_project(root, FORGE_ROOT))
            config["lab"]["recipes"] = [{
                "id": "status-only",
                "name": "Status only",
                "enabled": True,
                "profiles": ["release"],
                "workspace": "copy",
                "start": ["{python}", "-m", "http.server", "{port}", "--bind", "127.0.0.1", "--directory", "{workspace}"],
                "probes": [{"url": "http://127.0.0.1:{port}/", "expected_status": [200]}],
                "startup_timeout": 3,
            }]
            ok, detail = run_required_labs(root, FORGE_ROOT, config, "release")
            self.assertFalse(ok)
            self.assertIn("evidence is too weak", detail)
            self.assertIn("connectivity-smoke", detail)

    def test_missing_lab_prerequisite_is_blocked_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            config["lab"]["recipes"] = [{
                "id": "database-backed",
                "enabled": True,
                "workspace": "copy",
                "evidence_level": "environment-backed-behavior",
                "prerequisites": {"files": ["config.php"], "env": ["FORGE_TEST_DB_URL"]},
                "probes": [],
            }]
            result = run_lab(root, FORGE_ROOT, config, "database-backed")
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(result["prerequisite_results"])
            self.assertTrue(all(item["status"] == "BLOCKED" for item in result["prerequisite_results"]))
            self.assertEqual(result["files_copied"], 0)

    def test_stateful_journey_preserves_cookie_and_captured_response_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.py").write_text(
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "import json, sys, urllib.parse\n"
                "class H(BaseHTTPRequestHandler):\n"
                "  def log_message(self, *args): pass\n"
                "  def do_GET(self):\n"
                "    parsed=urllib.parse.urlparse(self.path)\n"
                "    if parsed.path == '/start':\n"
                "      body=json.dumps({'token':'abc123','ready':True}).encode()\n"
                "      self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('X-Ready','yes'); self.send_header('Set-Cookie','forge_session=ok'); self.end_headers(); self.wfile.write(body); return\n"
                "    cookie=self.headers.get('Cookie','')\n"
                "    token=urllib.parse.parse_qs(parsed.query).get('token',[''])[0]\n"
                "    if parsed.path == '/finish' and 'forge_session=ok' in cookie and token == 'abc123':\n"
                "      body=b'journey complete'; self.send_response(200); self.send_header('Content-Type','text/plain'); self.end_headers(); self.wfile.write(body); return\n"
                "    self.send_response(403); self.end_headers(); self.wfile.write(b'blocked')\n"
                "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n",
                encoding="utf-8",
            )
            config = default_config("Journey Fixture", detect_project(root, FORGE_ROOT))
            config["lab"]["recipes"] = [{
                "id": "journey",
                "enabled": True,
                "workspace": "copy",
                "evidence_level": "stateful-behavior",
                "prerequisites": {"executables": ["python"]},
                "start": ["{python}", "{workspace}/server.py", "{port}"],
                "probes": [{"url": "http://127.0.0.1:{port}/start", "expected_status": [200], "expected_content_type": "application/json", "json_assertions": [{"path": "ready", "equals": True}]}],
                "journey": [
                    {
                        "id": "establish-session",
                        "url": "http://127.0.0.1:{port}/start",
                        "expected_status": [200],
                        "expected_content_type": "application/json",
                        "required_headers": {"X-Ready": "yes"},
                        "json_assertions": [{"path": "ready", "equals": True}],
                        "capture": {"token": {"json_path": "token"}},
                    },
                    {
                        "id": "use-session",
                        "url": "http://127.0.0.1:{port}/finish?token={state:token}",
                        "expected_status": [200],
                        "contains": "journey complete",
                    },
                ],
                "startup_timeout": 5,
            }]
            result = run_lab(root, FORGE_ROOT, config, "journey")
            self.assertEqual(result["status"], "PASS", result)
            self.assertEqual(len(result["journey_results"]), 2)
            self.assertEqual(result["journey_state_keys"], ["token"])
            self.assertEqual(result["journey_results"][1]["status"], "PASS")

    def test_default_php_recipe_is_labeled_connectivity_not_behavioral_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo 'ok';\n", encoding="utf-8")
            recipe = next(item for item in default_lab_recipes(root, ["php"]) if item["id"] == "php-smoke")
            self.assertEqual(recipe["evidence_level"], "connectivity-smoke")
            self.assertEqual(recipe["profiles"], [])

    def test_internal_delivery_prunes_runtime_cache_residue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            installed = root / "Emotivus-Forge"
            installed.mkdir()
            (installed / "forge.py").write_text("print('forge')\n", encoding="utf-8")
            cache = installed / "emotivus_forge" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "lab.cpython-313.pyc").write_bytes(b"cache")
            (installed / "loose.pyc").write_bytes(b"cache")
            output = root / "internal.zip"
            result = build_internal_delivery(root, installed, config, output=output)
            self.assertEqual(result["status"], "PASS", result)
            with zipfile.ZipFile(output) as outer:
                nested_path = root / "nested.zip"
                nested_path.write_bytes(outer.read("Project-Source.zip"))
            with zipfile.ZipFile(nested_path) as nested:
                names = nested.namelist()
                self.assertFalse(any("__pycache__" in name for name in names))
                self.assertFalse(any(name.endswith(".pyc") for name in names))


class ForgeRuntimeProofTests(unittest.TestCase):
    AUTH_CATEGORIES = [
        "allowed-access", "denied-access", "direct-access-deny", "denied-mutation",
        "csrf", "explicit-deny", "privilege-management", "session-revocation",
    ]

    def _project(self, root: Path) -> dict[str, object]:
        (root / "index.php").write_text("<?php session_start(); if (!has_permission('users.manage')) { http_response_code(403); }\n", encoding="utf-8")
        initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
        return load_config(root)

    def _auth_cases(self) -> list[dict[str, str]]:
        cases = [
            {"id": "allow-admin", "category": "allowed-access", "actor": "admin", "action": "view", "resource": "users", "expected": "ALLOW"},
            {"id": "deny-staff", "category": "denied-access", "actor": "staff", "action": "view", "resource": "users", "expected": "DENY"},
            {"id": "deny-direct", "category": "direct-access-deny", "actor": "staff", "action": "direct-request", "resource": "users", "expected": "DENY"},
            {"id": "deny-post", "category": "denied-mutation", "actor": "staff", "action": "update", "resource": "users", "expected": "DENY"},
            {"id": "csrf", "category": "csrf", "actor": "admin", "action": "update-without-token", "resource": "users", "expected": "DENY"},
            {"id": "explicit-deny", "category": "explicit-deny", "actor": "admin", "action": "view", "resource": "advanced", "expected": "DENY"},
            {"id": "admin-self-promote", "category": "privilege-management", "actor": "admin", "action": "assign-developer", "target": "self", "expected": "DENY"},
            {"id": "revoked-session", "category": "session-revocation", "actor": "staff", "action": "reuse-session-after-revoke", "target": "self", "expected": "DENY"},
        ]
        return cases

    def _auth_contract(self, command: list[str], *, boundary: str = "staging", profiles: list[str] | None = None) -> dict[str, object]:
        return {
            "id": "authz", "kind": "authorization", "title": "Authorization", "enabled": True,
            "profiles": profiles or ["release"], "actors": ["developer", "admin", "staff"],
            "evidence_boundary": boundary, "command": command, "expected_cases": self._auth_cases(),
        }

    def _evidence(self, contract: dict[str, object], *, failing_id: str = "", include_secret: bool = False) -> dict[str, object]:
        cases = []
        for item in contract["expected_cases"]:
            case = dict(item)
            case["status"] = "FAIL" if item["id"] == failing_id else "PASS"
            if include_secret and item["id"] == "allow-admin":
                case["detail"] = "client_secret=real-secret-value Authorization: Bearer token-value"
                case["access_token"] = "token-value"
            cases.append(case)
        return {
            "schema": 1, "contract_id": contract["id"], "kind": contract["kind"],
            "contract_fingerprint": _contract_fingerprint(contract),
            "evidence_boundary": contract["evidence_boundary"],
            "status": "FAIL" if failing_id else "PASS", "cases": cases,
        }

    def test_authorization_contract_requires_privilege_and_revocation_coverage(self) -> None:
        contract = {
            "id": "authz", "kind": "authorization", "title": "Authorization",
            "enabled": True, "profiles": ["release"], "actors": ["admin", "staff"],
            "evidence_boundary": "staging", "command": ["{python}", "auth.py"],
            "required_categories": ["allowed-access", "denied-access"],
        }
        problems = validate_runtime_contract(contract)
        codes = {item["code"] for item in problems}
        self.assertIn("authorization.privilege-management", codes)
        self.assertIn("authorization.session-revocation", codes)
        self.assertIn("authorization.matrix", codes)

    def test_authorization_contract_catches_privilege_escalation_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            script = root / "auth_contract.py"
            contract = self._auth_contract(["{python}", "{project}/auth_contract.py"])
            contract["id"] = "admin-authz"
            evidence = self._evidence(contract, failing_id="admin-self-promote")
            script.write_text("import json\nprint('FORGE_RUNTIME_EVIDENCE=' + json.dumps(" + repr(evidence) + "))\n", encoding="utf-8")
            registry = {"schema": 1, "updated_utc": "", "contracts": [contract]}
            path = root / config["runtime_proof"]["contracts_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(registry), encoding="utf-8")
            result = run_runtime_contract(root, FORGE_ROOT, config, "admin-authz")
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("non-passing" in item or "did not pass" in item for item in result["problems"]))
            self.assertIn("admin-self-promote", json.dumps(result))

    def test_authorization_contract_passes_with_complete_behavioral_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            contract = self._auth_contract(["{python}", "{project}/auth.py"], boundary="disposable-local-environment", profiles=["section"])
            evidence = self._evidence(contract)
            (root / "auth.py").write_text("import json\nprint('FORGE_RUNTIME_EVIDENCE=' + json.dumps(" + repr(evidence) + "))\n", encoding="utf-8")
            path = root / config["runtime_proof"]["contracts_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"schema": 1, "updated_utc": "", "contracts": [contract]}), encoding="utf-8")
            result = run_runtime_contract(root, FORGE_ROOT, config, "authz")
            self.assertEqual(result["status"], "PASS", result)
            ok, detail = run_required_runtime_contracts(root, FORGE_ROOT, config, "section")
            self.assertTrue(ok, detail)

    def test_runtime_evidence_rejects_stale_contract_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            contract = self._auth_contract(["{python}", "{project}/auth.py"], boundary="disposable-local-environment", profiles=["section"])
            evidence = self._evidence(contract, include_secret=True)
            evidence["contract_fingerprint"] = "stale"
            (root / "auth.py").write_text("import json\nprint('FORGE_RUNTIME_EVIDENCE=' + json.dumps(" + repr(evidence) + "))\n", encoding="utf-8")
            path = root / config["runtime_proof"]["contracts_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"schema": 1, "updated_utc": "", "contracts": [contract]}), encoding="utf-8")
            result = run_runtime_contract(root, FORGE_ROOT, config, "authz")
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("stale", " ".join(result["problems"]))
            serialized = json.dumps(result)
            self.assertNotIn("real-secret-value", serialized)
            self.assertNotIn("token-value", serialized)
            self.assertIn("[REDACTED]", serialized)

    def test_migration_chain_detects_excluded_required_predecessor(self) -> None:
        contract = {
            "id": "schema", "kind": "migration", "title": "Schema",
            "profiles": ["release"], "evidence_boundary": "release-equivalent",
            "command": ["{python}", "migration.py"],
            "migrations": [
                {"id": "m1", "path": "m1.sql", "provides": ["audit_log"], "included_in_delivery": False},
                {"id": "m2", "path": "m2.sql", "requires": ["audit_log"], "provides": ["current"], "included_in_delivery": True},
            ],
        }
        result = analyze_migration_chain(contract)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "migration.excluded-predecessor" for item in result["problems"]))

    def test_migration_chain_orders_valid_dependencies(self) -> None:
        contract = {
            "id": "schema", "kind": "migration", "title": "Schema",
            "profiles": ["release"], "evidence_boundary": "release-equivalent",
            "command": ["{python}", "migration.py"], "initial_schema": ["base"],
            "migrations": [
                {"id": "m1", "requires": ["base"], "provides": ["users"], "included_in_delivery": True},
                {"id": "m2", "requires": ["users"], "provides": ["roles"], "included_in_delivery": True},
                {"id": "m3", "requires_migrations": ["m2"], "requires": ["roles"], "provides": ["permissions"], "included_in_delivery": True},
            ],
        }
        result = analyze_migration_chain(contract)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["order"], ["m1", "m2", "m3"])

    def test_runtime_plan_recommends_authorization_migration_and_browser_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "admin.php").write_text("<?php session_start(); function set_role(){}; $x='permission users.manage'; echo '<form><button>Save</button></form>'; SELECT * FROM users;\n", encoding="utf-8")
            config = self._project(root)
            payload = plan_runtime_proof(root, FORGE_ROOT, config, write=True)
            kinds = {item["kind"] for item in payload["recommendations"]}
            self.assertIn("authorization", kinds)
            self.assertIn("migration", kinds)
            self.assertIn("browser", kinds)
            self.assertTrue((root / ".forge" / "runtime" / "runtime-proof-plan.md").is_file())

    def test_runtime_plan_detects_existing_browser_orchestration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"devDependencies": {"@playwright/test": "1.0"}, "scripts": {"test:e2e": "playwright test"}}), encoding="utf-8")
            (root / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
            config = self._project(root)
            payload = plan_runtime_proof(root, FORGE_ROOT, config, write=False)
            tools = payload["detected_runtime_tools"]["browser"]
            self.assertIn("playwright", tools)
            self.assertIn("playwright.config.ts", tools)

    def test_release_gate_blocks_runtime_contract_with_weak_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._project(root)
            contract = self._auth_contract(["{python}", "{project}/auth.py"], boundary="disposable-local-environment", profiles=["release"])
            evidence = self._evidence(contract)
            (root / "auth.py").write_text("import json\nprint('FORGE_RUNTIME_EVIDENCE=' + json.dumps(" + repr(evidence) + "))\n", encoding="utf-8")
            path = root / config["runtime_proof"]["contracts_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"schema": 1, "updated_utc": "", "contracts": [contract]}), encoding="utf-8")
            ok, detail = run_required_runtime_contracts(root, FORGE_ROOT, config, "release")
            self.assertFalse(ok)
            self.assertIn("weaker", detail)

    def test_impact_separates_certification_dependency_and_runtime_path_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bootstrap.php").write_text("<?php require 'service.php'; if (!file_exists('config.php')) { exit; }\n", encoding="utf-8")
            (root / "service.php").write_text("<?php echo 'ok';\n", encoding="utf-8")
            initialize_project(root, FORGE_ROOT, setup_answers={"preset": "prototype", "versioning": "none"})
            config = load_config(root)
            config["packaging"]["required_files"] = ["bootstrap.php"]
            save_config(root, config)
            build_graph(root, FORGE_ROOT, config, write=True)
            impact = analyze_impact(root, FORGE_ROOT, config, ["bootstrap.php"])
            self.assertEqual(impact["schema"], 2)
            self.assertEqual(impact["impact_axes"]["certification"]["level"], "critical")
            self.assertEqual(impact["impact_axes"]["runtime_path"]["level"], "unknown")
            self.assertIn("cannot prove", impact["impact_axes"]["runtime_path"]["note"])


class ForgeAssuranceCoverageAndDeliveryTests(unittest.TestCase):
    def _config(self, root: Path) -> dict[str, object]:
        detection = detect_project(root, FORGE_ROOT)
        config = default_config("Fixture", detection)
        config["project"]["deployment_target"] = "static"
        return config

    def _record_current_command_pass(
        self,
        root: Path,
        config: dict[str, object],
        raw: dict[str, object],
        profile: str = "section",
        *,
        surfaces: list[str] | None = None,
    ) -> None:
        evidence = raw.get("evidence", {}) if isinstance(raw.get("evidence"), dict) else {}
        command = resolve_command([str(item) for item in raw.get("command", [])], project=root, forge=FORGE_ROOT)
        check = Check(str(raw["id"]), "command:test", 60, tuple(command), evidence_spec=evidence)
        fingerprint = tree_fingerprint(root, config.get("paths", {}).get("exclude", []), FORGE_ROOT)
        artifacts = []
        artifact_paths = evidence.get("artifacts", []) if isinstance(evidence, dict) else []
        if isinstance(artifact_paths, str):
            artifact_paths = [artifact_paths]
        for rel in artifact_paths if isinstance(artifact_paths, list) else []:
            path = root / str(rel)
            if path.is_file():
                artifacts.append({"path": str(rel), "sha256": sha256_file(path), "bytes": path.stat().st_size, "produced_in_run": True})
        write_json(root / config["paths"]["reports"] / f"{profile}.json", {
            "profile": profile, "status": "PASS", "tree_fingerprint": fingerprint,
            "results": [{
                "check_id": raw["id"], "status": "PASS", "command_hash": check.command_hash,
                "evidence": {"surfaces": surfaces or [], "artifacts": artifacts},
            }],
        })

    def test_surface_inventory_finds_php_pages_beyond_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo '<html>home</html>';", encoding="utf-8")
            (root / "dashboard.php").write_text("<?php session_start(); echo '<html>dashboard</html>';", encoding="utf-8")
            (root / "admin").mkdir()
            (root / "admin" / "users.php").write_text("<?php echo '<form></form>';", encoding="utf-8")
            (root / "includes").mkdir()
            (root / "includes" / "helper.php").write_text("<?php function helper() {}", encoding="utf-8")
            config = self._config(root)
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            surfaces = discover_surfaces(root, FORGE_ROOT, config, graph)
            paths = {item["path"] for item in surfaces if item["kind"] in {"browser-page", "entrypoint"}}
            self.assertIn("index.php", paths)
            self.assertIn("dashboard.php", paths)
            self.assertIn("admin/users.php", paths)
            self.assertNotIn("includes/helper.php", paths)

    def test_graph_deduplicates_typed_webhook_and_rejects_client_app_asset_as_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hooks").mkdir()
            (root / "hooks" / "inbound.php").write_text("<?php echo json_encode(['ok' => true]);", encoding="utf-8")
            (root / "assets").mkdir()
            (root / "assets" / "app.js").write_text("console.log('client bundle');\n", encoding="utf-8")
            config = self._config(root)
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            webhook_nodes = [node for node in graph["nodes"] if node.get("type") == "webhook" and node.get("path") == "hooks/inbound.php"]
            asset_nodes = [node for node in graph["nodes"] if node.get("path") == "assets/app.js"]
            self.assertEqual(len(webhook_nodes), 1)
            self.assertEqual(len(asset_nodes), 1)
            self.assertNotEqual(asset_nodes[0]["type"], "entrypoint")
            surfaces = discover_surfaces(root, FORGE_ROOT, config, graph)
            self.assertEqual([item["kind"] for item in surfaces if item["path"] == "hooks/inbound.php"], ["webhook"])
            self.assertFalse(any(item["path"] == "assets/app.js" for item in surfaces))

    def test_surface_inventory_classifies_php_webhooks_jobs_and_cli_without_helper_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "portal.php").write_text("<?php echo '<html>portal</html>';", encoding="utf-8")
            (root / "app").mkdir()
            (root / "app" / "bootstrap.php").write_text(
                "<?php function fail_request(): void { http_response_code(500); }", encoding="utf-8"
            )
            (root / "hooks").mkdir()
            (root / "hooks" / "inbound.php").write_text("<?php echo json_encode(['ok' => true]);", encoding="utf-8")
            (root / "jobs").mkdir()
            (root / "jobs" / "reconcile.php").write_text("<?php echo 'reconciled';", encoding="utf-8")
            (root / "bin").mkdir()
            (root / "bin" / "repair.php").write_text(
                "<?php if (PHP_SAPI !== 'cli') { exit(2); } fwrite(STDOUT, 'ok');", encoding="utf-8"
            )
            config = self._config(root)
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            graph_types = {(node.get("path"), node.get("type")) for node in graph.get("nodes", [])}
            self.assertIn(("hooks/inbound.php", "webhook"), graph_types)
            self.assertIn(("jobs/reconcile.php", "scheduled-job"), graph_types)
            self.assertIn(("bin/repair.php", "cli"), graph_types)
            self.assertNotIn(("app/bootstrap.php", "entrypoint"), graph_types)

            surfaces = discover_surfaces(root, FORGE_ROOT, config, graph)
            by_path = {}
            for item in surfaces:
                by_path.setdefault(item["path"], []).append(item["kind"])
            self.assertEqual(by_path["portal.php"], ["browser-page"])
            self.assertEqual(by_path["hooks/inbound.php"], ["webhook"])
            self.assertEqual(by_path["jobs/reconcile.php"], ["scheduled-job"])
            self.assertEqual(by_path["bin/repair.php"], ["cli"])
            self.assertNotIn("app/bootstrap.php", by_path)

    def test_configured_objective_source_claim_without_recurring_producer_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "portal.php").write_text("<?php echo '<html>portal</html>';", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "OPERATIONS.md").write_text(
                "Every page and upgrade has been verified for release.\n", encoding="utf-8"
            )
            config = self._config(root)
            config.setdefault("continuity", {})["objective_sources"] = ["docs/OPERATIONS.md"]
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            paths = {item["path"] for item in proof["unbacked_documentation_claims"]}
            self.assertIn("docs/OPERATIONS.md", paths)
            self.assertTrue(any("execution evidence" in item["problem"] for item in proof["unbacked_documentation_claims"]))

    def test_surface_inventory_rejects_assets_and_keyword_only_runtime_hints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "forge.py").write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            (root / "docs-site" / "assets").mkdir(parents=True)
            (root / "docs-site" / "index.html").write_text("<!doctype html><html><body>docs</body></html>", encoding="utf-8")
            (root / "docs-site" / "assets" / "app.js").write_text("console.log('docs asset');\n", encoding="utf-8")
            (root / "runtime_contracts.py").write_text(
                "# Documents webhook, cron, scheduler, callback_url and SQL contracts.\n"
                "SUPPORTED = ['webhook', 'cron', 'select ', 'if __name__']\n"
                "STATE_PATH = '.forge/update'\n",
                encoding="utf-8",
            )
            config = self._config(root)
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            surfaces = discover_surfaces(root, FORGE_ROOT, config, graph)
            paths = {item["path"] for item in surfaces}
            self.assertIn("forge.py", paths)
            self.assertIn("docs-site/index.html", paths)
            self.assertNotIn("docs-site/assets/app.js", paths)
            self.assertNotIn("runtime_contracts.py", paths)

    def test_graph_route_requires_real_request_handler_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state.py").write_text("OUTPUT = '.forge/update'\n", encoding="utf-8")
            (root / "server.py").write_text(
                "from flask import Flask\napp = Flask(__name__)\n"
                "@app.route('/health')\ndef health(): return 'ok'\n",
                encoding="utf-8",
            )
            config = self._config(root)
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            surfaces = discover_surfaces(root, FORGE_ROOT, config, graph)
            route_paths = {item["path"] for item in surfaces if item["kind"] == "route"}
            self.assertNotIn("state.py", route_paths)
            self.assertIn("server.py", route_paths)

    def test_keyword_only_database_mentions_do_not_force_upgrade_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Examples mention SELECT, ALTER TABLE, and migrations.\n", encoding="utf-8")
            config = self._config(root)
            config["packaging"]["enabled"] = False
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_level"], "source-verified")
            self.assertNotIn("persisted database or migration state was detected", proof["inferred_claim_reasons"])

    def test_empty_default_target_environment_is_not_a_declared_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            config = self._config(root)
            config["packaging"]["enabled"] = False
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertFalse(proof["target_environment"]["declared"])
            self.assertEqual(proof["target_environment"]["status"], "UNKNOWN")

    def test_release_claim_auto_escalates_and_blocks_uncovered_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo '<html>ok</html>';", encoding="utf-8")
            (root / "settings.php").write_text("<?php echo '<form></form>';", encoding="utf-8")
            config = self._config(root)
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_level"], "entrypoints-executed")
            self.assertEqual(proof["claim_status"], "FAIL")
            self.assertGreaterEqual(proof["surfaces"]["uncovered"], 2)
            self.assertTrue(any("lack recurring execution evidence" in item for item in proof["problems"]))

    def test_typed_recurring_execution_can_cover_declared_surface_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo '<html>ok</html>';", encoding="utf-8")
            (root / "settings.php").write_text("<?php echo '<form></form>';", encoding="utf-8")
            (root / "check.py").write_text("print('ok')\n", encoding="utf-8")
            config = self._config(root)
            config["commands"]["release"] = [{
                "id": "pages.execute",
                "command": ["{python}", "{project}/check.py"],
                "evidence": {"types": ["entrypoint-execution"], "surfaces": ["all:browser-page", "all:entrypoint"]},
            }]
            self._record_current_command_pass(root, config, config["commands"]["release"][0])
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_level"], "entrypoints-executed")
            self.assertEqual(proof["claim_status"], "FAIL")
            self.assertEqual(proof["surfaces"]["uncovered"], 2)
            self._record_current_command_pass(
                root, config, config["commands"]["release"][0],
                surfaces=["index.php", "settings.php"],
            )
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_status"], "PASS")
            self.assertEqual(proof["surfaces"]["uncovered"], 0)

    def test_blank_passing_command_cannot_claim_all_surface_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo '<html>ok</html>';", encoding="utf-8")
            (root / "check.py").write_text("print('ok')\n", encoding="utf-8")
            config = self._config(root)
            config["commands"]["release"] = [{
                "id": "pages.execute",
                "command": ["{python}", "{project}/check.py"],
                "evidence": {"types": ["entrypoint-execution"], "surfaces": ["all:browser-page"]},
            }]
            self._record_current_command_pass(root, config, config["commands"]["release"][0])
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_status"], "FAIL")
            self.assertEqual(proof["surfaces"]["covered"], 0)

    def test_upgrade_claim_requires_prior_state_plus_current_code_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "migrations").mkdir()
            (root / "migrations" / "002.sql").write_text("ALTER TABLE habits ADD COLUMN color TEXT;", encoding="utf-8")
            config = self._config(root)
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_level"], "upgrade-verified")
            self.assertEqual(proof["claim_status"], "FAIL")
            config["release_proof"]["deployment_states"] = [{
                "id": "prior-release-plus-current-code",
                "state": "prior-release-plus-current-code",
                "required": True,
                "evidence": ".forge/runtime/migration-upgrade-latest.json",
            }]
            fingerprint = tree_fingerprint(root, config.get("paths", {}).get("exclude", []), FORGE_ROOT)
            write_json(root / ".forge/runtime/migration-upgrade-latest.json", {
                "status": "PASS", "tree_fingerprint": fingerprint,
                "deployment_state": "prior-release-plus-current-code",
            })
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_status"], "FAIL")
            self.assertTrue(any("Forge-observed producer" in item for item in proof["problems"]))
            (root / "verify_upgrade.py").write_text("print('verified')\n", encoding="utf-8")
            command = {
                "id": "upgrade.verify",
                "command": ["{python}", "{project}/verify_upgrade.py"],
                "evidence": {"types": ["database-upgrade"], "artifacts": [".forge/runtime/migration-upgrade-latest.json"]},
            }
            config["commands"]["release"] = [command]
            config["release_proof"]["deployment_states"][0]["evidence"] = {
                "path": ".forge/runtime/migration-upgrade-latest.json",
                "producer": "upgrade.verify",
            }
            fingerprint = tree_fingerprint(root, config.get("paths", {}).get("exclude", []), FORGE_ROOT)
            write_json(root / ".forge/runtime/migration-upgrade-latest.json", {
                "status": "PASS", "tree_fingerprint": fingerprint,
                "deployment_state": "prior-release-plus-current-code",
            })
            self._record_current_command_pass(root, config, command)
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_status"], "PASS")

    def test_prewritten_evidence_file_is_not_provenance_without_current_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "migrations").mkdir()
            (root / "migrations" / "002.sql").write_text("ALTER TABLE habits ADD COLUMN color TEXT;", encoding="utf-8")
            script = root / "no_op.py"
            script.write_text("print('checked')\n", encoding="utf-8")
            config = self._config(root)
            command = {
                "id": "upgrade.no-op",
                "command": [sys.executable, str(script)],
                "evidence": {
                    "types": ["database-upgrade"],
                    "artifacts": [".forge/runtime/migration-upgrade-latest.json"],
                },
            }
            config["commands"]["quick"] = [command]
            config["release_proof"]["deployment_states"] = [{
                "id": "prior-release-plus-current-code",
                "state": "prior-release-plus-current-code",
                "required": True,
                "evidence": {
                    "path": ".forge/runtime/migration-upgrade-latest.json",
                    "producer": "upgrade.no-op",
                },
            }]
            fingerprint = tree_fingerprint(root, config.get("paths", {}).get("exclude", []), FORGE_ROOT)
            write_json(root / ".forge/runtime/migration-upgrade-latest.json", {
                "status": "PASS",
                "tree_fingerprint": fingerprint,
                "deployment_state": "prior-release-plus-current-code",
            })
            payload = run_profile(root, FORGE_ROOT, config, "quick", fresh=True)
            result = next(item for item in payload["results"] if item["check_id"] == "upgrade.no-op")
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["evidence"]["artifacts"][0]["produced_in_run"])
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_status"], "FAIL")
            self.assertTrue(any("not produced or refreshed" in item for item in proof["problems"]))

    def test_target_environment_matrix_blocks_untested_runtime_and_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.php").write_text("<?php echo '<html>ok</html>';", encoding="utf-8")
            config = self._config(root)
            config["project"]["deployment_target"] = "cpanel"
            fingerprint = tree_fingerprint(root, config.get("paths", {}).get("exclude", []), FORGE_ROOT)
            write_json(root / ".forge/runtime/target-env.json", {
                "status": "PASS", "tree_fingerprint": fingerprint, "evidence_boundary": "release-equivalent",
                "runtimes": {"php": ["8.3"]}, "extensions": [], "services": ["mysql"],
            })
            (root / "verify_target.py").write_text("print('verified')\n", encoding="utf-8")
            target_command = {
                "id": "target.verify", "command": ["{python}", "{project}/verify_target.py"],
                "evidence": {
                    "types": ["target-environment", "entrypoint-execution"],
                    "surfaces": ["all:browser-page", "all:entrypoint"],
                    "artifacts": [".forge/runtime/target-env.json"],
                },
            }
            config["commands"]["release"] = [target_command]
            self._record_current_command_pass(root, config, target_command, surfaces=["index.php"])
            config["environment"]["target"] = {
                "runtimes": {"php": "8.4"},
                "required_extensions": ["gd"],
                "required_services": ["mysql"],
                "evidence": [{"path": ".forge/runtime/target-env.json", "producer": "target.verify"}],
            }
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_level"], "target-environment-verified")
            self.assertEqual(proof["claim_status"], "FAIL")
            self.assertTrue(any("PHP 8.4".lower() in item.lower() or "runtime php 8.4" in item.lower() for item in proof["problems"]))
            self.assertTrue(any("gd" in item for item in proof["problems"]))

    def test_partial_delivery_requires_final_bundle_and_surfaces_specific_release_problem(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README-FIRST.md").write_text("Owner instructions\n", encoding="utf-8")
            config = self._config(root)
            config["release_proof"]["auto_minimum"] = False
            record_delivery_artifact(root, config, {
                "path": "README-FIRST.md",
                "role": "instructions",
                "mode": "frozen",
                "freeze_reason": "Approved owner-facing instructions.",
            })
            validation = validate_delivery_provenance(root, config)
            self.assertEqual(validation["status"], "FAIL")
            self.assertIn("final owner-facing delivery bundle has not been built", validation["problems"])
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_status"], "PASS")
            self.assertIn("final owner-facing delivery bundle has not been built", proof["dimension_problems"])
            save_config(root, config)
            result = subprocess.run(
                [sys.executable, str(FORGE_ROOT / "forge.py"), "prove", "coverage", str(root)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            compact = json.loads(result.stdout)
            self.assertIn("final owner-facing delivery bundle has not been built", compact["problems"])
            self.assertEqual(compact["claim_problems"], [])

    def test_refreshing_inner_artifact_invalidates_and_cannot_reuse_stale_outer_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "README-FIRST.md"
            artifact.write_text("version one\n", encoding="utf-8")
            config = self._config(root)
            record = {
                "path": "README-FIRST.md", "role": "instructions", "mode": "frozen",
                "freeze_reason": "Approved owner-facing instructions.",
            }
            record_delivery_artifact(root, config, record)
            built = build_final_delivery(root, config, root / "Owner-Handoff.zip")
            self.assertEqual(built["status"], "PASS", built.get("problems"))
            old_final = dict(built["manifest"]["final_bundle"])

            artifact.write_text("version two\n", encoding="utf-8")
            record_delivery_artifact(root, config, {**record, "freeze_reason": "Approved refreshed instructions."})
            validation = validate_delivery_provenance(root, config)
            self.assertEqual(validation["status"], "FAIL")
            self.assertIn("final owner-facing delivery bundle has not been built", validation["problems"])

            manifest_path = root / config["delivery_proof"]["manifest_path"]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["final_bundle"] = old_final
            write_json(manifest_path, manifest)
            validation = validate_delivery_provenance(root, config)
            self.assertEqual(validation["status"], "FAIL")
            self.assertIn("final delivery bundle contains stale artifact bytes: README-FIRST.md", validation["problems"])

    def test_generated_artifact_requires_forge_observed_execution_and_detects_input_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "source.txt").write_text("version one\n", encoding="utf-8")
            generator = root / "tools" / "build_changed.py"
            generator.write_text(
                "from pathlib import Path\nimport zipfile\n"
                "with zipfile.ZipFile('Changed Files.zip','w') as z: z.write('source.txt')\n",
                encoding="utf-8",
            )
            config = self._config(root)
            record = {
                "path": "Changed Files.zip", "role": "changed-files", "mode": "generated",
                "generator": {"command": ["{python}", "{project}/tools/build_changed.py"]},
                "inputs": ["source.txt", "tools/build_changed.py"],
            }
            item = record_delivery_artifact(root, config, record)
            self.assertEqual(item["generator"]["execution"]["status"], "PASS")
            built = build_final_delivery(root, config, root / "Owner-Handoff.zip")
            self.assertEqual(built["status"], "PASS", built.get("problems"))
            self.assertEqual(validate_delivery_provenance(root, config)["status"], "PASS")
            (root / "source.txt").write_text("version two\n", encoding="utf-8")
            validation = validate_delivery_provenance(root, config)
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(any("inputs changed" in item for item in validation["problems"]))

    def test_delivery_provenance_rejects_undeclared_artifact_and_invalid_generator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README-FIRST.md").write_text("handoff\n", encoding="utf-8")
            config = self._config(root)
            record_delivery_artifact(root, config, {
                "path": "README-FIRST.md", "role": "instructions", "mode": "frozen",
                "freeze_reason": "Owner-approved static handoff instructions.",
            })
            (root / "Old-Changed-Files.zip").write_bytes(b"stale")
            validation = validate_delivery_provenance(root, config)
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(any("outside the declared delivery manifest" in item for item in validation["problems"]))
            with self.assertRaises(RuntimeError):
                record_delivery_artifact(root, config, {
                    "path": "Never.zip", "role": "delta", "mode": "generated",
                    "generator": {"command": ["{python}", "{project}/tools/missing.py"]},
                    "inputs": ["README-FIRST.md"],
                })

    def test_documented_once_only_execution_claim_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("All 57 pages are now executed headlessly and verified.\n", encoding="utf-8")
            (root / "index.php").write_text("<?php echo '<html>ok</html>';", encoding="utf-8")
            config = self._config(root)
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(len(proof["unbacked_documentation_claims"]), 1)

    def test_resilience_contract_models_visible_actionable_failure(self) -> None:
        contract = {
            "id": "deployment-preflight", "kind": "resilience", "enabled": True,
            "profiles": ["release"], "evidence_boundary": "release-equivalent",
            "command": ["python3", "check.py"],
        }
        self.assertEqual(validate_runtime_contract(contract), [])

    def test_schema_seven_migrates_to_release_proof_schema(self) -> None:
        old = {"schema": 7, "project": {"name": "Fixture"}}
        migrated, steps = migrate_config_data(old)
        self.assertEqual(migrated["schema"], CURRENT_CONFIG_SCHEMA)
        self.assertIn("release_proof", migrated)
        self.assertIn("delivery_proof", migrated)
        self.assertTrue(any(item["id"] == "assurance-coverage-and-delivery-provenance" for item in steps))

    def test_schema_eight_migrates_to_observed_attestation_binding(self) -> None:
        old = {"schema": 8, "project": {"name": "Fixture"}, "release_proof": {}}
        migrated, steps = migrate_config_data(old)
        self.assertEqual(migrated["schema"], CURRENT_CONFIG_SCHEMA)
        self.assertEqual(migrated["release_proof"]["observed_attestations"]["surface_marker"], "FORGE_SURFACE")
        self.assertTrue(migrated["release_proof"]["observed_attestations"]["bind_evidence_artifacts"])
        self.assertTrue(any(item["id"] == "observed-evidence-attestation-binding" for item in steps))

    def test_current_lab_evidence_covers_declared_static_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<!doctype html><html><body>ready</body></html>", encoding="utf-8")
            config = self._config(root)
            recipe = next(item for item in default_lab_recipes(root, []) if item["id"] == "static-smoke")
            config["lab"]["recipes"] = [recipe]
            result = run_lab(root, FORGE_ROOT, config, "static-smoke")
            self.assertEqual(result["status"], "PASS", result)
            proof = build_release_proof(root, FORGE_ROOT, config, write=False)
            self.assertEqual(proof["claim_level"], "entrypoints-executed")
            self.assertEqual(proof["claim_status"], "PASS", proof["problems"])
            self.assertEqual(proof["surfaces"]["uncovered"], 0)

    def test_graph_joins_source_inputs_to_artifacts_and_final_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README-FIRST.md").write_text("Owner instructions\n", encoding="utf-8")
            config = self._config(root)
            record_delivery_artifact(root, config, {
                "path": "README-FIRST.md", "role": "instructions", "mode": "frozen",
                "freeze_reason": "Approved handoff instructions.",
            })
            built = build_final_delivery(root, config, root / "Owner-Handoff.zip")
            self.assertEqual(built["status"], "PASS", built.get("problems"))
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            types = {item["type"] for item in graph["nodes"]}
            self.assertIn("delivered-artifact", types)
            self.assertIn("delivery-bundle", types)
            self.assertTrue(any(item["type"] == "contained-in" for item in graph["edges"]))

    def test_deployment_manifest_embeds_current_scoped_release_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<!doctype html><html><body>ready</body></html>", encoding="utf-8")
            config = self._config(root)
            recipe = next(item for item in default_lab_recipes(root, []) if item["id"] == "static-smoke")
            config["lab"]["recipes"] = [recipe]
            self.assertEqual(run_lab(root, FORGE_ROOT, config, "static-smoke")["status"], "PASS")
            proof = build_release_proof(root, FORGE_ROOT, config, write=True)
            self.assertEqual(proof["claim_status"], "PASS")
            package = build_package(root, FORGE_ROOT, config, dry_run=False, output=root / "deploy" / "fixture.zip")
            self.assertEqual(package["status"], "PASS", package["problems"])
            self.assertEqual(package["manifest"]["release_proof"]["claim_level"], "entrypoints-executed")
            self.assertEqual(package["manifest"]["release_proof"]["claim_status"], "PASS")
            self.assertTrue(package["manifest"]["source_tree_fingerprint"])

    def test_evidence_index_surfaces_release_and_delivery_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README-FIRST.md").write_text("Owner instructions\n", encoding="utf-8")
            config = self._config(root)
            config["release_proof"]["auto_minimum"] = False
            build_release_proof(root, FORGE_ROOT, config, write=True)
            record_delivery_artifact(root, config, {
                "path": "README-FIRST.md", "role": "instructions", "mode": "frozen",
                "freeze_reason": "Approved handoff instructions.",
            })
            evidence = list_evidence(root, config)
            self.assertEqual(evidence["release_proofs"][0]["id"], "release-proof:latest")
            self.assertEqual(evidence["delivery_proofs"][0]["id"], "delivery-proof:manifest")


class ForgeConfidentialityAndContinuityTests(unittest.TestCase):
    def _write_ecosystem(self, root: Path) -> None:
        (root / "tools" / "data").mkdir(parents=True)
        (root / "tools" / "run_suite.py").write_text("#!/usr/bin/env python3\nprint('PASS')\n", encoding="utf-8")
        (root / "tools" / "data" / "rules.json").write_text('{"private_rule":"Orchid Vault"}\n', encoding="utf-8")
        (root / "TOOLSET-MANIFEST.json").write_text(json.dumps({
            "name": "Neutral Assurance Suite",
            "canonical_paths": ["tools/"],
            "commands": {
                "quick": "python3 tools/run_suite.py --profile quick",
                "release": "python3 tools/run_suite.py --profile release"
            },
            "forge": {"generated_state": [".suite-results"]}
        }, indent=2), encoding="utf-8")

    def test_confidentiality_policy_detects_private_term_without_echoing_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.md").write_text("Internal project codename: Orchid Vault\n", encoding="utf-8")
            policy = root / "private-policy.json"
            policy.write_text(json.dumps({"schema": 1, "forbidden_terms": [{"id": "private-project-name", "value": "Orchid Vault"}]}), encoding="utf-8")
            payload = scan_confidentiality(root, policy_path=policy, write=False)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["findings"][0]["rule_id"], "private-project-name")
            self.assertNotIn("Orchid Vault", json.dumps(payload))

    def test_confidentiality_policy_detects_exact_normalized_and_archive_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = b"private fixture payload\n"
            exact = __import__("hashlib").sha256(secret).hexdigest()
            normalized = __import__("hashlib").sha256(secret).hexdigest()
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "schema": 1,
                "forbidden_sha256": [{"id": "private-exact", "value": exact}],
                "forbidden_normalized_sha256": [{"id": "private-normalized", "value": normalized}]
            }), encoding="utf-8")
            archive = root / "bundle.zip"
            inner_buffer = __import__("io").BytesIO()
            with zipfile.ZipFile(inner_buffer, "w") as inner:
                inner.writestr("fixtures/private.txt", secret)
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("nested/fixture-bundle.zip", inner_buffer.getvalue())
            payload = scan_zip_archive(archive, policy_path=policy)
            self.assertEqual(payload["status"], "FAIL")
            rules = {item["rule_id"] for item in payload["findings"]}
            self.assertIn("private-exact", rules)
            self.assertIn("private-normalized", rules)

    def test_ecosystem_registry_and_lifecycle_are_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_ecosystem(root)
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            inventory = scan_existing_tools(root, FORGE_ROOT)
            adopted = absorb_tools(config, inventory)
            reports = write_tool_reports(root, inventory, adopted)
            registry_text = (root / ".forge" / "tool-ecosystems" / "neutral-assurance-suite.json").read_text(encoding="utf-8")
            lifecycle_text = Path(reports["lifecycle"]).read_text(encoding="utf-8")
            self.assertNotIn("Orchid Vault", registry_text)
            self.assertNotIn("Orchid Vault", lifecycle_text)
            self.assertIn("ecosystem-adopted", lifecycle_text)
            (root / "tools" / "data" / "rules.json").write_text('{"private_rule":"changed"}\n', encoding="utf-8")
            write_tool_reports(root, scan_existing_tools(root, FORGE_ROOT))
            lifecycle = json.loads(Path(reports["lifecycle"]).read_text(encoding="utf-8"))
            change = next(item for item in lifecycle["events"] if item["type"] == "ecosystem-inputs-changed")
            self.assertIn("tools/data/rules.json", change["changed_paths"])
            self.assertEqual(change["evidence_disposition"], "stale-until-rerun")

    def test_graph_models_typed_tool_connections_without_command_or_absolute_path_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_ecosystem(root)
            config = default_config("Fixture", detect_project(root, FORGE_ROOT))
            inventory = scan_existing_tools(root, FORGE_ROOT)
            adopted = absorb_tools(config, inventory)
            write_tool_reports(root, inventory, adopted)
            graph = build_graph(root, FORGE_ROOT, config, write=False)
            self.assertEqual(graph["project_root"], ".")
            node_types = {item["type"] for item in graph["nodes"]}
            self.assertTrue({"tool-ecosystem", "tool-input-set", "tool-command"}.issubset(node_types))
            edge_types = {item["type"] for item in graph["edges"]}
            self.assertTrue({"owns", "runs", "reads", "contains"}.issubset(edge_types))
            serialized = json.dumps(graph)
            self.assertNotIn("Orchid Vault", serialized)
            self.assertNotIn(str(root), serialized)
            command_nodes = [item for item in graph["nodes"] if item["type"] == "tool-command"]
            self.assertTrue(command_nodes)
            self.assertTrue(all("command_sha256" in item["metadata"] and "command" not in item["metadata"] for item in command_nodes))

    def test_config_schema_nine_migrates_to_metadata_only_confidentiality(self) -> None:
        base = default_config("Fixture", detect_project(FORGE_ROOT, FORGE_ROOT))
        base["schema"] = 9
        base.pop("confidentiality", None)
        migrated, migrations = migrate_config_data(base)
        self.assertEqual(migrated["schema"], CURRENT_CONFIG_SCHEMA)
        self.assertEqual(migrated["confidentiality"]["mode"], "metadata-only")
        self.assertFalse(migrated["confidentiality"]["capture_host_file_contents"])
        self.assertEqual(migrated["confidentiality"]["private_policy_env"], "FORGE_PRIVATE_POLICY")
        self.assertTrue(any(item["id"] == "metadata-only-confidentiality-boundary" for item in migrations))

    def test_package_builder_enforces_external_confidentiality_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "policy.json"
            policy.write_text(json.dumps({"schema": 1, "forbidden_terms": [{"id": "synthetic-block", "value": "Emotivus Forge"}]}), encoding="utf-8")
            output = root / "blocked.zip"
            process = subprocess.run([
                sys.executable, str(FORGE_ROOT / "tools" / "build_forge_package.py"), str(FORGE_ROOT),
                "--output", str(output), "--private-policy", str(policy)
            ], cwd=FORGE_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(output.exists())
            self.assertIn("confidentiality scan failed", process.stderr)


class ForgeExecutionBudgetTests(unittest.TestCase):
    def test_self_test_summary_is_compact_and_points_to_evidence(self) -> None:
        payload = {
            "status": "INCOMPLETE", "completed_count": 4, "total_count": 27, "remaining_count": 23,
            "halt_reason": "overall-budget", "resume_command": "python3 forge.py self-test --resume",
            "scope": {"id": "full"},
            "results": [{"shard_id": "forge-core:Neutral", "status": "PASS", "output": "very large output"}],
        }
        summary = _format_self_test_summary(payload)
        self.assertIn("INCOMPLETE — 4/27", summary)
        self.assertIn("Resume: python3 forge.py self-test --resume", summary)
        self.assertIn("self-test-latest.json", summary)
        self.assertNotIn("very large output", summary)

    def test_self_test_classes_are_discovered_as_isolated_shards(self) -> None:
        classes = discover_unittest_classes(FORGE_ROOT / "tests" / "test_forge_core.py")
        self.assertIn("ForgeDetectionTests", classes)
        self.assertIn("ForgeExecutionBudgetTests", classes)
        manifest = json.loads((FORGE_ROOT / "FORGE-MANIFEST.json").read_text(encoding="utf-8"))
        shards = build_shards(FORGE_ROOT, manifest, only=["ForgeDetectionTests"])
        self.assertEqual(len(shards), 1)
        self.assertEqual(shards[0].shard_id, "forge-core:ForgeDetectionTests")
        self.assertIn("emotivus_forge.test_shard_runner", shards[0].command)
        large = build_shards(FORGE_ROOT, manifest, only=["ForgeAssuranceCoverageAndDeliveryTests"] )
        self.assertEqual(len(large), 6)
        self.assertTrue(all("ForgeAssuranceCoverageAndDeliveryTests[" in item.shard_id for item in large))
        self.assertTrue(all(len(item.command) <= 8 for item in large))
        workflow = build_shards(FORGE_ROOT, manifest, only=["ForgeWorkflowTests"] )
        self.assertEqual(len(workflow), 2)

    def test_self_test_budget_pauses_cleanly_and_resume_completes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "FORGE-MANIFEST.json").write_text(json.dumps({
                "self_tests": [{
                    "id": "slow-neutral",
                    "command": ["{python}", "-c", "import time; time.sleep(0.4); print('done')"],
                    "timeout": 5
                }]
            }), encoding="utf-8")
            paused = run_self_tests(root, fresh=True, budget_seconds=0.1)
            self.assertEqual(paused["status"], "INCOMPLETE")
            self.assertEqual(paused["halt_reason"], "overall-budget")
            self.assertEqual(paused["completed_count"], 0)
            resumed = run_self_tests(root, resume=True, budget_seconds=8)
            self.assertEqual(resumed["status"], "PASS")
            self.assertEqual(resumed["passed_count"], 1)

    def test_timeout_never_blocks_on_detached_descendant_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(3)'], start_new_session=True); "
                "print('parent-started', flush=True); time.sleep(10)"
            )
            (root / "FORGE-MANIFEST.json").write_text(json.dumps({
                "self_tests": [{"id": "detached-pipe", "command": ["{python}", "-c", script], "timeout": 1}]
            }), encoding="utf-8")
            started = time.monotonic()
            result = run_self_tests(root, fresh=True)
            elapsed = time.monotonic() - started
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["results"][0]["status"], "TIMEOUT")
            self.assertLess(elapsed, 2.5)

    def test_concurrent_self_test_is_blocked_by_single_run_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "FORGE-MANIFEST.json").write_text(json.dumps({
                "self_tests": [{"id": "neutral", "command": ["{python}", "-c", "print('ok')"], "timeout": 5}]
            }), encoding="utf-8")
            lock = _run_lock_path(root)
            lock.mkdir(parents=True)
            (lock / "owner.json").write_text(json.dumps({"pid": os.getpid(), "token": "active"}), encoding="utf-8")
            try:
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    run_self_tests(root, fresh=True, budget_seconds=10)
            finally:
                (lock / "owner.json").unlink(missing_ok=True)
                lock.rmdir()

    @unittest.skipIf(os.name == "nt", "POSIX process-group signal regression")
    def test_external_termination_cleans_active_shard_and_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_pid_file = root / "active-child.pid"
            child_script = (
                "from pathlib import Path; import os,time; "
                f"Path({str(child_pid_file)!r}).write_text(str(os.getpid()), encoding='utf-8'); "
                "time.sleep(30)"
            )
            (root / "FORGE-MANIFEST.json").write_text(json.dumps({
                "self_tests": [{"id": "signal-cleanup", "command": ["{python}", "-c", child_script], "timeout": 60}]
            }), encoding="utf-8")
            runner = (
                "from pathlib import Path; import sys; "
                "from emotivus_forge.selftest import run_self_tests; "
                "run_self_tests(Path(sys.argv[1]), fresh=True, budget_seconds=60)"
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(FORGE_ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
            parent = subprocess.Popen(
                [sys.executable, "-c", runner, str(root)], cwd=FORGE_ROOT, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            )
            lock = _run_lock_path(root)
            try:
                deadline = time.monotonic() + 6
                while time.monotonic() < deadline and not (child_pid_file.exists() and lock.exists()):
                    time.sleep(0.05)
                self.assertTrue(child_pid_file.exists(), "the active shard did not start")
                self.assertTrue(lock.exists(), "the self-test lock was not acquired")
                child_pid = int(child_pid_file.read_text(encoding="utf-8"))
                os.kill(parent.pid, signal.SIGTERM)
                parent.wait(timeout=8)

                def child_is_active() -> bool:
                    proc_stat = Path(f"/proc/{child_pid}/stat")
                    if proc_stat.is_file():
                        try:
                            return proc_stat.read_text(encoding="utf-8").split()[2] != "Z"
                        except (OSError, IndexError):
                            pass
                    try:
                        os.kill(child_pid, 0)
                    except ProcessLookupError:
                        return False
                    return True

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and child_is_active():
                    time.sleep(0.05)
                self.assertFalse(child_is_active(), "the shard survived external parent termination")
                self.assertFalse(lock.exists(), "the run lock survived external parent termination")
            finally:
                if parent.poll() is None:
                    os.killpg(parent.pid, signal.SIGKILL)
                    parent.wait(timeout=5)

    def test_filtered_self_test_does_not_destroy_full_run_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "FORGE-MANIFEST.json").write_text(json.dumps({
                "self_tests": [
                    {"id": "fast-a", "command": ["{python}", "-c", "print('a')"], "timeout": 5},
                    {"id": "fast-b", "command": ["{python}", "-c", "print('b')"], "timeout": 5},
                ]
            }), encoding="utf-8")
            full = run_self_tests(root, fresh=True, budget_seconds=10)
            self.assertEqual(full["status"], "PASS")
            full_path = root / "self" / ".runtime" / "self-test-progress.json"
            full_before = full_path.read_text(encoding="utf-8")
            filtered = run_self_tests(root, fresh=True, only=["fast-a"], budget_seconds=10)
            self.assertEqual(filtered["status"], "PASS")
            self.assertEqual(filtered["scope"]["only"], ["fast-a"])
            self.assertEqual(full_path.read_text(encoding="utf-8"), full_before)
            scoped = list((root / "self" / ".runtime").glob("self-test-progress-only-*.json"))
            self.assertEqual(len(scoped), 1)

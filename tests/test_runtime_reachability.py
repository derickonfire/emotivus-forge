from __future__ import annotations

import json
from pathlib import Path

from tests.support import FORGE_ROOT, ForgeTestCase
from tools.map_runtime_reachability import (
    ALLOWED_CLASSIFICATIONS,
    PUBLIC_COMMANDS,
    _dynamic_trace,
    generate,
)


class RuntimeReachabilityTests(ForgeTestCase):
    def test_all_active_runtime_modules_are_reachable_and_classified(self) -> None:
        result = generate(FORGE_ROOT, run_dynamic=False)
        self.assertEqual(result["static_unreachable_modules"], [])
        self.assertEqual(result["unclassified_modules"], [])
        self.assertEqual(result["static_reachable_count"], result["module_count"])
        for row in result["modules"]:
            self.assertTrue(row["active_reachable"], row["module"])
            self.assertTrue(set(row["classifications"]).issubset(ALLOWED_CLASSIFICATIONS))
            self.assertNotEqual(row["classifications"], ["UNCLASSIFIED"])

    def test_manifest_path_patterns_are_classified(self) -> None:
        result = generate(FORGE_ROOT, run_dynamic=False)
        self.assertTrue(result["manifest_paths"])
        for row in result["manifest_paths"]:
            self.assertNotEqual(row["classifications"], ["UNCLASSIFIED"], row["path"])
            self.assertTrue(set(row["classifications"]).issubset(ALLOWED_CLASSIFICATIONS))

    def test_every_active_top_level_path_is_classified(self) -> None:
        result = generate(FORGE_ROOT, run_dynamic=False)
        self.assertEqual(result["unclassified_top_level_paths"], [])
        self.assertTrue(result["top_level_inventory"])
        for row in result["top_level_inventory"]:
            self.assertNotEqual(row["disposition"], "REVIEW", row["path"])

    def test_help_command_trace_is_observed_in_a_neutral_fixture(self) -> None:
        result = _dynamic_trace(FORGE_ROOT, "help", 30)
        self.assertEqual(result["trace_status"], "OBSERVED", result)
        self.assertEqual(result["command_exit_code"], 0)
        self.assertIn("emotivus_forge/cli.py", result["modules"])
        self.assertIn("emotivus_forge/commands/public.py", result["modules"])

    def test_generated_report_covers_all_public_commands(self) -> None:
        report = FORGE_ROOT / "planning" / "ACTIVE-RUNTIME-REACHABILITY.json"
        payload = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else generate(FORGE_ROOT, run_dynamic=True)
        self.assertEqual([row["command"] for row in payload["commands"]], list(PUBLIC_COMMANDS))
        self.assertTrue(all(row["trace_status"] == "OBSERVED" for row in payload["commands"]))
        self.assertEqual(payload["static_unreachable_count"], 0)
        self.assertEqual(payload["unclassified_modules"], [])
        self.assertIn("No module is removal-authorized", payload["truth_boundary"]["removal"])

    def test_report_is_deterministic_without_dynamic_execution(self) -> None:
        first = generate(FORGE_ROOT, run_dynamic=False)
        second = generate(FORGE_ROOT, run_dynamic=False)
        self.assertEqual(first, second)

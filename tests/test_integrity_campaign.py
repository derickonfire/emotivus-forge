from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from tests.support import FORGE_ROOT


def _load_campaign_module():
    path = FORGE_ROOT / "tools" / "run_integrity_campaign.py"
    spec = importlib.util.spec_from_file_location("forge_integrity_campaign_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load integrity campaign tool.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntegrityCampaignTests(unittest.TestCase):
    def test_current_source_passes_all_public_neutral_integrity_scenarios(self) -> None:
        module = _load_campaign_module()
        report = module.run_campaign(FORGE_ROOT)
        self.assertEqual(report["schema"], "forge-integrity-campaign/1")
        self.assertEqual(report["summary"], {"status": "PASS", "passed": 6, "failed": 0, "total": 6})
        self.assertTrue(report["fixture_policy"]["public_neutral"])
        self.assertFalse(report["fixture_policy"]["real_user_or_project_data"])
        self.assertFalse(report["fixture_policy"]["private_key_material"])
        self.assertEqual(
            {item["scenario_id"] for item in report["scenarios"]},
            {
                "external-writer-after-checkpoint",
                "package-source-drift-before-publication",
                "same-name-same-version-rival-artifacts",
                "filename-manifest-version-disagreement",
                "explicit-collision-quarantine-recovery",
                "project-ignore-bounds-artifact-observation",
            },
        )
        self.assertTrue(all(item["status"] == "PASS" for item in report["scenarios"]))
        self.assertIn("do not authenticate a writer", report["truth_boundary"])


if __name__ == "__main__":
    unittest.main()

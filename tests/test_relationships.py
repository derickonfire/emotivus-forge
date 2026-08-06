from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.relationships import (
    evaluate_relationships,
    record_relationship_set,
    relationship_records,
    retire_relationship_set,
)
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class ConfirmedRelationshipTests(ForgeTestCase):
    def _adopt_with_relationships(self, root: Path) -> Path:
        self._fixture(root)
        contract = self._relationship_contract(root)
        build_passport(root, FORGE_ROOT)
        record_relationship_set(root, FORGE_ROOT, contract)
        return contract

    def test_include_change_expands_impact_without_manufacturing_changed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_with_relationships(root)
            include = root / "includes" / "menu-data.php"
            include.write_text(include.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")

            result = run_scoped_check(root, FORGE_ROOT)

            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["changes"]["paths"], ["includes/menu-data.php"])
            self.assertIn("public/menu.php", result["check_plan"]["related_paths"])
            self.assertNotIn("public/menu.php", result["changes"]["paths"])
            self.assertIn("public-menu", result["check_plan"]["affected_surfaces"])
            required = {item["id"] for item in result["check_plan"]["required_checks"]}
            self.assertIn("native.public-menu-render", required)
            self.assertEqual(result["relationships"]["impact_count"], 1)

    def test_behavior_binding_propagates_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_with_relationships(root)
            behavior = root / "assets" / "menu-crop.js"
            behavior.write_text(behavior.read_text(encoding="utf-8") + "// binding change\n", encoding="utf-8")

            result = run_scoped_check(root, FORGE_ROOT)

            impact = next(item for item in result["relationships"]["impacts"] if item["relationship_id"] == "menu-crop-binding")
            self.assertEqual(impact["trigger_paths"], ["assets/menu-crop.js"])
            self.assertEqual(impact["related_paths"], ["templates/menu.html"])
            self.assertIn("behavior", result["check_plan"]["affected_surfaces"])
            self.assertIn("native.menu-crop-behavior", {item["id"] for item in result["check_plan"]["required_checks"]})

    def test_source_to_target_relationship_does_not_reverse_propagate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_with_relationships(root)
            public = root / "public" / "menu.php"
            public.write_text(public.read_text(encoding="utf-8") + "// public-only change\n", encoding="utf-8")

            result = run_scoped_check(root, FORGE_ROOT)

            ids = {item["relationship_id"] for item in result["relationships"]["impacts"]}
            self.assertIn("menu-entrypoint-data", ids)
            self.assertNotIn("menu-migration-effect", ids)

    def test_missing_required_endpoint_blocks_and_names_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_with_relationships(root)
            (root / "assets" / "menu-crop.js").unlink()

            result = run_scoped_check(root, FORGE_ROOT)

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["relationships"]["status"], "FAIL")
            messages = [item["message"] for item in result["findings"]]
            self.assertTrue(any("menu-crop-binding" in message and "crop behavior" in message for message in messages))

    def test_changed_relationship_contract_requires_renewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self._adopt_with_relationships(root)
            raw = json.loads(contract.read_text(encoding="utf-8"))
            raw["rationale"] += " The relationship contract now has an additional owner clarification."
            contract.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

            result = run_scoped_check(root, FORGE_ROOT)

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["relationships"]["attention_count"], 1)
            self.assertTrue(any("renewed authority" in item["message"] for item in result["findings"]))

    def test_retired_relationship_set_stops_propagating_but_remains_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_with_relationships(root)
            retire_relationship_set(root, "public-menu-runtime", "The project replaced this relationship model.")
            include = root / "includes" / "menu-data.php"
            include.write_text(include.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")

            result = run_scoped_check(root, FORGE_ROOT)
            records = relationship_records(root)

            self.assertEqual(records["public-menu-runtime"]["lifecycle_status"], "retired")
            self.assertEqual(result["relationships"]["impact_count"], 0)
            self.assertNotIn("public/menu.php", result["check_plan"]["related_paths"])

    def test_resume_keeps_relationship_details_local_and_counts_compact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_with_relationships(root)
            include = root / "includes" / "menu-data.php"
            include.write_text(include.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")

            resume = build_resume(root, FORGE_ROOT, budget="compact")
            markdown = resume["markdown"]

            self.assertIn("Confirmed relationships:", markdown)
            self.assertIn("1 current impact(s)", markdown)
            self.assertNotIn("public/menu.php", markdown)
            self.assertEqual(resume["relationships"]["impact_count"], 1)
            self.assertNotIn("impacts", resume["relationships"])

    def test_relationship_record_uses_existing_eight_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._adopt_with_relationships(root)
            build_resume(root, FORGE_ROOT, budget="compact")

            files = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())

            self.assertEqual(len(files), 8)
            self.assertIn("settings.json", files)
            settings = json.loads((root / ".forge" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["schema"], 21)
            self.assertIn("public-menu-runtime", settings["relationship_sets"])

    def test_unconfigured_projects_do_not_pay_relationship_scan_cost(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)

            result = evaluate_relationships(root, [])

            self.assertEqual(result["status"], "NOT_CONFIGURED")
            self.assertFalse(result["scan_bounded"])
            self.assertEqual(result["active_count"], 0)


if __name__ == "__main__":
    unittest.main()

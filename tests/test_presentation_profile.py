from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.authority_baseline import authorize_current_baseline
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.presentation_profile import (
    presentation_profile_summary,
    record_presentation_profile,
    retire_presentation_profile,
)
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.startup import run_forge
from emotivus_forge.core.state import load_settings
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class PresentationProfileTests(ForgeTestCase):
    def _profile(self, root: Path) -> Path:
        path = root / "forge-presentation-profile.json"
        path.write_text(json.dumps({
            "schema": 1,
            "profile_id": "owner-first",
            "title": "Owner-first structured reporting",
            "authority": "owner",
            "audiences": ["owner", "builder", "expert"],
            "default_audience": "owner",
            "structure": {
                "section_order": ["outcome", "what_changed", "validation", "limitations", "roadmap", "downloads", "next_action", "forge_line"]
            },
            "style": {
                "verbosity": "compact",
                "technical_detail": "after-owner-summary",
                "tables": "comparisons-and-status",
                "forge_line": "meaningful-events-only",
                "pass_language": "scope-and-exclusions",
                "tone": "clear, warm, precise, and owner-friendly",
                "headings": "descriptive",
                "bullets": "concise"
            },
            "max_owner_summary_characters": 1400,
            "truth_boundary": "This transfers owner-approved communication structure and claim discipline across AI models; it does not guarantee identical prose quality or style execution.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def test_profile_is_recorded_in_existing_settings_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_presentation_profile(root, FORGE_ROOT, self._profile(root))
            summary = presentation_profile_summary(root)
            self.assertEqual(summary["status"], "PASS")
            self.assertIn("owner-first", summary["instruction"])
            resume = build_resume(root, FORGE_ROOT)
            self.assertIn("Cross-model presentation", resume["markdown"])
            self.assertIn("every PASS states scope and exclusions", resume["markdown"])
            self.assertNotIn("section_order", resume["markdown"])
            self.assertEqual(load_settings(root)["schema"], 21)

    def test_run_forge_recommended_prompt_carries_compact_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_presentation_profile(root, FORGE_ROOT, self._profile(root))
            observed = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(observed["status"], "NOT_RUN")
            authorize_current_baseline(
                root,
                FORGE_ROOT,
                expected_fingerprint=observed["authority_baseline"]["current_fingerprint"],
                authority="owner",
                reason="Reviewed the exact presentation-profile fixture.",
            )
            checked = run_scoped_check(root, FORGE_ROOT, checkpoint=True)
            self.assertEqual(checked["status"], "PASS")
            payload = run_forge(root, FORGE_ROOT)
            prompt = payload["recommended_prompt"]["text"]
            self.assertIn("Presentation:", prompt)
            self.assertLessEqual(len(prompt), 680)

    def test_changed_profile_requires_renewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            profile = self._profile(root)
            record_presentation_profile(root, FORGE_ROOT, profile)
            profile.write_text(profile.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            summary = presentation_profile_summary(root)
            self.assertEqual(summary["status"], "ATTENTION")
            self.assertEqual(summary["attention"], 1)

    def test_new_profile_supersedes_prior_active_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            first = self._profile(root)
            record_presentation_profile(root, FORGE_ROOT, first)
            second = root / "second-profile.json"
            data = json.loads(first.read_text(encoding="utf-8"))
            data["profile_id"] = "builder-first"
            data["title"] = "Builder-first structured reporting"
            data["default_audience"] = "builder"
            second.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            record_presentation_profile(root, FORGE_ROOT, second)
            settings = load_settings(root)
            self.assertEqual(settings["presentation_profiles"]["owner-first"]["lifecycle_status"], "retired")
            self.assertEqual(settings["presentation_profiles"]["builder-first"]["lifecycle_status"], "active")

    def test_retired_profile_is_not_injected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_presentation_profile(root, FORGE_ROOT, self._profile(root))
            retire_presentation_profile(root, "owner-first", "The project communication contract changed.")
            summary = presentation_profile_summary(root)
            self.assertEqual(summary["status"], "NOT_CONFIGURED")
            self.assertEqual(summary["instruction"], "")


if __name__ == "__main__":
    unittest.main()

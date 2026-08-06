from __future__ import annotations

import tempfile
from pathlib import Path

from emotivus_forge.core.recommended_prompt import build_recommended_prompt
from emotivus_forge.core.startup import render_run, run_forge
from tests.support import FORGE_ROOT, ForgeTestCase


class RecommendedPromptTests(ForgeTestCase):
    def test_first_run_emits_copy_ready_prompt_from_exact_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            payload = run_forge(root, FORGE_ROOT)
            recommendation = payload["recommended_prompt"]
            self.assertTrue(recommendation["copy_ready"])
            self.assertEqual(recommendation["kind"], "continue-project")
            self.assertIn("Add a login screen", recommendation["text"])
            self.assertIn("Forge Session Close", recommendation["text"])
            self.assertLessEqual(len(recommendation["text"]), recommendation["max_characters"])
            self.assertIn("**Forge recommends this prompt —**", render_run(payload))

    def test_missing_objective_recommends_confirmation_before_code(self) -> None:
        payload = {
            "status": "ATTENTION",
            "action": "ADOPT + RESUME",
            "objective": {"text": ""},
            "next_action": {"text": ""},
            "continuity": {"status": "not-established"},
            "decision_forks": {"pending": []},
            "attention_counts": {"blocker": 0},
        }
        recommendation = build_recommended_prompt(payload)
        self.assertEqual(recommendation["kind"], "confirm-objective")
        self.assertIn("confirm the current objective before changing code", recommendation["text"])
        # M-G1-4: the no-objective prompt must not promise it surfaced *any*
        # hardcoded secrets — screening is bounded, not a completeness guarantee.
        self.assertNotIn("already surfaced", recommendation["text"])
        self.assertIn("bounded, not exhaustive", recommendation["text"])
        # M-G1-3: a derived, unconfirmed objective is not labeled "confirmed objective".
        derived = build_recommended_prompt({
            "status": "ATTENTION",
            "action": "RESUME",
            "objective": {"text": "Ship v2 to production", "status": "explicit", "source": "README.md"},
            "next_action": {"text": ""},
            "continuity": {"status": "current"},
            "decision_forks": {"pending": []},
            "attention_counts": {"blocker": 0},
        })
        self.assertIn("derived objective (unconfirmed)", derived["text"])
        self.assertNotIn("confirmed objective", derived["text"])

    def test_blocker_recommendation_stops_project_changes(self) -> None:
        payload = {
            "status": "BLOCKED",
            "action": "SCOPED CHECK + RESUME",
            "reason": "The canonical native gate changed and requires renewed authority.",
            "objective": {"text": "Build the account editor."},
            "next_action": {"text": "Build the account editor."},
            "continuity": {"status": "current"},
            "decision_forks": {"pending": []},
            "attention_counts": {"blocker": 1},
            "attention_items": [{
                "severity": "blocker",
                "message": "The canonical native gate changed and requires renewed authority.",
            }],
        }
        recommendation = build_recommended_prompt(payload)
        self.assertEqual(recommendation["kind"], "resolve-blocker")
        self.assertTrue(recommendation["text"].startswith("Stop before changing the project."))
        self.assertIn("requires renewed authority", recommendation["text"])

    def test_pending_decision_fork_preserves_owner_authority(self) -> None:
        payload = {
            "status": "READY",
            "action": "RESUME",
            "objective": {"text": "Build the account editor."},
            "next_action": {"text": "Add the safe save path."},
            "continuity": {"status": "current"},
            "decision_forks": {"pending": [{"id": "storage-format"}]},
            "attention_counts": {"blocker": 0},
        }
        recommendation = build_recommended_prompt(payload)
        self.assertIn("do not resolve pending decisions without the required authority", recommendation["text"])

    def test_needs_project_recommendation_is_plain_language(self) -> None:
        payload = {
            "status": "NEEDS_PROJECT",
            "action": "NONE",
            "objective": {},
            "next_action": {},
            "continuity": {},
            "decision_forks": {},
        }
        recommendation = build_recommended_prompt(payload)
        self.assertEqual(recommendation["kind"], "locate-project")
        self.assertIn("Place the complete target project beside Forge", recommendation["text"])

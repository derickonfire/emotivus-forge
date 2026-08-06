from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.startup import run_forge
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class RunForgeExperienceTests(ForgeTestCase):
    def _context(self, root: Path, **overrides: object) -> Path:
        payload = {
            "schema": "forge-session-context/1",
            "source_kind": "active-ai-distilled",
            "objective": "Repair login persistence without broadening scope.",
            "requested_items": ["Fix login persistence in login.py"],
            "ai_claims": ["Login persistence was completed in login.py"],
            "decisions": ["Keep the existing session architecture"],
            "next_action": "Run the browser persistence fixture.",
        }
        payload.update(overrides)
        path = root.parent / f"{root.name}-session-context.json"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return path

    def test_run_forge_reviews_distilled_context_and_enters_passive_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            run_forge(root, FORGE_ROOT)
            target = root / "login.py"
            target.write_text("remember = True\n", encoding="utf-8")
            context = self._context(root)
            payload = run_forge(root, FORGE_ROOT, session_context_path=str(context))
            self.assertEqual(payload["active_pass"]["status"], "COMPLETE")
            self.assertEqual(payload["forge_brief"]["phase"], "passive")
            self.assertEqual(payload["session_reconciliation"]["conversation_review"], "DISTILLED_CONTEXT_REVIEWED")
            self.assertFalse(payload["session_reconciliation"]["raw_conversation_retained"])
            self.assertEqual(payload["sidecar"]["operation"], "run-forge-active-pass")
            self.assertEqual(payload["sidecar"]["mode"], "development-sidecar")

    def test_run_forge_rejects_raw_transcript_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            context = self._context(root, messages=[{"role": "user", "content": "secret"}])
            with self.assertRaisesRegex(ValueError, "distilled digest"):
                run_forge(root, FORGE_ROOT, session_context_path=str(context))


    def test_run_forge_rejects_session_context_inside_project_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            inside = root / "session-context.json"
            inside.write_text(json.dumps({
                "schema": "forge-session-context/1",
                "objective": "Do work."
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside the project tree"):
                run_forge(root, FORGE_ROOT, session_context_path=str(inside))

    def test_claim_alignment_is_not_semantic_completion_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            run_forge(root, FORGE_ROOT)
            (root / "login.py").write_text("remember = True\n", encoding="utf-8")
            payload = run_forge(root, FORGE_ROOT, session_context_path=str(self._context(root)))
            claim = payload["session_reconciliation"]["claim_alignment"][0]
            self.assertIn(claim["status"], {"CHANGED_PATH_MATCH", "CHECKED_PATH_MATCH"})
            self.assertIn("does not prove semantic completion", claim["boundary"])

    def test_session_close_refreshes_resume_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            run_forge(root, FORGE_ROOT)
            (root / "app.py").write_text("print('changed')\n", encoding="utf-8")
            payload = run_scoped_check(
                root,
                FORGE_ROOT,
                checkpoint=True,
                session_close_data={
                    "session_type": "code-increment",
                    "summary": "Completed one bounded increment.",
                    "completed_work": ["Updated app.py"],
                    "decisions": [],
                    "owner_facts": [],
                    "unresolved_risks": ["Browser behavior not run."],
                    "next_action": "Run browser evidence.",
                    "interaction_telemetry": {},
                    "field_observation_path": "",
                },
            )
            close = payload["session_close"]
            self.assertTrue(close["resume_refreshed"])
            resume = (root / ".forge" / "resume.md").read_text(encoding="utf-8")
            self.assertIn("Run browser evidence.", resume)

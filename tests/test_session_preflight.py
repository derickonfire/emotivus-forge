from __future__ import annotations

import tempfile
from pathlib import Path

from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.session_close import build_session_close_preflight, close_session
from tests.support import FORGE_ROOT, ForgeTestCase


class SessionClosePreflightTests(ForgeTestCase):
    def test_preflight_rejects_next_action_already_listed_as_completed(self) -> None:
        preflight = build_session_close_preflight(
            session_type="code-increment",
            next_action="Add the profile editor",
            completed_work=["Add the profile editor"],
            decisions=[],
            owner_facts=[],
            unresolved_risks=[],
            check_payload={"status": "PASS"},
        )
        self.assertEqual(preflight["status"], "BLOCKED")
        self.assertIn("also listed as completed", preflight["errors"][0])

    def test_release_candidate_without_pass_is_recorded_with_explicit_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            result = close_session(
                root,
                FORGE_ROOT,
                session_type="release-candidate",
                next_action="Run the release verification gate.",
                check_payload={"status": "FAIL", "claim": "Scoped Check FAIL", "findings": []},
            )
            self.assertEqual(result["preflight"]["status"], "ATTENTION")
            self.assertIn("does not certify", result["preflight"]["warnings"][0])

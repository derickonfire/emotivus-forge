from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.lifecycle import (
    lifecycle_transition_summary,
    record_lifecycle_transition,
)
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from tests.support import FORGE_ROOT, ForgeTestCase


class LifecycleTransitionTests(ForgeTestCase):
    def _write(self, root: Path, **overrides: object) -> str:
        payload = {
            "schema": 1,
            "component": "legacy-secret-scanner",
            "disposition": "replace",
            "authority": "owner",
            "reason": "Superseded by the ranked ecosystem resolver.",
            "successor": "ecosystem-resolver",
            "preserved_invariants": ["exact identity", "secret BLOCK coverage"],
        }
        payload.update(overrides)
        (root / "lifecycle-transition.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return "lifecycle-transition.json"

    def test_replace_transition_is_recorded_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            result = record_lifecycle_transition(root, FORGE_ROOT, self._write(root))
            self.assertEqual(result["disposition"], "replace")
            self.assertTrue(result["event_id"])
            summary = lifecycle_transition_summary(root)
            self.assertEqual(summary["transition_count"], 1)
            self.assertEqual(summary["by_disposition"].get("replace"), 1)
            self.assertEqual(summary["components"]["legacy-secret-scanner"]["successor"], "ecosystem-resolver")

    def test_retain_transition_needs_no_successor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            record_lifecycle_transition(root, FORGE_ROOT, self._write(root, disposition="retain", successor="", preserved_invariants=[]))
            self.assertEqual(lifecycle_transition_summary(root)["by_disposition"].get("retain"), 1)

    def test_replace_requires_successor_and_preserved_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            with self.assertRaisesRegex(ValueError, "successor"):
                record_lifecycle_transition(root, FORGE_ROOT, self._write(root, successor=""))
            with self.assertRaisesRegex(ValueError, "invariants"):
                record_lifecycle_transition(root, FORGE_ROOT, self._write(root, preserved_invariants=[]))

    def test_invalid_disposition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            with self.assertRaisesRegex(ValueError, "disposition"):
                record_lifecycle_transition(root, FORGE_ROOT, self._write(root, disposition="delete"))

    def test_resume_surfaces_lifecycle_transitions_only_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self.assertNotIn("Component lifecycle:", build_resume(root, FORGE_ROOT, budget="compact")["markdown"])
            record_lifecycle_transition(root, FORGE_ROOT, self._write(root))
            self.assertIn("Component lifecycle:", build_resume(root, FORGE_ROOT, budget="compact")["markdown"])

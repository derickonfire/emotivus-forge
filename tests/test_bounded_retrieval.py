from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.bounded_retrieval import normalize_text, retrieve_continuity, token_similarity
from emotivus_forge.core.continuity_register import record_continuity_register
from emotivus_forge.core.ledger import record_event
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.state import load_settings, load_state
from tests.support import FORGE_ROOT, ForgeTestCase


class BoundedRetrievalTests(ForgeTestCase):
    def _root(self, directory: str) -> Path:
        root = Path(directory)
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        (root / "DECISIONS.md").write_text("# Decisions\n\nUse exact parent identity for every continuation.\n", encoding="utf-8")
        contract = root / "continuity.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "register_id": "continuity-main",
            "authority": "owner",
            "supersedes_register_id": "",
            "change_reason": "",
            "facts": [
                {
                    "fact_id": "parent.identity",
                    "key": "parent.identity",
                    "value": "Every continuation must bind the exact parent package and normalized tree.",
                    "trust": "owner-declared",
                    "rationale": "This prevents same-version branches from being treated as one history.",
                    "impact": "Resume and package intake must preserve parent identity.",
                    "change_reason": "",
                    "support": [
                        {"kind": "contract-declaration", "note": "The owner explicitly declared the lineage rule."},
                        {"kind": "project-file", "path": "DECISIONS.md"},
                    ],
                    "truth_boundary": "This records the governing lineage rule; it does not prove any incoming package satisfies it.",
                }
            ],
            "gaps": [
                {
                    "gap_id": "browser.shared-tablet",
                    "question": "Does the shared-tablet flow work on a real target device?",
                    "priority": "blocker",
                    "status": "open",
                    "blocking_scopes": ["ship", "release"],
                    "required_evidence": "A current exact-package shared-tablet browser and device receipt.",
                    "owner": "release reviewer",
                    "resolution": "",
                    "evidence": [],
                    "truth_boundary": "This records missing device evidence and does not predict whether the flow will pass.",
                }
            ],
            "retired_fact_keys": [],
            "retired_gap_ids": [],
            "truth_boundary": "This governs compact facts and gaps without retaining raw conversation history or changing project authority.",
        }, indent=2) + "\n", encoding="utf-8")
        record_continuity_register(root, FORGE_ROOT, contract)
        record_event(root, "session-close", {
            "session_type": "decision-checkpoint",
            "completed_work": ["Reviewed the lineage collision."],
            "decisions": [{"text": "Treat unmatched parents as merge candidates.", "rationale": "Automatic adoption would launder unknown edits."}],
            "owner_facts": [{"text": "Continuity is a core Forge mission.", "impact": "Resume must remain compact and traceable."}],
            "unresolved_risks": ["A stale route map may still overstate browser coverage."],
            "next_action": {"text": "Implement traceable bounded retrieval."},
            "continuity_snapshot": {},
            "checks": {},
        }, source="owner")
        return root

    def test_normalization_and_similarity_preserve_technical_tokens(self) -> None:
        self.assertIn("parent.sha256", normalize_text("Parent.SHA256 / Build-ID"))
        self.assertGreater(token_similarity("exact parent package", "bind exact parent package identity"), 0.7)

    def test_retrieval_selects_relevant_authoritative_fact_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            result = retrieve_continuity(root, "exact parent package lineage", result_budget=5)
            ids = [item["stable_id"] for item in result["results"]]
            self.assertIn("fact:parent.identity", ids)
            selected = next(item for item in result["results"] if item["stable_id"] == "fact:parent.identity")
            self.assertEqual(selected["trust"], "owner-declared")
            self.assertTrue(selected["selection_reasons"])
            self.assertTrue(result["relationship_trace"]["edges"])

    def test_blocker_gap_never_fades_under_unrelated_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            result = retrieve_continuity(root, "completely unrelated typography", result_budget=2)
            ids = [item["stable_id"] for item in result["results"]]
            self.assertIn("gap:browser.shared-tablet", ids)
            gap = next(item for item in result["results"] if item["stable_id"] == "gap:browser.shared-tablet")
            self.assertIn("never-fade", gap["selection_reasons"])

    def test_retrieval_does_not_mutate_authority_or_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            settings_before = json.dumps(load_settings(root), sort_keys=True)
            state_before = json.dumps(load_state(root).get("authority_baseline", {}), sort_keys=True)
            retrieve_continuity(root, "lineage", result_budget=4)
            self.assertEqual(json.dumps(load_settings(root), sort_keys=True), settings_before)
            self.assertEqual(json.dumps(load_state(root).get("authority_baseline", {}), sort_keys=True), state_before)

    def test_stale_support_remains_visible_and_is_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            (root / "DECISIONS.md").write_text("changed\n", encoding="utf-8")
            result = retrieve_continuity(root, "parent identity", result_budget=5)
            fact = next(item for item in result["results"] if item["stable_id"] == "fact:parent.identity")
            self.assertEqual(fact["support_status"], "stale")

    def test_resume_exposes_bounded_retrieval_and_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            resume = build_resume(root, FORGE_ROOT, budget="compact", query="shared tablet browser evidence")
            self.assertEqual(resume["bounded_retrieval"]["query"], "shared tablet browser evidence")
            self.assertIn("Traceable bounded retrieval", resume["markdown"])
            self.assertLessEqual(resume["bounded_retrieval"]["result_count"], 6)


if __name__ == "__main__":
    import unittest
    unittest.main()

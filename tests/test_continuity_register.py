from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.continuity_register import (
    assess_continuity_register,
    record_continuity_register,
    retire_continuity_register,
)
from tests.support import FORGE_ROOT, ForgeTestCase
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.ship_claims import assess_ship_claims
from emotivus_forge.core.sidecar import update_sidecar_status
from emotivus_forge.core.lineage import exact_directory_tree, lineage_summary, record_project_lineage


class ContinuityRegisterTests(ForgeTestCase):

    def _root(self, directory: str) -> Path:
        root = Path(directory)
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        return root
    def _contract(self, root: Path, *, register_id: str = "continuity-main", supersedes: str = "", changed_value: str = "Forge preserves project truth.", trust: str = "owner-declared") -> Path:
        (root / "README.md").write_text("# Project\nContinuity matters.\n", encoding="utf-8")
        contract = {
            "schema": 1,
            "register_id": register_id,
            "authority": "owner",
            "supersedes_register_id": supersedes,
            "change_reason": "Updated after explicit owner review." if supersedes else "",
            "facts": [
                {
                    "fact_id": "mission.continuity",
                    "key": "mission.continuity",
                    "value": changed_value,
                    "trust": trust,
                    "rationale": "This governs continuity design and roadmap priority.",
                    "impact": "Resume and Check must preserve it.",
                    "change_reason": "Owner refined the continuity mission." if supersedes and changed_value != "Forge preserves project truth." else "",
                    "support": [
                        {"kind": "contract-declaration", "note": "The owner explicitly declared this fact."},
                        {"kind": "project-file", "path": "README.md"},
                    ],
                    "truth_boundary": "This records the project mission; it does not prove every implementation satisfies it.",
                }
            ],
            "gaps": [
                {
                    "gap_id": "validation.real-cold-sessions",
                    "question": "Do real matched cold sessions improve continuity outcomes?",
                    "priority": "blocker",
                    "status": "open",
                    "blocking_scopes": ["ship", "roadmap"],
                    "required_evidence": "Representative matched trials with exact task and parent identity.",
                    "owner": "project owner",
                    "resolution": "",
                    "evidence": [],
                    "truth_boundary": "The gap records missing evidence and does not predict the result.",
                }
            ],
            "retired_fact_keys": [],
            "retired_gap_ids": [],
            "truth_boundary": "This register governs compact project facts and known gaps; it is not a transcript, semantic memory database, or release authorization.",
        }
        path = root / f"{register_id}.json"
        path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        return path

    def test_register_contract_does_not_create_false_lineage_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            (root / "README.md").write_text("# Project\nContinuity matters.\n", encoding="utf-8")
            lineage_path = root / "lineage.json"
            tree = exact_directory_tree(root, FORGE_ROOT, exclude_paths=[lineage_path.name])
            lineage_path.write_text(json.dumps({
                "schema": 1,
                "lineage_id": "continuity-lineage",
                "authority": "owner",
                "declared_version": "1.0.0",
                "build_id": "continuity-build",
                "relationship": "initial",
                "current": {"tree_sha256": tree["tree_sha256"], "tree_file_count": tree["file_count"]},
                "collision_declaration": {},
                "truth_boundary": "The owner declares this exact neutral lineage while Forge proves only normalized byte identity."
            }, indent=2) + "\n", encoding="utf-8")
            record_project_lineage(root, FORGE_ROOT, lineage_path)
            path = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, path)
            self.assertEqual(lineage_summary(root, FORGE_ROOT)["status"], "CURRENT")

    def test_records_trust_ranked_facts_and_open_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            path = self._contract(root)
            record = record_continuity_register(root, FORGE_ROOT, path)
            self.assertEqual(record["status"], "active")
            summary = assess_continuity_register(root)
            self.assertEqual(summary["status"], "CURRENT")
            self.assertEqual(summary["fact_count"], 1)
            self.assertEqual(summary["blocker_gap_count"], 1)
            self.assertEqual(summary["ship_blocking_gap_count"], 1)
            self.assertEqual(summary["trust_counts"]["owner-declared"], 1)
            passport = build_passport(root, FORGE_ROOT)
            self.assertEqual(passport["continuity_register"]["status"], "CURRENT")

    def test_project_evidenced_fact_requires_project_file_support(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            path = self._contract(root, trust="project-evidenced")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["facts"][0]["support"] = [{"kind": "contract-declaration", "note": "Only a declaration remains."}]
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires project-file support"):
                record_continuity_register(root, FORGE_ROOT, path)

    def test_support_drift_marks_register_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            path = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, path)
            (root / "README.md").write_text("changed\n", encoding="utf-8")
            summary = assess_continuity_register(root)
            self.assertEqual(summary["status"], "STALE")
            self.assertTrue(summary["stale_controls"])

    def test_changed_fact_cannot_be_lower_trust(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            first = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, first)
            second = self._contract(root, register_id="continuity-next", supersedes="continuity-main", changed_value="An agent guessed a different mission.", trust="agent-inferred")
            with self.assertRaisesRegex(ValueError, "lower-trust"):
                record_continuity_register(root, FORGE_ROOT, second)

    def test_open_gap_cannot_disappear_without_resolution_or_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            first = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, first)
            second = self._contract(root, register_id="continuity-next", supersedes="continuity-main")
            data = json.loads(second.read_text(encoding="utf-8"))
            data["gaps"] = []
            second.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Open continuity gap"):
                record_continuity_register(root, FORGE_ROOT, second)

    def test_register_source_drift_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            path = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, path)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["truth_boundary"] += " Changed."
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            self.assertEqual(assess_continuity_register(root)["status"], "APPROVAL_REQUIRED")

    def test_retirement_is_separate_and_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            path = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, path)
            retired = retire_continuity_register(root, "continuity-main", "The owner replaced this continuity model.")
            self.assertEqual(retired["status"], "retired")
            self.assertEqual(assess_continuity_register(root)["status"], "NOT_DECLARED")

    def test_resume_surfaces_governed_facts_gaps_and_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            path = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, path)
            resume = build_resume(root, FORGE_ROOT, budget="compact")
            self.assertEqual(resume["continuity_register"]["status"], "CURRENT")
            self.assertEqual(resume["sidecar"]["mode"], "development-sidecar")
            self.assertIn("Governed continuity facts", resume["markdown"])
            self.assertIn("Known continuity gaps", resume["markdown"])

    def test_ship_reports_explicit_ship_blocking_gap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            path = self._contract(root)
            record_continuity_register(root, FORGE_ROOT, path)
            claims = assess_ship_claims(root, FORGE_ROOT)
            continuity = claims["levels"][0]
            requirements = {row["requirement_id"]: row for row in continuity["requirements"]}
            self.assertEqual(requirements["continuity-register-current"]["status"], "PASS")
            self.assertEqual(requirements["ship-blocking-knowledge-gaps-resolved"]["status"], "FAIL")

    def test_sidecar_status_is_observational_and_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            status = update_sidecar_status(
                root, mode="evidence-analysis", operation="analysis", work_scope="Review field evidence",
                authority_status="CURRENT", unexpected_mutations=2, check_status="NOT_RUN",
            )
            self.assertEqual(status["mode"], "evidence-analysis")
            self.assertEqual(status["unexpected_mutations"], 2)
            self.assertFalse(status["authority_changed_by_operation"])
            self.assertIn("does not monitor the chat", status["truth_boundary"])


if __name__ == "__main__":
    import unittest
    unittest.main()

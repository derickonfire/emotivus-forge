from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core import code_orientation as co
from emotivus_forge.core.orientation import orient_project
from tests.support import ForgeTestCase


def _tree(root: Path) -> None:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "lib").mkdir(parents=True, exist_ok=True)
    (root / "app" / "login.py").write_text("import session\nsession.start()\n", encoding="utf-8")
    (root / "app" / "profile.py").write_text("import session\nsession.load()\n", encoding="utf-8")
    (root / "lib" / "session.py").write_text("def start(): pass\ndef load(): pass\n", encoding="utf-8")


def _events(*groups: list[str]) -> list[dict[str, object]]:
    return [{"paths": list(group)} for group in groups]


class CodeOrientationTests(ForgeTestCase):
    def test_every_view_declares_no_authority(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _tree(root)
            out = co.orient_code(root, ["app/login.py", "lib/session.py"], _events(["app/login.py"]))
        self.assertEqual(out["authority"], "none")
        self.assertEqual(out["evidence_tier"], "inferred")
        for flag in ("advances_baseline", "qualifies_check", "authorizes_release", "becomes_governed_fact"):
            self.assertFalse(out[flag], f"{flag} must be false")

    def test_every_row_carries_authority_and_tier(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _tree(root)
            out = co.orient_code(
                root, ["app/login.py", "app/profile.py", "lib/session.py"],
                _events(["app/login.py", "lib/session.py"], ["app/login.py", "lib/session.py"]),
            )
        rows = out["centrality"]["top"] + out["active_zones"]["top"] + out["coupling"]["top"]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["authority"], "none")
            self.assertEqual(row["evidence_tier"], "inferred")

    def test_centrality_counts_referencing_files_not_self(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _tree(root)
            result = co.compute_centrality(root, ["app/login.py", "app/profile.py", "lib/session.py"])
        scores = {row["path"]: row["referenced_by_count"] for row in result["top"]}
        self.assertEqual(scores["lib/session.py"], 2)
        self.assertEqual(scores["app/login.py"], 0)

    def test_a_file_referencing_only_itself_scores_zero(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "solo.py").write_text("solo = 1\nprint(solo)\n", encoding="utf-8")
            result = co.compute_centrality(root, ["solo.py"])
        self.assertEqual(result["top"][0]["referenced_by_count"], 0)

    def test_ambiguous_stems_are_flagged_not_silently_credited(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "a").mkdir(); (root / "b").mkdir()
            (root / "a" / "utils.py").write_text("x = 1\n", encoding="utf-8")
            (root / "b" / "utils.py").write_text("y = 2\n", encoding="utf-8")
            (root / "main.py").write_text("import utils\n", encoding="utf-8")
            result = co.compute_centrality(root, ["a/utils.py", "b/utils.py", "main.py"])
        flagged = {row["path"]: row["ambiguous_stem"] for row in result["top"]}
        self.assertTrue(flagged["a/utils.py"])
        self.assertTrue(flagged["b/utils.py"])
        self.assertFalse(flagged["main.py"])

    def test_active_zones_aggregate_ledger_paths_by_directory(self) -> None:
        result = co.compute_active_zones(_events(["app/login.py"], ["app/profile.py"], ["lib/session.py"]))
        zones = {row["zone"]: row["event_count"] for row in result["top"]}
        self.assertEqual(zones["app"], 2)
        self.assertEqual(zones["lib"], 1)

    def test_absent_ledger_reports_a_knowledge_gap_not_a_zero_claim(self) -> None:
        zones = co.compute_active_zones(None)
        coupling = co.compute_coupling(None)
        self.assertEqual(zones["top"], [])
        self.assertIn("knowledge_gap", zones)
        self.assertIn("unknown", zones["knowledge_gap"])
        self.assertIn("knowledge_gap", coupling)

    def test_orientation_never_uses_filesystem_timestamps(self) -> None:
        source = (Path(co.__file__)).read_text(encoding="utf-8")
        for forbidden in ("st_mtime", "getmtime", "st_ctime", "st_atime"):
            self.assertNotIn(forbidden, source, "orientation must not infer activity from timestamps")

    def test_coupling_requires_repeated_co_change(self) -> None:
        once = co.compute_coupling(_events(["a.py", "b.py"]))
        twice = co.compute_coupling(_events(["a.py", "b.py"], ["a.py", "b.py"]))
        self.assertEqual(once["top"], [])
        self.assertEqual(twice["top"][0]["paths"], ["a.py", "b.py"])
        self.assertEqual(twice["top"][0]["co_change_count"], 2)

    def test_sweeping_events_are_skipped_rather_than_coupling_everything(self) -> None:
        wide = [f"file{i}.py" for i in range(80)]
        result = co.compute_coupling(_events(wide, wide))
        self.assertEqual(result["top"], [])
        self.assertEqual(result["wide_events_skipped"], 2)

    def test_results_are_deterministically_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _tree(root)
            paths = ["app/login.py", "app/profile.py", "lib/session.py"]
            events = _events(["app/login.py", "lib/session.py"], ["app/login.py", "lib/session.py"])
            first = co.orient_code(root, paths, events)
            second = co.orient_code(root, paths, events)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_centrality_respects_the_file_budget_and_reports_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paths = []
            for i in range(12):
                name = f"m{i}.py"; (root / name).write_text("x = 1\n", encoding="utf-8"); paths.append(name)
            result = co.compute_centrality(root, paths, max_files=5)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["files_considered"], 5)

    def test_oversized_and_unreadable_files_are_skipped_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "big.py").write_text("x" * 5000, encoding="utf-8")
            (root / "bin.py").write_bytes(b"\xff\xfe\x00\x01")
            result = co.compute_centrality(root, ["big.py", "bin.py"], max_file_bytes=100)
        self.assertEqual(result["files_scanned"], 0)
        self.assertEqual(len(result["top"]), 2)

    def test_non_source_files_are_excluded_from_centrality(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "notes.md").write_text("session\n", encoding="utf-8")
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            result = co.compute_centrality(root, ["notes.md", "app.py"])
        self.assertEqual([row["path"] for row in result["top"]], ["app.py"])

    def test_malformed_events_do_not_raise(self) -> None:
        bad = [{"paths": "not-a-list"}, {}, {"paths": [1, 2, None]}, {"paths": ["ok.py"]}]
        self.assertIsInstance(co.compute_active_zones(bad)["top"], list)
        self.assertIsInstance(co.compute_coupling(bad)["top"], list)

    def test_truth_boundary_is_present_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = co.orient_code(Path(raw), [], None)
        self.assertIn("never means authorized", out["truth_boundary"])
        self.assertTrue(out["knowledge_gaps"])

    def test_orient_project_exposes_code_orientation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _tree(root); (root / ".forge").mkdir()
            (root / ".forge" / "ledger.jsonl").write_text(
                json.dumps({"paths": ["app/login.py", "lib/session.py"]}) + "\n"
                + json.dumps({"paths": ["app/login.py", "lib/session.py"]}) + "\n",
                encoding="utf-8")
            out = orient_project(root, root / ".forge", {})
        result = out["code_orientation"]
        self.assertEqual(result["authority"], "none")
        self.assertTrue(result["active_zones"]["top"])
        self.assertTrue(result["coupling"]["top"])

    def test_orient_project_without_ledger_reports_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _tree(root); (root / ".forge").mkdir()
            out = orient_project(root, root / ".forge", {})
        self.assertTrue(out["code_orientation"]["knowledge_gaps"])

    def test_corrupt_ledger_lines_are_ignored_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _tree(root); (root / ".forge").mkdir()
            (root / ".forge" / "ledger.jsonl").write_text(
                "{not json\n" + json.dumps({"paths": ["app/login.py"]}) + "\n\n", encoding="utf-8")
            out = orient_project(root, root / ".forge", {})
        self.assertEqual(out["code_orientation"]["active_zones"]["events_considered"], 1)

    def test_orientation_adds_no_public_command_and_no_state_file(self) -> None:
        from emotivus_forge.core import paths as forge_paths
        source = Path(co.__file__).read_text(encoding="utf-8")
        self.assertNotIn("write_json", source)
        self.assertNotIn("open(", source.replace("path.open(", ""))
        self.assertEqual(len(forge_paths.STATE_FILE_NAMES), 8)

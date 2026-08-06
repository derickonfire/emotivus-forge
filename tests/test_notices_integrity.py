from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from emotivus_forge.cli import main as cli_main
from emotivus_forge.core.common import read_jsonl_report
from emotivus_forge.core.knowledge import update_knowledge_index
from emotivus_forge.core.notices import issue_notice
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.state import load_settings, load_state
from emotivus_forge.core.storage import inspect_state_integrity, state_transaction
from emotivus_forge.core.state import CORE_STATE_SCHEMA
from tests.support import FORGE_ROOT, ForgeTestCase


class NoticeAndIntegrityTests(ForgeTestCase):
    def test_cli_json_exposes_one_line_ai_notice_and_human_output_uses_forge_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = cli_main(["run", str(root), "--json"])
            self.assertEqual(code, 0)
            payload = json.loads(stream.getvalue())
            notice = payload["ai_notice"]
            self.assertTrue(notice["speak"])
            self.assertEqual(notice["level"], "notice")
            self.assertIn("learned", notice["summary"].lower())

            # First adoption is not itself a warning. A later stale objective remains
            # visible in human output with the compact brand prefix.
            (root / "BACKLOG.md").unlink()
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = cli_main(["resume", str(root)])
            self.assertEqual(code, 0)
            self.assertIn("Forge —", stream.getvalue())

    def test_notice_ids_dedupe_repeated_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            first = issue_notice(root, level="warning", summary="A durable risk remains.", category="risk", event_key="risk-1")
            second = issue_notice(root, level="warning", summary="A durable risk remains.", category="risk", event_key="risk-1")
            self.assertTrue(first["speak"])
            self.assertFalse(second["speak"])
            self.assertTrue(second["repeated"])
            self.assertEqual(first["id"], second["id"])

    def test_quiet_mode_suppresses_notices_but_not_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            settings_path = root / ".forge" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["notice_mode"] = "quiet"
            settings_path.write_text(json.dumps(settings) + "\n", encoding="utf-8")
            routine = issue_notice(root, level="notice", summary="One project fact was learned.", category="knowledge", event_key="k1")
            warning = issue_notice(root, level="warning", summary="A safety boundary needs attention.", category="risk", event_key="r1")
            self.assertFalse(routine["speak"])
            self.assertTrue(warning["speak"])

    def test_malformed_json_blocks_without_overwriting_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            state_path = root / ".forge" / "state.json"
            damaged = '{"schema": 2, "snapshot": '
            state_path.write_text(damaged, encoding="utf-8")
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = cli_main(["run", str(root), "--json"])
            self.assertEqual(code, 1)
            payload = json.loads(stream.getvalue())
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertIn("preserved", payload["preservation"].lower())
            self.assertEqual(state_path.read_text(encoding="utf-8"), damaged)

    def test_jsonl_reader_recovers_valid_rows_and_reports_bad_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            path.write_text('{"id":"one"}\nnot-json\n{"id":"two"}\n', encoding="utf-8")
            rows, issues = read_jsonl_report(path)
            self.assertEqual([row["id"] for row in rows], ["one", "two"])
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].line, 2)

    def test_integrity_report_exposes_recovered_jsonl_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            ledger = root / ".forge" / "ledger.jsonl"
            ledger.write_text(ledger.read_text(encoding="utf-8") + "broken\n", encoding="utf-8")
            report = inspect_state_integrity(root)
            self.assertEqual(report["status"], "BLOCKED")
            issue = next(item for item in report["issues"] if item["path"] == "ledger.jsonl")
            self.assertGreater(issue["recovered_records"], 0)

    def test_state_transaction_rolls_back_all_eight_core_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            before = {
                path.name: path.read_bytes()
                for path in (root / ".forge").iterdir()
                if path.is_file()
            }
            with self.assertRaises(RuntimeError):
                with state_transaction(root):
                    (root / ".forge" / "state.json").write_text('{"schema":2,"changed":true}\n', encoding="utf-8")
                    (root / ".forge" / "passport.json").write_text('{"schema":1,"changed":true}\n', encoding="utf-8")
                    raise RuntimeError("simulate interrupted multi-file operation")
            after = {
                path.name: path.read_bytes()
                for path in (root / ".forge").iterdir()
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertNotIn(".operation.lock", after)

    def test_schema_one_settings_migrates_to_twelve_and_state_to_three(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            settings_path = root / ".forge" / "settings.json"
            state_path = root / ".forge" / "state.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["schema"] = 1
            settings.pop("notice_mode", None)
            settings["adoption_file_budget"] = 321
            settings_path.write_text(json.dumps(settings) + "\n", encoding="utf-8")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["schema"] = 1
            state.pop("notices", None)
            state.pop("knowledge", None)
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

            migrated_settings = load_settings(root)
            migrated_state = load_state(root)
            self.assertEqual(migrated_settings["schema"], 21)
            self.assertEqual(migrated_settings["notice_mode"], "standard")
            self.assertEqual(migrated_settings["adoption_file_budget"], 321)
            self.assertIn("project_identity", migrated_settings)
            self.assertIn("project_events", migrated_settings)
            self.assertIn("ledger_assertions", migrated_settings)
            self.assertIn("check_qualifications", migrated_settings)
            self.assertIn("artifact_provenance", migrated_settings)
            self.assertIn("deployable_boundaries", migrated_settings)
            self.assertIn("canonical_claims", migrated_settings)
            self.assertIn("relationship_sets", migrated_settings)
            self.assertIn("runtime_state_matrices", migrated_settings)
            self.assertEqual(migrated_state["schema"], CORE_STATE_SCHEMA)
            self.assertIn("notices", migrated_state)
            self.assertIn("knowledge", migrated_state)
            self.assertEqual(migrated_state["authority_baseline"]["status"], "not-established")

    def test_knowledge_delta_marks_missing_support_stale_instead_of_false(self) -> None:
        existing = {
            "knowledge_index": {
                "orientation.stacks": {
                    "key": "orientation.stacks",
                    "label": "observed technology stacks",
                    "value": ["php"],
                    "status": "observed",
                    "support": "bounded project snapshot",
                    "support_fingerprint": "old",
                    "first_seen_utc": "2026-01-01T00:00:00+00:00",
                    "last_seen_utc": "2026-01-01T00:00:00+00:00",
                }
            }
        }
        current = {
            "identity": {"name": "Example", "status": "inferred", "name_source": "directory"},
            "orientation": {"stacks": []},
            "objective": {},
            "native_gate": {},
            "safety": {},
        }
        index, delta = update_knowledge_index(existing, current)
        self.assertEqual(delta["stale"][0]["key"], "orientation.stacks")
        self.assertEqual(index["orientation.stacks"]["status"], "stale")
        self.assertNotIn("false", delta["stale"][0]["reason"].lower())

class LedgerIntegrityTests(ForgeTestCase):
    def test_new_ledger_events_are_hash_chained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            rows = [json.loads(line) for line in (root / ".forge" / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertGreaterEqual(len(rows), 1)
            self.assertTrue(all(row.get("event_hash") for row in rows))
            for previous, current in zip(rows, rows[1:]):
                self.assertEqual(current["previous_event_hash"], previous["event_hash"])

    def test_ledger_content_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            ledger = root / ".forge" / "ledger.jsonl"
            rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
            rows[0]["payload"]["files_observed"] = 999999
            ledger.write_text("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")
            report = inspect_state_integrity(root)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(any("hash" in item["message"] for item in report["issues"]))

class StateShapeValidationTests(ForgeTestCase):
    def test_invalid_settings_shape_is_blocked_before_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            path = root / ".forge" / "settings.json"
            settings = json.loads(path.read_text(encoding="utf-8"))
            settings["notice_mode"] = "loud-and-constant"
            path.write_text(json.dumps(settings) + "\n", encoding="utf-8")
            report = inspect_state_integrity(root)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(any("notice_mode" in item["message"] for item in report["issues"]))

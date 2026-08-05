from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core import session_adapters as sa
from emotivus_forge.core.state import CORE_STATE_SCHEMA, SETTINGS_SCHEMA, load_settings
from tests.support import FORGE_ROOT, ForgeTestCase


class SessionAdapterTests(ForgeTestCase):
    def test_default_configuration_is_entirely_off(self) -> None:
        defaults = sa.default_settings()
        self.assertFalse(defaults["enabled"])
        for event in sa.ADAPTER_EVENTS:
            self.assertFalse(defaults["events"][event]["enabled"])

    def test_fresh_settings_ship_adapters_off(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            settings = load_settings(Path(raw))
            self.assertIn("session_adapters", settings)
            self.assertFalse(settings["session_adapters"]["enabled"])

    def test_global_switch_dominates_per_event_switches(self) -> None:
        config = {
            "enabled": False,
            "events": {event: {"enabled": True} for event in sa.ADAPTER_EVENTS},
        }
        resolved = sa.resolve(config)
        self.assertFalse(resolved["globally_enabled"])
        self.assertEqual(resolved["active_events"], [])
        for event in sa.ADAPTER_EVENTS:
            self.assertTrue(resolved["events"][event]["requested"])
            self.assertFalse(resolved["events"][event]["active"])

    def test_enabled_adapters_resolve_active(self) -> None:
        config = {"enabled": True, "events": {sa.MILESTONE: {"enabled": True}}}
        resolved = sa.resolve(config)
        self.assertEqual(resolved["active_events"], [sa.MILESTONE])
        self.assertFalse(resolved["events"][sa.SESSION_START]["active"])

    def test_only_the_three_declared_events_exist(self) -> None:
        self.assertEqual(
            set(sa.ADAPTER_EVENTS), {sa.SESSION_START, sa.MILESTONE, sa.SESSION_END}
        )
        problems = sa.validate({"enabled": True, "events": {"deploy": {"enabled": True}}})
        self.assertTrue(any(item["event"] == "deploy" for item in problems))

    def test_adapter_cannot_map_a_sixth_command(self) -> None:
        problems = sa.validate(
            {"enabled": True, "events": {sa.MILESTONE: {"public_command": "deploy"}}}
        )
        self.assertTrue(any("sixth" in item["problem"] for item in problems))

    def test_mapped_commands_stay_within_the_five_public_commands(self) -> None:
        self.assertEqual(sa.PUBLIC_COMMANDS, ("help", "adopt", "resume", "check", "ship"))
        for event in sa.ADAPTER_EVENTS:
            command = sa.EVENT_CONTRACT[event]["public_command"]
            self.assertTrue(command is None or command in sa.PUBLIC_COMMANDS)

    def test_session_end_is_guidance_only(self) -> None:
        self.assertEqual(sa.EVENT_CONTRACT[sa.SESSION_END]["mode"], "guide")
        problems = sa.validate(
            {"enabled": True, "events": {sa.SESSION_END: {"mode": "invoke"}}}
        )
        self.assertTrue(any("guidance only" in item["problem"] for item in problems))

    def test_authority_transitions_are_rejected_not_ignored(self) -> None:
        for effect in ("advance_baseline", "approve_changes", "authorize_release", "merge_files"):
            problems = sa.validate(
                {"enabled": True, "events": {sa.MILESTONE: {"effects": [effect]}}}
            )
            self.assertTrue(
                any(effect in item["problem"] for item in problems),
                f"{effect} must be rejected",
            )

    def test_invalid_configuration_cannot_resolve_active(self) -> None:
        config = {
            "enabled": True,
            "events": {sa.MILESTONE: {"enabled": True, "effects": ["authorize_release"]}},
        }
        resolved = sa.resolve(config)
        self.assertTrue(resolved["problems"])
        self.assertFalse(resolved["globally_enabled"])
        self.assertEqual(resolved["active_events"], [])

    def test_contract_declares_no_daemon_and_no_prompt_rewriting(self) -> None:
        contract = sa.contract()
        self.assertFalse(contract["runs_continuously"])
        self.assertFalse(contract["installs_hooks"])
        self.assertFalse(contract["rewrites_prompts"])
        self.assertEqual(contract["process_model"], "host-invoked-one-shot")

    def test_contract_declares_no_new_command_or_state_file(self) -> None:
        contract = sa.contract()
        self.assertFalse(contract["adds_public_command"])
        self.assertFalse(contract["adds_state_file"])
        self.assertEqual(len(contract["public_commands"]), 5)

    def test_contract_default_state_is_off(self) -> None:
        contract = sa.contract()
        self.assertEqual(contract["default_state"], "off")
        self.assertFalse(contract["globally_enabled"])
        self.assertEqual(contract["active_events"], [])

    def test_contract_carries_an_explicit_truth_boundary(self) -> None:
        contract = sa.contract()
        self.assertIn("authority", contract["truth_boundary"])
        self.assertIn("no more", contract["truth_boundary"])

    def test_contract_is_deterministic(self) -> None:
        config = {"enabled": True, "events": {sa.SESSION_START: {"enabled": True}}}
        self.assertEqual(json.dumps(sa.contract(config), sort_keys=True),
                         json.dumps(sa.contract(config), sort_keys=True))

    def test_adapters_persist_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            before = sorted(p.name for p in root.rglob("*"))
            sa.contract({"enabled": True, "events": {sa.MILESTONE: {"enabled": True}}})
            self.assertEqual(sorted(p.name for p in root.rglob("*")), before)

    def test_settings_schema_advanced_to_twenty_one(self) -> None:
        self.assertEqual(SETTINGS_SCHEMA, 21)
        self.assertEqual(CORE_STATE_SCHEMA, 5)

    def test_migration_from_schema_twenty_adds_adapters_off(self) -> None:
        from emotivus_forge.core.state import _migrate_settings_20_to_21

        migrated = _migrate_settings_20_to_21({"schema": 20})
        self.assertEqual(migrated["schema"], 21)
        self.assertFalse(migrated["session_adapters"]["enabled"])

    def test_integrity_schema_bounds_track_the_constants(self) -> None:
        """Two hardcoded schema registries once drifted and blocked every migrated project."""
        from emotivus_forge.core.storage import _document_validation_error

        self.assertEqual(
            _document_validation_error("settings.json", {"schema": SETTINGS_SCHEMA}), ""
        )
        self.assertIn(
            "unsupported schema",
            _document_validation_error("settings.json", {"schema": SETTINGS_SCHEMA + 1}),
        )
        self.assertEqual(
            _document_validation_error("state.json", {"schema": CORE_STATE_SCHEMA}), ""
        )

    def test_state_file_count_remains_eight(self) -> None:
        schema_doc = (FORGE_ROOT / "docs" / "STATE-SCHEMA.md").read_text(encoding="utf-8")
        self.assertIn("eight", schema_doc.lower())

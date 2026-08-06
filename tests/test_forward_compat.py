from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core.forward_compat import (
    forward_compat_report,
    preserved_unknown_fields,
)
from emotivus_forge.core.paths import ForgePaths
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.state import SETTINGS_SCHEMA, load_settings
from tests.support import FORGE_ROOT, ForgeTestCase


class ForwardCompatTests(ForgeTestCase):
    def test_forward_migration_preserves_unknown_top_level_and_nested_fields(self) -> None:
        # G3: an older/foreign package carries fields this schema does not know. Forward
        # migration must preserve them verbatim rather than silently dropping them.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".forge").mkdir()
            (ForgePaths(root).settings).write_text(json.dumps({
                "schema": 19,  # older schema forces migration up to current
                "notice_mode": "standard",
                "future_top_level_field": {"vendor": "another-model", "note": "unknown here"},
                "project_identity": {"name": "demo", "future_nested_field": "must-survive"},
            }), encoding="utf-8")
            migrated = load_settings(root)
            self.assertEqual(migrated.get("schema"), SETTINGS_SCHEMA)
            self.assertEqual(migrated.get("future_top_level_field"), {"vendor": "another-model", "note": "unknown here"})
            self.assertEqual(migrated.get("project_identity", {}).get("future_nested_field"), "must-survive")

    def test_report_lists_unknown_fields_and_excludes_known(self) -> None:
        settings = {"schema": SETTINGS_SCHEMA, "notice_mode": "standard", "zeta_unknown": 1, "alpha_unknown": 2}
        self.assertEqual(preserved_unknown_fields(settings), ["alpha_unknown", "zeta_unknown"])
        report = forward_compat_report(settings)
        self.assertEqual(report["unknown_field_count"], 2)
        self.assertNotIn("notice_mode", report["unknown_fields"])
        self.assertNotIn("schema", report["unknown_fields"])

    def test_resume_surfaces_preserved_unknown_fields_only_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            # A clean project surfaces no forward-compat line.
            clean = build_resume(root, FORGE_ROOT, budget="compact")["markdown"]
            self.assertNotIn("Forward-compat:", clean)
            # Inject an unrecognized field (as an imported/foreign package would carry).
            settings_path = ForgePaths(root).settings
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            data["imported_vendor_block"] = {"from": "another-model"}
            settings_path.write_text(json.dumps(data), encoding="utf-8")
            surfaced = build_resume(root, FORGE_ROOT, budget="compact")["markdown"]
            self.assertIn("Forward-compat:", surfaced)
            self.assertIn("imported_vendor_block", surfaced)

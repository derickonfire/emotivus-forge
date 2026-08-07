from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from emotivus_forge.core.handoff import export_continuity_bundle, import_continuity_bundle
from emotivus_forge.core.lifecycle import lifecycle_transition_summary, record_lifecycle_transition
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.paths import STATE_FILE_NAMES, ForgePaths
from emotivus_forge.core.state import load_settings
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class G3RoundTripTests(ForgeTestCase):
    def _close_session(self, root: Path) -> dict:
        return run_scoped_check(root, FORGE_ROOT, session_close_data={
            "session_type": "code-increment",
            "summary": "Prepared a portable development handoff.",
            "completed_work": ["Recorded current project continuity."],
            "decisions": [],
            "owner_facts": [],
            "unresolved_risks": ["Runtime and deployment remain unverified."],
            "next_action": "Continue the next approved roadmap item.",
            "interaction_telemetry": {},
            "field_observation_path": "",
        })

    def test_g3_completion_round_trip(self) -> None:
        # G3 completion rule end to end: another model/vendor can migrate an older
        # package, preserve exact meaning, replace an obsolete component, and emit a
        # compatible continuity package another instance can consume.
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "source"
            source.mkdir()
            self._fixture(source)
            build_passport(source, FORGE_ROOT)

            # (1) The package carries a field this schema does not recognize.
            settings_path = ForgePaths(source).settings
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            data["imported_vendor_block"] = {"from": "another-model", "note": "unknown here"}
            settings_path.write_text(json.dumps(data), encoding="utf-8")
            # Forward-compat: the unknown field survives migration/load verbatim.
            self.assertEqual(load_settings(source).get("imported_vendor_block"), {"from": "another-model", "note": "unknown here"})

            # (2) Replace an obsolete component, declaring a verifiable invariant.
            (source / "lc.json").write_text(json.dumps({
                "schema": 1, "component": "old-widget", "disposition": "replace", "authority": "owner",
                "reason": "Superseded by the new widget.", "successor": "new-widget",
                "preserved_invariants": ["exact identity"],
                "invariant_checks": [{"subject": "observed-change-reconciliation", "required_truth_state": "OBSERVED"}],
            }) + "\n", encoding="utf-8")
            record_lifecycle_transition(source, FORGE_ROOT, "lc.json")
            # Forge verifies the declared invariant still holds after the replacement.
            self.assertEqual(run_scoped_check(source, FORGE_ROOT)["lifecycle_invariants"]["status"], "PRESERVED")

            # (3) Emit a compatible continuity package.
            self._close_session(source)
            package = directory / "Development.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("project/index.php", "<?php echo 'ok';\n")
            exported = export_continuity_bundle(source, str(directory / "Forge-Continuity.zip"), development_package=str(package), forge_root=FORGE_ROOT)

            # (4) Another instance consumes it into a fresh project.
            target = directory / "target"
            target.mkdir()
            self._fixture(target)
            imported = import_continuity_bundle(target, exported["bundle"], development_package=str(package))
            self.assertEqual(imported["status"], "IMPORTED")
            self.assertEqual(len([name for name in STATE_FILE_NAMES if (target / ".forge" / name).is_file()]), 8)

            # (5) Exact meaning preserved across the round trip.
            self.assertEqual(load_settings(target).get("imported_vendor_block"), {"from": "another-model", "note": "unknown here"})
            transitions = lifecycle_transition_summary(target)
            self.assertEqual(transitions["transition_count"], 1)
            self.assertEqual(transitions["components"]["old-widget"]["successor"], "new-widget")

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from emotivus_forge.core.narrative_integrity import check_narrative_integrity
from tests.support import FORGE_ROOT


def _copy_source(target: Path) -> Path:
    return Path(shutil.copytree(
        FORGE_ROOT,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "deploy", ".forge", ".git"),
    ))


class NarrativeIntegrityTests(unittest.TestCase):
    def test_current_certified_source_relationships_pass(self) -> None:
        result = check_narrative_integrity(FORGE_ROOT, observed_regressions=536, observed_modules=56)
        self.assertEqual(result["status"], "PASS", result.get("problems"))
        stale = check_narrative_integrity(FORGE_ROOT, observed_regressions=474, observed_modules=47)
        self.assertEqual(stale["status"], "FAIL")
        self.assertTrue(any("observed self-test regression count" in item for item in stale["problems"]))

    def test_version_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = _copy_source(Path(temp) / "Forge")
            product = json.loads((root / "FORGE-PRODUCT.json").read_text())
            product["version"] = "9.999"
            (root / "FORGE-PRODUCT.json").write_text(json.dumps(product, indent=2) + "\n")
            result = check_narrative_integrity(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("version" in item for item in result["problems"]))

    def test_website_download_checksum_boundary_is_edition_aware(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = _copy_source(Path(temp) / "Forge")
            release_notes = root / "docs-site" / "downloads" / "RELEASE-NOTES.md"
            if release_notes.is_file():
                release_notes.write_text(release_notes.read_text() + "drift\n")
                result = check_narrative_integrity(root)
                self.assertEqual(result["status"], "FAIL")
                self.assertTrue(any("checksum" in item for item in result["problems"]))
            else:
                # Public packages deliberately omit generated website evidence.
                # A synthetic malformed website surface must remain outside that edition's boundary.
                release_notes.parent.mkdir(parents=True, exist_ok=True)
                release_notes.write_text("synthetic drift\n")
                (release_notes.parent / "SHA256SUMS.txt").write_text("0" * 64 + "  RELEASE-NOTES.md\n")
                result = check_narrative_integrity(root)
                self.assertEqual(result["status"], "PASS", result.get("problems"))

    def test_public_edition_checks_only_packaged_public_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = _copy_source(Path(temp) / "Forge")
            manifest_path = root / "FORGE-MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["edition"] = "public"
            manifest["canonical_paths"] = list(manifest["public_paths"])
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            shutil.rmtree(root / "docs-site", ignore_errors=True)
            (root / "CERTIFICATION.md").unlink(missing_ok=True)
            (root / "IMPLEMENTATION-REPORT.md").unlink(missing_ok=True)
            result = check_narrative_integrity(root)
            self.assertEqual(result["status"], "PASS", result.get("problems"))


if __name__ == "__main__":
    unittest.main()

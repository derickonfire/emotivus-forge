from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.paths import STATE_FILE_NAMES
from emotivus_forge.core.project_identity import record_project_identity
from emotivus_forge.core.provenance import (
    provenance_summary,
    record_artifact_provenance,
    retire_artifact_provenance,
)
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class ProvenanceAndDeliveryTests(ForgeTestCase):
    def _artifact_fixture(self, root: Path) -> Path:
        (root / "src").mkdir(exist_ok=True)
        (root / "tools").mkdir(exist_ok=True)
        (root / "dist").mkdir(exist_ok=True)
        (root / "src" / "app.txt").write_text("release payload\n", encoding="utf-8")
        (root / "release.json").write_text('{"release":"preview"}\n', encoding="utf-8")
        (root / "tools" / "build.py").write_text("# deterministic fixture generator\n", encoding="utf-8")
        artifact = root / "dist" / "product.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.write(root / "src" / "app.txt", "app.txt")
        contract = root / "forge-artifact-provenance.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "provenance_id": "product-package",
            "title": "Product package lineage",
            "authority": "owner",
            "artifact_path": "dist/product.zip",
            "generator": {
                "command": "python tools/build.py",
                "source_paths": ["tools/build.py"],
            },
            "input_paths": ["src/**", "release.json"],
            "file_limit": 50,
            "baseline_build_id": "",
            "deliverable": True,
            "truth_boundary": "This records exact current bytes and declared lineage; it does not prove that the declared command ran or that the package works after delivery.",
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def test_current_provenance_passes_and_preserves_eight_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._artifact_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["artifact_provenance"]["status"], "PASS")
            self.assertEqual(payload["artifact_provenance"]["evaluations"][0]["status"], "CURRENT")
            build_resume(root, FORGE_ROOT, budget="compact")
            actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(actual, sorted(STATE_FILE_NAMES))

    def test_input_change_invalidates_recorded_artifact_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._artifact_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            (root / "src" / "app.txt").write_text("changed after package generation\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("declared inputs changed" in item["message"] for item in payload["findings"]))

    def test_artifact_change_invalidates_recorded_output_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._artifact_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            (root / "dist" / "product.zip").write_bytes(b"not the recorded package")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("artifact bytes changed" in item["message"] for item in payload["findings"]))

    def test_generator_source_change_invalidates_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._artifact_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            (root / "tools" / "build.py").write_text("# changed generator\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("generator source changed" in item["message"] for item in payload["findings"]))

    def test_unregistered_deliverable_is_visible_without_false_delivery_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "manual-export.zip").write_bytes(b"manual")
            build_passport(root, FORGE_ROOT)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["artifact_provenance"]["status"], "WARN")
            self.assertIn("manual-export.zip", payload["artifact_provenance"]["unregistered_deliverables"])
            self.assertTrue(any(item["check"] == "core.delivery-perimeter" for item in payload["findings"]))

    def test_changed_contract_requires_renewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._artifact_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("not current" in item["message"] for item in payload["findings"]))

    def test_baseline_binding_detects_owner_declared_baseline_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            identity = self._project_identity_contract(root)
            record_project_identity(root, FORGE_ROOT, identity)
            contract = self._artifact_fixture(root)
            raw = json.loads(contract.read_text(encoding="utf-8"))
            raw["baseline_build_id"] = "2026-07-31.2"
            contract.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            identity_raw = json.loads(identity.read_text(encoding="utf-8"))
            identity_raw["build_id"] = "2026-08-01.2"
            identity_raw["baseline"]["build_id"] = "2026-08-01.1"
            identity_raw["monotonic"]["android_version_code"] += 1
            identity.write_text(json.dumps(identity_raw, indent=2) + "\n", encoding="utf-8")
            record_project_identity(root, FORGE_ROOT, identity)
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("owner-declared baseline" in item["message"] for item in payload["findings"]))

    def test_retirement_preserves_history_but_removes_provenance_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._artifact_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            retire_artifact_provenance(root, "product-package", "The package is no longer distributed.")
            (root / "src" / "app.txt").write_text("later work\n", encoding="utf-8")
            payload = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(payload["status"], "NOT_RUN")
            summary = provenance_summary(root)
            self.assertEqual(summary["retired"], 1)
            self.assertEqual(summary["active"], 0)

    def test_resume_uses_compact_counts_not_digest_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            contract = self._artifact_fixture(root)
            build_passport(root, FORGE_ROOT)
            record_artifact_provenance(root, FORGE_ROOT, contract)
            resume = build_resume(root, FORGE_ROOT, budget="compact")
            markdown = resume["markdown"]
            self.assertIn("Artifact provenance:", markdown)
            self.assertNotIn("input_manifest", markdown)
            self.assertNotIn("artifact_sha256", markdown)

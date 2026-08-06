from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import json
import tempfile
import zipfile
from pathlib import Path

from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.project_identity import record_project_identity
from emotivus_forge.core.provenance import record_artifact_provenance
from emotivus_forge.core.release_package import (
    evaluate_release_package,
    record_release_package,
    release_package_summary,
    retire_release_package,
)
from emotivus_forge.core.resume import build_resume
from emotivus_forge.core.state import load_settings
from emotivus_forge.services.ship import ship_project
from tests.support import FORGE_ROOT, ForgeTestCase


class ReleasePackageCertificationTests(ForgeTestCase):
    def _setup_package(self, root: Path, *, entries: dict[str, str] | None = None, forbidden_literal: str = "") -> Path:
        self._fixture(root)
        (root / "src").mkdir(exist_ok=True)
        (root / "tools").mkdir(exist_ok=True)
        (root / "dist").mkdir(exist_ok=True)
        (root / "release" / "reviews").mkdir(parents=True, exist_ok=True)
        (root / "src" / "app.txt").write_text("neutral release payload\n", encoding="utf-8")
        (root / "tools" / "build.py").write_text("# deterministic fixture generator\n", encoding="utf-8")
        artifact = root / "dist" / "public.zip"
        contents = entries or {"app.txt": "neutral release payload\n", "README.md": "Public package\n"}
        with zipfile.ZipFile(artifact, "w") as archive:
            for name, value in contents.items():
                archive.writestr(name, value)
        build_passport(root, FORGE_ROOT)
        identity = self._project_identity_contract(root)
        record_project_identity(root, FORGE_ROOT, identity)
        provenance = root / "forge-public-provenance.json"
        provenance.write_text(json.dumps({
            "schema": 1,
            "provenance_id": "public-package",
            "title": "Public package lineage",
            "authority": "owner",
            "artifact_path": "dist/public.zip",
            "generator": {"command": "python tools/build.py", "source_paths": ["tools/build.py"]},
            "input_paths": ["src/**"],
            "file_limit": 50,
            "baseline_build_id": "",
            "deliverable": True,
            "truth_boundary": "This records exact current bytes and declared lineage; it does not prove that the declared command ran or that the final package works after distribution.",
        }, indent=2) + "\n", encoding="utf-8")
        record_artifact_provenance(root, FORGE_ROOT, provenance)
        package_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        review_paths = []
        for review_type in ("security", "privacy", "accessibility", "compatibility", "installation", "upgrade", "rollback"):
            evidence = root / "release" / "reviews" / f"{review_type}.md"
            evidence.write_text(f"# {review_type.title()} review\n\nBounded neutral fixture review.\n", encoding="utf-8")
            receipt = root / "release" / "reviews" / f"{review_type}.json"
            receipt.write_text(json.dumps({
                "schema": 1,
                "review_id": f"review-{review_type}",
                "review_type": review_type,
                "status": "PASS",
                "authority": "independent-reviewer",
                "candidate_build_id": "2026-08-01.1",
                "package_sha256": package_sha,
                "evidence_path": f"release/reviews/{review_type}.md",
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "reviewed_utc": "2026-08-02T01:00:00Z",
                "limitations": ["Synthetic fixture review only."],
            }, indent=2) + "\n", encoding="utf-8")
            review_paths.append(f"release/reviews/{review_type}.json")
        contract = root / "forge-release-package.json"
        literals = []
        if forbidden_literal:
            literals.append({"label": "private-project-term", "value": forbidden_literal, "case_sensitive": False})
        contract.write_text(json.dumps({
            "schema": 1,
            "release_package_id": "public-release",
            "title": "Exact public release package",
            "authority": "owner",
            "artifact_path": "dist/public.zip",
            "artifact_provenance_id": "public-package",
            "expected_build_id": "2026-08-01.1",
            "scan": {
                "max_entries": 100,
                "max_entry_bytes": 500000,
                "max_total_text_bytes": 2000000,
                "forbidden_path_patterns": ["private/**"],
                "forbidden_literals": literals,
                "allow_template_paths": True,
            },
            "required_review_types": ["security", "privacy", "accessibility", "compatibility", "installation", "upgrade", "rollback"],
            "review_receipts": review_paths,
            "truth_boundary": "This binds one exact ZIP to current identity, provenance, a bounded confidentiality scan, and project-owned review receipts; it does not prove release readiness or review methodology quality.",
        }, indent=2) + "\n", encoding="utf-8")
        record_release_package(root, FORGE_ROOT, contract)
        return contract

    def test_exact_package_confidentiality_and_reviews_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root)
            result = evaluate_release_package(root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["final_package"]["status"], "PASS")
            self.assertEqual(result["confidentiality"]["status"], "PASS")
            self.assertEqual(result["public_reviews"]["status"], "PASS")
            self.assertEqual(len(result["public_reviews"]["passed"]), 7)

    def test_package_byte_change_invalidates_binding_and_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root)
            with zipfile.ZipFile(root / "dist" / "public.zip", "a") as archive:
                archive.writestr("later.txt", "changed")
            result = evaluate_release_package(root)
            self.assertEqual(result["final_package"]["status"], "FAIL")
            self.assertEqual(result["confidentiality"]["status"], "NOT_RUN")
            self.assertIn("bytes changed", " ".join(result["final_package"]["reasons"]))


    def test_input_drift_invalidates_final_package_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root)
            (root / "src" / "app.txt").write_text("changed after package generation\n", encoding="utf-8")
            result = evaluate_release_package(root)
            self.assertEqual(result["final_package"]["status"], "FAIL")
            self.assertIn("declared inputs changed", " ".join(result["final_package"]["reasons"]))
            self.assertEqual(result["confidentiality"]["status"], "NOT_RUN")

    def test_sensitive_live_path_fails_confidentiality(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root, entries={"app.txt": "ok", ".env": "API_KEY=real-secret-value"})
            result = evaluate_release_package(root)
            self.assertEqual(result["final_package"]["status"], "PASS")
            self.assertEqual(result["confidentiality"]["status"], "FAIL")
            kinds = {item["kind"] for item in result["confidentiality"]["findings"]}
            self.assertIn("sensitive-path", kinds)
            self.assertIn("secret-assignment", kinds)

    def test_owner_declared_contamination_term_is_detected_without_entering_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_term = "Internal Project Phoenix"
            self._setup_package(root, entries={"app.txt": f"Do not ship {private_term}."}, forbidden_literal=private_term)
            result = evaluate_release_package(root)
            self.assertEqual(result["confidentiality"]["status"], "FAIL")
            self.assertTrue(any(item.get("label") == "private-project-term" for item in result["confidentiality"]["findings"]))
            settings_text = (root / ".forge" / "settings.json").read_text(encoding="utf-8")
            self.assertNotIn(private_term, settings_text)
            self.assertIn(hashlib.sha256(private_term.encode("utf-8")).hexdigest(), settings_text)

    def test_stale_review_evidence_fails_public_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root)
            (root / "release" / "reviews" / "security.md").write_text("changed review evidence\n", encoding="utf-8")
            result = evaluate_release_package(root)
            self.assertEqual(result["public_reviews"]["status"], "FAIL")
            self.assertIn("security", result["public_reviews"]["failed"])

    def test_contract_change_requires_renewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self._setup_package(root)
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            result = evaluate_release_package(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["final_package"]["status"], "FAIL")

    def test_retirement_removes_active_release_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root)
            retire_release_package(root, "public-release", "This package was superseded.")
            result = evaluate_release_package(root)
            self.assertEqual(result["status"], "NOT_RUN")

    def test_resume_is_compact_and_ship_ladder_exposes_new_levels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root)
            resume = build_resume(root, FORGE_ROOT, budget="compact")
            self.assertIn("Final release package:", resume["markdown"])
            self.assertNotIn("artifact_sha256", resume["markdown"])
            self.assertNotIn("private-project-term", resume["markdown"])
            ship = ship_project(root, FORGE_ROOT)
            level_ids = [item["level_id"] for item in ship["claim_readiness"]["levels"]]
            self.assertIn("final-package-bound", level_ids)
            self.assertIn("confidentiality-screened", level_ids)
            self.assertIn("public-release-reviewed", level_ids)
            self.assertFalse(ship["release_ready"])

    def test_public_builder_ignores_source_mtime_and_normalizes_zip_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("neutral package\n", encoding="utf-8")
            (root / "CONFIDENTIALITY-POLICY.json").write_text(json.dumps({
                "forbidden_terms": [], "forbidden_sha256": [],
                "forbidden_path_patterns": [], "allow_paths": [],
            }) + "\n", encoding="utf-8")
            (root / "FORGE-MANIFEST.json").write_text(json.dumps({
                "forge_schema": 1,
                "archive_root": "Emotivus-Forge",
                "canonical_paths": ["README.md", "CONFIDENTIALITY-POLICY.json", "FORGE-MANIFEST.json"],
                "public_paths": ["README.md", "CONFIDENTIALITY-POLICY.json", "FORGE-MANIFEST.json"],
            }, indent=2) + "\n", encoding="utf-8")
            first = root / "first.zip"
            second = root / "second.zip"
            command = [sys.executable, str(FORGE_ROOT / "tools" / "build_forge_package.py"), str(root), "--edition", "public"]
            subprocess.run(command + ["--output", str(first)], check=True, capture_output=True, text=True)
            os.utime(root / "README.md", (1_900_000_000, 1_900_000_000))
            subprocess.run(command + ["--output", str(second)], check=True, capture_output=True, text=True)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                for info in archive.infolist():
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o644)

    def test_summary_reports_compact_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_package(root)
            summary = release_package_summary(root)
            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(summary["review_ratio"], "7/7")


if __name__ == "__main__":
    import unittest
    unittest.main()

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.third_party_intake import (
    assess_third_party_intakes,
    record_third_party_intake,
    retire_third_party_intake,
    validate_third_party_intake,
)
from emotivus_forge.core.state import load_settings
from tests.support import FORGE_ROOT, ForgeTestCase


class ThirdPartyIntakeTests(ForgeTestCase):
    def _root(self, directory: str) -> Path:
        root = Path(directory) / "project"
        root.mkdir()
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        return root

    def _archive(self, directory: Path) -> tuple[Path, dict[str, tuple[str, int]]]:
        source = directory / "upstream-1.0.0.zip"
        members = {
            "upstream/LICENSE": b"Apache License Version 2.0\n",
            "upstream/internal/sanitize/secrets.go": b"package sanitize\nfunc Detect() {}\n",
            "upstream/internal/sanitize/secrets_test.go": b"package sanitize\nfunc TestDetect() {}\n",
        }
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        identities = {name: (hashlib.sha256(data).hexdigest(), len(data)) for name, data in members.items()}
        return source, identities

    def _contract(self, root: Path, source: Path, identities: dict[str, tuple[str, int]]) -> Path:
        license_sha, _ = identities["upstream/LICENSE"]
        candidates = []
        for candidate_id, classification, distribution, file_path in (
            ("secret-patterns", "adapt", "public", "upstream/internal/sanitize/secrets.go"),
            ("secret-tests", "adapt", "public", "upstream/internal/sanitize/secrets_test.go"),
            ("proxy", "reject", "rejected", "upstream/internal/sanitize/secrets.go"),
        ):
            digest, size = identities[file_path]
            candidates.append({
                "candidate_id": candidate_id,
                "classification": classification,
                "stage": "rejected" if classification == "reject" else "planned",
                "distribution": distribution,
                "intended_capability": "Bounded confidentiality screening",
                "mission_fit": "This supports exact-package confidentiality without adding a daemon or hidden state.",
                "upstream_files": [{"path": file_path, "sha256": digest, "bytes": size}],
                "dependency_closure": [{"name": "Go standard library", "type": "standard-library", "version": "1.x", "license": "BSD-style", "required": True}],
                "retained_behaviors": ["Recognize high-confidence secret forms."],
                "changed_behaviors": ["Report findings without mutating certified bytes."],
                "trust_semantic_differences": ["Detection does not establish authority or release readiness."],
                "security_review": "The candidate is bounded to static pattern matching and does not execute upstream code.",
                "confidentiality_review": "Only neutral patterns and tests may enter Forge; no upstream runtime state or private data is retained.",
                "original_tests": [file_path] if classification == "adapt" else [],
                "forge_tests": ["tests/test_confidentiality_screening.py"] if classification == "adapt" else [],
                "forge_files": ["emotivus_forge/core/confidentiality.py"] if classification == "adapt" else [],
                "attribution_notice": "Adapted from YesMem under Apache-2.0; behavior modified for Forge reporting." if classification == "adapt" else "",
                "update_retirement_procedure": "Re-review exact upstream bytes, tests, dependencies, and Forge trust boundaries before replacement.",
            })
        payload = {
            "schema": 1,
            "intake_id": "yesmem-1.0.0-review",
            "authority": "owner",
            "upstream_project": "YesMem",
            "upstream_version": "1.0.0",
            "upstream_archive_name": source.name,
            "upstream_archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "upstream_archive_bytes": source.stat().st_size,
            "license": {
                "spdx": "Apache-2.0",
                "copyright": "Example upstream owner",
                "upstream_file": "upstream/LICENSE",
                "sha256": license_sha,
                "notice_file": "",
            },
            "full_source_distribution": "external-only",
            "candidates": candidates,
            "truth_boundary": "This intake proves exact reviewed provenance and declared adaptation boundaries; it does not prove correctness, legal sufficiency, security, or release readiness.",
        }
        path = root / "third-party-intake.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def test_records_exact_external_archive_and_candidate_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            source, identities = self._archive(Path(directory))
            contract = self._contract(root, source, identities)
            record = record_third_party_intake(root, FORGE_ROOT, contract, source)
            self.assertEqual(record["status"], "active")
            summary = assess_third_party_intakes(root)
            self.assertEqual(summary["status"], "CURRENT")
            self.assertEqual(summary["candidate_count"], 3)
            self.assertEqual(summary["adapt_count"], 2)
            self.assertEqual(load_settings(root)["schema"], 21)

    def test_source_archive_must_remain_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            source, identities = self._archive(root)
            contract = self._contract(root, source, identities)
            with self.assertRaisesRegex(ValueError, "remain external"):
                record_third_party_intake(root, FORGE_ROOT, contract, source)

    def test_wrong_upstream_member_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            source, identities = self._archive(Path(directory))
            contract = self._contract(root, source, identities)
            data = json.loads(contract.read_text(encoding="utf-8"))
            data["candidates"][0]["upstream_files"][0]["sha256"] = "0" * 64
            contract.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match archive bytes"):
                validate_third_party_intake(root, FORGE_ROOT, contract, source)

    def test_contract_drift_requires_attention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            source, identities = self._archive(Path(directory))
            contract = self._contract(root, source, identities)
            record_third_party_intake(root, FORGE_ROOT, contract, source)
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertEqual(assess_third_party_intakes(root)["status"], "ATTENTION")

    def test_exact_upstream_archive_absorption_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            source, identities = self._archive(Path(directory))
            contract = self._contract(root, source, identities)
            record_third_party_intake(root, FORGE_ROOT, contract, source)
            (root / source.name).write_bytes(source.read_bytes())
            summary = assess_third_party_intakes(root)
            self.assertEqual(summary["status"], "ATTENTION")
            self.assertIn("absorbed", summary["attention"][0]["reason"])

    def test_retirement_is_separate_and_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            source, identities = self._archive(Path(directory))
            contract = self._contract(root, source, identities)
            record_third_party_intake(root, FORGE_ROOT, contract, source)
            retired = retire_third_party_intake(root, "yesmem-1.0.0-review", "The project replaced this exact reviewed intake.")
            self.assertEqual(retired["status"], "retired")
            self.assertEqual(assess_third_party_intakes(root)["status"], "NOT_DECLARED")


if __name__ == "__main__":
    import unittest
    unittest.main()

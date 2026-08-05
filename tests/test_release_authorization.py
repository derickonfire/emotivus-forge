from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from emotivus_forge.core.release_authorization import (
    evaluate_release_authorization,
    record_release_authorization,
    release_authorization_summary,
    retire_release_authorization,
)
from tests.support import FORGE_ROOT, ForgeTestCase
from tests import test_release_proof


class ReleaseAuthorizationTests(ForgeTestCase):
    def _setup_release_package(self, root: Path):
        return test_release_proof.ReleaseProofTests._setup_release_package(self, root)

    def _contract(self, root: Path, package_sha: str, package_bytes: int, *, valid_until: str = "2027-08-02T12:00:00Z", digest: str = "") -> Path:
        path = root / "forge-release-authorization.json"
        path.write_text(json.dumps({
            "schema": 1,
            "release_authorization_id": "public-release-authorization",
            "title": "Exact public package authorization",
            "authority": "owner",
            "authority_source": "project-declared owner decision",
            "release_package_id": "public-release",
            "package_sha256": digest or package_sha,
            "package_bytes": package_bytes,
            "build_id": "2026-08-01.1",
            "decision": "authorize-public-release",
            "authorized_utc": "2026-08-02T12:00:00Z",
            "valid_until_utc": valid_until,
            "authorized_channels": ["public-download", "website"],
            "conditions": ["Withdraw authorization if exact package bytes or required evidence change."],
            "rationale": "The project authority reviewed the exact final package identity and current bounded release evidence and authorizes distribution through the named channels.",
            "truth_boundary": "This records a project-declared authorization for one exact package and named channels; Forge does not authenticate the human, prove authorship or reviewer competence, or guarantee future package and channel state.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def test_no_authorization_is_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_release_package(root)
            self.assertEqual(evaluate_release_authorization(root)["status"], "NOT_RUN")

    def test_exact_current_package_authorization_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._contract(root, package_sha, package_bytes)
            record_release_authorization(root, FORGE_ROOT, contract)
            result = evaluate_release_authorization(root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["authorized_channels"], ["public-download", "website"])
            self.assertEqual(release_authorization_summary(root)["authorized_channel_count"], 2)

    def test_mismatched_package_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._contract(root, package_sha, package_bytes, digest="0" * 64)
            with self.assertRaisesRegex(ValueError, "does not match"):
                record_release_authorization(root, FORGE_ROOT, contract)

    def test_source_change_requires_authorization_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._contract(root, package_sha, package_bytes)
            record_release_authorization(root, FORGE_ROOT, contract)
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            result = evaluate_release_authorization(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("changed", result["reason"])

    def test_retirement_removes_current_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._contract(root, package_sha, package_bytes)
            record_release_authorization(root, FORGE_ROOT, contract)
            retire_release_authorization(root, "public-release-authorization", "The exact package was withdrawn.")
            self.assertEqual(evaluate_release_authorization(root)["status"], "NOT_RUN")

    def test_record_and_retire_must_be_separate_adopt_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            command = [
                sys.executable, str(FORGE_ROOT / "forge.py"), "adopt", str(root),
                "--record-release-authorization", "missing.json",
                "--retire-release-authorization", "public-release-authorization",
                "--release-authorization-reason", "Withdraw exact package authorization.",
                "--json",
            ]
            result = subprocess.run(command, cwd=FORGE_ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be separate Adopt operations", result.stderr)



if __name__ == "__main__":
    import unittest
    unittest.main()

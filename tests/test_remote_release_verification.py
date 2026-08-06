from __future__ import annotations

import json
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch

from emotivus_forge.core.release_distribution import evaluate_release_distribution, record_release_distribution
from emotivus_forge.core.remote_release import _RemoteContradictionError
from emotivus_forge.services.ship import ship_project
from tests.support import FORGE_ROOT
from tests.test_release_distribution_cold_session import DistributionFixture


class _Response:
    def __init__(self, body: bytes, *, status: int = 200, url: str = "https://example.invalid/download/public.zip", headers: dict[str, str] | None = None) -> None:
        self.body = body
        self.status = status
        self.url = url
        self.headers = headers or {
            "Content-Type": "application/zip",
            "Content-Length": str(len(body)),
        }
        self.offset = 0

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class _Opener:
    def __init__(self, response: _Response | Exception) -> None:
        self.response = response
        self.calls = 0

    def open(self, request, timeout: int):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        self.response.offset = 0
        return self.response


class RemoteReleaseVerificationTests(DistributionFixture):
    def _enable_remote(self, root: Path, contract: Path) -> None:
        raw = json.loads(contract.read_text(encoding="utf-8"))
        raw["remote_verification"] = {
            "schema": 1,
            "allowed_origins": ["https://example.invalid"],
            "timeout_seconds": 10,
            "max_artifact_bytes": 1_000_000,
            "truth_boundary": "A passing result proves only that a fresh bounded HTTPS GET returned bytes identical to this exact package at assessment time; it does not prove future availability, continuous CDN integrity, signer custody, or release readiness."
        }
        raw["truth_boundary"] = "This verifies detached signatures, signed local channel metadata, project-owned publication receipts, and optionally fresh exact-byte remote retrieval. It does not prove future availability, continuous CDN integrity, signer custody, or release readiness."
        contract.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        record_release_distribution(root, FORGE_ROOT, contract)

    def test_normal_distribution_evaluation_is_network_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            self._enable_remote(root, contract)
            with patch("emotivus_forge.core.remote_release.urllib.request.build_opener") as build_opener:
                result = evaluate_release_distribution(root)
            build_opener.assert_not_called()
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["remote_channels"]["status"], "NOT_RUN")
            self.assertTrue(result["remote_channels"]["configured"])

    def test_fresh_remote_exact_bytes_pass_without_retaining_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            self._enable_remote(root, contract)
            opener = _Opener(_Response(artifact.read_bytes()))
            with patch("emotivus_forge.core.remote_release.urllib.request.build_opener", return_value=opener):
                result = evaluate_release_distribution(root, perform_remote=True)
            remote = result["remote_channels"]
            self.assertEqual(remote["status"], "PASS")
            self.assertEqual(remote["passed"], ["primary-download"])
            self.assertFalse(remote["evaluations"][0]["observed"]["response_body_retained"])
            self.assertNotIn("body", remote["evaluations"][0])
            self.assertEqual(opener.calls, 1)

    def test_remote_digest_mismatch_is_contradicted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            self._enable_remote(root, contract)
            wrong = b"x" * len(artifact.read_bytes())
            opener = _Opener(_Response(wrong))
            with patch("emotivus_forge.core.remote_release.urllib.request.build_opener", return_value=opener):
                result = evaluate_release_distribution(root, perform_remote=True)
            row = result["remote_channels"]["evaluations"][0]
            self.assertEqual(result["remote_channels"]["status"], "FAIL")
            self.assertEqual(row["truth_state"], "CONTRADICTED")
            self.assertIn("digest", row["reason"])

    def test_remote_network_failure_is_blocked_attempted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            self._enable_remote(root, contract)
            opener = _Opener(urllib.error.URLError("offline"))
            with patch("emotivus_forge.core.remote_release.urllib.request.build_opener", return_value=opener):
                result = evaluate_release_distribution(root, perform_remote=True)
            row = result["remote_channels"]["evaluations"][0]
            self.assertEqual(result["remote_channels"]["status"], "BLOCKED")
            self.assertEqual(row["truth_state"], "BLOCKED_ATTEMPTED")
            self.assertTrue(row["attempted"])

    def test_forbidden_redirect_is_contradicted_not_network_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            self._enable_remote(root, contract)
            opener = _Opener(_RemoteContradictionError("Redirect target is outside the authority-approved remote origins."))
            with patch("emotivus_forge.core.remote_release.urllib.request.build_opener", return_value=opener):
                result = evaluate_release_distribution(root, perform_remote=True)
            row = result["remote_channels"]["evaluations"][0]
            self.assertEqual(result["remote_channels"]["status"], "FAIL")
            self.assertEqual(row["truth_state"], "CONTRADICTED")
            self.assertTrue(row["attempted"])

    def test_remote_final_origin_outside_contract_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            self._enable_remote(root, contract)
            response = _Response(artifact.read_bytes(), url="https://other.invalid/public.zip")
            opener = _Opener(response)
            with patch("emotivus_forge.core.remote_release.urllib.request.build_opener", return_value=opener):
                result = evaluate_release_distribution(root, perform_remote=True)
            row = result["remote_channels"]["evaluations"][0]
            self.assertEqual(row["status"], "FAIL")
            self.assertIn("outside", row["reason"])

    def test_contract_rejects_non_https_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            raw = json.loads(contract.read_text(encoding="utf-8"))
            raw["remote_verification"] = {
                "schema": 1,
                "allowed_origins": ["http://example.invalid"],
                "timeout_seconds": 10,
                "max_artifact_bytes": 1_000_000,
                "truth_boundary": "This deliberately long truth boundary exists only to exercise rejection of a non-HTTPS remote origin in a neutral test fixture without making any release claim."
            }
            contract.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "https"):
                record_release_distribution(root, FORGE_ROOT, contract)

    def test_ship_runs_remote_verification_and_exposes_claim_level(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            contract = self._setup_distribution(root, artifact)
            self._enable_remote(root, contract)
            opener = _Opener(_Response(artifact.read_bytes()))
            with patch("emotivus_forge.core.remote_release.urllib.request.build_opener", return_value=opener):
                ship = ship_project(root, FORGE_ROOT)
            remote_level = next(row for row in ship["claim_readiness"]["levels"] if row["level_id"] == "remote-channel-verified")
            remote_requirement = next(row for row in remote_level["requirements"] if row["requirement_id"] == "fresh-remote-artifact-retrieval")
            self.assertEqual(remote_requirement["status"], "PASS")
            self.assertFalse(ship["release_ready"])


if __name__ == "__main__":
    unittest.main()

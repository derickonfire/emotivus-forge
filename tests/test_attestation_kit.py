from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from emotivus_forge.core.attestation_kit import (
    AttestationKitError,
    build_owner_attestation_kit,
    verify_owner_attestation_kit,
)
from emotivus_forge.core.build_attestation import build_manifest_payload, write_build_manifest
from tests.test_build_attestation import E, N, _sign


class AttestationKitTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        source = root / "source"
        source.mkdir()
        (source / "tools").mkdir()
        project_root = Path(__file__).resolve().parents[1]
        runner = project_root / "tools" / "portable_attestation_runner.py"
        (source / "tools" / "portable_attestation_runner.py").write_bytes(runner.read_bytes())
        (source / "FORGE-MANIFEST.json").write_text(json.dumps({
            "forge_schema": 1,
            "version": "0.546",
            "edition": "development",
        }), encoding="utf-8")
        package = root / "RUN-FORGE-0.546.zip"
        packaged_manifest = {
            "forge_schema": 1,
            "version": "0.546",
            "edition": "public",
        }
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("Emotivus-Forge/FORGE-MANIFEST.json", json.dumps(packaged_manifest))
            archive.writestr("Emotivus-Forge/forge.py", "# neutral\n")
        payload = build_manifest_payload(
            package,
            version="0.546",
            edition="public",
            source_fingerprint="a" * 64,
            source_file_count=2,
            forge_manifest_sha256="b" * 64,
        )
        build_manifest = root / "RUN-FORGE-0.546.build.json"
        write_build_manifest(build_manifest, payload)
        key = root / "owner-public-key.json"
        key.write_text(json.dumps({
            "schema": 1,
            "algorithm": "rsa-pkcs1v15-sha256",
            "key_id": "owner-test-key",
            "modulus_hex": f"{N:x}",
            "public_exponent": E,
        }), encoding="utf-8")
        return source, package, build_manifest, key

    def _build(self, root: Path) -> tuple[Path, Path, Path]:
        source, package, build_manifest, key = self._fixture(root)
        kit = root / "Forge-0.546-Attestation-Kit.zip"
        build_owner_attestation_kit(source, package, build_manifest, kit)
        return kit, build_manifest, key

    def _extract(self, kit: Path, root: Path) -> Path:
        with zipfile.ZipFile(kit) as archive:
            archive.extractall(root)
        children = [path for path in root.iterdir() if path.is_dir()]
        self.assertEqual(len(children), 1)
        return children[0]

    def _run(self, kit_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "run-attestation.py", *args],
            cwd=kit_root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_kit_build_is_deterministic_and_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, package, build_manifest, _ = self._fixture(root)
            first = root / "first.zip"
            second = root / "second.zip"
            one = build_owner_attestation_kit(source, package, build_manifest, first)
            two = build_owner_attestation_kit(source, package, build_manifest, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(one["kit_id"], two["kit_id"])
            self.assertEqual(one["attestation_status"], "NOT_RUN")
            self.assertFalse(one["private_key_retained"])
            self.assertFalse(one["release_authorized"])
            self.assertEqual(verify_owner_attestation_kit(first)["status"], "PASS")

    def test_schema_one_build_manifest_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, package, build_manifest, _ = self._fixture(root)
            value = json.loads(build_manifest.read_text())
            value["schema"] = 1
            value.pop("packaged_forge_manifest_sha256")
            value.pop("packaged_forge_manifest_bytes")
            write_build_manifest(build_manifest, value)
            with self.assertRaises(AttestationKitError):
                build_owner_attestation_kit(source, package, build_manifest, root / "kit.zip")

    def test_extracted_kit_verifies_and_prepare_precommits_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, _, key = self._build(root)
            kit_root = self._extract(kit, root / "extract")
            verified = self._run(kit_root, "verify")
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            prepared = self._run(kit_root, "prepare", "--public-key", str(key), "--output-dir", "ceremony")
            self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
            result = json.loads(prepared.stdout)
            self.assertEqual(result["attestation_status"], "AWAITING_SIGNATURE")
            request = json.loads((kit_root / "ceremony" / "attestation-request.json").read_text())
            self.assertEqual(request["expected_public_key"]["fingerprint"], result["public_key_fingerprint"])
            self.assertFalse(request["private_key_retained"])
            self.assertFalse(request["release_authorized"])

    def test_complete_external_signature_produces_reverifiable_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, _, key = self._build(root)
            kit_root = self._extract(kit, root / "extract")
            prepared = self._run(kit_root, "prepare", "--public-key", str(key), "--output-dir", "ceremony")
            self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
            manifest_ref = json.loads((kit_root / "MANIFEST.json").read_text())["build_manifest"]["path"]
            signature = root / "signature.b64"
            signature.write_text(base64.b64encode(_sign((kit_root / manifest_ref).read_bytes())).decode("ascii") + "\n")
            finalized = self._run(kit_root, "finalize", "--ceremony-dir", "ceremony", "--signature", str(signature))
            self.assertEqual(finalized.returncode, 0, finalized.stdout + finalized.stderr)
            result = json.loads(finalized.stdout)
            self.assertEqual(result["attestation_status"], "VERIFIED")
            self.assertFalse(result["owner_identity_authenticated"])
            self.assertFalse(result["release_authorized"])
            verified = self._run(kit_root, "verify-receipt", "--ceremony-dir", "ceremony")
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["status"], "PASS")

    def test_missing_signature_is_structured_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, _, key = self._build(root)
            kit_root = self._extract(kit, root / "extract")
            self.assertEqual(self._run(kit_root, "prepare", "--public-key", str(key), "--output-dir", "ceremony").returncode, 0)
            result = self._run(kit_root, "finalize", "--ceremony-dir", "ceremony", "--signature", "missing.b64")
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(payload["attestation_status"], "NOT_RUN")

    def test_wrong_signature_is_structured_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, _, key = self._build(root)
            kit_root = self._extract(kit, root / "extract")
            self.assertEqual(self._run(kit_root, "prepare", "--public-key", str(key), "--output-dir", "ceremony").returncode, 0)
            signature = root / "wrong.b64"
            signature.write_text(base64.b64encode(b"x" * 256).decode("ascii") + "\n")
            result = self._run(kit_root, "finalize", "--ceremony-dir", "ceremony", "--signature", str(signature))
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("does not verify" in item for item in payload["problems"]))

    def test_changed_public_key_after_prepare_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, _, key = self._build(root)
            kit_root = self._extract(kit, root / "extract")
            self.assertEqual(self._run(kit_root, "prepare", "--public-key", str(key), "--output-dir", "ceremony").returncode, 0)
            key_path = kit_root / "ceremony" / "owner-public-key.json"
            value = json.loads(key_path.read_text())
            value["key_id"] = "other-owner-key"
            key_path.write_text(json.dumps(value))
            signature = root / "signature.b64"
            manifest_ref = json.loads((kit_root / "MANIFEST.json").read_text())["build_manifest"]["path"]
            signature.write_text(base64.b64encode(_sign((kit_root / manifest_ref).read_bytes())).decode("ascii") + "\n")
            result = self._run(kit_root, "finalize", "--ceremony-dir", "ceremony", "--signature", str(signature))
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(any("public key" in item for item in json.loads(result.stdout)["problems"]))

    def test_tampered_receipt_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, _, key = self._build(root)
            kit_root = self._extract(kit, root / "extract")
            self.assertEqual(self._run(kit_root, "prepare", "--public-key", str(key), "--output-dir", "ceremony").returncode, 0)
            manifest_ref = json.loads((kit_root / "MANIFEST.json").read_text())["build_manifest"]["path"]
            signature = root / "signature.b64"
            signature.write_text(base64.b64encode(_sign((kit_root / manifest_ref).read_bytes())).decode("ascii") + "\n")
            self.assertEqual(self._run(kit_root, "finalize", "--ceremony-dir", "ceremony", "--signature", str(signature)).returncode, 0)
            receipt_path = kit_root / "ceremony" / "attestation-receipt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["release_authorized"] = True
            receipt_path.write_text(json.dumps(receipt))
            result = self._run(kit_root, "verify-receipt", "--ceremony-dir", "ceremony")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["status"], "FAIL")

    def test_tampered_kit_archive_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kit, _, _ = self._build(root)
            with zipfile.ZipFile(kit, "a") as archive:
                archive.writestr("unexpected.txt", "drift")
            self.assertEqual(verify_owner_attestation_kit(kit)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()

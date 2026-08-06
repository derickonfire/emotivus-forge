from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from emotivus_forge.core.build_attestation import (
    build_manifest_payload,
    verify_build_attestation,
    write_build_manifest,
)

N = int("8481b2735f3204f8a14ecac8a39a5797ebc1e7883b6d7e6937894288d5d9f9d10079cff647c502aa8b790cfefae9e7f39d07c6ff9775c6d94d99285de67796c7a899586db40910885ef41722ac0a5139a4c363b24b3eedd4047229991eeb822440bac92f4f4cfb14bc5bec42d3959ab08eae40b6c09b0370f4eadca72c3d4e42c55b2f4223516f7ab29154fc4ae204bbc7e61f7c3bde4fbe3f96c6e13fc328f0b1e75dff143b929e0b7877665b62fb3ade589aa2e954411826cccf3322e514df1f8dc6646cc9dbea7afa0a7bad8ea264e577472df8bfba18f73c427e71e55f7b4808ef8bc16134796ed3e1406387c4e5dac30614eb4c23b2417848499d6dbae1", 16)
D = int("2f3517d303acc9d99c7a7a436e09fc3ffb35cb5b9d347eaf54a259aa6f69e7971ef0c6f6ea8dd54bd641cbb001cb98a011a7662dc413a942dce2fe5f29cf1c5048904d51542d508f0d29301ee1a51158148ba9f6a8d92418ff767ebc77281766fc0aafc7639cbced1fc82e0d86dd0b4df09f431df8d3a12fba89fc0fb0f2ac71192b52d1d6b7fd8735ebb118b64a6d6103045e19847ec143742080e297ca30d26b4f59eb0848456cbb9941ed11c1a754f6c6216f8d6254fe33eedb61be3a599c31387f5a49c487be96f1412b93a79515a6cdb1b0d5dcb9c95f64d9543a041147717e2116dd7a38d2478a381204f612858012ea865faeb915a75048950a07c95b", 16)
E = 65537
DI_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _sign(data: bytes) -> bytes:
    size = (N.bit_length() + 7) // 8
    digest_info = DI_PREFIX + hashlib.sha256(data).digest()
    encoded = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    return pow(int.from_bytes(encoded, "big"), D, N).to_bytes(size, "big")


class BuildAttestationTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        package = root / "RUN-FORGE-0.543.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("Emotivus-Forge/FORGE-MANIFEST.json", json.dumps({"version": "0.543", "edition": "public"}))
            archive.writestr("Emotivus-Forge/forge.py", "# neutral\n")
        payload = build_manifest_payload(
            package,
            version="0.543",
            edition="public",
            source_fingerprint="a" * 64,
            source_file_count=2,
            forge_manifest_sha256="b" * 64,
        )
        manifest = root / "RUN-FORGE-0.543.build.json"
        write_build_manifest(manifest, payload)
        key = root / "owner-public-key.json"
        key.write_text(json.dumps({
            "schema": 1,
            "algorithm": "rsa-pkcs1v15-sha256",
            "key_id": "owner-test-key",
            "modulus_hex": f"{N:x}",
            "public_exponent": E,
        }), encoding="utf-8")
        signature = root / "RUN-FORGE-0.543.build.sig"
        signature.write_text(base64.b64encode(_sign(manifest.read_bytes())).decode("ascii") + "\n", encoding="ascii")
        return package, manifest, key, signature

    def test_build_manifest_is_deterministic_and_binds_exact_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, manifest, _, _ = self._fixture(root)
            first = manifest.read_bytes()
            payload = build_manifest_payload(
                package,
                version="0.543",
                edition="public",
                source_fingerprint="a" * 64,
                source_file_count=2,
                forge_manifest_sha256="b" * 64,
            )
            write_build_manifest(manifest, payload)
            self.assertEqual(first, manifest.read_bytes())
            self.assertEqual(payload["package_sha256"], hashlib.sha256(package.read_bytes()).hexdigest())
            self.assertFalse(payload["private_key_retained"])
            self.assertFalse(payload["release_authorized"])

    def test_external_signature_verifies_without_private_key_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = verify_build_attestation(*self._fixture(Path(temp)))
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["private_key_retained"])
            self.assertFalse(result["release_authorized"])

    def test_tampered_package_fails_exact_byte_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, manifest, key, signature = self._fixture(Path(temp))
            package.write_bytes(package.read_bytes() + b"drift")
            result = verify_build_attestation(package, manifest, key, signature)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("package_sha256" in item for item in result["problems"]))

    def test_tampered_manifest_fails_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, manifest, key, signature = self._fixture(Path(temp))
            value = json.loads(manifest.read_text())
            value["source_selection_sha256"] = "c" * 64
            write_build_manifest(manifest, value)
            result = verify_build_attestation(package, manifest, key, signature)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("signature" in item for item in result["problems"]))

    def test_expected_source_fingerprint_is_optional_but_exact_when_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, manifest, key, signature = self._fixture(Path(temp))
            result = verify_build_attestation(
                package, manifest, key, signature, expected_source_fingerprint="d" * 64
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("source-selection" in item for item in result["problems"]))

    def test_packaged_forge_manifest_digest_is_reverified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, manifest, key, signature = self._fixture(Path(temp))
            value = json.loads(manifest.read_text())
            value["packaged_forge_manifest_sha256"] = "c" * 64
            write_build_manifest(manifest, value)
            signature.write_text(base64.b64encode(_sign(manifest.read_bytes())).decode("ascii") + "\n")
            result = verify_build_attestation(package, manifest, key, signature)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("packaged_forge_manifest_sha256" in item for item in result["problems"]))

    def test_expected_public_key_fingerprint_is_exact_when_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, manifest, key, signature = self._fixture(Path(temp))
            result = verify_build_attestation(
                package, manifest, key, signature, expected_public_key_fingerprint="d" * 64
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("precommitted expected key" in item for item in result["problems"]))

    def test_manifest_cannot_claim_release_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, manifest, key, signature = self._fixture(Path(temp))
            value = json.loads(manifest.read_text())
            value["release_authorized"] = True
            write_build_manifest(manifest, value)
            signature.write_text(base64.b64encode(_sign(manifest.read_bytes())).decode("ascii") + "\n")
            result = verify_build_attestation(package, manifest, key, signature)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("release authorization" in item for item in result["problems"]))


if __name__ == "__main__":
    unittest.main()

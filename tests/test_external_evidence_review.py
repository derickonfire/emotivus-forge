from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from emotivus_forge.core.attestation_kit import build_owner_attestation_kit
from emotivus_forge.core.build_attestation import build_manifest_payload, write_build_manifest
from emotivus_forge.core.evidence_kit import build_portable_evidence_kit
from emotivus_forge.core.external_evidence import (
    review_external_evidence,
    verify_review_receipt,
    write_review_receipt,
)
from tests.support import FORGE_ROOT
from tests.test_build_attestation import E, N, _sign
from tools.build_forge_package import build_package


class ExternalEvidenceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        cls.runtime = cls.root / "RUN-FORGE-current.zip"
        build_package(FORGE_ROOT, output=cls.runtime, edition="public")
        cls.evidence_kit = cls.root / "evidence-kit.zip"
        build_portable_evidence_kit(FORGE_ROOT, cls.runtime, cls.evidence_kit)
        cls.evidence_root = cls._extract_one(cls.evidence_kit, cls.root / "evidence-extract")

        source = cls.root / "attestation-source"
        source.mkdir()
        (source / "tools").mkdir()
        (source / "tools" / "portable_attestation_runner.py").write_bytes(
            (FORGE_ROOT / "tools" / "portable_attestation_runner.py").read_bytes()
        )
        version = json.loads((FORGE_ROOT / "FORGE-MANIFEST.json").read_text())["version"]
        (source / "FORGE-MANIFEST.json").write_text(json.dumps({
            "forge_schema": 1, "version": version, "edition": "development"
        }))
        cls.attestation_package = cls.root / f"RUN-FORGE-{version}.zip"
        cls.attestation_package.write_bytes(cls.runtime.read_bytes())
        payload = build_manifest_payload(
            cls.attestation_package,
            version=version,
            edition="public",
            source_fingerprint="a" * 64,
            source_file_count=2,
            forge_manifest_sha256="b" * 64,
        )
        cls.build_manifest = cls.root / f"RUN-FORGE-{version}.build.json"
        write_build_manifest(cls.build_manifest, payload)
        cls.public_key = cls.root / "owner-public-key.json"
        cls.public_key.write_text(json.dumps({
            "schema": 1,
            "algorithm": "rsa-pkcs1v15-sha256",
            "key_id": "owner-test-key",
            "modulus_hex": f"{N:x}",
            "public_exponent": E,
        }))
        cls.attestation_kit = cls.root / "attestation-kit.zip"
        build_owner_attestation_kit(source, cls.attestation_package, cls.build_manifest, cls.attestation_kit)
        cls.attestation_root = cls._extract_one(cls.attestation_kit, cls.root / "attestation-extract")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    @staticmethod
    def _extract_one(archive: Path, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
        roots = [path for path in destination.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("archive did not extract to one root")
        return roots[0]

    def _run(self, root: Path, script: str, *args: str, expected: int = 0) -> dict[str, object]:
        process = subprocess.run(
            [sys.executable, script, *args],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        self.assertEqual(process.returncode, expected, process.stderr or process.stdout)
        return json.loads(process.stdout)

    def _attestation_return(self, name: str = "attestation-return.zip") -> Path:
        ceremony = self.attestation_root / f"ceremony-{name.replace('.', '-')}"
        self._run(
            self.attestation_root,
            "run-attestation.py",
            "prepare",
            "--public-key",
            str(self.public_key),
            "--output-dir",
            str(ceremony),
        )
        kit_manifest = json.loads((self.attestation_root / "MANIFEST.json").read_text())
        subject = self.attestation_root / kit_manifest["build_manifest"]["path"]
        signature = self.root / f"{name}.sig.b64"
        signature.write_text(base64.b64encode(_sign(subject.read_bytes())).decode("ascii") + "\n")
        self._run(
            self.attestation_root,
            "run-attestation.py",
            "finalize",
            "--ceremony-dir",
            str(ceremony),
            "--signature",
            str(signature),
        )
        output = self.root / name
        result = self._run(
            self.attestation_root,
            "run-attestation.py",
            "package-return",
            "--ceremony-dir",
            str(ceremony),
            "--kit-archive",
            str(self.attestation_kit),
            "--output",
            str(output),
        )
        self.assertEqual(result["status"], "PASS")
        return output

    def test_attestation_return_is_deterministic_and_bounded(self) -> None:
        first = self._attestation_return("attestation-return-a.zip")
        second = self._attestation_return("attestation-return-b.zip")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        review = review_external_evidence(
            self.attestation_kit, first, reviewer="reviewer-a"
        )
        self.assertEqual(review["status"], "PASS", review["problems"])
        self.assertEqual(review["adjudication_status"], "VERIFIED_CRYPTOGRAPHIC_RECEIPT")
        self.assertEqual(review["owner_identity"], "NOT_AUTHENTICATED")
        self.assertFalse(review["release_authorized"])
        self.assertFalse(review["release_ready"])
        receipt_path = self.root / "attestation-review.json"
        write_review_receipt(receipt_path, review)
        self.assertEqual(verify_review_receipt(receipt_path)["status"], "PASS")

    def test_exact_duplicate_is_classified_without_promoting_claims(self) -> None:
        bundle = self._attestation_return("attestation-return-duplicate.zip")
        first = review_external_evidence(self.attestation_kit, bundle, reviewer="reviewer-a")
        prior = self.root / "prior-review.json"
        write_review_receipt(prior, first)
        second = review_external_evidence(
            self.attestation_kit,
            bundle,
            reviewer="reviewer-b",
            prior_reviews=[prior],
        )
        self.assertEqual(second["status"], "PASS")
        self.assertEqual(second["duplicate_status"], "DUPLICATE_EXACT")
        self.assertFalse(second["owner_identity_authenticated"])
        self.assertFalse(second["release_authorized"])

        conflicting_prior = dict(first)
        conflicting_prior["submission_id"] = "f" * 64
        conflicting_core = dict(conflicting_prior)
        conflicting_core.pop("review_id", None)
        from emotivus_forge.core.external_evidence import canonical_bytes, sha256_bytes
        conflicting_prior["review_id"] = sha256_bytes(canonical_bytes(conflicting_core))
        conflict_path = self.root / "conflicting-prior-review.json"
        write_review_receipt(conflict_path, conflicting_prior)
        conflict = review_external_evidence(
            self.attestation_kit,
            bundle,
            reviewer="reviewer-c",
            prior_reviews=[conflict_path],
        )
        self.assertEqual(conflict["status"], "PASS")
        self.assertEqual(conflict["duplicate_status"], "CONFLICTING_SUBMISSION")
        self.assertFalse(conflict["release_authorized"])

    def test_private_key_material_blocks_return_packaging(self) -> None:
        ceremony = self.attestation_root / "ceremony-private-material"
        self._run(
            self.attestation_root,
            "run-attestation.py",
            "prepare",
            "--public-key",
            str(self.public_key),
            "--output-dir",
            str(ceremony),
        )
        kit_manifest = json.loads((self.attestation_root / "MANIFEST.json").read_text())
        subject = self.attestation_root / kit_manifest["build_manifest"]["path"]
        signature = self.root / "private-material.sig.b64"
        signature.write_text(base64.b64encode(_sign(subject.read_bytes())).decode("ascii") + "\n")
        self._run(
            self.attestation_root,
            "run-attestation.py",
            "finalize",
            "--ceremony-dir",
            str(ceremony),
            "--signature",
            str(signature),
        )
        (ceremony / "accidental-secret.txt").write_bytes(
            b"-----BEGIN " + b"PRIVATE KEY-----\nnot-a-real-key\n"
        )
        result = self._run(
            self.attestation_root,
            "run-attestation.py",
            "package-return",
            "--ceremony-dir",
            str(ceremony),
            "--kit-archive",
            str(self.attestation_kit),
            "--output",
            str(self.root / "blocked-return.zip"),
            expected=1,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("private-key material" in item for item in result["problems"]))

    def test_writer_return_is_recomputed_as_reviewed_candidate_only(self) -> None:
        workspace = self.root / "writer-workspace"
        self._run(
            self.evidence_root,
            "run-evidence.py",
            "prepare-writer",
            "--workspace",
            str(workspace),
            "--controller",
            "controller-a",
            "--controller-assertion",
            "separate controller invocation",
        )
        self._run(
            self.evidence_root,
            "run-evidence.py",
            "writer",
            "--workspace",
            str(workspace),
            "--writer",
            "writer-b",
            "--writer-assertion",
            "separate writer invocation",
        )
        self._run(
            self.evidence_root,
            "run-evidence.py",
            "finish-writer",
            "--workspace",
            str(workspace),
            "--reviewer",
            "reviewer-c",
            "--accepted",
        )
        first = self.root / "writer-return-a.zip"
        second = self.root / "writer-return-b.zip"
        for output in (first, second):
            self._run(
                self.evidence_root,
                "run-evidence.py",
                "package-writer-return",
                "--workspace",
                str(workspace),
                "--kit-archive",
                str(self.evidence_kit),
                "--output",
                str(output),
            )
        self.assertEqual(first.read_bytes(), second.read_bytes())
        review = review_external_evidence(self.evidence_kit, first, reviewer="reviewer-d")
        self.assertEqual(review["status"], "PASS", review["problems"])
        self.assertEqual(review["adjudication_status"], "VERIFIED_REVIEWED_CANDIDATE")
        self.assertEqual(review["administrative_independence"], "NOT_AUTHENTICATED")
        self.assertFalse(review["independent_evidence_claimed"])

    def test_benchmark_return_is_one_bounded_paired_sample(self) -> None:
        packet = self.root / "benchmark-packet"
        self._run(
            self.evidence_root,
            "run-evidence.py",
            "prepare-benchmark",
            "--output-dir",
            str(packet),
            "--provider",
            "Example Provider",
            "--model",
            "Example Model",
        )
        for name, input_tokens, output_tokens in (
            ("forge-run.json", 100, 40),
            ("control-run.json", 160, 60),
        ):
            path = packet / name
            value = json.loads(path.read_text())
            value["exact_input_tokens"] = input_tokens
            value["exact_output_tokens"] = output_tokens
            value["human_review"] = {"reviewer": "reviewer-e", "accepted": True}
            path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
        self._run(
            self.evidence_root,
            "run-evidence.py",
            "finalize-benchmark",
            "--packet-dir",
            str(packet),
        )
        returned = self.root / "benchmark-return.zip"
        self._run(
            self.evidence_root,
            "run-evidence.py",
            "package-benchmark-return",
            "--packet-dir",
            str(packet),
            "--kit-archive",
            str(self.evidence_kit),
            "--output",
            str(returned),
        )
        review = review_external_evidence(self.evidence_kit, returned, reviewer="reviewer-f")
        self.assertEqual(review["status"], "PASS", review["problems"])
        self.assertEqual(review["adjudication_status"], "VERIFIED_PAIRED_SAMPLE")
        self.assertEqual(review["provider_report_authenticity"], "NOT_AUTHENTICATED")
        self.assertFalse(review["independent_evidence_claimed"])
        self.assertFalse(review["release_authorized"])

    def test_tampered_return_bundle_is_rejected(self) -> None:
        original = self._attestation_return("attestation-return-tamper-source.zip")
        tampered = self.root / "attestation-return-tampered.zip"
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(tampered, "w") as target:
            for info in source.infolist():
                content = source.read(info)
                if info.filename.endswith("attestation-receipt.json"):
                    content += b"\n"
                target.writestr(info, content)
        review = review_external_evidence(self.attestation_kit, tampered, reviewer="reviewer-g")
        self.assertEqual(review["status"], "FAIL")
        self.assertTrue(any("payload digest differs" in item for item in review["problems"]))
        self.assertFalse(review["release_authorized"])


if __name__ == "__main__":
    unittest.main()

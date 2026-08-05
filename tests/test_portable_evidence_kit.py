from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from emotivus_forge.core.evidence_kit import (
    EvidenceKitError,
    build_portable_evidence_kit,
    verify_portable_evidence_kit,
)
from tests.support import FORGE_ROOT
from tools.build_forge_package import build_package


class PortableEvidenceKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        cls.runtime = cls.root / "RUN-FORGE-current.zip"
        build_package(FORGE_ROOT, output=cls.runtime, edition="public")
        cls.first = cls.root / "evidence-a.zip"
        cls.second = cls.root / "evidence-b.zip"
        cls.first_result = build_portable_evidence_kit(FORGE_ROOT, cls.runtime, cls.first)
        cls.second_result = build_portable_evidence_kit(FORGE_ROOT, cls.runtime, cls.second)
        cls.extracted_parent = cls.root / "extracted"
        with zipfile.ZipFile(cls.first) as archive:
            archive.extractall(cls.extracted_parent)
        roots = [path for path in cls.extracted_parent.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("evidence kit did not extract to one root")
        cls.kit_root = roots[0]
        cls.runner = cls.kit_root / "run-evidence.py"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def _run(self, *args: str, expected: int = 0) -> dict[str, object]:
        process = subprocess.run(
            [sys.executable, str(self.runner), *args],
            cwd=self.kit_root,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        self.assertEqual(process.returncode, expected, process.stderr or process.stdout)
        return json.loads(process.stdout)

    def test_build_is_deterministic_and_cannot_claim_evidence_or_authorization(self) -> None:
        self.assertEqual(self.first.read_bytes(), self.second.read_bytes())
        self.assertEqual(self.first_result["sha256"], self.second_result["sha256"])
        result = verify_portable_evidence_kit(self.first)
        self.assertEqual(result["status"], "PASS", result["problems"])
        self.assertEqual(result["evidence_status"], "NOT_RUN")
        self.assertFalse(result["release_authorized"])

    def test_tampered_payload_is_rejected(self) -> None:
        tampered = self.root / "tampered.zip"
        with zipfile.ZipFile(self.first) as source, zipfile.ZipFile(tampered, "w") as target:
            for info in source.infolist():
                content = source.read(info)
                if info.filename.endswith("/README.md"):
                    content += b"tampered\n"
                target.writestr(info, content)
        result = verify_portable_evidence_kit(tampered)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("payload digest differs" in problem for problem in result["problems"]))

    def test_runtime_version_mismatch_is_rejected(self) -> None:
        mismatch = self.root / "runtime-mismatch.zip"
        with zipfile.ZipFile(mismatch, "w") as archive:
            archive.writestr("Emotivus-Forge/FORGE-MANIFEST.json", json.dumps({
                "version": "9.999", "edition": "public"
            }))
        with self.assertRaises(EvidenceKitError):
            build_portable_evidence_kit(FORGE_ROOT, mismatch, self.root / "mismatch-kit.zip")

    def test_extracted_kit_verifies_itself(self) -> None:
        result = self._run("verify")
        self.assertEqual(result["status"], "PASS", result["problems"])
        self.assertEqual(result["kit_id"], self.first_result["kit_id"])

    def test_two_process_writer_protocol_detects_post_checkpoint_drift(self) -> None:
        workspace = self.root / "writer-trial"
        prepared = self._run(
            "prepare-writer", "--workspace", str(workspace),
            "--controller", "controller-a",
            "--controller-assertion", "separate controller invocation",
        )
        self.assertEqual(prepared["status"], "READY_FOR_WRITER")
        written = self._run(
            "writer", "--workspace", str(workspace),
            "--writer", "writer-b",
            "--writer-assertion", "separate writer invocation",
        )
        self.assertEqual(written["status"], "MUTATION_COMPLETE")
        finished = self._run(
            "finish-writer", "--workspace", str(workspace),
            "--reviewer", "reviewer-c", "--accepted",
        )
        self.assertEqual(finished["status"], "PASS")
        self.assertEqual(finished["forge_result"]["workspace_integrity_status"], "DRIFTED")
        self.assertFalse(finished["forge_result"]["release_ready"])
        self.assertFalse(finished["independent_evidence_claimed"])
        self.assertEqual(finished["candidate_classification"], "REVIEWED-CANDIDATE")

    def test_benchmark_packet_starts_not_run_and_pairs_only_completed_exact_records(self) -> None:
        packet_dir = self.root / "benchmark"
        prepared = self._run(
            "prepare-benchmark", "--output-dir", str(packet_dir),
            "--provider", "Example Provider", "--model", "Example Model",
        )
        self.assertEqual(prepared["status"], "NOT_RUN")
        for name, input_tokens, output_tokens in (
            ("forge-run.json", 100, 40), ("control-run.json", 160, 60),
        ):
            path = packet_dir / name
            record = json.loads(path.read_text(encoding="utf-8"))
            record["exact_input_tokens"] = input_tokens
            record["exact_output_tokens"] = output_tokens
            record["human_review"] = {"reviewer": "reviewer-c", "accepted": True}
            path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        result = self._run("finalize-benchmark", "--packet-dir", str(packet_dir))
        self.assertEqual(result["status"], "PAIRED")
        self.assertEqual(result["comparison"]["pairs"][0]["token_delta"], -80)
        self.assertTrue(result["comparison"]["workspace_isolation"]["isolated"])
        self.assertFalse(result["independent_evidence_claimed"])
        self.assertFalse(result["release_authorized"])

    def test_incomplete_benchmark_templates_are_refused(self) -> None:
        packet_dir = self.root / "benchmark-incomplete"
        self._run(
            "prepare-benchmark", "--output-dir", str(packet_dir),
            "--provider", "Example Provider", "--model", "Example Model",
        )
        result = self._run("finalize-benchmark", "--packet-dir", str(packet_dir), expected=1)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing required fields", result["error"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from emotivus_forge.core.cold_session_validation import (
    cold_session_summary,
    evaluate_cold_session_validation,
    record_cold_session_validation,
)
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.project_identity import record_project_identity
from emotivus_forge.core.provenance import record_artifact_provenance
from emotivus_forge.core.release_distribution import (
    evaluate_release_distribution,
    record_release_distribution,
)
from emotivus_forge.core.release_package import record_release_package
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.ship import ship_project
from tests.support import FORGE_ROOT, ForgeTestCase

N = int("8481b2735f3204f8a14ecac8a39a5797ebc1e7883b6d7e6937894288d5d9f9d10079cff647c502aa8b790cfefae9e7f39d07c6ff9775c6d94d99285de67796c7a899586db40910885ef41722ac0a5139a4c363b24b3eedd4047229991eeb822440bac92f4f4cfb14bc5bec42d3959ab08eae40b6c09b0370f4eadca72c3d4e42c55b2f4223516f7ab29154fc4ae204bbc7e61f7c3bde4fbe3f96c6e13fc328f0b1e75dff143b929e0b7877665b62fb3ade589aa2e954411826cccf3322e514df1f8dc6646cc9dbea7afa0a7bad8ea264e577472df8bfba18f73c427e71e55f7b4808ef8bc16134796ed3e1406387c4e5dac30614eb4c23b2417848499d6dbae1", 16)
D = int("2f3517d303acc9d99c7a7a436e09fc3ffb35cb5b9d347eaf54a259aa6f69e7971ef0c6f6ea8dd54bd641cbb001cb98a011a7662dc413a942dce2fe5f29cf1c5048904d51542d508f0d29301ee1a51158148ba9f6a8d92418ff767ebc77281766fc0aafc7639cbced1fc82e0d86dd0b4df09f431df8d3a12fba89fc0fb0f2ac71192b52d1d6b7fd8735ebb118b64a6d6103045e19847ec143742080e297ca30d26b4f59eb0848456cbb9941ed11c1a754f6c6216f8d6254fe33eedb61be3a599c31387f5a49c487be96f1412b93a79515a6cdb1b0d5dcb9c95f64d9543a041147717e2116dd7a38d2478a381204f612858012ea865faeb915a75048950a07c95b", 16)
E = 65537
DI_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sign(data: bytes) -> bytes:
    size = (N.bit_length() + 7) // 8
    digest_info = DI_PREFIX + hashlib.sha256(data).digest()
    em = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    return pow(int.from_bytes(em, "big"), D, N).to_bytes(size, "big")


class DistributionFixture(ForgeTestCase):
    def _setup_release(self, root: Path) -> Path:
        self._fixture(root)
        for rel in ("src", "tools", "dist", "release/reviews", "release/signing", "release/channels", "release/cold"):
            (root / rel).mkdir(parents=True, exist_ok=True)
        (root / "src/app.txt").write_text("neutral payload\n", encoding="utf-8")
        (root / "tools/build.py").write_text("# neutral generator\n", encoding="utf-8")
        artifact = root / "dist/public.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("app.txt", "neutral payload\n")
        runtime = root / "dist/run-forge.zip"
        with zipfile.ZipFile(runtime, "w") as archive:
            archive.writestr("forge.py", "# neutral runtime\n")
        build_passport(root, FORGE_ROOT)
        record_project_identity(root, FORGE_ROOT, self._project_identity_contract(root))
        provenance = root / "forge-provenance.json"
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
            "truth_boundary": "This records exact current bytes and declared lineage; it does not prove that the declared command ran or that the final package works after distribution."
        }, indent=2) + "\n", encoding="utf-8")
        record_artifact_provenance(root, FORGE_ROOT, provenance)
        package_sha = _sha(artifact)
        receipt_paths = []
        for review_type in ("security", "privacy", "accessibility", "compatibility", "installation", "upgrade", "rollback"):
            evidence = root / f"release/reviews/{review_type}.md"
            evidence.write_text(f"# {review_type}\n", encoding="utf-8")
            receipt = root / f"release/reviews/{review_type}.json"
            receipt.write_text(json.dumps({
                "schema": 1,
                "review_id": f"review-{review_type}",
                "review_type": review_type,
                "status": "PASS",
                "authority": "reviewer",
                "candidate_build_id": "2026-08-01.1",
                "package_sha256": package_sha,
                "evidence_path": f"release/reviews/{review_type}.md",
                "evidence_sha256": _sha(evidence),
                "reviewed_utc": "2026-08-02T01:00:00Z",
                "limitations": ["Synthetic fixture only."]
            }, indent=2) + "\n", encoding="utf-8")
            receipt_paths.append(f"release/reviews/{review_type}.json")
        package_contract = root / "forge-release-package.json"
        package_contract.write_text(json.dumps({
            "schema": 1,
            "release_package_id": "public-release",
            "title": "Exact public release package",
            "authority": "owner",
            "artifact_path": "dist/public.zip",
            "artifact_provenance_id": "public-package",
            "expected_build_id": "2026-08-01.1",
            "scan": {"max_entries": 100, "max_entry_bytes": 500000, "max_total_text_bytes": 2000000, "forbidden_path_patterns": [], "forbidden_literals": [], "allow_template_paths": True},
            "required_review_types": ["security", "privacy", "accessibility", "compatibility", "installation", "upgrade", "rollback"],
            "review_receipts": receipt_paths,
            "truth_boundary": "This binds one exact ZIP to current identity, provenance, a bounded confidentiality scan, and project-owned review receipts; it does not prove release readiness or review methodology quality."
        }, indent=2) + "\n", encoding="utf-8")
        record_release_package(root, FORGE_ROOT, package_contract)
        return artifact

    def _setup_distribution(self, root: Path, artifact: Path) -> Path:
        key = root / "release/signing/public-key.json"
        key.write_text(json.dumps({
            "schema": 1,
            "algorithm": "rsa-pkcs1v15-sha256",
            "key_id": "neutral-test-key",
            "modulus_hex": f"{N:x}",
            "public_exponent": E
        }, indent=2) + "\n", encoding="utf-8")
        artifact_sig = root / "release/signing/public.zip.sig"
        artifact_sig.write_text(base64.b64encode(_sign(artifact.read_bytes())).decode("ascii") + "\n", encoding="ascii")
        manifest = root / "release/channel-manifest.json"
        manifest.write_text(json.dumps({
            "schema": 1,
            "distribution_id": "public-distribution",
            "release_package_id": "public-release",
            "build_id": "2026-08-01.1",
            "artifact_name": "public.zip",
            "artifact_sha256": _sha(artifact),
            "signature_sha256": _sha(artifact_sig),
            "channels": [{"channel_id": "primary-download", "artifact_uri": "https://example.invalid/download/public.zip", "artifact_sha256": _sha(artifact)}]
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        manifest_sig = root / "release/signing/channel-manifest.sig"
        manifest_sig.write_text(base64.b64encode(_sign(manifest.read_bytes())).decode("ascii") + "\n", encoding="ascii")
        evidence = root / "release/channels/primary.txt"
        evidence.write_text("External CI published the exact digest.\n", encoding="utf-8")
        receipt = root / "release/channels/primary.json"
        receipt.write_text(json.dumps({
            "schema": 1,
            "distribution_id": "public-distribution",
            "channel_id": "primary-download",
            "release_package_id": "public-release",
            "build_id": "2026-08-01.1",
            "artifact_sha256": _sha(artifact),
            "manifest_sha256": _sha(manifest),
            "published_uri": "https://example.invalid/download/public.zip",
            "published_utc": "2026-08-02T02:00:00Z",
            "status": "published",
            "source": "external-ci",
            "verification_tier": "production",
            "evidence_path": "release/channels/primary.txt",
            "evidence_sha256": _sha(evidence)
        }, indent=2) + "\n", encoding="utf-8")
        contract = root / "forge-release-distribution.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "distribution_id": "public-distribution",
            "title": "Signed public distribution",
            "authority": "owner",
            "release_package_id": "public-release",
            "artifact_signature": {"algorithm": "rsa-pkcs1v15-sha256", "public_key_path": "release/signing/public-key.json", "signature_path": "release/signing/public.zip.sig"},
            "channel_manifest_path": "release/channel-manifest.json",
            "channel_manifest_signature": {"algorithm": "rsa-pkcs1v15-sha256", "public_key_path": "release/signing/public-key.json", "signature_path": "release/signing/channel-manifest.sig"},
            "required_channels": ["primary-download"],
            "channel_receipts": ["release/channels/primary.json"],
            "truth_boundary": "This verifies detached signatures and binds signed local channel metadata to project-owned publication receipts. It does not independently prove remote availability, CDN integrity, signer custody, or release readiness."
        }, indent=2) + "\n", encoding="utf-8")
        record_release_distribution(root, FORGE_ROOT, contract)
        return contract

    def _cold_pair(
        self,
        root: Path,
        artifact: Path,
        pair_id: str,
        model: str = "Model-A",
        *,
        reviewer_role: str = "owner",
        task_name: str | None = None,
        baseline_name: str = "baseline-a",
        observed_utc: str | None = None,
        matched_overrides: dict[str, object] | None = None,
    ) -> str:
        runtime = root / "dist/run-forge.zip"
        task_name = task_name or pair_id
        task = root / f"release/cold/task-{task_name}.md"
        task.write_text(f"# task {task_name}\n", encoding="utf-8")
        baseline = root / f"release/cold/{baseline_name}.json"
        if not baseline.exists():
            baseline.write_text(json.dumps({"baseline": baseline_name}, sort_keys=True) + "\n", encoding="utf-8")
        for arm in ("forge", "control"):
            evidence = root / f"release/cold/{pair_id}-{arm}.md"
            evidence.write_text(f"# {pair_id} {arm}\n", encoding="utf-8")
        matched = {
            "same_provider": True,
            "same_model": True,
            "same_model_settings": True,
            "same_task_packet": True,
            "isolated_sessions": True,
            "forge_arm_used_exact_runtime": True,
            "control_arm_had_no_forge_access": True,
        }
        if matched_overrides:
            matched.update(matched_overrides)
        receipt = root / f"release/cold/{pair_id}.json"
        receipt.write_text(json.dumps({
            "schema": 2,
            "validation_id": "cold-release",
            "pair_id": pair_id,
            "host_release_package_id": "public-release",
            "host_package_sha256": _sha(artifact),
            "host_package_bytes": artifact.stat().st_size,
            "forge_runtime_sha256": _sha(runtime),
            "forge_runtime_bytes": runtime.stat().st_size,
            "observed_utc": observed_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "provider": "Neutral Provider",
            "model": model,
            "model_settings_fingerprint": hashlib.sha256(b"temperature=0").hexdigest(),
            "scenario": "continuation",
            "reviewer_role": reviewer_role,
            "reviewer_id": f"reviewer-{pair_id}",
            "arm_order": "randomized",
            "forge_session_id": f"{pair_id}-forge-session",
            "control_session_id": f"{pair_id}-control-session",
            "fresh_agents": True,
            "matched_conditions": matched,
            "task_packet_path": f"release/cold/task-{task_name}.md",
            "task_packet_sha256": _sha(task),
            "host_baseline_manifest_path": f"release/cold/{baseline_name}.json",
            "host_baseline_manifest_sha256": _sha(baseline),
            "forge_arm": {
                "objective_recovery": "correct", "first_action": "correct", "owner_corrections": 0, "time_to_meaningful_minutes": 4,
                "input_tokens": 1000, "output_tokens": 400,
                "evidence_path": f"release/cold/{pair_id}-forge.md", "evidence_sha256": _sha(root / f"release/cold/{pair_id}-forge.md")
            },
            "control_arm": {
                "objective_recovery": "partial", "first_action": "partial", "owner_corrections": 1, "time_to_meaningful_minutes": 7,
                "input_tokens": 1300, "output_tokens": 500,
                "evidence_path": f"release/cold/{pair_id}-control.md", "evidence_sha256": _sha(root / f"release/cold/{pair_id}-control.md")
            }
        }, indent=2) + "\n", encoding="utf-8")
        return f"release/cold/{pair_id}.json"

    def _cold_contract(self, root: Path, receipts: list[str], **overrides: object) -> Path:
        contract = {
            "schema": 2,
            "validation_id": "cold-release",
            "title": "Matched cold continuation evidence",
            "authority": "owner",
            "host_release_package_id": "public-release",
            "forge_runtime_artifact_path": "dist/run-forge.zip",
            "minimum_pairs": 2,
            "minimum_models": 2,
            "minimum_distinct_task_packets": 2,
            "minimum_distinct_host_baselines": 1,
            "minimum_external_review_pairs": 0,
            "maximum_receipt_age_days": 45,
            "required_scenarios": ["continuation"],
            "pair_receipts": receipts,
            "thresholds": {
                "max_forge_incorrect_objective_rate": 0,
                "max_forge_incorrect_first_action_rate": 0,
                "max_forge_owner_corrections_per_pair": 1,
            },
            "truth_boundary": "These human-reviewed matched fresh-agent observations are bounded field evidence for one exact host package and one exact Forge runtime. They are not universal causal proof, commercial validation, authenticated reviewer identity, or evidence for every project, provider, model, or task.",
        }
        contract.update(overrides)
        path = root / "forge-cold-session.json"
        path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        return path



class ReleaseDistributionAndColdSessionTests(DistributionFixture):
    def test_signatures_and_channel_receipt_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            self._setup_distribution(root, artifact)
            result = evaluate_release_distribution(root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["signatures"]["status"], "PASS")
            self.assertEqual(result["channels"]["status"], "PASS")

    def test_changed_artifact_signature_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            self._setup_distribution(root, artifact)
            signature = root / "release/signing/public.zip.sig"
            signature.write_text(base64.b64encode(b"x" * 256).decode("ascii") + "\n", encoding="ascii")
            result = evaluate_release_distribution(root)
            self.assertEqual(result["signatures"]["status"], "FAIL")
            self.assertEqual(result["channels"]["status"], "NOT_RUN")

    def test_stale_channel_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            self._setup_distribution(root, artifact)
            (root / "release/channels/primary.txt").write_text("changed\n", encoding="utf-8")
            result = evaluate_release_distribution(root)
            self.assertEqual(result["channels"]["status"], "FAIL")

    def test_cold_session_contract_passes_minimum_human_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            receipts = [
                self._cold_pair(root, artifact, "pair-1", task_name="task-a"),
                self._cold_pair(root, artifact, "pair-2", model="Model-B", task_name="task-b", reviewer_role="external-reviewer"),
            ]
            record_cold_session_validation(root, FORGE_ROOT, self._cold_contract(root, receipts))
            result = evaluate_cold_session_validation(root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["pair_count"], 2)
            self.assertEqual(result["model_count"], 2)
            self.assertEqual(result["task_packet_count"], 2)
            self.assertNotEqual(result["forge_runtime_sha256"], result["host_package_sha256"])

    def test_controlled_fixtures_do_not_satisfy_real_pair_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            receipts = [
                self._cold_pair(root, artifact, "pair-1", reviewer_role="controlled-fixture", task_name="task-a"),
                self._cold_pair(root, artifact, "pair-2", model="Model-B", reviewer_role="controlled-fixture", task_name="task-b"),
            ]
            record_cold_session_validation(root, FORGE_ROOT, self._cold_contract(root, receipts))
            result = evaluate_cold_session_validation(root)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["pair_count"], 0)
            self.assertEqual(result["fixture_pair_count"], 2)
            self.assertIn("human-reviewed pair minimum", result["coverage_missing"])

    def test_repeated_task_packet_does_not_satisfy_distinct_task_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            receipts = [
                self._cold_pair(root, artifact, "pair-1", task_name="same-task"),
                self._cold_pair(root, artifact, "pair-2", model="Model-B", task_name="same-task"),
            ]
            record_cold_session_validation(root, FORGE_ROOT, self._cold_contract(root, receipts))
            result = evaluate_cold_session_validation(root)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertIn("distinct task-packet coverage", result["coverage_missing"])

    def test_second_active_campaign_requires_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            receipts = [
                self._cold_pair(root, artifact, "pair-1", task_name="task-a"),
                self._cold_pair(root, artifact, "pair-2", model="Model-B", task_name="task-b"),
            ]
            first = self._cold_contract(root, receipts)
            record_cold_session_validation(root, FORGE_ROOT, first)
            second = self._cold_contract(root, receipts, validation_id="cold-release-two")
            with self.assertRaisesRegex(ValueError, "Only one active"):
                record_cold_session_validation(root, FORGE_ROOT, second)

    def test_unmatched_arm_conditions_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            receipts = [
                self._cold_pair(root, artifact, "pair-1", task_name="task-a", matched_overrides={"control_arm_had_no_forge_access": False}),
                self._cold_pair(root, artifact, "pair-2", model="Model-B", task_name="task-b"),
            ]
            record_cold_session_validation(root, FORGE_ROOT, self._cold_contract(root, receipts))
            result = evaluate_cold_session_validation(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["failed_receipts"], 1)

    def test_stale_pair_receipt_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            stale = (datetime.now(timezone.utc) - timedelta(days=60)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            receipts = [
                self._cold_pair(root, artifact, "pair-1", task_name="task-a", observed_utc=stale),
                self._cold_pair(root, artifact, "pair-2", model="Model-B", task_name="task-b"),
            ]
            record_cold_session_validation(root, FORGE_ROOT, self._cold_contract(root, receipts))
            result = evaluate_cold_session_validation(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["failed_receipts"], 1)

    def test_runtime_artifact_drift_invalidates_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            receipts = [
                self._cold_pair(root, artifact, "pair-1", task_name="task-a"),
                self._cold_pair(root, artifact, "pair-2", model="Model-B", task_name="task-b"),
            ]
            record_cold_session_validation(root, FORGE_ROOT, self._cold_contract(root, receipts))
            (root / "dist/run-forge.zip").write_bytes(b"changed runtime")
            result = evaluate_cold_session_validation(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("runtime artifact changed", result["reason"])

    def test_cold_session_partial_and_resume_compact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            receipt = self._cold_pair(root, artifact, "pair-1", task_name="task-a")
            contract = self._cold_contract(root, [receipt], minimum_pairs=3, minimum_models=2, minimum_distinct_task_packets=2)
            record_cold_session_validation(root, FORGE_ROOT, contract)
            self.assertEqual(cold_session_summary(root)["status"], "PARTIAL")
            resume = build_resume(root, FORGE_ROOT, budget="compact")
            self.assertIn("Cold-session validation", resume["markdown"])
            self.assertNotIn("evidence_sha256", resume["markdown"])
            self.assertNotIn("forge_objective_error_rate", resume["markdown"])

    def test_schema_one_contract_is_rejected_for_new_recording(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_release(root)
            legacy = root / "forge-cold-session.json"
            legacy.write_text(json.dumps({
                "schema": 1, "validation_id": "legacy", "title": "Legacy matched trial", "authority": "owner",
                "release_package_id": "public-release", "minimum_pairs": 1, "minimum_models": 1,
                "required_scenarios": ["continuation"], "pair_receipts": ["release/cold/missing.json"],
                "truth_boundary": "Legacy evidence lacks the safeguards required by the current matched-trial contract and cannot support a release claim."
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema 2"):
                record_cold_session_validation(root, FORGE_ROOT, legacy)

    def test_ship_ladder_exposes_signature_channel_and_cold_levels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._setup_release(root)
            self._setup_distribution(root, artifact)
            ship = ship_project(root, FORGE_ROOT)
            ids = [row["level_id"] for row in ship["claim_readiness"]["levels"]]
            self.assertIn("artifact-signature-verified", ids)
            self.assertIn("release-channel-bound", ids)
            self.assertIn("cold-session-validated", ids)
            self.assertFalse(ship["release_ready"])


if __name__ == "__main__":
    unittest.main()

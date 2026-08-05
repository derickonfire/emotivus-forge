from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.project_identity import record_project_identity
from emotivus_forge.core.provenance import record_artifact_provenance
from emotivus_forge.core.release_package import record_release_package
from emotivus_forge.core.release_proof import (
    REQUIRED_DOMAINS,
    evaluate_release_proof,
    record_release_proof,
    release_proof_summary,
    retire_release_proof,
)
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.ship import ship_project
from tests.support import FORGE_ROOT, ForgeTestCase


class ReleaseProofTests(ForgeTestCase):
    required_domains = ("security", "privacy", "accessibility", "compatibility", "runtime")

    def _setup_release_package(self, root: Path) -> tuple[Path, str, int]:
        self._fixture(root)
        (root / "src").mkdir(exist_ok=True)
        (root / "tools").mkdir(exist_ok=True)
        (root / "dist").mkdir(exist_ok=True)
        (root / "release" / "reviews").mkdir(parents=True, exist_ok=True)
        (root / "release" / "proof").mkdir(parents=True, exist_ok=True)
        (root / "src" / "app.txt").write_text("neutral release payload\n", encoding="utf-8")
        (root / "tools" / "build.py").write_text("# deterministic fixture generator\n", encoding="utf-8")
        artifact = root / "dist" / "public.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("app.txt", "neutral release payload\n")
            archive.writestr("README.md", "Public package\n")
        build_passport(root, FORGE_ROOT)
        record_project_identity(root, FORGE_ROOT, self._project_identity_contract(root))
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
        package_bytes = artifact.stat().st_size
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
                "forbidden_literals": [],
                "allow_template_paths": True,
            },
            "required_review_types": ["security", "privacy", "accessibility", "compatibility", "installation", "upgrade", "rollback"],
            "review_receipts": review_paths,
            "truth_boundary": "This binds one exact ZIP to current identity, provenance, a bounded confidentiality scan, and project-owned review receipts; it does not prove release readiness or review methodology quality.",
        }, indent=2) + "\n", encoding="utf-8")
        record_release_package(root, FORGE_ROOT, contract)
        return artifact, package_sha, package_bytes

    def _proof_contract(self, root: Path, *, missing_domain: str = "", missing_member: bool = False, uncovered_readme: bool = False, require_independent: bool = False) -> Path:
        surfaces = [
            {"surface_id": "runtime", "kind": "entrypoint", "description": "Primary packaged runtime payload", "package_members": ["missing.txt" if missing_member else "app.txt"]},
            {"surface_id": "guide", "kind": "documentation", "description": "Packaged operator-facing instructions", "package_members": ["README.md"]},
        ]
        obligations = []
        domains = []
        for domain in REQUIRED_DOMAINS:
            if domain == missing_domain:
                continue
            if domain in self.required_domains:
                obligation_id = f"{domain}-assurance"
                covered = ["runtime"] if uncovered_readme else ["runtime", "guide"]
                obligations.append({
                    "obligation_id": obligation_id,
                    "domain_id": domain,
                    "description": f"Assess the declared package surfaces for {domain} release risk.",
                    "surface_ids": covered,
                    "accepted_evidence_tiers": ["manual-review", "integration", "browser"],
                    "require_independent_reviewer": require_independent and domain == "security",
                    "receipt_path": f"release/proof/{obligation_id}.json",
                })
                domains.append({
                    "domain_id": domain,
                    "applicability": "required",
                    "rationale": f"The public package has a material {domain} assurance obligation before release.",
                    "obligation_ids": [obligation_id],
                })
            else:
                domains.append({
                    "domain_id": domain,
                    "applicability": "not-applicable",
                    "rationale": f"This synthetic package has no separately operated {domain} mechanism in the declared release boundary.",
                    "obligation_ids": [],
                })
        path = root / "forge-release-proof.json"
        path.write_text(json.dumps({
            "schema": 1,
            "release_proof_id": "public-release-proof",
            "title": "Bounded public release assurance map",
            "authority": "owner",
            "release_package_id": "public-release",
            "surfaces": surfaces,
            "domains": domains,
            "obligations": obligations,
            "truth_boundary": "This contract proves only declared exact-package surface presence and current package-bound receipts for explicitly classified assurance domains; it cannot discover undeclared surfaces, validate reviewer competence, execute tests, or authorize release.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def _write_receipts(self, root: Path, package_sha: str, package_bytes: int, *, omit: str = "", mismatch: str = "", expired: str = "", independent: bool = True) -> None:
        for domain in self.required_domains:
            obligation_id = f"{domain}-assurance"
            if domain == omit:
                continue
            evidence = root / "release" / "proof" / f"{obligation_id}.md"
            evidence.write_text(f"# {domain.title()} evidence\n\nScoped assurance evidence for the exact package.\n", encoding="utf-8")
            receipt = root / "release" / "proof" / f"{obligation_id}.json"
            receipt.write_text(json.dumps({
                "schema": 1,
                "release_proof_id": "public-release-proof",
                "obligation_id": obligation_id,
                "release_package_id": "public-release",
                "package_sha256": "0" * 64 if domain == mismatch else package_sha,
                "package_bytes": package_bytes,
                "build_id": "2026-08-01.1",
                "verdict": "PASS",
                "observed_utc": "2026-08-02T01:00:00Z",
                "valid_until_utc": "2026-08-01T01:00:00Z" if domain == expired else "2027-08-02T01:00:00Z",
                "evidence_tier": "manual-review",
                "method": f"Reviewed the declared exact-package surfaces against the bounded {domain} assurance checklist.",
                "surface_ids": ["runtime", "guide"],
                "reviewer": {"authority": "reviewer", "role": f"{domain} reviewer", "independent": independent},
                "evidence_artifacts": [{
                    "path": f"release/proof/{obligation_id}.md",
                    "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    "bytes": evidence.stat().st_size,
                }],
                "limitations": ["Synthetic fixture evidence only."],
                "truth_boundary": "This receipt records one bounded assessment against exact package bytes and named evidence; it does not prove universal correctness or release authorization.",
            }, indent=2) + "\n", encoding="utf-8")

    def test_complete_bounded_release_proof_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes)
            record_release_proof(root, FORGE_ROOT, contract)
            result = evaluate_release_proof(root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["passed_obligations"], 5)
            self.assertEqual(result["surface_count"], 2)
            self.assertEqual(len(result["required_domains"]) + len(result["not_applicable_domains"]), 9)

    def test_missing_required_domain_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_release_package(root)
            contract = self._proof_contract(root, missing_domain="deployment")
            with self.assertRaisesRegex(ValueError, "classify every required domain"):
                record_release_proof(root, FORGE_ROOT, contract)

    def test_absent_package_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_release_package(root)
            contract = self._proof_contract(root, missing_member=True)
            with self.assertRaisesRegex(ValueError, "absent from the exact package"):
                record_release_proof(root, FORGE_ROOT, contract)

    def test_uncovered_surface_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._setup_release_package(root)
            contract = self._proof_contract(root, uncovered_readme=True)
            with self.assertRaisesRegex(ValueError, "Every declared Release Proof surface"):
                record_release_proof(root, FORGE_ROOT, contract)

    def test_missing_receipt_is_partial_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes, omit="privacy")
            record_release_proof(root, FORGE_ROOT, contract)
            result = evaluate_release_proof(root)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertIn("privacy-assurance", result["missing_obligations"])

    def test_package_digest_mismatch_is_contradicted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes, mismatch="security")
            record_release_proof(root, FORGE_ROOT, contract)
            result = evaluate_release_proof(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("security-assurance", result["failed_obligations"])

    def test_expired_receipt_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes, expired="runtime")
            record_release_proof(root, FORGE_ROOT, contract)
            result = evaluate_release_proof(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("runtime-assurance", result["failed_obligations"])

    def test_evidence_artifact_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes)
            record_release_proof(root, FORGE_ROOT, contract)
            (root / "release" / "proof" / "security-assurance.md").write_text("changed evidence\n", encoding="utf-8")
            result = evaluate_release_proof(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("security-assurance", result["failed_obligations"])

    def test_required_independent_reviewer_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root, require_independent=True)
            self._write_receipts(root, package_sha, package_bytes, independent=False)
            record_release_proof(root, FORGE_ROOT, contract)
            result = evaluate_release_proof(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("security-assurance", result["failed_obligations"])

    def test_contract_change_requires_renewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes)
            record_release_proof(root, FORGE_ROOT, contract)
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            result = evaluate_release_proof(root)
            self.assertEqual(result["status"], "FAIL")

    def test_retirement_removes_release_proof_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes)
            record_release_proof(root, FORGE_ROOT, contract)
            retire_release_proof(root, "public-release-proof", "The final package was superseded.")
            self.assertEqual(evaluate_release_proof(root)["status"], "NOT_RUN")

    def test_resume_and_ship_expose_bounded_release_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes)
            record_release_proof(root, FORGE_ROOT, contract)
            resume = build_resume(root, FORGE_ROOT, budget="compact")
            self.assertIn("Release Proof:", resume["markdown"])
            self.assertNotIn(package_sha, resume["markdown"])
            ship = ship_project(root, FORGE_ROOT)
            levels = {item["level_id"]: item for item in ship["claim_readiness"]["levels"]}
            self.assertIn("release-proof-validated", levels)
            self.assertFalse(ship["release_ready"])

    def test_summary_is_compact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _artifact, package_sha, package_bytes = self._setup_release_package(root)
            contract = self._proof_contract(root)
            self._write_receipts(root, package_sha, package_bytes)
            record_release_proof(root, FORGE_ROOT, contract)
            summary = release_proof_summary(root)
            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(summary["domain_ratio"], "9/9")
            self.assertEqual(summary["obligation_ratio"], "5/5")


if __name__ == "__main__":
    import unittest
    unittest.main()

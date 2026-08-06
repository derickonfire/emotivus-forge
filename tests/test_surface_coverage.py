from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.support import FORGE_ROOT, ForgeTestCase
from emotivus_forge.core.lineage import exact_directory_tree, exact_zip_tree, record_project_lineage
from emotivus_forge.core.package_family import record_package_family
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.ship_claims import assess_ship_claims
from emotivus_forge.core.surface_coverage import record_surface_coverage, retire_surface_coverage, surface_coverage_summary


class SurfaceCoverageTests(ForgeTestCase):
    def _zip(self, path: Path, files: dict[str, str], prefix: str = "Project") -> Path:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, content in sorted(files.items()):
                archive.writestr(f"{prefix}/{relative}", content)
        return path

    def _setup_lineage_and_family(self, root: Path) -> None:
        self._fixture(root)
        build_passport(root, FORGE_ROOT)
        lineage_contract = root / "lineage.json"
        tree = exact_directory_tree(root, FORGE_ROOT, exclude_paths=[lineage_contract.name])
        lineage_contract.write_text(json.dumps({
            "schema": 1,
            "lineage_id": "lineage-current",
            "authority": "owner",
            "declared_version": "1.2.0",
            "build_id": "build-120",
            "relationship": "initial",
            "current": {"tree_sha256": tree["tree_sha256"], "tree_file_count": tree["file_count"]},
            "collision_declaration": {},
            "truth_boundary": "The owner declares lineage intent while Forge verifies exact normalized bytes without proving authorship or semantic correctness.",
        }, indent=2) + "\n", encoding="utf-8")
        record_project_lineage(root, FORGE_ROOT, lineage_contract)

        result = self._zip(root / "Result.zip", {
            "index.php": (root / "index.php").read_text(encoding="utf-8"),
            "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
        })
        result_tree = exact_zip_tree(result, strip_prefix="Project")
        family_contract = root / "package-family.json"
        family_contract.write_text(json.dumps({
            "schema": 1,
            "family_id": "family-120",
            "authority": "owner",
            "lineage_id": "lineage-current",
            "release_version": "1.2.0",
            "build_id": "build-120",
            "artifacts": [{
                "artifact_id": "result",
                "role": "full-site",
                "path": result.name,
                "sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
                "bytes": result.stat().st_size,
                "strip_prefix": "Project",
                "tree_sha256": result_tree["tree_sha256"],
                "tree_file_count": result_tree["file_count"],
            }],
            "outer_bundles": [],
            "deltas": [],
            "truth_boundary": "Forge proves exact package-family bytes but does not execute the application or establish semantic behavior.",
        }, indent=2) + "\n", encoding="utf-8")
        record_package_family(root, FORGE_ROOT, family_contract)

    def _receipt(self, root: Path, receipt_id: str, surfaces: list[str], tier: str, *, days: int = 30) -> dict[str, object]:
        evidence = root / f"{receipt_id}.txt"
        evidence.write_text(f"Evidence for {receipt_id}\n", encoding="utf-8")
        now = datetime.now(timezone.utc)
        return {
            "receipt_id": receipt_id,
            "surface_ids": surfaces,
            "tier": tier,
            "result": "PASS",
            "package_family_id": "family-120",
            "source_artifact_id": "result",
            "environment": "bounded test environment",
            "method": "A human reviewer executed the declared scoped procedure and recorded the result.",
            "reviewer": "independent reviewer",
            "observed_utc": (now - timedelta(days=1)).isoformat(),
            "expires_utc": (now + timedelta(days=days)).isoformat(),
            "evidence_path": evidence.name,
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "evidence_bytes": evidence.stat().st_size,
            "limitations": "This receipt covers only the named surface and explicit evidence tier.",
            "truth_boundary": "The receipt does not imply any unlisted evidence tier, route, user role, environment, or deployment behavior.",
        }

    def _contract(self, root: Path, *, receipts: list[dict[str, object]] | None = None, journey_required: str = "browser-tested") -> Path:
        contract = root / "surface-coverage.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "inventory_id": "surface-map-120",
            "authority": "owner",
            "lineage_id": "lineage-current",
            "release_version": "1.2.0",
            "build_id": "build-120",
            "package_family_id": "family-120",
            "source_artifact_id": "result",
            "surfaces": [
                {
                    "surface_id": "route-home",
                    "type": "route",
                    "title": "Home route",
                    "audiences": ["staff"],
                    "entrypoints": ["index.php"],
                    "steps": [],
                    "route": "/index.php",
                    "required_tier": "static-inspected",
                    "scope": "The public home route and its exact server entrypoint.",
                },
                {
                    "surface_id": "journey-login-home",
                    "type": "journey",
                    "title": "Login to home journey",
                    "audiences": ["staff"],
                    "entrypoints": [],
                    "steps": ["route-home"],
                    "route": "",
                    "required_tier": journey_required,
                    "scope": "The bounded staff journey that ends on the home route.",
                },
            ],
            "receipts": receipts or [],
            "truth_boundary": "Forge maps exact package surfaces to explicit receipts without inferring that source existence proves database, authentication, browser, device, staging, production, or deployment behavior.",
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def test_exact_surface_inventory_and_explicit_tiers_are_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup_lineage_and_family(root)
            receipts = [
                self._receipt(root, "static-home", ["route-home"], "static-inspected"),
                self._receipt(root, "browser-journey", ["journey-login-home"], "browser-tested"),
            ]
            record = record_surface_coverage(root, FORGE_ROOT, self._contract(root, receipts=receipts))
            self.assertEqual(record["coverage_counts"]["complete"], 2)
            summary = surface_coverage_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CURRENT")
            self.assertEqual(summary["coverage_status"], "COMPLETE")
            journey = next(row for row in summary["coverage_matrix"] if row["surface_id"] == "journey-login-home")
            self.assertEqual(journey["tier_statuses"]["browser-tested"], "PASS")
            self.assertEqual(journey["tier_statuses"]["authenticated-executed"], "NOT_RUN")
            levels = {row["level_id"]: row for row in assess_ship_claims(root, FORGE_ROOT)["levels"]}
            requirements = {row["requirement_id"]: row for row in levels["surface-coverage-mapped-candidate"]["requirements"]}
            self.assertEqual(requirements["exact-surface-inventory"]["status"], "PASS")
            self.assertEqual(requirements["project-required-surface-evidence"]["status"], "PASS")

    def test_route_existence_does_not_prove_browser_journey(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup_lineage_and_family(root)
            receipts = [self._receipt(root, "static-home", ["route-home"], "static-inspected")]
            record_surface_coverage(root, FORGE_ROOT, self._contract(root, receipts=receipts))
            summary = surface_coverage_summary(root, FORGE_ROOT)
            self.assertEqual(summary["coverage_status"], "GAPS")
            journey = next(row for row in summary["coverage_matrix"] if row["surface_id"] == "journey-login-home")
            self.assertEqual(journey["highest_explicit_pass_tier"], "source-exists")
            self.assertEqual(journey["required_tier_status"], "NOT_RUN")
            levels = {row["level_id"]: row for row in assess_ship_claims(root, FORGE_ROOT)["levels"]}
            requirements = {row["requirement_id"]: row for row in levels["surface-coverage-mapped-candidate"]["requirements"]}
            self.assertEqual(requirements["project-required-surface-evidence"]["status"], "FAIL")

    def test_missing_exact_artifact_entrypoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup_lineage_and_family(root)
            contract = self._contract(root)
            payload = json.loads(contract.read_text(encoding="utf-8"))
            payload["surfaces"][0]["entrypoints"] = ["missing.php"]
            contract.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not present in the exact source artifact"):
                record_surface_coverage(root, FORGE_ROOT, contract)

    def test_evidence_drift_contradicts_recorded_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup_lineage_and_family(root)
            receipt = self._receipt(root, "static-home", ["route-home"], "static-inspected")
            record_surface_coverage(root, FORGE_ROOT, self._contract(root, receipts=[receipt]))
            (root / "static-home.txt").write_text("changed evidence\n", encoding="utf-8")
            summary = surface_coverage_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CONTRADICTED")
            self.assertIn("immutable evidence identity", summary["reason"])

    def test_expired_receipt_remains_visible_as_stale_gap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup_lineage_and_family(root)
            receipt = self._receipt(root, "static-home", ["route-home"], "static-inspected", days=-1)
            # Rebuild a valid historical window that is now expired.
            now = datetime.now(timezone.utc)
            receipt["observed_utc"] = (now - timedelta(days=10)).isoformat()
            receipt["expires_utc"] = (now - timedelta(days=1)).isoformat()
            record_surface_coverage(root, FORGE_ROOT, self._contract(root, receipts=[receipt], journey_required="source-exists"))
            summary = surface_coverage_summary(root, FORGE_ROOT)
            route = next(row for row in summary["coverage_matrix"] if row["surface_id"] == "route-home")
            self.assertEqual(route["required_tier_status"], "STALE")
            self.assertEqual(summary["coverage_status"], "GAPS")

    def test_receipt_must_bind_active_family_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup_lineage_and_family(root)
            receipt = self._receipt(root, "static-home", ["route-home"], "static-inspected")
            receipt["source_artifact_id"] = "some-other-result"
            with self.assertRaisesRegex(ValueError, "not bound to the active"):
                record_surface_coverage(root, FORGE_ROOT, self._contract(root, receipts=[receipt]))

    def test_retirement_is_separate_and_removes_current_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup_lineage_and_family(root)
            record_surface_coverage(root, FORGE_ROOT, self._contract(root, receipts=[] , journey_required="source-exists"))
            retire_surface_coverage(root, "surface-map-120", "This surface inventory was superseded by a separately reviewed release map.")
            self.assertEqual(surface_coverage_summary(root, FORGE_ROOT)["status"], "NOT_DECLARED")

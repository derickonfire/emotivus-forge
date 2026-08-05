from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from tests.support import FORGE_ROOT, ForgeTestCase
from emotivus_forge.core.lineage import exact_directory_tree, exact_zip_tree, record_project_lineage
from emotivus_forge.core.package_family import record_package_family
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.paths import ForgePaths
from emotivus_forge.core.release_facts import record_release_facts, release_facts_summary, retire_release_facts
from emotivus_forge.core.ship_claims import CLAIM_ORDER, assess_ship_claims
from emotivus_forge.core.common import write_json


class ReleaseFactsTests(ForgeTestCase):
    def _setup(self, root: Path, *, version_text: str = "1.2.0", native_status: str = "NOT_RUN") -> None:
        self._fixture(root)
        (root / "README.md").write_text(
            f"# Product\n\nCurrent version: **{version_text}**\n\nSettings schema: **21**\n\nNative status: **{native_status}**\n",
            encoding="utf-8",
        )
        build_passport(root, FORGE_ROOT)
        passport = json.loads(ForgePaths(root).passport.read_text(encoding="utf-8"))
        passport.setdefault("evidence", {})["native_gate"] = {"status": native_status, "validity": "current", "regression_count": 12}
        write_json(ForgePaths(root).passport, passport)
        lineage_path = root / "lineage.json"
        tree = exact_directory_tree(root, FORGE_ROOT, exclude_paths=[lineage_path.name])
        lineage_path.write_text(json.dumps({
            "schema": 1, "lineage_id": "lineage-current", "authority": "owner",
            "declared_version": "1.2.0", "build_id": "build-120", "relationship": "initial",
            "current": {"tree_sha256": tree["tree_sha256"], "tree_file_count": tree["file_count"]},
            "collision_declaration": {},
            "truth_boundary": "The owner declares lineage while Forge verifies exact normalized bytes without proving authorship or semantic correctness.",
        }, indent=2) + "\n", encoding="utf-8")
        record_project_lineage(root, FORGE_ROOT, lineage_path)
        result = root / "Result.zip"
        with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in ("index.php", "BACKLOG.md", "README.md"):
                archive.writestr(f"Project/{name}", (root / name).read_bytes())
        result_tree = exact_zip_tree(result, strip_prefix="Project")
        family_path = root / "package-family.json"
        family_path.write_text(json.dumps({
            "schema": 1, "family_id": "family-120", "authority": "owner", "lineage_id": "lineage-current",
            "release_version": "1.2.0", "build_id": "build-120",
            "artifacts": [{
                "artifact_id": "result", "role": "full-site", "path": result.name,
                "sha256": hashlib.sha256(result.read_bytes()).hexdigest(), "bytes": result.stat().st_size,
                "strip_prefix": "Project", "tree_sha256": result_tree["tree_sha256"], "tree_file_count": result_tree["file_count"],
            }],
            "outer_bundles": [], "deltas": [],
            "truth_boundary": "Forge proves exact package bytes and normalized trees without executing the application or proving semantic behavior.",
        }, indent=2) + "\n", encoding="utf-8")
        record_package_family(root, FORGE_ROOT, family_path)

    def _contract(self, root: Path, *, include_native: bool = False, forbidden: list[str] | None = None) -> Path:
        facts = [
            {"fact_id": "release-version", "source": "lineage.version"},
            {"fact_id": "settings-schema", "source": "forge.settings_schema"},
        ]
        assertions = [
            {"fact_id": "release-version", "prefix": "Current version: **", "suffix": "**", "occurrences": 1},
            {"fact_id": "settings-schema", "prefix": "Settings schema: **", "suffix": "**", "occurrences": 1},
        ]
        if include_native:
            facts.append({"fact_id": "native-status", "source": "native.status"})
            assertions.append({"fact_id": "native-status", "prefix": "Native status: **", "suffix": "**", "occurrences": 1})
        path = root / "release-facts.json"
        path.write_text(json.dumps({
            "schema": 1, "fact_set_id": "release-facts-120", "authority": "owner",
            "lineage_id": "lineage-current", "release_version": "1.2.0", "build_id": "build-120",
            "package_family_id": "family-120", "source_artifact_id": "result",
            "facts": facts,
            "documents": [{"path": "README.md", "assertions": assertions, "forbidden_literals": forbidden or []}],
            "truth_boundary": "Forge checks only the declared visible fields inside the exact package and does not understand arbitrary prose or prove substantive correctness.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def test_current_exact_packaged_release_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup(root)
            record_release_facts(root, FORGE_ROOT, self._contract(root))
            summary = release_facts_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CURRENT")
            self.assertEqual(summary["check_count"], 2)
            self.assertEqual(summary["failed_count"], 0)

    def test_stale_visible_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup(root, version_text="1.1.9")
            with self.assertRaisesRegex(ValueError, "stale or contradictory"):
                record_release_facts(root, FORGE_ROOT, self._contract(root))

    def test_forbidden_legacy_literal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup(root)
            with self.assertRaisesRegex(ValueError, "stale or contradictory"):
                record_release_facts(root, FORGE_ROOT, self._contract(root, forbidden=["Current version: **1.2.0**"]))

    def test_artifact_drift_contradicts_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup(root)
            record_release_facts(root, FORGE_ROOT, self._contract(root))
            with zipfile.ZipFile(root / "Result.zip", "a") as archive:
                archive.writestr("Project/extra.txt", "drift")
            self.assertEqual(release_facts_summary(root, FORGE_ROOT)["status"], "CONTRADICTED")

    def test_dynamic_native_fact_change_becomes_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup(root, native_status="PASS")
            record_release_facts(root, FORGE_ROOT, self._contract(root, include_native=True))
            passport = json.loads(ForgePaths(root).passport.read_text(encoding="utf-8"))
            passport["evidence"]["native_gate"]["status"] = "FAIL"
            write_json(ForgePaths(root).passport, passport)
            self.assertEqual(release_facts_summary(root, FORGE_ROOT)["status"], "STALE")

    def test_retirement_is_separate_and_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._setup(root)
            record_release_facts(root, FORGE_ROOT, self._contract(root))
            retire_release_facts(root, "release-facts-120", "The exact release package was superseded by a newer build.")
            self.assertEqual(release_facts_summary(root, FORGE_ROOT)["status"], "NOT_DECLARED")

    def test_ship_order_contains_release_fact_rung(self) -> None:
        self.assertIn("release-facts-current-candidate", CLAIM_ORDER)
        self.assertLess(CLAIM_ORDER.index("native-verified-candidate"), CLAIM_ORDER.index("release-facts-current-candidate"))
        self.assertLess(CLAIM_ORDER.index("release-facts-current-candidate"), CLAIM_ORDER.index("runtime-content-verified"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._fixture(root); build_passport(root, FORGE_ROOT)
            levels = [row["level_id"] for row in assess_ship_claims(root, FORGE_ROOT)["levels"]]
            self.assertEqual(tuple(levels), CLAIM_ORDER)


if __name__ == "__main__":
    import unittest
    unittest.main()

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from tests.support import FORGE_ROOT, ForgeTestCase
from emotivus_forge.core.lineage import exact_directory_tree, exact_zip_tree, record_project_lineage
from emotivus_forge.core.package_family import package_family_summary, record_package_family, retire_package_family
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.ship_claims import assess_ship_claims


class PackageFamilyTests(ForgeTestCase):
    def _zip(self, path: Path, files: dict[str, bytes | str], prefix: str = "Project") -> Path:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, content in sorted(files.items()):
                archive.writestr(f"{prefix}/{relative}" if prefix else relative, content)
        return path

    def _artifact(self, path: Path, artifact_id: str, role: str, prefix: str = "Project") -> dict[str, object]:
        tree = exact_zip_tree(path, strip_prefix=prefix)
        return {
            "artifact_id": artifact_id,
            "role": role,
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "strip_prefix": prefix,
            "tree_sha256": tree["tree_sha256"],
            "tree_file_count": tree["file_count"],
        }

    def _lineage(self, root: Path) -> None:
        contract = root / "lineage.json"
        tree = exact_directory_tree(root, FORGE_ROOT, exclude_paths=[contract.name])
        contract.write_text(json.dumps({
            "schema": 1,
            "lineage_id": "lineage-current",
            "authority": "owner",
            "declared_version": "1.1.0",
            "build_id": "build-110",
            "relationship": "initial",
            "current": {"tree_sha256": tree["tree_sha256"], "tree_file_count": tree["file_count"]},
            "collision_declaration": {},
            "truth_boundary": "The owner declares lineage intent while Forge verifies exact normalized bytes without proving authorship or semantic correctness.",
        }, indent=2) + "\n", encoding="utf-8")
        record_project_lineage(root, FORGE_ROOT, contract)

    def _family_fixture(self, root: Path) -> Path:
        parent = self._zip(root / "Parent.zip", {
            "index.php": "<?php echo 'old';\n",
            "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
        })
        result = self._zip(root / "Result.zip", {
            "index.php": (root / "index.php").read_text(encoding="utf-8"),
            "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
        })
        delta = self._zip(root / "Changed.zip", {"index.php": (root / "index.php").read_text(encoding="utf-8")}, prefix="Payload")
        outer = root / "All-Exports.zip"
        with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("packages/Parent.zip", parent.read_bytes())
            archive.writestr("packages/Result.zip", result.read_bytes())
            archive.writestr("packages/Changed.zip", delta.read_bytes())
        artifacts = [
            self._artifact(parent, "parent", "full-site"),
            self._artifact(result, "result", "full-site"),
            self._artifact(delta, "delta", "changed-files", prefix="Payload"),
            self._artifact(outer, "outer", "outer-bundle", prefix=""),
        ]
        contract = root / "package-family.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "family_id": "family-110",
            "authority": "owner",
            "lineage_id": "lineage-current",
            "release_version": "1.1.0",
            "build_id": "build-110",
            "artifacts": artifacts,
            "outer_bundles": [{
                "artifact_id": "outer",
                "members": [
                    {"artifact_id": "parent", "member_path": "packages/Parent.zip"},
                    {"artifact_id": "result", "member_path": "packages/Result.zip"},
                    {"artifact_id": "delta", "member_path": "packages/Changed.zip"},
                ],
            }],
            "deltas": [{
                "delta_id": "parent-to-result",
                "parent_artifact_id": "parent",
                "delta_artifact_id": "delta",
                "result_artifact_id": "result",
                "payload_prefix": "Payload",
                "control_paths": [],
                "added_paths": [],
                "modified_paths": ["index.php"],
                "deleted_paths": [],
                "renamed_paths": [],
            }],
            "truth_boundary": "Forge proves exact package-family bytes and deterministic delta reconstruction but does not execute the software or prove semantic upgrade safety.",
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def test_exact_family_outer_bundle_and_delta_are_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._fixture(root); build_passport(root, FORGE_ROOT); self._lineage(root)
            record = record_package_family(root, FORGE_ROOT, self._family_fixture(root))
            self.assertEqual(record["lineage_result_artifact_ids"], ["result"])
            self.assertEqual(record["deltas"][0]["reconstructed_tree_sha256"], next(row["tree_sha256"] for row in record["artifacts"] if row["artifact_id"] == "result"))
            summary = package_family_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CURRENT")
            self.assertEqual(summary["artifact_count"], 4)
            levels = {row["level_id"]: row for row in assess_ship_claims(root, FORGE_ROOT)["levels"]}
            requirement = {row["requirement_id"]: row for row in levels["package-family-identified-candidate"]["requirements"]}
            self.assertEqual(requirement["exact-package-family"]["status"], "PASS")

    def test_delta_cannot_claim_wrong_modified_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._fixture(root); build_passport(root, FORGE_ROOT); self._lineage(root)
            contract = self._family_fixture(root)
            payload = json.loads(contract.read_text(encoding="utf-8")); payload["deltas"][0]["modified_paths"] = []
            contract.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "modified_paths"):
                record_package_family(root, FORGE_ROOT, contract)

    def test_outer_bundle_member_must_equal_exact_child_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._fixture(root); build_passport(root, FORGE_ROOT); self._lineage(root)
            contract = self._family_fixture(root)
            outer = root / "All-Exports.zip"
            with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("packages/Parent.zip", (root / "Parent.zip").read_bytes())
                archive.writestr("packages/Result.zip", b"not-the-result")
                archive.writestr("packages/Changed.zip", (root / "Changed.zip").read_bytes())
            payload = json.loads(contract.read_text(encoding="utf-8"))
            payload["artifacts"][-1] = self._artifact(outer, "outer", "outer-bundle", prefix="")
            contract.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not equal artifact result"):
                record_package_family(root, FORGE_ROOT, contract)

    def test_artifact_drift_contradicts_recorded_family(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._fixture(root); build_passport(root, FORGE_ROOT); self._lineage(root)
            record_package_family(root, FORGE_ROOT, self._family_fixture(root))
            (root / "Result.zip").write_bytes((root / "Result.zip").read_bytes() + b"drift")
            summary = package_family_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CONTRADICTED")
            self.assertIn("identity", summary["reason"])

    def test_retirement_is_separate_and_removes_current_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._fixture(root); build_passport(root, FORGE_ROOT); self._lineage(root)
            record_package_family(root, FORGE_ROOT, self._family_fixture(root))
            retire_package_family(root, "family-110", "This package family was superseded by a separately reviewed release family.")
            self.assertEqual(package_family_summary(root, FORGE_ROOT)["status"], "NOT_DECLARED")

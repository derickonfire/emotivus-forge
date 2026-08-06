from __future__ import annotations

import hashlib
import os
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from tests.support import FORGE_ROOT, ForgeTestCase
from emotivus_forge.core.lineage import (
    assess_project_lineage,
    exact_directory_tree,
    exact_zip_tree,
    lineage_summary,
    record_merge_candidate,
    record_project_lineage,
    resolve_merge_candidate,
)
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.state import load_settings, load_state
from emotivus_forge.core.ship_claims import assess_ship_claims


class LineageTests(ForgeTestCase):
    def _zip(self, path: Path, files: dict[str, bytes | str], *, prefix: str = "Project") -> Path:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, content in sorted(files.items()):
                data = content.encode("utf-8") if isinstance(content, str) else content
                archive.writestr(f"{prefix}/{relative}", data)
        return path

    def _archive_row(self, path: Path, *, version: str, build_id: str, prefix: str = "Project") -> dict[str, object]:
        tree = exact_zip_tree(path, strip_prefix=prefix)
        return {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "declared_version": version,
            "build_id": build_id,
            "strip_prefix": prefix,
            "tree_sha256": tree["tree_sha256"],
            "tree_file_count": tree["file_count"],
        }

    def _lineage_contract(
        self,
        root: Path,
        *,
        lineage_id: str,
        version: str,
        build_id: str,
        parent: dict[str, object] | None = None,
        relationship: str = "initial",
        collision: dict[str, object] | None = None,
        filename: str | None = None,
    ) -> Path:
        name = filename or f"{lineage_id}.json"
        path = root / name
        exclusions = [name]
        if parent:
            exclusions.append(str(parent["path"]))
        settings = load_settings(root)
        exclusions.extend(str(item) for item in settings.get("lineage_control_paths", []))
        current = exact_directory_tree(root, FORGE_ROOT, exclude_paths=exclusions)
        payload = {
            "schema": 1,
            "lineage_id": lineage_id,
            "authority": "owner",
            "declared_version": version,
            "build_id": build_id,
            "relationship": relationship,
            "parent": parent,
            "current": {
                "tree_sha256": current["tree_sha256"],
                "tree_file_count": current["file_count"],
            },
            "collision_declaration": collision or {},
            "truth_boundary": "The owner declares the intended lineage relationship; Forge verifies exact package and tree bytes but not authorship or semantic compatibility.",
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _record_initial(self, root: Path, *, version: str = "1.0.0", lineage_id: str = "lineage-a") -> Path:
        contract = self._lineage_contract(
            root,
            lineage_id=lineage_id,
            version=version,
            build_id=f"build-{lineage_id}",
        )
        record_project_lineage(root, FORGE_ROOT, contract)
        return contract

    def _candidate_contract(
        self,
        root: Path,
        *,
        candidate_id: str,
        version: str,
        parent: dict[str, object],
        incoming: dict[str, object],
    ) -> Path:
        path = root / f"{candidate_id}.json"
        path.write_text(json.dumps({
            "schema": 1,
            "candidate_id": candidate_id,
            "authority": "owner",
            "declared_version": version,
            "build_id": f"build-{candidate_id}",
            "parent": parent,
            "incoming": incoming,
            "truth_boundary": "The candidate record proves exact ancestry and path differences but does not apply, merge, approve, or authorize the branch.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def test_exact_tree_identity_ignores_mtime_but_detects_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            first = exact_directory_tree(root, FORGE_ROOT)
            stat = (root / "index.php").stat()
            os.utime(root / "index.php", ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
            second = exact_directory_tree(root, FORGE_ROOT)
            self.assertNotEqual((root / "index.php").stat().st_mtime_ns, stat.st_mtime_ns)
            self.assertEqual(first["tree_sha256"], second["tree_sha256"])
            (root / "index.php").write_text("<?php echo 'different';\n", encoding="utf-8")
            third = exact_directory_tree(root, FORGE_ROOT)
            self.assertNotEqual(first["tree_sha256"], third["tree_sha256"])

    def test_parent_bound_lineage_validates_exact_archive_and_current_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            parent_zip = self._zip(root / "parent.zip", {
                "index.php": "<?php echo 'parent';\n",
                "BACKLOG.md": "# Parent backlog\n",
            })
            parent = self._archive_row(parent_zip, version="0.9.0", build_id="build-parent")
            contract = self._lineage_contract(
                root,
                lineage_id="lineage-current",
                version="1.0.0",
                build_id="build-current",
                parent=parent,
                relationship="continuation",
            )
            record = record_project_lineage(root, FORGE_ROOT, contract)
            self.assertEqual(record["parent"]["sha256"], parent["sha256"])
            self.assertEqual(assess_project_lineage(root, FORGE_ROOT)["status"], "CURRENT")
            parent_zip.write_bytes(parent_zip.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "exact package identity does not match"):
                record_project_lineage(root, FORGE_ROOT, contract)

    def test_same_version_different_tree_requires_explicit_collision_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._record_initial(root)
            old_parent_zip = self._zip(root / "old-parent.zip", {
                "index.php": (root / "index.php").read_text(encoding="utf-8"),
                "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
            })
            old_parent = self._archive_row(old_parent_zip, version="1.0.0", build_id="build-lineage-a")
            (root / "index.php").write_text("<?php echo 'new exact tree';\n", encoding="utf-8")
            second = self._lineage_contract(
                root,
                lineage_id="lineage-b",
                version="1.0.0",
                build_id="build-b",
                parent=old_parent,
                relationship="supersession",
            )
            with self.assertRaisesRegex(ValueError, "declared version already maps to a different exact tree"):
                record_project_lineage(root, FORGE_ROOT, second)
            second = self._lineage_contract(
                root,
                lineage_id="lineage-b",
                version="1.0.0",
                build_id="build-b",
                parent=old_parent,
                relationship="supersession",
                collision={
                    "type": "supersession",
                    "reason": "The owner intentionally replaces the earlier mislabeled tree without claiming byte identity.",
                    "collides_with": ["lineage-a"],
                },
            )
            record = record_project_lineage(root, FORGE_ROOT, second)
            self.assertEqual(record["collision_declaration"]["type"], "supersession")
            assessment = assess_project_lineage(root, FORGE_ROOT)
            self.assertEqual(assessment["active_lineage_id"], "lineage-b")
            self.assertIn("1.0.0", assessment["version_collisions"])

    def test_unmatched_parent_is_quarantined_without_mutating_baseline_or_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._record_initial(root, version="1.0.0")
            before_state = load_state(root)
            parent_zip = self._zip(root / "other-parent.zip", {
                "index.php": "<?php echo 'other parent';\n",
                "BACKLOG.md": "# Other\n",
            })
            incoming_zip = self._zip(root / "incoming.zip", {
                "index.php": "<?php echo 'incoming';\n",
                "BACKLOG.md": "# Incoming\n",
                "new.php": "<?php echo 'new';\n",
            })
            contract = self._candidate_contract(
                root,
                candidate_id="branch-x",
                version="1.0.0",
                parent=self._archive_row(parent_zip, version="0.9.0", build_id="other-parent"),
                incoming=self._archive_row(incoming_zip, version="1.0.0", build_id="incoming-build"),
            )
            record = record_merge_candidate(root, FORGE_ROOT, contract)
            self.assertEqual(record["status"], "merge-candidate")
            self.assertFalse(record["parent_matches_authority"])
            self.assertTrue(record["same_version_collision"])
            self.assertIn("new.php", record["authority_to_incoming"]["added"])
            after_state = load_state(root)
            self.assertEqual(before_state.get("snapshot"), after_state.get("snapshot"))
            self.assertEqual(before_state.get("authority_baseline"), after_state.get("authority_baseline"))
            summary = lineage_summary(root, FORGE_ROOT)
            self.assertEqual(summary["unmatched_parent_count"], 1)
            self.assertEqual(summary["same_version_candidate_collision_count"], 1)

    def test_matching_parent_candidate_is_identified_and_rename_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._record_initial(root, version="1.0.0")
            parent_zip = self._zip(root / "parent.zip", {
                "index.php": (root / "index.php").read_text(encoding="utf-8"),
                "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
            })
            incoming_zip = self._zip(root / "incoming.zip", {
                "main.php": (root / "index.php").read_text(encoding="utf-8"),
                "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
            })
            contract = self._candidate_contract(
                root,
                candidate_id="branch-y",
                version="1.1.0",
                parent=self._archive_row(parent_zip, version="1.0.0", build_id="build-lineage-a"),
                incoming=self._archive_row(incoming_zip, version="1.1.0", build_id="incoming-y"),
            )
            record = record_merge_candidate(root, FORGE_ROOT, contract)
            self.assertEqual(record["status"], "lineage-matched-candidate")
            self.assertTrue(record["parent_matches_authority"])
            self.assertEqual(record["parent_to_incoming"]["renamed"][0]["from"], "index.php")
            self.assertEqual(record["parent_to_incoming"]["renamed"][0]["to"], "main.php")

    def test_candidate_resolution_never_authorizes_or_applies_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._record_initial(root)
            parent_zip = self._zip(root / "parent.zip", {
                "index.php": (root / "index.php").read_text(encoding="utf-8"),
                "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
            })
            incoming_zip = self._zip(root / "incoming.zip", {
                "index.php": "<?php echo 'candidate';\n",
                "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
            })
            contract = self._candidate_contract(
                root,
                candidate_id="branch-z",
                version="1.1.0",
                parent=self._archive_row(parent_zip, version="1.0.0", build_id="parent"),
                incoming=self._archive_row(incoming_zip, version="1.1.0", build_id="incoming"),
            )
            record_merge_candidate(root, FORGE_ROOT, contract)
            before = (root / "index.php").read_bytes()
            state_before = load_state(root)
            resolved = resolve_merge_candidate(
                root,
                "branch-z",
                "approved-for-reconciliation",
                "The owner approved reviewing and manually reconciling this exact branch, not adopting it wholesale.",
            )
            self.assertTrue(resolved["resolution"]["does_not_authorize_tree"])
            self.assertEqual((root / "index.php").read_bytes(), before)
            self.assertEqual(load_state(root), state_before)

    def test_lineage_source_drift_blocks_check_and_ship_level(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            contract = self._record_initial(root)
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            assessment = assess_project_lineage(root, FORGE_ROOT)
            self.assertEqual(assessment["status"], "APPROVAL_REQUIRED")
            levels = {row["level_id"]: row for row in assess_ship_claims(root, FORGE_ROOT)["levels"]}
            self.assertIn("lineage-identified-candidate", levels)
            self.assertEqual(levels["lineage-identified-candidate"]["status"], "FAIL")

    def test_cli_requires_lineage_operation_to_be_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            contract = self._lineage_contract(
                root,
                lineage_id="cli-lineage",
                version="1.0.0",
                build_id="cli-build",
            )
            result = subprocess.run([
                sys.executable,
                str(FORGE_ROOT / "forge.py"),
                "adopt",
                str(root),
                "--record-lineage",
                str(contract),
                "--confirm-objective",
                "Do unrelated work.",
                "--json",
            ], cwd=FORGE_ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be a separate Adopt operation", result.stderr + result.stdout)

    def test_archive_rejects_traversal_and_duplicate_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = root / "bad.zip"
            with zipfile.ZipFile(bad, "w") as archive:
                archive.writestr("Project/../escape.php", b"bad")
            with self.assertRaisesRegex(ValueError, "unsafe member path"):
                exact_zip_tree(bad, strip_prefix="Project")


if __name__ == "__main__":
    import unittest
    unittest.main()

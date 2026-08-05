from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from tests.support import FORGE_ROOT, ForgeTestCase
from emotivus_forge.core.lineage import exact_directory_tree, exact_zip_tree, record_project_lineage
from emotivus_forge.core.migration_identity import (
    migration_identity_summary,
    record_migration_catalog,
    retire_migration_catalog,
)
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.state import load_settings
from emotivus_forge.core.ship_claims import assess_ship_claims


class MigrationIdentityTests(ForgeTestCase):
    def _zip(self, root: Path, name: str, files: dict[str, str], prefix: str = "Project") -> Path:
        path = root / name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, content in sorted(files.items()):
                archive.writestr(f"{prefix}/{relative}", content)
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
        relationship: str = "initial",
        parent: dict[str, object] | None = None,
        collision: dict[str, object] | None = None,
    ) -> Path:
        path = root / f"{lineage_id}.json"
        settings = load_settings(root)
        exclusions = [path.name]
        exclusions.extend(str(item) for item in settings.get("lineage_control_paths", []))
        if parent:
            exclusions.append(str(parent["path"]))
        tree = exact_directory_tree(root, FORGE_ROOT, exclude_paths=exclusions)
        path.write_text(json.dumps({
            "schema": 1,
            "lineage_id": lineage_id,
            "authority": "owner",
            "declared_version": version,
            "build_id": build_id,
            "relationship": relationship,
            "parent": parent,
            "current": {"tree_sha256": tree["tree_sha256"], "tree_file_count": tree["file_count"]},
            "collision_declaration": collision or {},
            "truth_boundary": "The owner declares lineage intent; Forge verifies exact bytes but not authorship or semantic compatibility.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def _record_initial(self, root: Path, *, lineage_id: str = "lineage-a", version: str = "1.0.0") -> None:
        record_project_lineage(
            root,
            FORGE_ROOT,
            self._lineage_contract(root, lineage_id=lineage_id, version=version, build_id=f"build-{lineage_id}"),
        )

    def _catalog(
        self,
        root: Path,
        *,
        inventory_id: str,
        lineage_id: str,
        entries: list[dict[str, object]] | None = None,
        source: dict[str, object] | None = None,
        mode: str = "tracked",
        observation: dict[str, object] | None = None,
        reconciliations: list[dict[str, object]] | None = None,
    ) -> Path:
        path = root / f"{inventory_id}.json"
        payload = {
            "schema": 1,
            "inventory_id": inventory_id,
            "authority": "owner",
            "lineage_id": lineage_id,
            "engine": "neutral-sql",
            "mode": mode,
            "source": source or {"kind": "project-tree"},
            "entries": entries or [],
            "no_migrations_reason": "This neutral project has no persisted schema migration surface to track." if mode == "none" else "",
            "applied_observation": observation or {},
            "reconciliations": reconciliations or [],
            "truth_boundary": "Forge verifies exact migration identities and supplied ledger testimony but does not execute upgrades or prove database correctness.",
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _entry(self, root: Path, sequence: str, semantic_id: str, relative: str) -> dict[str, object]:
        path = root / relative
        return {
            "sequence": sequence,
            "semantic_id": semantic_id,
            "path": relative,
            "body_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "description": f"Neutral migration {semantic_id} for regression coverage.",
        }

    def test_explicit_no_migrations_declaration_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._record_initial(root)
            record = record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(root, inventory_id="none-a", lineage_id="lineage-a", mode="none"),
            )
            self.assertEqual(record["mode"], "none")
            summary = migration_identity_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CURRENT")
            self.assertEqual(summary["applied_observation"]["status"], "not-applicable")

    def test_matching_applied_observation_reports_applied_and_matching(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "migrations").mkdir()
            migration = root / "migrations" / "052_neutral.sql"
            migration.write_text("CREATE TABLE neutral_items (id INT);\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            self._record_initial(root)
            body = hashlib.sha256(migration.read_bytes()).hexdigest()
            evidence = root / "applied-ledger.json"
            evidence.write_text(json.dumps({"52": body}) + "\n", encoding="utf-8")
            observation = {
                "evidence_path": evidence.name,
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "observed_utc": "2026-08-02T12:00:00Z",
                "entries": [{"sequence": "52", "semantic_id": "neutral-items-v1", "body_sha256": body}],
                "truth_boundary": "This exported ledger is project-owned testimony and does not prove the live database schema or migration execution safety.",
            }
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(
                    root,
                    inventory_id="tracked-a",
                    lineage_id="lineage-a",
                    entries=[self._entry(root, "52", "neutral-items-v1", "migrations/052_neutral.sql")],
                    observation=observation,
                ),
            )
            summary = migration_identity_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CURRENT")
            self.assertEqual(summary["applied_observation"]["status"], "matching")
            self.assertEqual(summary["applied_observation"]["counts"]["applied-and-matching"], 1)

    def test_sequence_only_applied_observation_is_body_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "migrations").mkdir()
            migration = root / "migrations" / "052_neutral.sql"
            migration.write_text("CREATE TABLE neutral_items (id INT);\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            self._record_initial(root)
            evidence = root / "applied-ledger.json"
            evidence.write_text("{\"applied\":[52]}\n", encoding="utf-8")
            observation = {
                "evidence_path": evidence.name,
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "observed_utc": "2026-08-02T12:00:00Z",
                "entries": [{"sequence": "52"}],
                "truth_boundary": "This legacy ledger records only sequence presence and cannot identify the body that actually executed.",
            }
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(
                    root,
                    inventory_id="tracked-a",
                    lineage_id="lineage-a",
                    entries=[self._entry(root, "52", "neutral-items-v1", "migrations/052_neutral.sql")],
                    observation=observation,
                ),
            )
            summary = migration_identity_summary(root, FORGE_ROOT)
            self.assertEqual(summary["applied_observation"]["status"], "body-unknown")
            levels = {row["level_id"]: row for row in assess_ship_claims(root, FORGE_ROOT)["levels"]}
            self.assertEqual(levels["migration-history-identified-candidate"]["status"], "FAIL")

    def test_same_sequence_different_bodies_across_lineages_requires_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "migrations").mkdir()
            first_migration = root / "migrations" / "052_branch.sql"
            first_migration.write_text("CREATE TABLE branch_a (id INT);\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            self._record_initial(root, lineage_id="lineage-a", version="1.0.0")
            parent_zip = self._zip(root, "lineage-a.zip", {
                "index.php": (root / "index.php").read_text(encoding="utf-8"),
                "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
                "migrations/052_branch.sql": first_migration.read_text(encoding="utf-8"),
            })
            parent = self._archive_row(parent_zip, version="1.0.0", build_id="build-lineage-a")
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(
                    root,
                    inventory_id="catalog-a",
                    lineage_id="lineage-a",
                    source={"kind": "zip", "package": parent},
                    entries=[self._entry(root, "52", "branch-a-v1", "migrations/052_branch.sql")],
                ),
            )
            first_migration.write_text("CREATE TABLE branch_b (id INT, note TEXT);\n", encoding="utf-8")
            second_contract = self._lineage_contract(
                root,
                lineage_id="lineage-b",
                version="1.1.0",
                build_id="build-lineage-b",
                relationship="continuation",
                parent=parent,
            )
            record_project_lineage(root, FORGE_ROOT, second_contract)
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(
                    root,
                    inventory_id="catalog-b",
                    lineage_id="lineage-b",
                    entries=[self._entry(root, "52", "branch-b-v1", "migrations/052_branch.sql")],
                ),
            )
            summary = migration_identity_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "RECONCILIATION_REQUIRED")
            self.assertEqual(summary["unresolved_collision_count"], 1)
            self.assertEqual(summary["unresolved_collisions"][0]["kind"], "sequence-number-collision")

    def test_append_after_highest_reconciliation_resolves_known_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "migrations").mkdir()
            first_migration = root / "migrations" / "052_branch.sql"
            first_migration.write_text("CREATE TABLE branch_a (id INT);\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            self._record_initial(root, lineage_id="lineage-a", version="1.0.0")
            parent_zip = self._zip(root, "lineage-a.zip", {
                "index.php": (root / "index.php").read_text(encoding="utf-8"),
                "BACKLOG.md": (root / "BACKLOG.md").read_text(encoding="utf-8"),
                "migrations/052_branch.sql": first_migration.read_text(encoding="utf-8"),
            })
            parent = self._archive_row(parent_zip, version="1.0.0", build_id="build-lineage-a")
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(
                    root,
                    inventory_id="catalog-a",
                    lineage_id="lineage-a",
                    source={"kind": "zip", "package": parent},
                    entries=[self._entry(root, "52", "branch-a-v1", "migrations/052_branch.sql")],
                ),
            )
            first_migration.write_text("CREATE TABLE branch_b (id INT, note TEXT);\n", encoding="utf-8")
            reconciliation = root / "migrations" / "060_reconcile.sql"
            reconciliation.write_text("ALTER TABLE branch_b ADD COLUMN reconciled INT DEFAULT 1;\n", encoding="utf-8")
            record_project_lineage(
                root,
                FORGE_ROOT,
                self._lineage_contract(
                    root,
                    lineage_id="lineage-b",
                    version="1.1.0",
                    build_id="build-lineage-b",
                    relationship="continuation",
                    parent=parent,
                ),
            )
            entries = [
                self._entry(root, "52", "branch-b-v1", "migrations/052_branch.sql"),
                self._entry(root, "60", "reconcile-branch-a-b-v1", "migrations/060_reconcile.sql"),
            ]
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(
                    root,
                    inventory_id="catalog-b",
                    lineage_id="lineage-b",
                    entries=entries,
                    reconciliations=[{
                        "reconciliation_id": "reconcile-52-a-b",
                        "collision_sequences": ["52"],
                        "lineage_ids": ["lineage-a", "lineage-b"],
                        "strategy": "append-after-highest",
                        "new_sequence": "60",
                        "semantic_id": "reconcile-branch-a-b-v1",
                        "reason": "Preserve both historical migration bodies and reconcile after the highest trusted sequence.",
                    }],
                ),
            )
            summary = migration_identity_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CURRENT_WITH_RECONCILIATION")
            self.assertEqual(summary["unresolved_collision_count"], 0)

    def test_migration_body_drift_contradicts_recorded_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "migrations").mkdir()
            migration = root / "migrations" / "052_neutral.sql"
            migration.write_text("CREATE TABLE neutral_items (id INT);\n", encoding="utf-8")
            build_passport(root, FORGE_ROOT)
            self._record_initial(root)
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(
                    root,
                    inventory_id="tracked-a",
                    lineage_id="lineage-a",
                    entries=[self._entry(root, "52", "neutral-items-v1", "migrations/052_neutral.sql")],
                ),
            )
            migration.write_text("CREATE TABLE neutral_items (id INT, altered TEXT);\n", encoding="utf-8")
            summary = migration_identity_summary(root, FORGE_ROOT)
            self.assertEqual(summary["status"], "CONTRADICTED")
            self.assertIn("does not match the lineage", summary["reason"])

    def test_catalog_retirement_requires_separate_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            self._record_initial(root)
            record_migration_catalog(
                root,
                FORGE_ROOT,
                self._catalog(root, inventory_id="none-a", lineage_id="lineage-a", mode="none"),
            )
            retired = retire_migration_catalog(
                root,
                "none-a",
                "The project introduced persisted schema migrations and requires a tracked replacement catalog.",
            )
            self.assertEqual(retired["status"], "retired")
            self.assertEqual(migration_identity_summary(root, FORGE_ROOT)["status"], "NOT_DECLARED")


if __name__ == "__main__":
    import unittest
    unittest.main()

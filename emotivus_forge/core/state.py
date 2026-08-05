from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .. import __version__
from .common import ForgeStateError, read_json, utc_now, write_json
from .ledger import record_event
from .models import CoreSettings
from .paths import ForgePaths

CORE_STATE_SCHEMA = 5
SETTINGS_SCHEMA = 21


def _session_adapter_defaults() -> dict[str, Any]:
    from .session_adapters import default_settings

    return default_settings()


def _settings_defaults() -> dict[str, Any]:
    return {
        "schema": SETTINGS_SCHEMA,
        **CoreSettings().to_dict(),
        "authority_path_precedence": {},
        "session_adapters": _session_adapter_defaults(),
        "advanced_capabilities": {},
        "guardrails": {},
        "field_trials": {},
        "project_identity": {},
        "project_events": {},
        "ledger_assertions": {},
        "check_qualifications": {},
        "artifact_provenance": {},
        "deployable_boundaries": {},
        "canonical_claims": {},
        "relationship_sets": {},
        "runtime_state_matrices": {},
        "state_transition_plans": {},
        "release_packages": {},
        "presentation_profiles": {},
        "release_distributions": {},
        "cold_session_validations": {},
        "release_proofs": {},
        "release_authorizations": {},
        "project_lineages": {},
        "merge_candidates": {},
        "lineage_control_paths": [],
        "migration_catalogs": {},
        "migration_control_paths": [],
        "package_families": {},
        "package_family_control_paths": [],
        "surface_coverages": {},
        "surface_coverage_control_paths": [],
        "release_facts": {},
        "release_fact_control_paths": [],
        "continuity_registers": {},
        "active_continuity_register_id": "",
        "continuity_control_paths": [],
        "third_party_intakes": {},
        "third_party_control_paths": [],
    }


def default_settings() -> dict[str, Any]:
    return _settings_defaults()


def _migrate_settings_1_to_2(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("notice_mode", "standard")
    migrated["schema"] = 2
    return migrated



def _migrate_settings_2_to_3(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("project_identity", {})
    migrated.setdefault("project_events", {})
    migrated["schema"] = 3
    return migrated



def _migrate_settings_3_to_4(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("ledger_assertions", {})
    migrated.setdefault("check_qualifications", {})
    migrated["schema"] = 4
    return migrated


def _migrate_settings_4_to_5(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("artifact_provenance", {})
    migrated["schema"] = 5
    return migrated



def _migrate_settings_5_to_6(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("deployable_boundaries", {})
    migrated.setdefault("canonical_claims", {})
    migrated["schema"] = 6
    return migrated



def _migrate_settings_6_to_7(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("relationship_sets", {})
    migrated["schema"] = 7
    return migrated


def _migrate_settings_7_to_8(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("runtime_state_matrices", {})
    migrated["schema"] = 8
    return migrated


def _migrate_settings_8_to_9(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("state_transition_plans", {})
    migrated["schema"] = 9
    return migrated


def _migrate_settings_9_to_10(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("release_packages", {})
    migrated["schema"] = 10
    return migrated



def _migrate_settings_10_to_11(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("presentation_profiles", {})
    migrated.setdefault("release_distributions", {})
    migrated.setdefault("cold_session_validations", {})
    migrated["schema"] = 11
    return migrated


def _migrate_settings_11_to_12(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("release_proofs", {})
    migrated["schema"] = 12
    return migrated


def _migrate_settings_12_to_13(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("release_authorizations", {})
    migrated["schema"] = 13
    return migrated




def _migrate_settings_13_to_14(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("project_lineages", {})
    migrated.setdefault("merge_candidates", {})
    migrated.setdefault("lineage_control_paths", [])
    migrated["schema"] = 14
    return migrated



def _migrate_settings_14_to_15(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("migration_catalogs", {})
    migrated.setdefault("migration_control_paths", [])
    migrated["schema"] = 15
    return migrated



def _migrate_settings_15_to_16(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("package_families", {})
    migrated.setdefault("package_family_control_paths", [])
    migrated["schema"] = 16
    return migrated


def _migrate_settings_16_to_17(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("surface_coverages", {})
    migrated.setdefault("surface_coverage_control_paths", [])
    migrated["schema"] = 17
    return migrated


def _migrate_settings_17_to_18(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("release_facts", {})
    migrated.setdefault("release_fact_control_paths", [])
    migrated["schema"] = 18
    return migrated


def _migrate_settings_18_to_19(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("continuity_registers", {})
    migrated.setdefault("active_continuity_register_id", "")
    migrated.setdefault("continuity_control_paths", [])
    migrated["schema"] = 19
    return migrated


def _migrate_settings_19_to_20(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("third_party_intakes", {})
    migrated.setdefault("third_party_control_paths", [])
    migrated["schema"] = 20
    return migrated


def _migrate_settings_20_to_21(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("session_adapters", _session_adapter_defaults())
    migrated["schema"] = 21
    return migrated


def _migrate_state_1_to_2(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("notices", {"history": []})
    migrated.setdefault("knowledge", {"last_delta": {}, "stale_keys": []})
    migrated["schema"] = 2
    return migrated


def _migrate_state_2_to_3(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    # Earlier builds used `snapshot` as both an observed comparison point and an implied
    # authority checkpoint. That authority cannot be reconstructed safely during migration.
    migrated.setdefault("authority_baseline", {
        "schema": 1,
        "status": "not-established",
        "migration_reason": "Pre-0.526 snapshots were preserved as observed checkpoints only and require explicit project-authority authorization.",
    })
    migrated["schema"] = 3
    return migrated


def _migrate_state_3_to_4(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("sidecar", {
        "schema": 1,
        "mode": "development-sidecar",
        "operation": "migrated-observed-only",
        "work_scope": "",
        "authority_status": "",
        "unexpected_mutations": 0,
        "last_scoped_check_status": "NOT_RUN",
        "last_scoped_check_utc": "",
        "last_ship_status": "NOT_RUN",
        "ship_assessment_active": False,
        "authority_changed_by_operation": False,
        "updated_utc": "",
        "truth_boundary": "Migrated status is observational only and grants no authority.",
    })
    migrated["schema"] = 4
    return migrated


def _migrate_state_4_to_5(value: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(value)
    migrated.setdefault("workspace_integrity", {
        "schema": 1,
        "status": "NOT_ESTABLISHED",
        "session_start": {},
        "seal_candidate": {},
        "last_assessment": {},
        "truth_boundary": "Migrated state has no exact workspace seal candidate; run Forge and a passing checkpointed Check before Ship.",
    })
    migrated["schema"] = 5
    return migrated


def _apply_migrations(
    path: Path,
    value: dict[str, Any],
    *,
    current_schema: int,
    migrations: dict[int, Callable[[dict[str, Any]], dict[str, Any]]],
) -> tuple[dict[str, Any], bool]:
    raw_schema = value.get("schema", 1)
    if not isinstance(raw_schema, int) or raw_schema < 1:
        raise ForgeStateError(path, "schema must be a positive integer")
    if raw_schema > current_schema:
        raise ForgeStateError(path, f"schema {raw_schema} is newer than supported schema {current_schema}")
    migrated = dict(value)
    changed = False
    while raw_schema < current_schema:
        migrate = migrations.get(raw_schema)
        if migrate is None:
            raise ForgeStateError(path, f"no migration exists from schema {raw_schema}")
        migrated = migrate(migrated)
        raw_schema = int(migrated.get("schema", raw_schema + 1))
        changed = True
    return migrated, changed


def load_settings(project_root: Path) -> dict[str, Any]:
    paths = ForgePaths(project_root)
    settings = read_json(paths.settings, {})
    if not isinstance(settings, dict):
        raise ForgeStateError(paths.settings, "settings must be a JSON object")
    settings, migrated = _apply_migrations(
        paths.settings,
        settings or {"schema": SETTINGS_SCHEMA},
        current_schema=SETTINGS_SCHEMA,
        migrations={1: _migrate_settings_1_to_2, 2: _migrate_settings_2_to_3, 3: _migrate_settings_3_to_4, 4: _migrate_settings_4_to_5, 5: _migrate_settings_5_to_6, 6: _migrate_settings_6_to_7, 7: _migrate_settings_7_to_8, 8: _migrate_settings_8_to_9, 9: _migrate_settings_9_to_10, 10: _migrate_settings_10_to_11, 11: _migrate_settings_11_to_12, 12: _migrate_settings_12_to_13, 13: _migrate_settings_13_to_14, 14: _migrate_settings_14_to_15, 15: _migrate_settings_15_to_16, 16: _migrate_settings_16_to_17, 17: _migrate_settings_17_to_18, 18: _migrate_settings_18_to_19, 19: _migrate_settings_19_to_20, 20: _migrate_settings_20_to_21},
    )
    defaults = _settings_defaults()
    defaults.update(settings)
    defaults["schema"] = SETTINGS_SCHEMA
    try:
        typed = CoreSettings.from_dict(defaults)
    except (TypeError, ValueError) as exc:
        raise ForgeStateError(paths.settings, str(exc)) from exc
    defaults.update(typed.to_dict())
    if migrated:
        write_json(paths.settings, defaults)
    return defaults


def ensure_settings(project_root: Path) -> dict[str, Any]:
    settings = load_settings(project_root)
    write_json(ForgePaths(project_root).settings, settings)
    return settings


def load_state(project_root: Path) -> dict[str, Any]:
    path = ForgePaths(project_root).state
    value = read_json(path, {})
    if not isinstance(value, dict):
        raise ForgeStateError(path, "state must be a JSON object")
    value, migrated = _apply_migrations(
        path,
        value or {"schema": CORE_STATE_SCHEMA},
        current_schema=CORE_STATE_SCHEMA,
        migrations={1: _migrate_state_1_to_2, 2: _migrate_state_2_to_3, 3: _migrate_state_3_to_4, 4: _migrate_state_4_to_5},
    )
    if migrated:
        save_state(project_root, value)
    return value


def save_state(project_root: Path, state: dict[str, Any]) -> None:
    state["schema"] = CORE_STATE_SCHEMA
    state["updated_utc"] = utc_now()
    write_json(ForgePaths(project_root).state, state)


def _legacy_confirmed_records(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / ".forge" / "project" / "ledger.json"
    value = read_json(path, {})
    if not isinstance(value, dict):
        return []
    rows = value.get("entries", [])
    if not isinstance(rows, list):
        return []
    return [
        item for item in rows
        if isinstance(item, dict) and str(item.get("status", "")) in {"accepted", "active", "resolved"}
    ]


def migrate_legacy_state(project_root: Path) -> dict[str, Any]:
    paths = ForgePaths(project_root)
    if paths.passport.is_file():
        return {"migrated": False, "reason": "core state already exists", "records": 0}
    old_passport_path = project_root / ".forge" / "passport" / "passport.json"
    if not old_passport_path.is_file():
        return {"migrated": False, "reason": "no 1.4.1 passport found", "records": 0}
    old_passport = read_json(old_passport_path, {})
    if not isinstance(old_passport, dict):
        old_passport = {}
    records = _legacy_confirmed_records(project_root)
    migration = {
        "from": "1.4.1-dev",
        "to": __version__,
        "utc": utc_now(),
        "legacy_passport": str(old_passport_path.relative_to(project_root)),
        "preserved_record_count": len(records),
        "legacy_state_retained": True,
    }
    for item in records:
        record_event(project_root, "legacy-record", {
            "legacy_id": item.get("id", ""),
            "type": item.get("type", "record"),
            "title": item.get("title", ""),
            "status": item.get("status", ""),
            "rationale": item.get("rationale", item.get("description", "")),
            "source": ".forge/project/ledger.json",
        }, source="migration")
    record_event(project_root, "state-migration", migration, source="migration")
    state = {
        "schema": CORE_STATE_SCHEMA,
        "created_utc": utc_now(),
        "migration": migration,
        "legacy_summary": {
            "identity": old_passport.get("identity", {}),
            "objective": old_passport.get("objective", {}),
            "uncertainties": old_passport.get("uncertainties", []),
            "evidence": old_passport.get("evidence", {}),
        },
        "notices": {"history": []},
        "knowledge": {"last_delta": {}, "stale_keys": []},
        "authority_baseline": {
            "schema": 1,
            "status": "not-established",
            "reason": "Legacy migration preserved observed state only; explicit project-authority baseline authorization is required.",
        },
    }
    save_state(project_root, state)
    return {"migrated": True, "reason": "", "records": len(records), "state": state}


def is_adopted(project_root: Path) -> bool:
    return ForgePaths(project_root).passport.is_file() and ForgePaths(project_root).state.is_file()

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any

from . import __version__
from .detect import Detection
from .utils import read_json, utc_now, write_json

CONFIG_NAME = ".emotivus-forge.json"
STATE_DIR = ".forge"
CURRENT_CONFIG_SCHEMA = 10


def default_config(project_name: str, detection: Detection, forge_folder: str = "Emotivus-Forge") -> dict[str, Any]:
    required_runtimes = {
        "php": {"required": "php" in detection.adapters, "expected": ""},
        "node": {"required": False, "expected": ""},
        "python": {"required": False, "expected": ""},
    }
    commands: dict[str, list[dict[str, Any]]] = {"quick": [], "section": [], "release": []}
    if "node" in detection.adapters:
        manager = detection.package_manager or "npm"
        if "lint" in detection.package_scripts:
            commands["quick"].append({"id": "node.lint", "command": [manager, "run", "lint"], "timeout": 180, "evidence": {"types": ["static"], "surfaces": []}})
        if "test" in detection.package_scripts:
            test_command = [manager, "test"] if manager in {"npm", "pnpm", "yarn"} else [manager, "run", "test"]
            commands["section"].append({"id": "node.test", "command": test_command, "timeout": 300, "evidence": {"types": ["unit"], "surfaces": []}})
    if detection.detected_version:
        baseline_version = detection.detected_version if detection.existing_project else "0.0.0"
        target_version = detection.detected_version
        version_source = {"path": detection.version_path, "regex": detection.version_regex}
    elif detection.existing_project:
        baseline_version = "unversioned"
        target_version = "unversioned"
        version_source = {"path": "", "regex": ""}
    else:
        baseline_version = "0.0.0"
        target_version = "0.1.0"
        version_source = {"path": "", "regex": ""}
    return {
        "schema": CURRENT_CONFIG_SCHEMA,
        "forge_version": __version__,
        "project": {
            "name": project_name,
            "kind": "existing" if detection.existing_project else "new",
            "identity": detection.identity or str(uuid.uuid4()),
            "lineage": {"parent_identity": "", "fork_reason": ""},
            "self_hosting": detection.identity == "emotivus-forge-core",
            "risk_preset": "balanced",
            "deployment_target": "zip",
            "workspace_classification": "unknown",
        },
        "adapters": list(detection.adapters),
        "paths": {
            "exclude": [forge_folder, ".forge", ".git", "node_modules", "deploy", "dist", "build", "vendor", "tests/fixtures"],
            "reports": ".forge/reports",
            "baseline": ".forge/baseline.json",
            "deploy_ignore": ".deployignore",
        },
        "runtime": required_runtimes,
        "quality": {
            "require_tests": detection.existing_project,
            "require_documentation": False,
            "fail_on_new_warnings": False,
            "test_entry_points": [],
        },
        "versioning": {
            "enabled": True,
            "status": "development",
            "strategy": "auto",
            "baseline_version": baseline_version,
            "target_version": target_version,
            "package_version": target_version,
            "package_version_rule": "same",
            "source": version_source,
            "migration": {"required": False, "path": ""},
        },
        "packaging": {
            "enabled": True,
            "target": "zip",
            "output": "deploy/{project}-{version}.zip",
            "required_files": [],
            "exclude": [
                forge_folder, ".forge", ".git", ".github", ".gitlab", ".gitlab-ci.yml", ".forge-ci",
                "tests", "docs", "node_modules", "deploy", ".emotivus-forge.json", "FORGE-AGENT.md",
                ".deployignore", "Forge-State*.zip", "*.log", "*.tmp", "*.bak", ".DS_Store", "Thumbs.db",
            ],
            "immutable_exclude": [
                forge_folder, ".forge", ".git", ".github", ".gitlab", ".gitlab-ci.yml", ".forge-ci",
                "deploy", ".emotivus-forge.json", "FORGE-AGENT.md", ".deployignore",
            ],
            "hard_exclude": [
                ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_dsa",
                "id_ecdsa", "id_ed25519", "credentials.json", "service-account*.json", "config.local.php",
                "secrets.*", "*backup*.sql", "*dump*.sql", "*database*.sql", "*.sqlite", "*.sqlite3",
            ],
            "secret_scan": True,
            "zero_byte_allow": [".gitkeep", ".keep"],
        },
        "profiles": {
            "quick": {"audit": True, "commands": ["quick"], "package_dry_run": False, "release_gate": False},
            "section": {"audit": True, "commands": ["quick", "section"], "package_dry_run": True, "release_gate": False},
            "release": {"audit": True, "commands": ["quick", "section", "release"], "package_dry_run": True, "release_gate": True},
        },
        "commands": commands,
        "initialization": {
            "configured_utc": "",
            "preset": "balanced",
            "baseline_existing_advisories": detection.existing_project,
            "answers_schema": 1,
        },
        "verification": {"live_checks": [], "static_limit_notice": True},
        "security": {
            "synthetic_fixture_paths": ["tests/fixtures/security"],
            "allow_inline_synthetic_annotations": True,
        },
        "confidentiality": {
            "mode": "metadata-only",
            "capture_host_file_contents": False,
            "copy_host_files": False,
            "store_absolute_paths": False,
            "report_dir": ".forge/confidentiality",
            "private_policy_env": "FORGE_PRIVATE_POLICY",
            "scan_archives": True,
        },
        "graph": {
            "enabled": True,
            "output_dir": ".forge/graph",
            "refresh_profiles": ["section", "release"],
            "impact_depth": 2,
            "classification": {"minimum_confidence": 0.55, "corrections": {}},
        },
        "learn": {
            "enabled": True,
            "proposals_dir": ".forge/learn/proposals",
            "contracts_path": ".forge/policies/learned-contracts.json",
        },
        "lab": {
            "enabled": True,
            "output_dir": ".forge/lab",
            "required_profiles": [],
            "minimum_evidence_by_profile": {
                "quick": "connectivity-smoke",
                "section": "content-readiness",
                "release": "content-readiness"
            },
            "recipes": [],
        },
        "release_proof": {
            "enabled": True,
            "claim_level": "source-verified",
            "auto_minimum": True,
            "output_dir": ".forge/release-proof",
            "surfaces": [],
            "deployment_states": [],
            "scan_documentation_claims": True,
            "observed_attestations": {
                "surface_marker": "FORGE_SURFACE",
                "bind_evidence_artifacts": True,
            },
        },
        "delivery_proof": {
            "enabled": True,
            "manifest_path": ".forge/delivery/delivery-manifest.json",
            "output": "deploy/{project}-{version}-Handoff.zip",
            "scan_roots": ["."],
            "detect_patterns": [
                "*.zip", "*.tar", "*.tar.gz", "*.tgz", "*.7z",
                "HANDOVER.md", "README-FIRST.md", "README-FIRST.txt",
                "*-CONTEXT.txt", "*-PROJECT-INSTRUCTIONS.txt", "Forge-State*.zip"
            ],
        },
        "runtime_proof": {
            "enabled": True,
            "contracts_path": ".forge/contracts/runtime-contracts.json",
            "output_dir": ".forge/runtime",
            "required_kinds_by_profile": {"quick": [], "section": [], "release": []},
            "minimum_boundary_by_profile": {
                "quick": "local-process",
                "section": "disposable-local-environment",
                "release": "release-equivalent"
            },
        },
        "tool_migration": {"mode": "audit", "absorbed": [], "quarantined": [], "inventory_counts": {}, "lifecycle": [], "ecosystems": []},
        "isolation": {
            "mode": "mirror" if detection.identity == "emotivus-forge-core" else "host",
            "forge_root": forge_folder,
            "host_scanner_excludes": [forge_folder, ".forge"],
        },
        "environment": {
            "required_executables": [],
            "required_env": [],
            "expected_layout": [],
            "require_release_parity": True,
            "target": {
                "runtimes": {},
                "tested_runtimes": {},
                "required_extensions": [],
                "tested_extensions": [],
                "required_services": [],
                "tested_services": [],
                "evidence": [],
            },
        },
        "evidence": {
            "history_path": ".forge/evidence/execution-history.json",
            "failure_dir": ".forge/failures",
            "history_limit": 500,
            "boundaries": {"source": "development-tree", "package": "deployment-artifact"},
            "reuse": {"enabled": True, "require_same_tree": True, "require_same_environment": True},
            "anomaly": {"enabled": True, "minimum_samples": 3, "fast_ratio": 0.6},
        },
        "continuity": {
            "objective_sources": ["ACTIVE-BUILD-PROMPT.md", "BACKLOG.md", "ROADMAP.md", "Planning/ACTIVE-BUILD-PROMPT.md"],
            "next_action": "",
            "state_archive": "Forge-State.zip",
        },
        "project_memory": {
            "root": ".forge/project",
            "mode": "development",
            "scope": {"coding_allowed": True, "source": "", "reason": ""},
            "context": {
                "default_budget": "standard",
                "token_budgets": {"compact": 1200, "standard": 3000, "full": 8000},
                "output_dir": ".forge/context",
            },
            "traceability": {
                "release_requires_active_plan": False,
                "accepted_artifacts_require_canonical_ref": True,
                "release_requires_quality_coverage": True,
            },
            "pivot": {
                "require_release_gate_on_complete": True,
                "checkpoint_profile_order": ["release", "section", "quick"],
                "allowed_modes": ["exploration", "transition", "development", "release"],
                "default_entry_mode": "exploration",
            },
        },
        "maintenance": {
            "update": {
                "preserve_paths": ["policy-packs"],
                "post_update_profile": "quick",
                "backup_limit": 5,
            },
            "doctor": {
                "repairs_enabled": True,
                "allowed_types": ["create-directory", "create-file", "append-lines"],
            },
            "ci": {"provider": "none", "generated": []},
            "delivery": {
                "internal_output": "deploy/{project}-{version}-Internal.zip",
                "source_archive_name": "Project-Source.zip",
                "state_archive_name": "Forge-State.zip",
                "exclude": [
                    ".git", ".forge", "deploy", "node_modules", "vendor", "Forge-State*.zip",
                    "*.log", "*.tmp", "*.bak", "__pycache__", "*.pyc", "*.pyo",
                    ".pytest_cache", ".mypy_cache", ".ruff_cache"
                ],
            },
        },
        "detection": {
            "evidence": detection.evidence,
            "package_scripts": list(detection.package_scripts),
            "package_manager": detection.package_manager,
            "detected_version": detection.detected_version,
            "version_path": detection.version_path,
            "identity": detection.identity,
        },
    }


def migrate_config_data(data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a migrated copy and a deterministic migration record."""
    if not isinstance(data, dict):
        raise RuntimeError(f"{CONFIG_NAME} must be a JSON object")
    result = copy.deepcopy(data)
    migrations: list[dict[str, Any]] = []
    schema = result.get("schema")
    if schema == 1:
        result["schema"] = 2
        result.setdefault("maintenance", {
            "update": {"preserve_paths": ["policy-packs"], "post_update_profile": "quick", "backup_limit": 5},
            "doctor": {"repairs_enabled": True, "allowed_types": ["create-directory", "create-file", "append-lines"]},
            "ci": {"provider": "none", "generated": []},
            "delivery": {
                "internal_output": "deploy/{project}-{version}-Internal.zip",
                "source_archive_name": "Project-Source.zip",
                "state_archive_name": "Forge-State.zip",
                "exclude": [
                    ".git", ".forge", "deploy", "node_modules", "vendor", "Forge-State*.zip",
                    "*.log", "*.tmp", "*.bak", "__pycache__", "*.pyc", "*.pyo",
                    ".pytest_cache", ".mypy_cache", ".ruff_cache"
                ],
            },
        })
        packaging = result.setdefault("packaging", {})
        for key in ("exclude", "immutable_exclude"):
            values = packaging.setdefault(key, [])
            for item in (".github", ".gitlab", ".gitlab-ci.yml", ".forge-ci"):
                if item not in values:
                    values.append(item)
        migrations.append({"from": 1, "to": 2, "id": "maintenance-and-distribution"})
        schema = 2
    if schema == 2:
        result["schema"] = 3
        result.setdefault("project_memory", {
            "root": ".forge/project",
            "mode": "development",
            "context": {
                "default_budget": "standard",
                "token_budgets": {"compact": 1200, "standard": 3000, "full": 8000},
                "output_dir": ".forge/context",
            },
            "traceability": {
                "release_requires_active_plan": False,
                "accepted_artifacts_require_canonical_ref": True,
            },
        })
        migrations.append({"from": 2, "to": 3, "id": "project-intelligence-and-context"})
        schema = 3
    if schema == 3:
        result["schema"] = 4
        project = result.setdefault("project", {})
        project.setdefault("identity", str(uuid.uuid4()))
        project.setdefault("lineage", {"parent_identity": "", "fork_reason": ""})
        project.setdefault("workspace_classification", "unknown")
        result.setdefault("workspace", {"classification": "unknown", "confidence": "low", "authorities": {}, "missing_authorities": [], "allowed_activities": [], "restricted_activities": []})
        result.setdefault("work", {"mode": result.get("project_memory", {}).get("mode", "development"), "coding_allowed": True, "scope_source": "", "reason": ""})
        result.setdefault("runtime_requirements", {})
        result.setdefault("source_completeness", {"manifest": "", "status": "unknown", "reconstruction": []})
        result.setdefault("packaging_policy", {"contradictions": []})
        result.setdefault("tool_migration", {}).setdefault("lifecycle", [])
        result.setdefault("graph", {}).setdefault("classification", {"minimum_confidence": 0.55, "corrections": {}})
        result.setdefault("evidence", {}).setdefault("boundaries", {"source": "development-tree", "package": "deployment-artifact"})
        result.setdefault("evidence", {}).setdefault("reuse", {"enabled": True, "require_same_tree": True, "require_same_environment": True})
        result.setdefault("project_memory", {}).setdefault("scope", {"coding_allowed": True, "source": "", "reason": ""})
        migrations.append({"from": 3, "to": 4, "id": "provenance-scope-and-evidence-boundaries"})
        schema = 4
    if schema == 4:
        result["schema"] = 5
        memory = result.setdefault("project_memory", {})
        traceability = memory.setdefault("traceability", {})
        traceability.setdefault("release_requires_quality_coverage", True)
        memory.setdefault("pivot", {
            "require_release_gate_on_complete": True,
            "checkpoint_profile_order": ["release", "section", "quick"],
            "allowed_modes": ["exploration", "transition", "development", "release"],
            "default_entry_mode": "exploration",
        })
        migrations.append({"from": 4, "to": 5, "id": "controlled-change-and-pivot-lifecycle"})
        schema = 5
    if schema == 5:
        result["schema"] = 6
        lab = result.setdefault("lab", {})
        lab.setdefault("minimum_evidence_by_profile", {
            "quick": "connectivity-smoke",
            "section": "content-readiness",
            "release": "content-readiness",
        })
        delivery = result.setdefault("maintenance", {}).setdefault("delivery", {})
        excludes = delivery.setdefault("exclude", [])
        for item in ("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", ".ruff_cache"):
            if item not in excludes:
                excludes.append(item)
        migrations.append({"from": 5, "to": 6, "id": "lab-truthfulness-and-cache-hygiene"})
        schema = 6
    if schema == 6:
        result["schema"] = 7
        result.setdefault("runtime_proof", {
            "enabled": True,
            "contracts_path": ".forge/contracts/runtime-contracts.json",
            "output_dir": ".forge/runtime",
            "required_kinds_by_profile": {"quick": [], "section": [], "release": []},
            "minimum_boundary_by_profile": {
                "quick": "local-process",
                "section": "disposable-local-environment",
                "release": "release-equivalent"
            },
        })
        graph = result.setdefault("graph", {})
        graph.setdefault("impact_precision", {
            "separate_certification_dependency_runtime": True,
            "runtime_path_default": "unknown"
        })
        migrations.append({"from": 6, "to": 7, "id": "runtime-contracts-and-impact-precision"})
        schema = 7
    if schema == 7:
        result["schema"] = 8
        result.setdefault("release_proof", {
            "enabled": True,
            "claim_level": "source-verified",
            "auto_minimum": True,
            "output_dir": ".forge/release-proof",
            "surfaces": [],
            "deployment_states": [],
            "scan_documentation_claims": True,
        })
        result.setdefault("delivery_proof", {
            "enabled": True,
            "manifest_path": ".forge/delivery/delivery-manifest.json",
            "output": "deploy/{project}-{version}-Handoff.zip",
            "scan_roots": ["."],
            "detect_patterns": ["*.zip", "*.tar", "*.tar.gz", "*.tgz", "*.7z", "HANDOVER.md", "README-FIRST.md", "README-FIRST.txt", "*-CONTEXT.txt", "*-PROJECT-INSTRUCTIONS.txt", "Forge-State*.zip"],
        })
        result.setdefault("environment", {}).setdefault("target", {
            "runtimes": {}, "tested_runtimes": {},
            "required_extensions": [], "tested_extensions": [],
            "required_services": [], "tested_services": [],
            "evidence": [],
        })
        migrations.append({"from": 7, "to": 8, "id": "assurance-coverage-and-delivery-provenance"})
        schema = 8
    if schema == 8:
        result["schema"] = 9
        release_proof = result.setdefault("release_proof", {})
        release_proof.setdefault("observed_attestations", {
            "surface_marker": "FORGE_SURFACE",
            "bind_evidence_artifacts": True,
        })
        migrations.append({"from": 8, "to": 9, "id": "observed-evidence-attestation-binding"})
        schema = 9
    if schema == 9:
        result["schema"] = 10
        result.setdefault("confidentiality", {
            "mode": "metadata-only",
            "capture_host_file_contents": False,
            "copy_host_files": False,
            "store_absolute_paths": False,
            "report_dir": ".forge/confidentiality",
            "private_policy_env": "FORGE_PRIVATE_POLICY",
            "scan_archives": True,
        })
        migrations.append({"from": 9, "to": 10, "id": "metadata-only-confidentiality-boundary"})
        schema = 10
    if schema != CURRENT_CONFIG_SCHEMA:
        raise RuntimeError(f"{CONFIG_NAME} schema {schema!r} is unsupported; expected <= {CURRENT_CONFIG_SCHEMA}")
    result["forge_version"] = __version__
    return result, migrations


def migrate_config_file(project_root: Path, *, write: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    project_root = project_root.resolve()
    path = project_root / CONFIG_NAME
    try:
        original = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read {CONFIG_NAME}: {exc}") from exc
    migrated, migrations = migrate_config_data(original)
    backup = ""
    if migrations and write:
        stamp = utc_now().replace(":", "-")
        backup_path = project_root / ".forge" / "config-migrations" / stamp / f"{CONFIG_NAME}.schema-{original.get('schema', 'unknown')}.json"
        write_json(backup_path, original)
        write_json(path, migrated)
        write_json(project_root / ".forge" / "config-migrations" / stamp / "migration.json", {
            "schema": 1,
            "generated_utc": utc_now(),
            "config": CONFIG_NAME,
            "backup": str(backup_path.relative_to(project_root)),
            "migrations": migrations,
        })
        backup = str(backup_path)
    return migrated, migrations, backup


def load_config(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / CONFIG_NAME
    if not path.is_file():
        raise RuntimeError(f"{CONFIG_NAME} not found. Run `forge.py adopt <project>` first.")
    data, _migrations, _backup = migrate_config_file(project_root, write=True)
    return data


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def save_config(project_root: Path, config: dict[str, Any]) -> Path:
    migrated, _ = migrate_config_data(config)
    path = project_root.resolve() / CONFIG_NAME
    write_json(path, migrated)
    return path

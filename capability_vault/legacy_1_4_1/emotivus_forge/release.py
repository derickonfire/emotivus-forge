from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def validate_release(project_root: Path, config: dict[str, Any]) -> list[str]:
    versioning = config.get("versioning", {})
    if not versioning.get("enabled"):
        return []

    problems: list[str] = []
    status = str(versioning.get("status", "development"))
    baseline = str(versioning.get("baseline_version", "")).strip()
    target = str(versioning.get("target_version", "")).strip()
    package = str(versioning.get("package_version", "")).strip()
    if status != "release":
        problems.append("versioning.status must be 'release' before the release profile can pass")
    if not baseline:
        problems.append("versioning.baseline_version is required")
    if not target:
        problems.append("versioning.target_version is required")
    if baseline and target and baseline == target:
        problems.append("target_version must differ from baseline_version for a frozen release")
    if not package:
        problems.append("versioning.package_version is required")
    rule = str(versioning.get("package_version_rule", "same"))
    if target and package:
        if rule == "same" and package != target:
            problems.append("package_version must equal target_version under the 'same' rule")
        elif rule == "remove_dots" and package != target.replace(".", ""):
            problems.append("package_version must equal target_version with dots removed")
        elif rule not in {"same", "remove_dots", "none"}:
            problems.append(f"unsupported package_version_rule: {rule}")

    source = versioning.get("source", {})
    source_path = str(source.get("path", "")).strip()
    source_regex = str(source.get("regex", "")).strip()
    if source_path or source_regex:
        if not source_path or not source_regex:
            problems.append("versioning.source requires both path and regex")
        else:
            candidate = project_root / source_path
            if not candidate.is_file():
                problems.append(f"version source file does not exist: {source_path}")
            else:
                try:
                    match = re.search(source_regex, candidate.read_text(encoding="utf-8", errors="replace"), flags=re.M)
                except re.error as exc:
                    problems.append(f"version source regex is invalid: {exc}")
                else:
                    if not match or match.lastindex is None:
                        problems.append(f"version source regex did not capture a version in {source_path}")
                    elif match.group(1) != target:
                        problems.append(f"runtime version is {match.group(1)!r}, expected {target!r}")

    migration = versioning.get("migration", {})
    if migration.get("required"):
        migration_path = str(migration.get("path", "")).strip()
        if not migration_path:
            problems.append("a migration is required but versioning.migration.path is empty")
        elif not (project_root / migration_path).is_file():
            problems.append(f"declared migration does not exist: {migration_path}")
    return problems

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .utils import sha256_bytes, utc_now, write_json


def _forge_command(forge_folder: str, subcommand: str) -> str:
    return f"python3 {forge_folder}/forge.py {subcommand} ."


def _templates(provider: str, forge_folder: str) -> list[dict[str, Any]]:
    if provider == "github":
        content = f"""name: Emotivus Forge

on:
  pull_request:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  forge-section:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      - name: Forge Doctor
        run: {_forge_command(forge_folder, 'doctor')}
      - name: Forge Section Gate
        run: {_forge_command(forge_folder, 'check')} --profile section --fresh
      - name: Upload Forge evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: forge-evidence
          path: .forge/reports
          if-no-files-found: ignore

  forge-release:
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      - name: Forge Release Gate
        run: {_forge_command(forge_folder, 'check')} --profile release --fresh
"""
        return [{"path": ".github/workflows/emotivus-forge.yml", "content": content, "mode": 0o644}]
    if provider == "gitlab":
        content = f"""stages:
  - verify
  - release

forge_section:
  stage: verify
  image: python:3
  script:
    - {_forge_command(forge_folder, 'doctor')}
    - {_forge_command(forge_folder, 'check')} --profile section --fresh
  artifacts:
    when: always
    paths:
      - .forge/reports/

forge_release:
  stage: release
  image: python:3
  rules:
    - if: '$CI_COMMIT_TAG'
  script:
    - {_forge_command(forge_folder, 'check')} --profile release --fresh
"""
        return [{"path": ".gitlab-ci-forge.yml", "content": content, "mode": 0o644}]
    if provider == "shell":
        content = f"""#!/usr/bin/env sh
set -eu
PROFILE="${{1:-section}}"
case "$PROFILE" in
  quick|section|release) ;;
  *) echo "usage: $0 [quick|section|release]" >&2; exit 2 ;;
esac
{_forge_command(forge_folder, 'doctor')}
{_forge_command(forge_folder, 'check')} --profile "$PROFILE" --fresh
"""
        return [{"path": ".forge-ci/run.sh", "content": content, "mode": 0o755}]
    if provider == "cpanel":
        content = f"""#!/usr/bin/env sh
set -eu
OUTPUT="${{1:-}}"
{_forge_command(forge_folder, 'doctor')}
{_forge_command(forge_folder, 'check')} --profile release --fresh
if [ -n "$OUTPUT" ]; then
  {_forge_command(forge_folder, 'package')} --profile deployment --output "$OUTPUT"
else
  {_forge_command(forge_folder, 'package')} --profile deployment
fi
"""
        return [{"path": ".forge-ci/cpanel-release.sh", "content": content, "mode": 0o755}]
    raise ValueError(f"unsupported CI provider: {provider}")


def preview_ci(project_root: Path, config: dict[str, Any], provider: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_folder = str(config.get("isolation", {}).get("forge_root", "Emotivus-Forge"))
    files = []
    for item in _templates(provider, forge_folder):
        target = project_root / item["path"]
        existing = target.read_bytes() if target.is_file() else None
        incoming = item["content"].encode("utf-8")
        if existing is None:
            action = "create"
        elif existing == incoming:
            action = "unchanged"
        else:
            action = "replace"
        files.append({
            "path": item["path"],
            "action": action,
            "existing_sha256": sha256_bytes(existing) if existing is not None else "",
            "incoming_sha256": sha256_bytes(incoming),
            "content": item["content"],
            "mode": oct(item["mode"]),
        })
    payload = {
        "schema": 1,
        "status": "PASS",
        "generated_utc": utc_now(),
        "provider": provider,
        "files": files,
        "writes_performed": False,
        "notes": [
            "Generated CI invokes Forge and does not replace existing project assurance.",
            "Review runtime, database, and secret provisioning required by the host project before enabling the bridge.",
        ],
    }
    write_json(project_root / ".forge" / "ci" / "preview.json", payload)
    return payload


def write_ci(project_root: Path, config: dict[str, Any], provider: str, *, force: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    preview = preview_ci(project_root, config, provider)
    replacements = [item for item in preview["files"] if item["action"] == "replace"]
    if replacements and not force:
        raise RuntimeError("CI Bridge would replace existing files; rerun with --force only after reviewing the preview")
    timestamp = utc_now().replace(":", "-")
    backup_root = project_root / ".forge" / "ci" / "backups" / timestamp
    written: list[str] = []
    backups: list[str] = []
    for template, row in zip(_templates(provider, str(config.get("isolation", {}).get("forge_root", "Emotivus-Forge"))), preview["files"]):
        target = project_root / template["path"]
        if row["action"] == "unchanged":
            continue
        if target.exists():
            backup = backup_root / template["path"]
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            backups.append(str(backup.relative_to(project_root)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(template["content"], encoding="utf-8")
        os.chmod(target, template["mode"])
        written.append(template["path"])
    config.setdefault("maintenance", {}).setdefault("ci", {})["provider"] = provider
    generated = config["maintenance"]["ci"].setdefault("generated", [])
    for path in written:
        if path not in generated:
            generated.append(path)
    payload = {
        **preview,
        "status": "PASS",
        "writes_performed": True,
        "written": written,
        "backups": backups,
        "backup_root": str(backup_root) if backups else "",
    }
    write_json(project_root / ".forge" / "ci" / "latest-write.json", payload)
    return payload


def ci_action(project_root: Path, config: dict[str, Any], *, action: str, provider: str, force: bool = False) -> dict[str, Any]:
    if action == "preview":
        return preview_ci(project_root, config, provider)
    if action == "write":
        return write_ci(project_root, config, provider, force=force)
    raise ValueError(f"unsupported CI action: {action}")

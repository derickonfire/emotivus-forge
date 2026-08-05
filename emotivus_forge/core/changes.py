from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel
from .orientation import build_snapshot


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    files = snapshot.get("files", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(files, dict):
        files = {}
    canonical: list[tuple[str, int, int, str]] = []
    for path in sorted(files):
        item = files[path] if isinstance(files[path], dict) else {}
        canonical.append((
            str(path),
            int(item.get("size", 0) or 0),
            int(item.get("mtime_ns", 0) or 0),
            str(item.get("sha256", "")),
        ))
    payload = {
        "files": canonical,
        "truncated": bool(snapshot.get("truncated")) if isinstance(snapshot, dict) else False,
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def compare_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    before = previous.get("files", {}) if isinstance(previous, dict) else {}
    after = current.get("files", {}) if isinstance(current, dict) else {}
    if not isinstance(before, dict):
        before = {}
    if not isinstance(after, dict):
        after = {}
    added = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified: list[str] = []
    for path in sorted(set(before) & set(after)):
        left = before[path] if isinstance(before[path], dict) else {}
        right = after[path] if isinstance(after[path], dict) else {}
        if left.get("sha256") and right.get("sha256"):
            changed = left.get("sha256") != right.get("sha256")
        else:
            changed = (left.get("size"), left.get("mtime_ns")) != (right.get("size"), right.get("mtime_ns"))
        if changed:
            modified.append(path)
    paths = sorted(set(added + modified + deleted))
    return {
        "status": "changed" if paths else "unchanged",
        "count": len(paths),
        "paths": paths,
        "added": added,
        "modified": modified,
        "deleted": deleted,
    }


def reconcile_supplied_paths(
    project_root: Path,
    previous_snapshot: dict[str, Any],
    observed: dict[str, Any],
    supplied: list[str],
) -> dict[str, Any]:
    known_before = set(previous_snapshot.get("files", {})) if isinstance(previous_snapshot.get("files", {}), dict) else set()
    observed_paths = set(observed.get("paths", [])) if isinstance(observed, dict) else set()
    accepted: list[str] = []
    rejected: list[dict[str, str]] = []
    for raw in supplied:
        relative = normalize_rel(raw)
        if not relative or relative.startswith("../") or Path(relative).is_absolute():
            rejected.append({"path": raw, "reason": "path is outside the project"})
            continue
        if relative in observed_paths:
            if relative not in accepted:
                accepted.append(relative)
            continue
        if relative in known_before or (project_root / relative).exists():
            rejected.append({
                "path": relative,
                "reason": "path does not differ from the observed checkpoint; supplied paths may corroborate observed change but cannot create it",
            })
        else:
            rejected.append({
                "path": relative,
                "reason": "path does not exist and was not present in the observed checkpoint",
            })
    return {
        "accepted": sorted(accepted),
        "rejected": rejected,
        "policy": "corroboration-only",
    }


def detect_changes(
    project_root: Path,
    forge_root: Path,
    previous_snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    supplied_paths: list[str] | None = None,
) -> dict[str, Any]:
    current = build_snapshot(
        project_root,
        forge_root,
        max_files=int(settings.get("adoption_file_budget", 5000)),
        hash_file_limit=int(settings.get("hash_file_limit_bytes", 1_000_000)),
        hash_total_budget=int(settings.get("hash_total_budget_bytes", 8_000_000)),
    )
    observed = compare_snapshots(previous_snapshot, current)
    reconciled = reconcile_supplied_paths(project_root, previous_snapshot, observed, supplied_paths or [])
    paths = list(observed["paths"])
    confidence = "high" if not current.get("truncated") and not previous_snapshot.get("truncated") else "bounded"
    return {
        "status": observed["status"],
        "count": observed["count"],
        "paths": paths,
        "observed": observed,
        "supplied": reconciled,
        "current_snapshot": current,
        "baseline_fingerprint": snapshot_fingerprint(previous_snapshot),
        "current_fingerprint": snapshot_fingerprint(current),
        "source": "observed-checkpoint-reconciliation",
        "confidence": confidence,
    }

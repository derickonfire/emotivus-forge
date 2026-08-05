from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .common import read_json, sha256_file, utc_now, write_json
from .ledger import record_event
from .native_invocation import load_native_invocation_contract, refresh_native_invocation
from .paths import ForgePaths

CANONICAL_FILES: tuple[tuple[str, int, list[str]], ...] = (
    ("tools/run_all_checks.sh", 120, ["bash", "tools/run_all_checks.sh"]),
    ("tools/run-all-checks.sh", 118, ["bash", "tools/run-all-checks.sh"]),
    ("scripts/run_all_checks.sh", 115, ["bash", "scripts/run_all_checks.sh"]),
    ("scripts/run-all-checks.sh", 113, ["bash", "scripts/run-all-checks.sh"]),
    ("run_all_checks.sh", 110, ["bash", "run_all_checks.sh"]),
    ("run-all-checks.sh", 108, ["bash", "run-all-checks.sh"]),
    ("tools/check.py", 75, ["python3", "tools/check.py"]),
    ("tools/verify.py", 75, ["python3", "tools/verify.py"]),
)
EXECUTION_MODES = ("forge-authorized", "owner-only", "external-ci", "evidence-import-only")

MEMBER_RE = re.compile(
    r"(?m)(?:^|[;&|]\s*|\b(?:bash|sh|python3?|php|node)\s+)"
    r"(?P<path>(?:\./)?(?:tools|scripts|tests|test|bin)/[A-Za-z0-9_.\-/]+\.(?:sh|py|php|js|mjs|cjs))"
)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_fingerprint(project_root: Path, relative: str) -> str:
    path = project_root / relative
    try:
        return sha256_file(path) if path.is_file() else ""
    except OSError:
        return ""


def _candidate(
    identifier: str,
    command: list[str],
    score: int,
    source: str,
    kind: str,
    *,
    fingerprint: str,
    verification_style: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "command": command,
        "score": score,
        "source": source,
        "kind": kind,
        "verification_style": verification_style,
        "fingerprint": fingerprint,
        "status": "detected",
    }


def _package_candidates(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / "package.json"
    if not path.is_file() or path.stat().st_size > 1_000_000:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return []
    manager = "npm"
    if (project_root / "pnpm-lock.yaml").is_file():
        manager = "pnpm"
    elif (project_root / "yarn.lock").is_file():
        manager = "yarn"
    rows: list[dict[str, Any]] = []
    for name, score in (("check", 96), ("verify", 94), ("test", 88), ("lint", 70)):
        script = scripts.get(name)
        if isinstance(script, str) and script.strip():
            command = [manager, "run", name] if manager == "npm" else [manager, name]
            style = "conventional-test" if name == "test" else "project-orchestrator"
            rows.append(_candidate(
                f"package:{name}", command, score, f"package.json#scripts.{name}", "package-script",
                fingerprint=_hash_text(f"{manager}\0{name}\0{script}"), verification_style=style,
            ))
    return rows


def _make_candidates(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / "Makefile"
    if not path.is_file() or path.stat().st_size > 1_000_000:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    rows: list[dict[str, Any]] = []
    for target, score in (("check", 98), ("verify", 95), ("test", 86)):
        if re.search(rf"(?m)^{re.escape(target)}\s*:", text):
            rows.append(_candidate(
                f"make:{target}", ["make", target], score, f"Makefile#{target}", "make-target",
                fingerprint=_hash_text(f"{target}\0{text}"),
                verification_style="conventional-test" if target == "test" else "project-orchestrator",
            ))
    return rows


def _ecosystem_members(project_root: Path, canonical: dict[str, Any] | None, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(canonical, dict):
        return []
    members: dict[str, dict[str, Any]] = {}
    source = str(canonical.get("source", ""))
    source_file = source.split("#", 1)[0]
    path = project_root / source_file
    if path.is_file() and path.stat().st_size <= 1_000_000:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        for match in MEMBER_RE.finditer(text):
            relative = match.group("path").removeprefix("./")
            member_path = project_root / relative
            if member_path.is_file():
                members[relative] = {
                    "source": relative,
                    "relationship": "invoked-by-canonical-runner",
                    "fingerprint": _file_fingerprint(project_root, relative),
                    "status": "observed-not-registered-separately",
                }
    for row in rows:
        if row.get("id") == canonical.get("id"):
            continue
        member_source = str(row.get("source", ""))
        members.setdefault(member_source, {
            "source": member_source,
            "relationship": "alternate-entrypoint",
            "fingerprint": str(row.get("fingerprint", "")),
            "status": "catalogued-under-project-ecosystem",
        })
    return [members[key] for key in sorted(members)]


def _execution_policy(mode: str) -> str:
    policies = {
        "unassigned": "Detect and fingerprint the project gate, but do not execute or treat it as approved until project authority selects an execution mode.",
        "forge-authorized": "Forge may execute the fingerprint-bound canonical gate only when explicitly requested.",
        "owner-only": "Only the project owner may execute the gate. Forge may import fingerprint-bound owner evidence but must never run the command.",
        "external-ci": "An external CI system executes the gate. Forge may import fingerprint-bound CI evidence but must never run the command.",
        "evidence-import-only": "Forge never executes the gate; it only imports structured evidence bound to the current gate fingerprint.",
    }
    return policies.get(mode, policies["unassigned"])


def _registry_for_candidate(project_root: Path, discovered: dict[str, Any], match: dict[str, Any]) -> None:
    candidate_id = str(match.get("id", ""))
    discovered["canonical"] = match
    discovered["ecosystem"] = {
        "id": f"project-quality:{candidate_id}",
        "canonical_candidate_id": candidate_id,
        "members": _ecosystem_members(project_root.resolve(), match, discovered.get("candidates", [])),
        "policy": "Forge registers one canonical project quality ecosystem; subordinate tools remain project-owned and are not absorbed.",
    }


def discover_native_tools(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    rows: list[dict[str, Any]] = []
    for relative, score, command in CANONICAL_FILES:
        if (project_root / relative).is_file():
            rows.append(_candidate(
                f"file:{relative}", command, score, relative, "quality-runner",
                fingerprint=_file_fingerprint(project_root, relative), verification_style="project-orchestrator",
            ))
    rows.extend(_package_candidates(project_root))
    rows.extend(_make_candidates(project_root))
    rows.sort(key=lambda item: (-int(item["score"]), str(item["source"])))
    canonical = rows[0] if rows else None
    members = _ecosystem_members(project_root, canonical, rows)
    return {
        "schema": 4,
        "updated_utc": utc_now(),
        "verification_status": "existing-project-verification-detected" if rows else "unknown",
        "candidates": rows,
        "canonical": canonical,
        "ecosystem": {
            "id": f"project-quality:{canonical['id']}" if canonical else "",
            "canonical_candidate_id": canonical["id"] if canonical else "",
            "members": members,
            "policy": "Forge registers one canonical project quality ecosystem; subordinate tools remain project-owned and are not absorbed.",
        },
        "approval": {
            "status": "required" if canonical else "not-applicable",
            "lifecycle_status": "proposed" if canonical else "not-applicable",
            "execution_mode": "unassigned" if canonical else "not-applicable",
            "candidate_id": canonical["id"] if canonical else "",
            "approved_command": [],
            "approved_working_directory": "",
            "approved_environment": {},
            "approved_invocation": {},
            "invocation_contract_path": "",
            "approved_invocation_fingerprint": "",
            "current_invocation_fingerprint": "",
            "invocation_status": "required" if canonical else "not-applicable",
            "approved_fingerprint": "",
            "current_fingerprint": str(canonical.get("fingerprint", "")) if canonical else "",
            "approved_utc": "",
            "reason": "Project authority has not selected who may execute or supply evidence for this gate." if canonical else "",
        },
        "execution_policy": _execution_policy("unassigned" if canonical else "not-applicable"),
    }


def load_or_discover_native_tools(project_root: Path, *, refresh: bool = True) -> dict[str, Any]:
    paths = ForgePaths(project_root)
    existing = read_json(paths.native_tools, {})
    if not refresh and isinstance(existing, dict) and existing.get("schema") in {1, 2, 3, 4}:
        return existing
    discovered = discover_native_tools(project_root)
    if isinstance(existing, dict):
        approval = existing.get("approval", {})
        if isinstance(approval, dict) and approval.get("status") in {"approved", "registered", "reapproval-required"}:
            approved_id = str(approval.get("candidate_id", ""))
            match = next((item for item in discovered["candidates"] if item["id"] == approved_id), None)
            if match:
                _registry_for_candidate(project_root, discovered, match)
                old_fingerprint = str(approval.get("approved_fingerprint", ""))
                current_fingerprint = str(match.get("fingerprint", ""))
                mode = str(approval.get("execution_mode", "forge-authorized" if approval.get("status") == "approved" else "unassigned"))
                if mode not in EXECUTION_MODES:
                    mode = "unassigned"
                approved_invocation_fingerprint = str(approval.get("approved_invocation_fingerprint", ""))
                if approved_invocation_fingerprint == "legacy-unbound":
                    current_invocation = approval.get("approved_invocation", {}) if isinstance(approval.get("approved_invocation"), dict) else {}
                    invocation_status = "legacy-unbound"
                elif str(approval.get("invocation_contract_path", "")).strip():
                    current_invocation, invocation_status = refresh_native_invocation(project_root.resolve(), match, approval)
                else:
                    current_invocation, invocation_status = {}, "not-recorded"
                invocation_fingerprint = str(current_invocation.get("invocation_fingerprint", ""))
                invocation_ok = (
                    invocation_status in {"current", "legacy-unbound"}
                    and invocation_fingerprint
                    and approved_invocation_fingerprint == invocation_fingerprint
                ) or (mode != "forge-authorized" and invocation_status == "not-recorded")
                unchanged = bool(
                    old_fingerprint
                    and old_fingerprint == current_fingerprint
                    and mode in EXECUTION_MODES
                    and invocation_ok
                )
                active_status = "approved" if mode == "forge-authorized" else "registered"
                if unchanged:
                    reason = ""
                elif old_fingerprint != current_fingerprint:
                    reason = "The registered native-gate source fingerprint changed."
                elif mode == "forge-authorized":
                    reason = "The exact native invocation contract is missing or changed."
                else:
                    reason = ""
                discovered["approval"] = {
                    "status": active_status if unchanged else "reapproval-required",
                    "lifecycle_status": "active" if unchanged else "approval-required",
                    "execution_mode": mode,
                    "candidate_id": approved_id,
                    "approved_command": list(current_invocation.get("argv", [])) if unchanged and mode == "forge-authorized" else [],
                    "approved_working_directory": str(current_invocation.get("working_directory", "")) if unchanged else "",
                    "approved_environment": dict(current_invocation.get("environment", {})) if unchanged else {},
                    "approved_invocation": current_invocation if unchanged else {},
                    "invocation_contract_path": str(approval.get("invocation_contract_path", "")),
                    "approved_invocation_fingerprint": approved_invocation_fingerprint,
                    "current_invocation_fingerprint": invocation_fingerprint,
                    "invocation_status": invocation_status,
                    "approved_fingerprint": old_fingerprint,
                    "current_fingerprint": current_fingerprint,
                    "approved_utc": str(approval.get("approved_utc", "")),
                    "reason": reason,
                }
                discovered["execution_policy"] = _execution_policy(mode)
    write_json(paths.native_tools, discovered)
    return discovered


def set_native_execution_mode(
    project_root: Path,
    mode: str,
    candidate_id: str = "",
    invocation_contract_path: str = "",
    *,
    allow_legacy_unbound: bool = False,
) -> dict[str, Any]:
    mode = str(mode).strip().lower()
    if mode not in EXECUTION_MODES:
        raise RuntimeError(f"Native execution mode must be one of: {', '.join(EXECUTION_MODES)}")
    if mode == "forge-authorized" and not str(invocation_contract_path).strip() and not allow_legacy_unbound:
        raise RuntimeError(
            "Forge-authorized native execution requires --native-invocation with a project-owned exact invocation contract."
        )
    paths = ForgePaths(project_root)
    registry = load_or_discover_native_tools(project_root, refresh=True)
    target_id = candidate_id.strip()
    if not target_id:
        canonical = registry.get("canonical")
        if not isinstance(canonical, dict):
            raise RuntimeError("No native gate candidate is available to register.")
        target_id = str(canonical.get("id", ""))
    match = next((item for item in registry.get("candidates", []) if item.get("id") == target_id), None)
    if not isinstance(match, dict):
        raise RuntimeError(f"Native gate candidate was not found: {target_id}")
    if str(invocation_contract_path).strip():
        invocation = load_native_invocation_contract(project_root.resolve(), invocation_contract_path, match)
    elif allow_legacy_unbound:
        invocation = {
            "schema": 1,
            "candidate_id": target_id,
            "authority": "owner",
            "argv": list(match.get("command", [])),
            "working_directory": ".",
            "environment": {},
            "expected_checks": [],
            "expected_count": 0,
            "coverage_policy": "at-least",
            "timeout_seconds": 180,
            "verification_tier": "sandbox",
            "rationale": "Legacy programmatic test approval without a project-owned invocation contract.",
            "contract_path": "",
            "contract_sha256": "",
            "candidate_fingerprint": str(match.get("fingerprint", "")),
            "invocation_fingerprint": "legacy-unbound",
        }
    else:
        invocation = {}
    _registry_for_candidate(project_root, registry, match)
    status = "approved" if mode == "forge-authorized" else "registered"
    registry["schema"] = 4
    registry["approval"] = {
        "status": status,
        "lifecycle_status": "active",
        "execution_mode": mode,
        "candidate_id": target_id,
        "approved_command": list(invocation.get("argv", [])) if mode == "forge-authorized" else [],
        "approved_working_directory": str(invocation.get("working_directory", "")),
        "approved_environment": dict(invocation.get("environment", {})) if isinstance(invocation.get("environment"), dict) else {},
        "approved_invocation": invocation,
        "invocation_contract_path": str(invocation.get("contract_path", "")),
        "approved_invocation_fingerprint": str(invocation.get("invocation_fingerprint", "")),
        "current_invocation_fingerprint": str(invocation.get("invocation_fingerprint", "")),
        "invocation_status": "legacy-unbound" if allow_legacy_unbound else "current" if invocation else "not-recorded",
        "approved_fingerprint": str(match.get("fingerprint", "")),
        "current_fingerprint": str(match.get("fingerprint", "")),
        "approved_utc": utc_now(),
        "reason": "",
    }
    registry["execution_policy"] = _execution_policy(mode)
    write_json(paths.native_tools, registry)
    record_event(project_root, "native-gate-execution-policy", {
        "candidate_id": target_id,
        "source": match.get("source", ""),
        "execution_mode": mode,
        "command": invocation.get("argv", []),
        "working_directory": invocation.get("working_directory", ""),
        "expected_count": invocation.get("expected_count", 0),
        "coverage_policy": invocation.get("coverage_policy", "undeclared") if invocation else "undeclared",
        "gate_fingerprint": match.get("fingerprint", ""),
        "invocation_fingerprint": invocation.get("invocation_fingerprint", ""),
        "verification_style": match.get("verification_style", ""),
    }, source="owner")
    return registry


def approve_native_tool(project_root: Path, candidate_id: str = "", invocation_contract_path: str = "") -> dict[str, Any]:
    return set_native_execution_mode(project_root, "forge-authorized", candidate_id, invocation_contract_path)


def approve_canonical_native_tool(project_root: Path, invocation_contract_path: str = "") -> dict[str, Any]:
    if invocation_contract_path:
        return approve_native_tool(project_root, "", invocation_contract_path)
    return set_native_execution_mode(project_root, "forge-authorized", allow_legacy_unbound=True)

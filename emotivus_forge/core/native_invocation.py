from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .common import normalize_rel, read_json, sha256_file

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_KEY_RE = re.compile(r"(?:SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL)", re.I)
VALID_COVERAGE_POLICIES = {"exact", "at-least"}


def _fingerprint(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _project_file(project_root: Path, raw: str, *, label: str) -> tuple[Path, str]:
    candidate = Path(str(raw))
    path = candidate if candidate.is_absolute() else project_root / candidate
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(project_root).as_posix()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{label} must remain inside the adopted project.") from exc
    if resolved == project_root / ".forge" or (project_root / ".forge") in resolved.parents:
        raise RuntimeError(f"{label} must be project-owned and remain outside .forge state.")
    return resolved, relative


def load_native_invocation_contract(
    project_root: Path,
    contract_path: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _project_file(project_root, contract_path, label="Native invocation contract")
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Native invocation contract must resolve to a regular project file.")
    if path.stat().st_size > 100_000:
        raise RuntimeError("Native invocation contract exceeds the 100 KB limit.")
    value = read_json(path, {}, strict=False)
    if not isinstance(value, dict) or value.get("schema") not in {1, "forge-native-invocation/1"}:
        raise RuntimeError("Native invocation contract must use schema forge-native-invocation/1.")
    authority = str(value.get("authority", "")).strip().lower()
    if authority not in {"owner", "project-owner"}:
        raise RuntimeError("Native invocation contract must be recorded by the project owner.")
    expected_candidate = str(candidate.get("id", ""))
    declared_candidate = str(value.get("candidate_id", "canonical")).strip()
    if declared_candidate not in {"canonical", expected_candidate}:
        raise RuntimeError("Native invocation contract names a different native-gate candidate.")

    argv_raw = value.get("argv", [])
    if not isinstance(argv_raw, list) or not argv_raw or len(argv_raw) > 40:
        raise RuntimeError("Native invocation argv must contain 1 to 40 exact arguments.")
    argv = [str(item) for item in argv_raw]
    if any(not item or "\x00" in item or len(item) > 1000 for item in argv):
        raise RuntimeError("Native invocation arguments must be non-empty bounded strings without NUL bytes.")
    base_command = [str(item) for item in candidate.get("command", [])]
    if not base_command or argv[: len(base_command)] != base_command:
        raise RuntimeError(
            "Native invocation argv must begin with the detected canonical command exactly; append only project-approved arguments."
        )

    cwd_raw = str(value.get("working_directory", ".")).strip() or "."
    cwd_path, cwd_relative = _project_file(project_root, cwd_raw, label="Native invocation working directory")
    if not cwd_path.is_dir() or cwd_path.is_symlink():
        raise RuntimeError("Native invocation working directory must resolve to a regular project directory.")

    environment_raw = value.get("environment", {})
    if not isinstance(environment_raw, dict) or len(environment_raw) > 20:
        raise RuntimeError("Native invocation environment must be an object with at most 20 non-secret values.")
    environment: dict[str, str] = {}
    for raw_key, raw_value in environment_raw.items():
        key = str(raw_key)
        item = str(raw_value)
        if not _ENV_KEY_RE.fullmatch(key):
            raise RuntimeError(f"Invalid native invocation environment key: {key}")
        if _SECRET_KEY_RE.search(key):
            raise RuntimeError(
                f"Native invocation environment may not persist secret-shaped key {key}; supply credentials outside Forge state."
            )
        if len(item) > 500 or "\x00" in item:
            raise RuntimeError(f"Native invocation environment value for {key} is invalid or too large.")
        environment[key] = item

    expected_raw = value.get("expected_checks", [])
    if not isinstance(expected_raw, list) or len(expected_raw) > 300:
        raise RuntimeError("expected_checks must be an array with at most 300 check identifiers.")
    expected_checks = [str(item).strip() for item in expected_raw if str(item).strip()]
    if len(set(expected_checks)) != len(expected_checks):
        raise RuntimeError("expected_checks may not contain duplicate identifiers.")
    expected_count_raw = value.get("expected_count")
    expected_count = 0
    if expected_count_raw is not None:
        if not isinstance(expected_count_raw, int) or isinstance(expected_count_raw, bool) or not 1 <= expected_count_raw <= 1000:
            raise RuntimeError("expected_count must be an integer from 1 to 1000.")
        expected_count = expected_count_raw
    if not expected_checks and not expected_count:
        raise RuntimeError("Native invocation must declare expected_checks or expected_count so partial execution cannot look complete.")
    if expected_checks and expected_count and expected_count != len(expected_checks):
        raise RuntimeError("expected_count must equal the number of expected_checks when both are supplied.")

    coverage_policy = str(value.get("coverage_policy", "exact")).strip().lower()
    if coverage_policy not in VALID_COVERAGE_POLICIES:
        raise RuntimeError("coverage_policy must be exact or at-least.")
    timeout_seconds = value.get("timeout_seconds", 300)
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= 3600:
        raise RuntimeError("timeout_seconds must be an integer from 1 to 3600.")
    verification_tier = str(value.get("verification_tier", "sandbox")).strip().lower() or "sandbox"

    normalized = {
        "schema": 1,
        "candidate_id": expected_candidate,
        "authority": "owner",
        "argv": argv,
        "working_directory": cwd_relative or ".",
        "environment": environment,
        "expected_checks": expected_checks,
        "expected_count": expected_count or len(expected_checks),
        "coverage_policy": coverage_policy,
        "timeout_seconds": timeout_seconds,
        "verification_tier": verification_tier,
        "rationale": str(value.get("rationale", "")).strip()[:1000],
        "contract_path": relative,
        "contract_sha256": sha256_file(path),
        "candidate_fingerprint": str(candidate.get("fingerprint", "")),
    }
    normalized["invocation_fingerprint"] = _fingerprint({
        key: normalized[key]
        for key in (
            "candidate_id", "argv", "working_directory", "environment", "expected_checks",
            "expected_count", "coverage_policy", "timeout_seconds", "verification_tier",
            "candidate_fingerprint",
        )
    })
    return normalized


def refresh_native_invocation(
    project_root: Path,
    candidate: dict[str, Any],
    approval: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    path = str(approval.get("invocation_contract_path", "")).strip()
    if not path:
        return {}, "required"
    try:
        current = load_native_invocation_contract(project_root, path, candidate)
    except RuntimeError:
        return {}, "stale"
    approved = str(approval.get("approved_invocation_fingerprint", ""))
    status = "current" if approved and approved == current.get("invocation_fingerprint") else "stale"
    return current, status


def assess_native_coverage(entries: list[dict[str, Any]], invocation: dict[str, Any]) -> dict[str, Any]:
    observed_ids = sorted({str(item.get("id", "")).strip() for item in entries if str(item.get("id", "")).strip()})
    expected_ids = [str(item) for item in invocation.get("expected_checks", []) if str(item)]
    expected_count = int(invocation.get("expected_count", 0) or 0)
    policy = str(invocation.get("coverage_policy", "exact"))
    missing: list[str] = []
    unexpected: list[str] = []
    if expected_ids:
        missing = sorted(set(expected_ids) - set(observed_ids))
        unexpected = sorted(set(observed_ids) - set(expected_ids))
        complete = not missing and (policy != "exact" or not unexpected)
    else:
        complete = len(observed_ids) >= expected_count if policy == "at-least" else len(observed_ids) == expected_count
    return {
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        "policy": policy,
        "expected_count": expected_count,
        "observed_count": len(observed_ids),
        "expected_checks": expected_ids,
        "observed_checks": observed_ids,
        "missing_checks": missing,
        "unexpected_checks": unexpected,
        "invocation_fingerprint": str(invocation.get("invocation_fingerprint", "")),
        "boundary": "Coverage proves only that the declared gate members reported; it does not prove those members are correct or exhaustive.",
    }


def validate_native_invocation_contract(project_root: Path, contract_path: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper used by command handlers and tests."""
    normalized = load_native_invocation_contract(project_root, contract_path, candidate)
    return {
        "source": normalized["contract_path"],
        "source_sha256": normalized["contract_sha256"],
        "contract_fingerprint": normalized["invocation_fingerprint"],
        "contract": {
            "schema": 1,
            "candidate_id": normalized["candidate_id"],
            "authority": normalized["authority"],
            "rationale": normalized["rationale"],
            "command": normalized["argv"],
            "working_directory": normalized["working_directory"],
            "environment": normalized["environment"],
            "expected_checks": normalized["expected_checks"],
            "expected_check_count": normalized["expected_count"],
            "coverage_policy": normalized["coverage_policy"],
            "expected_exit_codes": [0],
            "timeout_seconds": normalized["timeout_seconds"],
            "verification_tier": normalized["verification_tier"],
            "verification_boundary": "Exact invocation and declared check coverage only; detector correctness and release readiness remain separate.",
        },
    }


def invocation_is_current(project_root: Path, invocation: dict[str, Any]) -> tuple[bool, str]:
    source = str(invocation.get("source", "")).strip()
    contract = invocation.get("contract", {}) if isinstance(invocation.get("contract"), dict) else {}
    candidate = {
        "id": str(contract.get("candidate_id", "")),
        "command": list(contract.get("command", []))[:2],
        "fingerprint": "",
    }
    if not source or not contract:
        return False, "No exact native invocation contract is recorded."
    path = project_root.resolve() / source
    if not path.is_file() or path.is_symlink():
        return False, "The exact native invocation contract is missing."
    if sha256_file(path) != str(invocation.get("source_sha256", "")):
        return False, "The exact native invocation contract changed."
    try:
        raw = read_json(path, {}, strict=False)
    except Exception:
        return False, "The exact native invocation contract is unreadable."
    if not isinstance(raw, dict):
        return False, "The exact native invocation contract is invalid."
    # The stored fingerprint is enough here; full semantic revalidation occurs when authority is renewed.
    return bool(str(invocation.get("contract_fingerprint", ""))), ""


def evaluate_invocation_coverage(entries: list[dict[str, Any]], invocation: dict[str, Any]) -> dict[str, Any]:
    contract = invocation.get("contract", {}) if isinstance(invocation.get("contract"), dict) else invocation
    normalized = {
        "expected_checks": list(contract.get("expected_checks", [])) if isinstance(contract.get("expected_checks"), list) else [],
        "expected_count": int(contract.get("expected_check_count", contract.get("expected_count", 0)) or 0),
        "coverage_policy": str(contract.get("coverage_policy", "exact")),
        "invocation_fingerprint": str(invocation.get("contract_fingerprint", invocation.get("invocation_fingerprint", ""))),
    }
    result = assess_native_coverage(entries, normalized)
    return {
        "status": "COMPLETE" if result["complete"] else "INCOMPLETE",
        "policy": result["policy"],
        "expected_check_count": result["expected_count"],
        "observed_check_count": result["observed_count"],
        "expected_checks": result["expected_checks"],
        "observed_checks": result["observed_checks"],
        "missing_checks": result["missing_checks"],
        "unexpected_checks": result["unexpected_checks"],
        "count_shortfall": result["observed_count"] < result["expected_count"],
        "count_excess": result["policy"] == "exact" and result["observed_count"] > result["expected_count"],
        "invocation_fingerprint": result["invocation_fingerprint"],
        "boundary": result["boundary"],
    }


def execution_environment(overrides: dict[str, Any]) -> dict[str, str]:
    import os
    environment = dict(os.environ)
    environment.update({str(key): str(value) for key, value in overrides.items()})
    return environment

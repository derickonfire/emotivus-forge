from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from ..core.common import sha256_file, utc_now, write_json
from ..core.paths import ForgePaths
from ..core.native_invocation import assess_native_coverage
from ..core.truth import TruthRecord, normalize_verification_tier, summarize_truth_records

JSON_MARKER_RE = re.compile(r"^\s*FORGE_(?:EVIDENCE|CHECK)\s+(\{.*\})\s*$")
PIPE_MARKER_RE = re.compile(r"^\s*FORGE_CHECK\|(.+?)\s*$")
STATUS_MARKER_RE = re.compile(r"^\s*(?:\[)?(PASS|FAIL|SKIP|WARN|WARNING)(?:\])?\s*(?::|\||-|—)\s*(.+?)\s*$", re.I)
VALID_STATUSES = {"PASS", "FAIL", "SKIP", "WARN"}


def _clean_status(value: Any) -> str:
    status = str(value or "").strip().upper()
    if status == "WARNING":
        status = "WARN"
    return status if status in VALID_STATUSES else "UNKNOWN"


def _evidence_from_mapping(value: dict[str, Any], line_number: int, marker: str) -> dict[str, Any] | None:
    identifier = str(value.get("id") or value.get("check") or value.get("name") or "").strip()
    status = _clean_status(value.get("status"))
    if not identifier or status == "UNKNOWN":
        return None
    surfaces_raw = value.get("surfaces", value.get("surface", []))
    if isinstance(surfaces_raw, str):
        surfaces = [item.strip() for item in re.split(r"[,;]", surfaces_raw) if item.strip()]
    elif isinstance(surfaces_raw, list):
        surfaces = [str(item).strip() for item in surfaces_raw if str(item).strip()]
    else:
        surfaces = []
    return {
        "id": identifier[:160],
        "status": status,
        "type": str(value.get("type", value.get("evidence_type", "native"))).strip()[:80] or "native",
        "surfaces": surfaces[:30],
        "message": str(value.get("message", "")).strip()[:400],
        "line": line_number,
        "marker": marker,
        "truth_state": "OBSERVED",
        "verification_tier": normalize_verification_tier(value.get("verification_tier", value.get("tier", "sandbox")), default="sandbox"),
        "attempted": True,
    }


def parse_native_evidence(stdout: str, stderr: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    parse_errors = 0
    combined = [("stdout", line) for line in stdout.splitlines()] + [("stderr", line) for line in stderr.splitlines()]
    for line_number, (stream, line) in enumerate(combined, 1):
        json_match = JSON_MARKER_RE.match(line)
        if json_match:
            try:
                value = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if isinstance(value, dict):
                entry = _evidence_from_mapping(value, line_number, f"forge-json:{stream}")
                if entry:
                    entries.append(entry)
            continue
        pipe_match = PIPE_MARKER_RE.match(line)
        if pipe_match:
            fields: dict[str, str] = {}
            for segment in pipe_match.group(1).split("|"):
                if "=" in segment:
                    key, raw = segment.split("=", 1)
                    fields[key.strip().lower()] = raw.strip()
            entry = _evidence_from_mapping(fields, line_number, f"forge-pipe:{stream}")
            if entry:
                entries.append(entry)
            else:
                parse_errors += 1
            continue
        status_match = STATUS_MARKER_RE.match(line)
        if status_match:
            label = status_match.group(2).strip()
            entry = {
                "id": label[:160],
                "status": _clean_status(status_match.group(1)),
                "type": "native",
                "surfaces": [],
                "message": "",
                "line": line_number,
                "marker": f"status-line:{stream}",
                "truth_state": "OBSERVED",
                "verification_tier": "sandbox",
                "attempted": True,
            }
            entries.append(entry)
    counts = Counter(entry["status"] for entry in entries)
    surfaces = sorted({surface for entry in entries for surface in entry.get("surfaces", [])})
    evidence_types = sorted({str(entry.get("type", "native")) for entry in entries})
    truth_summary = summarize_truth_records(entries)
    return {
        "schema": 1,
        "entries": entries[:1000],
        "entry_count": len(entries),
        "status_counts": dict(sorted(counts.items())),
        "surfaces": surfaces,
        "evidence_types": evidence_types,
        "parse_errors": parse_errors,
        "coverage_status": "reported" if surfaces else "unknown",
        "truth_summary": truth_summary,
        "verification_tiers": sorted({str(entry.get("verification_tier", "sandbox")) for entry in entries}),
    }


def _summarize_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(entry.get("status", "UNKNOWN")) for entry in entries)
    surfaces = sorted({
        str(surface) for entry in entries for surface in entry.get("surfaces", [])
        if str(surface).strip()
    })
    evidence_types = sorted({str(entry.get("type", "native")) for entry in entries})
    return {
        "schema": 1,
        "entries": entries[:1000],
        "entry_count": len(entries),
        "status_counts": dict(sorted(counts.items())),
        "surfaces": surfaces,
        "evidence_types": evidence_types,
        "parse_errors": 0,
        "coverage_status": "reported" if surfaces else "unknown",
        "truth_summary": summarize_truth_records(entries),
        "verification_tiers": sorted({str(entry.get("verification_tier", "sandbox")) for entry in entries}),
    }


def _blocked(reason: str, *, mode: str = "unassigned", subject: str = "native-gate.execution") -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "reason": reason,
        "command": [],
        "returncode": None,
        "execution_mode": mode,
        "execution_authority": "",
        "evidence": {"entry_count": 0, "surfaces": [], "coverage_status": "unknown"},
        "evidence_records": [],
        "raw_evidence": {},
        "truth": TruthRecord(
            subject=subject, truth_state="BLOCKED_UNATTEMPTED", result="BLOCKED",
            verification_tier="sandbox", attempted=False, reason=reason,
        ).to_dict(),
    }


def _write_evidence(
    project_root: Path,
    *,
    run_id: str,
    command: list[str],
    result: dict[str, Any],
    stdout: str,
    stderr: str,
) -> dict[str, str]:
    root = ForgePaths(project_root).native_evidence / run_id
    root.mkdir(parents=True, exist_ok=False)
    stdout_path = root / "stdout.log"
    stderr_path = root / "stderr.log"
    result_path = root / "result.json"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    write_json(result_path, {
        "schema": 1,
        "run_id": run_id,
        "generated_utc": utc_now(),
        "command": command,
        **result,
    })
    forge_root = project_root / ".forge"
    return {
        "result": result_path.relative_to(forge_root).as_posix(),
        "stdout": stdout_path.relative_to(forge_root).as_posix(),
        "stderr": stderr_path.relative_to(forge_root).as_posix(),
    }


def _write_imported_evidence(
    project_root: Path, *, run_id: str, source_path: Path, source_relative: str, source_digest: str, result: dict[str, Any]
) -> dict[str, str]:
    root = ForgePaths(project_root).native_evidence / run_id
    root.mkdir(parents=True, exist_ok=False)
    imported_path = root / "imported-evidence.json"
    result_path = root / "result.json"
    imported_path.write_bytes(source_path.read_bytes())
    write_json(result_path, {
        "schema": 1,
        "run_id": run_id,
        "generated_utc": utc_now(),
        "imported_from": source_relative,
        "imported_sha256": source_digest,
        **result,
    })
    forge_root = project_root / ".forge"
    return {
        "result": result_path.relative_to(forge_root).as_posix(),
        "imported": imported_path.relative_to(forge_root).as_posix(),
        "source": source_relative,
    }


def _undeclared_coverage(entries: list[dict[str, Any]]) -> dict[str, Any]:
    observed = sorted({str(item.get("id", "")) for item in entries if str(item.get("id", "")).strip()})
    return {
        "status": "undeclared",
        "complete": False,
        "policy": "none",
        "expected_count": 0,
        "observed_count": len(observed),
        "expected_checks": [],
        "observed_checks": observed,
        "missing_checks": [],
        "unexpected_checks": [],
        "invocation_fingerprint": "",
        "boundary": "No exact invocation contract was recorded; gate completeness is not established.",
    }


def import_native_evidence(project_root: Path, registry: dict[str, Any], evidence_path: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    approval = registry.get("approval", {}) if isinstance(registry.get("approval"), dict) else {}
    mode = str(approval.get("execution_mode", "unassigned"))
    if approval.get("status") not in {"approved", "registered"}:
        return _blocked("The native gate has no current fingerprint-bound execution policy.", mode=mode, subject="native-gate.evidence-import")
    raw_path = Path(str(evidence_path))
    source_path = raw_path if raw_path.is_absolute() else project_root / raw_path
    try:
        source_path = source_path.resolve()
        source_path.relative_to(project_root)
    except (OSError, ValueError):
        return _blocked("Imported native evidence must remain inside the adopted project.", mode=mode, subject="native-gate.evidence-import")
    if source_path == project_root / ".forge" or (project_root / ".forge") in source_path.parents:
        return _blocked("Imported native evidence must come from project-owned evidence outside Forge state.", mode=mode, subject="native-gate.evidence-import")
    if not source_path.is_file() or source_path.is_symlink():
        return _blocked("Imported native evidence does not resolve to a regular project file.", mode=mode, subject="native-gate.evidence-import")
    try:
        if source_path.stat().st_size > 5_000_000:
            return _blocked("Imported native evidence exceeds the 5 MB bounded import limit.", mode=mode, subject="native-gate.evidence-import")
        value = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _blocked(f"Imported native evidence is not readable JSON: {exc}", mode=mode, subject="native-gate.evidence-import")
    if not isinstance(value, dict) or value.get("schema") not in {1, "forge-native-evidence/1"}:
        return _blocked("Imported native evidence must use schema forge-native-evidence/1.", mode=mode, subject="native-gate.evidence-import")
    canonical = registry.get("canonical") if isinstance(registry.get("canonical"), dict) else {}
    expected_id = str(canonical.get("id", ""))
    expected_fingerprint = str(canonical.get("fingerprint", ""))
    if str(value.get("candidate_id", "")) != expected_id:
        return _blocked("Imported evidence names a different native-gate candidate.", mode=mode, subject="native-gate.evidence-import")
    if str(value.get("gate_fingerprint", "")) != expected_fingerprint or expected_fingerprint != str(approval.get("approved_fingerprint", "")):
        return _blocked("Imported evidence is not bound to the current native-gate fingerprint.", mode=mode, subject="native-gate.evidence-import")
    invocation = approval.get("approved_invocation", {}) if isinstance(approval.get("approved_invocation"), dict) else {}
    invocation_fingerprint = str(approval.get("approved_invocation_fingerprint", ""))
    if invocation_fingerprint and invocation_fingerprint != "legacy-unbound":
        if str(value.get("invocation_fingerprint", "")) != invocation_fingerprint:
            return _blocked("Imported evidence is not bound to the current exact native invocation contract.", mode=mode, subject="native-gate.evidence-import")
    authority = str(value.get("execution_authority", "")).strip().lower()
    if mode == "owner-only" and authority != "owner":
        return _blocked("Owner-only native evidence must identify the owner as the execution authority.", mode=mode, subject="native-gate.evidence-import")
    if mode == "external-ci" and authority not in {"external-ci", "ci"}:
        return _blocked("External-CI native evidence must identify external-ci as the execution authority.", mode=mode, subject="native-gate.evidence-import")
    if authority not in {"owner", "external-ci", "ci", "trusted-external"}:
        return _blocked("Imported native evidence has no recognized execution authority.", mode=mode, subject="native-gate.evidence-import")
    top_status = str(value.get("status", "")).upper()
    if top_status not in {"PASS", "FAIL", "ERROR"}:
        return _blocked("Imported native evidence status must be PASS, FAIL, or ERROR.", mode=mode, subject="native-gate.evidence-import")
    tier = normalize_verification_tier(value.get("verification_tier", invocation.get("verification_tier", "sandbox")), default="sandbox")
    entries: list[dict[str, Any]] = []
    raw_entries = value.get("entries", [])
    if not isinstance(raw_entries, list):
        return _blocked("Imported native evidence entries must be an array.", mode=mode, subject="native-gate.evidence-import")
    for index, item in enumerate(raw_entries, 1):
        if not isinstance(item, dict):
            return _blocked(f"Imported native evidence entry {index} must be an object.", mode=mode, subject="native-gate.evidence-import")
        merged = dict(item)
        merged.setdefault("verification_tier", tier)
        entry = _evidence_from_mapping(merged, index, "imported-json")
        if entry is None:
            return _blocked(f"Imported native evidence entry {index} is missing a valid id or status.", mode=mode, subject="native-gate.evidence-import")
        entries.append(entry)
    parsed = _summarize_entries(entries)
    coverage = assess_native_coverage(entries, invocation) if invocation else _undeclared_coverage(entries)
    if parsed.get("status_counts", {}).get("FAIL", 0):
        top_status = "FAIL"
    reason = str(value.get("reason", ""))[:500]
    if coverage.get("status") == "incomplete":
        top_status = "FAIL"
        reason = "Imported native evidence did not cover the complete approved invocation."
    source_relative = source_path.relative_to(project_root).as_posix()
    source_digest = sha256_file(source_path)
    timestamp = utc_now().replace(":", "").replace("-", "").replace("+00:00", "Z") + f"-{time.time_ns() % 1_000_000_000:09d}"
    run_id = f"{timestamp}-{expected_fingerprint[:10] or 'unbound'}-import"
    result_for_disk = {
        "status": top_status,
        "reason": reason,
        "returncode": value.get("returncode"),
        "execution_mode": mode,
        "execution_authority": authority,
        "executed_utc": str(value.get("executed_utc", "")),
        "evidence": parsed,
        "invocation_fingerprint": invocation_fingerprint,
        "coverage": coverage,
        "raw_output_retained": False,
    }
    try:
        refs = _write_imported_evidence(
            project_root, run_id=run_id, source_path=source_path, source_relative=source_relative,
            source_digest=source_digest, result=result_for_disk,
        )
    except OSError as exc:
        return {
            **_blocked(f"Native evidence was valid, but Forge could not retain it: {exc}", mode=mode, subject="native-gate.evidence-import"),
            "truth": TruthRecord(
                subject="native-gate.evidence-import", truth_state="BLOCKED_ATTEMPTED", result="ERROR",
                verification_tier=tier, attempted=True, reason=str(exc), source=source_relative,
            ).to_dict(),
        }
    evidence_summary = {key: item for key, item in parsed.items() if key != "entries"}
    evidence_records = [{
        "id": str(item.get("id", "")), "status": str(item.get("status", "UNKNOWN")),
        "type": str(item.get("type", "native")),
        "surfaces": list(item.get("surfaces", [])) if isinstance(item.get("surfaces"), list) else [],
        "truth_state": "OBSERVED", "verification_tier": str(item.get("verification_tier", tier)), "attempted": True,
    } for item in entries]
    exclusions = ["Forge did not execute the native gate"]
    if coverage.get("status") == "undeclared":
        exclusions.append("native invocation completeness was not declared")
    return {
        "status": top_status,
        "reason": reason,
        "command": list(invocation.get("argv", [])) if invocation else [],
        "working_directory": str(invocation.get("working_directory", "")) if invocation else "",
        "returncode": value.get("returncode"),
        "execution_mode": mode,
        "execution_authority": authority,
        "evidence": evidence_summary,
        "evidence_records": evidence_records,
        "invocation_fingerprint": invocation_fingerprint,
        "coverage": coverage,
        "raw_evidence": refs,
        "raw_output_retained": False,
        "output_in_chat": False,
        "imported": True,
        "truth": TruthRecord(
            subject="native-gate.evidence-import", truth_state="OBSERVED", result=top_status,
            verification_tier=tier, attempted=True, reason=reason,
            source=refs.get("result", ""), exclusions=tuple(exclusions),
        ).to_dict(),
    }


def run_native_gate(project_root: Path, registry: dict[str, Any], timeout: int) -> dict[str, Any]:
    approval = registry.get("approval", {})
    mode = str(approval.get("execution_mode", "unassigned")) if isinstance(approval, dict) else "unassigned"
    if not isinstance(approval, dict) or approval.get("status") not in {"approved", "registered"}:
        return _blocked("The detected native gate has no current fingerprint-bound execution policy.", mode=mode)
    if mode != "forge-authorized":
        return _blocked(
            f"Forge may not execute this native gate because its project-owned execution mode is {mode}. Import current structured evidence instead.",
            mode=mode,
        )
    invocation = approval.get("approved_invocation", {}) if isinstance(approval.get("approved_invocation"), dict) else {}
    command = [str(item) for item in invocation.get("argv", [])]
    if not command:
        return _blocked("Forge-authorized execution requires an exact project-owned native invocation contract.", mode=mode)
    working_relative = str(invocation.get("working_directory", ".")) or "."
    working_directory = (project_root / working_relative).resolve()
    try:
        working_directory.relative_to(project_root.resolve())
    except ValueError:
        return _blocked("The approved native-gate working directory escapes the adopted project.", mode=mode)
    if not working_directory.is_dir():
        return _blocked("The approved native-gate working directory no longer exists.", mode=mode)
    environment = dict(os.environ)
    overrides = invocation.get("environment", {}) if isinstance(invocation.get("environment"), dict) else {}
    environment.update({str(key): str(value) for key, value in overrides.items()})
    tier = normalize_verification_tier(invocation.get("verification_tier", "sandbox"), default="sandbox")
    effective_timeout = min(max(1, int(invocation.get("timeout_seconds", timeout))), max(1, int(timeout)))
    stdout = ""
    stderr = ""
    returncode: int | None = None
    reason = ""
    status = "ERROR"
    attempted = False
    truth_state = "UNKNOWN"
    try:
        attempted = True
        completed = subprocess.run(
            command,
            cwd=working_directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        returncode = completed.returncode
        status = "PASS" if completed.returncode == 0 else "FAIL"
        truth_state = "OBSERVED"
        if status == "FAIL":
            reason = f"Native gate returned exit code {completed.returncode}."
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        reason = f"Native gate exceeded the {effective_timeout}-second timeout."
        status = "ERROR"
        truth_state = "BLOCKED_ATTEMPTED"
    except OSError as exc:
        reason = str(exc)
        status = "ERROR"
        truth_state = "BLOCKED_ATTEMPTED"
    parsed = parse_native_evidence(stdout, stderr)
    coverage = assess_native_coverage(parsed.get("entries", []), invocation)
    if parsed.get("status_counts", {}).get("FAIL", 0):
        status = "FAIL"
        truth_state = "OBSERVED"
        if returncode == 0 and not reason:
            reason = "Structured native evidence reported one or more failed checks despite a zero exit code."
    if attempted and coverage.get("status") == "incomplete":
        status = "FAIL"
        truth_state = "OBSERVED"
        details = []
        if coverage.get("missing_checks"):
            details.append(f"missing {len(coverage['missing_checks'])} expected check(s)")
        if coverage.get("unexpected_checks") and coverage.get("policy") == "exact":
            details.append(f"observed {len(coverage['unexpected_checks'])} undeclared check(s)")
        if not details:
            details.append(f"observed {coverage.get('observed_count', 0)} of {coverage.get('expected_count', 0)} expected checks")
        reason = "Native invocation coverage incomplete: " + "; ".join(details) + "."
    timestamp = utc_now().replace(":", "").replace("-", "").replace("+00:00", "Z") + f"-{time.time_ns() % 1_000_000_000:09d}"
    fingerprint = str(approval.get("approved_fingerprint", ""))[:10] or "unbound"
    run_id = f"{timestamp}-{fingerprint}"
    result_for_disk = {
        "status": status,
        "reason": reason,
        "returncode": returncode,
        "evidence": parsed,
        "invocation_fingerprint": str(invocation.get("invocation_fingerprint", "")),
        "working_directory": working_relative,
        "environment_overrides": sorted(overrides),
        "coverage": coverage,
        "raw_output_retained": True,
    }
    try:
        refs = _write_evidence(
            project_root, run_id=run_id, command=command, result=result_for_disk, stdout=stdout, stderr=stderr,
        )
    except OSError as exc:
        refs = {}
        status = "ERROR"
        reason = f"Native gate ran, but Forge could not retain its raw evidence: {exc}"
    evidence_summary = {key: item for key, item in parsed.items() if key != "entries"}
    evidence_records = [{
        "id": str(item.get("id", "")),
        "status": str(item.get("status", "UNKNOWN")),
        "type": str(item.get("type", "native")),
        "surfaces": list(item.get("surfaces", [])) if isinstance(item.get("surfaces"), list) else [],
        "truth_state": str(item.get("truth_state", "OBSERVED")),
        "verification_tier": str(item.get("verification_tier", tier)),
        "attempted": bool(item.get("attempted", True)),
    } for item in parsed.get("entries", []) if isinstance(item, dict)]
    exclusions = ["browser", "staging", "production"]
    boundary = str(invocation.get("verification_boundary", "")).strip()
    if boundary:
        exclusions.append(boundary)
    return {
        "status": status,
        "reason": reason,
        "command": command,
        "working_directory": working_relative,
        "environment_overrides": sorted(overrides),
        "returncode": returncode,
        "execution_mode": "forge-authorized",
        "execution_authority": "forge",
        "invocation_fingerprint": str(invocation.get("invocation_fingerprint", "")),
        "coverage": coverage,
        "evidence": evidence_summary,
        "evidence_records": evidence_records,
        "raw_evidence": refs,
        "raw_output_retained": bool(refs),
        "output_in_chat": False,
        "truth": TruthRecord(
            subject="native-gate.execution", truth_state=truth_state, result=status,
            verification_tier=tier, attempted=attempted, reason=reason,
            source=refs.get("result", "") if isinstance(refs, dict) else "",
            exclusions=tuple(exclusions),
        ).to_dict(),
    }


from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .doctor import run_doctor
from .utils import sha256_bytes, utc_now, write_json

REMEDIATION_ROOT = Path(".forge/doctor/remediation")


def _proposal_id(kind: str, target: str, payload: dict[str, Any]) -> str:
    digest = sha256_bytes(json.dumps({"kind": kind, "target": target, "payload": payload}, sort_keys=True).encode("utf-8"))[:12]
    return f"doctor-{kind}-{digest}"


def propose_remediations(project_root: Path, forge_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    project_root = project_root.resolve()
    doctor = run_doctor(project_root, forge_root, config, write=True)
    allowed = set(str(item) for item in config.get("maintenance", {}).get("doctor", {}).get("allowed_types", []))
    proposals: list[dict[str, Any]] = []
    for raw in config.get("environment", {}).get("expected_layout", []):
        if not isinstance(raw, dict) or not raw.get("required", True) or not raw.get("repair"):
            continue
        path = str(raw.get("path", "")).strip()
        if not path:
            continue
        candidate = (project_root / path).resolve()
        kind = str(raw.get("kind", "either"))
        present = candidate.is_dir() if kind == "directory" else candidate.is_file() if kind == "file" else candidate.exists()
        if present:
            continue
        repair = raw.get("repair") if isinstance(raw.get("repair"), dict) else {}
        repair_type = str(repair.get("type", "")).strip()
        if repair_type not in allowed:
            continue
        payload: dict[str, Any] = {}
        if repair_type == "create-directory":
            payload = {"parents": bool(repair.get("parents", True))}
        elif repair_type == "create-file":
            payload = {"content": str(repair.get("content", "")), "encoding": "utf-8"}
        elif repair_type == "append-lines":
            payload = {"lines": [str(item) for item in repair.get("lines", []) if str(item).strip()]}
            if not payload["lines"]:
                continue
        else:
            continue
        proposal_id = _proposal_id(repair_type, path, payload)
        proposals.append({
            "id": proposal_id,
            "status": "PROPOSED",
            "type": repair_type,
            "target": path,
            "payload": payload,
            "reason": str(repair.get("reason", f"Restore required layout entry {path}")),
            "reversible": True,
            "requires_confirmation": True,
        })
    for raw in config.get("maintenance", {}).get("doctor", {}).get("repair_specs", []):
        if not isinstance(raw, dict):
            continue
        repair_type = str(raw.get("type", ""))
        target = str(raw.get("target", "")).strip()
        if repair_type not in allowed or not target:
            continue
        payload = {key: value for key, value in raw.items() if key not in {"id", "type", "target", "reason"}}
        proposal_id = str(raw.get("id", "")).strip() or _proposal_id(repair_type, target, payload)
        proposals.append({
            "id": proposal_id,
            "status": "PROPOSED",
            "type": repair_type,
            "target": target,
            "payload": payload,
            "reason": str(raw.get("reason", "Configured reversible repair")),
            "reversible": True,
            "requires_confirmation": True,
        })
    unique = {item["id"]: item for item in proposals}
    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "status": "PASS",
        "doctor_status": doctor["status"],
        "automatic_repairs_performed": False,
        "proposals": [unique[key] for key in sorted(unique)],
        "non_automated_problems": [item for item in doctor["problems"] if not any(proposal["target"] in item for proposal in unique.values())],
    }
    write_json(project_root / REMEDIATION_ROOT / "proposals.json", payload)
    return payload


def _load_proposals(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / REMEDIATION_ROOT / "proposals.json"
    if not path.is_file():
        raise RuntimeError("no Doctor remediation proposals exist; run `forge doctor --action propose` first")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Doctor remediation proposals are unreadable: {exc}") from exc
    return payload


def apply_remediation(project_root: Path, proposal_id: str, *, confirmed: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    if not confirmed:
        raise RuntimeError("Doctor remediation requires --confirm after reviewing the proposal")
    payload = _load_proposals(project_root)
    proposal = next((item for item in payload.get("proposals", []) if item.get("id") == proposal_id), None)
    if not proposal:
        raise RuntimeError(f"Doctor remediation proposal not found: {proposal_id}")
    target = (project_root / str(proposal["target"])).resolve()
    try:
        target.relative_to(project_root.parent.resolve())
    except ValueError as exc:
        raise RuntimeError("Doctor remediation target escapes the allowed workspace boundary") from exc
    transaction_id = utc_now().replace(":", "-") + "-" + proposal_id
    tx_root = project_root / REMEDIATION_ROOT / "transactions" / transaction_id
    tx_root.mkdir(parents=True, exist_ok=False)
    backup = tx_root / "backup"
    existed = target.exists()
    if existed:
        if target.is_dir():
            shutil.copytree(target, backup)
        else:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
    repair_type = str(proposal["type"])
    details: dict[str, Any] = {}
    try:
        if repair_type == "create-directory":
            target.mkdir(parents=bool(proposal.get("payload", {}).get("parents", True)), exist_ok=True)
            details = {"created": not existed, "kind": "directory"}
        elif repair_type == "create-file":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(proposal.get("payload", {}).get("content", "")), encoding="utf-8")
            details = {"created": not existed, "kind": "file"}
        elif repair_type == "append-lines":
            lines = [str(item) for item in proposal.get("payload", {}).get("lines", [])]
            target.parent.mkdir(parents=True, exist_ok=True)
            current = target.read_text(encoding="utf-8") if target.is_file() else ""
            existing_lines = set(current.splitlines())
            additions = [line for line in lines if line not in existing_lines]
            with target.open("a", encoding="utf-8") as handle:
                if current and not current.endswith("\n") and additions:
                    handle.write("\n")
                for line in additions:
                    handle.write(line + "\n")
            details = {"added_lines": additions, "kind": "file"}
        else:
            raise RuntimeError(f"unsupported Doctor remediation type: {repair_type}")
        status = "PASS"
        reason = ""
    except Exception as exc:
        status = "FAIL"
        reason = str(exc)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        if existed and backup.exists():
            if backup.is_dir():
                shutil.copytree(backup, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
    transaction = {
        "schema": 1,
        "status": status,
        "transaction_id": transaction_id,
        "proposal": proposal,
        "target": str(target),
        "target_relative": str(proposal["target"]),
        "existed_before": existed,
        "backup": str(backup) if existed else "",
        "details": details,
        "reason": reason,
        "applied_utc": utc_now(),
    }
    write_json(tx_root / "transaction.json", transaction)
    return transaction


def rollback_remediation(project_root: Path, transaction_id: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    tx_root = project_root / REMEDIATION_ROOT / "transactions" / transaction_id
    tx_path = tx_root / "transaction.json"
    if not tx_path.is_file():
        raise RuntimeError(f"Doctor remediation transaction not found: {transaction_id}")
    transaction = json.loads(tx_path.read_text(encoding="utf-8"))
    target = Path(str(transaction["target"]))
    backup = Path(str(transaction.get("backup", ""))) if transaction.get("backup") else None
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    if transaction.get("existed_before"):
        if backup is None or not backup.exists():
            raise RuntimeError("Doctor remediation backup is missing")
        if backup.is_dir():
            shutil.copytree(backup, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
    payload = {
        "schema": 1,
        "status": "PASS",
        "action": "rollback",
        "transaction_id": transaction_id,
        "target": str(target),
        "restored_previous": bool(transaction.get("existed_before")),
        "rolled_back_utc": utc_now(),
    }
    write_json(tx_root / "rollback.json", payload)
    return payload


def remediation_action(project_root: Path, forge_root: Path, config: dict[str, Any], *, action: str, proposal_id: str = "", transaction_id: str = "", confirmed: bool = False) -> dict[str, Any]:
    if action == "inspect":
        return run_doctor(project_root, forge_root, config, write=True)
    if action == "propose":
        return propose_remediations(project_root, forge_root, config)
    if action == "apply":
        if not proposal_id:
            raise ValueError("doctor --action apply requires --id <proposal-id>")
        return apply_remediation(project_root, proposal_id, confirmed=confirmed)
    if action == "rollback":
        if not transaction_id:
            raise ValueError("doctor --action rollback requires --transaction <transaction-id>")
        return rollback_remediation(project_root, transaction_id)
    if action == "list":
        return _load_proposals(project_root)
    raise ValueError(f"unsupported Doctor action: {action}")

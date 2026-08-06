from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import save_config
from .graph import build_graph, load_graph
from .utils import normalize_rel, utc_now, write_json

SUPPORTED_KINDS = {"file_exists", "file_not_exists", "file_nonempty", "file_contains", "file_not_contains", "json_value", "graph_node", "command", "manual"}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "defect"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read learning input {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("learning input must be a JSON object")
    return data


def _learning_paths(project_root: Path, config: dict[str, Any]) -> dict[str, Path]:
    learn = config.get("learn", {})
    proposals = project_root / learn.get("proposals_dir", ".forge/learn/proposals")
    contracts = project_root / learn.get("contracts_path", ".forge/policies/learned-contracts.json")
    return {"proposals": proposals, "contracts": contracts, "manual": project_root / ".forge/LEARNED-MANUAL-CHECKLIST.md"}


def _normalize_regression(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"kind": "manual", "instructions": "Define a durable automated regression before relying on this learning as a gate."}
    if not isinstance(raw, dict):
        raise ValueError("regression must be an object")
    kind = str(raw.get("kind", "manual")).strip().lower()
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"regression.kind must be one of: {', '.join(sorted(SUPPORTED_KINDS))}")
    result: dict[str, Any] = {"kind": kind}
    if kind in {"file_exists", "file_not_exists", "file_nonempty", "file_contains", "file_not_contains", "json_value"}:
        path = normalize_rel(str(raw.get("path", "")))
        if not path:
            raise ValueError(f"regression {kind} requires path")
        result["path"] = path
    if kind in {"file_contains", "file_not_contains"}:
        text = str(raw.get("text", ""))
        if not text:
            raise ValueError(f"regression {kind} requires text")
        result["text"] = text
        result["regex"] = bool(raw.get("regex", False))
    elif kind == "json_value":
        key = str(raw.get("key", "")).strip()
        if not key:
            raise ValueError("regression json_value requires dotted key")
        result["key"] = key
        result["expected"] = raw.get("expected")
    elif kind == "graph_node":
        node_type = str(raw.get("node_type", "")).strip()
        if not node_type:
            raise ValueError("regression graph_node requires node_type")
        result.update({
            "node_type": node_type,
            "path": normalize_rel(str(raw.get("path", ""))),
            "name_contains": str(raw.get("name_contains", "")).strip(),
            "subsystem": str(raw.get("subsystem", "")).strip(),
        })
    elif kind == "command":
        command = raw.get("command")
        if not isinstance(command, list) or not command:
            raise ValueError("regression command requires a non-empty command array")
        result["command"] = [str(item) for item in command]
        result["timeout"] = int(raw.get("timeout", 300))
    elif kind == "manual":
        result["instructions"] = str(raw.get("instructions", "Review and verify the approved invariant."))
    return result


def propose_learning(project_root: Path, forge_root: Path, config: dict[str, Any], input_path: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    raw = _read_json(input_path)
    title = str(raw.get("title", "")).strip()
    invariant = str(raw.get("invariant") or raw.get("approved_behavior") or "").strip()
    if not title or not invariant:
        raise ValueError("learning input requires title and invariant (or approved_behavior)")
    severity = str(raw.get("severity", "error")).strip().lower()
    if severity not in {"info", "warning", "error", "blocker"}:
        raise ValueError("severity must be info, warning, error, or blocker")
    affected_paths = [normalize_rel(str(item)) for item in raw.get("affected_paths", []) if normalize_rel(str(item))]
    regression = _normalize_regression(raw.get("regression") or ({"kind": "command", "command": raw["verification_command"]} if isinstance(raw.get("verification_command"), list) else None))
    scope = str(raw.get("scope", "project")).strip().lower()
    if scope not in {"project", "reusable"}:
        raise ValueError("scope must be project or reusable")
    category = str(raw.get("category", "behavior")).strip().lower() or "behavior"
    fingerprint = hashlib.sha256(json.dumps({"invariant": invariant, "regression": regression, "scope": scope}, sort_keys=True).encode()).hexdigest()
    proposal_id = f"learn-{_slug(title)}-{fingerprint[:8]}"

    graph = load_graph(project_root, config)
    if graph is None:
        graph = build_graph(project_root, forge_root, config, write=True)
    affected_set = set(affected_paths)
    subsystems = sorted({node.get("subsystem", "") for node in graph.get("nodes", []) if node.get("path") in affected_set and node.get("subsystem")})
    gate = str(raw.get("gate", "")).strip().lower()
    if gate not in {"quick", "section", "release"}:
        gate = "release" if severity == "blocker" or category in {"security", "migration", "deployment"} else "section" if severity == "error" else "quick"
    automation_status = "ready" if regression["kind"] != "manual" else "needs-human-rule"
    proposal = {
        "schema": 1,
        "id": proposal_id,
        "status": "proposed",
        "created_utc": utc_now(),
        "title": title,
        "invariant": invariant,
        "symptom": str(raw.get("symptom", "")).strip(),
        "root_cause": str(raw.get("root_cause", "")).strip(),
        "fix": str(raw.get("fix", "")).strip(),
        "severity": severity,
        "category": category,
        "scope": scope,
        "affected_paths": affected_paths,
        "affected_subsystems": subsystems,
        "recommended_gate": gate,
        "regression": regression,
        "automation_status": automation_status,
        "fingerprint": fingerprint,
        "notes": str(raw.get("notes", "")).strip(),
    }
    paths = _learning_paths(project_root, config)
    proposal_path = paths["proposals"] / f"{proposal_id}.json"
    write_json(proposal_path, proposal)
    _write_proposal_markdown(proposal_path.with_suffix(".md"), proposal)
    return {"status": "PROPOSED", "proposal": proposal, "path": str(proposal_path)}


def _write_proposal_markdown(path: Path, proposal: dict[str, Any]) -> None:
    regression = proposal["regression"]
    lines = [
        f"# {proposal['title']}", "",
        f"- Proposal ID: `{proposal['id']}`",
        f"- Status: {proposal['status']}",
        f"- Scope: {proposal['scope']}",
        f"- Severity: {proposal['severity']}",
        f"- Recommended gate: {proposal['recommended_gate']}",
        f"- Automation: {proposal['automation_status']}", "",
        "## Invariant", "", proposal["invariant"], "",
        "## Evidence", "",
        f"- Symptom: {proposal['symptom'] or 'not supplied'}",
        f"- Root cause: {proposal['root_cause'] or 'not supplied'}",
        f"- Fix: {proposal['fix'] or 'not supplied'}",
        f"- Affected paths: {', '.join(proposal['affected_paths']) or 'not supplied'}",
        f"- Affected subsystems: {', '.join(proposal['affected_subsystems']) or 'not mapped'}", "",
        "## Proposed regression", "",
        "```json", json.dumps(regression, indent=2), "```", "",
        "Review and edit the JSON proposal before approval. Forge never activates a proposed regression automatically.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _load_contracts(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": 1, "updated_utc": utc_now(), "contracts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read learned contracts: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("contracts"), list):
        raise RuntimeError("learned contracts file is malformed")
    return data


def approve_learning(project_root: Path, config: dict[str, Any], proposal_id: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = _learning_paths(project_root, config)
    proposal_path = paths["proposals"] / f"{proposal_id}.json"
    proposal = _read_json(proposal_path)
    if proposal.get("status") not in {"proposed", "approved"}:
        raise RuntimeError(f"proposal {proposal_id} cannot be approved from status {proposal.get('status')}")
    contracts = _load_contracts(paths["contracts"])
    existing = next((item for item in contracts["contracts"] if item.get("fingerprint") == proposal.get("fingerprint")), None)
    if existing:
        return {"status": "DUPLICATE", "contract": existing, "contracts_path": str(paths["contracts"])}

    regression = proposal["regression"]
    contract = {
        "id": proposal["id"],
        "title": proposal["title"],
        "invariant": proposal["invariant"],
        "severity": proposal["severity"],
        "category": proposal["category"],
        "scope": proposal["scope"],
        "affected_paths": proposal["affected_paths"],
        "affected_subsystems": proposal.get("affected_subsystems", []),
        "gate": proposal["recommended_gate"],
        "regression": regression,
        "fingerprint": proposal["fingerprint"],
        "approved_utc": utc_now(),
        "status": "active",
        "active": True,
        "lifecycle": [{"utc": utc_now(), "from": "proposed", "to": "active", "reason": "approved"}],
        "superseded_by": "",
    }
    contracts["contracts"].append(contract)
    contracts["updated_utc"] = utc_now()
    write_json(paths["contracts"], contracts)

    if regression["kind"] == "command":
        gate = contract["gate"]
        commands = config.setdefault("commands", {}).setdefault(gate, [])
        check_id = f"learn.{_slug(proposal['title'])}.{proposal['fingerprint'][:8]}"
        if not any(item.get("id") == check_id for item in commands if isinstance(item, dict)):
            commands.append({"id": check_id, "command": regression["command"], "timeout": regression.get("timeout", 300), "learned_contract": proposal["id"]})
        save_config(project_root, config)
    elif regression["kind"] == "manual":
        _write_manual_checklist(paths["manual"], contracts["contracts"])

    proposal["status"] = "approved"
    proposal["approved_utc"] = contract["approved_utc"]
    write_json(proposal_path, proposal)
    _write_proposal_markdown(proposal_path.with_suffix(".md"), proposal)
    return {"status": "APPROVED", "contract": contract, "contracts_path": str(paths["contracts"])}


def reject_learning(project_root: Path, config: dict[str, Any], proposal_id: str, reason: str = "") -> dict[str, Any]:
    path = _learning_paths(project_root, config)["proposals"] / f"{proposal_id}.json"
    proposal = _read_json(path)
    proposal["status"] = "rejected"
    proposal["rejected_utc"] = utc_now()
    proposal["rejection_reason"] = reason.strip()
    write_json(path, proposal)
    _write_proposal_markdown(path.with_suffix(".md"), proposal)
    return {"status": "REJECTED", "proposal": proposal}


def list_learning(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    paths = _learning_paths(project_root, config)
    proposals: list[dict[str, Any]] = []
    if paths["proposals"].is_dir():
        for path in sorted(paths["proposals"].glob("*.json")):
            try:
                proposals.append(_read_json(path))
            except RuntimeError:
                continue
    contracts = _load_contracts(paths["contracts"])
    return {"status": "PASS", "proposals": proposals, "contracts": contracts["contracts"]}


def evaluate_contracts(project_root: Path, forge_root: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    paths = _learning_paths(project_root, config)
    contracts = _load_contracts(paths["contracts"])
    findings: list[dict[str, str]] = []
    graph: dict[str, Any] | None = None
    for contract in contracts["contracts"]:
        if not contract.get("active", True):
            continue
        regression = contract.get("regression", {})
        kind = regression.get("kind")
        if kind in {"command", "manual"}:
            continue
        if kind == "graph_node" and graph is None:
            graph = load_graph(project_root, config) or build_graph(project_root, forge_root, config, write=True)
        ok, message, path = _evaluate_regression(project_root, forge_root, config, regression, graph)
        if not ok:
            findings.append({
                "check_id": f"learn.contract.{contract['id']}",
                "severity": contract.get("severity", "error"),
                "category": f"learned:{contract.get('category', 'behavior')}",
                "path": path,
                "message": f"Learned invariant violated: {contract.get('invariant', contract.get('title', ''))}. {message}",
            })
    return findings


def _evaluate_regression(project_root: Path, forge_root: Path, config: dict[str, Any], regression: dict[str, Any], graph: dict[str, Any] | None) -> tuple[bool, str, str]:
    kind = regression.get("kind")
    path_value = normalize_rel(str(regression.get("path", "")))
    candidate = project_root / path_value if path_value else project_root
    if kind == "file_exists":
        return candidate.is_file(), "Required file is missing." if not candidate.is_file() else "", path_value
    if kind == "file_not_exists":
        return not candidate.exists(), "Forbidden file or path exists." if candidate.exists() else "", path_value
    if kind == "file_nonempty":
        if not candidate.is_file():
            return False, "Required non-empty file is missing.", path_value
        return candidate.stat().st_size > 0, "File exists but is zero bytes.", path_value
    if kind in {"file_contains", "file_not_contains"}:
        if not candidate.is_file():
            return False, "Target file is missing.", path_value
        text = candidate.read_text(encoding="utf-8", errors="replace")
        needle = str(regression.get("text", ""))
        if regression.get("regex"):
            try:
                present = re.search(needle, text, flags=re.M) is not None
            except re.error as exc:
                return False, f"Contract regex is invalid: {exc}", path_value
        else:
            present = needle in text
        ok = present if kind == "file_contains" else not present
        return ok, "Expected content was not found." if kind == "file_contains" else "Forbidden content is present.", path_value
    if kind == "json_value":
        if not candidate.is_file():
            return False, "JSON target file is missing.", path_value
        try:
            value: Any = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return False, f"Could not read JSON: {exc}", path_value
        for part in str(regression.get("key", "")).split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return False, f"JSON key {regression.get('key')} is missing.", path_value
        expected = regression.get("expected")
        return value == expected, f"JSON value is {value!r}, expected {expected!r}.", path_value
    if kind == "graph_node":
        graph = graph or load_graph(project_root, config) or build_graph(project_root, forge_root, config, write=True)
        for node in graph.get("nodes", []):
            if node.get("type") != regression.get("node_type"):
                continue
            if path_value and node.get("path") != path_value:
                continue
            if regression.get("name_contains") and regression["name_contains"].lower() not in str(node.get("name", "")).lower():
                continue
            if regression.get("subsystem") and node.get("subsystem") != regression["subsystem"]:
                continue
            return True, "", path_value
        return False, "Required architecture node was not found in Forge Graph.", path_value
    return True, "", path_value


def _write_manual_checklist(path: Path, contracts: list[dict[str, Any]]) -> None:
    manual = [item for item in contracts if item.get("active", True) and item.get("regression", {}).get("kind") == "manual"]
    lines = ["# Learned Manual Verification", "", "These approved invariants could not yet be reduced to an automated contract.", ""]
    for contract in manual:
        lines.extend([
            f"- [ ] **{contract['title']}** — {contract['invariant']}",
            f"  - Instructions: {contract['regression'].get('instructions', 'Verify the invariant.')}",
            f"  - Gate: {contract.get('gate', 'release')}",
        ])
    if not manual:
        lines.append("No manual learned contracts are active.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

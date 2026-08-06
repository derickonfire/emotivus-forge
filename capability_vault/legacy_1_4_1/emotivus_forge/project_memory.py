from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from .brief import build_brief
from .graph import analyze_impact, build_graph, load_graph
from .utils import normalize_rel, tree_fingerprint, utc_now, write_json

PLAN_STATUSES = {"draft", "active", "paused", "complete", "superseded", "cancelled"}
LEDGER_TYPES = {"decision", "requirement", "defect", "limitation", "integration", "release", "artifact", "standard", "note"}
LEDGER_STATUSES = {"pending", "active", "accepted", "resolved", "rejected", "suspended", "superseded", "retired"}
PIVOT_STATUSES = {"proposed", "assessed", "active", "complete", "cancelled", "superseded"}
PIVOT_DISPOSITIONS = {"review", "retain", "revise", "suspend", "replace", "retire", "restore", "supersede"}
CONTEXT_MODES = {"cold", "task", "subsystem", "failure", "release", "pivot"}
CONTEXT_BUDGETS = {"compact", "standard", "full"}

PROJECT_MODES = {"exploration", "transition", "development", "release"}
OBLIGATION_KINDS = {
    "behavior", "implementation", "architecture", "security", "data", "privacy",
    "accessibility", "compatibility", "performance", "efficiency", "user_experience",
    "maintainability", "integration", "standard", "other",
}
OBLIGATION_STABILITIES = {"enduring", "architecture-bound", "temporary", "experimental"}

QUALITY_DIMENSIONS = (
    "security", "reliability", "performance", "efficiency", "accessibility",
    "user_experience", "maintainability", "compatibility", "privacy",
)


def _memory_config(config: dict[str, Any]) -> dict[str, Any]:
    memory = config.setdefault("project_memory", {})
    memory.setdefault("root", ".forge/project")
    memory.setdefault("mode", "development")
    memory.setdefault("scope", {"coding_allowed": True, "source": "", "reason": ""})
    context = memory.setdefault("context", {})
    context.setdefault("default_budget", "standard")
    context.setdefault("token_budgets", {"compact": 1200, "standard": 3000, "full": 8000})
    context.setdefault("output_dir", ".forge/context")
    traceability = memory.setdefault("traceability", {})
    traceability.setdefault("release_requires_active_plan", False)
    traceability.setdefault("accepted_artifacts_require_canonical_ref", True)
    traceability.setdefault("release_requires_quality_coverage", True)
    pivot = memory.setdefault("pivot", {})
    pivot.setdefault("require_release_gate_on_complete", True)
    pivot.setdefault("checkpoint_profile_order", ["release", "section", "quick"])
    pivot.setdefault("allowed_modes", ["exploration", "transition", "development", "release"])
    pivot.setdefault("default_entry_mode", "exploration")
    return memory


def _paths(project_root: Path, config: dict[str, Any]) -> dict[str, Path]:
    memory = _memory_config(config)
    root = project_root / str(memory.get("root", ".forge/project"))
    context_dir = project_root / str(memory.get("context", {}).get("output_dir", ".forge/context"))
    return {
        "root": root,
        "plans": root / "plans.json",
        "ledger": root / "ledger.json",
        "pivots": root / "pivots.json",
        "context": context_dir,
        "checkpoint": root / "pivot-checkpoints",
    }


def _default_store(kind: str) -> dict[str, Any]:
    base: dict[str, Any] = {"schema": 1, "updated_utc": utc_now()}
    if kind == "plans":
        base.update({"active_id": "", "plans": []})
    elif kind == "ledger":
        base.update({"entries": []})
    elif kind == "pivots":
        base.update({"active_id": "", "pivots": []})
    else:
        raise ValueError(f"unsupported project-memory store: {kind}")
    return base


def _load_store(path: Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        return _default_store(kind)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read project-memory store {path}: {exc}") from exc
    key = {"plans": "plans", "ledger": "entries", "pivots": "pivots"}[kind]
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get(key), list):
        raise RuntimeError(f"project-memory store is malformed: {path}")
    return data


def _save_store(path: Path, data: dict[str, Any]) -> None:
    data["updated_utc"] = utc_now()
    write_json(path, data)


def initialize_project_memory(project_root: Path, config: dict[str, Any]) -> dict[str, str]:
    project_root = project_root.resolve()
    paths = _paths(project_root, config)
    for key in ("plans", "ledger", "pivots"):
        path = paths[key]
        if not path.is_file():
            _save_store(path, _default_store(key))
    paths["context"].mkdir(parents=True, exist_ok=True)
    paths["checkpoint"].mkdir(parents=True, exist_ok=True)
    return {key: str(value) for key, value in paths.items()}


def _read_input(input_path: Path | None) -> dict[str, Any]:
    if input_path is None:
        raise ValueError("this action requires --input <file.json>")
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read input JSON {input_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("input JSON must be an object")
    return data


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "record"


def _id(prefix: str, title: str) -> str:
    stamp = utc_now().replace("-", "").replace(":", "").replace("+00:00", "Z")
    digest = hashlib.sha256(f"{prefix}\0{title}\0{stamp}".encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{stamp[:15]}-{digest}"


def _strings(value: Any, *, paths: bool = False) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("expected an array of strings")
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if paths:
            text = normalize_rel(text)
        if text and text not in result:
            result.append(text)
    return result


def _find(items: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    item = next((candidate for candidate in items if candidate.get("id") == item_id), None)
    if item is None:
        raise RuntimeError(f"project-memory item was not found: {item_id}")
    return item


def _quality_targets(value: Any) -> dict[str, str]:
    """Normalize broad quality intent without freezing one implementation or standard."""
    defaults = {name: "assess-and-improve" for name in QUALITY_DIMENSIONS}
    if value is None:
        return defaults
    if not isinstance(value, dict):
        raise ValueError("quality_targets must be an object")
    for raw_name, raw_target in value.items():
        name = re.sub(r"[^a-z0-9_]+", "_", str(raw_name).strip().lower()).strip("_")
        target = str(raw_target).strip()
        if not name or not target:
            raise ValueError("quality_targets keys and values must be non-empty")
        defaults[name] = target[:240]
    return defaults


def _quality_evidence(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("quality_evidence must be an object")
    result: dict[str, list[str]] = {}
    for raw_name, raw_items in value.items():
        name = re.sub(r"[^a-z0-9_]+", "_", str(raw_name).strip().lower()).strip("_")
        if not name:
            raise ValueError("quality_evidence keys must be non-empty")
        result[name] = _strings(raw_items)
    return result


def _quality_coverage(targets: dict[str, str], evidence: dict[str, list[str]]) -> dict[str, Any]:
    dimensions: dict[str, dict[str, Any]] = {}
    unresolved: list[str] = []
    for name, target in targets.items():
        normalized = str(target).strip().lower()
        refs = list(evidence.get(name, []))
        not_applicable = normalized in {"n/a", "na", "not-applicable", "not applicable", "none"}
        status = "not-applicable" if not_applicable else "covered" if refs else "unresolved"
        if status == "unresolved":
            unresolved.append(name)
        dimensions[name] = {"target": target, "status": status, "evidence": refs}
    return {
        "status": "covered" if not unresolved else "gaps",
        "dimensions": dimensions,
        "unresolved": unresolved,
        "covered_count": sum(1 for item in dimensions.values() if item["status"] == "covered"),
        "not_applicable_count": sum(1 for item in dimensions.values() if item["status"] == "not-applicable"),
    }


def _standard_ref_map(ledger_entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in ledger_entries if item.get("type") == "standard"}


def plan_action(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    action: str,
    input_path: Path | None = None,
    item_id: str = "",
    reason: str = "",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = _paths(project_root, config)
    store = _load_store(paths["plans"], "plans")
    plans = store["plans"]

    if action == "list":
        return {"status": "PASS", "active_id": store.get("active_id", ""), "plans": plans}
    if action == "show":
        if not item_id:
            raise ValueError("project plan --action show requires --id")
        return {"status": "PASS", "plan": _find(plans, item_id)}
    if action == "create":
        raw = _read_input(input_path)
        title = str(raw.get("title", "")).strip()
        objective = str(raw.get("objective", "")).strip()
        if not title or not objective:
            raise ValueError("a project plan requires title and objective")
        changed_paths = _strings(raw.get("changed_paths", raw.get("expected_files", [])), paths=True)
        impact: dict[str, Any] = {}
        if changed_paths:
            impact_payload = analyze_impact(project_root, forge_root, config, changed_paths, write=True)
            impact = {
                "risk": impact_payload.get("risk", {}),
                "impacted_node_count": len(impact_payload.get("impacted_nodes", [])),
                "targeted_tests": impact_payload.get("targeted_tests", []),
                "recommended_live_checks": impact_payload.get("recommended_live_checks", []),
            }
        quality_targets = _quality_targets(raw.get("quality_targets"))
        quality_evidence = _quality_evidence(raw.get("quality_evidence"))
        plan_id = _id("PLAN", title)
        plan = {
            "id": plan_id,
            "title": title,
            "objective": objective,
            "status": "draft",
            "created_utc": utc_now(),
            "updated_utc": utc_now(),
            "scope": _strings(raw.get("scope")),
            "out_of_scope": _strings(raw.get("out_of_scope")),
            "expected_files": _strings(raw.get("expected_files"), paths=True),
            "changed_paths": changed_paths,
            "tests": _strings(raw.get("tests")),
            "labs": _strings(raw.get("labs")),
            "migrations": _strings(raw.get("migrations"), paths=True),
            "release_evidence": _strings(raw.get("release_evidence")),
            "completion_criteria": _strings(raw.get("completion_criteria")),
            "source_refs": _strings(raw.get("source_refs"), paths=True),
            "decision_refs": _strings(raw.get("decision_refs")),
            "contract_refs": _strings(raw.get("contract_refs")),
            "work_type": str(raw.get("work_type", config.get("work", {}).get("mode", "development"))).strip().lower(),
            "quality_targets": quality_targets,
            "quality_evidence": quality_evidence,
            "quality_coverage": _quality_coverage(quality_targets, quality_evidence),
            "standards_refs": _strings(raw.get("standards_refs")),
            "quality_exceptions": _strings(raw.get("quality_exceptions")),
            "impact": impact,
            "notes": str(raw.get("notes", "")).strip(),
            "history": [{"status": "draft", "utc": utc_now(), "reason": "created"}],
        }
        plans.append(plan)
        _save_store(paths["plans"], store)
        return {"status": "CREATED", "plan": plan, "path": str(paths["plans"])}

    if action == "update":
        if not item_id:
            raise ValueError("project plan --action update requires --id")
        raw = _read_input(input_path)
        plan = _find(plans, item_id)
        scalar_fields = ("title", "objective", "notes", "work_type")
        list_fields = ("scope", "out_of_scope", "tests", "labs", "release_evidence", "completion_criteria", "decision_refs", "contract_refs", "standards_refs", "quality_exceptions")
        path_fields = ("expected_files", "changed_paths", "migrations", "source_refs")
        for field in scalar_fields:
            if field in raw:
                value = str(raw.get(field, "")).strip()
                if field in {"title", "objective"} and not value:
                    raise ValueError(f"plan {field} cannot be empty")
                plan[field] = value
        for field in list_fields:
            if field in raw:
                plan[field] = _strings(raw.get(field))
        for field in path_fields:
            if field in raw:
                plan[field] = _strings(raw.get(field), paths=True)
        if "quality_targets" in raw:
            plan["quality_targets"] = _quality_targets(raw.get("quality_targets"))
        if "quality_evidence" in raw:
            plan["quality_evidence"] = _quality_evidence(raw.get("quality_evidence"))
        plan["quality_coverage"] = _quality_coverage(plan.get("quality_targets", {}), plan.get("quality_evidence", {}))
        plan["updated_utc"] = utc_now()
        plan.setdefault("history", []).append({"status": plan.get("status", "draft"), "utc": utc_now(), "reason": reason.strip() or "updated"})
        _save_store(paths["plans"], store)
        return {"status": "UPDATED", "plan": plan}

    if not item_id:
        raise ValueError(f"project plan --action {action} requires --id")
    plan = _find(plans, item_id)
    if action == "activate":
        coding_allowed = bool(config.get("work", {}).get("coding_allowed", config.get("project_memory", {}).get("scope", {}).get("coding_allowed", True)))
        work_type = str(plan.get("work_type", "development"))
        if not coding_allowed and work_type in {"development", "feature", "refactor", "pivot"}:
            source = config.get("work", {}).get("scope_source", "")
            raise RuntimeError(f"active scope does not approve coding work; create an acceptance/operations plan or update the canonical scope first{f' ({source})' if source else ''}")
        previous_id = str(store.get("active_id", ""))
        if previous_id and previous_id != item_id:
            previous = _find(plans, previous_id)
            if previous.get("status") == "active":
                previous["status"] = "paused"
                previous.setdefault("history", []).append({"status": "paused", "utc": utc_now(), "reason": f"replaced by {item_id}"})
        plan["status"] = "active"
        store["active_id"] = item_id
    elif action == "complete":
        coverage = plan.get("quality_coverage") or _quality_coverage(plan.get("quality_targets", {}), plan.get("quality_evidence", {}))
        plan["quality_coverage"] = coverage
        if _memory_config(config).get("traceability", {}).get("release_requires_quality_coverage", True) and coverage.get("unresolved"):
            raise RuntimeError("plan cannot complete while quality coverage gaps remain: " + ", ".join(coverage["unresolved"]))
        if not plan.get("completion_criteria"):
            raise RuntimeError("plan cannot complete without declared completion criteria")
        plan["status"] = "complete"
        if store.get("active_id") == item_id:
            store["active_id"] = ""
    elif action == "supersede":
        plan["status"] = "superseded"
        plan["superseded_reason"] = reason.strip()
        if store.get("active_id") == item_id:
            store["active_id"] = ""
    elif action == "cancel":
        plan["status"] = "cancelled"
        plan["cancelled_reason"] = reason.strip()
        if store.get("active_id") == item_id:
            store["active_id"] = ""
    else:
        raise ValueError(f"unsupported project plan action: {action}")
    plan["updated_utc"] = utc_now()
    plan.setdefault("history", []).append({"status": plan["status"], "utc": utc_now(), "reason": reason.strip()})
    _save_store(paths["plans"], store)
    return {"status": plan["status"].upper(), "plan": plan, "active_id": store.get("active_id", "")}


def ledger_action(
    project_root: Path,
    config: dict[str, Any],
    *,
    action: str,
    input_path: Path | None = None,
    item_id: str = "",
    reason: str = "",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = _paths(project_root, config)
    store = _load_store(paths["ledger"], "ledger")
    entries = store["entries"]
    if action == "list":
        return {"status": "PASS", "entries": entries}
    if action == "show":
        if not item_id:
            raise ValueError("project record --action show requires --id")
        return {"status": "PASS", "entry": _find(entries, item_id)}
    if action == "add":
        raw = _read_input(input_path)
        kind = str(raw.get("type", "decision")).strip().lower()
        if kind not in LEDGER_TYPES:
            raise ValueError("ledger type must be one of: " + ", ".join(sorted(LEDGER_TYPES)))
        title = str(raw.get("title", "")).strip()
        summary = str(raw.get("summary", raw.get("decision", ""))).strip()
        if not title or not summary:
            raise ValueError("a project record requires title and summary")
        status = str(raw.get("status", "pending" if kind == "artifact" else "active")).strip().lower()
        if status not in LEDGER_STATUSES:
            raise ValueError("unsupported ledger status")
        canonical_ref = normalize_rel(str(raw.get("canonical_ref", "")).strip())
        if kind == "artifact" and status in {"accepted", "active"} and config.get("project_memory", {}).get("traceability", {}).get("accepted_artifacts_require_canonical_ref", True) and not canonical_ref:
            raise ValueError("an accepted artifact record requires canonical_ref")
        if kind == "standard":
            required_standard = {
                "source": str(raw.get("source", "")).strip(),
                "version": str(raw.get("version", "")).strip(),
                "authority": str(raw.get("authority", "")).strip(),
                "reviewed_utc": str(raw.get("reviewed_utc", "")).strip(),
            }
            missing_standard = [key for key, value in required_standard.items() if not value]
            if not _strings(raw.get("scope")):
                missing_standard.append("scope")
            if missing_standard:
                raise ValueError("a standard record requires: " + ", ".join(missing_standard))
        entry_id = _id(kind.upper()[:4], title)
        entry = {
            "id": entry_id,
            "type": kind,
            "title": title,
            "summary": summary,
            "status": status,
            "created_utc": utc_now(),
            "updated_utc": utc_now(),
            "reason": str(raw.get("reason", "")).strip(),
            "source_refs": _strings(raw.get("source_refs"), paths=True),
            "canonical_ref": canonical_ref,
            "applies_to": _strings(raw.get("applies_to"), paths=True),
            "tags": _strings(raw.get("tags")),
            "evidence": _strings(raw.get("evidence"), paths=True),
            "standard": {
                "source": str(raw.get("source", "")).strip(),
                "version": str(raw.get("version", "")).strip(),
                "authority": str(raw.get("authority", "")).strip(),
                "scope": _strings(raw.get("scope")),
                "reviewed_utc": str(raw.get("reviewed_utc", "")).strip(),
                "review_due": str(raw.get("review_due", "")).strip(),
                "replacement_history": _strings(raw.get("replacement_history")),
            } if kind == "standard" else {},
            "supersedes": _strings(raw.get("supersedes")),
            "superseded_by": "",
            "history": [{"status": status, "utc": utc_now(), "reason": "created"}],
        }
        for old_id in entry["supersedes"]:
            old = _find(entries, old_id)
            old["status"] = "superseded"
            old["superseded_by"] = entry_id
            old["updated_utc"] = utc_now()
            old.setdefault("history", []).append({"status": "superseded", "utc": utc_now(), "reason": f"superseded by {entry_id}"})
        entries.append(entry)
        _save_store(paths["ledger"], store)
        return {"status": "ADDED", "entry": entry, "path": str(paths["ledger"])}

    if not item_id:
        raise ValueError(f"project record --action {action} requires --id")
    entry = _find(entries, item_id)
    if action == "supersede":
        entry["status"] = "superseded"
        entry["superseded_reason"] = reason.strip()
    elif action == "retire":
        entry["status"] = "retired"
        entry["retired_reason"] = reason.strip()
    elif action == "resolve":
        entry["status"] = "resolved"
        entry["resolution"] = reason.strip()
    elif action == "accept":
        if entry.get("type") == "artifact" and config.get("project_memory", {}).get("traceability", {}).get("accepted_artifacts_require_canonical_ref", True) and not entry.get("canonical_ref"):
            raise ValueError("an artifact cannot be accepted until canonical_ref is recorded")
        entry["status"] = "accepted"
    elif action == "reject":
        entry["status"] = "rejected"
        entry["rejection_reason"] = reason.strip()
    else:
        raise ValueError(f"unsupported project record action: {action}")
    entry["updated_utc"] = utc_now()
    entry.setdefault("history", []).append({"status": entry["status"], "utc": utc_now(), "reason": reason.strip()})
    _save_store(paths["ledger"], store)
    return {"status": entry["status"].upper(), "entry": entry}


def _load_contracts(project_root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    path = project_root / config.get("learn", {}).get("contracts_path", ".forge/policies/learned-contracts.json")
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("contracts", []) if isinstance(data, dict) else []
    return [item for item in values if isinstance(item, dict) and item.get("active", True)]


def _all_contract_store(project_root: Path, config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = project_root / config.get("learn", {}).get("contracts_path", ".forge/policies/learned-contracts.json")
    if not path.is_file():
        return path, {"schema": 1, "updated_utc": utc_now(), "contracts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read learned contracts for pivot: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("contracts"), list):
        raise RuntimeError("learned contracts store is malformed")
    return path, data


def _normalize_obligations(raw: dict[str, Any]) -> list[dict[str, Any]]:
    values = raw.get("obligations", [])
    if values is None:
        values = []
    if not isinstance(values, list):
        raise ValueError("pivot obligations must be an array")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if isinstance(item, str):
            item = {"title": item, "kind": "behavior", "stability": "enduring"}
        if not isinstance(item, dict):
            raise ValueError("each pivot obligation must be a string or object")
        title = str(item.get("title", item.get("obligation", ""))).strip()
        if not title:
            raise ValueError("each pivot obligation requires a title")
        kind = str(item.get("kind", "behavior")).strip().lower().replace("-", "_")
        stability = str(item.get("stability", "enduring")).strip().lower()
        if kind not in OBLIGATION_KINDS:
            raise ValueError("pivot obligation kind must be one of: " + ", ".join(sorted(OBLIGATION_KINDS)))
        if stability not in OBLIGATION_STABILITIES:
            raise ValueError("pivot obligation stability must be one of: " + ", ".join(sorted(OBLIGATION_STABILITIES)))
        obligation_id = str(item.get("id", "")).strip() or f"OBL-{index + 1:03d}-{_slug(title)}"
        normalized.append({
            "id": obligation_id,
            "title": title,
            "kind": kind,
            "stability": stability,
            "source_refs": _strings(item.get("source_refs"), paths=True),
            "applies_to": _strings(item.get("applies_to"), paths=True),
            "quality_dimensions": _strings(item.get("quality_dimensions")),
            "required_evidence": _strings(item.get("required_evidence")),
            "notes": str(item.get("notes", "")).strip(),
        })
    for title in _strings(raw.get("enduring_obligations")):
        if not any(item["title"] == title for item in normalized):
            normalized.append({
                "id": f"OBL-{len(normalized) + 1:03d}-{_slug(title)}", "title": title,
                "kind": "behavior", "stability": "enduring", "source_refs": [], "applies_to": [],
                "quality_dimensions": [], "required_evidence": [], "notes": "",
            })
    for title in _strings(raw.get("architecture_obligations")):
        if not any(item["title"] == title for item in normalized):
            normalized.append({
                "id": f"OBL-{len(normalized) + 1:03d}-{_slug(title)}", "title": title,
                "kind": "architecture", "stability": "architecture-bound", "source_refs": [], "applies_to": [],
                "quality_dimensions": [], "required_evidence": [], "notes": "",
            })
    return normalized


def _suggest_disposition(*, category: str = "", kind: str = "", stability: str = "") -> tuple[str, str]:
    category = category.lower()
    kind = kind.lower()
    stability = stability.lower()
    if stability in {"temporary", "experimental"} or kind in {"implementation", "architecture"}:
        return "retire", "The item appears tied to temporary or architecture-specific implementation. Review before retirement."
    if category in {"security", "migration", "deployment", "data", "privacy"} or kind in {"security", "data", "privacy"}:
        return "revise", "The obligation is likely enduring but may need replacement evidence under the new design."
    if kind in {"accessibility", "compatibility", "performance", "efficiency", "user_experience", "maintainability", "behavior", "standard"} or stability == "enduring":
        return "retain", "The item appears to protect an enduring product or quality outcome."
    return "review", "Forge cannot determine whether this item is enduring or implementation-bound."


def _normalize_disposition_value(value: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(value, str):
        disposition = value.strip().lower()
        detail: dict[str, Any] = {"disposition": disposition, "reason": "", "successor": "", "evidence": [], "accepted_loss": ""}
    elif isinstance(value, dict):
        disposition = str(value.get("disposition", value.get("action", "review"))).strip().lower()
        detail = {
            "disposition": disposition,
            "reason": str(value.get("reason", "")).strip(),
            "successor": str(value.get("successor", value.get("successor_ref", ""))).strip(),
            "evidence": _strings(value.get("evidence", value.get("replacement_evidence", []))),
            "accepted_loss": str(value.get("accepted_loss", "")).strip(),
        }
    else:
        raise ValueError("pivot disposition values must be strings or objects")
    if disposition not in PIVOT_DISPOSITIONS:
        raise ValueError("pivot disposition must be one of: " + ", ".join(sorted(PIVOT_DISPOSITIONS)))
    return disposition, detail


def _latest_green_report(project_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    reports = project_root / config.get("paths", {}).get("reports", ".forge/reports")
    order = _memory_config(config).get("pivot", {}).get("checkpoint_profile_order", ["release", "section", "quick"])
    for profile in order:
        candidate = reports / f"{profile}.json"
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") == "PASS":
            return {
                "profile": profile,
                "path": str(candidate.relative_to(project_root)),
                "updated_utc": payload.get("updated_utc", payload.get("finished_utc", "")),
                "tree_fingerprint": payload.get("tree_fingerprint", ""),
                "environment_fingerprint": payload.get("environment_fingerprint", ""),
            }
    return {}


def _write_pivot_checkpoint(
    project_root: Path, forge_root: Path, config: dict[str, Any], paths: dict[str, Path], pivot: dict[str, Any]
) -> dict[str, Any]:
    checkpoint_dir = paths["checkpoint"] / str(pivot["id"])
    if checkpoint_dir.exists():
        raise RuntimeError(f"pivot checkpoint already exists: {checkpoint_dir}")
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    contracts_path, _contracts = _all_contract_store(project_root, config)
    candidates = {
        "config": project_root / ".emotivus-forge.json",
        "plans": paths["plans"],
        "ledger": paths["ledger"],
        "contracts": contracts_path,
    }
    files: list[dict[str, Any]] = []
    for label, source in candidates.items():
        if not source.is_file():
            continue
        destination = checkpoint_dir / f"{label}{source.suffix or '.json'}"
        destination.write_bytes(source.read_bytes())
        files.append({
            "label": label,
            "source": str(source.relative_to(project_root)),
            "snapshot": str(destination.relative_to(project_root)),
            "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        })
    last_green = _latest_green_report(project_root, config)
    if last_green.get("path"):
        source = project_root / str(last_green["path"])
        destination = checkpoint_dir / "last-green.json"
        destination.write_bytes(source.read_bytes())
        files.append({
            "label": "last_green", "source": str(source.relative_to(project_root)),
            "snapshot": str(destination.relative_to(project_root)), "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        })
    checkpoint = {
        "schema": 2,
        "pivot_id": pivot["id"],
        "created_utc": utc_now(),
        "project_identity": config.get("project", {}).get("identity", ""),
        "source_tree_fingerprint": tree_fingerprint(project_root, config.get("paths", {}).get("exclude", []), forge_root),
        "last_green": last_green,
        "files": files,
        "source_restore_included": False,
        "source_restore_note": "Forge preserves assurance state and fingerprints. Product source must be preserved through source control or an internal Forge delivery.",
    }
    manifest = checkpoint_dir / "checkpoint.json"
    write_json(manifest, checkpoint)
    return {**checkpoint, "path": str(manifest.relative_to(project_root))}


def _restore_pivot_checkpoint(project_root: Path, pivot: dict[str, Any], config: dict[str, Any], *, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise RuntimeError("restoring pre-pivot assurance state requires --confirm")
    checkpoint_path = project_root / str(pivot.get("checkpoint", {}).get("path", ""))
    if not checkpoint_path.is_file():
        raise RuntimeError("pivot checkpoint manifest is missing")
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read pivot checkpoint: {exc}") from exc
    restored: list[str] = []
    for item in checkpoint.get("files", []):
        if item.get("label") == "last_green":
            continue
        snapshot = project_root / str(item.get("snapshot", ""))
        destination = project_root / str(item.get("source", ""))
        if not snapshot.is_file():
            raise RuntimeError(f"pivot checkpoint snapshot is missing: {snapshot}")
        actual = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        if actual != item.get("sha256"):
            raise RuntimeError(f"pivot checkpoint snapshot failed integrity verification: {snapshot}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = snapshot.read_bytes()
        destination.write_bytes(data)
        if item.get("label") == "config":
            restored_config = json.loads(data.decode("utf-8"))
            config.clear()
            config.update(restored_config)
        restored.append(str(destination.relative_to(project_root)))
    return {
        "status": "PASS", "restored": restored,
        "source_restored": False,
        "note": checkpoint.get("source_restore_note", "Product source is not restored by Forge Pivot."),
    }


def _pivot_readiness(project_root: Path, forge_root: Path, config: dict[str, Any], pivot: dict[str, Any], plans: dict[str, Any]) -> dict[str, Any]:
    disposition_maps = [pivot.get("contract_dispositions", {}), pivot.get("record_dispositions", {}), pivot.get("obligation_dispositions", {})]
    unresolved = sorted({key for mapping in disposition_maps for key, value in mapping.items() if value == "review"})
    details = pivot.get("disposition_details", {})
    missing_reasons: list[str] = []
    missing_successors: list[str] = []
    unknown_successors: list[str] = []
    missing_evidence: list[str] = []
    contract_path, contract_store = _all_contract_store(project_root, config)
    known_successors = {str(item.get("id")) for item in contract_store.get("contracts", [])}
    ledger_store = _load_store(_paths(project_root, config)["ledger"], "ledger")
    known_successors.update(str(item.get("id")) for item in ledger_store.get("entries", []))
    known_successors.update(str(item.get("id")) for item in pivot.get("obligations", []))
    for ref, disposition in {**pivot.get("contract_dispositions", {}), **pivot.get("record_dispositions", {}), **pivot.get("obligation_dispositions", {})}.items():
        detail = details.get(ref, {})
        if disposition in {"suspend", "retire", "supersede"} and not str(detail.get("reason", "")).strip():
            missing_reasons.append(ref)
        if disposition in {"replace", "supersede"}:
            successor = str(detail.get("successor", "")).strip()
            if not successor:
                missing_successors.append(ref)
            elif successor not in known_successors:
                unknown_successors.append(f"{ref}->{successor}")
        if disposition in {"revise", "replace"} and not list(detail.get("evidence", [])):
            missing_evidence.append(ref)
        if disposition == "retire" and not (str(detail.get("reason", "")).strip() or str(detail.get("accepted_loss", "")).strip()):
            missing_reasons.append(ref)
    plan = _active_plan(plans, str(pivot.get("transition_plan_id", "")))
    coverage = plan.get("quality_coverage", {}) if plan else {}
    quality_gaps = list(coverage.get("unresolved", [])) if plan else list(QUALITY_DIMENSIONS)
    release_gate = _latest_green_report(project_root, config)
    release_gate_pass = release_gate.get("profile") == "release"
    current_fingerprint = tree_fingerprint(project_root, config.get("paths", {}).get("exclude", []), forge_root)
    gate_matches_tree = bool(release_gate_pass and release_gate.get("tree_fingerprint") in {"", current_fingerprint})
    ready = not any((unresolved, missing_reasons, missing_successors, unknown_successors, missing_evidence, quality_gaps))
    if _memory_config(config).get("pivot", {}).get("require_release_gate_on_complete", True):
        ready = ready and gate_matches_tree
    ready = ready and _memory_config(config).get("mode") == "release"
    return {
        "ready": ready,
        "mode": _memory_config(config).get("mode"),
        "unresolved": unresolved,
        "missing_reasons": sorted(set(missing_reasons)),
        "missing_successors": sorted(set(missing_successors)),
        "unknown_successors": sorted(set(unknown_successors)),
        "missing_replacement_evidence": sorted(set(missing_evidence)),
        "quality_gaps": quality_gaps,
        "release_gate": release_gate,
        "release_gate_matches_tree": gate_matches_tree,
        "transition_plan_id": pivot.get("transition_plan_id", ""),
    }


def _create_pivot_plan(project_root: Path, forge_root: Path, config: dict[str, Any], paths: dict[str, Path], pivot: dict[str, Any]) -> str:
    plans = _load_store(paths["plans"], "plans")
    existing_id = str(pivot.get("transition_plan_id", ""))
    if existing_id:
        _find(plans["plans"], existing_id)
        return existing_id
    plan_id = _id("PLAN", f"Pivot: {pivot['title']}")
    quality_targets = _quality_targets(pivot.get("quality_targets"))
    quality_evidence = _quality_evidence(pivot.get("quality_evidence"))
    plan = {
        "id": plan_id, "title": f"Pivot: {pivot['title']}", "objective": pivot["objective"],
        "status": "active", "created_utc": utc_now(), "updated_utc": utc_now(),
        "scope": ["Controlled transition for pivot " + pivot["id"]],
        "out_of_scope": list(pivot.get("out_of_scope", [])),
        "expected_files": list(pivot.get("changed_paths", [])), "changed_paths": list(pivot.get("changed_paths", [])),
        "tests": list(pivot.get("tests", [])), "labs": list(pivot.get("labs", [])),
        "migrations": list(pivot.get("migration_paths", [])),
        "release_evidence": list(pivot.get("release_evidence", ["gate:release"])),
        "completion_criteria": list(pivot.get("completion_criteria", ["Every pivot obligation has a final disposition and required replacement evidence."])),
        "source_refs": list(pivot.get("source_refs", [])), "decision_refs": [], "contract_refs": [],
        "work_type": "pivot", "quality_targets": quality_targets, "quality_evidence": quality_evidence,
        "quality_coverage": _quality_coverage(quality_targets, quality_evidence),
        "standards_refs": list(pivot.get("standards_refs", [])), "quality_exceptions": list(pivot.get("quality_exceptions", [])),
        "impact": pivot.get("impact", {}), "notes": f"Generated by Forge Pivot {pivot['id']}.",
        "history": [{"status": "active", "utc": utc_now(), "reason": "generated and activated by pivot"}],
    }
    previous_id = str(plans.get("active_id", ""))
    if previous_id:
        previous = _find(plans["plans"], previous_id)
        if previous.get("status") == "active":
            previous["status"] = "paused"
            previous.setdefault("history", []).append({"status": "paused", "utc": utc_now(), "reason": f"pivot {pivot['id']} activated"})
    plans["plans"].append(plan)
    plans["active_id"] = plan_id
    _save_store(paths["plans"], plans)
    return plan_id


def _apply_pivot_dispositions(project_root: Path, config: dict[str, Any], paths: dict[str, Path], pivot: dict[str, Any]) -> dict[str, Any]:
    changed_contracts: list[str] = []
    changed_records: list[str] = []
    contract_path, contract_store = _all_contract_store(project_root, config)
    contracts = {str(item.get("id")): item for item in contract_store.get("contracts", [])}
    details = pivot.get("disposition_details", {})
    for ref, disposition in pivot.get("contract_dispositions", {}).items():
        contract = contracts.get(str(ref))
        if contract is None:
            continue
        detail = details.get(ref, {})
        old_status = str(contract.get("status", "active" if contract.get("active", True) else "suspended"))
        if disposition == "retain":
            new_status, active = "active", True
        elif disposition == "restore":
            new_status, active = "active", True
        elif disposition == "suspend":
            new_status, active = "suspended", False
        elif disposition == "retire":
            new_status, active = "retired", False
        elif disposition in {"replace", "supersede"}:
            new_status, active = "superseded", False
        else:  # revise
            new_status, active = "active", True
        contract["status"] = new_status
        contract["active"] = active
        contract.setdefault("lifecycle", []).append({
            "pivot_id": pivot["id"], "utc": utc_now(), "from": old_status, "to": new_status,
            "disposition": disposition, "reason": detail.get("reason", ""),
            "successor": detail.get("successor", ""), "evidence": detail.get("evidence", []),
            "accepted_loss": detail.get("accepted_loss", ""),
        })
        if detail.get("successor"):
            contract["superseded_by"] = detail["successor"]
        changed_contracts.append(ref)
    if changed_contracts:
        contract_store["updated_utc"] = utc_now()
        write_json(contract_path, contract_store)

    ledger = _load_store(paths["ledger"], "ledger")
    records = {str(item.get("id")): item for item in ledger.get("entries", [])}
    for ref, disposition in pivot.get("record_dispositions", {}).items():
        record = records.get(str(ref))
        if record is None:
            continue
        detail = details.get(ref, {})
        old_status = str(record.get("status", "active"))
        mapping = {
            "retain": old_status if old_status not in {"suspended", "retired", "superseded"} else "active",
            "restore": "active", "suspend": "suspended", "retire": "retired",
            "replace": "superseded", "supersede": "superseded", "revise": "active",
        }
        record["status"] = mapping[disposition]
        if detail.get("successor"):
            record["superseded_by"] = detail["successor"]
        record.setdefault("history", []).append({
            "status": record["status"], "utc": utc_now(), "reason": detail.get("reason", ""),
            "pivot_id": pivot["id"], "disposition": disposition, "successor": detail.get("successor", ""),
            "evidence": detail.get("evidence", []), "previous_status": old_status,
        })
        record["updated_utc"] = utc_now()
        changed_records.append(ref)
    if changed_records:
        _save_store(paths["ledger"], ledger)
    return {"contracts": changed_contracts, "records": changed_records}


def pivot_action(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    action: str,
    input_path: Path | None = None,
    item_id: str = "",
    reason: str = "",
    mode: str = "",
    confirmed: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = _paths(project_root, config)
    store = _load_store(paths["pivots"], "pivots")
    pivots = store["pivots"]
    if action == "list":
        return {"status": "PASS", "active_id": store.get("active_id", ""), "mode": _memory_config(config).get("mode"), "pivots": pivots}
    if action == "show":
        if not item_id:
            raise ValueError("project pivot --action show requires --id")
        pivot = _find(pivots, item_id)
        plans = _load_store(paths["plans"], "plans")
        return {"status": "PASS", "pivot": pivot, "readiness": _pivot_readiness(project_root, forge_root, config, pivot, plans)}
    if action == "create":
        raw = _read_input(input_path)
        title = str(raw.get("title", "")).strip()
        objective = str(raw.get("objective", "")).strip()
        if not title or not objective:
            raise ValueError("a pivot requires title and objective")
        entry_mode = str(raw.get("entry_mode", _memory_config(config).get("pivot", {}).get("default_entry_mode", "exploration"))).strip().lower()
        if entry_mode not in PROJECT_MODES - {"release"}:
            raise ValueError("pivot entry_mode must be exploration, transition, or development")
        pivot_id = _id("PIVOT", title)
        obligations = _normalize_obligations(raw)
        pivot = {
            "id": pivot_id, "title": title, "objective": objective, "reason": str(raw.get("reason", "")).strip(),
            "status": "proposed", "created_utc": utc_now(), "updated_utc": utc_now(),
            "entry_mode": entry_mode, "changed_paths": _strings(raw.get("changed_paths"), paths=True),
            "obligations": obligations, "enduring_obligations": [item["title"] for item in obligations if item["stability"] == "enduring"],
            "intentional_breakage": _strings(raw.get("intentional_breakage")),
            "migration_concerns": _strings(raw.get("migration_concerns")), "migration_paths": _strings(raw.get("migration_paths"), paths=True),
            "source_refs": _strings(raw.get("source_refs"), paths=True), "out_of_scope": _strings(raw.get("out_of_scope")),
            "tests": _strings(raw.get("tests")), "labs": _strings(raw.get("labs")),
            "release_evidence": _strings(raw.get("release_evidence")) or ["gate:release"],
            "completion_criteria": _strings(raw.get("completion_criteria")),
            "quality_targets": _quality_targets(raw.get("quality_targets")),
            "quality_evidence": _quality_evidence(raw.get("quality_evidence")),
            "standards_refs": _strings(raw.get("standards_refs")), "quality_exceptions": _strings(raw.get("quality_exceptions")),
            "impact": {}, "contract_dispositions": {}, "record_dispositions": {}, "obligation_dispositions": {},
            "disposition_details": {}, "replacement_evidence": {}, "transition_plan_id": "", "checkpoint": {},
            "history": [{"status": "proposed", "utc": utc_now(), "reason": "created"}],
        }
        for obligation in obligations:
            suggestion, suggestion_reason = _suggest_disposition(kind=obligation["kind"], stability=obligation["stability"])
            initial = "retain" if obligation["stability"] == "enduring" and suggestion == "retain" else "review"
            pivot["obligation_dispositions"][obligation["id"]] = initial
            pivot["disposition_details"][obligation["id"]] = {"disposition": initial, "reason": "Explicitly declared enduring obligation" if initial == "retain" else "", "successor": "", "evidence": [], "accepted_loss": "", "suggested": suggestion, "suggestion_reason": suggestion_reason}
        pivots.append(pivot)
        _save_store(paths["pivots"], store)
        return {"status": "CREATED", "pivot": pivot}

    if not item_id:
        raise ValueError(f"project pivot --action {action} requires --id")
    pivot = _find(pivots, item_id)
    if action == "assess":
        changed_paths = list(pivot.get("changed_paths", []))
        impact_payload = analyze_impact(project_root, forge_root, config, changed_paths, write=True) if changed_paths else {
            "risk": {"level": "unknown", "score": 0}, "impacted_nodes": [], "targeted_tests": [], "recommended_live_checks": []
        }
        impacted_paths = {normalize_rel(str(item.get("path", ""))) for item in impact_payload.get("impacted_nodes", []) if item.get("path")}
        contract_path, contract_store = _all_contract_store(project_root, config)
        affected_contracts: list[dict[str, Any]] = []
        for contract in contract_store.get("contracts", []):
            if str(contract.get("status", "active")) in {"retired", "superseded"}:
                continue
            contract_paths = {normalize_rel(str(value)) for value in contract.get("affected_paths", [])}
            affected = not contract_paths or bool(contract_paths.intersection(impacted_paths | set(changed_paths)))
            if not affected:
                continue
            ref = str(contract.get("id"))
            suggestion, suggestion_reason = _suggest_disposition(category=str(contract.get("category", "")))
            affected_contracts.append({
                "id": ref, "title": contract.get("title", ""), "invariant": contract.get("invariant", ""),
                "category": contract.get("category", ""), "status": contract.get("status", "active"),
                "affected_paths": sorted(contract_paths), "suggested_disposition": suggestion,
            })
            pivot.setdefault("contract_dispositions", {}).setdefault(ref, "review")
            pivot.setdefault("disposition_details", {}).setdefault(ref, {"disposition": "review", "reason": "", "successor": "", "evidence": [], "accepted_loss": "", "suggested": suggestion, "suggestion_reason": suggestion_reason})
        ledger = _load_store(paths["ledger"], "ledger")
        affected_records: list[dict[str, Any]] = []
        for entry in ledger["entries"]:
            if entry.get("status") in {"superseded", "retired", "rejected"}:
                continue
            applies = {normalize_rel(str(value)) for value in entry.get("applies_to", [])}
            if applies and not applies.intersection(impacted_paths | set(changed_paths)):
                continue
            ref = str(entry.get("id"))
            kind = "standard" if entry.get("type") == "standard" else "architecture" if "architecture" in entry.get("tags", []) else "behavior"
            stability = "architecture-bound" if kind == "architecture" else "enduring"
            suggestion, suggestion_reason = _suggest_disposition(kind=kind, stability=stability)
            affected_records.append({
                "id": ref, "type": entry.get("type"), "title": entry.get("title"), "summary": entry.get("summary"),
                "status": entry.get("status"), "suggested_disposition": suggestion,
            })
            pivot.setdefault("record_dispositions", {}).setdefault(ref, "review")
            pivot.setdefault("disposition_details", {}).setdefault(ref, {"disposition": "review", "reason": "", "successor": "", "evidence": [], "accepted_loss": "", "suggested": suggestion, "suggestion_reason": suggestion_reason})
        pivot["impact"] = {
            "risk": impact_payload.get("risk", {}), "impacted_node_count": len(impact_payload.get("impacted_nodes", [])),
            "impacted_paths": sorted(impacted_paths), "targeted_tests": impact_payload.get("targeted_tests", []),
            "recommended_live_checks": impact_payload.get("recommended_live_checks", []),
            "affected_contracts": affected_contracts, "affected_records": affected_records,
            "obligation_summary": {
                "enduring": sum(1 for item in pivot.get("obligations", []) if item.get("stability") == "enduring"),
                "architecture_bound": sum(1 for item in pivot.get("obligations", []) if item.get("stability") == "architecture-bound"),
                "temporary_or_experimental": sum(1 for item in pivot.get("obligations", []) if item.get("stability") in {"temporary", "experimental"}),
            },
        }
        pivot["status"] = "assessed"
    elif action == "classify":
        raw = _read_input(input_path)
        for key, target in (("contracts", "contract_dispositions"), ("records", "record_dispositions"), ("obligations", "obligation_dispositions")):
            values = raw.get(key, {})
            if not isinstance(values, dict):
                raise ValueError(f"pivot classification {key} must be an object")
            for ref, value in values.items():
                disposition, detail = _normalize_disposition_value(value)
                pivot.setdefault(target, {})[str(ref)] = disposition
                pivot.setdefault("disposition_details", {})[str(ref)] = {**pivot.get("disposition_details", {}).get(str(ref), {}), **detail}
        evidence = raw.get("replacement_evidence", {})
        if evidence:
            if not isinstance(evidence, dict):
                raise ValueError("replacement_evidence must be an object")
            for ref, items in evidence.items():
                refs = _strings(items)
                pivot.setdefault("replacement_evidence", {})[str(ref)] = refs
                pivot.setdefault("disposition_details", {}).setdefault(str(ref), {"disposition": "review", "reason": "", "successor": "", "evidence": [], "accepted_loss": ""})["evidence"] = refs
        if raw.get("quality_evidence") is not None:
            pivot["quality_evidence"] = _quality_evidence(raw.get("quality_evidence"))
            plan_id = str(pivot.get("transition_plan_id", ""))
            if plan_id:
                plans = _load_store(paths["plans"], "plans")
                plan = _find(plans["plans"], plan_id)
                plan["quality_evidence"] = pivot["quality_evidence"]
                plan["quality_coverage"] = _quality_coverage(plan.get("quality_targets", {}), plan["quality_evidence"])
                plan["updated_utc"] = utc_now()
                _save_store(paths["plans"], plans)
    elif action == "activate":
        if pivot.get("status") not in {"assessed", "proposed"}:
            raise RuntimeError(f"pivot cannot activate from status {pivot.get('status')}")
        readiness_maps = [pivot.get("contract_dispositions", {}), pivot.get("record_dispositions", {}), pivot.get("obligation_dispositions", {})]
        unresolved = sorted({key for mapping in readiness_maps for key, value in mapping.items() if value == "review"})
        if unresolved:
            raise RuntimeError("pivot cannot activate until every affected contract, record, and obligation is classified: " + ", ".join(unresolved))
        details = pivot.get("disposition_details", {})
        missing_reason = [ref for mapping in readiness_maps for ref, disposition in mapping.items() if disposition in {"suspend", "retire", "supersede"} and not str(details.get(ref, {}).get("reason", "")).strip()]
        missing_successor = [ref for mapping in readiness_maps for ref, disposition in mapping.items() if disposition in {"replace", "supersede"} and not str(details.get(ref, {}).get("successor", "")).strip()]
        if missing_reason:
            raise RuntimeError("pivot activation requires reasons for suspended, retired, or superseded items: " + ", ".join(sorted(set(missing_reason))))
        if missing_successor:
            raise RuntimeError("pivot activation requires successor references for replaced or superseded items: " + ", ".join(sorted(set(missing_successor))))
        previous = str(store.get("active_id", ""))
        if previous and previous != item_id:
            raise RuntimeError(f"pivot {previous} is already active")
        pivot["checkpoint"] = _write_pivot_checkpoint(project_root, forge_root, config, paths, pivot)
        pivot["transition_plan_id"] = _create_pivot_plan(project_root, forge_root, config, paths, pivot)
        pivot["status"] = "active"
        store["active_id"] = item_id
        _memory_config(config)["mode"] = pivot.get("entry_mode", "exploration")
    elif action == "mode":
        if pivot.get("status") != "active":
            raise RuntimeError("only an active pivot can change mode")
        target = mode.strip().lower()
        if target not in PROJECT_MODES:
            raise ValueError("pivot mode must be one of: " + ", ".join(sorted(PROJECT_MODES)))
        current = str(_memory_config(config).get("mode", "development"))
        sequence = ["exploration", "transition", "development", "release"]
        if target == "release":
            plans = _load_store(paths["plans"], "plans")
            plan = _active_plan(plans, str(pivot.get("transition_plan_id", "")))
            coverage = plan.get("quality_coverage", {}) if plan else {}
            if coverage.get("unresolved"):
                raise RuntimeError("pivot cannot enter release mode while quality coverage gaps remain: " + ", ".join(coverage["unresolved"]))
            details = pivot.get("disposition_details", {})
            missing = [ref for ref, disposition in {**pivot.get("contract_dispositions", {}), **pivot.get("record_dispositions", {}), **pivot.get("obligation_dispositions", {})}.items() if disposition in {"revise", "replace"} and not details.get(ref, {}).get("evidence")]
            if missing:
                raise RuntimeError("pivot cannot enter release mode without replacement evidence: " + ", ".join(sorted(missing)))
        _memory_config(config)["mode"] = target
        pivot.setdefault("mode_history", []).append({"from": current, "to": target, "utc": utc_now(), "reason": reason.strip()})
    elif action == "complete":
        if pivot.get("status") != "active":
            raise RuntimeError("only an active pivot can complete")
        plans = _load_store(paths["plans"], "plans")
        readiness = _pivot_readiness(project_root, forge_root, config, pivot, plans)
        if not readiness["ready"]:
            raise RuntimeError("pivot completion boundary is not satisfied: " + json.dumps({key: value for key, value in readiness.items() if value and key not in {"ready", "release_gate", "transition_plan_id"}}, sort_keys=True))
        applied = _apply_pivot_dispositions(project_root, config, paths, pivot)
        plan_id = str(pivot.get("transition_plan_id", ""))
        if plan_id:
            plan = _find(plans["plans"], plan_id)
            plan["status"] = "complete"
            plan["updated_utc"] = utc_now()
            plan.setdefault("history", []).append({"status": "complete", "utc": utc_now(), "reason": f"pivot {item_id} completed"})
            if plans.get("active_id") == plan_id:
                plans["active_id"] = ""
            _save_store(paths["plans"], plans)
        pivot["status"] = "complete"
        pivot["completed_reason"] = reason.strip()
        pivot["completion"] = {
            "utc": utc_now(), "tree_fingerprint": tree_fingerprint(project_root, config.get("paths", {}).get("exclude", []), forge_root),
            "release_gate": readiness.get("release_gate", {}), "applied": applied,
            "accepted_intentional_breakage": list(pivot.get("intentional_breakage", [])),
        }
        store["active_id"] = ""
        _memory_config(config)["mode"] = "development"
    elif action == "restore":
        if pivot.get("status") not in {"active", "cancelled"}:
            raise RuntimeError("pivot assurance state can be restored only from an active or cancelled pivot")
        restoration = _restore_pivot_checkpoint(project_root, pivot, config, confirmed=confirmed)
        pivot["status"] = "cancelled"
        pivot["restoration"] = {**restoration, "utc": utc_now(), "reason": reason.strip()}
        if store.get("active_id") == item_id:
            store["active_id"] = ""
        _memory_config(config)["mode"] = "development"
    elif action == "cancel":
        pivot["status"] = "cancelled"
        pivot["cancelled_reason"] = reason.strip()
        if store.get("active_id") == item_id:
            store["active_id"] = ""
            _memory_config(config)["mode"] = "development"
    else:
        raise ValueError(f"unsupported project pivot action: {action}")
    pivot["updated_utc"] = utc_now()
    pivot.setdefault("history", []).append({"status": pivot["status"], "utc": utc_now(), "reason": reason.strip() or action, "mode": _memory_config(config).get("mode")})
    _save_store(paths["pivots"], store)
    return {
        "status": pivot["status"].upper(), "pivot": pivot, "active_id": store.get("active_id", ""),
        "project_mode": _memory_config(config).get("mode"),
        "readiness": _pivot_readiness(project_root, forge_root, config, pivot, _load_store(paths["plans"], "plans")),
    }


def _short(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _active_plan(plans: dict[str, Any], plan_id: str = "") -> dict[str, Any]:
    target = plan_id or str(plans.get("active_id", ""))
    if not target:
        return {}
    try:
        return _find(plans.get("plans", []), target)
    except RuntimeError:
        return {}


def _active_pivot(pivots: dict[str, Any], pivot_id: str = "") -> dict[str, Any]:
    target = pivot_id or str(pivots.get("active_id", ""))
    if not target:
        return {}
    try:
        return _find(pivots.get("pivots", []), target)
    except RuntimeError:
        return {}


def _estimated_tokens(payload: Any) -> int:
    return max(1, math.ceil(len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) / 4))


def _failure_payload(project_root: Path, config: dict[str, Any], failure_id: str) -> dict[str, Any]:
    root = project_root / config.get("evidence", {}).get("failure_dir", ".forge/failures")
    candidates = sorted(root.rglob("context.json"), key=lambda path: path.stat().st_mtime, reverse=True) if root.is_dir() else []
    if failure_id:
        candidates = [path for path in candidates if failure_id in path.as_posix()]
    if not candidates:
        return {}
    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "path": str(candidates[0].relative_to(project_root)),
        "profile": data.get("profile"),
        "check_id": data.get("failed_check", {}).get("check_id"),
        "status": data.get("failed_check", {}).get("status"),
        "changed_paths": (data.get("changes_since_last_green", {}).get("added", []) + data.get("changes_since_last_green", {}).get("modified", []) + data.get("changes_since_last_green", {}).get("removed", []))[:50],
        "reproduction_command": data.get("reproduction_command", []),
        "related_contracts": data.get("related_learned_contracts", [])[:20],
    }


def build_context_packet(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    mode: str = "cold",
    budget: str = "",
    plan_id: str = "",
    subsystem: str = "",
    failure_id: str = "",
    pivot_id: str = "",
    write: bool = True,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    if mode not in CONTEXT_MODES:
        raise ValueError("context mode must be one of: " + ", ".join(sorted(CONTEXT_MODES)))
    memory = _memory_config(config)
    context_config = memory.get("context", {})
    budget = budget or str(context_config.get("default_budget", "standard"))
    if budget not in CONTEXT_BUDGETS:
        raise ValueError("context budget must be compact, standard, or full")
    token_limit = int(context_config.get("token_budgets", {}).get(budget, {"compact": 1200, "standard": 3000, "full": 8000}[budget]))
    paths = _paths(project_root, config)
    plans = _load_store(paths["plans"], "plans")
    ledger = _load_store(paths["ledger"], "ledger")
    pivots = _load_store(paths["pivots"], "pivots")
    plan = _active_plan(plans, plan_id)
    pivot = _active_pivot(pivots, pivot_id)
    brief = build_brief(project_root, forge_root, config, write=False)
    graph = load_graph(project_root, config) or build_graph(project_root, forge_root, config, write=True)
    contracts = _load_contracts(project_root, config)

    changed_paths = set(plan.get("changed_paths", [])) | set(plan.get("expected_files", [])) | set(pivot.get("changed_paths", []))
    active_entries = [item for item in ledger.get("entries", []) if item.get("status") not in {"superseded", "retired", "rejected"}]
    if changed_paths:
        relevant = [item for item in active_entries if not item.get("applies_to") or changed_paths.intersection(item.get("applies_to", []))]
    else:
        relevant = active_entries
    if subsystem:
        relevant = [item for item in relevant if subsystem.lower() in " ".join(item.get("tags", []) + item.get("applies_to", [])).lower()]

    node_limit = {"compact": 8, "standard": 24, "full": 100}[budget]
    record_limit = {"compact": 6, "standard": 20, "full": 100}[budget]
    contract_limit = {"compact": 6, "standard": 20, "full": 100}[budget]
    graph_nodes = []
    for node in graph.get("nodes", []):
        if subsystem and str(node.get("subsystem", "")).lower() != subsystem.lower():
            continue
        if changed_paths and normalize_rel(str(node.get("path", ""))) not in changed_paths and mode in {"task", "pivot"}:
            continue
        graph_nodes.append({"id": node.get("id"), "type": node.get("type"), "path": node.get("path"), "subsystem": node.get("subsystem")})
        if len(graph_nodes) >= node_limit:
            break

    contract_items = []
    for item in contracts:
        affected = set(item.get("affected_paths", []))
        if changed_paths and affected and not changed_paths.intersection(affected):
            continue
        contract_items.append({
            "id": item.get("id"),
            "title": _short(item.get("title"), 120),
            "invariant": _short(item.get("invariant"), 280),
            "severity": item.get("severity"),
            "affected_paths": list(item.get("affected_paths", []))[:12],
        })
        if len(contract_items) >= contract_limit:
            break

    packet = {
        "schema": 1,
        "generated_utc": utc_now(),
        "mode": mode,
        "budget": budget,
        "token_limit": token_limit,
        "project": {
            "name": brief.get("project"),
            "version": brief.get("version"),
            "forge_version": brief.get("forge_version"),
            "development_mode": memory.get("mode", "development"),
            "objective": brief.get("objective", {}),
            "last_green": brief.get("last_green", {}),
            "source_changed_since_last_green": brief.get("source_changed_since_last_green"),
            "doctor_status": brief.get("doctor_status"),
        },
        "active_plan": {
            "id": plan.get("id"), "title": plan.get("title"), "objective": _short(plan.get("objective"), 500),
            "status": plan.get("status"), "scope": plan.get("scope", []), "out_of_scope": plan.get("out_of_scope", []),
            "expected_files": plan.get("expected_files", []), "tests": plan.get("tests", []), "labs": plan.get("labs", []),
            "completion_criteria": plan.get("completion_criteria", []), "source_refs": plan.get("source_refs", []),
            "quality_targets": plan.get("quality_targets", {}), "quality_coverage": plan.get("quality_coverage", {}),
            "standards_refs": plan.get("standards_refs", []), "quality_exceptions": plan.get("quality_exceptions", []),
        } if plan else {},
        "active_pivot": {
            "id": pivot.get("id"), "title": pivot.get("title"), "objective": _short(pivot.get("objective"), 500),
            "status": pivot.get("status"), "mode": memory.get("mode", "development"),
            "risk": pivot.get("impact", {}).get("risk", {}),
            "enduring_obligations": pivot.get("enduring_obligations", []),
            "obligations": pivot.get("obligations", []),
            "intentional_breakage": pivot.get("intentional_breakage", []),
            "transition_plan_id": pivot.get("transition_plan_id", ""),
            "unresolved_dispositions": sorted(
                [key for key, value in {**pivot.get("contract_dispositions", {}), **pivot.get("record_dispositions", {}), **pivot.get("obligation_dispositions", {})}.items() if value == "review"]
            ),
        } if pivot else {},
        "records": [
            {
                "id": item.get("id"), "type": item.get("type"), "status": item.get("status"),
                "title": _short(item.get("title"), 120), "summary": _short(item.get("summary"), 320),
                "canonical_ref": item.get("canonical_ref", ""), "source_refs": item.get("source_refs", [])[:8],
            }
            for item in relevant[:record_limit]
        ],
        "architecture": {
            "summary": graph.get("summary", {}),
            "nodes": graph_nodes,
            "subsystem": subsystem,
        },
        "learned_contracts": contract_items,
        "failure": _failure_payload(project_root, config, failure_id) if mode == "failure" or failure_id else {},
        "retrieval": {
            "full_context": f"python3 Emotivus-Forge/forge.py resume . --budget full",
            "project_status": "python3 Emotivus-Forge/forge.py resume . --budget compact",
            "verify": "python3 Emotivus-Forge/forge.py check . --profile quick --fresh",
        },
        "omitted": {
            "records": max(0, len(relevant) - record_limit),
            "contracts": max(0, len(contracts) - len(contract_items)),
            "graph_nodes": max(0, int(graph.get("summary", {}).get("nodes", 0)) - len(graph_nodes)),
        },
    }
    estimated = _estimated_tokens(packet)
    packet["estimated_tokens"] = estimated
    packet["within_budget"] = estimated <= token_limit
    if not packet["within_budget"] and budget != "full":
        # Preserve the most important facts and reduce optional detail rather than truncating arbitrary JSON.
        packet["records"] = packet["records"][: max(2, len(packet["records"]) // 2)]
        packet["architecture"]["nodes"] = packet["architecture"]["nodes"][: max(2, len(packet["architecture"]["nodes"]) // 2)]
        packet["learned_contracts"] = packet["learned_contracts"][: max(2, len(packet["learned_contracts"]) // 2)]
        packet["estimated_tokens"] = _estimated_tokens(packet)
        packet["within_budget"] = packet["estimated_tokens"] <= token_limit
    if write:
        stamp = utc_now().replace(":", "-")
        slug = _slug(plan.get("title") or pivot.get("title") or subsystem or mode)
        output = paths["context"] / f"{stamp}-{mode}-{budget}-{slug}.json"
        write_json(output, packet)
        latest = paths["context"] / f"latest-{mode}.json"
        write_json(latest, packet)
        packet["output"] = str(output)
        packet["latest"] = str(latest)
    return packet


def project_status(project_root: Path, forge_root: Path, config: dict[str, Any], *, budget: str = "compact") -> dict[str, Any]:
    packet = build_context_packet(project_root, forge_root, config, mode="cold", budget=budget, write=True)
    paths = _paths(project_root.resolve(), config)
    plans = _load_store(paths["plans"], "plans")
    ledger = _load_store(paths["ledger"], "ledger")
    pivots = _load_store(paths["pivots"], "pivots")
    packet["counts"] = {
        "plans": len(plans["plans"]),
        "active_records": sum(1 for item in ledger["entries"] if item.get("status") not in {"superseded", "retired", "rejected"}),
        "pivots": len(pivots["pivots"]),
    }
    return packet


def evaluate_project_memory(project_root: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    """Return deterministic project-memory findings for the static audit."""
    paths = _paths(project_root.resolve(), config)
    findings: list[dict[str, str]] = []
    plans = _load_store(paths["plans"], "plans")
    ledger = _load_store(paths["ledger"], "ledger")
    pivots = _load_store(paths["pivots"], "pivots")
    active_plan = _active_plan(plans)
    mode = str(_memory_config(config).get("mode", "development"))
    if active_plan:
        if not active_plan.get("completion_criteria"):
            findings.append({
                "check_id": "project.plan-completion-criteria", "severity": "warning", "category": "traceability",
                "path": str(paths["plans"].relative_to(project_root)),
                "message": "The active project plan has no declared completion criteria.",
            })
        missing_sources = [path for path in active_plan.get("source_refs", []) if not (project_root / path).exists()]
        if missing_sources:
            findings.append({
                "check_id": "project.plan-source-ref", "severity": "warning", "category": "traceability",
                "path": str(paths["plans"].relative_to(project_root)),
                "message": "The active project plan references missing source artifacts: " + ", ".join(missing_sources),
            })
        coverage = active_plan.get("quality_coverage") or _quality_coverage(active_plan.get("quality_targets", {}), active_plan.get("quality_evidence", {}))
        if coverage.get("unresolved"):
            findings.append({
                "check_id": "project.plan-quality-coverage", "severity": "error" if mode == "release" else "warning",
                "category": "quality-coverage", "path": str(paths["plans"].relative_to(project_root)),
                "message": "The active plan has unresolved quality-evidence dimensions: " + ", ".join(coverage["unresolved"]),
            })
        standards = _standard_ref_map(ledger["entries"])
        missing_standards = [ref for ref in active_plan.get("standards_refs", []) if ref not in standards]
        if missing_standards:
            findings.append({
                "check_id": "project.plan-standard-ref", "severity": "warning", "category": "standards",
                "path": str(paths["plans"].relative_to(project_root)),
                "message": "The active plan references standards that are not versioned Ledger records: " + ", ".join(missing_standards),
            })
    elif config.get("project_memory", {}).get("traceability", {}).get("release_requires_active_plan", False):
        findings.append({
            "check_id": "project.active-plan-required", "severity": "error", "category": "traceability",
            "path": str(paths["plans"].relative_to(project_root)),
            "message": "This project requires an active Forge project plan before release.",
        })
    for entry in ledger["entries"]:
        if entry.get("type") == "artifact" and entry.get("status") in {"accepted", "active"} and not entry.get("canonical_ref"):
            findings.append({
                "check_id": "project.artifact-canonical-ref", "severity": "error", "category": "traceability",
                "path": str(paths["ledger"].relative_to(project_root)),
                "message": f"Accepted artifact {entry.get('id')} has no canonical source-of-truth reference.",
            })
        if entry.get("type") == "standard" and entry.get("status") in {"active", "accepted"}:
            standard = entry.get("standard", {})
            missing = [key for key in ("source", "version", "authority") if not str(standard.get(key, "")).strip()]
            if not standard.get("scope"):
                missing.append("scope")
            if missing:
                findings.append({
                    "check_id": "project.standard-metadata", "severity": "error", "category": "standards",
                    "path": str(paths["ledger"].relative_to(project_root)),
                    "message": f"Active standard {entry.get('id')} lacks versioned authority metadata: {', '.join(missing)}.",
                })
    active_pivot = _active_pivot(pivots)
    if active_pivot:
        unresolved = [key for key, value in {**active_pivot.get("contract_dispositions", {}), **active_pivot.get("record_dispositions", {}), **active_pivot.get("obligation_dispositions", {})}.items() if value == "review"]
        if unresolved:
            findings.append({
                "check_id": "project.pivot-unresolved", "severity": "error" if mode == "release" else "warning", "category": "pivot",
                "path": str(paths["pivots"].relative_to(project_root)),
                "message": "The active pivot has unresolved contract, record, or obligation dispositions: " + ", ".join(sorted(unresolved)),
            })
        if not active_pivot.get("checkpoint", {}).get("path"):
            findings.append({
                "check_id": "project.pivot-checkpoint", "severity": "error", "category": "pivot",
                "path": str(paths["pivots"].relative_to(project_root)),
                "message": "The active pivot has no pre-pivot assurance checkpoint.",
            })
    return findings


def validate_project_release(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Validate release-facing project truth without interpreting product intent."""
    project_root = project_root.resolve()
    paths = _paths(project_root, config)
    plans = _load_store(paths["plans"], "plans")
    ledger = _load_store(paths["ledger"], "ledger")
    pivots = _load_store(paths["pivots"], "pivots")
    problems: list[str] = []
    traceability = _memory_config(config).get("traceability", {})
    active_plan = _active_plan(plans)
    if traceability.get("release_requires_active_plan", False) and not active_plan:
        problems.append("A release requires an active Forge project plan.")
    if active_plan:
        if not active_plan.get("completion_criteria"):
            problems.append(f"Active plan {active_plan.get('id')} has no completion criteria.")
        for relative in active_plan.get("expected_files", []):
            if relative and not (project_root / relative).exists():
                problems.append(f"Active plan expected file is missing: {relative}")
        coverage = active_plan.get("quality_coverage") or _quality_coverage(active_plan.get("quality_targets", {}), active_plan.get("quality_evidence", {}))
        if traceability.get("release_requires_quality_coverage", True) and coverage.get("unresolved"):
            problems.append("Active plan has unresolved quality-evidence dimensions: " + ", ".join(coverage["unresolved"]))
        standards = _standard_ref_map(ledger.get("entries", []))
        for ref in active_plan.get("standards_refs", []):
            standard = standards.get(ref)
            if not standard:
                problems.append(f"Active plan standard reference is missing or not a standard Ledger record: {ref}")
            elif standard.get("status") not in {"active", "accepted"}:
                problems.append(f"Active plan references an inactive standard: {ref}")
        for evidence in active_plan.get("release_evidence", []):
            text = str(evidence).strip()
            if not text:
                continue
            if text.startswith("gate:"):
                profile = text.split(":", 1)[1]
                # The release Gate cannot require its own already-written report while it is executing.
                if profile == "release":
                    continue
                report = project_root / config.get("paths", {}).get("reports", ".forge/reports") / f"{profile}.json"
                if not report.is_file():
                    problems.append(f"Required Gate evidence is missing: {text}")
                continue
            if text.startswith(("lab:", "manual:", "external:", "contract:")):
                continue
            if not (project_root / normalize_rel(text)).exists():
                problems.append(f"Required release evidence is missing: {text}")
    active_pivot = _active_pivot(pivots)
    if active_pivot:
        dispositions = {**active_pivot.get("contract_dispositions", {}), **active_pivot.get("record_dispositions", {}), **active_pivot.get("obligation_dispositions", {})}
        unresolved = [key for key, value in dispositions.items() if value == "review"]
        if unresolved:
            problems.append("The active pivot has unresolved dispositions: " + ", ".join(sorted(unresolved)))
        current_mode = str(_memory_config(config).get("mode", "development"))
        if current_mode != "release":
            if current_mode == "exploration":
                problems.append("The project is in exploration mode under an active pivot; deliberately transition through development and release proof before production release.")
            else:
                problems.append(f"An active pivot is in {current_mode} mode and must deliberately enter release mode before production release proof.")
        details = active_pivot.get("disposition_details", {})
        missing_reason = [ref for ref, disposition in dispositions.items() if disposition in {"suspend", "retire", "supersede"} and not str(details.get(ref, {}).get("reason", "")).strip()]
        missing_successor = [ref for ref, disposition in dispositions.items() if disposition in {"replace", "supersede"} and not str(details.get(ref, {}).get("successor", "")).strip()]
        missing_evidence = [ref for ref, disposition in dispositions.items() if disposition in {"revise", "replace"} and not details.get(ref, {}).get("evidence")]
        if missing_reason:
            problems.append("Pivot lifecycle reasons are missing for: " + ", ".join(sorted(missing_reason)))
        if missing_successor:
            problems.append("Pivot successor references are missing for: " + ", ".join(sorted(missing_successor)))
        if missing_evidence:
            problems.append("Pivot replacement evidence is missing for: " + ", ".join(sorted(missing_evidence)))
    for entry in ledger.get("entries", []):
        if entry.get("type") == "artifact" and entry.get("status") in {"accepted", "active"} and not entry.get("canonical_ref"):
            problems.append(f"Accepted artifact {entry.get('id')} lacks a canonical source-of-truth reference.")
    return problems

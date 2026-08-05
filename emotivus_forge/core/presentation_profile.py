from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .state import load_settings

PROFILE_SCHEMA = 1
AUDIENCES = {"owner", "builder", "expert"}
SECTIONS = {
    "outcome", "summary", "what_changed", "validation", "limitations",
    "roadmap", "downloads", "next_action", "forge_line",
}
VERBOSITY = {"compact", "standard", "detailed"}
TECHNICAL_DETAIL = {"after-owner-summary", "inline", "references-only"}
TABLES = {"comparisons-and-status", "when-useful", "avoid"}
FORGE_LINE = {"meaningful-events-only", "always", "never"}
PASS_LANGUAGE = {"scope-and-exclusions", "scope-only", "project-defined"}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Presentation profile requires {label}.")
    return text


def _identifier(value: Any, label: str) -> str:
    text = _required(value, label)
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in text):
        raise ValueError(f"{label} may contain only lowercase letters, numbers, hyphens, and underscores.")
    return text


def _source(project_root: Path, forge_root: Path, raw: str | Path) -> tuple[Path, str]:
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge") or _inside(path, forge_root.resolve()):
        raise ValueError("Presentation profiles must be project-owned files outside .forge and the Forge distribution.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Presentation profile does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _enum(value: Any, label: str, allowed: set[str]) -> str:
    text = str(value or "").strip()
    if text not in allowed:
        raise ValueError(f"{label} must be one of: {', '.join(sorted(allowed))}")
    return text


def validate_presentation_profile(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    path, relative = _source(project_root, forge_root, source_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Presentation profile is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != PROFILE_SCHEMA:
        raise ValueError("Presentation profile must be an object using schema 1.")

    profile_id = _identifier(raw.get("profile_id"), "profile_id")
    title = _required(raw.get("title"), "title", minimum=8)
    authority = _required(raw.get("authority"), "authority")
    audiences_raw = raw.get("audiences", ["owner", "builder", "expert"])
    if not isinstance(audiences_raw, list) or not audiences_raw:
        raise ValueError("audiences must be a non-empty array.")
    audiences: list[str] = []
    for item in audiences_raw:
        audience = _enum(item, "audience", AUDIENCES)
        if audience not in audiences:
            audiences.append(audience)
    default_audience = _enum(raw.get("default_audience", "owner"), "default_audience", AUDIENCES)
    if default_audience not in audiences:
        raise ValueError("default_audience must also appear in audiences.")

    structure = raw.get("structure", {})
    if not isinstance(structure, dict):
        raise ValueError("structure must be an object.")
    order_raw = structure.get("section_order")
    if not isinstance(order_raw, list) or not order_raw:
        raise ValueError("structure.section_order must be a non-empty array.")
    section_order: list[str] = []
    for item in order_raw:
        section = _enum(item, "section", SECTIONS)
        if section not in section_order:
            section_order.append(section)
    if section_order[0] not in {"outcome", "summary"}:
        raise ValueError("structure.section_order must begin with outcome or summary.")
    if "next_action" not in section_order:
        raise ValueError("structure.section_order must include next_action.")

    style = raw.get("style", {})
    if not isinstance(style, dict):
        raise ValueError("style must be an object.")
    verbosity = _enum(style.get("verbosity", "compact"), "style.verbosity", VERBOSITY)
    technical_detail = _enum(style.get("technical_detail", "after-owner-summary"), "style.technical_detail", TECHNICAL_DETAIL)
    tables = _enum(style.get("tables", "comparisons-and-status"), "style.tables", TABLES)
    forge_line = _enum(style.get("forge_line", "meaningful-events-only"), "style.forge_line", FORGE_LINE)
    pass_language = _enum(style.get("pass_language", "scope-and-exclusions"), "style.pass_language", PASS_LANGUAGE)
    tone = _required(style.get("tone", "clear, warm, and precise"), "style.tone", minimum=8)
    headings = _required(style.get("headings", "descriptive"), "style.headings", minimum=4)
    bullets = _required(style.get("bullets", "concise"), "style.bullets", minimum=4)

    max_chars = raw.get("max_owner_summary_characters", 1400)
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not 400 <= max_chars <= 4000:
        raise ValueError("max_owner_summary_characters must be an integer from 400 to 4000.")
    truth_boundary = _required(raw.get("truth_boundary"), "truth_boundary", minimum=40)

    contract = {
        "schema": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "title": title,
        "authority": authority,
        "audiences": audiences,
        "default_audience": default_audience,
        "structure": {"section_order": section_order},
        "style": {
            "verbosity": verbosity,
            "technical_detail": technical_detail,
            "tables": tables,
            "forge_line": forge_line,
            "pass_language": pass_language,
            "tone": tone,
            "headings": headings,
            "bullets": bullets,
        },
        "max_owner_summary_characters": max_chars,
        "truth_boundary": truth_boundary,
    }
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "contract": contract,
        "source": relative,
        "contract_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _current(project_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    return fingerprint_bound_status(
        project_root,
        record,
        changed_status="approval-required",
        missing_reason="The project-owned presentation profile is missing.",
        changed_reason="The project-owned presentation profile changed after authority approval.",
    )


def presentation_profile_records(project_root: Path) -> dict[str, dict[str, Any]]:
    raw = load_settings(project_root).get("presentation_profiles", {})
    if not isinstance(raw, dict):
        return {}
    return {key: _current(project_root, value) for key, value in raw.items() if isinstance(value, dict)}


def record_presentation_profile(project_root: Path, forge_root: Path, source_path: str | Path) -> dict[str, Any]:
    validated = validate_presentation_profile(project_root, forge_root, source_path)
    contract = validated["contract"]
    settings = load_settings(project_root)
    records = settings.get("presentation_profiles", {})
    if not isinstance(records, dict):
        records = {}
    for key, value in list(records.items()):
        if isinstance(value, dict) and value.get("lifecycle_status") == "active" and key != contract["profile_id"]:
            retired = dict(value)
            retired.update({
                "status": "retired",
                "lifecycle_status": "retired",
                "retired_utc": utc_now(),
                "retired_by": contract["authority"],
                "reason": f"Superseded by presentation profile {contract['profile_id']}.",
            })
            records[key] = retired
    record = {
        "status": "active",
        "lifecycle_status": "active",
        "profile_id": contract["profile_id"],
        "recorded_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["contract_fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": contract,
    }
    records[contract["profile_id"]] = record
    settings["presentation_profiles"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "presentation-profile-recorded", {
        "profile_id": contract["profile_id"],
        "title": contract["title"],
        "authority": contract["authority"],
        "default_audience": contract["default_audience"],
        "section_order": contract["structure"]["section_order"],
        "truth_boundary": contract["truth_boundary"],
    }, source=contract["authority"])
    return {**record, "ledger_event_id": event["id"]}


def retire_presentation_profile(project_root: Path, profile_id: str, reason: str, *, authority: str = "owner") -> dict[str, Any]:
    reason = _required(reason, "retirement reason", minimum=8)
    settings = load_settings(project_root)
    records = settings.get("presentation_profiles", {})
    if not isinstance(records, dict) or profile_id not in records or not isinstance(records[profile_id], dict):
        raise ValueError(f"Presentation profile is not recorded: {profile_id}")
    record = dict(records[profile_id])
    record.update({
        "status": "retired",
        "lifecycle_status": "retired",
        "retired_utc": utc_now(),
        "retired_by": authority,
        "reason": reason,
    })
    records[profile_id] = record
    settings["presentation_profiles"] = records
    write_json(ForgePaths(project_root).settings, settings)
    event = record_event(project_root, "presentation-profile-retired", {"profile_id": profile_id, "reason": reason}, source=authority)
    return {**record, "ledger_event_id": event["id"]}


def _compact_instruction(contract: dict[str, Any]) -> str:
    style = contract.get("style", {}) if isinstance(contract.get("style"), dict) else {}
    order = contract.get("structure", {}).get("section_order", []) if isinstance(contract.get("structure"), dict) else []
    parts = [
        f"{contract.get('default_audience', 'owner')}-first",
        "outcome first" if order and order[0] == "outcome" else "summary first",
        f"{style.get('headings', 'descriptive')} headers",
        f"{style.get('bullets', 'concise')} bullets",
    ]
    if style.get("tables") != "avoid":
        parts.append("tables for status/comparisons")
    if style.get("pass_language") == "scope-and-exclusions":
        parts.append("every PASS states scope and exclusions")
    if style.get("technical_detail") == "after-owner-summary":
        parts.append("technical detail below the owner summary")
    if "downloads" in order:
        parts.append("downloads grouped near the end")
    if "next_action" in order:
        parts.append("finish with the exact next action")
    if style.get("forge_line") == "meaningful-events-only":
        parts.append("one Forge line only for meaningful activity")
    elif style.get("forge_line") == "always":
        parts.append("finish with one Forge line")
    text = "Presentation: " + "; ".join(parts) + "."
    return text[:420].rstrip()


def presentation_profile_summary(project_root: Path) -> dict[str, Any]:
    records = presentation_profile_records(project_root)
    active = [row for row in records.values() if row.get("lifecycle_status") == "active"]
    attention = [row for row in records.values() if row.get("status") not in {"active", "retired"}]
    if not active:
        return {
            "schema": 1,
            "status": "ATTENTION" if attention else "NOT_CONFIGURED",
            "active": 0,
            "attention": len(attention),
            "instruction": "",
            "truth_boundary": "No project-owned presentation profile is active. Forge does not infer a permanent writing preference from chat style alone.",
        }
    record = active[0]
    contract = record.get("contract", {}) if isinstance(record.get("contract"), dict) else {}
    return {
        "schema": 1,
        "status": "PASS" if record.get("status") == "active" else "ATTENTION",
        "active": 1,
        "attention": len(attention),
        "profile_id": contract.get("profile_id", ""),
        "title": contract.get("title", ""),
        "default_audience": contract.get("default_audience", "owner"),
        "instruction": _compact_instruction(contract),
        "max_owner_summary_characters": contract.get("max_owner_summary_characters", 1400),
        "truth_boundary": "Forge transfers the owner-approved communication structure and claim discipline; the active AI model still authors the prose and may vary in quality.",
    }

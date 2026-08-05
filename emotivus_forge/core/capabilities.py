from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import normalize_rel, read_json, read_jsonl, unique_strings, utc_now, write_json
from .ledger import record_event
from .lifecycle import fingerprint_bound_status
from .paths import ForgePaths
from .session_close import latest_session_close
from .state import load_settings

CAPABILITY_SCHEMA = 1

CAPABILITY_CATALOG: dict[str, dict[str, Any]] = {
    "doctor": {
        "id": "doctor",
        "name": "Forge Doctor",
        "status": "activatable",
        "mode": "diagnose-only",
        "operation": "check",
        "trigger": "A concrete environment, runtime, dependency, or extension failure needs bounded diagnosis.",
        "distinct_value": "Compares project-declared environment expectations with the local execution environment without repairing either one.",
        "required_regressions": [
            "doctor.inactive-by-default",
            "doctor.explicit-contract",
            "doctor.diagnose-only",
            "doctor.budget-bound",
            "doctor.contract-change-requires-reactivation",
        ],
    },
    "graph": {
        "id": "graph", "name": "Forge Graph", "status": "vaulted",
        "trigger": "Repeated work establishes enough confirmed relationships to justify a progressive graph.",
        "reason_inactive": "No active implementation or focused activation regressions exist yet.",
    },
    "lab": {
        "id": "lab", "name": "Forge Lab", "status": "vaulted",
        "trigger": "A specific state or failure hypothesis requires a disposable experiment.",
        "reason_inactive": "No active targeted-experiment contract exists yet.",
    },
    "evidence": {
        "id": "evidence", "name": "Forge Evidence", "status": "vaulted",
        "trigger": "Typed evidence volume exceeds the compact Passport and Ledger reference model.",
        "reason_inactive": "The compact evidence model has not yet reached a measured scale limit.",
    },
    "runtime-proof": {
        "id": "runtime-proof",
        "name": "Runtime Proof",
        "status": "activatable",
        "mode": "content-aware-http",
        "operation": "check",
        "trigger": "A specific public or local HTTP surface needs bounded proof that the intended content rendered, not merely that a server responded.",
        "distinct_value": "Adds project-owned status, content-type, minimum-size, required-marker, forbidden-marker, origin, and response-budget assertions without replacing a browser test or native gate.",
        "required_regressions": [
            "runtime-proof.inactive-by-default",
            "runtime-proof.explicit-contract",
            "runtime-proof.content-aware",
            "runtime-proof.tiny-error-page-fails",
            "runtime-proof.host-bound",
            "runtime-proof.budget-bound",
            "runtime-proof.contract-change-requires-reactivation",
        ],
    },
    "release-proof": {
        "id": "release-proof", "name": "Release Proof", "status": "integrated-core",
        "mode": "exact-package-assurance-map",
        "operation": "ship",
        "trigger": "An explicit final package requires a project-owned map of declared release surfaces, required assurance domains, and current evidence receipts.",
        "distinct_value": "Binds declared package members and scoped assurance obligations to current exact-package receipts without executing tests, reviewing methodology, or authorizing release.",
    },
    "confidentiality": {
        "id": "confidentiality", "name": "Confidentiality Certification", "status": "vaulted",
        "trigger": "Packaging, Ship, or an explicit targeted privacy/security certification requires it.",
        "reason_inactive": "Only the core placeholder-aware boundary and package contamination scan are active.",
    },
    "ci-bridge": {
        "id": "ci-bridge", "name": "CI Bridge", "status": "deferred",
        "trigger": "A stable Git/CI installation stage exists.",
        "reason_inactive": "Forge does not yet have a stable public installer or CI authority contract.",
    },
    "update": {
        "id": "update", "name": "Forge Update", "status": "deferred",
        "trigger": "A stable installer and rollback contract exists.",
        "reason_inactive": "Automatic update behavior is unsafe before installation and rollback are stable.",
    },
}

_ENVIRONMENT_TERMS = (
    "environment", "runtime", "dependency", "dependencies", "extension", "module", "version mismatch",
    "database connection", "configuration", "config mismatch", "php", "python", "node", "blank page",
)
_LAB_TERMS = ("intermittent", "reproduce", "hypothesis", "state-specific", "state specific", "experiment")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _contract_fingerprint(contract: dict[str, Any]) -> str:
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relative_contract_path(project_root: Path, raw_path: str | Path) -> tuple[Path, str]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if not _inside(path, project_root) or _inside(path, project_root / ".forge"):
        raise ValueError("Capability activation contracts must be regular project files outside .forge.")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Capability activation contract does not exist as a regular file: {path}")
    return path, normalize_rel(path.relative_to(project_root))


def _required_string(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Capability activation contract requires {label}.")
    return text


def _required_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Capability activation contract requires {label} as an array.")
    rows = unique_strings(value)
    if not rows:
        raise ValueError(f"Capability activation contract requires at least one {label} entry.")
    return rows


def validate_activation_contract(
    project_root: Path,
    forge_root: Path,
    capability_id: str,
    contract_path: str | Path,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    capability_id = capability_id.strip()
    definition = CAPABILITY_CATALOG.get(capability_id)
    if not definition:
        raise ValueError(f"Unknown advanced capability: {capability_id}")
    if definition.get("status") != "activatable":
        raise ValueError(
            f"{definition.get('name', capability_id)} is {definition.get('status')} and has no certified active implementation."
        )
    path, relative = _relative_contract_path(project_root, contract_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Capability activation contract is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != CAPABILITY_SCHEMA:
        raise ValueError("Capability activation contract must be an object using schema 1.")
    if str(raw.get("capability_id", "")).strip() != capability_id:
        raise ValueError("Capability activation contract capability_id does not match the requested capability.")

    authority = _required_string(raw.get("authority"), "authority")
    trigger = raw.get("trigger")
    if not isinstance(trigger, dict):
        raise ValueError("Capability activation contract requires a trigger object.")
    trigger_description = _required_string(trigger.get("description"), "trigger.description", minimum=12)
    evidence_paths = _required_string_list(trigger.get("evidence_paths"), "trigger.evidence_paths")
    normalized_evidence: list[str] = []
    for item in evidence_paths:
        candidate = (project_root / item).resolve()
        if not _inside(candidate, project_root) or _inside(candidate, project_root / ".forge"):
            raise ValueError(f"Trigger evidence path is outside the project or inside .forge: {item}")
        if not candidate.exists():
            raise ValueError(f"Trigger evidence path does not exist: {item}")
        if _inside(candidate, forge_root):
            raise ValueError(f"Trigger evidence cannot point into the Forge distribution: {item}")
        normalized_evidence.append(normalize_rel(candidate.relative_to(project_root)))

    scope = raw.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("Capability activation contract requires a scope object.")
    included = _required_string_list(scope.get("included"), "scope.included")
    excluded = _required_string_list(scope.get("excluded"), "scope.excluded")

    budget = raw.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("Capability activation contract requires a budget object.")
    runtime_seconds = budget.get("runtime_seconds")
    file_limit = budget.get("file_limit")
    output_characters = budget.get("output_characters")
    if not isinstance(runtime_seconds, int) or not 1 <= runtime_seconds <= 60:
        raise ValueError("budget.runtime_seconds must be an integer from 1 to 60.")
    if not isinstance(file_limit, int) or not 1 <= file_limit <= 200:
        raise ValueError("budget.file_limit must be an integer from 1 to 200.")
    if not isinstance(output_characters, int) or not 500 <= output_characters <= 20_000:
        raise ValueError("budget.output_characters must be an integer from 500 to 20000.")

    regressions = _required_string_list(raw.get("focused_regressions"), "focused_regressions")
    missing_regressions = [item for item in definition.get("required_regressions", []) if item not in regressions]
    if missing_regressions:
        raise ValueError(f"Capability activation contract is missing required focused regressions: {', '.join(missing_regressions)}")

    native_advantage = raw.get("native_advantage")
    if not isinstance(native_advantage, dict):
        raise ValueError("Capability activation contract requires a native_advantage object.")
    if native_advantage.get("status") != "distinct-value":
        raise ValueError("native_advantage.status must be distinct-value.")
    advantage_explanation = _required_string(native_advantage.get("explanation"), "native_advantage.explanation", minimum=20)
    if raw.get("allow_repairs") is not False:
        raise ValueError("Capability activation requires allow_repairs to be explicitly false.")

    capability_extension: dict[str, Any] = {}
    attachments: list[dict[str, Any]] = []
    if capability_id == "runtime-proof":
        runtime_proof = raw.get("runtime_proof")
        if not isinstance(runtime_proof, dict):
            raise ValueError("Runtime Proof activation requires a runtime_proof object.")
        allowed_origins = _required_string_list(runtime_proof.get("allowed_origins"), "runtime_proof.allowed_origins")
        recipe_paths = _required_string_list(runtime_proof.get("recipe_paths"), "runtime_proof.recipe_paths")
        if len(recipe_paths) > file_limit:
            raise ValueError("runtime_proof.recipe_paths exceeds budget.file_limit.")
        from ..services.runtime_proof import validate_runtime_recipe
        recipes: list[dict[str, Any]] = []
        for raw_recipe_path in recipe_paths:
            recipe_path, recipe_relative = _relative_contract_path(project_root, raw_recipe_path)
            if _inside(recipe_path, forge_root):
                raise ValueError(f"Runtime-proof recipe cannot point into the Forge distribution: {raw_recipe_path}")
            try:
                recipe_raw = json.loads(recipe_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Runtime-proof recipe is not valid UTF-8 JSON: {raw_recipe_path}: {exc}") from exc
            recipe = validate_runtime_recipe(recipe_raw, allowed_origins=allowed_origins, source=recipe_relative)
            if recipe["request"]["timeout_seconds"] > runtime_seconds:
                raise ValueError(f"Runtime-proof recipe timeout exceeds capability runtime budget: {recipe_relative}")
            recipes.append({
                "source": recipe_relative,
                "source_fingerprint": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
                "recipe": recipe,
            })
            attachments.append({
                "source": recipe_relative,
                "source_fingerprint": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
                "kind": "runtime-proof-recipe",
            })
        recipe_ids = [row["recipe"]["recipe_id"] for row in recipes]
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ValueError("Runtime-proof recipe_id values must be unique within one activation contract.")
        capability_extension["runtime_proof"] = {
            "allowed_origins": sorted(set(allowed_origins)),
            "recipes": recipes,
            "credentials_allowed": False,
            "javascript_execution": False,
        }

    contract = {
        "schema": CAPABILITY_SCHEMA,
        "capability_id": capability_id,
        "authority": authority,
        "trigger": {"description": trigger_description, "evidence_paths": normalized_evidence},
        "scope": {"included": included, "excluded": excluded},
        "budget": {
            "runtime_seconds": runtime_seconds,
            "file_limit": file_limit,
            "output_characters": output_characters,
        },
        "focused_regressions": sorted(set(regressions)),
        "native_advantage": {"status": "distinct-value", "explanation": advantage_explanation},
        "allow_repairs": False,
        **capability_extension,
    }
    return {
        "contract": contract,
        "source": relative,
        "fingerprint": _contract_fingerprint(contract),
        "source_fingerprint": hashlib.sha256(path.read_bytes()).hexdigest(),
        "attachments": attachments,
    }


def _activation_record_status(project_root: Path, capability_id: str, record: dict[str, Any]) -> dict[str, Any]:
    current = fingerprint_bound_status(
        project_root, record,
        changed_status="reactivation-required",
        missing_reason="The activation contract source is missing.",
        changed_reason="The activation contract source changed after approval.",
    )
    if current.get("status") != "active":
        return current
    attachments = record.get("attachments", []) if isinstance(record.get("attachments"), list) else []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        source = str(attachment.get("source", "")).strip()
        expected = str(attachment.get("source_fingerprint", "")).strip()
        candidate = (project_root / source).resolve()
        if not source or not _inside(candidate, project_root) or not candidate.is_file() or candidate.is_symlink():
            changed = dict(current)
            changed.update({"status": "reactivation-required", "reason": f"Capability attachment is missing: {source}"})
            return changed
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            changed = dict(current)
            changed.update({"status": "reactivation-required", "reason": f"Capability attachment changed after approval: {source}"})
            return changed
    return current


def capability_activations(project_root: Path) -> dict[str, dict[str, Any]]:
    settings = load_settings(project_root)
    raw = settings.get("advanced_capabilities", {}) if isinstance(settings, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {
        capability_id: _activation_record_status(project_root.resolve(), capability_id, record)
        for capability_id, record in raw.items()
        if isinstance(record, dict)
    }


def activate_capability(
    project_root: Path,
    forge_root: Path,
    capability_id: str,
    contract_path: str | Path,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    validated = validate_activation_contract(project_root, forge_root, capability_id, contract_path)
    settings = load_settings(project_root)
    capabilities = settings.get("advanced_capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}
    record = {
        "status": "active",
        "capability_id": capability_id,
        "activated_utc": utc_now(),
        "contract_source": validated["source"],
        "contract_fingerprint": validated["fingerprint"],
        "source_fingerprint": validated["source_fingerprint"],
        "contract": validated["contract"],
        "operation": CAPABILITY_CATALOG[capability_id].get("operation", "check"),
        "implementation": "clean-room-active-core",
        "legacy_vault_loaded": False,
        "attachments": validated.get("attachments", []),
    }
    capabilities[capability_id] = record
    settings["advanced_capabilities"] = capabilities
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "capability-activated", {
        "capability_id": capability_id,
        "contract_source": validated["source"],
        "contract_fingerprint": validated["fingerprint"],
        "trigger": validated["contract"]["trigger"],
        "scope": validated["contract"]["scope"],
        "budget": validated["contract"]["budget"],
        "native_advantage": validated["contract"]["native_advantage"],
        "authority": validated["contract"]["authority"],
        "legacy_vault_loaded": False,
    })
    return record


def deactivate_capability(project_root: Path, capability_id: str, reason: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    reason = _required_string(reason, "deactivation reason", minimum=8)
    settings = load_settings(project_root)
    capabilities = settings.get("advanced_capabilities", {})
    if not isinstance(capabilities, dict) or capability_id not in capabilities:
        raise ValueError(f"Capability is not active or recorded: {capability_id}")
    previous = capabilities[capability_id] if isinstance(capabilities[capability_id], dict) else {}
    record = dict(previous)
    record.update({"status": "inactive", "deactivated_utc": utc_now(), "deactivation_reason": reason})
    capabilities[capability_id] = record
    settings["advanced_capabilities"] = capabilities
    write_json(ForgePaths(project_root).settings, settings)
    record_event(project_root, "capability-deactivated", {
        "capability_id": capability_id,
        "reason": reason,
        "previous_contract_fingerprint": previous.get("contract_fingerprint", ""),
    })
    return record


def require_active_capability(project_root: Path, capability_id: str, operation: str) -> dict[str, Any]:
    definition = CAPABILITY_CATALOG.get(capability_id)
    if not definition:
        raise ValueError(f"Unknown advanced capability: {capability_id}")
    activation = capability_activations(project_root).get(capability_id, {})
    if activation.get("status") != "active":
        reason = activation.get("reason") or "No current activation contract exists."
        raise RuntimeError(f"{definition.get('name', capability_id)} is not active: {reason}")
    if activation.get("operation") != operation:
        raise RuntimeError(f"{definition.get('name', capability_id)} is not activated for {operation}.")
    return activation


def _latest_session_payload(project_root: Path) -> dict[str, Any]:
    event = latest_session_close(project_root)
    payload = event.get("payload", {}) if isinstance(event, dict) else {}
    return payload if isinstance(payload, dict) else {}


def recommend_capabilities(project_root: Path, passport: dict[str, Any]) -> list[dict[str, Any]]:
    project_root = project_root.resolve()
    active = capability_activations(project_root)
    close_payload = _latest_session_payload(project_root)
    risks = [str(item).strip() for item in close_payload.get("unresolved_risks", []) if str(item).strip()]
    next_action = close_payload.get("next_action", {}) if isinstance(close_payload.get("next_action"), dict) else {}
    text = " ".join(risks + [str(next_action.get("text", ""))]).casefold()
    recommendations: list[dict[str, Any]] = []

    if active.get("doctor", {}).get("status") != "active" and any(term in text for term in _ENVIRONMENT_TERMS):
        recommendations.append({
            "capability_id": "doctor",
            "status": "recommended-not-active",
            "reason": "The latest durable handoff records an environment or runtime concern that bounded diagnosis could clarify.",
            "activation": "forge adopt <project> --activate-capability doctor --capability-contract <contract.json>",
        })
    if any(term in text for term in _LAB_TERMS):
        recommendations.append({
            "capability_id": "lab",
            "status": "not-activatable",
            "reason": "The latest handoff contains an experiment or reproduction trigger, but Forge Lab has no certified activation contract yet.",
        })
    session_type = str(close_payload.get("session_type", ""))
    if session_type in {"release-candidate", "deployment"}:
        recommendations.append({
            "capability_id": "release-proof",
            "status": "not-activatable",
            "reason": "A release or deployment handoff exists, but release proof remains vaulted and Ship stays blocked.",
        })

    records = read_jsonl(ForgePaths(project_root).ledger)
    session_count = sum(1 for row in records if row.get("event") == "session-close")
    if session_count >= 3 and active.get("graph", {}).get("status") != "active":
        recommendations.append({
            "capability_id": "graph",
            "status": "not-activatable",
            "reason": f"{session_count} durable sessions exist, but Graph remains vaulted until relationship accuracy and activation regressions are certified.",
        })
    return recommendations


def capability_summary(project_root: Path, passport: dict[str, Any]) -> dict[str, Any]:
    active = capability_activations(project_root)
    active_rows = []
    attention_rows = []
    for capability_id, record in sorted(active.items()):
        row = {
            "capability_id": capability_id,
            "name": CAPABILITY_CATALOG.get(capability_id, {}).get("name", capability_id),
            "status": record.get("status", "unknown"),
            "contract_source": record.get("contract_source", ""),
            "operation": record.get("operation", ""),
            "legacy_vault_loaded": False,
        }
        if row["status"] == "active":
            active_rows.append(row)
        else:
            attention_rows.append(row)
    return {
        "schema": 1,
        "active": active_rows,
        "attention": attention_rows,
        "recommendations": recommend_capabilities(project_root, passport),
        "inactive_count": sum(1 for item in CAPABILITY_CATALOG.values() if item.get("status") != "activatable"),
        "vault_loaded": False,
        "truth_boundary": "Recommendations do not activate capabilities. Activation requires a valid project-owned contract and explicit Adopt action.",
    }


def public_capability_catalog(project_root: Path | None = None) -> dict[str, Any]:
    activations = capability_activations(project_root) if project_root is not None else {}
    rows = []
    for capability_id, definition in CAPABILITY_CATALOG.items():
        activation = activations.get(capability_id, {})
        rows.append({
            "id": capability_id,
            "name": definition.get("name", capability_id),
            "catalog_status": definition.get("status", "unknown"),
            "project_status": activation.get("status", "inactive"),
            "trigger": definition.get("trigger", ""),
            "mode": definition.get("mode", ""),
            "reason_inactive": definition.get("reason_inactive", ""),
            "legacy_vault_loaded": False,
        })
    return {
        "schema": 1,
        "message": "Advanced capability metadata is visible; legacy vaulted code is not loaded.",
        "vault_loaded": False,
        "capabilities": rows,
    }

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MAX_SNAPSHOT_BYTES = 2_000_000
MAX_VALIDATORS = 40
VALIDATOR_KINDS = {
    "json-path-exists",
    "json-value-equals",
    "json-value-in",
    "json-array-count",
    "json-array-unique",
    "json-array-all-have-fields",
    "json-array-none-equals",
    "json-array-values-in",
    "json-array-references-exist",
}
_PATH_TOKEN = re.compile(r"(?:^|\.)([^.\[\]]+)|\[(\d+)\]")


def _required(value: Any, label: str, *, minimum: int = 1) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"Semantic state validator requires {label}.")
    return text


def _string_list(value: Any, label: str, *, required: bool = False, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array.")
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    if required and not rows:
        raise ValueError(f"{label} requires at least one entry.")
    if len(rows) > limit:
        raise ValueError(f"{label} may contain at most {limit} entries.")
    return rows


def _tokens(path: str) -> list[str | int]:
    text = path.strip()
    if text in {"", "$"}:
        return []
    if text.startswith("$."):
        text = text[2:]
    elif text.startswith("$"):
        text = text[1:]
    tokens: list[str | int] = []
    position = 0
    for match in _PATH_TOKEN.finditer(text):
        if match.start() != position:
            raise ValueError(f"Unsupported JSON path syntax: {path}")
        key, index = match.groups()
        tokens.append(int(index) if index is not None else str(key))
        position = match.end()
    if position != len(text):
        raise ValueError(f"Unsupported JSON path syntax: {path}")
    return tokens


def _resolve(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    try:
        for token in _tokens(path):
            if isinstance(token, int):
                if not isinstance(current, list) or token < 0 or token >= len(current):
                    return False, None
                current = current[token]
            else:
                if not isinstance(current, dict) or token not in current:
                    return False, None
                current = current[token]
    except ValueError:
        return False, None
    return True, current


def _relative(value: Any, field: str) -> tuple[bool, Any]:
    return _resolve(value, field)


def validate_semantic_validators(value: Any, label: str) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array.")
    if len(value) > MAX_VALIDATORS:
        raise ValueError(f"{label} may contain at most {MAX_VALIDATORS} validators.")
    ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"{label}[{index}] must be an object.")
        validator_id = _required(raw.get("validator_id"), f"{label}[{index}].validator_id")
        if validator_id in ids:
            raise ValueError(f"Duplicate semantic validator_id: {validator_id}")
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in validator_id):
            raise ValueError("semantic validator_id may contain only lowercase letters, numbers, hyphens, and underscores.")
        ids.add(validator_id)
        kind = str(raw.get("kind", "")).strip().lower()
        if kind not in VALIDATOR_KINDS:
            raise ValueError(f"{label}[{index}].kind must be one of {sorted(VALIDATOR_KINDS)}.")
        path = _required(raw.get("path", "$"), f"{label}[{index}].path")
        _tokens(path)
        row: dict[str, Any] = {"validator_id": validator_id, "kind": kind, "path": path}
        if kind == "json-value-equals":
            if "expected" not in raw:
                raise ValueError(f"{label}[{index}] requires expected.")
            row["expected"] = raw["expected"]
        elif kind == "json-value-in":
            allowed = raw.get("allowed")
            if not isinstance(allowed, list) or not allowed:
                raise ValueError(f"{label}[{index}].allowed must be a non-empty array.")
            if len(allowed) > 30:
                raise ValueError(f"{label}[{index}].allowed may contain at most 30 entries.")
            row["allowed"] = allowed
        elif kind == "json-array-count":
            bounds = {}
            for key in ("equals", "minimum", "maximum"):
                if key in raw:
                    number = raw[key]
                    if not isinstance(number, int) or number < 0:
                        raise ValueError(f"{label}[{index}].{key} must be a non-negative integer.")
                    bounds[key] = number
            if not bounds:
                raise ValueError(f"{label}[{index}] requires equals, minimum, or maximum.")
            if "minimum" in bounds and "maximum" in bounds and bounds["minimum"] > bounds["maximum"]:
                raise ValueError(f"{label}[{index}] minimum cannot exceed maximum.")
            row.update(bounds)
        elif kind == "json-array-unique":
            field = _required(raw.get("field"), f"{label}[{index}].field")
            _tokens(field)
            row["field"] = field
        elif kind == "json-array-all-have-fields":
            fields = _string_list(raw.get("fields"), f"{label}[{index}].fields", required=True, limit=20)
            for field in fields:
                _tokens(field)
            row["fields"] = fields
        elif kind == "json-array-none-equals":
            field = _required(raw.get("field"), f"{label}[{index}].field")
            _tokens(field)
            if "value" not in raw:
                raise ValueError(f"{label}[{index}] requires value.")
            row["field"] = field
            row["value"] = raw["value"]
        elif kind == "json-array-values-in":
            field = _required(raw.get("field"), f"{label}[{index}].field")
            _tokens(field)
            allowed = raw.get("allowed")
            if not isinstance(allowed, list) or not allowed:
                raise ValueError(f"{label}[{index}].allowed must be a non-empty array.")
            if len(allowed) > 30:
                raise ValueError(f"{label}[{index}].allowed may contain at most 30 entries.")
            row["field"] = field
            row["allowed"] = allowed
        elif kind == "json-array-references-exist":
            field = _required(raw.get("field"), f"{label}[{index}].field")
            target_path = _required(raw.get("target_path"), f"{label}[{index}].target_path")
            target_field = _required(raw.get("target_field"), f"{label}[{index}].target_field")
            _tokens(field)
            _tokens(target_path)
            _tokens(target_field)
            row["field"] = field
            row["target_path"] = target_path
            row["target_field"] = target_field
        rows.append(row)
    return rows


def load_snapshot(path: Path) -> Any:
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"Semantic state snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Semantic state snapshot is not valid UTF-8 JSON: {path.name}: {exc}") from exc


def evaluate_semantic_validators(path: Path, validators: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        document = load_snapshot(path)
    except ValueError as exc:
        return {"status": "FAIL", "passed": 0, "failed": len(validators) or 1, "results": [], "reason": str(exc)}
    results: list[dict[str, Any]] = []
    passed = 0
    for validator in validators:
        validator_id = str(validator.get("validator_id", "unknown"))
        kind = str(validator.get("kind", ""))
        path_text = str(validator.get("path", "$"))
        exists, observed = _resolve(document, path_text)
        ok = True
        reason = ""
        if kind == "json-path-exists":
            ok = exists
            reason = "path exists" if ok else "path is missing"
        elif not exists:
            ok = False
            reason = "path is missing"
        elif kind == "json-value-equals":
            ok = observed == validator.get("expected")
            reason = "value matches" if ok else "value does not match"
        elif kind == "json-value-in":
            ok = observed in validator.get("allowed", [])
            reason = "value is allowed" if ok else "value is not allowed"
        elif kind == "json-array-count":
            if not isinstance(observed, list):
                ok = False
                reason = "path is not an array"
            else:
                count = len(observed)
                if "equals" in validator and count != validator["equals"]:
                    ok = False
                if "minimum" in validator and count < validator["minimum"]:
                    ok = False
                if "maximum" in validator and count > validator["maximum"]:
                    ok = False
                reason = f"array count {count} satisfies bounds" if ok else f"array count {count} violates bounds"
        elif kind == "json-array-unique":
            if not isinstance(observed, list):
                ok = False
                reason = "path is not an array"
            else:
                values: list[str] = []
                missing = False
                for item in observed:
                    found, value = _relative(item, str(validator.get("field", "")))
                    if not found:
                        missing = True
                        break
                    values.append(json.dumps(value, sort_keys=True, ensure_ascii=False))
                ok = not missing and len(values) == len(set(values))
                reason = "array field values are unique" if ok else ("array item is missing the unique field" if missing else "array field contains duplicates")
        elif kind == "json-array-all-have-fields":
            if not isinstance(observed, list):
                ok = False
                reason = "path is not an array"
            else:
                fields = [str(item) for item in validator.get("fields", [])]
                ok = all(all(_relative(item, field)[0] for field in fields) for item in observed)
                reason = "all array items contain required fields" if ok else "one or more array items are missing required fields"
        elif kind == "json-array-none-equals":
            if not isinstance(observed, list):
                ok = False
                reason = "path is not an array"
            else:
                field = str(validator.get("field", ""))
                forbidden = validator.get("value")
                ok = True
                for item in observed:
                    found, value = _relative(item, field)
                    if not found or value == forbidden:
                        ok = False
                        break
                reason = "no array item contains the forbidden value" if ok else "an array item is missing the field or contains the forbidden value"
        elif kind == "json-array-values-in":
            if not isinstance(observed, list):
                ok = False
                reason = "path is not an array"
            else:
                field = str(validator.get("field", ""))
                allowed = validator.get("allowed", [])
                ok = True
                for item in observed:
                    found, value = _relative(item, field)
                    if not found or value not in allowed:
                        ok = False
                        break
                reason = "all array field values are allowed" if ok else "an array item is missing the field or contains a value outside the allowed set"
        elif kind == "json-array-references-exist":
            if not isinstance(observed, list):
                ok = False
                reason = "path is not an array"
            else:
                target_exists, target_rows = _resolve(document, str(validator.get("target_path", "")))
                if not target_exists or not isinstance(target_rows, list):
                    ok = False
                    reason = "target path is missing or is not an array"
                else:
                    target_field = str(validator.get("target_field", ""))
                    target_values: set[str] = set()
                    target_missing = False
                    for target in target_rows:
                        found, value = _relative(target, target_field)
                        if not found:
                            target_missing = True
                            break
                        target_values.add(json.dumps(value, sort_keys=True, ensure_ascii=False))
                    source_field = str(validator.get("field", ""))
                    source_missing = False
                    dangling = False
                    if not target_missing:
                        for item in observed:
                            found, value = _relative(item, source_field)
                            if not found:
                                source_missing = True
                                break
                            if json.dumps(value, sort_keys=True, ensure_ascii=False) not in target_values:
                                dangling = True
                                break
                    ok = not target_missing and not source_missing and not dangling
                    if ok:
                        reason = "all array references resolve to the target set"
                    elif target_missing:
                        reason = "a target array item is missing the target field"
                    elif source_missing:
                        reason = "a source array item is missing the reference field"
                    else:
                        reason = "one or more array references do not resolve to the target set"
        else:
            ok = False
            reason = "unsupported validator kind"
        if ok:
            passed += 1
        results.append({"validator_id": validator_id, "kind": kind, "status": "PASS" if ok else "FAIL", "reason": reason})
    failed = len(results) - passed
    return {
        "status": "PASS" if failed == 0 else "FAIL",
        "passed": passed,
        "failed": failed,
        "results": results,
        "reason": "" if failed == 0 else f"{failed} semantic validator(s) failed",
    }

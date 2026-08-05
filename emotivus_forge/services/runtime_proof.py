from __future__ import annotations

import hashlib
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..core.common import normalize_rel, utc_now
from ..core.truth import TruthRecord, normalize_verification_tier

_SAFE_HEADER_NAMES = {"accept", "accept-language", "user-agent"}
_BLOCKED_HEADER_NAMES = {"authorization", "cookie", "proxy-authorization", "x-api-key"}


def _origin(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Runtime-proof recipe URLs must use absolute http or https URLs.")
    if parsed.username or parsed.password:
        raise ValueError("Runtime-proof recipe URLs may not contain credentials.")
    host = parsed.hostname.lower()
    port = parsed.port
    default_port = 80 if parsed.scheme == "http" else 443
    suffix = f":{port}" if port and port != default_port else ""
    return f"{parsed.scheme}://{host}{suffix}"


def _safe_headers(raw: Any) -> dict[str, str]:
    if raw in (None, {}):
        return {"User-Agent": "Emotivus-Forge-Runtime-Proof/1"}
    if not isinstance(raw, dict):
        raise ValueError("request.headers must be an object.")
    headers: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        lowered = name.casefold()
        text = str(value).strip()
        if lowered in _BLOCKED_HEADER_NAMES or lowered not in _SAFE_HEADER_NAMES:
            raise ValueError(f"Runtime-proof recipe header is not permitted: {name}")
        if "\r" in text or "\n" in text:
            raise ValueError("Runtime-proof recipe headers may not contain line breaks.")
        headers[name] = text
    headers.setdefault("User-Agent", "Emotivus-Forge-Runtime-Proof/1")
    return headers


def _string_list(value: Any, label: str, *, required: bool = False, limit: int = 20) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array.")
    rows = []
    for item in value:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    if required and not rows:
        raise ValueError(f"{label} requires at least one entry.")
    if len(rows) > limit:
        raise ValueError(f"{label} may contain at most {limit} entries.")
    return rows


def validate_runtime_recipe(raw: Any, *, allowed_origins: list[str], source: str = "") -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise ValueError("Runtime-proof recipe must be an object using schema 1.")
    recipe_id = str(raw.get("recipe_id", "")).strip()
    if not recipe_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in recipe_id):
        raise ValueError("Runtime-proof recipe_id must use letters, numbers, dash, underscore, or dot.")
    title = str(raw.get("title", "")).strip()
    if len(title) < 8:
        raise ValueError("Runtime-proof recipe requires a descriptive title.")
    tier = normalize_verification_tier(raw.get("verification_tier"), default="sandbox")
    if tier in {"headless", "emulator", "dev_device"}:
        raise ValueError("HTTP runtime recipes cannot claim headless, emulator, or device execution tiers.")

    request = raw.get("request")
    if not isinstance(request, dict):
        raise ValueError("Runtime-proof recipe requires a request object.")
    method = str(request.get("method", "GET")).strip().upper()
    if method != "GET":
        raise ValueError("The active Runtime Proof service supports GET requests only.")
    url = str(request.get("url", "")).strip()
    origin = _origin(url)
    normalized_allowed = sorted({_origin(value) for value in allowed_origins})
    if origin not in normalized_allowed:
        raise ValueError(f"Runtime-proof recipe origin is not allowed by the activation contract: {origin}")
    timeout_seconds = request.get("timeout_seconds", 5)
    max_response_bytes = request.get("max_response_bytes", 262_144)
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 15:
        raise ValueError("request.timeout_seconds must be an integer from 1 to 15.")
    if not isinstance(max_response_bytes, int) or not 256 <= max_response_bytes <= 2_000_000:
        raise ValueError("request.max_response_bytes must be an integer from 256 to 2000000.")
    headers = _safe_headers(request.get("headers", {}))

    assertions = raw.get("assertions")
    if not isinstance(assertions, dict):
        raise ValueError("Runtime-proof recipe requires an assertions object.")
    statuses = assertions.get("status_in")
    if not isinstance(statuses, list) or not statuses:
        raise ValueError("assertions.status_in requires at least one HTTP status.")
    status_in = []
    for item in statuses:
        if not isinstance(item, int) or not 100 <= item <= 599:
            raise ValueError("assertions.status_in values must be integers from 100 to 599.")
        if item not in status_in:
            status_in.append(item)
    min_bytes = assertions.get("min_bytes")
    if not isinstance(min_bytes, int) or not 64 <= min_bytes <= max_response_bytes:
        raise ValueError("assertions.min_bytes must be an integer from 64 to request.max_response_bytes.")
    must_contain = _string_list(assertions.get("must_contain"), "assertions.must_contain", required=True)
    must_not_contain = _string_list(assertions.get("must_not_contain"), "assertions.must_not_contain")
    content_type_in = [value.casefold() for value in _string_list(assertions.get("content_type_in"), "assertions.content_type_in", required=True, limit=10)]
    exclusions = _string_list(raw.get("exclusions"), "exclusions", required=True, limit=20)

    return {
        "schema": 1,
        "recipe_id": recipe_id,
        "title": title,
        "verification_tier": tier,
        "request": {
            "method": method,
            "url": url,
            "origin": origin,
            "timeout_seconds": timeout_seconds,
            "max_response_bytes": max_response_bytes,
            "headers": headers,
        },
        "assertions": {
            "status_in": sorted(status_in),
            "min_bytes": min_bytes,
            "must_contain": must_contain,
            "must_not_contain": must_not_contain,
            "content_type_in": content_type_in,
        },
        "exclusions": exclusions,
        "source": source,
    }


class _OriginBoundRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_origins: set[str]) -> None:
        super().__init__()
        self.allowed_origins = allowed_origins

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> urllib.request.Request | None:
        target = urllib.parse.urljoin(req.full_url, newurl)
        if _origin(target) not in self.allowed_origins:
            raise urllib.error.URLError("redirect target is outside the activation contract allowed origins")
        return super().redirect_request(req, fp, code, msg, headers, target)


def _finding(recipe_id: str, severity: str, message: str, source: str) -> dict[str, Any]:
    return {
        "check": "capability.runtime-proof",
        "severity": severity,
        "path": source or ".",
        "line": 0,
        "message": f"{recipe_id}: {message}",
    }


def _execute_recipe(recipe: dict[str, Any], allowed_origins: set[str], deadline: float) -> dict[str, Any]:
    started = time.monotonic()
    request_spec = recipe["request"]
    assertions = recipe["assertions"]
    remaining = deadline - started
    if remaining <= 0:
        return {
            "recipe_id": recipe["recipe_id"],
            "title": recipe["title"],
            "status": "BLOCKED",
            "reason": "The capability runtime budget was exhausted before this recipe began.",
            "attempted": False,
            "truth_state": "BLOCKED_UNATTEMPTED",
            "verification_tier": recipe["verification_tier"],
            "source": recipe["source"],
            "findings": [_finding(recipe["recipe_id"], "blocker", "runtime budget exhausted before request", recipe["source"])],
        }
    timeout = min(float(request_spec["timeout_seconds"]), remaining)
    request = urllib.request.Request(request_spec["url"], method="GET", headers=request_spec["headers"])
    opener = urllib.request.build_opener(_OriginBoundRedirectHandler(allowed_origins))
    observed: dict[str, Any] = {}
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            final_url = response.geturl()
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().casefold()
            limit = int(request_spec["max_response_bytes"])
            body = response.read(limit + 1)
            exceeded = len(body) > limit
            if exceeded:
                body = body[:limit]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, OSError) as exc:
        reason = f"HTTP request could not complete: {exc}"
        return {
            "recipe_id": recipe["recipe_id"],
            "title": recipe["title"],
            "status": "BLOCKED",
            "reason": reason,
            "attempted": True,
            "truth_state": "BLOCKED_ATTEMPTED",
            "verification_tier": recipe["verification_tier"],
            "source": recipe["source"],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "findings": [_finding(recipe["recipe_id"], "blocker", reason, recipe["source"])],
        }

    text = body.decode("utf-8", errors="replace")
    observed = {
        "status": status,
        "final_url": final_url,
        "origin": _origin(final_url),
        "content_type": content_type,
        "bytes": len(body),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "response_truncated": exceeded,
    }
    failures: list[str] = []
    if observed["origin"] not in allowed_origins:
        failures.append("final response origin is outside the activation contract")
    if status not in assertions["status_in"]:
        failures.append(f"HTTP status {status} was not in {assertions['status_in']}")
    if exceeded:
        failures.append(f"response exceeded the {request_spec['max_response_bytes']} byte budget")
    if len(body) < assertions["min_bytes"]:
        failures.append(f"response contained {len(body)} bytes; minimum is {assertions['min_bytes']}")
    if not any(content_type == allowed or content_type.startswith(allowed + "/") for allowed in assertions["content_type_in"]):
        failures.append(f"content type {content_type or '(missing)'} was not in {assertions['content_type_in']}")
    for marker in assertions["must_contain"]:
        if marker not in text:
            failures.append(f"required marker was absent: {marker}")
    for marker in assertions["must_not_contain"]:
        if marker in text:
            failures.append(f"forbidden marker was present: {marker}")

    status_text = "FAIL" if failures else "PASS"
    truth_state = "CONTRADICTED" if failures else "OBSERVED"
    findings = [_finding(recipe["recipe_id"], "blocker", message, recipe["source"]) for message in failures]
    return {
        "recipe_id": recipe["recipe_id"],
        "title": recipe["title"],
        "status": status_text,
        "reason": "; ".join(failures),
        "attempted": True,
        "truth_state": truth_state,
        "verification_tier": recipe["verification_tier"],
        "source": recipe["source"],
        "observed": observed,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "findings": findings,
    }


def run_runtime_proof(project_root: Path, activation: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    project_root = project_root.resolve()
    contract = activation.get("contract", {}) if isinstance(activation.get("contract"), dict) else {}
    budget = contract.get("budget", {}) if isinstance(contract.get("budget"), dict) else {}
    runtime_spec = contract.get("runtime_proof", {}) if isinstance(contract.get("runtime_proof"), dict) else {}
    allowed_origins = {_origin(value) for value in runtime_spec.get("allowed_origins", [])}
    recipe_rows = runtime_spec.get("recipes", []) if isinstance(runtime_spec.get("recipes"), list) else []
    runtime_seconds = int(budget.get("runtime_seconds", 10))
    deadline = started + runtime_seconds

    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    truth_records: list[dict[str, Any]] = []
    for row in recipe_rows:
        if not isinstance(row, dict):
            continue
        recipe = row.get("recipe") if isinstance(row.get("recipe"), dict) else {}
        result = _execute_recipe(recipe, allowed_origins, deadline)
        evaluations.append(result)
        findings.extend(item for item in result.get("findings", []) if isinstance(item, dict))
        truth_records.append(TruthRecord(
            subject=f"runtime-proof:{result.get('recipe_id', 'unknown')}",
            truth_state=str(result.get("truth_state", "UNKNOWN")),
            result=str(result.get("status", "UNKNOWN")),
            verification_tier=str(result.get("verification_tier", "sandbox")),
            attempted=bool(result.get("attempted", False)),
            reason=(
                "The bounded HTTP response satisfied status, content type, minimum size, required-marker, forbidden-marker, origin, and response-budget assertions."
                if result.get("status") == "PASS" else str(result.get("reason", "Runtime recipe did not complete."))
            ),
            source=str(result.get("source", "")),
            exclusions=tuple(str(item) for item in recipe.get("exclusions", []) if str(item).strip()),
        ).to_dict())

    counts = {name: sum(1 for row in evaluations if row.get("status") == name) for name in ("PASS", "FAIL", "BLOCKED")}
    status = "FAIL" if counts["FAIL"] or counts["BLOCKED"] else "PASS"
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "schema": 1,
        "capability_id": "runtime-proof",
        "status": status,
        "mode": "content-aware-http",
        "generated_utc": utc_now(),
        "recipe_count": len(evaluations),
        "counts": counts,
        "evaluations": evaluations,
        "findings": findings,
        "truth_records": truth_records,
        "budget": {
            "runtime_seconds": runtime_seconds,
            "duration_ms": duration_ms,
            "budget_exhausted": time.monotonic() >= deadline,
            "max_recipe_count": int(budget.get("file_limit", 1)),
        },
        "actions_taken": [],
        "repairs_allowed": False,
        "credentials_allowed": False,
        "javascript_executed": False,
        "legacy_vault_loaded": False,
        "truth_boundary": (
            "This capability proves only the listed HTTP response assertions at the project-declared target tier. "
            "It does not execute JavaScript, inspect visual layout, authenticate, prove database state, prove deployment completeness, or certify release readiness."
        ),
    }

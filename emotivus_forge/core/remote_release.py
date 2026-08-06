from __future__ import annotations

import hashlib
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .. import __version__

REMOTE_VERIFICATION_SCHEMA = 1
_DEFAULT_TIMEOUT_SECONDS = 15
_MAX_TIMEOUT_SECONDS = 120
_DEFAULT_MAX_ARTIFACT_BYTES = 250_000_000
_MAX_CHANNELS = 10


class _RemoteContradictionError(Exception):
    """A remote response violated an authority-approved verification boundary."""


def _origin(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(str(raw_url).strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    if scheme != "https" or not hostname or parsed.username or parsed.password:
        raise ValueError("Remote release verification URLs must be credential-free https:// URLs.")
    port = parsed.port
    netloc = hostname if port in {None, 443} else f"{hostname}:{port}"
    return f"https://{netloc}"


def validate_remote_verification(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("remote_verification must be an object when provided.")
    if raw.get("schema", REMOTE_VERIFICATION_SCHEMA) != REMOTE_VERIFICATION_SCHEMA:
        raise ValueError("remote_verification must use schema 1.")
    allowed_raw = raw.get("allowed_origins")
    if not isinstance(allowed_raw, list) or not allowed_raw:
        raise ValueError("remote_verification.allowed_origins must be a non-empty array.")
    allowed_origins: list[str] = []
    for value in allowed_raw:
        origin = _origin(str(value))
        if str(value).strip().rstrip("/") != origin:
            raise ValueError("remote_verification.allowed_origins entries must be exact HTTPS origins without paths, queries, or fragments.")
        if origin not in allowed_origins:
            allowed_origins.append(origin)
    timeout = raw.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1 or timeout > _MAX_TIMEOUT_SECONDS:
        raise ValueError(f"remote_verification.timeout_seconds must be an integer from 1 to {_MAX_TIMEOUT_SECONDS}.")
    maximum = raw.get("max_artifact_bytes", _DEFAULT_MAX_ARTIFACT_BYTES)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1 or maximum > 2_000_000_000:
        raise ValueError("remote_verification.max_artifact_bytes must be an integer from 1 to 2000000000.")
    user_agent = str(raw.get("user_agent", f"Emotivus-Forge/{__version__}")).strip()
    if not user_agent or len(user_agent) > 160 or "\r" in user_agent or "\n" in user_agent:
        raise ValueError("remote_verification.user_agent must be a single non-empty line of at most 160 characters.")
    truth_boundary = str(raw.get("truth_boundary", "")).strip()
    if len(truth_boundary) < 80:
        raise ValueError("remote_verification.truth_boundary must contain at least 80 characters.")
    return {
        "schema": 1,
        "allowed_origins": allowed_origins,
        "timeout_seconds": timeout,
        "max_artifact_bytes": maximum,
        "user_agent": user_agent,
        "truth_boundary": truth_boundary,
    }


class _AllowedOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_origins: set[str]) -> None:
        super().__init__()
        self.allowed_origins = allowed_origins

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> urllib.request.Request | None:
        target = urllib.parse.urljoin(req.full_url, newurl)
        if _origin(target) not in self.allowed_origins:
            raise _RemoteContradictionError("Redirect target is outside the authority-approved remote origins.")
        return super().redirect_request(req, fp, code, msg, headers, target)


def _result(channel_id: str, uri: str, status: str, reason: str, *, attempted: bool, started: float, observed: dict[str, Any] | None = None) -> dict[str, Any]:
    truth_state = {
        "PASS": "OBSERVED",
        "FAIL": "CONTRADICTED",
        "BLOCKED": "BLOCKED_ATTEMPTED" if attempted else "BLOCKED_UNATTEMPTED",
    }.get(status, "UNKNOWN")
    return {
        "channel_id": channel_id,
        "artifact_uri": uri,
        "status": status,
        "truth_state": truth_state,
        "attempted": attempted,
        "reason": reason,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "observed": observed or {},
    }


def _fetch_channel(
    channel_id: str,
    uri: str,
    *,
    expected_sha256: str,
    expected_bytes: int,
    contract: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    allowed_origins = set(contract["allowed_origins"])
    try:
        source_origin = _origin(uri)
    except ValueError as exc:
        return _result(channel_id, uri, "FAIL", str(exc), attempted=False, started=started)
    if source_origin not in allowed_origins:
        return _result(channel_id, uri, "FAIL", "Signed manifest artifact URI is outside the authority-approved remote origins.", attempted=False, started=started)
    maximum = int(contract["max_artifact_bytes"])
    if expected_bytes < 1:
        return _result(channel_id, uri, "FAIL", "Exact local package byte length is unavailable.", attempted=False, started=started)
    if expected_bytes > maximum:
        return _result(
            channel_id,
            uri,
            "BLOCKED",
            f"Exact package is {expected_bytes} bytes, exceeding the authority-approved remote retrieval budget of {maximum} bytes.",
            attempted=False,
            started=started,
        )
    request = urllib.request.Request(uri, method="GET", headers={"User-Agent": str(contract["user_agent"]), "Accept": "application/octet-stream,*/*;q=0.1"})
    opener = urllib.request.build_opener(_AllowedOriginRedirectHandler(allowed_origins))
    digest = hashlib.sha256()
    count = 0
    try:
        with opener.open(request, timeout=int(contract["timeout_seconds"])) as response:
            status_code = int(getattr(response, "status", response.getcode()))
            final_url = str(response.geturl())
            final_origin = _origin(final_url)
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().casefold()
            content_length_raw = str(response.headers.get("Content-Length", "")).strip()
            while True:
                chunk = response.read(min(1024 * 1024, expected_bytes + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                digest.update(chunk)
                if count > expected_bytes:
                    break
    except _RemoteContradictionError as exc:
        return _result(channel_id, uri, "FAIL", str(exc), attempted=True, started=started)
    except urllib.error.HTTPError as exc:
        return _result(channel_id, uri, "FAIL", f"Remote channel returned HTTP {exc.code}.", attempted=True, started=started, observed={"http_status": int(exc.code)})
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
        return _result(channel_id, uri, "BLOCKED", f"Remote artifact retrieval could not complete: {exc}", attempted=True, started=started)

    observed_sha = digest.hexdigest()
    observed = {
        "http_status": status_code,
        "final_url": final_url,
        "final_origin": final_origin,
        "content_type": content_type,
        "content_length_header": content_length_raw,
        "retrieved_bytes": count,
        "retrieved_sha256": observed_sha,
        "response_body_retained": False,
        "tls_required": True,
    }
    failures: list[str] = []
    if status_code != 200:
        failures.append(f"HTTP status {status_code} is not 200")
    if final_origin not in allowed_origins:
        failures.append("final response origin is outside the authority-approved remote origins")
    if content_length_raw:
        try:
            if int(content_length_raw) != expected_bytes:
                failures.append(f"Content-Length {content_length_raw} does not match exact package bytes {expected_bytes}")
        except ValueError:
            failures.append("Content-Length is not a valid integer")
    if count != expected_bytes:
        failures.append(f"retrieved {count} bytes instead of exact package length {expected_bytes}")
    if observed_sha != expected_sha256:
        failures.append("retrieved artifact digest does not match the exact final package")
    if failures:
        return _result(channel_id, uri, "FAIL", "; ".join(failures) + ".", attempted=True, started=started, observed=observed)
    return _result(
        channel_id,
        uri,
        "PASS",
        "A fresh HTTPS GET retrieved bytes identical to the exact final package without retaining the response body.",
        attempted=True,
        started=started,
        observed=observed,
    )


def verify_remote_channels(
    manifest_channels: dict[str, dict[str, Any]],
    required_channels: list[str],
    *,
    expected_sha256: str,
    expected_bytes: int,
    contract: dict[str, Any],
) -> dict[str, Any]:
    if len(required_channels) > _MAX_CHANNELS:
        return {
            "status": "BLOCKED",
            "configured": True,
            "attempted": False,
            "required": required_channels,
            "passed": [],
            "failed": [],
            "blocked": required_channels,
            "evaluations": [],
            "reason": f"Remote verification supports at most {_MAX_CHANNELS} required channels per Ship assessment.",
            "truth_boundary": contract["truth_boundary"],
        }
    evaluations: list[dict[str, Any]] = []
    for channel_id in required_channels:
        row = manifest_channels.get(channel_id, {})
        uri = str(row.get("artifact_uri", "")).strip()
        if not row or not uri:
            evaluations.append({
                "channel_id": channel_id,
                "artifact_uri": uri,
                "status": "FAIL",
                "truth_state": "CONTRADICTED",
                "attempted": False,
                "reason": "Required channel is absent from the verified signed manifest.",
                "duration_ms": 0,
                "observed": {},
            })
            continue
        if str(row.get("artifact_sha256", "")) != expected_sha256:
            evaluations.append({
                "channel_id": channel_id,
                "artifact_uri": uri,
                "status": "FAIL",
                "truth_state": "CONTRADICTED",
                "attempted": False,
                "reason": "Signed manifest channel digest does not match the exact final package.",
                "duration_ms": 0,
                "observed": {},
            })
            continue
        evaluations.append(_fetch_channel(
            channel_id,
            uri,
            expected_sha256=expected_sha256,
            expected_bytes=expected_bytes,
            contract=contract,
        ))
    passed = [str(row["channel_id"]) for row in evaluations if row.get("status") == "PASS"]
    failed = [str(row["channel_id"]) for row in evaluations if row.get("status") == "FAIL"]
    blocked = [str(row["channel_id"]) for row in evaluations if row.get("status") == "BLOCKED"]
    status = "FAIL" if failed else "BLOCKED" if blocked else "PASS" if evaluations and len(passed) == len(required_channels) else "NOT_RUN"
    return {
        "schema": 1,
        "status": status,
        "configured": True,
        "attempted": any(bool(row.get("attempted")) for row in evaluations),
        "required": required_channels,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "evaluations": evaluations,
        "reason": (
            "Every required signed-manifest channel returned exact package bytes through a fresh bounded HTTPS GET."
            if status == "PASS" else
            "One or more remote channels contradicted the exact package binding."
            if status == "FAIL" else
            "One or more remote channel retrievals could not complete."
            if status == "BLOCKED" else
            "Remote verification did not run."
        ),
        "truth_boundary": contract["truth_boundary"],
    }

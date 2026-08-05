"""Bounded browser-executed evidence for one exact static website package.

The instrument intentionally uses an operator-supplied Chromium-family executable through an
explicit optional Playwright driver. It loads exact HTML and package-relative resources from a safely
extracted website ZIP under network-isolated routing, captures rendered DOM and PNG screenshots for
a fixed route/profile matrix, and emits a content-addressed receipt. A PASS is local browser viewport
evidence only: it is not a physical-device test, accessibility audit, manual visual review,
HTTP-server or production-origin check, independent review, release authorization, or release readiness.
"""
from __future__ import annotations

from .common import (
    canonical_bytes,
    pretty_bytes,
    sha256_bytes,
    sha256_file,
    member_is_symlink as _zip_symlink,
)

import argparse
import hashlib
import json
import mimetypes
import os
import platform
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit

SCHEMA = "forge-browser-viewport-evidence/1"
BUNDLE_SCHEMA = "forge-browser-evidence-bundle/1"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_MEMBERS = 500
MAX_MEMBER_BYTES = 50_000_000
MAX_TOTAL_BYTES = 150_000_000
MAX_DOM_BYTES = 8_000_000
DEFAULT_TIMEOUT_SECONDS = 45

TRUTH_BOUNDARY = (
    "This receipt proves that one named local Chromium-family executable rendered exact HTML and "
    "package-relative resources from the recorded website ZIP under network-isolated package routing, "
    "viewport shapes, color-mode settings, and execution environment. It does not prove HTTP-server, "
    "production-origin, physical-device, touch-input, or assistive-technology compatibility, "
    "accessibility conformance, manual visual correctness, remote-network behavior, independent "
    "control, reviewer identity, release authorization, "
    "or release readiness."
)

DEFAULT_ROUTES = ("/", "/run/", "/docs/", "/roadmap/", "/trust/", "/changelog/")
DEFAULT_PROFILES = (
    {"id": "desktop-light", "width": 1440, "height": 900, "color_scheme": "light", "mobile_claimed": False},
    {"id": "mobile-dark", "width": 390, "height": 844, "color_scheme": "dark", "mobile_claimed": False},
)


class BrowserEvidenceError(ValueError):
    """Raised when browser evidence cannot be produced or trusted."""


@dataclass(frozen=True)
class WebsiteIdentity:
    filename: str
    sha256: str
    bytes: int
    member_count: int



def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()




def inspect_website_zip(path: Path) -> tuple[WebsiteIdentity, list[zipfile.ZipInfo]]:
    path = path.resolve()
    if not path.is_file():
        raise BrowserEvidenceError(f"website ZIP is missing: {path}")
    infos: list[zipfile.ZipInfo]
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BrowserEvidenceError("website ZIP contains duplicate member names")
            if not infos or len(infos) > MAX_MEMBERS:
                raise BrowserEvidenceError("website ZIP member count is outside the bounded range")
            total = 0
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                parts = PurePosixPath(normalized).parts
                if info.is_dir():
                    continue
                if not normalized or normalized.startswith("/") or ".." in parts:
                    raise BrowserEvidenceError(f"website ZIP contains an unsafe path: {info.filename}")
                if info.flag_bits & 0x1:
                    raise BrowserEvidenceError(f"website ZIP contains an encrypted member: {info.filename}")
                if _zip_symlink(info):
                    raise BrowserEvidenceError(f"website ZIP contains a symlink: {info.filename}")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise BrowserEvidenceError(f"website ZIP member exceeds the byte budget: {info.filename}")
                total += info.file_size
                if total > MAX_TOTAL_BYTES:
                    raise BrowserEvidenceError("website ZIP exceeds the total uncompressed byte budget")
            required = {"index.html", "assets/styles.css", "downloads/RUN-FORGE.zip"}
            missing = sorted(required - set(names))
            if missing:
                raise BrowserEvidenceError(f"website ZIP is missing required members: {missing}")
            bad = archive.testzip()
            if bad:
                raise BrowserEvidenceError(f"website ZIP CRC verification failed at {bad}")
    except zipfile.BadZipFile as exc:
        raise BrowserEvidenceError(f"website ZIP is invalid: {exc}") from exc
    return WebsiteIdentity(path.name, sha256_file(path), path.stat().st_size, len(infos)), infos


def extract_website_zip(path: Path, destination: Path) -> WebsiteIdentity:
    identity, _ = inspect_website_zip(path)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(destination)
    return identity


def _png_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 24 or content[:8] != b"\x89PNG\r\n\x1a\n" or content[12:16] != b"IHDR":
        raise BrowserEvidenceError("browser screenshot is not a valid PNG with an IHDR header")
    return struct.unpack(">II", content[16:24])


def _safe_id(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "-" for ch in value.strip().casefold()).strip("-")
    return text or "root"


def _route_slug(route: str) -> str:
    route_path = urlsplit(route).path.strip("/")
    return _safe_id(route_path.replace("/", "-")) if route_path else "home"


def normalize_routes(routes: Iterable[str]) -> list[str]:
    output: list[str] = []
    for raw in routes:
        value = str(raw).strip()
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not value.startswith("/") or ".." in PurePosixPath(parsed.path).parts:
            raise BrowserEvidenceError(f"browser evidence route must be a safe local absolute path: {raw}")
        route = parsed.path or "/"
        if parsed.query:
            route += "?" + parsed.query
        if route not in output:
            output.append(route)
    if not output:
        raise BrowserEvidenceError("browser evidence requires at least one route")
    return output


def normalize_profiles(profiles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in profiles:
        if not isinstance(raw, dict):
            raise BrowserEvidenceError("browser profile must be an object")
        profile_id = _safe_id(str(raw.get("id", "")))
        width = int(raw.get("width", 0))
        height = int(raw.get("height", 0))
        scheme = str(raw.get("color_scheme", "light")).casefold()
        if profile_id in seen:
            raise BrowserEvidenceError(f"browser profile ID is duplicated: {profile_id}")
        if width < 240 or width > 4096 or height < 240 or height > 4096:
            raise BrowserEvidenceError(f"browser profile dimensions are outside the bounded range: {profile_id}")
        if scheme not in {"light", "dark"}:
            raise BrowserEvidenceError(f"browser profile color scheme is invalid: {profile_id}")
        if raw.get("mobile_claimed") is not False:
            raise BrowserEvidenceError("viewport profiles must explicitly preserve mobile_claimed false")
        output.append({
            "id": profile_id,
            "width": width,
            "height": height,
            "color_scheme": scheme,
            "mobile_claimed": False,
        })
        seen.add(profile_id)
    if not output:
        raise BrowserEvidenceError("browser evidence requires at least one profile")
    return output


def browser_identity(browser: Path) -> dict[str, Any]:
    requested = browser.expanduser()
    resolved_text = shutil.which(str(requested)) if not requested.is_absolute() else str(requested)
    if not resolved_text:
        raise BrowserEvidenceError(f"browser executable was not found: {browser}")
    resolved = Path(resolved_text).resolve()
    if not resolved.is_file():
        raise BrowserEvidenceError(f"browser executable is not a regular file: {resolved}")
    try:
        process = subprocess.run(
            [str(resolved), "--version"], text=True, capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BrowserEvidenceError(f"could not query browser version: {exc}") from exc
    version = (process.stdout or process.stderr).strip()
    if process.returncode != 0 or not version:
        raise BrowserEvidenceError("browser executable did not return a usable --version result")
    return {
        "requested": str(browser),
        "resolved": str(resolved),
        "sha256": sha256_file(resolved),
        "bytes": resolved.stat().st_size,
        "version_output": version[:500],
    }


def _playwright_version() -> str:
    try:
        from importlib.metadata import version
        return version("playwright")
    except Exception:
        return "unknown"


def _route_source_path(site_root: Path, route: str) -> Path:
    parsed = urlsplit(route)
    clean = parsed.path.strip("/")
    relative = Path(clean) if clean else Path()
    candidate = site_root / relative
    if parsed.path.endswith("/") or candidate.is_dir():
        candidate = candidate / "index.html"
    elif candidate.suffix == "":
        candidate = candidate / "index.html"
    candidate = candidate.resolve()
    try:
        candidate.relative_to(site_root.resolve())
    except ValueError as exc:
        raise BrowserEvidenceError(f"route source escapes the website root: {route}") from exc
    if not candidate.is_file():
        raise BrowserEvidenceError(f"route source is missing from the website package: {route}")
    return candidate


def _inject_base(html_text: str, route: str) -> str:
    parsed = urlsplit(route)
    base_path = parsed.path or "/"
    if not base_path.endswith("/"):
        base_path = base_path.rsplit("/", 1)[0] + "/"
    base = f'<base href="https://forge.package.invalid{base_path}">'
    lowered = html_text.casefold()
    index = lowered.find("<head")
    if index >= 0:
        close = html_text.find(">", index)
        if close >= 0:
            return html_text[: close + 1] + base + html_text[close + 1 :]
    return base + html_text


def _playwright_executor(
    *,
    browser: Path,
    site_root: Path,
    routes: list[str],
    profiles: list[dict[str, Any]],
    artifact_root: Path,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    """Execute exact package rendering through an optional external Playwright installation.

    Playwright is imported lazily and is not bundled with Forge. Browser URL navigation is not
    required: exact route HTML is loaded from the extracted package, package-relative requests are
    intercepted and fulfilled from that same root, and every other request is blocked and recorded.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserEvidenceError(
            "browser evidence requires an external Playwright installation; Forge does not bundle it"
        ) from exc

    launch_args = [
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-sync",
        "--metrics-recording-only",
        "--mute-audio",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        launch_args.append("--no-sandbox")
    results: list[dict[str, Any]] = []
    package_host = "forge.package.invalid"
    root = site_root.resolve()
    try:
        with sync_playwright() as driver:
            launched = driver.chromium.launch(
                executable_path=str(browser),
                headless=True,
                args=launch_args,
                timeout=timeout_seconds * 1000,
            )
            try:
                for profile in profiles:
                    context = launched.new_context(
                        viewport={"width": profile["width"], "height": profile["height"]},
                        color_scheme=profile["color_scheme"],
                        device_scale_factor=1,
                        is_mobile=False,
                        has_touch=False,
                        java_script_enabled=True,
                    )
                    try:
                        for route in routes:
                            page = context.new_page()
                            console_events: list[dict[str, str]] = []
                            page_errors: list[str] = []
                            failed_requests: list[dict[str, str]] = []
                            package_requests: list[dict[str, Any]] = []
                            external_requests: list[dict[str, str]] = []
                            page.on("console", lambda message, rows=console_events: rows.append({
                                "type": message.type,
                                "text": message.text[:2000],
                            }))
                            page.on("pageerror", lambda error, rows=page_errors: rows.append(str(error)[:4000]))
                            page.on("requestfailed", lambda request, rows=failed_requests: rows.append({
                                "url": request.url,
                                "method": request.method,
                                "failure": str(request.failure or "")[:1000],
                            }))

                            def handle_package_request(request_route: Any) -> None:
                                request = request_route.request
                                parsed = urlsplit(request.url)
                                if parsed.scheme not in {"http", "https"} or parsed.hostname != package_host:
                                    external_requests.append({"url": request.url, "method": request.method})
                                    request_route.abort("blockedbyclient")
                                    return
                                relative = parsed.path.lstrip("/")
                                candidate = (root / relative).resolve()
                                try:
                                    candidate.relative_to(root)
                                except ValueError:
                                    package_requests.append({"path": parsed.path, "status": 400, "bytes": 0})
                                    request_route.fulfill(status=400, body="unsafe package path")
                                    return
                                if candidate.is_dir():
                                    candidate = candidate / "index.html"
                                if not candidate.is_file():
                                    package_requests.append({"path": parsed.path, "status": 404, "bytes": 0})
                                    request_route.fulfill(status=404, body="missing package resource")
                                    return
                                content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                                package_requests.append({
                                    "path": parsed.path,
                                    "status": 200,
                                    "bytes": candidate.stat().st_size,
                                    "sha256": sha256_file(candidate),
                                })
                                request_route.fulfill(status=200, path=str(candidate), content_type=content_type)

                            page.route("**/*", handle_package_request)
                            source = _route_source_path(root, route)
                            source_bytes = source.read_bytes()
                            try:
                                html_text = source_bytes.decode("utf-8")
                            except UnicodeDecodeError as exc:
                                raise BrowserEvidenceError(f"route HTML is not UTF-8: {route}") from exc
                            started = time.monotonic()
                            page.set_content(
                                _inject_base(html_text, route),
                                wait_until="networkidle",
                                timeout=timeout_seconds * 1000,
                            )
                            page.wait_for_timeout(100)
                            duration_ms = int((time.monotonic() - started) * 1000)
                            dom = page.content().encode("utf-8")
                            if not dom or len(dom) > MAX_DOM_BYTES:
                                raise BrowserEvidenceError(
                                    f"rendered DOM byte length is invalid for {profile['id']} {route}"
                                )
                            screenshot = page.screenshot(type="png", full_page=False)
                            width, height = _png_dimensions(screenshot)
                            if (width, height) != (profile["width"], profile["height"]):
                                raise BrowserEvidenceError(
                                    f"screenshot dimensions differ for {profile['id']} {route}: {(width, height)}"
                                )
                            metrics = page.evaluate("""() => ({
                                title: document.title || '',
                                main_count: document.querySelectorAll('main').length,
                                h1_count: document.querySelectorAll('h1').length,
                                canonical: document.querySelector('link[rel="canonical"]')?.href || '',
                                html_lang: document.documentElement.lang || '',
                                body_text_chars: (document.body?.innerText || '').trim().length,
                                inner_width: window.innerWidth,
                                inner_height: window.innerHeight,
                                device_pixel_ratio: window.devicePixelRatio,
                                scroll_width: document.documentElement.scrollWidth,
                                scroll_height: document.documentElement.scrollHeight,
                                horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
                                prefers_dark: window.matchMedia('(prefers-color-scheme: dark)').matches,
                                ready_state: document.readyState,
                            })""")
                            problems: list[str] = []
                            bad_package = [row for row in package_requests if int(row.get("status", 0)) >= 400]
                            if bad_package:
                                problems.append("one or more package-relative browser requests failed")
                            if external_requests:
                                problems.append("one or more external network requests were attempted and blocked")
                            relevant_failed = [
                                row for row in failed_requests
                                if not any(row["url"] == external["url"] for external in external_requests)
                            ]
                            if relevant_failed:
                                problems.append("one or more package browser requests failed before fulfillment")
                            if page_errors:
                                problems.append("one or more page exceptions were observed")
                            if any(row["type"] == "error" for row in console_events):
                                problems.append("one or more console errors were observed")
                            if not metrics.get("title"):
                                problems.append("rendered DOM has no document title")
                            if metrics.get("main_count") != 1:
                                problems.append("rendered DOM must contain exactly one main element")
                            if int(metrics.get("h1_count", 0)) < 1:
                                problems.append("rendered DOM has no h1 element")
                            if int(metrics.get("body_text_chars", 0)) < 50:
                                problems.append("rendered body text is below the minimum viable size")
                            if bool(metrics.get("horizontal_overflow")):
                                problems.append("rendered page has horizontal document overflow")
                            if bool(metrics.get("prefers_dark")) != (profile["color_scheme"] == "dark"):
                                problems.append("browser color-scheme media query differs from the requested profile")
                            slug = _route_slug(route)
                            prefix = f"renders/{profile['id']}/{slug}"
                            dom_artifact = _write_artifact(artifact_root, f"{prefix}.html", dom)
                            screenshot_artifact = _write_artifact(artifact_root, f"{prefix}.png", screenshot)
                            events_content = pretty_bytes({
                                "console": console_events,
                                "page_errors": page_errors,
                                "failed_requests": failed_requests,
                                "package_requests": package_requests,
                                "external_requests_blocked": external_requests,
                            })
                            events_artifact = _write_artifact(artifact_root, f"{prefix}.events.json", events_content)
                            results.append({
                                "status": "PASS" if not problems else "FAIL",
                                "route": route,
                                "source": {
                                    "path": source.relative_to(root).as_posix(),
                                    "sha256": sha256_bytes(source_bytes),
                                    "bytes": len(source_bytes),
                                },
                                "transport": "network-isolated-package-routing",
                                "profile": dict(profile),
                                "duration_ms": duration_ms,
                                "document_source_status": 200,
                                "dom": {**dom_artifact, **metrics},
                                "screenshot": {**screenshot_artifact, "width": width, "height": height},
                                "events": {
                                    **events_artifact,
                                    "console_count": len(console_events),
                                    "console_error_count": sum(1 for row in console_events if row["type"] == "error"),
                                    "page_error_count": len(page_errors),
                                    "failed_request_count": len(relevant_failed),
                                    "package_request_count": len(package_requests),
                                    "package_error_count": len(bad_package),
                                    "external_request_count": len(external_requests),
                                },
                                "problems": problems,
                            })
                            page.close()
                    finally:
                        context.close()
            finally:
                launched.close()
    except PlaywrightTimeoutError as exc:
        raise BrowserEvidenceError(f"browser driver timed out: {exc}") from exc
    except PlaywrightError as exc:
        raise BrowserEvidenceError(f"browser driver failed: {exc}") from exc
    return results

def _environment() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
    }


def _write_artifact(root: Path, relative: str, content: bytes) -> dict[str, Any]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"path": relative, "sha256": sha256_bytes(content), "bytes": len(content)}


def _bundle_payloads(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if relative == "BUNDLE-MANIFEST.json":
            continue
        rows.append({"path": relative, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return rows


def build_evidence_bundle(source: Path, output: Path) -> dict[str, Any]:
    source = source.resolve()
    receipt_path = source / "browser-evidence.json"
    if not receipt_path.is_file():
        raise BrowserEvidenceError("browser evidence source has no browser-evidence.json receipt")
    payloads = _bundle_payloads(source)
    manifest_base = {
        "schema": BUNDLE_SCHEMA,
        "payloads": payloads,
        "truth_boundary": TRUTH_BOUNDARY,
        "release_authorized": False,
        "release_ready": False,
    }
    manifest = dict(manifest_base)
    manifest["bundle_id"] = sha256_bytes(canonical_bytes(manifest_base))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for row in payloads:
            relative = row["path"]
            info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, (source / relative).read_bytes())
        info = zipfile.ZipInfo("BUNDLE-MANIFEST.json", ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, pretty_bytes(manifest))
    temporary.replace(output)
    return {
        "schema": BUNDLE_SCHEMA,
        "bundle_id": manifest["bundle_id"],
        "output": str(output),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "payload_count": len(payloads),
    }


def verify_evidence_bundle(bundle: Path, *, expected_website_sha256: str = "") -> dict[str, Any]:
    problems: list[str] = []
    try:
        with zipfile.ZipFile(bundle) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                problems.append("bundle contains duplicate member names")
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                if normalized.startswith("/") or ".." in PurePosixPath(normalized).parts or info.flag_bits & 0x1 or _zip_symlink(info):
                    problems.append(f"bundle contains unsafe member: {info.filename}")
            if "BUNDLE-MANIFEST.json" not in names or "browser-evidence.json" not in names:
                problems.append("bundle is missing its manifest or receipt")
                return {"status": "FAIL", "problems": problems}
            manifest = json.loads(archive.read("BUNDLE-MANIFEST.json"))
            receipt = json.loads(archive.read("browser-evidence.json"))
            if manifest.get("schema") != BUNDLE_SCHEMA:
                problems.append("bundle manifest schema differs")
            base = {key: value for key, value in manifest.items() if key != "bundle_id"}
            if sha256_bytes(canonical_bytes(base)) != manifest.get("bundle_id"):
                problems.append("bundle ID differs from canonical manifest content")
            declared = manifest.get("payloads")
            if not isinstance(declared, list):
                problems.append("bundle payload list is invalid")
                declared = []
            declared_paths = {str(row.get("path", "")) for row in declared if isinstance(row, dict)}
            actual_paths = set(names) - {"BUNDLE-MANIFEST.json"}
            if declared_paths != actual_paths:
                problems.append("bundle payload membership differs")
            for row in declared:
                if not isinstance(row, dict) or row.get("path") not in actual_paths:
                    continue
                content = archive.read(str(row["path"]))
                if sha256_bytes(content) != row.get("sha256") or len(content) != row.get("bytes"):
                    problems.append(f"bundle payload identity differs: {row.get('path')}")
            if receipt.get("schema") != SCHEMA:
                problems.append("browser evidence receipt schema differs")
            receipt_base = {key: value for key, value in receipt.items() if key != "receipt_id"}
            if sha256_bytes(canonical_bytes(receipt_base)) != receipt.get("receipt_id"):
                problems.append("browser evidence receipt ID differs")
            website = receipt.get("website") if isinstance(receipt.get("website"), dict) else {}
            if expected_website_sha256 and website.get("sha256") != expected_website_sha256:
                problems.append("browser evidence website digest differs from the expected exact package")
            if receipt.get("status") != "PASS":
                problems.append("browser evidence receipt is not PASS")
            truth = receipt.get("truth") if isinstance(receipt.get("truth"), dict) else {}
            required_false = (
                "physical_device_tested", "touch_input_tested", "assistive_technology_tested",
                "accessibility_conformance_claimed", "manual_visual_reviewed", "production_origin_tested",
                "independent_reviewed", "release_authorized", "release_ready",
            )
            for key in required_false:
                if truth.get(key) is not False:
                    problems.append(f"truth flag must remain false: {key}")
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        problems.append(f"could not verify browser evidence bundle: {exc}")
    return {
        "status": "PASS" if not problems else "FAIL",
        "bundle": str(bundle),
        "sha256": sha256_file(bundle) if bundle.is_file() else "",
        "bytes": bundle.stat().st_size if bundle.is_file() else 0,
        "problems": problems,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def run_browser_evidence(
    website_zip: Path,
    browser: Path,
    output_dir: Path,
    *,
    routes: Iterable[str] = DEFAULT_ROUTES,
    profiles: Iterable[dict[str, Any]] = DEFAULT_PROFILES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    observed_at: str = "",
    bundle_output: Path | None = None,
    render_executor: Any = None,
) -> dict[str, Any]:
    website_zip = website_zip.resolve()
    output_dir = output_dir.resolve()
    route_list = normalize_routes(routes)
    profile_list = normalize_profiles(profiles)
    identity, _ = inspect_website_zip(website_zip)
    browser_record = browser_identity(browser)
    browser_record["driver"] = {"name": "playwright", "version": _playwright_version(), "bundled": False}
    resolved_browser = Path(browser_record["resolved"])
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    artifact_root = output_dir / "artifacts"
    artifact_root.mkdir()
    with tempfile.TemporaryDirectory(prefix="forge-browser-evidence-") as temp_text:
        temp = Path(temp_text)
        site_root = temp / "site"
        extract_website_zip(website_zip, site_root)
        executor = render_executor or _playwright_executor
        results = executor(
            browser=resolved_browser,
            site_root=site_root,
            routes=route_list,
            profiles=profile_list,
            artifact_root=artifact_root,
            timeout_seconds=timeout_seconds,
        )
    problems = [
        f"{row['profile']['id']} {row['route']}: {problem}"
        for row in results for problem in row.get("problems", [])
    ]
    base = {
        "schema": SCHEMA,
        "status": "PASS" if not problems else "FAIL",
        "observed_at": observed_at or utc_now(),
        "website": {
            "filename": identity.filename,
            "sha256": identity.sha256,
            "bytes": identity.bytes,
            "member_count": identity.member_count,
        },
        "browser": browser_record,
        "environment": _environment(),
        "routes": route_list,
        "profiles": profile_list,
        "render_count": len(results),
        "renders": results,
        "problems": problems,
        "truth": {
            "exact_website_bound": True,
            "browser_executed": True,
            "loopback_only_serving": False,
            "network_isolated_package_routing": True,
            "http_server_executed": False,
            "rendered_dom_captured": True,
            "screenshots_captured": True,
            "physical_device_tested": False,
            "touch_input_tested": False,
            "assistive_technology_tested": False,
            "accessibility_conformance_claimed": False,
            "manual_visual_reviewed": False,
            "production_origin_tested": False,
            "independent_reviewed": False,
            "release_authorized": False,
            "release_ready": False,
        },
        "truth_boundary": TRUTH_BOUNDARY,
    }
    receipt = dict(base)
    receipt["receipt_id"] = sha256_bytes(canonical_bytes(base))
    (output_dir / "browser-evidence.json").write_bytes(pretty_bytes(receipt))
    if bundle_output is not None:
        bundle = build_evidence_bundle(output_dir, bundle_output)
        receipt["bundle"] = bundle
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="execute browser viewport evidence against one exact website ZIP")
    run.add_argument("--website", type=Path, required=True)
    run.add_argument("--browser", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--bundle", type=Path)
    run.add_argument("--route", action="append", default=[])
    run.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    verify = sub.add_parser("verify", help="verify a packaged browser evidence bundle")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--website-sha256", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            result = run_browser_evidence(
                args.website,
                args.browser,
                args.output_dir,
                routes=args.route or DEFAULT_ROUTES,
                timeout_seconds=args.timeout,
                bundle_output=args.bundle,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["status"] == "PASS" else 1
        result = verify_evidence_bundle(args.bundle, expected_website_sha256=args.website_sha256)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    except (BrowserEvidenceError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc), "truth_boundary": TRUTH_BOUNDARY}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

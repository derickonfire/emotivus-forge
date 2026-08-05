from __future__ import annotations

import json
import os
import stat
import struct
import zlib
import binascii
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

from emotivus_forge.core import browser_evidence


class BrowserEvidenceTests(unittest.TestCase):
    def make_site_zip(self, root: Path, *, unsafe: bool = False) -> Path:
        site = root / "Forge-Website.zip"
        with zipfile.ZipFile(site, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "index.html",
                "<!doctype html><html lang='en'><head><title>Forge</title>"
                "<link rel='canonical' href='https://forge.emotivus.com/'></head>"
                "<body><main><h1>Forge home</h1><p>" + ("evidence " * 20) + "</p></main></body></html>",
            )
            archive.writestr(
                "run/index.html",
                "<!doctype html><html lang='en'><head><title>Run Forge</title></head>"
                "<body><main><h1>Run Forge</h1><p>" + ("bounded " * 20) + "</p></main></body></html>",
            )
            archive.writestr("assets/styles.css", "body{font-family:sans-serif}")
            archive.writestr("downloads/RUN-FORGE.zip", b"PK\x05\x06" + b"\x00" * 18)
            if unsafe:
                archive.writestr("../escape.txt", "unsafe")
        return site

    def make_fake_browser(self, root: Path, *, fail: bool = False) -> Path:
        path = root / "fake-chromium.py"
        body = f"""#!/usr/bin/env python3
import binascii, os, struct, sys, urllib.request, zlib
if '--version' in sys.argv:
    print('Forge Fake Chromium 1.0')
    raise SystemExit(0)
if {str(fail)}:
    print('forced browser failure', file=sys.stderr)
    raise SystemExit(7)
shot = next(arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--screenshot='))
size = next(arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--window-size='))
width, height = [int(value) for value in size.split(',')]
url = sys.argv[-1]
with urllib.request.urlopen(url, timeout=5) as response:
    data = response.read()
def chunk(kind, content):
    return struct.pack('>I', len(content)) + kind + content + struct.pack('>I', binascii.crc32(kind + content) & 0xffffffff)
raw = b''.join(b'\\x00' + b'\\xff\\xff\\xff' * width for _ in range(height))
png = b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
os.makedirs(os.path.dirname(shot), exist_ok=True)
open(shot, 'wb').write(png)
sys.stdout.buffer.write(data)
"""
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path


    def fake_executor(self, *, browser: Path, site_root: Path, routes, profiles, artifact_root: Path, timeout_seconds: int):
        del browser, timeout_seconds
        rows = []
        for profile in profiles:
            for route in routes:
                source = browser_evidence._route_source_path(site_root, route)
                dom = source.read_bytes()
                width, height = profile["width"], profile["height"]
                def chunk(kind: bytes, content: bytes) -> bytes:
                    return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", binascii.crc32(kind + content) & 0xffffffff)
                raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
                screenshot = (
                    b"\x89PNG\r\n\x1a\n"
                    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw, 9))
                    + chunk(b"IEND", b"")
                )
                slug = browser_evidence._route_slug(route)
                prefix = f"renders/{profile['id']}/{slug}"
                dom_artifact = browser_evidence._write_artifact(artifact_root, f"{prefix}.html", dom)
                screenshot_artifact = browser_evidence._write_artifact(artifact_root, f"{prefix}.png", screenshot)
                events_artifact = browser_evidence._write_artifact(
                    artifact_root,
                    f"{prefix}.events.json",
                    browser_evidence.pretty_bytes({
                        "console": [], "page_errors": [], "failed_requests": [],
                        "package_requests": [], "external_requests_blocked": [],
                    }),
                )
                title = "Run Forge" if route.startswith("/run") else "Forge"
                rows.append({
                    "status": "PASS",
                    "route": route,
                    "source": {
                        "path": source.relative_to(site_root).as_posix(),
                        "sha256": browser_evidence.sha256_bytes(dom),
                        "bytes": len(dom),
                    },
                    "transport": "network-isolated-package-routing",
                    "profile": dict(profile),
                    "duration_ms": 1,
                    "document_source_status": 200,
                    "dom": {
                        **dom_artifact,
                        "title": title,
                        "main_count": 1,
                        "h1_count": 1,
                        "canonical": "",
                        "html_lang": "en",
                        "body_text_chars": 120,
                        "inner_width": width,
                        "inner_height": height,
                        "device_pixel_ratio": 1,
                        "scroll_width": width,
                        "scroll_height": height,
                        "horizontal_overflow": False,
                        "prefers_dark": profile["color_scheme"] == "dark",
                        "ready_state": "complete",
                    },
                    "screenshot": {**screenshot_artifact, "width": width, "height": height},
                    "events": {
                        **events_artifact,
                        "console_count": 0,
                        "console_error_count": 0,
                        "page_error_count": 0,
                        "failed_request_count": 0,
                        "package_request_count": 0,
                        "package_error_count": 0,
                        "external_request_count": 0,
                    },
                    "problems": [],
                })
        return rows

    def test_run_and_verify_exact_browser_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            site = self.make_site_zip(root)
            browser = self.make_fake_browser(root)
            output = root / "evidence"
            bundle = root / "browser-evidence.zip"
            result = browser_evidence.run_browser_evidence(
                site,
                browser,
                output,
                routes=("/", "/run/"),
                profiles=browser_evidence.DEFAULT_PROFILES,
                observed_at="2026-08-04T23:00:00+00:00",
                bundle_output=bundle,
                render_executor=self.fake_executor,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["render_count"], 4)
            self.assertTrue(result["truth"]["browser_executed"])
            self.assertFalse(result["truth"]["physical_device_tested"])
            self.assertFalse(result["truth"]["release_authorized"])
            self.assertTrue(all(row["document_source_status"] == 200 for row in result["renders"]))
            self.assertTrue(all(row["screenshot"]["width"] == row["profile"]["width"] for row in result["renders"]))
            verification = browser_evidence.verify_evidence_bundle(
                bundle, expected_website_sha256=browser_evidence.sha256_file(site)
            )
            self.assertEqual(verification["status"], "PASS", verification["problems"])

    def test_packaging_same_evidence_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            site = self.make_site_zip(root)
            browser = self.make_fake_browser(root)
            output = root / "evidence"
            browser_evidence.run_browser_evidence(
                site, browser, output, routes=("/",), profiles=(browser_evidence.DEFAULT_PROFILES[0],),
                observed_at="2026-08-04T23:00:00+00:00",
                render_executor=self.fake_executor,
            )
            first = root / "first.zip"
            second = root / "second.zip"
            browser_evidence.build_evidence_bundle(output, first)
            browser_evidence.build_evidence_bundle(output, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_tampered_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            site = self.make_site_zip(root)
            browser = self.make_fake_browser(root)
            output = root / "evidence"
            source_bundle = root / "source.zip"
            browser_evidence.run_browser_evidence(
                site, browser, output, routes=("/",), profiles=(browser_evidence.DEFAULT_PROFILES[0],),
                observed_at="2026-08-04T23:00:00+00:00", bundle_output=source_bundle,
                render_executor=self.fake_executor,
            )
            tampered = root / "tampered.zip"
            with zipfile.ZipFile(source_bundle) as old, zipfile.ZipFile(tampered, "w") as new:
                for info in old.infolist():
                    content = old.read(info)
                    if info.filename.endswith(".html"):
                        content += b"tampered"
                    new.writestr(info, content)
            result = browser_evidence.verify_evidence_bundle(tampered)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("payload identity differs" in item for item in result["problems"]))

    def test_unsafe_website_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            with self.assertRaises(browser_evidence.BrowserEvidenceError):
                browser_evidence.inspect_website_zip(self.make_site_zip(root, unsafe=True))

    def test_nonlocal_route_is_rejected(self) -> None:
        with self.assertRaises(browser_evidence.BrowserEvidenceError):
            browser_evidence.normalize_routes(("https://example.com/",))
        with self.assertRaises(browser_evidence.BrowserEvidenceError):
            browser_evidence.normalize_routes(("/../secret",))

    def test_profile_cannot_claim_a_mobile_device(self) -> None:
        with self.assertRaises(browser_evidence.BrowserEvidenceError):
            browser_evidence.normalize_profiles(({
                "id": "phone", "width": 390, "height": 844,
                "color_scheme": "dark", "mobile_claimed": True,
            },))

    def test_browser_failure_is_not_converted_to_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            site = self.make_site_zip(root)
            browser = self.make_fake_browser(root, fail=True)
            with self.assertRaises(browser_evidence.BrowserEvidenceError):
                browser_evidence.run_browser_evidence(
                    site, browser, root / "out", routes=("/",),
                    profiles=(browser_evidence.DEFAULT_PROFILES[0],),
                    observed_at="2026-08-04T23:00:00+00:00",
                    render_executor=lambda **kwargs: (_ for _ in ()).throw(
                        browser_evidence.BrowserEvidenceError("forced browser failure")
                    ),
                )

    def test_receipt_id_binds_truth_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            site = self.make_site_zip(root)
            browser = self.make_fake_browser(root)
            output = root / "evidence"
            browser_evidence.run_browser_evidence(
                site, browser, output, routes=("/",), profiles=(browser_evidence.DEFAULT_PROFILES[0],),
                observed_at="2026-08-04T23:00:00+00:00",
                render_executor=self.fake_executor,
            )
            receipt = json.loads((output / "browser-evidence.json").read_text(encoding="utf-8"))
            base = {key: value for key, value in receipt.items() if key != "receipt_id"}
            self.assertEqual(receipt["receipt_id"], browser_evidence.sha256_bytes(browser_evidence.canonical_bytes(base)))
            self.assertFalse(receipt["truth"]["accessibility_conformance_claimed"])
            self.assertFalse(receipt["truth"]["production_origin_tested"])


if __name__ == "__main__":
    unittest.main()

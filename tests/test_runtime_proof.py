from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from emotivus_forge.core.capabilities import activate_capability, capability_activations, validate_activation_contract
from emotivus_forge.core.passport import build_passport
from emotivus_forge.core.paths import STATE_FILE_NAMES
from emotivus_forge.core.resume import build_resume
from emotivus_forge.services.scoped_check import run_scoped_check
from tests.support import FORGE_ROOT, ForgeTestCase


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/good":
            body = ("<!doctype html><html><body><main id=\"app\">Expected dashboard</main>" + "x" * 180 + "</body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif self.path == "/tiny":
            body = b"<html>Error</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        elif self.path == "/fatal":
            body = ("<html><main id=\"app\">Expected dashboard</main>Fatal error" + "x" * 180 + "</html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        elif self.path == "/json":
            body = (json.dumps({"status": "ok", "marker": "Expected dashboard", "padding": "x" * 180})).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/slow":
            time.sleep(2)
            body = b"<html><main>Expected dashboard</main>" + b"x" * 180 + b"</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        else:
            body = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


class RuntimeProofTests(ForgeTestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _recipe(self, root: Path, *, path: str = "/good", recipe_id: str = "homepage", min_bytes: int = 100, content_type: str = "text/html", forbidden: list[str] | None = None, headers: dict[str, str] | None = None, timeout: int = 2) -> Path:
        recipe = root / f"{recipe_id}.runtime.json"
        recipe.write_text(json.dumps({
            "schema": 1,
            "recipe_id": recipe_id,
            "title": "Homepage renders expected content",
            "verification_tier": "sandbox",
            "request": {
                "url": self.origin + path,
                "method": "GET",
                "timeout_seconds": timeout,
                "max_response_bytes": 4096,
                "headers": headers or {"Accept": content_type},
            },
            "assertions": {
                "status_in": [200],
                "content_type_in": [content_type],
                "min_bytes": min_bytes,
                "must_contain": ["Expected dashboard"],
                "must_not_contain": forbidden if forbidden is not None else ["Fatal error", "Traceback"],
            },
            "exclusions": [
                "JavaScript execution",
                "visual layout",
                "authenticated behavior",
                "database state",
                "deployment completeness",
                "release readiness"
            ]
        }, indent=2) + "\n", encoding="utf-8")
        return recipe

    def _contract(self, root: Path, recipe: Path, *, allowed_origins: list[str] | None = None, runtime_seconds: int = 5) -> Path:
        evidence = root / "runtime-proof-need.md"
        evidence.write_text("# Runtime proof need\n\nConfirm the expected page content renders.\n", encoding="utf-8")
        contract = root / "runtime-proof.activation.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "capability_id": "runtime-proof",
            "authority": "owner",
            "trigger": {
                "description": "A specific HTTP surface needs content-aware runtime evidence.",
                "evidence_paths": ["runtime-proof-need.md"]
            },
            "scope": {
                "included": ["declared HTTP response and content assertions"],
                "excluded": ["browser JavaScript", "visual layout", "authentication", "database state", "release readiness"]
            },
            "budget": {
                "runtime_seconds": runtime_seconds,
                "file_limit": 4,
                "output_characters": 8000
            },
            "focused_regressions": [
                "runtime-proof.inactive-by-default",
                "runtime-proof.explicit-contract",
                "runtime-proof.content-aware",
                "runtime-proof.tiny-error-page-fails",
                "runtime-proof.host-bound",
                "runtime-proof.budget-bound",
                "runtime-proof.contract-change-requires-reactivation"
            ],
            "native_advantage": {
                "status": "distinct-value",
                "explanation": "The recipe verifies minimum viable HTTP content without replacing browser tests or the project-native gate."
            },
            "runtime_proof": {
                "allowed_origins": allowed_origins or [self.origin],
                "recipe_paths": [recipe.name]
            },
            "allow_repairs": False
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def test_runtime_proof_is_inactive_and_lazy_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            sys.modules.pop("emotivus_forge.services.runtime_proof", None)
            ordinary = run_scoped_check(root, FORGE_ROOT)
            self.assertEqual(ordinary["status"], "NOT_RUN")
            self.assertNotIn("emotivus_forge.services.runtime_proof", sys.modules)
            blocked = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"])
            self.assertEqual(blocked["status"], "FAIL")
            self.assertNotIn("emotivus_forge.services.runtime_proof", sys.modules)

    def test_content_aware_recipe_passes_without_storing_response_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root)
            activate_capability(root, FORGE_ROOT, "runtime-proof", self._contract(root, recipe))
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"])
            result = payload["capabilities"][0]
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["counts"]["PASS"], 1)
            self.assertEqual(result["evaluations"][0]["observed"]["status"], 200)
            self.assertIn("response_sha256", result["evaluations"][0]["observed"])
            self.assertNotIn("body", json.dumps(result).casefold())
            self.assertFalse(result["javascript_executed"])
            self.assertFalse(result["credentials_allowed"])

    def test_tiny_http_200_error_page_fails_minimum_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root, path="/tiny", min_bytes=100)
            activate_capability(root, FORGE_ROOT, "runtime-proof", self._contract(root, recipe))
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"])
            self.assertEqual(payload["status"], "FAIL")
            messages = [item["message"] for item in payload["findings"]]
            self.assertTrue(any("minimum" in message for message in messages))
            self.assertTrue(any("required marker" in message for message in messages))

    def test_forbidden_runtime_marker_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root, path="/fatal")
            activate_capability(root, FORGE_ROOT, "runtime-proof", self._contract(root, recipe))
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"])
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("forbidden marker" in item["message"] for item in payload["findings"]))

    def test_activation_rejects_recipe_outside_allowed_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root)
            contract = self._contract(root, recipe, allowed_origins=["https://example.invalid"])
            with self.assertRaisesRegex(ValueError, "not allowed"):
                validate_activation_contract(root, FORGE_ROOT, "runtime-proof", contract)

    def test_activation_rejects_credentials_and_liveness_only_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root, headers={"Authorization": "Bearer secret"})
            contract = self._contract(root, recipe)
            with self.assertRaisesRegex(ValueError, "header is not permitted"):
                validate_activation_contract(root, FORGE_ROOT, "runtime-proof", contract)
            raw = json.loads(recipe.read_text(encoding="utf-8"))
            raw["request"]["headers"] = {"Accept": "text/html"}
            raw["assertions"]["must_contain"] = []
            recipe.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must_contain"):
                validate_activation_contract(root, FORGE_ROOT, "runtime-proof", contract)

    def test_recipe_change_requires_explicit_reactivation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root)
            contract = self._contract(root, recipe)
            activate_capability(root, FORGE_ROOT, "runtime-proof", contract)
            recipe.write_text(recipe.read_text(encoding="utf-8") + " \n", encoding="utf-8")
            self.assertEqual(capability_activations(root)["runtime-proof"]["status"], "reactivation-required")
            sys.modules.pop("emotivus_forge.services.runtime_proof", None)
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"])
            self.assertEqual(payload["status"], "FAIL")
            self.assertNotIn("emotivus_forge.services.runtime_proof", sys.modules)

    def test_runtime_timeout_is_blocked_attempted_not_failed_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root, path="/slow", timeout=1)
            activate_capability(root, FORGE_ROOT, "runtime-proof", self._contract(root, recipe, runtime_seconds=2))
            payload = run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"])
            evaluation = payload["capabilities"][0]["evaluations"][0]
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(evaluation["status"], "BLOCKED")
            self.assertEqual(evaluation["truth_state"], "BLOCKED_ATTEMPTED")

    def test_resume_keeps_runtime_summary_compact_and_eight_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            build_passport(root, FORGE_ROOT)
            recipe = self._recipe(root)
            activate_capability(root, FORGE_ROOT, "runtime-proof", self._contract(root, recipe))
            run_scoped_check(root, FORGE_ROOT, requested_capabilities=["runtime-proof"])
            resume = build_resume(root, FORGE_ROOT)
            self.assertIn("Latest runtime recipes", resume["markdown"])
            self.assertIn("browser behavior and release readiness remain unproven", resume["markdown"])
            self.assertNotIn("response_sha256", resume["markdown"])
            self.assertLess(len(resume["markdown"]), 5000)
            actual = sorted(path.name for path in (root / ".forge").iterdir() if path.is_file())
            self.assertEqual(actual, sorted(STATE_FILE_NAMES))


if __name__ == "__main__":
    unittest.main()

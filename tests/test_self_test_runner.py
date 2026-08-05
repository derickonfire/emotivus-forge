from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from emotivus_forge.commands.public import _run_self_test_module, handle_self_test
from tests.support import ForgeTestCase


class IsolatedSelfTestRunnerTests(ForgeTestCase):
    def _root(self, directory: str) -> Path:
        root = Path(directory)
        tests = root / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("", encoding="utf-8")
        (tests / "test_alpha.py").write_text("", encoding="utf-8")
        (tests / "test_beta.py").write_text("", encoding="utf-8")
        return root

    def test_isolated_runner_aggregates_module_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            def result(module, *_args):
                return {"module": module, "count": 2 if module.endswith("alpha") else 3, "returncode": 0, "timed_out": False, "detail": "OK"}
            output = io.StringIO()
            with patch("emotivus_forge.commands.public._run_self_test_module", side_effect=result), \
                    patch("emotivus_forge.core.narrative_integrity.check_narrative_integrity", return_value={"status": "PASS", "problems": []}), \
                    redirect_stdout(output):
                code = handle_self_test(root)
            self.assertEqual(code, 0)
            self.assertIn("5 focused regressions across 2 isolated modules", output.getvalue())

    def test_isolated_runner_reports_module_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root(directory)
            def result(module, *_args):
                if module.endswith("alpha"):
                    return {"module": module, "count": 0, "returncode": 1, "timed_out": True, "detail": "timeout"}
                return {"module": module, "count": 1, "returncode": 0, "timed_out": False, "detail": "OK"}
            output = io.StringIO()
            with patch("emotivus_forge.commands.public._run_self_test_module", side_effect=result), redirect_stdout(output):
                code = handle_self_test(root)
            self.assertEqual(code, 1)
            self.assertIn("timed out after 300 seconds", output.getvalue())

            # A module that finishes its assertion but leaves a non-daemon
            # thread behind must still return its completed unittest result.
            lingering = root / "tests" / "test_lingering.py"
            lingering.write_text(
                "import threading, time, unittest\n"
                "class Lingering(unittest.TestCase):\n"
                "    def test_done(self):\n"
                "        threading.Thread(target=lambda: time.sleep(30), daemon=False).start()\n",
                encoding="utf-8",
            )
            import os
            import time
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join([str(root / "tests"), str(root)])
            started = time.monotonic()
            item = _run_self_test_module("tests.test_lingering", root, environment)
            self.assertLess(time.monotonic() - started, 10)
            self.assertEqual(item["returncode"], 0, item)
            self.assertEqual(item["count"], 1)
            self.assertFalse(item["timed_out"])


if __name__ == "__main__":
    import unittest
    unittest.main()

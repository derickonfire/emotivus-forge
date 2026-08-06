from __future__ import annotations

import sys
import unittest


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    arguments = [item.strip() for item in arguments if item.strip()]
    if not arguments:
        print("usage: python -m emotivus_forge.test_shard_runner <test-name> [<test-name> ...]", file=sys.stderr)
        return 2
    suite = unittest.defaultTestLoader.loadTestsFromNames(arguments)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

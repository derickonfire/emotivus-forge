#!/usr/bin/env python3
"""Build or verify a deterministic runtime-bound Forge portable evidence kit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from emotivus_forge.core.evidence_kit import (  # noqa: E402
    EvidenceKitError,
    build_portable_evidence_kit,
    verify_portable_evidence_kit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--runtime", required=True)
    build.add_argument("--output", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--kit", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_portable_evidence_kit(ROOT, Path(args.runtime), Path(args.output))
        else:
            result = verify_portable_evidence_kit(Path(args.kit))
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result.get("status") == "PASS" else 1
    except (EvidenceKitError, OSError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify an optional external-key attestation for one exact Forge package."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emotivus_forge.core.build_attestation import verify_build_attestation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("build_manifest", type=Path)
    parser.add_argument("public_key", type=Path)
    parser.add_argument("signature", type=Path)
    parser.add_argument("--expected-source-fingerprint", default="")
    args = parser.parse_args()
    result = verify_build_attestation(
        args.package,
        args.build_manifest,
        args.public_key,
        args.signature,
        expected_source_fingerprint=args.expected_source_fingerprint,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

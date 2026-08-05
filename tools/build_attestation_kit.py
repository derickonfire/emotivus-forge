#!/usr/bin/env python3
"""Build or verify a deterministic Forge owner-attestation ceremony kit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emotivus_forge.core.attestation_kit import (  # noqa: E402
    AttestationKitError,
    build_owner_attestation_kit,
    verify_owner_attestation_kit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--root", type=Path, default=Path("."))
    build.add_argument("--package", type=Path, required=True)
    build.add_argument("--build-manifest", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--kit", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_owner_attestation_kit(
                args.root,
                args.package,
                args.build_manifest,
                args.output,
            )
        else:
            result = verify_owner_attestation_kit(args.kit)
    except (AttestationKitError, OSError, ValueError) as exc:
        result = {"status": "FAIL", "problems": [str(exc)]}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

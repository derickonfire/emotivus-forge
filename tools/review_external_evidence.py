#!/usr/bin/env python3
"""Review one exact returned Forge evidence bundle against its original sealed kit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from emotivus_forge.core.external_evidence import (  # noqa: E402
    ExternalEvidenceError,
    review_external_evidence,
    verify_review_receipt,
    write_review_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review")
    review.add_argument("--kit", type=Path, required=True)
    review.add_argument("--return-bundle", type=Path, required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--prior-review", type=Path, action="append", default=[])
    review.add_argument("--output", type=Path)
    verify = sub.add_parser("verify-review")
    verify.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "review":
            result = review_external_evidence(
                args.kit,
                args.return_bundle,
                reviewer=args.reviewer,
                prior_reviews=args.prior_review,
            )
            if args.output:
                write_review_receipt(args.output, result)
        else:
            result = verify_review_receipt(args.review)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result.get("status") == "PASS" else 1
    except (ExternalEvidenceError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

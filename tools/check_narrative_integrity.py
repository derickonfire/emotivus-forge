#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emotivus_forge.core.narrative_integrity import check_narrative_integrity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Forge distribution narrative integrity.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    result = check_narrative_integrity(Path(args.root))
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

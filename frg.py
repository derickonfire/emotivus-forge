#!/usr/bin/env python3
import os

os.environ["FORGE_INVOKED_AS"] = "frg"

from emotivus_forge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

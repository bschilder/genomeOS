#!/usr/bin/env python3
"""Capture and verify real Atlas comparison (design §11); no fixture substitution.

Build/serve website first, then supply its local URL and a PNG output path.
Requires the website's locked Playwright dependency and installed Chromium.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            "node",
            str(root / "website/scripts/verify-comparison.mjs"),
            args.base_url,
            str(args.out.resolve()),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()

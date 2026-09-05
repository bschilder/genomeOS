#!/usr/bin/env python3
"""Capture the interactive Atlas review figure required by design §11."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a reproducible review image from a running Atlas map."
    )
    parser.add_argument("--url", required=True, help="Atlas map URL, including /map/")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/figures/atlas_map_ui.png"),
    )
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--delay-ms", type=int, default=12_000)
    args = parser.parse_args()

    browser = next(
        (
            candidate
            for name in ("chromium", "chromium-browser", "google-chrome")
            if (candidate := shutil.which(name))
        ),
        None,
    )
    if browser is None:
        parser.error("Chromium or Google Chrome is required")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--enable-unsafe-swiftshader",
            f"--window-size={args.width},{args.height}",
            f"--virtual-time-budget={args.delay_ms}",
            f"--screenshot={args.out.resolve()}",
            args.url,
        ],
        check=True,
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

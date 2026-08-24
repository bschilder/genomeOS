"""Download the MAP HbS survey database (design §8, P1).

The open georeferenced survey data behind Piel et al. 2010/2013, served by the Malaria Atlas
Project as a WFS layer. No credentials required.

    python scripts/fetch_map_hbs.py --out data/raw/map_hbs_surveys.csv

Data is fetched by script rather than committed: the source is versioned upstream and large
enough that a checked-in copy would go stale silently.
"""

from __future__ import annotations

import argparse
import urllib.parse
import urllib.request
from pathlib import Path

WFS_BASE = "https://data.malariaatlas.org/geoserver/Explorer/ows"
LAYERS = {"hbs": "Explorer:HbS_Data", "g6pd": "Explorer:G6PD_Data"}


def url_for(layer: str) -> str:
    query = urllib.parse.urlencode(
        {
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            "typeName": LAYERS[layer],
            "outputFormat": "csv",
        }
    )
    return f"{WFS_BASE}?{query}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", choices=sorted(LAYERS), default="hbs")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url_for(args.layer), timeout=args.timeout) as response:
        payload = response.read()
    args.out.write_bytes(payload)
    print(f"{args.layer}: wrote {len(payload):,} bytes to {args.out}")


if __name__ == "__main__":
    main()

"""Download a WorldPop gridded population mosaic (design §9, P3).

Resolves the download URL through WorldPop's REST catalogue rather than hardcoding a path —
their directory layout has changed before, and a guessed URL fails as a 404 rather than loudly.

    python scripts/fetch_worldpop.py --year 2020 --out data/raw/worldpop_1km_2020.tif

The global 1 km mosaic is roughly 870 MB. Fetched by script, never committed.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

CATALOGUE = "https://hub.worldpop.org/rest/data/pop/wpgp1km"
CITATION = "WorldPop, University of Southampton. doi:10.5258/SOTON/WP00647"


def resolve(year: int, timeout: int = 60) -> str:
    """Find the mosaic URL for `year` in the WorldPop catalogue."""
    with urllib.request.urlopen(CATALOGUE, timeout=timeout) as response:
        entries = json.load(response)["data"]

    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("popyear")) != str(year):
            continue
        with urllib.request.urlopen(f"{CATALOGUE}?id={entry['id']}", timeout=timeout) as detail:
            payload = json.load(detail)["data"]
        payload = payload[0] if isinstance(payload, list) else payload
        files = [f for f in payload.get("files", []) if str(f).endswith(".tif")]
        if not files:
            raise RuntimeError(f"WorldPop entry {entry['id']} for {year} lists no .tif file")
        return files[0]

    years = sorted({str(e.get("popyear")) for e in entries if isinstance(e, dict)})
    raise RuntimeError(f"no WorldPop 1km mosaic for {year}; available: {years}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2020)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    url = resolve(args.year)
    print(f"resolved {args.year} -> {url}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=args.timeout) as response, args.out.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    print(f"wrote {args.out.stat().st_size:,} bytes to {args.out}\ncite: {CITATION}")


if __name__ == "__main__":
    main()

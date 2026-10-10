#!/usr/bin/env python3
"""Cut the 2,000-cell mesh-parity subset of ``cyt-il-6-174-c`` (Atlas design §11; spec §B.1, §B.5).

The same-input parity tests compare the legacy main-thread surface builder with the worker mesh on
real cells. This script takes every cell of ``cyt-il-6-174-c`` under the twelve named, contiguous
H3 resolution-1 parents below (northern Canada across Alaska to Chukotka, crossing ±180°), and
refuses unless the subset holds all four support states and at least one value outside
``metric_domains``. The source surface and manifest must match the source catalog's sha256 before
``--out`` is touched. It writes the subset as a canonical surface JSON (the real artifact identity,
cells in grid order, values bit-for-bit), the artifact manifest, a one-artifact catalog with
observations unavailable, and that tree's own grid, render and detail objects via
``encode_atlas_web.encode_export``, so the fixture survives the per-artifact files leaving git.

    python scripts/build_atlas_parity_subset.py \\
        --from-dir website/public/data/atlas --out website/tests/fixtures/atlas/parity
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import h3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genomeos.publication.surface_codec import SUPPORT_CODES  # noqa: E402
from scripts import encode_atlas_web  # noqa: E402
from scripts.build_atlas_e2e_fixture import prepare_out  # noqa: E402

ARTIFACT_ID = "cyt-il-6-174-c"
#: Contiguous resolution-1 parents; together 1,986 cells of the published grid.
PARITY_PARENTS: tuple[str, ...] = (
    "810c3ffffffffff",
    "810c7ffffffffff",
    "810d3ffffffffff",
    "810d7ffffffffff",
    "810dbffffffffff",
    "810ebffffffffff",
    "81123ffffffffff",
    "81127ffffffffff",
    "81133ffffffffff",
    "81137ffffffffff",
    "81177ffffffffff",
    "81273ffffffffff",
)
DEFAULT_FROM = ROOT / "website" / "public" / "data" / "atlas"
DEFAULT_OUT = ROOT / "website" / "tests" / "fixtures" / "atlas" / "parity"


def _contiguous(parents: tuple[str, ...]) -> bool:
    members = set(parents)
    seen = {parents[0]}
    frontier = [parents[0]]
    while frontier:
        for neighbour in h3.grid_disk(frontier.pop(), 1):
            if neighbour in members and neighbour not in seen:
                seen.add(neighbour)
                frontier.append(neighbour)
    return seen == members


def subset_cells(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The cells under ``PARITY_PARENTS`` in grid order, refused unless the subset is useful."""
    if not _contiguous(PARITY_PARENTS):
        raise ValueError("PARITY_PARENTS must be contiguous at resolution 1")
    parents = set(PARITY_PARENTS)
    cells = [cell for cell in payload["cells"] if h3.cell_to_parent(cell["h3_index"], 1) in parents]
    states = Counter(cell["support"] for cell in cells)
    if set(states) != set(SUPPORT_CODES):
        raise ValueError(f"parity subset must hold all four support states, got {dict(states)}")
    domains = payload["artifact"]["metric_domains"]
    outside = [
        cell
        for cell in cells
        for metric in ("post_mean", "post_sd")
        if not domains[metric][0] <= cell[metric] <= domains[metric][1]
    ]
    if not outside:
        raise ValueError("parity subset must hold a value outside metric_domains")
    return cells


def build_subset(from_dir: Path, out: Path) -> dict[str, Any]:
    from_dir, out = Path(from_dir), Path(out)
    source = json.loads((from_dir / "catalog.json").read_text(encoding="utf-8"))
    ref = next(artifact for artifact in source["artifacts"] if artifact["id"] == ARTIFACT_ID)
    payload = json.loads(encode_atlas_web.read_verified(from_dir, ref["surface_url"], ref["surface_sha256"]))
    cells = subset_cells(payload)
    manifest_ref = ref["downloads"]["manifest"]
    manifest_key = manifest_ref["url"]
    manifest = encode_atlas_web.read_verified(from_dir, manifest_key, manifest_ref["sha256"])
    prepare_out(out, source=from_dir)  # every source is read and verified first; ``out`` may not overlap
    surface = encode_atlas_web.canonical_bytes({**payload, "cells": cells})
    surface_key = f"{ARTIFACT_ID}.surface.json"
    (out / surface_key).write_bytes(surface)
    (out / manifest_key).write_bytes(manifest)
    digest = hashlib.sha256(surface).hexdigest()
    compact = {key: value for key, value in ref.items() if key not in encode_atlas_web.REF_FIELDS} | {
        "downloads": {
            **ref["downloads"],
            "observations": None,
            "surface": {**ref["downloads"]["surface"], "sha256": digest, "url": surface_key},
        },
        "n_cells": len(cells),
        "observations_available": False,
        "observations_sha256": None,
        "observations_url": None,
        "support_counts": dict(sorted(Counter(cell["support"] for cell in cells).items())),
        "surface_sha256": digest,
        "surface_url": surface_key,
    }
    catalog = {key: value for key, value in source.items() if key not in encode_atlas_web.CATALOG_FIELDS}
    (out / "catalog.json").write_bytes(encode_atlas_web.canonical_bytes({**catalog, "artifacts": [compact]}))
    return encode_atlas_web.encode_export(out, out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from-dir", type=Path, default=DEFAULT_FROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    catalog = build_subset(args.from_dir, args.out)
    print(f"wrote {catalog['artifacts'][0]['n_cells']} {ARTIFACT_ID} cells to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the committed e2e Atlas fixture tree (Atlas design §11; fast-load spec §B.5, §B.8).

Software-WebGL browser tests cannot afford 77,844 cells per layer, so they run against a compact
tree written from a full export: for every catalog artifact the same sorted cell subset (the
pinned-then-sampled rule of the former ``website/tests/atlas-browser-fixture.ts``: every grid cell
inside ``gridDisk(latLngToCell(INSPECTOR_TARGET), 2)`` in grid order, then evenly sampled others,
then sorted), the observations that fixture kept (the 8 nearest the inspector target, then evenly
sampled), one compact grid, and a catalog whose ``n_cells``, ``n_observations``,
``support_counts``, observation digests and sizes, ``grids`` and ``web`` describe exactly those
objects. Values are copied bit-for-bit and encoded by ``encode_atlas_web.encode_catalog``, which
verifies every object from disk. ``surface_sha256``, ``surface_url`` and the surface and manifest
downloads keep naming the full canonical artifact the subset was cut from; those files are not
copied. ``--from-dir`` reads catalog keys, so a bucket download works after Part C too.

The tree is written to a hidden sibling of ``--out`` and renamed onto it only once complete, so a
failed or interrupted run leaves the previous tree (or none), never a partial one that the next run
would refuse. ``--out`` may not be, contain or lie inside ``--from-dir``.

    python scripts/build_atlas_e2e_fixture.py \\
        --from-dir website/public/data/atlas --out website/tests/fixtures/atlas/e2e
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import encode_atlas_web  # noqa: E402

DEFAULT_FROM = ROOT / "website" / "public" / "data" / "atlas"
DEFAULT_OUT = ROOT / "website" / "tests" / "fixtures" / "atlas" / "e2e"
#: ``RENDER_CELL_BUDGET``, ``RENDER_OBSERVATION_BUDGET`` and ``INSPECTOR_TARGET`` of the former
#: ``website/tests/atlas-browser-fixture.ts``.
CELL_BUDGET = 256
OBSERVATION_BUDGET = 64
INSPECTOR_TARGET = (40.4407, -3.7201)
NEAREST_OBSERVATIONS = 8


def _evenly(items: Sequence[Any], slots: int) -> list[Any]:
    """``remaining[Math.floor((index * remaining.length) / slots)]`` for each slot."""
    return [items[(index * len(items)) // slots] for index in range(max(slots, 0))]


def select_rows(h3_index: Sequence[str], resolution: int, budget: int = CELL_BUDGET) -> list[int]:
    """Row indices of the compact surface, ascending (pinned inspector cells, then sampled)."""
    if len(h3_index) <= budget:
        return list(range(len(h3_index)))
    inspector = set(h3.grid_disk(h3.latlng_to_cell(*INSPECTOR_TARGET, resolution), 2))
    pinned = [row for row, cell in enumerate(h3_index) if cell in inspector][:budget]
    remaining = [row for row, cell in enumerate(h3_index) if cell not in inspector]
    return sorted(pinned + _evenly(remaining, budget - len(pinned)))


def select_observations(rows: Sequence[Mapping[str, Any]], budget: int = OBSERVATION_BUDGET) -> list[Any]:
    """The observations the browser fixture kept, in its order (nearest first, then sampled)."""
    if len(rows) <= budget:
        return list(rows)
    lat, lon = INSPECTOR_TARGET
    ordered = sorted(rows, key=lambda row: (row["lat"] - lat) ** 2 + (row["lon"] - lon) ** 2)
    nearest = ordered[: min(NEAREST_OBSERVATIONS, budget)]
    return nearest + _evenly(ordered[NEAREST_OBSERVATIONS:], budget - len(nearest))


def _sibling(path: Path, suffix: str) -> Path:
    """A hidden, unique sibling of the resolved ``path``: same filesystem, so renames are atomic."""
    return path.with_name(f".{path.name}.{os.getpid()}-{secrets.token_hex(4)}.{suffix}")


def _refuse_unsafe_out(out: Path, source: Path | None) -> None:
    """Refuse an ``out`` that overlaps ``source`` or is a non-empty directory with no catalog."""
    if source is not None:
        target, origin = out.resolve(), source.resolve()
        if target == origin or target in origin.parents or origin in target.parents:
            raise ValueError(f"{out}: refusing to write a fixture tree that overlaps its source {source}")
    if out.exists() and any(out.iterdir()) and not (out / "catalog.json").is_file():
        raise ValueError(f"{out}: refusing to replace a directory that is not a fixture tree")


def prepare_out(out: Path, *, source: Path | None = None) -> None:
    """Leave ``out`` an empty directory, replacing only a fixture tree that does not overlap ``source``."""
    out = Path(out).resolve()
    _refuse_unsafe_out(out, source)
    if out.exists():
        retired = _sibling(out, "old")
        out.rename(retired)  # an interrupted delete leaves a hidden sibling, never a partial ``out``
        shutil.rmtree(retired)
    out.mkdir(parents=True)


def build_fixture(
    from_dir: Path,
    out: Path,
    *,
    cell_budget: int = CELL_BUDGET,
    observation_budget: int = OBSERVATION_BUDGET,
) -> dict[str, Any]:
    """Write the compact tree under ``out`` and return its catalog.

    Every source object is read and every output object written and verified in a hidden sibling of
    ``out`` first; only a complete tree is renamed onto ``out``.
    """
    from_dir, out = Path(from_dir), Path(out).resolve()
    _refuse_unsafe_out(out, from_dir)
    source = json.loads((from_dir / "catalog.json").read_text(encoding="utf-8"))
    staging, retired = _sibling(out, "tmp"), _sibling(out, "old")
    staging.mkdir(parents=True)
    try:
        catalog = _write_tree(from_dir, source, staging, cell_budget, observation_budget)
        _refuse_unsafe_out(out, from_dir)
        if out.exists():
            out.rename(retired)
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if retired.exists():
        shutil.rmtree(retired)
    return catalog


def _write_tree(
    from_dir: Path, source: Mapping[str, Any], out: Path, cell_budget: int, observation_budget: int
) -> dict[str, Any]:
    """Write the compact objects and ``catalog.json`` into the empty directory ``out``."""
    rows: list[int] = []
    grid: list[str] | None = None
    subsets: dict[str, dict[str, Any]] = {}
    artifacts = []
    for ref in source["artifacts"]:
        payload = json.loads(
            encode_atlas_web.read_verified(from_dir, ref["surface_url"], ref["surface_sha256"])
        )
        cells = payload["cells"]
        if grid is None:
            grid = [cell["h3_index"] for cell in cells]
            rows = select_rows(grid, int(ref["resolution"]), cell_budget)
        elif [cell["h3_index"] for cell in cells] != grid:
            raise ValueError(f"{ref['id']}: h3_index sequence differs from the shared grid")
        subset = [cells[row] for row in rows]
        subsets[ref["id"]] = {**payload, "cells": subset}
        counts = Counter(cell["support"] for cell in subset)
        compact = {**ref, "n_cells": len(subset), "support_counts": dict(sorted(counts.items()))}
        if ref["observations_available"]:
            observations = json.loads(
                encode_atlas_web.read_verified(from_dir, ref["observations_url"], ref["observations_sha256"])
            )
            kept = select_observations(observations["observations"], observation_budget)
            data = encode_atlas_web.canonical_bytes({**observations, "observations": kept})
            key = f"{ref['id']}.observations.json"
            (out / key).write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            downloads = {
                **ref["downloads"],
                "observations": {**ref["downloads"]["observations"], "sha256": digest, "url": key},
            }
            compact.update(
                downloads=downloads,
                n_observations=len(kept),
                observations_sha256=digest,
                observations_url=key,
            )
        artifacts.append(compact)

    def load_surface(ref: Mapping[str, Any]) -> encode_atlas_web.SurfaceSource:
        return encode_atlas_web.SurfaceSource(payload=subsets[ref["id"]], sha256=ref["surface_sha256"])

    def observations_size(ref: Mapping[str, Any]) -> int | None:
        return (out / ref["observations_url"]).stat().st_size if ref["observations_available"] else None

    catalog = encode_atlas_web.encode_catalog(
        {**source, "artifacts": artifacts},
        out_dir=out,
        load_surface=load_surface,
        observations_size=observations_size,
    )
    (out / "catalog.json").write_bytes(encode_atlas_web.canonical_bytes(catalog))
    return catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from-dir", type=Path, default=DEFAULT_FROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    catalog = build_fixture(args.from_dir, args.out)
    print(f"wrote {len(catalog['artifacts'])} compact artifacts to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

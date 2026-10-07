#!/usr/bin/env python3
"""Encode an Atlas web export into GOSA web objects (Atlas design §11; fast-load spec §B.4, §B.5).

``export_atlas_web.py`` output is an intermediate; the site build fails until this has run. It
reads an export directory, takes the first catalog artifact's ``h3_index`` sequence as the shared
grid (a surface that differs is refused: positional alignment would otherwise be a silent
wrong-value bug), writes content-addressed ``grids/`` and ``surfaces/`` objects under ``--out``, and
writes ``catalog.json`` there with ``grids``, ``web`` and ``observations_bytes``. Before the catalog
is written, every object is read back from disk, decoded and compared with the canonical JSON cell
by cell: detail float64 bit-for-bit, render float32 equal to ``float32(JSON)``, support codes and
the support histogram exact. Byte-deterministic and idempotent; needs only the ``read`` extra.

    python scripts/encode_atlas_web.py [--in DIR] [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genomeos.publication import surface_codec as codec  # noqa: E402

DEFAULT_DIR = ROOT / "website" / "public" / "data" / "atlas"
#: Catalog fields owned by this encoder, stripped and recomputed on every run (idempotence).
CATALOG_FIELDS = ("grids",)
REF_FIELDS = ("observations_bytes", "web")
DATA_KEY = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


@dataclass(frozen=True)
class SurfaceSource:
    """A canonical surface payload and the sha256 of the JSON file it came from."""

    payload: dict[str, Any]
    sha256: str


@dataclass(frozen=True)
class SharedGrid:
    """The grid every artifact must match, as written and read back from disk."""

    h3: list[int]
    sha256: str
    entry: dict[str, Any]
    container: codec.GosaContainer


def canonical_bytes(value: Any) -> bytes:
    """``export_atlas_web._canonical_bytes``, repeated so this script needs no pandas."""
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def data_key(key: str) -> str:
    """Refuse a key that ``dataKeySchema`` in ``website/src/atlas/contracts.ts`` would refuse."""
    if not isinstance(key, str) or not DATA_KEY.match(key) or ".." in key.split("/"):
        raise ValueError(f"{key!r} is not a relative data key (^[a-z0-9][a-z0-9._/-]*$, no '..')")
    return key


def grid_key(resolution: int, container_sha: str) -> str:
    return data_key(f"grids/h3-r{resolution}.{container_sha[:16]}.gosa")


def tier_key(ref: Mapping[str, Any], tier: str, container_sha: str) -> str:
    stem = f"surfaces/{ref['id']}/{ref['model_version']}/{ref['data_version']}"
    return data_key(f"{stem}/{tier}.{container_sha[:16]}.gosa")


def write_object(out_dir: Path, key: str, data: bytes) -> dict[str, Any]:
    """Write a content-addressed object, refusing to replace different bytes at its key."""
    path = out_dir / key
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"{path}: a different object already exists at this content-addressed key")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {"bytes": len(data), "sha256": codec.container_sha256(data), "url": key}


def _read_object(out_dir: Path, entry: Mapping[str, Any], tier: str) -> codec.GosaContainer:
    data = (out_dir / entry["url"]).read_bytes()
    return codec.verify_container(data, tier=tier, sha256=entry["sha256"], size=entry["bytes"])


def _write_grid(out_dir: Path, h3: list[int], resolution: int) -> SharedGrid:
    data = codec.encode_grid(h3, resolution)
    entry = write_object(out_dir, grid_key(resolution, codec.container_sha256(data)), data)
    entry = {**entry, "n_cells": len(h3), "resolution": resolution}
    return SharedGrid(h3, codec.grid_sha256(h3), entry, _read_object(out_dir, entry, "grid"))


def _bits(values: Any, fmt: str) -> bytes:
    return struct.pack(f"<{len(values)}{fmt}", *values)


def _verify_against_json(
    out_dir: Path, ref: Mapping[str, Any], grid: SharedGrid, payload: Mapping[str, Any]
) -> None:
    """Decode the written tiers from disk and compare every cell with the canonical JSON."""
    render = _read_object(out_dir, ref["web"]["render"], "render")
    detail = _read_object(out_dir, ref["web"]["detail"], "detail")
    codec.verify_artifact_tiers(
        grid=grid.container, render=render, detail=detail, ref=ref, grid_sha256=grid.sha256
    )
    cells = payload["cells"]
    for tier in (render, detail):
        if tier.header["artifact"] != payload["artifact"]:
            raise ValueError(f"{ref['id']}: {tier.tier} artifact differs from the canonical surface")
    for field in codec.DETAIL_FIELDS:
        if _bits(detail.columns[field], "d") != _bits([cell[field] for cell in cells], "d"):
            raise ValueError(f"{ref['id']}: detail {field} is not bit-identical to the JSON")
    for field in ("post_mean", "post_sd"):
        if _bits(render.columns[field], "f") != _bits([cell[field] for cell in cells], "f"):
            raise ValueError(f"{ref['id']}: render {field} differs from float32(JSON)")
    if render.columns["support"] != tuple(codec.SUPPORT_CODES.index(cell["support"]) for cell in cells):
        raise ValueError(f"{ref['id']}: support codes differ from the JSON support states")


def encode_catalog(
    catalog: Mapping[str, Any],
    *,
    out_dir: Path,
    load_surface: Callable[[Mapping[str, Any]], SurfaceSource],
    observations_size: Callable[[Mapping[str, Any]], int | None],
) -> dict[str, Any]:
    """Encode and verify every artifact, one at a time; return the catalog with its web objects."""
    out_dir = Path(out_dir)
    grid: SharedGrid | None = None
    artifacts = []
    for entry in catalog["artifacts"]:
        ref = {key: value for key, value in entry.items() if key not in REF_FIELDS}
        source = load_surface(ref)
        cells = source.payload["cells"]
        if source.sha256 != ref["surface_sha256"] or len(cells) != ref["n_cells"]:
            raise ValueError(f"{ref['id']}: surface sha256 or cell count differs from the catalog")
        h3 = [int(cell["h3_index"], 16) for cell in cells]
        resolution = int(ref["resolution"])
        if grid is None:
            grid = _write_grid(out_dir, h3, resolution)
        elif h3 != grid.h3 or resolution != grid.entry["resolution"]:
            row = next((i for i, (a, b) in enumerate(zip(h3, grid.h3, strict=False)) if a != b), len(h3))
            raise ValueError(f"{ref['id']}: h3_index sequence differs from the shared grid at row {row}")
        common = {
            "artifact": source.payload["artifact"],
            "source_surface_sha256": source.sha256,
            "grid_sha256": grid.sha256,
        }
        render = codec.encode_render(
            **common,
            support=[cell["support"] for cell in cells],
            post_mean=[cell["post_mean"] for cell in cells],
            post_sd=[cell["post_sd"] for cell in cells],
        )
        columns: dict[str, Any] = {field: [cell[field] for cell in cells] for field in codec.DETAIL_FIELDS}
        detail = codec.encode_detail(**common, **columns)
        web = {
            "detail": write_object(out_dir, tier_key(ref, "detail", codec.container_sha256(detail)), detail),
            "grid_sha256": grid.sha256,
            "render": write_object(out_dir, tier_key(ref, "render", codec.container_sha256(render)), render),
        }
        encoded = {**ref, "observations_bytes": observations_size(ref), "web": web}
        _verify_against_json(out_dir, encoded, grid, source.payload)
        artifacts.append(encoded)
    if grid is None:
        raise ValueError("catalog has no artifacts to encode")
    base = {key: value for key, value in catalog.items() if key not in CATALOG_FIELDS}
    return {**base, "artifacts": artifacts, "grids": {grid.sha256: grid.entry}}


def encode_export(in_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Encode the export tree in ``in_dir``; write objects and ``catalog.json`` under ``out_dir``."""
    in_dir, out_dir = Path(in_dir), Path(out_dir)
    catalog = json.loads((in_dir / "catalog.json").read_text(encoding="utf-8"))

    def read_verified(key: str, sha256: str) -> bytes:
        data = (in_dir / data_key(key)).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError(f"{in_dir / key}: sha256 does not match the catalog")
        return data

    def load_surface(ref: Mapping[str, Any]) -> SurfaceSource:
        data = read_verified(ref["surface_url"], ref["surface_sha256"])
        return SurfaceSource(payload=json.loads(data), sha256=ref["surface_sha256"])

    def observations_size(ref: Mapping[str, Any]) -> int | None:
        if not ref["observations_available"]:
            return None
        return len(read_verified(ref["observations_url"], ref["observations_sha256"]))

    encoded = encode_catalog(
        catalog, out_dir=out_dir, load_surface=load_surface, observations_size=observations_size
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "catalog.json").write_bytes(canonical_bytes(encoded))
    return encoded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--in", dest="in_dir", type=Path, default=DEFAULT_DIR, help="export directory")
    parser.add_argument("--out", dest="out_dir", type=Path, help="output directory (default: --in)")
    args = parser.parse_args(argv)
    out_dir = args.out_dir or args.in_dir
    catalog = encode_export(args.in_dir, out_dir)
    print(f"encoded {len(catalog['artifacts'])} artifacts on one shared grid into {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

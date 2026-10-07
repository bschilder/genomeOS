#!/usr/bin/env python3
"""Review figure for the GOSA web rendition (Atlas design §11; fast-load spec §B.1, §B.5).

    python scripts/encode_atlas_web.py
    python scripts/plot_surface_codec_parity.py --out docs/figures/surface-codec-parity.png

Reads the encoded objects back through the codec and compares them with the canonical JSON.
(a) 32-bin palette quantisation from the float32 render tier versus float64, for 30 layers x 2
metrics, with a map around every flipped cell; (b) the HbS render-tier palette bins as the globe
draws them; (c) kir-3ds1, which has prior-dominated cells outside ``metric_domains`` in both
metrics: the world maps box the clamped region and a zoom row below outlines each region of
clamped cells at a scale where their palette colour and stipple stay visible; (d) the largest
|detail - JSON| over all six fields and the count of cell values whose float64 bit pattern differs.
Unknown cells are hatched and prior-dominated cells stippled in their palette colour: the figure
shows where there is no data, as the product does (AGENTS "Show the map"). Fitted surfaces only;
no observations are drawn. Bin and colour arithmetic mirror ``website/src/atlas``, including the
globe's separate palette bins for prior-dominated cells.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import h3  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Patch, Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genomeos.publication import surface_codec as codec  # noqa: E402
from genomeos.viz.basemap import draw_countries, h3_polygons  # noqa: E402

DEFAULT_DIR = ROOT / "website" / "public" / "data" / "atlas"
BINS = 32
#: ``PALETTES`` and ``defaultPalette`` in ``website/src/atlas/visual-encoding.ts``.
PALETTES = {
    "rainbow": ("#6e40aa", "#417de0", "#1ac7c2", "#7bd34d", "#f2cf44", "#ff5e63"),
    "plasma": ("#0d0887", "#cc4778", "#f0f921"),
}
DEFAULT_PALETTE = {"post_mean": "rainbow", "post_sd": "plasma"}
UNKNOWN_FACE, UNKNOWN_HATCH = "#eef0f3", "#8b96a8"
UNKNOWN = codec.SUPPORT_CODES.index("unknown")
PRIOR_DOMINATED = codec.SUPPORT_CODES.index("prior_dominated")
#: The cells ``partitionSurfaceCells`` passes to ``paletteBinsForCells`` for the surface itself.
SUPPORTED = frozenset({codec.SUPPORT_CODES.index("observed"), codec.SUPPORT_CODES.index("interpolated")})


def quantize(value: float, domain: Sequence[float], bins: int = BINS) -> int:
    """``quantizeMetric`` in ``website/src/atlas/scene/support-material.ts``."""
    lower, upper = domain
    if lower == upper:
        return 0
    normalized = min(1.0, max(0.0, (value - lower) / (upper - lower)))
    return min(bins - 1, math.floor(normalized * bins))


def _to_linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _to_srgb(channel: float) -> int:
    value = channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055
    return round(min(1.0, max(0.0, value)) * 255)


def color_at(palette: str, position: float) -> tuple[int, int, int]:
    """``colorAtStops``: linear-light interpolation between sRGB stops, rounded to bytes."""
    stops = PALETTES[palette]
    scaled = min(1.0, max(0.0, position)) * (len(stops) - 1)
    lower = min(math.floor(scaled), len(stops) - 2)
    amount = scaled - lower
    first, second = (
        [_to_linear(int(stop[offset : offset + 2], 16)) for offset in (1, 3, 5)]
        for stop in stops[lower : lower + 2]
    )
    red, green, blue = (_to_srgb(a + (b - a) * amount) for a, b in zip(first, second, strict=True))
    return red, green, blue


def _position(value: float, domain: Sequence[float]) -> float:
    lower, upper = domain
    return 0.0 if lower == upper else min(1.0, max(0.0, (value - lower) / (upper - lower)))


def bin_colors(
    support: Sequence[int],
    values: Sequence[float],
    domain: Sequence[float],
    palette: str,
    *,
    partition: Collection[int] = SUPPORTED,
) -> dict[int, tuple[int, int, int]]:
    """``paletteBinsForCells`` over one support partition: each bin takes the colour of the
    partition's first cell in grid order. The globe bins observed and interpolated cells together
    (the default) and prior-dominated cells on their own (``surface-layer.ts``)."""
    colors: dict[int, tuple[int, int, int]] = {}
    for code, value in zip(support, values, strict=True):
        if code in partition:
            colors.setdefault(quantize(value, domain), color_at(palette, _position(value, domain)))
    return colors


def cell_colors(
    support: Sequence[int], values: Sequence[float], domain: Sequence[float], palette: str
) -> list[tuple[int, int, int] | None]:
    """The colour the globe draws each row in: its partition's bin colour; ``None`` for unknown."""
    supported = bin_colors(support, values, domain, palette)
    prior = bin_colors(support, values, domain, palette, partition={PRIOR_DOMINATED})
    return [
        None
        if code == UNKNOWN
        else (prior if code == PRIOR_DOMINATED else supported)[quantize(value, domain)]
        for code, value in zip(support, values, strict=True)
    ]


def bin_flips(
    support: Sequence[int], detail: Sequence[float], render: Sequence[float], domain: Sequence[float]
) -> list[tuple[int, int, int]]:
    """``(row, float64 bin, float32 bin)`` for every binned (non-unknown) cell whose bin changes."""
    return [
        (row, quantize(wide, domain), quantize(narrow, domain))
        for row, (code, wide, narrow) in enumerate(zip(support, detail, render, strict=True))
        if code != UNKNOWN and quantize(wide, domain) != quantize(narrow, domain)
    ]


def max_detail_error(
    detail: Mapping[str, Sequence[float]], cells: Sequence[Mapping[str, Any]]
) -> dict[str, float]:
    """Largest |detail - JSON| per field (expected 0.0 for every field)."""
    return {
        field: max(abs(a - cell[field]) for a, cell in zip(detail[field], cells, strict=True))
        for field in codec.DETAIL_FIELDS
    }


def bit_mismatches(
    detail: Mapping[str, Sequence[float]], cells: Sequence[Mapping[str, Any]]
) -> dict[str, int]:
    """Number of cells per field whose float64 bit pattern differs from the JSON value (expected 0).

    This catches what |detail - JSON| cannot, such as -0.0 against 0.0."""
    return {
        field: sum(
            struct.pack("<d", a) != struct.pack("<d", cell[field])
            for a, cell in zip(detail[field], cells, strict=True)
        )
        for field in codec.DETAIL_FIELDS
    }


def outside_domain(support: Sequence[int], displayed: Sequence[float], domain: Sequence[float]) -> list[int]:
    """Rows of drawn (non-unknown) cells whose displayed float64 value lies outside ``domain``:
    their colour and height clamp, but the number shown does not."""
    lower, upper = domain
    return [
        row
        for row, (code, value) in enumerate(zip(support, displayed, strict=True))
        if code != UNKNOWN and not lower <= value <= upper
    ]


def outline_rings(cells: Iterable[str]) -> list[list[tuple[float, float]]]:
    """Closed (lon, lat) rings around the union of ``cells``: one outline per region, not one per
    cell, so the cells inside keep their palette colour and stipple visible."""
    return [
        [(lng, lat) for lat, lng in (*ring, ring[0])]
        for polygon in h3.cells_to_h3shape(list(cells), tight=False)
        for ring in (polygon.outer, *polygon.holes)
    ]


def _load(data_dir: Path, ref: Mapping[str, Any]) -> tuple[codec.GosaContainer, codec.GosaContainer, dict]:
    tiers = [
        codec.verify_container(
            (data_dir / ref["web"][tier]["url"]).read_bytes(),
            tier=tier,
            sha256=ref["web"][tier]["sha256"],
            size=ref["web"][tier]["bytes"],
        )
        for tier in ("render", "detail")
    ]
    surface = json.loads((data_dir / ref["surface_url"]).read_text(encoding="utf-8"))
    return tiers[0], tiers[1], surface


def _cell_map(ax, polygons, kept, support, values, domain, palette) -> None:
    """Draw the globe's palette bins, hatched unknown cells, and prior-dominated cells stippled in
    their own bin colour."""
    colors = cell_colors(support, values, domain, palette)
    faces, unknown, prior = [], [], []
    for polygon, row in zip(polygons, kept, strict=True):
        rgb = colors[row]
        if rgb is None:
            unknown.append(polygon)
            continue
        target = prior if support[row] == PRIOR_DOMINATED else faces
        target.append((polygon, tuple(channel / 255 for channel in rgb)))
    ax.add_collection(
        PolyCollection(
            [p for p, _ in faces], facecolors=[c for _, c in faces], edgecolors="face", linewidths=0
        )
    )
    ax.add_collection(
        PolyCollection(
            [p for p, _ in prior],
            facecolors=[c for _, c in prior],
            edgecolors="white",
            hatch="....",
            linewidths=0,
        )
    )
    ax.add_collection(
        PolyCollection(unknown, facecolors=UNKNOWN_FACE, edgecolors=UNKNOWN_HATCH, hatch="////", linewidths=0)
    )
    draw_countries(ax, linewidth=0.3, zorder=3)
    ax.set_aspect("equal")


def _outline(ax, cells: Iterable[str]) -> None:
    for ring in outline_rings(cells):
        lons, lats = zip(*ring, strict=True)
        ax.plot(lons, lats, color="black", linewidth=1.0, zorder=4)


def _extent(cells: Iterable[str], pad: float) -> tuple[float, float, float, float]:
    """``(west, east, south, north)`` around the centres of ``cells``, padded by ``pad`` degrees."""
    lats, lons = zip(*(h3.cell_to_latlng(cell) for cell in cells), strict=True)
    return min(lons) - pad, max(lons) + pad, min(lats) - pad, max(lats) + pad


def _ramp(fig, ax, palette: str, domain: Sequence[float], label: str) -> None:
    colours = [tuple(c / 255 for c in color_at(palette, t / 255)) for t in range(256)]
    mappable = plt.cm.ScalarMappable(
        norm=Normalize(domain[0], domain[1]), cmap=LinearSegmentedColormap.from_list(palette, colours)
    )
    bar = fig.colorbar(mappable, ax=ax, orientation="horizontal", fraction=0.05, pad=0.08)
    bar.set_label(f"{label} (low → high; clamped outside the domain)", fontsize=8)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "figures" / "surface-codec-parity.png")
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args(argv)
    catalog = json.loads((args.data_dir / "catalog.json").read_text(encoding="utf-8"))
    (grid_entry,) = catalog["grids"].values()
    grid = codec.decode((args.data_dir / grid_entry["url"]).read_bytes(), tier="grid")
    cells = [f"{cell:x}" for cell in grid.columns["h3"]]
    polygons, kept = h3_polygons(cells)

    flips: list[tuple[str, str, int, int, int]] = []
    counts: list[tuple[str, int, int]] = []
    worst = {field: 0.0 for field in codec.DETAIL_FIELDS}
    mismatched_values = compared_values = 0
    kept_layers: dict[str, tuple[codec.GosaContainer, codec.GosaContainer, dict]] = {}
    for ref in catalog["artifacts"]:
        render, detail, surface = _load(args.data_dir, ref)
        per_metric = []
        for metric in ("post_mean", "post_sd"):
            found = bin_flips(
                render.columns["support"],
                detail.columns[metric],
                render.columns[metric],
                ref["metric_domains"][metric],
            )
            flips += [(ref["id"], metric, *flip) for flip in found]
            per_metric.append(len(found))
        counts.append((ref["id"], *per_metric))
        errors = max_detail_error(detail.columns, surface["cells"])
        for field in codec.DETAIL_FIELDS:
            worst[field] = max(worst[field], errors[field])
        mismatched_values += sum(bit_mismatches(detail.columns, surface["cells"]).values())
        compared_values += len(surface["cells"]) * len(codec.DETAIL_FIELDS)
        if ref["id"] in {"hbs-rs334", "kir-3ds1"} or any(f[0] == ref["id"] for f in flips):
            kept_layers[ref["id"]] = (render, detail, ref)

    fig = plt.figure(figsize=(21, 15.5))
    grid_spec = fig.add_gridspec(3, 3, height_ratios=[1.15, 1, 0.9], hspace=0.2, wspace=0.16)

    summary = fig.add_subplot(grid_spec[0, 0])
    rows = range(len(counts))
    for column in (0, 1):
        for row, entry in zip(rows, counts, strict=True):
            value = entry[column + 1]
            summary.add_patch(Rectangle((column, row), 1, 1, color="#c0392b" if value else "#f2f4f6"))
            summary.text(column + 0.5, row + 0.5, str(value), ha="center", va="center", fontsize=7)
    summary.set(xlim=(0, 2), ylim=(len(counts), 0), xticks=[0.5, 1.5], xticklabels=["post_mean", "post_sd"])
    summary.set_yticks([row + 0.5 for row in rows], [entry[0] for entry in counts], fontsize=7)
    summary.set_title(
        f"(a) 32-bin flips, float32 render vs float64: {len(flips)} cell(s) in "
        f"{len(counts)} layers x 2 metrics",
        loc="left",
        fontsize=10,
    )

    flip_map = fig.add_subplot(grid_spec[0, 1])
    if flips:
        layer, metric, row, wide, narrow = flips[0]
        render, _, ref = kept_layers[layer]
        centre = cells[row]
        region = set(h3.grid_disk(centre, 6))
        local = [i for i, row_index in enumerate(kept) if cells[row_index] in region]
        _cell_map(
            flip_map,
            [polygons[i] for i in local],
            [kept[i] for i in local],
            render.columns["support"],
            render.columns[metric],
            ref["metric_domains"][metric],
            DEFAULT_PALETTE[metric],
        )
        for _, _, flipped, _, _ in (flip for flip in flips if flip[0] == layer and flip[1] == metric):
            lat, lon = h3.cell_to_latlng(cells[flipped])
            flip_map.add_patch(
                Circle((lon, lat), 0.9, fill=False, edgecolor="black", linewidth=1.6, zorder=4)
            )
        lat, lon = h3.cell_to_latlng(centre)
        flip_map.set(xlim=(lon - 7, lon + 7), ylim=(lat - 5, lat + 5))
        flip_map.set_title(
            f"(a) {layer} {metric}: {centre} moves from bin {wide} to bin {narrow}", loc="left", fontsize=10
        )
    else:
        flip_map.axis("off")
        flip_map.text(0.5, 0.5, "no 32-bin flips", ha="center", va="center", fontsize=14)

    note = fig.add_subplot(grid_spec[0, 2])
    note.axis("off")
    lines = [f"{field:<24s} {worst[field]:.3g}" for field in codec.DETAIL_FIELDS]
    note.text(
        0, 0.98, f"(d) max |detail - JSON|, {len(counts)} layers", fontsize=12, fontweight="bold", va="top"
    )
    note.text(0, 0.88, "\n".join(lines), family="monospace", fontsize=10, va="top", linespacing=1.6)
    note.text(
        0,
        0.40,
        f"float64 bit-pattern mismatches: {mismatched_values} of\n"
        f"{compared_values:,} cell values ({len(codec.DETAIL_FIELDS)} fields x {len(counts)} layers)\n"
        "Colour and height clamp to metric_domains;\ndisplayed numbers never do.\n"
        "Expected 0 and 0: every displayed number\ncomes from the detail tier.\n\n"
        f"Flips listed: {', '.join(f'{f[0]} {f[1]} {cells[f[2]]}' for f in flips) or 'none'}",
        fontsize=10,
        va="top",
    )

    hbs_render, _, hbs_ref = kept_layers["hbs-rs334"]
    hbs_axis = fig.add_subplot(grid_spec[1, 0])
    _cell_map(
        hbs_axis,
        polygons,
        kept,
        hbs_render.columns["support"],
        hbs_render.columns["post_mean"],
        hbs_ref["metric_domains"]["post_mean"],
        "rainbow",
    )
    hbs_axis.set(xlim=(-180, 180), ylim=(-60, 85))
    hbs_axis.set_title("(b) HbS render tier, post_mean palette bins (rainbow)", loc="left", fontsize=10)
    _ramp(fig, hbs_axis, "rainbow", hbs_ref["metric_domains"]["post_mean"], "HbS post_mean")

    kir_render, kir_detail, kir_ref = kept_layers["kir-3ds1"]
    drawn = set(kept)
    clamped = {
        metric: outside_domain(
            kir_render.columns["support"], kir_detail.columns[metric], kir_ref["metric_domains"][metric]
        )
        for metric in ("post_mean", "post_sd")
    }
    # One shared zoom extent, so the two zooms compare like for like. At world scale a res-4 cell is
    # about a pixel wide, so any outline there would cover the cells it marks.
    boxed = sorted({cells[row] for rows in clamped.values() for row in rows if row in drawn})
    west, east, south, north = _extent(boxed, pad=1.5) if boxed else (0.0, 0.0, 0.0, 0.0)
    in_zoom = [
        i
        for i, polygon in enumerate(polygons)
        if any(west <= x <= east and south <= y <= north for x, y in polygon)
    ]
    for column, metric in ((1, "post_mean"), (2, "post_sd")):
        domain = kir_ref["metric_domains"][metric]
        layer_args = (
            kir_render.columns["support"],
            kir_render.columns[metric],
            domain,
            DEFAULT_PALETTE[metric],
        )
        axis = fig.add_subplot(grid_spec[1, column])
        _cell_map(axis, polygons, kept, *layer_args)
        axis.set(xlim=(-180, 180), ylim=(-60, 85))
        axis.set_title(
            f"(c) kir-3ds1 {metric}: {len(clamped[metric])} cells outside metric_domains (boxed)",
            loc="left",
            fontsize=10,
        )
        _ramp(fig, axis, DEFAULT_PALETTE[metric], domain, f"kir-3ds1 {metric}")
        zoom = fig.add_subplot(grid_spec[2, column])
        if not boxed:
            zoom.axis("off")
            zoom.text(0.5, 0.5, "no cells outside metric_domains", ha="center", va="center", fontsize=14)
            continue
        axis.add_patch(
            Rectangle((west, south), east - west, north - south, fill=False, edgecolor="black", linewidth=1.0)
        )
        _cell_map(zoom, [polygons[i] for i in in_zoom], [kept[i] for i in in_zoom], *layer_args)
        _outline(zoom, [cells[row] for row in clamped[metric] if row in drawn])
        zoom.set(xlim=(west, east), ylim=(south, north))
        zoom.set_title(
            f"(c) kir-3ds1 {metric}, boxed region: clamped cells outlined (ramp above)",
            loc="left",
            fontsize=10,
        )

    legend_axis = fig.add_subplot(grid_spec[2, 0])
    legend_axis.axis("off")
    legend_axis.legend(
        handles=[
            Patch(facecolor=UNKNOWN_FACE, edgecolor=UNKNOWN_HATCH, hatch="////", label="unknown (no claim)"),
            Patch(
                facecolor="#888888", edgecolor="white", hatch="....", label="prior-dominated (palette colour)"
            ),
            Line2D([], [], color="black", linewidth=1.0, label="outline: cells outside metric_domains"),
            Patch(facecolor="none", edgecolor="black", label="box: the region zoomed in the row below"),
        ],
        loc="center",
        frameon=False,
        fontsize=11,
    )
    dropped = len(cells) - len(kept)
    fig.suptitle(
        f"GOSA web rendition parity — fitted surfaces only ({dropped} cells crossing ±180° not drawn)",
        fontsize=14,
        fontweight="bold",
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {args.out}: {len(flips)} flip(s), {mismatched_values} float64 mismatches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

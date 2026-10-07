#!/usr/bin/env python3
"""Review figure for the GOSA web rendition (Atlas design §11; fast-load spec §B.1, §B.5).

    python scripts/encode_atlas_web.py
    python scripts/plot_surface_codec_parity.py --out docs/figures/surface-codec-parity.png

Reads the encoded objects back through the codec and compares them with the canonical JSON.
(a) 32-bin palette quantisation from the float32 render tier versus float64, for 30 layers x 2
metrics, with a map around every flipped cell; (b) the HbS render-tier palette bins as the globe
draws them; (c) kir-3ds1, which has prior-dominated cells outside ``metric_domains`` in both
metrics, with clamped cells outlined; (d) the largest |detail - JSON| over all six fields.
Unknown cells are hatched and prior-dominated cells stippled in their palette colour: the figure
shows where there is no data, as the product does (AGENTS "Show the map"). Fitted surfaces only;
no observations are drawn. Bin and colour arithmetic mirror ``website/src/atlas``.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import h3  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402
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
MASKED = {codec.SUPPORT_CODES.index("unknown"), codec.SUPPORT_CODES.index("prior_dominated")}
UNKNOWN = codec.SUPPORT_CODES.index("unknown")
PRIOR_DOMINATED = codec.SUPPORT_CODES.index("prior_dominated")


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
    support: Sequence[int], values: Sequence[float], domain: Sequence[float], palette: str
) -> dict[int, tuple[int, int, int]]:
    """``paletteBinsForCells``: each bin takes the colour of its first non-masked cell in grid order."""
    colors: dict[int, tuple[int, int, int]] = {}
    for code, value in zip(support, values, strict=True):
        if code in MASKED:
            continue
        colors.setdefault(quantize(value, domain), color_at(palette, _position(value, domain)))
    return colors


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
    """Largest |detail - JSON| per field, plus a bit-pattern mismatch count (expected 0 and 0)."""
    errors: dict[str, float] = {}
    for field in codec.DETAIL_FIELDS:
        json_values = [cell[field] for cell in cells]
        errors[field] = max(abs(a - b) for a, b in zip(detail[field], json_values, strict=True))
        mismatched = struct.pack(f"<{len(cells)}d", *detail[field]) != struct.pack(
            f"<{len(cells)}d", *json_values
        )
        errors[f"{field}:bits"] = float(mismatched)
    return errors


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


def _cell_map(ax, polygons, kept, support, values, domain, palette, *, displayed=None) -> int:
    """Draw bins, hatched unknown and stippled prior-dominated cells; outline ``displayed`` values
    (float64) outside the domain and return how many there are."""
    colors = bin_colors(support, values, domain, palette)
    faces, unknown, prior, outside = [], [], [], []
    for polygon, row in zip(polygons, kept, strict=True):
        code, value = support[row], values[row]
        if code == UNKNOWN:
            unknown.append(polygon)
            continue
        rgb = colors.get(quantize(value, domain), color_at(palette, _position(value, domain)))
        target = prior if code == PRIOR_DOMINATED else faces
        target.append((polygon, tuple(channel / 255 for channel in rgb)))
        if displayed is not None and not domain[0] <= displayed[row] <= domain[1]:
            outside.append(polygon)
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
    if outside:
        ax.add_collection(PolyCollection(outside, facecolors="none", edgecolors="black", linewidths=0.5))
    draw_countries(ax, linewidth=0.3, zorder=3)
    ax.set_aspect("equal")
    return len(outside)


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
    bit_mismatches = 0
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
            bit_mismatches += int(errors[f"{field}:bits"])
        if ref["id"] in {"hbs-rs334", "kir-3ds1"} or any(f[0] == ref["id"] for f in flips):
            kept_layers[ref["id"]] = (render, detail, ref)

    fig = plt.figure(figsize=(21, 10.5))
    grid_spec = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.12, wspace=0.16)

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
    note.text(0, 0.98, "(d) max |detail - JSON|, 30 layers", fontsize=12, fontweight="bold", va="top")
    note.text(0, 0.88, "\n".join(lines), family="monospace", fontsize=10, va="top", linespacing=1.6)
    note.text(
        0,
        0.40,
        f"float64 bit-pattern mismatches: {bit_mismatches}\n"
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
    for column, metric in ((1, "post_mean"), (2, "post_sd")):
        axis = fig.add_subplot(grid_spec[1, column])
        clamped = _cell_map(
            axis,
            polygons,
            kept,
            kir_render.columns["support"],
            kir_render.columns[metric],
            kir_ref["metric_domains"][metric],
            DEFAULT_PALETTE[metric],
            displayed=kir_detail.columns[metric],
        )
        axis.set(xlim=(-180, 180), ylim=(-60, 85))
        axis.set_title(
            f"(c) kir-3ds1 {metric}: {clamped} cells outside metric_domains (outlined)",
            loc="left",
            fontsize=10,
        )
        _ramp(fig, axis, DEFAULT_PALETTE[metric], kir_ref["metric_domains"][metric], f"kir-3ds1 {metric}")

    fig.legend(
        handles=[
            Patch(facecolor=UNKNOWN_FACE, edgecolor=UNKNOWN_HATCH, hatch="////", label="unknown (no claim)"),
            Patch(
                facecolor="#888888", edgecolor="white", hatch="....", label="prior-dominated (palette colour)"
            ),
            Patch(facecolor="none", edgecolor="black", label="value outside metric_domains"),
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=9,
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
    print(f"wrote {args.out}: {len(flips)} flip(s), {bit_mismatches} float64 mismatches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

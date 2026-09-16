"""Plot CHELSA storage-consistency evidence offline (Atlas design §§4,7).

The native-block map and signed residual histogram remain climate storage
diagnostics. They are neither observations nor inferred genetic surfaces.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

SCHEMA = "chelsa-annual-consistency-v1"
FORMULA = "annual_raw == floor(sum(monthly_raw)/10)"
RESIDUAL = "10 * annual_raw - sum(monthly_raw)"
MONTHLY_ROLES = tuple(f"pr_{month:02d}" for month in range(1, 13))
ROLES = (*MONTHLY_ROLES, "bio12")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class EvidenceError(ValueError):
    """Raised when the aggregate cannot safely support the figure."""


@dataclass(frozen=True)
class PlotData:
    """Validated arrays and counts needed by the two-panel figure."""

    row_edges: NDArray[np.int64]
    col_edges: NDArray[np.int64]
    rates: NDArray[np.float64]
    residuals: NDArray[np.int64]
    residual_percentages: NDArray[np.float64]
    grid_cells: int
    comparable_cells: int
    excluded_cells: int
    failed_cells: int
    failure_percent: float
    maximum_block_failure_percent: float
    affine: tuple[float, float, float, float, float, float]


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{label} must be an array")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EvidenceError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise EvidenceError(f"{label} must be finite")
    return number


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _expected_asset_identity(role: str) -> tuple[str, str]:
    root = "https://os.unil.cloud.switch.ch/chelsa02/"
    if role in MONTHLY_ROLES:
        month = role[-2:]
        key = (
            "chelsa/global/climatologies/pr/1981-2010/"
            f"CHELSA_pr_{month}_1981-2010_V.2.1.tif"
        )
    else:
        key = (
            "chelsa/global/bioclim/bio12/1981-2010/"
            "CHELSA_bio12_1981-2010_V.2.1.tif"
        )
    return key, root + key


def _validate_assets(data: dict[str, Any], comparable_cells: int) -> None:
    assets = _sequence(data.get("assets"), "assets")
    _require(len(assets) == 13, "assets must contain exactly 13 entries")
    for expected_role, raw_asset in zip(ROLES, assets, strict=True):
        asset = _mapping(raw_asset, f"asset {expected_role}")
        _require(asset.get("role") == expected_role, "source roles are out of order")
        expected_key, expected_url = _expected_asset_identity(expected_role)
        _require(asset.get("object_key") == expected_key, f"wrong key for {expected_role}")
        _require(asset.get("public_url") == expected_url, f"wrong URL for {expected_role}")
        _integer(asset.get("size_bytes"), f"{expected_role}.size_bytes", minimum=1)
        _require(
            isinstance(asset.get("sha256"), str)
            and SHA256_PATTERN.fullmatch(asset["sha256"]) is not None,
            f"invalid SHA-256 for {expected_role}",
        )
        _require(asset.get("source_id") == "CHELSA_V2.1", "unexpected source ID")
        _require(asset.get("source_version") == "2.1", "unexpected source version")
        _require(asset.get("source_period") == "1981-2010", "unexpected source period")
        _require(asset.get("dtype") == "uint16", "unexpected source dtype")
        _require(asset.get("nodata") == 65535, "unexpected source nodata")
        _require(
            _integer(asset.get("native_valid_cells"), "native_valid_cells")
            == comparable_cells,
            "per-asset validity does not match the common comparable count",
        )
        packing = _mapping(asset.get("packing"), f"{expected_role}.packing")
        if expected_role in MONTHLY_ROLES:
            _require(packing.get("explicit") is True, "monthly packing must be explicit")
            _require(
                packing.get("stored_scale_present") is True
                and _number(packing.get("stored_scale_binary64"), "monthly scale") == 0.1,
                "monthly scale must be the explicit binary64 0.1 value",
            )
            _require(
                packing.get("stored_scale_encoded_text") == "0.100000000000000006",
                "monthly encoded scale text changed",
            )
            _require(
                packing.get("stored_offset_present") is True
                and _number(packing.get("stored_offset"), "monthly offset") == 0.0,
                "monthly offset must be explicit zero",
            )
            _require(asset.get("month") == int(expected_role[-2:]), "wrong month identity")
        else:
            _require(packing.get("explicit") is False, "annual packing must remain absent")
            _require(
                packing.get("stored_scale_present") is False
                and packing.get("stored_scale") is None
                and packing.get("stored_offset_present") is False
                and packing.get("stored_offset") is None,
                "annual stored SCALE/OFFSET absence was not preserved",
            )
            _require(
                _number(packing.get("gdal_reader_default_scale"), "annual reader scale")
                == 1.0
                and _number(
                    packing.get("gdal_reader_default_offset"), "annual reader offset"
                )
                == 0.0
                and packing.get("reader_defaults_qualified_as_physical_packing") is False,
                "annual GDAL defaults must remain unqualified",
            )


def _validate_blocks(
    result: dict[str, Any],
    width: int,
    height: int,
    block_width: int,
    block_height: int,
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]:
    row_edges = np.array([*range(0, height, block_height), height], dtype=np.int64)
    col_edges = np.array([*range(0, width, block_width), width], dtype=np.int64)
    shape = (len(row_edges) - 1, len(col_edges) - 1)
    rates = np.full(shape, np.nan, dtype=np.float64)
    blocks = _sequence(result.get("blocks"), "whole_grid.blocks")
    _require(len(blocks) == shape[0] * shape[1], "block count does not tile the grid")
    seen: set[tuple[int, int]] = set()
    sums = {
        "grid_cells": 0,
        "comparable_cells": 0,
        "failed_relation_cells": 0,
        "excluded_cells": 0,
    }
    block_minima: list[int] = []
    block_maxima: list[int] = []
    for index, raw_block in enumerate(blocks):
        block = _mapping(raw_block, f"block {index}")
        row = _integer(block.get("block_row"), f"block {index} row")
        col = _integer(block.get("block_col"), f"block {index} col")
        _require(row < shape[0] and col < shape[1], "block index is outside the grid")
        _require((row, col) not in seen, "duplicate block index")
        seen.add((row, col))
        expected_height = int(row_edges[row + 1] - row_edges[row])
        expected_width = int(col_edges[col + 1] - col_edges[col])
        _require(block.get("row_off") == int(row_edges[row]), "wrong block row offset")
        _require(block.get("col_off") == int(col_edges[col]), "wrong block column offset")
        _require(block.get("height") == expected_height, "wrong clipped block height")
        _require(block.get("width") == expected_width, "wrong clipped block width")
        grid_cells = _integer(block.get("grid_cells"), "block grid_cells")
        comparable = _integer(block.get("comparable_cells"), "block comparable_cells")
        failures = _integer(block.get("failed_relation_cells"), "block failures")
        excluded = _integer(block.get("excluded_cells"), "block exclusions")
        _require(grid_cells == expected_height * expected_width, "wrong block cell count")
        _require(failures <= comparable <= grid_cells, "invalid block comparison counts")
        _require(comparable + excluded == grid_cells, "block exclusions do not reconcile")
        minimum = _integer(
            block.get("minimum_residual_raw_tenths"), "block minimum", minimum=-20
        )
        maximum = _integer(
            block.get("maximum_residual_raw_tenths"), "block maximum", minimum=-20
        )
        _require(minimum <= maximum <= 20, "invalid block residual range")
        block_minima.append(minimum)
        block_maxima.append(maximum)
        rates[row, col] = 100.0 * failures / comparable if comparable else np.nan
        for key in sums:
            sums[key] += _integer(block.get(key), f"block {key}")
    _require(len(seen) == shape[0] * shape[1], "blocks do not cover every tile")
    for key, total in sums.items():
        _require(total == _integer(result.get(key), f"whole_grid.{key}"), f"{key} mismatch")
    _require(
        min(block_minima) == result.get("minimum_residual_raw_tenths")
        and max(block_maxima) == result.get("maximum_residual_raw_tenths"),
        "block residual extrema do not reconcile",
    )
    return row_edges, col_edges, rates


def validate_evidence(data: dict[str, Any]) -> PlotData:
    """Validate scientific refusals, source identities, tiling, and accounting."""

    _require(data.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    status = _mapping(data.get("status"), "status")
    _require(
        status.get("evidence") == "automated_proposal" and status.get("review") == "pending",
        "evidence status must remain automated_proposal/pending",
    )
    eligibility = _mapping(data.get("eligibility"), "eligibility")
    _require(
        eligibility.get("scientific_model") is False
        and eligibility.get("publication") is False,
        "scientific model and publication eligibility must both remain false",
    )
    scope = _mapping(data.get("scope"), "scope")
    _require(
        scope.get("observations_or_inferred_genetic_surfaces") is False,
        "climate storage evidence cannot be labeled as genetic evidence",
    )
    grid = _mapping(data.get("grid"), "grid")
    width = _integer(grid.get("width"), "grid.width", minimum=1)
    height = _integer(grid.get("height"), "grid.height", minimum=1)
    grid_cells = _integer(grid.get("grid_cells"), "grid.grid_cells", minimum=1)
    _require(grid_cells == width * height, "grid dimensions do not match grid_cells")
    _require(grid.get("crs") == "EPSG:4326", "grid CRS must be EPSG:4326")
    raw_affine = _sequence(grid.get("affine"), "grid.affine")
    _require(len(raw_affine) == 6, "grid affine must contain six values")
    affine = tuple(_number(value, "grid affine value") for value in raw_affine)
    dx, shear_x, _west, shear_y, dy, _north = affine
    _require(shear_x == shear_y == 0.0 and dx > 0.0 and dy < 0.0, "unsupported affine")
    block_width = _integer(grid.get("native_block_width"), "native block width", minimum=1)
    block_height = _integer(grid.get("native_block_height"), "native block height", minimum=1)
    _require(
        grid.get("edge_blocks_clipped_to_affine_extent") is True
        and grid.get("native_validity_includes_land_and_ocean") is True
        and grid.get("land_mask_applied") is False
        and grid.get("area_weighted") is False,
        "grid validity and weighting limitations changed",
    )
    result = _mapping(data.get("whole_grid"), "whole_grid")
    comparable_cells = _integer(result.get("comparable_cells"), "comparable_cells")
    excluded_cells = _integer(result.get("excluded_cells"), "excluded_cells")
    failed_cells = _integer(result.get("failed_relation_cells"), "failed_relation_cells")
    exact_cells = _integer(result.get("exact_match_cells"), "exact_match_cells")
    _require(result.get("formula") == FORMULA, "unexpected tested formula")
    _require(result.get("residual_definition") == RESIDUAL, "unexpected residual definition")
    _require(result.get("area_weighted") is False, "whole-grid counts cannot be weighted")
    _require(result.get("grid_cells") == grid_cells, "whole-grid size does not match grid")
    _require(comparable_cells + excluded_cells == grid_cells, "global exclusions do not reconcile")
    _require(exact_cells + failed_cells == comparable_cells, "formula outcomes do not reconcile")
    _validate_assets(data, comparable_cells)
    row_edges, col_edges, rates = _validate_blocks(
        result, width, height, block_width, block_height
    )
    raw_histogram = _mapping(
        result.get("residual_histogram_raw_tenths"), "residual histogram"
    )
    expected_keys = {str(value) for value in range(-20, 21)}
    _require(set(raw_histogram) == expected_keys, "residual histogram must span -20 through 20")
    histogram = {
        int(key): _integer(value, f"histogram[{key}]")
        for key, value in raw_histogram.items()
    }
    below = _integer(result.get("residual_below_minus20"), "residual below -20")
    above = _integer(result.get("residual_above20"), "residual above 20")
    _require(below == above == 0, "residual overflow would make the plotted histogram incomplete")
    _require(sum(histogram.values()) == comparable_cells, "histogram total does not reconcile")
    occupied = [value for value, count in histogram.items() if count]
    _require(bool(occupied), "histogram has no comparable values")
    minimum = _integer(
        result.get("minimum_residual_raw_tenths"), "minimum residual", minimum=-20
    )
    maximum = _integer(
        result.get("maximum_residual_raw_tenths"), "maximum residual", minimum=-20
    )
    _require(min(occupied) == minimum and max(occupied) == maximum, "histogram extrema mismatch")
    absolute_sum = sum(abs(value) * count for value, count in histogram.items())
    _require(
        absolute_sum == _integer(
            result.get("sum_absolute_residual_raw_tenths"), "absolute residual sum"
        ),
        "absolute residual sum does not reconcile",
    )
    failure_count = sum(count for value, count in histogram.items() if not -9 <= value <= 0)
    _require(failure_count == failed_cells, "histogram failures do not reconcile")
    _require(
        result.get("exact_formula_failure_residuals") == [-10]
        and histogram[-10] == failed_cells,
        "exact formula failures must all have residual -10",
    )
    worst = _mapping(data.get("selected_worst_cell_independent_check"), "worst-cell check")
    monthly_values = _sequence(worst.get("monthly_raw_values"), "worst-cell monthly values")
    _require(
        len(monthly_values) == 12
        and all(type(value) is int and value >= 0 for value in monthly_values),
        "worst-cell monthly values must be twelve nonnegative integers",
    )
    monthly_sum = sum(monthly_values)
    annual_raw = _integer(worst.get("annual_raw"), "worst-cell annual value")
    _require(monthly_sum == worst.get("monthly_raw_sum") == 1520, "worst-cell sum changed")
    _require(annual_raw == 151, "worst-cell annual value changed")
    _require(
        10 * annual_raw - monthly_sum == worst.get("signed_residual_raw_tenths") == -10,
        "worst-cell residual does not reconcile",
    )
    _require(
        worst.get("all_native_masks_permit_comparison") is True
        and worst.get("all_raw_values_independently_reproduced") is True,
        "worst-cell independent check is incomplete",
    )
    residuals = np.arange(minimum, maximum + 1, dtype=np.int64)
    percentages = np.array(
        [100.0 * histogram[int(value)] / comparable_cells for value in residuals],
        dtype=np.float64,
    )
    maximum_block_rate = float(np.nanmax(rates))
    _require(math.isfinite(maximum_block_rate), "no block has comparable cells")
    return PlotData(
        row_edges=row_edges,
        col_edges=col_edges,
        rates=rates,
        residuals=residuals,
        residual_percentages=percentages,
        grid_cells=grid_cells,
        comparable_cells=comparable_cells,
        excluded_cells=excluded_cells,
        failed_cells=failed_cells,
        failure_percent=100.0 * failed_cells / comparable_cells,
        maximum_block_failure_percent=maximum_block_rate,
        affine=affine,
    )


def load_evidence(path: Path) -> dict[str, Any]:
    """Load one aggregate JSON object without accessing source rasters or the network."""

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"could not load evidence: {error}") from error
    return _mapping(data, "evidence")


def render(plot: PlotData, out: Path) -> None:
    """Render a validated aggregate to a new PNG path."""

    dx, _shear_x, west, _shear_y, dy, north = plot.affine
    x_edges = west + plot.col_edges * dx
    y_edges = north + plot.row_edges * dy
    plt.rcParams.update({"font.size": 10, "axes.titleweight": "bold"})
    figure, (map_axis, histogram_axis) = plt.subplots(
        1,
        2,
        figsize=(14, 6.3),
        gridspec_kw={"width_ratios": [1.55, 1]},
    )
    figure.subplots_adjust(left=0.065, right=0.985, top=0.76, bottom=0.28, wspace=0.25)
    figure.suptitle(
        "CHELSA precipitation: annual versus monthly stored integers", fontsize=17, y=0.96
    )
    figure.text(
        0.5,
        0.885,
        "1981–2010 · V2.1 · post-hoc internal consistency check",
        ha="center",
        color="#444444",
    )
    figure.text(
        0.5,
        0.83,
        f"{plot.comparable_cells:,} comparable cells  |  "
        f"{plot.excluded_cells:,} excluded  |  "
        f"{plot.failed_cells:,} exact-formula failures "
        f"({plot.failure_percent:.4f}%)",
        ha="center",
        fontsize=11,
    )
    color_map = plt.get_cmap("YlOrRd").copy()
    color_map.set_bad("#cccccc")
    mesh = map_axis.pcolormesh(
        x_edges,
        y_edges,
        np.ma.masked_invalid(plot.rates),
        shading="flat",
        cmap=color_map,
        vmin=0.0,
        vmax=plot.maximum_block_failure_percent,
        rasterized=True,
    )
    map_axis.set_title("Exact-formula failures within native blocks", fontsize=11, pad=12)
    map_axis.set(xlabel="Longitude (degrees)", ylabel="Latitude (degrees)")
    map_axis.set_xlim(float(x_edges[0]), float(x_edges[-1]))
    map_axis.set_ylim(float(y_edges[-1]), float(y_edges[0]))
    map_axis.set_xticks([-180, -120, -60, 0, 60, 120, 180])
    map_axis.set_yticks([-90, -60, -30, 0, 30, 60])
    color_bar = figure.colorbar(
        mesh, ax=map_axis, orientation="horizontal", pad=0.24, fraction=0.065
    )
    color_bar.set_label("Failures / comparable cells in block (%)", fontsize=10)
    colors = ["#c75623" if value == -10 else "#286f8e" for value in plot.residuals]
    histogram_axis.bar(plot.residuals, plot.residual_percentages, color=colors, width=0.8)
    histogram_axis.set_title("Signed residual across comparable cells", fontsize=11, pad=12)
    histogram_axis.set(
        xlabel="10 × annual integer − sum of monthly integers",
        ylabel="Comparable cells (%)",
    )
    histogram_axis.set_xticks(plot.residuals)
    histogram_axis.set_ylim(0.0, float(plot.residual_percentages.max()) * 1.2)
    histogram_axis.grid(axis="y", alpha=0.2)
    histogram_axis.set_axisbelow(True)
    histogram_axis.annotate(
        f"Exact formula fails\n{plot.failure_percent:.4f}%",
        xy=(-10, plot.failure_percent),
        xytext=(-9.7, 3.3),
        fontsize=10,
        color="#a6421b",
        arrowprops={"arrowstyle": "->", "color": "#a6421b"},
    )
    for axis in (map_axis, histogram_axis):
        axis.spines[["top", "right"]].set_visible(False)
    figure.text(
        0.065,
        0.075,
        "Tested formula: annual integer = floor(sum of monthly integers / 10). "
        "Native blocks are 512 × 512 cells, clipped at edges.\n"
        "Native validity includes land and ocean; cells are not area-weighted. "
        "Gray would indicate a block with no comparable cells.\n"
        "Annual physical scaling is unverified. This diagnostic establishes neither "
        "climate accuracy nor genetic predictive value.",
        fontsize=9,
        color="#444444",
        linespacing=1.6,
    )
    try:
        with out.open("xb") as stream:
            figure.savefig(
                stream,
                format="png",
                dpi=180,
                facecolor="white",
                metadata={"Software": "genomeOS"},
            )
    finally:
        plt.close(figure)


def main(evidence: Path, out: Path) -> None:
    """Validate the complete aggregate before exclusively creating the PNG."""

    if out.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {out}")
    if not out.parent.is_dir():
        raise FileNotFoundError(f"output directory does not exist: {out.parent}")
    plot = validate_evidence(load_evidence(evidence))
    render(plot, out)
    print(
        f"wrote {out} from {plot.comparable_cells:,} comparable cells; "
        f"{plot.failed_cells:,} exact-formula failures; "
        f"{plot.excluded_cells:,} excluded"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    main(arguments.evidence, arguments.out)

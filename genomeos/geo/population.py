"""Gridded population denominators aggregated to H3 (design §9, P3).

§9 needs a population figure per H3 cell for two distinct jobs: the denominator of any per-capita
statistic, and the multiplier that turns an allele frequency into an expected number of people.
The source is WorldPop's gridded population; see `scripts/fetch_worldpop.py`.

**Aggregation is a sum, not a sample.** A cell's population is the total of every raster pixel
whose centre falls inside it. Sampling the raster at cell centres instead would be fast and
badly wrong: population is concentrated in a small fraction of pixels, so a centre sample either
lands on a city and overstates the cell by orders of magnitude, or misses it and reports empty
land where millions live.

**Nodata is not zero.** WorldPop marks ocean and unmapped land as nodata. §9 refuses to emit a
burden number where no denominator exists, and that refusal is only possible if "nobody lives
here" is distinguishable from "we have no raster coverage here". So a cell with valid pixels
summing to zero is emitted with `population = 0.0`, while a cell with no valid pixels at all is
absent from the output entirely.

Establishing coverage exactly would mean an H3 lookup for every land pixel, populated or not —
hundreds of millions of them globally. Instead, populated pixels are mapped exactly and empty-
but-valid pixels are sampled every `coverage_stride`-th pixel, which is ample to answer a
yes/no question about a cell spanning roughly 1,700 pixels at res 4. The stride is recorded on
the result.

Reading is windowed because the global 1 km mosaic is ~900 MB on disk and would need several GB
as a dense array. This is offline batch work by design (§5), not a serving-path operation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from genomeos.geo.h3util import RESOLUTION_LADDER, _check_resolution

#: Recorded per artifact so a published burden number states where its denominator came from
#: (§6's `denominator_source`).
WORLDPOP_SOURCE = "worldpop-1km-unconstrained"


@dataclass(frozen=True)
class PopulationGrid:
    """Population per H3 cell, plus what produced it."""

    cells: pd.DataFrame  # h3_index, population
    resolution: int
    source: str
    pixels_counted: int
    pixels_nodata: int
    coverage_stride: int

    def __str__(self) -> str:
        total = self.cells["population"].sum()
        return (
            f"{len(self.cells):,} H3 res-{self.resolution} cells, "
            f"total population {total:,.0f} ({self.source}); "
            f"{self.pixels_counted:,} pixels counted, {self.pixels_nodata:,} nodata"
        )


def aggregate_raster_to_h3(
    raster_path: Path,
    resolution: int,
    *,
    source: str = WORLDPOP_SOURCE,
    window_size: int = 1024,
    coverage_stride: int = 16,
) -> PopulationGrid:
    """Sum a population raster into H3 cells at `resolution`.

    Windowed, and windows that are entirely nodata are skipped without any H3 work — most of a
    global raster is ocean, so this is the difference between minutes and hours.

    Cells covered by valid but empty pixels are emitted with population 0.0; cells with no valid
    pixels are absent. See the module docstring on `coverage_stride`.
    """
    import h3
    import rasterio
    from rasterio.windows import Window

    _check_resolution(resolution)

    totals: dict[str, float] = defaultdict(float)
    counted = nodata_count = 0

    with rasterio.open(raster_path) as src:
        nodata = src.nodata
        for row_off in range(0, src.height, window_size):
            height = min(window_size, src.height - row_off)
            for col_off in range(0, src.width, window_size):
                width = min(window_size, src.width - col_off)
                window = Window(col_off, row_off, width, height)
                block = src.read(1, window=window)

                valid = np.isfinite(block)
                if nodata is not None:
                    valid &= block != nodata
                nodata_count += int((~valid).sum())

                if not valid.any():
                    continue

                populated = valid & (block > 0)
                rows, cols = np.nonzero(populated)
                if len(rows):
                    values = block[rows, cols].astype(float)
                    lons, lats = rasterio.transform.xy(
                        src.transform, rows + row_off, cols + col_off, offset="center"
                    )
                    for lat, lon, value in zip(lats, lons, values, strict=True):
                        cell = h3.latlng_to_cell(float(lat), float(lon), resolution)
                        totals[cell] += float(value)
                    counted += len(values)

                # Coverage only: valid pixels with no population still prove the cell is mapped.
                empty_rows, empty_cols = np.nonzero(valid & (block <= 0))
                if len(empty_rows):
                    empty_rows = empty_rows[::coverage_stride]
                    empty_cols = empty_cols[::coverage_stride]
                    lons, lats = rasterio.transform.xy(
                        src.transform, empty_rows + row_off, empty_cols + col_off, offset="center"
                    )
                    for lat, lon in zip(lats, lons, strict=True):
                        totals.setdefault(
                            h3.latlng_to_cell(float(lat), float(lon), resolution), 0.0
                        )

    cells = pd.DataFrame(
        {"h3_index": list(totals), "population": [totals[k] for k in totals]}
    ).sort_values("h3_index", ignore_index=True)

    return PopulationGrid(
        cells=cells,
        resolution=resolution,
        source=source,
        pixels_counted=counted,
        pixels_nodata=nodata_count,
        coverage_stride=coverage_stride,
    )


def births_from_population(
    cells: pd.DataFrame,
    crude_birth_rate: float | pd.Series,
    *,
    denominator_source: str = WORLDPOP_SOURCE,
) -> pd.DataFrame:
    """Annual births per cell: population × crude birth rate (§9).

    §9 states this is an approximation because no *global* gridded birth raster exists, and
    requires it recorded in `denominator_source` rather than left implicit — so the returned
    frame carries the source string and the CBR treatment in its column names.

    Worth noting for #96: WorldPop does publish per-country gridded birth rasters, so this
    approximation is avoidable country by country even though no global mosaic exists.
    """
    if isinstance(crude_birth_rate, float | int):
        if not 0.0 <= crude_birth_rate <= 1.0:
            raise ValueError("crude_birth_rate must be a proportion in [0, 1]")
    elif ((crude_birth_rate < 0.0) | (crude_birth_rate > 1.0)).any():
        raise ValueError("crude_birth_rate must be a proportion in [0, 1]")

    out = cells.copy()
    out["births"] = out["population"] * crude_birth_rate
    out["denominator_source"] = f"{denominator_source}+cbr"
    return out


def resolution_ladder_grids(
    raster_path: Path, resolutions: tuple[int, ...] = RESOLUTION_LADDER, **kwargs
) -> dict[int, PopulationGrid]:
    """Aggregate once per rung of the resolution ladder (§6)."""
    return {res: aggregate_raster_to_h3(raster_path, res, **kwargs) for res in resolutions}

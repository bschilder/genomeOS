"""Population denominator aggregation (design §9).

Tests run against small synthetic rasters, never the 870 MB global mosaic: the aggregation logic
is what needs verifying, and a hermetic test is worth more than a slow one.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

rasterio = pytest.importorskip("rasterio")

from genomeos.geo.h3util import cell_for  # noqa: E402
from genomeos.geo.population import (  # noqa: E402
    aggregate_raster_to_h3,
    births_from_population,
    resolution_ladder_grids,
)

NODATA = -9999.0


def _raster(tmp_path: Path, values: np.ndarray, *, west=0.0, north=0.0, pixel=0.1) -> Path:
    """A tiny north-up raster in WGS84, one band, with NODATA marked."""
    path = tmp_path / "pop.tif"
    transform = rasterio.transform.from_origin(west, north, pixel, pixel)
    with rasterio.open(
        path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1],
        count=1, dtype="float32", crs="EPSG:4326", transform=transform, nodata=NODATA,
    ) as dst:
        dst.write(values.astype("float32"), 1)
    return path


def test_population_is_summed_not_sampled(tmp_path):
    """A cell's population is the total of its pixels; sampling a centre would miss cities."""
    values = np.array([[10.0, 20.0], [30.0, 40.0]])
    grid = aggregate_raster_to_h3(_raster(tmp_path, values), 4)
    assert grid.cells["population"].sum() == pytest.approx(100.0)


def test_pixels_in_the_same_cell_are_combined(tmp_path):
    """These four adjacent 0.1 degree pixels fall in one res-4 cell."""
    grid = aggregate_raster_to_h3(_raster(tmp_path, np.full((2, 2), 5.0), pixel=0.01), 4)
    assert len(grid.cells) == 1
    assert grid.cells["population"].iloc[0] == pytest.approx(20.0)


def test_nodata_is_excluded_from_the_total(tmp_path):
    values = np.array([[10.0, NODATA], [NODATA, 40.0]])
    grid = aggregate_raster_to_h3(_raster(tmp_path, values), 4)
    assert grid.cells["population"].sum() == pytest.approx(50.0)
    assert grid.pixels_nodata == 2


def test_a_covered_but_empty_cell_reports_zero_rather_than_vanishing(tmp_path):
    """§9 must distinguish 'nobody lives here' from 'no coverage'; only the latter refuses."""
    grid = aggregate_raster_to_h3(_raster(tmp_path, np.zeros((2, 2)), pixel=0.01), 4, coverage_stride=1)
    assert len(grid.cells) == 1
    assert grid.cells["population"].iloc[0] == 0.0


def test_an_all_nodata_raster_produces_no_cells_at_all(tmp_path):
    """No coverage means no denominator, so the burden engine refuses downstream."""
    grid = aggregate_raster_to_h3(_raster(tmp_path, np.full((2, 2), NODATA)), 4)
    assert grid.cells.empty


def test_cells_are_the_ones_the_coordinates_fall_in(tmp_path):
    values = np.array([[7.0]])
    path = _raster(tmp_path, values, west=3.0, north=8.0, pixel=0.1)
    grid = aggregate_raster_to_h3(path, 4)
    expected = cell_for(8.0 - 0.05, 3.0 + 0.05, 4)
    assert grid.cells["h3_index"].iloc[0] == expected


def test_the_resolution_ladder_is_aggregated_in_one_pass_each(tmp_path):
    grids = resolution_ladder_grids(_raster(tmp_path, np.full((4, 4), 2.0)), (4, 5, 6))
    assert set(grids) == {4, 5, 6}
    for res, grid in grids.items():
        assert grid.resolution == res
        assert grid.cells["population"].sum() == pytest.approx(32.0)
    assert len(grids[6].cells) >= len(grids[4].cells), "finer cells cannot be fewer"


def test_an_off_ladder_resolution_is_refused(tmp_path):
    with pytest.raises(ValueError, match="ladder"):
        aggregate_raster_to_h3(_raster(tmp_path, np.full((2, 2), 1.0)), 9)


def test_the_source_is_recorded_for_the_artifact(tmp_path):
    grid = aggregate_raster_to_h3(_raster(tmp_path, np.full((2, 2), 1.0)), 4, source="test-source")
    assert grid.source == "test-source"
    assert "test-source" in str(grid)


# --- births (§9) ---


def test_births_are_population_times_the_crude_birth_rate():
    cells = pd.DataFrame({"h3_index": ["a", "b"], "population": [1000.0, 2000.0]})
    out = births_from_population(cells, 0.03)
    assert list(out["births"]) == pytest.approx([30.0, 60.0])


def test_births_record_that_a_crude_birth_rate_was_applied():
    """§9 requires the approximation recorded in denominator_source, not left implicit."""
    cells = pd.DataFrame({"h3_index": ["a"], "population": [1000.0]})
    out = births_from_population(cells, 0.03)
    assert out["denominator_source"].iloc[0].endswith("+cbr")


def test_a_per_cell_birth_rate_is_supported():
    cells = pd.DataFrame({"h3_index": ["a", "b"], "population": [1000.0, 1000.0]})
    out = births_from_population(cells, pd.Series([0.01, 0.05]))
    assert list(out["births"]) == pytest.approx([10.0, 50.0])


@pytest.mark.parametrize("bad", [1.5, -0.1])
def test_an_implausible_birth_rate_is_refused(bad):
    cells = pd.DataFrame({"h3_index": ["a"], "population": [1000.0]})
    with pytest.raises(ValueError, match="crude_birth_rate"):
        births_from_population(cells, bad)

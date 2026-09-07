"""Population denominator aggregation (design §9).

Tests run against small synthetic rasters, never the 870 MB global mosaic: the aggregation logic
is what needs verifying, and a hermetic test is worth more than a slow one.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

rasterio = pytest.importorskip("rasterio")

from genomeos.geo.h3util import cell_for  # noqa: E402
from genomeos.geo.population import (  # noqa: E402
    PopulationGrid,
    aggregate_raster_to_h3,
    births_from_population,
    publication_target_cells,
    resolution_ladder_grids,
)
from scripts.build_population_grid import (  # noqa: E402
    build_population_grid,
    population_grid_manifest_path,
    read_population_grid,
)

NODATA = -9999.0
ISLAND_FIXTURE = Path(__file__).parent / "fixtures" / "worldpop_small_islands.csv"


def _island_grid() -> PopulationGrid:
    source = pd.read_csv(ISLAND_FIXTURE)
    return PopulationGrid(
        cells=source[["h3_index", "population"]],
        resolution=3,
        source=str(source["source"].iloc[0]),
        source_version=str(source["source_version"].iloc[0]),
        pixels_counted=2,
        pixels_nodata=0,
        coverage_stride=16,
    )


def test_publication_target_keeps_population_backed_small_islands():
    targets = publication_target_cells(_island_grid(), ["835494fffffffff"])
    assert "835494fffffffff" in targets, "Praia/Cabo Verde must survive target selection"
    assert "833f30fffffffff" in targets, "Malta must survive target selection"
    assert "835969fffffffff" not in targets, "valid zero population is not a target"


def test_publication_target_refuses_zero_population_observation_cell():
    with pytest.raises(ValueError, match="zero population"):
        publication_target_cells(_island_grid(), ["835969fffffffff"])


def test_publication_target_refuses_observation_without_worldpop_coverage():
    with pytest.raises(ValueError, match="no WorldPop coverage"):
        publication_target_cells(_island_grid(), ["83754efffffffff"])


def test_publication_target_refuses_duplicate_population_cells():
    grid = _island_grid()
    duplicate = pd.concat([grid.cells, grid.cells.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        publication_target_cells(
            PopulationGrid(
                cells=duplicate,
                resolution=grid.resolution,
                source=grid.source,
                source_version=grid.source_version,
                pixels_counted=grid.pixels_counted,
                pixels_nodata=grid.pixels_nodata,
                coverage_stride=grid.coverage_stride,
            ),
            [],
        )


def test_publication_target_refuses_mismatched_h3_resolution():
    grid = _island_grid()
    cells = grid.cells.copy()
    cells.loc[0, "h3_index"] = "845494bffffffff"
    with pytest.raises(ValueError, match="resolution 3"):
        publication_target_cells(
            PopulationGrid(
                cells=cells,
                resolution=grid.resolution,
                source=grid.source,
                source_version=grid.source_version,
                pixels_counted=grid.pixels_counted,
                pixels_nodata=grid.pixels_nodata,
                coverage_stride=grid.coverage_stride,
            ),
            [],
        )


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
    grid = aggregate_raster_to_h3(
        _raster(tmp_path, values), 4, source_version="fixture-2020"
    )
    assert grid.cells["population"].sum() == pytest.approx(100.0)


def test_pixels_in_the_same_cell_are_combined(tmp_path):
    """These four adjacent 0.1 degree pixels fall in one res-4 cell."""
    grid = aggregate_raster_to_h3(
        _raster(tmp_path, np.full((2, 2), 5.0), pixel=0.01),
        4,
        source_version="fixture-2020",
    )
    assert len(grid.cells) == 1
    assert grid.cells["population"].iloc[0] == pytest.approx(20.0)


def test_nodata_is_excluded_from_the_total(tmp_path):
    values = np.array([[10.0, NODATA], [NODATA, 40.0]])
    grid = aggregate_raster_to_h3(
        _raster(tmp_path, values), 4, source_version="fixture-2020"
    )
    assert grid.cells["population"].sum() == pytest.approx(50.0)
    assert grid.pixels_nodata == 2


def test_a_covered_but_empty_cell_reports_zero_rather_than_vanishing(tmp_path):
    """§9 must distinguish 'nobody lives here' from 'no coverage'; only the latter refuses."""
    grid = aggregate_raster_to_h3(
        _raster(tmp_path, np.zeros((2, 2)), pixel=0.01),
        4,
        source_version="fixture-2020",
        coverage_stride=1,
    )
    assert len(grid.cells) == 1
    assert grid.cells["population"].iloc[0] == 0.0


def test_an_all_nodata_raster_produces_no_cells_at_all(tmp_path):
    """No coverage means no denominator, so the burden engine refuses downstream."""
    grid = aggregate_raster_to_h3(
        _raster(tmp_path, np.full((2, 2), NODATA)),
        4,
        source_version="fixture-2020",
    )
    assert grid.cells.empty


def test_cells_are_the_ones_the_coordinates_fall_in(tmp_path):
    values = np.array([[7.0]])
    path = _raster(tmp_path, values, west=3.0, north=8.0, pixel=0.1)
    grid = aggregate_raster_to_h3(path, 4, source_version="fixture-2020")
    expected = cell_for(8.0 - 0.05, 3.0 + 0.05, 4)
    assert grid.cells["h3_index"].iloc[0] == expected


def test_the_resolution_ladder_is_aggregated_in_one_pass_each(tmp_path):
    grids = resolution_ladder_grids(
        _raster(tmp_path, np.full((4, 4), 2.0)),
        (4, 5, 6),
        source_version="fixture-2020",
    )
    assert set(grids) == {4, 5, 6}
    for res, grid in grids.items():
        assert grid.resolution == res
        assert grid.cells["population"].sum() == pytest.approx(32.0)
    assert len(grids[6].cells) >= len(grids[4].cells), "finer cells cannot be fewer"


def test_an_off_ladder_resolution_is_refused(tmp_path):
    with pytest.raises(ValueError, match="ladder"):
        aggregate_raster_to_h3(
            _raster(tmp_path, np.full((2, 2), 1.0)),
            9,
            source_version="fixture-2020",
        )


def test_the_source_is_recorded_for_the_artifact(tmp_path):
    grid = aggregate_raster_to_h3(
        _raster(tmp_path, np.full((2, 2), 1.0)),
        4,
        source="test-source",
        source_version="fixture-2020",
    )
    assert grid.source == "test-source"
    assert "test-source" in str(grid)


def test_population_source_version_is_required(tmp_path):
    with pytest.raises(ValueError, match="source_version"):
        aggregate_raster_to_h3(
            _raster(tmp_path, np.full((2, 2), 1.0)),
            4,
            source_version="",
        )


def test_population_grid_builder_writes_source_version_and_hash(tmp_path):
    out = tmp_path / "worldpop-res4.parquet"
    result = build_population_grid(
        _raster(tmp_path, np.array([[10.0, 20.0]])),
        out,
        resolution=4,
        source_version="fixture-2020",
    )
    saved = pd.read_parquet(out)
    assert set(saved["source"]) == {"worldpop-1km-unconstrained"}
    assert set(saved["source_version"]) == {"fixture-2020"}
    assert result.source_version == "fixture-2020"
    manifest = json.loads(population_grid_manifest_path(out).read_text())
    assert manifest == {
        "coverage_stride": 16,
        "n_cells": len(saved),
        "parquet_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "pixels_counted": 2,
        "pixels_nodata": 0,
        "population_grid_format": 1,
        "resolution": 4,
        "source": "worldpop-1km-unconstrained",
        "source_version": "fixture-2020",
    }

    loaded = read_population_grid(out)
    assert loaded.resolution == result.resolution
    assert loaded.source == result.source
    assert loaded.source_version == result.source_version
    assert loaded.pixels_counted == result.pixels_counted
    assert loaded.pixels_nodata == result.pixels_nodata
    assert loaded.coverage_stride == result.coverage_stride
    pd.testing.assert_frame_equal(loaded.cells, result.cells)


def test_population_grid_builder_refuses_overwrite(tmp_path):
    out = tmp_path / "worldpop-res4.parquet"
    out.write_bytes(b"existing")
    with pytest.raises(FileExistsError, match="already exists"):
        build_population_grid(
            _raster(tmp_path, np.array([[10.0]])),
            out,
            resolution=4,
            source_version="fixture-2020",
        )


def test_population_grid_reader_refuses_parquet_checksum_mismatch(tmp_path):
    out = tmp_path / "worldpop-res4.parquet"
    build_population_grid(
        _raster(tmp_path, np.array([[10.0]])),
        out,
        resolution=4,
        source_version="fixture-2020",
    )
    out.write_bytes(out.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        read_population_grid(out)


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

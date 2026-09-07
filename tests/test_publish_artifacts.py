"""Publication-target integration for saved surface fits (design §7, §9)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from genomeos.geo.population import WORLDPOP_SOURCE, PopulationGrid
from scripts.publish_artifacts import publication_coordinates


def _grid() -> PopulationGrid:
    return PopulationGrid(
        cells=pd.DataFrame(
            {
                "h3_index": [
                    "835494fffffffff",
                    "833f30fffffffff",
                    "835969fffffffff",
                ],
                "population": [1.0, 2.0, 0.0],
            }
        ),
        resolution=3,
        source=WORLDPOP_SOURCE,
        source_version="fixture-2020",
        pixels_counted=2,
        pixels_nodata=0,
        coverage_stride=16,
    )


def test_publication_coordinates_include_every_observation_cell():
    observations = pd.DataFrame({"lat": [14.933], "lon": [-23.513]})
    cells, lat, lon, observation_cells = publication_coordinates(_grid(), observations)
    assert observation_cells == {"835494fffffffff"}
    assert observation_cells <= set(cells)
    assert len(cells) == len(lat) == len(lon) == 2
    assert np.isfinite(lat).all() and np.isfinite(lon).all()


def test_publication_coordinates_refuse_zero_population_observation():
    observations = pd.DataFrame({"lat": [23.0], "lon": [13.0]})
    with pytest.raises(ValueError, match="zero population"):
        publication_coordinates(_grid(), observations)


def test_publication_coordinates_refuse_missing_coordinates():
    observations = pd.DataFrame({"lat": [14.933]})
    with pytest.raises(ValueError, match="lat.*lon"):
        publication_coordinates(_grid(), observations)

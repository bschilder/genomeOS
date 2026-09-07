"""Publication-target integration for saved surface fits (design §7, §9)."""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from genomeos.geo.population import WORLDPOP_SOURCE, PopulationGrid
from scripts.publish_artifacts import publication_coordinates


def test_publish_artifacts_direct_cli_loads() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/publish_artifacts.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--population-cells" in completed.stdout


def _grid() -> PopulationGrid:
    return PopulationGrid(
        cells=pd.DataFrame(
            {
                "h3_index": [
                    "845494bffffffff",
                    "843f305ffffffff",
                    "8459653ffffffff",
                ],
                "population": [1.0, 2.0, 0.0],
            }
        ),
        resolution=4,
        source=WORLDPOP_SOURCE,
        source_version="fixture-2020",
        pixels_counted=2,
        pixels_nodata=0,
        coverage_stride=16,
    )


def test_publication_coordinates_use_positive_population_cells():
    observations = pd.DataFrame({"lat": [14.933], "lon": [-23.513]})
    cells, lat, lon = publication_coordinates(_grid(), observations)
    assert cells == ["843f305ffffffff", "845494bffffffff"]
    assert len(cells) == len(lat) == len(lon) == 2
    assert np.isfinite(lat).all() and np.isfinite(lon).all()


def test_administrative_centroid_does_not_create_a_surface_cell():
    observations = pd.DataFrame({"lat": [-19.2114], "lon": [-158.9782]})
    cells, _, _ = publication_coordinates(_grid(), observations)
    assert "84b4c3bffffffff" not in cells


def test_publication_coordinates_refuse_missing_coordinates():
    observations = pd.DataFrame({"lat": [14.933]})
    with pytest.raises(ValueError, match="lat.*lon"):
        publication_coordinates(_grid(), observations)

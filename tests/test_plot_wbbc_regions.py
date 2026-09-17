"""Geographic review artifact for WBBC region supports (Atlas design §§4, 6)."""

from __future__ import annotations

import numpy as np
import pytest

from scripts.plot_wbbc_regions import minimum_covering_disc, round_covering_radius


def test_minimum_covering_disc_covers_simple_equatorial_extent():
    points = np.asarray([[0.0, 0.0], [2.0, 0.0], [1.0, 0.0]])

    lon, lat, radius = minimum_covering_disc(points)

    assert lon == pytest.approx(1.0, abs=1e-5)
    assert lat == pytest.approx(0.0, abs=1e-5)
    assert radius == pytest.approx(111.195, abs=0.02)


def test_minimum_covering_disc_finds_spherical_midpoint_for_oblique_extent():
    # The two active boundary vertices for WBBC North. Their arithmetic lon/lat midpoint is not
    # the great-circle midpoint, so this catches a coarse axis-aligned search that overstates the
    # reviewed support by about 48 km.
    points = np.asarray([[89.975108, 33.630557], [134.718733, 48.263412]])

    lon, lat, radius = minimum_covering_disc(points)

    assert lon == pytest.approx(109.721579, abs=1e-5)
    assert lat == pytest.approx(43.146298, abs=1e-5)
    assert radius == pytest.approx(2012.5895, abs=0.02)


def test_radius_is_rounded_up_without_understating_support():
    assert round_covering_radius(343.1338702) == 350.0
    assert round_covering_radius(650.0) == 650.0

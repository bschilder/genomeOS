"""Vectorized observation-footprint tests (design §7; #37 design §§3–5)."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.surfaces.config import EARTH_RADIUS_KM
from genomeos.surfaces.footprint import (
    ObservationSupport,
    uniform_area_disc_support,
    weighted_mean_probability,
    weighted_point_support,
)


def _unit_sphere(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    return np.stack(
        (
            np.cos(lat_rad) * np.cos(lon_rad),
            np.cos(lat_rad) * np.sin(lon_rad),
            np.sin(lat_rad),
        ),
        axis=-1,
    )


def test_uniform_area_disc_support_is_normalized_on_the_sphere_and_deterministic():
    ids = ("equator", "antimeridian", "polar")
    lat = np.array([0.0, 12.0, 89.5])
    lon = np.array([0.0, 179.9, -45.0])
    radius = np.array([10.0, 300.0, 50.0])

    first = uniform_area_disc_support(
        ids, lat, lon, radius, radial_order=8, angular_order=16, support_version="synthetic-v1"
    )
    second = uniform_area_disc_support(
        ids, lat, lon, radius, radial_order=8, angular_order=16, support_version="synthetic-v1"
    )

    assert first.observation_ids == ids
    assert first.unit_sphere.shape == (3, 128, 3)
    assert first.weights.shape == (3, 128)
    np.testing.assert_array_equal(first.unit_sphere, second.unit_sphere)
    np.testing.assert_array_equal(first.weights, second.weights)
    np.testing.assert_allclose(np.linalg.norm(first.unit_sphere, axis=2), 1.0, atol=2e-15)
    np.testing.assert_allclose(first.weights.sum(axis=1), 1.0, atol=2e-16)
    assert np.all(first.weights > 0.0)
    assert first.metadata.weighting == "uniform_area"
    assert first.metadata.location_model == "independent_location_per_trial"
    assert first.metadata.points_per_observation == 128
    with pytest.raises(ValueError):
        first.weights[0, 0] = 0.0


def test_uniform_area_disc_support_is_permutation_equivariant():
    ids = np.array(["a", "b", "c"])
    lat = np.array([-20.0, 5.0, 70.0])
    lon = np.array([170.0, -179.0, 40.0])
    radius = np.array([3.0, 100.0, 700.0])
    order = np.array([2, 0, 1])
    direct = uniform_area_disc_support(
        tuple(ids), lat, lon, radius, radial_order=4, angular_order=8, support_version="v1"
    )
    permuted = uniform_area_disc_support(
        tuple(ids[order]),
        lat[order],
        lon[order],
        radius[order],
        radial_order=4,
        angular_order=8,
        support_version="v1",
    )

    inverse = np.argsort(order)
    np.testing.assert_array_equal(permuted.unit_sphere[inverse], direct.unit_sphere)
    np.testing.assert_array_equal(permuted.weights[inverse], direct.weights)


def test_uniform_area_quadrature_matches_the_spherical_cap_first_moment():
    lat = np.array([-35.0, 0.0, 82.0])
    lon = np.array([20.0, 179.8, -130.0])
    radius = np.array([1.0, 300.0, 2_000.0])
    support = uniform_area_disc_support(
        ("small", "middle", "large"),
        lat,
        lon,
        radius,
        radial_order=8,
        angular_order=16,
        support_version="moment-v1",
    )
    centres = _unit_sphere(lat, lon)
    mean_cosine = np.sum(
        np.einsum("nqk,nk->nq", support.unit_sphere, centres) * support.weights,
        axis=1,
    )
    expected = (1.0 + np.cos(radius / EARTH_RADIUS_KM)) / 2.0

    np.testing.assert_allclose(mean_cosine, expected, rtol=0.0, atol=3e-15)


def test_probability_average_reproduces_the_frozen_nonlinear_disc_case():
    centre_probability = 0.1
    scale_km = 200.0
    support = uniform_area_disc_support(
        ("case",),
        np.array([0.0]),
        np.array([0.0]),
        np.array([300.0]),
        radial_order=64,
        angular_order=256,
        support_version="frozen-diagnostic-v1",
    )
    points = support.unit_sphere[0]
    centre = np.array([1.0, 0.0, 0.0])
    east = np.array([0.0, 1.0, 0.0])
    cosine = np.clip(points @ centre, -1.0, 1.0)
    angular_distance = np.arccos(cosine)
    sine = np.sin(angular_distance)
    east_fraction = np.divide(
        points @ east,
        sine,
        out=np.zeros_like(sine),
        where=sine != 0.0,
    )
    east_km = EARTH_RADIUS_KM * angular_distance * east_fraction
    centre_logit = np.log(centre_probability / (1.0 - centre_probability))
    probabilities = 1.0 / (1.0 + np.exp(-(centre_logit + east_km / scale_km)))
    result = weighted_mean_probability(
        probabilities[None, :], support.weights, array_module=np
    )

    np.testing.assert_allclose(result, np.array([0.119976520323]), rtol=0.0, atol=5e-13)


def test_weighted_point_support_preserves_externally_supplied_population_weights():
    lat = np.array([[0.0, 0.2, -0.2], [40.0, 41.0, 42.0]])
    lon = np.array([[179.9, -179.9, 179.7], [10.0, 11.0, 12.0]])
    weights = np.array([[0.1, 0.7, 0.2], [0.25, 0.25, 0.5]])
    support = weighted_point_support(
        ("a", "b"),
        lat,
        lon,
        weights,
        weighting="population_weighted",
        location_model="independent_location_per_trial",
        support_version="worldpop-example-v1",
    )

    np.testing.assert_array_equal(support.unit_sphere, _unit_sphere(lat, lon))
    np.testing.assert_array_equal(support.weights, weights)
    assert support.metadata.weighting == "population_weighted"
    np.testing.assert_array_equal(
        weighted_mean_probability(
            np.array([[0.1, 0.2, 0.9], [0.0, 0.5, 1.0]]),
            support.weights,
            array_module=np,
        ),
        np.array([0.33, 0.625]),
    )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"observation_ids": ("",)}, "observation_ids"),
        ({"observation_ids": ("a", "a")}, "unique"),
        ({"support_version": ""}, "support_version"),
        ({"unit_sphere": np.ones((1, 2))}, "shape"),
        ({"unit_sphere": np.array([[[np.nan, 0.0, 1.0]]])}, "finite"),
        ({"unit_sphere": np.array([[[2.0, 0.0, 0.0]]])}, "unit sphere"),
        ({"weights": np.array([[0.9]])}, "sum to one"),
        ({"weights": np.array([[-0.1]])}, "nonnegative"),
        ({"location_model": "shared_location"}, "location_model"),
    ],
)
def test_observation_support_refuses_malformed_contracts(kwargs, match):
    values = {
        "observation_ids": ("a",),
        "unit_sphere": np.array([[[1.0, 0.0, 0.0]]]),
        "weights": np.array([[1.0]]),
        "weighting": "uniform_area",
        "location_model": "independent_location_per_trial",
        "support_version": "v1",
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError), match=match):
        ObservationSupport(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("lat", "lon", "radius", "match"),
    [
        ([0.0], [0.0, 1.0], [10.0], "same shape"),
        ([np.nan], [0.0], [10.0], "finite"),
        ([91.0], [0.0], [10.0], "latitude"),
        ([0.0], [181.0], [10.0], "longitude"),
        ([0.0], [0.0], [0.0], "strictly positive"),
        ([0.0], [0.0], [np.pi * EARTH_RADIUS_KM], "hemisphere"),
    ],
)
def test_uniform_area_disc_support_refuses_invalid_geometry(lat, lon, radius, match):
    with pytest.raises(ValueError, match=match):
        uniform_area_disc_support(
            ("a",), lat, lon, radius, radial_order=4, angular_order=8, support_version="v1"
        )


@pytest.mark.parametrize("order", [True, 0, -1, 2.5])
def test_uniform_area_disc_support_refuses_invalid_quadrature_orders(order):
    with pytest.raises((TypeError, ValueError), match="order"):
        uniform_area_disc_support(
            ("a",),
            [0.0],
            [0.0],
            [10.0],
            radial_order=order,  # type: ignore[arg-type]
            angular_order=8,
            support_version="v1",
        )

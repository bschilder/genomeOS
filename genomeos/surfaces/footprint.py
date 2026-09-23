"""Explicit vectorized observation support (design §7; #37 design §§3–5).

This module describes where an observation's count trials are assumed to arise. It
does not read rasters, infer radii, choose source semantics, or fit a model. Uniform
area and externally weighted supports share one immutable contract so the fitter can
change the weights without changing its likelihood implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Any, Literal

import numpy as np

from genomeos.surfaces.config import EARTH_RADIUS_KM

Weighting = Literal["uniform_area", "population_weighted"]
LocationModel = Literal["independent_location_per_trial"]

_WEIGHTINGS = frozenset({"uniform_area", "population_weighted"})
_LOCATION_MODELS = frozenset({"independent_location_per_trial"})
_UNIT_NORM_ATOL = 5e-13
_WEIGHT_SUM_ATOL = 5e-13


def _identifiers(values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("observation_ids must be a sequence of nonempty strings")
    try:
        result = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError("observation_ids must be a sequence of nonempty strings") from error
    if not result or any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError("observation_ids must contain nonempty strings")
    if len(set(result)) != len(result):
        raise ValueError("observation_ids must be unique")
    return result


def _float_array(value: object, name: str) -> np.ndarray:
    raw = np.asarray(value, dtype=object)
    if any(isinstance(item, (bool, np.bool_)) for item in raw.flat):
        raise ValueError(f"{name} must be numeric, excluding Boolean values")
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be numeric") from error
    return result


def _coordinates(lat: object, lon: object, *, ndim: int) -> tuple[np.ndarray, np.ndarray]:
    lat_arr = _float_array(lat, "lat")
    lon_arr = _float_array(lon, "lon")
    if lat_arr.ndim != ndim or lon_arr.ndim != ndim or lat_arr.shape != lon_arr.shape:
        raise ValueError(f"lat and lon must have the same shape and be {ndim}-dimensional")
    if lat_arr.size == 0:
        raise ValueError("lat and lon must be nonempty")
    if not np.isfinite(lat_arr).all() or not np.isfinite(lon_arr).all():
        raise ValueError("lat and lon must be finite")
    if np.any((lat_arr < -90.0) | (lat_arr > 90.0)):
        raise ValueError("latitude must be within [-90, 90]")
    if np.any((lon_arr < -180.0) | (lon_arr > 180.0)):
        raise ValueError("longitude must be within [-180, 180]")
    return lat_arr, lon_arr


def _unit_sphere(lat_rad: np.ndarray, lon_rad: np.ndarray) -> np.ndarray:
    cos_lat = np.cos(lat_rad)
    return np.stack(
        (
            cos_lat * np.cos(lon_rad),
            cos_lat * np.sin(lon_rad),
            np.sin(lat_rad),
        ),
        axis=-1,
    )


def _quadrature_order(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{name} order must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} order must be at least {minimum}")
    return result


@dataclass(frozen=True)
class ObservationSupportMetadata:
    """Small immutable identity retained with a fitted surface."""

    convention: Literal["footprint_probability_mean_v1"]
    weighting: Weighting
    location_model: LocationModel
    support_version: str
    points_per_observation: int


@dataclass(frozen=True)
class ObservationSupport:
    """Fixed-width spatial support aligned one-for-one with observation rows."""

    observation_ids: tuple[str, ...]
    unit_sphere: np.ndarray
    weights: np.ndarray
    weighting: Weighting
    location_model: LocationModel
    support_version: str

    def __post_init__(self) -> None:
        ids = _identifiers(self.observation_ids)
        points = _float_array(self.unit_sphere, "unit_sphere")
        weights = _float_array(self.weights, "weights")
        if points.ndim != 3 or points.shape[2] != 3 or points.shape[0] != len(ids):
            raise ValueError("unit_sphere must have shape (observations, support_points, 3)")
        if points.shape[1] == 0:
            raise ValueError("unit_sphere must contain at least one support point")
        if weights.shape != points.shape[:2]:
            raise ValueError("weights must match the observation and support-point shape")
        if not np.isfinite(points).all() or not np.isfinite(weights).all():
            raise ValueError("unit_sphere and weights must be finite")
        norms = np.linalg.norm(points, axis=2)
        if not np.allclose(norms, 1.0, rtol=0.0, atol=_UNIT_NORM_ATOL):
            raise ValueError("unit_sphere points must lie on the unit sphere")
        if np.any(weights < 0.0):
            raise ValueError("weights must be nonnegative")
        if not np.allclose(
            weights.sum(axis=1), 1.0, rtol=0.0, atol=_WEIGHT_SUM_ATOL
        ):
            raise ValueError("weights must sum to one for every observation")
        if self.weighting not in _WEIGHTINGS:
            raise ValueError(f"weighting must be one of {sorted(_WEIGHTINGS)}")
        if self.location_model not in _LOCATION_MODELS:
            raise ValueError(f"location_model must be one of {sorted(_LOCATION_MODELS)}")
        if not isinstance(self.support_version, str) or not self.support_version.strip():
            raise ValueError("support_version must be a nonempty string")

        points = np.ascontiguousarray(points)
        weights = np.ascontiguousarray(weights)
        points.setflags(write=False)
        weights.setflags(write=False)
        object.__setattr__(self, "observation_ids", ids)
        object.__setattr__(self, "unit_sphere", points)
        object.__setattr__(self, "weights", weights)

    @property
    def metadata(self) -> ObservationSupportMetadata:
        """Return the scientific identity stored with the fitted model."""
        return ObservationSupportMetadata(
            convention="footprint_probability_mean_v1",
            weighting=self.weighting,
            location_model=self.location_model,
            support_version=self.support_version,
            points_per_observation=self.unit_sphere.shape[1],
        )


def weighted_point_support(
    observation_ids: object,
    lat: object,
    lon: object,
    weights: object,
    *,
    weighting: Weighting,
    location_model: LocationModel,
    support_version: str,
) -> ObservationSupport:
    """Build support from caller-qualified points and already-normalized weights."""
    ids = _identifiers(observation_ids)
    lat_arr, lon_arr = _coordinates(lat, lon, ndim=2)
    if lat_arr.shape[0] != len(ids):
        raise ValueError("coordinate rows must match observation_ids")
    return ObservationSupport(
        observation_ids=ids,
        unit_sphere=_unit_sphere(np.radians(lat_arr), np.radians(lon_arr)),
        weights=_float_array(weights, "weights"),
        weighting=weighting,
        location_model=location_model,
        support_version=support_version,
    )


def uniform_area_disc_support(
    observation_ids: object,
    lat: object,
    lon: object,
    radius_km: object,
    *,
    radial_order: int,
    angular_order: int,
    support_version: str,
) -> ObservationSupport:
    """Build a vectorized spherical-area quadrature for reviewed disc radii."""
    ids = _identifiers(observation_ids)
    lat_arr, lon_arr = _coordinates(lat, lon, ndim=1)
    radius = _float_array(radius_km, "radius_km")
    if lat_arr.shape != radius.shape or len(ids) != len(lat_arr):
        raise ValueError("observation_ids, lat, lon and radius_km must have the same shape")
    if not np.isfinite(radius).all():
        raise ValueError("radius_km must be finite")
    if np.any(radius <= 0.0):
        raise ValueError("radius_km must be strictly positive")
    if np.any(radius >= 0.5 * np.pi * EARTH_RADIUS_KM):
        raise ValueError("radius_km must be smaller than a hemisphere")
    radial = _quadrature_order(radial_order, "radial", minimum=1)
    angular = _quadrature_order(angular_order, "angular", minimum=4)

    legendre_nodes, legendre_weights = np.polynomial.legendre.leggauss(radial)
    area_fraction = (legendre_nodes + 1.0) / 2.0
    radial_weights = legendre_weights / 2.0
    distance = 2.0 * EARTH_RADIUS_KM * np.arcsin(
        np.sqrt(area_fraction)[None, :]
        * np.sin(radius[:, None] / (2.0 * EARTH_RADIUS_KM))
    )
    central_angle = distance[:, :, None] / EARTH_RADIUS_KM
    bearing = (2.0 * np.pi / angular) * np.arange(angular, dtype=np.float64)[None, None, :]

    centre_lat = np.radians(lat_arr)[:, None, None]
    centre_lon = np.radians(lon_arr)[:, None, None]
    sin_lat = np.sin(centre_lat)
    cos_lat = np.cos(centre_lat)
    sin_distance = np.sin(central_angle)
    cos_distance = np.cos(central_angle)
    point_lat = np.arcsin(
        np.clip(
            sin_lat * cos_distance + cos_lat * sin_distance * np.cos(bearing),
            -1.0,
            1.0,
        )
    )
    point_lon = centre_lon + np.arctan2(
        np.sin(bearing) * sin_distance * cos_lat,
        cos_distance - sin_lat * np.sin(point_lat),
    )

    points = _unit_sphere(point_lat, point_lon).reshape(len(ids), radial * angular, 3)
    weights = np.broadcast_to(
        radial_weights[None, :, None] / angular,
        (len(ids), radial, angular),
    ).reshape(len(ids), radial * angular)
    return ObservationSupport(
        observation_ids=ids,
        unit_sphere=points,
        weights=weights,
        weighting="uniform_area",
        location_model="independent_location_per_trial",
        support_version=support_version,
    )


def weighted_mean_probability(
    probabilities: Any,
    weights: Any,
    *,
    array_module: Any,
) -> Any:
    """Average frequency-scale probabilities over one fixed-width support axis."""
    if probabilities.ndim != 2 or weights.ndim != 2:
        raise ValueError("probabilities and weights must be two-dimensional")
    if array_module is np:
        probability = _float_array(probabilities, "probabilities")
        weight = _float_array(weights, "weights")
        if probability.shape != weight.shape:
            raise ValueError("probabilities and weights must have the same shape")
        if not np.isfinite(probability).all() or np.any((probability < 0.0) | (probability > 1.0)):
            raise ValueError("probabilities must be finite and within [0, 1]")
        return np.sum(probability * weight, axis=1)
    return array_module.sum(probabilities * weights, axis=1)


def resolve_observation_support(
    observation_ids: tuple[str, ...],
    observation_centres: np.ndarray,
    support: ObservationSupport | None,
) -> tuple[np.ndarray, np.ndarray | None, ObservationSupportMetadata | None]:
    """Bind optional support to validated rows and return the flattened model inputs."""
    if support is None:
        return observation_centres, None, None
    if not isinstance(support, ObservationSupport):
        raise TypeError("observation_support must be an ObservationSupport")
    if support.observation_ids != observation_ids:
        raise ValueError(
            "observation_support observation IDs must exactly match the validated row order"
        )
    return support.unit_sphere.reshape(-1, 3), support.weights, support.metadata


def reshape_support_values(values: Any, observation_count: int, support_points: int | None) -> Any:
    """Restore the observation axis after one flattened field evaluation."""
    if support_points is None:
        return values
    return values.reshape((observation_count, support_points))


def add_observation_offset(values: Any, offset: Any, support_points: int | None) -> Any:
    """Broadcast one design/cohort/nugget offset across an observation's support."""
    return values + (offset if support_points is None else offset[:, None])

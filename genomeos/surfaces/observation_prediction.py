"""Draw-aligned GP observation-parameter extraction (design §§4–5, 7.1, 8, 12).

This offline adapter exposes the fitted graph's named latent logits and observation effects to
the pure unseen-cohort composer. It validates posterior identity and capabilities explicitly;
legacy fits without recorded provenance or the named graph node must be refitted.
"""

from __future__ import annotations

from numbers import Integral
from typing import TYPE_CHECKING

import numpy as np
import pymc as pm
import xarray as xr

from genomeos.surfaces.observation import (
    SEED,
    ObservationModelMetadata,
    ObservationParameters,
    SurveyQueries,
    compose_unseen_observations,
)

if TYPE_CHECKING:
    from genomeos.surfaces.fit import SurfaceFit


def _validate_request(
    fit: SurfaceFit, queries: SurveyQueries, seed: int
) -> ObservationModelMetadata:
    if not isinstance(queries, SurveyQueries):
        raise ValueError("queries must be SurveyQueries")
    metadata = getattr(fit, "prediction_metadata", None)
    if not isinstance(metadata, ObservationModelMetadata):
        raise ValueError(
            "prediction metadata is unavailable; refit before using unseen-cohort prediction"
        )
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("seed must be a nonnegative integer, not a boolean")

    unknown_designs = sorted(set(queries.sampling_designs) - set(metadata.fitted_designs))
    if unknown_designs:
        raise ValueError(f"query sampling design was not fitted: {unknown_designs}")
    seen_cohorts = sorted(set(queries.cohort_ids) & set(metadata.training_cohort_ids))
    if seen_cohorts:
        raise ValueError(f"seen cohort IDs are not valid unseen-cohort queries: {seen_cohorts}")
    if "latent_logit_pred" not in fit._model.named_vars:
        raise ValueError(
            "fitted graph has no latent_logit_pred node; refit before using unseen-cohort prediction"
        )
    return metadata


def _coordinate_labels(
    variable: xr.DataArray | xr.Dataset | xr.DataTree,
    name: str,
    dimension: str,
) -> tuple[int, ...]:
    if dimension not in variable.dims or dimension not in variable.coords:
        raise ValueError(f"{name} must carry explicit {dimension} coordinate labels")
    coordinate = variable.coords[dimension]
    if coordinate.dims != (dimension,):
        raise ValueError(f"{name} {dimension} coordinate labels must be one-dimensional")
    raw = coordinate.to_numpy().tolist()
    if not raw:
        raise ValueError(f"{name} {dimension} coordinate labels must be nonempty")
    if any(
        isinstance(label, (bool, np.bool_)) or not isinstance(label, Integral) for label in raw
    ):
        raise ValueError(f"{name} {dimension} coordinate labels must be integers")
    labels = tuple(int(label) for label in raw)
    if len(set(labels)) != len(labels):
        raise ValueError(f"{name} {dimension} coordinate labels must be unique")
    return labels


def _extract_named_array(
    variable: object,
    name: str,
    *,
    event_size: int | None,
    expected_coordinates: tuple[tuple[int, ...], tuple[int, ...]] | None,
) -> tuple[np.ndarray, tuple[tuple[int, ...], tuple[int, ...]]]:
    if not isinstance(variable, xr.DataArray):
        raise ValueError(f"{name} must be an xarray DataArray with named dimensions")
    if len(set(variable.dims)) != len(variable.dims):
        raise ValueError(f"{name} dimensions must be unique")
    if "chain" not in variable.dims or "draw" not in variable.dims:
        raise ValueError(f"{name} must have named chain and draw dimensions")

    event_dimensions = tuple(dim for dim in variable.dims if dim not in {"chain", "draw"})
    expected_event_axes = 0 if event_size is None else 1
    if len(event_dimensions) != expected_event_axes:
        raise ValueError(
            f"{name} must have exactly {expected_event_axes} positional event axis"
            + ("" if expected_event_axes == 1 else "es")
        )

    chains = _coordinate_labels(variable, name, "chain")
    draws = _coordinate_labels(variable, name, "draw")
    sorted_chains = tuple(sorted(chains))
    sorted_draws = tuple(sorted(draws))
    coordinates = (sorted_chains, sorted_draws)
    if expected_coordinates is not None and coordinates != expected_coordinates:
        raise ValueError(f"{name} chain/draw coordinate labels do not match the fitted posterior")

    ordered = variable.sel(chain=list(sorted_chains), draw=list(sorted_draws))
    event_shape: tuple[int, ...] = ()
    if event_size is not None:
        event_dimension = event_dimensions[0]
        positions = _coordinate_labels(variable, name, event_dimension)
        expected_positions = tuple(range(event_size))
        if set(positions) != set(expected_positions) or len(positions) != event_size:
            raise ValueError(
                f"{name} positional event axis must contain labels {expected_positions}"
            )
        ordered = ordered.sel({event_dimension: list(expected_positions)})
        event_shape = (event_size,)

    ordered = ordered.transpose("chain", "draw", *event_dimensions)
    values = ordered.to_numpy().reshape(len(sorted_chains) * len(sorted_draws), *event_shape)
    if not (
        np.issubdtype(values.dtype, np.integer)
        or np.issubdtype(values.dtype, np.floating)
    ):
        raise ValueError(f"{name} values must have a real numeric dtype")
    return values.astype(np.float64, copy=False), coordinates


def _posterior_group(fit: SurfaceFit) -> xr.Dataset | xr.DataTree:
    posterior = getattr(fit.idata, "posterior", None)
    if not isinstance(posterior, (xr.Dataset, xr.DataTree)):
        raise ValueError("fitted posterior must be an xarray Dataset or DataTree")
    return posterior


def _posterior_variable(posterior: xr.Dataset | xr.DataTree, name: str) -> object:
    if posterior is None or name not in posterior:
        raise ValueError(f"fitted posterior is missing required variable {name!r}")
    return posterior[name]


def _extract_effects(
    posterior: xr.Dataset | xr.DataTree,
    metadata: ObservationModelMetadata,
    posterior_coordinates: tuple[tuple[int, ...], tuple[int, ...]],
) -> tuple[
    np.ndarray,
    np.ndarray | None,
    np.ndarray | None,
    np.ndarray | None,
]:
    draws = len(posterior_coordinates[0]) * len(posterior_coordinates[1])
    contrasts = len(metadata.fitted_designs) - 1
    if contrasts:
        design, _ = _extract_named_array(
            _posterior_variable(posterior, "beta_design"),
            "beta_design",
            event_size=contrasts,
            expected_coordinates=posterior_coordinates,
        )
    else:
        if "beta_design" in posterior:
            raise ValueError("posterior beta_design conflicts with single-design prediction metadata")
        design = np.empty((draws, 0), dtype=np.float64)

    def scalar(name: str, applied: bool) -> np.ndarray | None:
        if not applied:
            if name in posterior:
                raise ValueError(f"posterior {name} conflicts with omitted prediction metadata")
            return None
        values, _ = _extract_named_array(
            _posterior_variable(posterior, name),
            name,
            event_size=None,
            expected_coordinates=posterior_coordinates,
        )
        return values

    cohort_sd = scalar("cohort_sd", metadata.cohort_effect_applied)
    nugget_sd = scalar("nugget_sd", metadata.nugget_applied)
    concentration = scalar("concentration", metadata.likelihood == "beta_binomial")

    if metadata.likelihood == "binomial" and "concentration" in posterior:
        raise ValueError("posterior concentration conflicts with binomial prediction metadata")
    return design, cohort_sd, nugget_sd, concentration


def _canonical_coordinates(queries: SurveyQueries) -> tuple[np.ndarray, np.ndarray]:
    canonical: list[tuple[float, float]] = []
    for lat, lon in zip(queries.lat, queries.lon, strict=True):
        normalized_lon = 180.0 if lon == -180.0 else lon
        if lat == -90.0 or lat == 90.0:
            normalized_lon = 0.0
        canonical.append((lat, normalized_lon))
    unique = tuple(sorted(set(canonical)))
    index = {coordinate: position for position, coordinate in enumerate(unique)}
    submitted_index = np.array([index[coordinate] for coordinate in canonical], dtype=np.intp)

    lat = np.radians(np.array([coordinate[0] for coordinate in unique], dtype=np.float64))
    lon = np.radians(np.array([coordinate[1] for coordinate in unique], dtype=np.float64))
    points = np.column_stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    )
    return points, submitted_index


def predict_new_cohort_parameters(
    fit: SurfaceFit,
    queries: SurveyQueries,
    *,
    seed: int = SEED,
) -> ObservationParameters:
    """Extract fitted draw-aligned parameters for explicit genuinely unseen survey cohorts."""
    metadata = _validate_request(fit, queries, seed)
    posterior = _posterior_group(fit)
    posterior_coordinates = (
        tuple(sorted(_coordinate_labels(posterior, "fitted posterior", "chain"))),
        tuple(sorted(_coordinate_labels(posterior, "fitted posterior", "draw"))),
    )
    design, cohort_sd, nugget_sd, concentration = _extract_effects(
        posterior, metadata, posterior_coordinates
    )
    points, submitted_index = _canonical_coordinates(queries)

    with fit._model:
        pm.set_data({"x_pred": points})
        drawn = pm.sample_posterior_predictive(
            fit.idata,
            var_names=["latent_logit_pred"],
            random_seed=int(seed),
            progressbar=False,
        )
    posterior_predictive = getattr(drawn, "posterior_predictive", None)
    if posterior_predictive is None or "latent_logit_pred" not in posterior_predictive:
        raise ValueError("posterior predictive output is missing latent_logit_pred")
    latent_unique, _ = _extract_named_array(
        posterior_predictive["latent_logit_pred"],
        "latent_logit_pred",
        event_size=len(points),
        expected_coordinates=posterior_coordinates,
    )
    draw_ids = tuple(
        (chain, draw)
        for chain in posterior_coordinates[0]
        for draw in posterior_coordinates[1]
    )
    return compose_unseen_observations(
        latent_unique[:, submitted_index],
        draw_ids=draw_ids,
        queries=queries,
        metadata=metadata,
        design_effect_draws=design,
        cohort_sd_draws=cohort_sd,
        nugget_sd_draws=nugget_sd,
        concentration_draws=concentration,
        seed=int(seed),
    )

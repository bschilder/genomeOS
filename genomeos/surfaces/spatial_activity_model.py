"""Research-only spatial activity model graph (design §§7–8; issues #384 and #391).

The ordinary and candidate arms share one conditional-frequency HSGP, one beta-binomial
concentration prior, and the same optional replicated-cohort term. The candidate adds a second
HSGP for the probability that the active count component applies. Its binary state is never
sampled: ``activity_beta_binomial_logp`` integrates it from the observed count law.

Each sampled spatial intercept is the exact mean of its field at the training locations. The
HSGP deviations are centered over those locations while the intercept prior is shifted by the
same amount, preserving the original prior and prediction fields under a one-to-one transform.

This module only builds a pure offline PyMC graph from explicit arrays and configuration. It does
not sample, score, serialize, inspect real HbS outcomes, or imply that either latent component has
a biological interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from numbers import Integral, Real
from typing import Literal

import numpy as np
import pymc as pm
import pytensor.tensor as pt
from pymc.gp.hsgp_approx import calc_eigenvalues, calc_eigenvectors, set_boundary

from genomeos.surfaces.activity_likelihood import activity_beta_binomial_logp

ActivityModelMode = Literal["ordinary", "spatial_activity"]
ACTIVITY_MODEL_MODES: tuple[ActivityModelMode, ...] = (
    "ordinary",
    "spatial_activity",
)


def _finite(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _positive(value: object, name: str) -> float:
    normalized = _finite(value, name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _basis(value: object) -> tuple[int, int, int]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError("hsgp_m must be a three-element tuple")
    normalized: list[int] = []
    for item in value:
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, Integral):
            raise ValueError("hsgp_m must contain positive integers")
        integer = int(item)
        if integer <= 0:
            raise ValueError("hsgp_m must contain positive integers")
        normalized.append(integer)
    return tuple(normalized)  # type: ignore[return-value]


@dataclass(frozen=True)
class SpatialActivityModelConfig:
    """Explicit graph priors for the simulation-only ordinary/candidate comparison."""

    hsgp_m: tuple[int, int, int]
    hsgp_c: float
    lengthscale_mu: float
    lengthscale_sigma: float
    conditional_intercept_mu: float
    conditional_intercept_sigma: float
    conditional_amplitude_sigma: float
    activity_intercept_mu: float
    activity_intercept_sigma: float
    activity_amplitude_sigma: float
    concentration_sigma: float
    cohort_sd_sigma: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "hsgp_m", _basis(self.hsgp_m))
        object.__setattr__(self, "hsgp_c", _positive(self.hsgp_c, "hsgp_c"))
        if self.hsgp_c <= 1.0:
            raise ValueError("hsgp_c must exceed one")
        for name in ("lengthscale_mu", "conditional_intercept_mu", "activity_intercept_mu"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        for name in (
            "lengthscale_sigma",
            "conditional_intercept_sigma",
            "conditional_amplitude_sigma",
            "activity_intercept_sigma",
            "activity_amplitude_sigma",
            "concentration_sigma",
            "cohort_sd_sigma",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))


@dataclass(frozen=True)
class SpatialActivityModelGraph:
    """Validated metadata around one unsampled PyMC graph."""

    model: pm.Model = field(repr=False)
    mode: ActivityModelMode
    cohort_effect_applied: bool
    n_observations: int
    n_predictions: int


def _coordinates(value: object, name: str) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a numeric unit-sphere matrix") from error
    if (
        raw.ndim != 2
        or raw.shape[1:] != (3,)
        or not raw.shape[0]
        or not np.issubdtype(raw.dtype, np.number)
        or np.issubdtype(raw.dtype, np.bool_)
        or np.issubdtype(raw.dtype, np.complexfloating)
    ):
        raise ValueError(f"{name} must be a nonempty numeric matrix with shape (rows, 3)")
    coordinates = raw.astype(np.float64)
    if not np.all(np.isfinite(coordinates)):
        raise ValueError(f"{name} must contain finite values")
    if not np.allclose(
        np.linalg.norm(coordinates, axis=1),
        np.ones(len(coordinates)),
        rtol=0.0,
        atol=1e-8,
    ):
        raise ValueError(f"{name} rows must be unit-sphere coordinates")
    return coordinates


def _integer_vector(value: object, name: str) -> np.ndarray:
    try:
        raw = np.asarray(value)
        objects = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain integer values") from error
    if (
        raw.ndim != 1
        or not np.issubdtype(raw.dtype, np.number)
        or np.issubdtype(raw.dtype, np.complexfloating)
        or np.issubdtype(raw.dtype, np.bool_)
        or any(isinstance(item, (bool, np.bool_)) for item in objects)
    ):
        raise ValueError(f"{name} must be a one-dimensional integer vector")
    numeric = raw.astype(np.float64)
    if not np.all(np.isfinite(numeric)) or np.any(numeric != np.floor(numeric)):
        raise ValueError(f"{name} must contain finite integer values")
    return numeric.astype(np.int64)


def _counts(ac: object, an: object, observations: int) -> tuple[np.ndarray, np.ndarray]:
    alternate = _integer_vector(ac, "ac")
    total = _integer_vector(an, "an")
    if alternate.shape != (observations,) or total.shape != (observations,):
        raise ValueError("ac and an must match the number of observed coordinates")
    if np.any(total <= 0):
        raise ValueError("an must contain positive denominators")
    if np.any(alternate < 0) or np.any(alternate > total):
        raise ValueError("ac must be between zero and AN")
    return alternate, total


def _cohorts(value: object | None, observations: int) -> tuple[np.ndarray, bool, int]:
    if value is None:
        return np.arange(observations, dtype=np.int64), False, observations
    cohort_index = _integer_vector(value, "cohort_index")
    if cohort_index.shape != (observations,):
        raise ValueError("cohort_index must match the number of observed coordinates")
    if np.any(cohort_index < 0):
        raise ValueError("cohort_index must contain nonnegative contiguous labels")
    labels = np.unique(cohort_index)
    if not np.array_equal(labels, np.arange(len(labels))):
        raise ValueError("cohort_index labels must be contiguous from zero")
    return cohort_index, len(labels) < observations, len(labels)


def _spatial_field(
    name: str,
    x_observed: pt.TensorVariable,
    x_prediction: pt.TensorVariable,
    *,
    intercept_mu: float,
    intercept_sigma: float,
    amplitude_sigma: float,
    config: SpatialActivityModelConfig,
) -> tuple[pt.TensorVariable, pt.TensorVariable]:
    lengthscale = pm.LogNormal(
        f"{name}_lengthscale",
        mu=config.lengthscale_mu,
        sigma=config.lengthscale_sigma,
    )
    amplitude = pm.HalfNormal(f"{name}_amplitude", sigma=amplitude_sigma)
    covariance = amplitude**2 * pm.gp.cov.Matern52(3, ls=lengthscale)
    x_center = (pt.max(x_observed, axis=0) + pt.min(x_observed, axis=0)).eval() / 2
    centered_observed = x_observed - x_center
    boundaries = set_boundary(centered_observed, config.hsgp_c)
    eigenvalues = calc_eigenvalues(boundaries, config.hsgp_m)
    observed_basis = calc_eigenvectors(
        centered_observed,
        boundaries,
        eigenvalues,
        config.hsgp_m,
    )
    prediction_basis = calc_eigenvectors(
        x_prediction - x_center,
        boundaries,
        eigenvalues,
        config.hsgp_m,
    )
    sqrt_psd = pt.sqrt(covariance.power_spectral_density(pt.sqrt(eigenvalues)))
    coefficients = pm.Normal(
        f"{name}_field_hsgp_coeffs",
        mu=0.0,
        sigma=1.0,
        size=int(np.prod(config.hsgp_m)),
    )
    weighted_coefficients = coefficients * sqrt_psd
    raw_observed = observed_basis @ weighted_coefficients
    raw_predicted = prediction_basis @ weighted_coefficients
    training_mean = pt.mean(raw_observed)
    intercept = pm.Normal(
        f"{name}_intercept",
        mu=intercept_mu + training_mean,
        sigma=intercept_sigma,
    )
    observed = pm.Deterministic(
        f"{name}_field", intercept + raw_observed - training_mean
    )
    predicted = pm.Deterministic(
        f"{name}_field_pred", intercept + raw_predicted - training_mean
    )
    return observed, predicted


def build_spatial_activity_model(
    x_observed: object,
    ac: object,
    an: object,
    x_prediction: object,
    *,
    cohort_index: object | None,
    mode: ActivityModelMode,
    config: SpatialActivityModelConfig,
) -> SpatialActivityModelGraph:
    """Build matched ordinary or spatial-activity HSGP count models.

    Coordinates must already be Cartesian unit-sphere rows. Prediction represents the smooth
    reference-cohort fields; a later predictive adapter integrates any new-cohort offset.
    """
    if not isinstance(config, SpatialActivityModelConfig):
        raise ValueError("config must be SpatialActivityModelConfig")
    if mode not in ACTIVITY_MODEL_MODES:
        raise ValueError(f"mode must be one of {ACTIVITY_MODEL_MODES}")
    observed_coordinates = _coordinates(x_observed, "x_observed")
    prediction_coordinates = _coordinates(x_prediction, "x_prediction")
    alternate, total = _counts(ac, an, len(observed_coordinates))
    cohorts, cohort_effect_applied, cohort_count = _cohorts(
        cohort_index, len(observed_coordinates)
    )

    with pm.Model() as model:
        x_data = pm.Data("x_observed", observed_coordinates)
        x_pred = pm.Data("x_prediction", prediction_coordinates)
        conditional_field, conditional_field_pred = _spatial_field(
            "conditional",
            x_data,
            x_pred,
            intercept_mu=config.conditional_intercept_mu,
            intercept_sigma=config.conditional_intercept_sigma,
            amplitude_sigma=config.conditional_amplitude_sigma,
            config=config,
        )
        conditional_logit = conditional_field
        if cohort_effect_applied:
            cohort_sd = pm.HalfNormal("cohort_sd", sigma=config.cohort_sd_sigma)
            cohort_z = pm.Normal("cohort_z", mu=0.0, sigma=1.0, shape=cohort_count)
            beta_cohort = pm.Deterministic("beta_cohort", cohort_sd * cohort_z)
            conditional_logit = conditional_logit + beta_cohort[cohorts]
        conditional_mean = pm.Deterministic(
            "conditional_mean", pm.math.invlogit(conditional_logit)
        )
        pm.Deterministic(
            "conditional_mean_pred", pm.math.invlogit(conditional_field_pred)
        )

        if mode == "spatial_activity":
            activity_field, activity_field_pred = _spatial_field(
                "activity",
                x_data,
                x_pred,
                intercept_mu=config.activity_intercept_mu,
                intercept_sigma=config.activity_intercept_sigma,
                amplitude_sigma=config.activity_amplitude_sigma,
                config=config,
            )
            activity_probability = pm.Deterministic(
                "activity_probability", pm.math.invlogit(activity_field)
            )
            pm.Deterministic(
                "activity_probability_pred", pm.math.invlogit(activity_field_pred)
            )
        else:
            activity_probability = pm.Deterministic(
                "activity_probability", pt.ones_like(conditional_mean)
            )
            pm.Deterministic(
                "activity_probability_pred", pt.ones_like(conditional_field_pred)
            )

        concentration = pm.HalfNormal(
            "concentration", sigma=config.concentration_sigma
        )
        pm.CustomDist(
            "obs",
            total,
            conditional_mean,
            activity_probability,
            concentration,
            logp=activity_beta_binomial_logp,
            observed=alternate,
            dtype="int64",
        )

    return SpatialActivityModelGraph(
        model=model,
        mode=mode,
        cohort_effect_applied=cohort_effect_applied,
        n_observations=len(observed_coordinates),
        n_predictions=len(prediction_coordinates),
    )

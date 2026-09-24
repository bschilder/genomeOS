"""Fit and predict the simulation-only spatial activity graph (design §§7–8, 12; #384).

The fitter applies the registered convergence gates before it creates held-out predictions. The
prediction boundary preserves posterior draw alignment and samples one new offset per held-out
cohort and draw. Its public result is ``ActivityCountPredictive``: the latent gate remains
analytically marginalized and is never exposed as a classification of observed zeros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from numbers import Integral, Real
from typing import Any

import numpy as np
import pymc as pm
from scipy.special import expit, logit

from genomeos.surfaces.config import NUTS_SAMPLERS
from genomeos.surfaces.convergence import (
    SamplerDiagnostics,
    convergence_failure,
    summarize_sampler_diagnostics,
)
from genomeos.surfaces.spatial_activity_model import (
    ACTIVITY_MODEL_MODES,
    ActivityModelMode,
    SpatialActivityModelGraph,
)
from genomeos.validation.spatial_activity_preflight import ActivityCountPredictive

SEED = 42


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    normalized = int(value)
    if normalized < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    return normalized


def _finite(value: object, name: str, *, minimum: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite and at least {minimum}")
    normalized = float(value)
    if not isfinite(normalized) or normalized < minimum:
        raise ValueError(f"{name} must be finite and at least {minimum}")
    return normalized


@dataclass(frozen=True)
class SpatialActivitySamplerConfig:
    """Frozen sampler budget and convergence gates for one preflight fit."""

    draws: int = 500
    tune: int = 1000
    chains: int = 4
    target_accept: float = 0.9
    nuts_sampler: str = "numpyro"
    max_rhat: float = 1.05
    min_ess: float = 200.0
    seed: int = SEED

    def __post_init__(self) -> None:
        object.__setattr__(self, "draws", _integer(self.draws, "draws", minimum=1))
        object.__setattr__(self, "tune", _integer(self.tune, "tune", minimum=1))
        object.__setattr__(self, "chains", _integer(self.chains, "chains", minimum=4))
        object.__setattr__(self, "seed", _integer(self.seed, "seed", minimum=0))
        target_accept = _finite(self.target_accept, "target_accept", minimum=0.0)
        if not 0.0 < target_accept < 1.0:
            raise ValueError("target_accept must be strictly between zero and one")
        object.__setattr__(self, "target_accept", target_accept)
        if not isinstance(self.nuts_sampler, str) or self.nuts_sampler not in NUTS_SAMPLERS:
            raise ValueError(f"nuts_sampler must be one of {NUTS_SAMPLERS}")
        max_rhat = _finite(self.max_rhat, "max_rhat", minimum=1.0)
        min_ess = _finite(self.min_ess, "min_ess", minimum=0.0)
        object.__setattr__(self, "max_rhat", max_rhat)
        object.__setattr__(self, "min_ess", min_ess)


class SpatialActivityConvergenceError(RuntimeError):
    """The registered sampler gates refused one preflight arm."""

    def __init__(self, reason: str, *, diagnostics: SamplerDiagnostics | None = None) -> None:
        self.diagnostics = diagnostics
        super().__init__(reason)


def _draw_matrix(value: object, name: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite draw matrix") from error
    if array.ndim != 2 or not array.shape[0] or not array.shape[1]:
        raise ValueError(f"{name} must be a nonempty two-dimensional draw matrix")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain finite draws")
    frozen = array.copy()
    frozen.setflags(write=False)
    return frozen


def _draw_vector(value: object, name: str, expected: int) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite draw vector") from error
    if array.shape != (expected,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite vector matching posterior draws")
    frozen = array.copy()
    frozen.setflags(write=False)
    return frozen


@dataclass(frozen=True, eq=False)
class SpatialActivityFit:
    """Aligned reference-cohort predictions and retained convergence evidence."""

    mode: ActivityModelMode
    config: SpatialActivitySamplerConfig
    idata: Any = field(repr=False)
    conditional_mean_draws: np.ndarray = field(repr=False)
    activity_probability_draws: np.ndarray = field(repr=False)
    concentration_draws: np.ndarray = field(repr=False)
    cohort_sd_draws: np.ndarray | None = field(repr=False)
    diagnostics: SamplerDiagnostics

    def __post_init__(self) -> None:
        if self.mode not in ACTIVITY_MODEL_MODES:
            raise ValueError(f"mode must be one of {ACTIVITY_MODEL_MODES}")
        if not isinstance(self.config, SpatialActivitySamplerConfig):
            raise ValueError("config must be SpatialActivitySamplerConfig")
        conditional = _draw_matrix(self.conditional_mean_draws, "conditional_mean_draws")
        activity = _draw_matrix(
            self.activity_probability_draws, "activity_probability_draws"
        )
        if activity.shape != conditional.shape:
            raise ValueError("activity_probability_draws must match conditional_mean_draws")
        if np.any((conditional <= 0.0) | (conditional >= 1.0)):
            raise ValueError("conditional_mean_draws must be strictly between zero and one")
        if np.any((activity < 0.0) | (activity > 1.0)):
            raise ValueError("activity_probability_draws must be between zero and one")
        concentration = _draw_vector(
            self.concentration_draws,
            "concentration_draws",
            conditional.shape[0],
        )
        if np.any(concentration <= 0.0):
            raise ValueError("concentration_draws must be positive")
        cohort_sd = self.cohort_sd_draws
        if cohort_sd is not None:
            cohort_sd = _draw_vector(cohort_sd, "cohort_sd_draws", conditional.shape[0])
            if np.any(cohort_sd < 0.0):
                raise ValueError("cohort_sd_draws must be nonnegative")
        if not isinstance(self.diagnostics, SamplerDiagnostics):
            raise ValueError("diagnostics must be SamplerDiagnostics")
        object.__setattr__(self, "conditional_mean_draws", conditional)
        object.__setattr__(self, "activity_probability_draws", activity)
        object.__setattr__(self, "concentration_draws", concentration)
        object.__setattr__(self, "cohort_sd_draws", cohort_sd)

    @property
    def n_draws(self) -> int:
        return self.conditional_mean_draws.shape[0]

    @property
    def n_predictions(self) -> int:
        return self.conditional_mean_draws.shape[1]


def _dataset(grouped: object, group: str) -> object:
    try:
        return getattr(grouped, group)
    except AttributeError as error:
        raise ValueError(f"sampler output is missing {group}") from error


def _posterior_vector(
    posterior: object,
    name: str,
    *,
    config: SpatialActivitySamplerConfig,
) -> np.ndarray:
    try:
        variable = posterior[name]  # type: ignore[index]
    except (KeyError, TypeError) as error:
        raise ValueError(f"posterior is missing {name!r}") from error
    if variable.dims != ("chain", "draw") or variable.sizes != {
        "chain": config.chains,
        "draw": config.draws,
    }:
        raise ValueError(f"posterior {name!r} must match configured chain/draw axes")
    return np.asarray(variable.to_numpy(), dtype=np.float64).reshape(-1)


def _predictive_matrix(
    posterior_predictive: object,
    name: str,
    *,
    config: SpatialActivitySamplerConfig,
    predictions: int,
) -> np.ndarray:
    try:
        variable = posterior_predictive[name]  # type: ignore[index]
    except (KeyError, TypeError) as error:
        raise ValueError(f"posterior_predictive is missing {name!r}") from error
    if (
        len(variable.dims) != 3
        or variable.dims[:2] != ("chain", "draw")
        or variable.shape != (config.chains, config.draws, predictions)
    ):
        raise ValueError(
            f"posterior_predictive {name!r} must match configured chain/draw/prediction axes"
        )
    return np.asarray(variable.to_numpy(), dtype=np.float64).reshape(-1, predictions)


def fit_spatial_activity_graph(
    graph: SpatialActivityModelGraph,
    *,
    config: SpatialActivitySamplerConfig,
) -> SpatialActivityFit:
    """Sample one matched model arm and refuse it before prediction if gates fail."""
    if not isinstance(graph, SpatialActivityModelGraph):
        raise ValueError("graph must be SpatialActivityModelGraph")
    if not isinstance(config, SpatialActivitySamplerConfig):
        raise ValueError("config must be SpatialActivitySamplerConfig")
    sample_kwargs: dict[str, Any] = {
        "draws": config.draws,
        "tune": config.tune,
        "chains": config.chains,
        "random_seed": config.seed,
        "progressbar": False,
        "target_accept": config.target_accept,
    }
    if config.nuts_sampler == "pymc":
        sample_kwargs["cores"] = 1
    else:
        sample_kwargs["nuts_sampler"] = config.nuts_sampler
        sample_kwargs["nuts"] = {"chain_method": "vectorized"}

    with graph.model:
        idata = pm.sample(**sample_kwargs)
    try:
        diagnostics = summarize_sampler_diagnostics(
            idata,
            chains=config.chains,
            draws=config.draws,
        )
    except (TypeError, ValueError, ArithmeticError) as error:
        raise SpatialActivityConvergenceError(
            f"sampler diagnostics are invalid: {error}"
        ) from error
    failure = convergence_failure(
        diagnostics,
        max_rhat=config.max_rhat,
        min_ess=config.min_ess,
    )
    if failure is not None:
        raise SpatialActivityConvergenceError(failure, diagnostics=diagnostics)

    with graph.model:
        predicted = pm.sample_posterior_predictive(
            idata,
            var_names=["conditional_mean_pred", "activity_probability_pred"],
            random_seed=config.seed,
            progressbar=False,
        )
    posterior = _dataset(idata, "posterior")
    posterior_predictive = _dataset(predicted, "posterior_predictive")
    conditional = _predictive_matrix(
        posterior_predictive,
        "conditional_mean_pred",
        config=config,
        predictions=graph.n_predictions,
    )
    activity = _predictive_matrix(
        posterior_predictive,
        "activity_probability_pred",
        config=config,
        predictions=graph.n_predictions,
    )
    concentration = _posterior_vector(posterior, "concentration", config=config)
    cohort_sd = (
        _posterior_vector(posterior, "cohort_sd", config=config)
        if graph.cohort_effect_applied
        else None
    )
    return SpatialActivityFit(
        mode=graph.mode,
        config=config,
        idata=idata,
        conditional_mean_draws=conditional,
        activity_probability_draws=activity,
        concentration_draws=concentration,
        cohort_sd_draws=cohort_sd,
        diagnostics=diagnostics,
    )


def _prediction_cohorts(value: object, predictions: int) -> tuple[np.ndarray, int]:
    try:
        raw = np.asarray(value)
        objects = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as error:
        raise ValueError("prediction_cohort_index must contain integer labels") from error
    if (
        raw.shape != (predictions,)
        or not np.issubdtype(raw.dtype, np.number)
        or np.issubdtype(raw.dtype, np.bool_)
        or np.issubdtype(raw.dtype, np.complexfloating)
        or any(isinstance(item, (bool, np.bool_)) for item in objects)
    ):
        raise ValueError("prediction_cohort_index must match predictions with integer labels")
    numeric = raw.astype(np.float64)
    if not np.all(np.isfinite(numeric)) or np.any(numeric != np.floor(numeric)):
        raise ValueError("prediction_cohort_index must contain finite integer labels")
    labels = numeric.astype(np.int64)
    unique = np.unique(labels)
    if not np.array_equal(unique, np.arange(len(unique))):
        raise ValueError("prediction_cohort_index labels must be contiguous from zero")
    return labels, len(unique)


def predict_spatial_activity_counts(
    fitted: SpatialActivityFit,
    *,
    prediction_cohort_index: object,
    seed: int = SEED,
) -> ActivityCountPredictive:
    """Create a marginal count predictive with shared new-cohort effects."""
    if not isinstance(fitted, SpatialActivityFit):
        raise ValueError("fitted must be SpatialActivityFit")
    seed = _integer(seed, "seed", minimum=0)
    cohorts, cohort_count = _prediction_cohorts(
        prediction_cohort_index,
        fitted.n_predictions,
    )
    conditional = fitted.conditional_mean_draws
    if fitted.cohort_sd_draws is not None:
        rng = np.random.default_rng(seed)
        standardized = rng.normal(size=(fitted.n_draws, cohort_count))
        offsets = fitted.cohort_sd_draws[:, np.newaxis] * standardized
        conditional = expit(logit(conditional) + offsets[:, cohorts])
    concentration = np.broadcast_to(
        fitted.concentration_draws[:, np.newaxis],
        conditional.shape,
    )
    return ActivityCountPredictive(
        conditional_mean_draws=conditional,
        activity_probability_draws=fitted.activity_probability_draws,
        concentration_draws=concentration,
    )

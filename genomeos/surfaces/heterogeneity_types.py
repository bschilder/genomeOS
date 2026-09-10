"""Validated B0H fit and prediction contracts (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

import numpy as np

from genomeos.validation.predictive import CountPredictive

SEED = 42
MAX_RHAT = 1.05
MIN_ESS = 200.0


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be positive and finite")
    try:
        normalized = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be positive and finite") from error
    if not isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return normalized


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    normalized = int(value)
    if normalized < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return normalized


def _literal_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty literal string")
    return value


def _canonical_ids(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    normalized = tuple(_literal_id(item, name) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    if normalized != tuple(sorted(normalized)):
        raise ValueError(f"{name} must be canonically sorted")
    return normalized


def _immutable_float64(value: object, name: str, shape: tuple[int, ...]) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype != np.dtype(np.float64):
        raise ValueError(f"{name} must have dtype float64")
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    return np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)


@dataclass(frozen=True)
class PopulationHeterogeneityConfig:
    """Fixed priors and explicit sampler settings for one training-only B0H fit."""

    mean_prior_alpha: float
    mean_prior_beta: float
    rho_prior_alpha: float
    rho_prior_beta: float
    draws: int = 500
    tune: int = 1000
    chains: int = 4
    target_accept: float = 0.9
    seed: int = SEED

    def __post_init__(self) -> None:
        for name in (
            "mean_prior_alpha",
            "mean_prior_beta",
            "rho_prior_alpha",
            "rho_prior_beta",
        ):
            object.__setattr__(self, name, _positive_real(getattr(self, name), name))
        object.__setattr__(self, "draws", _integer(self.draws, "draws", minimum=1))
        object.__setattr__(self, "tune", _integer(self.tune, "tune", minimum=1))
        object.__setattr__(self, "chains", _integer(self.chains, "chains", minimum=4))
        object.__setattr__(self, "seed", _integer(self.seed, "seed", minimum=0))
        target_accept = self.target_accept
        if isinstance(target_accept, (bool, np.bool_)) or not isinstance(target_accept, Real):
            raise ValueError("target_accept must be finite and strictly between 0 and 1")
        try:
            normalized_target = float(target_accept)
        except OverflowError as error:
            raise ValueError("target_accept must be finite and strictly between 0 and 1") from error
        if not isfinite(normalized_target) or not 0.0 < normalized_target < 1.0:
            raise ValueError("target_accept must be finite and strictly between 0 and 1")
        object.__setattr__(self, "target_accept", normalized_target)


@dataclass(frozen=True)
class VariantTrainingCounts:
    """Auditable positive-denominator training totals for one variant."""

    variant_id: str
    training_observation_count: int
    training_ac: int
    training_an: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "variant_id", _literal_id(self.variant_id, "variant_id"))
        count = _integer(self.training_observation_count, "training_observation_count", minimum=1)
        ac = _integer(self.training_ac, "training_ac", minimum=0)
        an = _integer(self.training_an, "training_an", minimum=1)
        if ac > an:
            raise ValueError("training_ac must not exceed training_an")
        object.__setattr__(self, "training_observation_count", count)
        object.__setattr__(self, "training_ac", ac)
        object.__setattr__(self, "training_an", an)


@dataclass(frozen=True)
class VariantHeterogeneityDiagnostics:
    """Finite convergence diagnostics for both parameters of one variant."""

    variant_id: str
    max_rhat: float
    min_bulk_ess: float
    min_tail_ess: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "variant_id", _literal_id(self.variant_id, "variant_id"))
        for name in ("max_rhat", "min_bulk_ess", "min_tail_ess"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
                raise ValueError(f"{name} must be finite")
            normalized = float(value)
            if not isfinite(normalized):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, normalized)


class HeterogeneityConvergenceError(RuntimeError):
    """A sampler result failed fixed B0H convergence gates."""

    def __init__(
        self,
        reason: str,
        *,
        diagnostics: tuple[VariantHeterogeneityDiagnostics, ...] = (),
        divergence_count: int | None = None,
    ) -> None:
        self.reason = _literal_id(reason, "reason")
        self.diagnostics = tuple(diagnostics)
        if any(not isinstance(item, VariantHeterogeneityDiagnostics) for item in self.diagnostics):
            raise ValueError("diagnostics must contain VariantHeterogeneityDiagnostics values")
        self.divergence_count = divergence_count
        if divergence_count is not None:
            self.divergence_count = _integer(divergence_count, "divergence_count", minimum=0)
        super().__init__(self.reason)


@dataclass(frozen=True, eq=False)
class PopulationHeterogeneityFit:
    """Validated labeled posterior draws and training provenance for B0H."""

    config: PopulationHeterogeneityConfig
    variant_ids: tuple[str, ...]
    mean_draws: np.ndarray
    rho_draws: np.ndarray
    training_record_ids: tuple[str, ...]
    training_group_ids: tuple[str, ...]
    unavailable_training_ids: tuple[str, ...]
    training_counts: tuple[VariantTrainingCounts, ...]
    diagnostics: tuple[VariantHeterogeneityDiagnostics, ...]
    divergence_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.config, PopulationHeterogeneityConfig):
            raise ValueError("config must be PopulationHeterogeneityConfig")
        variant_ids = _canonical_ids(self.variant_ids, "variant_ids")
        if not variant_ids:
            raise ValueError("variant_ids must be nonempty")
        shape = (self.config.chains, self.config.draws, len(variant_ids))
        mean = _immutable_float64(self.mean_draws, "mean_draws", shape)
        rho = _immutable_float64(self.rho_draws, "rho_draws", shape)
        if np.any((mean <= 0.0) | (mean >= 1.0)):
            raise ValueError("mean_draws must be strictly between 0 and 1")
        if np.any((rho <= 0.0) | (rho >= 1.0)):
            raise ValueError("rho_draws must be strictly between 0 and 1")
        concentration = (1.0 - rho) / rho
        CountPredictive(
            mean.reshape(-1, len(variant_ids)),
            concentration=concentration.reshape(-1, len(variant_ids)),
        )
        object.__setattr__(self, "variant_ids", variant_ids)
        object.__setattr__(self, "mean_draws", mean)
        object.__setattr__(self, "rho_draws", rho)

        training_record_ids = _canonical_ids(self.training_record_ids, "training_record_ids")
        training_group_ids = _canonical_ids(self.training_group_ids, "training_group_ids")
        unavailable_ids = _canonical_ids(
            self.unavailable_training_ids, "unavailable_training_ids"
        )
        if not set(unavailable_ids) <= set(training_record_ids):
            raise ValueError("unavailable_training_ids must be retained in training_record_ids")
        object.__setattr__(self, "training_record_ids", training_record_ids)
        object.__setattr__(self, "training_group_ids", training_group_ids)
        object.__setattr__(self, "unavailable_training_ids", unavailable_ids)

        training_counts = tuple(self.training_counts)
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, VariantTrainingCounts) for item in training_counts):
            raise ValueError("training_counts must contain VariantTrainingCounts values")
        if any(not isinstance(item, VariantHeterogeneityDiagnostics) for item in diagnostics):
            raise ValueError(
                "diagnostics must contain VariantHeterogeneityDiagnostics values"
            )
        if tuple(item.variant_id for item in training_counts) != variant_ids:
            raise ValueError("training_counts must match variant_ids")
        if tuple(item.variant_id for item in diagnostics) != variant_ids:
            raise ValueError("diagnostics must match variant_ids")
        available_record_count = len(training_record_ids) - len(unavailable_ids)
        if sum(item.training_observation_count for item in training_counts) != available_record_count:
            raise ValueError(
                "summed training_observation_count must match available training provenance"
            )
        if any(item.max_rhat > MAX_RHAT for item in diagnostics) or any(
            item.min_bulk_ess < MIN_ESS or item.min_tail_ess < MIN_ESS for item in diagnostics
        ):
            raise ValueError("diagnostics must satisfy fixed convergence gates")
        object.__setattr__(self, "training_counts", training_counts)
        object.__setattr__(self, "diagnostics", diagnostics)
        divergence_count = _integer(self.divergence_count, "divergence_count", minimum=0)
        if divergence_count:
            raise ValueError("successful fits must have zero divergences")
        object.__setattr__(self, "divergence_count", divergence_count)


@dataclass(frozen=True)
class ReferenceHeterogeneityPrediction:
    """Marginal count predictions and submitted-row identities for one holdout."""

    marginal_predictive: CountPredictive
    observation_ids: tuple[str, ...]
    unavailable_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.marginal_predictive, CountPredictive):
            raise ValueError("marginal_predictive must be CountPredictive")
        observation_ids = tuple(_literal_id(item, "observation_ids") for item in self.observation_ids)
        unavailable_ids = tuple(_literal_id(item, "unavailable_ids") for item in self.unavailable_ids)
        if len(set(observation_ids + unavailable_ids)) != len(observation_ids + unavailable_ids):
            raise ValueError("prediction identities must be unique and disjoint")
        if len(observation_ids) != self.marginal_predictive.n_observations:
            raise ValueError("observation_ids must match predictive observations")
        object.__setattr__(self, "observation_ids", observation_ids)
        object.__setattr__(self, "unavailable_ids", unavailable_ids)

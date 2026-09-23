"""Pure spherical B1 local count smoother (design §§4–8, 12; #307).

Scientific objective
    Test whether nearby reviewed allele counts can preserve local peaks and suppress unsupported
    background without a global latent field or any environmental covariate.
Measurable output
    For each query, return a count-predictive distribution or an explicit support refusal, plus
    footprint-edge distance, weighted evidence, and posterior parameters.
Engineering interface
    :func:`fit_local_count` accepts already-qualified P1 observations and an explicit immutable
    :class:`LocalCountConfig`. It performs no file, network, rendering, or serving-path work.
Assumptions and refusals
    The compact triweight kernel defines a generalized-Bayes power likelihood: weighted allele
    counts are not represented as literal sampled alleles. Training and query rows must describe
    the same single modern variant. Queries with too few in-band training observations return
    ``unknown``; no pooled or prior-only fallback is emitted.

Distances are computed in bounded query chunks. Each chunk broadcasts over all training rows;
there is no query-by-training Python loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real
from typing import Literal

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import validate_allele_observations
from genomeos.validation.predictive import CountPredictive
from genomeos.validation.splits import EARTH_RADIUS_KM

SEED = 42

SupportState = Literal["emitted", "unknown"]


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be positive and finite")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return normalized


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be a positive integer")
    normalized = int(value)
    if normalized <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _seed(value: object) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError("seed must be a nonnegative integer")
    normalized = int(value)
    if normalized < 0:
        raise ValueError("seed must be a nonnegative integer")
    return normalized


@dataclass(frozen=True)
class LocalCountConfig:
    """Declared scientific and bounded-memory configuration for one local fit."""

    bandwidth_km: float
    prior_alpha: float
    prior_beta: float
    posterior_draws: int
    minimum_training_observations: int = 1
    minimum_effective_alleles: float = 1.0
    query_chunk_size: int = 1024

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "bandwidth_km", _positive_real(self.bandwidth_km, "bandwidth_km")
        )
        object.__setattr__(
            self, "prior_alpha", _positive_real(self.prior_alpha, "prior_alpha")
        )
        object.__setattr__(
            self, "prior_beta", _positive_real(self.prior_beta, "prior_beta")
        )
        object.__setattr__(
            self,
            "posterior_draws",
            _positive_integer(self.posterior_draws, "posterior_draws"),
        )
        object.__setattr__(
            self,
            "minimum_training_observations",
            _positive_integer(
                self.minimum_training_observations, "minimum_training_observations"
            ),
        )
        object.__setattr__(
            self,
            "minimum_effective_alleles",
            _positive_real(self.minimum_effective_alleles, "minimum_effective_alleles"),
        )
        object.__setattr__(
            self,
            "query_chunk_size",
            _positive_integer(self.query_chunk_size, "query_chunk_size"),
        )


@dataclass(frozen=True)
class LocalCountSupport:
    """Support decision and auditable weighted-count posterior for one query."""

    source_record_id: str
    status: SupportState
    refusal_reason: str | None
    nearest_edge_distance_km: float
    training_observation_count: int
    effective_training_observations: float
    effective_allele_count: float
    alpha: float | None
    beta: float | None
    posterior_mean: float | None


@dataclass(frozen=True)
class LocalCountFit:
    """Predictive distributions for emitted IDs and support decisions for every query."""

    predictive: CountPredictive | None
    observation_ids: tuple[str, ...]
    support: tuple[LocalCountSupport, ...]


def _validated_inputs(
    training_observations: pd.DataFrame, query_observations: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    training = validate_allele_observations(training_observations)
    queries = validate_allele_observations(query_observations)
    if training.empty:
        raise ValueError("training_observations must not be empty")
    if queries.empty:
        raise ValueError("query_observations must not be empty")
    overlap = sorted(set(training["source_record_id"]) & set(queries["source_record_id"]))
    if overlap:
        raise ValueError(f"training and query source_record_id values overlap: {overlap}")
    variants = tuple(sorted(set(training["variant_id"]) | set(queries["variant_id"])))
    if len(variants) != 1:
        raise ValueError("training and query observations must describe the same single variant")
    if variants[0].startswith("phenotype:"):
        raise ValueError("local count smoothing rejects phenotype composites")
    dated = pd.concat(
        [training.loc[:, ["date_lower", "date_upper"]], queries.loc[:, ["date_lower", "date_upper"]]],
        ignore_index=True,
    )
    if ((dated["date_lower"] != 0) | (dated["date_upper"] != 0)).any():
        raise ValueError("local count smoothing requires modern observations")
    return (
        training.sort_values("source_record_id").reset_index(drop=True),
        queries.sort_values("source_record_id").reset_index(drop=True),
    )


def _edge_distance_chunk(
    query_lat: np.ndarray,
    query_lon: np.ndarray,
    query_radius: np.ndarray,
    training_lat: np.ndarray,
    training_lon: np.ndarray,
    training_radius: np.ndarray,
) -> np.ndarray:
    delta_lat = training_lat[None, :] - query_lat[:, None]
    delta_lon = training_lon[None, :] - query_lon[:, None]
    haversine = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(query_lat[:, None])
        * np.cos(training_lat[None, :])
        * np.sin(delta_lon / 2.0) ** 2
    )
    haversine = np.clip(haversine, 0.0, 1.0)
    center_distance = 2.0 * EARTH_RADIUS_KM * np.arctan2(
        np.sqrt(haversine), np.sqrt(1.0 - haversine)
    )
    return np.maximum(
        center_distance - query_radius[:, None] - training_radius[None, :], 0.0
    )


def _triweight(distance: np.ndarray, bandwidth_km: float) -> np.ndarray:
    scaled = distance / bandwidth_km
    interior = scaled < 1.0
    squared_remainder = np.where(interior, 1.0 - scaled * scaled, 0.0)
    return squared_remainder * squared_remainder * squared_remainder


def fit_local_count(
    training_observations: pd.DataFrame,
    query_observations: pd.DataFrame,
    *,
    config: LocalCountConfig,
    seed: int = SEED,
) -> LocalCountFit:
    """Fit one compact-support local weighted-count posterior at every query."""
    if not isinstance(config, LocalCountConfig):
        raise TypeError("config must be a LocalCountConfig")
    normalized_seed = _seed(seed)
    training, queries = _validated_inputs(training_observations, query_observations)

    training_lat = np.radians(training["lat"].to_numpy(dtype=float, copy=True))
    training_lon = np.radians(training["lon"].to_numpy(dtype=float, copy=True))
    training_radius = training["radius_km"].to_numpy(dtype=float, copy=True)
    training_ac = training["ac"].to_numpy(dtype=float, copy=True)
    training_non_ac = (
        training["an"].to_numpy(dtype=float, copy=True) - training_ac
    )
    training_an = training["an"].to_numpy(dtype=float, copy=True)

    support: list[LocalCountSupport] = []
    emitted_alpha: list[float] = []
    emitted_beta: list[float] = []
    emitted_ids: list[str] = []
    for start in range(0, len(queries), config.query_chunk_size):
        chunk = queries.iloc[start : start + config.query_chunk_size]
        edge_distance = _edge_distance_chunk(
            np.radians(chunk["lat"].to_numpy(dtype=float, copy=True)),
            np.radians(chunk["lon"].to_numpy(dtype=float, copy=True)),
            chunk["radius_km"].to_numpy(dtype=float, copy=True),
            training_lat,
            training_lon,
            training_radius,
        )
        weights = _triweight(edge_distance, config.bandwidth_km)
        observation_count = np.count_nonzero(weights > 0.0, axis=1)
        weight_sum = weights.sum(axis=1)
        weight_square_sum = np.square(weights).sum(axis=1)
        effective_observations = np.divide(
            np.square(weight_sum),
            weight_square_sum,
            out=np.zeros_like(weight_sum),
            where=weight_square_sum > 0.0,
        )
        effective_alleles = weights @ training_an
        alpha = config.prior_alpha + weights @ training_ac
        beta = config.prior_beta + weights @ training_non_ac
        enough_rows = observation_count >= config.minimum_training_observations
        enough_alleles = effective_alleles >= config.minimum_effective_alleles
        emitted = enough_rows & enough_alleles

        for index, record_id in enumerate(chunk["source_record_id"]):
            if emitted[index]:
                posterior_mean = float(alpha[index] / (alpha[index] + beta[index]))
                emitted_ids.append(record_id)
                emitted_alpha.append(float(alpha[index]))
                emitted_beta.append(float(beta[index]))
                support.append(
                    LocalCountSupport(
                        source_record_id=record_id,
                        status="emitted",
                        refusal_reason=None,
                        nearest_edge_distance_km=float(edge_distance[index].min()),
                        training_observation_count=int(observation_count[index]),
                        effective_training_observations=float(effective_observations[index]),
                        effective_allele_count=float(effective_alleles[index]),
                        alpha=float(alpha[index]),
                        beta=float(beta[index]),
                        posterior_mean=posterior_mean,
                    )
                )
            else:
                refusal_reason = (
                    "insufficient_local_training_observations"
                    if not enough_rows[index]
                    else "insufficient_effective_alleles"
                )
                support.append(
                    LocalCountSupport(
                        source_record_id=record_id,
                        status="unknown",
                        refusal_reason=refusal_reason,
                        nearest_edge_distance_km=float(edge_distance[index].min()),
                        training_observation_count=int(observation_count[index]),
                        effective_training_observations=float(effective_observations[index]),
                        effective_allele_count=float(effective_alleles[index]),
                        alpha=None,
                        beta=None,
                        posterior_mean=None,
                    )
                )

    if not emitted_ids:
        return LocalCountFit(predictive=None, observation_ids=(), support=tuple(support))
    alpha_array = np.asarray(emitted_alpha)
    beta_array = np.asarray(emitted_beta)
    rng = np.random.default_rng(normalized_seed)
    mean_draws = rng.beta(
        alpha_array[None, :],
        beta_array[None, :],
        size=(config.posterior_draws, len(emitted_ids)),
    )
    return LocalCountFit(
        predictive=CountPredictive(mean_draws),
        observation_ids=tuple(emitted_ids),
        support=tuple(support),
    )

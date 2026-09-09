"""Pure B0 pooled allele-count baseline (design §§ 5, 7, 8; #189).

The B0 model pools training allele counts separately for each variant and updates an explicit
Beta prior under a binomial likelihood. One latent frequency is sampled per posterior draw and
variant, then shared by every held-out observation of that variant. This represents posterior
uncertainty in a pooled frequency; it is not a resident-calibrated spatial model and does not
model recruited-cohort or survey heterogeneity.

``fit_pooled_b0`` is deterministic given its validated observations, prior, draw count and seed.
Held-out counts never enter the posterior. A held-out variant without training evidence is
refused rather than assigned the prior or pooled with another variant.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import validate_allele_observations
from genomeos.validation.predictive import CountPredictive

SEED = 42


class B0InfeasibleError(ValueError):
    """The declared holdout cannot be evaluated by the B0 scientific model."""

    def __init__(self, absent_variants: tuple[str, ...]) -> None:
        self.absent_variants = absent_variants
        super().__init__(f"test variants absent from training: {list(absent_variants)}")


@dataclass(frozen=True)
class B0VariantPosterior:
    """Auditable pooled posterior parameters for one training variant."""

    variant_id: str
    training_observation_count: int
    training_ac: int
    training_an: int
    alpha: float
    beta: float


@dataclass(frozen=True)
class PooledB0Fit:
    """Posterior predictive aligned to held-out rows plus its fitted parameters."""

    predictive: CountPredictive
    observation_ids: tuple[str, ...]
    posteriors: tuple[B0VariantPosterior, ...]


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


def fit_pooled_b0(
    training_observations: pd.DataFrame,
    test_observations: pd.DataFrame,
    *,
    prior_alpha: float,
    prior_beta: float,
    posterior_draws: int,
    seed: int = SEED,
) -> PooledB0Fit:
    """Fit per-variant pooled Beta posteriors and return held-out binomial mixtures."""
    training = validate_allele_observations(training_observations)
    testing = validate_allele_observations(test_observations)
    alpha_prior = _positive_real(prior_alpha, "prior_alpha")
    beta_prior = _positive_real(prior_beta, "prior_beta")
    draws = _positive_integer(posterior_draws, "posterior_draws")
    normalized_seed = _seed(seed)

    test_variants = tuple(sorted(testing["variant_id"].unique()))
    training_variants = set(training["variant_id"])
    absent = tuple(sorted(set(test_variants) - training_variants))
    if absent:
        raise B0InfeasibleError(absent)

    rng = np.random.default_rng(normalized_seed)
    draws_by_variant: dict[str, np.ndarray] = {}
    posteriors: list[B0VariantPosterior] = []
    for variant_id in test_variants:
        rows = training.loc[training["variant_id"] == variant_id]
        total_ac = int(rows["ac"].sum())
        total_an = int(rows["an"].sum())
        posterior_alpha = alpha_prior + total_ac
        posterior_beta = beta_prior + total_an - total_ac
        if (
            not isfinite(posterior_alpha)
            or not isfinite(posterior_beta)
            or not isfinite(posterior_alpha + posterior_beta)
        ):
            raise ValueError(
                f"posterior parameters for {variant_id!r} are outside the stable numeric domain"
            )
        draws_by_variant[variant_id] = rng.beta(posterior_alpha, posterior_beta, size=draws)
        posteriors.append(
            B0VariantPosterior(
                variant_id=variant_id,
                training_observation_count=int(len(rows)),
                training_ac=total_ac,
                training_an=total_an,
                alpha=posterior_alpha,
                beta=posterior_beta,
            )
        )

    mean_draws = np.column_stack(
        [draws_by_variant[variant_id] for variant_id in testing["variant_id"]]
    )
    return PooledB0Fit(
        predictive=CountPredictive(mean_draws),
        observation_ids=tuple(testing["source_record_id"]),
        posteriors=tuple(posteriors),
    )

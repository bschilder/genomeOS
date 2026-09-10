"""Pure pooled allele-count posterior kernel (design §§ 5, 7, 8; #189).

This module operates only on already-qualified allele counts. It performs no P1
observation validation, file access, sampling, or serving-path inference.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

import numpy as np


def _literal_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty literal string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    return int(value)


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


@dataclass(frozen=True)
class PooledAlleleCount:
    """One qualified allele count supplied to the shared posterior kernel."""

    record_id: str
    variant_id: str
    ac: int
    an: int

    def __post_init__(self) -> None:
        record_id = _literal_id(self.record_id, "record_id")
        variant_id = _literal_id(self.variant_id, "variant_id")
        ac = _integer(self.ac, "ac")
        an = _integer(self.an, "an")
        if an <= 0:
            raise ValueError("an must be a positive integer")
        if ac < 0 or ac > an:
            raise ValueError("ac must satisfy 0 <= ac <= an")
        object.__setattr__(self, "record_id", record_id)
        object.__setattr__(self, "variant_id", variant_id)
        object.__setattr__(self, "ac", ac)
        object.__setattr__(self, "an", an)


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


def pooled_beta_posteriors(
    training_counts: Sequence[PooledAlleleCount],
    variant_ids: Sequence[str],
    *,
    prior_alpha: float,
    prior_beta: float,
) -> tuple[B0VariantPosterior, ...]:
    """Pool matching training counts into sorted per-variant Beta posteriors."""
    rows = tuple(training_counts)
    if any(not isinstance(row, PooledAlleleCount) for row in rows):
        raise ValueError("training_counts must contain only PooledAlleleCount values")
    record_ids = tuple(row.record_id for row in rows)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("training record_id values must be unique")

    requested = tuple(_literal_id(value, "variant_id") for value in variant_ids)
    if not requested:
        raise ValueError("variant_ids must be nonempty")
    if len(set(requested)) != len(requested):
        raise ValueError("variant_ids must be unique")

    alpha_prior = _positive_real(prior_alpha, "prior_alpha")
    beta_prior = _positive_real(prior_beta, "prior_beta")
    training_variants = {row.variant_id for row in rows}
    absent = tuple(sorted(set(requested) - training_variants))
    if absent:
        raise B0InfeasibleError(absent)

    posteriors = []
    for variant_id in sorted(requested):
        matching = tuple(row for row in rows if row.variant_id == variant_id)
        total_ac = sum(row.ac for row in matching)
        total_an = sum(row.an for row in matching)
        try:
            alpha = alpha_prior + total_ac
            beta = beta_prior + (total_an - total_ac)
            concentration = alpha + beta
        except OverflowError as error:
            raise ValueError(
                f"posterior parameters for {variant_id!r} are outside the stable numeric domain"
            ) from error
        if (
            not isfinite(alpha)
            or alpha <= 0.0
            or not isfinite(beta)
            or beta <= 0.0
            or not isfinite(concentration)
            or concentration <= 0.0
        ):
            raise ValueError(
                f"posterior parameters for {variant_id!r} are outside the stable numeric domain"
            )
        posteriors.append(
            B0VariantPosterior(
                variant_id,
                len(matching),
                total_ac,
                total_an,
                alpha,
                beta,
            )
        )
    return tuple(posteriors)

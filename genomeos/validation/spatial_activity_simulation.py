"""Registered synthetic truths for the spatial activity preflight (design §§7–8; #384).

The null, weak-separation, and strong-separation regimes are generated only from explicit
unit-sphere coordinates, denominators, cohort identities, configuration, and seed. Counts are
new synthetic observations. No real allele count, burden layer, pathogen layer, or fitted-model
error determines the truth fields.

Synthetic latent activity is retained solely because this module owns the known data-generating
truth. A downstream model still receives counts and may never classify a real observed zero as
inactive.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real
from typing import Literal

import numpy as np
from scipy.special import expit, logit

from genomeos.validation.predictive import MAX_COUNT
from genomeos.validation.spatial_activity_preflight import simulate_activity_counts

SEED = 42
DEFAULT_SEEDS = (42, 43, 44)
TRUTH_REGIMES = ("null", "localized_weak", "localized_strong")
TruthRegime = Literal["null", "localized_weak", "localized_strong"]
_LOCAL_RADIUS_CHORD = 0.40


def _real(value: object, name: str, *, minimum: float, strict: bool) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite")
    normalized = float(value)
    valid = normalized > minimum if strict else normalized >= minimum
    if not isfinite(normalized) or not valid:
        relation = "greater than" if strict else "at least"
        raise ValueError(f"{name} must be finite and {relation} {minimum}")
    return normalized


def _seed(value: object) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError("seed must be a nonnegative integer")
    normalized = int(value)
    if normalized < 0:
        raise ValueError("seed must be a nonnegative integer")
    return normalized


@dataclass(frozen=True)
class SpatialActivityScenario:
    """One preregistered data-generating condition and development seed."""

    truth: TruthRegime
    denominator_multiplier: float
    cohort_sd: float
    concentration: float
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.truth, str) or self.truth not in TRUTH_REGIMES:
            raise ValueError(f"truth must be one of {TRUTH_REGIMES}")
        object.__setattr__(
            self,
            "denominator_multiplier",
            _real(
                self.denominator_multiplier,
                "denominator_multiplier",
                minimum=0.0,
                strict=True,
            ),
        )
        object.__setattr__(
            self,
            "cohort_sd",
            _real(self.cohort_sd, "cohort_sd", minimum=0.0, strict=False),
        )
        object.__setattr__(
            self,
            "concentration",
            _real(self.concentration, "concentration", minimum=0.0, strict=True),
        )
        object.__setattr__(self, "seed", _seed(self.seed))

    @property
    def scenario_id(self) -> str:
        denominator = f"{self.denominator_multiplier:g}".replace(".", "p")
        cohort = f"{self.cohort_sd:g}".replace(".", "p")
        return f"{self.truth}-denom-{denominator}-cohort-{cohort}-seed-{self.seed}"


@dataclass(frozen=True)
class SpatialActivitySyntheticData:
    """Synthetic counts and known truth in the caller's original row order."""

    scenario: SpatialActivityScenario
    record_ids: tuple[str, ...]
    cohort_ids: tuple[str, ...]
    ac: tuple[int, ...]
    an: tuple[int, ...]
    active: tuple[bool, ...]
    reference_conditional_mean_truth: tuple[float, ...]
    observation_conditional_mean_truth: tuple[float, ...]
    activity_probability_truth: tuple[float, ...]
    marginal_mean_truth: tuple[float, ...]
    cohort_logit_offset_truth: tuple[float, ...]


def default_spatial_activity_scenarios() -> tuple[SpatialActivityScenario, ...]:
    """Return the frozen 18-condition development grid for seeds 42, 43, and 44."""
    conditions: tuple[tuple[TruthRegime, float, float], ...] = (
        ("null", 1.0, 0.0),
        ("localized_weak", 1.0, 0.0),
        ("localized_strong", 1.0, 0.0),
        ("localized_strong", 0.25, 0.0),
        ("localized_strong", 4.0, 0.0),
        ("localized_strong", 1.0, 0.5),
    )
    return tuple(
        SpatialActivityScenario(
            truth=truth,
            denominator_multiplier=denominator_multiplier,
            cohort_sd=cohort_sd,
            concentration=40.0,
            seed=seed,
        )
        for seed in DEFAULT_SEEDS
        for truth, denominator_multiplier, cohort_sd in conditions
    )


def _labels(value: object, name: str, *, expected: int | None = None) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list, np.ndarray)):
        raise ValueError(f"{name} must be a one-dimensional sequence of literal strings")
    raw = np.asarray(value, dtype=object)
    if raw.ndim != 1 or (expected is not None and len(raw) != expected):
        if expected is None:
            raise ValueError(f"{name} must be a nonempty one-dimensional sequence")
        raise ValueError(f"{name} must match record_ids")
    labels = tuple(raw.tolist())
    if not labels or any(not isinstance(item, str) or not item.strip() for item in labels):
        raise ValueError(f"{name} must contain nonempty literal strings")
    return labels


def _coordinates(value: object, *, expected: int) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError("coordinates must be a numeric unit-sphere matrix") from error
    if (
        raw.shape != (expected, 3)
        or not np.issubdtype(raw.dtype, np.number)
        or np.issubdtype(raw.dtype, np.bool_)
        or np.issubdtype(raw.dtype, np.complexfloating)
    ):
        raise ValueError("coordinates must match record_ids with shape (rows, 3)")
    coordinates = raw.astype(np.float64)
    if not np.all(np.isfinite(coordinates)):
        raise ValueError("coordinates must contain finite values")
    if not np.allclose(
        np.linalg.norm(coordinates, axis=1),
        np.ones(expected),
        rtol=0.0,
        atol=1e-8,
    ):
        raise ValueError("coordinate rows must be unit-sphere vectors")
    if len(np.unique(coordinates, axis=0)) < 2:
        raise ValueError("coordinates must contain at least two distinct locations")
    return coordinates


def _denominators(value: object, *, expected: int, multiplier: float) -> np.ndarray:
    try:
        raw = np.asarray(value)
        objects = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as error:
        raise ValueError("an must contain positive integer denominators") from error
    if (
        raw.shape != (expected,)
        or not np.issubdtype(raw.dtype, np.number)
        or np.issubdtype(raw.dtype, np.bool_)
        or np.issubdtype(raw.dtype, np.complexfloating)
        or any(isinstance(item, (bool, np.bool_)) for item in objects)
    ):
        raise ValueError("an must match record_ids with positive integer denominators")
    numeric = raw.astype(np.float64)
    if (
        not np.all(np.isfinite(numeric))
        or np.any(numeric != np.floor(numeric))
        or np.any(numeric <= 0.0)
    ):
        raise ValueError("an must contain positive finite integer denominators")
    scaled = np.rint(numeric * multiplier)
    if np.any(scaled <= 0.0) or np.any(scaled > MAX_COUNT):
        raise ValueError(
            f"scaled denominators must be between one and MAX_COUNT={MAX_COUNT}"
        )
    return scaled.astype(np.int64)


def _activity_centres(coordinates: np.ndarray) -> np.ndarray:
    unique = np.unique(coordinates, axis=0)
    first = unique[0]
    distance = np.linalg.norm(unique - first, axis=1)
    maximum = float(np.max(distance))
    candidates = unique[np.isclose(distance, maximum, rtol=0.0, atol=1e-12)]
    second = candidates[0]
    return np.vstack((first, second))


def _truth_fields(
    coordinates: np.ndarray,
    truth: TruthRegime,
) -> tuple[np.ndarray, np.ndarray]:
    centres = _activity_centres(coordinates)
    distance = np.linalg.norm(
        coordinates[:, np.newaxis, :] - centres[np.newaxis, :, :],
        axis=2,
    )
    localized = np.max(
        np.exp(-0.5 * (distance / _LOCAL_RADIUS_CHORD) ** 2),
        axis=1,
    )
    broad_logit = -3.2 + 0.65 * coordinates[:, 2] - 0.45 * coordinates[:, 1]
    if truth == "null":
        return expit(broad_logit), np.ones(len(coordinates))
    if truth == "localized_weak":
        return expit(-5.0 + 3.0 * localized), expit(-0.8 + 3.0 * localized)
    return expit(broad_logit), expit(-3.5 + 8.0 * localized)


def _restore(values: np.ndarray, canonical_order: np.ndarray) -> np.ndarray:
    restored = np.empty_like(values)
    restored[canonical_order] = values
    return restored


def simulate_spatial_activity_scenario(
    record_ids: object,
    coordinates: object,
    an: object,
    *,
    cohort_ids: object,
    scenario: SpatialActivityScenario,
) -> SpatialActivitySyntheticData:
    """Generate one row-order-invariant synthetic count dataset."""
    if not isinstance(scenario, SpatialActivityScenario):
        raise ValueError("scenario must be SpatialActivityScenario")
    records = _labels(record_ids, "record_ids")
    if len(set(records)) != len(records):
        raise ValueError("record_ids must be unique")
    cohorts = _labels(cohort_ids, "cohort_ids", expected=len(records))
    positions = _coordinates(coordinates, expected=len(records))
    denominators = _denominators(
        an,
        expected=len(records),
        multiplier=scenario.denominator_multiplier,
    )

    canonical_order = np.argsort(np.asarray(records), kind="stable")
    canonical_positions = positions[canonical_order]
    canonical_denominators = denominators[canonical_order]
    canonical_cohorts = np.asarray(cohorts, dtype=object)[canonical_order]
    reference_mean, activity_probability = _truth_fields(
        canonical_positions,
        scenario.truth,
    )

    cohort_labels = tuple(sorted(set(canonical_cohorts.tolist())))
    cohort_index = {label: index for index, label in enumerate(cohort_labels)}
    seed_sequence = np.random.SeedSequence(scenario.seed)
    cohort_seed, count_seed = seed_sequence.spawn(2)
    cohort_rng = np.random.default_rng(cohort_seed)
    cohort_offsets = (
        np.zeros(len(cohort_labels), dtype=np.float64)
        if scenario.cohort_sd == 0.0
        else cohort_rng.normal(0.0, scenario.cohort_sd, len(cohort_labels))
    )
    row_offsets = np.asarray(
        [cohort_offsets[cohort_index[label]] for label in canonical_cohorts],
        dtype=np.float64,
    )
    observation_mean = expit(logit(reference_mean) + row_offsets)
    simulation = simulate_activity_counts(
        canonical_denominators,
        conditional_mean=observation_mean,
        concentration=np.full(len(records), scenario.concentration),
        activity_probability=activity_probability,
        seed=int(count_seed.generate_state(1, dtype=np.uint32)[0]),
    )
    alternate = np.asarray(simulation.ac, dtype=np.int64)
    active = np.asarray(simulation.active, dtype=np.bool_)
    marginal = activity_probability * observation_mean

    return SpatialActivitySyntheticData(
        scenario=scenario,
        record_ids=records,
        cohort_ids=cohorts,
        ac=tuple(int(value) for value in _restore(alternate, canonical_order)),
        an=tuple(int(value) for value in _restore(canonical_denominators, canonical_order)),
        active=tuple(bool(value) for value in _restore(active, canonical_order)),
        reference_conditional_mean_truth=tuple(
            float(value) for value in _restore(reference_mean, canonical_order)
        ),
        observation_conditional_mean_truth=tuple(
            float(value) for value in _restore(observation_mean, canonical_order)
        ),
        activity_probability_truth=tuple(
            float(value) for value in _restore(activity_probability, canonical_order)
        ),
        marginal_mean_truth=tuple(
            float(value) for value in _restore(marginal, canonical_order)
        ),
        cohort_logit_offset_truth=tuple(
            float(value) for value in _restore(row_offsets, canonical_order)
        ),
    )

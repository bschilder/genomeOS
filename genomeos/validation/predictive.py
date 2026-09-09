"""Exact posterior-predictive scoring for allele counts (design §7, §8; #189).

``CountPredictive`` represents a mixture over draw-aligned observation distributions. Callers
must provide probabilities after every intended latent, cohort, and sampling-design effect has
already been applied. A missing effect is not inferred or defaulted here.

Predictive intervals are central, equal-tail intervals of a finite discrete count distribution.
Their endpoints lie on the ``1 / AN`` frequency grid and coverage can therefore exceed the
nominal level, especially for small denominators or boundary-heavy predictions. Width and
coverage must be interpreted together rather than treating nominal coverage as exactly attainable.

Beta-binomial CDFs are summed exactly in fixed-size chunks, using the shorter support tail. This
keeps memory bounded independently of ``AN`` but does not hide the computational cost: an exact
interior CDF or quantile can still require time proportional to the shorter tail length.

The supported count domain is ``-1 <= AC <= AN <= 2**31 - 1`` (with ``AC=-1`` reserved for the
CDF boundary). The upper bound keeps integer successor and floating log-mass arithmetic inside a
tested domain far beyond any individual survey. Interior beta-binomial concentrations above
``1 / sqrt(float epsilon)`` are refused because subtracting their log-beta normalizers no longer
retains reliable probability-scale precision; callers must explicitly select binomial semantics
rather than obtain that distribution through an unstable finite-concentration approximation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import betaln, gammaln, logsumexp, xlog1py, xlogy
from scipy.stats import binom

SEED = 42
MAX_COUNT = int(np.iinfo(np.int32).max)
_MAX_BETA_CONCENTRATION = float(1.0 / np.sqrt(np.finfo(float).eps))
_CDF_CHUNK_SIZE = 4096


def _numeric_array(value: object, name: str) -> np.ndarray:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
        array.dtype, np.complexfloating
    ):
        raise ValueError(f"{name} must be numeric")
    return array


def _float_array(value: object, name: str) -> np.ndarray:
    return _numeric_array(value, name).astype(float)


def _immutable_array(array: np.ndarray) -> np.ndarray:
    """Copy onto a bytes-backed buffer whose write flag cannot be re-enabled."""
    contiguous = np.ascontiguousarray(array)
    return np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)


def _count_vector(value: object, name: str, observations: int) -> np.ndarray:
    array = _numeric_array(value, name)
    if array.shape != (observations,):
        raise ValueError(f"{name} must have shape ({observations},)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    if np.issubdtype(array.dtype, np.floating) and not np.all(array == np.floor(array)):
        raise ValueError(f"{name} must contain integer counts")
    if np.any(array > MAX_COUNT):
        raise ValueError(f"{name} exceeds the supported maximum {MAX_COUNT}")
    return array.astype(np.int64)


def _validated_an(value: object, observations: int) -> np.ndarray:
    an = _count_vector(value, "an", observations)
    if np.any(an <= 0):
        raise ValueError("an must contain positive denominators")
    return an


def _validated_ac(
    value: object, an: np.ndarray, observations: int, *, cdf_threshold: bool
) -> np.ndarray:
    ac = _count_vector(value, "ac", observations)
    lower = -1 if cdf_threshold else 0
    if np.any(ac < lower) or np.any(ac > an):
        interval = "between -1 and AN" if cdf_threshold else "between 0 and AN"
        raise ValueError(f"ac must be {interval}")
    return ac


def _log_combination(n: int | np.ndarray, k: np.ndarray) -> np.ndarray:
    return gammaln(np.asarray(n) + 1) - gammaln(k + 1) - gammaln(np.asarray(n) - k + 1)


def _beta_binomial_log_mass(
    k: np.ndarray, n: int, alpha: float, beta: float
) -> np.ndarray:
    return _log_combination(n, k) + betaln(k + alpha, n - k + beta) - betaln(alpha, beta)


def _beta_binomial_tail_logsum(
    start: int, stop: int, n: int, alpha: float, beta: float
) -> float:
    total = -np.inf
    for chunk_start in range(start, stop, _CDF_CHUNK_SIZE):
        chunk_stop = min(chunk_start + _CDF_CHUNK_SIZE, stop)
        support = np.arange(chunk_start, chunk_stop, dtype=np.int64)
        total = float(
            np.logaddexp(
                total,
                logsumexp(_beta_binomial_log_mass(support, n, alpha, beta)),
            )
        )
    return total


def _beta_binomial_cdf(k: int, n: int, mean: float, concentration: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if mean == 0.0:
        return 1.0
    if mean == 1.0:
        return 0.0

    alpha = mean * concentration
    beta = (1.0 - mean) * concentration
    lower_terms = k + 1
    upper_terms = n - k
    if lower_terms <= upper_terms:
        return float(np.exp(_beta_binomial_tail_logsum(0, k + 1, n, alpha, beta)))

    log_survival = _beta_binomial_tail_logsum(k + 1, n + 1, n, alpha, beta)
    return float(-np.expm1(log_survival))


def _validate_beta_shapes(mean: np.ndarray, concentration: np.ndarray) -> None:
    interior = (mean > 0.0) & (mean < 1.0)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        alpha = mean[interior] * concentration[interior]
        beta = (1.0 - mean[interior]) * concentration[interior]
        log_normalizer = betaln(alpha, beta)
    unusable = (
        (alpha <= 0.0)
        | (beta <= 0.0)
        | ~np.isfinite(alpha)
        | ~np.isfinite(beta)
        | ~np.isfinite(log_normalizer)
        | (concentration[interior] > _MAX_BETA_CONCENTRATION)
    )
    if np.any(unusable):
        raise ValueError(
            "interior mean and concentration produce beta-binomial shape parameters "
            "outside the supported stable numeric domain"
        )


@dataclass(frozen=True, eq=False)
class CountPredictive:
    """Immutable binomial or beta-binomial mixture over predictive draws.

    Both parameter arrays have shape ``(draws, observations)``. ``concentration=None`` selects
    the binomial distribution explicitly; otherwise each draw is beta-binomial with
    ``alpha = mean * concentration`` and ``beta = (1 - mean) * concentration``.
    """

    mean_draws: np.ndarray
    concentration: np.ndarray | None = None

    def __post_init__(self) -> None:
        mean = _float_array(self.mean_draws, "mean_draws")
        if mean.ndim != 2:
            raise ValueError("mean_draws must be a two-dimensional (draws, observations) array")
        if 0 in mean.shape:
            raise ValueError("mean_draws must contain at least one draw and observation")
        if not np.all(np.isfinite(mean)):
            raise ValueError("mean_draws must be finite")
        if np.any((mean < 0.0) | (mean > 1.0)):
            raise ValueError("mean_draws must be between 0 and 1")
        mean = _immutable_array(mean)
        object.__setattr__(self, "mean_draws", mean)

        if self.concentration is None:
            return
        concentration = _float_array(self.concentration, "concentration")
        if concentration.shape != mean.shape:
            raise ValueError("concentration must have the same shape as mean_draws")
        if not np.all(np.isfinite(concentration)):
            raise ValueError("concentration must be finite")
        if np.any(concentration <= 0.0):
            raise ValueError("concentration must be positive")
        _validate_beta_shapes(mean, concentration)
        concentration = _immutable_array(concentration)
        object.__setattr__(self, "concentration", concentration)

    @property
    def n_draws(self) -> int:
        return self.mean_draws.shape[0]

    @property
    def n_observations(self) -> int:
        return self.mean_draws.shape[1]

    def _counts(
        self, ac: object, an: object, *, cdf_threshold: bool = False
    ) -> tuple[np.ndarray, np.ndarray]:
        denominator = _validated_an(an, self.n_observations)
        count = _validated_ac(
            ac, denominator, self.n_observations, cdf_threshold=cdf_threshold
        )
        return count, denominator

    def _draw_log_mass(self, ac: np.ndarray, an: np.ndarray) -> np.ndarray:
        count = ac[np.newaxis, :]
        denominator = an[np.newaxis, :]
        mean = self.mean_draws
        log_mass = _log_combination(denominator, count)

        if self.concentration is None:
            return log_mass + xlogy(count, mean) + xlog1py(denominator - count, -mean)

        result = np.full(mean.shape, -np.inf)
        at_zero = mean == 0.0
        at_one = mean == 1.0
        result[at_zero & (count == 0)] = 0.0
        result[at_one & (count == denominator)] = 0.0
        interior = ~(at_zero | at_one)
        alpha = mean[interior] * self.concentration[interior]
        beta = (1.0 - mean[interior]) * self.concentration[interior]
        interior_count = np.broadcast_to(count, mean.shape)[interior]
        interior_an = np.broadcast_to(denominator, mean.shape)[interior]
        result[interior] = (
            _log_combination(interior_an, interior_count)
            + betaln(interior_count + alpha, interior_an - interior_count + beta)
            - betaln(alpha, beta)
        )
        return result

    def log_prob(self, ac: object, an: object) -> np.ndarray:
        """Integrated log probability mass for each valid observed count."""
        count, denominator = self._counts(ac, an)
        return logsumexp(self._draw_log_mass(count, denominator), axis=0) - np.log(
            self.n_draws
        )

    def _cdf_one(self, observation: int, ac: int, an: int) -> float:
        if ac == -1:
            return 0.0
        if ac == an:
            return 1.0
        means = self.mean_draws[:, observation]
        if self.concentration is None:
            return float(np.mean(binom.cdf(ac, an, means)))
        concentrations = self.concentration[:, observation]
        return float(
            np.mean(
                [
                    _beta_binomial_cdf(ac, an, float(mean), float(concentration))
                    for mean, concentration in zip(means, concentrations, strict=True)
                ]
            )
        )

    def cdf(self, ac: object, an: object) -> np.ndarray:
        """Integrated ``P(Y <= ac)``; ``ac=-1`` is admitted only as the lower CDF boundary."""
        count, denominator = self._counts(ac, an, cdf_threshold=True)
        return np.array(
            [
                self._cdf_one(index, int(count[index]), int(denominator[index]))
                for index in range(self.n_observations)
            ]
        )

    def sample_counts(self, an: object, seed: int = SEED) -> np.ndarray:
        """One replicated count for every predictive draw and observation."""
        denominator = _validated_an(an, self.n_observations)
        rng = np.random.default_rng(seed)
        probability = self.mean_draws
        if self.concentration is not None:
            probability = self.mean_draws.copy()
            interior = (probability > 0.0) & (probability < 1.0)
            alpha = probability[interior] * self.concentration[interior]
            beta = (1.0 - probability[interior]) * self.concentration[interior]
            probability[interior] = rng.beta(alpha, beta)
        return rng.binomial(denominator[np.newaxis, :], probability)

    def _quantiles(self, an: object, probabilities: object) -> np.ndarray:
        """Exact left-continuous count quantiles without materializing ``0, ..., AN``."""
        denominator = _validated_an(an, self.n_observations)
        levels = _float_array(probabilities, "probabilities")
        if levels.ndim != 1 or len(levels) == 0:
            raise ValueError("probabilities must be a nonempty one-dimensional array")
        if not np.all(np.isfinite(levels)) or np.any((levels <= 0.0) | (levels > 1.0)):
            raise ValueError("probabilities must be finite and between 0 (exclusive) and 1")

        result = np.empty((len(levels), self.n_observations), dtype=np.int64)
        for level_index, level in enumerate(levels):
            for observation, n in enumerate(denominator):
                low, high = -1, int(n)
                while high - low > 1:
                    midpoint = (low + high) // 2
                    if self._cdf_one(observation, midpoint, int(n)) >= level:
                        high = midpoint
                    else:
                        low = midpoint
                result[level_index, observation] = high
        return result


def predictive_diagnostics(
    predictive: CountPredictive, ac: object, an: object, seed: int = SEED
) -> pd.DataFrame:
    """Per-observation proper score, error ingredients, intervals, and randomized PIT.

    ``absolute_error`` can be averaged directly to obtain MAE. Average ``squared_error`` before
    taking its square root to obtain RMSE; averaging per-row square roots would instead be MAE.
    """
    count, denominator = predictive._counts(ac, an)
    log_score = predictive.log_prob(count, denominator)
    observed_frequency = count / denominator
    levels = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
    quantiles = predictive._quantiles(denominator, levels)
    by_level = {level: quantiles[index] for index, level in enumerate(levels)}

    median_frequency = by_level[0.5] / denominator
    predictive_mean = np.mean(predictive.mean_draws, axis=0)
    data: dict[str, np.ndarray] = {
        "log_score": log_score,
        "absolute_error": np.abs(median_frequency - observed_frequency),
        "squared_error": (predictive_mean - observed_frequency) ** 2,
    }
    for label, lower_level, upper_level in (
        (50, 0.25, 0.75),
        (80, 0.1, 0.9),
        (95, 0.025, 0.975),
    ):
        lower = by_level[lower_level]
        upper = by_level[upper_level]
        data[f"coverage_{label}"] = (count >= lower) & (count <= upper)
        data[f"interval_width_{label}"] = (upper - lower) / denominator

    lower_cdf = predictive.cdf(count - 1, denominator)
    probability_mass = np.exp(log_score)
    data["randomized_pit"] = lower_cdf + np.random.default_rng(seed).random(
        predictive.n_observations
    ) * probability_mass
    return pd.DataFrame(data)

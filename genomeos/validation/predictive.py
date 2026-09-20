"""Exact posterior-predictive scoring for allele counts (design §7, §8; #189, #314).

``CountPredictive`` represents a mixture over draw-aligned observation distributions. Callers
must provide probabilities after every intended latent, cohort, and sampling-design effect has
already been applied. A missing effect is not inferred or defaulted here.

Predictive intervals are central, equal-tail intervals of a finite discrete count distribution.
Their endpoints lie on the ``1 / AN`` frequency grid and coverage can therefore exceed the
nominal level, especially for small denominators or boundary-heavy predictions. Width and
coverage must be interpreted together rather than treating nominal coverage as exactly attainable.
Quantile search starts from a Cantelli upper bracket derived from the exact predictive-mixture
moments, verifies that bracket with the selected exact CDF backend, and only then bisects. This
avoids probing the middle of a million-count support for a rare allele without approximating the
returned quantile (#316).

Beta-binomial CDFs are summed exactly in fixed-size chunks, starting with the shorter support
tail. If that tail has probability above one half, the small complementary tail is summed
directly. This keeps memory bounded independently of ``AN`` but does not hide the
computational cost: an exact interior CDF or quantile can still require time proportional to a
support-tail length.

The supported count domain is ``-1 <= AC <= AN <= 2**31 - 1`` (with ``AC=-1`` reserved for the
CDF boundary). The upper bound keeps integer successor and floating log-mass arithmetic inside a
tested domain far beyond any individual survey. Interior beta-binomial concentrations above
``1 / sqrt(float epsilon)`` are refused because subtracting their log-beta normalizers no longer
retains reliable probability-scale precision; callers must explicitly select binomial semantics
rather than obtain that distribution through an unstable finite-concentration approximation.
Log mass uses a fixed exact prefix followed by a controlled Euler--Maclaurin tail for each
rising factorial. Tail log ratios switch between an algebraically differenced ``log1p`` form near
zero and direct ``log1p`` subtraction away from zero; the differenced form loses significant bits
when its argument approaches negative one at high shape and count. Two equivalent factorizations
are evaluated, and the one with the smaller sum of intermediate magnitudes is selected per draw to
avoid cancellation at both high counts and high concentration. Work and temporary arrays remain
bounded independently of ``AN``. CDF and quantile queries retain their exact tail-sum arithmetic,
whose runtime can still depend on the queried support tail.
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
_LOG_HALF = float(np.log(0.5))
_RISING_EXACT_PREFIX = 16
_RISING_PREFIX_INDEX = np.arange(_RISING_EXACT_PREFIX, dtype=float)
_STIRLING_POWERS = np.asarray((1, 3, 5, 7, 9, 11), dtype=float)
_STIRLING_COEFFICIENTS = np.asarray(
    (1.0 / 12.0, -1.0 / 360.0, 1.0 / 1260.0, -1.0 / 1680.0, 1.0 / 1188.0, -691.0 / 360360.0)
)


def _log_ratio(
    numerator: np.ndarray,
    denominator: np.ndarray,
    difference: np.ndarray | None = None,
) -> np.ndarray:
    """Return ``log(numerator / denominator)`` accurately near and far from one."""
    if difference is None:
        difference = numerator - denominator
    near_one = np.abs(difference) < 0.5 * denominator
    log1p_difference = np.where(near_one, difference, 0.0)
    stable = np.log1p(log1p_difference / denominator)
    direct = np.log(numerator) - np.log(denominator)
    return np.where(near_one, stable, direct)


def _bounded_log_rising_ratio(
    numerator: np.ndarray,
    denominator: np.ndarray,
    length: int,
    *,
    difference: np.ndarray | None = None,
) -> np.ndarray:
    """Evaluate ``log((numerator)_length / (denominator)_length)`` in bounded work.

    The first 16 factors are direct log ratios. The remaining Euler--Maclaurin terms are
    algebraically differenced before evaluation; separately evaluating two large rising
    factorials would erase a small but valid log probability through cancellation.
    """
    if difference is None:
        difference = numerator - denominator
    result = np.zeros(np.broadcast_shapes(numerator.shape, denominator.shape))
    prefix = _RISING_PREFIX_INDEX[: min(length, _RISING_EXACT_PREFIX)]
    if prefix.size:
        result += np.sum(
            _log_ratio(
                numerator[..., np.newaxis] + prefix,
                denominator[..., np.newaxis] + prefix,
                difference[..., np.newaxis],
            ),
            axis=-1,
        )

    remaining = max(length - _RISING_EXACT_PREFIX, 0)
    numerator_start = numerator + _RISING_EXACT_PREFIX
    denominator_start = denominator + _RISING_EXACT_PREFIX
    log_start_ratio = _log_ratio(
        numerator_start, denominator_start, difference
    )
    denominator_tail_log = np.log1p(remaining / denominator_start)
    # log1p(remaining / numerator_start) - log1p(remaining / denominator_start).
    # The single-log identity is accurate near zero, but its argument can approach -1 when
    # one rising-factorial base is much larger than the other. In that regime, forming 1+x
    # loses bits before log1p sees it; the two direct log1p terms remain well conditioned.
    tail_log_argument = -(difference / numerator_start) * (
        remaining / (denominator_start + remaining)
    )
    use_differenced_log = np.abs(tail_log_argument) < 0.5
    tail_log_difference = np.where(
        use_differenced_log,
        np.log1p(np.where(use_differenced_log, tail_log_argument, 0.0)),
        np.log1p(remaining / numerator_start)
        - np.log1p(remaining / denominator_start),
    )
    tail = (
        remaining * log_start_ratio
        + difference * denominator_tail_log
        + (numerator_start + remaining - 0.5) * tail_log_difference
    )
    shifted_log_ratio = np.log1p(difference / denominator_start)[..., np.newaxis]
    tail_shifted_log_ratio = np.log1p(
        difference / (denominator_start + remaining)
    )[..., np.newaxis]
    powers = _STIRLING_POWERS.reshape((1,) * result.ndim + (-1,))
    coefficients = _STIRLING_COEFFICIENTS.reshape((1,) * result.ndim + (-1,))
    correction = np.sum(
        coefficients
        * (
            np.expm1(-powers * tail_shifted_log_ratio)
            / (denominator_start[..., np.newaxis] + remaining) ** powers
            - np.expm1(-powers * shifted_log_ratio)
            / denominator_start[..., np.newaxis] ** powers
        ),
        axis=-1,
    )
    return result + tail + correction


def _bounded_beta_log_mass(
    k: int, n: int, mean: np.ndarray, concentration: np.ndarray
) -> np.ndarray:
    """Evaluate normalized beta-binomial log masses with work independent of ``n``."""
    if n == 1:
        return np.log(mean) if k else np.log1p(-mean)
    alpha = mean * concentration
    beta = (1.0 - mean) * concentration
    log_choose = _log_combination(n, np.asarray(k))
    if k <= n - k:
        endpoint = _bounded_log_rising_ratio(
            beta, concentration, n, difference=-alpha
        )
        direct_adjustment = _bounded_log_rising_ratio(alpha, beta + n - k, k)
        paired_first = _bounded_log_rising_ratio(
            np.asarray(float(n - k + 1)),
            beta + n - k,
            k,
            difference=np.asarray(1.0) - beta,
        )
        paired_second = _bounded_log_rising_ratio(
            alpha,
            np.asarray(1.0),
            k,
            difference=alpha - 1.0,
        )
    else:
        # Reflect the same identity around n to start from P(n).
        remainder = n - k
        endpoint = _bounded_log_rising_ratio(
            alpha, concentration, n, difference=-beta
        )
        direct_adjustment = _bounded_log_rising_ratio(beta, alpha + k, remainder)
        paired_first = _bounded_log_rising_ratio(
            np.asarray(float(k + 1)),
            alpha + k,
            remainder,
            difference=np.asarray(1.0) - alpha,
        )
        paired_second = _bounded_log_rising_ratio(
            beta,
            np.asarray(1.0),
            remainder,
            difference=beta - 1.0,
        )
    direct = endpoint + log_choose + direct_adjustment
    paired = endpoint + paired_first + paired_second
    direct_condition = np.abs(endpoint) + np.abs(log_choose) + np.abs(direct_adjustment)
    paired_condition = np.abs(endpoint) + np.abs(paired_first) + np.abs(paired_second)
    result = np.where(paired_condition < direct_condition, paired, direct)
    if np.any(~np.isfinite(result)) or np.any(result > 0.0):
        raise FloatingPointError("beta-binomial log mass is outside the stable numeric domain")
    return result


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
        log_cdf = _beta_binomial_tail_logsum(0, k + 1, n, alpha, beta)
        if log_cdf <= _LOG_HALF:
            result = float(np.exp(log_cdf))
        else:
            log_survival = _beta_binomial_tail_logsum(k + 1, n + 1, n, alpha, beta)
            result = float(-np.expm1(log_survival))
    else:
        log_survival = _beta_binomial_tail_logsum(k + 1, n + 1, n, alpha, beta)
        if log_survival <= _LOG_HALF:
            result = float(-np.expm1(log_survival))
        else:
            result = float(np.exp(_beta_binomial_tail_logsum(0, k + 1, n, alpha, beta)))
    if not np.isfinite(result) or not 0.0 <= result <= 1.0:
        raise FloatingPointError("beta-binomial CDF is outside the stable numeric domain")
    return result


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
    cdf_backend: str = "scipy"

    def __post_init__(self) -> None:
        if not isinstance(self.cdf_backend, str) or self.cdf_backend not in {"scipy", "cupy"}:
            raise ValueError("cdf_backend must be either 'scipy' or 'cupy'")
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

    def validated_counts(
        self, ac: object, an: object, *, allow_cdf_boundary: bool = False
    ) -> tuple[np.ndarray, np.ndarray]:
        """Validate count vectors once for every scoring backend and diagnostic caller."""
        denominator = _validated_an(an, self.n_observations)
        count = _validated_ac(
            ac, denominator, self.n_observations, cdf_threshold=allow_cdf_boundary
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
        for observation, n in enumerate(an):
            selected = interior[:, observation]
            if np.any(selected):
                result[selected, observation] = _bounded_beta_log_mass(
                    int(ac[observation]), int(n), mean[selected, observation],
                    self.concentration[selected, observation],
                )
        return result

    def log_prob(self, ac: object, an: object) -> np.ndarray:
        """Integrated log probability mass for each valid observed count."""
        count, denominator = self.validated_counts(ac, an)
        masses = self._draw_log_mass(count, denominator)
        result = logsumexp(masses, axis=0) - np.log(self.n_draws)
        near_one = np.all(masses > -np.log(2.0), axis=0)
        result[near_one] = np.log1p(np.mean(np.expm1(masses[:, near_one]), axis=0))
        if np.any(np.isnan(result) | (result > 0.0)):
            raise FloatingPointError("integrated log mass is outside the stable numeric domain")
        return result

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

    def _cdf_evaluator(self):
        if self.cdf_backend == "scipy":
            def scipy_cdf(count: np.ndarray, denominator: np.ndarray) -> np.ndarray:
                return np.array(
                    [
                        [
                            self._cdf_one(observation, int(row[observation]), int(n))
                            for observation, n in enumerate(denominator)
                        ]
                        for row in count
                    ]
                )

            return scipy_cdf

        from genomeos.validation.predictive_cupy import CuPyCDF

        return CuPyCDF(self.mean_draws, self.concentration)

    def cdf(self, ac: object, an: object) -> np.ndarray:
        """Integrated ``P(Y <= ac)``; ``ac=-1`` is admitted only as the lower CDF boundary."""
        count, denominator = self.validated_counts(ac, an, allow_cdf_boundary=True)
        return self._cdf_evaluator()(count[np.newaxis, :], denominator)[0]

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

    def _count_moments(self, denominator: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return exact mean and variance of each posterior-predictive count mixture."""
        n = denominator[np.newaxis, :].astype(float)
        probability = self.mean_draws
        conditional_mean = n * probability
        if self.concentration is None:
            conditional_variance = n * probability * (1.0 - probability)
        else:
            conditional_variance = (
                n
                * probability
                * (1.0 - probability)
                * (n + self.concentration)
                / (1.0 + self.concentration)
            )
        mean = np.mean(conditional_mean, axis=0)
        variance = np.mean(conditional_variance + conditional_mean**2, axis=0) - mean**2
        return mean, np.maximum(variance, 0.0)

    def quantiles(self, an: object, probabilities: object) -> np.ndarray:
        """Exact left-continuous count quantiles without materializing ``0, ..., AN``."""
        denominator = _validated_an(an, self.n_observations)
        levels = _float_array(probabilities, "probabilities")
        if levels.ndim != 1 or len(levels) == 0:
            raise ValueError("probabilities must be a nonempty one-dimensional array")
        if not np.all(np.isfinite(levels)) or np.any((levels <= 0.0) | (levels > 1.0)):
            raise ValueError("probabilities must be finite and between 0 (exclusive) and 1")

        cdf = self._cdf_evaluator()
        low = np.full((len(levels), self.n_observations), -1, dtype=np.int64)
        high = np.broadcast_to(denominator, low.shape).copy()
        at_one = levels == 1.0
        mean, variance = self._count_moments(denominator)
        bounded_levels = levels[~at_one, np.newaxis]
        # Cantelli: P(Y - E[Y] >= a) <= Var(Y) / (Var(Y) + a**2). Choosing
        # a**2 = Var(Y) * q / (1 - q) makes this an upper bracket for quantile q.
        # The exact CDF check below is still authoritative over the floating calculation.
        cantelli_distance = np.sqrt(
            variance[np.newaxis, :] * bounded_levels / (1.0 - bounded_levels)
        )
        bracket = np.ceil(mean[np.newaxis, :] + cantelli_distance).astype(np.int64)
        high[~at_one] = np.clip(bracket, 0, denominator[np.newaxis, :])
        bracket_cdf = cdf(high, denominator)
        failed_bracket = (~at_one[:, np.newaxis]) & (bracket_cdf < levels[:, np.newaxis])
        high = np.where(failed_bracket, denominator[np.newaxis, :], high)
        upper_support = np.where(np.any(self.mean_draws > 0.0, axis=0), denominator, 0)
        high[at_one] = upper_support
        low[at_one] = upper_support - 1
        while np.any(high - low > 1):
            active = high - low > 1
            midpoint = (low + high) // 2
            values = cdf(np.where(active, midpoint, high), denominator)
            move_high = active & (values >= levels[:, np.newaxis])
            high = np.where(move_high, midpoint, high)
            low = np.where(active & ~move_high, midpoint, low)
        return high


def predictive_diagnostics(
    predictive: CountPredictive, ac: object, an: object, seed: int = SEED
) -> pd.DataFrame:
    """Per-observation proper score, error ingredients, intervals, and randomized PIT.

    ``absolute_error`` can be averaged directly to obtain MAE. Average ``squared_error`` before
    taking its square root to obtain RMSE; averaging per-row square roots would instead be MAE.
    """
    count, denominator = predictive.validated_counts(ac, an)
    log_score = predictive.log_prob(count, denominator)
    observed_frequency = count / denominator
    levels = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
    quantiles = predictive.quantiles(denominator, levels)
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

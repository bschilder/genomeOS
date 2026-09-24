"""Spatial-activity count-mixture preflight (design §§7–8; issues #103, #384).

This module represents the first simulation-only boundary for a spatially varying activity
candidate. The latent activity state is analytically marginalized for prediction: an observed
zero always retains both inactive and ordinary beta-binomial sampling-zero explanations. The
component fields are not interpreted as presence, endemicity, ancestry, migration, or selection.

The public target is the marginal count distribution. Conditional frequency and activity may be
weakly or non-identifiable even when their marginal prediction is stable; downstream preflights
must measure that dependence and may refuse component interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import betaln, gammaln, logsumexp

from genomeos.validation.count_legacy import beta_binomial_cdf

SEED = 42


def _numeric_array(value: object, name: str, *, dimensions: int) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if (
        raw.ndim != dimensions
        or not np.issubdtype(raw.dtype, np.number)
        or np.issubdtype(raw.dtype, np.complexfloating)
        or np.issubdtype(raw.dtype, np.bool_)
    ):
        raise ValueError(f"{name} must be a {dimensions}-dimensional numeric array")
    result = raw.astype(float)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain finite values")
    return result


def _probabilities(value: object, name: str, *, strict: bool, dimensions: int) -> np.ndarray:
    result = _numeric_array(value, name, dimensions=dimensions)
    lower = result > 0.0 if strict else result >= 0.0
    upper = result < 1.0 if strict else result <= 1.0
    if not np.all(lower & upper):
        qualifier = "strictly " if strict else ""
        raise ValueError(f"{name} must be {qualifier}between zero and one")
    return result


def _positive(value: object, name: str, *, dimensions: int) -> np.ndarray:
    result = _numeric_array(value, name, dimensions=dimensions)
    if np.any(result <= 0.0):
        raise ValueError(f"{name} must contain positive values")
    return result


def _counts(
    ac: object,
    an: object,
    observations: int,
    *,
    allow_cdf_boundary: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    alternate_raw = _numeric_array(ac, "ac", dimensions=1)
    total_raw = _numeric_array(an, "an", dimensions=1)
    if alternate_raw.shape != (observations,) or total_raw.shape != (observations,):
        raise ValueError("ac and an must match the predictive observation dimension")
    if np.any(alternate_raw != np.floor(alternate_raw)) or np.any(
        total_raw != np.floor(total_raw)
    ):
        raise ValueError("ac and an must contain integer counts")
    alternate = alternate_raw.astype(np.int64)
    total = total_raw.astype(np.int64)
    if np.any(total <= 0):
        raise ValueError("an must contain positive denominators")
    lower = -1 if allow_cdf_boundary else 0
    if np.any(alternate < lower) or np.any(alternate > total):
        boundary = "minus one and AN" if allow_cdf_boundary else "zero and AN"
        raise ValueError(f"ac must be between {boundary}")
    return alternate, total


@dataclass(frozen=True)
class ActivityComponentDiagnostics:
    """Draw-level component dependence, without a biological interpretation rule."""

    component_correlation: tuple[float | None, ...]
    conditional_mean_sd: tuple[float, ...]
    activity_probability_sd: tuple[float, ...]
    marginal_mean_sd: tuple[float, ...]


@dataclass(frozen=True)
class ActivityCountPredictive:
    """Draw-aligned marginal count distributions for an unobserved activity state."""

    conditional_mean_draws: np.ndarray
    activity_probability_draws: np.ndarray
    concentration_draws: np.ndarray
    cdf_backend: str = "scipy"

    def __post_init__(self) -> None:
        if not isinstance(self.cdf_backend, str) or self.cdf_backend not in {"scipy", "cupy"}:
            raise ValueError("cdf_backend must be either 'scipy' or 'cupy'")
        mean = _probabilities(
            self.conditional_mean_draws,
            "conditional_mean_draws",
            strict=True,
            dimensions=2,
        )
        activity = _probabilities(
            self.activity_probability_draws,
            "activity_probability_draws",
            strict=False,
            dimensions=2,
        )
        concentration = _positive(
            self.concentration_draws,
            "concentration_draws",
            dimensions=2,
        )
        if mean.shape != activity.shape or mean.shape != concentration.shape:
            raise ValueError("all component draws must have the same shape")
        if not mean.shape[0] or not mean.shape[1]:
            raise ValueError("component draws must contain draws and observations")
        for name, value in (
            ("conditional_mean_draws", mean),
            ("activity_probability_draws", activity),
            ("concentration_draws", concentration),
        ):
            frozen = value.copy()
            frozen.setflags(write=False)
            object.__setattr__(self, name, frozen)

    @property
    def n_draws(self) -> int:
        return self.conditional_mean_draws.shape[0]

    @property
    def n_observations(self) -> int:
        return self.conditional_mean_draws.shape[1]

    @property
    def mean_draws(self) -> np.ndarray:
        """Draw-aligned marginal frequency expectations used by shared diagnostics."""
        return self.activity_probability_draws * self.conditional_mean_draws

    def validated_counts(
        self,
        ac: object,
        an: object,
        *,
        allow_cdf_boundary: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Validate count vectors for shared scoring and diagnostic callers."""
        return _counts(
            ac,
            an,
            self.n_observations,
            allow_cdf_boundary=allow_cdf_boundary,
        )

    def log_prob(self, ac: object, an: object) -> np.ndarray:
        """Return posterior-integrated log mass for each observed count."""
        draws = self.n_draws
        alternate, total = self.validated_counts(ac, an)
        count = alternate[np.newaxis, :]
        denominator = total[np.newaxis, :]
        alpha = self.conditional_mean_draws * self.concentration_draws
        beta = (1.0 - self.conditional_mean_draws) * self.concentration_draws
        beta_binomial = (
            gammaln(denominator + 1.0)
            - gammaln(count + 1.0)
            - gammaln(denominator - count + 1.0)
            + betaln(count + alpha, denominator - count + beta)
            - betaln(alpha, beta)
        )
        with np.errstate(divide="ignore"):
            log_activity = np.log(self.activity_probability_draws)
            log_inactive = np.log1p(-self.activity_probability_draws)
        draw_log_mass = np.where(
            count == 0,
            np.logaddexp(log_inactive, log_activity + beta_binomial),
            log_activity + beta_binomial,
        )
        return logsumexp(draw_log_mass, axis=0) - np.log(draws)

    def marginal_mean_frequency(self) -> np.ndarray:
        """Return the posterior mean of the marginal allele-frequency expectation."""
        return np.mean(self.mean_draws, axis=0)

    def _cdf_one(self, observation: int, ac: int, an: int) -> float:
        if ac == -1:
            return 0.0
        if ac == an:
            return 1.0
        component = np.asarray(
            [
                beta_binomial_cdf(ac, an, float(mean), float(concentration))
                for mean, concentration in zip(
                    self.conditional_mean_draws[:, observation],
                    self.concentration_draws[:, observation],
                    strict=True,
                )
            ]
        )
        activity = self.activity_probability_draws[:, observation]
        return float(np.mean((1.0 - activity) + activity * component))

    def _cdf_evaluator(self):
        if self.cdf_backend == "scipy":

            def scipy_cdf(count: np.ndarray, denominator: np.ndarray) -> np.ndarray:
                return np.asarray(
                    [
                        [
                            self._cdf_one(observation, int(row[observation]), int(n))
                            for observation, n in enumerate(denominator)
                        ]
                        for row in count
                    ]
                )

            return scipy_cdf

        from genomeos.validation.predictive_cupy import ActivityCuPyCDF

        return ActivityCuPyCDF(
            self.conditional_mean_draws,
            self.concentration_draws,
            self.activity_probability_draws,
        )

    def cdf(self, ac: object, an: object) -> np.ndarray:
        """Return integrated ``P(Y <= ac)`` with ``ac=-1`` as the lower boundary."""
        count, denominator = self.validated_counts(
            ac,
            an,
            allow_cdf_boundary=True,
        )
        return self._cdf_evaluator()(count[np.newaxis, :], denominator)[0]

    def _count_moments(self, denominator: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n = denominator[np.newaxis, :].astype(float)
        probability = self.conditional_mean_draws
        conditional_mean = n * probability
        conditional_variance = (
            n
            * probability
            * (1.0 - probability)
            * (n + self.concentration_draws)
            / (1.0 + self.concentration_draws)
        )
        active = self.activity_probability_draws
        mean = np.mean(active * conditional_mean, axis=0)
        second_moment = np.mean(
            active * (conditional_variance + conditional_mean**2),
            axis=0,
        )
        return mean, np.maximum(second_moment - mean**2, 0.0)

    def quantiles(self, an: object, probabilities: object) -> np.ndarray:
        """Return exact left-continuous count quantiles by bounded binary search."""
        denominator_raw = _numeric_array(an, "an", dimensions=1)
        if denominator_raw.shape != (self.n_observations,):
            raise ValueError("an must match the predictive observation dimension")
        if np.any(denominator_raw != np.floor(denominator_raw)) or np.any(
            denominator_raw <= 0.0
        ):
            raise ValueError("an must contain positive integer denominators")
        denominator = denominator_raw.astype(np.int64)
        levels = _probabilities(
            probabilities,
            "probabilities",
            strict=True,
            dimensions=1,
        )
        low = np.full((len(levels), self.n_observations), -1, dtype=np.int64)
        upper_support = np.where(
            np.any(self.activity_probability_draws > 0.0, axis=0),
            denominator,
            0,
        )
        cdf = self._cdf_evaluator()
        zero_cdf = cdf(np.zeros((1, self.n_observations), dtype=np.int64), denominator)[0]
        resolved_at_zero = levels[:, np.newaxis] <= zero_cdf[np.newaxis, :]
        mean, variance = self._count_moments(denominator)
        cantelli_distance = np.sqrt(
            variance[np.newaxis, :] * levels[:, np.newaxis] / (1.0 - levels[:, np.newaxis])
        )
        bracket = np.ceil(mean[np.newaxis, :] + cantelli_distance).astype(np.int64)
        high = np.where(
            resolved_at_zero,
            0,
            np.clip(bracket, 0, upper_support[np.newaxis, :]),
        )
        bracket_cdf = cdf(high, denominator)
        high = np.where(
            (~resolved_at_zero) & (bracket_cdf < levels[:, np.newaxis]),
            upper_support[np.newaxis, :],
            high,
        )
        while np.any(high - low > 1):
            active = high - low > 1
            midpoint = (low + high) // 2
            values = cdf(np.where(active, midpoint, high), denominator)
            move_high = active & (values >= levels[:, np.newaxis])
            high = np.where(move_high, midpoint, high)
            low = np.where(active & ~move_high, midpoint, low)
        return high

    def sample_counts(self, an: object, seed: int = SEED) -> np.ndarray:
        """Draw one replicated count for every posterior draw and observation."""
        denominator_raw = _numeric_array(an, "an", dimensions=1)
        if denominator_raw.shape != (self.n_observations,):
            raise ValueError("an must match the predictive observation dimension")
        if np.any(denominator_raw != np.floor(denominator_raw)) or np.any(
            denominator_raw <= 0.0
        ):
            raise ValueError("an must contain positive integer denominators")
        if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
            raise ValueError("seed must be an integer")
        denominator = denominator_raw.astype(np.int64)
        rng = np.random.default_rng(int(seed))
        active = rng.random(self.conditional_mean_draws.shape) < self.activity_probability_draws
        latent_frequency = rng.beta(
            self.conditional_mean_draws * self.concentration_draws,
            (1.0 - self.conditional_mean_draws) * self.concentration_draws,
        )
        counts = rng.binomial(denominator[np.newaxis, :], latent_frequency)
        return np.where(active, counts, 0)

    def component_diagnostics(self) -> ActivityComponentDiagnostics:
        """Report posterior component dependence without declaring identifiability."""
        conditional_sd = np.std(self.conditional_mean_draws, axis=0)
        activity_sd = np.std(self.activity_probability_draws, axis=0)
        marginal_sd = np.std(self.mean_draws, axis=0)
        correlations: list[float | None] = []
        for observation in range(self.n_observations):
            if conditional_sd[observation] == 0.0 or activity_sd[observation] == 0.0:
                correlations.append(None)
            else:
                correlations.append(
                    float(
                        np.corrcoef(
                            self.conditional_mean_draws[:, observation],
                            self.activity_probability_draws[:, observation],
                        )[0, 1]
                    )
                )
        return ActivityComponentDiagnostics(
            component_correlation=tuple(correlations),
            conditional_mean_sd=tuple(float(value) for value in conditional_sd),
            activity_probability_sd=tuple(float(value) for value in activity_sd),
            marginal_mean_sd=tuple(float(value) for value in marginal_sd),
        )


@dataclass(frozen=True)
class ActivitySimulation:
    """Synthetic counts plus latent truth retained only for simulation assessment."""

    ac: tuple[int, ...]
    active: tuple[bool, ...]


def simulate_activity_counts(
    an: object,
    *,
    conditional_mean: object,
    concentration: object,
    activity_probability: object,
    seed: int = SEED,
) -> ActivitySimulation:
    """Draw one beta-binomial activity-mixture replicate with explicit seeded truth."""
    total_raw = _numeric_array(an, "an", dimensions=1)
    if np.any(total_raw != np.floor(total_raw)) or np.any(total_raw <= 0.0):
        raise ValueError("an must contain positive integer denominators")
    total = total_raw.astype(np.int64)
    mean = _probabilities(
        conditional_mean, "conditional_mean", strict=True, dimensions=1
    )
    precision = _positive(concentration, "concentration", dimensions=1)
    activity = _probabilities(
        activity_probability, "activity_probability", strict=False, dimensions=1
    )
    if mean.shape != total.shape or precision.shape != total.shape or activity.shape != total.shape:
        raise ValueError("simulation parameters must have the same shape as an")
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
        raise ValueError("seed must be an integer")

    rng = np.random.default_rng(int(seed))
    active = rng.random(len(total)) < activity
    latent_frequency = rng.beta(mean * precision, (1.0 - mean) * precision)
    alternate = np.where(active, rng.binomial(total, latent_frequency), 0)
    return ActivitySimulation(
        ac=tuple(int(value) for value in alternate),
        active=tuple(bool(value) for value in active),
    )

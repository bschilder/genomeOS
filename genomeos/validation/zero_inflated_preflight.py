"""Nonspatial zero-inflated count preflight (design §§7–8; issue #103).

The canonical HbS surface uses a beta-binomial observation law. Large zero-count surveys can
remain plausible under that law even when its latent mean is high, so this module tests one
narrower question before any spatial mixture is built: does an additional absent component earn
held-out count probability after beta-binomial sampling variation is already present?

An observed zero is never labelled as structural absence. The zero-inflated model assigns it the
sum of the beta-binomial sampling-zero mass and an extra latent absent mass. Fits are scalar,
nonspatial development diagnostics. They do not alter the surface fitter, infer geography, or
make a model eligible for publication.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize
from scipy.special import betaln, expit, gammaln, logit

MODELS = ("beta_binomial", "zero_inflated_beta_binomial")
MIN_ROWS = 8
_PARAMETER_BOUNDS = ((-18.0, 8.0), (-8.0, 16.0))
_ZERO_BOUND = (-18.0, 8.0)
_EQUIVALENT_OBJECTIVE_TOL = 1e-5


@dataclass(frozen=True)
class CountModelFit:
    """One deterministic scalar count-likelihood fit."""

    model: str
    mean: float
    concentration: float
    structural_zero_probability: float
    log_likelihood: float
    n_rows: int
    n_starts: int
    n_successful_starts: int
    n_equivalent_starts: int
    max_equivalent_parameter_relative_span: float


@dataclass(frozen=True)
class FoldComparison:
    """Held-out comparison for one whole-cohort fold."""

    fold: int
    n_train: int
    n_test: int
    n_test_groups: int
    beta_binomial: CountModelFit = field(repr=False)
    zero_inflated_beta_binomial: CountModelFit = field(repr=False)
    mean_log_score_delta: float
    mean_group_log_score_delta: float
    mean_zero_log_score_delta: float
    mean_positive_log_score_delta: float


@dataclass(frozen=True)
class CountModelComparison:
    """Complete cohort-blocked comparison; positive deltas favour zero inflation."""

    folds: tuple[FoldComparison, ...]
    n_folds: int
    n_rows: int
    n_groups: int
    groups_split: int
    folds_improved: int
    mean_log_score_delta: float
    mean_group_log_score_delta: float
    mean_zero_log_score_delta: float
    mean_positive_log_score_delta: float


@dataclass(frozen=True)
class StructuralZeroProfilePoint:
    """Conditional MLE at one fixed extra-zero probability."""

    structural_zero_probability: float
    mean: float
    concentration: float
    log_likelihood: float
    n_starts: int
    n_successful_starts: int


def _finite_integer_vector(value: object, name: str) -> np.ndarray:
    try:
        raw = np.asarray(value)
        objects = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a numeric count vector") from error
    if raw.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if np.issubdtype(raw.dtype, np.bool_) or any(
        isinstance(item, (bool, np.bool_)) for item in objects
    ):
        raise ValueError(f"{name} must contain integer counts, not Boolean values")
    if not np.issubdtype(raw.dtype, np.number) or np.issubdtype(
        raw.dtype, np.complexfloating
    ):
        raise ValueError(f"{name} must be numeric")
    numeric = raw.astype(float)
    if not np.all(np.isfinite(numeric)):
        raise ValueError(f"{name} must contain finite counts")
    if not np.all(numeric == np.floor(numeric)):
        raise ValueError(f"{name} must contain integer counts")
    return numeric.astype(np.int64)


def _counts(ac: object, an: object) -> tuple[np.ndarray, np.ndarray]:
    alternate = _finite_integer_vector(ac, "ac")
    total = _finite_integer_vector(an, "an")
    if alternate.shape != total.shape:
        raise ValueError("ac and an must have the same shape")
    if not len(alternate):
        raise ValueError("ac and an must contain observations")
    if np.any(total <= 0):
        raise ValueError("an must contain positive denominators")
    if np.any(alternate < 0) or np.any(alternate > total):
        raise ValueError("ac must be between zero and AN")
    return alternate, total


def _probability(value: object, name: str, *, strict: bool) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be numeric, not Boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    lower = numeric > 0.0 if strict else numeric >= 0.0
    upper = numeric < 1.0 if strict else numeric <= 1.0
    if not np.isfinite(numeric) or not lower or not upper:
        qualifier = "strictly " if strict else ""
        raise ValueError(f"{name} must be {qualifier}between zero and one")
    return numeric


def _positive(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be numeric, not Boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not np.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return numeric


def count_log_mass(
    ac: object,
    an: object,
    *,
    mean: object,
    concentration: object,
    structural_zero: object,
) -> np.ndarray:
    """Return exact normalized beta-binomial or zero-inflated log masses.

    ``structural_zero=0`` is the ordinary beta-binomial. At zero counts, a positive
    ``structural_zero`` is combined with the beta-binomial sampling-zero mass by log-sum-exp.
    """
    alternate, total = _counts(ac, an)
    probability = _probability(mean, "mean", strict=True)
    precision = _positive(concentration, "concentration")
    absent = _probability(structural_zero, "structural_zero", strict=False)
    alpha = probability * precision
    beta = (1.0 - probability) * precision
    log_mass = (
        gammaln(total + 1.0)
        - gammaln(alternate + 1.0)
        - gammaln(total - alternate + 1.0)
        + betaln(alternate + alpha, total - alternate + beta)
        - betaln(alpha, beta)
    )
    log_absent = -np.inf if absent == 0.0 else float(np.log(absent))
    log_present = -np.inf if absent == 1.0 else float(np.log1p(-absent))
    return np.where(
        alternate == 0,
        np.logaddexp(log_absent, log_present + log_mass),
        log_present + log_mass,
    )


def _model(model: str) -> str:
    if not isinstance(model, str) or model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}")
    return model


def _parameters(raw: np.ndarray, model: str) -> tuple[float, float, float]:
    mean = float(expit(raw[0]))
    concentration = float(np.exp(raw[1]))
    structural_zero = float(expit(raw[2])) if model == "zero_inflated_beta_binomial" else 0.0
    return mean, concentration, structural_zero


def _starts(ac: np.ndarray, an: np.ndarray, model: str) -> tuple[np.ndarray, ...]:
    pooled = float(np.clip(np.sum(ac, dtype=float) / np.sum(an, dtype=float), 1e-6, 1 - 1e-6))
    if model == "beta_binomial":
        return tuple(
            np.array([np.clip(logit(pooled) + offset, -12.0, 6.0), np.log(concentration)])
            for offset in (-1.0, 0.0, 1.0)
            for concentration in (5.0, 50.0, 500.0)
        )
    return tuple(
        np.array(
            [
                np.clip(logit(np.clip(pooled / (1.0 - absent), 1e-6, 0.95)), -12.0, 6.0),
                np.log(concentration),
                logit(absent),
            ]
        )
        for absent in (0.02, 0.15, 0.35, 0.60)
        for concentration in (10.0, 100.0, 1_000.0)
    )


def fit_count_model(ac: object, an: object, *, model: str) -> CountModelFit:
    """Fit one scalar count model with deterministic vectorized multi-start MLE."""
    model = _model(model)
    alternate, total = _counts(ac, an)
    if len(alternate) < MIN_ROWS:
        raise ValueError(f"at least {MIN_ROWS} observations are required")
    if not np.any(alternate == 0) or not np.any(alternate > 0):
        raise ValueError("fit requires both zero and positive observed counts")
    order = np.lexsort((alternate, total))
    alternate, total = alternate[order], total[order]
    starts = _starts(alternate, total, model)
    bounds = _PARAMETER_BOUNDS + ((_ZERO_BOUND,) if model == "zero_inflated_beta_binomial" else ())

    def objective(raw: np.ndarray) -> float:
        mean, concentration, structural_zero = _parameters(raw, model)
        return float(
            -np.sum(
                count_log_mass(
                    alternate,
                    total,
                    mean=mean,
                    concentration=concentration,
                    structural_zero=structural_zero,
                ),
                dtype=np.float64,
            )
        )

    attempts = [
        minimize(
            objective,
            start,
            method="L-BFGS-B",
            bounds=bounds,
            options={"ftol": 1e-13, "gtol": 1e-8, "maxiter": 5_000, "maxls": 100},
        )
        for start in starts
    ]
    successful = [
        attempt
        for attempt in attempts
        if attempt.success and np.isfinite(attempt.fun) and np.all(np.isfinite(attempt.x))
    ]
    if not successful:
        raise RuntimeError(f"{model} optimization did not converge from any start")
    best = min(successful, key=lambda attempt: float(attempt.fun))
    equivalent = [
        attempt
        for attempt in successful
        if float(attempt.fun) <= float(best.fun) + _EQUIVALENT_OBJECTIVE_TOL
    ]
    transformed = np.asarray([_parameters(attempt.x, model) for attempt in equivalent])
    denominator = np.maximum(np.abs(transformed[0]), 1e-12)
    relative_span = float(np.max(np.ptp(transformed, axis=0) / denominator))
    mean, concentration, structural_zero = _parameters(best.x, model)
    return CountModelFit(
        model=model,
        mean=mean,
        concentration=concentration,
        structural_zero_probability=structural_zero,
        log_likelihood=float(-best.fun),
        n_rows=len(alternate),
        n_starts=len(starts),
        n_successful_starts=len(successful),
        n_equivalent_starts=len(equivalent),
        max_equivalent_parameter_relative_span=relative_span,
    )


def _profile_objective(
    raw: np.ndarray,
    alternate: np.ndarray,
    total: np.ndarray,
    fixed_probability: float,
) -> float:
    return float(
        -np.sum(
            count_log_mass(
                alternate,
                total,
                mean=float(expit(raw[0])),
                concentration=float(np.exp(raw[1])),
                structural_zero=fixed_probability,
            ),
            dtype=np.float64,
        )
    )


def profile_structural_zero(
    ac: object,
    an: object,
    *,
    probabilities: object,
) -> tuple[StructuralZeroProfilePoint, ...]:
    """Profile the zero-inflated likelihood without interpreting the curve as a CI."""
    alternate, total = _counts(ac, an)
    if len(alternate) < MIN_ROWS or not np.any(alternate == 0) or not np.any(alternate > 0):
        raise ValueError(f"profile requires at least {MIN_ROWS} rows with zero and positive counts")
    try:
        requested = np.asarray(probabilities, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("probabilities must be a finite one-dimensional vector") from error
    if (
        requested.ndim != 1
        or not len(requested)
        or not np.all(np.isfinite(requested))
        or np.any(requested < 0.0)
        or np.any(requested >= 1.0)
        or len(np.unique(requested)) != len(requested)
    ):
        raise ValueError("probabilities must contain unique finite values in [0, 1)")
    order = np.lexsort((alternate, total))
    alternate, total = alternate[order], total[order]
    starts = _starts(alternate, total, "beta_binomial")
    points: list[StructuralZeroProfilePoint] = []
    for probability in np.sort(requested):
        fixed_probability = float(probability)
        attempts = [
            minimize(
                _profile_objective,
                start,
                args=(alternate, total, fixed_probability),
                method="L-BFGS-B",
                bounds=_PARAMETER_BOUNDS,
                options={"ftol": 1e-13, "gtol": 1e-8, "maxiter": 5_000, "maxls": 100},
            )
            for start in starts
        ]
        successful = [
            attempt
            for attempt in attempts
            if attempt.success and np.isfinite(attempt.fun) and np.all(np.isfinite(attempt.x))
        ]
        if not successful:
            raise RuntimeError(
                f"profile optimization failed at structural_zero={fixed_probability}"
            )
        best = min(successful, key=lambda attempt: float(attempt.fun))
        points.append(
            StructuralZeroProfilePoint(
                structural_zero_probability=fixed_probability,
                mean=float(expit(best.x[0])),
                concentration=float(np.exp(best.x[1])),
                log_likelihood=float(-best.fun),
                n_starts=len(starts),
                n_successful_starts=len(successful),
            )
        )
    return tuple(points)


def _labels(value: object, name: str, expected: int) -> np.ndarray:
    raw = np.asarray(value, dtype=object)
    if raw.ndim != 1 or len(raw) != expected:
        raise ValueError(f"{name} must be a one-dimensional vector matching ac and an")
    if any(not isinstance(item, str) or not item for item in raw):
        raise ValueError(f"{name} must contain nonempty string labels")
    return raw.astype(str)


def _folds(value: object, expected: int) -> np.ndarray:
    raw = _finite_integer_vector(value, "folds")
    if len(raw) != expected:
        raise ValueError("folds must match ac and an")
    if np.any(raw < 0) or len(np.unique(raw)) < 2:
        raise ValueError("folds must contain at least two nonnegative fold labels")
    return raw


def _group_means(values: np.ndarray, groups: np.ndarray) -> np.ndarray:
    return np.asarray([np.mean(values[groups == group]) for group in np.unique(groups)])


def compare_count_models(
    ac: object,
    an: object,
    *,
    groups: object,
    folds: object,
) -> CountModelComparison:
    """Compare scalar beta-binomial arms on whole-cohort held-out folds."""
    alternate, total = _counts(ac, an)
    group_labels = _labels(groups, "groups", len(alternate))
    fold_labels = _folds(folds, len(alternate))
    group_fold_counts = np.asarray(
        [len(np.unique(fold_labels[group_labels == group])) for group in np.unique(group_labels)]
    )
    groups_split = int(np.sum(group_fold_counts > 1))
    if groups_split:
        raise ValueError("cohort groups must not be split between folds")

    comparisons: list[FoldComparison] = []
    all_delta: list[np.ndarray] = []
    all_groups: list[np.ndarray] = []
    all_ac: list[np.ndarray] = []
    for fold in np.unique(fold_labels):
        test = fold_labels == fold
        train = ~test
        baseline = fit_count_model(alternate[train], total[train], model="beta_binomial")
        inflated = fit_count_model(
            alternate[train], total[train], model="zero_inflated_beta_binomial"
        )
        baseline_score = count_log_mass(
            alternate[test],
            total[test],
            mean=baseline.mean,
            concentration=baseline.concentration,
            structural_zero=0.0,
        )
        inflated_score = count_log_mass(
            alternate[test],
            total[test],
            mean=inflated.mean,
            concentration=inflated.concentration,
            structural_zero=inflated.structural_zero_probability,
        )
        delta = inflated_score - baseline_score
        zero = alternate[test] == 0
        if not np.any(zero) or not np.any(~zero):
            raise ValueError("every held-out fold must contain zero and positive counts")
        comparisons.append(
            FoldComparison(
                fold=int(fold),
                n_train=int(np.sum(train)),
                n_test=int(np.sum(test)),
                n_test_groups=len(np.unique(group_labels[test])),
                beta_binomial=baseline,
                zero_inflated_beta_binomial=inflated,
                mean_log_score_delta=float(np.mean(delta)),
                mean_group_log_score_delta=float(
                    np.mean(_group_means(delta, group_labels[test]))
                ),
                mean_zero_log_score_delta=float(np.mean(delta[zero])),
                mean_positive_log_score_delta=float(np.mean(delta[~zero])),
            )
        )
        all_delta.append(delta)
        all_groups.append(group_labels[test])
        all_ac.append(alternate[test])

    delta = np.concatenate(all_delta)
    heldout_groups = np.concatenate(all_groups)
    heldout_ac = np.concatenate(all_ac)
    zero = heldout_ac == 0
    ordered = tuple(sorted(comparisons, key=lambda comparison: comparison.fold))
    return CountModelComparison(
        folds=ordered,
        n_folds=len(ordered),
        n_rows=len(alternate),
        n_groups=len(np.unique(group_labels)),
        groups_split=groups_split,
        folds_improved=int(sum(item.mean_group_log_score_delta > 0.0 for item in ordered)),
        mean_log_score_delta=float(np.mean(delta)),
        mean_group_log_score_delta=float(np.mean(_group_means(delta, heldout_groups))),
        mean_zero_log_score_delta=float(np.mean(delta[zero])),
        mean_positive_log_score_delta=float(np.mean(delta[~zero])),
    )

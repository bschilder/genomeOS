"""Immutable B0H descriptive summaries and boundaries (design §§5,7–8,12; #211)."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from genomeos.surfaces.heterogeneity_types import ReferenceHeterogeneityPrediction
from genomeos.validation.heterogeneity_attempts import FitAttemptSpec
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import DiagnosticCallError
from genomeos.validation.heterogeneity_simulation_types import (
    HeldoutTarget,
    fixed_simulation_truth,
    generation_id,
    simulation_integer,
    simulation_probability,
    simulation_reference_count,
)
from genomeos.validation.predictive import CountPredictive

_PAIRS = ((2, 4), (1, 5), (0, 6))
_COLUMNS = (
    "log_score", "absolute_error", "squared_error", "coverage_50",
    "interval_width_50", "coverage_80", "interval_width_80",
    "coverage_95", "interval_width_95", "randomized_pit",
)


def _tuple(value: object, length: int | None, name: str) -> tuple:
    if not isinstance(value, tuple) or length is not None and len(value) != length:
        raise ValueError(f"{name} must be an immutable tuple of the required length")
    return value


def _record(value, cls):
    if not isinstance(value, cls):
        raise ValueError(f"expected {cls.__name__}")
    return replace(value)


def _backend(value: object) -> None:
    if type(value) is not str or value not in ("scipy", "cupy"):
        raise ValueError("cdf_backend must be scipy or cupy")


def _positive_count(value: object) -> int:
    count = simulation_integer(value, "draw_count")
    if count <= 0:
        raise ValueError("draw_count must be positive")
    return count


def _targets(value: object) -> tuple[HeldoutTarget, ...]:
    targets = tuple(_record(target, HeldoutTarget) for target in _tuple(value, None, "targets"))
    if not targets or len({target.row.record_id for target in targets}) != len(targets):
        raise ValueError("targets must be nonempty with unique row IDs")
    if len({target.row.variant_id for target in targets}) != 1 or any(t.row.an != 20 for t in targets):
        raise ValueError("heldout summaries require one variant and AN20 targets")
    return targets


@dataclass(frozen=True)
class ParameterPosteriorSummary:
    parameter: Literal["mean", "rho"]
    truth: float
    estimate: float
    quantiles: tuple[float, ...]
    draw_count: int

    def __post_init__(self) -> None:
        if type(self.parameter) is not str or self.parameter not in ("mean", "rho"):
            raise ValueError("parameter must be mean or rho")
        truth = simulation_probability(self.truth, "truth")
        estimate = simulation_probability(self.estimate, "estimate")
        quantiles = tuple(
            simulation_probability(value, "quantile")
            for value in _tuple(self.quantiles, 7, "quantiles")
        )
        if not 0.0 < estimate < 1.0 or any(not 0.0 < q < 1.0 for q in quantiles):
            raise ValueError("accepted posterior summaries must be interior")
        if tuple(sorted(quantiles)) != quantiles:
            raise ValueError("quantiles must be nondecreasing")
        if self.parameter == "rho" and truth == 1.0:
            raise ValueError("rho truth must be below one")
        object.__setattr__(self, "truth", truth)
        object.__setattr__(self, "estimate", estimate)
        object.__setattr__(self, "quantiles", quantiles)
        object.__setattr__(self, "draw_count", _positive_count(self.draw_count))

    @property
    def absolute_error(self) -> float:
        return abs(self.estimate - self.truth)

    @property
    def squared_error(self) -> float:
        return (self.estimate - self.truth) ** 2

    @property
    def coverage(self) -> tuple[bool, bool, bool]:
        return tuple(self.quantiles[lo] <= self.truth <= self.quantiles[hi] for lo, hi in _PAIRS)

    @property
    def interval_width(self) -> tuple[float, float, float]:
        return tuple(self.quantiles[hi] - self.quantiles[lo] for lo, hi in _PAIRS)


@dataclass(frozen=True)
class HeldoutPredictiveSummary:
    target: HeldoutTarget
    log_score: float
    absolute_error: float
    squared_error: float
    coverage: tuple[bool, bool, bool]
    interval_width: tuple[float, float, float]
    randomized_pit: float

    def __post_init__(self) -> None:
        target = _record(self.target, HeldoutTarget)
        if target.row.an != 20:
            raise ValueError("summary target must have AN20")
        if type(self.log_score) not in (float, np.float16, np.float32, np.float64):
            raise ValueError("log_score must be a supported floating scalar")
        score = float(self.log_score)
        if math.isnan(score) or score > 0.0:
            raise ValueError("log_score must be nonpositive, including negative infinity")
        coverage = _tuple(self.coverage, 3, "coverage")
        if any(type(value) not in (bool, np.bool_) for value in coverage):
            raise ValueError("coverage must contain Boolean scalars")
        coverage = tuple(bool(value) for value in coverage)
        widths = tuple(
            simulation_probability(value, "interval_width")
            for value in _tuple(self.interval_width, 3, "interval_width")
        )
        if coverage != tuple(sorted(coverage)) or widths != tuple(sorted(widths)):
            raise ValueError("coverage and widths must be nested in 50/80/95 order")
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "log_score", score)
        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "interval_width", widths)
        for name in ("absolute_error", "squared_error", "randomized_pit"):
            object.__setattr__(self, name, simulation_probability(getattr(self, name), name))


def require_summary_prediction(
    prediction: ReferenceHeterogeneityPrediction, *,
    targets: tuple[HeldoutTarget, ...], cdf_backend: Literal["scipy", "cupy"],
    draw_count: int,
) -> None:
    """Check exact row order, backend and array representation before scoring."""
    targets = _targets(targets)
    _backend(cdf_backend)
    count = _positive_count(draw_count)
    if not isinstance(prediction, ReferenceHeterogeneityPrediction):
        raise ValueError("predictor must return ReferenceHeterogeneityPrediction")
    if not isinstance(prediction.marginal_predictive, CountPredictive):
        raise ValueError("prediction must contain CountPredictive")
    if (
        type(prediction.observation_ids) is not tuple
        or prediction.observation_ids != tuple(target.row.record_id for target in targets)
        or type(prediction.unavailable_ids) is not tuple
        or prediction.unavailable_ids != ()
    ):
        raise ValueError("prediction IDs must match original target order exactly")
    marginal = prediction.marginal_predictive
    if type(marginal.cdf_backend) is not str or marginal.cdf_backend != cdf_backend:
        raise ValueError("returned backend does not match explicit backend")
    for array in (marginal.mean_draws, marginal.concentration):
        if (
            not isinstance(array, np.ndarray) or array.dtype != np.dtype("float64")
            or array.shape != (count, len(targets)) or not np.all(np.isfinite(array))
            or array.flags.writeable
        ):
            raise ValueError("prediction arrays must be immutable finite float64 with exact shape")
    if np.any((marginal.mean_draws <= 0.) | (marginal.mean_draws >= 1.)):
        raise ValueError("B0H predictive mean draws must be interior")
    if np.any(marginal.concentration <= 0.):
        raise ValueError("B0H predictive concentration must be positive")


def predictive_summary_rows(
    frame: pd.DataFrame, *, targets: tuple[HeldoutTarget, ...],
) -> tuple[HeldoutPredictiveSummary, ...]:
    """Validate public diagnostic output without casting or reordering defects."""
    targets = _targets(targets)
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != _COLUMNS:
        raise ValueError("diagnostics must return the exact public DataFrame columns")
    if type(frame.index) is not pd.RangeIndex or not frame.index.equals(pd.RangeIndex(len(targets))):
        raise ValueError("diagnostics must retain canonical positional row order")
    for name in _COLUMNS:
        dtype = np.dtype("bool") if name.startswith("coverage_") else np.dtype("float64")
        if frame[name].dtype != dtype:
            raise ValueError(f"diagnostic {name} has an unexpected dtype")
    return tuple(
        HeldoutPredictiveSummary(
            target, frame.at[index, "log_score"], frame.at[index, "absolute_error"],
            frame.at[index, "squared_error"],
            tuple(frame.at[index, f"coverage_{level}"] for level in (50, 80, 95)),
            tuple(frame.at[index, f"interval_width_{level}"] for level in (50, 80, 95)),
            frame.at[index, "randomized_pit"],
        )
        for index, target in enumerate(targets)
    )


@dataclass(frozen=True)
class PredictiveSummaryEvidence:
    seed: DiagnosticSeedIdentity
    seed_words: tuple[int, int, int, int]
    seed_uint128: int
    cdf_backend: Literal["scipy", "cupy"]
    draw_count: int
    targets: tuple[HeldoutTarget, ...]
    status: Literal["complete", "prediction_failed", "diagnostics_failed"]
    prediction: ReferenceHeterogeneityPrediction | None
    rows: tuple[HeldoutPredictiveSummary, ...]
    error: DiagnosticCallError | None

    def __post_init__(self) -> None:
        seed = _record(self.seed, DiagnosticSeedIdentity)
        if seed.purpose_id != 7 or seed.spawn_key != ():
            raise ValueError("predictive evidence requires purpose7 with an empty spawn key")
        words = tuple(
            simulation_integer(value, "seed word")
            for value in _tuple(self.seed_words, 4, "seed_words")
        )
        scalar = simulation_integer(self.seed_uint128, "seed_uint128")
        if words != seed.scalar_words or scalar != seed.scalar_uint128:
            raise ValueError("exact seed words and scalar must match their identity")
        _backend(self.cdf_backend)
        count = _positive_count(self.draw_count)
        targets = _targets(self.targets)
        kinds = ("shared_cluster0", "fresh_cluster") if seed.case.study_id == 2 else ("fresh_population",)
        if tuple(target.kind for target in targets) != kinds:
            raise ValueError("target kinds/order do not match the study")
        for target in targets:
            expected = simulation_reference_count(
                generation_id(seed.case), "heldout", target.kind, target.row.ac, 20
            )
            if target.row != expected:
                raise ValueError("target row/variant identity does not match the case")
        rows = tuple(_record(row, HeldoutPredictiveSummary) for row in _tuple(self.rows, None, "rows"))
        if type(self.status) is not str or self.status not in (
            "complete", "prediction_failed", "diagnostics_failed"
        ):
            raise ValueError("unknown predictive evidence status")
        if self.status == "prediction_failed":
            if self.prediction is not None:
                raise ValueError("failed prediction cannot retain a returned object")
        else:
            require_summary_prediction(
                self.prediction, targets=targets, cdf_backend=self.cdf_backend, draw_count=count
            )
        if self.status == "complete":
            if self.error is not None or tuple(row.target for row in rows) != targets:
                raise ValueError("complete diagnostics must contain all aligned rows and no error")
        else:
            _record(self.error, DiagnosticCallError)
            if rows:
                raise ValueError("failed predictive calls cannot carry partial successful rows")
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "seed_words", words)
        object.__setattr__(self, "seed_uint128", scalar)
        object.__setattr__(self, "draw_count", count)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "rows", rows)


@dataclass(frozen=True)
class HeterogeneityFitSummary:
    spec: FitAttemptSpec
    variant_id: str
    parameters: tuple[ParameterPosteriorSummary, ParameterPosteriorSummary]
    predictive: PredictiveSummaryEvidence

    def __post_init__(self) -> None:
        spec = _record(self.spec, FitAttemptSpec)
        parameters = tuple(
            _record(item, ParameterPosteriorSummary)
            for item in _tuple(self.parameters, 2, "parameters")
        )
        if tuple(item.parameter for item in parameters) != ("mean", "rho"):
            raise ValueError("parameter summaries must be ordered mean then rho")
        predictive = _record(self.predictive, PredictiveSummaryEvidence)
        if predictive.seed.case != spec.case or predictive.seed.attempt_id != spec.attempt_id:
            raise ValueError("predictive seed must bind the accepted attempt")
        count = spec.config.chains * spec.config.draws
        if predictive.draw_count != count or any(item.draw_count != count for item in parameters):
            raise ValueError("every summary must use all accepted chain/draw entries")
        expected_variant = predictive.targets[0].row.variant_id
        if type(self.variant_id) is not str or self.variant_id != expected_variant:
            raise ValueError("summary variant must match case-bound heldouts")
        truth = fixed_simulation_truth(spec.case)
        actual = tuple(item.truth for item in parameters)
        if truth is not None and actual != (truth.mean, truth.rho):
            raise ValueError("parameter truths must match the fixed study")
        if spec.case.study_id == 0 and not all(0. < value < 1. for value in actual):
            raise ValueError("prior-study truths must be interior")
        object.__setattr__(self, "spec", spec)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "predictive", predictive)

    @property
    def h_ess_status(self) -> Literal["not_computed"]:
        return "not_computed"

    @property
    def h_mcse_status(self) -> Literal["not_computed"]:
        return "not_computed"

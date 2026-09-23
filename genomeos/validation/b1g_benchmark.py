"""Nested fixed-grid B1G count benchmark (design §§4–8, 12; #331).

Scientific objective
    Select compact positive spatial bases using outer-training evidence only, then measure their
    count prediction on dependency-aware held-out HbS regions.
Measurable output
    A complete candidate ledger per outer fold, one terminal status per planned fold, and the
    ordinary cohort/region macro count diagnostics used by the B0, B1, and B2 comparisons.
Engineering interface
    :func:`plan_b1g_benchmark`, :func:`evaluate_b1g_fold`, and
    :func:`evaluate_b1g_benchmark` are pure in-memory boundaries. Fitting and prediction are
    injectable only as controlled test/runner seams.
Assumptions and refusals
    The nine-cell grid, buffered splits, likelihood, and tie break are fixed. Every inner fold must
    complete with exact prediction coverage. Failed candidates and outer folds remain explicit.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

import pandas as pd

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_basis import B1GBasisConfig
from genomeos.validation.b1g_fit import B1GFit, B1GPrediction, fit_b1g, predict_b1g
from genomeos.validation.benchmark import (
    BenchmarkFoldStatus,
    cohort_macro_mean_log_score,
    summarize_benchmark,
    validate_allele_observations,
    validate_predictive_diagnostics,
)
from genomeos.validation.local_count_selection import validate_local_count_assignments
from genomeos.validation.predictive import predictive_diagnostics
from genomeos.validation.splits import BenchmarkSplit, build_buffered_splits

SEED = 42
_RADII_KM = (500.0, 1000.0, 2000.0)
_BASIS_COUNTS = (8, 16, 32)
_DIAGNOSTIC_COLUMNS = (
    "log_score",
    "absolute_error",
    "squared_error",
    "coverage_50",
    "interval_width_50",
    "coverage_80",
    "interval_width_80",
    "coverage_95",
    "interval_width_95",
    "randomized_pit",
)
PREDICTION_COLUMNS = (
    "split_id",
    "block_id",
    "source_record_id",
    "variant_id",
    "region_id",
    "variant_group",
    "cohort_id",
    "observed_ac",
    "observed_an",
    "basis_radius_km",
    "basis_count",
    "fit_seed",
    "predictive_seed",
) + _DIAGNOSTIC_COLUMNS

FitFunction = Callable[..., B1GFit]
PredictFunction = Callable[..., B1GPrediction]
FoldState = Literal["completed", "failed", "infeasible"]


@dataclass(frozen=True)
class B1GBenchmarkConfig:
    """Frozen sampling choices around the preregistered nine-cell candidate grid."""

    fit_config: FitConfig
    query_chunk_size: int = 1024
    cdf_backend: str = "scipy"

    def __post_init__(self) -> None:
        if not isinstance(self.fit_config, FitConfig):
            raise TypeError("fit_config must be a FitConfig")
        if self.fit_config.likelihood != "beta_binomial" or self.fit_config.nugget:
            raise ValueError("B1G requires beta_binomial likelihood without a nugget")
        if isinstance(self.query_chunk_size, bool) or not isinstance(self.query_chunk_size, int):
            raise ValueError("query_chunk_size must be a positive integer")
        if self.query_chunk_size <= 0:
            raise ValueError("query_chunk_size must be a positive integer")
        if self.cdf_backend not in {"scipy", "cupy"}:
            raise ValueError("cdf_backend must be either 'scipy' or 'cupy'")

    @property
    def candidate_configs(self) -> tuple[B1GBasisConfig, ...]:
        return tuple(
            B1GBasisConfig(radius, count, self.query_chunk_size)
            for radius in _RADII_KM
            for count in _BASIS_COUNTS
        )


@dataclass(frozen=True)
class B1GInnerFoldRecord:
    """One terminal candidate fit inside an outer-training set."""

    split_id: str
    status: FoldState
    expected_test_ids: tuple[str, ...]
    fit_seed: int
    predictive_seed: int
    sampler_diagnostics: SamplerDiagnostics | None
    failure_reason: str | None


@dataclass(frozen=True)
class B1GCandidateScore:
    """Complete inner-fold evidence for one fixed candidate."""

    radius_km: float
    basis_count: int
    requested_count: int
    scored_count: int
    mean_log_score: float | None
    completed_inner_fold_count: int
    failed_inner_fold_count: int
    failure_reasons: tuple[str, ...]
    eligible: bool
    inner_folds: tuple[B1GInnerFoldRecord, ...]


@dataclass(frozen=True)
class B1GSelection:
    """Winning training-only configuration and the complete candidate ledger."""

    selected_config: B1GBasisConfig
    candidate_scores: tuple[B1GCandidateScore, ...]


class B1GSelectionError(ValueError):
    """No fixed-grid candidate completed every inner fold."""

    def __init__(self, message: str, scores: tuple[B1GCandidateScore, ...]) -> None:
        self.scores = scores
        super().__init__(message)


@dataclass(frozen=True)
class B1GBenchmarkPlan:
    observations: pd.DataFrame
    assignments: pd.DataFrame
    dependencies: tuple[tuple[str, str], ...]
    splits: tuple[BenchmarkSplit, ...]
    buffer_km: float
    data_version: str
    config: B1GBenchmarkConfig
    seed: int


@dataclass(frozen=True)
class B1GFoldStatus:
    split_id: str
    status: FoldState
    expected_test_ids: tuple[str, ...]
    selected_radius_km: float | None
    selected_basis_count: int | None
    failure_reason: str | None


@dataclass(frozen=True)
class B1GFoldResult:
    status: B1GFoldStatus
    predictions: pd.DataFrame
    candidate_scores: tuple[B1GCandidateScore, ...]
    sampler_diagnostics: SamplerDiagnostics | None


@dataclass(frozen=True)
class B1GBenchmarkResult:
    predictions: pd.DataFrame
    fold_status: tuple[B1GFoldStatus, ...]
    candidate_scores: pd.DataFrame
    splits: tuple[BenchmarkSplit, ...]
    summary: dict[str, object]


def derive_b1g_seed(seed: int, *parts: object) -> int:
    """Derive a stable uint32 seed from semantic fold and candidate identities."""
    payload = "\0".join((str(seed), *(str(part) for part in parts)))
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:4], "big")


def plan_b1g_benchmark(
    observations: pd.DataFrame,
    block_assignments: pd.DataFrame,
    dependencies: Sequence[tuple[str, str]],
    *,
    buffer_km: float,
    data_version: str,
    config: B1GBenchmarkConfig,
    seed: int = SEED,
) -> B1GBenchmarkPlan:
    """Validate one modern variant and freeze every outer fold before any fit."""
    if not isinstance(config, B1GBenchmarkConfig):
        raise TypeError("config must be a B1GBenchmarkConfig")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    validated = validate_allele_observations(observations)
    variants = tuple(sorted(validated["variant_id"].unique()))
    if len(variants) != 1 or variants[0].startswith("phenotype:"):
        raise ValueError("B1G benchmark requires one non-phenotype variant")
    if ((validated["date_lower"] != 0) | (validated["date_upper"] != 0)).any():
        raise ValueError("B1G benchmark requires modern observations")
    assignments = validate_local_count_assignments(validated, block_assignments)
    splits = build_buffered_splits(
        validated,
        assignments.loc[:, ["source_record_id", "block_id"]],
        dependencies,
        buffer_km=buffer_km,
        data_version=data_version,
    )
    return B1GBenchmarkPlan(
        observations=validated.sort_values("source_record_id").reset_index(drop=True),
        assignments=assignments,
        dependencies=tuple(dependencies),
        splits=splits,
        buffer_km=float(buffer_km),
        data_version=data_version,
        config=config,
        seed=seed,
    )


def _empty_predictions() -> pd.DataFrame:
    return pd.DataFrame(columns=PREDICTION_COLUMNS)


def _prediction_frame(
    testing: pd.DataFrame,
    assignments: pd.DataFrame,
    split: BenchmarkSplit,
    prediction: B1GPrediction,
    *,
    basis_config: B1GBasisConfig,
    fit_seed: int,
    predictive_seed: int,
) -> pd.DataFrame:
    ordered, identity = _prediction_identity(
        testing,
        assignments,
        split,
        prediction,
        basis_config=basis_config,
        fit_seed=fit_seed,
        predictive_seed=predictive_seed,
    )
    diagnostics = validate_predictive_diagnostics(
        predictive_diagnostics(
            prediction.predictive,
            ordered["ac"].to_numpy(),
            ordered["an"].to_numpy(),
            seed=predictive_seed,
        )
    )
    return pd.concat([identity, diagnostics], axis=1).loc[:, PREDICTION_COLUMNS]


def _prediction_identity(
    testing: pd.DataFrame,
    assignments: pd.DataFrame,
    split: BenchmarkSplit,
    prediction: B1GPrediction,
    *,
    basis_config: B1GBasisConfig,
    fit_seed: int,
    predictive_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    expected = tuple(sorted(testing["source_record_id"]))
    if prediction.observation_ids != expected:
        raise ValueError("B1G prediction identities do not exactly cover the held-out fold")
    ordered = testing.sort_values("source_record_id").reset_index(drop=True)
    identity = ordered.loc[
        :, ["source_record_id", "variant_id", "cohort_id", "ac", "an"]
    ].merge(
        assignments.loc[:, ["source_record_id", "region_id", "variant_group"]],
        on="source_record_id",
        how="left",
        validate="one_to_one",
    )
    identity = identity.rename(columns={"ac": "observed_ac", "an": "observed_an"})
    identity.insert(0, "split_id", split.split_id)
    identity.insert(1, "block_id", split.block_id)
    identity["basis_radius_km"] = basis_config.radius_km
    identity["basis_count"] = basis_config.basis_count
    identity["fit_seed"] = fit_seed
    identity["predictive_seed"] = predictive_seed
    return ordered, identity


def _prediction_log_score_frame(
    testing: pd.DataFrame,
    assignments: pd.DataFrame,
    split: BenchmarkSplit,
    prediction: B1GPrediction,
    *,
    basis_config: B1GBasisConfig,
    fit_seed: int,
    predictive_seed: int,
) -> pd.DataFrame:
    ordered, identity = _prediction_identity(
        testing,
        assignments,
        split,
        prediction,
        basis_config=basis_config,
        fit_seed=fit_seed,
        predictive_seed=predictive_seed,
    )
    count, denominator = prediction.predictive.validated_counts(
        ordered["ac"].to_numpy(),
        ordered["an"].to_numpy(),
    )
    columns = ["split_id", "source_record_id", "region_id", "variant_group", "cohort_id"]
    frame = identity.loc[:, columns].copy()
    frame["log_score"] = prediction.predictive.log_prob(count, denominator)
    cohort_macro_mean_log_score(frame)
    return frame


def _fit_and_score(
    training: pd.DataFrame,
    testing: pd.DataFrame,
    assignments: pd.DataFrame,
    split: BenchmarkSplit,
    *,
    basis_config: B1GBasisConfig,
    benchmark_config: B1GBenchmarkConfig,
    seed: int,
    fit_function: FitFunction,
    predict_function: PredictFunction,
    diagnostic_scope: Literal["full", "log_score"] = "full",
) -> tuple[pd.DataFrame, SamplerDiagnostics, int, int]:
    fit_seed = derive_b1g_seed(
        seed, split.split_id, basis_config.radius_km, basis_config.basis_count, "fit"
    )
    predictive_seed = derive_b1g_seed(
        seed, split.split_id, basis_config.radius_km, basis_config.basis_count, "predictive"
    )
    fit = fit_function(
        training,
        basis_config=basis_config,
        fit_config=replace(benchmark_config.fit_config, seed=fit_seed),
    )
    prediction = predict_function(
        fit,
        testing,
        seed=predictive_seed,
        cdf_backend=benchmark_config.cdf_backend,
    )
    if diagnostic_scope == "full":
        frame_function = _prediction_frame
    elif diagnostic_scope == "log_score":
        frame_function = _prediction_log_score_frame
    else:
        raise ValueError("diagnostic_scope must be 'full' or 'log_score'")
    frame = frame_function(
        testing,
        assignments,
        split,
        prediction,
        basis_config=basis_config,
        fit_seed=fit_seed,
        predictive_seed=predictive_seed,
    )
    return frame, fit.sampler_diagnostics, fit_seed, predictive_seed


def _select_candidate(
    training: pd.DataFrame,
    assignments: pd.DataFrame,
    dependencies: tuple[tuple[str, str], ...],
    *,
    buffer_km: float,
    data_version: str,
    config: B1GBenchmarkConfig,
    seed: int,
    fit_function: FitFunction,
    predict_function: PredictFunction,
) -> B1GSelection:
    try:
        inner_splits = build_buffered_splits(
            training,
            assignments.loc[:, ["source_record_id", "block_id"]],
            dependencies,
            buffer_km=buffer_km,
            data_version=data_version,
        )
    except ValueError as error:
        raise B1GSelectionError(f"inner split planning failed: {error}", ()) from error
    by_id = training.set_index("source_record_id", drop=False)
    scores: list[B1GCandidateScore] = []
    for basis_config in config.candidate_configs:
        frames = []
        failures = []
        inner_records: list[B1GInnerFoldRecord] = []
        for split in inner_splits:
            fit_seed = derive_b1g_seed(
                seed, split.split_id, basis_config.radius_km, basis_config.basis_count, "fit"
            )
            predictive_seed = derive_b1g_seed(
                seed,
                split.split_id,
                basis_config.radius_km,
                basis_config.basis_count,
                "predictive",
            )
            try:
                if not split.train_ids:
                    raise ValueError("no training observations")
                (
                    frame,
                    diagnostics,
                    returned_fit_seed,
                    returned_predictive_seed,
                ) = _fit_and_score(
                    by_id.loc[list(split.train_ids)].reset_index(drop=True),
                    by_id.loc[list(split.test_ids)].reset_index(drop=True),
                    assignments,
                    split,
                    basis_config=basis_config,
                    benchmark_config=config,
                    seed=seed,
                    fit_function=fit_function,
                    predict_function=predict_function,
                    diagnostic_scope="log_score",
                )
                if (returned_fit_seed, returned_predictive_seed) != (fit_seed, predictive_seed):
                    raise RuntimeError("derived inner seeds changed during fit")
                frames.append(frame)
                inner_records.append(
                    B1GInnerFoldRecord(
                        split.split_id,
                        "completed",
                        split.test_ids,
                        fit_seed,
                        predictive_seed,
                        diagnostics,
                        None,
                    )
                )
            except Exception as error:
                reason = f"{split.split_id}: {type(error).__name__}: {error}"
                failures.append(reason)
                diagnostics = getattr(error, "diagnostics", None)
                if not isinstance(diagnostics, SamplerDiagnostics):
                    diagnostics = None
                inner_records.append(
                    B1GInnerFoldRecord(
                        split.split_id,
                        "failed",
                        split.test_ids,
                        fit_seed,
                        predictive_seed,
                        diagnostics,
                        reason,
                    )
                )
        predictions = pd.concat(frames, ignore_index=True) if frames else _empty_predictions()
        mean_log_score = cohort_macro_mean_log_score(predictions) if frames else None
        requested = sum(len(split.test_ids) for split in inner_splits)
        scored = len(predictions)
        eligible = not failures and scored == requested and mean_log_score is not None
        scores.append(
            B1GCandidateScore(
                radius_km=basis_config.radius_km,
                basis_count=basis_config.basis_count,
                requested_count=requested,
                scored_count=scored,
                mean_log_score=mean_log_score,
                completed_inner_fold_count=len(inner_splits) - len(failures),
                failed_inner_fold_count=len(failures),
                failure_reasons=tuple(failures),
                eligible=eligible,
                inner_folds=tuple(inner_records),
            )
        )
    score_tuple = tuple(scores)
    eligible = tuple(score for score in score_tuple if score.eligible)
    if not eligible:
        raise B1GSelectionError("no B1G candidate completed every inner fold", score_tuple)
    selected = max(
        eligible,
        key=lambda score: (
            float(score.mean_log_score),
            -score.basis_count,
            -score.radius_km,
        ),
    )
    return B1GSelection(
        B1GBasisConfig(selected.radius_km, selected.basis_count, config.query_chunk_size),
        score_tuple,
    )


def evaluate_b1g_fold(
    plan: B1GBenchmarkPlan,
    split: BenchmarkSplit,
    *,
    fit_function: FitFunction = fit_b1g,
    predict_function: PredictFunction = predict_b1g,
) -> B1GFoldResult:
    """Select on inner folds, then evaluate one untouched outer fold."""
    if not isinstance(plan, B1GBenchmarkPlan) or split not in plan.splits:
        raise ValueError("split must belong to plan")
    if not split.train_ids:
        reason = "outer split has no training observations after leakage exclusions"
        status = B1GFoldStatus(split.split_id, "infeasible", split.test_ids, None, None, reason)
        return B1GFoldResult(status, _empty_predictions(), (), None)
    by_id = plan.observations.set_index("source_record_id", drop=False)
    training_ids = set(split.train_ids)
    training = by_id.loc[list(split.train_ids)].reset_index(drop=True)
    testing = by_id.loc[list(split.test_ids)].reset_index(drop=True)
    inner_assignments = plan.assignments[
        plan.assignments["source_record_id"].isin(training_ids)
    ].reset_index(drop=True)
    inner_dependencies = tuple(
        pair for pair in plan.dependencies if pair[0] in training_ids and pair[1] in training_ids
    )
    scores: tuple[B1GCandidateScore, ...] = ()
    selected: B1GBasisConfig | None = None
    try:
        selection = _select_candidate(
            training,
            inner_assignments,
            inner_dependencies,
            buffer_km=plan.buffer_km,
            data_version=f"{plan.data_version}:outer:{split.split_id}",
            config=plan.config,
            seed=derive_b1g_seed(plan.seed, split.split_id, "selection"),
            fit_function=fit_function,
            predict_function=predict_function,
        )
        scores = selection.candidate_scores
        selected = selection.selected_config
        predictions, diagnostics, _, _ = _fit_and_score(
            training,
            testing,
            plan.assignments,
            split,
            basis_config=selected,
            benchmark_config=plan.config,
            seed=plan.seed,
            fit_function=fit_function,
            predict_function=predict_function,
        )
        status = B1GFoldStatus(
            split.split_id,
            "completed",
            split.test_ids,
            selected.radius_km,
            selected.basis_count,
            None,
        )
        return B1GFoldResult(status, predictions, scores, diagnostics)
    except B1GSelectionError as error:
        reason = str(error)
        status = B1GFoldStatus(split.split_id, "infeasible", split.test_ids, None, None, reason)
        return B1GFoldResult(status, _empty_predictions(), error.scores, None)
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        status = B1GFoldStatus(
            split.split_id,
            "failed",
            split.test_ids,
            None if selected is None else selected.radius_km,
            None if selected is None else selected.basis_count,
            reason,
        )
        return B1GFoldResult(status, _empty_predictions(), scores, None)


def finalize_b1g_benchmark(
    plan: B1GBenchmarkPlan, folds: Sequence[B1GFoldResult]
) -> B1GBenchmarkResult:
    """Validate one terminal result per frozen outer split and build the macro report."""
    if not isinstance(plan, B1GBenchmarkPlan):
        raise TypeError("plan must be a B1GBenchmarkPlan")
    by_id = {fold.status.split_id: fold for fold in folds}
    expected_ids = tuple(split.split_id for split in plan.splits)
    if len(by_id) != len(folds) or set(by_id) != set(expected_ids):
        raise ValueError("folds must contain exactly one result for every planned split")
    ordered = tuple(by_id[split_id] for split_id in expected_ids)
    statuses = []
    frames = []
    for split, fold in zip(plan.splits, ordered, strict=True):
        if fold.status.expected_test_ids != split.test_ids:
            raise ValueError("fold expected_test_ids contradict the frozen split")
        if fold.status.status == "completed":
            frames.append(fold.predictions)
            statuses.append(BenchmarkFoldStatus(split.split_id, "completed", split.test_ids, None))
        else:
            statuses.append(
                BenchmarkFoldStatus(
                    split.split_id,
                    fold.status.status,
                    split.test_ids,
                    fold.status.failure_reason,
                )
            )
    predictions = pd.concat(frames, ignore_index=True) if frames else _empty_predictions()
    summary = summarize_benchmark(predictions, statuses, expected_ids)
    candidate_records = [
        {"split_id": fold.status.split_id, **score.__dict__}
        for fold in ordered
        for score in fold.candidate_scores
    ]
    return B1GBenchmarkResult(
        predictions=predictions.sort_values(["split_id", "source_record_id"]).reset_index(drop=True),
        fold_status=tuple(fold.status for fold in ordered),
        candidate_scores=pd.DataFrame.from_records(candidate_records),
        splits=plan.splits,
        summary=summary,
    )


def evaluate_b1g_benchmark(
    plan: B1GBenchmarkPlan,
    *,
    fit_function: FitFunction = fit_b1g,
    predict_function: PredictFunction = predict_b1g,
) -> B1GBenchmarkResult:
    """Evaluate every frozen outer fold and retain all candidate and fold outcomes."""
    if not isinstance(plan, B1GBenchmarkPlan):
        raise TypeError("plan must be a B1GBenchmarkPlan")
    folds = tuple(
        evaluate_b1g_fold(
            plan,
            split,
            fit_function=fit_function,
            predict_function=predict_function,
        )
        for split in plan.splits
    )
    return finalize_b1g_benchmark(plan, folds)

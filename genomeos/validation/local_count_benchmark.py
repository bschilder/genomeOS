"""Training-only B1 local-count benchmark (design §§4–8, 12; #307).

Scientific objective
    Compare a compact-support local count smoother with B0 and the frozen B2 arm without letting
    outer held-out counts choose the smoothing scale.
Acceptance evidence
    Every outer query appears in a support ledger. Predictive metrics use the shared exact count
    scorer only for emitted rows, while requested, emitted, and excluded counts remain explicit.
Engineering interface
    Planning, bandwidth selection, fold evaluation, and finalization are pure in-memory functions.
    File I/O and artifact provenance belong to the CLI adapter.
Assumptions and refusals
    Candidate bandwidths and the minimum inner emission fraction are prespecified. Inner splits
    reuse the outer training rows, blocks, dependency edges, footprint buffer, and count score.
    A candidate with any failed inner fold, too little emission, or no score is ineligible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral
from typing import Literal

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import (
    BenchmarkFoldStatus,
    summarize_benchmark,
    validate_allele_observations,
    validate_predictive_diagnostics,
)
from genomeos.validation.local_count import LocalCountSupport, fit_local_count
from genomeos.validation.local_count_evidence import validate_local_count_fold
from genomeos.validation.local_count_selection import (
    LocalCountBenchmarkConfig,
    LocalCountCandidateScore,
    LocalCountInfeasibleError,
    derive_local_count_seed,
    select_local_count_bandwidth,
    validate_local_count_assignments,
)
from genomeos.validation.predictive import predictive_diagnostics
from genomeos.validation.splits import BenchmarkSplit, build_buffered_splits

SEED = 42
DIAGNOSTIC_COLUMNS = (
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
    "bandwidth_km",
    "nearest_edge_distance_km",
    "training_observation_count",
    "effective_training_observations",
    "effective_allele_count",
    "posterior_alpha",
    "posterior_beta",
    "posterior_mean",
    "posterior_seed",
    "predictive_seed",
) + DIAGNOSTIC_COLUMNS
SUPPORT_COLUMNS = (
    "split_id",
    "block_id",
    "source_record_id",
    "status",
    "refusal_reason",
    "bandwidth_km",
    "nearest_edge_distance_km",
    "training_observation_count",
    "effective_training_observations",
    "effective_allele_count",
    "posterior_alpha",
    "posterior_beta",
    "posterior_mean",
)

FoldState = Literal["completed", "failed", "infeasible"]


def _seed(value: object) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 0:
        raise ValueError("seed must be a nonnegative integer")
    return int(value)


@dataclass(frozen=True)
class LocalCountFoldStatus:
    """One outer fold with separate requested, emitted, and refused identities."""

    split_id: str
    status: FoldState
    expected_test_ids: tuple[str, ...]
    emitted_test_ids: tuple[str, ...]
    refused_test_ids: tuple[str, ...]
    selected_bandwidth_km: float | None
    failure_reason: str | None


@dataclass(frozen=True)
class LocalCountBenchmarkPlan:
    """Validated inputs and immutable outer split ledger."""

    observations: pd.DataFrame
    assignments: pd.DataFrame
    dependencies: tuple[tuple[str, str], ...]
    splits: tuple[BenchmarkSplit, ...]
    config: LocalCountBenchmarkConfig
    buffer_km: float
    data_version: str
    seed: int


@dataclass(frozen=True)
class LocalCountFoldResult:
    """Predictions, support, and training-only selection for one terminal outer fold."""

    status: LocalCountFoldStatus
    predictions: pd.DataFrame
    support: pd.DataFrame
    candidate_scores: tuple[LocalCountCandidateScore, ...]


@dataclass(frozen=True)
class LocalCountBenchmarkResult:
    """Complete in-memory B1 benchmark evidence."""

    predictions: pd.DataFrame
    support: pd.DataFrame
    fold_status: tuple[LocalCountFoldStatus, ...]
    candidate_scores: pd.DataFrame
    splits: tuple[BenchmarkSplit, ...]
    summary: dict[str, object]


def plan_local_count_benchmark(
    observations: pd.DataFrame,
    block_assignments: pd.DataFrame,
    dependencies: Sequence[tuple[str, str]],
    *,
    buffer_km: float,
    data_version: str,
    config: LocalCountBenchmarkConfig,
    seed: int = SEED,
) -> LocalCountBenchmarkPlan:
    """Validate one modern variant and freeze every outer fold before selection."""
    if not isinstance(config, LocalCountBenchmarkConfig):
        raise TypeError("config must be a LocalCountBenchmarkConfig")
    validated = validate_allele_observations(observations)
    variants = tuple(sorted(validated["variant_id"].unique()))
    if len(variants) != 1 or variants[0].startswith("phenotype:"):
        raise ValueError("local count benchmark requires one non-phenotype variant")
    if ((validated["date_lower"] != 0) | (validated["date_upper"] != 0)).any():
        raise ValueError("local count benchmark requires modern observations")
    assignments = validate_local_count_assignments(validated, block_assignments)
    splits = build_buffered_splits(
        validated,
        assignments.loc[:, ["source_record_id", "block_id"]],
        dependencies,
        buffer_km=buffer_km,
        data_version=data_version,
    )
    return LocalCountBenchmarkPlan(
        observations=validated.sort_values("source_record_id").reset_index(drop=True),
        assignments=assignments,
        dependencies=tuple(dependencies),
        splits=splits,
        config=config,
        buffer_km=float(buffer_km),
        data_version=data_version,
        seed=_seed(seed),
    )


def _empty_predictions() -> pd.DataFrame:
    return pd.DataFrame(columns=PREDICTION_COLUMNS)


def _support_frame(
    split: BenchmarkSplit,
    bandwidth_km: float | None,
    rows: Sequence[LocalCountSupport],
) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "split_id": split.split_id,
                "block_id": split.block_id,
                "source_record_id": row.source_record_id,
                "status": row.status,
                "refusal_reason": row.refusal_reason or "",
                "bandwidth_km": bandwidth_km,
                "nearest_edge_distance_km": row.nearest_edge_distance_km,
                "training_observation_count": row.training_observation_count,
                "effective_training_observations": row.effective_training_observations,
                "effective_allele_count": row.effective_allele_count,
                "posterior_alpha": row.alpha,
                "posterior_beta": row.beta,
                "posterior_mean": row.posterior_mean,
            }
            for row in rows
        ],
        columns=SUPPORT_COLUMNS,
    )


def _failed_support(split: BenchmarkSplit, reason: str, bandwidth_km: float | None) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "split_id": split.split_id,
                "block_id": split.block_id,
                "source_record_id": record_id,
                "status": "unknown",
                "refusal_reason": reason,
                "bandwidth_km": bandwidth_km,
                "nearest_edge_distance_km": None,
                "training_observation_count": 0,
                "effective_training_observations": 0.0,
                "effective_allele_count": 0.0,
                "posterior_alpha": None,
                "posterior_beta": None,
                "posterior_mean": None,
            }
            for record_id in split.test_ids
        ],
        columns=SUPPORT_COLUMNS,
    )


def evaluate_local_count_fold(plan: LocalCountBenchmarkPlan, split: BenchmarkSplit) -> LocalCountFoldResult:
    """Select on inner training folds, then evaluate one untouched outer fold."""
    if not isinstance(plan, LocalCountBenchmarkPlan) or split not in plan.splits:
        raise ValueError("split must belong to plan")
    by_id = plan.observations.set_index("source_record_id", drop=False)
    if not split.train_ids:
        reason = "outer split has no training observations after leakage exclusions"
        status = LocalCountFoldStatus(
            split.split_id, "infeasible", split.test_ids, (), split.test_ids, None, reason
        )
        return LocalCountFoldResult(status, _empty_predictions(), _failed_support(split, reason, None), ())

    training = by_id.loc[list(split.train_ids)].reset_index(drop=True)
    testing = by_id.loc[list(split.test_ids)].reset_index(drop=True)
    training_ids = set(split.train_ids)
    inner_assignments = plan.assignments[plan.assignments["source_record_id"].isin(training_ids)].reset_index(
        drop=True
    )
    inner_dependencies = tuple(
        pair for pair in plan.dependencies if pair[0] in training_ids and pair[1] in training_ids
    )
    candidate_scores: tuple[LocalCountCandidateScore, ...] = ()
    selected_bandwidth: float | None = None
    try:
        selection = select_local_count_bandwidth(
            training,
            inner_assignments,
            inner_dependencies,
            buffer_km=plan.buffer_km,
            data_version=f"{plan.data_version}:outer:{split.split_id}",
            config=plan.config,
            seed=derive_local_count_seed(plan.seed, split.split_id, "selection"),
        )
        candidate_scores = selection.candidate_scores
        selected_bandwidth = selection.selected_bandwidth_km
        posterior_seed = derive_local_count_seed(plan.seed, split.split_id, "posterior")
        predictive_seed = derive_local_count_seed(plan.seed, split.split_id, "predictive")
        fit = fit_local_count(
            training,
            testing,
            config=plan.config.model_config(selected_bandwidth),
            seed=posterior_seed,
        )
        support = _support_frame(split, selected_bandwidth, fit.support)
        if fit.predictive is None:
            reason = "selected bandwidth emitted no outer test predictions"
            status = LocalCountFoldStatus(
                split.split_id,
                "infeasible",
                split.test_ids,
                (),
                split.test_ids,
                selected_bandwidth,
                reason,
            )
            return LocalCountFoldResult(
                status,
                _empty_predictions(),
                support,
                candidate_scores,
            )
        emitted_ids = fit.observation_ids
        refused_ids = tuple(sorted(set(split.test_ids) - set(emitted_ids)))
        emitted = by_id.loc[list(emitted_ids)].reset_index(drop=True)
        diagnostics = validate_predictive_diagnostics(
            predictive_diagnostics(
                fit.predictive,
                emitted["ac"].to_numpy(),
                emitted["an"].to_numpy(),
                seed=predictive_seed,
            )
        )
        support_by_id = {row.source_record_id: row for row in fit.support}
        assignment_by_id = plan.assignments.set_index("source_record_id")
        records = []
        for index, observation in enumerate(emitted.itertuples(index=False)):
            local = support_by_id[observation.source_record_id]
            assignment = assignment_by_id.loc[observation.source_record_id]
            record = {
                "split_id": split.split_id,
                "block_id": split.block_id,
                "source_record_id": observation.source_record_id,
                "variant_id": observation.variant_id,
                "region_id": assignment["region_id"],
                "variant_group": assignment["variant_group"],
                "cohort_id": observation.cohort_id,
                "observed_ac": int(observation.ac),
                "observed_an": int(observation.an),
                "bandwidth_km": selected_bandwidth,
                "nearest_edge_distance_km": local.nearest_edge_distance_km,
                "training_observation_count": local.training_observation_count,
                "effective_training_observations": local.effective_training_observations,
                "effective_allele_count": local.effective_allele_count,
                "posterior_alpha": local.alpha,
                "posterior_beta": local.beta,
                "posterior_mean": local.posterior_mean,
                "posterior_seed": posterior_seed,
                "predictive_seed": predictive_seed,
            }
            record.update(diagnostics.iloc[index].to_dict())
            records.append(record)
        predictions = pd.DataFrame.from_records(records, columns=PREDICTION_COLUMNS)
        status = LocalCountFoldStatus(
            split.split_id,
            "completed",
            split.test_ids,
            emitted_ids,
            refused_ids,
            selected_bandwidth,
            None,
        )
        return LocalCountFoldResult(status, predictions, support, candidate_scores)
    except LocalCountInfeasibleError as error:
        if error.scores:
            candidate_scores = error.scores
        reason = str(error)
        status = LocalCountFoldStatus(
            split.split_id,
            "infeasible",
            split.test_ids,
            (),
            split.test_ids,
            selected_bandwidth,
            reason,
        )
        return LocalCountFoldResult(
            status,
            _empty_predictions(),
            _failed_support(split, reason, selected_bandwidth),
            candidate_scores,
        )
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        status = LocalCountFoldStatus(
            split.split_id,
            "failed",
            split.test_ids,
            (),
            split.test_ids,
            selected_bandwidth,
            reason,
        )
        return LocalCountFoldResult(
            status,
            _empty_predictions(),
            _failed_support(split, reason, selected_bandwidth),
            candidate_scores,
        )


def finalize_local_count_benchmark(
    plan: LocalCountBenchmarkPlan, folds: Sequence[LocalCountFoldResult]
) -> LocalCountBenchmarkResult:
    """Validate one terminal result per outer split and summarize supported rows."""
    if not isinstance(plan, LocalCountBenchmarkPlan):
        raise TypeError("plan must be a LocalCountBenchmarkPlan")
    rebuilt = plan_local_count_benchmark(
        plan.observations,
        plan.assignments,
        plan.dependencies,
        buffer_km=plan.buffer_km,
        data_version=plan.data_version,
        config=plan.config,
        seed=plan.seed,
    )
    if rebuilt.splits != plan.splits:
        raise ValueError("plan splits contradict frozen inputs")
    by_split = {fold.status.split_id: fold for fold in folds}
    expected_ids = tuple(split.split_id for split in plan.splits)
    if len(by_split) != len(folds) or set(by_split) != set(expected_ids):
        raise ValueError("folds must contain exactly one result for every planned split")
    ordered = tuple(by_split[split_id] for split_id in expected_ids)
    for split, fold in zip(plan.splits, ordered, strict=True):
        validate_local_count_fold(fold, split, plan.observations, plan.assignments, config=plan.config)
    predictions = pd.concat([fold.predictions for fold in ordered], ignore_index=True)
    support = pd.concat([fold.support for fold in ordered], ignore_index=True)
    score_statuses = []
    for fold in ordered:
        status = fold.status
        if status.status == "completed":
            score_statuses.append(
                BenchmarkFoldStatus(status.split_id, "completed", status.emitted_test_ids, None)
            )
        else:
            score_statuses.append(
                BenchmarkFoldStatus(
                    status.split_id,
                    status.status,
                    status.expected_test_ids,
                    status.failure_reason,
                )
            )
    supported_summary = summarize_benchmark(predictions, score_statuses, expected_ids)
    requested = sum(len(split.test_ids) for split in plan.splits)
    emitted = sum(len(fold.status.emitted_test_ids) for fold in ordered)
    summary = {
        "comparison_complete": all(fold.status.status == "completed" for fold in ordered),
        "requested_observation_count": requested,
        "emitted_observation_count": emitted,
        "excluded_observation_count": requested - emitted,
        "excluded_fraction": (requested - emitted) / requested,
        "supported_only_benchmark": supported_summary,
    }
    candidate_records = []
    for fold in ordered:
        for score in fold.candidate_scores:
            candidate_records.append({"split_id": fold.status.split_id, **score.__dict__})
    candidate_frame = pd.DataFrame.from_records(candidate_records)
    return LocalCountBenchmarkResult(
        predictions=predictions.sort_values(["split_id", "source_record_id"]).reset_index(drop=True),
        support=support.sort_values(["split_id", "source_record_id"]).reset_index(drop=True),
        fold_status=tuple(fold.status for fold in ordered),
        candidate_scores=candidate_frame,
        splits=plan.splits,
        summary=summary,
    )


def validate_local_count_result(plan: LocalCountBenchmarkPlan, result: LocalCountBenchmarkResult) -> None:
    """Revalidate complete retained evidence immediately before artifact publication."""
    if result.splits != plan.splits:
        raise ValueError("result split ledger differs from plan")
    if not set(result.predictions["split_id"]) <= {s.split_id for s in plan.splits} or not set(
        result.support["split_id"]
    ) <= {s.split_id for s in plan.splits}:
        raise ValueError("result contains extra split identities")
    folds = tuple(
        LocalCountFoldResult(
            status,
            result.predictions.loc[result.predictions.split_id == status.split_id],
            result.support.loc[result.support.split_id == status.split_id],
            (),
        )
        for status in result.fold_status
    )
    replay = finalize_local_count_benchmark(plan, folds)
    if replay.summary != result.summary:
        raise ValueError("result summary contradicts retained evidence")


def evaluate_local_count_benchmark(plan: LocalCountBenchmarkPlan) -> LocalCountBenchmarkResult:
    """Evaluate every frozen outer fold and retain all terminal outcomes."""
    if not isinstance(plan, LocalCountBenchmarkPlan):
        raise TypeError("plan must be a LocalCountBenchmarkPlan")
    folds = tuple(evaluate_local_count_fold(plan, split) for split in plan.splits)
    return finalize_local_count_benchmark(plan, folds)

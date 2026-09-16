"""Offline single-variant spatial-GP benchmark (design §§4–5, 7–8, 12; #189).

Scientific objective
    Measure the unchanged current GP's predictive distribution for geographically held-out
    survey counts. This module does not claim improvement, certify resident sampling, or promote
    a model.
Acceptance evidence
    Every dependency-aware planned split has a terminal status. Completed splits carry exact
    integrated count diagnostics that the shared benchmark reporter balances by declared cohort,
    region, and variant group.
Engineering interface
    :func:`evaluate_single_variant_gp` builds splits from reviewed assignments, fits each fold
    offline, predicts genuinely unseen cohorts, and returns predictions, statuses, splits, and a
    fail-closed summary. There is no serving or file I/O path here.
Assumptions and refusals
    Inputs contain one modern allele, whole cohorts occupy one block, and every count lies in the
    selected likelihood's supported scoring domain. A global scoring-domain failure occurs before
    any expensive fit. Individual fit and prediction failures remain in the split ledger.

The fold loop is intentional because each fold is a distinct posterior fit. Within a fold,
queries and scoring are submitted as complete arrays; this module adds no observation-by-draw or
population-by-draw Python loop.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from numbers import Integral
from typing import Any

import numpy as np
import pandas as pd

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.fit import fit_surface
from genomeos.surfaces.observation import SurveyQueries
from genomeos.validation.benchmark import (
    BenchmarkFoldStatus,
    summarize_benchmark,
    validate_allele_observations,
    validate_predictive_diagnostics,
)
from genomeos.validation.predictive import (
    MAX_BETA_SCORING_COUNT,
    MAX_COUNT,
    CountPredictive,
    predictive_diagnostics,
)
from genomeos.validation.splits import BenchmarkSplit, build_buffered_splits

SEED = 42
ASSIGNMENT_COLUMNS = ("source_record_id", "block_id", "region_id", "variant_group")
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
    "fit_seed",
    "predictive_seed",
) + DIAGNOSTIC_COLUMNS

FitFunction = Callable[[pd.DataFrame, FitConfig], Any]


@dataclass(frozen=True)
class SpatialGPBenchmarkResult:
    """Complete in-memory evidence from one planned single-variant benchmark."""

    predictions: pd.DataFrame
    fold_status: tuple[BenchmarkFoldStatus, ...]
    splits: tuple[BenchmarkSplit, ...]
    summary: dict[str, object]


def _require_label(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} values must be nonempty strings")
    return value


def _validate_assignments(
    observations: pd.DataFrame, assignments: pd.DataFrame
) -> pd.DataFrame:
    if not isinstance(assignments, pd.DataFrame):
        raise TypeError("block_assignments must be a pandas DataFrame")
    if assignments.columns.duplicated().any() or tuple(assignments.columns) != ASSIGNMENT_COLUMNS:
        raise ValueError(
            f"block_assignments columns must be exactly {list(ASSIGNMENT_COLUMNS)}"
        )
    result = assignments.copy(deep=True)
    for column in ASSIGNMENT_COLUMNS:
        result[column] = result[column].map(
            lambda value, field=column: _require_label(value, field)
        )
    if result["source_record_id"].duplicated().any():
        raise ValueError("block_assignments must map every source_record_id exactly once")
    if set(result["source_record_id"]) != set(observations["source_record_id"]):
        raise ValueError("block_assignments must map exactly the observation source_record_id set")

    joined = observations.loc[:, ["source_record_id", "cohort_id"]].merge(
        result.loc[:, ["source_record_id", "block_id"]],
        on="source_record_id",
        how="left",
        validate="one_to_one",
    )
    blocks_per_cohort = joined.groupby("cohort_id", sort=True)["block_id"].nunique()
    split_cohorts = tuple(sorted(blocks_per_cohort[blocks_per_cohort != 1].index))
    if split_cohorts:
        raise ValueError(
            "block_assignments must place every whole cohort in one block; "
            f"split cohorts: {list(split_cohorts)}"
        )
    if result["variant_group"].nunique() != 1:
        raise ValueError("one benchmarked variant must map to exactly one variant_group")
    return result.sort_values("source_record_id").reset_index(drop=True)


def _validate_scientific_scope(observations: pd.DataFrame) -> None:
    variants = tuple(sorted(observations["variant_id"].unique()))
    if len(variants) != 1:
        raise ValueError("single-variant GP benchmark requires exactly one variant_id")
    if variants[0].startswith("phenotype:"):
        raise ValueError("single-variant GP benchmark rejects phenotype composites")
    dated = (observations["date_lower"] != 0) | (observations["date_upper"] != 0)
    if dated.any():
        raise ValueError("single-variant GP benchmark requires modern observations")


def _fold_seed(seed: int, split_id: str, purpose: str) -> int:
    digest = hashlib.sha256(f"{seed}\0{split_id}\0{purpose}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _scoring_refusal(observations: pd.DataFrame, likelihood: str) -> str | None:
    denominator = observations["an"].to_numpy(dtype=np.int64, copy=False)
    above_count_domain = denominator > MAX_COUNT
    if np.any(above_count_domain):
        return (
            "benchmark preflight refused before fitting: "
            f"{int(above_count_domain.sum())} denominators exceed the maximum supported count "
            f"{MAX_COUNT:,}"
        )
    if likelihood == "beta_binomial":
        above_scoring_domain = denominator > MAX_BETA_SCORING_COUNT
        if np.any(above_scoring_domain):
            return (
                "benchmark preflight refused before fitting: "
                f"{int(above_scoring_domain.sum())} beta-binomial denominators exceed the exact "
                f"integrated log-score work limit of {MAX_BETA_SCORING_COUNT:,}; no observation "
                "or fold was dropped"
            )
    return None


def _empty_predictions() -> pd.DataFrame:
    return pd.DataFrame(columns=PREDICTION_COLUMNS)


def _summarized_result(
    predictions: pd.DataFrame,
    statuses: Sequence[BenchmarkFoldStatus],
    splits: tuple[BenchmarkSplit, ...],
) -> SpatialGPBenchmarkResult:
    ordered = predictions.sort_values(["source_record_id", "split_id"]).reset_index(drop=True)
    status_tuple = tuple(statuses)
    summary = summarize_benchmark(
        ordered,
        status_tuple,
        tuple(split.split_id for split in splits),
    )
    return SpatialGPBenchmarkResult(ordered, status_tuple, splits, summary)


def _fold_predictions(
    observations: pd.DataFrame,
    assignments: pd.DataFrame,
    split: BenchmarkSplit,
    *,
    config: FitConfig,
    seed: int,
    cdf_backend: str,
    fit_function: FitFunction,
) -> pd.DataFrame:
    by_id = observations.set_index("source_record_id", drop=False)
    training = by_id.loc[list(split.train_ids)].reset_index(drop=True)
    testing = by_id.loc[list(split.test_ids)].reset_index(drop=True)
    if training.empty:
        raise ValueError("split has no training observations after dependency and buffer exclusions")
    if set(training["cohort_id"]) & set(testing["cohort_id"]):
        raise ValueError("held-out cohorts must be genuinely unseen during fitting")

    fit_seed = _fold_seed(seed, split.split_id, "fit")
    predictive_seed = _fold_seed(seed, split.split_id, "predictive")
    fit = fit_function(training, replace(config, seed=fit_seed))
    queries = SurveyQueries(
        observation_ids=tuple(testing["source_record_id"]),
        cohort_ids=tuple(testing["cohort_id"]),
        sampling_designs=tuple(testing["sampling_design"]),
        lat=tuple(testing["lat"]),
        lon=tuple(testing["lon"]),
    )
    parameters = fit.predict_new_cohort_parameters(queries, seed=predictive_seed)
    predictive = CountPredictive(
        parameters.mean_draws,
        concentration=parameters.concentration,
        cdf_backend=cdf_backend,
    )
    diagnostics = validate_predictive_diagnostics(
        predictive_diagnostics(
            predictive,
            testing["ac"].to_numpy(),
            testing["an"].to_numpy(),
            seed=predictive_seed,
        )
    )

    identity = testing.loc[
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
    identity["fit_seed"] = fit_seed
    identity["predictive_seed"] = predictive_seed
    return pd.concat(
        [identity.reset_index(drop=True), diagnostics.reset_index(drop=True)],
        axis=1,
    ).loc[:, PREDICTION_COLUMNS]


def evaluate_single_variant_gp(
    observations: pd.DataFrame,
    block_assignments: pd.DataFrame,
    dependencies: Sequence[tuple[str, str]],
    *,
    buffer_km: float,
    data_version: str,
    config: FitConfig,
    seed: int = SEED,
    cdf_backend: str = "scipy",
    fit_function: FitFunction = fit_surface,
) -> SpatialGPBenchmarkResult:
    """Run every reviewed split or return a complete fail-closed split ledger.

    ``fit_function`` is an offline dependency seam used by tests and controlled runners. Its
    production default is the unchanged :func:`genomeos.surfaces.fit.fit_surface` implementation.
    """
    if not isinstance(config, FitConfig):
        raise TypeError("config must be a FitConfig")
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("seed must be a nonnegative integer, not a boolean")
    if cdf_backend not in {"scipy", "cupy"}:
        raise ValueError("cdf_backend must be either 'scipy' or 'cupy'")
    if not callable(fit_function):
        raise TypeError("fit_function must be callable")

    validated = validate_allele_observations(observations)
    _validate_scientific_scope(validated)
    assignments = _validate_assignments(validated, block_assignments)
    splits = build_buffered_splits(
        validated,
        assignments.loc[:, ["source_record_id", "block_id"]],
        dependencies,
        buffer_km=buffer_km,
        data_version=data_version,
    )

    refusal = _scoring_refusal(validated, config.likelihood)
    if refusal is not None:
        statuses = tuple(
            BenchmarkFoldStatus(split.split_id, "failed", split.test_ids, refusal)
            for split in splits
        )
        return _summarized_result(_empty_predictions(), statuses, splits)

    statuses: list[BenchmarkFoldStatus] = []
    prediction_frames: list[pd.DataFrame] = []
    for split in splits:
        if not split.train_ids:
            statuses.append(
                BenchmarkFoldStatus(
                    split.split_id,
                    "infeasible",
                    split.test_ids,
                    "split has no training observations after dependency and buffer exclusions",
                )
            )
            continue
        try:
            prediction_frames.append(
                _fold_predictions(
                    validated,
                    assignments,
                    split,
                    config=config,
                    seed=int(seed),
                    cdf_backend=cdf_backend,
                    fit_function=fit_function,
                )
            )
        except Exception as error:  # Every planned fold remains visible in the result ledger.
            statuses.append(
                BenchmarkFoldStatus(
                    split.split_id,
                    "failed",
                    split.test_ids,
                    f"{type(error).__name__}: {error}",
                )
            )
        else:
            statuses.append(
                BenchmarkFoldStatus(split.split_id, "completed", split.test_ids, None)
            )

    predictions = (
        pd.concat(prediction_frames, ignore_index=True)
        if prediction_frames
        else _empty_predictions()
    )
    return _summarized_result(predictions, statuses, splits)

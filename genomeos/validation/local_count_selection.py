"""Training-only bandwidth selection for B1 local counts (design §§5, 7–8; #307).

The candidate family, inner emission gate, buffered split geometry, and count score are explicit.
Selection sees only the caller's outer-training rows. A bandwidth that fails an inner fold or
emits too little evidence cannot win by hiding difficult geography.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Real

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import validate_allele_observations
from genomeos.validation.local_count import LocalCountConfig, fit_local_count
from genomeos.validation.splits import build_buffered_splits

ASSIGNMENT_COLUMNS = ("source_record_id", "block_id", "region_id", "variant_group")


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be positive and finite")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return normalized


def _unit_interval(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be between zero and one")
    normalized = float(value)
    if not isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be between zero and one")
    return normalized


def derive_local_count_seed(seed: int, *parts: object) -> int:
    """Derive a stable uint32 seed from one declared root and semantic identity parts."""
    payload = "\0".join((str(seed), *(str(part) for part in parts)))
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:4], "big")


@dataclass(frozen=True)
class LocalCountBenchmarkConfig:
    """Prespecified candidate family and inner-selection gate."""

    candidate_bandwidths_km: tuple[float, ...]
    prior_alpha: float
    prior_beta: float
    posterior_draws: int
    minimum_training_observations: int = 1
    minimum_effective_alleles: float = 1.0
    minimum_inner_emission_fraction: float = 0.5
    query_chunk_size: int = 1024

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_bandwidths_km, tuple) or not self.candidate_bandwidths_km:
            raise ValueError("candidate_bandwidths_km must be a nonempty increasing tuple")
        candidates = tuple(
            _positive_real(value, "candidate_bandwidths_km")
            for value in self.candidate_bandwidths_km
        )
        if any(right <= left for left, right in zip(candidates, candidates[1:], strict=False)):
            raise ValueError("candidate_bandwidths_km must be strictly increasing")
        object.__setattr__(self, "candidate_bandwidths_km", candidates)
        probe = LocalCountConfig(
            bandwidth_km=candidates[0],
            prior_alpha=self.prior_alpha,
            prior_beta=self.prior_beta,
            posterior_draws=self.posterior_draws,
            minimum_training_observations=self.minimum_training_observations,
            minimum_effective_alleles=self.minimum_effective_alleles,
            query_chunk_size=self.query_chunk_size,
        )
        object.__setattr__(self, "prior_alpha", probe.prior_alpha)
        object.__setattr__(self, "prior_beta", probe.prior_beta)
        object.__setattr__(self, "posterior_draws", probe.posterior_draws)
        object.__setattr__(
            self, "minimum_training_observations", probe.minimum_training_observations
        )
        object.__setattr__(
            self, "minimum_effective_alleles", probe.minimum_effective_alleles
        )
        object.__setattr__(self, "query_chunk_size", probe.query_chunk_size)
        object.__setattr__(
            self,
            "minimum_inner_emission_fraction",
            _unit_interval(
                self.minimum_inner_emission_fraction,
                "minimum_inner_emission_fraction",
            ),
        )

    def model_config(self, bandwidth_km: float) -> LocalCountConfig:
        """Resolve one declared candidate into the core model configuration."""
        if bandwidth_km not in self.candidate_bandwidths_km:
            raise ValueError("bandwidth_km is not a declared candidate")
        return LocalCountConfig(
            bandwidth_km=bandwidth_km,
            prior_alpha=self.prior_alpha,
            prior_beta=self.prior_beta,
            posterior_draws=self.posterior_draws,
            minimum_training_observations=self.minimum_training_observations,
            minimum_effective_alleles=self.minimum_effective_alleles,
            query_chunk_size=self.query_chunk_size,
        )


@dataclass(frozen=True)
class LocalCountCandidateScore:
    """Training-only evidence for one bandwidth candidate."""

    bandwidth_km: float
    requested_count: int
    emitted_count: int
    emission_fraction: float
    mean_log_score: float | None
    completed_inner_fold_count: int
    failed_inner_fold_count: int
    inner_failure_reasons: tuple[str, ...]
    eligible: bool


@dataclass(frozen=True)
class LocalCountSelection:
    """Selected bandwidth and the complete prespecified candidate ledger."""

    selected_bandwidth_km: float
    candidate_scores: tuple[LocalCountCandidateScore, ...]


class LocalCountInfeasibleError(ValueError):
    """The training-only selector or outer support gate emitted no usable model."""

    def __init__(self, message: str, scores: tuple[LocalCountCandidateScore, ...] = ()) -> None:
        self.scores = scores
        super().__init__(message)


def validate_local_count_assignments(
    observations: pd.DataFrame, assignments: pd.DataFrame
) -> pd.DataFrame:
    """Validate exact identities, whole-cohort blocks, and one variant group."""
    if not isinstance(assignments, pd.DataFrame):
        raise TypeError("block_assignments must be a pandas DataFrame")
    if assignments.columns.duplicated().any() or tuple(assignments.columns) != ASSIGNMENT_COLUMNS:
        raise ValueError(f"block_assignments columns must be exactly {list(ASSIGNMENT_COLUMNS)}")
    result = assignments.copy(deep=True)
    for column in ASSIGNMENT_COLUMNS:
        if not result[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError(f"{column} values must be nonempty strings")
    if result["source_record_id"].duplicated().any() or set(result["source_record_id"]) != set(
        observations["source_record_id"]
    ):
        raise ValueError("block_assignments must map every source_record_id exactly once")
    joined = observations.loc[:, ["source_record_id", "cohort_id"]].merge(
        result.loc[:, ["source_record_id", "block_id"]], validate="one_to_one"
    )
    split_cohorts = joined.groupby("cohort_id")["block_id"].nunique()
    if (split_cohorts != 1).any():
        raise ValueError("block_assignments must place every whole cohort in one block")
    if result["variant_group"].nunique() != 1:
        raise ValueError("one benchmarked variant must map to exactly one variant_group")
    return result.sort_values("source_record_id").reset_index(drop=True)


def select_local_count_bandwidth(
    training_observations: pd.DataFrame,
    training_assignments: pd.DataFrame,
    dependencies: Sequence[tuple[str, str]],
    *,
    buffer_km: float,
    data_version: str,
    config: LocalCountBenchmarkConfig,
    seed: int,
) -> LocalCountSelection:
    """Select a declared bandwidth using only buffered folds within outer training data."""
    training = validate_allele_observations(training_observations)
    assignments = validate_local_count_assignments(training, training_assignments)
    try:
        inner_splits = build_buffered_splits(
            training,
            assignments.loc[:, ["source_record_id", "block_id"]],
            dependencies,
            buffer_km=buffer_km,
            data_version=data_version,
        )
    except ValueError as error:
        raise LocalCountInfeasibleError(f"inner split planning failed: {error}") from error
    by_id = training.set_index("source_record_id", drop=False)
    scores: list[LocalCountCandidateScore] = []
    for bandwidth in config.candidate_bandwidths_km:
        requested = emitted = completed = failed = 0
        log_scores: list[np.ndarray] = []
        failure_reasons: list[str] = []
        for split in inner_splits:
            requested += len(split.test_ids)
            if not split.train_ids:
                failed += 1
                failure_reasons.append(f"{split.split_id}: no training observations")
                continue
            try:
                inner_train = by_id.loc[list(split.train_ids)].reset_index(drop=True)
                inner_test = by_id.loc[list(split.test_ids)].reset_index(drop=True)
                fit = fit_local_count(
                    inner_train,
                    inner_test,
                    config=config.model_config(bandwidth),
                    seed=derive_local_count_seed(seed, split.split_id, bandwidth, "posterior"),
                )
                if fit.predictive is not None:
                    emitted_test = by_id.loc[list(fit.observation_ids)]
                    log_scores.append(
                        fit.predictive.log_prob(
                            emitted_test["ac"].to_numpy(), emitted_test["an"].to_numpy()
                        )
                    )
                    emitted += len(fit.observation_ids)
                completed += 1
            except Exception as error:
                failed += 1
                failure_reasons.append(
                    f"{split.split_id}: {type(error).__name__}: {error}"
                )
        emission_fraction = emitted / requested if requested else 0.0
        combined = np.concatenate(log_scores) if log_scores else np.asarray([], dtype=float)
        mean_log_score = float(np.mean(combined)) if combined.size else None
        eligible = (
            failed == 0
            and emitted > 0
            and emission_fraction >= config.minimum_inner_emission_fraction
            and mean_log_score is not None
            and not np.isnan(mean_log_score)
        )
        scores.append(
            LocalCountCandidateScore(
                bandwidth_km=bandwidth,
                requested_count=requested,
                emitted_count=emitted,
                emission_fraction=emission_fraction,
                mean_log_score=mean_log_score,
                completed_inner_fold_count=completed,
                failed_inner_fold_count=failed,
                inner_failure_reasons=tuple(failure_reasons),
                eligible=eligible,
            )
        )
    score_tuple = tuple(scores)
    eligible_scores = tuple(score for score in score_tuple if score.eligible)
    if not eligible_scores:
        raise LocalCountInfeasibleError(
            "no bandwidth passed the training-only emission and fold-completion gates",
            score_tuple,
        )
    selected = max(
        eligible_scores,
        key=lambda score: (float(score.mean_log_score), -score.bandwidth_km),
    )
    return LocalCountSelection(selected.bandwidth_km, score_tuple)

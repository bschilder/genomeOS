"""Closed B0H descriptive/reduction outputs (design §§5,7–8,12; runner §6)."""
from __future__ import annotations

import math
import struct
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from genomeos.validation.heterogeneity_runner_records import ClosedRecord, Digest, Natural, Text
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId
from genomeos.validation.sbc_ranks import RankTestResult

Bits = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
CommonStageStatus = Literal[
    "unstarted", "not_admitted", "started_unresolved", "owner_lost", "execution_failed"
]
GenerationStatus = CommonStageStatus | Literal["available", "all_unavailable", "generation_failed"]
StructuralStatus = CommonStageStatus | Literal[
    "expected_refusal", "unexpected_exception", "unexpected_return"
]
AttemptStatus = CommonStageStatus | Literal["accepted", "convergence_failed", "failed", "identity_rejected"]
QuantityStatus = CommonStageStatus | Literal["complete", "incomplete"]
SummaryStatus = CommonStageStatus | Literal["complete", "prediction_failed", "diagnostics_failed"]
RankFailure = Literal[
    "unstarted", "started_unresolved", "owner_lost", "execution_failed", "not_admitted",
    "generation:unstarted", "generation:started_unresolved", "generation:owner_lost",
    "generation:execution_failed", "generation:generation_failed",
    "attempt0:unstarted", "attempt0:started_unresolved", "attempt0:owner_lost",
    "attempt0:execution_failed", "attempt0:failed", "attempt0:identity_rejected",
    "attempt1:unstarted", "attempt1:started_unresolved", "attempt1:owner_lost",
    "attempt1:execution_failed", "attempt1:failed", "attempt1:identity_rejected",
    "attempt1:convergence_failed", "quantities:unstarted",
    "control_failed", "quantity_failed", "reference_failed", "dependence_reference_unresolved",
    "dependence_rank_order_unresolved", "comparison_failed", "rank_failed",
]
Metric = Literal[
    "estimate", "truth", "absolute_error", "squared_error", "log_score", "randomized_pit",
    "coverage_50", "coverage_80", "coverage_95", "width_50", "width_80", "width_95",
]
Target = Literal["parameter_mean", "parameter_rho", "fresh_population", "shared_cluster0", "fresh_cluster"]


def _metric_value(metric: str, bits: str, *, aggregate: bool) -> None:
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    if math.isnan(value) or value == math.inf or (value == -math.inf and metric != "log_score"):
        raise ValueError("unsupported nonfinite descriptive value")
    if metric == "log_score":
        if value > 0:
            raise ValueError("log probability mass cannot be positive")
    elif metric in ("estimate", "truth", "randomized_pit") or metric.startswith("coverage_"):
        if not 0 <= value <= 1:
            raise ValueError("descriptive fraction outside [0,1]")
        if metric.startswith("coverage_") and not aggregate and value not in (0.0, 1.0):
            raise ValueError("per-case coverage must be an observed Boolean encoded as binary64")
    elif value < 0:
        raise ValueError("error/width cannot be negative")


class CaseAccounting(ClosedRecord):
    case: SbcCaseId
    generation: GenerationStatus
    structural: StructuralStatus
    attempt0: AttemptStatus
    attempt1: AttemptStatus
    quantities: QuantityStatus
    summary: SummaryStatus
    accepted_attempt: Literal[0, 1] | None
    owner_loss_count: Natural
    execution_failure_count: Natural
    unstarted_required_stages: tuple[Literal["generation", "structural", "fit", "quantities", "summary"], ...]
    unresolved_reasons: tuple[Text, ...]


class RankReduction(ClosedRecord):
    track_id: Literal[0, 1]
    mode_id: Literal[0, 1, 2]
    quantity_id: Literal[0, 1, 2, 3, 4, 5]
    counts: tuple[Natural, Natural, Natural, Natural, Natural]
    actual_n: Annotated[int, Field(ge=0, le=512)]
    missing_n: Annotated[int, Field(ge=0, le=512)]
    failure_status_counts: tuple[tuple[RankFailure, Natural], ...]
    test: RankTestResult | None
    role: Literal["correct_family", "required_control", "other_control"]
    decision: Literal["reject", "not_reject", "uncomputable"]

    @model_validator(mode="after")
    def denominator(self) -> Self:
        role = ("correct_family" if self.mode_id == 0 else "required_control"
                if (self.mode_id, self.quantity_id) in ((1, 3), (2, 5)) else "other_control")
        if self.role != role:
            raise ValueError("rank role differs from frozen declaration")
        names = tuple(name for name, _ in self.failure_status_counts)
        if names != tuple(sorted(set(names))) or any(count == 0 for _, count in self.failure_status_counts):
            raise ValueError("rank failures must be unique ordered nonzero counts")
        if sum(self.counts) != self.actual_n or self.actual_n + self.missing_n != 512:
            raise ValueError("rank denominator mismatch")
        if sum(count for _, count in self.failure_status_counts) != self.missing_n:
            raise ValueError("rank failure denominator mismatch")
        if (self.test is None) != (self.actual_n != 512):
            raise ValueError("only full N512 admits test")
        if self.test is not None and self.test.counts != self.counts:
            raise ValueError("rank test count mismatch")
        expected = "uncomputable" if self.test is None else (
            "reject" if self.test.p_value <= .05 / 12 else "not_reject")
        if self.decision != expected:
            raise ValueError("rank decision differs from fixed threshold")
        return self


class DescriptiveRow(ClosedRecord):
    case: SbcCaseId
    target_kind: Target
    metric: Metric
    value_bits: Bits
    dependence_label: Literal["independent_dataset", "shared_history_paired_tracks",
                              "boundary_degenerate_paired_tracks", "paired_tracks"]

    @model_validator(mode="after")
    def numeric_value(self) -> Self:
        _metric_value(self.metric, self.value_bits, aggregate=False)
        return self


class DescriptiveAggregate(ClosedRecord):
    study_id: Literal[0, 1, 2, 4]
    case_id: Natural
    track_id: Literal[0, 1]
    target_kind: Target
    metric: Metric
    planned_n: Natural
    actual_n: Natural
    failed_n: Natural
    mean_bits: Bits | None

    @model_validator(mode="after")
    def denominator(self) -> Self:
        if self.actual_n + self.failed_n != self.planned_n:
            raise ValueError("descriptive denominator mismatch")
        if (self.mean_bits is None) != (self.actual_n == 0):
            raise ValueError("descriptive mean requires actual observations")
        if self.mean_bits is not None:
            _metric_value(self.metric, self.mean_bits, aggregate=True)
        return self


class StudyReduction(ClosedRecord):
    format: Literal["b0h_reduction"]
    version: Literal["1"]
    campaign_sha256: Digest
    inventory_sha256: Digest
    null_sha256: Digest
    cases: tuple[CaseAccounting, ...]
    planned_initial_fits: Literal[1936]
    planned_retry_slots: Literal[1936]
    completed_fit_calls: Natural
    ambiguous_fit_calls: Natural
    completed_generation_calls: Natural
    completed_structural_calls: Natural
    completed_quantity_calls: Natural
    completed_summary_calls: Natural
    ranks: tuple[RankReduction, ...]
    rows: tuple[DescriptiveRow, ...]
    aggregates: tuple[DescriptiveAggregate, ...]
    correct_family_rejected: bool
    sensitivity_limited: bool
    unconditional_claim_eligible: bool
    claim_reasons: tuple[Text, ...]
    permitted_claim: Literal["no discrepancy detected at this design's resolution"] | None

    @model_validator(mode="after")
    def fixed_sizes(self) -> Self:
        from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
        if tuple(case.case for case in self.cases) != enumerate_sbc_cases():
            raise ValueError("reduction requires exact ordered1938 cases")
        expected = tuple((track, mode, quantity) for track in (0, 1)
                         for mode in range(3) for quantity in range(6))
        if tuple((row.track_id, row.mode_id, row.quantity_id) for row in self.ranks) != expected:
            raise ValueError("reduction requires exact ordered36 rank rows")
        rejected = any(row.decision == "reject" for row in self.ranks if row.role == "correct_family")
        limited = any(row.decision != "reject" for row in self.ranks if row.role == "required_control")
        if self.correct_family_rejected != rejected or self.sensitivity_limited != limited:
            raise ValueError("reduction decisions contradict fixed rank roles")
        finished_fit = {"accepted", "convergence_failed", "failed", "identity_rejected", "execution_failed"}
        fit_states = tuple(state for case in self.cases for state in (case.attempt0, case.attempt1))
        if self.completed_fit_calls != sum(state in finished_fit for state in fit_states):
            raise ValueError("completed fit calls contradict case accounting")
        if self.ambiguous_fit_calls != sum(
            state in ("started_unresolved", "owner_lost") for state in fit_states
        ):
            raise ValueError("ambiguous fit calls contradict case accounting")
        if self.unconditional_claim_eligible != (not self.claim_reasons):
            raise ValueError("claim eligibility contradicts reasons")
        if (self.permitted_claim is not None) != self.unconditional_claim_eligible:
            raise ValueError("claim wording contradicts eligibility")
        return self

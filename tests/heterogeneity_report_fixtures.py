"""Authored reporting fixtures; these are not executed calibration results."""
from __future__ import annotations

import struct

from genomeos.validation.heterogeneity_reduction_records import (
    CaseAccounting,
    DescriptiveAggregate,
    DescriptiveRow,
    RankReduction,
    StudyReduction,
)
from genomeos.validation.heterogeneity_simulation_types import enumerate_sbc_cases
from genomeos.validation.sbc_ranks import RankTestResult


def _bits(value: float) -> str:
    return struct.pack(">d", value).hex()


def _accounting() -> tuple[CaseAccounting, ...]:
    return tuple(
        CaseAccounting(
            case=case,
            generation="all_unavailable" if case.study_id == 3 else "available",
            structural="expected_refusal" if case.study_id == 3 else "not_admitted",
            attempt0="not_admitted" if case.study_id == 3 else "accepted",
            attempt1="not_admitted",
            quantities="complete" if case.study_id == 0 else "not_admitted",
            summary="not_admitted" if case.study_id == 3 else "complete",
            accepted_attempt=None if case.study_id == 3 else 0,
            owner_loss_count=0,
            execution_failure_count=0,
            unstarted_required_stages=(),
            unresolved_reasons=(),
        )
        for case in enumerate_sbc_cases()
    )


def _complete_rank(track: int, mode: int, quantity: int) -> RankReduction:
    required = (mode, quantity) in ((1, 3), (2, 5))
    counts = (512, 0, 0, 0, 0) if required else (103, 103, 102, 102, 102)
    p_value = 2 / 100001 if required else 0.5
    role = "correct_family" if mode == 0 else "required_control" if required else "other_control"
    return RankReduction(
        track_id=track,
        mode_id=mode,
        quantity_id=quantity,
        counts=counts,
        actual_n=512,
        missing_n=0,
        failure_status_counts=(),
        test=RankTestResult(
            counts=counts,
            statistic=2048 if required else 6,
            p_value=p_value,
            bonferroni_p_value=min(1.0, 12 * p_value),
        ),
        role=role,
        decision="reject" if required else "not_reject",
    )


def synthetic_reduction(*, incomplete_ranks: bool = False) -> StudyReduction:
    """Return a constructor-valid authored fixture with all cases and rank rows."""
    cases = _accounting()
    ranks = tuple(
        _complete_rank(track, mode, quantity)
        for track in (0, 1)
        for mode in range(3)
        for quantity in range(6)
    )
    reasons: tuple[str, ...] = ()
    if incomplete_ranks:
        mutable = list(ranks)
        mutable[0] = RankReduction(
            track_id=0,
            mode_id=0,
            quantity_id=0,
            counts=(103, 102, 102, 102, 102),
            actual_n=511,
            missing_n=1,
            failure_status_counts=(("rank_failed", 1),),
            test=None,
            role="correct_family",
            decision="uncomputable",
        )
        mutable[23] = RankReduction(
            track_id=1,
            mode_id=0,
            quantity_id=5,
            counts=(0, 0, 0, 0, 0),
            actual_n=0,
            missing_n=512,
            failure_status_counts=(("unstarted", 512),),
            test=None,
            role="correct_family",
            decision="uncomputable",
        )
        ranks = tuple(mutable)
        reasons = ("incomplete_rank_outcomes",)
    rows = (
        DescriptiveRow(
            case=cases[0].case,
            target_kind="fresh_population",
            metric="log_score",
            value_bits=_bits(-float("inf")),
            dependence_label="independent_dataset",
        ),
    )
    aggregates = (
        DescriptiveAggregate(
            study_id=0,
            case_id=0,
            track_id=0,
            target_kind="fresh_population",
            metric="log_score",
            planned_n=1,
            actual_n=1,
            failed_n=0,
            mean_bits=_bits(-float("inf")),
        ),
        DescriptiveAggregate(
            study_id=0,
            case_id=0,
            track_id=1,
            target_kind="fresh_population",
            metric="log_score",
            planned_n=1,
            actual_n=0,
            failed_n=1,
            mean_bits=None,
        ),
    )
    return StudyReduction(
        format="b0h_reduction",
        version="1",
        campaign_sha256="1" * 64,
        inventory_sha256="2" * 64,
        null_sha256="3" * 64,
        cases=cases,
        planned_initial_fits=1936,
        planned_retry_slots=1936,
        completed_fit_calls=1936,
        ambiguous_fit_calls=0,
        completed_generation_calls=1938,
        completed_structural_calls=2,
        completed_quantity_calls=1024,
        completed_summary_calls=1936,
        ranks=ranks,
        rows=rows,
        aggregates=aggregates,
        correct_family_rejected=False,
        sensitivity_limited=False,
        unconditional_claim_eligible=not reasons,
        claim_reasons=reasons,
        permitted_claim=None if reasons else "no discrepancy detected at this design's resolution",
    )

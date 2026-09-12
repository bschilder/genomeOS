#!/usr/bin/env python3
"""Author the synthetic B0H reporting demonstration (report design §§1,3–4; Atlas §§5,7–8,12).

The output exercises reporting states through public immutable records. It is
not an executed simulation calibration and supplies no scientific evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from genomeos.validation.heterogeneity_reduction import (  # noqa: E402
    reduction_bytes,
    study_claim_reasons,
)
from genomeos.validation.heterogeneity_reduction_records import (  # noqa: E402
    CaseAccounting,
    DescriptiveAggregate,
    DescriptiveRow,
    RankReduction,
    StudyReduction,
)
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId  # noqa: E402
from genomeos.validation.sbc_ranks import RankTestResult  # noqa: E402

_GROUP_SHAPES = ((1, 512), (24, 16), (4, 16), (1, 1), (2, 4))


def _bits(value: float) -> str:
    return struct.pack(">d", value).hex()


def _case_ids() -> tuple[SbcCaseId, ...]:
    return tuple(
        SbcCaseId(track, study, case, replicate)
        for study, (case_count, replicate_count) in enumerate(_GROUP_SHAPES)
        for case in range(case_count)
        for replicate in range(replicate_count)
        for track in (0, 1)
    )


def _case_accounting() -> tuple[CaseAccounting, ...]:
    rows = []
    for case in _case_ids():
        if case.study_id == 3:
            values = {
                "generation": "all_unavailable",
                "structural": "expected_refusal",
                "attempt0": "not_admitted",
                "attempt1": "not_admitted",
                "quantities": "not_admitted",
                "summary": "not_admitted",
                "accepted_attempt": None,
                "owner_loss_count": 0,
                "execution_failure_count": 0,
                "unstarted_required_stages": (),
                "unresolved_reasons": (),
            }
        else:
            values = {
                "generation": "available",
                "structural": "not_admitted",
                "attempt0": "accepted",
                "attempt1": "not_admitted",
                "quantities": "complete" if case.study_id == 0 else "not_admitted",
                "summary": "complete",
                "accepted_attempt": 0,
                "owner_loss_count": 0,
                "execution_failure_count": 0,
                "unstarted_required_stages": (),
                "unresolved_reasons": (),
            }

        identity = (case.track_id, case.study_id, case.case_id, case.replicate_id)
        if identity == (0, 0, 0, 0):
            values.update(attempt0="convergence_failed", attempt1="accepted", accepted_attempt=1)
        elif identity == (1, 0, 0, 0):
            values.update(
                attempt0="started_unresolved",
                quantities="not_admitted",
                summary="not_admitted",
                accepted_attempt=None,
                unresolved_reasons=("attempt0:started_unresolved",),
            )
        elif identity == (0, 0, 0, 1):
            values.update(
                quantities="incomplete",
                summary="not_admitted",
                unresolved_reasons=("quantities:incomplete",),
            )
        elif identity == (0, 1, 0, 0):
            values.update(
                generation="generation_failed",
                attempt0="not_admitted",
                summary="not_admitted",
                accepted_attempt=None,
                unresolved_reasons=("generation:generation_failed",),
            )
        elif identity == (1, 1, 0, 1):
            values.update(
                summary="diagnostics_failed",
                unresolved_reasons=("summary:diagnostics_failed",),
            )
        elif identity == (1, 2, 0, 0):
            values.update(
                attempt0="execution_failed",
                summary="not_admitted",
                accepted_attempt=None,
                execution_failure_count=1,
                unresolved_reasons=("attempt0:execution_failed",),
            )
        elif identity == (1, 3, 0, 0):
            values.update(
                structural="unexpected_return",
                unresolved_reasons=("structural:unexpected_return",),
            )
        rows.append(CaseAccounting(case=case, **values))
    return tuple(rows)


def _rank(track: int, mode: int, quantity: int) -> RankReduction:
    role = (
        "correct_family"
        if mode == 0
        else "required_control"
        if (mode, quantity) in ((1, 3), (2, 5))
        else "other_control"
    )
    if (track, mode, quantity) == (0, 0, 0):
        return RankReduction(
            track_id=track,
            mode_id=mode,
            quantity_id=quantity,
            counts=(103, 102, 102, 102, 102),
            actual_n=511,
            missing_n=1,
            failure_status_counts=(("rank_failed", 1),),
            test=None,
            role=role,
            decision="uncomputable",
        )
    if (track, mode, quantity) == (1, 0, 5):
        return RankReduction(
            track_id=track,
            mode_id=mode,
            quantity_id=quantity,
            counts=(0, 0, 0, 0, 0),
            actual_n=0,
            missing_n=512,
            failure_status_counts=(("unstarted", 512),),
            test=None,
            role=role,
            decision="uncomputable",
        )

    reject = (track, mode, quantity) in {
        (0, 0, 1),
        (0, 1, 3),
        (1, 2, 5),
    }
    counts = (512, 0, 0, 0, 0) if reject else (103, 103, 102, 102, 102)
    p_value = 2 / 100001 if reject else 0.5
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
            statistic=2048 if reject else 6,
            p_value=p_value,
            bonferroni_p_value=min(1.0, 12 * p_value),
        ),
        role=role,
        decision="reject" if reject else "not_reject",
    )


def _completed_count(rows: tuple[CaseAccounting, ...], field: str) -> int:
    unfinished = {"unstarted", "not_admitted", "started_unresolved", "owner_lost"}
    return sum(getattr(row, field) not in unfinished for row in rows)


def build_demo_reduction() -> StudyReduction:
    """Return the complete deterministic authored reporting example."""
    cases = _case_accounting()
    ranks = tuple(
        _rank(track, mode, quantity)
        for track in (0, 1)
        for mode in range(3)
        for quantity in range(6)
    )
    reasons = study_claim_reasons(cases, ranks)
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
        completed_fit_calls=_completed_count(cases, "attempt0")
        + _completed_count(cases, "attempt1"),
        ambiguous_fit_calls=sum(
            status in {"started_unresolved", "owner_lost"}
            for row in cases
            for status in (row.attempt0, row.attempt1)
        ),
        completed_generation_calls=_completed_count(cases, "generation"),
        completed_structural_calls=_completed_count(cases, "structural"),
        completed_quantity_calls=_completed_count(cases, "quantities"),
        completed_summary_calls=_completed_count(cases, "summary"),
        ranks=ranks,
        rows=rows,
        aggregates=aggregates,
        correct_family_rejected=True,
        sensitivity_limited=True,
        unconditional_claim_eligible=False,
        claim_reasons=reasons,
        permitted_claim=None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an authored synthetic B0H report fixture")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        data = reduction_bytes(build_demo_reduction())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("xb") as stream:
            stream.write(data)
        print(
            json.dumps(
                {
                    "evidence_kind": "synthetic_fixture",
                    "publication_eligible": False,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except (OSError, TypeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())

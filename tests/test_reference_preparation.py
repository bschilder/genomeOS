"""Reference count projection controls (reference acquisition design §§5–6)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from genomeos.validation.reference_acquisition_types import AcquisitionWindowReceipt
from genomeos.validation.reference_genotypes import (
    MissingOriginCount,
    PopulationCount,
    QcTally,
    VariantCounts,
)
from genomeos.validation.reference_preparation import (
    check_native_totals,
    prepare_rows,
    validate_acquisition_window_accounting,
    validate_preparation_window_accounting,
)
from genomeos.validation.reference_preparation_types import (
    PreparationStageReceipt,
    PreparationWindowReceipt,
)
from tests.reference_acquisition_fixture import synthetic_window


def _qc() -> QcTally:
    return QcTally(
        (("accepted", 1), ("low_gq", 1), ("missing_gt", 1)),
        (
            ("ad_alt", 1),
            ("ad_arity", 1),
            ("ad_missing", 1),
            ("ad_ref", 1),
            ("dp", 1),
            ("gq", 2),
            ("gt", 3),
        ),
        (MissingOriginCount("gt", "literal_dot", 1),),
    )


def _counts() -> tuple[VariantCounts, ...]:
    return (
        VariantCounts(
            "GRCh38:chr1:101:A:G",
            (
                PopulationCount("Han", "r", 2, 3, 4, 1, 2),
                PopulationCount("NorthernHan", "r", 1, 0, 0, 0, 0),
            ),
            _qc(),
        ),
    )


def test_reference_projection_keeps_unavailable_cell():
    rows = prepare_rows(synthetic_window("chr1"), _counts(), kind="quality")
    keyed = {row.group_id: row for row in rows}
    assert (keyed["NorthernHan"].ac, keyed["NorthernHan"].an) == (0, 0)
    assert keyed["Han"].variant_group == "GRCh38:chr1:101-10100"
    assert keyed["Han"].record_id == json.dumps(
        ["Han", "GRCh38:chr1:101:A:G"], separators=(",", ":")
    )
    check_native_totals(_counts(), (("GRCh38:chr1:101:A:G", 3, 4),))


def test_called_and_quality_tracks_retain_identical_keys_but_distinct_counts():
    window = synthetic_window("chr1")
    called = prepare_rows(window, _counts(), kind="called")
    quality = prepare_rows(window, _counts(), kind="quality")
    assert [row.record_id for row in called] == [row.record_id for row in quality]
    assert [(row.ac, row.an) for row in called] == [(3, 4), (0, 0)]
    assert [(row.ac, row.an) for row in quality] == [(1, 2), (0, 0)]


@pytest.mark.parametrize(
    "native",
    [
        (("GRCh38:chr1:101:A:G", 2, 4),),
        (("GRCh38:chr1:101:G:A", 1, 4),),
        (),
        (("GRCh38:chr1:101:A:G", 3, 4), ("GRCh38:chr1:102:A:C", 0, 0)),
        (("GRCh38:chr1:101:A:G", 3, 4), ("GRCh38:chr1:101:A:G", 3, 4)),
    ],
)
def test_native_identity_or_count_mismatch_refuses(native):
    with pytest.raises(ValueError):
        check_native_totals(_counts(), native)


@pytest.mark.parametrize("kind", ["", "combined", None])
def test_projection_refuses_unknown_track_kind(kind):
    with pytest.raises(ValueError):
        prepare_rows(synthetic_window("chr1"), _counts(), kind=kind)


def test_missing_qc_coverage_is_not_a_valid_hand_control():
    good = _qc()
    with pytest.raises(ValueError):
        replace(good, inspection_totals=())
    with pytest.raises(ValueError):
        replace(good, missing_origins=())


def _stage(stage: str) -> PreparationStageReceipt:
    return PreparationStageReceipt(stage, "not_attempted", "record_invalid", None, None, None)


def _preparation_receipt(window_id: str) -> PreparationWindowReceipt:
    chrom = window_id.split("-", 1)[0]
    return PreparationWindowReceipt(
        window_id,
        chrom,
        "refused",
        "record_invalid",
        None,
        None,
        None,
        (_stage("technical_qc_4117"), _stage("paper_ancestry_exclusion_4094")),
    )


def _acquisition_receipt(window_id: str) -> AcquisitionWindowReceipt:
    chrom = window_id.split("-", 1)[0]
    return AcquisitionWindowReceipt(
        window_id, chrom, "refused", "record_invalid", None, None, None, None, None, None, ()
    )


def _expected_ids() -> tuple[str, ...]:
    return tuple(f"chr{chrom}-s{stratum}" for chrom in range(1, 23) for stratum in range(1, 4))


def test_phase_specific_window_accounting_requires_all_66_exact_ids():
    expected = _expected_ids()
    acquisition = tuple(_acquisition_receipt(value) for value in expected)
    preparation = tuple(_preparation_receipt(value) for value in expected)
    validate_acquisition_window_accounting(expected, acquisition)
    validate_preparation_window_accounting(expected, preparation)
    for changed in (acquisition[:-1], (*acquisition[:-1], acquisition[0])):
        with pytest.raises(ValueError):
            validate_acquisition_window_accounting(expected, changed)
    with pytest.raises(ValueError):
        validate_preparation_window_accounting(expected, preparation[::-1])


def test_phase_receipts_refuse_cross_phase_states_and_wrong_stage_order():
    with pytest.raises(ValueError):
        _acquisition_receipt("chr1-s1").__class__(
            "chr1-s1", "chr1", "counts_prepared", None, 1, 1, None, None, None, None, ()
        )
    with pytest.raises(ValueError):
        PreparationWindowReceipt(
            "chr1-s1",
            "chr1",
            "records_acquired",
            None,
            1,
            1,
            (("retained", 1),),
            (_stage("technical_qc_4117"), _stage("paper_ancestry_exclusion_4094")),
        )
    with pytest.raises(ValueError, match="stage order"):
        replace(
            _preparation_receipt("chr1-s1"),
            stages=(_stage("paper_ancestry_exclusion_4094"), _stage("technical_qc_4117")),
        )

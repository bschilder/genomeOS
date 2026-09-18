"""Original-token genotype controls (reference acquisition design §4)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from genomeos.validation.reference_cohorts import CohortColumn
from genomeos.validation.reference_genotypes import (
    NativeVariantTokens,
    QcTally,
    assess_call,
    check_native_interpretation,
    count_cohort_pair_with_native,
    count_variant,
    plan_cohort_pair,
)
from genomeos.validation.reference_vcf_tokens import SourceRecord


def _record(
    sample_ids: tuple[str, ...] = ("s1", "s2", "s3", "s4"),
    sample_tokens: tuple[str, ...] = (
        "0/1:20:10:2,8",
        "1/1:19:20:.",
        "./.:.:.:.",
        "0/0:20:10:.",
    ),
    *,
    ref: str = "A",
    alt: str = "G",
) -> SourceRecord:
    return SourceRecord(
        "chr1",
        101,
        ref,
        alt,
        "PASS",
        ("GT", "GQ", "DP", "AD"),
        sample_ids,
        sample_tokens,
        1 << 16,
        "a" * 64,
    )


@pytest.mark.parametrize(
    "tokens,dosage,reason",
    [
        ((".", "bad", "bad", "bad"), None, "missing_gt"),
        (("./.", "bad", "bad", "bad"), None, "missing_gt"),
        (("0|1", "20", "10", "2,8"), 1, "accepted"),
        (("1/0", "20", "10", "8,2"), 1, "accepted"),
        (("1/1", "20", "10", "bad"), 2, "accepted"),
        (("0/1", ".", "bad", "bad"), 1, "missing_gq"),
        (("0/1", "19", "bad", "bad"), 1, "low_gq"),
        (("0/1", "20", ".", "bad"), 1, "missing_dp"),
        (("0/1", "20", "9", "bad"), 1, "low_dp"),
        (("0/1", "20", "10", ".,bad,extra"), 1, "missing_het_ad"),
        (("0/1", "20", "10", "1,bad"), 1, "low_het_balance"),
        (("0/1", "20", "10", "8,1"), 1, "low_het_balance"),
    ],
)
def test_preserved_lazy_dispositions(tokens, dosage, reason):
    answer = assess_call(*tokens)
    assert (answer.dosage, answer.disposition) == (dosage, reason)


@pytest.mark.parametrize(
    "tokens",
    [
        ("0/.", "20", "10", "2,8"),
        ("1", "20", "10", "2,8"),
        ("0/1/1", "20", "10", "2,8"),
        ("0/2", "20", "10", "2,8"),
        ("0/1", "-1", "10", "2,8"),
        ("0/1", "20", "x", "2,8"),
        ("0/1", "20", "10", "2,bad"),
        ("0/1", "20", "10", "2,8,0"),
        ("0/1", "20.0", "10", "2,8"),
    ],
)
def test_encountered_invalid_encodings_refuse(tokens):
    with pytest.raises(ValueError):
        assess_call(*tokens)


def test_inspection_coverage_is_truthful():
    assert assess_call(".", "bad", "bad", "bad").inspected_fields == ("gt",)
    assert assess_call("1/1", "20", "10", "bad").inspected_fields == ("gt", "gq", "dp")
    assert assess_call("0/1", "20", "10", "1,bad").inspected_fields == (
        "gt",
        "gq",
        "dp",
        "ad_missing",
        "ad_arity",
        "ad_ref",
    )


def test_native_tokens_join_by_id_not_source_index():
    record = _record(("s1", "s2"), ("0/0:20:10:.", "1/1:20:10:."))
    columns = (
        CohortColumn("s1", 0, "p", "r"),
        CohortColumn("s2", 1, "p", "r"),
    )
    reverse = NativeVariantTokens(
        "GRCh38:chr1:101:A:G",
        ("s2", "s1"),
        ("1/1:20:10:.", "0/0:20:10:."),
    )
    check_native_interpretation(record, columns, reverse)
    with pytest.raises(ValueError):
        check_native_interpretation(record, columns, replace(reverse, sample_ids=("s1", "s2")))
    with pytest.raises(ValueError):
        check_native_interpretation(record, (replace(columns[0], sample_id="s2"), columns[1]), reverse)


@pytest.mark.parametrize(
    "native",
    [
        NativeVariantTokens("GRCh38:chr2:101:A:G", ("s1", "s2"), ("0/0:20:10:.", "1/1:20:10:.")),
        NativeVariantTokens("GRCh38:chr1:101:A:G", ("s1",), ("0/0:20:10:.",)),
        NativeVariantTokens(
            "GRCh38:chr1:101:A:G",
            ("s1", "s2", "s3"),
            ("0/0:20:10:.", "1/1:20:10:.", "0/0:20:10:."),
        ),
    ],
)
def test_native_identity_mismatch_refuses(native):
    record = _record(("s1", "s2"), ("0/0:20:10:.", "1/1:20:10:."))
    columns = (CohortColumn("s1", 0, "p", "r"), CohortColumn("s2", 1, "p", "r"))
    with pytest.raises(ValueError):
        check_native_interpretation(record, columns, native)


def test_native_record_contract_refuses_duplicate_ids_or_length_mismatch():
    with pytest.raises(ValueError, match="unique"):
        NativeVariantTokens("GRCh38:chr1:101:A:G", ("s1", "s1"), (".", "."))
    with pytest.raises(ValueError, match="length"):
        NativeVariantTokens("GRCh38:chr1:101:A:G", ("s1",), ())


def test_native_comparison_is_semantic_and_lazy():
    columns = (CohortColumn("s1", 0, "p", "r"),)
    leading_zero = _record(("s1",), ("0/1:020:010:002,008",))
    check_native_interpretation(
        leading_zero,
        columns,
        NativeVariantTokens("GRCh38:chr1:101:A:G", ("s1",), ("1|0:20:10:2,8",)),
    )
    homozygote = _record(("s1",), ("1/1:20:10:malformed",))
    check_native_interpretation(
        homozygote,
        columns,
        NativeVariantTokens("GRCh38:chr1:101:A:G", ("s1",), ("1/1:20:10:different",)),
    )
    large = _record(("s1",), ("0/1:999999999999999999999:10:2,8",))
    with pytest.raises(ValueError):
        check_native_interpretation(
            large,
            columns,
            NativeVariantTokens("GRCh38:chr1:101:A:G", ("s1",), ("0/1:.:10:2,8",)),
        )


def test_paired_counting_matches_two_independent_cohort_calls():
    record = _record()
    technical = (
        CohortColumn("s1", 0, "p1", "r"),
        CohortColumn("s2", 1, "p1", "r"),
        CohortColumn("s3", 2, "p2", "r"),
        CohortColumn("s4", 3, "p2", "r"),
    )
    paper = (technical[0], technical[3])
    technical_native = NativeVariantTokens(
        "GRCh38:chr1:101:A:G",
        tuple(reversed(record.sample_ids)),
        tuple(reversed(record.sample_tokens)),
    )
    paper_native = NativeVariantTokens(
        "GRCh38:chr1:101:A:G",
        ("s4", "s1"),
        (record.sample_tokens[3], record.sample_tokens[0]),
    )

    paired = count_cohort_pair_with_native(
        record,
        plan_cohort_pair(record.sample_ids, technical, paper),
        technical_native,
        paper_native,
    )

    assert paired == (count_variant(record, technical), count_variant(record, paper))
    check_native_interpretation(record, technical, technical_native)
    check_native_interpretation(record, paper, paper_native)

    malformed = replace(
        technical_native,
        tokens=("0/0:bad:10:.", *technical_native.tokens[1:]),
    )
    with pytest.raises(ValueError, match="native_encoding_refused"):
        count_cohort_pair_with_native(
            record,
            plan_cohort_pair(record.sample_ids, technical, paper),
            malformed,
            paper_native,
        )

    disagreement = replace(
        technical_native,
        tokens=("0/1:20:10:2,8", *technical_native.tokens[1:]),
    )
    with pytest.raises(ValueError, match="native_mismatch"):
        count_cohort_pair_with_native(
            record,
            plan_cohort_pair(record.sample_ids, technical, paper),
            disagreement,
            paper_native,
        )


def test_literal_population_count_control_and_missing_origin():
    columns = (
        CohortColumn("s1", 0, "p1", "r"),
        CohortColumn("s2", 1, "p1", "r"),
        CohortColumn("s3", 2, "p2", "r"),
        CohortColumn("s4", 3, "p2", "r"),
    )
    answer = count_variant(_record(), columns)
    by_population = {value.population: value for value in answer.populations}
    assert (
        by_population["p1"].called_ac,
        by_population["p1"].called_an,
        by_population["p1"].quality_ac,
        by_population["p1"].quality_an,
    ) == (3, 4, 1, 2)
    assert (
        by_population["p2"].called_ac,
        by_population["p2"].called_an,
        by_population["p2"].quality_ac,
        by_population["p2"].quality_an,
    ) == (0, 2, 0, 2)
    assert sum(count for _, count in answer.qc.dispositions) == 4
    assert [(item.field, item.origin, item.count) for item in answer.qc.missing_origins] == [
        ("gt", "literal_dot", 1)
    ]

    without_called_p2 = count_variant(_record(), columns[:-1])
    p2 = {value.population: value for value in without_called_p2.populations}["p2"]
    assert (p2.sample_count, p2.called_ac, p2.called_an, p2.quality_ac, p2.quality_an) == (1, 0, 0, 0, 0)


def test_counting_joins_source_identity_and_tracks_allele_orientation():
    columns = (
        CohortColumn("s2", 0, "p", "r"),
        CohortColumn("s1", 1, "p", "r"),
    )
    permuted = _record(("s2", "s1"), ("1/1:19:20:.", "0/1:20:10:2,8"))
    count = count_variant(permuted, columns).populations[0]
    assert (count.called_ac, count.called_an, count.quality_ac, count.quality_an) == (3, 4, 1, 2)
    with pytest.raises(ValueError, match="identity"):
        count_variant(permuted, (replace(columns[0], sample_id="s1"), columns[1]))

    forward = count_variant(_record(("s1",), ("0/1:20:10:2,8",)), (CohortColumn("s1", 0, "p", "r"),))
    reverse = count_variant(
        _record(("s1",), ("1/0:20:10:8,2",), ref="G", alt="A"),
        (CohortColumn("s1", 0, "p", "r"),),
    )
    assert forward.variant_id == "GRCh38:chr1:101:A:G"
    assert reverse.variant_id == "GRCh38:chr1:101:G:A"


def test_count_records_are_immutable():
    result = count_variant(_record(("s1",), ("0/0:20:10:.",)), (CohortColumn("s1", 0, "p", "r"),))
    with pytest.raises(FrozenInstanceError):
        result.variant_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "format_keys,token,expected",
    [
        (("GT", "GQ", "DP", "AD"), "0/1:.:bad:bad", ("gq", "literal_dot")),
        (("GT", "GQ", "DP", "AD"), "0/1", ("gq", "omitted_trailing")),
        (("GT", "DP", "AD"), "0/1:bad:bad", ("gq", "absent_record_format")),
        (("GT", "GQ", "DP", "AD"), "0/1:20:10:.,bad,extra", ("ad", "literal_dot")),
    ],
)
def test_only_visited_missing_values_contribute_their_exact_origin(format_keys, token, expected):
    record = replace(_record(("s1",), (token,)), format_keys=format_keys)
    result = count_variant(record, (CohortColumn("s1", 0, "p", "r"),))
    assert [(value.field, value.origin) for value in result.qc.missing_origins] == [expected]

    missing_gt = replace(_record(("s1",), ("./.:.:.:.",)), format_keys=("GT", "GQ", "DP", "AD"))
    result = count_variant(missing_gt, (CohortColumn("s1", 0, "p", "r"),))
    assert [(value.field, value.origin) for value in result.qc.missing_origins] == [
        ("gt", "literal_dot")
    ]


def test_qc_tally_refuses_invented_coverage():
    with pytest.raises(ValueError, match="GT inspection"):
        QcTally((("accepted", 1),), (), ())
    with pytest.raises(ValueError, match="missing-origin"):
        QcTally((("missing_gt", 1),), (("gt", 1),), ())

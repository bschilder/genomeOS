"""Exact cohort identity controls (reference acquisition design §2; Atlas §§4, 7.1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from genomeos.validation.reference_cohorts import (
    CohortExclusions,
    QualifiedCohortInputs,
    Sample,
    cohort_columns,
    qualify_cohort_inputs,
    qualify_real_cohorts,
    select_cohorts,
)


def _qualified_synthetic_inputs() -> QualifiedCohortInputs:
    metadata = (
        b"s\tpopulation\thgdp_tgp_meta.Genetic.region\tsample_filters.hard_filtered\n"
        b"bad1\tp\tr\tfalse\n"
        b"bad2\tp\tr\tfalse\n"
        b"s1\tHan\tEast Asia\tfalse\n"
        b"s2\tNorthernHan\tEast Asia\tfalse\n"
    )
    exclusions = (
        b'{"contamination_ids":["bad1","bad2"],"control_id":"control",'
        b'"schema_version":"reference_cohort_exclusions_v1"}\n'
    )
    return qualify_cohort_inputs(
        metadata,
        b"s2\n",
        exclusions,
        b"s1\ns2\n",
        b"s1\n",
        b"synthetic dependency audit\n",
    )


def test_literal_groups_and_reordered_header():
    samples = (
        Sample("s1", "Han", "r1", False),
        Sample("s2", "NorthernHan", "r1", False),
        Sample("s3", "PapuanHighlands", "r2", False),
        Sample("s4", "PapuanSepik", "r2", False),
        Sample("hard", "Han", "r1", True),
        Sample("bad1", "Han", "r1", False),
        Sample("bad2", "Han", "r1", False),
    )
    technical, paper = select_cohorts(
        samples, CohortExclusions("control", ("bad1", "bad2")), ("s2",)
    )
    assert [sample.sample_id for sample in technical.samples] == ["s1", "s2", "s3", "s4"]
    assert [sample.sample_id for sample in paper.samples] == ["s1", "s3", "s4"]
    header = ("s4", "bad1", "s2", "control", "s1", "s3", "hard", "bad2")
    actual = cohort_columns(header, technical)
    assert [(column.sample_id, column.sample_index, column.population) for column in actual] == [
        ("s4", 0, "PapuanSepik"),
        ("s2", 2, "NorthernHan"),
        ("s1", 4, "Han"),
        ("s3", 5, "PapuanHighlands"),
    ]


@pytest.mark.parametrize("outliers", [("unknown",), ("s1", "s1")])
def test_bad_outlier_identity_refuses(outliers):
    samples = (
        Sample("s1", "p", "r", False),
        Sample("bad1", "p", "r", False),
        Sample("bad2", "p", "r", False),
    )
    with pytest.raises(ValueError, match="outlier"):
        select_cohorts(samples, CohortExclusions("control", ("bad1", "bad2")), outliers)


def test_sample_contract_is_immutable_and_refuses_plausible_metadata_substitutions():
    sample = Sample("s1", "Han", "East Asia", False)
    with pytest.raises(FrozenInstanceError):
        sample.population = "Han display"  # type: ignore[misc]
    for population in ("", "NA", " Han", "Han "):
        with pytest.raises(ValueError, match="population"):
            Sample("s1", population, "East Asia", False)
    with pytest.raises(ValueError, match="hard_filtered"):
        Sample("s1", "Han", "East Asia", "false")  # type: ignore[arg-type]


def test_duplicate_metadata_and_population_region_disagreement_refuse_without_exposing_ids():
    duplicate = "private-sample-token"
    with pytest.raises(ValueError, match="metadata") as error:
        select_cohorts(
            (Sample(duplicate, "p", "r", False), Sample(duplicate, "p", "r", False)),
            CohortExclusions("control", ("bad1", "bad2")),
            (),
        )
    assert duplicate not in str(error.value)

    with pytest.raises(ValueError, match="region"):
        select_cohorts(
            (
                Sample("s1", "same-population", "r1", False),
                Sample("s2", "same-population", "r2", False),
                Sample("bad1", "p", "r", False),
                Sample("bad2", "p", "r", False),
            ),
            CohortExclusions("control", ("bad1", "bad2")),
            (),
        )


def test_exclusions_are_distinct_present_and_separate_from_hard_filters_and_control():
    with pytest.raises(ValueError, match="contamination"):
        CohortExclusions("control", ("bad", "bad"))
    with pytest.raises(ValueError, match="sorted"):
        CohortExclusions("control", ("z", "a"))

    ordinary = (Sample("s1", "p", "r", False), Sample("bad1", "p", "r", False))
    with pytest.raises(ValueError, match="contamination"):
        select_cohorts(ordinary, CohortExclusions("control", ("bad1", "bad2")), ())

    hard_overlap = (*ordinary, Sample("bad2", "p", "r", True))
    with pytest.raises(ValueError, match="hard"):
        select_cohorts(hard_overlap, CohortExclusions("control", ("bad1", "bad2")), ())

    control_overlap = (*ordinary, Sample("bad2", "p", "r", False), Sample("control", "p", "r", False))
    with pytest.raises(ValueError, match="control"):
        select_cohorts(control_overlap, CohortExclusions("control", ("bad1", "bad2")), ())


def test_header_join_refuses_duplicate_or_missing_members_without_printing_tokens():
    samples = (
        Sample("private-member", "p", "r", False),
        Sample("bad1", "p", "r", False),
        Sample("bad2", "p", "r", False),
    )
    technical, _ = select_cohorts(
        samples, CohortExclusions("control", ("bad1", "bad2")), ()
    )
    for header in (("private-member", "private-member"), ("someone-else",)):
        with pytest.raises(ValueError) as error:
            cohort_columns(header, technical)
        assert "private-member" not in str(error.value)
        assert "someone-else" not in str(error.value)


@pytest.mark.parametrize("changed_index", range(5))
def test_real_qualification_hashes_every_private_input_before_parsing(changed_index):
    inputs = [b"not-the-real-private-input"] * 5
    inputs[changed_index] = b"\xffchanged"
    with pytest.raises(ValueError, match="input hash"):
        qualify_real_cohorts(*inputs)


def test_qualified_inputs_bind_exact_bytes_cohorts_and_source_columns():
    inputs = _qualified_synthetic_inputs()

    assert [sample.sample_id for sample in inputs.technical.samples] == ["s1", "s2"]
    assert [sample.sample_id for sample in inputs.paper.samples] == ["s1"]
    assert inputs.source_samples == ("bad1", "bad2", "s1", "s2", "control")

    with pytest.raises(ValueError, match="differ from retained bytes"):
        replace(inputs, source_samples=("s1", "s2", "control"))


def test_qualified_inputs_refuse_empty_or_substituted_retained_evidence():
    inputs = _qualified_synthetic_inputs()

    with pytest.raises(ValueError, match="nonempty bytes"):
        replace(inputs, dependency_audit=b"")
    with pytest.raises(ValueError, match="differ from retained bytes"):
        replace(inputs, technical=inputs.paper)

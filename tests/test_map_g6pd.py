"""MAP G6PD survey adapter (design §6, §8, §7.1a).

G6PD is golden test 2 because it exercises what HbS cannot: X-linked inheritance, an enzyme
assay rather than a genotype, and a phenotype produced by many alleles. The tests below are
written around the decisions those differences force, because each one is a place where a
plausible-looking shortcut would produce a wrong allele frequency rather than an error.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import map_g6pd

FIXTURE = Path(__file__).parent / "fixtures" / "map_g6pd_surveys.csv"


@pytest.fixture(scope="module")
def loaded():
    return map_g6pd.load(FIXTURE, "test-g6pd")


def test_allele_counts_are_hemizygous_males(loaded):
    """The whole point of using males: one X, so deficient/total *is* the allele frequency.

    Counting a deficient male as two alleles, or dividing by 2*males as an autosomal adapter
    would, halves or doubles the frequency without ever raising.
    """
    obs, _ = loaded
    row = obs[obs["population_id"] == "map-g6pd-661"].iloc[0]
    assert row["ac"] == 44, "one deficient allele per deficient male"
    assert row["an"] == 226, "one allele per male, not two"


def test_females_are_excluded_rather_than_assumed(loaded):
    """A female recorded 'deficient' may be homozygous or a heterozygote with skewed
    X-inactivation, and those imply very different allele frequencies. The source cannot tell
    them apart, so the surveys that report only females contribute nothing and are counted."""
    obs, report = loaded
    assert "map-g6pd-1723" not in set(obs["population_id"])
    assert report.refusals["female_only_needs_inactivation_model"] >= 1


def test_administrative_centroids_are_placed_at_country_scale_not_refused(loaded):
    """`area_size` is capped near 3,800 km2 across this export, so for a country or province
    centroid it understates location uncertainty by orders of magnitude — Nigeria's Admin0 rows
    report 20 km2 for a country whose equivalent radius is 538 km.

    The fix is to compute the radius from the actual country polygon, not to discard the row:
    refusing these threw away 54,355 hemizygous observations over a metadata gap. §7 places each
    observation as a disc, and a too-large radius makes an observation less influential rather
    than wrong, so erring coarse is the safe direction.
    """
    obs, report = loaded
    kept = set(obs["population_id"])
    assert "map-g6pd-1609" in kept, "Admin0 centroid must be recovered, not refused"
    assert "map-g6pd-148" in kept, "Admin1 centroid must be recovered, not refused"
    assert report.recovered_centroids == 2

    centroid = obs[obs["population_id"] == "map-g6pd-148"].iloc[0]
    assert centroid["radius_km"] > 100.0, "a province centroid is not a 30 km disc"


def test_the_report_separates_empty_rows_from_recoverable_ones(loaded):
    """827 rows of the real export are metadata-only stubs with nothing to recover, so retention
    against *all* rows understates how much usable data is kept. Both figures are reported: the
    meaningful one is retention among rows that carry counts (99% on the real corpus)."""
    obs, report = loaded
    assert report.with_counts <= report.total
    assert report.retained <= report.with_counts
    assert "of surveys that report any counts" in str(report)
    assert "no_counts_reported" in report.refusals


def test_unused_female_alleles_are_counted_so_the_gap_stays_visible(loaded):
    """324 real surveys report both sexes and this adapter uses only the males, leaving ~207,000
    female alleles unused. That is a likelihood limitation, not a data defect, and it is printed
    rather than left for someone to discover."""
    _, report = loaded
    assert report.unused_female_alleles > 0
    assert "female alleles unused" in str(report)


def test_absence_surveys_are_kept_not_dropped(loaded):
    """A survey finding no deficient males is evidence, not a missing value. Dropping zeros
    biases every fitted surface upward exactly where the variant is genuinely absent."""
    obs, _ = loaded
    absent = obs[obs["population_id"] == "map-g6pd-9"]
    assert len(absent) == 1
    assert absent.iloc[0]["ac"] == 0
    assert absent.iloc[0]["an"] == 116


def test_surveys_with_no_counts_at_all_are_refused(loaded):
    obs, report = loaded
    assert "map-g6pd-790" not in set(obs["population_id"])
    assert report.refusals["no_counts_reported"] >= 1


def test_radius_comes_from_the_reported_area(loaded):
    obs, _ = loaded
    row = obs[obs["population_id"] == "map-g6pd-659"].iloc[0]
    assert row["radius_km"] == pytest.approx(math.sqrt(10.0 / math.pi))


def test_the_variant_id_is_a_phenotype_not_a_locus(loaded):
    """G6PD deficiency is ~200 alleles assayed by enzyme activity. A `chr-pos-ref-alt` id would
    assert a single causal allele that these surveys never measured."""
    obs, _ = loaded
    assert set(obs["variant_id"]) == {"phenotype:g6pd-deficiency"}
    assert obs["rsid"].isna().all(), "a composite phenotype has no single dbSNP id"


def test_output_satisfies_the_observations_contract(loaded):
    obs, _ = loaded
    OBSERVATIONS_SCHEMA.validate(obs)


def test_cohorts_key_on_the_study_not_the_site():
    """Keyed by citation, not by site. One cohort level per observation is not a cohort effect —
    it is an observation-level overdispersion term, unidentifiable as the study-level effect
    §7.1d wants and free to absorb the spatial signal the GP exists to explain.

    Tested on the keying rule directly rather than as a count over the fixture, because a handful
    of rows need not contain a repeated study even though the real corpus does (239 cohorts
    across 875 surveys).
    """
    same_a = map_g6pd._cohort_id("Howes et al. 2012", 1)
    same_b = map_g6pd._cohort_id("Howes et al. 2012", 2)
    other = map_g6pd._cohort_id("Nkhoma et al. 2009", 3)
    assert same_a == same_b, "two sites from one study share a cohort"
    assert same_a != other

    # An unattributed row becomes its own singleton rather than being pooled with unrelated
    # surveys, which would invent a shared ascertainment that does not exist.
    assert map_g6pd._cohort_id(None, 7) != map_g6pd._cohort_id(None, 8)


def test_the_report_accounts_for_every_input_row(loaded):
    """A shrinking corpus must be visible. Retained plus refused must equal what went in."""
    obs, report = loaded
    assert report.total == len(pd.read_csv(FIXTURE))
    assert report.retained + sum(report.refusals.values()) == report.total
    assert str(report).startswith(f"{report.retained}/{report.total}")

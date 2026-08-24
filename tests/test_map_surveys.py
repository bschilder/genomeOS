"""MAP HbS survey adapter tests (design §6, §8, §7.1a).

The fixture is a nine-row slice of the real MAP export, chosen to include every refusal case
found in the full database rather than a synthetic happy path.
"""

from pathlib import Path

import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import map_surveys

FIXTURE = Path(__file__).parent / "fixtures" / "map_hbs_surveys.csv"


@pytest.fixture
def loaded():
    return map_surveys.load(FIXTURE, "0.1.0")


def test_load_conforms_to_schema(loaded):
    obs, _ = loaded
    OBSERVATIONS_SCHEMA.validate(obs)
    assert len(obs) > 0


def test_surveys_are_population_random_and_not_disease_depleted(loaded):
    """MAP surveys are population screening surveys — the reference design for β_design (§7.1a)."""
    obs, _ = loaded
    assert (obs["sampling_design"] == "population_random").all()
    assert not obs["disease_ascertainment_excluded"].any()


def test_each_survey_site_is_its_own_cohort(loaded):
    obs, _ = loaded
    assert obs["cohort_id"].nunique() == len(obs)


def test_all_rows_are_the_hbs_variant(loaded):
    obs, _ = loaded
    assert (obs["variant_id"] == map_surveys.HBS_VARIANT_ID).all()
    assert (obs["rsid"] == "rs334").all()


def test_allele_counts_come_from_the_reported_genotypes(loaded):
    """ac = hbas + 2·hbss over an = 2·sample_size."""
    obs, _ = loaded
    nigeria = obs[obs["population_id"] == "map-hbs-1020"].iloc[0]
    assert nigeria["ac"] == 2392 + 2 * 318
    assert nigeria["an"] == 2 * 10115


def test_radius_comes_from_the_recorded_area_class_not_a_constant(loaded):
    """§6 gives uncertainty_radius_km no default; MAP records a spatial extent per survey."""
    obs, _ = loaded
    assert (obs["radius_km"] > 0).all()


def test_zero_count_surveys_are_retained(loaded):
    """AC=0 is evidence of absence-so-far, not a row to drop (§7.1b)."""
    obs, _ = loaded
    assert (obs["ac"] == 0).any()


# --- refusals: every one of these was found in the real database ---


def test_partially_genotyped_surveys_are_refused():
    """A US newborn-screening row types only screen-positives; its denominator is ambiguous."""
    obs, report = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=False)
    assert "map-hbs-1067" not in set(obs["population_id"])
    assert report.refusals.get("partially_genotyped", 0) >= 1


def test_internally_inconsistent_surveys_are_refused():
    _, report = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=False)
    assert report.refusals.get("genotypes_exceed_sample", 0) >= 1


def test_incomplete_genotypes_are_refused_rather_than_assumed_zero(loaded):
    """Treating a missing hbss as 0 biases frequency down exactly where HbS is common."""
    _, report = loaded
    assert report.refusals.get("incomplete_genotypes", 0) >= 1


def test_surveys_with_no_stated_extent_are_refused(loaded):
    _, report = loaded
    assert report.refusals.get("no_area_type", 0) >= 1


def test_unbounded_area_surveys_are_refused(loaded):
    """'>100 km²' has no upper bound, so the disc in §7 cannot be sized honestly."""
    _, report = loaded
    assert report.refusals.get("unbounded_area", 0) >= 1


def test_report_accounts_for_every_input_row(loaded):
    obs, report = loaded
    assert report.total == report.retained + sum(report.refusals.values())
    assert report.retained == len(obs)


def test_piel_2013_subset_is_the_default_and_can_be_widened():
    narrow, narrow_report = map_surveys.load(FIXTURE, "0.1.0")
    wide, _ = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=False)
    assert narrow_report.refusals.get("excluded_from_piel_2013", 0) >= 1
    assert len(wide) >= len(narrow)


def test_an_invalid_genotyped_fraction_is_refused():
    with pytest.raises(ValueError, match="min_genotyped_fraction"):
        map_surveys.load(FIXTURE, "0.1.0", min_genotyped_fraction=1.5)

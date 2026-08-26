"""MAP HbS survey adapter tests (design §6, §8, §7.1a).

The fixture is a nine-row slice of the real MAP export, chosen to include every refusal case
found in the full database rather than a synthetic happy path.
"""

from pathlib import Path

import pandas as pd
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


def test_allele_counts_use_the_typed_denominator_not_the_approached_one(loaded):
    """ac = hbas + 2·hbss over an = 2·(hbaa + hbas + hbss).

    The denominator is the people actually typed, not the people approached. Where a survey typed
    everyone the two are identical; where it did not, dividing observed carriers by people who
    were never tested understates the frequency.
    """
    obs, _ = loaded
    nigeria = obs[obs["population_id"] == "map-hbs-1020"].iloc[0]
    assert nigeria["ac"] == 2392 + 2 * 318
    assert nigeria["an"] == 2 * (6796 + 2392 + 318), "9,506 typed of 10,115 approached"


def test_radius_comes_from_the_recorded_area_class_not_a_constant(loaded):
    """§6 gives uncertainty_radius_km no default; MAP records a spatial extent per survey."""
    obs, _ = loaded
    assert (obs["radius_km"] > 0).all()


def test_zero_count_surveys_are_retained(loaded):
    """AC=0 is evidence of absence-so-far, not a row to drop (§7.1b)."""
    obs, _ = loaded
    assert (obs["ac"] == 0).any()


# --- refusals: every one of these was found in the real database ---


def test_screen_positive_only_surveys_are_refused_but_ordinary_partial_ones_are_not():
    """The line is *how small* the typed share is, not that it is below 100%.

    A US newborn-screening row typed 47,276 of 3,212,374 infants because only screen-positives
    were typed; that subset is enriched for carriers by construction and gives an HbS frequency
    of 0.31 for the United States. Incomplete fieldwork looks nothing like that — the real
    distribution of partial surveys has a median of 82% typed — so refusing every partial survey
    to catch this one discarded eighty-odd ordinary ones.
    """
    obs, report = map_surveys.load(FIXTURE, "0.1.0")
    assert "map-hbs-1067" not in set(obs["population_id"])
    assert report.refusals.get("screen_positives_only", 0) >= 1
    assert report.partially_typed >= 1, "ordinary partial surveys are kept, and counted"


def test_a_small_genotype_excess_is_a_rounded_sample_size_not_broken_data(loaded, tmp_path):
    """All four such rows in the real export exceed `sample_size` by 3-14%, which is what a
    rounded or restated sample size looks like next to exact genotype counts. The genotypes are
    the measurement, so they win and become the denominator. Only an implausible excess signals a
    genuinely inconsistent row.
    """
    obs, _ = loaded
    row = obs[obs["population_id"] == "map-hbs-267"]
    assert len(row) == 1, "a 14% excess is kept, not refused"
    assert row.iloc[0]["an"] == 2 * (164 + 34 + 2), "denominator is the genotypes, not the sample"

    frame = pd.read_csv(FIXTURE)
    frame.loc[frame["id"] == 267, "sample_size"] = 10.0  # genotypes now 20x the sample
    path = tmp_path / "inconsistent.csv"
    frame.to_csv(path, index=False)
    _, report = map_surveys.load(path, "0.1.0")
    assert report.refusals.get("genotypes_exceed_sample", 0) >= 1


def test_genuinely_incomplete_genotypes_are_still_refused(loaded):
    """Where hbss cannot be derived, assuming it is 0 biases frequency down where HbS is common."""
    _, report = loaded
    assert report.refusals.get("incomplete_genotypes", 0) >= 1


def test_surveys_with_no_stated_extent_get_a_coarse_radius_not_a_refusal():
    """Refusing a real measurement over blank metadata discarded 388 usable surveys.

    §7 places each observation as a disc of `radius_km`, so a too-large radius makes a survey
    less influential while a too-small one lets a diffuse survey act as a pinpoint. Erring
    coarse is the safe direction.
    """
    obs, report = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=False)
    assert "no_area_type" not in report.refusals
    assert "unbounded_area" not in report.refusals
    assert (obs["radius_km"] > 0).all()
    assert obs["radius_km"].max() > 5.0, "unclassed surveys should get a coarser extent"


def test_hbss_is_derived_by_subtraction_when_the_sample_is_fully_accounted_for():
    """hbaa + hbas == sample_size fixes hbss at zero arithmetically — no assumption (#89)."""
    obs, report = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=False)
    assert report.derived_hbss >= 1
    assert len(obs) >= 1


def test_report_accounts_for_every_input_row(loaded):
    obs, report = loaded
    assert report.total == report.retained + sum(report.refusals.values())
    assert report.retained == len(obs)


def test_the_piel_subset_filter_is_off_by_default_and_available_for_parity():
    """That flag marks comparability with a published analysis, not data quality.

    The rows outside Piel et al.'s 2013 subset are ordinary surveys they happened not to use, and
    excluding them by default shrank every fitted surface for no scientific reason. Golden test 1
    turns it on because a parity comparison must be scored on the reference's own inputs.
    """
    wide, _ = map_surveys.load(FIXTURE, "0.1.0")
    narrow, narrow_report = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=True)
    assert narrow_report.refusals.get("excluded_from_piel_2013", 0) >= 1
    assert len(wide) >= len(narrow)


def test_an_invalid_genotyped_fraction_is_refused():
    with pytest.raises(ValueError, match="min_genotyped_fraction"):
        map_surveys.load(FIXTURE, "0.1.0", min_genotyped_fraction=1.5)

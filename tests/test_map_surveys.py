from pathlib import Path

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import map_surveys

FIXTURE = Path(__file__).parent / "fixtures" / "map_hbs_surveys.tsv"


def test_load_conforms_to_schema():
    obs = map_surveys.load(FIXTURE, "0.1.0")
    OBSERVATIONS_SCHEMA.validate(obs)
    assert len(obs) == 3


def test_surveys_are_population_random_and_not_disease_depleted():
    """MAP surveys are population screening surveys — the reference design for β_design (§7.1a)."""
    obs = map_surveys.load(FIXTURE, "0.1.0")
    assert (obs["sampling_design"] == "population_random").all()
    assert not obs["disease_ascertainment_excluded"].any()


def test_each_survey_site_is_its_own_cohort():
    obs = map_surveys.load(FIXTURE, "0.1.0")
    assert obs["cohort_id"].nunique() == 3


def test_all_rows_are_the_hbs_variant():
    obs = map_surveys.load(FIXTURE, "0.1.0")
    assert (obs["variant_id"] == map_surveys.HBS_VARIANT_ID).all()
    assert (obs["rsid"] == "rs334").all()

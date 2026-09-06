import pandas as pd
import pandera.errors
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA, SAMPLING_DESIGNS


def _row(**overrides) -> pd.DataFrame:
    row = {
        "variant_id": "chr11-5227002-T-A",
        "rsid": "rs334",
        "population_id": "hgdp-yoruba",
        "lat": 7.38,
        "lon": 3.9,
        "radius_km": 50.0,
        "ac": 12,
        "an": 200,
        "source_record_id": "map-surveys:survey-001",
        "source": "map_surveys",
        "assay": "genotype",
        "date_lower": 0,
        "date_upper": 0,
        "sampling_design": "population_random",
        "disease_ascertainment_excluded": False,
        "cohort_id": "map-hbs-ng-001",
        "ingest_version": "0.1.0",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_valid_observation_passes():
    OBSERVATIONS_SCHEMA.validate(_row())


def test_every_sampling_design_in_the_enum_is_accepted():
    for design in SAMPLING_DESIGNS:
        OBSERVATIONS_SCHEMA.validate(_row(sampling_design=design))


@pytest.mark.parametrize(
    "overrides",
    [
        {"ac": -1},                                # counts are non-negative
        {"an": 0},                                 # an must be > 0
        {"ac": 300, "an": 200},                    # ac may not exceed an
        {"sampling_design": None},                 # mandatory, no default (§7.1)
        {"sampling_design": "unknown"},            # not in enum
        {"disease_ascertainment_excluded": None},  # mandatory
        {"cohort_id": ""},                         # mandatory, non-empty
        {"source_record_id": ""},                  # provenance join key, non-empty
        {"variant_id": "11:5227002T>A"},           # must be chr-pos-ref-alt on GRCh38
        {"date_lower": -5},                        # years BP, non-negative
    ],
)
def test_invalid_observations_are_rejected(overrides):
    with pytest.raises(pandera.errors.SchemaError):
        OBSERVATIONS_SCHEMA.validate(_row(**overrides))


def test_zero_count_observation_is_valid_and_not_dropped():
    """AC=0 with AN=200 is weak evidence, not evidence of absence (design §7.1b)."""
    OBSERVATIONS_SCHEMA.validate(_row(ac=0))

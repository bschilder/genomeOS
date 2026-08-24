import pandas as pd
import pandera.errors
import pytest

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA


def _valid_row(**overrides) -> pd.DataFrame:
    row = {
        "population_id": "hgdp-yoruba",
        "lat": 7.38,
        "lon": 3.9,
        "uncertainty_radius_km": 50.0,
        "location_type": "ancestral",
        "provenance": "10.1126/science.1078311",
        "biocultural_notice": None,
        "registry_version": "0.1.0",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_valid_population_row_passes():
    POPULATIONS_SCHEMA.validate(_valid_row())


@pytest.mark.parametrize(
    "overrides",
    [
        {"lat": 91.0},                       # out of range
        {"lon": -181.0},                     # out of range
        {"uncertainty_radius_km": 0.0},      # must be > 0
        {"uncertainty_radius_km": None},     # no default permitted
        {"location_type": "guessed"},        # not in enum
        {"provenance": ""},                  # must be non-empty
        {"population_id": "HGDP Yoruba"},    # must be slug-cased
    ],
)
def test_invalid_population_rows_are_rejected(overrides):
    with pytest.raises(pandera.errors.SchemaError):
        POPULATIONS_SCHEMA.validate(_valid_row(**overrides))


def test_duplicate_population_id_is_rejected():
    dup = pd.concat([_valid_row(), _valid_row()], ignore_index=True)
    with pytest.raises(pandera.errors.SchemaError):
        POPULATIONS_SCHEMA.validate(dup)


def test_aliases_reject_duplicate_source_label_pair():
    dup = pd.DataFrame(
        [
            {"population_id": "hgdp-yoruba", "source": "hgdp", "label": "Yoruba"},
            {"population_id": "onekg-yri", "source": "hgdp", "label": "Yoruba"},
        ]
    )
    with pytest.raises(pandera.errors.SchemaError):
        ALIASES_SCHEMA.validate(dup)

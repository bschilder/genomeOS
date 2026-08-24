import pandas as pd
import pandera.errors
import pytest

from genomeos.registry.build import AliasCollisionError, build_registry
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA


def _source(pop_id: str, source: str, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    populations = pd.DataFrame(
        [
            {
                "population_id": pop_id,
                "lat": 7.38,
                "lon": 3.9,
                "uncertainty_radius_km": 50.0,
                "location_type": "ancestral",
                "provenance": "doi:test",
                "biocultural_notice": None,
                "registry_version": "0.1.0",
            }
        ]
    )
    aliases = pd.DataFrame([{"population_id": pop_id, "source": source, "label": label}])
    return populations, aliases


def test_build_concatenates_and_validates():
    populations, aliases = build_registry(
        [_source("hgdp-yoruba", "hgdp", "Yoruba"), _source("onekg-yri", "onekg", "YRI")]
    )
    POPULATIONS_SCHEMA.validate(populations)
    ALIASES_SCHEMA.validate(aliases)
    assert len(populations) == 2


def test_same_source_label_mapped_to_two_ids_is_a_hard_error():
    with pytest.raises(AliasCollisionError, match="Yoruba"):
        build_registry(
            [_source("hgdp-yoruba", "hgdp", "Yoruba"), _source("onekg-yri", "hgdp", "Yoruba")]
        )


def test_duplicate_population_id_across_sources_is_a_hard_error():
    # Specific rather than blind: "it raised something" would also be satisfied by an
    # unrelated bug, and the point of this test is that the *uniqueness* check fires.
    with pytest.raises(pandera.errors.SchemaError):
        build_registry(
            [_source("hgdp-yoruba", "hgdp", "Yoruba"), _source("hgdp-yoruba", "afnd", "Yoruba*")]
        )

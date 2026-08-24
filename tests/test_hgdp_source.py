from pathlib import Path

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA
from genomeos.registry.sources import hgdp

FIXTURE = Path(__file__).parent / "fixtures" / "hgdp_populations.tsv"


def test_load_conforms_to_schemas():
    populations, aliases = hgdp.load(FIXTURE, registry_version="0.1.0")
    POPULATIONS_SCHEMA.validate(populations)
    ALIASES_SCHEMA.validate(aliases)


def test_load_slugs_ids_and_preserves_original_label_as_alias():
    populations, aliases = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert set(populations["population_id"]) >= {"hgdp-yoruba", "hgdp-sardinian"}
    yoruba = aliases[aliases["population_id"] == "hgdp-yoruba"].iloc[0]
    assert yoruba["source"] == "hgdp"
    assert yoruba["label"] == "Yoruba"


def test_hgdp_coordinates_are_ancestral_with_a_stated_radius():
    populations, _ = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert (populations["location_type"] == "ancestral").all()
    assert (populations["uncertainty_radius_km"] > 0).all()


def test_hgdp_entries_carry_a_biocultural_notice():
    populations, _ = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert populations["biocultural_notice"].notna().all()

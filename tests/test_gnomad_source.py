from pathlib import Path

import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import gnomad_hgdp_1kg as gnomad
from genomeos.registry.build import build_registry
from genomeos.registry.sources import hgdp

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def registry():
    return build_registry([hgdp.load(FIXTURES / "hgdp_populations.tsv", "0.1.0")])


def test_load_conforms_to_schema(registry):
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    OBSERVATIONS_SCHEMA.validate(obs)
    assert len(obs) == 4


def test_coordinates_and_radius_come_from_the_registry(registry):
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    yoruba = obs[obs["population_id"] == "hgdp-yoruba"].iloc[0]
    assert yoruba["lat"] == pytest.approx(7.38)
    assert yoruba["radius_km"] == pytest.approx(50.0)


def test_gnomad_is_marked_disease_depleted_healthy_reference(registry):
    """gnomAD excludes severe pediatric disease cases and their first-degree relatives (§7.1a)."""
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    assert (obs["sampling_design"] == "healthy_reference").all()
    assert obs["disease_ascertainment_excluded"].all()


def test_zero_count_rows_are_retained(registry):
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    assert (obs["ac"] == 0).sum() == 2


def test_unmapped_population_label_is_a_hard_error(tmp_path, registry):
    populations, aliases = registry
    bad = tmp_path / "bad.tsv"
    bad.write_text(
        "variant_id\trsid\tpop_label\tAC\tAN\nchr11-5227002-T-A\trs334\tAtlantis\t1\t100\n"
    )
    with pytest.raises(gnomad.UnmappedPopulationError, match="Atlantis"):
        gnomad.load(bad, populations, aliases, "0.1.0")

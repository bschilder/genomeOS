"""AFND registry adapter (design §6, §7.1, P0).

The fixture is nine hand-written rows in AFND's documented population-page format. The first
three transcribe the public metadata of real AFND populations — pop_id 1986, 2800 and 1500 — so
the parsing is checked against coordinates AFND actually prints; no frequency data is included,
and the corpus itself is not redistributed (see the adapter docstring on the licence). The rows
named "Example ..." are constructed to exercise one refusal or derivation each.
"""

import math
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.schema import SAMPLING_DESIGNS
from genomeos.registry.build import build_registry
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA
from genomeos.registry.sources import afnd, hgdp

FIXTURE = Path(__file__).parent / "fixtures" / "afnd_populations.tsv"
HGDP_FIXTURE = Path(__file__).parent / "fixtures" / "hgdp_populations.tsv"


@pytest.fixture(scope="module")
def loaded() -> tuple[pd.DataFrame, pd.DataFrame, afnd.RegistryReport]:
    return afnd.load(FIXTURE, registry_version="0.1.0")


def _loaded():
    return afnd.load(FIXTURE, registry_version="0.1.0")


def _row(populations: pd.DataFrame, pop_id: str) -> pd.Series:
    return populations.set_index("population_id").loc[pop_id]


def test_load_conforms_to_schemas(loaded):
    populations, aliases, _ = loaded
    POPULATIONS_SCHEMA.validate(populations)
    ALIASES_SCHEMA.validate(aliases)


def test_population_id_is_the_afnd_accession_and_the_name_is_the_alias(loaded):
    populations, aliases, _ = loaded
    assert "afnd-1986" in set(populations["population_id"])
    alias = aliases[aliases["population_id"] == "afnd-1986"].iloc[0]
    assert alias["source"] == "afnd"
    assert alias["label"] == "Peru Lamas City Lama"


def test_coordinates_are_parsed_from_afnds_sexagesimal_form(loaded):
    populations, _, _ = loaded
    peru = _row(populations, "afnd-1986")
    assert peru["lat"] == pytest.approx(-(6 + 25 / 60))
    assert peru["lon"] == pytest.approx(-(76 + 32 / 60))
    # Seconds are read where AFND supplies them.
    rome = _row(populations, "afnd-9003")
    assert rome["lat"] == pytest.approx(41 + 54 / 60 + 30 / 3600)
    assert rome["lon"] == pytest.approx(12 + 29 / 60 + 12 / 3600)


def test_radius_comes_from_afnds_own_settlement_class(loaded):
    populations, _, _ = loaded
    assert _row(populations, "afnd-2800")["uncertainty_radius_km"] == 50.0  # Rural
    assert _row(populations, "afnd-1986")["uncertainty_radius_km"] == 100.0  # Urban
    assert _row(populations, "afnd-9002")["uncertainty_radius_km"] == 250.0  # Urban and Rural


def test_degree_precision_widens_the_radius_past_the_settlement_class(loaded):
    """A coordinate cannot be more certain than the way it was written down (§7)."""
    populations, _, _ = loaded
    degrees_only = _row(populations, "afnd-9001")
    assert degrees_only["uncertainty_radius_km"] > afnd.SAMPLING_AREA_RADIUS_KM["rural"]
    expected = afnd.precision_radius_km(
        afnd.Coordinate(degrees=-8.0, quantum_deg=1.0), afnd.Coordinate(143.0, 1.0)
    )
    assert degrees_only["uncertainty_radius_km"] == pytest.approx(expected)
    assert expected == pytest.approx(78.2, abs=0.5)


def test_no_radius_is_below_its_own_coordinate_precision(loaded):
    populations, _, _ = loaded
    assert (populations["uncertainty_radius_km"] > 0).all()
    arcminute = afnd.precision_radius_km(
        afnd.Coordinate(-6.4167, 1 / 60), afnd.Coordinate(-76.5333, 1 / 60)
    )
    assert _row(populations, "afnd-1986")["uncertainty_radius_km"] >= arcminute


def test_trailing_zero_minutes_are_read_as_degree_precision():
    """`8º 0' N` is a coordinate rounded to the degree, not an exact arcminute."""
    assert afnd.parse_dms("8º 0' N", axis="lat") == afnd.Coordinate(8.0, 1.0)
    assert afnd.parse_dms("8º 55' S", axis="lat") == afnd.Coordinate(-(8 + 55 / 60), 1 / 60)
    assert afnd.parse_dms("41º 54' 30'' N", axis="lat").quantum_deg == pytest.approx(1 / 3600)


def test_parse_dms_rejects_the_wrong_axis_and_out_of_range_degrees():
    assert afnd.parse_dms("76º 32' W", axis="lat") is None  # a longitude hemisphere
    assert afnd.parse_dms("6º 25' S", axis="lon") is None
    assert afnd.parse_dms("100º 0' N", axis="lat") is None
    assert afnd.parse_dms("", axis="lat") is None
    assert afnd.parse_dms("6.42 S", axis="lat") is None


def test_precision_radius_shrinks_toward_the_poles():
    equator = afnd.precision_radius_km(afnd.Coordinate(0.0, 1.0), afnd.Coordinate(0.0, 1.0))
    polar = afnd.precision_radius_km(afnd.Coordinate(80.0, 1.0), afnd.Coordinate(0.0, 1.0))
    assert polar < equator
    assert equator == pytest.approx(0.5 * math.hypot(111.12, 111.12), rel=1e-3)


def test_unknown_settlement_class_takes_the_widest_extent_not_a_refusal():
    """529 of AFND's 1,821 populations state no settlement class, and refusing them discarded 29%
    of the corpus over one metadata field while their coordinates were perfectly good.

    This is not the fabricated radius §6 forbids: it is the **widest class in AFND's own stated
    vocabulary**, chosen because an unstated settlement type could genuinely be any of them and
    the widest is the only choice that cannot understate. §7 places each population as a disc, so
    erring coarse makes it less influential rather than wrongly precise — the same reasoning
    applied to MAP's administrative centroids.
    """
    populations, _, _ = _loaded()
    row = _row(populations, "afnd-1500")
    assert row["uncertainty_radius_km"] == afnd.UNKNOWN_SETTLEMENT_RADIUS_KM
    assert afnd.UNKNOWN_SETTLEMENT_RADIUS_KM == max(afnd.SAMPLING_AREA_RADIUS_KM.values())


def test_unrecorded_ascertainment_is_counted_not_refused_at_the_registry():
    """A population must not be dropped from the *registry* over a field the registry never stores.

    `POPULATIONS_SCHEMA` has no ascertainment columns — they belong to `OBSERVATIONS_SCHEMA` at
    P1 — so refusing here cost 160 populations for nothing. The question is real and is enforced
    where it applies: `sampling_design_for` still returns None for an unmappable source, and P1
    must refuse that population's *observations* rather than guess a design.
    """
    populations, _, report = _loaded()
    assert "afnd-9004" in set(populations["population_id"])
    assert report.unmapped_ascertainment >= 1
    assert afnd.sampling_design_for("Other") is None, "P1's guard must still hold"


def test_unreadable_coordinate_and_missing_accession_are_refused(loaded):
    populations, _, report = loaded
    ids = set(populations["population_id"])
    assert "afnd-9005" not in ids
    assert report.refusals["unreadable_latitude"] == 1
    assert report.refusals["unusable_pop_id"] == 1


def test_every_input_row_is_either_retained_or_counted_as_a_refusal(loaded):
    """§12: rows are refused with a stated reason, never silently dropped."""
    _, _, report = loaded
    assert report.total == 9
    assert report.retained == 7
    assert report.retained + sum(report.refusals.values()) == report.total
    assert set(report.refusals) <= set(afnd.REFUSAL_REASONS)
    assert "refused" in str(report)


def test_grandparent_residence_is_the_only_ancestral_location_type(loaded):
    populations, _, _ = loaded
    assert _row(populations, "afnd-1986")["location_type"] == "ancestral"
    # Two generations is not the same claim, and neither is "Not Known" (§4).
    assert _row(populations, "afnd-9003")["location_type"] == "sampling"
    assert _row(populations, "afnd-2800")["location_type"] == "sampling"


def test_disease_cohorts_are_recorded_rather_than_refused(loaded):
    """A clinical cohort is a valid observation whose bias §7.1's β_design corrects."""
    populations, _, _ = loaded
    assert "afnd-9003" in set(populations["population_id"])
    assert afnd.sampling_design_for("Disease Study Patients") == ("clinical_case", False)


def test_donor_registries_are_recorded_as_disease_depleted():
    """Donor-eligibility criteria remove significant disease by policy (§6, §7.1a)."""
    for source in ("Bone Marrow Registry", "Blood Donor", "Stem Cell Donors"):
        design, excluded = afnd.sampling_design_for(source)
        assert design == "healthy_reference"
        assert excluded is True
    assert afnd.sampling_design_for("Controls for Disease Study") == ("clinical_control", True)


def test_anthropology_studies_do_not_claim_the_population_random_anchor():
    """β_design is identified by contrast against `population_random`; do not dilute it."""
    assert afnd.sampling_design_for("Anthropology Study") == ("convenience", False)


def test_every_mapped_design_is_a_valid_observations_sampling_design():
    designs = {design for design, _ in afnd.SAMPLING_DESIGN_BY_SOURCE.values()}
    assert designs <= set(SAMPLING_DESIGNS)


def test_entries_carry_a_biocultural_notice_and_a_resolvable_provenance(loaded):
    populations, _, _ = loaded
    assert populations["biocultural_notice"].str.contains("CARE Principles").all()
    peru = _row(populations, "afnd-1986")
    assert peru["provenance"].startswith(afnd.PROVENANCE_DOI)
    # `pop_name` is the accession parameter: AFND's public navigation keys on the name,
    # not the numeric id, and that is the key the frequency redistributions share.
    assert "pop_name=1986" in peru["provenance"]


def test_missing_required_column_is_a_hard_error(tmp_path):
    truncated = tmp_path / "afnd.tsv"
    truncated.write_text("pop_id\tpopulation\tlatitude\tlongitude\n1\tX\t1º 0' N\t1º 0' E\n")
    with pytest.raises(ValueError, match="sample_source"):
        afnd.load(truncated, registry_version="0.1.0")


def test_afnd_composes_with_hgdp_into_one_registry(loaded):
    populations, aliases, _ = loaded
    merged_populations, merged_aliases = build_registry(
        [hgdp.load(HGDP_FIXTURE, "0.1.0"), (populations, aliases)]
    )
    POPULATIONS_SCHEMA.validate(merged_populations)
    ALIASES_SCHEMA.validate(merged_aliases)
    assert set(merged_aliases["source"]) == {"hgdp", "afnd"}

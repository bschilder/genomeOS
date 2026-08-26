"""Country identity and the H3 → country rollup (design §9, §10, §11).

The rollup is the join that three sources meet on, so most of these assertions are about the
*failure* modes: an unresolved name, an unassigned cell, an enclave assigned to the country that
surrounds it. Each of them silently understates a national total rather than raising, which is
why they are tested rather than argued about.
"""

import pandas as pd
import pytest

pytest.importorskip("matplotlib")

from genomeos.geo.countries import (  # noqa: E402
    ISO3_ALIASES,
    NATURAL_EARTH_ISO3_FIXUPS,
    UnknownCountryError,
    assign_countries,
    country_at,
    feature_iso3,
    resolve_iso3,
    rollup_by_country,
)
from genomeos.geo.h3util import cell_for  # noqa: E402
from genomeos.reference.piel2013 import national_estimates  # noqa: E402
from genomeos.viz.basemap import load_countries  # noqa: E402

# Accra, Maseru (inside the Lesotho-shaped hole in South Africa), Ibadan, mid-Atlantic.
PLACES = {
    "GHA": (5.55, -0.20),
    "LSO": (-29.31, 27.48),
    "NGA": (7.38, 3.90),
    None: (0.0, -30.0),
}


# --- name reconciliation (#94: ISO3 throughout, never name matching) ---


@pytest.mark.parametrize(
    "name",
    [
        "Tanzania",  # Natural Earth
        "Tanzania, United Republic of",  # Piel et al. / ISO 3166
        "United Republic of Tanzania",  # MAP
        "TZA",  # already a code
    ],
)
def test_the_same_country_resolves_from_every_source_spelling(name):
    assert resolve_iso3(name) == "TZA"


@pytest.mark.parametrize("name", ["Côte d'Ivoire", "Cote d'Ivoire", "Ivory Coast"])
def test_accents_and_punctuation_do_not_change_identity(name):
    assert resolve_iso3(name) == "CIV"


@pytest.mark.parametrize("name", ["Guinea‐Bissau", "Guinea-Bissau", "guinea bissau"])
def test_the_appendix_unicode_hyphen_resolves_like_a_plain_one(name):
    """The Piel appendix writes U+2010, not hyphen-minus; a byte comparison misses it."""
    assert resolve_iso3(name) == "GNB"


def test_an_unresolvable_name_raises_and_says_which_one():
    """§12: never a silent drop. A null here removes the country from every downstream total."""
    with pytest.raises(UnknownCountryError, match="Freedonia"):
        resolve_iso3("Freedonia")


def test_every_published_country_resolves():
    """Golden test 1's denominator is all 191 published countries, so all 191 must have a code."""
    published = national_estimates()
    assert published["iso3"].notna().all()
    assert published["iso3"].is_unique
    for country, iso3 in zip(published["country"], published["iso3"], strict=True):
        assert resolve_iso3(country) == iso3


def test_every_natural_earth_name_resolves_to_its_own_code():
    """Cross-checks the hand-written table against Natural Earth's codes for ~170 countries."""
    for feature in load_countries():
        assert resolve_iso3(feature["properties"]["name"]) == feature_iso3(feature)


def test_natural_earths_minus_99_codes_are_decided_rather_than_passed_through():
    """France and Norway have ISO3 codes; `-99` is a Natural Earth artifact, not a fact."""
    by_name = {f["properties"]["name"]: feature_iso3(f) for f in load_countries()}
    assert by_name["France"] == "FRA"
    assert by_name["Norway"] == "NOR"
    assert set(NATURAL_EARTH_ISO3_FIXUPS) <= set(by_name)


def test_the_alias_table_holds_no_contradictions():
    for name, iso3 in ISO3_ALIASES.items():
        assert resolve_iso3(name) == iso3
        assert len(iso3) == 3 and iso3.isupper()


# --- assignment (§9's "within each country's boundary") ---


@pytest.mark.parametrize("iso3,latlon", PLACES.items())
def test_a_point_is_assigned_to_the_country_it_falls_in(iso3, latlon):
    assert country_at([latlon[0]], [latlon[1]])[0] == iso3


def test_an_enclave_beats_the_country_that_surrounds_it():
    """Maseru is inside South Africa's exterior ring and inside the hole cut for Lesotho.

    Without subtracting holes the answer depends on iteration order, which is how an enclave
    quietly joins its neighbour's national total.
    """
    assert country_at([-29.31], [27.48])[0] == "LSO"


def test_open_ocean_is_no_country_rather_than_an_error():
    """`None` is a real answer; it is the aggregation step that refuses to proceed with it."""
    assert country_at([0.0], [-30.0])[0] is None


def test_assignment_returns_one_row_per_cell_in_order():
    cells = [cell_for(lat, lon, 4) for lat, lon in PLACES.values()]
    frame = assign_countries(cells)
    assert list(frame["h3_index"]) == cells
    assert [None if pd.isna(value) else value for value in frame["iso3"]] == list(PLACES)


def test_assignment_is_deterministic():
    cells = [cell_for(lat, lon, 4) for lat, lon in PLACES.values()]
    assert assign_countries(cells).equals(assign_countries(cells))


def test_assignment_of_nothing_is_refused():
    with pytest.raises(ValueError, match="at least one cell"):
        assign_countries([])


# --- rollup (§10: masked cells excluded, excluded fraction returned) ---


def _cells(**overrides) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "h3_index": ["a", "b", "c", "d"],
            "iso3": ["GHA", "GHA", "NGA", "NGA"],
            "support": ["observed", "unknown", "observed", "interpolated"],
            "post_mean": [0.10, 0.99, 0.20, 0.30],
        }
    )
    return frame.assign(**overrides)


def test_masked_cells_are_excluded_and_the_fraction_is_reported():
    rolled = rollup_by_country(_cells()).set_index("iso3")
    assert rolled.loc["GHA", "value"] == pytest.approx(0.10)  # the `unknown` cell is not averaged
    assert rolled.loc["GHA", "unmapped_fraction"] == pytest.approx(0.5)
    assert rolled.loc["NGA", "unmapped_fraction"] == 0.0


def test_a_country_with_nothing_but_masked_cells_gets_no_number():
    frame = _cells(support=["unknown", "prior_dominated", "observed", "observed"])
    rolled = rollup_by_country(frame).set_index("iso3")
    assert pd.isna(rolled.loc["GHA", "value"])
    assert rolled.loc["GHA", "unmapped_fraction"] == 1.0


def test_sums_and_means_are_both_available_for_the_choropleth():
    """#61's statistic selector; the aggregation itself is mask.aggregate_cells either way."""
    rolled = rollup_by_country(_cells(), statistic="sum").set_index("iso3")
    assert rolled.loc["NGA", "value"] == pytest.approx(0.50)


def test_cells_with_no_country_are_a_hard_error_not_a_quiet_drop():
    frame = _cells(iso3=["GHA", None, "NGA", "NGA"])
    with pytest.raises(ValueError, match="no iso3"):
        rollup_by_country(frame)


def test_a_frame_without_an_iso3_column_is_refused():
    with pytest.raises(ValueError, match="iso3"):
        rollup_by_country(_cells().drop(columns=["iso3"]))

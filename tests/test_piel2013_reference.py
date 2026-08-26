"""Golden test 1 target data (design §8).

These assertions are transcription checks. A PDF table parse that silently drops or merges rows
would surface later as an apparent model failure in #45, so the target is validated on its own.
"""

import pytest

from genomeos.reference.piel2013 import (
    GLOBAL_AS_NEONATES,
    GLOBAL_SS_NEONATES,
    national_estimates,
)


@pytest.fixture(scope="module")
def targets():
    return national_estimates()


def test_every_country_in_web_table_1_was_extracted(targets):
    assert len(targets) == 191
    assert targets["country"].is_unique


def test_every_row_carries_an_iso3_code(targets):
    """The parity join is on ISO3, not on names (#94). A blank code would drop the country.

    Two rows sharing a code is the worse failure: they would merge on every downstream join and
    one country's burden would be reported under another's name.
    """
    assert targets["iso3"].notna().all()
    assert targets["iso3"].is_unique
    assert targets["iso3"].str.fullmatch(r"[A-Z]{3}").all()


def test_iso3_spot_checks_across_the_naming_conventions(targets):
    """The appendix uses ISO 3166 names as they stood in 2010, which is not how anyone spells
    them: Natural Earth says "Tanzania", MAP says "United Republic of Tanzania"."""
    codes = targets.set_index("country")["iso3"]
    assert codes["Nigeria"] == "NGA"
    assert codes["India"] == "IND"
    assert codes["Congo, the Democratic Republic of the"] == "COD"
    assert codes["Congo"] == "COG"
    assert codes["Tanzania, United Republic of"] == "TZA"
    assert codes["Côte d'Ivoire"] == "CIV"
    assert codes["Swaziland"] == "SWZ"  # eSwatini since 2018; the published row predates it
    assert codes["Libyan Arab Jamahiriya"] == "LBY"


def test_point_estimates_lie_inside_their_published_iqrs(targets):
    for stem in ("as", "ss"):
        point = targets[f"{stem}_neonates_per_year"]
        assert (targets[f"{stem}_iqr_lower"] <= point).all()
        assert (point <= targets[f"{stem}_iqr_upper"]).all()
    assert (targets["hbs_af_iqr_lower"] <= targets["hbs_af"]).all()
    assert (targets["hbs_af"] <= targets["hbs_af_iqr_upper"]).all()


def test_allele_frequencies_are_biologically_plausible(targets):
    assert targets["hbs_af"].max() <= 0.30, "HbS peaks near 0.20; higher implies a parse error"
    assert (targets["hbs_af"] >= 0.0).all()


def test_spot_check_against_the_published_table(targets):
    """Hand-checked against appendix Web Table 1, p.31."""
    drc = targets[targets["country"] == "Congo, the Democratic Republic of the"].iloc[0]
    assert drc["surveys"] == 11
    assert drc["hbs_af"] == pytest.approx(0.165)
    assert drc["as_neonates_per_year"] == 489_745
    assert drc["as_iqr_lower"] == 455_733
    assert drc["ss_neonates_per_year"] == 38_217
    assert drc["ss_iqr_upper"] == 44_870

    cuba = targets[targets["country"] == "Cuba"].iloc[0]
    assert cuba["as_neonates_per_year"] == 6_578
    assert cuba["ss_neonates_per_year"] == 240


def test_summed_national_medians_fall_below_the_published_global_posterior(targets):
    """Medians do not sum (§8). This documents the gap so it is never read as a model failure.

    If a future extraction made these sums *match* the global figures, that would mean the table
    had been misread — not that the transcription improved.
    """
    summed_as = targets["as_neonates_per_year"].sum()
    summed_ss = targets["ss_neonates_per_year"].sum()
    assert summed_as < GLOBAL_AS_NEONATES[0]
    assert summed_ss < GLOBAL_SS_NEONATES[0]
    assert summed_as / GLOBAL_AS_NEONATES[0] > 0.90, "a >10% shortfall would suggest dropped rows"
    assert summed_ss / GLOBAL_SS_NEONATES[0] > 0.90


def test_high_burden_countries_are_present(targets):
    """Parity is scored where HbS is common, so these must not be missing."""
    countries = set(targets["country"])
    for expected in ("Nigeria", "India", "Congo, the Democratic Republic of the", "Ghana"):
        assert expected in countries

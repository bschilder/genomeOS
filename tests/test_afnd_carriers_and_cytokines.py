"""KIR carrier frequencies and cytokine genotype counting (design §6, §12; #133).

The two families AFND publishes that are not row-wise allele frequencies. The tests target the
places each can silently produce a wrong number: a unit read as the wrong scale, a genotype set
completed by assumption rather than arithmetic, and a carrier frequency landing in a table whose
denominator means chromosomes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.schema import CARRIER_OBSERVATIONS_SCHEMA
from genomeos.observations.sources import afnd_carriers, afnd_cytokines

FIXTURES = Path(__file__).parent / "fixtures"
POPULATIONS = FIXTURES / "afnd_populations.tsv"
PLACED = "Peru Lamas City Lama"


def _table(tmp_path, rows) -> Path:
    path = tmp_path / "freq.tsv"
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)
    return path


def test_a_full_genotype_triple_gives_the_allele_frequency_by_counting(tmp_path):
    """p(B) = f(BB) + f(AB)/2. Arithmetic, with no Hardy-Weinberg anywhere in it.

    CC 25%, CG 50%, GG 25% -> p(G) = 0.25 + 0.25 = 0.50, from 100 individuals = 100 of 200.
    A mean of exactly 0.50 is a tie, so the alphabetical choice stands (see MINOR_ALLELE_RULE).
    """
    path = _table(tmp_path, {
        "group": ["cyt"] * 3,
        "gene": ["IL-6-"] * 3,
        "allele": ["IL-6/ - 174 CC", "IL-6/ - 174 CG", "IL-6/ - 174 GG"],
        "population": [PLACED] * 3,
        "indivs_over_n": ["25.0", "50.0", "25.0"],
        "alleles_over_2n": ["", "", ""],
        "n": ["100", "100", "100"],
    })
    obs, _ = afnd_cytokines.load(path, POPULATIONS, "test")
    assert len(obs) == 1
    row = obs.iloc[0]
    assert row["variant_id"] == "cyt:il-6-174-g"
    assert (row["ac"], row["an"]) == (100, 200)


def test_an_incomplete_genotype_set_is_refused_not_completed(tmp_path):
    """Two classes cannot give an allele frequency without assuming HWE, so they give none."""
    path = _table(tmp_path, {
        "group": ["cyt"] * 2,
        "gene": ["IL-6-"] * 2,
        "allele": ["IL-6/ - 174 CC", "IL-6/ - 174 GG"],
        "population": [PLACED] * 2,
        "indivs_over_n": ["40.0", "60.0"],
        "alleles_over_2n": ["", ""],
        "n": ["100", "100"],
    })
    obs, report = afnd_cytokines.load(path, POPULATIONS, "test")
    assert obs.empty
    assert report.refusals["incomplete_genotype_set"] == 1


def test_genotype_percentages_that_do_not_sum_to_100_are_refused(tmp_path):
    """A triple summing to 60 is a missing class or a unit error. Either must fail (§12)."""
    path = _table(tmp_path, {
        "group": ["cyt"] * 3,
        "gene": ["IL-6-"] * 3,
        "allele": ["IL-6/ - 174 CC", "IL-6/ - 174 CG", "IL-6/ - 174 GG"],
        "population": [PLACED] * 3,
        "indivs_over_n": ["20.0", "20.0", "20.0"],
        "alleles_over_2n": ["", "", ""],
        "n": ["100", "100", "100"],
    })
    obs, report = afnd_cytokines.load(path, POPULATIONS, "test")
    assert obs.empty
    assert report.refusals["genotype_percentages_do_not_sum_to_100"] == 1


def test_kir_presence_becomes_a_carrier_frequency_over_individuals(tmp_path):
    """The denominator is people, and the percentage is converted exactly once."""
    path = _table(tmp_path, {
        "group": ["kir"],
        "gene": ["2DL1"],
        "allele": ["2DL1"],
        "population": [PLACED],
        "indivs_over_n": ["95.0"],
        "alleles_over_2n": [""],
        "n": ["200"],
    })
    carriers, _ = afnd_carriers.load(path, POPULATIONS, "test")
    assert len(carriers) == 1
    row = carriers.iloc[0]
    assert row["variant_id"] == "kir:2dl1"
    # 95% of 200 individuals, NOT 95% of 400 chromosomes
    assert (row["carriers"], row["n_individuals"]) == (190, 200)
    assert "ac" not in carriers.columns and "an" not in carriers.columns


def test_carrier_output_validates_against_its_own_schema(tmp_path):
    """It must not be possible to hand carrier counts to the allele-frequency schema."""
    path = _table(tmp_path, {
        "group": ["kir"], "gene": ["3DL1"], "allele": ["3DL1"], "population": [PLACED],
        "indivs_over_n": ["50.0"], "alleles_over_2n": [""], "n": ["100"],
    })
    carriers, _ = afnd_carriers.load(path, POPULATIONS, "test")
    CARRIER_OBSERVATIONS_SCHEMA.validate(carriers)
    assert set(carriers.columns) >= {"carriers", "n_individuals"}


def test_allele_level_kir_rows_are_not_read_as_presence(tmp_path):
    """`3DL1*007` is a real allele frequency and belongs to the other adapter."""
    path = _table(tmp_path, {
        "group": ["kir", "kir"],
        "gene": ["3DL1", "3DL1"],
        "allele": ["3DL1", "3DL1*007"],
        "population": [PLACED, PLACED],
        "indivs_over_n": ["80.0", "10.0"],
        "alleles_over_2n": ["", "0.1"],
        "n": ["100", "100"],
    })
    carriers, report = afnd_carriers.load(path, POPULATIONS, "test")
    assert list(carriers["variant_id"]) == ["kir:3dl1"]
    assert report.total_rows == 1


def test_a_percentage_above_100_is_refused_rather_than_rescaled(tmp_path):
    """`indivs_over_n` above 100 means the units changed. Rescaling silently would misstate
    every carrier frequency in the release."""
    path = _table(tmp_path, {
        "group": ["kir"], "gene": ["2DL1"], "allele": ["2DL1"], "population": [PLACED],
        "indivs_over_n": ["950.0"], "alleles_over_2n": [""], "n": ["200"],
    })
    with pytest.raises(ValueError, match="above 100"):
        afnd_carriers.load(path, POPULATIONS, "test")


def test_the_minor_allele_is_reported_not_the_alphabetical_one(tmp_path):
    """Choosing alphabetically maps the MAJOR allele for about half of loci, and a major-allele
    surface is flat by construction — TNF-alpha -308 rendered as a solid 0.9 field worldwide
    before this rule existed. The minor allele carries the geographic signal.

    AA 81%, AG 18%, GG 1% -> p(G) = 0.01 + 0.09 = 0.10, so G is minor and G is reported.
    Alphabetically G is still second here, so the id is unchanged; the next test flips it.
    """
    path = _table(tmp_path, {
        "group": ["cyt"] * 3,
        "gene": ["IL-6-"] * 3,
        "allele": ["IL-6/ - 174 AA", "IL-6/ - 174 AG", "IL-6/ - 174 GG"],
        "population": [PLACED] * 3,
        "indivs_over_n": ["81.0", "18.0", "1.0"],
        "alleles_over_2n": ["", "", ""],
        "n": ["100", "100", "100"],
    })
    obs, _ = afnd_cytokines.load(path, POPULATIONS, "test")
    row = obs.iloc[0]
    assert row["variant_id"] == "cyt:il-6-174-g"
    assert (row["ac"], row["an"]) == (20, 200)


def test_a_major_alphabetical_allele_is_flipped_to_its_minor_partner(tmp_path):
    """AA 1%, AG 18%, GG 81% -> p(G) = 0.90, so G is MAJOR. The reported allele becomes A at
    0.10, and the frequency is complemented exactly: p(A) = 1 - p(G) for a biallelic locus."""
    path = _table(tmp_path, {
        "group": ["cyt"] * 3,
        "gene": ["IL-6-"] * 3,
        "allele": ["IL-6/ - 174 AA", "IL-6/ - 174 AG", "IL-6/ - 174 GG"],
        "population": [PLACED] * 3,
        "indivs_over_n": ["1.0", "18.0", "81.0"],
        "alleles_over_2n": ["", "", ""],
        "n": ["100", "100", "100"],
    })
    obs, _ = afnd_cytokines.load(path, POPULATIONS, "test")
    row = obs.iloc[0]
    assert row["variant_id"] == "cyt:il-6-174-a"
    assert (row["ac"], row["an"]) == (20, 200)

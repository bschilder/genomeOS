"""AFND allele-frequency adapter (design §6, §7.1, P1).

The tests target the three places this source can silently produce wrong numbers: a count
reconstructed from a rounded frequency, a refusal report that does not add up, and ascertainment
inherited from a population that never stated any.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import afnd_frequencies as af

FIXTURES = Path(__file__).parent / "fixtures"
POPULATIONS = FIXTURES / "afnd_populations.tsv"


@pytest.fixture(scope="module")
def frequencies(tmp_path_factory) -> Path:
    """A frequency table over the populations in the registry fixture.

    `n` deliberately carries a thousand separator on one row: AFND prints them, and parsing
    without stripping refused 27% of the real table as having no sample size at all.
    """
    path = tmp_path_factory.mktemp("afnd") / "freq.tsv"
    pd.DataFrame(
        {
            "group": ["hla"] * 5,
            "gene": ["DQB1", "DQB1", "DQB1", "A", "A"],
            "allele": ["DQB1*03:01"] * 3 + ["A*01:01"] * 2,
            "population": [
                "Peru Lamas City Lama",
                "Papua New Guinea Wonie",
                "India Tamil Nadu Nadar",
                "Peru Lamas City Lama",
                "Example Unrecorded Study Type",
            ],
            "indivs_over_n": ["", "", "", "", ""],
            "alleles_over_2n": ["0.1250", "0.0000", "0.0500", "0.2500", "0.3000"],
            "n": ["100", "1,000", "50", "100", "100"],
        }
    ).to_csv(path, sep="\t", index=False)
    return path


def test_counts_are_reconstructed_from_the_frequency_and_sample_size(frequencies):
    """AFND publishes a frequency, not a count, so `ac = round(af * 2n)`. Getting this wrong
    scales every allele frequency in the corpus without ever raising."""
    obs, _ = af.load(frequencies, POPULATIONS, "test")
    row = obs[
        (obs["variant_id"] == "hla:dqb1-03-01") & (obs["population_id"] == "afnd-1986")
    ].iloc[0]
    assert row["an"] == 200, "two alleles per individual"
    assert row["ac"] == 25, "0.1250 * 200"


def test_thousand_separators_in_the_sample_size_are_parsed_not_refused(frequencies):
    """AFND prints `3,732`. Refusing those rows looks identical in a report to data that has no
    sample size, which is how 33,514 real rows were nearly lost."""
    obs, report = af.load(frequencies, POPULATIONS, "test")
    row = obs[obs["population_id"] == "afnd-2800"].iloc[0]
    assert row["an"] == 2000, "'1,000' individuals"
    assert "no_sample_size" not in report.refusals


def test_a_zero_frequency_is_an_observation_not_a_missing_value(frequencies):
    """An allele measured and absent is evidence. Dropping zeros biases every fitted surface
    upward exactly where the allele is genuinely absent."""
    obs, _ = af.load(frequencies, POPULATIONS, "test")
    absent = obs[obs["population_id"] == "afnd-2800"]
    assert len(absent) == 1
    assert absent.iloc[0]["ac"] == 0


def test_a_population_with_no_stated_ascertainment_is_refused_here(frequencies):
    """The registry keeps such populations because it stores no ascertainment; P1 cannot, because
    §7.1 gives `sampling_design` no default. This is where that debt comes due."""
    obs, report = af.load(frequencies, POPULATIONS, "test")
    assert "afnd-9004" not in set(obs["population_id"])
    assert report.refusals["ascertainment_not_stated"] >= 1


def test_every_input_row_is_counted_exactly_once(frequencies):
    """Retained + refused must equal the input. Counting each condition over the whole frame
    double-counts a row failing two of them, and the report stops being an account."""
    _, report = af.load(frequencies, POPULATIONS, "test")
    assert report.retained + sum(report.refusals.values()) == report.total


def test_alleles_are_keyed_as_hla_not_as_a_locus(frequencies):
    """An HLA allele is a haplotype of many linked variants named by the WHO committee, not a
    chr-pos-ref-alt triple; forcing one would assert a coordinate nobody measured."""
    obs, _ = af.load(frequencies, POPULATIONS, "test")
    assert set(obs["variant_id"]) <= {"hla:dqb1-03-01", "hla:a-01-01"}
    assert af.variant_id("DQB1", "DQB1*03:01", "hla") == "hla:dqb1-03-01"


def test_output_satisfies_the_observations_contract(frequencies):
    obs, _ = af.load(frequencies, POPULATIONS, "test")
    OBSERVATIONS_SCHEMA.validate(obs)


def test_min_populations_is_a_modelling_filter_and_is_reported(frequencies):
    """A spatial field cannot be identified from a handful of points, but that is a modelling
    judgement rather than a data defect — so it defaults off and is counted when used."""
    _, permissive = af.load(frequencies, POPULATIONS, "test")
    _, strict = af.load(frequencies, POPULATIONS, "test", min_populations=3)
    assert "below_min_populations" not in permissive.refusals
    assert strict.refusals["below_min_populations"] >= 1


def test_each_gene_family_gets_its_own_namespace():
    """AFND ships four families and only one of them is HLA (#134).

    The prefix is a provenance claim. `hla:2dl1` for KIR2DL1 asserts something false about what
    was measured, which §4 treats as a bug rather than a naming preference.
    """
    assert af.variant_id("DQB1", "DQB1*03:01", "hla") == "hla:dqb1-03-01"
    assert af.variant_id("3DL1", "3DL1*007", "kir") == "kir:3dl1-007"
    assert af.variant_id("MICA", "MICA*004", "mic") == "mic:mica-004"


def test_an_unrecognised_family_is_refused_rather_than_guessed():
    """A new AFND group needs a namespace and a decision, not a default prefix."""
    with pytest.raises(ValueError, match="unknown AFND group"):
        af.variant_id("FOO", "FOO*01", "notafamily")


def _table(tmp_path, rows):
    path = tmp_path / "freq.tsv"
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)
    return path


def test_cytokine_genotypes_are_refused_not_converted_to_allele_counts(tmp_path):
    """Cytokine rows are diploid genotypes, so there is no allele count to recover (#133).

    Deriving one would need Hardy-Weinberg, which is an assumption about the population and
    exactly the kind of silent substitution the invariants forbid.
    """
    path = _table(tmp_path, {
        "group": ["cyt", "hla"],
        "gene": ["IL-6-", "DQB1"],
        "allele": ["IL-6/ - 174 CC", "DQB1*03:01"],
        "population": ["Peru Lamas City Lama"] * 2,
        "indivs_over_n": ["", ""],
        "alleles_over_2n": ["0.4000", "0.1250"],
        "n": ["100", "100"],
    })
    obs, report = af.load(path, POPULATIONS, "test")
    assert set(obs["variant_id"]) == {"hla:dqb1-03-01"}
    assert "cytokine_genotype_not_allele_frequency" in report.refusals


def test_kir_gene_presence_is_refused_but_kir_alleles_are_kept(tmp_path):
    """`allele == gene` on a copy-number-variable KIR gene is a carrier frequency, not an
    allele frequency, so it cannot share a column with one (#133)."""
    path = _table(tmp_path, {
        "group": ["kir", "kir"],
        "gene": ["2DL1", "3DL1"],
        "allele": ["2DL1", "3DL1*007"],
        "population": ["Peru Lamas City Lama"] * 2,
        "indivs_over_n": ["", ""],
        "alleles_over_2n": ["0.9000", "0.1000"],
        "n": ["100", "100"],
    })
    obs, report = af.load(path, POPULATIONS, "test")
    assert set(obs["variant_id"]) == {"kir:3dl1-007"}
    assert report.refusals["kir_gene_presence_not_allele_frequency"] == 1


def test_donor_registry_strata_are_refused(tmp_path):
    """NMDP and DKMS sub-populations are ancestry strata, not places (#141).

    All 21 NMDP strata share the registry's Maryland coordinate and all 15 DKMS strata share a
    German one, and together the 37 carry 91% of the corpus's statistical weight against 905
    genuinely geographic populations. A point-referenced surface cannot represent stratification,
    so they are refused rather than relocated: "NMDP European Caucasian" is a blend of European
    source populations that exists at no location in Europe.
    """
    path = _table(tmp_path, {
        "group": ["hla"] * 3,
        "gene": ["DQB1"] * 3,
        "allele": ["DQB1*03:01"] * 3,
        "population": [
            "USA NMDP Chinese",
            "Germany DKMS - German donors",
            "Peru Lamas City Lama",
        ],
        "indivs_over_n": ["", "", ""],
        "alleles_over_2n": ["0.2000", "0.1500", "0.1250"],
        "n": ["199344", "3456066", "100"],
    })
    obs, report = af.load(path, POPULATIONS, "test")
    # only the real population survives, and with it the weight that was drowning it
    assert len(obs) == 1
    assert report.refusals["donor_registry_ancestry_stratum"] == 2


def test_the_registry_refusal_is_reported_before_missing_data(tmp_path):
    """A registry stratum that also lacks a frequency is reported as a stratum.

    Same reasoning as the gene-family refusals: a refusal list that misattributes rows to
    "missing data" sends the reader looking for a scraping bug that does not exist.
    """
    path = _table(tmp_path, {
        "group": ["hla", "hla"],
        "gene": ["DQB1", "DQB1"],
        "allele": ["DQB1*03:01", "DQB1*03:01"],
        "population": ["USA NMDP Korean", "Peru Lamas City Lama"],
        "indivs_over_n": ["", ""],
        "alleles_over_2n": ["", "0.1250"],   # the registry row has no frequency either
        "n": ["155168", "100"],
    })
    _, report = af.load(path, POPULATIONS, "test")
    assert report.refusals["donor_registry_ancestry_stratum"] == 1
    assert "no_frequency_reported" not in report.refusals

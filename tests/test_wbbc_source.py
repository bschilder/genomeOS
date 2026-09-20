"""WBBC regional count ingestion (Atlas design §§4, 6, 7.1; issue #325)."""

from __future__ import annotations

import gzip
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.sources import wbbc
from genomeos.registry.sources import wbbc as wbbc_registry

FIXTURES = Path(__file__).parent / "fixtures"
REQUESTED = frozenset({"chr22-16050075-A-G", "chr22-16050080-C-T"})


@pytest.fixture
def registry() -> tuple[pd.DataFrame, pd.DataFrame]:
    return wbbc_registry.load(FIXTURES / "wbbc_regions.tsv", "0.1.0")


def test_reconstructs_four_regional_counts_and_retains_zeros(registry):
    populations, aliases = registry

    observations, report = wbbc.load(
        FIXTURES / "wbbc_sites.vcf",
        populations,
        aliases,
        "0.1.0",
        variant_ids=REQUESTED,
        chunk_size=1,
    )

    first = observations.loc[observations["variant_id"] == "chr22-16050075-A-G"]
    assert dict(zip(first["population_id"], first["ac"], strict=True)) == {
        "wbbc-north": 1,
        "wbbc-central": 0,
        "wbbc-south": 8,
        "wbbc-lingnan": 1,
    }
    assert dict(zip(first["population_id"], first["an"], strict=True)) == {
        "wbbc-north": 448,
        "wbbc-central": 100,
        "wbbc-south": 8070,
        "wbbc-lingnan": 126,
    }
    zero = observations.loc[observations["variant_id"] == "chr22-16050080-C-T"]
    assert len(zero) == 4
    assert zero["ac"].eq(0).all()
    assert observations["sampling_design"].eq("convenience").all()
    assert observations["disease_ascertainment_excluded"].eq(False).all()  # noqa: E712
    assert observations["cohort_id"].eq("wbbc:wgs-frequency-release-v1").all()
    assert observations["assay"].eq("genome_frequency_reconstructed").all()
    assert observations["source_record_id"].is_unique
    assert report.scanned_variants == 3
    assert report.matched_variants == 2
    assert report.retained_observations == 8
    assert report.requested_variants == 2
    assert report.maximum_regional_count_residual < 0.005


def test_geography_comes_from_the_registry(registry):
    populations, aliases = registry
    observations, _ = wbbc.load(
        FIXTURES / "wbbc_sites.vcf",
        populations,
        aliases,
        "0.1.0",
        variant_ids=frozenset({"chr22-16050075-A-G"}),
    )

    expected = populations.set_index("population_id")
    actual = observations.set_index("population_id")
    for column, source_column in (
        ("lat", "lat"),
        ("lon", "lon"),
        ("radius_km", "uncertainty_radius_km"),
    ):
        assert actual[column].to_dict() == expected[source_column].to_dict()


def test_plain_and_gzip_inputs_are_byte_semantically_identical(tmp_path: Path, registry):
    compressed = tmp_path / "wbbc.vcf.gz"
    compressed.write_bytes(gzip.compress((FIXTURES / "wbbc_sites.vcf").read_bytes(), mtime=0))
    populations, aliases = registry

    plain, plain_report = wbbc.load(
        FIXTURES / "wbbc_sites.vcf",
        populations,
        aliases,
        "0.1.0",
        variant_ids=REQUESTED,
        chunk_size=100,
    )
    gzipped, gzip_report = wbbc.load(
        compressed,
        populations,
        aliases,
        "0.1.0",
        variant_ids=REQUESTED,
        chunk_size=1,
    )

    pd.testing.assert_frame_equal(plain, gzipped)
    assert plain_report == gzip_report


def test_multiple_chromosome_files_satisfy_one_curated_variant_set(tmp_path: Path, registry):
    lines = (FIXTURES / "wbbc_sites.vcf").read_text(encoding="utf-8").splitlines()
    header = "\n".join(line for line in lines if line.startswith("#")) + "\n"
    records = [line for line in lines if not line.startswith("#")]
    first = tmp_path / "part-1.vcf"
    second = tmp_path / "part-2.vcf"
    first.write_text(header + records[0] + "\n", encoding="utf-8")
    second.write_text(header + "\n".join(records[1:]) + "\n", encoding="utf-8")
    populations, aliases = registry

    observations, report = wbbc.load_many(
        [first, second],
        populations,
        aliases,
        "0.1.0",
        variant_ids=REQUESTED,
        chunk_size=1,
    )

    assert len(observations) == 8
    assert report.scanned_variants == 3
    assert report.matched_variants == 2


def test_requires_a_nonempty_explicit_variant_set(registry):
    populations, aliases = registry

    with pytest.raises(ValueError, match="non-empty.*variant"):
        wbbc.load(
            FIXTURES / "wbbc_sites.vcf",
            populations,
            aliases,
            "0.1.0",
            variant_ids=frozenset(),
        )


def test_missing_requested_variant_is_a_hard_error(registry):
    populations, aliases = registry

    with pytest.raises(wbbc.RequestedVariantNotFoundError, match="chr1-1-A-G"):
        wbbc.load(
            FIXTURES / "wbbc_sites.vcf",
            populations,
            aliases,
            "0.1.0",
            variant_ids=frozenset({"chr1-1-A-G"}),
        )


def test_unmapped_source_region_is_a_hard_error(registry):
    populations, aliases = registry
    aliases = aliases.loc[aliases["label"] != "Lingnan"].copy()

    with pytest.raises(wbbc.UnmappedRegionError, match="Lingnan"):
        wbbc.load(
            FIXTURES / "wbbc_sites.vcf",
            populations,
            aliases,
            "0.1.0",
            variant_ids=REQUESTED,
        )


def test_distinct_source_regions_cannot_collapse_to_one_population(registry):
    populations, aliases = registry
    aliases = aliases.copy()
    aliases.loc[aliases["label"] == "Central", "population_id"] = "wbbc-north"

    with pytest.raises(wbbc.UnmappedRegionError, match="distinct populations"):
        wbbc.load(
            FIXTURES / "wbbc_sites.vcf",
            populations,
            aliases,
            "0.1.0",
            variant_ids=REQUESTED,
        )


def test_unexpected_source_region_alias_is_a_hard_error(registry):
    populations, aliases = registry
    extra = aliases.iloc[[0]].copy()
    extra["label"] = "Northern China"
    aliases = pd.concat([aliases, extra], ignore_index=True)

    with pytest.raises(wbbc.UnmappedRegionError, match="unexpected.*Northern China"):
        wbbc.load(
            FIXTURES / "wbbc_sites.vcf",
            populations,
            aliases,
            "0.1.0",
            variant_ids=REQUESTED,
        )


def _mutated_vcf(tmp_path: Path, old: str, new: str) -> Path:
    path = tmp_path / "mutated.vcf"
    path.write_text((FIXTURES / "wbbc_sites.vcf").read_text().replace(old, new), encoding="utf-8")
    return path


def test_refuses_when_reported_global_ac_breaks_the_rounding_control(tmp_path: Path, registry):
    path = _mutated_vcf(tmp_path, "AC=10;AF=0.00111607", "AC=11;AF=0.00111607")
    populations, aliases = registry

    with pytest.raises(ValueError, match="global AC/AF/AN rounding control"):
        wbbc.load(path, populations, aliases, "0.1.0", variant_ids=REQUESTED)


def test_refuses_when_global_genotypes_do_not_reproduce_ns_and_ac(tmp_path: Path, registry):
    path = _mutated_vcf(tmp_path, "RR=4471|RA=8|AA=1", "RR=4472|RA=8|AA=1")
    populations, aliases = registry

    with pytest.raises(ValueError, match="genotype count control"):
        wbbc.load(path, populations, aliases, "0.1.0", variant_ids=REQUESTED)


def test_refuses_an_ambiguous_regional_count_reconstruction(tmp_path: Path, registry):
    path = _mutated_vcf(tmp_path, "North_AF=0.00223214", "North_AF=0.003348214285714286")
    populations, aliases = registry

    with pytest.raises(ValueError, match="regional AF.*AN reconstruction"):
        wbbc.load(path, populations, aliases, "0.1.0", variant_ids=REQUESTED)


def test_refuses_info_schema_drift_instead_of_defaulting(tmp_path: Path, registry):
    path = _mutated_vcf(tmp_path, ";Lingnan_AN=126", "")
    populations, aliases = registry

    with pytest.raises(ValueError, match="INFO schema"):
        wbbc.load(path, populations, aliases, "0.1.0", variant_ids=REQUESTED)

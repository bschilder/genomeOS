"""Normalized external variant-cache contracts (Atlas design §11)."""

from __future__ import annotations

import pytest

from scripts.fetch_external_variant_info import normalize_dbsnp, normalize_gnomad

VARIANT = "chr11-5227002-T-A"


def test_normalize_gnomad_keeps_query_release_and_frequency_counts() -> None:
    payload = {
        "data": {
            "variant": {
                "variant_id": "11-5227002-T-A",
                "chrom": "11",
                "pos": 5227002,
                "ref": "T",
                "alt": "A",
                "rsids": ["rs334"],
                "exome": {"ac": 2335, "an": 1458356, "ac_hom": 31, "ac_hemi": 0},
                "genome": {"ac": 1937, "an": 152294, "ac_hom": 9, "ac_hemi": 0},
                "joint": {
                    "ac": 4272,
                    "an": 1610650,
                    "populations": [
                        {
                            "id": "afr",
                            "ac": 3707,
                            "an": 74908,
                            "homozygote_count": 36,
                            "hemizygote_count": 0,
                        },
                        {
                            "id": "afr_XX",
                            "ac": 2029,
                            "an": 41402,
                            "homozygote_count": 12,
                            "hemizygote_count": 0,
                        },
                        {
                            "id": "nfe",
                            "ac": 46,
                            "an": 1176872,
                            "homozygote_count": 0,
                            "hemizygote_count": 0,
                        },
                        {
                            "id": "",
                            "ac": 4272,
                            "an": 1610650,
                            "homozygote_count": 40,
                            "hemizygote_count": 0,
                        },
                    ],
                },
                "non_coding_constraint": {
                    "chrom": "chr11",
                    "start": 5227000,
                    "stop": 5228000,
                    "possible": 1722,
                    "observed": 151,
                    "expected": 144.25935104346829,
                    "oe": 1.0467259065549284,
                    "z": -0.5612155853702537,
                },
                "transcript_consequences": [
                    {
                        "gene_symbol": "HBB",
                        "major_consequence": "missense_variant",
                        "hgvsc": "c.20A>T",
                        "hgvsp": "p.Glu7Val",
                        "is_canonical": True,
                        "is_mane_select": True,
                    }
                ],
            },
            "clinvar_variant": {
                "clinical_significance": "Pathogenic",
                "clinvar_variation_id": "15333",
                "gold_stars": 2,
                "last_evaluated": "2026-02-26",
                "review_status": "criteria provided, multiple submitters, no conflicts",
                "submissions": [
                    {
                        "clinical_significance": "Pathogenic",
                        "conditions": [
                            {"name": "Hb SS disease", "medgen_id": "C0002895"}
                        ],
                    },
                    {
                        "clinical_significance": "Pathogenic",
                        "conditions": [
                            {"name": "Hb SS disease", "medgen_id": "C0002895"},
                            {"name": "not provided", "medgen_id": "C3661900"},
                        ],
                    },
                    {
                        "clinical_significance": "protective",
                        "conditions": [
                            {"name": "Malaria, resistance to", "medgen_id": "C2720293"}
                        ],
                    },
                ],
            },
            "meta": {"clinvar_release_date": "2026-06-06"},
        }
    }
    result = normalize_gnomad(payload, VARIANT, "gnomad_r4", "2026-09-07T00:00:00Z")
    assert result["query"]["normalized_variant_id"] == VARIANT
    assert result["source_release"] == "gnomad_r4"
    assert result["schema_version"] == 2
    assert result["record"]["joint"]["af"] == pytest.approx(4272 / 1610650)
    assert result["record"]["canonical_consequence"]["gene_symbol"] == "HBB"
    assert result["record"]["genetic_ancestry_group_frequencies"] == [
        {
            "ac": 3707,
            "af": pytest.approx(3707 / 74908),
            "an": 74908,
            "hemizygote_count": 0,
            "homozygote_count": 36,
            "id": "afr",
            "label": "African/African American",
        },
        {
            "ac": 46,
            "af": pytest.approx(46 / 1176872),
            "an": 1176872,
            "hemizygote_count": 0,
            "homozygote_count": 0,
            "id": "nfe",
            "label": "European (non-Finnish)",
        },
    ]
    assert result["record"]["genomic_constraint"] == {
        "chrom": "chr11",
        "dataset_release": "gnomAD v3.1.2",
        "expected": pytest.approx(144.25935104346829),
        "observed": 151,
        "oe": pytest.approx(1.0467259065549284),
        "possible": 1722,
        "start": 5227000,
        "stop": 5228000,
        "z": pytest.approx(-0.5612155853702537),
    }
    assert result["record"]["clinvar"]["submission_count"] == 3
    assert result["record"]["clinvar"]["release_date"] == "2026-06-06"
    assert result["record"]["clinvar"]["conditions"] == [
        {
            "classifications": ["Pathogenic"],
            "medgen_id": "C0002895",
            "name": "Hb SS disease",
            "submission_count": 2,
        },
        {
            "classifications": ["protective"],
            "medgen_id": "C2720293",
            "name": "Malaria, resistance to",
            "submission_count": 1,
        },
        {
            "classifications": ["Pathogenic"],
            "medgen_id": "C3661900",
            "name": "not provided",
            "submission_count": 1,
        },
    ]


def test_normalize_gnomad_refuses_unknown_aggregate_ancestry_group() -> None:
    payload = {
        "data": {
            "variant": {
                "variant_id": "11-5227002-T-A",
                "chrom": "11",
                "pos": 5227002,
                "ref": "T",
                "alt": "A",
                "rsids": ["rs334"],
                "exome": None,
                "genome": None,
                "joint": {
                    "ac": 1,
                    "an": 100,
                    "populations": [
                        {
                            "id": "unexpected",
                            "ac": 1,
                            "an": 100,
                            "homozygote_count": 0,
                            "hemizygote_count": 0,
                        }
                    ],
                },
                "non_coding_constraint": None,
                "transcript_consequences": [],
            },
            "clinvar_variant": None,
            "meta": {"clinvar_release_date": "2026-06-06"},
        }
    }

    with pytest.raises(ValueError, match="ancestry group"):
        normalize_gnomad(payload, VARIANT, "gnomad_r4", "2026-09-07T00:00:00Z")


def test_normalize_dbsnp_selects_exact_grch38_alt() -> None:
    payload = {
        "refsnp_id": "334",
        "last_update_build_id": "157",
        "last_update_date": "2024-11-1T07:22Z",
        "citations": [1, 2],
        "primary_snapshot_data": {
            "placements_with_allele": [
                {
                    "is_ptlp": True,
                    "placement_annot": {
                        "seq_id_traits_by_assembly": [
                            {"assembly_name": "GRCh38.p14", "is_top_level": True}
                        ]
                    },
                    "alleles": [
                        {
                            "allele": {
                                "spdi": {
                                    "seq_id": "NC_000011.10",
                                    "position": 5227001,
                                    "deleted_sequence": "T",
                                    "inserted_sequence": "A",
                                }
                            },
                            "hgvs": "NC_000011.10:g.5227002T>A",
                        }
                    ],
                }
            ]
        },
    }
    result = normalize_dbsnp(payload, "rs334", VARIANT, "2026-09-07T00:00:00Z")
    assert result["record"]["spdi"]["position"] == 5227001
    assert result["record"]["hgvs"] == "NC_000011.10:g.5227002T>A"
    assert result["record"]["citation_count"] == 2


def test_normalize_dbsnp_refuses_a_different_alt() -> None:
    payload = {
        "refsnp_id": "334",
        "primary_snapshot_data": {"placements_with_allele": []},
    }
    with pytest.raises(ValueError, match="exact GRCh38 allele"):
        normalize_dbsnp(payload, "rs334", VARIANT, "2026-09-07T00:00:00Z")

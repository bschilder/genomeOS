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
                "joint": {"ac": 4272, "an": 1610650},
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
            }
        }
    }
    result = normalize_gnomad(payload, VARIANT, "gnomad_r4", "2026-09-07T00:00:00Z")
    assert result["query"]["normalized_variant_id"] == VARIANT
    assert result["source_release"] == "gnomad_r4"
    assert result["record"]["joint"]["af"] == pytest.approx(4272 / 1610650)
    assert result["record"]["canonical_consequence"]["gene_symbol"] == "HBB"


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

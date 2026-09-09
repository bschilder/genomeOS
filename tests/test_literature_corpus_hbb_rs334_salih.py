"""Validate the staged HBB rs334 literature corpus slice (Salih 2010).

The corpus under tests/fixtures/literature/hbb-rs334-salih-2010/ is staged
evidence, not promoted observations. This test proves every shipped file
satisfies the frozen literature contracts and pins the honest state for
issue #151: exact AA/AS/SS genotype counts from Salih et al. 2010 Table 1
(map to GRCh38 chr11-5227002-T-A, counted ALT A = HbS), origin is
automated_proposal, reuse is no_restriction_found (CC BY 2.0 checked on the
BMC and PMC surfaces), verification pending on every row, and the search
manifest is reproducible.

Run: pytest tests/test_literature_corpus_hbb_rs334_salih.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from genomeos.observations.evidence import (
    validate_literature_tables,
    validate_search_manifest,
)

CORPUS = Path("tests/fixtures/literature/hbb-rs334-salih-2010")


def _read_tsv(name: str) -> pd.DataFrame:
    path = CORPUS / name
    assert path.exists(), f"missing corpus file {path}"
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False).replace("", pd.NA)


def test_corpus_files_validate_under_frozen_contracts() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    assert len(evidence) == 2
    assert len(fields) == 2 * 19
    validated_evidence, validated_fields = validate_literature_tables(evidence, fields)
    assert len(validated_evidence) == 2
    assert len(validated_fields) == 38


def test_search_manifest_validates_with_deterministic_ids() -> None:
    searches = _read_tsv("searches.tsv")
    validated = validate_search_manifest(searches)
    assert len(validated) == len(searches)
    keys = validated[["database", "query", "executed_at"]].drop_duplicates()
    ids = validated.groupby(["database", "query", "executed_at"])["search_id"].nunique()
    assert (ids == 1).all()
    assert len(keys) == 3
    # every candidate must be screened (no undecided rows except pending)
    assert set(validated["decision"]).issubset({"included", "excluded", "pending"})


def test_corpus_normalization_state_is_verified() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    assert set(validated["normalization_status"].dropna()) == {"verified"}
    assert set(validated["variant_id"]) == {"chr11-5227002-T-A"}
    assert set(validated["counted_allele"]) == {"A"}


def test_corpus_reuse_state_is_no_restriction_found() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    # CC BY 2.0 on the BMC article and PMC surfaces; no restriction on
    # factual-data reuse found. The terms check is recorded per surface.
    assert set(validated["reuse_status"].dropna()) == {"no_restriction_found"}


def test_corpus_origin_is_automated_proposal() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    assert set(validated["extraction_method"].dropna()) == {"automated_proposal"}


def test_corpus_verification_is_pending_everywhere() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    assert set(validated["verification_status"].dropna()) == {"pending"}
    assert validated["verified_by"].isna().all()
    assert validated["verified_at"].isna().all()


def test_corpus_derived_counts_recompute_from_genotypes() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    # S (ALT A) copies from Salih 2010 Table 1 N row: AS + 2*SS
    expected = {
        "Hausa": (121, 448),
        "Massalit": (98, 492),
    }
    for _, row in validated.iterrows():
        exp_ac, exp_an = expected[row["population_label"]]
        assert int(row["ac_lower"]) == exp_ac
        assert int(row["ac_upper"]) == exp_ac
        assert int(row["an"]) == exp_an
        assert int(row["an"]) % 2 == 0  # diploid autosomal denominator
    # Regression: paper AA/AS/SS labels must not leak into genotype-class
    # JSON keys (S is not a nucleotide); keys must be canonical ACGT classes.
    ac_rows = fields.loc[fields["field_name"] == "ac_lower"]
    assert len(ac_rows) == 2
    for raw in ac_rows["raw_value"].dropna():
        payload = json.loads(raw)
        assert all(set(k) <= {"A", "C", "G", "T"} and len(k) == 2 for k in payload)
        assert "S" not in raw

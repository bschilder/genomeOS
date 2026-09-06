"""Validate the staged LCT rs4988235 literature corpus slice (Enattah 2007).

The corpus under tests/fixtures/literature/lct-enattah-2007/ is staged
evidence, not promoted observations. This test proves every shipped file
satisfies the frozen literature contracts and pins the honest state after
the 2026-09-06 review: locators point to Table 3, origin is
automated_proposal, reuse is no_restriction_found (PMC surface checked,
no specific factual-data restriction), verification pending on every row,
and the search manifest is reproducible.

Run: pytest tests/test_literature_corpus_lct_enattah.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeos.observations.evidence import (
    validate_literature_tables,
    validate_search_manifest,
)

CORPUS = Path("tests/fixtures/literature/lct-enattah-2007")


def _read_tsv(name: str) -> pd.DataFrame:
    path = CORPUS / name
    assert path.exists(), f"missing corpus file {path}"
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False).replace("", pd.NA)


def test_corpus_files_validate_under_frozen_contracts() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    assert len(evidence) == 12
    assert len(fields) == 12 * 19
    validated_evidence, validated_fields = validate_literature_tables(evidence, fields)
    assert len(validated_evidence) == 12
    assert len(validated_fields) == 228


def test_search_manifest_validates_with_deterministic_ids() -> None:
    searches = _read_tsv("searches.tsv")
    validated = validate_search_manifest(searches)
    assert len(validated) == len(searches)
    # every unique search has one deterministic id for its database/query/date
    keys = validated[["database", "query", "executed_at"]].drop_duplicates()
    ids = validated.groupby(["database", "query", "executed_at"])["search_id"].nunique()
    assert (ids == 1).all()
    assert len(keys) == 3


def test_corpus_normalization_state_is_verified() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    statuses = set(validated["normalization_status"].dropna())
    assert statuses == {"verified"}


def test_corpus_reuse_state_is_no_restriction_found() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    statuses = set(validated["reuse_status"].dropna())
    # PMC surface for PMID 17701907 carries an ASHG (c) boilerplate notice;
    # per project policy boilerplate does not restrict factual data reuse.
    # The terms check is recorded on the PMC surface itself.
    assert statuses == {"no_restriction_found"}


def test_corpus_origin_is_automated_proposal() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    # agent-transcribed records without a human extractor and without a
    # deterministic importer are immutable automated proposals.
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
    # T-13910 copy counts from Enattah 2007 Table 3 (N CC/CT/TT -> GRCh38 G/A)
    expected = {
        "Komi": 3,
        "Udmurts": 20,
        "Mokshas": 17,
        "Erzas": 16,
        "Saami": 10,
        "Finns, eastern": 83,
        "Finns, western": 190,
        "Basques": 112,
        "Pathan": 17,
        "Sindi": 23,
        "Brahui": 16,
        "Qashqai": 1,
    }
    assert not validated["record_locator"].str.contains("table:2").any()
    assert validated["record_locator"].str.contains("table:3,row:").all()
    for _, row in validated.iterrows():
        assert int(row["ac_lower"]) == expected[row["population_label"]]
        assert int(row["ac_upper"]) == expected[row["population_label"]]
        assert int(row["an"]) % 2 == 0  # diploid autosomal denominator

"""Validate the staged LCT rs4988235 literature corpus slice (Enattah 2007).

The corpus under tests/fixtures/literature/lct-enattah-2007/ is staged
evidence, not promoted observations. This test proves it satisfies the
frozen literature contracts and pins the honest state: normalization
verified, reuse restricted (PMC ASHG rights notice), verification pending
on every row.

Run: pytest tests/test_literature_corpus_lct_enattah.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeos.observations.evidence import validate_literature_tables

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


def test_corpus_normalization_state_is_verified() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    statuses = set(validated["normalization_status"].dropna())
    assert statuses == {"verified"}


def test_corpus_reuse_state_is_restricted() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    validated, _ = validate_literature_tables(evidence, fields)
    statuses = set(validated["reuse_status"].dropna())
    # PMC surface for PMID 17701907 carries an explicit ASHG (c) notice;
    # the documented reuse rule says an explicit restriction wins.
    assert statuses == {"restricted"}


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
    # T-13910 copy counts from Enattah 2007 Table 2 (CC/CT/TT -> GRCh38 G/A)
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
    for _, row in validated.iterrows():
        assert int(row["ac_lower"]) == expected[row["population_label"]]
        assert int(row["ac_upper"]) == expected[row["population_label"]]
        assert int(row["an"]) % 2 == 0  # diploid autosomal denominator

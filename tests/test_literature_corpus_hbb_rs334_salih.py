"""Validate the staged HBB rs334 literature corpus slice (Salih 2010).

The corpus under tests/fixtures/literature/hbb-rs334-salih-2010/ is staged
evidence, not promoted observations. This test proves every shipped file
satisfies the frozen literature contracts and pins the honest state for
issue #151: exact AA/AS/SS genotype counts from Salih et al. 2010 Table 1
(map to GRCh38 chr11-5227002-T-A, counted ALT A = HbS), origin is
automated_proposal, reuse is no_restriction_found (CC BY 2.0 checked on the
BMC and PMC surfaces), verification pending on every row, and the search
manifest is reproducible. The builder replay test at the bottom proves the
committed payload fixtures regenerate the committed corpus files exactly.

Run: pytest tests/test_literature_corpus_hbb_rs334_salih.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from genomeos.observations.evidence import (
    validate_literature_tables,
    validate_search_manifest,
)

REPO_ROOT = Path(__file__).parents[1]
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


CRLF = bytes([13, 10])
LF = bytes([10])


def _normalised(path: Path) -> bytes:
    """Read file bytes with line endings normalised to LF.

    The repository stores the corpus TSVs with LF and the index agrees, but a
    Windows checkout with core.autocrlf rewrites the working copy to CRLF, which
    would otherwise fail the replay comparison for a reason unrelated to evidence.
    """
    return path.read_bytes().replace(CRLF, LF)


def test_builder_replay_reproduces_the_committed_fixture(tmp_path: Path) -> None:
    """Replaying the committed PubMed payloads must regenerate the shipped corpus.

    This is what makes the builder's reproducibility claim checkable instead of
    asserted: the committed ESearch payload fixtures are the only source, the builder
    takes every timestamp from their capture metadata rather than the wall clock, and
    the three corpus TSVs must come back identical.
    """
    out = tmp_path / "replay"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_hbb_salih_fixture.py"),
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for name in ("evidence.tsv", "field_evidence.tsv", "searches.tsv"):
        replayed = _normalised(out / name)
        committed = _normalised(REPO_ROOT / CORPUS / name)
        assert replayed == committed, f"{name} does not replay from the committed payloads"

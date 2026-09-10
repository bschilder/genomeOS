"""Validate the staged HBB rs334 literature corpus slice (Salih 2010).

The corpus under tests/fixtures/literature/hbb-rs334-salih-2010/ is staged
evidence, not promoted observations. This module proves three things.

1. The ledgers satisfy the frozen literature contracts and pin the honest state
   for issue #151: exact AA/AS/SS genotype counts from Salih et al. 2010 Table 1
   (map to GRCh38 chr11-5227002-T-A, counted ALT A = HbS), origin is
   automated_proposal, reuse is no_restriction_found (CC BY 2.0 checked on the
   BMC and PMC surfaces), and verification is pending on every row.

2. Discovery and screening are separate immutable manifest versions (design
   §5.1): searches.pending.tsv is derivable from the committed ESearch payloads
   through scripts/fetch_pubmed_manifest.py, and searches.tsv is a screening
   revision over exactly those rows.

3. The ledgers are reproducible: replaying scripts/build_hbb_salih_fixture.py
   regenerates the committed evidence and field files exactly.

Run: pytest tests/test_literature_corpus_hbb_rs334_salih.py
"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pandas as pd

from genomeos.observations.evidence import (
    validate_literature_tables,
    validate_search_manifest,
)

REPO_ROOT = Path(__file__).parents[1]
CORPUS = REPO_ROOT / "tests" / "fixtures" / "literature" / "hbb-rs334-salih-2010"
MANIFEST_FILES = ("searches.pending.tsv", "searches.tsv")
LEDGER_FILES = ("evidence.tsv", "field_evidence.tsv")
BUILD_MANIFEST = runpy.run_path(str(REPO_ROOT / "scripts" / "fetch_pubmed_manifest.py"))[
    "build_manifest"
]

CRLF = bytes([13, 10])
LF = bytes([10])


def _provenance() -> dict:
    return json.loads((CORPUS / "PROVENANCE.json").read_text(encoding="utf-8"))


def _read_tsv(name: str) -> pd.DataFrame:
    path = CORPUS / name
    assert path.exists(), f"missing corpus file {path}"
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False).replace("", pd.NA)


def _normalised(path: Path) -> bytes:
    """Read file bytes with line endings normalised to LF.

    The repository stores the corpus files with LF and the index agrees, but a
    Windows checkout with core.autocrlf rewrites the working copy to CRLF, which
    would otherwise fail a byte comparison for a reason unrelated to evidence.
    """
    return path.read_bytes().replace(CRLF, LF)


def test_corpus_ledgers_validate_under_frozen_contracts() -> None:
    evidence = _read_tsv("evidence.tsv")
    fields = _read_tsv("field_evidence.tsv")
    assert len(evidence) == 2
    assert len(fields) == 2 * 19
    validated_evidence, validated_fields = validate_literature_tables(evidence, fields)
    assert len(validated_evidence) == 2
    assert len(validated_fields) == 38


def test_manifest_versions_validate_with_deterministic_ids() -> None:
    for name in MANIFEST_FILES:
        validated = validate_search_manifest(_read_tsv(name))
        assert len(validated) == 44
        keys = validated[["database", "query", "executed_at"]].drop_duplicates()
        assert len(keys) == 3
        ids = validated.groupby(["database", "query", "executed_at"])["search_id"].nunique()
        assert (ids == 1).all()
        assert set(validated["decision"]).issubset({"included", "excluded", "pending"})


def test_discovery_snapshot_is_derivable_from_the_committed_payloads() -> None:
    provenance = _provenance()
    pending = _read_tsv("searches.pending.tsv")
    assert len(provenance["discovery"]["queries"]) == 3
    for entry in provenance["discovery"]["queries"]:
        payload = json.loads((CORPUS / entry["payload"]).read_text(encoding="utf-8"))
        rebuilt = BUILD_MANIFEST(
            payload,
            corpus_id=provenance["corpus_id"],
            query=entry["query"],
            executed_at=entry["executed_at"],
            manifest_version=provenance["discovery"]["manifest_version"],
        )
        committed = pending.loc[pending["search_id"] == rebuilt.iloc[0]["search_id"]]
        assert len(committed) == len(rebuilt)
        assert committed["candidate_id"].tolist() == rebuilt["candidate_id"].tolist()
        assert set(committed["decision"]) == {"pending"}
        # a search result begins pending and decides nothing
        assert committed["decision_reason"].isna().all()


def test_screening_is_a_revision_of_the_discovery_snapshot() -> None:
    provenance = _provenance()
    pending = _read_tsv("searches.pending.tsv")
    screened = _read_tsv("searches.tsv")

    # the revision describes exactly the snapshot it revises
    assert len(pending) == len(screened)
    assert set(pending["candidate_id"]) == set(screened["candidate_id"])
    assert set(zip(pending["search_id"], pending["candidate_id"], strict=True)) == set(
        zip(screened["search_id"], screened["candidate_id"], strict=True)
    )
    for column in ("corpus_id", "database", "query", "executed_at"):
        assert pending[column].tolist() == screened[column].tolist()

    # only the decisions and the version move forward
    assert set(pending["decision"]) == {"pending"}
    assert set(pending["manifest_version"]) == {provenance["discovery"]["manifest_version"]}
    assert set(screened["manifest_version"]) == {provenance["screening"]["manifest_version"]}
    assert provenance["screening"]["over"] == provenance["discovery"]["manifest_version"]

    # coverage totals reconcile (design §8)
    counts = screened["decision"].value_counts()
    assert counts.sum() == len(screened)
    assert set(counts.index) == {"included", "excluded", "pending"}
    excluded = screened.loc[screened["decision"] == "excluded"]
    assert excluded["decision_reason"].notna().all()
    assert screened.loc[screened["decision"] != "excluded", "decision_reason"].isna().all()


def test_corpus_normalization_state_is_verified() -> None:
    validated, _ = validate_literature_tables(_read_tsv("evidence.tsv"), _read_tsv("field_evidence.tsv"))
    assert set(validated["normalization_status"].dropna()) == {"verified"}
    assert set(validated["variant_id"]) == {"chr11-5227002-T-A"}
    assert set(validated["counted_allele"]) == {"A"}


def test_corpus_reuse_state_is_no_restriction_found() -> None:
    validated, _ = validate_literature_tables(_read_tsv("evidence.tsv"), _read_tsv("field_evidence.tsv"))
    # CC BY 2.0 on the BMC article and PMC surfaces; no restriction on
    # factual-data reuse found. The terms check is recorded per surface.
    assert set(validated["reuse_status"].dropna()) == {"no_restriction_found"}


def test_corpus_origin_is_automated_proposal() -> None:
    validated, _ = validate_literature_tables(_read_tsv("evidence.tsv"), _read_tsv("field_evidence.tsv"))
    assert set(validated["extraction_method"].dropna()) == {"automated_proposal"}


def test_corpus_verification_is_pending_everywhere() -> None:
    validated, _ = validate_literature_tables(_read_tsv("evidence.tsv"), _read_tsv("field_evidence.tsv"))
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


def test_provenance_records_the_extraction_timestamp_the_ledgers_use() -> None:
    provenance = _provenance()
    evidence = _read_tsv("evidence.tsv")
    assert set(evidence["extracted_at"].dropna()) == {provenance["extraction"]["extracted_at"]}


def test_builder_replay_reproduces_the_committed_ledgers(tmp_path: Path) -> None:
    """Replaying the builder must regenerate the shipped evidence and field files.

    This is what makes reproducibility checkable rather than asserted. Every input
    is explicit: the extraction timestamp comes from the provenance record rather
    than the wall clock, and the output must match what is committed.
    """
    out = tmp_path / "replay"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_hbb_salih_fixture.py"),
            "--out",
            str(out),
            "--extracted-at",
            _provenance()["extraction"]["extracted_at"],
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for name in LEDGER_FILES:
        assert _normalised(out / name) == _normalised(CORPUS / name), (
            f"{name} does not replay from the recorded inputs"
        )

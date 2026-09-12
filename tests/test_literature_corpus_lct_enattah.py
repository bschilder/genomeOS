"""Validate the staged LCT rs4988235 literature corpus slice (Enattah 2007).

The corpus under tests/fixtures/literature/lct-enattah-2007/ is staged
evidence, not promoted observations. This test proves every shipped file
satisfies the frozen literature contracts and pins the honest state after
the 2026-09-06 review: locators point to Table 3, origin is
automated_proposal, reuse is no_restriction_found (PMC surface checked,
no specific factual-data restriction), verification pending on every row,
and the search manifest is reproducible.

The first seven tests assert the science and are unchanged from the merged
slice. The rest cover the #237 provenance backfill: the builder replays the
committed ledgers, every shipped identifier is regenerated rather than
revalidated, the corrected discovery snapshot derives from the committed
payloads, and no committed payload is a truncated capture — which is the defect
this backfill found.

The published searches.tsv is deliberately not rewritten by this backfill.
Re-deriving a manifest from a re-capture changes search_id by construction, so
superseding a published manifest version is a data revision that wants the
maintainer's decision rather than a reviewer's, and it is tracked separately.
Until that lands, searches.tsv remains the merged 37-row manifest and
searches.pending.tsv is the corrected 70-row discovery snapshot beside it; the
two deliberately do not share identifiers.

Run: pytest tests/test_literature_corpus_lct_enattah.py
"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pandas as pd

from genomeos.observations.evidence import (
    TRACKED_FIELDS,
    make_source_record_id,
    validate_literature_tables,
    validate_search_manifest,
)

CORPUS = Path("tests/fixtures/literature/lct-enattah-2007")
REPO_ROOT = Path(__file__).parents[1]
CORPUS_DIR = REPO_ROOT / "tests" / "fixtures" / "literature" / "lct-enattah-2007"
#: The corrected all-pending discovery snapshot, and the published manifest it does not yet
#: supersede. They are separate captures and so share no search_id (see the module docstring).
PENDING_MANIFEST = "searches.pending.tsv"
PUBLISHED_MANIFEST = "searches.tsv"
LEDGER_FILES = ("evidence.tsv", "field_evidence.tsv")
BUILD_MANIFEST = runpy.run_path(str(REPO_ROOT / "scripts" / "fetch_pubmed_manifest.py"))[
    "build_manifest"
]

CRLF = bytes([13, 10])
LF = bytes([10])


def _read_tsv(name: str) -> pd.DataFrame:
    path = CORPUS / name
    assert path.exists(), f"missing corpus file {path}"
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False).replace("", pd.NA)


def _provenance() -> dict:
    return json.loads((CORPUS_DIR / "PROVENANCE.json").read_text(encoding="utf-8"))


def _payload(entry: dict) -> dict:
    return json.loads((CORPUS_DIR / entry["payload"]).read_text(encoding="utf-8"))


def _normalised(path: Path) -> bytes:
    """Read file bytes with line endings normalised to LF.

    The repository stores these files with LF and the index agrees, but a Windows
    checkout with core.autocrlf rewrites the working copy to CRLF, which would
    otherwise fail a byte comparison for a reason unrelated to evidence.
    """
    return path.read_bytes().replace(CRLF, LF)


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
    # field-evidence payloads must never drift back to the stale locator text:
    # raw_value is auditable evidence, not a comment (2026-09-09 review).
    field_text = (CORPUS / "field_evidence.tsv").read_text(encoding="utf-8")
    assert "table:2" not in field_text
    assert "Table 2" not in field_text
    for _, row in validated.iterrows():
        assert int(row["ac_lower"]) == expected[row["population_label"]]
        assert int(row["ac_upper"]) == expected[row["population_label"]]
        assert int(row["an"]) % 2 == 0  # diploid autosomal denominator


# --- provenance backfill (issue #237) -------------------------------------------------------


def test_manifest_versions_validate_with_deterministic_ids() -> None:
    # the corrected snapshot carries all 70 matches; the published manifest still
    # carries the 37 the merged capture recorded
    for name, rows in ((PENDING_MANIFEST, 70), (PUBLISHED_MANIFEST, 37)):
        validated = validate_search_manifest(_read_tsv(name))
        assert len(validated) == rows, name
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
        rebuilt = BUILD_MANIFEST(
            _payload(entry),
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


def test_the_published_manifest_is_not_rewritten_by_this_backfill() -> None:
    """Re-deriving the manifest is a data revision, so it is deliberately out of scope here.

    The payloads reproduce the merged Q1/Q2 candidate sets exactly and show Q3's real 58, so a
    corrected snapshot and the published screening revision no longer describe the same capture.
    Tying them back together means publishing a manifest whose search_ids differ from the
    published ones, and that decision belongs to the maintainer rather than to a backfill. This
    asserts the split explicitly so neither file can drift into implying the other.
    """
    provenance = _provenance()
    pending = _read_tsv(PENDING_MANIFEST)
    published = _read_tsv(PUBLISHED_MANIFEST)

    # the corrected snapshot is one capture, all pending, one version
    assert len(pending) == 70
    assert set(pending["decision"]) == {"pending"}
    assert set(pending["manifest_version"]) == {provenance["discovery"]["manifest_version"]}
    assert set(pending["executed_at"]) == {
        entry["executed_at"] for entry in provenance["discovery"]["queries"]
    }

    # the published manifest still carries exactly the decisions the merged slice made
    assert len(published) == 37
    counts = published["decision"].value_counts()
    assert counts.sum() == len(published)
    assert set(counts.index) <= {"included", "excluded", "pending"}
    # This slice decides exactly two inclusions and no exclusions. Any exclusion here would be a
    # new judgement, and it has to arrive with a recorded reason: an exclusion with no reason is
    # the silent failure mode tracked in #242.
    assert counts.get("included", 0) == 2
    assert counts.get("excluded", 0) == 0
    excluded = published.loc[published["decision"] == "excluded"]
    assert excluded["decision_reason"].notna().all()
    # the two inclusions are the papers the audit record names
    assert set(published.loc[published["decision"] == "included", "candidate_id"]) == {
        "pmid:17701907",
        "pmid:15114531",
    }

    # and the two captures deliberately share no identifier, so neither can be mistaken for the
    # other's revision
    assert set(pending["search_id"]).isdisjoint(set(published["search_id"]))


def test_payloads_are_complete_captures_not_truncated() -> None:
    """Guard the defect this backfill found: no committed payload may be truncated.

    The merged slice shipped a manifest whose third query recorded 25 of 58 matches, because the
    capture was capped without recording the cap. `count == len(idlist)` is the invariant
    docs/literature-evidence-curation.md names — "a truncated or paginated response otherwise
    becomes a short, confident-looking manifest" — so it is asserted on every payload directly.
    """
    provenance = _provenance()
    for entry in provenance["discovery"]["queries"]:
        result = _payload(entry)["esearchresult"]
        assert int(result["count"]) == len(result["idlist"]), entry["name"]
        assert int(result["retmax"]) == len(result["idlist"]), entry["name"]


def test_third_query_records_every_match_not_the_truncated_twenty_five() -> None:
    """The corrected manifest must carry all 58 Q3 matches, not the merged 25."""
    provenance = _provenance()
    q3 = next(e for e in provenance["discovery"]["queries"] if e["name"] == "Q3")
    result = _payload(q3)["esearchresult"]
    assert int(result["count"]) == 58

    pending = _read_tsv(PENDING_MANIFEST)
    q3_rows = pending.loc[pending["query"] == q3["query"]]
    assert len(q3_rows) == 58

    # the published manifest is untouched, so it still records the truncated 25
    published = _read_tsv(PUBLISHED_MANIFEST)
    assert len(published.loc[published["query"] == q3["query"]]) == 25


def test_builder_covers_exactly_the_tracked_fields() -> None:
    fields = _read_tsv("field_evidence.tsv")
    assert len(fields) == 12 * len(TRACKED_FIELDS)
    for _, group in fields.groupby("source_record_id"):
        assert len(group) == len(TRACKED_FIELDS)
        assert set(group["field_name"]) == set(TRACKED_FIELDS)


def test_every_shipped_source_record_id_is_regenerated() -> None:
    """The 12 ids are derived, so the builder must reproduce them, not revalidate them."""
    evidence = _read_tsv("evidence.tsv")
    regenerated = {
        make_source_record_id(row["corpus_id"], row["record_source_id"], row["record_locator"])
        for _, row in evidence.iterrows()
    }
    assert regenerated == set(evidence["source_record_id"])
    assert evidence["source_record_id"].nunique() == 12


def test_provenance_records_the_extraction_timestamp_the_ledgers_use() -> None:
    evidence = _read_tsv("evidence.tsv")
    assert set(evidence["extracted_at"].dropna()) == {
        _provenance()["extraction"]["extracted_at"]
    }
    assert _provenance()["extraction"]["builder"] == "scripts/build_lct_enattah_fixture.py"


def test_builder_replay_reproduces_the_committed_ledgers(tmp_path: Path) -> None:
    """Replaying the builder must regenerate the shipped evidence and field files.

    Every input is explicit: the extraction timestamp comes from the provenance record rather than
    the wall clock, and the output must match what is committed, byte for byte.
    """
    out = tmp_path / "replay"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_lct_enattah_fixture.py"),
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
        assert _normalised(out / name) == _normalised(CORPUS_DIR / name), (
            f"{name} does not replay from the recorded inputs"
        )

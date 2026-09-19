"""Tests for scripts/check_manifest_payload_counts.py.

The check exists because a merged manifest recorded 25 candidates for a query that matched 58, and
nothing about the file looked wrong (#272). So the tests that matter are the ones that feed it the
disagreement and watch it refuse — a check whose removal breaks no test is the defect #299 records.

Every fixture is built in `tmp_path`; the committed corpora are read, never edited.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genomeos.observations.evidence import make_search_id  # noqa: E402
from scripts.check_manifest_payload_counts import inspect, main, read_manifest  # noqa: E402

CORPORA = ROOT / "tests/fixtures/literature"
QUERY = "rs4988235[All Fields] AND (population[Title/Abstract] OR frequency[Title/Abstract])"
EXECUTED_AT = "2026-09-12T04:08:25Z"
VERSION = "lct-rs4988235@2026-09-12.1"
HEADER = [
    "search_id", "corpus_id", "database", "query", "executed_at",
    "candidate_id", "decision", "decision_reason", "manifest_version",
]


def build_corpus(
    base: Path,
    *,
    payload_count: int = 58,
    payload_ids: int = 58,
    manifest_rows: int | None = None,
    manifest_version: str = VERSION,
    extra_tsv: bool = False,
) -> Path:
    corpus = base / "lct-enattah-2007"
    (corpus / "payloads").mkdir(parents=True)
    ids = [str(40_000_000 - index) for index in range(payload_ids)]
    (corpus / "payloads" / "Q3.json").write_text(
        json.dumps({"header": {"type": "esearch"}, "esearchresult": {
            "count": str(payload_count), "retmax": str(payload_ids), "idlist": ids}}),
        encoding="utf-8",
    )
    (corpus / "PROVENANCE.json").write_text(
        json.dumps({"corpus_id": "lct-rs4988235", "discovery": {
            "manifest_version": VERSION,
            "queries": [{"name": "Q3", "query": QUERY, "executed_at": EXECUTED_AT,
                         "payload": "payloads/Q3.json"}]}}),
        encoding="utf-8",
    )
    _write_manifest(
        corpus / "searches.pending.tsv",
        ids[:manifest_rows if manifest_rows is not None else payload_ids],
        version=manifest_version,
    )
    if extra_tsv:
        (corpus / "evidence.tsv").write_text(
            "source_record_id\tcorpus_id\tvariant_id\nsr-1\tlct-rs4988235\tchr2-135851076-G-A\n",
            encoding="utf-8",
        )
    return corpus


def _write_manifest(path: Path, ids: list[str], version: str = VERSION) -> None:
    search_id = make_search_id("pubmed", QUERY, EXECUTED_AT)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(HEADER)
        for pmid in ids:
            writer.writerow([search_id, "lct-rs4988235", "pubmed", QUERY, EXECUTED_AT,
                             f"pmid:{pmid}", "pending", "", version])


def test_both_committed_corpora_reconcile() -> None:
    """The check passes on what is on main, which is #248's acceptance evidence for its own row."""
    corpora = sorted(path for path in CORPORA.iterdir() if (path / "PROVENANCE.json").is_file())
    assert [path.name for path in corpora] == ["hbb-rs334-salih-2010", "lct-enattah-2007"]
    for corpus in corpora:
        assert inspect(corpus).problems == [], corpus.name


def test_truncated_manifest_is_refused(tmp_path: Path) -> None:
    """The historical defect: a capture capped at 25 while the query matched 58."""
    problems = inspect(build_corpus(tmp_path, manifest_rows=25)).problems
    assert len(problems) == 1
    assert "records 25 candidate(s)" in problems[0]
    assert "matching 58" in problems[0]


def test_payload_disagreeing_with_its_own_idlist_is_refused(tmp_path: Path) -> None:
    """The payload is validated, not trusted: its count must equal the identifiers it returned."""
    problems = inspect(build_corpus(tmp_path, payload_count=57)).problems
    assert any("does not equal its idlist length 58" in problem for problem in problems)


def test_non_numeric_and_duplicate_pmids_are_refused(tmp_path: Path) -> None:
    corpus = build_corpus(tmp_path)
    payload = json.loads((corpus / "payloads" / "Q3.json").read_text(encoding="utf-8"))
    payload["esearchresult"].update(count="3", idlist=["40000000", "40000000", "PMC123"])
    (corpus / "payloads" / "Q3.json").write_text(json.dumps(payload), encoding="utf-8")
    problems = inspect(corpus).problems
    assert any("non-numeric PMIDs" in problem for problem in problems)
    assert any("duplicate PMIDs" in problem for problem in problems)


def test_declared_version_with_no_manifest_is_refused(tmp_path: Path) -> None:
    """A provenance naming a version no committed file carries is a dangling claim, not a pass."""
    corpus = build_corpus(tmp_path, manifest_version="lct-rs4988235@2026-09-12.9")
    problems = inspect(corpus).problems
    assert any("records 0 candidate(s)" in problem and VERSION in problem for problem in problems)


def test_screening_version_does_not_satisfy_the_discovery_query(tmp_path: Path) -> None:
    """Screening republishes a snapshot under a new version keeping the same search_id.

    Matching rows by search_id alone compares a payload against the union of two manifests. The
    committed hbb corpus carries the same three search_ids in both files, one at .1 and one at .2,
    so this is the live shape rather than a hypothetical one.
    """
    corpus = build_corpus(tmp_path, payload_count=5, payload_ids=5)
    ids = [str(40_000_000 - index) for index in range(5)]
    _write_manifest(corpus / "searches.tsv", ids, version="lct-rs4988235@2026-09-12.2")
    result = inspect(corpus)
    assert result.problems == []
    assert "manifest 5 row(s)" in result.lines[1]


def test_a_non_manifest_tsv_is_not_read_as_an_empty_manifest(tmp_path: Path) -> None:
    """evidence.tsv shares the directory. Reading it as a manifest would report a truncation."""
    corpus = build_corpus(tmp_path, extra_tsv=True)
    assert read_manifest(corpus / "evidence.tsv") is None
    result = inspect(corpus)
    assert result.problems == []
    assert "1 manifest file(s)" in result.lines[0]


def test_missing_declared_payload_is_refused(tmp_path: Path) -> None:
    corpus = build_corpus(tmp_path)
    (corpus / "payloads" / "Q3.json").unlink()
    problems = inspect(corpus).problems
    assert any("declared payload Q3.json is absent" in problem for problem in problems)


def test_corpus_without_a_discovery_block_is_not_counted(tmp_path: Path) -> None:
    """Only a corpus that declares a payload is examined, so the published lct manifest is untouched."""
    corpus = tmp_path / "promotable"
    corpus.mkdir()
    (corpus / "PROVENANCE.json").write_text(json.dumps({"corpus_id": "promotable"}), encoding="utf-8")
    result = inspect(corpus)
    assert result.problems == [] and result.examined is False


def test_cli_refuses_a_missing_fixtures_root(tmp_path: Path) -> None:
    _run_main(["check_manifest_payload_counts.py", "--fixtures-root", str(tmp_path / "absent")], 1)


def test_cli_exits_nonzero_and_names_both_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    build_corpus(tmp_path, manifest_rows=25)
    _run_main(["check_manifest_payload_counts.py", "--fixtures-root", str(tmp_path)], 1)
    output = capsys.readouterr().out
    assert "records 25 candidate(s)" in output and "matching 58" in output
    assert "truncated or" in output


def test_cli_passes_on_the_committed_corpora(capsys: pytest.CaptureFixture) -> None:
    _run_main(["check_manifest_payload_counts.py"], 0)
    assert "reconciliation passed (2 corpora)" in capsys.readouterr().out


def _run_main(argv: list[str], expected: int) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", argv)
        assert main() == expected

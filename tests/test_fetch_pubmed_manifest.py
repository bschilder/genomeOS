"""Reproducible PubMed discovery-manifest tests (literature design §§4, 5.1)."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.evidence import (
    LITERATURE_SEARCH_COLUMNS,
    validate_search_manifest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pubmed" / "esearch_rs4988235.json"
BUILD_MANIFEST = runpy.run_path(
    Path(__file__).parents[1] / "scripts" / "fetch_pubmed_manifest.py"
)["build_manifest"]
QUERY = 'rs4988235[All Fields] AND ("allele frequency"[All Fields])'
EXECUTED_AT = "2026-09-05T12:00:00Z"
VERSION = "lct-rs4988235@2026-09-05.1"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text())


def _build(payload: dict | None = None) -> pd.DataFrame:
    return BUILD_MANIFEST(
        payload if payload is not None else _payload(),
        corpus_id="lct-rs4988235",
        query=QUERY,
        executed_at=EXECUTED_AT,
        manifest_version=VERSION,
    )


def test_build_manifest_is_schema_valid_pending_and_deterministic():
    first = _build()
    second = _build()

    validate_search_manifest(first)
    pd.testing.assert_frame_equal(first, second)
    assert tuple(first.columns) == LITERATURE_SEARCH_COLUMNS
    assert first["candidate_id"].tolist() == ["pmid:11788828", "pmid:29063188"]
    assert first["decision"].tolist() == ["pending", "pending"]
    assert first["decision_reason"].isna().all()
    assert first["executed_at"].unique().tolist() == [EXECUTED_AT]
    assert first["manifest_version"].unique().tolist() == [VERSION]
    assert first["search_id"].nunique() == 1
    assert first.iloc[0]["search_id"] == (
        "pubmed:1c2892a97e29463e3954bc4c78557ce2d07098d1dd00ccc2507e8c3cf78c55d7"
    )


def test_search_identity_changes_with_query_or_execution():
    original = _build().iloc[0]["search_id"]
    changed_query = BUILD_MANIFEST(
        _payload(),
        corpus_id="lct-rs4988235",
        query="rs4988235[Title/Abstract]",
        executed_at=EXECUTED_AT,
        manifest_version=VERSION,
    ).iloc[0]["search_id"]
    changed_time = BUILD_MANIFEST(
        _payload(),
        corpus_id="lct-rs4988235",
        query=QUERY,
        executed_at="2026-09-05T12:00:01Z",
        manifest_version=VERSION,
    ).iloc[0]["search_id"]
    assert len({original, changed_query, changed_time}) == 3


def test_duplicate_pubmed_candidates_are_rejected():
    payload = _payload()
    payload["esearchresult"]["idlist"].append("29063188")
    with pytest.raises(ValueError, match="duplicate PMID"):
        _build(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.pop("esearchresult"), "esearchresult"),
        (lambda payload: payload["esearchresult"].update(idlist=["PMID29063188"]), "PMID"),
        (lambda payload: payload["esearchresult"].update(count="3"), "count"),
    ],
)
def test_malformed_or_incomplete_esearch_payload_is_rejected(mutation, message):
    payload = _payload()
    mutation(payload)
    with pytest.raises(ValueError, match=message):
        _build(payload)

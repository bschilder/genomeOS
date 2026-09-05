"""Fetch a reproducible PubMed screening manifest (literature design §§4, 5.1).

Network I/O ends at this script. ``build_manifest`` converts a captured ESearch JSON payload into
the frozen discovery contract without deciding which papers to include; every candidate begins as
pending and must be screened in a later immutable manifest version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

from genomeos.observations.evidence import (
    LITERATURE_SEARCH_COLUMNS,
    validate_search_manifest,
)

DATABASE = "pubmed"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def _search_id(query: str, executed_at: str) -> str:
    identity = json.dumps(
        [DATABASE, query, executed_at], ensure_ascii=False, separators=(",", ":")
    )
    return f"{DATABASE}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def _candidate_ids(payload: dict[str, Any]) -> list[str]:
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        raise ValueError("PubMed payload must contain an esearchresult object")
    raw_ids = result.get("idlist")
    if not isinstance(raw_ids, list):
        raise ValueError("PubMed esearchresult.idlist must be a list")
    if any(not isinstance(value, str) or not value.isascii() or not value.isdigit() for value in raw_ids):
        raise ValueError("every PubMed candidate must be a numeric PMID")
    if any(value.startswith("0") for value in raw_ids):
        raise ValueError("every PubMed candidate must be a positive canonical PMID")
    if len(raw_ids) != len(set(raw_ids)):
        raise ValueError("PubMed payload contains a duplicate PMID")
    try:
        count = int(result["count"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PubMed esearchresult.count must be an integer string") from error
    if count != len(raw_ids):
        raise ValueError(
            f"PubMed result count {count} does not equal captured idlist length {len(raw_ids)}"
        )
    return sorted(raw_ids, key=int)


def build_manifest(
    payload: dict[str, Any],
    corpus_id: str,
    query: str,
    executed_at: str,
    manifest_version: str,
) -> pd.DataFrame:
    """Convert one complete ESearch response into pending screening rows."""
    if not isinstance(payload, dict):
        raise ValueError("PubMed payload must be a JSON object")
    search_id = _search_id(query, executed_at)
    rows = [
        {
            "search_id": search_id,
            "corpus_id": corpus_id,
            "database": DATABASE,
            "query": query,
            "executed_at": executed_at,
            "candidate_id": f"pmid:{pmid}",
            "decision": "pending",
            "decision_reason": pd.NA,
            "manifest_version": manifest_version,
        }
        for pmid in _candidate_ids(payload)
    ]
    frame = pd.DataFrame(rows, columns=LITERATURE_SEARCH_COLUMNS)
    return validate_search_manifest(frame)


def _fetch(query: str, timeout: float) -> dict[str, Any]:
    parameters = urllib.parse.urlencode(
        {"db": DATABASE, "term": query, "retmode": "json", "retmax": 100_000}
    )
    request = urllib.request.Request(
        f"{ESEARCH_URL}?{parameters}", headers={"User-Agent": "genomeOS-literature-manifest/1"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        raise ValueError("PubMed returned a non-object JSON payload")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--executed-at", required=True, help="UTC timestamp ending in Z")
    parser.add_argument("--manifest-version", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    manifest = build_manifest(
        _fetch(args.query, args.timeout),
        corpus_id=args.corpus_id,
        query=args.query,
        executed_at=args.executed_at,
        manifest_version=args.manifest_version,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.out, sep="\t", index=False, na_rep="")
    print(f"wrote {len(manifest)} pending PubMed candidates to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

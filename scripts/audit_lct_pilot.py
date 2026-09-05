"""Audit the commit-pinned LCT pilot without manufacturing P1 facts (design §§4, 5.2, 8).

The upstream CSV is an inventory input, not a trusted observation table. Each complete source row
receives a content-addressed locator. Only values physically present in target-compatible columns
enter the evidence proposal; source coordinates and all unreviewed scientific metadata stay out.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
from pathlib import Path

import pandas as pd

from genomeos.observations.evidence import (
    FIELD_EVIDENCE_COLUMNS,
    LITERATURE_EVIDENCE_COLUMNS,
    TRACKED_FIELDS,
    make_source_record_id,
    validate_literature_tables,
)

CORPUS_ID = "lct-rs4988235"
UPSTREAM_COMMIT = "7c2b1cc6bb783b56fdfffaed5c44d8e8273da994"
UPSTREAM_PATH = "data/lct_rs4988235_observations.csv"
RECORD_SOURCE_ID = (
    "repo:github.com/manpreetbola/protective-alleles-gnomad-v4@"
    f"{UPSTREAM_COMMIT}:{UPSTREAM_PATH}"
)
RECORD_SOURCE_URL = (
    "https://raw.githubusercontent.com/manpreetbola/protective-alleles-gnomad-v4/"
    f"{UPSTREAM_COMMIT}/{UPSTREAM_PATH}"
)
UPSTREAM_COLUMNS = (
    "population",
    "country",
    "continent",
    "lat",
    "lon",
    "an",
    "ac",
    "af_reported",
    "source_type",
    "pmid",
    "original_ref",
    "status_notes",
)
REPORTED_FIELDS = {
    "population_label": "population",
    "an": "an",
    "ac_lower": "ac",
    "ac_upper": "ac",
    "reported_frequency": "af_reported",
    "citation_text": "original_ref",
}


def _validate_source(frame: pd.DataFrame) -> None:
    if tuple(frame.columns) != UPSTREAM_COLUMNS:
        raise ValueError(
            f"expected exact upstream columns {UPSTREAM_COLUMNS}, got {tuple(frame.columns)}"
        )
    for column in frame.columns:
        if not frame[column].map(lambda value: isinstance(value, str)).all():
            raise ValueError(f"upstream column {column} must be loaded as literal strings")
        for value in frame[column]:
            if any(char in value for char in "\t\r\n"):
                raise ValueError(f"upstream column {column} contains control whitespace")
    emitted_columns = {*REPORTED_FIELDS.values(), "status_notes"}
    for column in emitted_columns:
        if frame[column].map(lambda value: value != value.strip()).any():
            raise ValueError(f"emitted upstream column {column} contains surrounding whitespace")
    for column in set(UPSTREAM_COLUMNS) - {"pmid"}:
        if frame[column].eq("").any():
            raise ValueError(f"upstream column {column} contains a blank required value")


def _record_locator(row: pd.Series) -> str:
    canonical = json.dumps(
        [row[column] for column in UPSTREAM_COLUMNS],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"dataset-record:sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _integer(value: str, name: str) -> int:
    if re.fullmatch(r"0|[1-9][0-9]*", value) is None:
        raise ValueError(f"upstream {name} must be a canonical non-negative integer")
    return int(value)


def _main_row(
    source: pd.Series, record_locator: str, extracted_at: str, ingest_version: str
) -> dict[str, object]:
    an = _integer(source["an"], "an")
    ac = _integer(source["ac"], "ac")
    row: dict[str, object] = {column: pd.NA for column in LITERATURE_EVIDENCE_COLUMNS}
    row.update(
        {
            "source_record_id": make_source_record_id(
                CORPUS_ID, RECORD_SOURCE_ID, record_locator
            ),
            "corpus_id": CORPUS_ID,
            "normalization_status": "unresolved",
            "population_label": source["population"],
            "an": an,
            "ac_lower": ac,
            "ac_upper": ac,
            "reported_frequency": source["af_reported"],
            "citation_text": source["original_ref"],
            "record_source_id": RECORD_SOURCE_ID,
            "record_locator": record_locator,
            "record_source_url": RECORD_SOURCE_URL,
            "verification_status": "pending",
            "extraction_method": "automated_proposal",
            "extracted_by": f"import:lct-pilot@{UPSTREAM_COMMIT}",
            "extracted_at": extracted_at,
            "reuse_status": "not_checked",
            "notes": source["status_notes"],
            "ingest_version": ingest_version,
        }
    )
    return row


def _field_rows(main: dict[str, object], source: pd.Series) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    record_locator = str(main["record_locator"])
    for field_name in TRACKED_FIELDS:
        source_column = REPORTED_FIELDS.get(field_name)
        if source_column is None:
            rows.append(
                {
                    "source_record_id": main["source_record_id"],
                    "field_name": field_name,
                    "evidence_status": "not_reviewed",
                    "raw_value": pd.NA,
                    "evidence_source_id": pd.NA,
                    "source_locator": pd.NA,
                    "checked_scope": pd.NA,
                    "derivation_method": pd.NA,
                    "decision_reference": pd.NA,
                    "notes": "Automated migration did not review or claim this field.",
                }
            )
            continue
        rows.append(
            {
                "source_record_id": main["source_record_id"],
                "field_name": field_name,
                "evidence_status": "reported",
                "raw_value": source[source_column],
                "evidence_source_id": RECORD_SOURCE_ID,
                "source_locator": f"{record_locator},column:{source_column}",
                "checked_scope": pd.NA,
                "derivation_method": pd.NA,
                "decision_reference": pd.NA,
                "notes": pd.NA,
            }
        )
    return rows


def _count_inventory(notes: pd.Series) -> dict[str, int]:
    reconstructed = notes.str.startswith("approx_count:")
    exact = notes.eq("exact_count") | notes.str.startswith("CORRECTED")
    return {
        "basis_unresolved": int((~reconstructed & ~exact).sum()),
        "exact": int(exact.sum()),
        "frequency_reconstructed": int(reconstructed.sum()),
    }


def migrate(
    frame: pd.DataFrame,
    *,
    extracted_at: str,
    ingest_version: str,
    expected_rows: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Inventory an upstream frame and emit structurally valid, always-pending proposals."""
    _validate_source(frame)
    if len(frame) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows, found {len(frame)}")

    locators = frame.apply(_record_locator, axis=1)
    duplicated = sorted(locators.loc[locators.duplicated(keep=False)].unique())
    if duplicated:
        raise ValueError(f"duplicate immutable record anchor: {duplicated}")

    evidence_rows: list[dict[str, object]] = []
    field_rows: list[dict[str, object]] = []
    for (_, source), record_locator in zip(frame.iterrows(), locators, strict=True):
        main = _main_row(source, record_locator, extracted_at, ingest_version)
        evidence_rows.append(main)
        field_rows.extend(_field_rows(main, source))
    evidence, fields = validate_literature_tables(
        pd.DataFrame(evidence_rows, columns=LITERATURE_EVIDENCE_COLUMNS),
        pd.DataFrame(field_rows, columns=FIELD_EVIDENCE_COLUMNS),
    )

    reconciliation = {
        "all_rows_assigned_exactly_one_anchor": (
            len(evidence) == len(frame)
            and evidence["source_record_id"].is_unique
            and len(fields) == len(frame) * len(TRACKED_FIELDS)
        ),
        "duplicate_immutable_anchors": duplicated,
        "evidence_rows": len(evidence),
        "field_evidence_rows": len(fields),
        "input_rows": len(frame),
        "unique_immutable_anchors": len(set(locators)),
    }
    if not reconciliation["all_rows_assigned_exactly_one_anchor"]:
        raise ValueError("not every input row was assigned exactly one evidence anchor")

    report: dict[str, object] = {
        "audit_version": "lct-pilot-audit@2026-09-05.1",
        "source": {
            "commit": UPSTREAM_COMMIT,
            "path": UPSTREAM_PATH,
            "record_source_id": RECORD_SOURCE_ID,
            "url": RECORD_SOURCE_URL,
        },
        "reconciliation": reconciliation,
        "coverage": {
            "country_label_count": int(frame["country"].nunique()),
            "count_inventory": _count_inventory(frame["status_notes"]),
            "source_format_anomalies": {
                "surrounding_whitespace_by_column": {
                    column: int(frame[column].map(lambda value: value != value.strip()).sum())
                    for column in UPSTREAM_COLUMNS
                }
            },
            "source_column_missingness": {
                column: int(frame[column].eq("").sum()) for column in UPSTREAM_COLUMNS
            },
            "target_field_missingness": {
                field: int(evidence[field].isna().sum()) for field in TRACKED_FIELDS
            },
        },
        "safeguards": {
            "source_coordinates_imported": False,
            "uncertainty_radius_invented": False,
            "unreviewed_scientific_metadata_invented": False,
        },
    }
    return evidence, fields, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-rows", type=int, required=True)
    parser.add_argument("--extracted-at", required=True)
    parser.add_argument("--ingest-version", required=True)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--field-evidence-out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    args = parser.parse_args()

    frame = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    evidence, fields, report = migrate(
        frame,
        extracted_at=args.extracted_at,
        ingest_version=args.ingest_version,
        expected_rows=args.expected_rows,
    )
    for path in (args.evidence_out, args.field_evidence_out, args.report_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(args.evidence_out, sep="\t", index=False, na_rep="")
    fields.to_csv(args.field_evidence_out, sep="\t", index=False, na_rep="")
    command = [
        ".venv/bin/python",
        "scripts/audit_lct_pilot.py",
        "--input",
        str(args.input),
        "--expected-rows",
        str(args.expected_rows),
        "--extracted-at",
        args.extracted_at,
        "--ingest-version",
        args.ingest_version,
        "--evidence-out",
        str(args.evidence_out),
        "--field-evidence-out",
        str(args.field_evidence_out),
        "--report-out",
        str(args.report_out),
    ]
    report["command"] = shlex.join(command)
    report["input_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.report_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"audited {len(evidence)}/{args.expected_rows} LCT rows; "
        f"wrote {len(fields)} field-evidence decisions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

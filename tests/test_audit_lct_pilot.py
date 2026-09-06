"""LCT pilot inventory and non-inventive migration tests (literature design §§5.2, 8)."""

from __future__ import annotations

import runpy
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.evidence import TRACKED_FIELDS, validate_literature_tables

ROOT = Path(__file__).parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "literature" / "lct_pilot_sample.csv"
MODULE = runpy.run_path(ROOT / "scripts" / "audit_lct_pilot.py")
MIGRATE = MODULE["migrate"]
SOURCE_ID = (
    "repo:github.com/manpreetbola/protective-alleles-gnomad-v4@"
    "7c2b1cc6bb783b56fdfffaed5c44d8e8273da994:"
    "data/lct_rs4988235_observations.csv"
)


def _frame() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, dtype=str, keep_default_na=False)


def _migrate(frame: pd.DataFrame | None = None):
    return MIGRATE(
        _frame() if frame is None else frame,
        extracted_at="2026-09-05T12:00:00Z",
        ingest_version="lct-rs4988235@2026-09-05.1",
        expected_rows=3,
    )


def test_migration_emits_valid_pending_evidence_without_invented_metadata():
    evidence, fields, report = _migrate()

    validate_literature_tables(evidence, fields)
    assert len(evidence) == 3
    assert len(fields) == 3 * len(TRACKED_FIELDS)
    assert evidence["record_source_id"].unique().tolist() == [SOURCE_ID]
    assert evidence["record_locator"].str.match(r"^dataset-record:sha256:[0-9a-f]{64}$").all()
    assert evidence["source_record_id"].str.match(
        r"^literature:lct-rs4988235:[0-9a-f]{64}$"
    ).all()
    assert (evidence["extraction_method"] == "automated_proposal").all()
    assert (evidence["verification_status"] == "pending").all()
    assert evidence[["verified_by", "verified_at", "verification_reference"]].isna().all().all()
    assert evidence["reuse_status"].eq("not_checked").all()

    prohibited = [
        "cohort_id",
        "assay",
        "sampling_design",
        "disease_ascertainment_excluded",
        "date_lower",
        "date_upper",
        "variant_id",
        "rsid",
        "counted_allele",
        "count_basis",
        "denominator_basis",
    ]
    assert evidence[prohibited].isna().all().all()
    assert not {"lat", "lon", "country", "uncertainty_radius_km", "radius_km"}.intersection(
        evidence.columns
    )
    unresolved = fields.loc[fields["field_name"].isin(prohibited)]
    assert unresolved["evidence_status"].eq("not_reviewed").all()
    assert unresolved["source_locator"].isna().all()
    assert unresolved["evidence_source_id"].isna().all()
    assert report["safeguards"]["source_coordinates_imported"] is False
    assert report["safeguards"]["uncertainty_radius_invented"] is False


def test_source_present_values_are_preserved_as_source_located_proposals():
    evidence, fields, _ = _migrate()
    first = evidence.loc[evidence["population_label"] == "Sami"].iloc[0]
    assert (first["an"], first["ac_lower"], first["ac_upper"]) == (58, 17, 17)
    assert first["reported_frequency"] == "0.29310344827586204"
    assert first["citation_text"] == "Liebert et al. (2017) Hum Genet. 136 1445-1453"
    first_fields = fields.loc[fields["source_record_id"] == first["source_record_id"]]
    reported = first_fields.set_index("field_name")["evidence_status"]
    for name in (
        "population_label",
        "an",
        "ac_lower",
        "ac_upper",
        "reported_frequency",
        "citation_text",
    ):
        assert reported[name] == "reported"
    assert first_fields.loc[
        first_fields["evidence_status"] == "reported", "source_locator"
    ].str.contains(",column:").all()


def test_content_anchors_are_order_independent_and_duplicate_rows_fail():
    evidence, _, _ = _migrate()
    reversed_evidence, _, _ = _migrate(_frame().iloc[::-1].reset_index(drop=True))
    assert sorted(evidence["source_record_id"]) == sorted(reversed_evidence["source_record_id"])

    duplicated = pd.concat([_frame().iloc[:2], _frame().iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate immutable record anchor"):
        _migrate(duplicated)


def test_inventory_reconciles_every_row_without_guessing_count_basis():
    _, _, report = _migrate()
    assert report["reconciliation"] == {
        "all_rows_assigned_exactly_one_anchor": True,
        "duplicate_immutable_anchors": [],
        "evidence_rows": 3,
        "field_evidence_rows": 57,
        "input_rows": 3,
        "unique_immutable_anchors": 3,
    }
    assert report["coverage"]["country_label_count"] == 3
    assert report["coverage"]["count_inventory"] == {
        "basis_unresolved": 1,
        "exact": 1,
        "frequency_reconstructed": 1,
    }
    assert report["coverage"]["target_field_missingness"]["count_basis"] == 3


def test_ignored_coordinate_format_anomaly_is_recorded_without_becoming_metadata():
    frame = _frame()
    frame.loc[0, "lon"] = "\N{NO-BREAK SPACE}" + frame.loc[0, "lon"]
    evidence, _, report = _migrate(frame)
    assert "lon" not in evidence
    assert report["coverage"]["source_format_anomalies"][
        "surrounding_whitespace_by_column"
    ]["lon"] == 1


def test_expected_row_count_is_an_acceptance_gate():
    with pytest.raises(ValueError, match="expected 426 rows"):
        MIGRATE(
            _frame(),
            extracted_at="2026-09-05T12:00:00Z",
            ingest_version="lct-rs4988235@2026-09-05.1",
            expected_rows=426,
        )

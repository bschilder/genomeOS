"""Isolated software fixtures, never scientific validation or published evidence."""

from __future__ import annotations

import math

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from genomeos.evidence.api import evidence_associations
from genomeos.evidence.policy import provenance_issues, validate_p_value
from genomeos.evidence.query import associations, audit
from genomeos.evidence.schema import EvidencePage
from genomeos.models import Association, SourceAsset, SourceRelease
from tests.test_api import seed


def query(session, **kwargs):
    return associations(session, variant=None, limit=50, offset=0, **kwargs)


def test_empty_is_not_negative_evidence(db_session):
    result = query(db_session, phenotype_id=123)
    assert result.status == "unavailable"
    assert result.coverage == "selective_index_only"
    assert result.total_indexed_matches == result.examined == 0
    report = audit(db_session)
    assert report.association_count == report.phenotype_count == report.release_count == 0
    assert not db_session.new


def test_fixture_sources_cannot_be_served(db_session):
    phenotype = seed(db_session)
    page = query(db_session, phenotype_id=phenotype.id)
    assert page.items == []
    assert len(page.refusals) == page.total_indexed_matches
    assert all("source_location_not_qualified" in r.reasons for r in page.refusals)
    assert "fixture://" not in page.model_dump_json()


def qualify_software_fixture(session):
    # These fabricated rows test the adapter only. No fetch or production export occurs.
    phenotype = seed(session)
    for asset in session.query(SourceAsset):
        asset.uri = "https://pan-ukb-us-east-1.s3.amazonaws.com/software-test.tsv.bgz"
        asset.checksum = "a" * 64
    session.commit()
    return phenotype


def test_exact_identity_missing_scale_and_unknown_qc(db_session):
    phenotype = qualify_software_fixture(db_session)
    row = db_session.query(Association).first()
    row.low_confidence = None
    db_session.commit()
    page = query(db_session, phenotype_id=phenotype.id)
    value = next(item for item in page.items if item.association_id == row.id)
    assert value.low_confidence is None
    assert value.effect_scale == "unrecorded"
    assert value.trait.modifier == "irnt"
    assert value.effect_allele == value.variant.split(":")[-1]
    assert value.provenance.sha256 == "a" * 64
    exact = associations(db_session, variant=value.variant, phenotype_id=None, limit=1, offset=0)
    assert len(exact.items) == 1
    assert exact.items[0].variant == value.variant
    empty = associations(db_session, variant=value.variant, phenotype_id=None, limit=1, offset=999)
    assert empty.examined == 0
    assert empty.total_indexed_matches == exact.total_indexed_matches


@pytest.mark.parametrize(
    "changes",
    [{"beta": math.inf}, {"standard_error": -1.0}, {"allele_frequency": 1.1}, {"population_code": "unknown"}],
)
def test_corrupt_rows_fail_instead_of_disappearing(db_session, changes):
    phenotype = qualify_software_fixture(db_session)
    row = db_session.query(Association).first()
    for key, value in changes.items():
        setattr(row, key, value)
    db_session.commit()
    with pytest.raises(ValidationError):
        query(db_session, phenotype_id=phenotype.id)


def test_release_mismatch_is_hard_error(db_session):
    phenotype = qualify_software_fixture(db_session)
    first = db_session.query(SourceRelease).first()
    second = SourceRelease(source_id=first.source_id, version="other-release")
    db_session.add(second)
    db_session.flush()
    phenotype.release_id = second.id
    db_session.commit()
    with pytest.raises(ValueError, match="different releases"):
        query(db_session, phenotype_id=phenotype.id)


@pytest.mark.parametrize("variant", ["rs334", "GRCh38:11:5227002:T:A", "GRCh37:1:0:A:G"])
def test_no_identity_fallback(db_session, variant):
    with pytest.raises(HTTPException) as error:
        evidence_associations(variant, None, 50, 0, db_session)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "uri",
    [
        "fixture://x",
        "https://user:secret@pan-ukb-us-east-1.s3.amazonaws.com/a",
        "https://pan-ukb-us-east-1.s3.amazonaws.com/a?token=secret",
        "https://unrelated.org/file",
        "https://[broken",
    ],
)
def test_provenance_locations_refuse_private_or_unqualified_values(uri):
    assert "source_location_not_qualified" in provenance_issues("pan-ukb", uri, "a" * 64)


def test_p_encoding_consistency():
    validate_p_value(-8 * math.log(10), "ln", 8.0)
    validate_p_value(1e-8, "raw", 8.0)
    for encoded, encoding, canonical in [
        (1, "ln", 8),
        (8, "raw", 8),
        (8, "ln", 8),
        (8, "unknown", 8),
        (math.inf, "neg_log10", 8),
    ]:
        with pytest.raises(ValueError):
            validate_p_value(encoded, encoding, canonical)


def test_contract_requires_explicit_fields_and_reconciled_counts(db_session):
    value = query(db_session, phenotype_id=1).model_dump()
    value["examined"] = 1
    with pytest.raises(ValidationError):
        EvidencePage.model_validate(value)
    value["examined"] = 0
    del value["coverage"]
    with pytest.raises(ValidationError):
        EvidencePage.model_validate(value)


def test_audit_counts_and_checksums(db_session):
    seed(db_session)
    value = audit(db_session)
    assert value.association_count > 0
    assert sum(a.indexed_associations for a in value.assets) == value.association_count
    assert any("source_sha256_unrecorded" in a.issues for a in value.assets)
    assert all("source_location_not_qualified" in a.issues for a in value.assets)
    assert value.orphan_associations == 0


def test_corrupt_statistics_still_fail_when_source_is_unqualified(db_session):
    phenotype = seed(db_session)
    row = db_session.query(Association).first()
    row.standard_error = -2.0
    db_session.commit()
    with pytest.raises(ValidationError):
        query(db_session, phenotype_id=phenotype.id)


def test_audit_is_bounded_with_explicit_total(db_session):
    seed(db_session)
    first = audit(db_session, limit=1, offset=0)
    second = audit(db_session, limit=1, offset=1)
    assert first.asset_count == second.asset_count == 2
    assert len(first.assets) == len(second.assets) == 1
    assert first.assets[0].asset_id != second.assets[0].asset_id
    with pytest.raises(ValueError):
        audit(db_session, limit=0)


def test_http_contract_without_scientific_seed(tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from genomeos.api import app
    from genomeos.db import Base, get_session

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        client = TestClient(app)
        response = client.get("/v1/evidence/associations", params={"phenotype_id": 1})
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"
        assert client.get("/v1/evidence/associations").status_code == 422
        assert client.get("/v1/evidence/audit?limit=201").status_code == 422
        assert client.get("/v1/evidence/audit").json()["association_count"] == 0
        page = client.get("/evidence")
        assert page.status_code == 200
        assert "Missing evidence does not mean no association" in page.text
    finally:
        app.dependency_overrides.pop(get_session)
        engine.dispose()


def test_import_records_actual_source_bytes_and_refuses_replacement(db_session, tmp_path):
    import hashlib
    from pathlib import Path

    from genomeos.ingest import IngestionError, ingest_associations

    phenotype = seed(db_session)
    source = Path(__file__).parent / "fixtures" / "associations.tsv"
    asset = db_session.query(SourceAsset).filter_by(asset_type="phenotype_sumstats").one()
    assert asset.checksum == hashlib.sha256(source.read_bytes()).hexdigest()
    replacement = tmp_path / "changed.tsv"
    replacement.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(IngestionError, match="bytes changed"):
        ingest_associations(db_session, replacement, phenotype_id=phenotype.id, source_uri=asset.uri)

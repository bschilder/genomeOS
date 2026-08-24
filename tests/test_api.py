from pathlib import Path

from fastapi import HTTPException

from genomeos.api import list_phenotypes, phenotype_region, top_associations
from genomeos.ingest import ingest_associations, ingest_phenotype_manifest
from genomeos.models import Phenotype

FIXTURES = Path(__file__).parent / "fixtures"


def seed(session):
    with (FIXTURES / "phenotypes.tsv").open() as stream:
        ingest_phenotype_manifest(
            session, stream, version="test-2026", source_uri="fixture://phenotypes"
        )
    phenotype = session.query(Phenotype).filter_by(phenocode="21001").one()
    ingest_associations(
        session,
        FIXTURES / "associations.tsv",
        phenotype_id=phenotype.id,
        source_uri="fixture://bmi.tsv.bgz",
    )
    return phenotype


def test_phenotype_search(db_session):
    seed(db_session)
    page = list_phenotypes(
        q="mass", trait_type=None, population="AFR", limit=50, offset=0, session=db_session
    )
    assert page.total == 1
    assert page.items[0].native_key == "continuous:21001:both_sexes::irnt"


def test_top_associations_include_provenance(db_session):
    phenotype = seed(db_session)
    page = top_associations(
        phenotype_id=phenotype.id,
        population=None,
        min_neg_log10_p=7.30103,
        include_low_confidence=False,
        limit=100,
        offset=0,
        session=db_session,
    )
    assert page.total == 3
    assert page.items[0].provenance.license == "CC-BY-4.0"
    assert page.items[0].variant.startswith("GRCh37:")


def test_region_queries_are_disabled_by_default(db_session):
    phenotype = seed(db_session)
    try:
        phenotype_region(
            phenotype_id=phenotype.id,
            region="1:1-2000",
            limit=100,
            session=db_session,
        )
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("region query should be disabled")

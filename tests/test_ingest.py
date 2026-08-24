from pathlib import Path

import pytest

from genomeos.ingest import IngestionError, ingest_associations, ingest_phenotype_manifest
from genomeos.models import Association, Phenotype

FIXTURES = Path(__file__).parent / "fixtures"


def seed_manifest(session):
    with (FIXTURES / "phenotypes.tsv").open() as stream:
        assert ingest_phenotype_manifest(
            session, stream, version="test-2026", source_uri="fixture://phenotypes"
        ) == 2


def test_manifest_preserves_composite_identity_and_populations(db_session):
    seed_manifest(db_session)
    phenotype = db_session.query(Phenotype).filter_by(phenocode="21001").one()
    assert phenotype.native_key == "continuous:21001:both_sexes::irnt"
    assert {population.code for population in phenotype.populations} == {"AFR", "EUR"}
    assert phenotype.populations[0].n_cases is not None


def test_selective_association_index(db_session):
    seed_manifest(db_session)
    phenotype = db_session.query(Phenotype).filter_by(phenocode="21001").one()
    inserted = ingest_associations(
        db_session,
        FIXTURES / "associations.tsv",
        phenotype_id=phenotype.id,
        source_uri="fixture://bmi.tsv.bgz",
    )
    assert inserted == 3
    assert db_session.query(Association).count() == 3
    assert {item.population_code for item in db_session.query(Association)} == {
        "AFR",
        "EUR",
        "META_HQ",
    }
    assert ingest_associations(
        db_session,
        FIXTURES / "associations.tsv",
        phenotype_id=phenotype.id,
        source_uri="fixture://bmi.tsv.bgz",
    ) == 3
    assert db_session.query(Association).count() == 3


def test_ambiguous_pvalue_fails_closed(db_session, tmp_path):
    seed_manifest(db_session)
    phenotype = db_session.query(Phenotype).first()
    path = tmp_path / "ambiguous.tsv"
    path.write_text("chr\tpos\tref\talt\tpval_AFR\n1\t1\tA\tG\t8\n")
    with pytest.raises(IngestionError, match="ambiguous p-value"):
        ingest_associations(
            db_session,
            path,
            phenotype_id=phenotype.id,
            source_uri="fixture://ambiguous",
        )

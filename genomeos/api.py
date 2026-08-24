from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .db import get_session, init_db
from .models import Association, Phenotype, SourceAsset, SourceRelease, Variant
from .schemas import AssociationOut, Page, PhenotypeOut, ProvenanceOut
from .tabix import Region, RegionQueryUnavailable, TabixRegionReader

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="GenomeOS", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/panukb/phenotypes", response_model=Page)
def list_phenotypes(
    q: str | None = None,
    trait_type: str | None = None,
    population: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    statement = select(Phenotype).options(joinedload(Phenotype.populations))
    if q:
        pattern = f"%{q}%"
        statement = statement.where(
            or_(Phenotype.description.ilike(pattern), Phenotype.phenocode.ilike(pattern))
        )
    if trait_type:
        statement = statement.where(Phenotype.trait_type == trait_type)
    if population:
        statement = statement.where(Phenotype.populations.any(code=population.upper()))
    count = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(statement.order_by(Phenotype.id).offset(offset).limit(limit)).unique()
    return Page(
        items=[PhenotypeOut.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
        total=count,
    )


@app.get("/v1/panukb/phenotypes/{phenotype_id}", response_model=PhenotypeOut)
def get_phenotype(phenotype_id: int, session: Session = Depends(get_session)):
    phenotype = session.scalar(
        select(Phenotype)
        .options(joinedload(Phenotype.populations))
        .where(Phenotype.id == phenotype_id)
    )
    if phenotype is None:
        raise HTTPException(404, "phenotype not found")
    return phenotype


def _association_out(association: Association, session: Session) -> AssociationOut:
    asset = session.get(SourceAsset, association.source_asset_id)
    release = session.get(SourceRelease, asset.release_id)
    return AssociationOut(
        id=association.id,
        phenotype_id=association.phenotype_id,
        variant=association.variant.canonical_id,
        population=association.population_code,
        analysis_kind=association.analysis_kind,
        beta=association.beta,
        standard_error=association.standard_error,
        allele_frequency=association.allele_frequency,
        neg_log10_p=association.neg_log10_p,
        low_confidence=association.low_confidence,
        provenance=ProvenanceOut(
            source=release.source.slug,
            release=release.version,
            asset_uri=asset.uri,
            source_row=association.source_row,
            license=release.source.license_id,
        ),
    )


@app.get("/v1/panukb/phenotypes/{phenotype_id}/top-associations", response_model=Page)
def top_associations(
    phenotype_id: int,
    population: str | None = None,
    min_neg_log10_p: float = Query(7.30103, ge=0),
    include_low_confidence: bool = False,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    statement = (
        select(Association)
        .options(joinedload(Association.variant))
        .where(
            Association.phenotype_id == phenotype_id,
            Association.neg_log10_p >= min_neg_log10_p,
        )
    )
    if population:
        statement = statement.where(Association.population_code == population.upper())
    if not include_low_confidence:
        statement = statement.where(or_(Association.low_confidence.is_(False), Association.low_confidence.is_(None)))
    count = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    associations = session.scalars(
        statement.order_by(Association.neg_log10_p.desc()).offset(offset).limit(limit)
    ).all()
    return Page(
        items=[_association_out(item, session) for item in associations],
        limit=limit,
        offset=offset,
        total=count,
    )


@app.get("/v1/panukb/variants/{variant_id}/associations", response_model=Page)
def variant_associations(
    variant_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    parts = variant_id.split(":")
    if len(parts) != 5:
        raise HTTPException(422, "variant must be assembly:chromosome:position:ref:alt")
    assembly, chromosome, position, reference, alternate = parts
    try:
        position_int = int(position)
    except ValueError as exc:
        raise HTTPException(422, "variant position must be an integer") from exc
    variant = session.scalar(
        select(Variant).where(
            Variant.assembly == assembly,
            Variant.chromosome == chromosome,
            Variant.position == position_int,
            Variant.reference == reference,
            Variant.alternate == alternate,
        )
    )
    if variant is None:
        raise HTTPException(404, "variant not present in the selective index")
    statement = (
        select(Association)
        .options(joinedload(Association.variant))
        .where(Association.variant_id == variant.id)
    )
    count = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    associations = session.scalars(
        statement.order_by(Association.neg_log10_p.desc()).offset(offset).limit(limit)
    ).all()
    return Page(
        items=[_association_out(item, session) for item in associations],
        limit=limit,
        offset=offset,
        total=count,
    )


@app.get("/v1/panukb/phenotypes/{phenotype_id}/regions/{region}")
def phenotype_region(
    phenotype_id: int,
    region: str,
    limit: int = Query(1000, ge=1, le=10000),
    session: Session = Depends(get_session),
):
    if not settings.region_query_enabled:
        raise HTTPException(503, "federated region queries are disabled")
    phenotype = session.get(Phenotype, phenotype_id)
    if phenotype is None:
        raise HTTPException(404, "phenotype not found")
    if not phenotype.summary_stats_uri:
        raise HTTPException(404, "summary-statistics asset is not registered")
    try:
        parsed = Region.parse(region)
        rows = TabixRegionReader().fetch(
            phenotype.summary_stats_uri,
            parsed,
            limit=min(limit, settings.region_max_rows),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RegionQueryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "phenotype_id": phenotype_id,
        "region": region,
        "rows": rows,
        "provenance": {
            "source": "pan-ukb",
            "asset_uri": phenotype.summary_stats_uri,
            "index_uri": phenotype.summary_stats_index_uri,
            "license": "CC-BY-4.0",
        },
    }

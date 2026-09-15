"""Bounded SQL read adapter for trait evidence (Atlas design §10).

No ingestion, normalization, map linkage, or inference occurs here. A refused row
is accounted for explicitly; malformed stored values fail the request.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from genomeos.models import Association, DataSource, Phenotype, SourceAsset, SourceRelease, Variant

from .policy import provenance_issues, validate_p_value
from .schema import (
    VARIANT_PATTERN,
    AssetAudit,
    AssociationValues,
    EvidenceAudit,
    EvidencePage,
    EvidenceProvenance,
    IndexedAssociation,
    Refusal,
    TraitIdentity,
)

INTERPRETATION = (
    "Source-indexed associations only. Missing rows do not establish no association. "
    "Effect scale is unrecorded in this index; do not interpret beta as odds, risk, or trait units. "
    "Unknown QC remains unknown. No geographic, causal, or pleiotropy claim is made."
)


def associations(
    session: Session,
    *,
    variant: str | None,
    phenotype_id: int | None,
    limit: int,
    offset: int,
) -> EvidencePage:
    if (variant is None) == (phenotype_id is None):
        raise ValueError("supply exactly one of variant or phenotype_id")
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("invalid pagination")
    query = select(Association)
    if variant is not None:
        if not re.fullmatch(VARIANT_PATTERN, variant):
            raise ValueError("variant requires exact GRCh37:chromosome:position:ref:alt identity")
        assembly, chrom, pos, ref, alt = variant.split(":")
        query = query.where(
            Association.variant_id.in_(
                select(Variant.id).where(
                    Variant.assembly == assembly,
                    Variant.chromosome == chrom,
                    Variant.position == int(pos),
                    Variant.reference == ref,
                    Variant.alternate == alt,
                )
            )
        )
    else:
        if phenotype_id is None or phenotype_id < 1:
            raise ValueError("phenotype_id must be positive")
        query = query.where(Association.phenotype_id == phenotype_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.options(
            joinedload(Association.variant),
            joinedload(Association.phenotype),
        )
        .order_by(Association.id)
        .offset(offset)
        .limit(limit)
    ).all()
    items, refusals = [], []
    for row in rows:
        asset = session.get(SourceAsset, row.source_asset_id)
        if asset is None or row.variant is None or row.phenotype is None:
            raise ValueError("orphan association in the source index")
        release = session.get(SourceRelease, asset.release_id)
        if release is None or release.source is None:
            raise ValueError("orphan source provenance")
        if row.phenotype.release_id != release.id:
            raise ValueError("trait and association belong to different releases")
        validate_p_value(row.encoded_p_value, row.p_value_encoding, row.neg_log10_p)
        trait = row.phenotype
        values = AssociationValues(
            association_id=row.id,
            phenotype_id=trait.id,
            trait=TraitIdentity(
                source=release.source.slug,
                release=release.version,
                trait_type=trait.trait_type,
                phenocode=trait.phenocode,
                pheno_sex=trait.pheno_sex,
                coding=trait.coding,
                modifier=trait.modifier,
                description=trait.description,
            ),
            variant=row.variant.canonical_id,
            effect_allele=row.variant.alternate,
            population=row.population_code,
            analysis_kind=row.analysis_kind,
            beta=row.beta,
            standard_error=row.standard_error,
            effect_scale="unrecorded",
            independent_review="not_recorded",
            allele_frequency=row.allele_frequency,
            neg_log10_p=row.neg_log10_p,
            encoded_p_value=row.encoded_p_value,
            p_value_encoding=row.p_value_encoding,
            low_confidence=row.low_confidence,
        )
        issues = provenance_issues(release.source.slug, asset.uri, asset.checksum)
        if issues:
            refusals.append(Refusal(record_id=row.id, reasons=issues))
            continue
        items.append(
            IndexedAssociation(
                **values.model_dump(),
                provenance=EvidenceProvenance(
                    source=release.source.slug,
                    release=release.version,
                    asset_uri=asset.uri,
                    sha256=asset.checksum,
                    source_row=row.source_row,
                    license=release.source.license_id,
                ),
            )
        )

    return EvidencePage(
        schema_version=1,
        coverage="selective_index_only",
        status="available" if items else "unavailable",
        total_indexed_matches=total,
        examined=len(rows),
        limit=limit,
        offset=offset,
        items=items,
        refusals=refusals,
        interpretation=INTERPRETATION,
    )


def audit(session: Session, *, limit: int = 200, offset: int = 0) -> EvidenceAudit:
    """Inventory registered metadata only; never infer full-input availability."""
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("invalid audit pagination")
    counts = (
        select(
            Association.source_asset_id.label("asset_id"),
            func.count().label("n"),
        )
        .group_by(Association.source_asset_id)
        .subquery()
    )
    rows = session.execute(
        select(SourceAsset, SourceRelease, DataSource, func.coalesce(counts.c.n, 0))
        .outerjoin(SourceRelease, SourceAsset.release_id == SourceRelease.id)
        .outerjoin(DataSource, SourceRelease.source_id == DataSource.id)
        .outerjoin(counts, counts.c.asset_id == SourceAsset.id)
        .order_by(SourceAsset.id)
        .offset(offset)
        .limit(limit)
    ).all()
    assets = []
    for asset, release, source, count in rows:
        if release is None or source is None:
            raise ValueError("orphan source provenance")
        assets.append(
            AssetAudit(
                asset_id=asset.id,
                release=release.version,
                indexed_associations=count,
                issues=provenance_issues(source.slug, asset.uri, asset.checksum),
            )
        )
    orphan = session.scalar(
        select(func.count())
        .select_from(Association)
        .where(
            ~Association.source_asset_id.in_(select(SourceAsset.id))
            | ~Association.phenotype_id.in_(select(Phenotype.id))
            | ~Association.variant_id.in_(select(Variant.id))
        )
    )
    return EvidenceAudit(
        schema_version=1,
        coverage="inspected_database_only",
        phenotype_count=session.scalar(select(func.count()).select_from(Phenotype)),
        association_count=session.scalar(select(func.count()).select_from(Association)),
        release_count=session.scalar(select(func.count()).select_from(SourceRelease)),
        asset_count=session.scalar(select(func.count()).select_from(SourceAsset)),
        limit=limit,
        offset=offset,
        assets=assets,
        orphan_associations=orphan,
        limitations=[
            "This audit checks registered metadata, not source contents or independent review.",
            "Full summary-statistics coverage, LD and sample overlap are not qualified by this index.",
            "Counted-allele map links and distinct-trait gene attribution are not registered.",
            "Genetic correlation, colocalization and pleiotropy protocols are not implemented or validated.",
        ],
    )

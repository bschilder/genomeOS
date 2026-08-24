from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    homepage: Mapped[str] = mapped_column(Text)
    license_id: Mapped[str] = mapped_column(String(64))


class SourceRelease(Base):
    __tablename__ = "source_releases"
    __table_args__ = (UniqueConstraint("source_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    version: Mapped[str] = mapped_column(String(128))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[DataSource] = relationship()


class SourceAsset(Base):
    __tablename__ = "source_assets"
    __table_args__ = (UniqueConstraint("release_id", "asset_type", "uri"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("source_releases.id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(64))
    uri: Mapped[str] = mapped_column(Text)
    index_uri: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(128))
    schema_json: Mapped[dict | None] = mapped_column(JSON)
    release: Mapped[SourceRelease] = relationship()


class Phenotype(Base):
    __tablename__ = "phenotypes"
    __table_args__ = (
        UniqueConstraint(
            "release_id", "trait_type", "phenocode", "pheno_sex", "coding", "modifier"
        ),
        Index("ix_phenotype_description", "description"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("source_releases.id"), index=True)
    trait_type: Mapped[str] = mapped_column(String(32))
    phenocode: Mapped[str] = mapped_column(String(128))
    pheno_sex: Mapped[str] = mapped_column(String(32), default="both_sexes")
    coding: Mapped[str] = mapped_column(String(128), default="")
    modifier: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text)
    description_more: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(255))
    in_max_independent_set: Mapped[bool | None] = mapped_column(Boolean)
    summary_stats_uri: Mapped[str | None] = mapped_column(Text)
    summary_stats_index_uri: Mapped[str | None] = mapped_column(Text)
    source_asset_id: Mapped[int | None] = mapped_column(ForeignKey("source_assets.id"))
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_payload: Mapped[dict | None] = mapped_column(JSON)
    populations: Mapped[list[PhenotypePopulation]] = relationship(
        back_populates="phenotype", cascade="all, delete-orphan"
    )

    @property
    def native_key(self) -> str:
        return ":".join(
            [self.trait_type, self.phenocode, self.pheno_sex, self.coding, self.modifier]
        )


class PhenotypePopulation(Base):
    __tablename__ = "phenotype_populations"
    __table_args__ = (UniqueConstraint("phenotype_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    phenotype_id: Mapped[int] = mapped_column(ForeignKey("phenotypes.id"), index=True)
    code: Mapped[str] = mapped_column(String(8))
    n_cases: Mapped[int | None] = mapped_column(Integer)
    n_controls: Mapped[int | None] = mapped_column(Integer)
    qc_status: Mapped[str | None] = mapped_column(String(128))
    lambda_gc: Mapped[float | None] = mapped_column(Float)
    phenotype: Mapped[Phenotype] = relationship(back_populates="populations")


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("assembly", "chromosome", "position", "reference", "alternate"),
        Index("ix_variant_region", "assembly", "chromosome", "position"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    assembly: Mapped[str] = mapped_column(String(32), default="GRCh37")
    chromosome: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(Text)
    alternate: Mapped[str] = mapped_column(Text)
    rsid: Mapped[str | None] = mapped_column(String(64), index=True)
    high_quality: Mapped[bool | None] = mapped_column(Boolean)

    @property
    def canonical_id(self) -> str:
        return f"{self.assembly}:{self.chromosome}:{self.position}:{self.reference}:{self.alternate}"


class Association(Base):
    __tablename__ = "associations"
    __table_args__ = (
        UniqueConstraint("phenotype_id", "variant_id", "population_code", "analysis_kind"),
        Index("ix_assoc_pheno_population_p", "phenotype_id", "population_code", "neg_log10_p"),
        Index("ix_assoc_variant_p", "variant_id", "neg_log10_p"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    phenotype_id: Mapped[int] = mapped_column(ForeignKey("phenotypes.id"), index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id"), index=True)
    population_code: Mapped[str] = mapped_column(String(32))
    analysis_kind: Mapped[str] = mapped_column(String(32), default="population")
    beta: Mapped[float | None] = mapped_column(Float)
    standard_error: Mapped[float | None] = mapped_column(Float)
    allele_frequency: Mapped[float | None] = mapped_column(Float)
    case_allele_frequency: Mapped[float | None] = mapped_column(Float)
    control_allele_frequency: Mapped[float | None] = mapped_column(Float)
    neg_log10_p: Mapped[float] = mapped_column(Float)
    encoded_p_value: Mapped[float] = mapped_column(Float)
    p_value_encoding: Mapped[str] = mapped_column(String(32))
    low_confidence: Mapped[bool | None] = mapped_column(Boolean)
    source_asset_id: Mapped[int] = mapped_column(ForeignKey("source_assets.id"))
    source_row: Mapped[int] = mapped_column(Integer)
    phenotype: Mapped[Phenotype] = relationship()
    variant: Mapped[Variant] = relationship()

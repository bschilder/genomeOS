from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PopulationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    n_cases: int | None
    n_controls: int | None
    qc_status: str | None
    lambda_gc: float | None


class PhenotypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    native_key: str
    trait_type: str
    phenocode: str
    pheno_sex: str
    coding: str
    modifier: str
    description: str
    description_more: str | None
    category: str | None
    in_max_independent_set: bool | None
    populations: list[PopulationOut]


class ProvenanceOut(BaseModel):
    source: str
    release: str
    asset_uri: str
    source_row: int
    genome_build: str = "GRCh37"
    license: str


class AssociationOut(BaseModel):
    id: int
    phenotype_id: int
    variant: str
    population: str
    analysis_kind: str
    beta: float | None
    standard_error: float | None
    allele_frequency: float | None
    neg_log10_p: float
    low_confidence: bool | None
    provenance: ProvenanceOut


class Page(BaseModel):
    items: list
    limit: int
    offset: int
    total: int

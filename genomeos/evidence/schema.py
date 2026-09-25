"""Strict source-index evidence contracts (Atlas design §§6, 10, 12).

Null means unrecorded, never a default scientific value. Coverage describes the
selective index only; these contracts cannot encode a causal or pleiotropy claim.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VARIANT_PATTERN = r"GRCh37:([1-9]|1[0-9]|2[0-2]|X|Y|MT):[1-9][0-9]*:[ACGT]+:[ACGT]+"
Text = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]
Positive = Annotated[int, Field(gt=0)]
Probability = Annotated[float, Field(ge=0, le=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class TraitIdentity(Contract):
    source: Literal["pan-ukb"]
    release: Text
    trait_type: Text
    phenocode: Text
    pheno_sex: Text
    coding: str
    modifier: str
    description: Text


class EvidenceProvenance(Contract):
    source: Literal["pan-ukb"]
    release: Text
    asset_uri: Text
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_row: Annotated[int, Field(ge=2)]
    license: Text


class AssociationValues(Contract):
    association_id: Positive
    phenotype_id: Positive
    trait: TraitIdentity
    variant: Annotated[str, Field(pattern=f"^{VARIANT_PATTERN}$")]
    effect_allele: Text
    population: Literal["AFR", "AMR", "CSA", "EAS", "EUR", "MID", "META", "META_HQ"]
    analysis_kind: Literal["population", "meta", "meta_hq"]
    beta: float | None
    standard_error: Annotated[float, Field(gt=0)] | None
    effect_scale: Literal["unrecorded"]
    independent_review: Literal["not_recorded"]
    allele_frequency: Probability | None
    neg_log10_p: Annotated[float, Field(ge=0)]
    encoded_p_value: float
    p_value_encoding: Literal["ln", "neg_log10", "raw"]
    low_confidence: bool | None

    @model_validator(mode="after")
    def consistent_identity(self) -> AssociationValues:
        if self.variant.split(":")[-2] == self.variant.split(":")[-1]:
            raise ValueError("reference and alternate alleles must differ")
        if self.effect_allele != self.variant.split(":")[-1]:
            raise ValueError("Pan-UKB effect allele must equal alternate")
        expected = {"META": "meta", "META_HQ": "meta_hq"}.get(self.population, "population")
        if self.analysis_kind != expected:
            raise ValueError("population and analysis kind mismatch")
        return self


class IndexedAssociation(AssociationValues):
    provenance: EvidenceProvenance

    @model_validator(mode="after")
    def consistent_release(self) -> IndexedAssociation:
        if self.trait.release != self.provenance.release:
            raise ValueError("trait and association release mismatch")
        return self


class Refusal(Contract):
    record_id: Positive
    reasons: Annotated[list[Text], Field(min_length=1)]


class EvidencePage(Contract):
    schema_version: Literal[1]
    coverage: Literal["selective_index_only"]
    status: Literal["available", "unavailable"]
    total_indexed_matches: Count
    examined: Count
    limit: Annotated[int, Field(ge=1, le=200)]
    offset: Count
    items: list[IndexedAssociation]
    refusals: list[Refusal]
    interpretation: Text

    @model_validator(mode="after")
    def reconciles(self) -> EvidencePage:
        if self.examined != len(self.items) + len(self.refusals):
            raise ValueError("every examined association must be returned or refused")
        if self.examined > self.limit or self.examined > self.total_indexed_matches:
            raise ValueError("invalid page counts")
        if (self.status == "available") != bool(self.items):
            raise ValueError("availability must match returned evidence")
        return self


class AssetAudit(Contract):
    asset_id: Positive
    release: Text
    indexed_associations: Count
    issues: list[Text]


class EvidenceAudit(Contract):
    schema_version: Literal[1]
    coverage: Literal["inspected_database_only"]
    phenotype_count: Count
    association_count: Count
    release_count: Count
    asset_count: Count
    limit: Annotated[int, Field(ge=1, le=200)]
    offset: Count
    assets: list[AssetAudit]
    orphan_associations: Count
    limitations: list[Text]

"""Versioned environmental-covariate candidate registry (design §7; issue #290).

Catalog metadata, extraction evidence, and benchmark admission are separate states. This module
performs no network or raster I/O: a later extraction adapter must bind its observed properties and
content hash to the immutable candidate identity defined here.
"""

from __future__ import annotations

import json
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

ASSET_REGISTRY_SCHEMA_VERSION = "covariate_asset_registry_v1"
DEFAULT_REGISTRY_RESOURCE = "earth_engine_assets.json"
REQUIRED_IMAGE_PROPERTIES = (
    "DATASET_VERSION",
    "MODEL_VERSION",
    "PROCESSING_SOFTWARE_VERSION",
    "UTM_ZONE",
    "system:time_start",
    "system:time_end",
)

CommercialFinding = Literal[
    "explicitly_open",
    "permission_granted",
    "no_restriction_found",
    "restricted",
    "not_checked",
]
CommercialCompatibility = Literal["compatible", "incompatible", "unresolved"]
AdmissionStatus = Literal["candidate_only", "extraction_qualified", "benchmark_admitted", "rejected"]
ExtractionStatus = Literal["not_run", "fixture_extracted", "benchmark_extracted"]


def _https(value: str, name: str) -> str:
    if not value.startswith("https://"):
        raise ValueError(f"{name} must use https")
    return value


def _nonempty_unique(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if any(not value.strip() or value != value.strip() for value in values):
        raise ValueError(f"{name} must contain trimmed nonempty strings")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    return values


class CommercialUseDeclaration(BaseModel):
    """Source-specific terms evidence, separate from scientific admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding: CommercialFinding
    restricted_fields: tuple[StrictStr, ...] = ()
    checked_at: date | None = None
    terms_url: StrictStr | None = None
    recorded_in: StrictStr | None = None

    @model_validator(mode="after")
    def evidence_matches_finding(self) -> CommercialUseDeclaration:
        _nonempty_unique(self.restricted_fields, "restricted_fields")
        if self.finding == "restricted" and not self.restricted_fields:
            raise ValueError("restricted commercial use must name restricted_fields")
        if self.finding != "restricted" and self.restricted_fields:
            raise ValueError("only restricted commercial use may name restricted_fields")
        evidence = (self.checked_at, self.terms_url, self.recorded_in)
        if self.finding == "not_checked":
            if any(value is not None for value in evidence):
                raise ValueError("not_checked commercial use cannot claim completed evidence")
        elif any(value is None for value in evidence):
            raise ValueError("a completed commercial-use check requires date, terms URL and record")
        if self.terms_url is not None:
            _https(self.terms_url, "commercial_use terms_url")
        if self.recorded_in is not None and not self.recorded_in.strip():
            raise ValueError("commercial_use recorded_in must be nonempty")
        return self


class CovariateAsset(BaseModel):
    """One exact Earth Engine embedding candidate and its current evidence state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_key: StrictStr = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    platform: Literal["google_earth_engine"]
    asset_id: StrictStr = Field(min_length=1)
    catalog_url: StrictStr
    source_checked_at: date
    publishers: tuple[StrictStr, ...] = Field(min_length=1)
    dataset_version: StrictStr = Field(min_length=1)
    model_version: StrictStr = Field(min_length=1)
    required_image_properties: tuple[StrictStr, ...]
    crs_semantics: Literal["per_image_local_utm"]
    available_years: tuple[StrictInt, ...] = Field(min_length=1)
    valid_time_start: date
    valid_time_end_exclusive: date
    temporal_resolution: Literal["annual"]
    nominal_scale_m: StrictFloat = Field(gt=0.0)
    collection_layout: Literal["tiled_images"]
    approximate_image_edge_m: StrictFloat = Field(gt=0.0)
    empirically_observed_scale_m: StrictFloat | None = Field(default=None, gt=0.0)
    vector_dimension: StrictInt = Field(gt=0)
    band_names: tuple[StrictStr, ...] = Field(min_length=1)
    band_units: Literal["dimensionless"]
    band_value_min: StrictFloat
    band_value_max: StrictFloat
    vector_semantics: Literal["joint_unit_length_vector"]
    coverage_summary: StrictStr = Field(min_length=1)
    coverage_limitations: tuple[StrictStr, ...] = Field(min_length=1)
    upstream_dependencies_status: Literal["partially_documented", "documented"]
    upstream_dependencies: tuple[StrictStr, ...] = Field(min_length=1)
    license_spdx: StrictStr = Field(min_length=1)
    license_url: StrictStr
    attribution: StrictStr = Field(min_length=1)
    commercial_use: CommercialUseDeclaration
    commercial_compatibility: CommercialCompatibility
    admission_status: AdmissionStatus
    extraction_status: ExtractionStatus
    extraction_receipt_sha256: StrictStr | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    scientific_role: StrictStr = Field(min_length=1)
    required_comparators: tuple[StrictStr, ...] = Field(min_length=1)
    interpretation_limits: tuple[StrictStr, ...] = Field(min_length=1)
    source_issue_url: StrictStr

    @field_validator("catalog_url", "license_url", "source_issue_url")
    @classmethod
    def https_urls(cls, value: str, info) -> str:
        return _https(value, info.field_name)

    @field_validator(
        "publishers",
        "required_image_properties",
        "band_names",
        "coverage_limitations",
        "upstream_dependencies",
        "required_comparators",
        "interpretation_limits",
    )
    @classmethod
    def nonempty_unique_sequences(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        return _nonempty_unique(values, info.field_name)

    @model_validator(mode="after")
    def internally_consistent(self) -> CovariateAsset:
        if not self.asset_id.strip() or self.asset_id != self.asset_id.strip():
            raise ValueError("asset_id must be a trimmed nonempty string")
        if self.valid_time_start.month != 1 or self.valid_time_start.day != 1:
            raise ValueError("valid_time_start must begin an annual interval on January 1")
        if self.valid_time_end_exclusive.month != 1 or self.valid_time_end_exclusive.day != 1:
            raise ValueError("valid_time_end_exclusive must end an annual interval on January 1")
        expected_years = tuple(
            range(self.valid_time_start.year, self.valid_time_end_exclusive.year)
        )
        if self.available_years != expected_years:
            raise ValueError(
                "available_years must equal the continuous annual interval between valid-time bounds"
            )
        expected_bands = tuple(f"A{index:02d}" for index in range(self.vector_dimension))
        if self.band_names != expected_bands:
            raise ValueError("band_names must be the complete ordered vector_dimension axes")
        if not self.band_value_min < self.band_value_max:
            raise ValueError("band_value_min must be smaller than band_value_max")
        if self.required_image_properties != REQUIRED_IMAGE_PROPERTIES:
            raise ValueError(
                "required_image_properties must retain dataset, model, processing, projection "
                "and temporal identity"
            )

        expected_compatibility: CommercialCompatibility
        if self.commercial_use.finding in {"explicitly_open", "permission_granted"}:
            expected_compatibility = "compatible"
        elif self.commercial_use.finding == "restricted":
            expected_compatibility = "incompatible"
        else:
            expected_compatibility = "unresolved"
        if self.commercial_compatibility != expected_compatibility:
            raise ValueError(
                "commercial_compatibility must agree with the recorded commercial-use evidence"
            )

        observed = self.empirically_observed_scale_m
        receipt = self.extraction_receipt_sha256
        if self.extraction_status == "not_run" and (observed is not None or receipt is not None):
            raise ValueError("not_run extraction cannot claim observed scale or a receipt")
        if self.extraction_status != "not_run" and (observed is None or receipt is None):
            raise ValueError("completed extraction requires observed scale and a receipt hash")
        if self.admission_status == "benchmark_admitted" and self.extraction_status != "benchmark_extracted":
            raise ValueError("benchmark admission requires a benchmark extraction receipt")
        if self.admission_status == "extraction_qualified" and self.extraction_status == "not_run":
            raise ValueError("extraction qualification requires retained extraction evidence")
        return self


class CovariateAssetRegistry(BaseModel):
    """Canonical collection of unique source assets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["covariate_asset_registry_v1"]
    assets: tuple[CovariateAsset, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_assets(self) -> CovariateAssetRegistry:
        keys = [asset.asset_key for asset in self.assets]
        if len(keys) != len(set(keys)):
            raise ValueError("asset_key values must be unique")
        identities = [(asset.platform, asset.asset_id) for asset in self.assets]
        if len(identities) != len(set(identities)):
            raise ValueError("platform asset identity values must be unique")
        if keys != sorted(keys):
            raise ValueError("assets must be sorted by asset_key")
        return self


def encode_registry(registry: CovariateAssetRegistry) -> bytes:
    """Return timestamp-free canonical JSON bytes for review and hashing."""
    payload = registry.model_dump(mode="json")
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def decode_registry(raw: bytes) -> CovariateAssetRegistry:
    """Decode and independently validate canonical registry bytes."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("covariate asset registry is not valid JSON") from error
    registry = CovariateAssetRegistry.model_validate(payload)
    if encode_registry(registry) != raw:
        raise ValueError("covariate asset registry JSON is not canonical")
    return registry


def default_registry_bytes() -> bytes:
    """Read the package-owned registry without filesystem assumptions."""
    return files("genomeos.covariates").joinpath(DEFAULT_REGISTRY_RESOURCE).read_bytes()


def load_default_registry() -> CovariateAssetRegistry:
    return decode_registry(default_registry_bytes())


def load_registry(path: Path) -> CovariateAssetRegistry:
    return decode_registry(path.read_bytes())


def lookup_asset(registry: CovariateAssetRegistry, asset_key: str) -> CovariateAsset:
    for asset in registry.assets:
        if asset.asset_key == asset_key:
            return asset
    raise KeyError(f"unknown covariate asset: {asset_key}")

"""Versioned Atlas serving catalog contract (design §5, §6, §10, P4).

The catalog is the immutable boundary between offline publication and the read API. Paths and
checksums live here rather than in API code, and every scientific quantity is named explicitly so
a client cannot confuse allele, carrier, phenotype, or burden measurements.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ArtifactFile(BaseModel):
    """One immutable Parquet object referenced by the catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str = Field(pattern=SHA256.pattern)
    row_count: int = Field(ge=0)
    schema_version: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def relative_artifact_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("artifact paths must be relative and remain inside the catalog root")
        return value


class VariantEntry(BaseModel):
    """Public metadata and immutable objects for one renderable entity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: str = Field(pattern=IDENTIFIER.pattern)
    label: str = Field(min_length=1)
    entity_type: Literal["variant", "phenotype"]
    measurement: Literal["allele_frequency", "carrier_frequency", "phenotype_frequency"]
    surface_eligible: bool
    assumptions: tuple[str, ...] = ()
    resolutions: tuple[int, ...] = ()
    observations: ArtifactFile | None = None
    surface: ArtifactFile | None = None
    burden: ArtifactFile | None = None

    @field_validator("resolutions")
    @classmethod
    def valid_resolutions(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if any(value < 0 or value > 15 for value in values):
            raise ValueError("H3 resolutions must be between 0 and 15")
        if tuple(sorted(set(values))) != values:
            raise ValueError("H3 resolutions must be unique and sorted")
        return values

    @model_validator(mode="after")
    def renderable_surface_is_present(self) -> VariantEntry:
        if self.surface_eligible and self.surface is None:
            raise ValueError("a surface-eligible entry must reference a surface artifact")
        if self.surface is None and self.resolutions:
            raise ValueError("resolutions cannot be declared without a surface artifact")
        if self.surface is not None and not self.resolutions:
            raise ValueError("a surface artifact must declare at least one resolution")
        return self

    def public_metadata(self) -> dict:
        """Return client-safe metadata without storage paths or object checksums."""
        metadata = self.model_dump(
            include={
                "variant_id",
                "label",
                "entity_type",
                "measurement",
                "surface_eligible",
                "assumptions",
                "resolutions",
            }
        )
        metadata.update(
            has_observations=self.observations is not None,
            has_surface=self.surface is not None,
            has_burden=self.burden is not None,
        )
        return metadata


class ArtifactManifest(BaseModel):
    """One immutable, version-pinned Atlas serving catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2"] = "2"
    artifact_version: str = Field(min_length=1)
    registry_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    created_at: datetime
    assumptions: tuple[str, ...] = ()
    variants: tuple[VariantEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_variants(self) -> ArtifactManifest:
        identifiers = [variant.variant_id for variant in self.variants]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("variant IDs must be unique within an artifact manifest")
        return self

    @classmethod
    def load(cls, path: Path) -> ArtifactManifest:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def variant(self, variant_id: str) -> VariantEntry | None:
        return next((variant for variant in self.variants if variant.variant_id == variant_id), None)

    def files(self) -> tuple[ArtifactFile, ...]:
        return tuple(
            artifact
            for variant in self.variants
            for artifact in (variant.observations, variant.surface, variant.burden)
            if artifact is not None
        )

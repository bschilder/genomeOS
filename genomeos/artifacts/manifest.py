"""Versioned manifest for one immutable Atlas artifact set (design §5, §6, P4)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VARIANT_ID = re.compile(r"^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M)-\d+-[ACGT]+-[ACGT]+$")


class VariantEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: str = Field(pattern=VARIANT_ID.pattern)
    label: str = Field(min_length=1)
    surface_eligible: bool = True


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1"
    artifact_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    created_at: datetime
    variants: tuple[VariantEntry, ...] = Field(min_length=1)
    observations_path: str
    surfaces_path: str

    @field_validator("observations_path", "surfaces_path")
    @classmethod
    def relative_artifact_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact paths must be relative and remain inside the artifact root")
        return value

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

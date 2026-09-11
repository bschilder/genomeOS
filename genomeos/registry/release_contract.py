"""Pure immutable registry identity contract (publication design §§identity, manifest)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Literal

import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from genomeos.registry.build import build_registry
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA

_RELEASE_PATTERN = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
_RELEASE_RE = re.compile(rf"^{_RELEASE_PATTERN}$")
_FULL_VERSION_PATTERN = rf"{_RELEASE_PATTERN}\+sha256\.[0-9a-f]{{64}}"
_SHA256_PATTERN = r"[0-9a-f]{64}"
_FILE_NAMES = ("populations.parquet", "population_aliases.parquet")
_SOFTWARE_KEYS = {"python", "pandas", "pyarrow", "pandera"}


class RegistryInput(BaseModel):
    """Exact source or implementation bytes included in a registry identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["source", "implementation"]
    role: StrictStr
    sha256: StrictStr = Field(pattern=rf"^{_SHA256_PATTERN}$")
    size_bytes: StrictInt = Field(ge=0)

    @field_validator("role")
    @classmethod
    def _role_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("role must be nonblank")
        return value


class RegistryFile(BaseModel):
    """Integrity and logical-content record for one fixed registry table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Literal["populations.parquet", "population_aliases.parquet"]
    sha256: StrictStr = Field(pattern=rf"^{_SHA256_PATTERN}$")
    size_bytes: StrictInt = Field(ge=0)
    row_count: StrictInt = Field(ge=0)
    logical_sha256: StrictStr = Field(pattern=rf"^{_SHA256_PATTERN}$")


class RegistryManifest(BaseModel):
    """Strict completion record for an immutable local registry publication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["registry-publication-v1"]
    release_version: StrictStr = Field(pattern=rf"^{_RELEASE_PATTERN}$")
    registry_version: StrictStr = Field(pattern=rf"^{_FULL_VERSION_PATTERN}$")
    inputs: tuple[RegistryInput, ...]
    files: tuple[RegistryFile, ...]
    software_versions: dict[StrictStr, StrictStr]

    @model_validator(mode="after")
    def _validate_complete_contract(self) -> RegistryManifest:
        _validate_inputs(self.inputs, require_sorted=True)
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(_FILE_NAMES) or set(paths) != set(_FILE_NAMES):
            raise ValueError(f"files must contain each fixed registry file once: {_FILE_NAMES}")
        if not self.registry_version.startswith(f"{self.release_version}+sha256."):
            raise ValueError("registry_version must use release_version")
        if set(self.software_versions) != _SOFTWARE_KEYS or any(
            not value.strip() for value in self.software_versions.values()
        ):
            raise ValueError(
                "software_versions must contain nonblank python, pandas, pyarrow and pandera"
            )
        return self


def identify_input(
    kind: Literal["source", "implementation"], role: str, payload: bytes
) -> RegistryInput:
    """Identify exact input bytes without consulting paths or external state."""
    return RegistryInput(
        kind=kind,
        role=role,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _validate_release_version(release_version: str) -> str:
    if not isinstance(release_version, str):
        raise TypeError("release_version must be a string")
    if _RELEASE_RE.fullmatch(release_version) is None:
        raise ValueError("release_version must be normal semver MAJOR.MINOR.PATCH")
    return release_version


def _validate_inputs(
    inputs: tuple[RegistryInput, ...], *, require_sorted: bool = False
) -> tuple[RegistryInput, ...]:
    validated = tuple(
        item if isinstance(item, RegistryInput) else RegistryInput.model_validate(item)
        for item in inputs
    )
    pairs = [(item.kind, item.role) for item in validated]
    if len(pairs) != len(set(pairs)):
        raise ValueError("duplicate registry input kind/role pair")
    if not any(item.kind == "source" for item in validated):
        raise ValueError("registry identity requires at least one source input")
    ordered = tuple(sorted(validated, key=lambda item: (item.kind, item.role)))
    if require_sorted and validated != ordered:
        raise ValueError("registry inputs must be sorted by kind and role")
    return ordered


def _validated_tables(
    populations: pd.DataFrame, aliases: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validated_populations, validated_aliases = build_registry(
        [(populations.copy(deep=True), aliases.copy(deep=True))]
    )
    population_columns = list(POPULATIONS_SCHEMA.columns)
    alias_columns = list(ALIASES_SCHEMA.columns)
    validated_populations = validated_populations.loc[:, population_columns].copy(deep=True)
    validated_aliases = validated_aliases.loc[:, alias_columns].copy(deep=True)
    for column in ("lat", "lon", "uncertainty_radius_km"):
        if not validated_populations[column].map(math.isfinite).all():
            raise ValueError(f"population {column} values must be finite")
    return validated_populations, validated_aliases


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _python_scalar(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    item = getattr(value, "item", None)
    if item is not None:
        value = item()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("logical table values must be finite")
    return value


def _logical_sha256(frame: pd.DataFrame, *, omit_registry_version: bool) -> str:
    columns = list(frame.columns)
    if omit_registry_version:
        columns.remove("registry_version")
    payload = {
        "columns": columns,
        "rows": [
            [_python_scalar(value) for value in row]
            for row in frame.loc[:, columns].itertuples(index=False, name=None)
        ],
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _identity_from_validated(
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    inputs: tuple[RegistryInput, ...],
    release_version: str,
) -> tuple[str, str, str]:
    release_version = _validate_release_version(release_version)
    inputs = _validate_inputs(inputs)
    populations_sha256 = _logical_sha256(populations, omit_registry_version=True)
    aliases_sha256 = _logical_sha256(aliases, omit_registry_version=False)
    payload = {
        "identity_schema": "registry-identity-v1",
        "release_version": release_version,
        "inputs": [record.model_dump(mode="json") for record in inputs],
        "populations_sha256": populations_sha256,
        "population_aliases_sha256": aliases_sha256,
    }
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return f"{release_version}+sha256.{digest}", populations_sha256, aliases_sha256


def registry_identity(
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    inputs: tuple[RegistryInput, ...],
    release_version: str,
) -> str:
    """Return the full immutable identity for validated logical registry content."""
    validated_populations, validated_aliases = _validated_tables(populations, aliases)
    identity, _, _ = _identity_from_validated(
        validated_populations,
        validated_aliases,
        inputs,
        release_version,
    )
    return identity

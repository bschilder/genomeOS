"""Bounded DuckDB reads over a concrete local artifact directory (design §10, P4)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import duckdb

from genomeos.artifacts.manifest import ArtifactManifest
from genomeos.observability import log_event

LOGGER = logging.getLogger(__name__)
MAX_ROWS = 5_000
OBSERVATION_COLUMNS = (
    "variant_id",
    "population_id",
    "lat",
    "lon",
    "radius_km",
    "ac",
    "an",
    "sampling_design",
    "source",
)
SURFACE_COLUMNS = (
    "variant_id",
    "h3_resolution",
    "h3_index",
    "lat",
    "lon",
    "post_mean",
    "post_sd",
    "q025",
    "q975",
    "support",
)


class ArtifactUnavailable(RuntimeError):
    pass


class ArtifactCatalog:
    """Read one immutable artifact set rooted at a local directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._manifest: ArtifactManifest | None = None

    def load_manifest(self) -> ArtifactManifest:
        if self._manifest is not None:
            return self._manifest
        started = time.perf_counter()
        path = self.root / "manifest.json"
        try:
            manifest = ArtifactManifest.load(path)
            for relative in (manifest.observations_path, manifest.surfaces_path):
                artifact = (self.root / relative).resolve()
                if not artifact.is_relative_to(self.root) or not artifact.is_file():
                    raise ArtifactUnavailable(f"artifact file is unavailable: {relative}")
        except (OSError, ValueError) as error:
            raise ArtifactUnavailable(f"manifest is unavailable or invalid: {path}") from error
        log_event(
            LOGGER,
            "manifest_loaded",
            duration_ms=_milliseconds(started),
            artifact_version=manifest.artifact_version,
            data_version=manifest.data_version,
            model_version=manifest.model_version,
            variant_count=len(manifest.variants),
        )
        self._manifest = manifest
        return manifest

    def check_ready(self) -> ArtifactManifest:
        manifest = self.load_manifest()
        self._query(manifest.observations_path, ("variant_id",), limit=1, emit_log=False)
        self._query(manifest.surfaces_path, ("variant_id",), limit=1, emit_log=False)
        return manifest

    def list_variants(self) -> tuple[ArtifactManifest, tuple[dict[str, Any], ...]]:
        manifest = self.load_manifest()
        return manifest, tuple(variant.model_dump() for variant in manifest.variants)

    def observations(
        self,
        variant_id: str,
        *,
        limit: int = 1_000,
        bounds: tuple[float, float, float, float] | None = None,
    ) -> tuple[ArtifactManifest, list[dict[str, Any]]]:
        manifest = self._eligible_manifest(variant_id, surface_required=False)
        rows = self._query(
            manifest.observations_path,
            OBSERVATION_COLUMNS,
            variant_id=variant_id,
            bounds=bounds,
            limit=limit,
            data_version=manifest.data_version,
            model_version=manifest.model_version,
        )
        return manifest, rows

    def surface(
        self,
        variant_id: str,
        resolution: int,
        *,
        limit: int = 5_000,
        bounds: tuple[float, float, float, float] | None = None,
    ) -> tuple[ArtifactManifest, list[dict[str, Any]]]:
        manifest = self._eligible_manifest(variant_id, surface_required=True)
        rows = self._query(
            manifest.surfaces_path,
            SURFACE_COLUMNS,
            variant_id=variant_id,
            resolution=resolution,
            bounds=bounds,
            limit=limit,
            data_version=manifest.data_version,
            model_version=manifest.model_version,
        )
        return manifest, rows

    def _eligible_manifest(
        self, variant_id: str, *, surface_required: bool
    ) -> ArtifactManifest:
        manifest = self.load_manifest()
        variant = manifest.variant(variant_id)
        if variant is None:
            raise KeyError(variant_id)
        if surface_required and not variant.surface_eligible:
            raise PermissionError(f"surface rendering is not eligible for {variant_id}")
        return manifest

    def _query(
        self,
        relative_path: str,
        columns: tuple[str, ...],
        *,
        variant_id: str | None = None,
        resolution: int | None = None,
        bounds: tuple[float, float, float, float] | None = None,
        limit: int,
        data_version: str | None = None,
        model_version: str | None = None,
        emit_log: bool = True,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= MAX_ROWS:
            raise ValueError(f"limit must be between 1 and {MAX_ROWS}")
        path = str((self.root / relative_path).resolve())
        clauses: list[str] = []
        parameters: list[Any] = [path]
        if variant_id is not None:
            clauses.append("variant_id = ?")
            parameters.append(variant_id)
        if resolution is not None:
            clauses.append("h3_resolution = ?")
            parameters.append(resolution)
        if bounds is not None:
            west, south, east, north = bounds
            clauses.extend(("lon BETWEEN ? AND ?", "lat BETWEEN ? AND ?"))
            parameters.extend((west, east, south, north))

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        selected = ", ".join(columns)
        sql = f"SELECT {selected} FROM read_parquet(?){where} LIMIT ?"  # noqa: S608
        parameters.append(limit)
        started = time.perf_counter()
        try:
            with duckdb.connect() as connection:
                cursor = connection.execute(sql, parameters)
                names = [description[0] for description in cursor.description]
                rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        except duckdb.Error as error:
            if emit_log:
                log_event(
                    LOGGER,
                    "artifact_query_failed",
                    duration_ms=_milliseconds(started),
                    artifact_kind=Path(relative_path).stem,
                    variant_id=variant_id,
                    data_version=data_version,
                    model_version=model_version,
                    error_type=type(error).__name__,
                )
            raise ArtifactUnavailable(f"artifact query failed for {relative_path}") from error
        if emit_log:
            log_event(
                LOGGER,
                "artifact_query_completed",
                duration_ms=_milliseconds(started),
                artifact_kind=Path(relative_path).stem,
                variant_id=variant_id,
                h3_resolution=resolution,
                data_version=data_version,
                model_version=model_version,
                row_count=len(rows),
            )
        return rows


def _milliseconds(started: float) -> float:
    return round((time.perf_counter() - started) * 1_000, 3)

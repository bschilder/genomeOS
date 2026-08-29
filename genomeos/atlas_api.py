"""Read-only Atlas artifact API and diagnostic preview (design §10, P4)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text

from .artifacts import ArtifactCatalog, ArtifactManifest, ArtifactUnavailable
from .config import settings
from .db import engine
from .observability import log_event

router = APIRouter()
LOGGER = logging.getLogger(__name__)
PREVIEW_PATH = Path(__file__).with_name("static") / "preview.html"
BASEMAP_PATH = Path(__file__).resolve().parents[1] / "reference" / "ne_110m_countries.geojson"
artifact_catalog = ArtifactCatalog(settings.atlas_artifact_root)


@router.get("/ready")
async def ready():
    try:
        _check_database()
        manifest = artifact_catalog.check_ready()
    except (ArtifactUnavailable, OSError) as error:
        log_event(LOGGER, "readiness_failed", component="artifact_catalog")
        raise HTTPException(503, "artifact catalog is unavailable") from error
    except Exception as error:
        log_event(LOGGER, "readiness_failed", component="database")
        raise HTTPException(503, "database is unavailable") from error
    return {
        "status": "ready",
        "artifact_version": manifest.artifact_version,
        "registry_version": manifest.registry_version,
        "data_version": manifest.data_version,
        "model_version": manifest.model_version,
    }


@router.get("/preview", include_in_schema=False)
async def preview():
    return FileResponse(PREVIEW_PATH)


@router.get("/preview/basemap", include_in_schema=False)
async def preview_basemap():
    return FileResponse(BASEMAP_PATH, media_type="application/geo+json")


@router.get("/v1/atlas/variants")
async def atlas_variants():
    try:
        manifest, variants = artifact_catalog.list_variants()
    except ArtifactUnavailable as error:
        raise HTTPException(503, "artifact catalog is unavailable") from error
    return _artifact_response(manifest, list(variants))


@router.get("/v1/atlas/observations")
async def atlas_observations(
    variant_id: str,
    limit: int = Query(1_000, ge=1, le=5_000),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
):
    bounds = _bounds(west, south, east, north)
    try:
        manifest, rows = artifact_catalog.observations(variant_id, limit=limit, bounds=bounds)
    except KeyError as error:
        raise HTTPException(404, "variant is not present in this artifact set") from error
    except ArtifactUnavailable as error:
        raise HTTPException(503, "observation artifact is unavailable") from error
    return _artifact_response(manifest, rows)


@router.get("/v1/atlas/surface")
async def atlas_surface(
    variant_id: str,
    resolution: int = Query(4, ge=0, le=15),
    limit: int = Query(5_000, ge=1, le=5_000),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
):
    bounds = _bounds(west, south, east, north)
    try:
        manifest, rows = artifact_catalog.surface(
            variant_id, resolution, limit=limit, bounds=bounds
        )
    except KeyError as error:
        raise HTTPException(404, "variant or resolution is not present in this artifact set") from error
    except PermissionError as error:
        raise HTTPException(403, "variant is not eligible for surface rendering") from error
    except ArtifactUnavailable as error:
        raise HTTPException(503, "surface artifact is unavailable") from error
    return _artifact_response(manifest, rows)


def _bounds(
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
) -> tuple[float, float, float, float] | None:
    values = (west, south, east, north)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise HTTPException(422, "west, south, east, and north must be supplied together")
    assert all(value is not None for value in values)
    bounds = (float(west), float(south), float(east), float(north))
    if bounds[0] > bounds[2] or bounds[1] > bounds[3]:
        raise HTTPException(422, "viewport bounds must satisfy west <= east and south <= north")
    return bounds


def _artifact_response(manifest: ArtifactManifest, rows: list[dict]):
    return {
        "artifact_version": manifest.artifact_version,
        "registry_version": manifest.registry_version,
        "data_version": manifest.data_version,
        "model_version": manifest.model_version,
        "count": len(rows),
        "items": rows,
    }


def _check_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

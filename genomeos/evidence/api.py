"""Thin read-only trait-evidence routes (Atlas design §10)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from genomeos.db import get_session

from .query import associations, audit
from .schema import VARIANT_PATTERN, EvidenceAudit, EvidencePage

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/evidence", include_in_schema=False)
def browser():
    return FileResponse(Path(__file__).parents[1] / "static" / "evidence.html")


@router.get("/v1/evidence/audit", response_model=EvidenceAudit)
def evidence_audit(
    limit: int = Query(200, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    try:
        return audit(session, limit=limit, offset=offset)
    except (ValueError, SQLAlchemyError) as error:
        LOGGER.warning("Evidence inventory unavailable: %s", type(error).__name__)
        raise HTTPException(503, "evidence inventory unavailable or invalid") from error


@router.get("/v1/evidence/associations", response_model=EvidencePage)
def evidence_associations(
    variant: str | None = None,
    phenotype_id: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    # Request validation is separate from stored-data corruption.
    if (variant is None) == (phenotype_id is None):
        raise HTTPException(422, "supply exactly one of variant or phenotype_id")
    if variant is not None and not re.fullmatch(VARIANT_PATTERN, variant):
        raise HTTPException(422, "variant requires exact GRCh37:chromosome:position:ref:alt identity")
    try:
        return associations(session, variant=variant, phenotype_id=phenotype_id, limit=limit, offset=offset)
    except (ValueError, SQLAlchemyError) as error:
        LOGGER.warning("Evidence query unavailable: %s", type(error).__name__)
        raise HTTPException(
            503, "source evidence is unavailable or invalid; no substitute was loaded"
        ) from error

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import HTTPException

from genomeos.atlas_api import (
    atlas_observations,
    atlas_surface,
    atlas_variants,
    preview,
    ready,
)
from genomeos.observability import RequestLoggingMiddleware

VARIANT = "chr11-5227002-T-A"


class Records(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def run(coroutine):
    return asyncio.run(coroutine)


def test_ready_atlas_queries_and_preview_contracts():
    ready_response = run(ready())
    variants = run(atlas_variants())
    observations = run(atlas_observations(VARIANT, 1_000, None, None, None, None))
    surface = run(atlas_surface(VARIANT, 4, 5_000, None, None, None, None))
    preview_response = run(preview())

    assert ready_response["status"] == "ready"
    assert variants["items"][0]["variant_id"] == VARIANT
    assert observations["count"] == 3
    assert surface["count"] == 6
    assert surface["data_version"] == ready_response["data_version"]
    assert {item["support"] for item in surface["items"]} >= {
        "prior_dominated",
        "unknown",
    }
    assert str(preview_response.path).endswith("preview.html")


def test_request_logging_middleware_emits_one_safe_completion_event():
    sent: list[dict] = []

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/atlas/surface",
        "headers": [
            (b"x-request-id", b"request-42"),
            (b"authorization", b"Bearer must-not-be-logged"),
            (b"cookie", b"session=must-not-be-logged"),
        ],
    }
    handler = Records()
    root = logging.getLogger()
    previous_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    run(RequestLoggingMiddleware(inner)(scope, receive, send))
    root.removeHandler(handler)
    root.setLevel(previous_level)

    completed = [
        record
        for record in handler.records
        if getattr(record, "event", None) == "request_completed"
    ]
    response_headers = dict(sent[0]["headers"])
    assert response_headers[b"x-request-id"] == b"request-42"
    assert len(completed) == 1
    assert completed[0].event_fields["path"] == "/v1/atlas/surface"
    rendered = " ".join(record.getMessage() for record in handler.records)
    assert "must-not-be-logged" not in rendered


def test_atlas_queries_fail_closed():
    with pytest.raises(HTTPException) as missing:
        run(atlas_surface("chr1-1-A-C", 4, 5_000, None, None, None, None))
    with pytest.raises(HTTPException) as partial_bounds:
        run(atlas_observations(VARIANT, 1_000, -10, None, None, None))
    assert missing.value.status_code == 404
    assert partial_bounds.value.status_code == 422

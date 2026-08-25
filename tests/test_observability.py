from __future__ import annotations

import json
import logging

from genomeos.observability import JsonFormatter, reset_request_id, set_request_id


def test_json_formatter_has_stable_fields_and_request_context():
    record = logging.LogRecord(
        "genomeos.test",
        logging.INFO,
        __file__,
        1,
        "query complete",
        (),
        None,
    )
    record.event = "artifact_query_completed"
    record.event_fields = {"duration_ms": 1.25, "row_count": 3}
    token = set_request_id("request-7")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["event"] == "artifact_query_completed"
    assert payload["request_id"] == "request-7"
    assert payload["duration_ms"] == 1.25
    assert payload["row_count"] == 3

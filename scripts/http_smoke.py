#!/usr/bin/env python3
"""Exercise the running API through HTTP; used by local and container smoke checks."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request

VARIANT_ID = "chr11-5227002-T-A"


def get(base_url: str, path: str, *, request_id: str | None = None):
    request = urllib.request.Request(f"{base_url}{path}")
    if request_id:
        request.add_header("X-Request-ID", request_id)
    with urllib.request.urlopen(request, timeout=3) as response:
        body = response.read()
        return response, body


def wait_ready(base_url: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _, body = get(base_url, "/ready")
            return json.loads(body)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(f"service did not become ready within {timeout}s") from last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    ready = wait_ready(base_url, args.timeout)
    response, variants_body = get(base_url, "/v1/atlas/variants", request_id="http-smoke-1")
    _, basemap_body = get(base_url, "/preview/basemap")
    variants = json.loads(variants_body)
    basemap = json.loads(basemap_body)
    encoded = urllib.parse.quote(VARIANT_ID)
    _, observations_body = get(base_url, f"/v1/atlas/observations?variant_id={encoded}")
    _, surface_body = get(
        base_url, f"/v1/atlas/surface?variant_id={encoded}&resolution=4"
    )
    _, preview = get(base_url, "/preview")
    observations = json.loads(observations_body)
    surface = json.loads(surface_body)

    assert response.headers["X-Request-ID"] == "http-smoke-1"
    assert basemap["type"] == "FeatureCollection"
    assert basemap["features"]
    assert ready["data_version"] == variants["data_version"] == surface["data_version"]
    assert variants["items"][0]["variant_id"] == VARIANT_ID
    assert observations["count"] == 3
    assert surface["count"] == 6
    assert {item["support"] for item in surface["items"]} >= {
        "prior_dominated",
        "unknown",
    }
    assert b"Interactive diagnostic of immutable published surfaces" in preview
    assert b"not a product map" in preview
    print("HTTP smoke passed: ready, variants, observations, surface, preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

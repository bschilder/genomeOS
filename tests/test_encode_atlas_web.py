"""Web-object encoder for the static Atlas client (Atlas design §11; fast-load spec §B.5)."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from genomeos.publication import surface_codec as codec
from scripts import encode_atlas_web, export_atlas_web

#: Ascending resolution-3 cells around Madrid.
CELLS = ("833901fffffffff", "833908fffffffff", "83390cfffffffff")
ROWS = (
    ("observed", 0.2, 0.01, 0.15, 0.25, 0.1, 0.0),
    ("interpolated", 0.05, 0.03, 0.01, 0.11, 0.5, 120.5),
    ("unknown", 0.11, 0.08, 0.001, 0.4, 0.99, 1500.25),
)


def _identity(artifact_id: str) -> dict[str, Any]:
    return {
        "artifact_format": 1,
        "data_version": "map-test",
        "entity_type": "variant",
        "hf_dataset": "bschilder/genomeos-data",
        "hf_revision": "fc17bc1c1d96a0d0766746dcf26277ccdc669717",
        "id": artifact_id,
        "label": f"{artifact_id} fixture",
        "measurement": "allele_frequency",
        "metric_domains": {"post_mean": [0.05, 0.2], "post_sd": [0.01, 0.03]},
        "model_version": "v1",
        "registry_version": "map-test-registry",
        "resolution": 3,
        "variant_id": f"fixture:{artifact_id}",
    }


def _cells(order: tuple[str, ...] = CELLS) -> list[dict[str, Any]]:
    fields = (
        "support",
        "post_mean",
        "post_sd",
        "q025",
        "q975",
        "posterior_contraction",
        "dist_nearest_obs_km",
    )
    return [
        {"h3_index": cell, **dict(zip(fields, row, strict=True))}
        for cell, row in zip(order, ROWS, strict=True)
    ]


def _write_export(
    root: Path, surfaces: dict[str, list[dict[str, Any]]], *, observations: bool = True
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for artifact_id, cells in surfaces.items():
        identity = _identity(artifact_id)
        surface = encode_atlas_web.canonical_bytes(
            {"artifact": identity, "cells": cells, "schema_version": 1}
        )
        (root / f"{artifact_id}.surface.json").write_bytes(surface)
        ref = {
            **identity,
            "n_cells": len(cells),
            "observations_available": observations,
            "observations_sha256": None,
            "observations_url": None,
            "support_counts": dict(Counter(cell["support"] for cell in cells)),
            "surface_sha256": hashlib.sha256(surface).hexdigest(),
            "surface_url": f"{artifact_id}.surface.json",
        }
        if observations:
            payload = encode_atlas_web.canonical_bytes(
                {"artifact": identity, "observations": [], "schema_version": 1}
            )
            (root / f"{artifact_id}.observations.json").write_bytes(payload)
            ref["observations_sha256"] = hashlib.sha256(payload).hexdigest()
            ref["observations_url"] = f"{artifact_id}.observations.json"
        artifacts.append(ref)
    (root / "catalog.json").write_bytes(
        encode_atlas_web.canonical_bytes(
            {"artifact_version": "fixture", "artifacts": artifacts, "schema_version": 1}
        )
    )
    return root


def test_cli_writes_content_addressed_objects_and_catalog_fields(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "web", {"alpha": _cells(), "beta": _cells()})
    assert encode_atlas_web.main(["--in", str(export)]) == 0
    catalog = json.loads((export / "catalog.json").read_text())

    ((grid_sha, grid),) = catalog["grids"].items()
    assert grid_sha == codec.grid_sha256([int(cell, 16) for cell in CELLS])
    assert grid["url"] == f"grids/h3-r3.{grid['sha256'][:16]}.gosa"
    assert (grid["n_cells"], grid["resolution"]) == (3, 3)
    for ref in catalog["artifacts"]:
        web = ref["web"]
        assert web["grid_sha256"] == grid_sha
        assert (
            web["render"]["url"]
            == f"surfaces/{ref['id']}/v1/map-test/render.{web['render']['sha256'][:16]}.gosa"
        )
        assert web["detail"]["url"].startswith(f"surfaces/{ref['id']}/v1/map-test/detail.")
        for tier in ("render", "detail"):
            data = (export / web[tier]["url"]).read_bytes()
            assert len(data) == web[tier]["bytes"]
            assert hashlib.sha256(data).hexdigest() == web[tier]["sha256"]
        assert ref["observations_bytes"] == (export / ref["observations_url"]).stat().st_size
    detail = codec.decode(
        (export / catalog["artifacts"][0]["web"]["detail"]["url"]).read_bytes(), tier="detail"
    )
    assert detail.columns["dist_nearest_obs_km"] == (0.0, 120.5, 1500.25)


def test_encoding_is_byte_deterministic_and_idempotent_in_place(tmp_path: Path) -> None:
    first = _write_export(tmp_path / "first", {"alpha": _cells()})
    second = _write_export(tmp_path / "second", {"alpha": _cells()})
    encode_atlas_web.encode_export(first, first)
    encode_atlas_web.encode_export(second, second)
    encoded = (first / "catalog.json").read_bytes()
    assert encoded == (second / "catalog.json").read_bytes()
    encode_atlas_web.encode_export(first, first)  # re-encoding an encoded tree changes nothing
    assert (first / "catalog.json").read_bytes() == encoded
    files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*.gosa"))
    assert len(files) == 3


def test_canonical_bytes_matches_the_exporter_serialisation() -> None:
    """The encoder repeats the exporter's serialisation to stay pandas-free; drift fails here."""
    value = {
        "z": [1, 2.5, -0.0, 1e-300, None, True],
        "artifact": {"label": "Ñandú — Ålesund 東京  ", "nested": {"b": [], "a": {"é": [{}]}}},
    }
    expected = export_atlas_web._canonical_bytes(value)
    assert encode_atlas_web.canonical_bytes(value) == expected
    assert "東京".encode() in expected  # written as UTF-8, not \u escapes


def test_observations_bytes_is_null_when_observations_are_unavailable(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "web", {"alpha": _cells()}, observations=False)
    catalog = encode_atlas_web.encode_export(export, export)
    assert catalog["artifacts"][0]["observations_bytes"] is None


def test_out_directory_receives_objects_and_catalog_without_touching_the_input(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "web", {"alpha": _cells()})
    before = (export / "catalog.json").read_bytes()
    encode_atlas_web.main(["--in", str(export), "--out", str(tmp_path / "staged")])
    assert (export / "catalog.json").read_bytes() == before
    assert json.loads((tmp_path / "staged" / "catalog.json").read_text())["grids"]


def test_refuses_a_surface_whose_h3_order_differs_from_the_shared_grid(tmp_path: Path) -> None:
    swapped = (CELLS[0], CELLS[2], CELLS[1])
    export = _write_export(tmp_path / "web", {"alpha": _cells(), "beta": _cells(swapped)})
    before = (export / "catalog.json").read_bytes()
    with pytest.raises(ValueError, match="beta: h3_index sequence differs from the shared grid at row 1"):
        encode_atlas_web.encode_export(export, export)
    assert (export / "catalog.json").read_bytes() == before


def test_refuses_a_grid_that_is_not_strictly_increasing(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "web", {"alpha": _cells(tuple(reversed(CELLS)))})
    with pytest.raises(codec.GosaError, match="grid not strictly increasing"):
        encode_atlas_web.encode_export(export, export)


def test_refuses_json_whose_bytes_differ_from_the_catalog_digest(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "web", {"alpha": _cells()})
    path = export / "alpha.surface.json"
    path.write_bytes(path.read_bytes().replace(b"0.2,", b"0.3,", 1))
    with pytest.raises(ValueError, match="sha256 does not match the catalog"):
        encode_atlas_web.encode_export(export, export)


def test_refuses_to_replace_a_different_object_at_a_content_addressed_key(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "web", {"alpha": _cells()})
    catalog = encode_atlas_web.encode_export(export, export)
    (export / catalog["artifacts"][0]["web"]["render"]["url"]).write_bytes(b"GOSA tampered")
    with pytest.raises(ValueError, match="different object already exists"):
        encode_atlas_web.encode_export(export, export)


def test_round_trip_verification_failure_leaves_the_catalog_unwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = _write_export(tmp_path / "web", {"alpha": _cells()})
    before = (export / "catalog.json").read_bytes()
    real = codec.encode_detail

    def drifted(**fields: Any) -> bytes:
        # One ulp off in float64: the same float32, so only the bit-for-bit JSON check can see it.
        fields["q975"] = [math.nextafter(fields["q975"][0], 1.0), *fields["q975"][1:]]
        return real(**fields)

    monkeypatch.setattr(encode_atlas_web.codec, "encode_detail", drifted)
    with pytest.raises(ValueError, match="detail q975 is not bit-identical to the JSON"):
        encode_atlas_web.encode_export(export, export)
    assert (export / "catalog.json").read_bytes() == before


def test_refuses_keys_the_browser_contract_would_refuse() -> None:
    for key in ("/data/atlas/x.gosa", "https://x/y.gosa", "a/../b.gosa", "Surfaces/x.gosa", ""):
        with pytest.raises(ValueError, match="relative data key"):
            encode_atlas_web.data_key(key)
    assert encode_atlas_web.data_key("surfaces/hbs-rs334/v3/map-2026-08/render.0123456789abcdef.gosa")

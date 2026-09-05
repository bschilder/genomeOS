from __future__ import annotations

import json
from pathlib import Path

import h3
import pandas as pd
import pytest

from genomeos.artifacts import ArtifactCatalog
from genomeos.artifacts.build import build_catalog

VARIANT = "chr11-5227002-T-A"


def _source(root: Path, *, declared_rows: int = 1) -> Path:
    directory = root / "published" / "variant__v1__data-v1"
    directory.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {
                "h3_index": h3.latlng_to_cell(5.56, -0.20, 3),
                "variant_id": VARIANT,
                "post_mean": 0.1,
                "post_sd": 0.01,
                "q025": 0.08,
                "q975": 0.12,
                "support": "observed",
                "model_version": "v1",
                "data_version": "data-v1",
            }
        ]
    )
    frame.to_parquet(directory / "cells.parquet", index=False)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_format": 1,
                "variant_id": VARIANT,
                "model_version": "v1",
                "data_version": "data-v1",
                "resolution": 3,
                "n_cells": declared_rows,
            }
        ),
        encoding="utf-8",
    )
    return directory.parent


def _metadata(root: Path, variant_id: str = VARIANT) -> Path:
    path = root / "metadata.json"
    path.write_text(
        json.dumps(
            {
                "artifact_version": "catalog-v1",
                "registry_version": "registry-v1",
                "created_at": "2026-08-29T00:00:00Z",
                "variants": {
                    variant_id: {
                        "label": "HbS",
                        "entity_type": "variant",
                        "measurement": "allele_frequency",
                        "surface_eligible": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_builds_a_catalog_the_api_can_query(tmp_path):
    out = tmp_path / "catalog"
    build_catalog(_source(tmp_path), _metadata(tmp_path), out)

    catalog = ArtifactCatalog(out)
    manifest = catalog.check_ready()
    _, rows = catalog.surface(VARIANT, 3)

    assert manifest.registry_version == "registry-v1"
    assert rows[0]["variant_id"] == VARIANT
    assert rows[0]["h3_resolution"] == 3
    assert rows[0]["lat"] == pytest.approx(5.56, abs=1.0)
    assert manifest.variant(VARIANT).observations is None


def test_refuses_implicit_metadata_bad_counts_and_overwrite(tmp_path):
    source = _source(tmp_path, declared_rows=2)
    with pytest.raises(ValueError, match="declares 2 cells"):
        build_catalog(source, _metadata(tmp_path), tmp_path / "bad-count")

    source = _source(tmp_path / "second")
    with pytest.raises(ValueError, match="metadata is missing"):
        build_catalog(source, _metadata(tmp_path / "second", "chr1-1-A-C"), tmp_path / "missing")

    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(FileExistsError, match="refusing to replace"):
        build_catalog(source, _metadata(tmp_path / "second"), out)

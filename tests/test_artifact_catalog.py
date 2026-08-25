from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from genomeos.artifacts import ArtifactCatalog, ArtifactUnavailable

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "artifacts"
VARIANT = "chr11-5227002-T-A"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_demo_catalog_is_versioned_bounded_and_read_only():
    catalog = ArtifactCatalog(DEMO)
    before = {path.name: digest(path) for path in DEMO.iterdir()}

    manifest = catalog.check_ready()
    observed_manifest, observations = catalog.observations(VARIANT)
    surface_manifest, cells = catalog.surface(VARIANT, 4)

    assert manifest == observed_manifest == surface_manifest
    assert manifest.data_version == "demo-2026-08-24"
    assert len(observations) == 3
    assert {row["support"] for row in cells} == {
        "observed",
        "interpolated",
        "prior_dominated",
        "unknown",
    }
    assert before == {path.name: digest(path) for path in DEMO.iterdir()}


def test_catalog_bounds_queries_without_loading_unrequested_rows():
    _, rows = ArtifactCatalog(DEMO).surface(VARIANT, 4, bounds=(-10, 0, 20, 20))
    assert rows
    assert all(-10 <= row["lon"] <= 20 and 0 <= row["lat"] <= 20 for row in rows)


def test_catalog_fails_closed_for_unknown_or_ineligible_paths(tmp_path):
    with pytest.raises(ArtifactUnavailable):
        ArtifactCatalog(tmp_path).check_ready()
    with pytest.raises(KeyError):
        ArtifactCatalog(DEMO).surface("chr1-1-A-C", 4)

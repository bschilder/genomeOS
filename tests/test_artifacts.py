"""Immutable per-cell surface artifacts (design §5, §6).

Two properties carry the design's weight and are tested directly: an artifact **cannot be
silently overwritten**, and the **support mask travels with the numbers**. Everything else about
the format is convenience; those two are what make a published surface citable and honest.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from genomeos.surfaces.artifacts import (
    ARTIFACT_COLUMNS,
    ARTIFACT_FORMAT,
    ArtifactManifest,
    publish,
    read,
)


def _frame(n: int = 5, variant_id: str = "chr11-5227002-T-A") -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "h3_index": [f"83{i:04x}fffffffff" for i in range(n)],
            "variant_id": variant_id,
            "post_median": rng.uniform(0, 0.2, n),
            "post_mean": rng.uniform(0, 0.2, n),
            "post_sd": rng.uniform(0, 0.05, n),
            "q025": 0.0,
            "q975": 0.3,
            "q25": 0.01,
            "q75": 0.1,
            "support": ["observed", "interpolated", "unknown", "prior_dominated", "observed"][:n],
            "posterior_contraction": rng.uniform(0, 1, n),
            "dist_nearest_obs_km": rng.uniform(0, 3000, n),
            "model_version": "v1",
            "data_version": "map-2026-08",
        },
        columns=list(ARTIFACT_COLUMNS),
    )


def _manifest(variant_id: str = "chr11-5227002-T-A", model_version: str = "v1") -> ArtifactManifest:
    return ArtifactManifest(
        variant_id=variant_id,
        model_version=model_version,
        data_version="map-2026-08",
        resolution=3,
        n_cells=5,
        correlation_range_km=680.0,
        prior_frequency_sd=0.119,
        likelihood="beta_binomial",
        lengthscale_sigma=0.7,
        n_observations=1071,
        support_counts={"observed": 2},
    )


def test_publishing_twice_is_refused_because_artifacts_are_immutable(tmp_path):
    """§5: a model change publishes new artifacts and never mutates a map someone has cited.

    A silent overwrite is exactly the failure that guarantee exists to prevent, so the second
    write must raise rather than succeed quietly.
    """
    publish(_frame(), tmp_path, manifest=_manifest())
    with pytest.raises(FileExistsError, match="immutable"):
        publish(_frame(), tmp_path, manifest=_manifest())


def test_a_new_model_version_publishes_alongside_rather_than_replacing(tmp_path):
    """The key is `(variant_id, model_version, data_version)`, so a refit coexists with what it
    supersedes and an older citation keeps resolving."""
    first = publish(_frame(), tmp_path, manifest=_manifest(model_version="v1"))
    second = publish(_frame(), tmp_path, manifest=_manifest(model_version="v2"))
    assert first != second
    assert first.exists() and second.exists()


def test_the_support_mask_travels_with_the_numbers(tmp_path):
    """§4's defence against a persuasive-but-unfounded cline is that a consumer can tell measured
    from inferred. An artifact of values without `support` strips the column that makes it honest.
    """
    directory = publish(_frame(), tmp_path, manifest=_manifest())
    frame, _ = read(directory)
    assert "support" in frame.columns
    assert "posterior_contraction" in frame.columns
    # The distance is carried too, so a consumer can apply a stricter threshold without refitting.
    assert "dist_nearest_obs_km" in frame.columns
    assert frame["support"].notna().all()


def test_the_manifest_records_what_would_otherwise_be_unrecoverable(tmp_path):
    """A number is not citable without the assumptions behind it. The likelihood and the
    lengthscale prior in particular are per-variant choices (#116) that cannot be recovered from
    the cell values alone."""
    directory = publish(_frame(), tmp_path, manifest=_manifest())
    _, manifest = read(directory)
    assert manifest["likelihood"] == "beta_binomial"
    assert manifest["lengthscale_sigma"] == 0.7
    assert manifest["correlation_range_km"] == 680.0
    assert manifest["n_observations"] == 1071
    assert manifest["artifact_format"] == ARTIFACT_FORMAT


def test_an_artifact_from_an_unknown_format_is_refused_not_misread(tmp_path):
    directory = publish(_frame(), tmp_path, manifest=_manifest())
    path = directory / "manifest.json"
    payload = json.loads(path.read_text())
    payload["artifact_format"] = 999
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="artifact_format"):
        read(directory)


def test_a_phenotype_composite_round_trips(tmp_path):
    """`phenotype:g6pd-deficiency` contains a colon, which is not a safe path component
    everywhere; the directory name must be sanitised without losing the id in the data."""
    variant = "phenotype:g6pd-deficiency"
    directory = publish(
        _frame(variant_id=variant), tmp_path, manifest=_manifest(variant_id=variant)
    )
    assert ":" not in directory.name
    frame, manifest = read(directory)
    assert set(frame["variant_id"]) == {variant}
    assert manifest["variant_id"] == variant

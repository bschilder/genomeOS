"""Leakage-resistant benchmark split manifests (design §§5, 7, 8)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from math import pi

import pandas as pd
import pytest

from genomeos.validation.splits import (
    EARTH_RADIUS_KM,
    BenchmarkSplit,
    build_buffered_splits,
    validate_split,
)


def _observations(*rows: tuple[object, object, object, object, object]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["source_record_id", "cohort_id", "lat", "lon", "radius_km"],
    )


def _assignments(*rows: tuple[object, object]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["source_record_id", "block_id"])


def _by_block(splits: tuple[BenchmarkSplit, ...], block_id: str) -> BenchmarkSplit:
    return next(split for split in splits if split.block_id == block_id)


def test_transitive_edges_and_shared_cohorts_do_not_leak_into_training():
    """Removing either graph closure or cohort edges would leak a related survey."""
    observations = _observations(
        ("test", "shared", 0.0, 0.0, 1.0),
        ("direct", "direct-cohort", 0.0, 100.0, 1.0),
        ("transitive", "transitive-cohort", 0.0, 120.0, 1.0),
        ("cohort-peer", "shared", 0.0, 140.0, 1.0),
        ("safe", "safe-cohort", 0.0, 60.0, 1.0),
    )
    assignments = _assignments(
        ("test", "held-out"),
        ("direct", "other"),
        ("transitive", "other"),
        ("cohort-peer", "other"),
        ("safe", "other"),
    )

    split = _by_block(
        build_buffered_splits(
            observations,
            assignments,
            (("test", "direct"), ("direct", "transitive")),
            buffer_km=10.0,
            data_version="p1-test-v1",
        ),
        "held-out",
    )

    assert split.test_ids == ("test",)
    assert split.train_ids == ("safe",)
    assert split.excluded_ids == ("cohort-peer", "direct", "transitive")
    assert split.exclusion_reasons == (
        ("cohort-peer", ("dependency",)),
        ("direct", ("dependency",)),
        ("transitive", ("dependency",)),
    )


def test_buffer_uses_footprint_edges_and_retains_every_applicable_reason():
    """A dependency that also overlaps a test footprint must retain both reasons."""
    observations = _observations(
        ("test", "test-cohort", 0.0, 0.0, 5.0),
        ("same-site", "other-cohort", 0.0, 0.0, 2.0),
        ("both", "third-cohort", 0.0, 0.1, 2.0),
        ("safe", "safe-cohort", 0.0, 20.0, 2.0),
    )
    assignments = _assignments(
        ("test", "a"), ("same-site", "b"), ("both", "b"), ("safe", "b")
    )

    split = _by_block(
        build_buffered_splits(
            observations,
            assignments,
            (("test", "both"),),
            buffer_km=10.0,
            data_version="p1-test-v1",
        ),
        "a",
    )

    assert split.exclusion_reasons == (
        ("both", ("buffer", "dependency")),
        ("same-site", ("buffer",)),
    )
    assert split.train_ids == ("safe",)


def test_exact_buffer_boundary_is_excluded_and_realized_separation_is_recorded():
    """Changing <= to < would put the boundary record in training."""
    boundary = EARTH_RADIUS_KM * pi / 2.0 - 3.0
    observations = _observations(
        ("test", "c1", 0.0, 0.0, 1.0),
        ("boundary", "c2", 0.0, 90.0, 2.0),
        ("safe", "c3", 0.0, 91.0, 2.0),
    )
    assignments = _assignments(("test", "a"), ("boundary", "b"), ("safe", "b"))

    split = _by_block(
        build_buffered_splits(
            observations,
            assignments,
            (),
            buffer_km=boundary,
            data_version="p1-test-v1",
        ),
        "a",
    )

    assert split.excluded_ids == ("boundary",)
    assert split.train_ids == ("safe",)
    assert split.min_edge_separation_km == pytest.approx(10115.752301251947)


def test_antimeridian_and_polar_neighbours_are_buffered_geodesically():
    """Planar longitude subtraction would miss both short great-circle paths."""
    observations = _observations(
        ("date-test", "c1", 0.0, 179.9, 1.0),
        ("pole-test", "c2", 90.0, 0.0, 1.0),
        ("date-near", "c3", 0.0, -179.9, 1.0),
        ("pole-near", "c4", 89.9, 180.0, 1.0),
        ("safe", "c5", 0.0, 0.0, 1.0),
    )
    assignments = _assignments(
        ("date-test", "a"),
        ("pole-test", "a"),
        ("date-near", "b"),
        ("pole-near", "b"),
        ("safe", "b"),
    )

    split = _by_block(
        build_buffered_splits(
            observations, assignments, (), buffer_km=25.0, data_version="p1-test-v1"
        ),
        "a",
    )

    assert split.excluded_ids == ("date-near", "pole-near")
    assert split.train_ids == ("safe",)


def test_every_planned_block_is_frozen_even_when_its_train_set_is_empty():
    """Dropping an infeasible fold would hide a benchmark failure."""
    observations = _observations(
        ("one", "shared", 0.0, 0.0, 1.0),
        ("two", "shared", 0.0, 10.0, 1.0),
    )
    assignments = _assignments(("one", "a"), ("two", "b"))

    splits = build_buffered_splits(
        observations, assignments, (), buffer_km=1.0, data_version="p1-test-v1"
    )

    assert tuple(split.block_id for split in splits) == ("a", "b")
    assert all(split.train_ids == () for split in splits)
    assert all(split.min_edge_separation_km is None for split in splits)
    with pytest.raises(FrozenInstanceError):
        splits[0].block_id = "changed"  # type: ignore[misc]


def test_manifest_is_deterministic_under_row_edge_order_and_orientation():
    """Iteration order must not alter immutable artifact identities."""
    observations = _observations(
        ("a", "ca", 0.0, 0.0, 1.0),
        ("b", "cb", 0.0, 30.0, 1.0),
        ("c", "cc", 0.0, 60.0, 1.0),
    )
    assignments = _assignments(("a", "left"), ("b", "right"), ("c", "right"))
    first = build_buffered_splits(
        observations,
        assignments,
        (("a", "b"), ("b", "c")),
        buffer_km=5.0,
        data_version="p1-test-v1",
    )
    second = build_buffered_splits(
        observations.iloc[::-1].reset_index(drop=True),
        assignments.iloc[::-1].reset_index(drop=True),
        (("c", "b"), ("b", "a")),
        buffer_km=5.0,
        data_version="p1-test-v1",
    )

    assert first == second
    assert len({split.split_id for split in first}) == len(first)


def test_validate_split_recomputes_membership_reasons_fingerprint_and_id():
    """A self-consistent-looking supplied hash must not excuse a modified manifest."""
    observations = _observations(
        ("test", "c1", 0.0, 0.0, 1.0),
        ("near", "c2", 0.0, 0.1, 1.0),
        ("safe", "c3", 0.0, 20.0, 1.0),
    )
    assignments = _assignments(("test", "a"), ("near", "b"), ("safe", "b"))
    kwargs = {"buffer_km": 20.0, "data_version": "p1-test-v1"}
    split = _by_block(build_buffered_splits(observations, assignments, (), **kwargs), "a")
    validate_split(split, observations, assignments, (), **kwargs)

    corruptions = (
        replace(split, train_ids=("near", "safe")),
        replace(split, exclusion_reasons=()),
        replace(split, input_fingerprint="0" * 64),
        replace(split, split_id="0" * 64),
    )
    for corrupted in corruptions:
        with pytest.raises(ValueError, match="does not match"):
            validate_split(corrupted, observations, assignments, (), **kwargs)

    changed = observations.copy()
    changed.loc[changed["source_record_id"] == "safe", "lat"] = 1.0
    with pytest.raises(ValueError, match="does not match"):
        validate_split(split, changed, assignments, (), **kwargs)


@pytest.mark.parametrize(
    ("observations", "match"),
    [
        (_observations(("x", "c", 0.0, 0.0, 1.0), ("x", "d", 1.0, 1.0, 1.0)), "unique"),
        (_observations(("", "c", 0.0, 0.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)), "source_record_id"),
        (_observations((1, "c", 0.0, 0.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)), "source_record_id"),
        (_observations(("x", " ", 0.0, 0.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)), "cohort_id"),
        (_observations(("x", "c", "0", 0.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)), "lat"),
        (_observations(("x", "c", 91.0, 0.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)), "lat"),
        (_observations(("x", "c", 0.0, 181.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)), "lon"),
        (_observations(("x", "c", 0.0, 0.0, 0.0), ("y", "d", 1.0, 1.0, 1.0)), "radius_km"),
        (_observations(("x", "c", 0.0, 0.0, float("nan")), ("y", "d", 1.0, 1.0, 1.0)), "radius_km"),
    ],
)
def test_invalid_observation_identity_coordinates_and_radii_are_refused(observations, match):
    """Invalid P1 footprint fields must fail instead of being coerced or defaulted."""
    assignments = _assignments(("x", "a"), ("y", "b"))
    with pytest.raises(ValueError, match=match):
        build_buffered_splits(
            observations, assignments, (), buffer_km=1.0, data_version="p1-test-v1"
        )


@pytest.mark.parametrize(
    ("assignments", "dependencies", "match"),
    [
        (_assignments(("x", "a")), (), "exactly"),
        (_assignments(("x", "a"), ("y", "b"), ("z", "c")), (), "exactly"),
        (_assignments(("x", "a"), ("x", "b"), ("y", "b")), (), "exactly once"),
        (_assignments(("x", "a"), ("y", " ")), (), "block_id"),
        (_assignments(("x", "a"), ("y", 2)), (), "block_id"),
        (_assignments(("x", "a"), ("y", "a")), (), "at least two"),
        (_assignments(("x", "a"), ("y", "b")), (("x", "orphan"),), "unknown"),
        (_assignments(("x", "a"), ("y", "b")), (("x",),), "pair"),
    ],
)
def test_orphan_or_malformed_assignments_and_edges_are_refused(assignments, dependencies, match):
    observations = _observations(
        ("x", "c", 0.0, 0.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)
    )
    with pytest.raises(ValueError, match=match):
        build_buffered_splits(
            observations, assignments, dependencies, buffer_km=1.0, data_version="p1-test-v1"
        )


@pytest.mark.parametrize(
    ("buffer_km", "data_version", "match"),
    [
        (0.0, "v1", "buffer_km"),
        (float("inf"), "v1", "buffer_km"),
        ("1", "v1", "buffer_km"),
        (1.0, "", "data_version"),
        (1.0, 1, "data_version"),
    ],
)
def test_buffer_and_data_version_are_explicit_validated_inputs(buffer_km, data_version, match):
    observations = _observations(
        ("x", "c", 0.0, 0.0, 1.0), ("y", "d", 1.0, 1.0, 1.0)
    )
    assignments = _assignments(("x", "a"), ("y", "b"))
    with pytest.raises(ValueError, match=match):
        build_buffered_splits(
            observations, assignments, (), buffer_km=buffer_km, data_version=data_version
        )


def test_fingerprint_covers_every_input_that_defines_membership():
    """Changing cohort, footprint, block, edge, buffer, or version must change provenance."""
    observations = _observations(
        ("x", "cx", 0.0, 0.0, 1.0),
        ("y", "cy", 0.0, 30.0, 1.0),
        ("z", "cz", 0.0, 60.0, 1.0),
    )
    assignments = _assignments(("x", "a"), ("y", "b"), ("z", "b"))

    def fingerprint(obs=observations, blocks=assignments, edges=(), buffer=1.0, version="v1"):
        return build_buffered_splits(
            obs, blocks, edges, buffer_km=buffer, data_version=version
        )[0].input_fingerprint

    changed_cohort = observations.copy()
    changed_cohort.loc[0, "cohort_id"] = "new-cohort"
    changed_radius = observations.copy()
    changed_radius.loc[0, "radius_km"] = 2.0
    changed_blocks = _assignments(("x", "b"), ("y", "a"), ("z", "b"))

    baseline = fingerprint()
    assert len(
        {
            baseline,
            fingerprint(obs=changed_cohort),
            fingerprint(obs=changed_radius),
            fingerprint(blocks=changed_blocks),
            fingerprint(edges=(("x", "y"),)),
            fingerprint(buffer=2.0),
            fingerprint(version="v2"),
        }
    ) == 7

"""Dependency-aware buffered benchmark manifests (design §§5, 7, 8).

These pure offline functions define geographic evidence holdouts before model fitting. Callers
provide observation identities, cohort identities, reviewed dependency edges, sampling
coordinates and footprint radii explicitly. This module does not infer ancestry, participant
identity, block geography, or whether a catalog radius is a reviewed recruitment footprint.

Dependencies use ``Sequence[tuple[str, str]]``: each two-tuple is one undirected edge between
``source_record_id`` values. This representation is intentionally JSON/TSV-adapter friendly for
the later CLI, while the science layer itself performs no file I/O. Split records contain only
tuples and scalars, so a frozen record has no mutable nested collection.

``input_fingerprint`` hashes canonical validated values for every input that determines split
membership. It is deliberately not a source-file checksum: the later I/O adapter must hash each
complete input file independently so provenance also covers ignored columns and raw file bytes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Literal

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088
_DISTANCE_CHUNK_SIZE = 1024
_OBSERVATION_COLUMNS = ("source_record_id", "cohort_id", "lat", "lon", "radius_km")
_ASSIGNMENT_COLUMNS = ("source_record_id", "block_id")

ExclusionReason = Literal["buffer", "dependency"]
DependencyPair = tuple[str, str]
ExclusionReasons = tuple[tuple[str, tuple[ExclusionReason, ...]], ...]


@dataclass(frozen=True)
class BenchmarkSplit:
    """One immutable planned holdout and its leakage exclusions.

    ``train_ids == ()`` is an explicit infeasible split, not a reason to omit the block.
    ``min_edge_separation_km`` is unavailable only when no training observation remains.
    """

    split_id: str
    block_id: str
    train_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    exclusion_reasons: ExclusionReasons
    min_edge_separation_km: float | None
    input_fingerprint: str
    buffer_km: float
    data_version: str


@dataclass(frozen=True)
class _Observation:
    source_record_id: str
    cohort_id: str
    lat: float
    lon: float
    radius_km: float


@dataclass(frozen=True)
class _PreparedInputs:
    observations: tuple[_Observation, ...]
    block_by_id: tuple[tuple[str, str], ...]
    dependencies: tuple[DependencyPair, ...]
    buffer_km: float
    data_version: str
    fingerprint: str


def _require_dataframe(frame: object, name: str, required: tuple[str, ...]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if frame.columns.duplicated().any():
        raise ValueError(f"{name} must not contain duplicate column labels")
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")
    return frame


def _require_label(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} values must be nonempty strings")
    return value


def _require_number(value: object, field: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{field} values must be numeric and finite")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{field} values must be numeric and finite")
    return result


def _canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _prepare_inputs(
    observations: pd.DataFrame,
    block_assignments: pd.DataFrame,
    dependencies: Sequence[DependencyPair],
    *,
    buffer_km: float,
    data_version: str,
) -> _PreparedInputs:
    obs_frame = _require_dataframe(observations, "observations", _OBSERVATION_COLUMNS)
    assignment_frame = _require_dataframe(
        block_assignments, "block_assignments", _ASSIGNMENT_COLUMNS
    )
    normalized_buffer = _require_number(buffer_km, "buffer_km")
    if normalized_buffer <= 0.0:
        raise ValueError("buffer_km must be positive and finite")
    normalized_version = _require_label(data_version, "data_version")

    normalized_observations: list[_Observation] = []
    for values in obs_frame.loc[:, _OBSERVATION_COLUMNS].itertuples(index=False, name=None):
        record_id = _require_label(values[0], "source_record_id")
        cohort_id = _require_label(values[1], "cohort_id")
        lat = _require_number(values[2], "lat")
        lon = _require_number(values[3], "lon")
        radius_km = _require_number(values[4], "radius_km")
        if not -90.0 <= lat <= 90.0:
            raise ValueError("lat values must be within [-90, 90]")
        if not -180.0 <= lon <= 180.0:
            raise ValueError("lon values must be within [-180, 180]")
        if radius_km <= 0.0:
            raise ValueError("radius_km values must be positive and finite")
        normalized_observations.append(_Observation(record_id, cohort_id, lat, lon, radius_km))

    observation_ids = [observation.source_record_id for observation in normalized_observations]
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("observations source_record_id values must be unique")
    id_set = set(observation_ids)

    normalized_assignments: list[tuple[str, str]] = []
    for record_value, block_value in assignment_frame.loc[
        :, _ASSIGNMENT_COLUMNS
    ].itertuples(index=False, name=None):
        record_id = _require_label(record_value, "block_assignments source_record_id")
        block_id = _require_label(block_value, "block_id")
        normalized_assignments.append((record_id, block_id))
    assigned_ids = [record_id for record_id, _ in normalized_assignments]
    if len(set(assigned_ids)) != len(assigned_ids):
        raise ValueError("block_assignments must map every source_record_id exactly once")
    if set(assigned_ids) != id_set:
        raise ValueError("block_assignments must map exactly the observation source_record_id set")
    if len({block_id for _, block_id in normalized_assignments}) < 2:
        raise ValueError("block_assignments must define at least two nonempty blocks")

    if isinstance(dependencies, (str, bytes)) or not isinstance(dependencies, Sequence):
        raise TypeError("dependencies must be a sequence of (source_record_id, source_record_id) pairs")
    normalized_dependencies: set[DependencyPair] = set()
    for pair in dependencies:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("each dependency must be a two-tuple pair")
        left = _require_label(pair[0], "dependency source_record_id")
        right = _require_label(pair[1], "dependency source_record_id")
        unknown = sorted({left, right} - id_set)
        if unknown:
            raise ValueError(f"dependency references unknown source_record_id values: {unknown}")
        normalized_dependencies.add((left, right) if left <= right else (right, left))

    sorted_observations = tuple(
        sorted(normalized_observations, key=lambda observation: observation.source_record_id)
    )
    sorted_assignments = tuple(sorted(normalized_assignments))
    sorted_dependencies = tuple(sorted(normalized_dependencies))
    fingerprint_payload = {
        "schema_version": 1,
        "observations": [
            [
                observation.source_record_id,
                observation.cohort_id,
                observation.lat,
                observation.lon,
                observation.radius_km,
            ]
            for observation in sorted_observations
        ],
        "block_assignments": sorted_assignments,
        "dependencies": sorted_dependencies,
        "buffer_km": normalized_buffer,
        "data_version": normalized_version,
    }
    return _PreparedInputs(
        observations=sorted_observations,
        block_by_id=sorted_assignments,
        dependencies=sorted_dependencies,
        buffer_km=normalized_buffer,
        data_version=normalized_version,
        fingerprint=_canonical_json_hash(fingerprint_payload),
    )


class _Components:
    def __init__(self, ids: Sequence[str]) -> None:
        self._parent = {record_id: record_id for record_id in ids}

    def find(self, record_id: str) -> str:
        parent = self._parent[record_id]
        while parent != self._parent[parent]:
            parent = self._parent[parent]
        while record_id != parent:
            next_id = self._parent[record_id]
            self._parent[record_id] = parent
            record_id = next_id
        return parent

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            self._parent[right_root] = left_root
        else:
            self._parent[left_root] = right_root


def _dependency_components(prepared: _PreparedInputs) -> _Components:
    ids = [observation.source_record_id for observation in prepared.observations]
    components = _Components(ids)
    first_by_cohort: dict[str, str] = {}
    for observation in prepared.observations:
        first = first_by_cohort.setdefault(
            observation.cohort_id, observation.source_record_id
        )
        components.union(first, observation.source_record_id)
    for left, right in prepared.dependencies:
        components.union(left, right)
    return components


def _minimum_edge_separations(
    candidates: Sequence[_Observation], tests: Sequence[_Observation]
) -> np.ndarray:
    """Minimum footprint-edge distance per candidate using bounded two-dimensional chunks."""
    result = np.full(len(candidates), np.inf, dtype=float)
    for candidate_start in range(0, len(candidates), _DISTANCE_CHUNK_SIZE):
        candidate_chunk = candidates[candidate_start : candidate_start + _DISTANCE_CHUNK_SIZE]
        candidate_lat = np.radians([observation.lat for observation in candidate_chunk])[:, None]
        candidate_lon = np.radians([observation.lon for observation in candidate_chunk])[:, None]
        candidate_radius = np.asarray(
            [observation.radius_km for observation in candidate_chunk]
        )[:, None]
        chunk_minimum = np.full(len(candidate_chunk), np.inf, dtype=float)
        for test_start in range(0, len(tests), _DISTANCE_CHUNK_SIZE):
            test_chunk = tests[test_start : test_start + _DISTANCE_CHUNK_SIZE]
            test_lat = np.radians([observation.lat for observation in test_chunk])[None, :]
            test_lon = np.radians([observation.lon for observation in test_chunk])[None, :]
            test_radius = np.asarray([observation.radius_km for observation in test_chunk])[None, :]
            delta_lat = test_lat - candidate_lat
            delta_lon = test_lon - candidate_lon
            haversine = (
                np.sin(delta_lat / 2.0) ** 2
                + np.cos(candidate_lat) * np.cos(test_lat) * np.sin(delta_lon / 2.0) ** 2
            )
            haversine = np.clip(haversine, 0.0, 1.0)
            centre_distance = 2.0 * EARTH_RADIUS_KM * np.arctan2(
                np.sqrt(haversine), np.sqrt(1.0 - haversine)
            )
            edge_distance = np.maximum(
                centre_distance - candidate_radius - test_radius, 0.0
            )
            chunk_minimum = np.minimum(chunk_minimum, edge_distance.min(axis=1))
        result[
            candidate_start : candidate_start + len(candidate_chunk)
        ] = chunk_minimum
    return result


def _split_id_payload(split: BenchmarkSplit) -> dict[str, object]:
    return {
        "schema_version": 1,
        "block_id": split.block_id,
        "train_ids": split.train_ids,
        "test_ids": split.test_ids,
        "excluded_ids": split.excluded_ids,
        "exclusion_reasons": split.exclusion_reasons,
        "min_edge_separation_km": split.min_edge_separation_km,
        "input_fingerprint": split.input_fingerprint,
        "buffer_km": split.buffer_km,
        "data_version": split.data_version,
    }


def _build_prepared_splits(prepared: _PreparedInputs) -> tuple[BenchmarkSplit, ...]:
    observation_by_id = {
        observation.source_record_id: observation for observation in prepared.observations
    }
    block_by_id = dict(prepared.block_by_id)
    components = _dependency_components(prepared)
    splits: list[BenchmarkSplit] = []
    for block_id in sorted(set(block_by_id.values())):
        test_ids = tuple(
            sorted(record_id for record_id, assigned in block_by_id.items() if assigned == block_id)
        )
        candidate_ids = tuple(sorted(set(observation_by_id) - set(test_ids)))
        candidates = tuple(observation_by_id[record_id] for record_id in candidate_ids)
        tests = tuple(observation_by_id[record_id] for record_id in test_ids)
        edge_separations = _minimum_edge_separations(candidates, tests)
        test_components = {components.find(record_id) for record_id in test_ids}

        reasons_by_id: dict[str, tuple[ExclusionReason, ...]] = {}
        train_ids: list[str] = []
        train_positions: list[int] = []
        for index, record_id in enumerate(candidate_ids):
            reasons: list[ExclusionReason] = []
            if edge_separations[index] <= prepared.buffer_km:
                reasons.append("buffer")
            if components.find(record_id) in test_components:
                reasons.append("dependency")
            if reasons:
                reasons_by_id[record_id] = tuple(reasons)
            else:
                train_ids.append(record_id)
                train_positions.append(index)

        train_ids_tuple = tuple(train_ids)
        minimum_separation = (
            float(np.min(edge_separations[train_positions])) if train_positions else None
        )
        excluded_ids = tuple(sorted(reasons_by_id))
        exclusion_reasons: ExclusionReasons = tuple(
            (record_id, reasons_by_id[record_id]) for record_id in excluded_ids
        )
        split_without_id = BenchmarkSplit(
            split_id="",
            block_id=block_id,
            train_ids=train_ids_tuple,
            test_ids=test_ids,
            excluded_ids=excluded_ids,
            exclusion_reasons=exclusion_reasons,
            min_edge_separation_km=minimum_separation,
            input_fingerprint=prepared.fingerprint,
            buffer_km=prepared.buffer_km,
            data_version=prepared.data_version,
        )
        splits.append(
            BenchmarkSplit(
                **{
                    **split_without_id.__dict__,
                    "split_id": _canonical_json_hash(_split_id_payload(split_without_id)),
                }
            )
        )
    return tuple(splits)


def build_buffered_splits(
    observations: pd.DataFrame,
    block_assignments: pd.DataFrame,
    dependencies: Sequence[DependencyPair],
    *,
    buffer_km: float,
    data_version: str,
) -> tuple[BenchmarkSplit, ...]:
    """Build one deterministic dependency-aware split per caller-supplied block."""
    prepared = _prepare_inputs(
        observations,
        block_assignments,
        dependencies,
        buffer_km=buffer_km,
        data_version=data_version,
    )
    return _build_prepared_splits(prepared)


def validate_split(
    split: BenchmarkSplit,
    observations: pd.DataFrame,
    block_assignments: pd.DataFrame,
    dependencies: Sequence[DependencyPair],
    *,
    buffer_km: float,
    data_version: str,
) -> None:
    """Recompute and validate one split against all original membership-defining inputs."""
    if not isinstance(split, BenchmarkSplit):
        raise TypeError("split must be a BenchmarkSplit")
    expected_splits = build_buffered_splits(
        observations,
        block_assignments,
        dependencies,
        buffer_km=buffer_km,
        data_version=data_version,
    )
    expected_by_block = {expected.block_id: expected for expected in expected_splits}
    expected = expected_by_block.get(split.block_id)
    if expected is None or split != expected:
        raise ValueError("split does not match the manifest recomputed from its declared inputs")

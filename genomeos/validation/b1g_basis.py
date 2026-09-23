"""Compact positive-basis geometry for B1G (design §§4–8, 12; #331).

Scientific objective
    Test whether local positive-count anchors can recover HbS peaks without lifting unsupported
    zero-count regions or introducing environmental covariates.
Measurable output
    Select a deterministic fixed-size set of positive training footprints for each declared B1G
    basis configuration.
Engineering interface
    :func:`select_b1g_centres` accepts qualified P1 training observations and an explicit frozen
    :class:`B1GBasisConfig`. It performs no file, network, fitting, or serving-path work.
Assumptions and refusals
    Candidates must be modern observations of one non-phenotype variant with positive allele
    counts. Duplicate footprints collapse to the smallest ``source_record_id``. A fold with too
    few unique positive footprints is infeasible and fails explicitly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real
from typing import Literal

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import validate_allele_observations
from genomeos.validation.splits import EARTH_RADIUS_KM, BenchmarkSplit, build_buffered_splits

_ALLOWED_RADII_KM = frozenset({500.0, 1000.0, 2000.0})
_ALLOWED_BASIS_COUNTS = frozenset({8, 16, 32})

PreflightState = Literal["eligible", "infeasible"]


class B1GInfeasibleError(ValueError):
    """Raised when a training fold cannot supply the declared positive basis."""


@dataclass(frozen=True)
class B1GBasisConfig:
    """One cell in the fixed B1G preflight grid."""

    radius_km: float
    basis_count: int
    query_chunk_size: int = 1024

    def __post_init__(self) -> None:
        if isinstance(self.radius_km, (bool, np.bool_)) or not isinstance(
            self.radius_km, Real
        ):
            raise ValueError(f"radius_km must be one of {sorted(_ALLOWED_RADII_KM)}")
        radius_km = float(self.radius_km)
        if radius_km not in _ALLOWED_RADII_KM:
            raise ValueError(f"radius_km must be one of {sorted(_ALLOWED_RADII_KM)}")
        if isinstance(self.basis_count, (bool, np.bool_)) or not isinstance(
            self.basis_count, Integral
        ):
            raise ValueError(f"basis_count must be one of {sorted(_ALLOWED_BASIS_COUNTS)}")
        basis_count = int(self.basis_count)
        if basis_count not in _ALLOWED_BASIS_COUNTS:
            raise ValueError(f"basis_count must be one of {sorted(_ALLOWED_BASIS_COUNTS)}")
        if isinstance(self.query_chunk_size, (bool, np.bool_)) or not isinstance(
            self.query_chunk_size, Integral
        ):
            raise ValueError("query_chunk_size must be a positive integer")
        query_chunk_size = int(self.query_chunk_size)
        if query_chunk_size <= 0:
            raise ValueError("query_chunk_size must be a positive integer")
        object.__setattr__(self, "radius_km", radius_km)
        object.__setattr__(self, "basis_count", basis_count)
        object.__setattr__(self, "query_chunk_size", query_chunk_size)


@dataclass(frozen=True)
class B1GCentreSet:
    """Immutable, selection-ordered positive training footprints."""

    source_record_ids: tuple[str, ...]
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    footprint_radii_km: tuple[float, ...]


@dataclass(frozen=True)
class B1GBasisMatrix:
    """One immutable query-by-centre Wendland matrix."""

    source_record_ids: tuple[str, ...]
    centre_source_record_ids: tuple[str, ...]
    values: np.ndarray

    def __post_init__(self) -> None:
        values = np.asarray(self.values, dtype=float).copy()
        expected_shape = (len(self.source_record_ids), len(self.centre_source_record_ids))
        if values.shape != expected_shape:
            raise ValueError(f"values must have shape {expected_shape}")
        if not np.isfinite(values).all() or ((values < 0.0) | (values > 1.0)).any():
            raise ValueError("values must be finite and within [0, 1]")
        values.setflags(write=False)
        object.__setattr__(self, "values", values)


@dataclass(frozen=True)
class B1GPreflightCell:
    """One preserved split × radius × basis-count geometry result."""

    split_id: str
    block_id: str
    radius_km: float
    basis_count: int
    status: PreflightState
    failure_reason: str | None
    training_observation_count: int
    unique_positive_footprint_count: int
    test_observation_count: int
    positive_test_count: int
    zero_test_count: int
    geometrically_supported_test_count: int | None
    geometrically_supported_positive_count: int | None
    geometrically_supported_zero_count: int | None
    centre_source_record_ids: tuple[str, ...]
    query_chunk_size: int
    matrix_nbytes: int | None


@dataclass(frozen=True)
class B1GPreflightGridSummary:
    """Fold-aggregated geometric reach for one preregistered grid cell."""

    radius_km: float
    basis_count: int
    planned_fold_count: int
    eligible_fold_count: int
    infeasible_fold_count: int
    evaluated_positive_count: int
    evaluated_zero_count: int
    geometrically_supported_positive_count: int
    geometrically_supported_zero_count: int
    positive_support_fraction: float | None
    zero_support_fraction: float | None
    matrix_nbytes: int


@dataclass(frozen=True)
class B1GPreflightReport:
    """Complete immutable geometry ledger for the fixed B1G grid."""

    splits: tuple[BenchmarkSplit, ...]
    cells: tuple[B1GPreflightCell, ...]
    grid_summary: tuple[B1GPreflightGridSummary, ...]
    data_version: str
    buffer_km: float


def _edge_distance_matrix(
    query_lat: np.ndarray,
    query_lon: np.ndarray,
    query_radius: np.ndarray,
    centre_lat: np.ndarray,
    centre_lon: np.ndarray,
    centre_radius: np.ndarray,
) -> np.ndarray:
    """Return footprint-edge distances for one vectorized query-by-centre block."""
    delta_lat = centre_lat[None, :] - query_lat[:, None]
    delta_lon = centre_lon[None, :] - query_lon[:, None]
    haversine = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(query_lat[:, None])
        * np.cos(centre_lat[None, :])
        * np.sin(delta_lon / 2.0) ** 2
    )
    haversine = np.clip(haversine, 0.0, 1.0)
    centre_distance = 2.0 * EARTH_RADIUS_KM * np.arctan2(
        np.sqrt(haversine), np.sqrt(1.0 - haversine)
    )
    return np.maximum(
        centre_distance - query_radius[:, None] - centre_radius[None, :],
        0.0,
    )


def wendland_c2(distance_km: np.ndarray, *, radius_km: float) -> np.ndarray:
    """Evaluate the preregistered compact-support C2 Wendland basis."""
    if isinstance(radius_km, (bool, np.bool_)) or not isinstance(radius_km, Real):
        raise ValueError("radius_km must be positive and finite")
    radius = float(radius_km)
    if not isfinite(radius) or radius <= 0.0:
        raise ValueError("radius_km must be positive and finite")
    distance = np.asarray(distance_km, dtype=float)
    if not np.isfinite(distance).all() or (distance < 0.0).any():
        raise ValueError("distance_km must contain finite nonnegative values")
    scaled = distance / radius
    interior = scaled < 1.0
    remainder = np.where(interior, 1.0 - scaled, 0.0)
    return np.where(interior, remainder**4 * (4.0 * scaled + 1.0), 0.0)


def _positive_footprints(training_observations: pd.DataFrame) -> pd.DataFrame:
    training = validate_allele_observations(training_observations)
    if training.empty:
        raise ValueError("training_observations must not be empty")
    variants = tuple(sorted(set(training["variant_id"])))
    if len(variants) != 1:
        raise ValueError("training_observations must describe one variant")
    if variants[0].startswith("phenotype:"):
        raise ValueError("B1G rejects phenotype composites")
    if ((training["date_lower"] != 0) | (training["date_upper"] != 0)).any():
        raise ValueError("B1G requires modern observations")
    positive = training.loc[training["ac"] > 0].sort_values("source_record_id")
    return positive.drop_duplicates(
        subset=["lat", "lon", "radius_km"],
        keep="first",
    ).reset_index(drop=True)


def select_b1g_centres(
    training_observations: pd.DataFrame,
    *,
    config: B1GBasisConfig,
) -> B1GCentreSet:
    """Select deterministic farthest-first centres from positive training footprints."""
    if not isinstance(config, B1GBasisConfig):
        raise TypeError("config must be a B1GBasisConfig")
    candidates = _positive_footprints(training_observations)
    if len(candidates) < config.basis_count:
        raise B1GInfeasibleError(
            "training fold has "
            f"{len(candidates)} unique positive footprints; {config.basis_count} required"
        )

    latitudes = np.radians(candidates["lat"].to_numpy(dtype=float, copy=True))
    longitudes = np.radians(candidates["lon"].to_numpy(dtype=float, copy=True))
    radii = candidates["radius_km"].to_numpy(dtype=float, copy=True)
    selected = [0]
    minimum_distance = _edge_distance_matrix(
        latitudes,
        longitudes,
        radii,
        latitudes[:1],
        longitudes[:1],
        radii[:1],
    )[:, 0]
    minimum_distance[0] = -np.inf

    for _ in range(1, config.basis_count):
        next_index = int(np.argmax(minimum_distance))
        selected.append(next_index)
        distance_to_new_centre = _edge_distance_matrix(
            latitudes,
            longitudes,
            radii,
            latitudes[next_index : next_index + 1],
            longitudes[next_index : next_index + 1],
            radii[next_index : next_index + 1],
        )[:, 0]
        np.minimum(minimum_distance, distance_to_new_centre, out=minimum_distance)
        minimum_distance[selected] = -np.inf

    chosen = candidates.iloc[selected]
    return B1GCentreSet(
        source_record_ids=tuple(chosen["source_record_id"]),
        latitudes=tuple(chosen["lat"].astype(float)),
        longitudes=tuple(chosen["lon"].astype(float)),
        footprint_radii_km=tuple(chosen["radius_km"].astype(float)),
    )


def build_b1g_basis(
    training_observations: pd.DataFrame,
    query_observations: pd.DataFrame,
    *,
    config: B1GBasisConfig,
) -> B1GBasisMatrix:
    """Build a training-only B1G basis for held-out queries in bounded chunks."""
    if not isinstance(config, B1GBasisConfig):
        raise TypeError("config must be a B1GBasisConfig")
    training = validate_allele_observations(training_observations)
    queries = validate_allele_observations(query_observations)
    if queries.empty:
        raise ValueError("query_observations must not be empty")
    overlap = sorted(set(training["source_record_id"]) & set(queries["source_record_id"]))
    if overlap:
        raise ValueError(f"training and query source_record_id values overlap: {overlap}")
    variants = tuple(sorted(set(training["variant_id"]) | set(queries["variant_id"])))
    if len(variants) != 1:
        raise ValueError("training and query observations must describe the same single variant")
    if variants[0].startswith("phenotype:"):
        raise ValueError("B1G rejects phenotype composites")
    dated = pd.concat(
        [training.loc[:, ["date_lower", "date_upper"]], queries.loc[:, ["date_lower", "date_upper"]]],
        ignore_index=True,
    )
    if ((dated["date_lower"] != 0) | (dated["date_upper"] != 0)).any():
        raise ValueError("B1G requires modern observations")

    centres = select_b1g_centres(training, config=config)
    queries = queries.sort_values("source_record_id").reset_index(drop=True)
    centre_lat = np.radians(np.asarray(centres.latitudes))
    centre_lon = np.radians(np.asarray(centres.longitudes))
    centre_radius = np.asarray(centres.footprint_radii_km)
    values = np.empty((len(queries), config.basis_count), dtype=float)
    for start in range(0, len(queries), config.query_chunk_size):
        chunk = queries.iloc[start : start + config.query_chunk_size]
        edge_distance = _edge_distance_matrix(
            np.radians(chunk["lat"].to_numpy(dtype=float, copy=True)),
            np.radians(chunk["lon"].to_numpy(dtype=float, copy=True)),
            chunk["radius_km"].to_numpy(dtype=float, copy=True),
            centre_lat,
            centre_lon,
            centre_radius,
        )
        values[start : start + len(chunk)] = wendland_c2(
            edge_distance,
            radius_km=config.radius_km,
        )
    return B1GBasisMatrix(
        source_record_ids=tuple(queries["source_record_id"]),
        centre_source_record_ids=centres.source_record_ids,
        values=values,
    )


def _infeasible_cell(
    split: BenchmarkSplit,
    config: B1GBasisConfig,
    *,
    reason: str,
    training_count: int,
    positive_footprint_count: int,
    test_count: int,
    positive_test_count: int,
) -> B1GPreflightCell:
    return B1GPreflightCell(
        split_id=split.split_id,
        block_id=split.block_id,
        radius_km=config.radius_km,
        basis_count=config.basis_count,
        status="infeasible",
        failure_reason=reason,
        training_observation_count=training_count,
        unique_positive_footprint_count=positive_footprint_count,
        test_observation_count=test_count,
        positive_test_count=positive_test_count,
        zero_test_count=test_count - positive_test_count,
        geometrically_supported_test_count=None,
        geometrically_supported_positive_count=None,
        geometrically_supported_zero_count=None,
        centre_source_record_ids=(),
        query_chunk_size=config.query_chunk_size,
        matrix_nbytes=None,
    )


def _summarize_grid(cells: Sequence[B1GPreflightCell]) -> tuple[B1GPreflightGridSummary, ...]:
    summaries: list[B1GPreflightGridSummary] = []
    for radius_km in sorted(_ALLOWED_RADII_KM):
        for basis_count in sorted(_ALLOWED_BASIS_COUNTS):
            planned = [
                cell
                for cell in cells
                if cell.radius_km == radius_km and cell.basis_count == basis_count
            ]
            eligible = [cell for cell in planned if cell.status == "eligible"]
            positive_count = sum(cell.positive_test_count for cell in eligible)
            zero_count = sum(cell.zero_test_count for cell in eligible)
            supported_positive = sum(
                int(cell.geometrically_supported_positive_count) for cell in eligible
            )
            supported_zero = sum(
                int(cell.geometrically_supported_zero_count) for cell in eligible
            )
            summaries.append(
                B1GPreflightGridSummary(
                    radius_km=radius_km,
                    basis_count=basis_count,
                    planned_fold_count=len(planned),
                    eligible_fold_count=len(eligible),
                    infeasible_fold_count=len(planned) - len(eligible),
                    evaluated_positive_count=positive_count,
                    evaluated_zero_count=zero_count,
                    geometrically_supported_positive_count=supported_positive,
                    geometrically_supported_zero_count=supported_zero,
                    positive_support_fraction=(
                        supported_positive / positive_count if positive_count else None
                    ),
                    zero_support_fraction=(supported_zero / zero_count if zero_count else None),
                    matrix_nbytes=sum(int(cell.matrix_nbytes) for cell in eligible),
                )
            )
    return tuple(summaries)


def preflight_b1g_basis(
    observations: pd.DataFrame,
    block_assignments: pd.DataFrame,
    dependencies: Sequence[tuple[str, str]],
    *,
    buffer_km: float,
    data_version: str,
    query_chunk_size: int = 1024,
) -> B1GPreflightReport:
    """Evaluate geometric support for every fixed-grid cell on frozen outer folds."""
    validated = validate_allele_observations(observations)
    variants = tuple(sorted(set(validated["variant_id"])))
    if len(variants) != 1 or variants[0].startswith("phenotype:"):
        raise ValueError("B1G preflight requires one non-phenotype variant")
    if ((validated["date_lower"] != 0) | (validated["date_upper"] != 0)).any():
        raise ValueError("B1G preflight requires modern observations")
    configs = tuple(
        B1GBasisConfig(radius_km, basis_count, query_chunk_size)
        for radius_km in sorted(_ALLOWED_RADII_KM)
        for basis_count in sorted(_ALLOWED_BASIS_COUNTS)
    )
    splits = build_buffered_splits(
        validated,
        block_assignments,
        dependencies,
        buffer_km=buffer_km,
        data_version=data_version,
    )
    by_id = validated.set_index("source_record_id", drop=False)
    cells: list[B1GPreflightCell] = []
    for split in splits:
        training = by_id.loc[list(split.train_ids)].reset_index(drop=True)
        testing = (
            by_id.loc[list(split.test_ids)]
            .reset_index(drop=True)
            .sort_values("source_record_id")
            .reset_index(drop=True)
        )
        positive_test = testing["ac"].to_numpy(dtype=int, copy=True) > 0
        positive_footprint_count = (
            len(_positive_footprints(training)) if not training.empty else 0
        )
        for config in configs:
            if positive_footprint_count < config.basis_count:
                reason = (
                    "training fold has "
                    f"{positive_footprint_count} unique positive footprints; "
                    f"{config.basis_count} required"
                )
                cells.append(
                    _infeasible_cell(
                        split,
                        config,
                        reason=reason,
                        training_count=len(training),
                        positive_footprint_count=positive_footprint_count,
                        test_count=len(testing),
                        positive_test_count=int(positive_test.sum()),
                    )
                )
                continue
            basis = build_b1g_basis(training, testing, config=config)
            geometrically_supported = np.any(basis.values > 0.0, axis=1)
            cells.append(
                B1GPreflightCell(
                    split_id=split.split_id,
                    block_id=split.block_id,
                    radius_km=config.radius_km,
                    basis_count=config.basis_count,
                    status="eligible",
                    failure_reason=None,
                    training_observation_count=len(training),
                    unique_positive_footprint_count=positive_footprint_count,
                    test_observation_count=len(testing),
                    positive_test_count=int(positive_test.sum()),
                    zero_test_count=int((~positive_test).sum()),
                    geometrically_supported_test_count=int(geometrically_supported.sum()),
                    geometrically_supported_positive_count=int(
                        (geometrically_supported & positive_test).sum()
                    ),
                    geometrically_supported_zero_count=int(
                        (geometrically_supported & ~positive_test).sum()
                    ),
                    centre_source_record_ids=basis.centre_source_record_ids,
                    query_chunk_size=config.query_chunk_size,
                    matrix_nbytes=basis.values.nbytes,
                )
            )
    return B1GPreflightReport(
        splits=splits,
        cells=tuple(cells),
        grid_summary=_summarize_grid(cells),
        data_version=data_version,
        buffer_km=float(buffer_km),
    )

"""Reference-year population denominators for burden comparisons (design §8, §9).

A gridded population raster and a published burden benchmark answer different questions. The
raster says where people lived in its own reference year; the benchmark's national totals say
how many people its target year contained. A parity run may use the raster as within-country
spatial weights, but it must reproduce the benchmark's national totals before applying disease
frequencies or birth rates. Otherwise population growth is misreported as model error.

This module performs only that alignment. It carries no burden expression, model inference or
I/O, so callers must name both sources and the target year at the composition boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CELL_COLUMNS = frozenset({"h3_index", "iso3", "population"})
TARGET_COLUMNS = frozenset({"iso3", "target_population"})
PROVENANCE_COLUMNS = frozenset(
    {
        "population_weight",
        "population_scale_factor",
        "population_weight_source",
        "population_target_source",
        "population_target_year",
    }
)


@dataclass(frozen=True)
class PopulationAlignment:
    """Aligned per-cell populations and the country-level transformation that produced them."""

    cells: pd.DataFrame = field(repr=False)
    scales: pd.DataFrame = field(repr=False)
    weight_source: str
    target_source: str
    target_year: int
    unused_target_iso3: tuple[str, ...]


def align_country_populations(
    cells: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    weight_source: str,
    target_source: str,
    target_year: int,
) -> PopulationAlignment:
    """Rescale spatial weights to explicit national populations without changing their pattern.

    ``cells.population`` is treated only as a nonnegative within-country weight. Every country
    represented by a cell must have exactly one positive ``targets.target_population``. Extra
    targets are retained in ``unused_target_iso3`` because a reference can contain small states
    absent from a coarse country geometry; callers can then preserve those as explicit refusals.

    The returned ``population`` column is aligned to the target while ``population_weight``
    preserves the submitted values. Source names, target year and per-country scale factors are
    repeated on cells so later denominator construction cannot lose the transformation's meaning.
    """
    weight_source = _source(weight_source, "weight_source")
    target_source = _source(target_source, "target_source")
    if isinstance(target_year, (bool, np.bool_)) or not isinstance(
        target_year, (int, np.integer)
    ) or target_year <= 0:
        raise ValueError("target_year must be a positive integer")

    cell_frame = _cells(cells)
    target_frame = _targets(targets)
    cell_countries = set(cell_frame["iso3"])
    target_countries = set(target_frame["iso3"])
    missing = sorted(cell_countries - target_countries)
    if missing:
        raise ValueError(f"no target population for cell countries {missing}")

    weights = cell_frame.groupby("iso3", sort=True)["population"].sum()
    no_weight = sorted(weights.index[weights <= 0])
    if no_weight:
        raise ValueError(f"countries require positive spatial weight; got {no_weight}")

    target_by_country = target_frame.set_index("iso3")["target_population"]
    scales = pd.DataFrame(
        {
            "iso3": weights.index,
            "population_weight_total": weights.to_numpy(dtype=float),
            "target_population": target_by_country.loc[weights.index].to_numpy(dtype=float),
        }
    )
    scales["scale_factor"] = (
        scales["target_population"] / scales["population_weight_total"]
    )

    out = cell_frame.copy()
    out["population_weight"] = out["population"].to_numpy(dtype=float)
    factor = out["iso3"].map(scales.set_index("iso3")["scale_factor"])
    out["population_scale_factor"] = factor.to_numpy(dtype=float)
    out["population"] = out["population_weight"] * out["population_scale_factor"]
    out["population_weight_source"] = weight_source
    out["population_target_source"] = target_source
    out["population_target_year"] = int(target_year)

    actual = out.groupby("iso3", sort=True)["population"].sum()
    expected = scales.set_index("iso3")["target_population"]
    if not np.allclose(actual.loc[expected.index], expected, rtol=1e-12, atol=1e-6):
        raise RuntimeError("aligned cell populations do not reproduce country targets")

    return PopulationAlignment(
        cells=out,
        scales=scales,
        weight_source=weight_source,
        target_source=target_source,
        target_year=int(target_year),
        unused_target_iso3=tuple(sorted(target_countries - cell_countries)),
    )


def _cells(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("cells must be a nonempty DataFrame")
    missing = CELL_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"cells are missing required columns {sorted(missing)}")
    collisions = PROVENANCE_COLUMNS & set(frame.columns)
    if collisions:
        raise ValueError(f"cells already contain alignment columns {sorted(collisions)}")
    out = frame.copy()
    _validate_iso3(out["iso3"], "cells.iso3")
    if out["h3_index"].isna().any() or (out["h3_index"].astype(str).str.strip() == "").any():
        raise ValueError("cells.h3_index must be nonempty")
    if out["h3_index"].duplicated().any():
        raise ValueError("cells contain duplicate h3_index values")
    out["population"] = _numbers(out["population"], "cells.population", nonnegative=True)
    return out


def _targets(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("targets must be a nonempty DataFrame")
    missing = TARGET_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"targets are missing required columns {sorted(missing)}")
    out = frame.loc[:, ["iso3", "target_population"]].copy()
    _validate_iso3(out["iso3"], "targets.iso3")
    if out["iso3"].duplicated().any():
        raise ValueError("targets contain duplicate iso3 values")
    out["target_population"] = _numbers(
        out["target_population"], "targets.target_population", positive=True
    )
    return out


def _validate_iso3(values: pd.Series, name: str) -> None:
    valid = values.map(
        lambda value: isinstance(value, str)
        and len(value) == 3
        and value.isalpha()
        and value.isupper()
    )
    if not valid.all():
        raise ValueError(f"{name} must contain explicit uppercase ISO3 codes")


def _numbers(
    values: pd.Series,
    name: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
) -> pd.Series:
    raw = values.to_numpy(dtype=object)
    if any(isinstance(value, (bool, np.bool_)) for value in raw):
        raise ValueError(f"{name} must be numeric, not Boolean")
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError(f"{name} must contain finite numbers")
    if nonnegative and (numeric < 0).any():
        raise ValueError(f"{name} cannot contain negative values")
    if positive and (numeric <= 0).any():
        raise ValueError(f"{name} must contain positive values")
    return numeric


def _source(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value.strip()

"""HGDP registry adapter for curated inputs (design §§6, 12, 13; P0).

Every registry source module exposes the same `load(path, registry_version)` signature and
returns `(populations, aliases)` conforming to `registry.schema`. This parser consumes curated
input, not an untouched vendor export. Source qualification must establish coordinate meaning,
spatial support, and evidence before parsing; successful parsing does not establish review or
scientific eligibility.

Input coordinates represent ancestral localities, so `location_type = "ancestral"`. HGDP is an
indigenous-population panel, so every entry carries a CARE-aligned biocultural notice.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import pandas as pd

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA

SOURCE = "hgdp"
BIOCULTURAL_NOTICE = (
    "Indigenous-population panel. Reuse governed by the CARE Principles; see "
    "https://www.gida-global.org/careprinciples"
)


def slugify(label: str) -> str:
    """`"Yoruba"` -> `"hgdp-yoruba"`; matches the `_SLUG` pattern in registry.schema."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")
    return f"{SOURCE}-{cleaned}"


def _read_input(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader, None)
            if header is None:
                raise ValueError(f"{path}: missing TSV header")
            if len(header) != len(set(header)) or any(not name.strip() for name in header):
                raise ValueError(f"{path}: duplicate or blank column names")
            required = {
                "population",
                "latitude",
                "longitude",
                "uncertainty_radius_km",
                "provenance",
            }
            missing = required - set(header)
            if missing:
                raise ValueError(f"{path}: missing required columns {sorted(missing)}")
            rows = []
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(f"{path}: wrong field count at line {reader.line_num}")
                rows.append(row)
        except csv.Error as exc:
            raise ValueError(f"{path}: malformed TSV at line {reader.line_num}") from exc
    return pd.DataFrame(rows, columns=header, dtype=str)


def load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = _read_input(path)
    for column in (
        "population",
        "latitude",
        "longitude",
        "uncertainty_radius_km",
        "provenance",
    ):
        if raw[column].str.strip().eq("").any():
            raise ValueError(f"{path}: blank required value in {column}")

    numeric = {}
    for column in ("latitude", "longitude", "uncertainty_radius_km"):
        try:
            values = raw[column].astype(float)
        except ValueError as exc:
            raise ValueError(f"{path}: invalid numeric value in {column}") from exc
        if not values.map(math.isfinite).all():
            raise ValueError(f"{path}: nonfinite value in {column}")
        numeric[column] = values
    if (numeric["uncertainty_radius_km"] <= 0).any():
        raise ValueError(f"{path}: uncertainty_radius_km must be strictly positive")

    ids = raw["population"].map(slugify)
    populations = pd.DataFrame(
        {
            "population_id": ids,
            "lat": numeric["latitude"],
            "lon": numeric["longitude"],
            "uncertainty_radius_km": numeric["uncertainty_radius_km"],
            "location_type": "ancestral",
            "provenance": raw["provenance"],
            "biocultural_notice": BIOCULTURAL_NOTICE,
            "registry_version": registry_version,
        }
    )
    aliases = pd.DataFrame(
        {"population_id": ids, "source": SOURCE, "label": raw["population"]}
    )
    return POPULATIONS_SCHEMA.validate(populations), ALIASES_SCHEMA.validate(aliases)

"""WBBC regional registry adapter (Atlas design §§4, 6, 7.1; P0).

WBBC publishes four broad genetic regions defined by named Chinese administrative divisions.
They are not sampling sites.  The reviewed input represents each region by the centre of the
smallest great-circle disc covering its Natural Earth 1:10m member-province boundaries, with the
radius rounded upward.  ``location_type = "inferred"`` and the large radius preserve that coarse
support instead of presenting a multi-province group as a precise point.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA

SOURCE = "wbbc"
_COLUMNS = (
    "region",
    "latitude",
    "longitude",
    "uncertainty_radius_km",
    "member_divisions",
    "provenance",
)

# Reviewed against Cong et al. 2022 Supplementary Figure 1 and Natural Earth v5.1.1
# ne_10m_admin_1_states_provinces (public domain). Radii are the measured covering radii rounded
# upward to the next 25 km: North 2012.59, Central 343.13, South 1290.25, Lingnan 647.82 km.
_REVIEWED = {
    "North": (
        43.146298,
        109.721579,
        2025.0,
        "Gansu|Hebei|Heilongjiang|Henan|Inner Mongolia|Jilin|Liaoning|Ningxia|Qinghai|"
        "Shaanxi|Shandong|Shanxi|Tianjin",
    ),
    "Central": (32.235380, 118.341915, 350.0, "Anhui|Jiangsu"),
    "South": (
        28.503013,
        109.420054,
        1300.0,
        "Chongqing|Fujian|Guizhou|Hubei|Hunan|Jiangxi|Sichuan|Yunnan|Zhejiang",
    ),
    "Lingnan": (23.876558, 110.815613, 650.0, "Guangxi|Guangdong|Hainan"),
}
REGION_ORDER = tuple(_REVIEWED)


def load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the reviewed four-row WBBC region contract into P0 registry tables."""
    raw = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    if tuple(raw.columns) != _COLUMNS:
        raise ValueError(f"{path}: expected exactly the columns {list(_COLUMNS)}")
    if len(raw) != len(_REVIEWED) or set(raw["region"]) != set(_REVIEWED):
        raise ValueError(
            f"{path}: WBBC regions must be exactly {sorted(_REVIEWED)} with one row each"
        )
    if raw["region"].duplicated().any():
        raise ValueError(f"{path}: duplicate WBBC region")

    rows = raw.set_index("region").loc[list(REGION_ORDER)].copy()
    for column in ("latitude", "longitude", "uncertainty_radius_km"):
        rows[column] = pd.to_numeric(rows[column], errors="raise")

    for region, (lat, lon, radius, divisions) in _REVIEWED.items():
        row = rows.loc[region]
        if row["member_divisions"] != divisions:
            raise ValueError(f"{path}: {region} member divisions differ from the reviewed contract")
        actual = (float(row["latitude"]), float(row["longitude"]), float(row["uncertainty_radius_km"]))
        if actual != (lat, lon, radius):
            raise ValueError(f"{path}: {region} reviewed geography changed: {actual!r}")
        provenance = str(row["provenance"])
        if "10.1038/s41467-022-30526-x" not in provenance or "natural-earth:v5.1.1" not in provenance:
            raise ValueError(f"{path}: {region} provenance must name the paper and geometry release")

    population_ids = pd.Series(
        [f"wbbc-{region.lower()}" for region in REGION_ORDER], dtype="string"
    )
    populations = pd.DataFrame(
        {
            "population_id": population_ids,
            "lat": rows["latitude"].to_numpy(),
            "lon": rows["longitude"].to_numpy(),
            "uncertainty_radius_km": rows["uncertainty_radius_km"].to_numpy(),
            "location_type": "inferred",
            "provenance": rows["provenance"].to_numpy(),
            "biocultural_notice": pd.array([pd.NA] * len(rows), dtype="string"),
            "registry_version": registry_version,
        }
    )
    aliases = pd.DataFrame(
        {
            "population_id": population_ids,
            "source": SOURCE,
            "label": REGION_ORDER,
        }
    )
    return POPULATIONS_SCHEMA.validate(populations), ALIASES_SCHEMA.validate(aliases)

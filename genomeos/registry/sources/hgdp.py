"""HGDP registry adapter (design §6, P0) — the reference implementation of the adapter contract.

Every registry source module exposes the same `load(path, registry_version)` signature and
returns `(populations, aliases)` conforming to `registry.schema`. HGDP coordinates are the
Cavalli-Sforza panel's *ancestral* sampling localities, so `location_type = "ancestral"`.

HGDP is an indigenous-population panel, so every entry carries a CARE-aligned biocultural
notice per design §13.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SOURCE = "hgdp"

# HGDP localities are villages/regions, not points. 50 km is the panel-wide default extent; a
# per-population refinement is future work tracked as its own issue.
DEFAULT_RADIUS_KM = 50.0

PROVENANCE = "10.1126/science.1078311"  # Cann et al. 2002, HGDP-CEPH panel
BIOCULTURAL_NOTICE = (
    "Indigenous-population panel. Reuse governed by the CARE Principles; see "
    "https://www.gida-global.org/careprinciples"
)


def slugify(label: str) -> str:
    """`"Yoruba"` -> `"hgdp-yoruba"`; matches the `_SLUG` pattern in registry.schema."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")
    return f"{SOURCE}-{cleaned}"


def load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(path, sep="\t")
    missing = {"population", "latitude", "longitude"} - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")

    ids = raw["population"].map(slugify)

    populations = pd.DataFrame(
        {
            "population_id": ids,
            "lat": raw["latitude"].astype(float),
            "lon": raw["longitude"].astype(float),
            "uncertainty_radius_km": DEFAULT_RADIUS_KM,
            "location_type": "ancestral",
            "provenance": PROVENANCE,
            "biocultural_notice": BIOCULTURAL_NOTICE,
            "registry_version": registry_version,
        }
    )
    aliases = pd.DataFrame(
        {"population_id": ids, "source": SOURCE, "label": raw["population"].astype(str)}
    )
    return populations, aliases

"""Country identity, and the H3 → country rollup (design §9, §10, §11, P3/P5).

Two requirements that look separate and are the same requirement:

- **#94** needs national AS/SS neonate totals, which means summing a per-cell burden inside each
  country boundary.
- **#61** needs an admin choropleth, which means aggregating a per-cell statistic inside each
  country boundary.

They share one implementation here rather than each growing their own, because the part that is
easy to get subtly wrong — which country an H3 cell belongs to — has one right answer and would
otherwise have two chances to be wrong.

**ISO3 is the join key; the country name never is.** MAP writes "United Republic of Tanzania",
Piel et al. write "Tanzania, United Republic of", Natural Earth writes "Tanzania". Name matching
across three sources fails *silently*: an unmatched country drops out of a total, which is
indistinguishable from a country with no burden. So `resolve_iso3` raises on a name it cannot
resolve, naming the name (§12), and every downstream join is on ISO3.

**Geometry is Natural Earth 1:110m**, the file already committed for the review figures
(`genomeos.viz.basemap`), reused rather than duplicated. Three consequences a reader should know
before trusting a national number:

- **A cell belongs to the country its centre falls in.** At res 4 a cell is ~1,770 km², so cells
  straddling a border are assigned whole. Errors are compensating along a long border and are
  not along a short one, and they are largest for small countries — which is the same direction
  as the next point.
- **1:110m has no polygon for a small state at all.** Malta, Singapore, Bahrain, Mauritius, Cape
  Verde, Comoros and the Caribbean and Pacific islands are absent, so they receive no cells and
  therefore no estimate. For §8 that is honest and costly in the right direction: those countries
  stay in the parity denominator as countries we did not estimate (#93).
- **Dependencies are bundled into the metropolitan feature.** French Guiana is inside Natural
  Earth's France, so its cells are assigned FRA and no GUF estimate is produced even though Piel
  publishes one. A finer admin file (GADM, per §10) fixes this and #61 will need one anyway.

Pure functions over coordinates, with no HTTP or I/O beyond reading the committed geometry (§5).
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

import pandas as pd

from genomeos.surfaces.mask import aggregate_cells
from genomeos.viz.basemap import load_countries

#: Natural Earth 1:110m records `-99` in `iso_a3` for features whose sovereignty is contested or
#: whose dependencies it bundles, so the property cannot be trusted on its own. Each of these is
#: a decision with a burden consequence, so each is written down rather than defaulted:
#:
#: - **France, Norway** — real ISO 3166 codes; the `-99` is a Natural Earth artifact.
#: - **N. Cyprus → CYP, Somaliland → SOM** — de facto territories with no ISO 3166 code, folded
#:   into the state whose *published* national estimate covers them. Piel et al. report Somalia
#:   and Cyprus whole, so leaving Somaliland unassigned would delete roughly a third of Somalia's
#:   population from a country where HbS is common — an error that would read as model failure.
#: - **Kosovo → XKX** — the user-assigned code, kept separate rather than folded into Serbia.
#:   No published Piel row uses it, so a Kosovo estimate surfaces as unmatched instead of
#:   quietly inflating a country that *is* scored.
NATURAL_EARTH_ISO3_FIXUPS: dict[str, str] = {
    "France": "FRA",
    "Norway": "NOR",
    "N. Cyprus": "CYP",
    "Somaliland": "SOM",
    "Kosovo": "XKX",
}

#: Names that Natural Earth does not carry, or spells differently from the sources we join to.
#: Written as they appear in the wild and normalised on load, so this table stays readable.
#:
#: The first block is every Piel et al. 2013 country whose spelling differs from Natural Earth's
#: (ISO 3166 names as they stood in 2010, hence "Libyan Arab Jamahiriya" and "Swaziland"); the
#: second is the same countries as MAP, GADM and everyday usage spell them.
ISO3_ALIASES: dict[str, str] = {
    # Small territories absent from Natural Earth 1:110m, so their names never enter the index
    # from the geometry. See SUPPLEMENTARY_AREAS_KM2.
    "Hong Kong Special Administrative Region of China": "HKG",
    "Hong Kong SAR, China": "HKG",
    "Niue": "NIU",
    "Tokelau": "TKL",
    "Cook Islands": "COK",
    # --- Piel et al. 2013 / ISO 3166-1 (2010) names ---
    "Aruba": "ABW",
    "Bahrain": "BHR",
    "Barbados": "BRB",
    "Bolivia (Plurinational State of)": "BOL",
    "Bosnia and Herzegovina": "BIH",
    "Brunei Darussalam": "BRN",
    "Cape Verde": "CPV",
    "Central African Republic": "CAF",
    "Comoros": "COM",
    "Congo, the Democratic Republic of the": "COD",
    "Czech Republic": "CZE",
    "Dominican Republic": "DOM",
    "Equatorial Guinea": "GNQ",
    "French Guiana": "GUF",
    "French Polynesia": "PYF",
    "Grenada": "GRD",
    "Guadeloupe": "GLP",
    "Guam": "GUM",
    "Hong Kong": "HKG",
    "Iran, Islamic Republic of": "IRN",
    "Korea, Democratic People's Republic of": "PRK",
    "Korea, Republic of": "KOR",
    "Lao People's Democratic Republic": "LAO",
    "Libyan Arab Jamahiriya": "LBY",
    "Maldives": "MDV",
    "Malta": "MLT",
    "Martinique": "MTQ",
    "Mauritius": "MUS",
    "Mayotte": "MYT",
    "Micronesia, Federated States of": "FSM",
    "Moldova, Republic of": "MDA",
    # Dissolved in October 2010, the year Piel et al. estimate for, and its ISO 3166 code was
    # withdrawn with it. Kept because the published row exists and must stay in the denominator.
    "Netherlands Antilles": "ANT",
    "Réunion": "REU",
    "Russian Federation": "RUS",
    "Saint Lucia": "LCA",
    "Saint Vincent and the Grenadines": "VCT",
    "Samoa": "WSM",
    "Sao Tome and Principe": "STP",
    "Singapore": "SGP",
    "Solomon Islands": "SLB",
    "Swaziland": "SWZ",
    "Syrian Arab Republic": "SYR",
    "Tanzania, United Republic of": "TZA",
    "Tonga": "TON",
    "Venezuela, Bolivarian Republic of": "VEN",
    "Viet Nam": "VNM",
    "Virgin Islands, U.S.": "VIR",
    "Western Sahara": "ESH",
    # --- MAP / GADM / everyday spellings of the same places ---
    "Burma": "MMR",
    "Cabo Verde": "CPV",
    "Democratic Republic of the Congo": "COD",
    "East Timor": "TLS",
    "Ivory Coast": "CIV",
    "Macedonia": "MKD",
    "Republic of the Congo": "COG",
    "St. Lucia": "LCA",
    "St. Vincent and the Grenadines": "VCT",
    "United Republic of Tanzania": "TZA",
    "United States": "USA",
}


class UnknownCountryError(ValueError):
    """A country name that no source in the join resolves to an ISO3 code.

    Raised rather than returning `None` because the alternative — a null that flows into a merge
    — removes the country from every downstream total without saying so (§12).
    """


def _normalise(name: str) -> str:
    """Fold a country name to a comparison key.

    Accents, the several Unicode dashes the Piel appendix uses (Guinea‐Bissau carries U+2010,
    not a hyphen-minus), punctuation and a leading article are all incidental to identity, and
    each of them has produced a failed join in one of the three sources this reconciles.
    """
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.lower().replace("&", " and ")
    folded = "".join(" " if unicodedata.category(char) in {"Pd", "Zs"} else char for char in folded)
    folded = "".join(char for char in folded if char.isalnum() or char == " ")
    folded = " ".join(folded.split())
    return folded.removeprefix("the ")


def feature_iso3(feature: dict) -> str:
    """The ISO3 of one Natural Earth feature, with the `-99` cases decided explicitly."""
    name = feature["properties"]["name"]
    iso3 = feature["properties"]["iso_a3"]
    if iso3 and iso3 != "-99":
        return iso3
    if name in NATURAL_EARTH_ISO3_FIXUPS:
        return NATURAL_EARTH_ISO3_FIXUPS[name]
    raise UnknownCountryError(
        f"Natural Earth feature {name!r} carries iso_a3={iso3!r} and has no entry in "
        "NATURAL_EARTH_ISO3_FIXUPS; decide what it should roll up to rather than dropping it"
    )


@lru_cache(maxsize=1)
def _iso3_index() -> dict[str, str]:
    """Normalised name → ISO3, from the committed geometry plus the alias table."""
    index = {_normalise(feature["properties"]["name"]): feature_iso3(feature)
             for feature in load_countries()}
    index.update({_normalise(name): iso3 for name, iso3 in ISO3_ALIASES.items()})
    return index


def resolve_iso3(name: str) -> str:
    """ISO 3166-1 alpha-3 for a country name, however the source spells it.

    A three-letter code is passed through, so a caller that already has ISO3 need not branch.
    """
    if isinstance(name, str) and len(name) == 3 and name.isalpha() and name.isupper():
        return name
    resolved = _iso3_index().get(_normalise(name))
    if resolved is None:
        raise UnknownCountryError(
            f"no ISO3 code for country {name!r}; add it to ISO3_ALIASES in "
            "genomeos/geo/countries.py rather than letting it drop out of the join"
        )
    return resolved


@lru_cache(maxsize=1)
def _country_paths() -> tuple:
    """Exterior rings with their holes and bounding boxes, in a deterministic order.

    The bounding box is stored so a point can be rejected with four comparisons instead of a ray
    cast — nearly every point misses nearly every country, and the same prefilter is what makes
    `basemap.land_mask` finish a global grid in hundredths of a second.

    Holes are kept and subtracted rather than ignored, which is what makes an enclave come out
    right: Maseru sits inside South Africa's exterior ring *and* inside the Lesotho-shaped hole
    in it, so ignoring holes would make the answer depend on iteration order.
    """
    import numpy as np
    from matplotlib.path import Path as MplPath

    entries = []
    for feature in load_countries():
        iso3 = feature_iso3(feature)
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        for polygon in polygons:
            if not polygon or len(polygon[0]) < 3:
                continue  # a ring with fewer than three vertices encloses no area
            exterior = np.asarray(polygon[0], dtype=float)
            holes = tuple(
                MplPath(np.asarray(ring, dtype=float)) for ring in polygon[1:] if len(ring) >= 3
            )
            entries.append(
                (
                    iso3,
                    MplPath(exterior),
                    holes,
                    exterior[:, 0].min(),
                    exterior[:, 0].max(),
                    exterior[:, 1].min(),
                    exterior[:, 1].max(),
                )
            )
    # Sorted by ISO3 so the assignment is deterministic given the geometry file (§5).
    return tuple(sorted(entries, key=lambda entry: entry[0]))


def country_at(lat, lon):
    """ISO3 of the country each (lat, lon) falls in, or `None` where none does.

    `None` is a real answer — open ocean, and Antarctic and maritime gaps in the 1:110m file —
    not a failure, so it is returned rather than raised. It is the *aggregation* step that
    refuses to proceed with unassigned cells, because that is where dropping one would silently
    understate a country.
    """
    import numpy as np

    lat_arr = np.asarray(lat, dtype=float).ravel()
    lon_arr = np.asarray(lon, dtype=float).ravel()
    if lat_arr.shape != lon_arr.shape:
        raise ValueError("lat and lon must have the same length")

    points = np.column_stack([lon_arr, lat_arr])
    out = np.full(len(points), None, dtype=object)
    assigned = np.zeros(len(points), dtype=bool)
    xs, ys = points[:, 0], points[:, 1]

    for iso3, exterior, holes, x0, x1, y0, y1 in _country_paths():
        candidate = ~assigned & (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
        if not candidate.any():
            continue
        index = np.flatnonzero(candidate)
        index = index[exterior.contains_points(points[index])]
        for hole in holes:
            if not len(index):
                break
            index = index[~hole.contains_points(points[index])]
        if not len(index):
            continue
        out[index] = iso3
        assigned[index] = True

    return out


def assign_countries(cells) -> pd.DataFrame:
    """`h3_index` → `iso3` for each cell, by the country its cell centre falls in.

    One row per input cell in input order, `iso3` null where the centre is in no country. This
    is the join #94 and #61 both need; see the module docstring for what the centre rule costs.
    """
    import h3

    cells = list(cells)
    if not cells:
        raise ValueError("assign_countries requires at least one cell")

    centres = [h3.cell_to_latlng(cell) for cell in cells]
    iso3 = country_at([c[0] for c in centres], [c[1] for c in centres])
    return pd.DataFrame({"h3_index": cells, "iso3": iso3})


def rollup_by_country(
    cells: pd.DataFrame, column: str = "post_mean", statistic: str = "mean"
) -> pd.DataFrame:
    """One statistic per country, with the unmapped fraction §10 requires alongside it.

    The aggregation itself is `surfaces.mask.aggregate_cells`, so masked cells are excluded by
    the same code that excludes them everywhere else — a second implementation here is exactly
    how a mask stops being enforced. `value` is null for a country whose cells are all masked:
    §9's no-number-rather-than-a-wrong-one, at country scale.
    """
    if "iso3" not in cells.columns:
        raise ValueError("`cells` must carry an `iso3` column; see assign_countries")
    unassigned = int(cells["iso3"].isna().sum())
    if unassigned:
        raise ValueError(
            f"{unassigned} cells have no iso3. Assign or drop them explicitly before rolling "
            "up: a cell silently discarded here understates the country it belonged to"
        )

    rows = []
    for iso3, sub in cells.groupby("iso3", sort=True):
        result = aggregate_cells(sub, column=column, statistic=statistic)
        rows.append(
            {
                "iso3": iso3,
                "value": result.value,
                "statistic": result.statistic,
                "unmapped_fraction": result.unmapped_fraction,
                "n_included": result.n_included,
                "n_cells": result.n_total,
            }
        )
    return pd.DataFrame(rows)



#: Land areas for states and territories that Natural Earth 1:110m omits entirely. It is a
#: *basemap* generalised for world-scale display, so it drops microstates — and dropping them
#: here would discard real observations: Singapore alone contributes 35,714 hemizygous males to
#: the G6PD corpus, the largest single survey in it. Published land areas in km², rounded, from
#: the CIA World Factbook / UN Statistics Division. Kept explicit and small rather than pulling
#: in a higher-resolution basemap for eleven polygons.
SUPPLEMENTARY_AREAS_KM2: dict[str, float] = {
    "BHR": 787.0,     # Bahrain
    "COK": 236.0,     # Cook Islands
    "GUM": 544.0,     # Guam
    "HKG": 1114.0,    # Hong Kong SAR
    "MUS": 2040.0,    # Mauritius
    "NIU": 262.0,     # Niue
    "SGP": 734.0,     # Singapore
    "STP": 964.0,     # Sao Tome and Principe
    "TKL": 12.0,      # Tokelau
    "TON": 747.0,     # Tonga
    "WSM": 2842.0,    # Samoa
}

#: Mean Earth radius, matching `surfaces.fit`. Defined locally so `geo` does not depend on
#: `surfaces` for a constant.
EARTH_RADIUS_KM = 6371.0088


def _ring_area_km2(ring) -> float:
    """Spherical area of one closed ring, by the standard spherical-excess line integral.

    A planar shoelace on raw degrees would understate high-latitude countries badly, and the
    whole point of this figure is to describe how little we know about where a centroid actually
    is — an understated area is the failure we are trying to avoid.
    """
    import numpy as np

    arr = np.asarray(ring, dtype=float)
    lon = np.radians(arr[:, 0])
    lat = np.radians(arr[:, 1])
    if lon[0] != lon[-1] or lat[0] != lat[-1]:
        lon = np.append(lon, lon[0])
        lat = np.append(lat, lat[0])
    total = np.sum((lon[1:] - lon[:-1]) * (2.0 + np.sin(lat[:-1]) + np.sin(lat[1:])))
    return abs(total) * EARTH_RADIUS_KM**2 / 2.0


@lru_cache(maxsize=512)
def country_area_km2(iso3: str) -> float:
    """Total land area of a country, from the committed Natural Earth geometry.

    Used where a coordinate is an administrative *centroid* rather than a place: the honest
    uncertainty radius for such a point is the scale of the unit it stands for, and that scale
    has to be computed rather than guessed. Raises rather than returning zero for an unknown
    code, per §12.
    """
    if iso3 in SUPPLEMENTARY_AREAS_KM2:
        return SUPPLEMENTARY_AREAS_KM2[iso3]
    total = 0.0
    for feature in load_countries():
        if feature_iso3(feature) != iso3:
            continue
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        for polygon in polygons:
            if polygon and len(polygon[0]) >= 3:
                total += _ring_area_km2(polygon[0])
                # Interior rings are holes, so they do not add land.
                for hole in polygon[1:]:
                    if len(hole) >= 3:
                        total -= _ring_area_km2(hole)
    if total <= 0.0:
        raise UnknownCountryError(f"no geometry for ISO3 {iso3!r}; cannot derive an area")
    return total


def country_radius_km(iso3: str) -> float:
    """Radius of a circle with the country's area — an equivalent extent, not a bounding radius."""
    import math

    return math.sqrt(country_area_km2(iso3) / math.pi)

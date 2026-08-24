"""Population geolocation registry schema (design §6, sub-project P0).

The registry is the join table that gives every population label a coordinate. Per design §2's
central finding, coordinates — not variants — are the binding constraint on the whole atlas, so
this schema is deliberately strict: `uncertainty_radius_km` has no default, `provenance` cannot
be empty, and `location_type` must state whether the coordinate is where the sample was *taken*
or where the population is *from* (design §4 — 1KG labels such as GBR/ASW are diaspora sampling
sites, not ancestral origins).

Aliases live in a separate long table rather than the nested `array<struct>` of §6: a long table
makes collisions detectable (see registry.build) and the join testable.
"""

from __future__ import annotations

import pandera.pandas as pa

LOCATION_TYPES: tuple[str, ...] = ("sampling", "ancestral", "inferred")

_SLUG = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"

POPULATIONS_SCHEMA = pa.DataFrameSchema(
    {
        "population_id": pa.Column(str, pa.Check.str_matches(_SLUG), nullable=False, unique=True),
        "lat": pa.Column(float, pa.Check.in_range(-90.0, 90.0), nullable=False),
        "lon": pa.Column(float, pa.Check.in_range(-180.0, 180.0), nullable=False),
        # No default: a coordinate without a stated extent is not usable (design §7 weights
        # each observation as a disc of this radius, not as a point).
        "uncertainty_radius_km": pa.Column(float, pa.Check.gt(0.0), nullable=False),
        "location_type": pa.Column(str, pa.Check.isin(LOCATION_TYPES), nullable=False),
        "provenance": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        # CARE-aligned notice for entries derived from indigenous-population panels (§13).
        "biocultural_notice": pa.Column(str, nullable=True, required=True),
        "registry_version": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
    },
    strict=True,
    coerce=True,
    name="populations",
)

ALIASES_SCHEMA = pa.DataFrameSchema(
    {
        "population_id": pa.Column(str, pa.Check.str_matches(_SLUG), nullable=False),
        "source": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "label": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
    },
    strict=True,
    coerce=True,
    unique=["source", "label"],
    name="population_aliases",
)

"""Georeferenced allele-count observations (design §6, §7.1, sub-project P1).

This is the "what was measured" layer of design §5 — never to be conflated with fitted
surfaces. Two properties are load-bearing:

1. **Counts, not frequencies.** We store `ac` and `an` rather than `ac/an` because a zero count
   out of 200 alleles is weak evidence, not evidence of absence; the binomial likelihood in §7
   depends on `an` being present (§7.1b).
2. **Ascertainment is mandatory.** `sampling_design`, `disease_ascertainment_excluded` and
   `cohort_id` are what make the `β_design` / `β_cohort` correction in §7.1 estimable at all.
   None of the four ascertainment biases can be modelled without them, and they cannot be
   retrofitted without re-ingesting every source — hence no defaults and no nullability.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera import extensions

SAMPLING_DESIGNS: tuple[str, ...] = (
    "population_random",
    "healthy_reference",
    "clinical_case",
    "clinical_control",
    "newborn_screening",
    "carrier_screening",
    "convenience",
)

# chr-pos-ref-alt on GRCh38 (Global Constraints).
VARIANT_ID_PATTERN = r"^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M)-\d+-[ACGT]+-[ACGT]+$"

# Registered via the extension API rather than written as inline lambdas. An anonymous
# lambda check is dropped by `schema.to_json()`, so it would be absent from the frozen
# contract — and a check whose removal never appears in a diff defeats the point of freezing
# the contract at all. Registration also makes them available to Plan 3's client.


@extensions.register_check_method(check_type="vectorized")
def ac_le_an(df):
    """Allele count may not exceed the number of alleles examined."""
    return df["ac"] <= df["an"]


@extensions.register_check_method(check_type="vectorized")
def date_lower_le_upper(df):
    """Years BP: the lower bound may not postdate the upper bound."""
    return df["date_lower"] <= df["date_upper"]


OBSERVATIONS_SCHEMA = pa.DataFrameSchema(
    {
        "variant_id": pa.Column(str, pa.Check.str_matches(VARIANT_ID_PATTERN), nullable=False),
        "rsid": pa.Column(str, nullable=True, required=True),
        "population_id": pa.Column(str, nullable=False),
        "lat": pa.Column(float, pa.Check.in_range(-90.0, 90.0), nullable=False),
        "lon": pa.Column(float, pa.Check.in_range(-180.0, 180.0), nullable=False),
        "radius_km": pa.Column(float, pa.Check.gt(0.0), nullable=False),
        "ac": pa.Column(int, pa.Check.ge(0), nullable=False),
        "an": pa.Column(int, pa.Check.gt(0), nullable=False),
        "source": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "assay": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        # Years before present; modern = 0, ancient from AADR (§7 time axis).
        "date_lower": pa.Column(int, pa.Check.ge(0), nullable=False),
        "date_upper": pa.Column(int, pa.Check.ge(0), nullable=False),
        "sampling_design": pa.Column(str, pa.Check.isin(SAMPLING_DESIGNS), nullable=False),
        # pandas' nullable "boolean" rather than numpy bool, deliberately. Under numpy bool a
        # null coerces silently to False — i.e. "this cohort was not disease-depleted", the
        # opposite of the safe reading, and invisible in the data. The extension dtype keeps it
        # as <NA> so nullable=False rejects it. A missing flag must fail (§7.1a, §12).
        # (Column-level coerce=False does not help: schema-level coerce wins in pandera 0.32.)
        "disease_ascertainment_excluded": pa.Column("boolean", nullable=False),
        "cohort_id": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "ingest_version": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
    },
    checks=[
        pa.Check.ac_le_an(error="ac must not exceed an"),
        pa.Check.date_lower_le_upper(error="date_lower must not exceed date_upper"),
    ],
    strict=True,
    coerce=True,
    name="observations",
)

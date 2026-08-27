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

# chr-pos-ref-alt on GRCh38 (Global Constraints), or an explicitly-marked phenotype composite.
#
# The `phenotype:` form exists because some layers measure a *phenotype* that many alleles
# produce, not a variant. G6PD deficiency (§8's golden test 2) is the motivating case: it is
# caused by ~200 alleles and MAP's surveys assay enzyme activity rather than genotype, so there
# is no single allele the observations could honestly be keyed by. Howes et al. modelled the
# aggregate deficiency frequency the same way, which is what makes the parity comparison
# meaningful.
#
# The prefix is deliberately ugly and deliberately not parseable as a locus: a composite must be
# impossible to mistake for a variant at a glance, in a filename, or in a join key. §6 keys
# artifacts by variant and does not yet describe this case — see the tracking issue before
# building anything that assumes every id is a locus.
#: A third form, ``hla:``, for classical HLA and KIR alleles. Unlike ``phenotype:`` these *are*
#: single alleles at a single locus — but an HLA allele is a haplotype of many linked variants
#: named by the WHO Nomenclature Committee (``DQB1*03:01``), not a ``chr-pos-ref-alt`` triple, and
#: forcing one would pick an arbitrary tag SNP and assert a coordinate the source never measured.
#: The prefix keeps them joinable to IPD-IMGT/HLA while making it obvious they are not loci.
#: Each namespace added here should be a deliberate decision, not a widening.
VARIANT_ID_PATTERN = (
    r"^(?:chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M)-\d+-[ACGT]+-[ACGT]+"
    r"|phenotype:[a-z0-9][a-z0-9-]*"
    # One namespace per immunogenetic gene family, not one `hla:` namespace for all of them.
    # AFND ships KIR, MIC and cytokine data alongside HLA, and an id that says `hla:` for
    # KIR2DL1 is a false provenance claim (#134). `cyt:` is reserved rather than used: cytokine
    # rows are genotypes and this store holds allele counts, so they are refused at ingest (#133).
    r"|(?:hla|kir|mic|cyt):[a-z0-9][a-z0-9._-]*)$"
)

# Registered via the extension API rather than written as inline lambdas. An anonymous
# lambda check is dropped by `schema.to_json()`, so it would be absent from the frozen
# contract — and a check whose removal never appears in a diff defeats the point of freezing
# the contract at all. Registration also makes them available to Plan 3's client.


@extensions.register_check_method(check_type="vectorized")
def ac_le_an(df):
    """Allele count may not exceed the number of alleles examined."""
    return df["ac"] <= df["an"]


@extensions.register_check_method(check_type="vectorized")
def carriers_le_individuals(df):
    """Carriers may not exceed the individuals examined."""
    return df["carriers"] <= df["n_individuals"]


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


#: Carrier frequency over **individuals**, not allele frequency over chromosomes (#133).
#:
#: A separate table rather than a unit flag on `OBSERVATIONS_SCHEMA`, because `ac`/`an` would then
#: mean two different things in one column and any consumer averaging across rows would be mixing
#: chromosomes with people. §4 keeps measurement types apart for the same reason it keeps
#: observations and surfaces apart: a reader must never have to infer which one they are holding.
#:
#: The source is KIR gene presence/absence. KIR genes are copy-number variable, so what a study
#: reports is the fraction of individuals carrying the gene at all — there is no diploid genotype
#: to count chromosomes from, and converting via Hardy-Weinberg would assume a model the locus
#: does not obey.
#:
#: The columns mirror `OBSERVATIONS_SCHEMA` exactly apart from the numerator and denominator, so
#: the same geospatial machinery fits it: a binomial over individuals rather than over
#: chromosomes.
CARRIER_OBSERVATIONS_SCHEMA = pa.DataFrameSchema(
    {
        "variant_id": pa.Column(str, pa.Check.str_matches(VARIANT_ID_PATTERN), nullable=False),
        "rsid": pa.Column(str, nullable=True, required=True),
        "population_id": pa.Column(str, nullable=False),
        "lat": pa.Column(float, pa.Check.in_range(-90.0, 90.0), nullable=False),
        "lon": pa.Column(float, pa.Check.in_range(-180.0, 180.0), nullable=False),
        "radius_km": pa.Column(float, pa.Check.gt(0.0), nullable=False),
        # The two columns that differ, and the reason this schema exists.
        "carriers": pa.Column(int, pa.Check.ge(0), nullable=False),
        "n_individuals": pa.Column(int, pa.Check.gt(0), nullable=False),
        "source": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "assay": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "date_lower": pa.Column(int, pa.Check.ge(0), nullable=False),
        "date_upper": pa.Column(int, pa.Check.ge(0), nullable=False),
        "sampling_design": pa.Column(str, pa.Check.isin(SAMPLING_DESIGNS), nullable=False),
        "disease_ascertainment_excluded": pa.Column("boolean", nullable=False),
        "cohort_id": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "ingest_version": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
    },
    checks=[
        pa.Check.carriers_le_individuals(error="carriers must not exceed n_individuals"),
        pa.Check.date_lower_le_upper(error="date_lower must not exceed date_upper"),
    ],
    strict=True,
    coerce=True,
    name="carrier_observations",
)

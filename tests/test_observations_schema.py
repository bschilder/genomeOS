import pandas as pd
import pandera.errors
import pytest

from genomeos.observations.schema import (
    CARRIER_OBSERVATIONS_SCHEMA,
    OBSERVATIONS_SCHEMA,
    SAMPLING_DESIGNS,
)

# Pandera reports a failed *coercion* as `SchemaErrors` and a failed *check* as `SchemaError`, and
# the two are unrelated classes — `SchemaErrors` is not a subclass. A refusal test that named only
# one of them would pass for the wrong reason, or stop failing if the rejection moved between the
# two stages. What these tests assert is that the row is refused, so they accept either.
REFUSED = (pandera.errors.SchemaError, pandera.errors.SchemaErrors)


def _row(**overrides) -> pd.DataFrame:
    row = {
        "variant_id": "chr11-5227002-T-A",
        "rsid": "rs334",
        "population_id": "hgdp-yoruba",
        "lat": 7.38,
        "lon": 3.9,
        "radius_km": 50.0,
        "ac": 12,
        "an": 200,
        "source_record_id": "map-surveys:survey-001",
        "source": "map_surveys",
        "assay": "genotype",
        "date_lower": 0,
        "date_upper": 0,
        "sampling_design": "population_random",
        "disease_ascertainment_excluded": False,
        "cohort_id": "map-hbs-ng-001",
        "ingest_version": "0.1.0",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_valid_observation_passes():
    OBSERVATIONS_SCHEMA.validate(_row())


def test_every_sampling_design_in_the_enum_is_accepted():
    for design in SAMPLING_DESIGNS:
        OBSERVATIONS_SCHEMA.validate(_row(sampling_design=design))


@pytest.mark.parametrize(
    "overrides",
    [
        {"ac": -1},                                # counts are non-negative
        {"an": 0},                                 # an must be > 0
        {"ac": 300, "an": 200},                    # ac may not exceed an
        {"sampling_design": None},                 # mandatory, no default (§7.1)
        {"sampling_design": "unknown"},            # not in enum
        {"disease_ascertainment_excluded": None},  # mandatory
        {"cohort_id": ""},                         # mandatory, non-empty
        {"source_record_id": ""},                  # provenance join key, non-empty
        {"variant_id": "11:5227002T>A"},           # must be chr-pos-ref-alt on GRCh38
        {"date_lower": -5},                        # years BP, non-negative
    ],
)
def test_invalid_observations_are_rejected(overrides):
    with pytest.raises(pandera.errors.SchemaError):
        OBSERVATIONS_SCHEMA.validate(_row(**overrides))


def test_zero_count_observation_is_valid_and_not_dropped():
    """AC=0 with AN=200 is weak evidence, not evidence of absence (design §7.1b)."""
    OBSERVATIONS_SCHEMA.validate(_row(ac=0))


# --- counts and dates are whole numbers, and coercion must not pretend otherwise (#192) ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"ac": 50.7},                        # a fraction of an allele is not a count
        {"an": 200.5},                       # nor a fraction of a chromosome examined
        {"date_lower": 3.9, "date_upper": 100},
        {"date_upper": 4.9},                 # years BP are whole years
    ],
)
def test_a_fractional_count_or_date_is_refused_rather_than_truncated(overrides):
    """§12: never silently coerce a bad value.

    Under `pa.Column(int)` these were accepted and truncated — `an=200.5` became 200 — because
    schema-level coercion runs before any check and numpy int casting truncates. Nothing
    downstream could tell the stored 200 from a measured one.
    """
    with pytest.raises(REFUSED):
        OBSERVATIONS_SCHEMA.validate(_row(**overrides))


def test_a_count_exceeding_its_denominator_cannot_truncate_into_passing():
    """The `ac_le_an` check ran on post-coercion values, so truncation manufactured conformance.

    `ac=200.9` against `an=200` is a violation of the invariant. Truncating it to 200 first made
    it satisfy `ac <= an`, so the check passed a row it exists to reject. This is the part of #192
    that loses an invariant rather than merely losing precision.
    """
    with pytest.raises(REFUSED):
        OBSERVATIONS_SCHEMA.validate(_row(ac=200.9, an=200))


@pytest.mark.parametrize("overrides", [{"ac": 12.0}, {"an": 200.0}, {"date_upper": 0.0}])
def test_an_integral_float_is_still_accepted(overrides):
    """Refusing these would be over-correcting, and would break every adapter.

    `map_surveys` computes `2 * genotyped` and `afnd_frequencies` computes `2 * n_individuals` in
    floating point. 200.0 is the same measurement as 200; only a non-integral value is a claim
    nobody made.
    """
    OBSERVATIONS_SCHEMA.validate(_row(**overrides))


def test_counts_are_still_mandatory():
    """The dtype change must not have widened nullability by the back door."""
    for column in ("ac", "an", "date_lower", "date_upper"):
        with pytest.raises(REFUSED):
            OBSERVATIONS_SCHEMA.validate(_row(**{column: None}))


def test_validated_counts_convert_to_plain_numpy_integers():
    """`surfaces.fit` and `validation.crossval` read these with `.to_numpy(dtype=...)`.

    The nullable extension dtype must not leak an object array into the likelihood, which is the
    one way this change could break a consumer far from the schema.
    """
    validated = OBSERVATIONS_SCHEMA.validate(_row())
    assert validated["an"].to_numpy(dtype=int).dtype == "int64"
    assert validated["ac"].to_numpy(dtype=float).dtype == "float64"


def _carrier_row(**overrides) -> pd.DataFrame:
    row = {
        "variant_id": "kir:2dl1",
        "rsid": None,
        "population_id": "hgdp-yoruba",
        "lat": 7.38,
        "lon": 3.9,
        "radius_km": 50.0,
        "carriers": 40,
        "n_individuals": 100,
        "source_record_id": "afnd-carriers:kir-2dl1-yoruba",
        "source": "afnd_carriers",
        "assay": "gene_presence",
        "date_lower": 0,
        "date_upper": 0,
        "sampling_design": "population_random",
        "disease_ascertainment_excluded": False,
        "cohort_id": "afnd-yoruba",
        "ingest_version": "0.1.0",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_carrier_counts_reject_fractions_too():
    """A fraction of a person is not a carrier count, and the same coercion applied here."""
    CARRIER_OBSERVATIONS_SCHEMA.validate(_carrier_row())
    for overrides in ({"carriers": 40.5}, {"n_individuals": 100.5}, {"carriers": 100.9}):
        with pytest.raises(REFUSED):
            CARRIER_OBSERVATIONS_SCHEMA.validate(_carrier_row(**overrides))

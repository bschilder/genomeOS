"""MAP HbS survey adapter tests (design §6, §8, §7.1a)."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import map_surveys

FIXTURES = Path(__file__).parent / "fixtures"
RAW_FIXTURE = FIXTURES / "map_hbs_surveys.csv"
CURATED_FIXTURE = FIXTURES / "map_hbs_curated_synthetic.csv"
FIXTURE = CURATED_FIXTURE
SUPPORT_COLUMNS = {
    "radius_km",
    "support_kind",
    "coordinate_provenance",
    "radius_provenance",
}


@pytest.fixture
def loaded():
    return map_surveys.load(FIXTURE, "0.1.0")


def _mutated_fixture(tmp_path: Path, **changes: object) -> Path:
    frame = pd.read_csv(CURATED_FIXTURE, keep_default_na=False)
    for field, value in changes.items():
        frame[field] = frame[field].astype(object)
        frame.loc[frame["id"] == 9001, field] = value
    path = tmp_path / "curated.csv"
    frame.to_csv(path, index=False)
    return path


def test_raw_area_only_export_requires_explicit_support():
    with pytest.raises(ValueError, match="explicit spatial support") as error:
        map_surveys.load(RAW_FIXTURE, "test")
    assert all(field in str(error.value) for field in SUPPORT_COLUMNS)
    assert "curated MAP CSV" in str(error.value)


def test_load_conforms_to_schema(loaded):
    obs, _ = loaded
    OBSERVATIONS_SCHEMA.validate(obs)
    assert len(obs) == 7


def test_surveys_are_population_random_and_not_disease_depleted(loaded):
    """MAP surveys are population screening surveys — the reference design for β_design (§7.1a)."""
    obs, _ = loaded
    assert (obs["sampling_design"] == "population_random").all()
    assert not obs["disease_ascertainment_excluded"].any()


def test_each_synthetic_survey_site_is_its_own_cohort(loaded):
    obs, _ = loaded
    assert obs["cohort_id"].nunique() == len(obs)


def test_all_rows_are_the_hbs_variant(loaded):
    obs, _ = loaded
    assert (obs["variant_id"] == map_surveys.HBS_VARIANT_ID).all()
    assert (obs["rsid"] == "rs334").all()


def test_source_record_ids_are_the_native_survey_ids(loaded):
    """Catches a local row number replacing the source's stable survey identity."""
    obs, _ = loaded
    assert obs["source_record_id"].is_unique
    assert "map-surveys:9001" in set(obs["source_record_id"])


def test_allele_counts_use_the_typed_denominator_not_the_approached_one(loaded):
    """ac = hbas + 2·hbss over an = 2·(hbaa + hbas + hbss).

    The denominator is the people actually typed, not the people approached. Where a survey typed
    everyone the two are identical; where it did not, dividing observed carriers by people who
    were never tested understates the frequency.
    """
    obs, _ = loaded
    partial = obs[obs["population_id"] == "map-hbs-9002"].iloc[0]
    assert partial["ac"] == 7
    assert partial["an"] == 80, "40 typed of 50 approached"


def test_radius_is_the_exact_explicit_bounding_support(loaded):
    """Changing an area label must not recalculate explicitly declared support."""
    obs, _ = loaded
    by_id = obs.set_index("source_record_id")
    assert by_id.loc["map-surveys:9001", "radius_km"] == 73.25
    assert by_id.loc["map-surveys:9006", "radius_km"] == 122.0


def test_zero_count_surveys_are_retained(loaded):
    """AC=0 is evidence of absence-so-far, not a row to drop (§7.1b)."""
    obs, _ = loaded
    assert (obs["ac"] == 0).any()


# --- refusals: every one of these was found in the real database ---


def test_screen_positive_only_surveys_are_refused_but_ordinary_partial_ones_are_not():
    """The line is *how small* the typed share is, not that it is below 100%.

    A US newborn-screening row typed 47,276 of 3,212,374 infants because only screen-positives
    were typed; that subset is enriched for carriers by construction and gives an HbS frequency
    of 0.31 for the United States. Incomplete fieldwork looks nothing like that — the real
    distribution of partial surveys has a median of 82% typed — so refusing every partial survey
    to catch this one discarded eighty-odd ordinary ones.
    """
    obs, report = map_surveys.load(FIXTURE, "0.1.0")
    assert "map-hbs-9009" not in set(obs["population_id"])
    assert report.refusals.get("screen_positives_only", 0) == 1
    assert report.partially_typed == 1, "ordinary partial surveys are kept, and counted"


def test_a_small_genotype_excess_is_a_rounded_sample_size_not_broken_data(loaded, tmp_path):
    """All four such rows in the real export exceed `sample_size` by 3-14%, which is what a
    rounded or restated sample size looks like next to exact genotype counts. The genotypes are
    the measurement, so they win and become the denominator. Only an implausible excess signals a
    genuinely inconsistent row.
    """
    obs, _ = loaded
    row = obs[obs["population_id"] == "map-hbs-9006"]
    assert len(row) == 1, "a 14% excess is kept, not refused"
    assert row.iloc[0]["an"] == 16, "denominator is the genotypes, not the sample"

    frame = pd.read_csv(FIXTURE)
    frame.loc[frame["id"] == 9006, "sample_size"] = 1.0  # genotypes now 8x the sample
    path = tmp_path / "inconsistent.csv"
    frame.to_csv(path, index=False)
    _, report = map_surveys.load(path, "0.1.0")
    assert report.refusals.get("genotypes_exceed_sample", 0) >= 1


def test_genuinely_incomplete_genotypes_are_still_refused(loaded):
    """Where hbss cannot be derived, assuming it is 0 biases frequency down where HbS is common."""
    _, report = loaded
    assert report.refusals.get("incomplete_genotypes", 0) >= 1


def test_explicit_radius_is_preserved_when_area_label_changes(tmp_path):
    frame = pd.read_csv(CURATED_FIXTURE)
    frame.loc[frame.id == 9001, "radius_km"] = 73.25
    frame.loc[frame.id == 9001, "area_type"] = "Large polygon (>100 km2)"
    path = tmp_path / "curated.csv"
    frame.to_csv(path, index=False)
    obs, _ = map_surveys.load(path, "test")
    assert obs.set_index("source_record_id").loc["map-surveys:9001", "radius_km"] == 73.25


def test_hbss_is_derived_by_subtraction_when_the_sample_is_fully_accounted_for():
    """hbaa + hbas == sample_size fixes hbss at zero arithmetically — no assumption (#89)."""
    obs, report = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=False)
    assert report.derived_hbss == 1
    assert "map-surveys:9004" in set(obs["source_record_id"])


def test_report_accounts_for_every_input_row(loaded):
    obs, report = loaded
    assert report.total == report.retained + sum(report.refusals.values())
    assert report.retained == len(obs)


def test_the_piel_subset_filter_is_off_by_default_and_available_for_parity():
    """That flag marks comparability with a published analysis, not data quality.

    The rows outside Piel et al.'s 2013 subset are ordinary surveys they happened not to use, and
    excluding them by default shrank every fitted surface for no scientific reason. Golden test 1
    turns it on because a parity comparison must be scored on the reference's own inputs.
    """
    wide, _ = map_surveys.load(FIXTURE, "0.1.0")
    narrow, narrow_report = map_surveys.load(FIXTURE, "0.1.0", piel_2013_subset_only=True)
    assert narrow_report.refusals.get("excluded_from_piel_2013", 0) == 1
    assert len(wide) == len(narrow) + 1


def test_an_invalid_genotyped_fraction_is_refused():
    with pytest.raises(ValueError, match="min_genotyped_fraction"):
        map_surveys.load(FIXTURE, "0.1.0", min_genotyped_fraction=1.5)


@pytest.mark.parametrize("field", sorted(SUPPORT_COLUMNS))
def test_each_explicit_support_column_is_required(tmp_path, field):
    frame = pd.read_csv(CURATED_FIXTURE)
    frame.drop(columns=field).to_csv(tmp_path / "curated.csv", index=False)
    with pytest.raises(ValueError, match="explicit spatial support") as error:
        map_surveys.load(tmp_path / "curated.csv", "test")
    assert field in str(error.value)


def test_duplicate_support_headers_are_rejected_before_pandas_mangles_them(tmp_path):
    with CURATED_FIXTURE.open(newline="") as source:
        rows = list(csv.reader(source))
    rows[0].append("radius_km")
    for row in rows[1:]:
        row.append("1")
    path = tmp_path / "duplicate.csv"
    with path.open("w", newline="") as destination:
        csv.writer(destination).writerows(rows)
    with pytest.raises(ValueError, match=r"duplicate.*radius_km.*explicit spatial support"):
        map_surveys.load(path, "test")


@pytest.mark.parametrize(
    "support_kind",
    ["equal_area_disc", "ancestral_bounding_disc", "", "unknown", 1],
)
def test_invalid_support_kind_is_a_hard_error(tmp_path, support_kind):
    path = _mutated_fixture(tmp_path, support_kind=support_kind)
    with pytest.raises(ValueError, match=r"MAP survey 9001:.*support_kind"):
        map_surveys.load(path, "test")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coordinate_provenance", "   "),
        ("radius_provenance", "   "),
        ("coordinate_provenance", 1),
        ("radius_provenance", 1),
    ],
)
def test_invalid_support_provenance_is_a_hard_error(tmp_path, field, value):
    if isinstance(value, int):
        frame = pd.read_csv(CURATED_FIXTURE)
        frame[field] = value
        path = tmp_path / "curated.csv"
        frame.to_csv(path, index=False)
    else:
        path = _mutated_fixture(tmp_path, **{field: value})
    with pytest.raises(ValueError, match=rf"MAP survey 9001: blank {field}"):
        map_surveys.load(path, "test")


@pytest.mark.parametrize(
    ("radius", "message"),
    [
        (0, "finite and positive"),
        (-1, "finite and positive"),
        ("NaN", "invalid radius_km"),
        ("inf", "finite and positive"),
        ("not-a-number", "invalid radius_km"),
        ("true", "invalid radius_km"),
        ("FALSE", "invalid radius_km"),
    ],
)
def test_invalid_declared_radius_is_a_hard_error(tmp_path, radius, message):
    path = _mutated_fixture(tmp_path, radius_km=radius)
    with pytest.raises(ValueError, match=rf"MAP survey 9001:.*{message}"):
        map_surveys.load(path, "test")


def test_a_bounded_area_token_cannot_rescue_invalid_support(tmp_path):
    path = _mutated_fixture(tmp_path, area_type="Point (≤ 10 km2)", radius_km=0)
    with pytest.raises(ValueError, match=r"MAP survey 9001: radius_km"):
        map_surveys.load(path, "test")


def test_support_is_not_validated_for_a_count_refused_row(tmp_path):
    frame = pd.read_csv(CURATED_FIXTURE, keep_default_na=False)
    refused = frame["id"] == 9007
    frame["radius_km"] = frame["radius_km"].astype(object)
    frame.loc[refused, ["radius_km", "support_kind", "coordinate_provenance"]] = ""
    path = tmp_path / "curated.csv"
    frame.to_csv(path, index=False)
    obs, report = map_surveys.load(path, "test")
    assert "map-surveys:9007" not in set(obs["source_record_id"])
    assert report.refusals["genotypes_exceed_sample"] == 1
    assert report.total == report.retained + sum(report.refusals.values())


def test_exact_counts_reconstructions_refusals_and_report_reconcile(loaded):
    obs, report = loaded
    by_id = obs.set_index("source_record_id")
    assert by_id.loc["map-surveys:9001", ["ac", "an"]].tolist() == [6, 50]
    assert by_id.loc["map-surveys:9002", ["ac", "an"]].tolist() == [7, 80]
    assert by_id.loc["map-surveys:9003", ["ac", "an"]].tolist() == [0, 20]
    assert by_id.loc["map-surveys:9004", ["ac", "an"]].tolist() == [1, 20]
    assert by_id.loc["map-surveys:9005", ["ac", "an"]].tolist() == [4, 20]
    assert by_id.loc["map-surveys:9006", ["ac", "an"]].tolist() == [4, 16]
    assert report.derived_hbaa == 1
    assert report.partially_typed == 1
    assert report.refusals == {
        "genotypes_exceed_sample": 1,
        "incomplete_genotypes": 1,
        "missing_coordinates": 1,
        "screen_positives_only": 1,
    }
    assert report.total == report.retained + sum(report.refusals.values())

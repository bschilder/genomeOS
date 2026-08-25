"""National burden totals (design §8, §9, §10).

These are the numbers golden test 1 is scored on, so the tests are arithmetic against
hand-computed values rather than shape checks — and the two that matter most are the ones that
would still *look* right if they were wrong: the population weighting (a centroid value would
pass a shape check) and the draw-wise summation (summing per-country medians reproduces Piel's
own 4-7% shortfall and reads as model failure, #92).
"""

import numpy as np
import pandas as pd
import pytest

from genomeos.burden.national import (
    MIN_MAPPED_POPULATION_FRACTION,
    REFUSAL_LOW_COVERAGE,
    NationalRollup,
    national_totals,
)
from genomeos.burden.propagate import (
    REFUSAL_NO_DENOMINATOR,
    REFUSAL_NO_PENETRANCE,
    REFUSAL_UNSUPPORTED,
    BurdenConfig,
)
from genomeos.geo.population import births_from_population
from genomeos.validation.hbs_parity import REQUIRED_COLUMNS, score_parity, to_parity_frame

# HbS: SS neonates are the homozygotes, AS neonates the heterozygotes (§9, fully penetrant).
SS = BurdenConfig(
    inheritance="autosomal_recessive",
    metric="affected_count",
    penetrance=1.0,
    denominator_source="worldpop-1km-unconstrained+cbr",
)
AS = BurdenConfig(inheritance="autosomal_recessive", metric="carrier_count")


def _cells(**overrides) -> pd.DataFrame:
    """Two countries, two cells each, with a tenfold population contrast inside one of them."""
    frame = pd.DataFrame(
        {
            "h3_index": ["a", "b", "c", "d"],
            "iso3": ["GHA", "GHA", "NGA", "NGA"],
            "support": ["observed", "observed", "observed", "observed"],
            "denominator": [1_000.0, 10_000.0, 5_000.0, 5_000.0],
        }
    )
    return frame.assign(**overrides)


def _draws(values, n_draws=200) -> np.ndarray:
    """`n_draws` identical draws, so the point estimate is arithmetic and not a sampling result."""
    return np.tile(np.asarray(values, dtype=float), (n_draws, 1))


# --- population weighting (§9: sum over cells, never a centroid value) ---


def test_the_total_is_births_weighted_within_the_country():
    """The dense cell dominates, which is the whole reason a centroid value is unacceptable."""
    rollup = national_totals(_cells(), _draws([0.1, 0.2, 0.1, 0.1]), SS)
    ghana = rollup.per_country.set_index("iso3").loc["GHA"]
    assert ghana["point"] == pytest.approx(1_000 * 0.1**2 + 10_000 * 0.2**2)
    assert ghana["mapped_denominator"] == pytest.approx(11_000)


def test_carriers_and_affected_use_the_hardy_weinberg_expressions():
    p = 0.1
    rollup = national_totals(_cells(), _draws([p] * 4), AS)
    nigeria = rollup.per_country.set_index("iso3").loc["NGA"]
    assert nigeria["point"] == pytest.approx(10_000 * 2 * p * (1 - p))


def test_births_from_the_population_denominator_flow_straight_in():
    """§9's denominator: cell population × the national crude birth rate."""
    population = pd.DataFrame(
        {"h3_index": ["a", "b"], "iso3": ["GHA", "GHA"], "support": ["observed"] * 2,
         "population": [100_000.0, 200_000.0]}
    )
    cells = births_from_population(population, 0.032).rename(columns={"births": "denominator"})
    rollup = national_totals(cells, _draws([0.15, 0.15]), SS)
    assert rollup.per_country["point"].iloc[0] == pytest.approx(300_000 * 0.032 * 0.15**2)


# --- draw-wise summation (#92: medians do not sum) ---


def test_the_point_estimate_is_the_median_of_the_summed_draws():
    """Two cells whose high draws never coincide: each cell's own median is zero, the country's
    is not. Summing per-cell medians — the failure mode #92 describes — would report nothing."""
    cells = _cells().iloc[:2].assign(denominator=[1.0, 1.0])
    draws = np.array([[0.5, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.5]])
    rollup = national_totals(cells, draws, SS)

    frequency = draws**2
    assert rollup.per_country["point"].iloc[0] == pytest.approx(np.median(frequency.sum(axis=1)))
    assert np.median(frequency, axis=0).sum() == 0.0


def test_the_interval_is_an_iqr_because_the_published_one_is():
    """§8 compares like for like; a 95% interval makes the overlap criterion nearly free (#92)."""
    draws = np.random.default_rng(42).uniform(0.05, 0.25, size=(500, 4))
    rollup = national_totals(_cells(), draws, SS)
    ghana = rollup.per_country.set_index("iso3").loc["GHA"]

    weights = np.array([1_000.0, 10_000.0])
    per_draw = (draws[:, :2] ** 2) @ weights
    assert ghana["iqr_lower"] == pytest.approx(np.quantile(per_draw, 0.25))
    assert ghana["iqr_upper"] == pytest.approx(np.quantile(per_draw, 0.75))
    assert rollup.quantiles == (0.25, 0.75)


def test_the_global_total_is_our_global_posterior_not_a_sum_of_national_medians():
    """§8's third criterion. Summing our medians would reproduce Piel's own shortfall (#92)."""
    draws = np.random.default_rng(0).uniform(0.02, 0.3, size=(400, 4))
    rollup = national_totals(_cells(), draws, SS)

    weights = _cells()["denominator"].to_numpy()
    per_draw = (draws**2) @ weights
    assert rollup.global_total[0] == pytest.approx(np.median(per_draw))
    assert rollup.global_total[0] != pytest.approx(rollup.per_country["point"].sum())


# --- the mask (§7, §10: excluded, and the excluded fraction returned) ---


def test_masked_cells_are_excluded_from_the_total():
    """The masked cell here holds a tenth of the country's births, so coverage survives it."""
    cells = _cells(support=["unknown", "observed", "observed", "prior_dominated"])
    rollup = national_totals(cells, _draws([0.1] * 4), SS)
    ghana = rollup.per_country.set_index("iso3").loc["GHA"]
    assert ghana["point"] == pytest.approx(10_000 * 0.1**2)
    assert ghana["n_included"] == 1


def test_coverage_is_reported_by_population_and_by_cells_because_they_disagree():
    """Half of Ghana's cells are unmapped and 91% of its people are mapped. Only the second
    number says whether the total means anything, which is why it is the one that governs."""
    cells = _cells(support=["unknown", "observed", "observed", "observed"])
    ghana = national_totals(cells, _draws([0.1] * 4), SS).per_country.set_index("iso3").loc["GHA"]
    assert ghana["unmapped_cell_fraction"] == pytest.approx(0.5)
    assert ghana["mapped_population_fraction"] == pytest.approx(10_000 / 11_000)
    assert pd.notna(ghana["point"])


def test_a_country_whose_masked_cells_hold_its_people_is_refused():
    """Same cell count, the other cell masked: 9% of the population mapped, so no number."""
    cells = _cells(support=["observed", "unknown", "observed", "observed"])
    ghana = national_totals(cells, _draws([0.1] * 4), SS).per_country.set_index("iso3").loc["GHA"]
    assert ghana["mapped_population_fraction"] == pytest.approx(1_000 / 11_000)
    assert pd.isna(ghana["point"])
    assert ghana["refusal"] == REFUSAL_LOW_COVERAGE


def test_the_partial_total_is_never_scaled_up_to_the_whole_country():
    """§4: no imputation, no assuming the mapped rate holds over the unmapped remainder. The
    emitted number is the mapped population's burden and nothing else."""
    cells = _cells(support=["unknown", "observed", "observed", "observed"])
    ghana = national_totals(cells, _draws([0.1] * 4), SS).per_country.set_index("iso3").loc["GHA"]
    assert ghana["point"] == pytest.approx(10_000 * 0.1**2)
    assert ghana["point"] != pytest.approx(11_000 * 0.1**2)


def test_the_coverage_threshold_is_named_recorded_and_overridable():
    """A rollup states the bar it was produced under; the bar itself is a constant, not a magic
    number passed at a call site."""
    cells = _cells(support=["observed", "unknown", "observed", "observed"])
    default = national_totals(cells, _draws([0.1] * 4), SS)
    assert default.min_mapped_population == MIN_MAPPED_POPULATION_FRACTION == 0.80

    relaxed = national_totals(cells, _draws([0.1] * 4), SS, min_mapped_population=0.05)
    assert relaxed.per_country.set_index("iso3").loc["GHA", "point"] == pytest.approx(
        1_000 * 0.1**2
    )


def test_the_global_total_keeps_the_cells_of_a_country_it_refused():
    """The coverage refusal is about attributing a number to a country, not about whether those
    people exist — so the global posterior still counts their cells."""
    cells = _cells(support=["observed", "unknown", "observed", "observed"])
    rollup = national_totals(cells, _draws([0.1] * 4), SS)
    weights = np.array([1_000.0, 5_000.0, 5_000.0])
    assert rollup.global_total[0] == pytest.approx((0.1**2) * weights.sum())


def test_a_country_that_is_entirely_masked_gets_no_number_and_a_reason():
    cells = _cells(support=["unknown", "prior_dominated", "observed", "observed"])
    rollup = national_totals(cells, _draws([0.1] * 4), SS)
    ghana = rollup.per_country.set_index("iso3").loc["GHA"]
    assert pd.isna(ghana["point"])
    assert ghana["refusal"] == REFUSAL_UNSUPPORTED  # the cell-level reason, not the coverage one
    assert ghana["mapped_population_fraction"] == 0.0
    assert rollup.n_estimated == 1
    assert list(rollup.refused()["iso3"]) == ["GHA"]


def test_a_cell_with_no_denominator_is_refused_rather_than_treated_as_empty():
    """§9: no population denominator, no number. Treating it as zero people would understate."""
    cells = _cells(denominator=[np.nan, 10_000.0, 5_000.0, 5_000.0])
    ghana = national_totals(cells, _draws([0.1] * 4), SS).per_country.set_index("iso3").loc["GHA"]
    assert ghana["point"] == pytest.approx(10_000 * 0.1**2)
    assert ghana["n_included"] == 1


def test_a_country_with_no_denominator_anywhere_is_refused_for_that_reason():
    cells = _cells(denominator=[np.nan, np.nan, 5_000.0, 5_000.0])
    ghana = national_totals(cells, _draws([0.1] * 4), SS).per_country.set_index("iso3").loc["GHA"]
    assert pd.isna(ghana["point"])
    assert ghana["refusal"] == REFUSAL_NO_DENOMINATOR
    assert pd.isna(ghana["mapped_population_fraction"])


def test_a_variant_with_no_penetrance_estimate_refuses_every_affected_total():
    """§9: carrier frequency still ships, affected counts do not."""
    config = BurdenConfig(inheritance="autosomal_recessive", metric="affected_count")
    rollup = national_totals(_cells(), _draws([0.1] * 4), config)
    assert set(rollup.per_country["refusal"]) == {REFUSAL_NO_PENETRANCE}
    assert rollup.global_total is None


def test_a_country_with_no_births_at_all_reports_an_undefined_share_not_full_coverage():
    cells = _cells(denominator=[0.0, 0.0, 5_000.0, 5_000.0])
    ghana = national_totals(cells, _draws([0.1] * 4), SS).per_country.set_index("iso3").loc["GHA"]
    assert ghana["point"] == 0.0  # nobody there is a real zero, not a refusal
    assert pd.isna(ghana["mapped_population_fraction"])


# --- inputs that would be wrong silently (§12) ---


def test_a_cell_with_no_country_is_a_hard_error():
    with pytest.raises(ValueError, match="no iso3"):
        national_totals(_cells(iso3=["GHA", None, "NGA", "NGA"]), _draws([0.1] * 4), SS)


def test_a_duplicated_cell_is_a_hard_error_because_it_would_be_counted_twice():
    with pytest.raises(ValueError, match="duplicate"):
        national_totals(_cells(h3_index=["a", "a", "c", "d"]), _draws([0.1] * 4), SS)


def test_a_missing_denominator_column_is_a_hard_error():
    with pytest.raises(ValueError, match="denominator"):
        national_totals(_cells().drop(columns=["denominator"]), _draws([0.1] * 4), SS)


def test_draws_must_line_up_with_cells():
    with pytest.raises(ValueError, match="cells"):
        national_totals(_cells(), _draws([0.1, 0.1]), SS)


def test_a_frequency_metric_is_refused_and_points_at_the_choropleth_rollup():
    """A national frequency is a choice of statistic (§10), not a sum."""
    config = BurdenConfig(inheritance="autosomal_recessive", metric="affected_freq", penetrance=1.0)
    with pytest.raises(ValueError, match="rollup_by_country"):
        national_totals(_cells(), _draws([0.1] * 4), config)


# --- the shape golden test 1 consumes (§8) ---

TARGETS = pd.DataFrame(
    {
        "iso3": ["GHA", "NGA", "IND"],
        "country": ["Ghana", "Nigeria", "India"],
        "ss_neonates_per_year": [200, 400, 100],
        "ss_iqr_lower": [150, 350, 50],
        "ss_iqr_upper": [250, 450, 150],
    }
)


def _rollup() -> NationalRollup:
    return national_totals(_cells(), _draws([0.2, 0.2, 0.2, 0.2]), SS)


def test_the_parity_frame_carries_exactly_what_the_scorer_requires():
    frame = to_parity_frame(_rollup().per_country, targets=TARGETS)
    assert set(REQUIRED_COLUMNS) <= set(frame.columns)
    assert set(frame["country"]) == {"Ghana", "Nigeria"}


def test_a_country_we_estimated_but_nobody_published_is_not_scored():
    """It cannot be scored, and the scorer requires one row per country. The rollup keeps it."""
    frame = to_parity_frame(_rollup().per_country, targets=TARGETS.iloc[:1])
    assert list(frame["iso3"]) == ["GHA"]
    assert set(_rollup().per_country["iso3"]) == {"GHA", "NGA"}


def test_a_refused_country_still_reaches_the_scorer_and_counts_against_us():
    """§8's denominator is every published country; a refusal must not improve the score."""
    cells = _cells(support=["unknown", "unknown", "observed", "observed"])
    frame = to_parity_frame(national_totals(cells, _draws([0.2] * 4), SS).per_country, TARGETS)
    result = score_parity(frame, metric="ss", targets=TARGETS)
    assert result.n_published == 3  # India was never estimated, Ghana was refused
    assert result.n_estimated == 1
    assert result.point_inside_fraction <= 1 / 3


def test_the_rollup_scores_end_to_end_against_published_numbers():
    """440 SS in Ghana and 400 in Nigeria against targets of 200 and 400: one inside, one not."""
    frame = to_parity_frame(_rollup().per_country, targets=TARGETS)
    result = score_parity(frame, metric="ss", targets=TARGETS)
    assert result.n_estimated == 2
    assert result.point_inside_fraction == pytest.approx(1 / 3)
    assert not result.passed


def test_the_parity_frame_needs_iso3_on_both_sides():
    with pytest.raises(ValueError, match="iso3"):
        to_parity_frame(_rollup().per_country, targets=TARGETS.drop(columns=["iso3"]))
    with pytest.raises(ValueError, match="iso3"):
        to_parity_frame(_rollup().per_country.drop(columns=["iso3"]), targets=TARGETS)


def test_the_top_and_bottom_table_carries_coverage_beside_every_estimate():
    """A top-ten country at 55% mapped population is a different claim from one at 99%, and the
    table has to make that visible without a second lookup."""
    frame = to_parity_frame(_rollup().per_country, targets=TARGETS)
    table = score_parity(frame, metric="ss", targets=TARGETS).top_bottom(n=1)

    assert list(table["iso3"]) == ["GHA", "NGA"]  # sorted by our point estimate, largest first
    assert list(table["point"]) == sorted(table["point"], reverse=True)
    for column in ("country", "iqr_lower", "published_point", "mapped_population_fraction"):
        assert column in table.columns
    assert (table["mapped_population_fraction"] == 1.0).all()


def test_the_summary_line_states_coverage_and_the_global_total():
    text = str(_rollup())
    assert "2 of 2 countries estimated" in text
    assert "affected_count" in text
    assert "refusing below 80%" in text

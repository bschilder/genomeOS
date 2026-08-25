"""Golden test 1 scoring (design §8).

The scorer decides whether v1 is done, so it is tested for being *pessimistic* in the right
places as much as for arithmetic: a scorer that flatters the pipeline is worse than none.
"""

import pandas as pd
import pytest

from genomeos.reference.piel2013 import GLOBAL_SS_NEONATES
from genomeos.validation.hbs_parity import ParityCriteria, score_parity

TARGETS = pd.DataFrame(
    {
        "country": ["Aland", "Borduria", "Carpathia", "Dorset", "Elbonia"],
        "ss_neonates_per_year": [1000, 2000, 3000, 4000, 5000],
        "ss_iqr_lower": [900, 1800, 2700, 3600, 4500],
        "ss_iqr_upper": [1100, 2200, 3300, 4400, 5500],
    }
)

GLOBAL_OK = (GLOBAL_SS_NEONATES[0], GLOBAL_SS_NEONATES[1], GLOBAL_SS_NEONATES[2])


def _ours(points, spread=0.05, countries=None) -> pd.DataFrame:
    countries = countries or list(TARGETS["country"])
    return pd.DataFrame(
        {
            "country": countries,
            "point": points,
            "iqr_lower": [p * (1 - spread) for p in points],
            "iqr_upper": [p * (1 + spread) for p in points],
        }
    )


def test_exact_agreement_passes_all_three_criteria():
    result = score_parity(
        _ours([1000, 2000, 3000, 4000, 5000]),
        global_estimate=GLOBAL_OK,
        targets=TARGETS,
    )
    assert result.point_inside_fraction == 1.0
    assert result.interval_overlap_fraction == 1.0
    assert result.global_within_published
    assert result.passed


def test_a_systematic_overestimate_fails_the_point_criterion():
    result = score_parity(
        _ours([3000, 6000, 9000, 12000, 15000]), global_estimate=GLOBAL_OK, targets=TARGETS
    )
    assert result.point_inside_fraction == 0.0
    assert not result.passed


def test_countries_we_could_not_estimate_count_against_us():
    """Otherwise the score improves as coverage shrinks: refusing to answer would look accurate."""
    result = score_parity(
        _ours([1000, 2000], countries=["Aland", "Borduria"]),
        global_estimate=GLOBAL_OK,
        targets=TARGETS,
    )
    assert result.n_published == 5
    assert result.n_estimated == 2
    assert result.point_inside_fraction == pytest.approx(0.4)
    assert not result.passed


def test_wide_intervals_can_overlap_while_points_still_miss():
    """The two criteria are independent on purpose; §8 requires both."""
    result = score_parity(
        _ours([1500, 3000, 4500, 6000, 7500], spread=0.9),
        global_estimate=GLOBAL_OK,
        targets=TARGETS,
    )
    assert result.interval_overlap_fraction == 1.0
    assert result.point_inside_fraction == 0.0
    assert not result.passed


def test_a_missing_global_estimate_fails_rather_than_skips():
    """An unmeasured criterion is not a met one."""
    result = score_parity(_ours([1000, 2000, 3000, 4000, 5000]), targets=TARGETS)
    assert result.point_criterion_met and result.overlap_criterion_met
    assert not result.global_within_published
    assert not result.passed


def test_a_global_total_outside_the_published_iqr_fails():
    result = score_parity(
        _ours([1000, 2000, 3000, 4000, 5000]),
        global_estimate=(GLOBAL_SS_NEONATES[2] * 2, 0, 0),
        targets=TARGETS,
    )
    assert not result.global_within_published


def test_thresholds_are_the_ones_section_8_states():
    criteria = ParityCriteria()
    assert criteria.point_inside_interval_min == 0.80
    assert criteria.interval_overlap_min == 0.95


def test_failures_are_diagnosable_by_published_burden():
    """A bare pass/fail is not actionable; the biggest misses must be findable."""
    result = score_parity(
        _ours([1000, 2000, 3000, 4000, 50000]), global_estimate=GLOBAL_OK, targets=TARGETS
    )
    worst = result.worst_countries()
    assert list(worst["country"]) == ["Elbonia"]
    assert worst.iloc[0]["published_point"] == 5000


def test_borderline_values_on_the_interval_edge_count_as_inside():
    result = score_parity(_ours([900, 1800, 2700, 3600, 4500], spread=0.0), targets=TARGETS)
    assert result.point_inside_fraction == 1.0


def test_duplicate_countries_are_refused():
    duplicated = pd.concat([_ours([1000] * 5), _ours([1000] * 5)])
    with pytest.raises(ValueError, match="one row per country"):
        score_parity(duplicated, targets=TARGETS)


def test_missing_columns_are_refused():
    with pytest.raises(ValueError, match="missing required columns"):
        score_parity(pd.DataFrame({"country": ["Aland"]}), targets=TARGETS)


def test_unknown_metric_is_refused():
    with pytest.raises(ValueError, match="metric"):
        score_parity(_ours([1000] * 5), metric="carriers", targets=TARGETS)


def test_scores_against_the_real_published_targets_by_default():
    """Smoke test on the committed Piel table rather than the synthetic fixture."""
    result = score_parity(
        pd.DataFrame(
            {"country": ["Nigeria"], "point": [91_011], "iqr_lower": [80_000], "iqr_upper": [100_000]}
        )
    )
    assert result.n_published == 191
    assert result.n_estimated == 1

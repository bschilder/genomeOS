"""Burden engine tests (design §9, §12)."""

import numpy as np
import pandas as pd
import pytest

from genomeos.burden.expressions import affected_frequency, carrier_frequency
from genomeos.burden.propagate import (
    REFUSAL_NO_DENOMINATOR,
    REFUSAL_NO_PENETRANCE,
    REFUSAL_UNSUPPORTED,
    BurdenConfig,
    compute_burden,
)

# --- expressions: hand-computable, no model (§9) ---


def test_recessive_carrier_frequency_is_hardy_weinberg():
    assert carrier_frequency(np.array([0.1]), "autosomal_recessive")[0] == pytest.approx(0.18)


def test_recessive_affected_frequency_is_p_squared_at_full_penetrance():
    got = affected_frequency(np.array([0.1]), "autosomal_recessive", penetrance=1.0)
    assert got[0] == pytest.approx(0.01)


def test_inbreeding_raises_affected_and_lowers_carriers():
    p = np.array([0.1])
    assert carrier_frequency(p, "autosomal_recessive", inbreeding=0.05)[0] == pytest.approx(0.171)
    got = affected_frequency(p, "autosomal_recessive", penetrance=1.0, inbreeding=0.05)
    assert got[0] == pytest.approx(0.01 + 0.05 * 0.1 * 0.9)


def test_dominant_affected_frequency_follows_one_minus_q_squared():
    got = affected_frequency(np.array([0.1]), "autosomal_dominant", penetrance=1.0)
    assert got[0] == pytest.approx(1.0 - 0.9**2)


def test_dominant_has_no_carrier_concept():
    """A heterozygote is a case, not a carrier; returning a number would invite misreading."""
    assert carrier_frequency(np.array([0.1]), "autosomal_dominant")[0] == 0.0


def test_x_linked_uses_the_cell_sex_ratio():
    p = np.array([0.1])
    balanced = affected_frequency(p, "x_linked_recessive", penetrance=1.0, female_fraction=0.5)
    male_heavy = affected_frequency(p, "x_linked_recessive", penetrance=1.0, female_fraction=0.1)
    assert male_heavy[0] > balanced[0], "hemizygous males manifest at p, females at p^2"
    assert balanced[0] == pytest.approx(0.5 * 0.1 + 0.5 * 0.01)


def test_penetrance_scales_affected_frequency():
    p = np.array([0.2])
    full = affected_frequency(p, "autosomal_recessive", penetrance=1.0)
    half = affected_frequency(p, "autosomal_recessive", penetrance=0.5)
    assert half[0] == pytest.approx(full[0] * 0.5)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"p": np.array([1.5])},
        {"p": np.array([-0.1])},
        {"inbreeding": 1.5},
    ],
)
def test_out_of_range_inputs_are_refused(kwargs):
    p = kwargs.pop("p", np.array([0.1]))
    with pytest.raises(ValueError):
        carrier_frequency(p, "autosomal_recessive", **kwargs)


def test_unknown_inheritance_is_refused():
    with pytest.raises(ValueError, match="inheritance"):
        carrier_frequency(np.array([0.1]), "mitochondrial")


# --- propagation (§9) ---


def _cells(support=("observed", "interpolated"), denominator=(1000.0, 1000.0)) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "h3_index": [f"cell-{i}" for i in range(len(support))],
            "support": list(support),
            "denominator": list(denominator),
        }
    )


def _draws(n_draws=800, values=(0.1, 0.2)) -> np.ndarray:
    rng = np.random.default_rng(0)
    return np.clip(rng.normal(values, 0.02, size=(n_draws, len(values))), 0.0, 1.0)


def test_propagation_yields_an_interval_that_brackets_the_mean():
    out = compute_burden(
        _draws(), _cells(), BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq")
    )
    assert (out["q025"] < out["mean"]).all()
    assert (out["mean"] < out["q975"]).all()


def test_draw_based_propagation_differs_from_plugging_in_the_mean():
    """§9: the transformations are nonlinear, so analytic propagation is not used."""
    draws = _draws(values=(0.5,))
    cells = _cells(support=("observed",), denominator=(1000.0,))
    out = compute_burden(
        draws, cells, BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq")
    )
    naive = carrier_frequency(np.array([draws.mean()]), "autosomal_recessive")[0]
    assert out["mean"].iloc[0] != pytest.approx(naive, abs=1e-9)


def test_propagation_is_deterministic_given_the_seed():
    draws, cells = _draws(), _cells()
    config = BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq")
    a = compute_burden(draws, cells, config)["mean"].to_numpy()
    b = compute_burden(draws, cells, config)["mean"].to_numpy()
    assert np.array_equal(a, b)


def test_counts_scale_with_the_denominator():
    out = compute_burden(
        _draws(),
        _cells(denominator=(1000.0, 2000.0)),
        BurdenConfig(
            inheritance="autosomal_recessive", metric="carrier_count", denominator_source="worldpop"
        ),
    )
    assert out["mean"].iloc[1] > out["mean"].iloc[0]


def test_hwe_assumption_is_recorded_per_row_not_buried():
    out = compute_burden(
        _draws(), _cells(), BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq")
    )
    assert out["hwe_assumed"].all()


# --- refusals (§9, §12) — each is a test, not a convention ---


@pytest.mark.parametrize("masked", ["unknown", "prior_dominated"])
def test_masked_cells_are_refused_not_estimated(masked):
    out = compute_burden(
        _draws(),
        _cells(support=("observed", masked)),
        BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq"),
    )
    assert out["refusal"].iloc[1] == REFUSAL_UNSUPPORTED
    assert pd.isna(out["mean"].iloc[1])
    assert not pd.isna(out["mean"].iloc[0]), "the supported cell must still be computed"


def test_missing_penetrance_refuses_affected_but_not_carriers():
    """§9: carrier layers ship; affected-count layers do not."""
    draws, cells = _draws(), _cells()
    affected = compute_burden(
        draws, cells, BurdenConfig(inheritance="autosomal_recessive", metric="affected_freq")
    )
    assert (affected["refusal"] == REFUSAL_NO_PENETRANCE).all()
    assert affected["mean"].isna().all()

    carriers = compute_burden(
        draws, cells, BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq")
    )
    assert carriers["refusal"].isna().all()
    assert carriers["mean"].notna().all()


def test_missing_denominator_refuses_counts_but_not_frequencies():
    draws = _draws()
    cells = _cells(denominator=(1000.0, np.nan))
    counts = compute_burden(
        draws, cells, BurdenConfig(inheritance="autosomal_recessive", metric="carrier_count")
    )
    assert counts["refusal"].iloc[1] == REFUSAL_NO_DENOMINATOR
    assert pd.isna(counts["mean"].iloc[1])

    freqs = compute_burden(
        draws, cells, BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq")
    )
    assert freqs["mean"].notna().all(), "a frequency needs no denominator"


def test_a_refused_cell_is_returned_with_a_reason_rather_than_dropped():
    """Callers must be able to tell 'we will not say' from 'this cell does not exist'."""
    out = compute_burden(
        _draws(),
        _cells(support=("unknown", "unknown")),
        BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq"),
    )
    assert len(out) == 2
    assert out["mean"].isna().all()
    assert (out["refusal"] == REFUSAL_UNSUPPORTED).all()


def test_mismatched_draw_and_cell_counts_are_refused():
    with pytest.raises(ValueError, match="cells"):
        compute_burden(
            _draws(values=(0.1, 0.2, 0.3)),
            _cells(),
            BurdenConfig(inheritance="autosomal_recessive", metric="carrier_freq"),
        )


def test_unknown_metric_is_refused():
    with pytest.raises(ValueError, match="metric"):
        BurdenConfig(inheritance="autosomal_recessive", metric="dalys")

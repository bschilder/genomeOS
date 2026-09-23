"""Reference-year population alignment for burden comparisons (design §8, §9)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from genomeos.burden.denominators import align_country_populations


def _cells() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "h3_index": ["a", "b", "c", "d", "e"],
            "iso3": ["GHA", "GHA", "NGA", "NGA", "NGA"],
            "population": [100.0, 300.0, 0.0, 400.0, 600.0],
            "support": ["observed", "interpolated", "unknown", "observed", "interpolated"],
        }
    )


def _targets() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "iso3": ["GHA", "NGA", "MLT"],
            "target_population": [800.0, 500.0, 420.0],
        }
    )


def _align(cells: pd.DataFrame | None = None, targets: pd.DataFrame | None = None):
    return align_country_populations(
        _cells() if cells is None else cells,
        _targets() if targets is None else targets,
        weight_source="WorldPop 2020",
        target_source="Piel et al. 2013 Web Table 1",
        target_year=2010,
    )


def test_country_weights_are_rescaled_to_exact_reference_totals() -> None:
    result = _align()
    totals = result.cells.groupby("iso3")["population"].sum()

    assert totals.to_dict() == pytest.approx({"GHA": 800.0, "NGA": 500.0})
    assert result.scales.set_index("iso3")["scale_factor"].to_dict() == pytest.approx(
        {"GHA": 2.0, "NGA": 0.5}
    )
    assert result.unused_target_iso3 == ("MLT",)


def test_zero_population_cells_are_preserved_when_the_country_has_weight() -> None:
    result = _align()
    zero = result.cells.set_index("h3_index").loc["c"]

    assert zero["population_weight"] == 0.0
    assert zero["population"] == 0.0
    assert len(result.cells) == len(_cells())


def test_alignment_preserves_other_columns_and_records_provenance() -> None:
    result = _align()

    assert result.cells["h3_index"].tolist() == _cells()["h3_index"].tolist()
    assert result.cells["support"].tolist() == _cells()["support"].tolist()
    assert (result.cells["population_weight_source"] == "WorldPop 2020").all()
    assert (result.cells["population_target_source"] == "Piel et al. 2013 Web Table 1").all()
    assert (result.cells["population_target_year"] == 2010).all()


def test_alignment_is_deterministic_under_cell_and_target_reordering() -> None:
    first = _align()
    second = _align(
        _cells().sample(frac=1.0, random_state=42).reset_index(drop=True),
        _targets().iloc[::-1].reset_index(drop=True),
    )

    columns = ["h3_index", "population_weight", "population", "population_scale_factor"]
    pd.testing.assert_frame_equal(
        first.cells[columns].sort_values("h3_index").reset_index(drop=True),
        second.cells[columns].sort_values("h3_index").reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(first.scales, second.scales)


@pytest.mark.parametrize(
    ("cells", "targets", "match"),
    [
        (_cells().assign(iso3=["GHA", "GHA", "NGA", "NGA", "CHN"]), _targets(), "target"),
        (_cells(), pd.concat([_targets(), _targets().iloc[[0]]]), "duplicate"),
        (_cells().assign(iso3=["GHA", None, "NGA", "NGA", "NGA"]), _targets(), "iso3"),
        (_cells().assign(h3_index=["a", "a", "c", "d", "e"]), _targets(), "duplicate"),
        (_cells().assign(population=[100.0, np.nan, 0.0, 400.0, 600.0]), _targets(), "finite"),
        (_cells().assign(population=[100.0, -1.0, 0.0, 400.0, 600.0]), _targets(), "negative"),
        (_cells().assign(population=[True, 300.0, 0.0, 400.0, 600.0]), _targets(), "Boolean"),
        (
            _cells().assign(population=[100.0, 300.0, 0.0, 0.0, 0.0]),
            _targets(),
            "positive spatial weight",
        ),
        (_cells(), _targets().assign(target_population=[800.0, 0.0, 420.0]), "positive"),
        (_cells(), _targets().assign(target_population=[800.0, np.nan, 420.0]), "finite"),
        (_cells(), _targets().assign(target_population=[800.0, True, 420.0]), "Boolean"),
    ],
)
def test_invalid_or_unalignable_inputs_are_hard_errors(cells, targets, match) -> None:
    with pytest.raises(ValueError, match=match):
        _align(cells, targets)


@pytest.mark.parametrize(
    ("keyword", "value", "match"),
    [
        ("weight_source", "", "weight_source"),
        ("target_source", " ", "target_source"),
        ("target_year", 0, "target_year"),
        ("target_year", True, "target_year"),
    ],
)
def test_alignment_provenance_is_required(keyword, value, match) -> None:
    arguments = {
        "weight_source": "WorldPop 2020",
        "target_source": "Piel et al. 2013 Web Table 1",
        "target_year": 2010,
    }
    arguments[keyword] = value
    with pytest.raises(ValueError, match=match):
        align_country_populations(_cells(), _targets(), **arguments)

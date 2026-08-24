import h3
import pytest

from genomeos.geo.h3util import (
    GLOBAL_RESOLUTION,
    RESOLUTION_LADDER,
    cell_for,
    cells_within_km,
    parent_of,
)


def test_ladder_is_ascending_and_starts_at_the_global_resolution():
    assert RESOLUTION_LADDER == tuple(sorted(RESOLUTION_LADDER))
    assert RESOLUTION_LADDER[0] == GLOBAL_RESOLUTION
    assert RESOLUTION_LADDER[-1] == 6, "res 6 is the finest v1 emits (design §6)"


def test_cell_for_is_deterministic_and_round_trips_to_the_same_cell():
    a = cell_for(7.38, 3.9, 4)
    assert a == cell_for(7.38, 3.9, 4)
    assert h3.get_resolution(a) == 4


def test_parent_of_walks_up_the_ladder():
    fine = cell_for(7.38, 3.9, 6)
    assert parent_of(fine, 4) == cell_for(7.38, 3.9, 4)


def test_parent_of_rejects_a_finer_target_resolution():
    coarse = cell_for(7.38, 3.9, 4)
    with pytest.raises(ValueError):
        parent_of(coarse, 6)


def test_cells_within_km_covers_the_centre_and_grows_with_radius():
    near = cells_within_km(7.38, 3.9, 30.0, 4)
    far = cells_within_km(7.38, 3.9, 300.0, 4)
    assert cell_for(7.38, 3.9, 4) in near
    assert len(far) > len(near)


def test_cells_within_km_rejects_a_non_positive_radius():
    with pytest.raises(ValueError):
        cells_within_km(7.38, 3.9, 0.0, 4)

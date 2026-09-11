"""Deterministic reference-window geometry controls (design §§4–8, 12; #254)."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from genomeos.validation.reference_window_types import (
    GenomicInterval,
    ReferenceWindow,
    StartRun,
    WindowConfig,
)
from genomeos.validation.reference_windows import (
    DRAW_METHOD,
    MAX_TRANSFER_BYTES,
    SEED,
    eligible_start_runs,
    select_reference_windows,
    start_at_rank,
)


def _config() -> WindowConfig:
    return WindowConfig(
        schema_version="reference_window_config_v1",
        width=10_000,
        strata=3,
        seed=SEED,
        numpy_version=np.__version__,
        bit_generator="PCG64",
        draw_method=DRAW_METHOD,
        exclusion=GenomicInterval("chr22", 20_000_000, 20_010_000),
        max_transfer_bytes=MAX_TRANSFER_BYTES,
        header_prefix_bytes=1_048_576,
        eof_bytes=28,
    )


def test_forbidden_overlap_starts_match_exhaustive_frame():
    runs = eligible_start_runs(0, 12, 3, ((5, 7),))
    expected = [s for s in range(10) if s + 3 <= 5 or s >= 7]
    assert runs == (StartRun(0, 2), StartRun(7, 9))
    assert [start_at_rank(runs, k) for k in range(6)] == expected


def test_touching_exclusion_is_allowed():
    runs = eligible_start_runs(0, 12, 3, ((5, 7),))
    assert start_at_rank(runs, 2) == 2  # [2,5)
    assert start_at_rank(runs, 3) == 7  # [7,10)


def test_seeded_rank_oracle():
    rng = np.random.Generator(np.random.PCG64(42))
    # Independent recorded oracle under NumPy 2.4.6, eight eligible starts.
    assert [int(rng.integers(0, 8, dtype=np.int64)) for _ in range(3)] == [0, 6, 5]
    runs = (StartRun(0, 2), StartRun(7, 11))
    assert [start_at_rank(runs, k) for k in (0, 6, 5)] == [0, 10, 9]


def test_eligible_runs_match_exhaustive_enumeration():
    for width in range(1, 6):
        for frame_length in range(width, 16):
            candidates = range(frame_length - width + 1)
            exclusions = [()] + [
                ((left, right),)
                for left in range(frame_length)
                for right in range(left + 1, frame_length + 1)
            ]
            for excluded in exclusions:
                expected = [
                    start
                    for start in candidates
                    if all(start + width <= left or start >= right for left, right in excluded)
                ]
                if expected:
                    runs = eligible_start_runs(0, frame_length, width, excluded)
                    actual = list(
                        itertools.chain.from_iterable(range(run.first, run.last + 1) for run in runs)
                    )
                    assert actual == expected
                else:
                    with pytest.raises(ValueError, match="eligible"):
                        eligible_start_runs(0, frame_length, width, excluded)


@pytest.mark.parametrize(
    ("runs", "rank"),
    [
        ((StartRun(0, 2),), -1),
        ((StartRun(0, 2),), 3),
        ((StartRun(0, 2),), True),
        ((StartRun(0, 2),), 1.0),
        ((), 0),
    ],
)
def test_start_at_rank_rejects_invalid_rank_or_runs(runs, rank):
    with pytest.raises((TypeError, ValueError)):
        start_at_rank(runs, rank)


def test_start_at_rank_validates_all_runs_before_returning():
    with pytest.raises(ValueError, match="sorted"):
        start_at_rank((StartRun(0, 0), StartRun(0, 1)), 0)


def test_reference_window_constructor_rejects_nonfixed_width():
    with pytest.raises(ValueError, match="width"):
        ReferenceWindow(
            window_id="chr1-s1",
            chrom="chr1",
            stratum=1,
            stratum_start0=0,
            stratum_end0=20_000,
            start0=0,
            end0=9_999,
            eligible_runs=(StartRun(0, 10_000),),
            eligible_count=10_001,
            rank=0,
        )


def test_reference_window_constructor_rejects_eligible_runs_outside_stratum():
    with pytest.raises(ValueError, match="eligible run"):
        ReferenceWindow(
            window_id="chr1-s1",
            chrom="chr1",
            stratum=1,
            stratum_start0=100,
            stratum_end0=20_100,
            start0=100,
            end0=10_100,
            eligible_runs=(StartRun(0, 10_100),),
            eligible_count=10_101,
            rank=100,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        (-1, 12, 3, ()),
        (0, 12, 0, ()),
        (0, 2, 3, ()),
        (False, 12, 3, ()),
        (0, 12.5, 3, ()),
        (0, 12, 3, ((7, 5),)),
    ],
)
def test_eligible_start_runs_rejects_invalid_geometry(arguments):
    with pytest.raises((TypeError, ValueError)):
        eligible_start_runs(*arguments)


def test_full_manifest_has_fixed_natural_geometry_and_is_order_independent():
    lengths = tuple((f"chr{chrom}", 30_060_000 + chrom * 30_000) for chrom in range(1, 23))
    windows = select_reference_windows(lengths, _config())
    shuffled = tuple(reversed(lengths))

    assert select_reference_windows(shuffled, _config()) == windows
    assert len(windows) == 66
    assert [window.window_id for window in windows] == [
        f"chr{chrom}-s{stratum}" for chrom in range(1, 23) for stratum in range(1, 4)
    ]
    lengths_by_chrom = dict(lengths)
    for window in windows:
        index = int(window.chrom[3:])
        length = lengths_by_chrom[window.chrom]
        assert window.stratum_start0 == length * (window.stratum - 1) // 3
        assert window.stratum_end0 == length * window.stratum // 3
        assert window.end0 - window.start0 == 10_000
        assert window.eligible_count == sum(run.last - run.first + 1 for run in window.eligible_runs)
        assert window.start0 == start_at_rank(window.eligible_runs, window.rank)
        if index == 22:
            assert window.end0 <= 20_000_000 or window.start0 >= 20_010_000


def test_full_selection_matches_independently_recorded_literal_oracle():
    lengths = tuple((f"chr{chrom}", 30_060_000 + chrom * 30_000) for chrom in range(1, 23))
    windows = select_reference_windows(lengths, _config())
    # Recorded from an independent direct arithmetic implementation of this synthetic frame.
    expected_starts = (
        894294,
        17785040,
        26618807,
        4401951,
        14383143,
        28691737,
        862894,
        17051575,
        22122754,
        946482,
        15351114,
        29925005,
        7401669,
        17727066,
        27357822,
        7915668,
        15248192,
        21450104,
        8464662,
        14629890,
        25223547,
        3741352,
        11941926,
        29551059,
        7893832,
        16613038,
        24284385,
        8318120,
        15634288,
        24722917,
        4558651,
        12429656,
        21192415,
        5617944,
        19134324,
        20926468,
        8703074,
        18542180,
        23106343,
        6411394,
        11837075,
        28014591,
        7117314,
        13771984,
        21030067,
        9871999,
        14712642,
        29443042,
        6901216,
        18113944,
        28115777,
        1983368,
        13908202,
        25155887,
        5077474,
        10656798,
        25995009,
        1575295,
        17809868,
        27413930,
        9428235,
        17841469,
        24207088,
        9897625,
        14434782,
        23813193,
    )
    assert tuple(window.start0 for window in windows) == expected_starts


@pytest.mark.parametrize(
    "lengths",
    [
        tuple((f"chr{chrom}", 30_000) for chrom in range(1, 22)),
        tuple((f"chr{chrom}", 30_000) for chrom in range(1, 23)) + (("chr22", 30_000),),
        tuple((f"chr{chrom}", 30_000) for chrom in range(1, 23)) + (("chrX", 30_000),),
        tuple((f"chr{chrom}", 30_000 if chrom != 22 else 2**29) for chrom in range(1, 23)),
    ],
)
def test_full_manifest_rejects_invalid_contig_set(lengths):
    with pytest.raises(ValueError):
        select_reference_windows(lengths, _config())

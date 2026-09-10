"""Constructed B0H summary evidence; no sampler execution (design §§7–8,12)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pandas as pd
import pytest

from genomeos.validation.heterogeneity_simulation_types import (
    HeldoutTarget,
    SbcCaseId,
    generation_id,
    simulation_reference_count,
)
from genomeos.validation.heterogeneity_summary_types import (
    ParameterPosteriorSummary,
    predictive_summary_rows,
)


def ordinary_target():
    case = SbcCaseId(0, 0, 0, 0)
    row = simulation_reference_count(
        generation_id(case), "heldout", "fresh_population", 2, 20
    )
    return HeldoutTarget("fresh_population", row, .5, None, None, None, None)


def literal_frame():
    return pd.DataFrame({
        "log_score": [-np.inf],
        "absolute_error": [.4],
        "squared_error": [.16],
        "coverage_50": [False],
        "interval_width_50": [.5],
        "coverage_80": [True],
        "interval_width_80": [.8],
        "coverage_95": [True],
        "interval_width_95": [1.],
        "randomized_pit": [.1],
    })


def test_literal_parameter_interval_and_error_evidence():
    item = ParameterPosteriorSummary(
        "mean", .25, .5, (.1, .2, .25, .5, .75, .8, .9), 2000
    )
    assert item.absolute_error == .25
    assert item.squared_error == .0625
    assert item.coverage == (True, True, True)
    assert item.interval_width == pytest.approx((.5, .6, .8), rel=0, abs=2e-15)
    with pytest.raises(FrozenInstanceError):
        item.estimate = .25
    for changes in (
        {"parameter": "latent_frequency"}, {"draw_count": True},
        {"truth": np.nan}, {"estimate": 0.}, {"quantiles": (.2,)},
        {"quantiles": [.1, .2, .25, .5, .75, .8, .9]},
        {"quantiles": (.1, .2, .75, .5, .25, .8, .9)},
    ):
        with pytest.raises(ValueError):
            replace(item, **changes)


def test_negative_infinite_log_score_is_retained():
    target = ordinary_target()
    rows = predictive_summary_rows(literal_frame(), targets=(target,))
    assert rows[0].target == target
    assert rows[0].log_score == -np.inf
    assert rows[0].coverage == (False, True, True)
    assert rows[0].interval_width == (.5, .8, 1.)
    assert rows[0].randomized_pit == .1


@pytest.mark.parametrize("field,value", [
    ("log_score", np.nan), ("log_score", np.inf), ("log_score", .01),
    ("absolute_error", np.inf), ("squared_error", -.1),
    ("interval_width_80", 1.1), ("randomized_pit", np.nan),
    ("randomized_pit", 1.1),
])
def test_nonfinite_or_out_of_domain_frame_is_a_defect(field, value):
    frame = literal_frame()
    frame[field] = [value]
    with pytest.raises(ValueError):
        predictive_summary_rows(frame, targets=(ordinary_target(),))


def test_malformed_frames_are_not_coerced():
    frame = literal_frame()
    malformed = (
        frame.to_dict(), frame.iloc[:0], frame.assign(extra=0),
        frame.rename(index={0: "row0"}),
        frame.drop(columns="log_score"), frame.loc[:, frame.columns[::-1]],
        frame.astype({"absolute_error": "object"}),
        frame.astype({"squared_error": "float32"}),
        frame.astype({"randomized_pit": "complex128"}),
        frame.assign(coverage_50=1), frame.assign(absolute_error=True),
        frame.assign(coverage_50=True, coverage_80=False),
        frame.assign(interval_width_50=.9),
        pd.concat([frame, frame]),
    )
    for bad in malformed:
        with pytest.raises(ValueError):
            predictive_summary_rows(bad, targets=(ordinary_target(),))


def test_output_rows_retain_no_mutable_dataframe_reference():
    frame = literal_frame()
    rows = predictive_summary_rows(frame, targets=(ordinary_target(),))
    frame.loc[0, "randomized_pit"] = .9
    assert rows[0].randomized_pit == .1
    with pytest.raises(FrozenInstanceError):
        rows[0].randomized_pit = .9

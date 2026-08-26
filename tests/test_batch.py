"""Batch orchestration and the published exclusion list (design §12).

The property under test throughout is §12's: **every variant that goes in comes out either as a
fit or as an exclusion carrying a reason.** A variant that vanishes is the failure mode this
module exists to prevent, because a consumer cannot tell a refused variant from an absent one.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from genomeos.surfaces.batch import (
    EXCLUSION_REASONS,
    MIN_OBSERVATIONS,
    BatchResult,
    Exclusion,
    VariantJob,
    jobs_from_sources,
    run_batch,
    write_exclusions,
)
from genomeos.surfaces.fit import FitConfig

SEED = 42


def _observations(n: int, variant_id: str = "chr11-5227002-T-A") -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    lat = rng.uniform(-10, 20, n)
    lon = rng.uniform(-15, 40, n)
    an = np.full(n, 200)
    ac = rng.binomial(an, 0.08)
    return pd.DataFrame(
        {
            "variant_id": variant_id,
            "rsid": "rs334",
            "population_id": [f"p{i}" for i in range(n)],
            "lat": lat,
            "lon": lon,
            "radius_km": 5.0,
            "ac": ac,
            "an": an,
            "source": "test",
            "assay": "genotype",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": [f"c{i % 4}" for i in range(n)],
            "ingest_version": "test",
        }
    )


# --- the core invariant ---


def test_every_variant_is_either_fitted_or_excluded():
    """No third outcome. This is §12 stated as an assertion."""
    jobs = [
        VariantJob("chr1-1-A-T", _observations(0, "chr1-1-A-T")),
        VariantJob("chr2-2-A-T", _observations(3, "chr2-2-A-T")),
    ]
    result = run_batch(jobs)
    assert result.n_attempted == len(jobs)
    accounted = set(result.fitted) | {e.variant_id for e in result.exclusions}
    assert accounted == {job.variant_id for job in jobs}


def test_a_variant_with_no_observations_is_excluded_with_a_reason():
    result = run_batch([VariantJob("chr1-1-A-T", _observations(0, "chr1-1-A-T"))])
    assert not result.fitted
    assert result.exclusions[0].reason == "no_observations"
    assert result.exclusions[0].n_observations == 0


def test_too_few_observations_is_named_rather_than_left_to_fail_later():
    """Excluded early on purpose. A handful of surveys cannot identify a spatial range, a cohort
    effect and an overdispersion parameter, and letting it through would surface the same problem
    later as an opaque convergence failure."""
    n = MIN_OBSERVATIONS - 1
    result = run_batch([VariantJob("chr2-2-A-T", _observations(n, "chr2-2-A-T"))])
    assert result.exclusions[0].reason == "too_few_observations"
    assert str(n) in result.exclusions[0].detail


def test_an_unexpected_error_is_recorded_not_swallowed_and_not_fatal():
    """A malformed variant must not end the run — but it must not disappear either. The batch is
    the one place where catching broad exceptions is correct, and this pins why."""
    broken = _observations(20, "chr3-3-A-T").drop(columns=["lat"])
    jobs = [
        VariantJob("chr3-3-A-T", broken),
        VariantJob("chr4-4-A-T", _observations(0, "chr4-4-A-T")),
    ]
    result = run_batch(jobs)
    failure = next(e for e in result.exclusions if e.variant_id == "chr3-3-A-T")
    assert failure.reason == "unexpected_error"
    assert failure.detail, "the exception type and message must be preserved"
    assert result.n_attempted == 2, "the run continued past the failure"


def test_strict_mode_reraises_so_a_single_variant_run_can_be_debugged():
    broken = _observations(20, "chr3-3-A-T").drop(columns=["lat"])
    with pytest.raises(Exception):  # noqa: B017 - any failure must surface under strict
        run_batch([VariantJob("chr3-3-A-T", broken)], strict=True)


# --- the published list ---


def test_the_exclusion_list_is_written_even_when_empty(tmp_path):
    """An absent file is ambiguous: nothing excluded, or the list never produced? This file
    exists to remove exactly that ambiguity, so it is always written."""
    path = write_exclusions(BatchResult(), tmp_path / "exclusions.json", data_version="v1")
    payload = json.loads(path.read_text())
    assert payload["exclusions"] == []
    assert payload["n_excluded"] == 0
    assert payload["data_version"] == "v1"


def test_the_exclusion_list_is_deterministic(tmp_path):
    """Two runs over the same inputs must produce identical bytes, so a diff means something
    changed rather than that the dict order moved."""
    result = BatchResult(
        exclusions=[
            Exclusion("chr2-2-A-T", "no_observations", "none", 0),
            Exclusion("chr1-1-A-T", "did_not_converge", "r_hat 1.9", 40),
        ]
    )
    first = write_exclusions(result, tmp_path / "a.json", data_version="v1").read_text()
    second = write_exclusions(result, tmp_path / "b.json", data_version="v1").read_text()
    assert first == second
    rows = json.loads(first)["exclusions"]
    assert [r["reason"] for r in rows] == sorted(r["reason"] for r in rows)


def test_an_unnamed_exclusion_reason_is_refused():
    """The reason vocabulary is closed so a new failure mode gets thought about rather than
    folded into `unexpected_error`."""
    with pytest.raises(ValueError, match="unknown exclusion reason"):
        Exclusion("chr1-1-A-T", "vibes", "", 0)
    assert "did_not_converge" in EXCLUSION_REASONS


# --- job construction ---


def test_jobs_are_split_one_per_variant():
    """`fit_surface` refuses a frame with more than one variant, so this split is the only
    supported route from a mixed observations store to a batch."""
    mixed = pd.concat(
        [_observations(10, "chr1-1-A-T"), _observations(10, "phenotype:g6pd-deficiency")]
    )
    jobs = list(jobs_from_sources({"src": mixed}, FitConfig()))
    assert [j.variant_id for j in jobs] == ["chr1-1-A-T", "phenotype:g6pd-deficiency"]
    assert all(j.observations["variant_id"].nunique() == 1 for j in jobs)


def test_summary_reports_the_excluded_fraction():
    result = BatchResult(exclusions=[Exclusion("chr1-1-A-T", "no_observations", "none", 0)])
    text = str(result)
    assert "0/1 variants fitted" in text
    assert "no_observations" in text

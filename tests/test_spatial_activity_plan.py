"""Nested split planning tests for the spatial activity preflight (#384)."""

from __future__ import annotations

import pandas as pd
import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.spatial_activity_fit import SpatialActivitySamplerConfig
from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig
from genomeos.validation.spatial_activity_simulation import (
    default_spatial_activity_scenarios,
)
from genomeos.validation.spatial_gp_benchmark import plan_single_variant_gp_benchmark

VARIANT = "chr11-5227002-T-A"


def _observations(blocks: int = 5) -> pd.DataFrame:
    rows = []
    for block in range(blocks):
        for replicate in range(2):
            index = block * 2 + replicate
            rows.append(
                {
                    "variant_id": VARIANT,
                    "rsid": "rs334",
                    "population_id": f"population-{index:02d}",
                    "lat": float(-50 + block * 25 + replicate),
                    "lon": float(-150 + block * 65 + replicate),
                    "radius_km": 1.0,
                    "ac": index % 3,
                    "an": 100 + index,
                    "source_record_id": f"record-{index:02d}",
                    "source": "synthetic",
                    "assay": "genotype",
                    "date_lower": 0,
                    "date_upper": 0,
                    "sampling_design": "population_random",
                    "disease_ascertainment_excluded": True,
                    "cohort_id": f"cohort-{block:02d}",
                    "ingest_version": "test",
                }
            )
    return pd.DataFrame.from_records(rows)


def _assignments(observations: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_record_id": observations["source_record_id"],
            "block_id": observations["cohort_id"].str.replace("cohort", "block"),
            "region_id": observations["cohort_id"].str.replace("cohort", "region"),
            "variant_group": "hbs",
        }
    )


def _baseline_plan(blocks: int = 5, dependencies=()):
    observations = _observations(blocks)
    return plan_single_variant_gp_benchmark(
        observations,
        _assignments(observations),
        dependencies,
        buffer_km=300.0,
        data_version="synthetic-template-v1",
        config=FitConfig(draws=10, tune=10, chains=4),
    )


def _model_config() -> SpatialActivityModelConfig:
    return SpatialActivityModelConfig(
        hsgp_m=(2, 2, 2),
        hsgp_c=1.5,
        lengthscale_mu=-2.0,
        lengthscale_sigma=0.4,
        conditional_intercept_mu=-3.5,
        conditional_intercept_sigma=1.5,
        conditional_amplitude_sigma=1.0,
        activity_intercept_mu=2.5,
        activity_intercept_sigma=1.0,
        activity_amplitude_sigma=1.0,
        concentration_sigma=100.0,
        cohort_sd_sigma=0.5,
    )


def _sampler_config() -> SpatialActivitySamplerConfig:
    return SpatialActivitySamplerConfig(draws=10, tune=10, chains=4)


def test_plan_reuses_five_outer_splits_and_builds_three_inner_splits_each() -> None:
    from genomeos.validation.spatial_activity_plan import (
        plan_spatial_activity_preflight,
    )

    baseline = _baseline_plan()
    plan = plan_spatial_activity_preflight(
        baseline,
        dependencies=(),
        model_config=_model_config(),
        sampler_config=_sampler_config(),
        scenarios=default_spatial_activity_scenarios(),
    )

    assert plan.outer_splits == baseline.splits
    assert len(plan.outer_splits) == 5
    assert plan.modes == ("ordinary", "spatial_activity")
    assert len(plan.scenarios) == 18
    assert len(plan.inner_plans) == 5
    for outer, inner in zip(plan.outer_splits, plan.inner_plans, strict=True):
        assert inner.outer_split_id == outer.split_id
        assert inner.refusal_reason is None
        assert inner.grouping is not None
        assert len(inner.splits) == 3
        outer_training = set(outer.train_ids)
        assert all(
            set(split.train_ids + split.test_ids + split.excluded_ids) == outer_training
            for split in inner.splits
        )


def test_plan_retains_infeasible_inner_protocol_without_relaxing_fold_count() -> None:
    from genomeos.validation.spatial_activity_plan import (
        plan_spatial_activity_preflight,
    )

    plan = plan_spatial_activity_preflight(
        _baseline_plan(blocks=3),
        dependencies=(),
        model_config=_model_config(),
        sampler_config=_sampler_config(),
        scenarios=default_spatial_activity_scenarios(),
    )

    assert len(plan.outer_splits) == 3
    assert all(inner.grouping is None for inner in plan.inner_plans)
    assert all(inner.splits == () for inner in plan.inner_plans)
    assert all("three" in inner.refusal_reason for inner in plan.inner_plans)


def test_plan_reapplies_dependencies_inside_outer_training_partitions() -> None:
    from genomeos.validation.spatial_activity_plan import (
        plan_spatial_activity_preflight,
    )

    dependency = (("record-00", "record-02"),)
    plan = plan_spatial_activity_preflight(
        _baseline_plan(dependencies=dependency),
        dependencies=dependency,
        model_config=_model_config(),
        sampler_config=_sampler_config(),
        scenarios=default_spatial_activity_scenarios(),
    )

    relevant = [
        inner
        for outer, inner in zip(plan.outer_splits, plan.inner_plans, strict=True)
        if {"record-00", "record-02"} <= set(outer.train_ids)
    ]
    assert relevant
    for inner in relevant:
        for split in inner.splits:
            if "record-00" in split.test_ids:
                assert "record-02" in split.excluded_ids
            if "record-02" in split.test_ids:
                assert "record-00" in split.excluded_ids


def test_plan_refuses_unknown_dependency_identity() -> None:
    from genomeos.validation.spatial_activity_plan import (
        plan_spatial_activity_preflight,
    )

    with pytest.raises(ValueError, match="unknown"):
        plan_spatial_activity_preflight(
            _baseline_plan(),
            dependencies=(("record-00", "missing"),),
            model_config=_model_config(),
            sampler_config=_sampler_config(),
            scenarios=default_spatial_activity_scenarios(),
        )


def test_plan_refuses_duplicate_or_incomplete_scenario_grid() -> None:
    from genomeos.validation.spatial_activity_plan import (
        plan_spatial_activity_preflight,
    )

    scenarios = default_spatial_activity_scenarios()
    with pytest.raises(ValueError, match="scenario grid"):
        plan_spatial_activity_preflight(
            _baseline_plan(),
            dependencies=(),
            model_config=_model_config(),
            sampler_config=_sampler_config(),
            scenarios=scenarios[:-1] + (scenarios[0],),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("baseline", object()),
        ("model", object()),
        ("sampler", object()),
    ],
)
def test_plan_refuses_wrong_contract_types(field: str, value: object) -> None:
    from genomeos.validation.spatial_activity_plan import (
        plan_spatial_activity_preflight,
    )

    kwargs = {
        "baseline_plan": _baseline_plan(),
        "dependencies": (),
        "model_config": _model_config(),
        "sampler_config": _sampler_config(),
        "scenarios": default_spatial_activity_scenarios(),
    }
    key = {
        "baseline": "baseline_plan",
        "model": "model_config",
        "sampler": "sampler_config",
    }[field]
    kwargs[key] = value
    with pytest.raises((TypeError, ValueError)):
        plan_spatial_activity_preflight(**kwargs)

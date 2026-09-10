"""Structural and hand-likelihood tests for B0H (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from math import log
from types import SimpleNamespace

import arviz as az
import numpy as np
import pytest
import xarray as xr

from genomeos.surfaces.heterogeneity_types import (
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    VariantTrainingCounts,
)
from genomeos.surfaces.reference_heterogeneity import (
    fit_reference_population_heterogeneity,
    predict_reference_population_heterogeneity,
)
from genomeos.validation.count_baseline import B0InfeasibleError
from genomeos.validation.predictive import MAX_BETA_SCORING_COUNT
from genomeos.validation.reference_counts import ReferenceCount, ReferenceInfeasibleError


def row(group: str, variant: str = "v", ac: int = 1, an: int = 2) -> ReferenceCount:
    return ReferenceCount(f"{group}:{variant}", variant, group, "synthetic", "block", ac, an)


def config(**changes: object) -> PopulationHeterogeneityConfig:
    values: dict[str, object] = {
        "mean_prior_alpha": 1,
        "mean_prior_beta": 1,
        "rho_prior_alpha": 1,
        "rho_prior_beta": 9,
        "draws": 300,
        "tune": 7,
        "chains": 4,
        "target_accept": 0.9,
        "seed": 42,
    }
    values.update(changes)
    return PopulationHeterogeneityConfig(**values)  # type: ignore[arg-type]


def idata_for(
    variant_ids: tuple[str, ...], *, chains: int = 4, draws: int = 300, seed: int = 7
) -> xr.DataTree:
    rng = np.random.default_rng(seed)
    shape = (chains, draws, len(variant_ids))
    posterior = xr.Dataset(
        {
            "mean": (("chain", "draw", "variant"), rng.beta(3, 5, shape).astype(np.float64)),
            "rho": (("chain", "draw", "variant"), rng.beta(2, 12, shape).astype(np.float64)),
        },
        coords={
            "chain": np.arange(chains),
            "draw": np.arange(draws),
            "variant": np.asarray(variant_ids, dtype=str),
        },
    )
    sample_stats = xr.Dataset(
        {"diverging": (("chain", "draw"), np.zeros((chains, draws), dtype=bool))},
        coords={"chain": np.arange(chains), "draw": np.arange(draws)},
    )
    return xr.DataTree.from_dict({"posterior": posterior, "sample_stats": sample_stats})


def install_sampler(
    monkeypatch: pytest.MonkeyPatch, inference_data: xr.DataTree
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def sample(**kwargs: object) -> xr.DataTree:
        from genomeos.surfaces.reference_heterogeneity import pm

        captured["model"] = pm.Model.get_context()
        captured["kwargs"] = kwargs
        return inference_data

    monkeypatch.setattr("genomeos.surfaces.reference_heterogeneity.pm.sample", sample)
    return captured


def test_population_heterogeneity_config_has_declared_defaults() -> None:
    value = PopulationHeterogeneityConfig(1, 1, 1, 9)
    assert (value.draws, value.tune, value.chains, value.target_accept, value.seed) == (
        500,
        1000,
        4,
        0.9,
        42,
    )


@pytest.mark.parametrize(
    "field", ["mean_prior_alpha", "mean_prior_beta", "rho_prior_alpha", "rho_prior_beta"]
)
@pytest.mark.parametrize("invalid", [0, -1, np.nan, np.inf, True])
def test_config_rejects_invalid_prior_shapes(field: str, invalid: object) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        config(**{field: invalid})


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("draws", 0), ("draws", 1.5), ("draws", True),
        ("tune", 0), ("tune", 1.5), ("chains", 3), ("chains", 4.0),
        ("seed", -1), ("seed", False),
        ("target_accept", 0), ("target_accept", 1),
        ("target_accept", np.nan), ("target_accept", True),
    ],
)
def test_config_rejects_invalid_sampler_settings(field: str, invalid: object) -> None:
    with pytest.raises(ValueError):
        config(**{field: invalid})


def test_fit_builds_declared_beta_binomial_graph_and_uses_explicit_sampler_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fit_config = config()
    captured = install_sampler(monkeypatch, idata_for(("v",), draws=fit_config.draws))
    fit_reference_population_heterogeneity(
        [row("first"), row("second"), row("unavailable", ac=0, an=0)], config=fit_config
    )

    model = captured["model"]
    assert model.coords["variant"] == ("v",)
    point = model.initial_point()
    point["mean_logodds__"] = np.array([log(0.25 / 0.75)])
    point["rho_logodds__"] = np.array([log(0.2 / 0.8)])
    observed_logp = float(model.compile_logp(vars=[model["obs"]], jacobian=False)(point))
    assert observed_logp == pytest.approx(2 * log(0.3), abs=1e-12)
    assert observed_logp != pytest.approx(2 * log(0.375), abs=1e-6)
    assert captured["kwargs"] == {
        "draws": 300,
        "tune": 7,
        "chains": 4,
        "random_seed": 42,
        "nuts_sampler": "numpyro",
        "target_accept": 0.9,
        "nuts": {"chain_method": "vectorized"},
        "progressbar": False,
    }


def test_graph_uses_asymmetric_prior_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    fit_config = config(mean_prior_alpha=2, mean_prior_beta=3, rho_prior_alpha=3, rho_prior_beta=4)
    captured = install_sampler(monkeypatch, idata_for(("v",), draws=fit_config.draws))
    fit_reference_population_heterogeneity([row("train")], config=fit_config)
    model = captured["model"]
    point = model.initial_point()
    point["mean_logodds__"] = np.array([log(0.25 / 0.75)])
    point["rho_logodds__"] = np.array([log(0.2 / 0.8)])
    prior_logp = float(model.compile_logp(vars=[model["mean"], model["rho"]], jacobian=False)(point))
    expected = log(12 * 0.25 * 0.75**2) + log(60 * 0.2**2 * 0.8**3)
    assert prior_logp == pytest.approx(expected, abs=1e-6)


def test_graph_aligns_distinct_rows_to_their_literal_variant_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fit_config = config()
    captured = install_sampler(monkeypatch, idata_for(("a", "z"), draws=fit_config.draws))
    fit_reference_population_heterogeneity(
        [row("group-a", "a", ac=1, an=2), row("group-z", "z", ac=0, an=3)],
        config=fit_config,
    )
    model = captured["model"]
    point = model.initial_point()
    point["mean_logodds__"] = np.array([log(0.25 / 0.75), log(0.6 / 0.4)])
    point["rho_logodds__"] = np.array([log(0.2 / 0.8), log(0.5 / 0.5)])

    observed_logp = float(model.compile_logp(vars=[model["obs"]], jacobian=False)(point))

    # Variant a: P(AC=1|AN=2, mean=.25, rho=.2)=.3.
    # Variant z: P(AC=0|AN=3, mean=.6, rho=.5)=.4*1.4*2.4/(1*2*3)=.224.
    assert observed_logp == pytest.approx(log(0.3) + log(0.224), abs=1e-12)
    # Swapping the row-to-variant index instead gives .24 * .5.
    assert observed_logp != pytest.approx(log(0.24) + log(0.5), abs=1e-6)


def test_fit_retains_literal_identities_training_totals_and_immutable_copies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fit_config = config()
    inference_data = idata_for(("z", "a"), draws=fit_config.draws)
    source_mean = inference_data.posterior["mean"].values
    install_sampler(monkeypatch, inference_data)
    fitted = fit_reference_population_heterogeneity(
        [
            row("group z", "z", ac=2, an=3), row("group a", "a", ac=1, an=4),
            row("second a", "a", ac=2, an=5), row("missing z", "z", ac=0, an=0),
        ],
        config=fit_config,
    )

    assert fitted.variant_ids == ("a", "z")
    assert fitted.training_record_ids == ("group a:a", "group z:z", "missing z:z", "second a:a")
    assert fitted.training_group_ids == ("group a", "group z", "missing z", "second a")
    assert fitted.unavailable_training_ids == ("missing z:z",)
    assert [
        (c.variant_id, c.training_observation_count, c.training_ac, c.training_an)
        for c in fitted.training_counts
    ] == [("a", 2, 3, 9), ("z", 1, 2, 3)]
    assert fitted.mean_draws.dtype == np.float64
    assert fitted.mean_draws.shape == (4, 300, 2)
    expected_first = source_mean[:, :, 1].copy()
    source_mean[:, :, 1] = 0.99
    np.testing.assert_array_equal(fitted.mean_draws[:, :, 0], expected_first)
    with pytest.raises(ValueError):
        fitted.mean_draws.flags.writeable = True


@pytest.mark.parametrize("training", [[], [row("missing", ac=0, an=0)]])
def test_fit_refuses_empty_or_all_unavailable_training(training: list[ReferenceCount]) -> None:
    with pytest.raises((ValueError, ReferenceInfeasibleError)):
        fit_reference_population_heterogeneity(training, config=config())


def test_fit_refuses_training_denominator_above_scoring_domain() -> None:
    with pytest.raises(ValueError, match=str(MAX_BETA_SCORING_COUNT)):
        fit_reference_population_heterogeneity(
            [row("too-large", ac=1, an=MAX_BETA_SCORING_COUNT + 1)], config=config()
        )


def _missing_mean(data: xr.DataTree) -> None:
    del data.posterior["mean"]


def _missing_variant(data: xr.DataTree) -> None:
    data.posterior = data.posterior.sel(variant=["a"])


def _duplicate_variant(data: xr.DataTree) -> None:
    data["posterior"] = data.posterior.to_dataset().assign_coords(variant=["a", "a"])


def _misalign_rho(data: xr.DataTree) -> None:
    data.posterior["rho"] = data.posterior["rho"].assign_coords(variant=["a", "missing"])


def _wrong_axes(data: xr.DataTree) -> None:
    data.posterior["mean"] = data.posterior["mean"].transpose("draw", "chain", "variant")


def _wrong_chain_size(data: xr.DataTree) -> None:
    data["posterior"] = data.posterior.to_dataset().isel(chain=slice(3))


def _wrong_draw_size(data: xr.DataTree) -> None:
    data["posterior"] = data.posterior.to_dataset().isel(draw=slice(299))


def _wrong_draw_labels(data: xr.DataTree) -> None:
    data["posterior"] = data.posterior.to_dataset().assign_coords(draw=np.arange(1, 301))


def _noninteger_chain_labels(data: xr.DataTree) -> None:
    data["posterior"] = data.posterior.to_dataset().assign_coords(chain=np.arange(4, dtype=float))


def _wrong_sample_stats_labels(data: xr.DataTree) -> None:
    data["sample_stats"] = data.sample_stats.to_dataset().assign_coords(draw=np.arange(1, 301))


def _float32_mean(data: xr.DataTree) -> None:
    data.posterior["mean"] = data.posterior["mean"].astype(np.float32)


def _nan_mean(data: xr.DataTree) -> None:
    data.posterior["mean"].values[0, 0, 0] = np.nan


def _boundary_rho(data: xr.DataTree) -> None:
    data.posterior["rho"].values[0, 0, 0] = 0.0


def _missing_diverging(data: xr.DataTree) -> None:
    del data.sample_stats["diverging"]


def _numeric_diverging(data: xr.DataTree) -> None:
    data.sample_stats["diverging"] = data.sample_stats["diverging"].astype(np.int64)


@pytest.mark.parametrize(
    "mutation",
    [
        _missing_mean, _missing_variant, _duplicate_variant, _misalign_rho, _wrong_axes,
        _wrong_chain_size, _wrong_draw_size,
        _wrong_draw_labels, _noninteger_chain_labels, _wrong_sample_stats_labels,
        _float32_mean, _nan_mean,
        _boundary_rho, _missing_diverging, _numeric_diverging,
    ],
    ids=lambda mutation: mutation.__name__,
)
def test_fit_refuses_malformed_or_numerically_invalid_sampler_output(
    monkeypatch: pytest.MonkeyPatch, mutation: Callable[[xr.DataTree], None]
) -> None:
    inference_data = idata_for(("a", "z"))
    mutation(inference_data)
    install_sampler(monkeypatch, inference_data)
    with pytest.raises((ValueError, ArithmeticError)):
        fit_reference_population_heterogeneity([row("ga", "a"), row("gz", "z")], config=config())


def test_fit_aligns_reordered_labeled_variant_axes(monkeypatch: pytest.MonkeyPatch) -> None:
    inference_data = idata_for(("z", "a"))
    expected_mean_a = inference_data.posterior["mean"].sel(variant="a").values.copy()
    expected_rho_a = inference_data.posterior["rho"].sel(variant="a").values.copy()
    install_sampler(monkeypatch, inference_data)
    fitted = fit_reference_population_heterogeneity([row("ga", "a"), row("gz", "z")], config=config())
    np.testing.assert_array_equal(fitted.mean_draws[:, :, 0], expected_mean_a)
    np.testing.assert_array_equal(fitted.rho_draws[:, :, 0], expected_rho_a)


def test_fit_refuses_divergent_sampler_and_carries_global_count(monkeypatch: pytest.MonkeyPatch) -> None:
    inference_data = idata_for(("v",))
    inference_data.sample_stats["diverging"].values[1, 2] = True
    install_sampler(monkeypatch, inference_data)
    with pytest.raises(HeterogeneityConvergenceError) as raised:
        fit_reference_population_heterogeneity([row("train")], config=config())
    assert raised.value.divergence_count == 1
    assert raised.value.reason == "sampler produced divergent transitions"
    assert len(raised.value.diagnostics) == 1
    assert raised.value.diagnostics[0].variant_id == "v"


def test_fit_refuses_nonmixing_chains_using_real_arviz(monkeypatch: pytest.MonkeyPatch) -> None:
    inference_data = idata_for(("v",))
    for chain in range(4):
        inference_data.posterior["mean"].values[chain, :, 0] = 0.1 + 0.2 * chain
    install_sampler(monkeypatch, inference_data)
    with pytest.raises(HeterogeneityConvergenceError, match="convergence"):
        fit_reference_population_heterogeneity([row("train")], config=config())


@pytest.mark.parametrize(
    ("test_method", "bad_value"),
    [("bulk", 199.0), ("tail", 199.0), ("tail", np.nan)],
)
def test_fit_refuses_low_or_nonfinite_ess(
    monkeypatch: pytest.MonkeyPatch, test_method: str, bad_value: float
) -> None:
    inference_data = idata_for(("v",))
    install_sampler(monkeypatch, inference_data)
    real_ess = az.ess

    def ess(data: xr.DataTree, *, var_names: list[str], method: str) -> xr.Dataset:
        result = real_ess(data, var_names=var_names, method=method)
        if method == test_method:
            result["rho"].values[0] = bad_value
        return result

    monkeypatch.setattr("genomeos.surfaces.reference_heterogeneity.az.ess", ess)
    with pytest.raises(HeterogeneityConvergenceError):
        fit_reference_population_heterogeneity([row("train")], config=config())


def test_nonfinite_diagnostic_error_retains_other_finite_variant_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inference_data = idata_for(("a", "z"))
    install_sampler(monkeypatch, inference_data)
    real_ess = az.ess

    def ess(data: xr.DataTree, *, var_names: list[str], method: str) -> xr.Dataset:
        result = real_ess(data, var_names=var_names, method=method)
        if method == "tail":
            result["rho"].loc[{"variant": "z"}] = np.nan
        return result

    monkeypatch.setattr("genomeos.surfaces.reference_heterogeneity.az.ess", ess)
    with pytest.raises(HeterogeneityConvergenceError) as raised:
        fit_reference_population_heterogeneity(
            [row("ga", "a"), row("gz", "z")], config=config()
        )
    assert tuple(item.variant_id for item in raised.value.diagnostics) == ("a",)
    assert raised.value.divergence_count == 0


def test_fit_refuses_concentration_outside_count_predictive_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    inference_data = idata_for(("v",))
    inference_data.posterior["rho"].values[:] *= 1e-10
    install_sampler(monkeypatch, inference_data)
    with pytest.raises(ValueError, match="stable numeric domain"):
        fit_reference_population_heterogeneity([row("train")], config=config())


def fitted_for_prediction(monkeypatch: pytest.MonkeyPatch):
    fit_config = config()
    install_sampler(monkeypatch, idata_for(("a", "v"), draws=fit_config.draws))
    return fit_reference_population_heterogeneity(
        [row("train-a", "a"), row("train-v", "v")], config=fit_config
    )


@pytest.mark.parametrize(
    ("field", "nested"),
    [
        (
            "training_counts",
            SimpleNamespace(
                variant_id="a",
                training_observation_count=1,
                training_ac=1,
                training_an=2,
            ),
        ),
        (
            "diagnostics",
            SimpleNamespace(
                variant_id="a",
                max_rhat=np.nan,
                min_bulk_ess=300.0,
                min_tail_ess=300.0,
            ),
        ),
    ],
)
def test_fit_contract_rejects_non_contract_nested_items(
    monkeypatch: pytest.MonkeyPatch, field: str, nested: SimpleNamespace
) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    replacement = list(getattr(fitted, field))
    replacement[0] = nested
    with pytest.raises(ValueError, match=field):
        replace(fitted, **{field: tuple(replacement)})


def test_fit_contract_rejects_training_count_aggregate_inconsistent_with_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    first = fitted.training_counts[0]
    contradictory = VariantTrainingCounts(
        first.variant_id,
        first.training_observation_count + 1,
        first.training_ac,
        first.training_an,
    )
    with pytest.raises(ValueError, match="training_observation_count"):
        replace(fitted, training_counts=(contradictory, *fitted.training_counts[1:]))


def test_prediction_preserves_scoreable_and_unavailable_order_and_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    predicted = predict_reference_population_heterogeneity(
        fitted,
        [row("query-z", "v", ac=2), row("query-missing", "unknown", ac=0, an=0), row("query-a", "a", ac=0)],
        cdf_backend="cupy",
    )
    assert predicted.observation_ids == ("query-z:v", "query-a:a")
    assert predicted.unavailable_ids == ("query-missing:unknown",)
    assert predicted.marginal_predictive.cdf_backend == "cupy"
    assert predicted.marginal_predictive.mean_draws.shape == (1200, 2)


def test_held_out_count_never_changes_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    first = predict_reference_population_heterogeneity(fitted, [row("query", ac=0)])
    changed = predict_reference_population_heterogeneity(fitted, [row("query", ac=2)])
    np.testing.assert_array_equal(
        first.marginal_predictive.mean_draws, changed.marginal_predictive.mean_draws
    )
    np.testing.assert_array_equal(
        first.marginal_predictive.concentration, changed.marginal_predictive.concentration
    )


@pytest.mark.parametrize(
    "testing",
    [[row("train-v")], [ReferenceCount("new-id", "v", "train-v", "synthetic", "block", 1, 2)]],
)
def test_prediction_rejects_training_record_or_group_overlap(
    monkeypatch: pytest.MonkeyPatch, testing: list[ReferenceCount]
) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    with pytest.raises(ValueError, match="disjoint"):
        predict_reference_population_heterogeneity(fitted, testing)


def test_prediction_refuses_absent_scoreable_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    with pytest.raises(B0InfeasibleError) as raised:
        predict_reference_population_heterogeneity(fitted, [row("query", "absent")])
    assert raised.value.absent_variants == ("absent",)


def test_prediction_refuses_all_unavailable_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    with pytest.raises(ReferenceInfeasibleError):
        predict_reference_population_heterogeneity(fitted, [row("query", ac=0, an=0)])


def test_prediction_uses_count_predictive_numeric_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    fitted = fitted_for_prediction(monkeypatch)
    with pytest.raises(ValueError, match="cdf_backend"):
        predict_reference_population_heterogeneity(
            fitted, [row("query")], cdf_backend="automatic"  # type: ignore[arg-type]
        )

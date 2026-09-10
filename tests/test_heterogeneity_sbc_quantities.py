"""B0H selected quantities: mocked orchestration plus one actual reference."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from unittest.mock import Mock

import numpy as np
import pytest

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityFit,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation import heterogeneity_sbc_quantities as quantities
from genomeos.validation.heterogeneity_attempts import (
    FitAttemptResult,
    FitIdentityError,
    plan_fit_attempt,
    require_fit_identity,
)
from genomeos.validation.heterogeneity_dependence import (
    DependenceComparisons,
    DependencePointReference,
    HeterogeneityDependenceReference,
    dependence_comparisons,
    heterogeneity_dependence_reference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError,
    PriorControlFailure,
    PriorControlResult,
)
from genomeos.validation.heterogeneity_sbc_quantities import selected_sbc_quantities
from genomeos.validation.heterogeneity_sbc_quantity_types import (
    require_quantity_comparisons,
    require_quantity_reference,
)
from genomeos.validation.heterogeneity_simulation_types import (
    GeneratedDataset,
    GenerationProvenance,
    HeldoutTarget,
    ParameterTruth,
    SbcCaseId,
    generation_id,
    sbc_seed_identity,
    simulation_reference_count,
)
from genomeos.validation.sbc_ranks import randomized_rank


def fixture(track=0, attempt_id=0, *, varying=False, study=0):
    assert study in (0, 1)
    case = SbcCaseId(track, study, 0, 0)
    generation = generation_id(case)
    ans = (0, 1, 2, 5, 10, 20, 40, 64) * 2
    acs = (0, 0, 1, 2, 4, 7, 11, 19) * 2
    rows = tuple(
        simulation_reference_count(generation, "train", str(i), ac, an)
        for i, (ac, an) in enumerate(zip(acs, ans, strict=True))
    )
    heldout = HeldoutTarget(
        "fresh_population",
        simulation_reference_count(generation, "heldout", "fresh_population", 3, 20),
        0.25 if study == 0 else 0.001,
        None,
        None,
        None,
        None,
    )
    data = GeneratedDataset(
        case,
        GenerationProvenance(
            generation, tuple(sbc_seed_identity(case, purpose_id=p, attempt_id=0) for p in range(4))
        ),
        ParameterTruth(0.25, 0.25) if study == 0 else ParameterTruth(0.001, 0.0),
        rows,
        ((0.25 if study == 0 else 0.001),) * 16,
        None,
        (heldout,),
        0,
        0,
    )
    spec = plan_fit_attempt(data, attempt_id=attempt_id)
    shape = (4, spec.config.draws, 1)
    means = np.empty(shape, dtype=np.float64)
    rhos = np.empty(shape, dtype=np.float64)
    for chain, (mean, rho) in enumerate(((0.125, 0.125), (0.25, 0.1875), (0.375, 0.3125), (0.5, 0.4375))):
        means[chain, :, 0] = mean
        rhos[chain, :, 0] = rho
        if varying:
            means[chain, :, 0] = 0.125 + (chain * spec.config.draws + np.arange(spec.config.draws)) / 8192
            rhos[chain, :, 0] = 0.125 + (chain * spec.config.draws + np.arange(spec.config.draws)) / 16384
    variant = rows[0].variant_id
    fit = PopulationHeterogeneityFit(
        spec.config,
        (variant,),
        means,
        rhos,
        tuple(sorted(row.record_id for row in rows)),
        tuple(sorted({row.group_id for row in rows})),
        tuple(sorted(row.record_id for row in rows if row.an == 0)),
        (VariantTrainingCounts(variant, 14, sum(acs), sum(ans)),),
        (VariantHeterogeneityDiagnostics(variant, 1.0, 200.0, 200.0),),
        0,
    )
    return data, FitAttemptResult(spec, "accepted", fit, None, (), None)


def literal_control(*, seed):
    return PriorControlResult(seed, ((0.125, 0.25), (0.375, 0.5), (0.625, 0.75), (0.875, 0.125)), None)


def mocked_reference(counts, *, mean_prior, rho_prior, points):
    """Synthetic arithmetic for call/guard tests, not a mixed-count h oracle."""
    unique = tuple(dict.fromkeys(points))
    records = []
    for mean, rho in points:
        value = float(unique.index((mean, rho)))
        records.append(
            DependencePointReference(
                mean,
                rho,
                ((value, 0.0, 0.0, 0.0),) * 3,
                (value,) * 3,
                value,
                1e-12,
                True,
            )
        )
    return HeterogeneityDependenceReference((64, 128, 256), False, tuple(records))


def install_mocks(monkeypatch):
    monkeypatch.setattr(quantities, "draw_prior_control", literal_control)
    reference = Mock(side_effect=mocked_reference)
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    return reference


def exact_mass(ac, an, mean, rho):
    """Independent rational rising-factorial Beta-binomial product."""
    mean, rho = Fraction(mean), Fraction(rho)
    kappa = (1 - rho) / rho
    alpha, beta = mean * kappa, (1 - mean) * kappa
    result = Fraction(math.comb(an, ac))
    for j in range(ac):
        result *= alpha + j
    for j in range(an - ac):
        result *= beta + j
    for j in range(an):
        result /= alpha + beta + j
    return result


@pytest.mark.parametrize("track,attempt_id", ((0, 0), (1, 0), (0, 1), (1, 1)))
def test_literal_selection_pairing_and_rational_quantities(monkeypatch, track, attempt_id):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture(track, attempt_id)
    result = selected_sbc_quantities(data, attempt=attempt)
    expected_indices = []
    for chain in range(4):
        entropy = (42, 211, 1, track, 0, 0, 0, 5, attempt_id)
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy, spawn_key=(chain,))))
        expected_indices.append((chain, int(rng.integers(0, attempt.spec.config.draws))))
    assert result.selected_indices == tuple(expected_indices)
    assert result.selection_seeds == tuple(
        DiagnosticSeedIdentity(data.case_id, attempt_id, 5, (chain,)) for chain in range(4)
    )
    correct = tuple(
        (float(attempt.fit.mean_draws[c, d, 0]), float(attempt.fit.rho_draws[c, d, 0]))
        for c, d in expected_indices
    )
    assert result.points[1:5] == correct
    assert result.points[9:13] == tuple((correct[c][0], correct[(c - 1) % 4][1]) for c in range(4))
    assert result.point_slots == tuple(range(13)) and result.complete
    assert result.selection_method == "one_uniform_postwarmup_draw_per_chain"
    assert reference.call_count == 1
    assert reference.call_args.args == (tuple((row.ac, row.an) for row in data.training),)
    assert reference.call_args.kwargs == {
        "mean_prior": (1.0, 1.0),
        "rho_prior": (1.0, 9.0 if track == 0 else 4.0),
        "points": result.points,
    }
    for index, (mean, rho) in enumerate(result.points):
        expected = (
            mean,
            rho,
            mean * rho,
            math.log(float(math.prod(exact_mass(row.ac, row.an, mean, rho) for row in data.training))),
            math.log(float(exact_mass(0, 20, mean, rho))),
        )
        actual = tuple(entry.values[index] for entry in result.scalar_quantities)
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)
    for entry in result.ranks:
        if entry.quantity_id == 5:
            assert entry.comparisons.status == "resolved"
            assert entry.rank == randomized_rank(
                0, entry.comparisons.comparisons, seed=entry.seed.scalar_uint128
            )


def test_varying_chains_preserve_selected_pair_and_heldout_is_irrelevant(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture(varying=True)
    first = selected_sbc_quantities(data, attempt=attempt)
    for i, (chain, draw) in enumerate(first.selected_indices, start=1):
        assert first.points[i] == (
            attempt.fit.mean_draws[chain, draw, 0],
            attempt.fit.rho_draws[chain, draw, 0],
        )
    target = data.heldouts[0]
    changed = replace(data, heldouts=(replace(target, row=replace(target.row, ac=4)),))
    second = selected_sbc_quantities(changed, attempt=attempt)
    assert first == second


def test_guard_runs_first_and_rejects_before_rng(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    called = []
    original_guard = require_fit_identity

    def guard(dataset, *, spec, fit):
        called.append("guard")
        original_guard(dataset, spec=spec, fit=fit)

    monkeypatch.setattr(quantities, "require_fit_identity", guard)
    real_generator = np.random.Generator

    def generator(bitgen):
        assert called == ["guard"]
        return real_generator(bitgen)

    monkeypatch.setattr(quantities.np.random, "Generator", generator)
    selected_sbc_quantities(data, attempt=attempt)
    _, wrong_attempt = fixture(track=1)
    sentinel = Mock(side_effect=AssertionError("RNG must not run"))
    monkeypatch.setattr(quantities.np.random, "Generator", sentinel)
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=wrong_attempt)
    sentinel.assert_not_called()


def test_stress_failed_attempt_and_fit_identity_are_rejected_before_rng(monkeypatch):
    from genomeos.validation.heterogeneity_attempts import AttemptError

    data, attempt = fixture()
    stress, stress_attempt = fixture(study=1)
    wrong_fit = replace(
        attempt.fit, training_group_ids=tuple("wrong:" + group for group in attempt.fit.training_group_ids)
    )
    wrong_attempt = replace(attempt, fit=wrong_fit)
    failed = FitAttemptResult(
        attempt.spec,
        "failed",
        None,
        AttemptError("runtime", "builtins.RuntimeError", "fit", None, None, None),
        (),
        None,
    )
    sentinel = Mock(side_effect=AssertionError("RNG must not run"))
    monkeypatch.setattr(quantities.np.random, "Generator", sentinel)
    for dataset, result in ((stress, stress_attempt), (data, failed), (None, attempt)):
        with pytest.raises(ValueError):
            selected_sbc_quantities(dataset, attempt=result)
    with pytest.raises(FitIdentityError) as rejected:
        selected_sbc_quantities(data, attempt=wrong_attempt)
    assert "training_group_ids" in rejected.value.mismatches
    sentinel.assert_not_called()


def test_identical_parameter_point_is_literal_h_tie(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    means = attempt.fit.mean_draws.copy()
    rhos = attempt.fit.rho_draws.copy()
    means[0, :, 0], rhos[0, :, 0] = data.truth.mean, data.truth.rho
    attempt = replace(attempt, fit=replace(attempt.fit, mean_draws=means, rho_draws=rhos))
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.points[1] == result.points[0]
    assert result.ranks[5].comparisons.comparisons[0] == 0


def test_repeated_draw_index_across_chains_is_valid(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture(varying=True)

    class IndexStream:
        def integers(self, low, high):
            assert low == 0 and high == 500
            return np.int64(11)

    monkeypatch.setattr(quantities.np.random, "Generator", lambda bitgen: IndexStream())
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.selected_indices == ((0, 11), (1, 11), (2, 11), (3, 11))


def test_nine_actual_points_on_control_failure(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()

    def failed_control(*, seed):
        return PriorControlResult(
            seed,
            ((0.25, 0.125),) * 3,
            PriorControlFailure(3, "rho", "rounded_boundary", 0.375, 0.0, None, None),
        )

    monkeypatch.setattr(quantities, "draw_prior_control", failed_control)
    rank_spy = Mock(wraps=randomized_rank)
    comparison_spy = Mock(wraps=dependence_comparisons)
    monkeypatch.setattr(quantities, "randomized_rank", rank_spy)
    monkeypatch.setattr(quantities, "dependence_comparisons", comparison_spy)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.point_slots == (0, 1, 2, 3, 4, 9, 10, 11, 12)
    assert len(result.points) == len(result.reference.points) == 9
    assert reference.call_count == 1 and rank_spy.call_count == 12
    assert [call.kwargs["draw_indices"] for call in comparison_spy.call_args_list] == [
        (1, 2, 3, 4),
        (5, 6, 7, 8),
    ]
    assert all(entry.status == "control_failed" for entry in result.ranks[6:12])
    assert all(entry.status == "ranked" for entry in (*result.ranks[:6], *result.ranks[12:]))
    assert result.control.failure.sampled_mean == 0.375 and not result.complete


def test_scalar_calls_include_an0_and_precede_single_reference(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    calls = []
    real_mass = quantities.heterogeneity_log_mass

    def log_mass(ac, an, *, mean, rho):
        calls.append((ac, an))
        assert mean.shape == rho.shape == (13,)
        return real_mass(ac, an, mean=mean, rho=rho)

    def reference(counts, **kwargs):
        assert calls == [(row.ac, row.an) for row in data.training] + [(0, 20)]
        calls.append("reference")
        return mocked_reference(counts, **kwargs)

    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    selected_sbc_quantities(data, attempt=attempt)
    assert calls.count((0, 0)) == 2 and calls[-1] == "reference"


def test_actual_training_exception_retains_other_quantities(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    calls = []
    real_mass = quantities.heterogeneity_log_mass

    def log_mass(ac, an, *, mean, rho):
        calls.append((ac, an))
        if len(calls) == 3:
            raise KeyError("training-call")
        return real_mass(ac, an, mean=mean, rho=rho)

    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert calls == [(0, 0), (0, 1), (1, 2), (0, 20)]
    assert result.scalar_quantities[3].error == DiagnosticCallError("builtins.KeyError", "'training-call'")
    assert result.scalar_quantities[3].failed_training_row == 2
    assert result.scalar_quantities[3].values is None
    assert all(result.scalar_quantities[q].values is not None for q in (0, 1, 2, 4))
    assert reference.call_count == 1
    assert all(result.ranks[m * 6 + 3].status == "quantity_failed" for m in range(3))


def test_actual_reference_exception_retains_fifteen_scalar_ranks(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(
        quantities, "heterogeneity_dependence_reference", Mock(side_effect=KeyError("reference"))
    )
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.reference is None
    assert result.reference_error == DiagnosticCallError("builtins.KeyError", "'reference'")
    assert sum(entry.status == "ranked" for entry in result.ranks) == 15
    assert all(result.ranks[m * 6 + 5].status == "reference_failed" for m in range(3))


@pytest.mark.parametrize("state", ("dependence_reference_unresolved", "dependence_rank_order_unresolved"))
def test_actual_public_guard_unresolved_states_keep_raw_evidence(monkeypatch, state):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    def reference(counts, **kwargs):
        result = mocked_reference(counts, **kwargs)
        truth = result.points[0]
        if state == "dependence_reference_unresolved":
            truth = replace(truth, resolved=False)
        else:
            truth = replace(truth, error_bound=1e6)
        return replace(result, points=(truth, *result.points[1:]))

    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.reference is not None and result.reference_error is None
    for mode in range(3):
        entry = result.ranks[mode * 6 + 5]
        assert entry.status == entry.comparisons.status == state
        assert len(entry.comparisons.comparisons_by_order) == 3
        assert entry.rank is entry.error is entry.comparisons.comparisons is None
    assert sum(entry.status == "ranked" for entry in result.ranks) == 15


@pytest.mark.parametrize(
    "stage,status", (("dependence_comparisons", "comparison_failed"), ("randomized_rank", "rank_failed"))
)
def test_actual_comparison_and_rank_exceptions_are_separate(monkeypatch, stage, status):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, stage, Mock(side_effect=RuntimeError("call")))
    result = selected_sbc_quantities(data, attempt=attempt)
    affected = result.ranks if stage == "randomized_rank" else result.ranks[5::6]
    assert all(entry.status == status for entry in affected)
    assert all(entry.error == DiagnosticCallError("builtins.RuntimeError", "call") for entry in affected)
    assert result.reference is not None and all(
        entry.values is not None for entry in result.scalar_quantities
    )


@pytest.mark.parametrize(
    "bad",
    (
        0.0,
        [0.0] * 13,
        np.zeros((13, 1)),
        np.zeros(12),
        np.zeros(13, dtype=np.float32),
        np.zeros(13, dtype=bool),
        np.zeros(13, dtype=complex),
        np.full(13, np.nan),
        np.full(13, np.inf),
    ),
)
def test_malformed_logmass_return_propagates(monkeypatch, bad):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, "heterogeneity_log_mass", Mock(return_value=bad))
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)
    reference.assert_not_called()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda r: object(),
        lambda r: replace(r, orders=(64, 128, 255)),
        lambda r: replace(r, analytic_separability=1),
        lambda r: replace(r, points=r.points[:-1]),
        lambda r: replace(r, points=(replace(r.points[0], mean=0.3), *r.points[1:])),
        lambda r: replace(r, points=(replace(r.points[0], components=((0.0,) * 3,) * 3), *r.points[1:])),
        lambda r: replace(r, points=(replace(r.points[0], raw_values=(float("nan"),) * 3), *r.points[1:])),
        lambda r: replace(r, points=(replace(r.points[0], error_bound=-1.0), *r.points[1:])),
        lambda r: replace(r, points=(replace(r.points[0], resolved=1), *r.points[1:])),
    ),
)
def test_malformed_typed_reference_propagates_before_comparison(monkeypatch, mutation):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    def reference(counts, **kwargs):
        return mutation(mocked_reference(counts, **kwargs))

    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    comparisons = Mock(side_effect=AssertionError("malformed reference reached guard"))
    monkeypatch.setattr(quantities, "dependence_comparisons", comparisons)
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)
    comparisons.assert_not_called()


@pytest.mark.parametrize(
    "bad",
    (
        object(),
        DependenceComparisons("wrong", ((1,) * 4,) * 3, None),
        DependenceComparisons("resolved", ((True,) * 4,) * 3, (1,) * 4),
        DependenceComparisons("resolved", ((1,) * 4,) * 3, None),
        DependenceComparisons("resolved", ((-1,) * 4,) * 3, (-1,) * 4),
        DependenceComparisons("dependence_rank_order_unresolved", ((1,) * 4,) * 3, (1,) * 4),
    ),
)
def test_malformed_comparison_propagates(monkeypatch, bad):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, "dependence_comparisons", Mock(return_value=bad))
    rank_spy = Mock(wraps=randomized_rank)
    monkeypatch.setattr(quantities, "randomized_rank", rank_spy)
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)
    assert rank_spy.call_count == 5


@pytest.mark.parametrize("bad", (True, np.bool_(False), 2.0, -1, 5, None))
def test_malformed_rank_propagates(monkeypatch, bad):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, "randomized_rank", Mock(return_value=bad))
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)


@pytest.mark.parametrize(
    "truth,draws",
    (
        (True, (1, 2, 3, 4)),
        (13, (1, 2, 3, 4)),
        (0, (0, 1, 2, 3)),
        (0, (1, 1, 2, 3)),
        (0, (-1, 2, 3, 4)),
        (0, (1, 2, 3, 13)),
        (0, (True, 2, 3, 4)),
        (0, (1, 2, 3)),
        (0, [1, 2, 3, 4]),
    ),
)
def test_public_comparison_binding_refuses_bad_indices(monkeypatch, truth, draws):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    comparisons = result.ranks[5].comparisons
    require_quantity_comparisons(
        comparisons, reference=result.reference, truth_index=0, draw_indices=(1, 2, 3, 4)
    )
    with pytest.raises(ValueError):
        require_quantity_comparisons(
            comparisons, reference=result.reference, truth_index=truth, draw_indices=draws
        )


def test_future_call_failure_preserves_training_and_reference(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    real_mass = quantities.heterogeneity_log_mass
    calls = []

    def log_mass(ac, an, *, mean, rho):
        calls.append((ac, an))
        if len(calls) == 17:
            raise KeyError("future-call")
        return real_mass(ac, an, mean=mean, rho=rho)

    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert calls == [(row.ac, row.an) for row in data.training] + [(0, 20)]
    assert result.scalar_quantities[3].values is not None
    future = result.scalar_quantities[4]
    assert future.values is None and future.failed_training_row is None
    assert future.error == DiagnosticCallError("builtins.KeyError", "'future-call'")
    assert reference.call_count == 1
    assert all(result.ranks[mode * 6 + 4].status == "quantity_failed" for mode in range(3))
    assert sum(entry.status == "ranked" for entry in result.ranks) == 15


def test_accumulation_overflow_is_not_invented_oracle_failure(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    log_mass = Mock(return_value=np.full(13, -1.7e308, dtype=np.float64))
    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    with pytest.raises(ArithmeticError, match="accumulation"):
        selected_sbc_quantities(data, attempt=attempt)
    assert log_mass.call_count == 2
    reference.assert_not_called()


def test_selection_and_base_exception_propagate(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    class BrokenSelection:
        def integers(self, low, high):
            raise RuntimeError("selection")

    with monkeypatch.context() as patch:
        patch.setattr(quantities.np.random, "Generator", lambda bitgen: BrokenSelection())
        with pytest.raises(RuntimeError, match="selection"):
            selected_sbc_quantities(data, attempt=attempt)
    monkeypatch.setattr(
        quantities, "heterogeneity_dependence_reference", Mock(side_effect=KeyboardInterrupt())
    )
    with pytest.raises(KeyboardInterrupt):
        selected_sbc_quantities(data, attempt=attempt)


def test_immutable_and_inconsistent_result_states(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    with pytest.raises(FrozenInstanceError):
        result.ranks = ()
    for changes in (
        {"point_slots": (0,)},
        {"ranks": result.ranks[::-1]},
        {"selected_indices": ((0, 500), (1, 0), (2, 0), (3, 0))},
        {"reference_error": DiagnosticCallError("builtins.ValueError", "fabricated")},
    ):
        with pytest.raises(ValueError):
            replace(result, **changes)
    ranked = result.ranks[0]
    for changes in (
        {"rank": True},
        {"status": "control_failed"},
        {"error": DiagnosticCallError("builtins.ValueError", "fabricated")},
    ):
        with pytest.raises(ValueError):
            replace(ranked, **changes)
    scalar = result.scalar_quantities[0]
    with pytest.raises(ValueError):
        replace(scalar, values=None)
    with pytest.raises(ValueError):
        replace(scalar, values=(float("nan"),) * 13)


def test_actual_reference_on_one_valid_mixed_an_case(monkeypatch):
    """Integration only: real reference/guard, synthetic accepted fit and control."""
    monkeypatch.setattr(quantities, "draw_prior_control", literal_control)
    actual_reference = Mock(wraps=heterogeneity_dependence_reference)
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", actual_reference)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    assert actual_reference.call_count == 1
    assert result.reference_error is None
    require_quantity_reference(result.reference, points=result.points)
    assert result.reference.orders == (64, 128, 256)
    assert result.reference.analytic_separability is False
    assert all(entry.values is not None for entry in result.scalar_quantities)
    for mode, draw_indices in enumerate(((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12))):
        expected = dependence_comparisons(result.reference, truth_index=0, draw_indices=draw_indices)
        entry = result.ranks[mode * 6 + 5]
        assert entry.comparisons == expected
        if expected.status == "resolved":
            assert entry.status == "ranked"
            assert entry.rank == randomized_rank(0, expected.comparisons, seed=entry.seed.scalar_uint128)
        else:
            assert entry.status == expected.status and entry.rank is None


@pytest.mark.parametrize("quantity", (3, 4))
@pytest.mark.parametrize("length", (0, 12, 14, 9))
def test_outer_scalar_vectors_match_complete_control_point_count(monkeypatch, quantity, length):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    scalar = replace(result.scalar_quantities[quantity], values=(0.25,) * length)
    scalars = (*result.scalar_quantities[:quantity], scalar, *result.scalar_quantities[quantity + 1 :])
    with pytest.raises(ValueError, match="scalar vector length"):
        replace(result, scalar_quantities=scalars)


@pytest.mark.parametrize("quantity", (3, 4))
@pytest.mark.parametrize("length", (0, 8, 10, 13))
def test_outer_scalar_vectors_match_failed_control_point_count(monkeypatch, quantity, length):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    def failed_control(*, seed):
        return PriorControlResult(
            seed,
            ((0.25, 0.125),) * 3,
            PriorControlFailure(3, "rho", "rounded_boundary", 0.375, 0.0, None, None),
        )

    monkeypatch.setattr(quantities, "draw_prior_control", failed_control)
    result = selected_sbc_quantities(data, attempt=attempt)
    scalar = replace(result.scalar_quantities[quantity], values=(0.25,) * length)
    scalars = (*result.scalar_quantities[:quantity], scalar, *result.scalar_quantities[quantity + 1 :])
    with pytest.raises(ValueError, match="scalar vector length"):
        replace(result, scalar_quantities=scalars)


@pytest.mark.parametrize("quantity", (0, 5))
def test_outer_rejects_control_failed_rank_when_parent_control_completed(monkeypatch, quantity):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    index = 6 + quantity
    failed = replace(result.ranks[index], status="control_failed", rank=None, comparisons=None, error=None)
    ranks = (*result.ranks[:index], failed, *result.ranks[index + 1 :])
    with pytest.raises(ValueError, match="control failure"):
        replace(result, ranks=ranks)


def test_outer_retains_true_failed_control_mode_one_ranks(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    def failed_control(*, seed):
        return PriorControlResult(
            seed,
            ((0.25, 0.125),) * 3,
            PriorControlFailure(3, "rho", "rounded_boundary", 0.375, 0.0, None, None),
        )

    monkeypatch.setattr(quantities, "draw_prior_control", failed_control)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert all(entry.status == "control_failed" for entry in result.ranks[6:12])
    assert replace(result) == result

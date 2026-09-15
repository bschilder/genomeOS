"""Contract fixtures for one declared B0H fit attempt (design §§5, 7–8, 12)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock

import numpy as np
import pytest

from genomeos.surfaces import reference_heterogeneity
from genomeos.surfaces.heterogeneity_types import (
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    PopulationHeterogeneityFit,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation import heterogeneity_attempts as attempts
from genomeos.validation.heterogeneity_attempts import (
    AttemptError,
    FitAttemptResult,
    FitAttemptSpec,
    FitIdentityError,
    StructuralCheckResult,
    exercise_unavailable,
    plan_fit_attempt,
    require_fit_identity,
    run_fit_attempt,
)
from genomeos.validation.heterogeneity_simulation import (
    AllUnavailableDataset,
    GeneratedDataset,
    GenerationFailure,
    SbcCaseId,
    generate_sbc_case,
    sbc_seed_identity,
)
from genomeos.validation.reference_counts import ReferenceInfeasibleError


def _generated(case: SbcCaseId) -> GeneratedDataset:
    result = generate_sbc_case(case)
    assert isinstance(result, GeneratedDataset)
    return result


@pytest.fixture
def data() -> GeneratedDataset:
    """Small fixed mean=.05, rho=.1, sixteen-AN20 metadata fixture."""
    return _generated(SbcCaseId(0, 1, 13, 0))


def _training_counts(
    data: GeneratedDataset,
    *,
    variant_id: str | None = None,
    rows: tuple[object, ...] | None = None,
) -> tuple[VariantTrainingCounts, ...]:
    selected = data.training if rows is None else rows
    available = tuple(row for row in selected if row.an > 0)  # type: ignore[attr-defined]
    variant = data.training[0].variant_id if variant_id is None else variant_id
    return (
        VariantTrainingCounts(
            variant,
            len(available),
            sum(row.ac for row in available),  # type: ignore[attr-defined]
            sum(row.an for row in available),  # type: ignore[attr-defined]
        ),
    )


def _mocked_fit(
    data: GeneratedDataset,
    spec: FitAttemptSpec,
    *,
    config: PopulationHeterogeneityConfig | None = None,
    variant_id: str | None = None,
    training_record_ids: tuple[str, ...] | None = None,
    training_group_ids: tuple[str, ...] | None = None,
    unavailable_training_ids: tuple[str, ...] | None = None,
    training_counts: tuple[VariantTrainingCounts, ...] | None = None,
) -> PopulationHeterogeneityFit:
    """Create a typed mock-metadata fit; these are not measured sampler diagnostics."""
    fit_config = spec.config if config is None else config
    variant = data.training[0].variant_id if variant_id is None else variant_id
    record_ids = (
        tuple(sorted(row.record_id for row in data.training))
        if training_record_ids is None
        else training_record_ids
    )
    group_ids = (
        tuple(sorted({row.group_id for row in data.training}))
        if training_group_ids is None
        else training_group_ids
    )
    unavailable = (
        tuple(sorted(row.record_id for row in data.training if row.an == 0))
        if unavailable_training_ids is None
        else unavailable_training_ids
    )
    counts = _training_counts(data, variant_id=variant) if training_counts is None else training_counts
    shape = (fit_config.chains, fit_config.draws, 1)
    return PopulationHeterogeneityFit(
        config=fit_config,
        variant_ids=(variant,),
        mean_draws=np.full(shape, 0.25, dtype=np.float64),
        rho_draws=np.full(shape, 0.2, dtype=np.float64),
        training_record_ids=record_ids,
        training_group_ids=group_ids,
        unavailable_training_ids=unavailable,
        training_counts=counts,
        diagnostics=(VariantHeterogeneityDiagnostics(variant, 1.0, 200.0, 200.0),),
        divergence_count=0,
    )


def _run_fake(
    monkeypatch: pytest.MonkeyPatch,
    data: GeneratedDataset,
    spec: FitAttemptSpec,
    returned: object,
) -> tuple[FitAttemptResult, list[tuple[object, PopulationHeterogeneityConfig]]]:
    calls: list[tuple[object, PopulationHeterogeneityConfig]] = []

    def fake_fit(training: object, *, config: PopulationHeterogeneityConfig) -> object:
        calls.append((training, config))
        if isinstance(returned, BaseException):
            raise returned
        return returned

    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", fake_fit)
    return run_fit_attempt(data, spec=spec), calls


def test_initial_attempt_uses_literal_declared_seed() -> None:
    data = _generated(SbcCaseId(0, 0, 0, 0))
    spec = plan_fit_attempt(data, attempt_id=0)
    assert spec.seed.entropy == (42, 211, 1, 0, 0, 0, 0, 4, 0)
    assert spec.config == PopulationHeterogeneityConfig(
        mean_prior_alpha=1.0,
        mean_prior_beta=1.0,
        rho_prior_alpha=1.0,
        rho_prior_beta=9.0,
        draws=500,
        tune=1000,
        chains=4,
        target_accept=0.9,
        seed=279725986,
    )


def test_retry_changes_only_budget_and_declared_seed() -> None:
    data = _generated(SbcCaseId(0, 0, 0, 0))
    first = plan_fit_attempt(data, attempt_id=0)
    retry = plan_fit_attempt(data, attempt_id=1)
    assert retry.seed.entropy == (42, 211, 1, 0, 0, 0, 0, 4, 1)
    assert retry.config == replace(first.config, draws=1000, tune=2000, seed=2209982770)


def test_track_one_uses_literal_prior_and_seed_anchors() -> None:
    data = _generated(SbcCaseId(1, 0, 0, 0))
    initial = plan_fit_attempt(data, attempt_id=0)
    retry = plan_fit_attempt(data, attempt_id=1)
    assert initial.seed.entropy == (42, 211, 1, 1, 0, 0, 0, 4, 0)
    assert initial.config == PopulationHeterogeneityConfig(1, 1, 1, 4, 500, 1000, 4, 0.9, 848552836)
    assert retry.seed.entropy == (42, 211, 1, 1, 0, 0, 0, 4, 1)
    assert retry.config == PopulationHeterogeneityConfig(1, 1, 1, 4, 1000, 2000, 4, 0.9, 1074711532)


@pytest.mark.parametrize("attempt_id", (True, 2, -1))
def test_planner_rejects_invalid_attempt_domains(attempt_id: object, data: GeneratedDataset) -> None:
    with pytest.raises(ValueError, match="attempt_id"):
        plan_fit_attempt(data, attempt_id=attempt_id)  # type: ignore[arg-type]


def test_planner_rejects_failure_structural_and_wrong_inputs() -> None:
    prior = _generated(SbcCaseId(0, 0, 0, 0))
    failure = GenerationFailure(
        prior.case_id,
        prior.provenance,
        "truth_validation",
        None,
        "rounded_prior_boundary",
        None,
        0.0,
        0.1,
        0.0,
        None,
        None,
    )
    structural = generate_sbc_case(SbcCaseId(0, 3, 0, 0))
    assert isinstance(structural, AllUnavailableDataset)
    for malformed in (failure, structural, object(), None):
        with pytest.raises(ValueError, match="GeneratedDataset"):
            plan_fit_attempt(malformed, attempt_id=0)  # type: ignore[arg-type]


def test_spec_refuses_wrong_entropy_and_config(data: GeneratedDataset) -> None:
    planned = plan_fit_attempt(data, attempt_id=0)
    wrong_seed = sbc_seed_identity(SbcCaseId(1, 1, 13, 0), purpose_id=4, attempt_id=0)
    with pytest.raises(ValueError, match="planned"):
        FitAttemptSpec(data.case_id, 0, wrong_seed, planned.config)
    with pytest.raises(ValueError, match="planned"):
        FitAttemptSpec(data.case_id, 0, planned.seed, replace(planned.config, target_accept=0.8))


def test_planner_refuses_fit_seed_collision_without_reseeding(
    monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset
) -> None:
    seed_type = type(sbc_seed_identity(data.case_id, purpose_id=4, attempt_id=0))
    monkeypatch.setattr(seed_type, "fit_uint32", property(lambda self: 7))
    with pytest.raises(ValueError, match="collide"):
        plan_fit_attempt(data, attempt_id=0)


@pytest.mark.parametrize("track", (0, 1))
@pytest.mark.parametrize("attempt_id", (0, 1))
def test_each_explicit_track_attempt_invokes_once_with_exact_rows_and_config(
    monkeypatch: pytest.MonkeyPatch, track: int, attempt_id: int
) -> None:
    data = _generated(SbcCaseId(track, 1, 13, 0))
    spec = plan_fit_attempt(data, attempt_id=attempt_id)
    fitted = _mocked_fit(data, spec)
    result, calls = _run_fake(monkeypatch, data, spec, fitted)
    assert result == FitAttemptResult(spec, "accepted", fitted, None, (), None)
    assert result.fit is fitted
    assert calls == [(data.training, spec.config)]


def test_mocked_public_return_is_preserved(monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    mocked_fit = _mocked_fit(data, spec)
    result, calls = _run_fake(monkeypatch, data, spec, mocked_fit)
    assert result.status == "accepted"
    assert result.fit is mocked_fit
    assert calls == [(data.training, spec.config)]
    assert result.error is None and result.identity_mismatches == ()


def test_shared_paired_stress_is_not_batched(monkeypatch: pytest.MonkeyPatch) -> None:
    left = _generated(SbcCaseId(0, 2, 3, 0))
    right = _generated(SbcCaseId(1, 2, 3, 0))
    left_spec = plan_fit_attempt(left, attempt_id=0)
    right_spec = plan_fit_attempt(right, attempt_id=0)
    left_result, left_calls = _run_fake(monkeypatch, left, left_spec, _mocked_fit(left, left_spec))
    right_result, right_calls = _run_fake(monkeypatch, right, right_spec, _mocked_fit(right, right_spec))
    assert left.training == right.training
    assert left_spec.config.rho_prior_beta == 9.0
    assert right_spec.config.rho_prior_beta == 4.0
    assert left_spec.seed != right_spec.seed
    assert left_result.status == right_result.status == "accepted"
    assert left_calls == [(left.training, left_spec.config)]
    assert right_calls == [(right.training, right_spec.config)]


def test_mixed_an_passes_all_rows_and_checks_lexical_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _generated(SbcCaseId(0, 0, 0, 0))
    spec = plan_fit_attempt(data, attempt_id=0)
    fit = _mocked_fit(data, spec)
    result, calls = _run_fake(monkeypatch, data, spec, fit)
    row_ids = tuple(sorted(row.record_id for row in data.training))
    assert len(calls[0][0]) == 16  # type: ignore[arg-type]
    assert calls == [(data.training, spec.config)]
    assert row_ids.index(next(item for item in row_ids if item.endswith("row:10"))) < row_ids.index(
        next(item for item in row_ids if item.endswith("row:2"))
    )
    assert fit.training_record_ids == row_ids
    assert fit.unavailable_training_ids == tuple(
        sorted(row.record_id for row in data.training if row.an == 0)
    )
    assert fit.training_counts == _training_counts(data)
    assert result.status == "accepted"


@pytest.mark.parametrize(
    ("diagnostics", "divergence_count"),
    (
        ((), None),
        ((), 0),
        ((VariantHeterogeneityDiagnostics("variant", 1.0, 200.0, 200.0),), 3),
    ),
)
def test_convergence_failure_preserves_sparse_or_full_metadata(
    monkeypatch: pytest.MonkeyPatch,
    data: GeneratedDataset,
    diagnostics: tuple[VariantHeterogeneityDiagnostics, ...],
    divergence_count: int | None,
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    error = HeterogeneityConvergenceError(
        "fixed convergence refusal", diagnostics=diagnostics, divergence_count=divergence_count
    )
    result, calls = _run_fake(monkeypatch, data, spec, error)
    assert calls == [(data.training, spec.config)]
    assert result.status == "convergence_failed" and result.fit is None
    assert result.error == AttemptError(
        "convergence",
        "genomeos.surfaces.heterogeneity_types.HeterogeneityConvergenceError",
        "fixed convergence refusal",
        "fixed convergence refusal",
        diagnostics,
        divergence_count,
    )
    assert result.identity_mismatches == () and result.returned_type is None


@pytest.mark.parametrize(
    ("error", "category"),
    (
        (ReferenceInfeasibleError("none available"), "reference_infeasible"),
        (ValueError("bad value"), "value"),
        (OverflowError("overflow"), "arithmetic"),
        (FloatingPointError("float"), "arithmetic"),
        (ArithmeticError("math"), "arithmetic"),
        (RuntimeError("runtime"), "runtime"),
    ),
)
def test_known_execution_errors_are_lossless_and_never_retry(
    monkeypatch: pytest.MonkeyPatch,
    data: GeneratedDataset,
    error: Exception,
    category: str,
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    result, calls = _run_fake(monkeypatch, data, spec, error)
    assert calls == [(data.training, spec.config)]
    assert result == FitAttemptResult(
        spec,
        "failed",
        None,
        AttemptError(
            category,
            f"{type(error).__module__}.{type(error).__qualname__}",
            str(error),
            None,
            None,
            None,
        ),
        (),
        None,
    )


class UnknownExecutionError(Exception):
    pass


@pytest.mark.parametrize("error", (UnknownExecutionError("unknown"), KeyboardInterrupt(), SystemExit()))
def test_unknown_and_base_exceptions_propagate_unchanged(
    monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset, error: BaseException
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    calls: list[tuple[object, PopulationHeterogeneityConfig]] = []

    def fake_fit(training: object, *, config: PopulationHeterogeneityConfig) -> object:
        calls.append((training, config))
        raise error

    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", fake_fit)
    with pytest.raises(type(error)) as caught:
        run_fit_attempt(data, spec=spec)
    assert caught.value is error
    assert calls == [(data.training, spec.config)]


@pytest.mark.parametrize(
    "config",
    (
        PopulationHeterogeneityConfig(2, 1, 1, 9, seed=279725986),
        PopulationHeterogeneityConfig(1, 1, 1, 9, seed=7),
    ),
)
def test_returned_prior_or_seed_config_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset, config: PopulationHeterogeneityConfig
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    fit = _mocked_fit(data, spec, config=config)
    result, _ = _run_fake(monkeypatch, data, spec, fit)
    assert result.status == "identity_rejected" and result.fit is fit
    assert result.identity_mismatches == ("config",)


def test_returned_budget_and_axes_mismatches_are_all_retained(
    monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    config = replace(spec.config, draws=501)
    fit = _mocked_fit(data, spec, config=config)
    result, _ = _run_fake(monkeypatch, data, spec, fit)
    assert result.fit is fit
    assert result.identity_mismatches == ("config", "mean_draws.shape", "rho_draws.shape")


def test_returned_variant_mismatches_are_all_retained(
    monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    fit = _mocked_fit(data, spec, variant_id="synthetic:other:variant:0")
    result, _ = _run_fake(monkeypatch, data, spec, fit)
    assert result.fit is fit
    assert result.identity_mismatches == ("variant_ids", "training_counts")


def test_returned_record_and_counts_joint_mismatch_is_legal_and_rejected(
    monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    removed = data.training[0]
    remaining = tuple(row for row in data.training if row.record_id != removed.record_id)
    fit = _mocked_fit(
        data,
        spec,
        training_record_ids=tuple(sorted(row.record_id for row in remaining)),
        training_counts=_training_counts(data, rows=remaining),
    )
    result, _ = _run_fake(monkeypatch, data, spec, fit)
    assert result.identity_mismatches == ("training_record_ids", "training_counts")


def test_returned_group_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    fit = _mocked_fit(data, spec, training_group_ids=("wrong-group",))
    result, _ = _run_fake(monkeypatch, data, spec, fit)
    assert result.identity_mismatches == ("training_group_ids",)


def test_returned_unavailable_and_counts_joint_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _generated(SbcCaseId(0, 0, 0, 0))
    spec = plan_fit_attempt(data, attempt_id=0)
    unavailable = tuple(sorted(row.record_id for row in data.training if row.an == 0))
    fit = _mocked_fit(
        data,
        spec,
        unavailable_training_ids=unavailable[1:],
        training_counts=(
            replace(_training_counts(data)[0], training_observation_count=15),
        ),
    )
    result, _ = _run_fake(monkeypatch, data, spec, fit)
    assert result.identity_mismatches == ("unavailable_training_ids", "training_counts")


def test_returned_count_totals_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch, data: GeneratedDataset
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    expected = _training_counts(data)[0]
    replacement_ac = expected.training_ac - 1 if expected.training_ac else 1
    fit = _mocked_fit(data, spec, training_counts=(replace(expected, training_ac=replacement_ac),))
    result, _ = _run_fake(monkeypatch, data, spec, fit)
    assert result.identity_mismatches == ("training_counts",)


@pytest.mark.parametrize(
    ("returned", "qualified"),
    ((None, "builtins.NoneType"), (object(), "builtins.object")),
)
def test_wrong_return_type_records_only_actual_qualified_type(
    monkeypatch: pytest.MonkeyPatch,
    data: GeneratedDataset,
    returned: object,
    qualified: str,
) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    result, calls = _run_fake(monkeypatch, data, spec, returned)
    assert calls == [(data.training, spec.config)]
    assert result == FitAttemptResult(
        spec, "identity_rejected", None, None, ("return_type",), qualified
    )


def test_public_identity_guard_returns_none_or_structured_error(data: GeneratedDataset) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    assert require_fit_identity(data, spec=spec, fit=_mocked_fit(data, spec)) is None
    wrong = _mocked_fit(data, spec, config=replace(spec.config, draws=501))
    with pytest.raises(FitIdentityError) as caught:
        require_fit_identity(data, spec=spec, fit=wrong)
    assert caught.value.mismatches == ("config", "mean_draws.shape", "rho_draws.shape")
    with pytest.raises(FitIdentityError) as wrong_type:
        require_fit_identity(data, spec=spec, fit=object())  # type: ignore[arg-type]
    assert wrong_type.value.mismatches == ("return_type",)


def test_invalid_callers_are_rejected_before_public_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _generated(SbcCaseId(0, 1, 13, 0))
    other = _generated(SbcCaseId(1, 1, 13, 0))
    call = Mock(side_effect=AssertionError("fitter must not be called"))
    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", call)
    with pytest.raises(ValueError, match="planned"):
        run_fit_attempt(data, spec=plan_fit_attempt(other, attempt_id=0))
    with pytest.raises(ValueError, match="GeneratedDataset"):
        run_fit_attempt(object(), spec=plan_fit_attempt(data, attempt_id=0))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="FitAttemptSpec"):
        run_fit_attempt(data, spec=object())  # type: ignore[arg-type]
    assert call.call_count == 0


def test_contract_states_are_frozen_and_reject_invalid_combinations(data: GeneratedDataset) -> None:
    spec = plan_fit_attempt(data, attempt_id=0)
    fit = _mocked_fit(data, spec)
    error = AttemptError("value", "builtins.ValueError", "bad", None, None, None)
    accepted = FitAttemptResult(spec, "accepted", fit, None, (), None)
    with pytest.raises(FrozenInstanceError):
        accepted.status = "failed"  # type: ignore[misc]
    for args in (
        (spec, "accepted", None, None, (), None),
        (spec, "accepted", fit, error, (), None),
        (spec, "failed", None, None, (), None),
        (spec, "identity_rejected", fit, None, (), None),
        (spec, "identity_rejected", None, None, ("return_type",), None),
        (spec, "identity_rejected", fit, None, ("return_type",), None),
    ):
        with pytest.raises(ValueError):
            FitAttemptResult(*args)
    with pytest.raises(ValueError):
        FitIdentityError(("training_counts", "config"))
    with pytest.raises(ValueError):
        FitIdentityError(("config", "config"))
    with pytest.raises(ValueError):
        FitIdentityError(("return_type", "config"))
    identity_error = FitIdentityError(("config",))
    with pytest.raises(AttributeError):
        identity_error.mismatches = ("training_counts",)  # type: ignore[misc]


@pytest.mark.parametrize(
    "args",
    (
        ("bad", "builtins.ValueError", "", None, None, None),
        ("value", "", "", None, None, None),
        ("value", "builtins.ValueError", "", "reason", None, None),
        ("value", "builtins.ValueError", "", None, (), None),
        ("convergence", "builtins.RuntimeError", "", None, (), None),
        ("convergence", "builtins.RuntimeError", "", "reason", None, None),
        ("convergence", "builtins.RuntimeError", "", "reason", [], None),
        ("convergence", "builtins.RuntimeError", "", "reason", (), True),
        ("convergence", "builtins.RuntimeError", "", "reason", (), -1),
    ),
)
def test_attempt_error_rejects_bad_category_reason_count_and_types(args: tuple[object, ...]) -> None:
    with pytest.raises(ValueError):
        AttemptError(*args)  # type: ignore[arg-type]


@pytest.mark.parametrize("track", (0, 1))
def test_actual_structural_refusal_occurs_before_model_and_sample(
    monkeypatch: pytest.MonkeyPatch, track: int
) -> None:
    dataset = generate_sbc_case(SbcCaseId(track, 3, 0, 0))
    assert isinstance(dataset, AllUnavailableDataset)
    model = Mock(side_effect=AssertionError("pm.Model must not be entered"))
    sample = Mock(side_effect=AssertionError("pm.sample must not be entered"))
    monkeypatch.setattr(reference_heterogeneity.pm, "Model", model)
    monkeypatch.setattr(reference_heterogeneity.pm, "sample", sample)
    result = exercise_unavailable(dataset)
    assert result.case == dataset.case_id
    assert result.status == "expected_refusal"
    assert result.error == AttemptError(
        "reference_infeasible",
        "genomeos.validation.reference_counts.ReferenceInfeasibleError",
        "training data have no available rows",
        None,
        None,
        None,
    )
    assert result.fit is None and result.returned_type is None
    assert result.expected_sampler_calls == 0
    assert model.call_count == sample.call_count == 0


@pytest.mark.parametrize(
    ("returned", "status", "category", "returned_type"),
    (
        (ValueError("bad"), "unexpected_exception", "unexpected_exception", None),
        (None, "unexpected_return", None, "builtins.NoneType"),
        (object(), "unexpected_return", None, "builtins.object"),
    ),
)
def test_structural_alternate_outcomes_are_typed_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    returned: object,
    status: str,
    category: str | None,
    returned_type: str | None,
) -> None:
    dataset = generate_sbc_case(SbcCaseId(0, 3, 0, 0))
    assert isinstance(dataset, AllUnavailableDataset)
    calls: list[tuple[object, PopulationHeterogeneityConfig]] = []

    def fake_fit(training: object, *, config: PopulationHeterogeneityConfig) -> object:
        calls.append((training, config))
        if isinstance(returned, BaseException):
            raise returned
        return returned

    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", fake_fit)
    result = exercise_unavailable(dataset)
    assert result.status == status and len(calls) == 1
    assert calls[0][0] == dataset.training
    assert calls[0][1] == PopulationHeterogeneityConfig(1, 1, 1, 9, 500, 1000, 4, 0.9, 42)
    assert result.returned_type == returned_type and result.fit is None
    assert (None if result.error is None else result.error.category) == category


def test_structural_typed_unexpected_return_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    structural = generate_sbc_case(SbcCaseId(0, 3, 0, 0))
    data = _generated(SbcCaseId(0, 1, 13, 0))
    assert isinstance(structural, AllUnavailableDataset)
    spec = plan_fit_attempt(data, attempt_id=0)
    fit = _mocked_fit(data, spec)
    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", lambda *a, **k: fit)
    result = exercise_unavailable(structural)
    assert result == StructuralCheckResult(structural.case_id, "unexpected_return", None, fit, None)


@pytest.mark.parametrize("error", (KeyboardInterrupt(), SystemExit()))
def test_structural_base_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    dataset = generate_sbc_case(SbcCaseId(0, 3, 0, 0))
    assert isinstance(dataset, AllUnavailableDataset)

    def fake_fit(*args: object, **kwargs: object) -> object:
        raise error

    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", fake_fit)
    with pytest.raises(type(error)) as caught:
        exercise_unavailable(dataset)
    assert caught.value is error


def test_structural_contract_rejects_wrong_case_and_state(data: GeneratedDataset) -> None:
    error = AttemptError(
        "reference_infeasible", "builtins.ValueError", "no rows", None, None, None
    )
    with pytest.raises(ValueError, match="study 3"):
        StructuralCheckResult(data.case_id, "expected_refusal", error, None, None)
    case = SbcCaseId(0, 3, 0, 0)
    for args in (
        (case, "expected_refusal", None, None, None),
        (case, "unexpected_exception", error, None, None),
        (case, "unexpected_return", error, None, None),
        (case, "unexpected_return", None, None, None),
    ):
        with pytest.raises(ValueError):
            StructuralCheckResult(*args)


def test_exercise_unavailable_rejects_nonstructural_input() -> None:
    with pytest.raises(ValueError, match="AllUnavailableDataset"):
        exercise_unavailable(_generated(SbcCaseId(0, 1, 13, 0)))  # type: ignore[arg-type]

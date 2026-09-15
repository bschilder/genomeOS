"""One-call B0H fit-attempt accounting (design §§5, 7–8, 12; #211).

This pure boundary binds a generated case to one declared public fitter call.
It records known realized failures and refuses returned fits whose public
identity differs from the requested case. Durable retry/checkpoint policy and
scientific calibration remain outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from genomeos.surfaces.heterogeneity_types import (
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    PopulationHeterogeneityFit,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.surfaces.reference_heterogeneity import (
    fit_reference_population_heterogeneity,
)
from genomeos.validation.heterogeneity_simulation import (
    AllUnavailableDataset,
    GeneratedDataset,
    SbcCaseId,
    SeedIdentity,
    sbc_seed_identity,
)
from genomeos.validation.heterogeneity_simulation_types import simulation_integer
from genomeos.validation.reference_counts import ReferenceInfeasibleError

SEED = 42

_ERROR_CATEGORIES = {
    "convergence",
    "reference_infeasible",
    "value",
    "arithmetic",
    "runtime",
    "unexpected_exception",
}
_IDENTITY_FIELDS = (
    "config",
    "variant_ids",
    "mean_draws.shape",
    "rho_draws.shape",
    "training_record_ids",
    "training_group_ids",
    "unavailable_training_ids",
    "training_counts",
    "return_type",
)


def _qualified_type(value: object) -> str:
    kind = type(value)
    return f"{kind.__module__}.{kind.__qualname__}"


def _literal(value: object, name: str, *, qualified: bool = False) -> str:
    if not isinstance(value, str) or not value.strip() or qualified and "." not in value:
        qualifier = " qualified" if qualified else ""
        raise ValueError(f"{name} must be a nonempty{qualifier} string")
    return value


def _normalized_case(case: object, *, allow_structural: bool) -> SbcCaseId:
    if not isinstance(case, SbcCaseId):
        raise ValueError("case must be an SbcCaseId")
    normalized = SbcCaseId(**vars(case))
    if (normalized.study_id == 3) != allow_structural:
        domain = "study 3" if allow_structural else "a nonstructural study"
        raise ValueError(f"case must belong to {domain}")
    return normalized


def _planned_fit_metadata(
    case: SbcCaseId, attempt_id: object
) -> tuple[int, SeedIdentity, PopulationHeterogeneityConfig]:
    normalized_case = _normalized_case(case, allow_structural=False)
    attempt = simulation_integer(attempt_id, "attempt_id")
    if attempt not in (0, 1):
        raise ValueError("attempt_id must be 0 or 1")
    initial = sbc_seed_identity(normalized_case, purpose_id=4, attempt_id=0)
    retry = sbc_seed_identity(normalized_case, purpose_id=4, attempt_id=1)
    if initial.fit_uint32 == retry.fit_uint32:
        raise ValueError("planned fit seeds collide")
    seed = (initial, retry)[attempt]
    fit_seed = seed.fit_uint32
    if fit_seed is None:  # pragma: no cover - SeedIdentity purpose 4 guarantees this
        raise ValueError("planned fit seed is unavailable")
    config = PopulationHeterogeneityConfig(
        mean_prior_alpha=1.0,
        mean_prior_beta=1.0,
        rho_prior_alpha=1.0,
        rho_prior_beta=9.0 if normalized_case.track_id == 0 else 4.0,
        draws=500 if attempt == 0 else 1000,
        tune=1000 if attempt == 0 else 2000,
        chains=4,
        target_accept=0.9,
        seed=fit_seed,
    )
    return attempt, seed, config


@dataclass(frozen=True)
class FitAttemptSpec:
    """One exact case, budget and purpose-4 seed requested for fitting."""

    case: SbcCaseId
    attempt_id: int
    seed: SeedIdentity
    config: PopulationHeterogeneityConfig

    def __post_init__(self) -> None:
        case = _normalized_case(self.case, allow_structural=False)
        attempt, expected_seed, expected_config = _planned_fit_metadata(case, self.attempt_id)
        if not isinstance(self.seed, SeedIdentity) or not isinstance(
            self.config, PopulationHeterogeneityConfig
        ):
            raise ValueError("seed and config must be their declared public types")
        seed = SeedIdentity(self.seed.entropy)
        config = PopulationHeterogeneityConfig(**vars(self.config))
        if seed != expected_seed or config != expected_config:
            raise ValueError("seed and config must match the complete planned fit attempt")
        object.__setattr__(self, "case", case)
        object.__setattr__(self, "attempt_id", attempt)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "config", config)


@dataclass(frozen=True)
class AttemptError:
    """Lossless metadata for one recognized fitter exception."""

    category: str
    exception_class: str
    message: str
    reason: str | None
    diagnostics: tuple[VariantHeterogeneityDiagnostics, ...] | None
    divergence_count: int | None

    def __post_init__(self) -> None:
        if type(self.category) is not str or self.category not in _ERROR_CATEGORIES:
            raise ValueError("category is not a declared attempt error category")
        exception_class = _literal(self.exception_class, "exception_class", qualified=True)
        if type(self.message) is not str:
            raise ValueError("message must be a literal string")
        if self.category == "convergence":
            reason = _literal(self.reason, "reason")
            if not isinstance(self.diagnostics, tuple) or any(
                not isinstance(item, VariantHeterogeneityDiagnostics)
                for item in self.diagnostics
            ):
                raise ValueError("convergence diagnostics must be an immutable typed tuple")
            count = self.divergence_count
            if count is not None:
                count = simulation_integer(count, "divergence_count")
                if count < 0:
                    raise ValueError("divergence_count must be nonnegative")
            object.__setattr__(self, "reason", reason)
            object.__setattr__(self, "divergence_count", count)
        elif self.reason is not None or self.diagnostics is not None or self.divergence_count is not None:
            raise ValueError("only convergence errors carry reason, diagnostics, or divergences")
        object.__setattr__(self, "exception_class", exception_class)


def _identity_mismatches(value: object, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(type(item) is not str for item in value):
        raise ValueError("identity_mismatches must be an immutable string tuple")
    mismatches = value
    if not mismatches and not allow_empty:
        raise ValueError("identity mismatches must be nonempty")
    if len(set(mismatches)) != len(mismatches) or any(
        item not in _IDENTITY_FIELDS for item in mismatches
    ):
        raise ValueError("identity mismatches must be unique closed field names")
    expected_order = tuple(field for field in _IDENTITY_FIELDS if field in mismatches)
    if mismatches != expected_order:
        raise ValueError("identity mismatches must follow the declared field order")
    if "return_type" in mismatches and mismatches != ("return_type",):
        raise ValueError("return_type is allowed only as the sole mismatch")
    return mismatches


class FitIdentityError(ValueError):
    """A returned fit differs from its generated dataset and planned attempt."""

    def __init__(self, mismatches: tuple[str, ...]) -> None:
        self._mismatches = _identity_mismatches(mismatches, allow_empty=False)
        super().__init__(f"fit identity mismatches: {', '.join(self.mismatches)}")

    @property
    def mismatches(self) -> tuple[str, ...]:
        """Return the immutable ordered closed mismatch fields."""
        return self._mismatches


@dataclass(frozen=True)
class FitAttemptResult:
    """One accepted, failed or identity-rejected public fitter invocation."""

    spec: FitAttemptSpec
    status: str
    fit: PopulationHeterogeneityFit | None
    error: AttemptError | None
    identity_mismatches: tuple[str, ...]
    returned_type: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.spec, FitAttemptSpec):
            raise ValueError("spec must be a FitAttemptSpec")
        mismatches = _identity_mismatches(self.identity_mismatches, allow_empty=True)
        returned_type = self.returned_type
        if returned_type is not None:
            returned_type = _literal(returned_type, "returned_type", qualified=True)
        accepted = (
            self.status == "accepted"
            and isinstance(self.fit, PopulationHeterogeneityFit)
            and self.fit.config == self.spec.config
            and self.error is None
            and not mismatches
            and returned_type is None
        )
        convergence_failed = (
            self.status == "convergence_failed"
            and self.fit is None
            and isinstance(self.error, AttemptError)
            and self.error.category == "convergence"
            and not mismatches
            and returned_type is None
        )
        failed = (
            self.status == "failed"
            and self.fit is None
            and isinstance(self.error, AttemptError)
            and self.error.category != "convergence"
            and not mismatches
            and returned_type is None
        )
        rejected_typed = (
            self.status == "identity_rejected"
            and isinstance(self.fit, PopulationHeterogeneityFit)
            and self.error is None
            and bool(mismatches)
            and mismatches != ("return_type",)
            and returned_type is None
        )
        rejected_wrong_type = (
            self.status == "identity_rejected"
            and self.fit is None
            and self.error is None
            and mismatches == ("return_type",)
            and returned_type is not None
        )
        if sum((accepted, convergence_failed, failed, rejected_typed, rejected_wrong_type)) != 1:
            raise ValueError("fit attempt fields do not match exactly one declared result state")
        object.__setattr__(self, "identity_mismatches", mismatches)
        object.__setattr__(self, "returned_type", returned_type)


@dataclass(frozen=True)
class StructuralCheckResult:
    """Actual outcome of the all-unavailable public-fitter structural check."""

    case: SbcCaseId
    status: str
    error: AttemptError | None
    fit: PopulationHeterogeneityFit | None
    returned_type: str | None

    def __post_init__(self) -> None:
        case = _normalized_case(self.case, allow_structural=True)
        returned_type = self.returned_type
        if returned_type is not None:
            returned_type = _literal(returned_type, "returned_type", qualified=True)
        expected_refusal = (
            self.status == "expected_refusal"
            and isinstance(self.error, AttemptError)
            and self.error.category == "reference_infeasible"
            and self.fit is None
            and returned_type is None
        )
        unexpected_exception = (
            self.status == "unexpected_exception"
            and isinstance(self.error, AttemptError)
            and self.error.category == "unexpected_exception"
            and self.fit is None
            and returned_type is None
        )
        unexpected_typed = (
            self.status == "unexpected_return"
            and self.error is None
            and isinstance(self.fit, PopulationHeterogeneityFit)
            and returned_type is None
        )
        unexpected_wrong_type = (
            self.status == "unexpected_return"
            and self.error is None
            and self.fit is None
            and returned_type is not None
        )
        if sum(
            (expected_refusal, unexpected_exception, unexpected_typed, unexpected_wrong_type)
        ) != 1:
            raise ValueError("structural fields do not match exactly one declared result state")
        object.__setattr__(self, "case", case)
        object.__setattr__(self, "returned_type", returned_type)

    @property
    def expected_sampler_calls(self) -> int:
        """Return the fixed sampler-call expectation, not an observed count."""
        return 0


def plan_fit_attempt(dataset: GeneratedDataset, *, attempt_id: int) -> FitAttemptSpec:
    """Plan one exact initial or retry invocation for an available generated case."""
    if not isinstance(dataset, GeneratedDataset):
        raise ValueError("dataset must be a GeneratedDataset")
    attempt, seed, config = _planned_fit_metadata(dataset.case_id, attempt_id)
    return FitAttemptSpec(dataset.case_id, attempt, seed, config)


def _require_planned_case(dataset: object, spec: object) -> GeneratedDataset:
    if not isinstance(dataset, GeneratedDataset):
        raise ValueError("dataset must be a GeneratedDataset")
    if not isinstance(spec, FitAttemptSpec):
        raise ValueError("spec must be a FitAttemptSpec")
    planned = plan_fit_attempt(dataset, attempt_id=spec.attempt_id)
    if spec != planned:
        raise ValueError("spec must be the complete planned attempt for dataset")
    return dataset


def require_fit_identity(
    dataset: GeneratedDataset,
    *,
    spec: FitAttemptSpec,
    fit: PopulationHeterogeneityFit,
) -> None:
    """Require all case-bound returned-fit fields in their fixed comparison order."""
    data = _require_planned_case(dataset, spec)
    if not isinstance(fit, PopulationHeterogeneityFit):
        raise FitIdentityError(("return_type",))
    variant_id = data.training[0].variant_id
    available = tuple(row for row in data.training if row.an > 0)
    expected_counts = (
        VariantTrainingCounts(
            variant_id,
            len(available),
            sum(row.ac for row in available),
            sum(row.an for row in available),
        ),
    )
    expected = {
        "config": spec.config,
        "variant_ids": (variant_id,),
        "mean_draws.shape": (4, spec.config.draws, 1),
        "rho_draws.shape": (4, spec.config.draws, 1),
        "training_record_ids": tuple(sorted(row.record_id for row in data.training)),
        "training_group_ids": tuple(sorted({row.group_id for row in data.training})),
        "unavailable_training_ids": tuple(
            sorted(row.record_id for row in data.training if row.an == 0)
        ),
        "training_counts": expected_counts,
    }
    actual = {
        "config": fit.config,
        "variant_ids": fit.variant_ids,
        "mean_draws.shape": fit.mean_draws.shape,
        "rho_draws.shape": fit.rho_draws.shape,
        "training_record_ids": fit.training_record_ids,
        "training_group_ids": fit.training_group_ids,
        "unavailable_training_ids": fit.unavailable_training_ids,
        "training_counts": fit.training_counts,
    }
    mismatches = tuple(field for field in _IDENTITY_FIELDS[:-1] if actual[field] != expected[field])
    if mismatches:
        raise FitIdentityError(mismatches)


def _attempt_error(error: BaseException, category: str) -> AttemptError:
    if category == "convergence":
        if not isinstance(error, HeterogeneityConvergenceError):  # pragma: no cover
            raise ValueError("convergence category requires its typed public error")
        return AttemptError(
            category,
            _qualified_type(error),
            str(error),
            error.reason,
            error.diagnostics,
            error.divergence_count,
        )
    return AttemptError(category, _qualified_type(error), str(error), None, None, None)


def _failed_attempt(
    spec: FitAttemptSpec, error: BaseException, *, category: str
) -> FitAttemptResult:
    status = "convergence_failed" if category == "convergence" else "failed"
    return FitAttemptResult(spec, status, None, _attempt_error(error, category), (), None)


def _identity_rejected(
    spec: FitAttemptSpec, returned: object, mismatches: tuple[str, ...]
) -> FitAttemptResult:
    if isinstance(returned, PopulationHeterogeneityFit):
        return FitAttemptResult(spec, "identity_rejected", returned, None, mismatches, None)
    return FitAttemptResult(
        spec, "identity_rejected", None, None, ("return_type",), _qualified_type(returned)
    )


def run_fit_attempt(
    dataset: GeneratedDataset, *, spec: FitAttemptSpec
) -> FitAttemptResult:
    """Invoke the public fitter exactly once and account for its actual outcome."""
    data = _require_planned_case(dataset, spec)
    try:
        fitted = fit_reference_population_heterogeneity(data.training, config=spec.config)
    except HeterogeneityConvergenceError as error:
        return _failed_attempt(spec, error, category="convergence")
    except ReferenceInfeasibleError as error:
        return _failed_attempt(spec, error, category="reference_infeasible")
    except ValueError as error:
        return _failed_attempt(spec, error, category="value")
    except ArithmeticError as error:
        return _failed_attempt(spec, error, category="arithmetic")
    except RuntimeError as error:
        return _failed_attempt(spec, error, category="runtime")
    try:
        require_fit_identity(data, spec=spec, fit=fitted)
    except FitIdentityError as error:
        return _identity_rejected(spec, fitted, error.mismatches)
    return FitAttemptResult(spec, "accepted", fitted, None, (), None)


def _structural_config(case: SbcCaseId) -> PopulationHeterogeneityConfig:
    return PopulationHeterogeneityConfig(
        mean_prior_alpha=1.0,
        mean_prior_beta=1.0,
        rho_prior_alpha=1.0,
        rho_prior_beta=9.0 if case.track_id == 0 else 4.0,
        draws=500,
        tune=1000,
        chains=4,
        target_accept=0.9,
        seed=SEED,
    )


def exercise_unavailable(dataset: AllUnavailableDataset) -> StructuralCheckResult:
    """Exercise the public all-AN0 refusal using an explicitly unused inert seed."""
    if not isinstance(dataset, AllUnavailableDataset):
        raise ValueError("dataset must be an AllUnavailableDataset")
    try:
        returned = fit_reference_population_heterogeneity(
            dataset.training, config=_structural_config(dataset.case_id)
        )
    except ReferenceInfeasibleError as error:
        return StructuralCheckResult(
            dataset.case_id,
            "expected_refusal",
            _attempt_error(error, "reference_infeasible"),
            None,
            None,
        )
    except Exception as error:
        return StructuralCheckResult(
            dataset.case_id,
            "unexpected_exception",
            _attempt_error(error, "unexpected_exception"),
            None,
            None,
        )
    if isinstance(returned, PopulationHeterogeneityFit):
        return StructuralCheckResult(dataset.case_id, "unexpected_return", None, returned, None)
    return StructuralCheckResult(
        dataset.case_id, "unexpected_return", None, None, _qualified_type(returned)
    )

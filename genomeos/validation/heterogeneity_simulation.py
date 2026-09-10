"""Independent B0H synthetic sampling (design §§5, 7–8, 12; #211).

This pure validation module creates deterministic known-truth count datasets.
Synthetic group labels are nonspatial and make no population or linked-locus
independence claim. Generation remains separate from fitting and scoring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from genomeos.validation.heterogeneity_simulation_types import (
    SEED,
    AllUnavailableDataset,
    Entropy,
    GeneratedDataset,
    GenerationFailure,
    GenerationId,
    GenerationProvenance,
    GenerationResult,
    HeldoutTarget,
    ParameterTruth,
    SbcCaseId,
    SeedIdentity,
    SharedHistory,
    enumerate_sbc_cases,
    generation_id,
    sbc_seed_identity,
)
from genomeos.validation.heterogeneity_simulation_types import (
    fixed_simulation_truth as _fixed_truth,
)
from genomeos.validation.heterogeneity_simulation_types import (
    simulation_failure_scalar as _failure_scalar,
)
from genomeos.validation.heterogeneity_simulation_types import (
    simulation_integer as _integer,
)
from genomeos.validation.heterogeneity_simulation_types import (
    simulation_probability as _probability,
)
from genomeos.validation.heterogeneity_simulation_types import (
    simulation_reference_count as _reference_count,
)
from genomeos.validation.heterogeneity_simulation_types import (
    simulation_training_an as _training_an,
)

__all__ = [
    "SEED",
    "Entropy",
    "SbcCaseId",
    "GenerationId",
    "SeedIdentity",
    "ParameterTruth",
    "GenerationProvenance",
    "SharedHistory",
    "HeldoutTarget",
    "GeneratedDataset",
    "AllUnavailableDataset",
    "GenerationFailure",
    "GenerationResult",
    "enumerate_sbc_cases",
    "generation_id",
    "sbc_seed_identity",
    "generate_sbc_case",
]

_RNG_EXCEPTIONS = (ValueError, FloatingPointError, OverflowError)


def _provenance(case: SbcCaseId) -> GenerationProvenance:
    seeds = tuple(sbc_seed_identity(case, purpose_id=i, attempt_id=0) for i in range(4))
    return GenerationProvenance(generation_id(case), seeds)  # type: ignore[arg-type]


def _evidence(value: object) -> float | int | None:
    try:
        return _failure_scalar(value, "offending_value")
    except ValueError:
        return None


@dataclass(frozen=True)
class _DrawContext:
    case: SbcCaseId
    provenance: GenerationProvenance
    truth: ParameterTruth | None = None
    sampled_mean: float | None = None
    sampled_rho: float | None = None

    def failure(
        self,
        stage: str,
        index: int | None,
        reason: str,
        *,
        offending: object = None,
        error: BaseException | None = None,
        sampled_mean: float | None = None,
        sampled_rho: float | None = None,
    ) -> GenerationFailure:
        return GenerationFailure(
            self.case,
            self.provenance,
            stage,
            index,
            reason,
            self.truth,
            self.sampled_mean if sampled_mean is None else sampled_mean,
            self.sampled_rho if sampled_rho is None else sampled_rho,
            _evidence(offending),
            None if error is None else type(error).__name__,
            None if error is None else str(error),
        )


def _stream(identity: SeedIdentity) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(identity.entropy)))


def _call(
    rng: np.random.Generator, method: str, *args: float | int
) -> tuple[object | None, BaseException | None]:
    try:
        return getattr(rng, method)(*args), None
    except _RNG_EXCEPTIONS as error:
        return None, error


def _draw_probability(
    rng: np.random.Generator,
    method: str,
    args: tuple[float, ...],
    context: _DrawContext,
    stage: str,
    index: int | None,
) -> float | GenerationFailure:
    raw, error = _call(rng, method, *args)
    if error is not None:
        return context.failure(stage, index, "rng_exception", error=error)
    try:
        return _probability(raw, stage)
    except ValueError:
        return context.failure(stage, index, "invalid_rng_scalar", offending=raw)


def _draw_count(
    rng: np.random.Generator,
    an: int,
    q: float,
    context: _DrawContext,
    stage: str,
    index: int,
) -> int | GenerationFailure:
    raw, error = _call(rng, "binomial", an, q)
    if error is not None:
        return context.failure(stage, index, "rng_exception", error=error)
    try:
        value = _integer(raw, stage)
    except ValueError:
        return context.failure(stage, index, "invalid_rng_scalar", offending=raw)
    if not 0 <= value <= an:
        return context.failure(stage, index, "invalid_rng_scalar", offending=raw)
    return value


def _beta_shapes(context: _DrawContext) -> tuple[float, float] | GenerationFailure:
    truth = context.truth
    if truth is None:  # pragma: no cover - callers establish validated truth
        raise AssertionError("Beta shapes require validated truth")
    try:
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            kappa = np.float64((1.0 - truth.rho) / truth.rho)
            a = np.float64(truth.mean * kappa)
            b = np.float64((1.0 - truth.mean) * kappa)
    except _RNG_EXCEPTIONS as error:
        return context.failure("beta_shapes", None, "invalid_beta_shapes", error=error)
    values = (kappa, a, b)
    invalid = tuple(value for value in values if not math.isfinite(float(value)) or value <= 0.0)
    if invalid:
        return context.failure("beta_shapes", None, "invalid_beta_shapes", offending=invalid[0])
    return float(a), float(b)


def _training_counts(
    context: _DrawContext, latents: tuple[float, ...]
) -> tuple[int, ...] | GenerationFailure:
    counts: list[int] = []
    rng = _stream(context.provenance.seeds[2])
    ans = _training_an(context.case)
    for index, (an, q) in enumerate(zip(ans, latents, strict=True)):
        draw = _draw_count(rng, an, q, context, "training_count", index)
        if isinstance(draw, GenerationFailure):
            return draw
        counts.append(draw)
    return tuple(counts)


def _training_rows(context: _DrawContext, counts: tuple[int, ...]) -> tuple[object, ...]:
    generation = context.provenance.generation_id
    ans = _training_an(context.case)
    return tuple(
        _reference_count(generation, "train", str(i), ac, an)
        for i, (ac, an) in enumerate(zip(counts, ans, strict=True))
    )


def _ordinary(context: _DrawContext, shapes: tuple[float, float] | None) -> GenerationResult:
    truth = context.truth
    if truth is None:  # pragma: no cover - callers establish validated truth
        raise AssertionError("ordinary generation requires truth")
    latents: list[float] = []
    if shapes is None:
        latents = [truth.mean] * 16
    else:
        rng = _stream(context.provenance.seeds[1])
        for index in range(16):
            draw = _draw_probability(rng, "beta", shapes, context, "training_population", index)
            if isinstance(draw, GenerationFailure):
                return draw
            latents.append(draw)
    latent_tuple = tuple(latents)
    counts = _training_counts(context, latent_tuple)
    if isinstance(counts, GenerationFailure):
        return counts
    rng = _stream(context.provenance.seeds[3])
    heldout_q: float | GenerationFailure = truth.mean
    if shapes is not None:
        heldout_q = _draw_probability(rng, "beta", shapes, context, "heldout_population", 0)
    if isinstance(heldout_q, GenerationFailure):
        return heldout_q
    heldout_ac = _draw_count(rng, 20, heldout_q, context, "heldout_count", 0)
    if isinstance(heldout_ac, GenerationFailure):
        return heldout_ac
    generation = context.provenance.generation_id
    heldout = HeldoutTarget(
        "fresh_population",
        _reference_count(generation, "heldout", "fresh_population", heldout_ac, 20),
        heldout_q,
        None,
        None,
        None,
        None,
    )
    raw_beta = (*latent_tuple, heldout_q) if shapes is not None else ()
    return GeneratedDataset(
        context.case,
        context.provenance,
        truth,
        _training_rows(context, counts),  # type: ignore[arg-type]
        latent_tuple,
        None,
        (heldout,),
        raw_beta.count(0.0),
        raw_beta.count(1.0),
    )


def _shared_training(
    context: _DrawContext, shapes: tuple[float, float]
) -> tuple[tuple[float, ...], SharedHistory] | GenerationFailure:
    rng = _stream(context.provenance.seeds[1])
    clusters: list[float] = []
    candidates: list[float] = []
    switches: list[bool] = []
    latents: list[float] = []
    threshold = math.sqrt(0.5)
    for cluster_id in range(2):
        cluster = _draw_probability(rng, "beta", shapes, context, "training_cluster", cluster_id)
        if isinstance(cluster, GenerationFailure):
            return cluster
        clusters.append(cluster)
        for index in range(cluster_id * 8, cluster_id * 8 + 8):
            candidate = _draw_probability(rng, "beta", shapes, context, "training_population", index)
            if isinstance(candidate, GenerationFailure):
                return candidate
            uniform = _draw_probability(rng, "random", (), context, "training_switch", index)
            if isinstance(uniform, GenerationFailure):
                return uniform
            if uniform == 1.0:
                return context.failure("training_switch", index, "invalid_rng_scalar", offending=uniform)
            use = uniform < threshold
            candidates.append(candidate)
            switches.append(use)
            latents.append(cluster if use else candidate)
    history = SharedHistory(tuple(clusters), tuple(candidates), tuple(switches))  # type: ignore[arg-type]
    return tuple(latents), history


def _shared_heldout(
    context: _DrawContext,
    shapes: tuple[float, float],
    history: SharedHistory,
) -> tuple[HeldoutTarget, HeldoutTarget] | GenerationFailure:
    rng = _stream(context.provenance.seeds[3])
    threshold = math.sqrt(0.5)
    candidate0 = _draw_probability(rng, "beta", shapes, context, "heldout_population", 0)
    if isinstance(candidate0, GenerationFailure):
        return candidate0
    uniform0 = _draw_probability(rng, "random", (), context, "heldout_switch", 0)
    if isinstance(uniform0, GenerationFailure):
        return uniform0
    if uniform0 == 1.0:
        return context.failure("heldout_switch", 0, "invalid_rng_scalar", offending=uniform0)
    use0 = uniform0 < threshold
    q0 = history.cluster_frequencies[0] if use0 else candidate0
    ac0 = _draw_count(rng, 20, q0, context, "heldout_count", 0)
    if isinstance(ac0, GenerationFailure):
        return ac0
    cluster2 = _draw_probability(rng, "beta", shapes, context, "heldout_cluster", 1)
    if isinstance(cluster2, GenerationFailure):
        return cluster2
    candidate2 = _draw_probability(rng, "beta", shapes, context, "heldout_population", 1)
    if isinstance(candidate2, GenerationFailure):
        return candidate2
    uniform2 = _draw_probability(rng, "random", (), context, "heldout_switch", 1)
    if isinstance(uniform2, GenerationFailure):
        return uniform2
    if uniform2 == 1.0:
        return context.failure("heldout_switch", 1, "invalid_rng_scalar", offending=uniform2)
    use2 = uniform2 < threshold
    q2 = cluster2 if use2 else candidate2
    ac2 = _draw_count(rng, 20, q2, context, "heldout_count", 1)
    if isinstance(ac2, GenerationFailure):
        return ac2
    generation = context.provenance.generation_id
    return (
        HeldoutTarget(
            "shared_cluster0",
            _reference_count(generation, "heldout", "shared_cluster0", ac0, 20),
            q0,
            0,
            history.cluster_frequencies[0],
            candidate0,
            use0,
        ),
        HeldoutTarget(
            "fresh_cluster",
            _reference_count(generation, "heldout", "fresh_cluster", ac2, 20),
            q2,
            2,
            cluster2,
            candidate2,
            use2,
        ),
    )


def _shared(context: _DrawContext, shapes: tuple[float, float]) -> GenerationResult:
    training = _shared_training(context, shapes)
    if isinstance(training, GenerationFailure):
        return training
    latents, history = training
    counts = _training_counts(context, latents)
    if isinstance(counts, GenerationFailure):
        return counts
    heldouts = _shared_heldout(context, shapes, history)
    if isinstance(heldouts, GenerationFailure):
        return heldouts
    raw_beta = (
        *history.cluster_frequencies,
        *history.candidate_frequencies,
        heldouts[0].candidate_frequency,
        heldouts[1].cluster_frequency,
        heldouts[1].candidate_frequency,
    )
    truth = context.truth
    if truth is None:  # pragma: no cover - callers establish validated truth
        raise AssertionError("shared generation requires truth")
    return GeneratedDataset(
        context.case,
        context.provenance,
        truth,
        _training_rows(context, counts),  # type: ignore[arg-type]
        latents,
        history,
        heldouts,
        raw_beta.count(0.0),
        raw_beta.count(1.0),
    )


def _prior_context(case: SbcCaseId, provenance: GenerationProvenance) -> _DrawContext | GenerationFailure:
    initial = _DrawContext(case, provenance)
    rng = _stream(provenance.seeds[0])
    raw_mean, error = _call(rng, "beta", 1.0, 1.0)
    if error is not None:
        return initial.failure("truth_mean", None, "rng_exception", error=error)
    try:
        mean = _probability(raw_mean, "sampled_mean")
    except ValueError:
        return initial.failure(
            "truth_mean",
            None,
            "invalid_rng_scalar",
            offending=raw_mean,
            sampled_mean=_evidence(raw_mean),
        )
    mean_context = _DrawContext(case, provenance, sampled_mean=mean)
    raw_rho, error = _call(rng, "beta", 1.0, 9.0 if case.track_id == 0 else 4.0)
    if error is not None:
        return mean_context.failure("truth_rho", None, "rng_exception", error=error)
    try:
        rho = _probability(raw_rho, "sampled_rho")
    except ValueError:
        return mean_context.failure(
            "truth_rho",
            None,
            "invalid_rng_scalar",
            offending=raw_rho,
            sampled_rho=_evidence(raw_rho),
        )
    context = _DrawContext(case, provenance, sampled_mean=mean, sampled_rho=rho)
    if mean in (0.0, 1.0) or rho in (0.0, 1.0):
        offending = mean if mean in (0.0, 1.0) else rho
        return context.failure("truth_validation", None, "rounded_prior_boundary", offending=offending)
    return _DrawContext(case, provenance, ParameterTruth(mean, rho), mean, rho)


def generate_sbc_case(case: SbcCaseId) -> GenerationResult:
    """Generate one deterministic case or an explicit typed refusal."""
    if not isinstance(case, SbcCaseId):
        raise ValueError("case must be an SbcCaseId")
    case = SbcCaseId(**vars(case))
    provenance = _provenance(case)
    if case.study_id == 3:
        rows = tuple(
            _reference_count(provenance.generation_id, "train", str(index), 0, 0) for index in range(16)
        )
        return AllUnavailableDataset(case, provenance, rows)
    truth = _fixed_truth(case)
    context: _DrawContext | GenerationFailure
    context = (
        _prior_context(case, provenance) if case.study_id == 0 else _DrawContext(case, provenance, truth)
    )
    if isinstance(context, GenerationFailure):
        return context
    if context.truth is None:  # pragma: no cover - fixed-case table is complete
        raise AssertionError("eligible case must have truth")
    shapes: tuple[float, float] | None = None
    if context.truth.rho > 0.0:
        shape_result = _beta_shapes(context)
        if isinstance(shape_result, GenerationFailure):
            return shape_result
        shapes = shape_result
    if case.study_id == 2:
        if shapes is None:  # pragma: no cover - shared cases are interior
            raise AssertionError("shared study must have Beta shapes")
        return _shared(context, shapes)
    return _ordinary(context, shapes)

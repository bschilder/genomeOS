"""Synthetic constructor-valid codec cases; no realized science is claimed."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityConfig,
    PopulationHeterogeneityFit,
    ReferenceHeterogeneityPrediction,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation.heterogeneity_attempts import (
    AttemptError,
    FitAttemptResult,
    FitAttemptSpec,
    StructuralCheckResult,
)
from genomeos.validation.heterogeneity_dependence import (
    DependenceComparisons,
    DependencePointReference,
    HeterogeneityDependenceReference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError,
    PriorControlFailure,
    PriorControlResult,
)
from genomeos.validation.heterogeneity_sbc_quantity_types import (
    QuantityRankEvidence,
    ScalarQuantityEvidence,
    SelectedSbcQuantities,
)
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset,
    GeneratedDataset,
    GenerationFailure,
    GenerationProvenance,
    HeldoutTarget,
    ParameterTruth,
    SbcCaseId,
    SharedHistory,
    fixed_simulation_truth,
    generation_id,
    sbc_seed_identity,
    simulation_reference_count,
    simulation_training_an,
)
from genomeos.validation.heterogeneity_summary_types import (
    HeldoutPredictiveSummary,
    HeterogeneityFitSummary,
    ParameterPosteriorSummary,
    PredictiveSummaryEvidence,
)
from genomeos.validation.predictive import CountPredictive


def provenance(case):
    return GenerationProvenance(
        generation_id(case),
        tuple(sbc_seed_identity(case, purpose_id=purpose, attempt_id=0) for purpose in range(4)),
    )


def dataset(study=0, case_index=0, track=0):
    case = SbcCaseId(track, study, case_index, 0)
    prov = provenance(case)
    truth = fixed_simulation_truth(case)
    if study == 0:
        truth = ParameterTruth(0.25, 0.125)
    training = tuple(
        simulation_reference_count(
            prov.generation_id,
            "train",
            str(index),
            an if study == 4 and case_index == 1 else 0,
            an,
        )
        for index, an in enumerate(simulation_training_an(case))
    )
    if study == 3:
        return AllUnavailableDataset(case, prov, training)
    if study == 2:
        history = SharedHistory((0.125, 0.75), (0.25, 0.5) * 8, (True, False) * 8)
        latents = tuple(
            history.cluster_frequencies[index // 8] if use else candidate
            for index, (use, candidate) in enumerate(
                zip(history.uses_cluster, history.candidate_frequencies, strict=True)
            )
        )
        heldouts = (
            HeldoutTarget(
                "shared_cluster0",
                simulation_reference_count(prov.generation_id, "heldout", "shared_cluster0", 2, 20),
                0.125,
                0,
                0.125,
                0.375,
                True,
            ),
            HeldoutTarget(
                "fresh_cluster",
                simulation_reference_count(prov.generation_id, "heldout", "fresh_cluster", 17, 20),
                0.875,
                2,
                0.625,
                0.875,
                False,
            ),
        )
        raw = (*history.cluster_frequencies, *history.candidate_frequencies, 0.375, 0.625, 0.875)
    else:
        history = None
        latents = (truth.mean,) * 16 if truth.rho == 0.0 else (0.0, 1.0, 0.25, 0.75) * 4
        frequency = truth.mean if truth.rho == 0.0 else 0.375
        ac = 20 if study == 4 and case_index == 1 else 0
        heldouts = (
            HeldoutTarget(
                "fresh_population",
                simulation_reference_count(prov.generation_id, "heldout", "fresh_population", ac, 20),
                frequency,
                None,
                None,
                None,
                None,
            ),
        )
        raw = (*latents, frequency) if truth.rho > 0 else ()
    return GeneratedDataset(
        case, prov, truth, training, latents, history, heldouts, raw.count(0.0), raw.count(1.0)
    )


def attempt_spec(data, attempt=0):
    seed = sbc_seed_identity(data.case_id, purpose_id=4, attempt_id=attempt)
    config = PopulationHeterogeneityConfig(
        1.0,
        1.0,
        1.0,
        9.0 if data.case_id.track_id == 0 else 4.0,
        500 if attempt == 0 else 1000,
        1000 if attempt == 0 else 2000,
        4,
        0.9,
        seed.fit_uint32,
    )
    return FitAttemptSpec(data.case_id, attempt, seed, config)


def fitted(data, spec, *, own_draws=None, variants=1):
    config = spec.config if own_draws is None else replace(spec.config, draws=own_draws)
    variant = data.training[0].variant_id
    ids = (variant,) if variants == 1 else (variant, variant + "z")
    shape = (config.chains, config.draws, variants)
    grid = np.arange(np.prod(shape), dtype=np.float64).reshape(shape)
    mean = 0.125 + (grid % 17) / 64.0
    rho = 0.0625 + (grid % 11) / 64.0
    available = tuple(row for row in data.training if row.an > 0)
    counts = (VariantTrainingCounts(variant, len(available), 0, sum(row.an for row in available)),)
    records = tuple(sorted(row.record_id for row in data.training))
    groups = tuple(sorted(row.group_id for row in data.training))
    if variants == 2:
        records += ("z-extra-record",)
        groups += ("z-extra-group",)
        counts += (VariantTrainingCounts(ids[1], 1, 0, 20),)
    return PopulationHeterogeneityFit(
        config,
        ids,
        mean,
        rho,
        records,
        groups,
        tuple(sorted(row.record_id for row in data.training if row.an == 0)),
        counts,
        tuple(VariantHeterogeneityDiagnostics(v, 1.01, 250.0, 300.0) for v in ids),
        0,
    )


def generation_failures():
    results = []
    rng_stages = (
        (0, "truth_mean", (None,)),
        (0, "truth_rho", (None,)),
        (2, "training_cluster", (0, 1)),
        (2, "training_population", tuple(range(16))),
        (2, "training_switch", tuple(range(16))),
        (2, "training_count", tuple(range(16))),
        (2, "heldout_cluster", (1,)),
        (2, "heldout_population", (0, 1)),
        (2, "heldout_switch", (0, 1)),
        (2, "heldout_count", (0, 1)),
        (0, "training_population", (0,)),
        (0, "training_count", (0,)),
        (0, "heldout_population", (0,)),
        (0, "heldout_count", (0,)),
    )
    for track in (0, 1):
        for study, stage, indices in rng_stages:
            data = dataset(study, track=track)
            truth_stage = stage.startswith("truth_")
            truth = None if truth_stage else data.truth
            mean = 0.25 if study == 0 and stage != "truth_mean" else None
            rho = 0.125 if study == 0 and not truth_stage else None
            for index in indices:
                for exception in ("ValueError", "FloatingPointError", "OverflowError"):
                    results.append(
                        GenerationFailure(
                            data.case_id,
                            data.provenance,
                            stage,
                            index,
                            "rng_exception",
                            truth,
                            mean,
                            rho,
                            None,
                            exception,
                            "",
                        )
                    )
                for bad in (None, -1, -float("inf")):
                    results.append(
                        GenerationFailure(
                            data.case_id,
                            data.provenance,
                            stage,
                            index,
                            "invalid_rng_scalar",
                            truth,
                            bad if stage == "truth_mean" else mean,
                            bad if stage == "truth_rho" else rho,
                            bad,
                            None,
                            None,
                        )
                    )
        prior = dataset(track=track)
        for mean, rho in ((0.0, 0.125), (1.0, 0.125), (0.25, 0.0), (0.25, 1.0)):
            results.append(
                GenerationFailure(
                    prior.case_id,
                    prior.provenance,
                    "truth_validation",
                    None,
                    "rounded_prior_boundary",
                    None,
                    mean,
                    rho,
                    mean if mean in (0.0, 1.0) else rho,
                    None,
                    None,
                )
            )
        for data in (prior, dataset(1, 2, track), dataset(2, track=track)):
            mean, rho = (0.25, 0.125) if data.case_id.study_id == 0 else (None, None)
            for bad in (0, -1, float("inf"), -float("inf")):
                results.append(
                    GenerationFailure(
                        data.case_id,
                        data.provenance,
                        "beta_shapes",
                        None,
                        "invalid_beta_shapes",
                        data.truth,
                        mean,
                        rho,
                        bad,
                        None,
                        None,
                    )
                )
            for exception in ("ValueError", "FloatingPointError", "OverflowError"):
                results.append(
                    GenerationFailure(
                        data.case_id,
                        data.provenance,
                        "beta_shapes",
                        None,
                        "invalid_beta_shapes",
                        data.truth,
                        mean,
                        rho,
                        None,
                        exception,
                        "shape failure",
                    )
                )
    return tuple(results)


def attempt_outcomes():
    results = []
    for track in (0, 1):
        data = dataset(track=track)
        for attempt in (0, 1):
            spec = attempt_spec(data, attempt)
            results.append(FitAttemptResult(spec, "accepted", fitted(data, spec), None, (), None))
            for diagnostics in ((), (VariantHeterogeneityDiagnostics("v", 1.2, 2.0, 3.0),)):
                for divergence in (None, 0, 8):
                    error = AttemptError(
                        "convergence", "builtins.RuntimeError", "", "fixture", diagnostics, divergence
                    )
                    results.append(FitAttemptResult(spec, "convergence_failed", None, error, (), None))
            for category in (
                "reference_infeasible",
                "value",
                "arithmetic",
                "runtime",
                "unexpected_exception",
            ):
                error = AttemptError(category, "builtins.ValueError", "", None, None, None)
                results.append(FitAttemptResult(spec, "failed", None, error, (), None))
            results.append(
                FitAttemptResult(
                    spec,
                    "identity_rejected",
                    fitted(data, spec, own_draws=2, variants=2),
                    None,
                    ("config", "variant_ids", "mean_draws.shape", "rho_draws.shape"),
                    None,
                )
            )
            results.append(
                FitAttemptResult(spec, "identity_rejected", None, None, ("return_type",), "builtins.dict")
            )
        case = dataset(3, track=track).case_id
        for status, category in (
            ("expected_refusal", "reference_infeasible"),
            ("unexpected_exception", "unexpected_exception"),
        ):
            results.append(
                StructuralCheckResult(
                    case,
                    status,
                    AttemptError(category, "builtins.ValueError", "", None, None, None),
                    None,
                    None,
                )
            )
        results.append(
            StructuralCheckResult(case, "unexpected_return", None, fitted(data, spec, own_draws=3), None)
        )
        results.append(StructuralCheckResult(case, "unexpected_return", None, None, "builtins.list"))
    return tuple(results)


def selected(
    *, failure=None, failed_quantity=None, reference_status="resolved", rank_failure=False, attempt=0, track=0
):
    data = dataset(track=track)
    spec = attempt_spec(data, attempt)
    seed = DiagnosticSeedIdentity(spec.case, attempt, 8, (1,))
    prior_pairs = ((0.625, 0.0625), (0.75, 0.125), (0.875, 0.25), (0.5, 0.375))
    control = PriorControlResult(
        seed, prior_pairs if failure is None else prior_pairs[: failure.chain], failure
    )
    correct = ((0.125, 0.25), (0.25, 0.375), (0.375, 0.5), (0.5, 0.625))
    cyclic = ((0.125, 0.625), (0.25, 0.25), (0.375, 0.375), (0.5, 0.5))
    points = ((0.25, 0.125),) + correct + (prior_pairs if failure is None else ()) + cyclic
    slots = tuple(range(13)) if failure is None else (0, 1, 2, 3, 4, 9, 10, 11, 12)
    error = DiagnosticCallError("builtins.ArithmeticError", "synthetic retained failure")
    values = (
        tuple(p[0] for p in points),
        tuple(p[1] for p in points),
        tuple(p[0] * p[1] for p in points),
        (-2.0,) * len(points),
        (-3.0,) * len(points),
    )
    scalars = tuple(
        ScalarQuantityEvidence(q, None, error, 3 if q == 3 else None)
        if q == failed_quantity
        else ScalarQuantityEvidence(q, value, None, None)
        for q, value in enumerate(values)
    )
    reference = (
        None
        if reference_status == "reference_failed"
        else HeterogeneityDependenceReference(
            (64, 128, 256),
            False,
            tuple(
                DependencePointReference(
                    mean,
                    rho,
                    ((1.0, 2.0, 3.0, 4.0),) * 3,
                    (0.0, 0.0, 0.0),
                    0.0,
                    0.0,
                    reference_status != "dependence_reference_unresolved",
                )
                for mean, rho in points
            ),
        )
    )
    ranks = []
    for mode in range(3):
        for quantity in range(6):
            comparison = None
            call_error = None
            rank = None
            if mode == 1 and failure is not None:
                status = "control_failed"
            elif quantity == failed_quantity:
                status = "quantity_failed"
            elif quantity < 5:
                status = "rank_failed" if rank_failure else "ranked"
                rank = None if rank_failure else 2
                call_error = error if rank_failure else None
            elif reference_status in ("reference_failed", "comparison_failed"):
                status = reference_status
                call_error = error if status == "comparison_failed" else None
            else:
                unresolved = reference_status.startswith("dependence_")
                comparison = DependenceComparisons(
                    reference_status if unresolved else "resolved",
                    ((0, 0, 0, 0),) * 3,
                    None if unresolved else (0, 0, 0, 0),
                )
                status = reference_status if unresolved else "rank_failed" if rank_failure else "ranked"
                rank = 2 if status == "ranked" else None
                call_error = error if status == "rank_failed" else None
            ranks.append(
                QuantityRankEvidence(
                    mode,
                    quantity,
                    DiagnosticSeedIdentity(spec.case, attempt, 6, (mode, quantity)),
                    status,
                    rank,
                    comparison,
                    call_error,
                )
            )
    return SelectedSbcQuantities(
        spec,
        ((0, 0), (1, 3), (2, 6), (3, 9)),
        tuple(DiagnosticSeedIdentity(spec.case, attempt, 5, (chain,)) for chain in range(4)),
        control,
        slots,
        points,
        scalars,
        reference,
        error if reference is None else None,
        tuple(ranks),
    )


def control_failures():
    result = []
    error = DiagnosticCallError("builtins.RuntimeError", "")
    for chain in range(4):
        for parameter in ("mean", "rho"):
            for reason, bad, returned, failure_error in (
                ("rng_exception", None, None, error),
                ("invalid_scalar", -1, None, None),
                ("invalid_scalar", float("inf"), None, None),
                ("invalid_scalar", None, "builtins.list", None),
                ("rounded_boundary", 0, None, None),
                ("rounded_boundary", 1.0, None, None),
            ):
                result.append(
                    PriorControlFailure(
                        chain,
                        parameter,
                        reason,
                        bad if parameter == "mean" else 0.25,
                        bad if parameter == "rho" else None,
                        returned,
                        failure_error,
                    )
                )
    return tuple(result)


def summary(study=0, case_index=0, track=0, attempt=0, backend="scipy", status="complete"):
    data = dataset(study, case_index, track)
    spec = attempt_spec(data, attempt)
    count = spec.config.chains * spec.config.draws
    seed = DiagnosticSeedIdentity(spec.case, attempt, 7, ())
    parameters = tuple(
        ParameterPosteriorSummary(
            parameter,
            truth,
            0.5,
            (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875),
            count,
        )
        for parameter, truth in (("mean", data.truth.mean), ("rho", data.truth.rho))
    )
    prediction = None
    if status != "prediction_failed":
        grid = np.arange(count * len(data.heldouts), dtype=np.float64).reshape(count, len(data.heldouts))
        prediction = ReferenceHeterogeneityPrediction(
            CountPredictive(0.125 + grid % 17 / 64, 2.0 + grid % 11, backend),
            tuple(target.row.record_id for target in data.heldouts),
            (),
        )
    rows = (
        tuple(
            HeldoutPredictiveSummary(
                target,
                -float("inf") if index == 0 else -2.0,
                0.25,
                0.125,
                (False, True, True),
                (0.25, 0.5, 0.75),
                0.25 if index == 0 else 0.875,
            )
            for index, target in enumerate(data.heldouts)
        )
        if status == "complete"
        else ()
    )
    predictive = PredictiveSummaryEvidence(
        seed,
        seed.scalar_words,
        seed.scalar_uint128,
        backend,
        count,
        data.heldouts,
        status,
        prediction,
        rows,
        None if status == "complete" else DiagnosticCallError("builtins.RuntimeError", ""),
    )
    return HeterogeneityFitSummary(spec, data.training[0].variant_id, parameters, predictive)


def all_outcomes():
    generated = tuple(
        dataset(study, index, track)
        for track in (0, 1)
        for study, size in ((0, 1), (1, 24), (2, 4), (3, 1), (4, 2))
        for index in range(size)
    )
    quantities = (
        tuple(selected(failure=failure) for failure in control_failures())
        + tuple(
            selected(attempt=attempt, track=track, reference_status=status, rank_failure=failed)
            for attempt in (0, 1)
            for track in (0, 1)
            for status in (
                "resolved",
                "reference_failed",
                "dependence_reference_unresolved",
                "dependence_rank_order_unresolved",
                "comparison_failed",
            )
            for failed in (False, True)
        )
        + (selected(failed_quantity=3), selected(failed_quantity=4))
    )
    summaries = tuple(
        summary(study, 0, track, attempt, backend, status)
        for study in (0, 1, 2, 4)
        for track in (0, 1)
        for attempt in (0, 1)
        for backend in ("scipy", "cupy")
        for status in ("complete", "prediction_failed", "diagnostics_failed")
    )
    return generated + generation_failures() + attempt_outcomes() + quantities + summaries

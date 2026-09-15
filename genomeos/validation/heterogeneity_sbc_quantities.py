"""Guarded B0H selected-quantity orchestration (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

import numpy as np

from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityFit
from genomeos.validation.heterogeneity_attempts import FitAttemptResult, require_fit_identity
from genomeos.validation.heterogeneity_dependence import (
    dependence_comparisons,
    heterogeneity_dependence_reference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_oracle import heterogeneity_log_mass
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError,
    PriorControlResult,
    draw_prior_control,
)
from genomeos.validation.heterogeneity_sbc_quantity_types import (
    QuantityRankEvidence,
    ScalarQuantityEvidence,
    SelectedSbcQuantities,
    require_quantity_comparisons,
    require_quantity_reference,
)
from genomeos.validation.heterogeneity_simulation_types import (
    GeneratedDataset,
    simulation_integer,
)
from genomeos.validation.sbc_ranks import randomized_rank

SEED = 42


def _returned_vector(value: object, size: int) -> np.ndarray:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != np.dtype(np.float64)
        or value.shape != (size,)
        or not np.all(np.isfinite(value))
    ):
        raise ValueError("log mass must return a finite float64 point vector")
    return value


def _actual_error(error: Exception) -> DiagnosticCallError:
    return DiagnosticCallError(type(error).__module__ + "." + type(error).__qualname__, str(error))


def _scalar_quantities(
    data: GeneratedDataset, points: tuple[tuple[float, float], ...]
) -> tuple[ScalarQuantityEvidence, ...]:
    means = np.array([point[0] for point in points], dtype=np.float64)
    rhos = np.array([point[1] for point in points], dtype=np.float64)
    entries = [
        ScalarQuantityEvidence(quantity, tuple(float(x) for x in values), None, None)
        for quantity, values in enumerate((means, rhos, means * rhos))
    ]
    total = np.zeros(len(points), dtype=np.float64)
    for index, row in enumerate(data.training):
        try:
            returned = heterogeneity_log_mass(row.ac, row.an, mean=means, rho=rhos)
        except Exception as error:
            entries.append(ScalarQuantityEvidence(3, None, _actual_error(error), index))
            break
        vector = _returned_vector(returned, len(points))
        with np.errstate(over="ignore", invalid="ignore"):
            total += vector
        if not np.all(np.isfinite(total)):
            raise ArithmeticError("training log likelihood accumulation must remain finite")
    else:
        entries.append(ScalarQuantityEvidence(3, tuple(float(x) for x in total), None, None))
    try:
        returned = heterogeneity_log_mass(0, 20, mean=means, rho=rhos)
    except Exception as error:
        entries.append(ScalarQuantityEvidence(4, None, _actual_error(error), None))
    else:
        values = _returned_vector(returned, len(points))
        entries.append(ScalarQuantityEvidence(4, tuple(float(x) for x in values), None, None))
    return tuple(entries)


def selected_sbc_quantities(dataset: GeneratedDataset, *, attempt: FitAttemptResult) -> SelectedSbcQuantities:
    """Retain one accepted fit's paired scalar and dependence-rank evidence."""
    if not isinstance(dataset, GeneratedDataset):
        raise ValueError("dataset must be a GeneratedDataset")
    if not isinstance(attempt, FitAttemptResult):
        raise ValueError("attempt must be a FitAttemptResult")
    if dataset.case_id.study_id != 0 or attempt.spec.case.study_id != 0:
        raise ValueError("selected quantities require an accepted prior-SBC study0 attempt")
    if attempt.status != "accepted" or not isinstance(attempt.fit, PopulationHeterogeneityFit):
        raise ValueError("attempt must be an accepted typed fit")
    spec = attempt.spec
    fit = attempt.fit
    require_fit_identity(dataset, spec=spec, fit=fit)

    selection_seeds = tuple(
        DiagnosticSeedIdentity(spec.case, spec.attempt_id, 5, (chain,)) for chain in range(4)
    )
    indices: list[tuple[int, int]] = []
    correct: list[tuple[float, float]] = []
    for chain, identity in enumerate(selection_seeds):
        stream = np.random.Generator(
            np.random.PCG64(np.random.SeedSequence(identity.entropy, spawn_key=identity.spawn_key))
        )
        draw = simulation_integer(stream.integers(0, spec.config.draws), "selected draw")
        if not 0 <= draw < spec.config.draws:
            raise ValueError("selected draw is outside the accepted attempt")
        indices.append((chain, draw))
        correct.append(
            (
                float(fit.mean_draws[chain, draw, 0]),
                float(fit.rho_draws[chain, draw, 0]),
            )
        )
    correct_points = tuple(correct)
    cyclic = tuple((correct_points[chain][0], correct_points[(chain - 1) % 4][1]) for chain in range(4))
    control_seed = DiagnosticSeedIdentity(spec.case, spec.attempt_id, 8, (1,))
    control = draw_prior_control(seed=control_seed)
    if not isinstance(control, PriorControlResult):
        raise ValueError("control helper must return a PriorControlResult")
    control = PriorControlResult(control.seed, control.pairs, control.failure)
    if control.seed != control_seed:
        raise ValueError("control identity does not match accepted attempt")
    truth = (dataset.truth.mean, dataset.truth.rho)
    if control.status == "complete":
        slots = tuple(range(13))
        points = (truth, *correct_points, *control.pairs, *cyclic)
    else:
        slots = (0, 1, 2, 3, 4, 9, 10, 11, 12)
        points = (truth, *correct_points, *cyclic)
    scalar_quantities = _scalar_quantities(dataset, points)
    reference = None
    reference_error = None
    try:
        reference = heterogeneity_dependence_reference(
            tuple((row.ac, row.an) for row in dataset.training),
            mean_prior=(1.0, 1.0),
            rho_prior=(1.0, 9.0 if spec.case.track_id == 0 else 4.0),
            points=points,
        )
    except Exception as error:
        reference_error = _actual_error(error)
    else:
        require_quantity_reference(reference, points=points)

    position = {slot: index for index, slot in enumerate(slots)}
    rank_entries = []
    for mode in range(3):
        for quantity in range(6):
            identity = DiagnosticSeedIdentity(spec.case, spec.attempt_id, 6, (mode, quantity))
            comparisons = None
            rank = None
            error_evidence = None
            if mode == 1 and control.status == "failed":
                status = "control_failed"
            elif quantity < 5 and scalar_quantities[quantity].values is None:
                status = "quantity_failed"
            elif quantity == 5 and reference is None:
                status = "reference_failed"
            else:
                draw_indices = tuple(position[1 + mode * 4 + chain] for chain in range(4))
                if quantity < 5:
                    values = scalar_quantities[quantity].values
                    truth_value = values[position[0]]
                    draw_values = tuple(values[index] for index in draw_indices)
                    status = "ready"
                else:
                    try:
                        comparisons = dependence_comparisons(
                            reference,
                            truth_index=position[0],
                            draw_indices=draw_indices,
                        )
                    except Exception as error:
                        status = "comparison_failed"
                        error_evidence = _actual_error(error)
                    else:
                        require_quantity_comparisons(
                            comparisons,
                            reference=reference,
                            truth_index=position[0],
                            draw_indices=draw_indices,
                        )
                        status = "ready" if comparisons.status == "resolved" else comparisons.status
                        if status == "ready":
                            truth_value, draw_values = 0, comparisons.comparisons
                if status == "ready":
                    scalar_seed = identity.scalar_uint128
                    try:
                        returned_rank = randomized_rank(truth_value, draw_values, seed=scalar_seed)
                    except Exception as error:
                        status = "rank_failed"
                        error_evidence = _actual_error(error)
                    else:
                        rank = simulation_integer(returned_rank, "rank")
                        if not 0 <= rank <= 4:
                            raise ValueError("rank must be between0 and4")
                        status = "ranked"
            rank_entries.append(
                QuantityRankEvidence(mode, quantity, identity, status, rank, comparisons, error_evidence)
            )
    return SelectedSbcQuantities(
        spec,
        tuple(indices),
        selection_seeds,
        control,
        slots,
        points,
        scalar_quantities,
        reference,
        reference_error,
        tuple(rank_entries),
    )

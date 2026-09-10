"""Immutable B0H selected-quantity evidence (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from genomeos.validation.heterogeneity_attempts import FitAttemptSpec
from genomeos.validation.heterogeneity_dependence import (
    DependenceComparisons,
    DependencePointReference,
    HeterogeneityDependenceReference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError,
    PriorControlResult,
)
from genomeos.validation.heterogeneity_simulation_types import simulation_integer

SEED = 42
_FLOAT_TYPES = (float, np.float16, np.float32, np.float64)
_RANK_STATUSES = {
    "ranked",
    "control_failed",
    "quantity_failed",
    "reference_failed",
    "dependence_reference_unresolved",
    "dependence_rank_order_unresolved",
    "comparison_failed",
    "rank_failed",
}


def _float(value: object, name: str, *, interior: bool = False) -> float:
    if type(value) not in _FLOAT_TYPES or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite supported float")
    normalized = float(value)
    if interior and not 0.0 < normalized < 1.0:
        raise ValueError(f"{name} must be strictly interior")
    return normalized


def _error(value: object, name: str) -> DiagnosticCallError:
    if not isinstance(value, DiagnosticCallError):
        raise ValueError(f"{name} must be a DiagnosticCallError")
    return DiagnosticCallError(value.exception_class, value.message)


def require_quantity_reference(
    reference: HeterogeneityDependenceReference,
    *,
    points: tuple[tuple[float, float], ...],
) -> None:
    """Check immutable typed reference representation and its input-point binding."""
    if not isinstance(reference, HeterogeneityDependenceReference):
        raise ValueError("reference must be a HeterogeneityDependenceReference")
    if (
        type(reference.orders) is not tuple
        or len(reference.orders) != 3
        or any(
            isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, np.integer)) for x in reference.orders
        )
        or reference.orders != (64, 128, 256)
        or type(reference.analytic_separability) is not bool
    ):
        raise ValueError("reference order or separability metadata is malformed")
    if type(points) is not tuple or not points:
        raise ValueError("expected points must be a nonempty tuple")
    if type(reference.points) is not tuple or len(reference.points) != len(points):
        raise ValueError("reference point count does not match")
    for record, expected in zip(reference.points, points, strict=True):
        if not isinstance(record, DependencePointReference):
            raise ValueError("reference point is malformed")
        if type(expected) is not tuple or len(expected) != 2:
            raise ValueError("expected point is malformed")
        for value in (*expected, record.mean, record.rho):
            if type(value) not in _FLOAT_TYPES or not math.isfinite(float(value)) or not 0 < float(value) < 1:
                raise ValueError("point parameters must be finite interior floats")
        if (float(record.mean), float(record.rho)) != expected:
            raise ValueError("reference point does not match input")
        if (
            type(record.components) is not tuple
            or len(record.components) != 3
            or any(type(row) is not tuple or len(row) != 4 for row in record.components)
            or type(record.raw_values) is not tuple
            or len(record.raw_values) != 3
            or type(record.resolved) is not bool
        ):
            raise ValueError("reference point evidence shape is malformed")
        for value in (
            *record.raw_values,
            record.value,
            record.error_bound,
            *(value for row in record.components for value in row),
        ):
            if type(value) not in _FLOAT_TYPES or not math.isfinite(float(value)):
                raise ValueError("reference evidence must contain finite supported floats")
        if record.error_bound < 0:
            raise ValueError("reference error bound must be nonnegative")


def _require_comparison_structure(comparisons: object) -> None:
    if not isinstance(comparisons, DependenceComparisons):
        raise ValueError("comparison call must return DependenceComparisons")
    if type(comparisons.status) is not str or comparisons.status not in (
        "resolved",
        "dependence_reference_unresolved",
        "dependence_rank_order_unresolved",
    ):
        raise ValueError("comparison status is invalid")
    rows = comparisons.comparisons_by_order
    if type(rows) is not tuple or len(rows) != 3:
        raise ValueError("raw comparisons must have three order rows")
    checked = list(rows)
    if comparisons.status == "resolved":
        if comparisons.comparisons is None:
            raise ValueError("resolved comparisons require resolved signs")
        checked.append(comparisons.comparisons)
    elif comparisons.comparisons is not None:
        raise ValueError("unresolved comparisons cannot carry resolved signs")
    for row in checked:
        if type(row) is not tuple or len(row) != 4:
            raise ValueError("comparison rows must contain four signs")
        for value in row:
            sign = simulation_integer(value, "comparison sign")
            if sign not in (-1, 0, 1):
                raise ValueError("comparison signs must be -1, 0 or1")


def require_quantity_comparisons(
    comparisons: DependenceComparisons,
    *,
    reference: HeterogeneityDependenceReference,
    truth_index: int,
    draw_indices: tuple[int, int, int, int],
) -> None:
    """Bind typed comparison signs to one already-returned reference exactly."""
    if (
        not isinstance(reference, HeterogeneityDependenceReference)
        or type(reference.points) is not tuple
        or any(not isinstance(point, DependencePointReference) for point in reference.points)
    ):
        raise ValueError("comparison reference is malformed")
    require_quantity_reference(reference, points=tuple((point.mean, point.rho) for point in reference.points))
    truth = simulation_integer(truth_index, "truth index")
    if type(draw_indices) is not tuple or len(draw_indices) != 4:
        raise ValueError("draw indices must be a four-tuple")
    draws = tuple(simulation_integer(index, "draw index") for index in draw_indices)
    if (
        not 0 <= truth < len(reference.points)
        or any(not 0 <= index < len(reference.points) for index in draws)
        or truth in draws
        or len(set(draws)) != 4
    ):
        raise ValueError("comparison indices must be in range and distinct")
    _require_comparison_structure(comparisons)
    expected_raw = tuple(
        tuple(
            int(reference.points[index].raw_values[order] > reference.points[truth].raw_values[order])
            - int(reference.points[index].raw_values[order] < reference.points[truth].raw_values[order])
            for index in draws
        )
        for order in range(3)
    )
    if comparisons.comparisons_by_order != expected_raw:
        raise ValueError("raw comparison signs do not match their reference points")


@dataclass(frozen=True)
class ScalarQuantityEvidence:
    """One retained scalar vector or one actual quantity-call failure."""

    quantity_id: Literal[0, 1, 2, 3, 4]
    values: tuple[float, ...] | None
    error: DiagnosticCallError | None
    failed_training_row: int | None

    def __post_init__(self) -> None:
        quantity = simulation_integer(self.quantity_id, "quantity_id")
        if quantity not in range(5):
            raise ValueError("quantity_id must be between 0 and 4")
        if self.values is None:
            if quantity not in (3, 4) or self.error is None:
                raise ValueError("only callable likelihood quantities may retain failures")
            error = _error(self.error, "error")
            if quantity == 3:
                row = simulation_integer(self.failed_training_row, "failed_training_row")
                if row not in range(16):
                    raise ValueError("failed_training_row must be between 0 and 15")
            elif self.failed_training_row is not None:
                raise ValueError("future quantity failure has no training row")
            else:
                row = None
            values = None
        else:
            if (
                type(self.values) is not tuple
                or self.error is not None
                or self.failed_training_row is not None
            ):
                raise ValueError("successful scalar evidence has only finite immutable values")
            values = tuple(_float(value, "scalar value") for value in self.values)
            error = None
            row = None
        object.__setattr__(self, "quantity_id", quantity)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "error", error)
        object.__setattr__(self, "failed_training_row", row)


@dataclass(frozen=True)
class QuantityRankEvidence:
    """One planned purpose-6 rank outcome, including incomplete evidence states."""

    mode_id: Literal[0, 1, 2]
    quantity_id: Literal[0, 1, 2, 3, 4, 5]
    seed: DiagnosticSeedIdentity
    status: Literal[
        "ranked",
        "control_failed",
        "quantity_failed",
        "reference_failed",
        "dependence_reference_unresolved",
        "dependence_rank_order_unresolved",
        "comparison_failed",
        "rank_failed",
    ]
    rank: int | None
    comparisons: DependenceComparisons | None
    error: DiagnosticCallError | None

    def __post_init__(self) -> None:
        mode = simulation_integer(self.mode_id, "mode_id")
        quantity = simulation_integer(self.quantity_id, "quantity_id")
        if mode not in range(3) or quantity not in range(6):
            raise ValueError("mode_id or quantity_id is outside the declared rank domain")
        if not isinstance(self.seed, DiagnosticSeedIdentity):
            raise ValueError("seed must be a DiagnosticSeedIdentity")
        seed = DiagnosticSeedIdentity(
            self.seed.case, self.seed.attempt_id, self.seed.purpose_id, self.seed.spawn_key
        )
        if seed.purpose_id != 6 or seed.spawn_key != (mode, quantity):
            raise ValueError("rank seed does not match mode and quantity")
        if type(self.status) is not str or self.status not in _RANK_STATUSES:
            raise ValueError("status is not a declared rank outcome")
        rank = None if self.rank is None else simulation_integer(self.rank, "rank")
        if rank is not None and rank not in range(5):
            raise ValueError("rank must be between 0 and 4")
        comparisons = self.comparisons
        if comparisons is not None:
            _require_comparison_structure(comparisons)
        error = None if self.error is None else _error(self.error, "error")
        scalar = quantity < 5
        valid = (
            (
                self.status == "ranked"
                and rank is not None
                and error is None
                and (
                    (scalar and comparisons is None)
                    or (not scalar and comparisons is not None and comparisons.status == "resolved")
                )
            )
            or (self.status == "control_failed" and mode == 1 and rank is comparisons is error is None)
            or (self.status == "quantity_failed" and scalar and rank is comparisons is error is None)
            or (self.status == "reference_failed" and not scalar and rank is comparisons is error is None)
            or (
                self.status in ("dependence_reference_unresolved", "dependence_rank_order_unresolved")
                and not scalar
                and rank is error is None
                and comparisons is not None
                and comparisons.status == self.status
            )
            or (
                self.status == "comparison_failed"
                and not scalar
                and rank is comparisons is None
                and error is not None
            )
            or (
                self.status == "rank_failed"
                and rank is None
                and error is not None
                and (
                    (scalar and comparisons is None)
                    or (not scalar and comparisons is not None and comparisons.status == "resolved")
                )
            )
        )
        if not valid:
            raise ValueError("rank evidence fields do not match its declared status")
        object.__setattr__(self, "mode_id", mode)
        object.__setattr__(self, "quantity_id", quantity)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "rank", rank)
        object.__setattr__(self, "error", error)


@dataclass(frozen=True)
class SelectedSbcQuantities:
    """All selected points and closed rank evidence for one accepted study-0 attempt."""

    spec: FitAttemptSpec
    selected_indices: tuple[tuple[int, int], ...]
    selection_seeds: tuple[DiagnosticSeedIdentity, ...]
    control: PriorControlResult
    point_slots: tuple[int, ...]
    points: tuple[tuple[float, float], ...]
    scalar_quantities: tuple[ScalarQuantityEvidence, ...]
    reference: HeterogeneityDependenceReference | None
    reference_error: DiagnosticCallError | None
    ranks: tuple[QuantityRankEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.spec, FitAttemptSpec) or self.spec.case.study_id != 0:
            raise ValueError("selected quantities require a study-0 FitAttemptSpec")
        spec = FitAttemptSpec(self.spec.case, self.spec.attempt_id, self.spec.seed, self.spec.config)
        if type(self.selected_indices) is not tuple or len(self.selected_indices) != 4:
            raise ValueError("selected_indices must contain four immutable chain/draw pairs")
        indices = []
        for chain, pair in enumerate(self.selected_indices):
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("selected index must be an immutable chain/draw pair")
            actual_chain = simulation_integer(pair[0], "selected chain")
            draw = simulation_integer(pair[1], "selected draw")
            if actual_chain != chain or not 0 <= draw < spec.config.draws:
                raise ValueError("selected indices must be ordered and in attempt bounds")
            indices.append((actual_chain, draw))
        if type(self.selection_seeds) is not tuple or len(self.selection_seeds) != 4:
            raise ValueError("selection_seeds must contain four immutable identities")
        seeds = tuple(
            DiagnosticSeedIdentity(seed.case, seed.attempt_id, seed.purpose_id, seed.spawn_key)
            if isinstance(seed, DiagnosticSeedIdentity)
            else None
            for seed in self.selection_seeds
        )
        expected_seeds = tuple(
            DiagnosticSeedIdentity(spec.case, spec.attempt_id, 5, (chain,)) for chain in range(4)
        )
        if seeds != expected_seeds:
            raise ValueError("selection seeds do not match the accepted attempt")
        if not isinstance(self.control, PriorControlResult):
            raise ValueError("control must be a PriorControlResult")
        control = PriorControlResult(self.control.seed, self.control.pairs, self.control.failure)
        expected_control_seed = DiagnosticSeedIdentity(spec.case, spec.attempt_id, 8, (1,))
        if control.seed != expected_control_seed:
            raise ValueError("control identity does not match accepted attempt")
        slots = tuple(range(13)) if control.status == "complete" else (0, 1, 2, 3, 4, 9, 10, 11, 12)
        if type(self.point_slots) is not tuple or self.point_slots != slots:
            raise ValueError("point_slots does not match the control outcome")
        if type(self.points) is not tuple or len(self.points) != len(slots):
            raise ValueError("points does not match the canonical point map")
        points = tuple(
            (_float(pair[0], "point mean", interior=True), _float(pair[1], "point rho", interior=True))
            if type(pair) is tuple and len(pair) == 2
            else (_ for _ in ()).throw(ValueError("point must be a mean/rho tuple"))
            for pair in self.points
        )
        correct = points[1:5]
        cyclic = tuple((correct[c][0], correct[(c - 1) % 4][1]) for c in range(4))
        if control.status == "complete":
            if points[5:9] != control.pairs or points[9:13] != cyclic:
                raise ValueError("complete control or cyclic points do not match")
        elif points[5:9] != cyclic:
            raise ValueError("failed control retains only cyclic points")
        if type(self.scalar_quantities) is not tuple or len(self.scalar_quantities) != 5:
            raise ValueError("scalar_quantities must contain exactly five entries")
        scalars = tuple(
            ScalarQuantityEvidence(item.quantity_id, item.values, item.error, item.failed_training_row)
            if isinstance(item, ScalarQuantityEvidence)
            else None
            for item in self.scalar_quantities
        )
        if any(item is None for item in scalars) or tuple(item.quantity_id for item in scalars) != tuple(
            range(5)
        ):
            raise ValueError("scalar quantities must be ordered q0 through q4")
        for quantity, expected in enumerate(
            (
                tuple(point[0] for point in points),
                tuple(point[1] for point in points),
                tuple(point[0] * point[1] for point in points),
            )
        ):
            if scalars[quantity].values != expected:
                raise ValueError("q0 through q2 must exactly match canonical points")
        if (self.reference is None) == (self.reference_error is None):
            raise ValueError("reference and reference_error must be an exclusive pair")
        reference_error = (
            None if self.reference_error is None else _error(self.reference_error, "reference_error")
        )
        if self.reference is not None:
            require_quantity_reference(self.reference, points=points)
        if type(self.ranks) is not tuple or len(self.ranks) != 18:
            raise ValueError("ranks must contain exactly eighteen entries")
        ranks = tuple(
            QuantityRankEvidence(
                item.mode_id,
                item.quantity_id,
                item.seed,
                item.status,
                item.rank,
                item.comparisons,
                item.error,
            )
            if isinstance(item, QuantityRankEvidence)
            else None
            for item in self.ranks
        )
        if any(item is None for item in ranks) or tuple(
            (item.mode_id, item.quantity_id) for item in ranks
        ) != tuple((mode, quantity) for mode in range(3) for quantity in range(6)):
            raise ValueError("ranks must be mode-major and quantity-major")
        position = {slot: index for index, slot in enumerate(slots)}
        for entry in ranks:
            expected_seed = DiagnosticSeedIdentity(
                spec.case, spec.attempt_id, 6, (entry.mode_id, entry.quantity_id)
            )
            if entry.seed != expected_seed:
                raise ValueError("rank seed does not match the accepted attempt")
            if entry.comparisons is not None:
                draws = tuple(position[1 + entry.mode_id * 4 + c] for c in range(4))
                require_quantity_comparisons(
                    entry.comparisons, reference=self.reference, truth_index=position[0], draw_indices=draws
                )
            if entry.mode_id == 1 and control.status == "failed":
                if entry.status != "control_failed":
                    raise ValueError("failed control must dominate mode-1 ranks")
            elif entry.quantity_id < 5:
                failed = scalars[entry.quantity_id].values is None
                if failed != (entry.status == "quantity_failed") and not (
                    not failed and entry.status in ("ranked", "rank_failed")
                ):
                    raise ValueError("scalar rank status does not match scalar evidence")
            elif self.reference is None:
                if entry.status != "reference_failed":
                    raise ValueError("missing reference must dominate dependence rank")
            elif entry.status == "reference_failed":
                raise ValueError("reference failure state cannot accompany a reference")
        object.__setattr__(self, "spec", spec)
        object.__setattr__(self, "selected_indices", tuple(indices))
        object.__setattr__(self, "selection_seeds", seeds)
        object.__setattr__(self, "control", control)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "scalar_quantities", scalars)
        object.__setattr__(self, "reference_error", reference_error)
        object.__setattr__(self, "ranks", ranks)

    @property
    def selection_method(self) -> str:
        """Return the frozen chain-preserving selection label."""
        return "one_uniform_postwarmup_draw_per_chain"

    @property
    def complete(self) -> bool:
        """Return whether all locally computable ranks and controls completed."""
        return self.control.status == "complete" and all(entry.status == "ranked" for entry in self.ranks)

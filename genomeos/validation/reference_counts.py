"""Pure reference-count folds and marginal B0 adapter (design §§ 5, 7, 8; #189).

This implements the reference-count design's table/fold and exact marginal B0
sections. Reference-panel operational groups are not resident populations or
certified independent studies, and this module performs no file or network I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral

import numpy as np

from genomeos.validation.count_baseline import (
    B0VariantPosterior,
    PooledAlleleCount,
    pooled_beta_posteriors,
)
from genomeos.validation.predictive import SEED, CountPredictive
from genomeos.validation.reference_count_types import ReferenceCount, validate_reference_counts


def _literal_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty literal string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    return int(value)


@dataclass(frozen=True)
class ReferenceFold:
    """One dependency-aware reference-resource train/test split."""

    split_id: str
    train_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    test_groups: tuple[str, ...]


def _components(groups: set[str], edges: tuple[tuple[str, str], ...]) -> list[tuple[str, ...]]:
    neighbors = {group: set() for group in groups}
    for left, right in edges:
        neighbors[left].add(right)
        neighbors[right].add(left)
    pending = set(groups)
    result = []
    while pending:
        start = min(pending)
        component = {start}
        frontier = [start]
        pending.remove(start)
        while frontier:
            current = frontier.pop()
            discovered = neighbors[current] & pending
            pending.difference_update(discovered)
            component.update(discovered)
            frontier.extend(sorted(discovered, reverse=True))
        result.append(tuple(sorted(component)))
    return sorted(result)


def _validated_edges(
    dependency_edges: Sequence[tuple[str, str]], groups: set[str]
) -> tuple[tuple[str, str], ...]:
    edges = tuple(dependency_edges)
    canonical = []
    for edge in edges:
        if not isinstance(edge, (tuple, list)) or len(edge) != 2:
            raise ValueError("dependency edges must be pairs of group IDs")
        left = _literal_id(edge[0], "dependency edge endpoint")
        right = _literal_id(edge[1], "dependency edge endpoint")
        if left not in groups or right not in groups:
            raise ValueError("dependency edge endpoints must be known group IDs")
        if left == right:
            raise ValueError("dependency edges must join distinct groups")
        canonical.append(tuple(sorted((left, right))))
    if len(set(canonical)) != len(canonical):
        raise ValueError("duplicate undirected dependency edges are not allowed")
    return tuple(canonical)


def reference_group_folds(
    rows: Sequence[ReferenceCount],
    *,
    dependency_edges: Sequence[tuple[str, str]],
    n_folds: int = 5,
    seed: int = SEED,
) -> tuple[ReferenceFold, ...]:
    """Build deterministic folds without splitting declared dependency components."""
    table = validate_reference_counts(rows)
    folds = _integer(n_folds, "n_folds")
    if folds < 2:
        raise ValueError("n_folds must be at least 2")
    normalized_seed = _integer(seed, "seed")
    if normalized_seed < 0:
        raise ValueError("seed must be a nonnegative integer")

    groups = {row.group_id for row in table}
    components = _components(groups, _validated_edges(dependency_edges, groups))
    if len(components) < folds:
        raise ValueError("dependency components must number at least n_folds")
    permutation = np.random.default_rng(normalized_seed).permutation(len(components))
    fold_groups = [set() for _ in range(folds)]
    for position, index in enumerate(permutation):
        fold_groups[position % folds].update(components[int(index)])

    all_ids = {row.record_id for row in table}
    result = []
    for index, test_groups in enumerate(fold_groups):
        test_ids = tuple(sorted(row.record_id for row in table if row.group_id in test_groups))
        result.append(
            ReferenceFold(
                f"reference-{index}",
                tuple(sorted(all_ids - set(test_ids))),
                test_ids,
                tuple(sorted(test_groups)),
            )
        )
    return tuple(result)


class ReferenceInfeasibleError(ValueError):
    """A reference holdout contains no rows with available denominators."""


@dataclass(frozen=True)
class ReferenceB0Fit:
    """Exact marginal B0 predictions and their fitted posterior parameters."""

    marginal_predictive: CountPredictive
    observation_ids: tuple[str, ...]
    unavailable_ids: tuple[str, ...]
    posteriors: tuple[B0VariantPosterior, ...]


def fit_reference_b0(
    training: Sequence[ReferenceCount],
    testing: Sequence[ReferenceCount],
    *,
    prior_alpha: float,
    prior_beta: float,
) -> ReferenceB0Fit:
    """Fit pooled training counts and return exact test-row marginal predictions."""
    training_rows = validate_reference_counts(training)
    testing_rows = validate_reference_counts(testing)
    training_ids = {row.record_id for row in training_rows}
    testing_ids = {row.record_id for row in testing_rows}
    if training_ids & testing_ids:
        raise ValueError("training and testing record IDs must be disjoint")
    training_groups = {row.group_id for row in training_rows}
    testing_groups = {row.group_id for row in testing_rows}
    if training_groups & testing_groups:
        raise ValueError("training and testing group IDs must be disjoint")

    scoreable = tuple(row for row in testing_rows if row.an > 0)
    unavailable_ids = tuple(row.record_id for row in testing_rows if row.an == 0)
    if not scoreable:
        raise ReferenceInfeasibleError("test fold has no scoreable rows")
    counts = tuple(
        PooledAlleleCount(row.record_id, row.variant_id, row.ac, row.an)
        for row in training_rows
        if row.an > 0
    )
    posteriors = pooled_beta_posteriors(
        counts,
        tuple(sorted({row.variant_id for row in scoreable})),
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
    )
    by_variant = {posterior.variant_id: posterior for posterior in posteriors}
    shape_a = np.asarray([by_variant[row.variant_id].alpha for row in scoreable])
    shape_b = np.asarray([by_variant[row.variant_id].beta for row in scoreable])
    concentration = shape_a + shape_b
    mean = shape_a / concentration
    reconstructed_a = mean * concentration
    reconstructed_b = (1.0 - mean) * concentration
    stable = (
        np.all(np.isfinite(mean))
        and np.all((mean > 0.0) & (mean < 1.0))
        and np.allclose(reconstructed_a, shape_a, rtol=1e-10, atol=0.0)
        and np.allclose(reconstructed_b, shape_b, rtol=1e-10, atol=0.0)
    )
    if not stable:
        raise ValueError("marginal parameters are outside the stable numeric domain")
    marginal = CountPredictive(mean[None, :], concentration=concentration[None, :])
    return ReferenceB0Fit(
        marginal,
        tuple(row.record_id for row in scoreable),
        unavailable_ids,
        posteriors,
    )

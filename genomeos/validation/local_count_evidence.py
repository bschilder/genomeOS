"""Semantic B1 evidence boundary (design §§4–8, 12; #307).

Validate retained terminal results against their frozen requested identities before scoring or
publication. This pure module neither repairs contradictions nor fits replacement results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import validate_predictive_diagnostics

if TYPE_CHECKING:
    from genomeos.validation.local_count_benchmark import LocalCountFoldResult
    from genomeos.validation.local_count_selection import LocalCountBenchmarkConfig
    from genomeos.validation.splits import BenchmarkSplit


def validate_local_count_fold(
    fold: LocalCountFoldResult,
    split: BenchmarkSplit,
    observations: pd.DataFrame,
    assignments: pd.DataFrame,
    *,
    config: LocalCountBenchmarkConfig,
) -> None:
    """Refuse contradictions between requested, supported, emitted and scored evidence."""
    config.__post_init__()
    status = fold.status
    expected = set(split.test_ids)
    if not expected or len(expected) != len(split.test_ids):
        raise ValueError("planned test identities must be nonempty and unique")
    if status.split_id != split.split_id or status.status not in ("completed", "failed", "infeasible"):
        raise ValueError("invalid terminal fold identity or state")
    for ids in (status.expected_test_ids, status.emitted_test_ids, status.refused_test_ids):
        if len(ids) != len(set(ids)):
            raise ValueError("fold identities must be unique")
    emitted, refused = set(status.emitted_test_ids), set(status.refused_test_ids)
    if set(status.expected_test_ids) != expected or emitted & refused or emitted | refused != expected:
        raise ValueError("emitted/refused identities must partition the planned test identities")
    if status.status == "completed":
        if not emitted or status.failure_reason is not None:
            raise ValueError("completed fold requires emissions and no failure reason")
    elif emitted or not isinstance(status.failure_reason, str) or not status.failure_reason.strip():
        raise ValueError("failed/infeasible fold requires a reason and no emissions")
    if status.selected_bandwidth_km is not None and (
        not np.isfinite(status.selected_bandwidth_km) or status.selected_bandwidth_km <= 0
    ):
        raise ValueError("selected bandwidth must be positive and finite")
    if (
        status.selected_bandwidth_km is not None
        and status.selected_bandwidth_km not in config.candidate_bandwidths_km
    ):
        raise ValueError("selected bandwidth is not a declared candidate")
    if emitted and status.selected_bandwidth_km is None:
        raise ValueError("emissions require a selected bandwidth")

    support, predictions = fold.support, fold.predictions
    for frame, ids, label in ((support, expected, "support"), (predictions, emitted, "predictions")):
        if frame.columns.duplicated().any() or "source_record_id" not in frame:
            raise ValueError(f"{label} requires unique columns and record identities")
        if frame["source_record_id"].duplicated().any() or set(frame["source_record_id"]) != ids:
            raise ValueError(f"{label} must cover exactly its declared identities")
        if (
            not {"split_id", "block_id"} <= set(frame.columns)
            or not ((frame["split_id"] == split.split_id) & (frame["block_id"] == split.block_id)).all()
        ):
            raise ValueError(f"{label} split/block identity mismatch")
    posterior = ["posterior_alpha", "posterior_beta", "posterior_mean"]
    support_metrics = [
        "nearest_edge_distance_km",
        "training_observation_count",
        "effective_training_observations",
        "effective_allele_count",
    ]
    required = set(posterior + support_metrics + ["status", "refusal_reason", "bandwidth_km"])
    if not required <= set(support.columns):
        raise ValueError("support is missing semantic fields")
    for row in support.itertuples(index=False):
        is_emitted = row.source_record_id in emitted
        counts = np.array([getattr(row, field) for field in support_metrics[1:]], dtype=float)
        if not np.isfinite(counts).all() or (counts < 0).any() or counts[0] != int(counts[0]):
            raise ValueError("support evidence counts must be finite and nonnegative")
        distance = row.nearest_edge_distance_km
        if not pd.isna(distance) and (not np.isfinite(distance) or distance < 0):
            raise ValueError("support distance must be finite and nonnegative when available")
        if is_emitted and (pd.isna(distance) or (counts <= 0).any()):
            raise ValueError("emitted support requires positive local evidence and a distance")
        if row.status != ("emitted" if is_emitted else "unknown"):
            raise ValueError("support status contradicts emitted/refused identities")
        values = np.array([getattr(row, field) for field in posterior], dtype=float)
        if is_emitted:
            if (
                counts[0] < config.minimum_training_observations
                or counts[2] < config.minimum_effective_alleles
                or distance >= status.selected_bandwidth_km
            ):
                raise ValueError("emitted support contradicts frozen support thresholds")
            if not np.isclose(
                values[:2].sum(), config.prior_alpha + config.prior_beta + counts[2], rtol=1e-12, atol=1e-14
            ):
                raise ValueError("posterior concentration contradicts retained effective allele count")
            if row.refusal_reason != "" or not np.isfinite(values).all() or (values[:2] <= 0).any():
                raise ValueError("emitted support requires valid posterior and no refusal")
            if not np.isclose(values[2], values[0] / values[:2].sum(), rtol=1e-12, atol=1e-15):
                raise ValueError("posterior mean contradicts retained alpha/beta")
        elif (
            not isinstance(row.refusal_reason, str)
            or not row.refusal_reason.strip()
            or not np.isnan(values).all()
        ):
            raise ValueError("refused support requires a reason and null posterior")
        bandwidth = row.bandwidth_km
        if (
            not (pd.isna(bandwidth) and status.selected_bandwidth_km is None)
            and bandwidth != status.selected_bandwidth_km
        ):
            raise ValueError("support bandwidth contradicts fold status")
    if not emitted:
        return
    required_predictions = {
        "variant_id",
        "cohort_id",
        "region_id",
        "variant_group",
        "observed_ac",
        "observed_an",
    }
    if not required_predictions <= set(predictions.columns):
        raise ValueError("predictions are missing observation identities")
    obs = observations.set_index("source_record_id")
    assigned = assignments.set_index("source_record_id")
    supporting = support.set_index("source_record_id")
    shared = [column for column in support if column not in ("status", "refusal_reason", "source_record_id")]
    if not set(shared) <= set(predictions):
        raise ValueError("predictions are missing retained support fields")
    for row in predictions.itertuples(index=False):
        record_id = row.source_record_id
        for column, source in (
            ("variant_id", obs),
            ("cohort_id", obs),
            ("region_id", assigned),
            ("variant_group", assigned),
        ):
            if getattr(row, column) != source.loc[record_id, column]:
                raise ValueError(f"prediction {column} contradicts frozen observation/assignment")
        for column, source_column in (("observed_ac", "ac"), ("observed_an", "an")):
            if getattr(row, column) != obs.loc[record_id, source_column]:
                raise ValueError(f"prediction {column} contradicts frozen count")
        for column in shared:
            if getattr(row, column) != supporting.loc[record_id, column]:
                raise ValueError(f"prediction {column} contradicts retained support")
    validate_predictive_diagnostics(predictions)

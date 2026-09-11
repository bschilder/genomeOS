"""Identity-checked descriptive B0H minus B0 reports (design §§5, 7–8, 12).

Only immutable in-memory publications enter this reporting boundary. Recomputed
summaries use source-population/region/locus weighting; these dependent rows do
not establish external, resident, geographic, joint-LD, or release fitness.
Full-pair metrics require five completed folds in both models. Conditional
metrics use the intersection of completed folds, with identical row membership.
No fit, stochastic statistic, confidence interval, winner, or promotion is made.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import sqrt
from typing import Any

from genomeos.validation.benchmark import summarize_benchmark
from genomeos.validation.reference_b0h_artifacts import fingerprint
from genomeos.validation.reference_comparison_inputs import (
    BASE_CONFIGURATION,
    ReferencePublication,
    decode_reference_publication,
)

_METRIC_UNITS = {
    "mean_log_score": "natural_log",
    "mae": "frequency",
    "rmse": "frequency",
    "coverage_50": "percentage_points",
    "coverage_80": "percentage_points",
    "coverage_95": "percentage_points",
    "interval_width_50": "frequency",
    "interval_width_80": "frequency",
    "interval_width_95": "frequency",
    "mean_randomized_pit": "unit_interval",
}


def _require_equal(left: object, right: object, name: str) -> None:
    if left != right:
        raise ValueError(f"paired {name} mismatch")


def _validate_pair(left: ReferencePublication, right: ReferencePublication) -> None:
    for name in BASE_CONFIGURATION:
        _require_equal(left.manifest["configuration"][name], right.manifest["configuration"][name], name)
    for name in ("target", "joint_prediction_supported", "input_files", "dependency_qualification"):
        _require_equal(left.manifest[name], right.manifest[name], name)
    for name in ("root", "split", "pit_by_fold"):
        _require_equal(left.manifest["seeds"][name], right.manifest["seeds"][name], name)
    for a, b in zip(left.folds, right.folds, strict=True):
        for name in ("split_id", "train_ids", "test_ids", "test_groups", "pit_seed"):
            _require_equal(a[name], b[name], name)

    def unavailable(publication: ReferencePublication) -> set[tuple[str, str]]:
        return {
            (r["split_id"], r["record_id"])
            for r in publication.row_status
            if r["status"] == "unavailable_denominator"
        }

    _require_equal(unavailable(left), unavailable(right), "unavailable membership")
    columns = ["variant_id", "cohort_id", "region_id", "variant_group", "observed_ac", "observed_an"]
    keys = ["split_id", "source_record_id"]
    a = left.predictions.set_index(keys)
    b = right.predictions.set_index(keys)
    common = a.index.intersection(b.index)
    for key in common:
        _require_equal(
            a.loc[key, columns].tolist(), b.loc[key, columns].tolist(), "prediction identity/count"
        )


def _differences(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, object]:
    result = {}
    for metric, unit in _METRIC_UNITS.items():
        a, b = left[metric], right[metric]
        reason = None
        if a is None or b is None:
            value, reason = None, "unavailable"
        elif a == b == "-Infinity":
            value, reason = None, "both_negative_infinity"
        elif a == "-Infinity":
            value = "Infinity"
        elif b == "-Infinity":
            value = "-Infinity"
        else:
            value = (b - a) * (100 if unit == "percentage_points" else 1)
        result[metric] = {"value": value, "reason": reason, "unit": unit}
    return result


def _cell_differences(left: dict[str, Any], right: dict[str, Any], name: str, keys: tuple[str, ...]):
    records = []
    for a, b in zip(left[name], right[name], strict=True):
        _require_equal([a[k] for k in keys], [b[k] for k in keys], "aggregation cell")
        records.append(
            {
                **{k: a[k] for k in keys},
                "observation_count": a["observation_count"],
                "zero_probability_count_b0": a["zero_probability_count"],
                "zero_probability_count_b0h": b["zero_probability_count"],
                "differences": _differences(
                    {**a, "rmse": sqrt(a["mean_squared_error"])}, {**b, "rmse": sqrt(b["mean_squared_error"])}
                ),
            }
        )
    return records


def _paired_summary(
    left: ReferencePublication, right: ReferencePublication, split_ids: list[str], reason: str
):
    if not split_ids:
        return dict(
            available=False,
            reason=reason,
            split_ids=[],
            b0=None,
            b0h=None,
            differences=None,
            cell_differences=[],
            declared_cohort_cell_differences=[],
        )
    summaries = []
    for publication in (left, right):
        predictions = publication.predictions[publication.predictions.split_id.isin(split_ids)]
        statuses = tuple(s for s in publication.statuses if s.split_id in split_ids)
        summaries.append(summarize_benchmark(predictions, statuses, split_ids))
    a, b = summaries
    return dict(
        available=True,
        reason=None,
        split_ids=split_ids,
        b0=a,
        b0h=b,
        differences=_differences(a["metrics"], b["metrics"]),
        cell_differences=_cell_differences(a, b, "cell_metrics", ("region_id", "variant_group")),
        declared_cohort_cell_differences=_cell_differences(
            a, b, "declared_cohort_cell_metrics", ("region_id", "variant_group", "cohort_id")
        ),
    )


def compare_reference_publications(b0: Mapping[str, bytes], b0h: Mapping[str, bytes]) -> dict[str, object]:
    """Return descriptive paired diagnostics; corrupt or mismatched evidence raises ValueError."""
    left = decode_reference_publication(b0, heterogeneity=False)
    right = decode_reference_publication(b0h, heterogeneity=True)
    _validate_pair(left, right)
    common = [
        a["split_id"]
        for a, b in zip(left.folds, right.folds, strict=True)
        if a["status"] == b["status"] == "completed"
    ]
    complete = len(common) == 5
    matched = int(left.predictions.split_id.isin(common).sum())
    total, unavailable = left.summary["total_row_count"], left.summary["unavailable_row_count"]
    return {
        "schema_version": 1,
        "evidence_kind": "descriptive_paired_comparison",
        "publication_eligible": False,
        "comparison_complete": complete,
        "target": left.manifest["target"],
        "evidence_role": left.manifest["configuration"]["evidence_role"],
        "difference_direction": "B0H_minus_B0",
        "limitations": [
            "Source population groups and adjacent variants are dependent development evidence.",
            "No independence-based confidence intervals, winner, or promotion claim.",
            "No external generalization, geographic, resident-population, or joint-LD claim.",
            "Conditional metrics describe only folds completed in both models.",
            "Narrower intervals alone do not establish improvement.",
        ],
        "publication_fingerprints": {
            "b0": fingerprint(b0["manifest.json"]),
            "b0h": fingerprint(b0h["manifest.json"]),
        },
        "configurations": {"b0": left.manifest["configuration"], "b0h": right.manifest["configuration"]},
        "input_files": left.manifest["input_files"],
        "dependency_qualification": left.manifest["dependency_qualification"],
        "seeds": {"b0": left.manifest["seeds"], "b0h": right.manifest["seeds"]},
        "source_provenance": {
            name: {
                key: publication.manifest[key]
                for key in ("git", "science_source_sha256", "package_versions", "limitations")
            }
            for name, publication in (("b0", left), ("b0h", right))
        },
        "fold_outcomes": [
            {"split_id": a["split_id"], "b0": a, "b0h": b}
            for a, b in zip(left.folds, right.folds, strict=True)
        ],
        "fit_diagnostics_b0h": right.fit_diagnostics,
        "row_status": {"b0": list(left.row_status), "b0h": list(right.row_status)},
        "counts": {
            "total_rows": total,
            "matched_rows": matched,
            "unavailable_rows": unavailable,
            "excluded_scoreable_rows": total - unavailable - matched,
            "failed_rows_b0": left.summary["failed_row_count"],
            "failed_rows_b0h": right.summary["failed_row_count"],
        },
        "model_run_summaries": {"b0": left.summary, "b0h": right.summary},
        "full_pair": _paired_summary(left, right, common if complete else [], "incomplete_pair"),
        "completed_fold_conditional": _paired_summary(left, right, common, "no_common_completed_folds"),
    }

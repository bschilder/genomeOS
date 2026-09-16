#!/usr/bin/env python3
"""Render geographic B1 support and matched held-out score evidence (design §§4–8; #307).

The map shows measured query locations only. It never draws an inferred surface. The score panel
compares B1 with B0 on the exact rows emitted by the explicitly post-hoc fixed-2,000 km support
sensitivity. The prespecified primary result remains separate in the annotation and JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.validation.benchmark import BenchmarkFoldStatus, summarize_benchmark  # noqa: E402
from genomeos.viz.basemap import draw_countries  # noqa: E402

PRIMARY_ROLE = "prespecified_primary"
SENSITIVITY_ROLE = "posthoc_sensitivity"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot source-neutral HbS B1 support and matched B1-minus-B0 count scores."
    )
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--primary", required=True, type=Path)
    parser.add_argument("--sensitivity", required=True, type=Path)
    parser.add_argument("--b0", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def _artifact(path: Path, role: str) -> tuple[dict[str, object], dict[str, object]]:
    manifest = _json(path / "manifest.json")
    summary = _json(path / "summary.json")
    if manifest.get("model", {}).get("model_id") != "B1-local-count":
        raise ValueError(f"{path} is not a B1 local-count artifact")
    if manifest.get("analysis_role") != role or summary.get("analysis_role") != role:
        raise ValueError(f"{path} must have analysis_role={role!r}")
    if manifest.get("publication_eligible") is not False:
        raise ValueError(f"{path} must remain nonpublication evidence")
    return manifest, summary["benchmark"]


def _finite_or_infinity(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace("-Infinity", -np.inf), errors="raise")


def _matched_b0_summary(
    b0_predictions: pd.DataFrame,
    sensitivity_predictions: pd.DataFrame,
    sensitivity_manifest: dict[str, object],
) -> dict[str, object]:
    keys = sensitivity_predictions.loc[:, ["split_id", "source_record_id"]]
    matched = b0_predictions.merge(keys, on=["split_id", "source_record_id"], validate="one_to_one")
    statuses = []
    split_ids = []
    for split in sensitivity_manifest["splits"]:
        split_id = split["split_id"]
        result = split["result"]
        emitted = tuple(result["emitted_test_ids"])
        split_ids.append(split_id)
        if emitted:
            statuses.append(BenchmarkFoldStatus(split_id, "completed", emitted, None))
        else:
            statuses.append(
                BenchmarkFoldStatus(
                    split_id,
                    result["status"],
                    tuple(result["expected_test_ids"]),
                    result["failure_reason"],
                )
            )
    return summarize_benchmark(matched, statuses, tuple(split_ids))


def _row_metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    delta = frame["log_score_b1"] - frame["log_score_b0"]
    return {
        "observation_count": int(len(frame)),
        "b1_mean_log_score": float(frame["log_score_b1"].mean()),
        "b0_mean_log_score": float(frame["log_score_b0"].mean()),
        "mean_log_score_delta": float(delta.mean()),
        "median_log_score_delta": float(delta.median()),
        "b1_mae": float(frame["absolute_error_b1"].mean()),
        "b0_mae": float(frame["absolute_error_b0"].mean()),
        "b1_coverage_95": float(frame["coverage_95_b1"].mean()),
        "b0_coverage_95": float(frame["coverage_95_b0"].mean()),
    }


def _candidate_summary(path: Path) -> list[dict[str, object]]:
    frame = pd.read_csv(path / "bandwidth_selection.tsv", sep="\t")
    records = []
    for bandwidth, group in frame.groupby("bandwidth_km", sort=True):
        records.append(
            {
                "bandwidth_km": float(bandwidth),
                "outer_fold_count": int(len(group)),
                "eligible_outer_fold_count": int(group["eligible"].sum()),
                "minimum_inner_emission_fraction": float(group["emission_fraction"].min()),
                "mean_inner_emission_fraction": float(group["emission_fraction"].mean()),
                "maximum_inner_emission_fraction": float(group["emission_fraction"].max()),
            }
        )
    return records


def _compact_benchmark(summary: dict[str, object]) -> dict[str, object]:
    supported = summary["supported_only_benchmark"]
    return {
        "comparison_complete": summary["comparison_complete"],
        "requested_observation_count": summary["requested_observation_count"],
        "emitted_observation_count": summary["emitted_observation_count"],
        "excluded_observation_count": summary["excluded_observation_count"],
        "excluded_fraction": summary["excluded_fraction"],
        "supported_only": {
            "metrics": supported["metrics"],
            "scored_observation_count": supported["scored_observation_count"],
            "split_counts": supported["split_counts"],
        },
    }


def _build_report(
    observations_path: Path,
    primary_path: Path,
    sensitivity_path: Path,
    b0_path: Path,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    primary_manifest, primary_summary = _artifact(primary_path, PRIMARY_ROLE)
    sensitivity_manifest, sensitivity_summary = _artifact(
        sensitivity_path, SENSITIVITY_ROLE
    )
    b0_manifest = _json(b0_path / "manifest.json")
    if b0_manifest.get("model", {}).get("model_id") != "B0":
        raise ValueError("b0 must be a B0 benchmark artifact")
    expected_inputs = primary_manifest["input_files"]
    if (
        sensitivity_manifest["input_files"] != expected_inputs
        or b0_manifest["input_files"] != expected_inputs
    ):
        raise ValueError("B0, primary B1, and sensitivity B1 must use byte-identical inputs")

    observations = pd.read_csv(
        observations_path,
        sep="\t",
        usecols=["source_record_id", "lat", "lon"],
        dtype={"source_record_id": str},
    )
    if observations["source_record_id"].duplicated().any():
        raise ValueError("observation source_record_id values must be unique")
    support = pd.read_csv(
        sensitivity_path / "support.tsv", sep="\t", keep_default_na=False
    ).merge(observations, on="source_record_id", validate="one_to_one")
    sensitivity_predictions = pd.read_csv(sensitivity_path / "predictions.tsv", sep="\t")
    b0_predictions = pd.read_csv(b0_path / "predictions.tsv", sep="\t")
    sensitivity_predictions["log_score"] = _finite_or_infinity(
        sensitivity_predictions["log_score"]
    )
    b0_predictions["log_score"] = _finite_or_infinity(b0_predictions["log_score"])
    matched = sensitivity_predictions.merge(
        b0_predictions,
        on=["split_id", "source_record_id"],
        suffixes=("_b1", "_b0"),
        validate="one_to_one",
    )
    matched["log_score_delta"] = matched["log_score_b1"] - matched["log_score_b0"]
    matched["count_stratum"] = np.where(matched["observed_ac_b1"] > 0, "positive", "zero")
    strata = {
        str(label): _row_metrics(group)
        for label, group in matched.groupby("count_stratum", sort=True)
    }
    b0_matched = _matched_b0_summary(
        b0_predictions, sensitivity_predictions, sensitivity_manifest
    )
    refusal_counts = {
        str(reason or "emitted"): int(count)
        for reason, count in support["refusal_reason"].value_counts(dropna=False).items()
    }
    report = {
        "schema_version": 1,
        "scientific_promotion_decision": "not_made",
        "publication_eligible": False,
        "source_specific_features": False,
        "environmental_covariates": False,
        "input_sha256": {
            "observations": _sha256(observations_path),
            "assignments": expected_inputs["assignments"]["sha256"],
            "dependencies": expected_inputs["dependencies"]["sha256"],
        },
        "primary": {
            "analysis_role": PRIMARY_ROLE,
            "configuration": primary_manifest["configuration"],
            "qualification": primary_manifest["qualification"],
            "benchmark": _compact_benchmark(primary_summary),
            "candidate_summary": _candidate_summary(primary_path),
        },
        "sensitivity": {
            "analysis_role": SENSITIVITY_ROLE,
            "configuration": sensitivity_manifest["configuration"],
            "qualification": sensitivity_manifest["qualification"],
            "benchmark": _compact_benchmark(sensitivity_summary),
            "support_state_counts": refusal_counts,
            "matched_row_weighted": _row_metrics(matched),
            "matched_count_strata": strata,
            "matched_b0_macro_metrics": b0_matched["metrics"],
        },
        "b2_current": {
            "valid_comparison_available": False,
            "reason": "three_hour_cutoff_before_all_folds_completed",
        },
        "interpretation": {
            "primary": "prespecified_local_support_grid_infeasible_for_global_geographic_holdouts",
            "sensitivity": "local_signal_on_a_posthoc_support_limited_subset_only",
            "promotion": "rejected_pending_broader_support_and_zero_count_repair",
        },
    }
    return report, support, matched


def _render(report: dict[str, object], support: pd.DataFrame, matched: pd.DataFrame, out: Path) -> None:
    emitted = support["status"] == "emitted"
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 6.3))
    figure.subplots_adjust(left=0.07, right=0.985, bottom=0.18, top=0.82, wspace=0.13)
    map_ax, score_ax = axes
    draw_countries(map_ax, color="#9aa0a6", linewidth=0.45, zorder=1)
    map_ax.scatter(
        support.loc[~emitted, "lon"],
        support.loc[~emitted, "lat"],
        s=8,
        color="#c8cdd2",
        alpha=0.58,
        linewidths=0,
        label="Refused",
        zorder=2,
    )
    map_ax.scatter(
        support.loc[emitted, "lon"],
        support.loc[emitted, "lat"],
        s=13,
        color="#1769aa",
        alpha=0.85,
        linewidths=0,
        label="Emitted",
        zorder=3,
    )
    map_ax.set(xlim=(-180, 180), ylim=(-60, 85), xlabel="Longitude", ylabel="Latitude")
    map_ax.set_title("A  Fixed 2,000 km sensitivity: actual query locations", loc="left")
    map_ax.legend(frameon=False, loc="lower left", ncols=2)
    map_ax.grid(color="#eceff1", linewidth=0.5, zorder=0)

    colors = np.where(matched["count_stratum"] == "positive", "#1769aa", "#d97706")
    score_ax.scatter(
        matched["nearest_edge_distance_km"],
        matched["log_score_delta"],
        s=15,
        color=colors,
        alpha=0.72,
        linewidths=0,
    )
    score_ax.axhline(0.0, color="#343a40", linewidth=1.0)
    score_ax.set_yscale("symlog", linthresh=10.0, linscale=0.7)
    score_ax.set(
        xlim=(0, 2000),
        xlabel="Nearest training-footprint edge distance (km)",
        ylabel="Held-out log score difference, B1 − B0 (symlog)",
    )
    score_ax.set_title("B  Matched emitted rows: local count evidence vs pooled B0", loc="left")
    score_ax.grid(color="#eceff1", linewidth=0.5)
    score_ax.scatter([], [], s=20, color="#1769aa", label="Positive count")
    score_ax.scatter([], [], s=20, color="#d97706", label="Zero count")
    score_ax.legend(frameon=False, loc="lower right")

    primary = report["primary"]["benchmark"]
    sensitivity = report["sensitivity"]["benchmark"]
    strata = report["sensitivity"]["matched_count_strata"]
    figure.suptitle(
        "HbS B1 local counts: positive-count gains, sparse support, worse zeros",
        fontsize=15,
        fontweight="bold",
        y=0.96,
    )
    figure.text(
        0.5,
        0.045,
        (
            f"Prespecified primary emitted {primary['emitted_observation_count']}/"
            f"{primary['requested_observation_count']}; post-hoc sensitivity emitted "
            f"{sensitivity['emitted_observation_count']}/{sensitivity['requested_observation_count']} "
            f"({100 * sensitivity['excluded_fraction']:.1f}% excluded).  "
            f"Mean Δ log score: positive {strata['positive']['mean_log_score_delta']:+.1f}, "
            f"zero {strata['zero']['mean_log_score_delta']:+.2f} nats/observation."
        ),
        ha="center",
        fontsize=9.5,
        color="#343a40",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        out,
        dpi=190,
        facecolor="white",
        metadata={"Software": "genomeOS B1 local-count evidence renderer v1"},
    )
    plt.close(figure)


def main() -> int:
    args = _parser().parse_args()
    report, support, matched = _build_report(
        args.observations, args.primary, args.sensitivity, args.b0
    )
    _render(report, support, matched, args.out)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.validation.benchmark import BenchmarkFoldStatus, summarize_benchmark  # noqa: E402
from genomeos.validation.local_count_artifact import (  # noqa: E402
    SUMMARY_ATOL,
    SUMMARY_RTOL,
    read_local_count_comparison,
)
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
    undefined = int(delta.isna().sum())
    opposite = bool(np.isposinf(delta).any() and np.isneginf(delta).any())
    return {
        "observation_count": int(len(frame)),
        "b1_mean_log_score": float(frame["log_score_b1"].mean()),
        "b0_mean_log_score": float(frame["log_score_b0"].mean()),
        "mean_log_score_delta": float(np.mean(delta.to_numpy())),
        "paired_delta_available": not undefined and not opposite,
        "undefined_delta_count": undefined,
        "positive_infinite_delta_count": int(np.isposinf(delta).sum()),
        "negative_infinite_delta_count": int(np.isneginf(delta).sum()),
        "paired_delta_unavailable_reason": "undefined_paired_scores"
        if undefined
        else ("opposite_infinite_differences" if opposite else None),
        "median_log_score_delta": float(np.median(delta.to_numpy())),
        "b1_mae": float(frame["absolute_error_b1"].mean()),
        "b0_mae": float(frame["absolute_error_b0"].mean()),
        "b1_coverage_95": float(frame["coverage_95_b1"].mean()),
        "b0_coverage_95": float(frame["coverage_95_b0"].mean()),
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None if np.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    return value


def _stratified(support: pd.DataFrame, matched: pd.DataFrame) -> dict[str, object]:
    frame = support.copy()
    frame["denominator"] = pd.cut(
        frame["an"], [0, 100, 1000, 10000, np.inf], labels=["1–100", "101–1000", "1001–10000", ">10000"]
    )
    frame["distance_km"] = pd.cut(
        frame["nearest_edge_distance_km"],
        [-np.inf, 500, 1000, 2000, np.inf],
        labels=["0–500", ">500–1000", ">1000–2000", ">2000"],
    )
    frame["distance_km"] = frame["distance_km"].cat.add_categories(["unavailable"]).fillna("unavailable")
    frame["count"] = np.where(frame["ac"] == 0, "zero", "positive")
    result = {
        "analysis_role": "posthoc_descriptive_strata",
        "intervals": "right_closed",
        "endemic_background": {
            "available": False,
            "review_state": "not_reviewed",
            "reason": "no_existing_reviewed_outcome_independent_definition",
            "acceptance_item": "open",
        },
    }
    for name in ("count", "denominator", "distance_km"):
        rows = []
        for label, group in frame.groupby(name, observed=True, sort=True):
            keys = group[["split_id", "source_record_id"]]
            scored = matched.merge(keys, on=["split_id", "source_record_id"], validate="one_to_one")
            emitted = int((group["status"] == "emitted").sum())
            rows.append(
                {
                    "stratum": str(label),
                    "requested_count": len(group),
                    "emitted_count": emitted,
                    "refused_count": len(group) - emitted,
                    "emission_fraction": emitted / len(group),
                    "refusal_counts": {
                        str(k): int(v)
                        for k, v in group.loc[group.status != "emitted", "refusal_reason"]
                        .value_counts()
                        .items()
                    },
                    "matched_scores": _row_metrics(scored) if len(scored) else None,
                }
            )
        result[name] = rows
    return result


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
    (
        manifests,
        summaries,
        support,
        sensitivity_predictions,
        b0_predictions,
        primary_support,
        primary_predictions,
    ) = read_local_count_comparison(observations_path, primary_path, sensitivity_path, b0_path)
    primary_manifest, sensitivity_manifest, _ = manifests
    primary_summary, sensitivity_summary, _ = summaries
    expected_inputs = primary_manifest["input_files"]
    matched = sensitivity_predictions.merge(
        b0_predictions,
        on=["split_id", "source_record_id"],
        suffixes=("_b1", "_b0"),
        validate="one_to_one",
    )
    primary_matched = primary_predictions.merge(
        b0_predictions, on=["split_id", "source_record_id"], suffixes=("_b1", "_b0"), validate="one_to_one"
    )
    matched["log_score_delta"] = matched["log_score_b1"] - matched["log_score_b0"]
    matched["count_stratum"] = np.where(matched["observed_ac_b1"] > 0, "positive", "zero")
    strata = {str(label): _row_metrics(group) for label, group in matched.groupby("count_stratum", sort=True)}
    b0_matched = _matched_b0_summary(b0_predictions, sensitivity_predictions, sensitivity_manifest)
    refusal_counts = {
        str(reason or "emitted"): int(count)
        for reason, count in support["refusal_reason"].value_counts(dropna=False).items()
    }
    report = {
        "schema_version": 2,
        "summary_replay_tolerance": {"rtol": SUMMARY_RTOL, "atol": SUMMARY_ATOL},
        "retained_manifest_sha256": {
            "primary": _sha256(primary_path / "manifest.json"),
            "sensitivity": _sha256(sensitivity_path / "manifest.json"),
            "b0": _sha256(b0_path / "manifest.json"),
        },
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
            "retained_evidence_strata": _stratified(primary_support, primary_matched),
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
            "retained_evidence_strata": _stratified(support, matched),
        },
        "b2_current": {
            "valid_comparison_available": False,
            "reason": "later_completed_development_result_lacks_required_convergence_evidence",
            "historical_snapshot": {
                "date": "2026-09-16",
                "run": "hbs-current-gp-benchmark-20260916-v1-partial",
                "reason": "three_hour_cutoff_before_all_folds_completed",
            },
            "later_development_result": {
                "date": "2026-09-17",
                "report": "docs/research/hbs-current-gp-benchmark-2026-09-17.json",
                "pull_request": "https://github.com/bschilder/genomeOS/pull/332",
                "report_sha256": _sha256(
                    Path(__file__).resolve().parents[1]
                    / "docs/research/hbs-current-gp-benchmark-2026-09-17.json"
                ),
                "completed_observation_count": 994,
                "qualification": "not_convergence_qualified_and_calibration_gates_not_met",
                "comparison": "no_qualified_matched_B2_available;_old_results_not_retroactively_qualified",
            },
        },
        "interpretation": {
            "primary": "prespecified_local_support_grid_infeasible_for_global_geographic_holdouts",
            "sensitivity": "local_signal_on_a_posthoc_support_limited_subset_only",
            "promotion": "rejected_pending_broader_support_and_zero_count_repair",
        },
    }
    return _json_safe(report), support, matched


def _format_score(metrics: dict) -> str:
    value = metrics.get("mean_log_score_delta")
    return f"{value:+.2f}" if isinstance(value, (int, float)) else str(value or "undefined")


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

    finite = np.isfinite(matched["log_score_delta"])
    plotted = matched.loc[finite]
    colors = np.where(plotted["count_stratum"] == "positive", "#1769aa", "#d97706")
    score_ax.scatter(
        plotted["nearest_edge_distance_km"],
        plotted["log_score_delta"],
        s=15,
        color=colors,
        alpha=0.72,
        linewidths=0,
    )
    if not finite.all():
        score_ax.text(
            0.02,
            0.98,
            f"{int((~finite).sum())} infinite/undefined paired scores retained in JSON",
            transform=score_ax.transAxes,
            va="top",
            fontsize=8,
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
            f"Mean Δ log score: positive {_format_score(strata.get('positive', {}))}, "
            f"zero {_format_score(strata.get('zero', {}))} nats/observation."
        ),
        ha="center",
        fontsize=9.5,
        color="#343a40",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as output:
        figure.savefig(
            output,
            format="png",
            dpi=190,
            facecolor="white",
            metadata={"Software": "genomeOS B1 local-count evidence renderer v2"},
        )
    plt.close(figure)


def main() -> int:
    args = _parser().parse_args()
    for path in (args.out, args.report):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"output already exists; use a new version: {path}")
    destinations = args.out.resolve(), args.report.resolve()
    if destinations[0] == destinations[1] or any(
        left in right.parents for left, right in (destinations, destinations[::-1])
    ):
        raise ValueError("figure and report destinations must be distinct and non-nested")
    report, support, matched = _build_report(args.observations, args.primary, args.sensitivity, args.b0)
    payload = json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with (
        TemporaryDirectory(prefix=".b1-figure-", dir=args.out.parent) as figure_dir,
        TemporaryDirectory(prefix=".b1-report-", dir=args.report.parent) as report_dir,
    ):
        temporary_figure = Path(figure_dir) / "figure.png"
        temporary_report = Path(report_dir) / "report.json"
        _render(report, support, matched, temporary_figure)
        with temporary_report.open("x") as output:
            output.write(payload)
        # Hard links create complete files exclusively, including against racing symlinks.
        os.link(temporary_figure, args.out)
        try:
            os.link(temporary_report, args.report)
        except OSError:
            # Roll back only our own published inode, never a competing replacement.
            if not args.out.is_symlink() and args.out.exists() and args.out.samefile(temporary_figure):
                args.out.unlink()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

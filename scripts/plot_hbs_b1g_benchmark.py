#!/usr/bin/env python3
"""Render the matched HbS B1G comparison (design §§4–8, 12; issue #331).

Both map panels show measured held-out survey locations. They encode B1G-minus-B2 predictive
differences and never draw an inferred allele-frequency surface. The JSON report also retains the
required B1G-minus-B0 comparison and leaves scientific promotion unset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as colors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.validation.b1g_comparison import compare_b1g_benchmarks  # noqa: E402
from genomeos.viz.basemap import draw_countries  # noqa: E402

STRONGEST_BASELINE = "B2-current"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--b0", required=True, type=Path)
    parser.add_argument("--b2", required=True, type=Path)
    parser.add_argument("--b1g", required=True, type=Path)
    parser.add_argument("--checkpoint-header", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_record(path: Path) -> dict[str, object]:
    return {"sha256": _sha256(path), "size_bytes": path.stat().st_size}


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must contain an object: {path}")
    return value


def _verify_output_files(root: Path, manifest: Mapping[str, object]) -> None:
    records = manifest.get("output_files")
    if not isinstance(records, Mapping) or not records:
        raise ValueError(f"artifact has no output file inventory: {root}")
    for name, expected in records.items():
        path = root / str(name)
        if not path.is_file() or _file_record(path) != expected:
            raise ValueError(f"artifact output differs from its manifest: {path}")


def _read_predictions(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", keep_default_na=False)
    frame["log_score"] = pd.to_numeric(
        frame["log_score"].replace("-Infinity", -np.inf), errors="raise"
    )
    for column in ("coverage_50", "coverage_80", "coverage_95"):
        if not frame[column].isin((True, False)).all():
            raise ValueError(f"{path} contains invalid {column} values")
        frame[column] = frame[column].astype(bool)
    return frame


def _artifact(
    root: Path, expected_model: str
) -> tuple[dict[str, object], dict[str, object], pd.DataFrame]:
    manifest = _read_json(root / "manifest.json")
    summary = _read_json(root / "summary.json")
    model = manifest.get("model")
    if not isinstance(model, dict) or model.get("model_id") != expected_model:
        raise ValueError(f"{root} is not a {expected_model} artifact")
    if manifest.get("publication_eligible") is not False:
        raise ValueError(f"{root} must remain nonpublication evidence")
    if summary.get("model_id") != expected_model or summary.get("publication_eligible") is not False:
        raise ValueError(f"{root} summary identity differs from its manifest")
    _verify_output_files(root, manifest)
    return manifest, summary, _read_predictions(root / "predictions.tsv")


def _equivalent_summary(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(
            _equivalent_summary(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _equivalent_summary(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, float):
        return bool(np.isclose(left, right, rtol=1e-14, atol=1e-15, equal_nan=False))
    return left == right


def _compact_benchmark(summary: Mapping[str, object]) -> dict[str, object]:
    return {
        "comparison_complete": summary["comparison_complete"],
        "split_counts": summary["split_counts"],
        "scored_observation_count": summary["scored_observation_count"],
        "represented_cell_count": summary["represented_cell_count"],
        "represented_declared_cohort_cell_count": summary[
            "represented_declared_cohort_cell_count"
        ],
        "zero_probability_count": summary["zero_probability_count"],
        "metrics": summary["metrics"],
    }


def _verify_summary_replay(
    report: Mapping[str, object],
    candidate_summary: Mapping[str, object],
    b0_summary: Mapping[str, object],
    b2_summary: Mapping[str, object],
) -> None:
    comparisons = report["comparisons"]
    for model, expected in (("B0", b0_summary), ("B2-current", b2_summary)):
        comparison = comparisons[model]
        if not _equivalent_summary(
            comparison["candidate_benchmark"], candidate_summary["benchmark"]
        ):
            raise ValueError(f"recomputed B1G summary differs in the {model} comparison")
        if not _equivalent_summary(comparison["baseline_benchmark"], expected["benchmark"]):
            raise ValueError(f"recomputed {model} summary differs from its artifact")


def build_report(
    observations_path: Path,
    b0_path: Path,
    b2_path: Path,
    b1g_path: Path,
    checkpoint_header_path: Path,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Validate immutable artifacts and return the dual comparison plus plotting rows."""
    b0_manifest, b0_summary, b0_predictions = _artifact(b0_path, "B0")
    b2_manifest, b2_summary, b2_predictions = _artifact(b2_path, "B2-current")
    b1g_manifest, b1g_summary, b1g_predictions = _artifact(b1g_path, "B1G")
    checkpoint_header = _read_json(checkpoint_header_path)
    report, matched = compare_b1g_benchmarks(
        b1g_predictions,
        b0_predictions,
        b2_predictions,
        candidate_manifest=b1g_manifest,
        candidate_checkpoint_header=checkpoint_header,
        b0_manifest=b0_manifest,
        b2_manifest=b2_manifest,
    )
    _verify_summary_replay(report, b1g_summary, b0_summary, b2_summary)

    expected_observations = b0_manifest["input_files"]["observations"]
    if _file_record(observations_path) != expected_observations:
        raise ValueError("observation table differs from the frozen B0/B1G input")
    observations = pd.read_csv(
        observations_path,
        sep="\t",
        usecols=["source_record_id", "lat", "lon"],
        dtype={"source_record_id": str},
    )
    if observations["source_record_id"].duplicated().any():
        raise ValueError("observation source_record_id values must be unique")
    plotting_rows = matched[STRONGEST_BASELINE].merge(
        observations, on="source_record_id", validate="one_to_one"
    )
    if not np.isfinite(plotting_rows[["lat", "lon"]].to_numpy(dtype=float)).all():
        raise ValueError("matched observations contain nonfinite coordinates")

    report["artifact_identity"].update(
        {
            "candidate_manifest": _file_record(b1g_path / "manifest.json"),
            "checkpoint_header": _file_record(checkpoint_header_path),
            "baseline_manifests": {
                "B0": _file_record(b0_path / "manifest.json"),
                "B2-current": _file_record(b2_path / "manifest.json"),
            },
        }
    )
    report["summary_replay_validation"] = {
        "structure_and_symbolic_values": "exact",
        "float_relative_tolerance": 1e-14,
        "float_absolute_tolerance": 1e-15,
        "candidate_passed": True,
        "baselines_passed": {"B0": True, "B2-current": True},
    }
    for comparison in report["comparisons"].values():
        comparison["candidate_benchmark"] = _compact_benchmark(
            comparison["candidate_benchmark"]
        )
        comparison["baseline_benchmark"] = _compact_benchmark(
            comparison["baseline_benchmark"]
        )
    return report, plotting_rows


def _symmetric_limit(values: pd.Series, *, floor: float) -> float:
    finite = np.abs(values.astype(float).to_numpy())
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return floor
    return max(floor, float(np.quantile(finite, 0.95)))


def build_figure(report: Mapping[str, object], matched: pd.DataFrame):
    """Build an observation-only geographic and predictive-calibration figure."""
    figure, axes = plt.subplots(1, 3, figsize=(18.0, 6.2))
    figure.subplots_adjust(left=0.045, right=0.99, bottom=0.19, top=0.83, wspace=0.19)
    log_ax, error_ax, calibration_ax = axes
    for axis in (log_ax, error_ax):
        draw_countries(axis, color="#a7adb4", linewidth=0.45, zorder=1)
        axis.set(xlim=(-180, 180), ylim=(-60, 85), xlabel="Longitude", ylabel="Latitude")
        axis.grid(color="#eceff1", linewidth=0.5, zorder=0)

    log_limit = _symmetric_limit(matched["log_score_delta"], floor=1.0)
    raw_log = matched["log_score_delta"].to_numpy(dtype=float)
    plotted_log = np.nan_to_num(raw_log, nan=0.0, posinf=log_limit, neginf=-log_limit)
    log_order = np.argsort(np.abs(plotted_log))
    log_edgecolors = np.zeros((len(matched), 4), dtype=float)
    log_edgecolors[np.isnan(raw_log)] = (0.12, 0.12, 0.12, 1.0)
    log_linewidths = np.where(np.isnan(raw_log), 0.9, 0.0)
    log_scatter = log_ax.scatter(
        matched.iloc[log_order]["lon"],
        matched.iloc[log_order]["lat"],
        c=plotted_log[log_order],
        s=16,
        marker="o",
        cmap="RdYlGn",
        norm=colors.SymLogNorm(
            linthresh=max(0.25, log_limit / 50.0),
            vmin=-log_limit,
            vmax=log_limit,
            base=10,
        ),
        edgecolors=log_edgecolors[log_order],
        linewidths=log_linewidths[log_order],
        alpha=0.82,
        zorder=2,
    )
    figure.colorbar(log_scatter, ax=log_ax, shrink=0.72, pad=0.015).set_label(
        "B1G − B2 held-out log score (green = B1G better)"
    )
    if np.isnan(raw_log).any():
        log_ax.scatter(
            [],
            [],
            marker="o",
            facecolor="#fee08b",
            edgecolor="#1f1f1f",
            linewidth=0.9,
            label="Undefined paired score",
        )
        log_ax.legend(frameon=False, loc="lower left")
    log_ax.set_title("A  Count score at measured held-out surveys", loc="left")

    errors = matched["absolute_error_improvement"]
    error_limit = _symmetric_limit(errors, floor=0.001)
    error_order = np.argsort(np.abs(errors.to_numpy(dtype=float)))
    error_scatter = error_ax.scatter(
        matched.iloc[error_order]["lon"],
        matched.iloc[error_order]["lat"],
        c=matched.iloc[error_order]["absolute_error_improvement"],
        s=16,
        marker="o",
        cmap="RdYlGn",
        norm=colors.TwoSlopeNorm(vmin=-error_limit, vcenter=0.0, vmax=error_limit),
        linewidths=0,
        alpha=0.82,
        zorder=2,
    )
    figure.colorbar(error_scatter, ax=error_ax, shrink=0.72, pad=0.015).set_label(
        "B2 − B1G absolute frequency error (green = B1G better)"
    )
    error_ax.set_title("B  Error change at the same surveys", loc="left")

    comparison = report["comparisons"][STRONGEST_BASELINE]
    candidate = comparison["candidate_benchmark"]["metrics"]
    baseline = comparison["baseline_benchmark"]["metrics"]
    levels = np.array([50, 80, 95], dtype=float)
    candidate_coverage = 100.0 * np.array(
        [candidate[f"coverage_{int(level)}"] for level in levels], dtype=float
    )
    baseline_coverage = 100.0 * np.array(
        [baseline[f"coverage_{int(level)}"] for level in levels], dtype=float
    )
    calibration_ax.plot(levels, levels, color="#72777d", linestyle="--", label="Nominal")
    calibration_ax.plot(
        levels, baseline_coverage, color="#d97706", marker="o", linewidth=2, label="B2"
    )
    calibration_ax.plot(
        levels, candidate_coverage, color="#1b8a5a", marker="o", linewidth=2, label="B1G"
    )
    calibration_ax.fill_between(
        levels,
        levels - 3.0,
        levels + 3.0,
        color="#9aa0a6",
        alpha=0.14,
        label="±3 percentage points",
    )
    calibration_ax.set(
        xlim=(47, 98),
        ylim=(0, 100),
        xlabel="Nominal predictive interval coverage (%)",
        ylabel="Balanced macro empirical coverage (%)",
    )
    calibration_ax.set_title("C  Predictive interval calibration", loc="left")
    calibration_ax.grid(color="#eceff1", linewidth=0.5)
    calibration_ax.legend(frameon=False, loc="upper left")

    differences = comparison["balanced_macro_metric_differences"]
    interval = comparison["paired_outer_block_log_score_interval"]
    log_difference = differences["mean_log_score"]
    log_text = (
        f"{log_difference['value']:+.2f}"
        if log_difference["available"] and isinstance(log_difference["value"], float)
        else str(log_difference["value"] or log_difference["reason"])
    )
    interval_text = (
        f"[{interval['lower']:+.2f}, {interval['upper']:+.2f}]"
        if interval["available"]
        else str(interval["reason"])
    )
    figure.suptitle(
        "HbS compact positive-basis B1G versus current B2 on matched geographic holdouts",
        fontsize=15,
        fontweight="bold",
        y=0.965,
    )
    figure.text(
        0.5,
        0.045,
        (
            f"Matched n={comparison['matched_observation_count']}; balanced macro Δ log score "
            f"{log_text}; exhaustive outer-block 95% interval {interval_text}; relative MAE "
            f"improvement {100 * differences['relative_mae_improvement']:+.1f}%.  "
            "Development evidence; unresolved dependency/stratum gates; no promotion decision."
        ),
        ha="center",
        fontsize=9.2,
        color="#343a40",
    )
    return figure


def render(report: Mapping[str, object], matched: pd.DataFrame, out: Path) -> None:
    figure = build_figure(report, matched)
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        out,
        dpi=190,
        facecolor="white",
        metadata={"Software": "genomeOS matched B1G benchmark renderer v1"},
    )
    plt.close(figure)


def main() -> int:
    args = _parser().parse_args()
    if args.out.exists() or args.report.exists():
        raise FileExistsError("output figure and report paths must be new")
    report, matched = build_report(
        args.observations,
        args.b0,
        args.b2,
        args.b1g,
        args.checkpoint_header,
    )
    render(report, matched, args.out)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

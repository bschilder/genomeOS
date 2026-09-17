#!/usr/bin/env python3
"""Render the matched HbS B2-current versus B0 comparison (design §§4–8; issue #189).

Both map panels show measured held-out query locations. They encode paired predictive differences
at those observations and never draw an inferred allele-frequency surface. The report replays the
frozen benchmark summaries, preserves every held-out row, and leaves scientific promotion unset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as colors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.validation.benchmark import BenchmarkFoldStatus  # noqa: E402
from genomeos.validation.paired_benchmark import compare_paired_benchmarks  # noqa: E402
from genomeos.viz.basemap import draw_countries  # noqa: E402

PREREGISTRATION_URL = (
    "https://github.com/bschilder/genomeOS/issues/189#issuecomment-5705882045"
)
BYTE_IDENTICAL_INPUTS = ("assignments", "dependencies")
OBSERVATIONS_TSV_SHA256 = "820d725fae9859a6cebca98296676e8c525b103f7033aa5237b9aaa00f79b331"
OBSERVATIONS_PARQUET_SHA256 = (
    "466034e22015ce5f4e0b90067adb2232491b625591d50c8ac83d955565345b4b"
)
RHAT_WARNING = "The rhat statistic is larger than 1.01 for some parameters."
DIVERGENCE_WARNING = "There was 1 divergence after tuning."
CORE_SPLIT_FIELDS = (
    "split_id",
    "block_id",
    "buffer_km",
    "data_version",
    "input_fingerprint",
    "train_ids",
    "test_ids",
    "excluded_ids",
    "exclusion_reasons",
    "min_edge_separation_km",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--b0", required=True, type=Path)
    parser.add_argument("--b2", required=True, type=Path)
    parser.add_argument("--run-log", required=True, type=Path)
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


def _verify_output_files(root: Path, manifest: dict[str, object]) -> None:
    records = manifest.get("output_files")
    if not isinstance(records, dict) or not records:
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


def _artifact(root: Path, expected_model: str) -> tuple[dict[str, object], dict[str, object], pd.DataFrame]:
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


def _statuses(manifest: dict[str, object]) -> tuple[tuple[BenchmarkFoldStatus, ...], tuple[str, ...]]:
    splits = manifest.get("splits")
    if not isinstance(splits, list) or len(splits) != 5:
        raise ValueError("the frozen HbS comparison requires five split records")
    statuses = tuple(
        BenchmarkFoldStatus(
            split["split_id"],
            split["status"],
            tuple(split["test_ids"]),
            split["failure_reason"],
        )
        for split in splits
    )
    return statuses, tuple(status.split_id for status in statuses)


def _verify_shared_identity(
    b0_manifest: dict[str, object], b2_manifest: dict[str, object]
) -> None:
    for name in BYTE_IDENTICAL_INPUTS:
        if b0_manifest["input_files"].get(name) != b2_manifest["input_files"].get(name):
            raise ValueError(f"B0 and B2 {name} inputs differ")
    if (
        b0_manifest["input_files"].get("observations", {}).get("sha256")
        != OBSERVATIONS_TSV_SHA256
    ):
        raise ValueError("B0 observations are not the frozen TSV serialization")
    if (
        b2_manifest["input_files"].get("observations", {}).get("sha256")
        != OBSERVATIONS_PARQUET_SHA256
    ):
        raise ValueError("B2 observations are not the frozen Parquet serialization")
    b0_configuration = b0_manifest["configuration"]
    b2_configuration = b2_manifest["configuration"]
    for field in ("buffer_km", "data_version", "seed"):
        if b0_configuration.get(field) != b2_configuration.get(field):
            raise ValueError(f"B0 and B2 configuration differs at {field}")
    b0_splits = b0_manifest["splits"]
    b2_splits = b2_manifest["splits"]
    if len(b0_splits) != len(b2_splits):
        raise ValueError("B0 and B2 split counts differ")
    for b0_split, b2_split in zip(b0_splits, b2_splits, strict=True):
        for field in CORE_SPLIT_FIELDS:
            if b0_split[field] != b2_split[field]:
                raise ValueError(f"B0 and B2 split identity differs at {field}")


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


def _compact_benchmark(summary: dict[str, object]) -> dict[str, object]:
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


def _run_diagnostics(path: Path) -> dict[str, object]:
    text = path.read_text()
    start_marker = "===== B2 CURRENT GP CHECKPOINTED "
    done_marker = "===== DONE "
    if start_marker not in text or done_marker not in text:
        raise ValueError("terminal run log is missing start or completion markers")
    science_log = text[text.index(start_marker) : text.rindex(done_marker)]
    fit_count = science_log.count("NUTS[numpyro]:")
    rhat_count = science_log.count(RHAT_WARNING)
    divergence_count = science_log.count(DIVERGENCE_WARNING)
    if fit_count != 5 or rhat_count != 5 or divergence_count != 1:
        raise ValueError("terminal run log has unexpected sampler warning counts")
    return {
        "nuts_fit_invocation_count": fit_count,
        "rhat_above_1_01_warning_count": rhat_count,
        "reported_post_tuning_divergence_count": divergence_count,
        "numerical_rhat_values_retained": False,
        "per_fold_convergence_diagnostics_retained": False,
        "convergence_acceptance": "not_met",
        "scientific_implication": "predictive_result_requires_sampler_repair_and_recheck",
    }


def build_report(
    observations_path: Path, b0_path: Path, b2_path: Path, run_log_path: Path
) -> tuple[dict[str, object], pd.DataFrame]:
    """Validate both immutable artifacts and return the frozen comparison plus plotting rows."""
    b0_manifest, b0_summary, b0_predictions = _artifact(b0_path, "B0")
    b2_manifest, b2_summary, b2_predictions = _artifact(b2_path, "B2-current")
    _verify_shared_identity(b0_manifest, b2_manifest)
    statuses, split_ids = _statuses(b2_manifest)
    comparison, matched = compare_paired_benchmarks(
        b2_predictions, b0_predictions, statuses, split_ids
    )
    if not _equivalent_summary(comparison["candidate_benchmark"], b2_summary["benchmark"]):
        raise ValueError("recomputed B2 summary differs from the published B2 summary")
    if not _equivalent_summary(comparison["baseline_benchmark"], b0_summary["benchmark"]):
        raise ValueError("recomputed B0 summary differs from the published B0 summary")
    comparison["candidate_benchmark"] = _compact_benchmark(
        comparison["candidate_benchmark"]
    )
    comparison["baseline_benchmark"] = _compact_benchmark(
        comparison["baseline_benchmark"]
    )

    expected_observations = b0_manifest["input_files"]["observations"]
    if _file_record(observations_path) != expected_observations:
        raise ValueError("observation table differs from the benchmark input")
    observations = pd.read_csv(
        observations_path,
        sep="\t",
        usecols=["source_record_id", "lat", "lon"],
        dtype={"source_record_id": str},
    )
    if observations["source_record_id"].duplicated().any():
        raise ValueError("observation source_record_id values must be unique")
    matched = matched.merge(observations, on="source_record_id", validate="one_to_one")
    if not np.isfinite(matched[["lat", "lon"]].to_numpy(dtype=float)).all():
        raise ValueError("matched observations contain nonfinite coordinates")

    report = {
        "schema_version": 1,
        "analysis_role": "prespecified_matched_development_comparison",
        "preregistration": PREREGISTRATION_URL,
        "publication_eligible": False,
        "scientific_promotion_decision": "not_made",
        "source_specific_features": False,
        "environmental_covariates": False,
        "models": {"candidate": "B2-current", "baseline": "B0"},
        "artifact_identity": {
            "candidate_manifest": _file_record(b2_path / "manifest.json"),
            "baseline_manifest": _file_record(b0_path / "manifest.json"),
            "terminal_run_log": _file_record(run_log_path),
            "byte_identical_inputs": {
                name: b0_manifest["input_files"][name] for name in BYTE_IDENTICAL_INPUTS
            },
            "observation_serializations": {
                "baseline_tsv": b0_manifest["input_files"]["observations"],
                "candidate_parquet": b2_manifest["input_files"]["observations"],
            },
            "candidate_code_revision": b2_manifest["code_revision"],
            "baseline_code_revision": b0_manifest["code_revision"],
            "candidate_configuration": b2_manifest["configuration"],
            "baseline_configuration": b0_manifest["configuration"],
        },
        "qualification": {
            "candidate": b2_manifest["qualification"],
            "dependency_aware_promotion_evidence": False,
            "reason": "dependency_review_not_checked_and_assignments_unreviewed",
        },
        "summary_replay_validation": {
            "structure_and_symbolic_values": "exact",
            "float_relative_tolerance": 1e-14,
            "float_absolute_tolerance": 1e-15,
            "candidate_passed": True,
            "baseline_passed": True,
        },
        "sampler_diagnostics": _run_diagnostics(run_log_path),
        "comparison": comparison,
        "interpretation": {
            "status": "descriptive_development_evidence",
            "automatic_winner": None,
            "next_model_change": None,
        },
    }
    return report, matched


def _symmetric_limit(values: pd.Series, *, floor: float) -> float:
    finite = np.abs(values.astype(float).to_numpy())
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return floor
    return max(floor, float(np.quantile(finite, 0.95)))


def build_figure(report: dict[str, object], matched: pd.DataFrame):
    """Build a three-panel observation-only geographic and calibration figure."""
    figure, axes = plt.subplots(1, 3, figsize=(18.0, 6.2))
    figure.subplots_adjust(left=0.045, right=0.99, bottom=0.19, top=0.83, wspace=0.19)
    log_ax, error_ax, calibration_ax = axes
    for axis in (log_ax, error_ax):
        draw_countries(axis, color="#a7adb4", linewidth=0.45, zorder=1)
        axis.set(xlim=(-180, 180), ylim=(-60, 85), xlabel="Longitude", ylabel="Latitude")
        axis.grid(color="#eceff1", linewidth=0.5, zorder=0)

    log_limit = _symmetric_limit(matched["log_score_delta"], floor=1.0)
    raw_log_values = matched["log_score_delta"].to_numpy(dtype=float)
    plotted_log_values = np.nan_to_num(
        raw_log_values, nan=0.0, posinf=log_limit, neginf=-log_limit
    )
    log_order = np.argsort(np.abs(plotted_log_values))
    log_edgecolors = np.zeros((len(matched), 4), dtype=float)
    log_edgecolors[np.isnan(raw_log_values)] = (0.15, 0.15, 0.15, 1.0)
    log_linewidths = np.where(np.isnan(raw_log_values), 0.8, 0.0)
    log_scatter = log_ax.scatter(
        matched.iloc[log_order]["lon"],
        matched.iloc[log_order]["lat"],
        c=plotted_log_values[log_order],
        s=16,
        marker="o",
        cmap="RdBu",
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
        "B2 − B0 held-out log score (nats)"
    )
    log_ax.set_title("A  Integrated count score at held-out surveys", loc="left")

    error_values = matched["absolute_error_improvement"]
    error_limit = _symmetric_limit(error_values, floor=0.001)
    error_order = np.argsort(np.abs(error_values.to_numpy(dtype=float)))
    error_scatter = error_ax.scatter(
        matched.iloc[error_order]["lon"],
        matched.iloc[error_order]["lat"],
        c=matched.iloc[error_order]["absolute_error_improvement"],
        s=16,
        marker="o",
        cmap="RdBu",
        norm=colors.TwoSlopeNorm(vmin=-error_limit, vcenter=0.0, vmax=error_limit),
        linewidths=0,
        alpha=0.82,
        zorder=2,
    )
    figure.colorbar(error_scatter, ax=error_ax, shrink=0.72, pad=0.015).set_label(
        "B0 − B2 absolute frequency error (positive = B2 better)"
    )
    error_ax.set_title("B  Absolute-error change at the same surveys", loc="left")

    levels = np.array([50, 80, 95], dtype=float)
    comparison = report["comparison"]
    candidate = comparison["candidate_benchmark"]["metrics"]
    baseline = comparison["baseline_benchmark"]["metrics"]
    candidate_coverage = 100.0 * np.array(
        [candidate[f"coverage_{int(level)}"] for level in levels], dtype=float
    )
    baseline_coverage = 100.0 * np.array(
        [baseline[f"coverage_{int(level)}"] for level in levels], dtype=float
    )
    calibration_ax.plot(levels, levels, color="#72777d", linestyle="--", label="Nominal")
    calibration_ax.plot(
        levels, baseline_coverage, color="#d97706", marker="o", linewidth=2, label="B0"
    )
    calibration_ax.plot(
        levels, candidate_coverage, color="#1769aa", marker="o", linewidth=2, label="B2 current GP"
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
    figure.suptitle(
        "HbS current spatial GP versus pooled B0 on five matched geographic holdouts",
        fontsize=15,
        fontweight="bold",
        y=0.965,
    )
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
    figure.text(
        0.5,
        0.045,
        (
            f"Matched n={comparison['matched_observation_count']}; balanced macro Δ log score "
            f"{log_text}; exhaustive outer-block 95% interval {interval_text}; relative MAE "
            f"improvement {100 * differences['relative_mae_improvement']:+.1f}%.  "
            "Development evidence; dependency review incomplete; no promotion decision."
        ),
        ha="center",
        fontsize=9.2,
        color="#343a40",
    )
    return figure


def render(report: dict[str, object], matched: pd.DataFrame, out: Path) -> None:
    figure = build_figure(report, matched)
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        out,
        dpi=190,
        facecolor="white",
        metadata={"Software": "genomeOS matched B2-current benchmark renderer v1"},
    )
    plt.close(figure)


def main() -> int:
    args = _parser().parse_args()
    if args.out.exists() or args.report.exists():
        raise FileExistsError("output figure and report paths must be new")
    report, matched = build_report(args.observations, args.b0, args.b2, args.run_log)
    render(report, matched, args.out)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

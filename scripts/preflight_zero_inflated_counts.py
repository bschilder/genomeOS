#!/usr/bin/env python3
"""Freeze a cohort-blocked zero-inflated count preflight (design §§7–8; issue #103).

This is a nonspatial development comparison. It tests whether an extra absent component improves
held-out count probability after beta-binomial sampling variation is already present. It does not
fit a surface, label any observed zero as true absence, use an environmental covariate, or make an
artifact eligible for publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.validation import zero_inflated_preflight as preflight_module  # noqa: E402
from genomeos.validation.crossval import make_folds  # noqa: E402
from genomeos.validation.zero_inflated_preflight import (  # noqa: E402
    CountModelComparison,
    CountModelFit,
    compare_count_models,
    count_log_mass,
    fit_count_model,
    profile_structural_zero,
)

N_FOLDS = 5
ZERO_DIAGNOSTIC_DENOMINATORS = np.array([100, 500, 1_000, 2_000])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_observations(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise ValueError(f"observations file does not exist: {path}")
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif path.suffix in {".tsv", ".txt"}:
        frame = pd.read_csv(path, sep="\t")
    elif path.suffix == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError("observations must be .parquet, .tsv, .txt or .csv")
    missing = {"ac", "an", "cohort_id"} - set(frame.columns)
    if missing:
        raise ValueError(f"observations are missing required columns {sorted(missing)}")
    if frame.empty:
        raise ValueError("observations must contain at least one row")
    # Validate the complete input before applying the declared denominator filter. Bad rows are
    # hard errors; they do not disappear because a later selection would exclude them.
    count_log_mass(
        frame["ac"], frame["an"], mean=0.1, concentration=20.0, structural_zero=0.0
    )
    return frame


def _fold_frame(comparison: CountModelComparison) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fold": item.fold,
                "n_train": item.n_train,
                "n_test": item.n_test,
                "n_test_groups": item.n_test_groups,
                "mean_log_score_delta": item.mean_log_score_delta,
                "mean_group_log_score_delta": item.mean_group_log_score_delta,
                "mean_zero_log_score_delta": item.mean_zero_log_score_delta,
                "mean_positive_log_score_delta": item.mean_positive_log_score_delta,
                "beta_binomial_mean": item.beta_binomial.mean,
                "beta_binomial_concentration": item.beta_binomial.concentration,
                "zero_inflated_mean": item.zero_inflated_beta_binomial.mean,
                "zero_inflated_concentration": item.zero_inflated_beta_binomial.concentration,
                "structural_zero_probability": (
                    item.zero_inflated_beta_binomial.structural_zero_probability
                ),
            }
            for item in comparison.folds
        ]
    )


def _optimizer_starts_all_succeed(
    comparison: CountModelComparison,
    full_fits: tuple[CountModelFit, CountModelFit],
) -> bool:
    fits = [*full_fits]
    for fold in comparison.folds:
        fits.extend((fold.beta_binomial, fold.zero_inflated_beta_binomial))
    return all(fit.n_successful_starts == fit.n_starts for fit in fits)


def _gate(
    comparison: CountModelComparison,
    full_fits: tuple[CountModelFit, CountModelFit],
) -> dict:
    checks = {
        "cohort_macro_log_score_improves": comparison.mean_group_log_score_delta > 0.0,
        "no_positive_count_log_score_regression": (
            comparison.mean_positive_log_score_delta >= 0.0
        ),
        "at_least_four_of_five_folds_improve": comparison.folds_improved >= 4,
        "optimizer_starts_all_succeed": _optimizer_starts_all_succeed(
            comparison, full_fits
        ),
    }
    return {
        "advance_to_spatial_mixture": all(checks.values()),
        "gate_checks": checks,
        "rule": "all predeclared checks must pass",
    }


def _zero_probability(fit: CountModelFit) -> list[float]:
    return np.exp(
        count_log_mass(
            np.zeros(len(ZERO_DIAGNOSTIC_DENOMINATORS), dtype=int),
            ZERO_DIAGNOSTIC_DENOMINATORS,
            mean=fit.mean,
            concentration=fit.concentration,
            structural_zero=fit.structural_zero_probability,
        )
    ).tolist()


def _render(
    folds: pd.DataFrame,
    profile: pd.DataFrame,
    comparison: CountModelComparison,
    full_inflated: CountModelFit,
    out: Path,
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.4), constrained_layout=True)
    colors = np.where(folds["mean_group_log_score_delta"] > 0.0, "#0072b2", "#d55e00")
    axes[0].bar(
        folds["fold"].astype(str),
        folds["mean_group_log_score_delta"],
        color=colors,
    )
    axes[0].axhline(0.0, color="#3f3f46", linewidth=1.0)
    axes[0].axhline(
        comparison.mean_group_log_score_delta,
        color="#7c3aed",
        linestyle="--",
        linewidth=1.5,
        label=(
            "all-cohort macro mean "
            f"{comparison.mean_group_log_score_delta:+.4f} nats/observation"
        ),
    )
    axes[0].set_xlabel("whole-cohort held-out fold")
    axes[0].set_ylabel("zero-inflated − beta-binomial log score")
    axes[0].set_title("A  Held-out cohort-macro score", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].grid(axis="y", alpha=0.22)
    axes[0].text(
        0.03,
        0.04,
        (
            f"zero rows: {comparison.mean_zero_log_score_delta:+.4f}\n"
            f"positive rows: {comparison.mean_positive_log_score_delta:+.4f}\n"
            "positive values favour zero inflation"
        ),
        transform=axes[0].transAxes,
        va="bottom",
        fontsize=8,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9},
    )

    relative = profile["log_likelihood"] - profile["log_likelihood"].max()
    axes[1].plot(
        profile["structural_zero_probability"],
        relative,
        color="#0072b2",
        linewidth=2.2,
    )
    axes[1].axvline(
        full_inflated.structural_zero_probability,
        color="#d55e00",
        linestyle="--",
        linewidth=1.5,
        label=(
            "full-data MLE "
            f"π₀={full_inflated.structural_zero_probability:.3f}"
        ),
    )
    axes[1].axhline(
        -1.92,
        color="#71717a",
        linestyle=":",
        linewidth=1.2,
        label="descriptive 1.92 log-likelihood drop",
    )
    axes[1].set_xlabel("fixed extra-zero probability π₀")
    axes[1].set_ylabel("profile log likelihood relative to maximum")
    axes[1].set_title("B  Full-data likelihood profile", loc="left", fontweight="bold")
    axes[1].legend(frameon=False, fontsize=8)
    axes[1].grid(alpha=0.22)

    figure.suptitle(
        "Zero-inflated beta-binomial preflight — cohort-blocked, no spatial fit",
        fontsize=14,
        fontweight="bold",
    )
    figure.savefig(out, dpi=160, facecolor="white")
    plt.close(figure)


def run(
    observations: Path,
    out: Path,
    *,
    min_an: int,
    profile_max: float,
    profile_points: int,
) -> Path:
    if out.exists():
        raise ValueError(f"output directory already exists: {out}")
    if isinstance(min_an, bool) or not isinstance(min_an, int) or min_an <= 0:
        raise ValueError("min_an must be a positive integer")
    if not np.isfinite(profile_max) or not 0.0 < profile_max < 1.0:
        raise ValueError("profile_max must be finite and strictly between zero and one")
    if isinstance(profile_points, bool) or not isinstance(profile_points, int) or profile_points < 3:
        raise ValueError("profile_points must be an integer of at least three")

    frame = read_observations(observations)
    eligible = frame.loc[frame["an"] >= min_an].reset_index(drop=True)
    if eligible.empty:
        raise ValueError("no observations pass the declared denominator threshold")
    folds = make_folds(eligible, n_folds=N_FOLDS, strategy="grouped")
    comparison = compare_count_models(
        eligible["ac"], eligible["an"], groups=eligible["cohort_id"], folds=folds
    )
    full_beta = fit_count_model(eligible["ac"], eligible["an"], model="beta_binomial")
    full_inflated = fit_count_model(
        eligible["ac"], eligible["an"], model="zero_inflated_beta_binomial"
    )
    profile = profile_structural_zero(
        eligible["ac"],
        eligible["an"],
        probabilities=np.linspace(0.0, profile_max, profile_points),
    )
    fold_frame = _fold_frame(comparison)
    profile_frame = pd.DataFrame([asdict(point) for point in profile])
    gate = _gate(comparison, (full_beta, full_inflated))

    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp-", dir=out.parent))
    try:
        folds_path = temporary / "fold_metrics.csv"
        profile_path = temporary / "structural_zero_profile.csv"
        figure_path = temporary / "zero-inflated-count-preflight.png"
        fold_frame.to_csv(folds_path, index=False, float_format="%.17g")
        profile_frame.to_csv(profile_path, index=False, float_format="%.17g")
        _render(fold_frame, profile_frame, comparison, full_inflated, figure_path)

        module_path = Path(preflight_module.__file__).resolve()
        script_path = Path(__file__).resolve()
        zero_rows = eligible["ac"].to_numpy() == 0
        report = {
            "schema_version": 1,
            "artifact": "zero-inflated-beta-binomial-method-preflight",
            "evidence_kind": "method_preflight",
            "publication_eligible": False,
            "spatial_fit_performed": False,
            "environmental_covariates_used": [],
            "issue": 103,
            "inputs": {
                "observations": {
                    "artifact": observations.name,
                    "sha256": sha256(observations),
                    "rows": len(frame),
                    "eligible_rows": len(eligible),
                    "rows_below_min_an": len(frame) - len(eligible),
                    "eligible_cohorts": int(eligible["cohort_id"].nunique()),
                    "eligible_zero_rows": int(np.sum(zero_rows)),
                    "eligible_positive_rows": int(np.sum(~zero_rows)),
                }
            },
            "configuration": {
                "min_an": min_an,
                "fold_strategy": "cohort_grouped",
                "n_folds": N_FOLDS,
                "profile_max": profile_max,
                "profile_points": profile_points,
            },
            "model_semantics": {
                "beta_binomial": "ordinary beta-binomial count mass",
                "zero_inflated_beta_binomial": (
                    "at AC=0, structural-zero mass plus beta-binomial sampling-zero mass; "
                    "at AC>0, beta-binomial mass weighted by one minus structural-zero mass"
                ),
                "observed_zero_is_structural_absence": False,
            },
            "full_data_fits": {
                "beta_binomial": asdict(full_beta),
                "zero_inflated_beta_binomial": asdict(full_inflated),
                "marginal_mean": {
                    "beta_binomial": full_beta.mean,
                    "zero_inflated_beta_binomial": (
                        (1.0 - full_inflated.structural_zero_probability)
                        * full_inflated.mean
                    ),
                },
                "zero_count_probability": {
                    "an": ZERO_DIAGNOSTIC_DENOMINATORS.tolist(),
                    "beta_binomial": _zero_probability(full_beta),
                    "zero_inflated_beta_binomial": _zero_probability(full_inflated),
                },
            },
            "comparison": asdict(comparison),
            "decision": gate,
            "limitations": [
                "This scalar preflight is not a spatial occurrence or allele-frequency model.",
                "The extra-zero probability is a distributional component, not a reviewed "
                "label of population absence.",
                "Cohort-blocked development folds are not sealed independent geographic validation.",
                "The likelihood profile is descriptive; mixture-boundary inference is nonstandard.",
                "A favorable result would still require a separately reviewed spatial model "
                "and held-out validation.",
            ],
            "executed_source_sha256": {
                str(module_path.relative_to(script_path.parents[1])): sha256(module_path),
                str(script_path.relative_to(script_path.parents[1])): sha256(script_path),
            },
            "outputs": {
                path.name: sha256(path) for path in (folds_path, profile_path, figure_path)
            },
        }
        (temporary / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        temporary.replace(out)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--min-an", type=int, default=50)
    parser.add_argument("--profile-max", type=float, default=0.30)
    parser.add_argument("--profile-points", type=int, default=31)
    arguments = parser.parse_args()
    run(
        arguments.observations,
        arguments.out,
        min_an=arguments.min_an,
        profile_max=arguments.profile_max,
        profile_points=arguments.profile_points,
    )


if __name__ == "__main__":
    main()

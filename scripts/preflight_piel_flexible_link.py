#!/usr/bin/env python3
"""Freeze Piel cubic and Stukel link-family preflights (design §7, §8; issue #103).

This is a nonspatial method preflight. It reads allele counts, fits both interpretations of the
ambiguous Web Appendix 1 smoothing equation, and emits aggregate curves, coefficients, hashes and
a review figure. It does not fit a surface, select an arm, use an environmental covariate or make
an artifact eligible for publication.
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
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.special import expit  # noqa: E402
from scipy.stats import norm  # noqa: E402

from genomeos.surfaces import piel_flexible_link, piel_published_link  # noqa: E402
from genomeos.surfaces.piel_flexible_link import (  # noqa: E402
    NORMAL_FIT,
    PLOTTING_POSITION,
    SMOOTHING_RULES,
    fit_piel_flexible_link,
    fit_stukel_link,
    smooth_piel_frequencies,
)
from genomeos.surfaces.piel_published_link import (  # noqa: E402
    fit_published_piel_link,
)

ARTICLE = "Piel FB et al. Lancet 2013;381:142-151; doi:10.1016/S0140-6736(12)61229-X"
APPENDIX = "Web Appendix 1 pp. 13, 15; PMC3547249 supplementary file mmc1.pdf"
STUKEL_ARTICLE = "Stukel TA. JASA 1988;83:426-431; doi:10.1080/01621459.1988.10478613"
QUANTILES = np.array([0.001, 0.01, 0.05, 0.5, 0.95, 0.99, 0.999])
CURVE_POINTS = 501


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
    missing = {"ac", "an"} - set(frame.columns)
    if missing:
        raise ValueError(f"observations are missing required columns {sorted(missing)}")
    if frame.empty:
        raise ValueError("observations must contain at least one row")
    return frame


def _arm_dict(result: piel_flexible_link.PielFlexibleLinkPreflight) -> dict:
    encoded = asdict(result)
    encoded["link"]["coefficients"] = list(result.link.coefficients)
    return encoded


def _stukel_arm_dict(result: piel_flexible_link.StukelLinkPreflight) -> dict:
    return asdict(result)


def _published_arm_dict(
    result: piel_published_link.PublishedPielLinkPreflight,
) -> dict:
    encoded = asdict(result)
    encoded["link"]["coefficients"] = list(result.link.coefficients)
    return encoded


def _curves(
    results: dict[str, piel_flexible_link.PielFlexibleLinkPreflight],
    stukel_results: dict[str, piel_flexible_link.StukelLinkPreflight],
    published_result: piel_published_link.PublishedPielLinkPreflight,
) -> pd.DataFrame:
    lower = min(
        -10.0,
        *(result.normal_location - 4.5 * result.normal_scale for result in results.values()),
    )
    upper = max(
        3.0,
        *(result.normal_location + 4.5 * result.normal_scale for result in results.values()),
    )
    latent = np.linspace(lower, upper, CURVE_POINTS)
    values = {"latent": latent, "inverse_logit": expit(latent)}
    values.update({rule: result.link.frequency(latent) for rule, result in results.items()})
    values["piel_published_2013"] = published_result.aligned_frequency(latent)
    values.update(
        {f"stukel_{rule}": result.aligned_frequency(latent) for rule, result in stukel_results.items()}
    )
    return pd.DataFrame(values)


def _quantile_table(
    frame: pd.DataFrame,
    results: dict[str, piel_flexible_link.PielFlexibleLinkPreflight],
    stukel_results: dict[str, piel_flexible_link.StukelLinkPreflight],
    published_result: piel_published_link.PublishedPielLinkPreflight,
    min_an: int,
) -> pd.DataFrame:
    eligible = frame.loc[frame["an"] >= min_an]
    rows: list[dict] = []
    for rule, result in results.items():
        smoothed = smooth_piel_frequencies(eligible["ac"], eligible["an"], rule=rule)
        latent = result.normal_location + result.normal_scale * norm.ppf(QUANTILES)
        fitted = result.link.frequency(latent)
        stukel_fitted = stukel_results[rule].aligned_frequency(latent)
        published_fitted = (
            published_result.aligned_frequency(latent)
            if rule == "piel_printed_2013"
            else np.full(latent.shape, np.nan)
        )
        empirical = np.quantile(smoothed, QUANTILES)
        rows.extend(
            {
                "smoothing_rule": rule,
                "quantile": float(quantile),
                "empirical_smoothed_frequency": float(observed),
                "fitted_link_frequency": float(predicted),
                "stukel_link_frequency": float(stukel),
                "published_piel_link_frequency": float(published),
            }
            for quantile, observed, predicted, stukel, published in zip(
                QUANTILES,
                empirical,
                fitted,
                stukel_fitted,
                published_fitted,
                strict=True,
            )
        )
    return pd.DataFrame(rows)


def _render(
    curves: pd.DataFrame,
    quantiles: pd.DataFrame,
    diagnostic_latent: tuple[float, ...],
    diagnostic_frequency: dict[str, list[float]],
    out: Path,
) -> None:
    colors = {
        "inverse_logit": "#3f3f46",
        "piel_published_2013": "#009e73",
        "piel_printed_2013": "#0072b2",
        "uniform_binomial_conjugate": "#d55e00",
    }
    labels = {
        "inverse_logit": "current inverse-logit",
        "piel_published_2013": "published Piel 2013 cubic",
        "piel_printed_2013": "appendix equation as printed",
        "uniform_binomial_conjugate": "uniform-binomial conjugate equation",
    }
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.4), constrained_layout=True)
    for column in colors:
        axes[0].plot(
            curves["latent"],
            curves[column],
            color=colors[column],
            linewidth=2.2,
            label=labels[column],
        )
    for rule in SMOOTHING_RULES:
        axes[0].plot(
            curves["latent"],
            curves[f"stukel_{rule}"],
            color=colors[rule],
            linewidth=1.6,
            linestyle="-.",
            label=f"{labels[rule]} — aligned Stukel",
        )
    axes[0].set_yscale("log")
    axes[0].set_ylim(1e-6, 1)
    axes[0].set_xlabel("Gaussian latent value")
    axes[0].set_ylabel("allele frequency")
    axes[0].set_title(
        "A  Candidate links and current-fit diagnostic", loc="left", fontweight="bold"
    )
    axes[0].grid(alpha=0.22)
    axes[0].legend(frameon=False, fontsize=8)
    if len(diagnostic_latent) == 1:
        reference = diagnostic_latent[0]
        axes[0].axvline(reference, color="#71717a", linestyle=":", linewidth=1.4)
        axes[0].text(
            0.03,
            0.05,
            (
                f"At current-fit intercept x = {reference:.3f}\n"
                f"inverse-logit: {100 * diagnostic_frequency['inverse_logit'][0]:.3f}%\n"
                f"published Piel: {100 * diagnostic_frequency['piel_published_2013'][0]:.3f}%\n"
                f"printed equation: {100 * diagnostic_frequency['piel_printed_2013'][0]:.3f}%\n"
                f"conjugate equation: {100 * diagnostic_frequency['uniform_binomial_conjugate'][0]:.3f}%\n"
                f"printed Stukel: {100 * diagnostic_frequency['stukel_piel_printed_2013'][0]:.3f}%\n"
                "conjugate Stukel: "
                f"{100 * diagnostic_frequency['stukel_uniform_binomial_conjugate'][0]:.3f}%\n"
                "diagnostic only; no spatial refit"
            ),
            transform=axes[0].transAxes,
            fontsize=7.5,
            va="bottom",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9},
        )

    for rule in SMOOTHING_RULES:
        selected = quantiles.loc[quantiles["smoothing_rule"] == rule]
        axes[1].plot(
            selected["quantile"],
            selected["empirical_smoothed_frequency"],
            color=colors[rule],
            linewidth=2.2,
            label=f"{labels[rule]} — empirical",
        )
        axes[1].plot(
            selected["quantile"],
            selected["fitted_link_frequency"],
            color=colors[rule],
            linewidth=1.5,
            linestyle="--",
            label=f"{labels[rule]} — cubic fit",
        )
        axes[1].plot(
            selected["quantile"],
            selected["stukel_link_frequency"],
            color=colors[rule],
            linewidth=1.5,
            linestyle="-.",
            label=f"{labels[rule]} — Stukel fit",
        )
        if rule == "piel_printed_2013":
            axes[1].plot(
                selected["quantile"],
                selected["published_piel_link_frequency"],
                color=colors["piel_published_2013"],
                linewidth=1.8,
                linestyle=":",
                label="published Piel 2013 cubic",
            )
    axes[1].set_xscale("logit")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("empirical quantile")
    axes[1].set_ylabel("smoothed allele frequency")
    axes[1].set_title("B  Quantile-matching preflight", loc="left", fontweight="bold")
    axes[1].grid(alpha=0.22)
    axes[1].legend(frameon=False, fontsize=7)

    figure.suptitle(
        "Piel cubic and Stukel links — method preflight, no spatial fit",
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.002,
        "Green: published Piel cubic (dotted in panel B); dashed: reconstructed cubics; "
        "dash-dot: aligned Stukel fits. This artifact is not publication eligible.",
        ha="center",
        fontsize=8.5,
    )
    figure.savefig(out, dpi=160, facecolor="white")
    plt.close(figure)


def run(
    observations: Path,
    out: Path,
    *,
    min_an: int,
    diagnostic_latent: tuple[float, ...],
) -> Path:
    if out.exists():
        raise ValueError(f"output directory already exists: {out}")
    if any(not np.isfinite(value) for value in diagnostic_latent):
        raise ValueError("diagnostic latent values must be finite")
    frame = read_observations(observations)
    results = {
        rule: fit_piel_flexible_link(frame["ac"], frame["an"], rule=rule, min_an=min_an)
        for rule in SMOOTHING_RULES
    }
    stukel_results = {
        rule: fit_stukel_link(frame["ac"], frame["an"], rule=rule, min_an=min_an)
        for rule in SMOOTHING_RULES
    }
    published_result = fit_published_piel_link(frame["ac"], frame["an"], min_an=min_an)
    curves = _curves(results, stukel_results, published_result)
    quantiles = _quantile_table(
        frame, results, stukel_results, published_result, min_an
    )
    diagnostic_frequency = {
        "inverse_logit": expit(np.asarray(diagnostic_latent)).tolist(),
        **{
            rule: result.link.frequency(diagnostic_latent).tolist()
            for rule, result in results.items()
        },
        **{
            f"stukel_{rule}": result.aligned_frequency(diagnostic_latent).tolist()
            for rule, result in stukel_results.items()
        },
        "piel_published_2013": published_result.aligned_frequency(
            diagnostic_latent
        ).tolist(),
    }
    diagnostics = {
        "latent": list(diagnostic_latent),
        "frequency": diagnostic_frequency,
        "stukel_aligned_frequency": {
            rule: result.aligned_frequency(diagnostic_latent).tolist()
            for rule, result in stukel_results.items()
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp-", dir=out.parent))
    try:
        curves_path = temporary / "link_curves.csv"
        quantiles_path = temporary / "smoothed_frequency_quantiles.csv"
        figure_path = temporary / "piel-flexible-link-preflight.png"
        curves.to_csv(curves_path, index=False, float_format="%.17g")
        quantiles.to_csv(quantiles_path, index=False, float_format="%.17g")
        _render(curves, quantiles, diagnostic_latent, diagnostic_frequency, figure_path)

        module_path = Path(piel_flexible_link.__file__).resolve()
        script_path = Path(__file__).resolve()
        report = {
            "schema_version": 3,
            "artifact": "piel-flexible-link-method-preflight",
            "evidence_kind": "method_preflight",
            "publication_eligible": False,
            "spatial_fit_performed": False,
            "environmental_covariates_used": [],
            "issue": 103,
            "primary_source": {
                "article": ARTICLE,
                "appendix": APPENDIX,
                "appendix_sha256": piel_published_link.PIEL_APPENDIX_SHA256,
                "published_coefficients_page": 15,
                "stukel_article": STUKEL_ARTICLE,
            },
            "inputs": {
                "observations": {
                    "artifact": observations.name,
                    "sha256": sha256(observations),
                    "rows": len(frame),
                }
            },
            "configuration": {
                "min_an": min_an,
                "normal_fit": NORMAL_FIT,
                "plotting_position": PLOTTING_POSITION,
                "diagnostic_latent": list(diagnostic_latent),
            },
            "arms": {rule: _arm_dict(result) for rule, result in results.items()},
            "stukel_arms": {
                rule: _stukel_arm_dict(result) for rule, result in stukel_results.items()
            },
            "published_piel_arm": _published_arm_dict(published_result),
            "diagnostics": diagnostics,
            "limitations": [
                "The published coefficients are specific to Piel's source data; affine quantile "
                "alignment to the current data is diagnostic and is not a source spatial refit.",
                "The appendix's printed smoothing equation conflicts with its stated conjugate model.",
                "The appendix does not fully specify the posterior CDF fitting procedure; "
                "this run uses a named plug-in MLE quantile interpretation.",
                "This preflight does not test spatial held-out count prediction or national burden.",
                "The observed HbS range does not identify Stukel's positive-latent branch; "
                "alpha_positive is fixed at zero and explicitly reported as unfitted.",
            ],
            "executed_source_sha256": {
                str(module_path.relative_to(script_path.parents[1])): sha256(module_path),
                str(
                    Path(piel_published_link.__file__).resolve().relative_to(
                        script_path.parents[1]
                    )
                ): sha256(Path(piel_published_link.__file__).resolve()),
                str(script_path.relative_to(script_path.parents[1])): sha256(script_path),
            },
            "outputs": {
                path.name: sha256(path)
                for path in (curves_path, quantiles_path, figure_path)
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
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-an", type=int, default=50)
    parser.add_argument("--diagnostic-latent", type=float, action="append", default=[])
    args = parser.parse_args()
    run(
        args.observations,
        args.out,
        min_an=args.min_an,
        diagnostic_latent=tuple(args.diagnostic_latent),
    )


if __name__ == "__main__":
    main()

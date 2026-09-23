#!/usr/bin/env python3
"""Freeze an HbS GP-amplitude prior preflight (design §§7–8; issue #103).

The adapter binds a preregistration to one fitted posterior and its draw-aligned global fields,
then delegates all numerical work to the pure validation module. It performs no refit and writes
no publication-eligible surface. The figure maps the exact diagnostic cell strata separately from
the prior-sensitivity summaries so geography remains visible and auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.validation import amplitude_prior_sensitivity as science_module  # noqa: E402
from genomeos.validation.amplitude_prior_sensitivity import (  # noqa: E402
    AmplitudeSensitivityResult,
    evaluate_amplitude_prior_sensitivity,
)

SCHEMA = "hbs-amplitude-prior-sensitivity-preregistration-v1"
RESULT_SCHEMA = "hbs-amplitude-prior-sensitivity-result-v1"
METHOD = "self_normalized_importance_reweighting"
SUMMARY_NAMES = (
    "amplitude",
    "intercept",
    "invlogit_intercept",
    "population_weighted_nordic_frequency",
    "population_weighted_endemic_peak_frequency",
    "endemic_minus_nordic_frequency",
)
SCIENCE_PATH = Path(science_module.__file__).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _number(value: object, context: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{context} must be numeric, not Boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{context} must be numeric") from error
    if not np.isfinite(number):
        raise ValueError(f"{context} must be finite")
    return number


def _pair(value: object, context: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{context} must contain exactly two values")
    lower, upper = (_number(item, context) for item in value)
    if not lower < upper:
        raise ValueError(f"{context} must be strictly increasing")
    return lower, upper


def _load_preregistration(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise ValueError(f"preregistration does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("preregistration must be valid UTF-8 JSON") from error
    data = _mapping(payload, "preregistration")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"preregistration schema must be {SCHEMA!r}")
    if data.get("issue") != 103 or data.get("method") != METHOD:
        raise ValueError("preregistration must bind issue 103 and the supported method")
    if data.get("environmental_covariates_used") is not False:
        raise ValueError("environmental_covariates_used must be false")
    prior = _mapping(data.get("original_prior"), "original_prior")
    if prior.get("family") != "HalfNormal":
        raise ValueError("original prior family must be HalfNormal")
    scales = data.get("candidate_scales")
    if not isinstance(scales, list):
        raise ValueError("candidate_scales must be an array")
    diagnostics = _mapping(data.get("diagnostics"), "diagnostics")
    if diagnostics.get("summaries") != list(SUMMARY_NAMES):
        raise ValueError("diagnostic summaries differ from the frozen interface")
    _pair(
        _mapping(diagnostics.get("nordic_supported_box"), "nordic_supported_box").get(
            "latitude_degrees"
        ),
        "Nordic latitude bounds",
    )
    _pair(
        _mapping(diagnostics.get("nordic_supported_box"), "nordic_supported_box").get(
            "longitude_degrees"
        ),
        "Nordic longitude bounds",
    )
    _mapping(diagnostics.get("endemic_peak_cells"), "endemic_peak_cells")
    inputs = _mapping(data.get("inputs"), "inputs")
    required_hashes = {
        "fit_sha256",
        "draw_manifest_sha256",
        "frequency_draws_sha256",
        "cells_sha256",
    }
    if not required_hashes <= set(inputs):
        raise ValueError("preregistration is missing required input hashes")
    for name in required_hashes:
        value = inputs[name]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"{name} must be a SHA-256 hex digest")
    if not isinstance(data.get("claims_excluded"), list) or not data["claims_excluded"]:
        raise ValueError("claims_excluded must be a nonempty array")
    return data


def _verify_input_hashes(
    preregistration: Mapping[str, Any],
    *,
    fit: Path,
    manifest: Path,
    frequency: Path,
    cells: Path,
) -> dict[str, dict[str, object]]:
    expected = _mapping(preregistration["inputs"], "inputs")
    bindings = {
        "fit": (fit, "fit_sha256"),
        "draw_manifest": (manifest, "draw_manifest_sha256"),
        "frequency_draws": (frequency, "frequency_draws_sha256"),
        "cells": (cells, "cells_sha256"),
    }
    result = {}
    for name, (path, field) in bindings.items():
        if not path.is_file():
            raise ValueError(f"{name} does not exist: {path}")
        digest = sha256(path)
        if digest != expected[field]:
            raise ValueError(f"{name.replace('_', ' ')} SHA-256 differs from preregistration")
        result[name] = {"sha256": digest, "bytes": path.stat().st_size}
    return result


def _posterior_draws(fit_path: Path, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    try:
        with fit_path.open("rb") as stream:
            payload = pickle.load(stream)  # noqa: S301 - owner-controlled local research artifact
        fit = payload["fit"]
        amplitude = np.asarray(fit.idata.posterior["amplitude"], dtype=float).reshape(-1)
        intercept = np.asarray(fit.idata.posterior["intercept"], dtype=float).reshape(-1)
    except (KeyError, TypeError, AttributeError, pickle.UnpicklingError) as error:
        raise ValueError("fit lacks aligned amplitude/intercept posterior draws") from error
    if amplitude.shape != intercept.shape or not len(amplitude):
        raise ValueError("fit amplitude/intercept posterior shapes differ or are empty")
    if np.any(indices >= len(amplitude)):
        raise ValueError("selected draw index exceeds the fitted posterior")
    return amplitude[indices], intercept[indices]


def _selected_indices(manifest_path: Path) -> tuple[Mapping[str, Any], np.ndarray]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("draw manifest must be valid UTF-8 JSON") from error
    data = _mapping(manifest, "draw manifest")
    raw = data.get("selected_draw_indices")
    if not isinstance(raw, list) or not raw:
        raise ValueError("selected_draw_indices must be a nonempty array")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in raw):
        raise ValueError("selected_draw_indices must contain nonnegative integers")
    indices = np.asarray(raw, dtype=int)
    if len(np.unique(indices)) != len(indices):
        raise ValueError("selected_draw_indices must be unique")
    if data.get("n_draws") != len(indices):
        raise ValueError("draw manifest n_draws differs from selected_draw_indices")
    return data, indices


def _cell_masks(
    cells: pd.DataFrame, preregistration: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    required = {"lat", "lon", "population", "post_median", "support"}
    missing = required - set(cells.columns)
    if missing:
        raise ValueError(f"cells are missing required columns {sorted(missing)}")
    diagnostics = _mapping(preregistration["diagnostics"], "diagnostics")
    nordic_config = _mapping(diagnostics["nordic_supported_box"], "nordic_supported_box")
    peak_config = _mapping(diagnostics["endemic_peak_cells"], "endemic_peak_cells")
    latitude = _pair(nordic_config["latitude_degrees"], "Nordic latitude bounds")
    longitude = _pair(nordic_config["longitude_degrees"], "Nordic longitude bounds")
    nordic_support = nordic_config.get("support_in")
    peak_support = peak_config.get("support_in")
    if not isinstance(nordic_support, list) or not isinstance(peak_support, list):
        raise ValueError("diagnostic support_in values must be arrays")
    threshold = _number(
        peak_config.get("baseline_post_median_at_least"), "endemic peak threshold"
    )
    nordic = (
        cells["support"].isin(nordic_support)
        & cells["lat"].between(*latitude, inclusive="both")
        & cells["lon"].between(*longitude, inclusive="both")
    ).to_numpy()
    peak = (
        cells["support"].isin(peak_support) & (cells["post_median"] >= threshold)
    ).to_numpy()
    return nordic, peak


def _candidate_payload(result: AmplitudeSensitivityResult) -> list[dict[str, object]]:
    candidates = []
    for candidate in result.candidates:
        row = asdict(candidate)
        row["half_normal_scale"] = row.pop("scale")
        candidates.append(row)
    return candidates


def _render(
    cells: pd.DataFrame,
    nordic: np.ndarray,
    peak: np.ndarray,
    result: AmplitudeSensitivityResult,
    *,
    minimum_ess: float,
    out: Path,
) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(16.5, 5.2), constrained_layout=True)
    axes[0].scatter(cells["lon"], cells["lat"], s=0.7, color="#d4d4d8", alpha=0.35)
    axes[0].scatter(
        cells.loc[peak, "lon"], cells.loc[peak, "lat"], s=2.2, color="#d55e00",
        alpha=0.65, label="baseline median ≥8%",
    )
    axes[0].scatter(
        cells.loc[nordic, "lon"], cells.loc[nordic, "lat"], s=3.0, color="#0072b2",
        alpha=0.8, label="Nordic supported box",
    )
    axes[0].set(xlim=(-180, 180), ylim=(-90, 90), xlabel="longitude", ylabel="latitude")
    axes[0].set_title("A  Frozen surface-cell strata", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, fontsize=8, markerscale=2.5)
    axes[0].grid(alpha=0.15)

    scales = np.asarray([candidate.scale for candidate in result.candidates])
    series = (
        ("population_weighted_nordic_frequency", "Nordic", "#0072b2"),
        ("population_weighted_endemic_peak_frequency", "endemic peak", "#d55e00"),
        ("endemic_minus_nordic_frequency", "peak − Nordic", "#009e73"),
    )
    reference_index = next(
        index
        for index, candidate in enumerate(result.candidates)
        if candidate.decision_reason == "reference_prior"
    )
    for name, label, color in series:
        medians = np.asarray([candidate.summaries[name].median for candidate in result.candidates])
        baseline = medians[reference_index]
        axes[1].plot(scales, 10_000 * (medians - baseline), color=color, marker="o", label=label)
    axes[1].axhline(0.0, color="#52525b", linewidth=1.0)
    axes[1].invert_xaxis()
    axes[1].set_xlabel("HalfNormal amplitude-prior scale (tighter →)")
    axes[1].set_ylabel("change from current prior (basis points)")
    axes[1].set_title("B  Background rises while peaks flatten", loc="left", fontweight="bold")
    axes[1].legend(frameon=False, fontsize=8)
    axes[1].grid(alpha=0.2)

    ess = np.asarray([candidate.effective_sample_size for candidate in result.candidates])
    maximum = np.asarray([candidate.maximum_normalized_weight for candidate in result.candidates])
    axes[2].bar([str(scale) for scale in scales], ess, color="#6b7280")
    axes[2].axhline(minimum_ess, color="#d55e00", linestyle="--", label="ESS gate")
    for index, (value, max_weight) in enumerate(zip(ess, maximum, strict=True)):
        axes[2].text(
            index,
            value,
            f"ESS {value:.1f}\nmax w {max_weight:.3f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    axes[2].set_xlabel("HalfNormal amplitude-prior scale")
    axes[2].set_ylabel("importance effective sample size")
    axes[2].set_title("C  Reweighting remains numerically usable", loc="left", fontweight="bold")
    axes[2].legend(frameon=False, fontsize=8)
    axes[2].grid(axis="y", alpha=0.2)
    figure.suptitle(
        "HbS amplitude-prior sensitivity — importance reweighting, no refit",
        fontsize=14,
        fontweight="bold",
    )
    figure.savefig(out, dpi=160, facecolor="white")
    plt.close(figure)


def run(
    *,
    fit: Path,
    manifest: Path,
    frequency: Path,
    cells: Path,
    preregistration: Path,
    out: Path,
) -> Path:
    if out.exists():
        raise ValueError(f"output directory already exists: {out}")
    prereg = _load_preregistration(preregistration)
    inputs = _verify_input_hashes(
        prereg, fit=fit, manifest=manifest, frequency=frequency, cells=cells
    )
    draw_manifest, indices = _selected_indices(manifest)
    amplitude, intercept = _posterior_draws(fit, indices)
    fields = np.load(frequency, mmap_mode="r", allow_pickle=False)
    cell_frame = pd.read_parquet(cells)
    if draw_manifest.get("n_cells") != len(cell_frame):
        raise ValueError("draw manifest n_cells differs from the cell table")
    nordic, peak = _cell_masks(cell_frame, prereg)
    diagnostics = _mapping(prereg["diagnostics"], "diagnostics")
    prior = _mapping(prereg["original_prior"], "original_prior")
    result = evaluate_amplitude_prior_sensitivity(
        amplitude,
        intercept,
        fields,
        cell_frame["population"].to_numpy(),
        nordic,
        peak,
        original_scale=prior["scale"],
        candidate_scales=prereg["candidate_scales"],
        minimum_effective_sample_size=diagnostics["minimum_effective_sample_size"],
        maximum_single_weight=diagnostics["maximum_single_normalized_weight"],
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    try:
        figure_name = "amplitude-prior-sensitivity.png"
        _render(
            cell_frame,
            nordic,
            peak,
            result,
            minimum_ess=float(diagnostics["minimum_effective_sample_size"]),
            out=temporary / figure_name,
        )
        candidates = _candidate_payload(result)
        payload = {
            "schema": RESULT_SCHEMA,
            "method": METHOD,
            "preregistration_sha256": sha256(preregistration),
            "n_selected_draws": result.n_draws,
            "n_cells": result.n_cells,
            "strata": {
                "nordic_supported_cells": result.nordic_cells,
                "nordic_supported_population_weight": result.nordic_population_weight,
                "endemic_peak_cells": result.peak_cells,
                "endemic_peak_population_weight": result.peak_population_weight,
            },
            "candidates": candidates,
            "any_candidate_advances_to_full_refit": any(
                row["advance_to_full_refit"] for row in candidates
            ),
            "decision_rule": prereg["decision_rule"],
            "scientific_acceptance": False,
            "publication_eligible": False,
            "environmental_covariates_used": False,
            "claims_excluded": prereg["claims_excluded"],
            "inputs": inputs,
            "sources": {
                "science_module": {
                    "path": str(SCIENCE_PATH.relative_to(ROOT)),
                    "sha256": sha256(SCIENCE_PATH),
                },
                "runner": {
                    "path": str(Path(__file__).resolve().relative_to(ROOT)),
                    "sha256": sha256(Path(__file__).resolve()),
                },
            },
            "figure": {"path": figure_name, "sha256": sha256(temporary / figure_name)},
        }
        result_path = temporary / "result.json"
        result_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(out)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return out / "result.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit", type=Path, required=True)
    parser.add_argument("--draw-manifest", dest="manifest", type=Path, required=True)
    parser.add_argument("--frequency-draws", dest="frequency", type=Path, required=True)
    parser.add_argument("--cells", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    result = run(**vars(arguments))
    print(json.dumps({"result": str(result), "result_sha256": sha256(result)}, sort_keys=True))


if __name__ == "__main__":
    main()

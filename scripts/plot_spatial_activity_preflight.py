#!/usr/bin/env python3
"""Render aggregate spatial-activity preflight evidence (design §8; issue #384).

The input is the complete private campaign result. The emitted JSON deliberately omits the
720-task inventory after authenticating and hashing it, and the figure contains only the six
seed-collapsed synthetic-condition summaries used by the preregistered decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

TASK_COUNT = 720
RESULT_VERSION = 1
CAMPAIGN_MANIFEST_SHA256 = (
    "6dad935bd9e1e2a3b9ea3946e985c5ebdd77ab0e4d2b3480b0438e7446c03712"
)
SHA256 = re.compile(r"[0-9a-f]{64}")
CONDITIONS = (
    (("null", 1.0, 0.0), "Null"),
    (("localized_weak", 1.0, 0.0), "Weak"),
    (("localized_strong", 1.0, 0.0), "Strong\nprimary"),
    (("localized_strong", 0.25, 0.0), "Strong\nlow n"),
    (("localized_strong", 4.0, 0.0), "Strong\nhigh n"),
    (("localized_strong", 1.0, 0.5), "Strong +\ncohort SD"),
)
OPTIONAL_METRICS = (
    "mean_log_score_delta",
    "log_score_delta_ci95_low",
    "log_score_delta_ci95_high",
    "relative_mae_improvement",
    "relative_marginal_recovery_improvement",
    "mean_zero_log_score_delta",
    "mean_positive_log_score_delta",
    "candidate_coverage_50",
    "candidate_coverage_80",
    "candidate_coverage_95",
    "candidate_mean_absolute_component_correlation",
    "candidate_mean_inactive_probability",
    "candidate_fraction_draws_below_activity_threshold",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _optional_number(value: object, field: str) -> float | None:
    return None if value is None else _number(value, field)


def _condition_key(comparison: Mapping[str, object]) -> tuple[str, float, float]:
    truth = comparison.get("truth")
    if not isinstance(truth, str):
        raise ValueError("comparison truth must be a string")
    denominator = _number(
        comparison.get("denominator_multiplier"), "denominator_multiplier"
    )
    cohort_sd = _number(comparison.get("cohort_sd"), "cohort_sd")
    expected_id = f"{truth}|denominator={denominator:g}|cohort_sd={cohort_sd:g}"
    if comparison.get("condition_id") != expected_id:
        raise ValueError(f"comparison condition identity is inconsistent: {expected_id}")
    return truth, denominator, cohort_sd


def _validate_comparison(comparison: object) -> dict[str, object]:
    if not isinstance(comparison, Mapping):
        raise ValueError("comparisons must contain JSON objects")
    _, denominator, cohort_sd = _condition_key(comparison)
    if denominator <= 0.0 or cohort_sd < 0.0:
        raise ValueError("comparison denominator/cohort values are outside their domain")
    if not isinstance(comparison.get("complete"), bool):
        raise ValueError("comparison complete must be boolean")
    counts = {}
    for field in (
        "paired_outer_fold_count",
        "paired_zero_stratum_count",
        "paired_positive_stratum_count",
        "candidate_component_correlation_fold_count",
        "candidate_component_correlation_observation_count",
    ):
        counts[field] = _integer(comparison.get(field), field)
    if counts["paired_outer_fold_count"] != 15:
        raise ValueError("each seed-collapsed condition must contain 15 outer-fold pairs")
    if counts["paired_zero_stratum_count"] > 15 or counts["paired_positive_stratum_count"] > 15:
        raise ValueError("paired stratum counts exceed the outer-fold pair count")
    if counts["candidate_component_correlation_fold_count"] > 15:
        raise ValueError("component-correlation fold count exceeds the outer-fold pair count")
    for field in OPTIONAL_METRICS:
        if field not in comparison:
            raise ValueError(f"comparison is missing registered metric: {field}")
        _optional_number(comparison.get(field), field)
    mean = comparison.get("mean_log_score_delta")
    low = comparison.get("log_score_delta_ci95_low")
    high = comparison.get("log_score_delta_ci95_high")
    if (mean is None or low is None or high is None) and not (
        mean is None and low is None and high is None
    ):
        raise ValueError("log-score estimate and interval must be jointly available")
    if mean is not None and not (float(low) <= float(mean) <= float(high)):
        raise ValueError("log-score interval must enclose its mean")
    for field in (
        "candidate_coverage_50",
        "candidate_coverage_80",
        "candidate_coverage_95",
        "candidate_mean_absolute_component_correlation",
        "candidate_mean_inactive_probability",
        "candidate_fraction_draws_below_activity_threshold",
    ):
        value = comparison.get(field)
        if value is not None and not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{field} must lie in [0, 1]")
    return dict(comparison)


def _validate_artifacts(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) != TASK_COUNT:
        raise ValueError("campaign result must contain exactly 720 task artifacts")
    artifacts: dict[str, object] = {}
    for name, record in value.items():
        if (
            not isinstance(name, str)
            or not name.endswith(".json")
            or SHA256.fullmatch(name[:-5]) is None
        ):
            raise ValueError("task artifact names must be content-addressed JSON files")
        if not isinstance(record, Mapping):
            raise ValueError(f"task artifact record must be an object: {name}")
        digest = record.get("sha256")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise ValueError(f"task artifact has an invalid SHA-256: {name}")
        _integer(record.get("size_bytes"), f"{name} size_bytes", minimum=1)
        artifacts[name] = dict(record)
    return artifacts


def build_public_summary(
    result: Mapping[str, object], *, source_bytes: bytes
) -> dict[str, object]:
    """Validate the final campaign artifact and return aggregate-only review evidence."""
    if not isinstance(result, Mapping):
        raise ValueError("campaign result must be a JSON object")
    if not isinstance(source_bytes, bytes):
        raise TypeError("source_bytes must be bytes")
    try:
        source_document = json.loads(source_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("source bytes do not encode the supplied campaign result") from error
    if source_document != result:
        raise ValueError("source bytes do not encode the supplied campaign result")
    if result.get("format") != "spatial_activity_campaign_result":
        raise ValueError("input is not a spatial activity campaign result")
    if result.get("evidence_kind") != "synthetic_preflight":
        raise ValueError("campaign result evidence kind changed")
    if result.get("publication_eligible") is not False:
        raise ValueError("campaign result must remain nonpublication evidence")
    if result.get("version") != RESULT_VERSION:
        raise ValueError(f"campaign result version must be {RESULT_VERSION}")
    task_count = _integer(result.get("task_count"), "task_count")
    if task_count != TASK_COUNT:
        raise ValueError("campaign result must cover exactly 720 tasks")
    completed = _integer(result.get("completed_task_count"), "completed_task_count")
    retried = _integer(result.get("retried_task_count"), "retried_task_count")
    if completed > task_count or retried > task_count:
        raise ValueError("campaign completion counts exceed the registered task count")
    manifest_sha256 = result.get("campaign_manifest_sha256")
    if not isinstance(manifest_sha256, str) or SHA256.fullmatch(manifest_sha256) is None:
        raise ValueError("campaign manifest SHA-256 is invalid")
    if manifest_sha256 != CAMPAIGN_MANIFEST_SHA256:
        raise ValueError("result does not use the registered campaign manifest")

    artifacts = _validate_artifacts(result.get("task_artifacts"))
    raw_comparisons = result.get("comparisons")
    if isinstance(raw_comparisons, (str, bytes)) or not isinstance(
        raw_comparisons, Sequence
    ):
        raise ValueError("campaign comparisons must be a sequence")
    comparisons = [_validate_comparison(item) for item in raw_comparisons]
    by_key = {_condition_key(item): item for item in comparisons}
    expected = {key for key, _ in CONDITIONS}
    if len(comparisons) != len(CONDITIONS) or set(by_key) != expected:
        raise ValueError("campaign result must contain the six registered conditions once")

    decision = result.get("decision")
    if not isinstance(decision, Mapping) or not isinstance(
        decision.get("eligible_for_real_fit"), bool
    ):
        raise ValueError("campaign decision is invalid")
    reasons = decision.get("refusal_reasons")
    if (
        isinstance(reasons, (str, bytes))
        or not isinstance(reasons, Sequence)
        or any(not isinstance(reason, str) or not reason for reason in reasons)
    ):
        raise ValueError("campaign refusal reasons are invalid")
    if bool(decision["eligible_for_real_fit"]) == bool(reasons):
        raise ValueError("campaign decision contradicts its refusal reasons")
    ordered = [by_key[key] for key, _ in CONDITIONS]
    return {
        "campaign_manifest_sha256": manifest_sha256,
        "comparisons": ordered,
        "completed_task_count": completed,
        "decision": {
            "eligible_for_real_fit": decision["eligible_for_real_fit"],
            "refusal_reasons": list(reasons),
        },
        "evidence_kind": "synthetic_preflight",
        "format": "spatial_activity_preflight_public_summary",
        "publication_eligible": False,
        "retried_task_count": retried,
        "source_result_sha256": _sha256(source_bytes),
        "task_artifact_inventory_sha256": _sha256(_canonical(artifacts)),
        "task_count": task_count,
        "version": RESULT_VERSION,
    }


def _values(comparisons: Sequence[Mapping[str, object]], field: str) -> np.ndarray:
    return np.asarray(
        [np.nan if item[field] is None else float(item[field]) for item in comparisons],
        dtype=float,
    )


def _condition_axis(axis, labels: Sequence[str]) -> None:
    axis.set_xticks(np.arange(len(labels)), labels)
    axis.tick_params(axis="x", labelsize=8.5)
    axis.grid(axis="y", color="#e5e7eb", linewidth=0.7)
    axis.set_axisbelow(True)


def _bar_colors(values: np.ndarray) -> list[str]:
    return ["#1b8a5a" if np.isfinite(value) and value >= 0 else "#c75b39" for value in values]


def build_figure(summary: Mapping[str, object]):
    """Build the six-panel view of the registered aggregate decision evidence."""
    comparisons = summary["comparisons"]
    labels = [
        label if comparison["complete"] else f"{label}\n(incomplete)"
        for (_, label), comparison in zip(CONDITIONS, comparisons, strict=True)
    ]
    x = np.arange(len(labels), dtype=float)
    figure, axes = plt.subplots(2, 3, figsize=(18.5, 10.2))
    figure.subplots_adjust(
        left=0.055,
        right=0.985,
        bottom=0.16,
        top=0.86,
        hspace=0.48,
        wspace=0.26,
    )
    log_ax, mae_ax, recovery_ax, coverage_ax, dependence_ax, null_ax = axes.flat

    log_score = _values(comparisons, "mean_log_score_delta")
    low = _values(comparisons, "log_score_delta_ci95_low")
    high = _values(comparisons, "log_score_delta_ci95_high")
    available = np.isfinite(log_score) & np.isfinite(low) & np.isfinite(high)
    if available.any():
        log_ax.errorbar(
            x[available],
            log_score[available],
            yerr=np.vstack(
                (log_score[available] - low[available], high[available] - log_score[available])
            ),
            fmt="o",
            color="#245c8a",
            ecolor="#6689a8",
            capsize=4,
            linewidth=1.5,
        )
    log_ax.axhline(0.0, color="#343a40", linewidth=1.0)
    log_ax.plot(
        [-0.28, 0.28],
        [-0.01, -0.01],
        color="#7c3aed",
        linewidth=3,
        label="Null lower-CI gate",
    )
    log_ax.set_ylabel("Activity model − ordinary model (nats)")
    log_ax.set_title("A  Held-out count log score", loc="left")
    log_ax.legend(frameon=False, fontsize=8, loc="best")
    _condition_axis(log_ax, labels)

    mae = 100.0 * _values(comparisons, "relative_mae_improvement")
    mae_ax.bar(x, mae, color=_bar_colors(mae), width=0.68)
    mae_ax.axhline(0.0, color="#343a40", linewidth=1.0)
    mae_threshold = np.asarray([-5.0, 5.0, 5.0, -5.0, -5.0, -5.0])
    mae_ax.scatter(x, mae_threshold, marker="_", s=220, color="#111827", label="Gate")
    mae_ax.set_ylabel("Relative MAE improvement (%)")
    mae_ax.set_title("B  Count-error improvement", loc="left")
    mae_ax.legend(frameon=False, fontsize=8, loc="best")
    _condition_axis(mae_ax, labels)

    recovery = 100.0 * _values(
        comparisons, "relative_marginal_recovery_improvement"
    )
    recovery_ax.bar(x, recovery, color=_bar_colors(recovery), width=0.68)
    recovery_ax.axhline(0.0, color="#343a40", linewidth=1.0)
    recovery_ax.scatter(
        x[:3], [-5.0, 0.0, 0.0], marker="_", s=220, color="#111827", label="Applicable gate"
    )
    recovery_ax.set_ylabel("Relative recovery improvement (%)")
    recovery_ax.set_title("C  Marginal-truth recovery", loc="left")
    recovery_ax.legend(frameon=False, fontsize=8, loc="best")
    _condition_axis(recovery_ax, labels)

    offsets = (-0.18, 0.0, 0.18)
    coverage_fields = (
        ("candidate_coverage_50", 0.50, "50% interval", "#2563eb"),
        ("candidate_coverage_80", 0.80, "80% interval", "#7c3aed"),
        ("candidate_coverage_95", 0.95, "95% interval", "#c2410c"),
    )
    coverage_ax.axhspan(-3.0, 3.0, color="#1b8a5a", alpha=0.11, label="±3 pp gate")
    coverage_ax.axhline(0.0, color="#343a40", linewidth=1.0)
    for offset, (field, nominal, label, color) in zip(offsets, coverage_fields, strict=True):
        error = 100.0 * (_values(comparisons, field) - nominal)
        coverage_ax.scatter(x + offset, error, marker="o", s=34, color=color, label=label)
    coverage_ax.set_ylabel("Empirical − nominal coverage (percentage points)")
    coverage_ax.set_title("D  Predictive interval calibration", loc="left")
    coverage_ax.legend(frameon=False, fontsize=8, ncol=2, loc="best")
    _condition_axis(coverage_ax, labels)

    dependence = _values(
        comparisons, "candidate_mean_absolute_component_correlation"
    )
    dependence_ax.bar(x, dependence, color="#64748b", width=0.68)
    dependence_ax.set_ylim(0.0, 1.0)
    dependence_ax.set_ylabel("Mean absolute posterior correlation")
    dependence_ax.set_title("E  Component dependence", loc="left")
    _condition_axis(dependence_ax, labels)

    null = comparisons[0]
    null_values = 100.0 * np.asarray(
        [
            np.nan
            if null["candidate_mean_inactive_probability"] is None
            else float(null["candidate_mean_inactive_probability"]),
            np.nan
            if null["candidate_fraction_draws_below_activity_threshold"] is None
            else float(null["candidate_fraction_draws_below_activity_threshold"]),
        ]
    )
    null_x = np.arange(2)
    null_ax.bar(null_x, null_values, color="#7c3aed", width=0.58)
    null_ax.scatter(
        null_x, [10.0, 25.0], marker="_", s=240, color="#111827", label="Maximum allowed"
    )
    null_ax.set_xticks(
        null_x,
        ["Mean inactive\nprobability", "Draws below\nactivity threshold"],
    )
    null_ax.set_ylabel("Posterior support (%)")
    null_ax.set_title("F  False inactive support under null truth", loc="left")
    null_ax.legend(frameon=False, fontsize=8, loc="best")
    null_ax.grid(axis="y", color="#e5e7eb", linewidth=0.7)
    null_ax.set_axisbelow(True)

    decision = summary["decision"]
    eligible = bool(decision["eligible_for_real_fit"])
    verdict = "ELIGIBLE" if eligible else "INELIGIBLE"
    color = "#166534" if eligible else "#991b1b"
    figure.suptitle(
        f"Spatial activity simulation preflight — {verdict} for a real HbS fit",
        fontsize=16,
        fontweight="bold",
        color=color,
        y=0.965,
    )
    reason_count = len(decision["refusal_reasons"])
    figure.text(
        0.5,
        0.052,
        (
            f"{summary['completed_task_count']}/{summary['task_count']} tasks completed "
            f"successfully; all {summary['task_count']} terminal artifacts retained; "
            f"{summary['retried_task_count']} used the one allowed convergence retry; "
            f"{reason_count} preregistered refusal reason{'s' if reason_count != 1 else ''}.\n"
            "Three seeds are collapsed across five geographic outer folds. Synthetic development "
            "evidence only.\n"
            "No allele-frequency surface or biological boundary is shown."
        ),
        ha="center",
        va="center",
        fontsize=9.2,
        linespacing=1.3,
        color="#374151",
    )
    return figure


def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def render(summary: Mapping[str, object], out: Path) -> None:
    """Render a new PNG path without leaving a partial output on failure."""
    if out.exists():
        raise FileExistsError(f"refusing to overwrite output: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(f".{out.name}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    figure = build_figure(summary)
    try:
        figure.savefig(
            temporary,
            format="png",
            dpi=190,
            facecolor="white",
            metadata={"Software": "genomeOS spatial activity preflight renderer v1"},
        )
        os.replace(temporary, out)
    finally:
        plt.close(figure)
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = _parser().parse_args()
    if args.report.exists() or args.out.exists():
        raise FileExistsError("output figure and report paths must be new")
    source_bytes = args.result.read_bytes()
    result = json.loads(source_bytes)
    summary = build_public_summary(result, source_bytes=source_bytes)
    render(summary, args.out)
    try:
        report_bytes = (
            json.dumps(
                summary,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode()
            + b"\n"
        )
        _write_exclusive(args.report, report_bytes)
    except BaseException:
        args.out.unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

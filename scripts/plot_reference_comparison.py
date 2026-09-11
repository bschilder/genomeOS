#!/usr/bin/env python3
"""Render paired report bytes without fitting (Atlas design §§5, 7–8, 12).

Implements the Figure section of the 2026-09-11 paired-report design. Every
identity is shown, including absent publications and failed folds. Conditional
metrics are explicitly labelled; no confidence bars, ranking, or promotion.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import itertools
import json
import math
import zlib
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

PANELS = (
    ("Paired MAE", ("mae",), "frequency"),
    ("Integrated log score", ("mean_log_score",), "natural_log"),
    (
        "Coverage difference (50 / 80 / 95%)",
        tuple(f"coverage_{x}" for x in (50, 80, 95)),
        "percentage_points",
    ),
    (
        "Interval width difference (50 / 80 / 95%)",
        tuple(f"interval_width_{x}" for x in (50, 80, 95)),
        "frequency",
    ),
)
STAGES = ("technical_qc_4117", "paper_ancestry_exclusion_4094")
IDENTITY_FIELDS = ("cohort_stage", "count_kind", "seed", "rho_prior_beta")
COLORS = ("#176a91", "#b65816", "#6b529c")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _strict_json(data: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def number(token):
        value = float(token)
        _require(math.isfinite(value), "nonfinite JSON number")
        return value

    def constant(token):
        raise ValueError(f"nonfinite JSON constant: {token}")

    report = json.loads(data, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)
    _require(isinstance(report, dict), "report must be an object")
    return report


def _display_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    _require(report["schema_version"] == 1, "unsupported report schema")
    _require(report["evidence_kind"] == "descriptive_paired_comparison_matrix", "invalid evidence kind")
    _require(report["publication_eligible"] is False, "report must deny publication eligibility")
    _require(report["difference_direction"] == "B0H_minus_B0", "invalid difference direction")
    expected = tuple(itertools.product(STAGES, ("called", "quality"), (42, 43, 44), (9, 4)))
    pairs = report["pairs"]
    by_id = {tuple(row[k] for k in IDENTITY_FIELDS): row for row in pairs}
    _require(
        len(pairs) == len(by_id) == 24 and set(by_id) == set(expected), "expected all24 unique identities"
    )
    result = []
    for identity in expected:
        pair = by_id[identity]
        row = {**dict(zip(IDENTITY_FIELDS, identity, strict=True)), "metrics": {}}
        section = None
        label = f"{identity[0]} | {identity[1]} | seed={identity[2]} | rho_prior_beta={identity[3]}"
        if pair["status"] == "not_available":
            _require(pair["comparison"] is None and bool(pair["reason"]), "invalid unavailable pair")
            row["status"] = "not_available"
            label += f"\nnot_available: {pair['reason']}"
        else:
            _require(pair["status"] == "available", "unknown pair status")
            comparison = pair["comparison"]
            _require(comparison["difference_direction"] == "B0H_minus_B0", "invalid pair direction")
            _require(comparison["publication_eligible"] is False, "pair must deny publication eligibility")
            for side in ("b0", "b0h"):
                config = comparison["configurations"][side]
                fields = IDENTITY_FIELDS if side == "b0h" else IDENTITY_FIELDS[:3]
                _require(
                    all(config[k] == row[k] for k in fields), "pair configuration disagrees with identity"
                )
            folds = comparison["fold_outcomes"]
            _require(len(folds) == 5, "expected all five folds")
            failures = {side: sum(f[side]["status"] != "completed" for f in folds) for side in ("b0", "b0h")}
            if comparison["full_pair"]["available"]:
                _require(not any(failures.values()), "full metrics cannot include failed folds")
                row["status"], section = "complete", comparison["full_pair"]
            elif comparison["completed_fold_conditional"]["available"]:
                row["status"], section = "conditional", comparison["completed_fold_conditional"]
            else:
                row["status"] = "failed"
            label += f"\n{row['status']}"
            if section is not None:
                label += f": {len(section['split_ids'])}/5 common completed folds"
            else:
                label += ": no common completed folds"
            if row["status"] != "complete":
                label += "; " + "; ".join(f"{side} failed/infeasible={n}" for side, n in failures.items())
            row["fold_outcomes"] = folds
        row["label"] = label
        for _, metrics, unit in PANELS:
            for metric in metrics:
                entry = (
                    section["differences"][metric]
                    if section
                    else dict(value=None, reason=row["status"], unit=unit)
                )
                _require(entry["unit"] == unit, f"invalid {metric} unit")
                value, reason = entry["value"], entry["reason"]
                if type(value) in (float, int):
                    _require(math.isfinite(value) and reason is None, f"invalid finite {metric}")
                    display = f"{value:+.4g}"
                elif value is None:
                    _require(isinstance(reason, str) and bool(reason), f"missing {metric} reason")
                    display = f"undefined: {reason}" if reason == "both_negative_infinity" else reason
                else:
                    _require(
                        metric == "mean_log_score" and value in ("Infinity", "-Infinity") and reason is None,
                        f"invalid nonfinite {metric}",
                    )
                    display = value
                row["metrics"][metric] = {**entry, "display": display}
        result.append(row)
    return result


def build_figure(report: dict[str, Any]) -> tuple[Figure, dict[str, Any]]:
    """Return every plotted value/state plus named artists for independent replay."""
    rows = _display_rows(report)
    roles = {p["comparison"]["evidence_role"] for p in report["pairs"] if p["comparison"] is not None}
    synthetic = roles == {"synthetic"}
    title = (
        "SYNTHETIC reporting demonstration — no model-performance result"
        if synthetic
        else "Descriptive paired comparison — dependent development evidence"
    )
    figure, axes = plt.subplots(2, 4, figsize=(27, 18), squeeze=False)
    figure.subplots_adjust(left=0.29, right=0.985, bottom=0.12, top=0.90, wspace=0.22, hspace=0.30)
    figure.suptitle(title, fontsize=19, fontweight="bold", y=0.975)
    figure.text(
        0.5,
        0.946,
        "B0H minus B0 • both prior tracks • every requested identity retained • "
        "no confidence bars or model winner",
        ha="center",
        fontsize=12,
    )
    for track_index, rho in enumerate((9, 4)):
        track = [row for row in rows if row["rho_prior_beta"] == rho]
        for panel_index, (title, metrics, unit) in enumerate(PANELS):
            axis = axes[track_index, panel_index]
            axis_id = f"rho{rho}-panel{panel_index}"
            axis.set_gid(axis_id)
            axis.set_title(f"rho_prior_beta={rho}\n{title}", fontsize=11, pad=12)
            axis.set_xlabel(f"B0H minus B0 [{unit}]", fontsize=10)
            axis.axvline(0, color="#8b969f", linewidth=0.8, linestyle="--")
            axis.set_ylim(11.6, -0.6)
            finite = [
                row["metrics"][metric]["value"]
                for row in track
                for metric in metrics
                if type(row["metrics"][metric]["value"]) in (float, int)
            ]
            low, high = min([0.0, *finite]), max([0.0, *finite])
            padding = max(high - low, 0.02) * 0.32
            axis.set_xlim(low - padding, high + padding)
            axis.set_yticks(range(12), [r["label"] if panel_index == 0 else "" for r in track], fontsize=8)
            axis.tick_params(axis="y", length=0)
            for index, label in enumerate(axis.get_yticklabels()):
                if panel_index == 0:
                    gid = f"rho{rho}-row{index}-label"
                    label.set_gid(gid)
                    track[index]["label_artist"] = gid
            axis.grid(axis="x", color="#e4e8eb", linewidth=0.6)
            for spine in axis.spines.values():
                spine.set_visible(False)
            for index, row in enumerate(track):
                if index % 2 == 0:
                    axis.axhspan(index - 0.48, index + 0.48, color="#f2f5f7", zorder=0)
                for metric_index, metric in enumerate(metrics):
                    entry = row["metrics"][metric]
                    y = index + (metric_index - (len(metrics) - 1) / 2) * 0.22
                    gid = f"rho{rho}-row{index}-{metric}"
                    value = entry["value"]
                    if type(value) in (float, int):
                        (artist,) = axis.plot(value, y, "o", color=COLORS[metric_index], markersize=5)
                        value_label = axis.annotate(
                            entry["display"],
                            (value, y),
                            xytext=(5, 0),
                            textcoords="offset points",
                            fontsize=7,
                            va="center",
                            color=COLORS[metric_index],
                        )
                        value_label.set_gid(gid + "-value")
                        entry["value_label_artist"] = gid + "-value"
                    else:
                        artist = axis.text(
                            0.5,
                            y,
                            entry["display"],
                            transform=axis.get_yaxis_transform(),
                            ha="center",
                            va="center",
                            fontsize=7,
                            color="#6b3e32",
                        )
                    artist.set_gid(gid)
                    entry.update(artist=gid, axis_artist=axis_id)
            if len(metrics) == 3:
                for index, level in enumerate((50, 80, 95)):
                    axis.plot([], [], "o", color=COLORS[index], label=f"{level}%")
                axis.legend(
                    loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3, frameon=False, fontsize=9
                )
    figure.text(
        0.5,
        0.02,
        "Coverage: percentage points. MAE and widths: frequency units. Log score: natural-log units.\n"
        "Conditional rows use only common completed folds. "
        "Undefined and infinite contrasts have no finite-axis position.\n"
        "Narrower intervals alone do not establish improvement. "
        "No external, geographic, resident, joint-LD, or publication claim.",
        ha="center",
        fontsize=11,
    )
    return figure, {
        "schema_version": 1,
        "synthetic": synthetic,
        "difference_direction": "B0H_minus_B0",
        "rows": rows,
    }


def _fingerprint(data: bytes) -> dict[str, Any]:
    return dict(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


def run(report_path: Path, out: Path) -> None:
    """Write a new PNG and receipt, retaining partial output if a write fails."""
    _require(not out.exists(), f"output directory already exists: {out}")
    data = report_path.read_bytes()
    encoding = "gzip" if report_path.suffix == ".gz" else "json"
    try:
        decoded = gzip.decompress(data) if encoding == "gzip" else data
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError(f"invalid gzip report: {error}") from error
    figure, receipt = build_figure(_strict_json(decoded))
    try:
        out.mkdir(parents=True, exist_ok=False)
        figure.savefig(out / "comparison.png", dpi=110, metadata={"Software": "genomeOS paired comparison"})
        receipt.update(
            input_report=_fingerprint(data),
            input_encoding=encoding,
            decoded_report=_fingerprint(decoded),
            executed_source=_fingerprint(Path(__file__).read_bytes()),
            package_versions={name: importlib.metadata.version(name) for name in ("matplotlib", "numpy")},
            output_files={"comparison.png": _fingerprint((out / "comparison.png").read_bytes())},
        )
        (out / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
    finally:
        plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.report, args.out)
    except (OSError, TypeError, ValueError, KeyError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

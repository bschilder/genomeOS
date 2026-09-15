#!/usr/bin/env python3
"""Render canonical B0H calibration reports offline (report design §§1,3–4; Atlas §§5,7–8,12)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import genomeos.validation.heterogeneity_reduction as reduction_module  # noqa: E402
import genomeos.validation.heterogeneity_report as report_module  # noqa: E402
from genomeos.validation.heterogeneity_reduction_records import StudyReduction  # noqa: E402

EVIDENCE_KINDS = ("synthetic_fixture", "executed_simulation_calibration")
MODE_LABELS = ("correct", "prior-only", "cyclic-rho")
QUANTITY_LABELS = (
    "mean",
    "rho",
    "mean*rho",
    "training log likelihood",
    "log mass AC0/AN20",
    "dependence quantity",
)
GROUP_DENOMINATORS = (512, 384, 64, 1, 8)
STAGES = ("generation", "structural", "attempt0", "attempt1", "quantities", "summary")
STATUS_ORDER = (
    "available",
    "all_unavailable",
    "generation_failed",
    "expected_refusal",
    "unexpected_exception",
    "unexpected_return",
    "accepted",
    "convergence_failed",
    "failed",
    "identity_rejected",
    "complete",
    "incomplete",
    "prediction_failed",
    "diagnostics_failed",
    "unstarted",
    "not_admitted",
    "started_unresolved",
    "owner_lost",
    "execution_failed",
)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_FILES = {
    "scripts/plot_b0h_calibration.py": lambda: Path(__file__),
    "genomeos/validation/heterogeneity_report.py": lambda: Path(report_module.__file__),
    "genomeos/validation/heterogeneity_reduction.py": lambda: Path(reduction_module.__file__),
}


def _banner(evidence_kind: str) -> str:
    if evidence_kind == "synthetic_fixture":
        return "AUTHORED SYNTHETIC REPORTING FIXTURE — NOT EXECUTED CALIBRATION"
    if evidence_kind == "executed_simulation_calibration":
        return "EXECUTED SIMULATION-CALIBRATION REPORT — NOT REAL-POPULATION EVIDENCE"
    raise ValueError("unsupported evidence kind")


def _claim_text(reduction: StudyReduction) -> str:
    eligibility = str(reduction.unconditional_claim_eligible).lower()
    reasons = ", ".join(reduction.claim_reasons) if reduction.claim_reasons else "none"
    text = (
        f"recorded claim eligibility: {eligibility} | publication eligible: false\n"
        f"claim reasons: {reasons}"
    )
    if reduction.unconditional_claim_eligible:
        text += f"\nrecorded permitted claim: {reduction.permitted_claim}"
    return text


def _rank_label(row) -> str:
    return (
        f"m{row.mode_id}/q{row.quantity_id} · "
        f"{MODE_LABELS[row.mode_id]} / {QUANTITY_LABELS[row.quantity_id]}"
    )


def _rank_annotation(row) -> str:
    p_values = (
        "raw p: unavailable | adjusted p: unavailable"
        if row.test is None
        else f"raw p: {row.test.p_value:.6g} | adjusted p: {row.test.bonferroni_p_value:.6g}"
    )
    failures = (
        ", ".join(f"{status}={count}" for status, count in row.failure_status_counts)
        if row.failure_status_counts
        else "none"
    )
    return f"N={row.actual_n}/512 | {row.role} | {row.decision}\n{p_values}\nmissing: {failures}"


def build_rank_figure(reduction: StudyReduction, evidence_kind: str) -> Figure:
    """Draw both frozen rank tracks without replacing missing outcomes."""
    banner = _banner(evidence_kind)
    figure = plt.figure(figsize=(24, 28))
    grid = figure.add_gridspec(
        3,
        2,
        height_ratios=(1, 1, 0.11),
        width_ratios=(1.1, 1.65),
        left=0.12,
        right=0.99,
        bottom=0.025,
        top=0.95,
        hspace=0.17,
        wspace=0.025,
    )
    figure.suptitle(banner, fontsize=16, fontweight="bold")
    for track in (0, 1):
        axis = figure.add_subplot(grid[track, 0])
        metadata_axis = figure.add_subplot(grid[track, 1])
        axis.set_gid(f"rank-counts-track{track}")
        metadata_axis.set_gid(f"rank-metadata-track{track}")
        rows = [row for row in reduction.ranks if row.track_id == track]
        values = np.asarray([(*row.counts, row.missing_n) for row in rows], dtype=int)
        axis.imshow(values, cmap="Blues", vmin=0, vmax=512, aspect="auto")
        axis.set_xticks(range(6), ("bin 0", "bin 1", "bin 2", "bin 3", "bin 4", "missing"))
        axis.set_yticks(range(len(rows)), [_rank_label(row) for row in rows], fontsize=9)
        axis.tick_params(axis="x", labelsize=10)
        axis.set_title(
            f"track {track} — exact outcome counts (common 0–512 fill scale)", loc="left"
        )
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(values[row_index]):
                count = axis.text(
                    column_index,
                    row_index,
                    str(int(value)),
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="white" if value >= 256 else "#111827",
                )
                count.set_gid(f"rank-count-{track}-{row_index}-{column_index}")
            annotation = metadata_axis.text(
                0.01,
                row_index,
                _rank_annotation(row),
                ha="left",
                va="center",
                fontsize=8.2,
                linespacing=0.9,
                color="#111827",
            )
            annotation.set_gid(f"rank-{row.track_id}-{row.mode_id}-{row.quantity_id}")
        metadata_axis.set_xlim(0, 1)
        metadata_axis.set_ylim(axis.get_ylim())
        metadata_axis.set_title("N / role / decision · readable p-values · missing reasons", loc="left")
        metadata_axis.set_axis_off()
    footer = figure.add_subplot(grid[2, :])
    footer.set_gid("rank-footer")
    footer.set_axis_off()
    footer.text(
        0.5,
        0.58,
        _claim_text(reduction),
        ha="center",
        va="center",
        fontsize=10,
        wrap=True,
    )
    footer.text(
        0.5,
        0.12,
        "Exact binary64 p-value bits are retained in reduction.json and receipt.json. "
        "No real-population benchmark, geographic surface, or publication gate.",
        ha="center",
        va="center",
        fontsize=10,
        wrap=True,
    )
    return figure


def _accounting_values(reduction: StudyReduction, stage: str):
    groups = tuple((track, study) for track in (0, 1) for study in range(5))
    observed = {getattr(row, stage) for row in reduction.cases}
    statuses = tuple(status for status in STATUS_ORDER if status in observed)
    values = np.asarray(
        [
            [
                sum(
                    row.case.track_id == track
                    and row.case.study_id == study
                    and getattr(row, stage) == status
                    for row in reduction.cases
                )
                for status in statuses
            ]
            for track, study in groups
        ],
        dtype=int,
    )
    if int(values.sum()) != 1938:
        raise ValueError(f"{stage} accounting does not contain all1938 cases")
    if tuple(values.sum(axis=1)) != tuple(GROUP_DENOMINATORS[study] for _, study in groups):
        raise ValueError(f"{stage} group denominators differ from the frozen design")
    return groups, statuses, values


def build_accounting_figure(reduction: StudyReduction, evidence_kind: str) -> Figure:
    """Draw six case-accounting panels in which every planned case appears once."""
    banner = _banner(evidence_kind)
    figure = plt.figure(figsize=(24, 28))
    grid = figure.add_gridspec(
        4,
        2,
        height_ratios=(1, 1, 1, 0.15),
        left=0.11,
        right=0.99,
        bottom=0.02,
        top=0.95,
        hspace=0.42,
        wspace=0.2,
    )
    figure.suptitle(banner, fontsize=16, fontweight="bold")
    for index, stage in enumerate(STAGES):
        axis = figure.add_subplot(grid[index // 2, index % 2])
        axis.set_gid(f"accounting-{stage}")
        groups, statuses, values = _accounting_values(reduction, stage)
        axis.imshow(values, cmap="Blues", vmin=0, vmax=512, aspect="auto")
        axis.set_title(stage, fontsize=13)
        axis.set_xticks(range(len(statuses)), statuses, rotation=30, ha="right", fontsize=9)
        axis.set_yticks(
            range(len(groups)),
            [
                f"track{track}/study{study} (N={GROUP_DENOMINATORS[study]})"
                for track, study in groups
            ],
            fontsize=9,
        )
        for row_index, column_index in np.ndindex(values.shape):
            value = int(values[row_index, column_index])
            axis.text(
                column_index,
                row_index,
                str(value),
                ha="center",
                va="center",
                fontsize=8.5,
                color="white" if value >= 256 else "#111827",
            )
    footer = figure.add_subplot(grid[3, :])
    footer.set_gid("accounting-footer")
    footer.set_axis_off()
    footer.text(
        0.5,
        0.63,
        _claim_text(reduction),
        ha="center",
        va="center",
        fontsize=10,
        wrap=True,
    )
    footer.text(
        0.5,
        0.13,
        "Each panel counts all 1,938 cases exactly once on a shared sequential blue 0–512 ramp. "
        "Stages share cases and are not independent observations; not_admitted can mean an "
        "unnecessary retry or a blocked downstream stage.",
        ha="center",
        va="center",
        fontsize=10,
        wrap=True,
    )
    return figure


def _bytes_record(data: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def source_hashes() -> dict[str, dict[str, object]]:
    """Attest the actual renderer, decoder and serializer imported from this checkout."""
    records = {}
    for relative, loaded_path in _SOURCE_FILES.items():
        expected = (ROOT / relative).resolve()
        actual = loaded_path().resolve()
        if actual != expected:
            raise ValueError(f"{relative} was imported from a different checkout")
        records[relative] = _bytes_record(actual.read_bytes())
    return records


def _rank_receipt(reduction: StudyReduction) -> list[dict[str, object]]:
    panels = []
    for track in (0, 1):
        rows = []
        for row in reduction.ranks:
            if row.track_id != track:
                continue
            test = None
            if row.test is not None:
                test = {
                    "statistic": row.test.statistic,
                    "p_value_bits": struct.pack(">d", row.test.p_value).hex(),
                    "bonferroni_p_value_bits": struct.pack(
                        ">d", row.test.bonferroni_p_value
                    ).hex(),
                }
            rows.append(
                {
                    "track_id": row.track_id,
                    "mode_id": row.mode_id,
                    "quantity_id": row.quantity_id,
                    "label": _rank_label(row),
                    "counts": list(row.counts),
                    "actual_n": row.actual_n,
                    "missing_n": row.missing_n,
                    "failure_status_counts": [list(item) for item in row.failure_status_counts],
                    "role": row.role,
                    "decision": row.decision,
                    "test": test,
                    "annotation": _rank_annotation(row),
                }
            )
        panels.append({"track_id": track, "rows": rows})
    return panels


def _accounting_receipt(reduction: StudyReduction) -> list[dict[str, object]]:
    panels = []
    for stage in STAGES:
        groups, statuses, values = _accounting_values(reduction, stage)
        rows = []
        for index, (track, study) in enumerate(groups):
            rows.append(
                {
                    "track_id": track,
                    "study_id": study,
                    "label": f"track{track}/study{study} (N={GROUP_DENOMINATORS[study]})",
                    "denominator": GROUP_DENOMINATORS[study],
                    "status_counts": {
                        status: int(values[index, column])
                        for column, status in enumerate(statuses)
                    },
                }
            )
        panels.append(
            {
                "stage": stage,
                "statuses": list(statuses),
                "groups": rows,
                "total_cases": int(values.sum()),
            }
        )
    return panels


def _save_figure(figure: Figure, path: Path) -> None:
    try:
        with path.open("xb") as stream:
            figure.savefig(
                stream,
                format="png",
                dpi=160,
                facecolor="white",
                metadata={"Software": "genomeOS B0H calibration report renderer v1"},
            )
    finally:
        plt.close(figure)


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def render_report(
    reduction_path: Path,
    *,
    expected_reduction_sha256: str,
    evidence_kind: str,
    output: Path,
) -> dict[str, object]:
    """Validate canonical input, then render immutable outputs and a final receipt."""
    _banner(evidence_kind)
    if not _DIGEST.fullmatch(expected_reduction_sha256):
        raise ValueError("expected reduction SHA-256 must be 64 lowercase hexadecimal characters")
    if output.exists() or output.is_symlink():
        raise ValueError("output destination already exists")
    sources = source_hashes()
    raw = reduction_path.read_bytes()
    input_record = _bytes_record(raw)
    if input_record["sha256"] != expected_reduction_sha256:
        raise ValueError("reduction SHA-256 differs from the expected digest")
    reduction = report_module.read_study_reduction(raw)
    rank_panels = _rank_receipt(reduction)
    accounting_panels = _accounting_receipt(reduction)

    output.mkdir(parents=True, exist_ok=False)
    with (output / "reduction.json").open("xb") as stream:
        stream.write(raw)
    _save_figure(build_rank_figure(reduction, evidence_kind), output / "ranks.png")
    _save_figure(build_accounting_figure(reduction, evidence_kind), output / "accounting.png")
    outputs = {
        name: _bytes_record((output / name).read_bytes())
        for name in ("reduction.json", "ranks.png", "accounting.png")
    }
    receipt = {
        "format": "b0h_calibration_report_receipt",
        "version": "1",
        "evidence_kind": evidence_kind,
        "publication_eligible": False,
        "input": input_record,
        "outputs": outputs,
        "source_sha256": sources,
        "code_revision": _revision(),
        "versions": {
            "renderer_version": "1",
            "reduction_format": reduction.format,
            "reduction_version": reduction.version,
            "matplotlib": matplotlib.__version__,
            "python": sys.version.split()[0],
        },
        "figure_labels": {
            "banner": _banner(evidence_kind),
            "rank_columns": ["bin 0", "bin 1", "bin 2", "bin 3", "bin 4", "missing"],
            "rank_count_limits": [0, 512],
            "mode_labels": list(MODE_LABELS),
            "quantity_labels": list(QUANTITY_LABELS),
            "accounting_count_limits": [0, 512],
        },
        "rank_panels": rank_panels,
        "accounting_panels": accounting_panels,
        "claim": {
            "unconditional_claim_eligible": reduction.unconditional_claim_eligible,
            "claim_reasons": list(reduction.claim_reasons),
            "permitted_claim": reduction.permitted_claim,
        },
        "limitations": [
            "This report does not independently certify fitting, provenance, p-values, "
            "or scientific acceptance.",
            "It is not a real-population prediction benchmark or geographic surface.",
            "Accounting stages share cases and are not independent observations.",
            "An authored synthetic fixture is never observed calibration acceptance.",
        ],
    }
    receipt_bytes = json.dumps(
        receipt,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    with (output / "receipt.json").open("xb") as stream:
        stream.write(receipt_bytes)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a canonical offline B0H calibration report")
    parser.add_argument("--reduction", required=True, type=Path)
    parser.add_argument("--expected-reduction-sha256", required=True)
    parser.add_argument("--evidence-kind", required=True, choices=EVIDENCE_KINDS)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = render_report(
            args.reduction,
            expected_reduction_sha256=args.expected_reduction_sha256,
            evidence_kind=args.evidence_kind,
            output=args.out,
        )
        print(
            json.dumps(
                {
                    "format": receipt["format"],
                    "evidence_kind": receipt["evidence_kind"],
                    "publication_eligible": False,
                    "input_sha256": receipt["input"]["sha256"],
                    "outputs": receipt["outputs"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except (OSError, TypeError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())

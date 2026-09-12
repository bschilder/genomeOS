#!/usr/bin/env python3
"""Render immutable synthetic numerical and complete-runtime evidence (design §7, §8).

No biological accuracy, map accuracy or scientific calibration claim follows from these
plots. Zeros, floating underflow, refusals, failures and incomplete laws remain accounted.
Runtime profiles use the existing complete-workflow profiler, including transfers and sync.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_checked(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"hash mismatch: {path}")
    return json.loads(path.read_text())


def read_run(path: Path, expected: str) -> tuple[dict, list[dict], dict]:
    receipt = load_checked(path, expected)
    root = path.parent.resolve()
    for relative, checksum in receipt["file_sha256"].items():
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or digest(target) != checksum:
            raise ValueError(f"evidence file hash mismatch: {relative}")
    for relative, checksum in receipt["source_sha256"].items():
        if digest(root / "source" / relative) != checksum:
            raise ValueError(f"source snapshot mismatch: {relative}")
    matrix = load_checked(root / "matrix.json", receipt["matrix_sha256"])
    load_checked(root / "complement-declaration.json", receipt["complement_sha256"])
    planned = {case["case_id"]: case for group in ("small", "long") for case in matrix[group]}
    events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
    outcomes = [event for event in events if event["event"] == "outcome"]
    controls = [event for event in events if event["event"] == "control_outcome"]
    if len({item["name"] for item in controls}) != len(controls):
        raise ValueError("duplicate control outcomes")
    if not {item["name"] for item in controls} <= set(receipt["planned_controls"]):
        raise ValueError("undeclared control outcome")
    if len(controls) != receipt["summary"]["completed_controls"]:
        raise ValueError("control accounting mismatch")
    if len({item["case_id"] for item in outcomes}) != len(outcomes):
        raise ValueError("duplicate law outcomes")
    for item in outcomes:
        case = planned[item["case_id"]]
        if (
            item["status"] == "expected_domain_refusal"
            and case["expected_operation"] != "refuse_numeric_domain"
        ):
            raise ValueError("unexpected refusal mislabeled as expected")
        if any(item[key] != value for key, value in case.items()):
            raise ValueError("outcome differs from declared case")
        counts = [point["ac"] for point in item["points"]]
        if len(counts) != len(set(counts)) or not set(counts) <= set(case["queried_ac"]):
            raise ValueError("invalid evaluated point accounting")
        if item["status"] in {"pass", "candidate_mismatch"} and counts != case["queried_ac"]:
            raise ValueError("evaluated law has missing points")
    statuses = dict(Counter(item["status"] for item in outcomes))
    points = [point for item in outcomes for point in item["points"]]
    accounting = {
        "backend": receipt["backend"],
        "planned_laws": len(planned),
        "planned_points": sum(len(case["queried_ac"]) for case in planned.values()),
        "completed_laws": len(outcomes),
        "incomplete_laws": len(planned) - len(outcomes),
        "evaluated_points": len(points),
        "law_status_counts": statuses,
        "accounted_planned_points": sum(len(item["queried_ac"]) for item in outcomes),
        "zero_log_errors": sum(float(point["log_absolute_error"]) == 0 for point in points),
        "float_underflow_comparisons": sum(
            tail["float_underflow"] for point in points for tail in point["tails"].values()
        ),
    }
    for key in (
        "completed_laws",
        "incomplete_laws",
        "evaluated_points",
        "law_status_counts",
        "accounted_planned_points",
    ):
        if accounting[key] != receipt["summary"][key]:
            raise ValueError(f"receipt accounting mismatch: {key}")
    if (
        accounting["planned_laws"] != receipt["planned_laws"]
        or accounting["planned_points"] != receipt["planned_points"]
    ):
        raise ValueError("receipt planned inventory mismatch")
    return receipt, outcomes, accounting


def runtime_profiles(entries: list[list[str]]) -> list[dict]:
    profiles = []
    groups: dict[str, list[dict]] = {}
    for label, filename, checksum in entries:
        profile = load_checked(Path(filename), checksum)
        if profile["evidence_kind"] != "synthetic_performance_probe":
            raise ValueError("runtime input is not a synthetic full-workflow profile")
        if not profile["executed_source_sha256"] or not profile["source_revision"]:
            raise ValueError("runtime source provenance absent")
        timing = profile["timing"]
        repeats = profile["configuration"]["repeats"]
        if any(len(timing[key]) != repeats for key in ("cpu_warm_seconds", "gpu_warm_seconds")):
            raise ValueError("runtime repeats missing")
        row = {"label": label, "sha256": checksum, "profile": profile}
        profiles.append(row)
        config = dict(profile["configuration"])
        # Baseline/candidate match every workload knob, including concentration and seed.
        groups.setdefault(json.dumps(config, sort_keys=True), []).append(row)
    for rows in groups.values():
        if len({row["profile"]["input_sha256"] for row in rows}) != 1:
            raise ValueError("baseline/candidate runtime inputs do not match")
    return profiles


def render(runs: list[list[str]], profiles: list[list[str]], out: Path) -> dict:
    if out.exists():
        raise ValueError("output directory already exists")
    parsed = [read_run(Path(filename), checksum) for filename, checksum in runs]
    runtime = runtime_profiles(profiles)
    if not parsed and not runtime:
        raise ValueError("at least one numerical receipt or runtime profile is required")
    if parsed and len({(item[0]["matrix_sha256"], item[0]["complement_sha256"]) for item in parsed}) != 1:
        raise ValueError("CPU/GPU numerical runs must use identical declared inputs")
    if parsed and len({json.dumps(item[0]["source_sha256"], sort_keys=True) for item in parsed}) != 1:
        raise ValueError("CPU/GPU numerical runs must use identical source hashes")
    out.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        "label": "Synthetic numerical/performance evidence; no calibration claim",
        "numerical": [],
        "runtime": runtime,
        "input_receipts": runs,
    }
    if parsed:
        figure, (axis, inventory) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [3, 2]})
        descriptions = []
        for receipt, outcomes, accounting in parsed:
            for group, marker in (("small", "."), ("long", "x")):
                rows = [
                    (item["concentration"], float(point["log_absolute_error"]))
                    for item in outcomes
                    if item["group"] == group
                    for point in item["points"]
                ]
                if rows:
                    x, y = zip(*rows, strict=True)
                    axis.scatter(
                        x,
                        y,
                        s=9,
                        marker=marker,
                        alpha=0.6,
                        label=f"{receipt['backend']} {group}: {len(rows)} points",
                    )
            descriptions.append(
                f"{receipt['backend']}: {accounting['evaluated_points']} evaluated / "
                f"{accounting['planned_points']} planned points\n"
                f"{accounting['law_status_counts']}\n"
                f"incomplete laws: {accounting['incomplete_laws']}\n"
                f"zero errors: {accounting['zero_log_errors']}; underflow comparisons: "
                f"{accounting['float_underflow_comparisons']}"
            )
            result["numerical"].append(accounting)
        axis.set(
            xscale="log",
            yscale="symlog",
            xlabel="Finite concentration",
            ylabel="Absolute log-mass error (symlog includes zero)",
        )
        axis.set_yscale("symlog", linthresh=1e-15)
        if axis.collections:
            axis.legend(fontsize=8)
        inventory.axis("off")
        inventory.text(0, 1, "\n\n".join(descriptions), va="top", fontsize=9, wrap=True)
        figure.suptitle("Synthetic numerical evidence — complete declared domain accounting")
        figure.text(
            0.02,
            0.01,
            "Complement: independently reflected Decimal reference; "
            "does not prove two-rounded-input invariance.",
            fontsize=9,
        )
        figure.tight_layout(rect=(0, 0.06, 1, 0.95))
        figure.savefig(out / "numerical-errors.png", dpi=160)
        plt.close(figure)
        result["complement_limitation"] = parsed[0][0]["complement_limitation"]
    if runtime:
        figure, axis = plt.subplots(figsize=(12, 5))
        ticks, labels = [], []
        for i, row in enumerate(runtime):
            profile = row["profile"]
            timing = profile["timing"]
            for offset, backend, cold_key, warm_key in (
                (-0.16, "CPU", "cpu_first_seconds", "cpu_warm_seconds"),
                (0.16, "GPU", "gpu_cold_context_plus_first_scoring_seconds", "gpu_warm_seconds"),
            ):
                x = i + offset
                axis.scatter(
                    [x],
                    [timing[cold_key]],
                    marker="D",
                    color="black",
                    s=32,
                    label="Cold (GPU includes context)" if i == 0 and offset < 0 else None,
                )
                axis.scatter(
                    np.full(len(timing[warm_key]), x),
                    timing[warm_key],
                    alpha=0.6,
                    label="Every warm repeat" if i == 0 and offset < 0 else None,
                )
                ticks.append(x)
                labels.append(f"{row['label']}\n{backend}")
        axis.set_xticks(ticks, labels, rotation=25, ha="right")
        axis.set(
            ylabel="Complete predictive_diagnostics seconds",
            yscale="log",
            title="Synthetic complete-workflow runtime — transfers and synchronization included",
        )
        axis.legend()
        figure.tight_layout()
        figure.savefig(out / "full-runtime.png", dpi=160)
        plt.close(figure)
    result["output_sha256"] = {path.name: digest(path) for path in out.glob("*.png")}
    (out / "plot-accounting.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", nargs=2, action="append", default=[], metavar=("RECEIPT", "SHA256"))
    parser.add_argument(
        "--profile", nargs=3, action="append", default=[], metavar=("LABEL", "REPORT", "SHA256")
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        render(args.run, args.profile, args.out)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

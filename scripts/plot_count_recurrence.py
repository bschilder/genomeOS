#!/usr/bin/env python3
"""Render immutable synthetic numerical and complete-runtime evidence (design §7, §8).

No biological accuracy, map accuracy or scientific calibration claim follows from these
plots. Zeros, floating underflow, refusals, failures and incomplete laws remain accounted.
Runtime profiles use the existing complete-workflow profiler, including transfers and sync.

Compatibility: legacy receipts are verified against their own copied source/evidence hashes
and rendered read-only with their original pass/failure statuses. Their grouped controls
are labelled as lacking subcase records; no new subcase result is inferred retroactively.
Accounting-v2 receipts must reconcile every declared control subcase and retained point stage.
The renderer's own source hash is recorded separately from the executed validation source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from textwrap import fill
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
        "completed_laws": sum(item["status"] != "incomplete_execution" for item in outcomes),
        "incomplete_laws": len(planned) - sum(item["status"] != "incomplete_execution" for item in outcomes),
        "evaluated_points": len(points),
        "law_status_counts": statuses,
        "accounted_planned_points": sum(len(item["queried_ac"]) for item in outcomes),
        "zero_log_errors": sum(float(point["log_absolute_error"]) == 0 for point in points),
        "float_underflow_comparisons": sum(
            tail["float_underflow"] for point in points for tail in point["tails"].values()
        ),
        "run_passed": receipt["summary"]["passed"],
        "control_group_status_counts": dict(Counter(item["status"] for item in controls)),
        "control_subcase_accounting": "not_recorded_by_legacy_adapter",
    }
    if receipt.get("accounting_version", 1) >= 2:
        plans = receipt["planned_control_subcases"]
        planned_subcases = {(name, item["subcase_id"]): item for name, rows in plans.items() for item in rows}
        rows = [event for event in events if event["event"] == "control_subcase_outcome"]
        observed = [(item["name"], item["subcase_id"]) for item in rows]
        if len(set(observed)) != len(rows) or set(observed) != set(planned_subcases):
            raise ValueError("control subcase inventory mismatch")
        for item in rows:
            plan = planned_subcases[(item["name"], item["subcase_id"])]
            if item["depends_on"] != plan["depends_on"] or item["status"] not in {
                "pass",
                "fail",
                "incomplete",
            }:
                raise ValueError("invalid control subcase outcome")
        subcounts = {
            "planned_control_subcases": len(planned_subcases),
            "accounted_control_subcases": len(rows),
            "completed_control_subcases": sum(item["status"] != "incomplete" for item in rows),
            "incomplete_control_subcases": sum(item["status"] == "incomplete" for item in rows),
            "control_subcase_status_counts": dict(Counter(item["status"] for item in rows)),
        }
        for key, value in subcounts.items():
            if value != receipt["summary"][key]:
                raise ValueError(f"control subcase accounting mismatch: {key}")
        accounting.update(subcounts, control_subcase_accounting="explicit")
        for control in controls:
            recorded = {
                item["subcase_id"]: {
                    key: value for key, value in item.items() if key not in {"event", "name"}
                }
                for item in rows
                if item["name"] == control["name"]
            }
            if recorded != {item["subcase_id"]: item for item in control["subcases"]}:
                raise ValueError("control outcome differs from recorded subcases")
        stages = [event for event in events if event["event"] == "candidate_points"]
        if len({item["case_id"] for item in stages}) != len(stages):
            raise ValueError("duplicate candidate stage")
        outcome_points = {item["case_id"]: item["points"] for item in outcomes}
        if any(outcome_points.get(item["case_id"]) != item["points"] for item in stages):
            raise ValueError("retained candidate points missing from final outcomes")
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
        "renderer_source_sha256": digest(Path(__file__)),
        "plot_accounting_version": 2,
    }
    if parsed:
        descriptions = []
        for receipt, _, accounting in parsed:
            lines = [
                f"{receipt['backend']}: {'PASS' if accounting.get('run_passed') else 'FAIL'}",
                f"Evaluated points: {accounting['evaluated_points']}",
                f"Planned points: {accounting['planned_points']}",
            ]
            lines.extend(f"{name}: {count}" for name, count in accounting["law_status_counts"].items())
            lines.extend(
                [
                    f"incomplete laws: {accounting['incomplete_laws']}",
                    f"zero log errors: {accounting['zero_log_errors']}",
                    f"underflow comparisons: {accounting['float_underflow_comparisons']}",
                ]
            )
            if accounting.get("control_subcase_accounting") == "explicit":
                lines.extend(
                    f"control subcases {status}: {count}"
                    for status, count in accounting["control_subcase_status_counts"].items()
                )
            else:
                lines.append("Legacy control subcases: not recorded")
            descriptions.append("\n".join(fill(line, width=43) for line in lines))
        height = max(6, 0.24 * sum(item.count("\n") + 3 for item in descriptions))
        figure, (axis, inventory) = plt.subplots(
            1, 2, figsize=(13, height), gridspec_kw={"width_ratios": [3, 2]}
        )
        domain = []
        for receipt, outcomes, accounting in parsed:
            for group, marker in (("small", "."), ("long", "x")):
                rows = [
                    (float(np.log10(item["concentration"])), float(point["log_absolute_error"]))
                    for item in outcomes
                    if item["group"] == group
                    for point in item["points"]
                ]
                if rows:
                    x, y = zip(*rows, strict=True)
                    domain.extend(x)
                    axis.scatter(
                        x,
                        y,
                        s=9,
                        marker=marker,
                        alpha=0.6,
                        label=f"{receipt['backend']} {group}: {len(rows)} points",
                    )
            result["numerical"].append(accounting)
        axis.set(
            yscale="symlog",
            xlabel="log10(finite concentration)",
            ylabel="Absolute log-mass error (symlog includes zero)",
        )
        axis.set_yscale("symlog", linthresh=1e-15)
        if domain:
            margin = max(1.0, (max(domain) - min(domain)) * 0.025)
            axis.set_xlim(min(domain) - margin, max(domain) + margin)
        if axis.collections:
            axis.legend(fontsize=8)
        inventory.axis("off")
        inventory.text(0.02, 0.98, "\n\n".join(descriptions), va="top", fontsize=9)
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
        result["concentration_coordinate"] = "log10(concentration), displayed on a linear axis"
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

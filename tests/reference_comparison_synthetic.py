"""Tiny synthetic paired publications; hand-set diagnostics are not fit evidence."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace

import pandas as pd
from reference_b0h_synthetic import synthetic_fit

from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityConfig
from genomeos.validation.benchmark import BenchmarkFoldStatus, summarize_benchmark
from genomeos.validation.reference_b0h_artifacts import MODEL, encode_b0h, fingerprint, json_bytes
from genomeos.validation.reference_b0h_fold import B0HAttempt, B0HFoldResult
from genomeos.validation.reference_counts import ReferenceCount

PREDICTION_COLUMNS = (
    "split_id source_record_id variant_id region_id variant_group cohort_id observed_ac observed_an "
    "log_score absolute_error squared_error coverage_50 interval_width_50 coverage_80 "
    "interval_width_80 coverage_95 interval_width_95 randomized_pit"
).split()
POSTERIOR_COLUMNS = (
    "split_id variant_id training_observation_count training_ac training_an posterior_alpha posterior_beta"
).split()


def tsv(rows, columns):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def read_tsv(data):
    return list(csv.DictReader(io.StringIO(data.decode()), delimiter="\t"))


def refresh(files, name, data):
    files[name] = data
    manifest = json.loads(files["manifest.json"])
    manifest["output_files"][name] = fingerprint(data)
    files["manifest.json"] = json_bytes(manifest)


def publication(*, heterogeneity=False, failed=(), infeasible=(), all_zero=False, rho=9, log_score=-1.0):
    """Five groups, two unequally represented cells, and one unavailable AN0 row."""
    rows = tuple(
        ReferenceCount(f"{g}:{v}", v, g, "A" if i < 2 else "B", "NA", 0, 10)
        for i, g in enumerate(("001", "NA", "é:/g", "g3", "g4"))
        for v in (("001", "é:/v") if i < 2 else ("001",))
    ) + (ReferenceCount("NA", "missing", "g4", "B", "NA", 0, 0),)
    if all_zero:
        rows = tuple(replace(row, an=0) for row in rows)
        infeasible = tuple(range(5))
    configuration = dict(
        source_release="synthetic-v1",
        cohort_stage="technical_qc_4117",
        count_kind="called",
        evidence_role="synthetic",
        prior_alpha=1.0,
        prior_beta=1.0,
        folds=5,
        seed=42,
    )
    if heterogeneity:
        configuration.update(
            model=MODEL,
            rho_prior_alpha=1.0,
            rho_prior_beta=float(rho),
            draws=2,
            tune=3,
            chains=4,
            target_accept=0.9,
            cdf_backend="scipy",
        )
    folds, statuses, row_status, predictions, results, posteriors = [], [], [], [], [], []
    for i, group in enumerate(("001", "NA", "é:/g", "g3", "g4")):
        split = f"00{i}"
        test = tuple(row for row in rows if row.group_id == group)
        train = tuple(row for row in rows if row.group_id != group)
        state = "failed" if i in failed else "completed"
        reason = "ValueError: synthetic scoring failure" if i in failed else None
        if i in infeasible:
            state, reason = "infeasible", "synthetic preflight refusal"
        folds.append(
            dict(
                split_id=split,
                train_ids=[r.record_id for r in train],
                test_ids=[r.record_id for r in test],
                test_groups=[group],
                status=state,
                failure_reason=reason,
                pit_seed=100 + i,
            )
        )
        statuses.append(
            BenchmarkFoldStatus(
                split, state, tuple(r.record_id for r in test if r.an > 0 or state != "completed"), reason
            )
        )
        for row in test:
            row_status.append(
                dict(
                    split_id=split,
                    record_id=row.record_id,
                    status="unavailable_denominator"
                    if not row.an
                    else ("scored" if state == "completed" else state),
                    reason="AN is zero" if not row.an else (reason or ""),
                )
            )
            if not row.an or state != "completed":
                continue
            error = (
                ((0.2 if i == 0 else 0.1) if i < 2 else 0.4)
                if heterogeneity
                else ((0.1 if row.variant_id == "001" else 0.3) if i == 0 else (0.6 if i == 1 else 0.2))
            )
            prediction = dict(
                split_id=split,
                source_record_id=row.record_id,
                variant_id=row.variant_id,
                region_id=row.region_id,
                variant_group=row.variant_group,
                cohort_id=group,
                observed_ac=row.ac,
                observed_an=row.an,
                log_score=log_score,
                absolute_error=error,
                squared_error=error**2,
                randomized_pit=0.25,
            )
            for level in (50, 80, 95):
                prediction[f"coverage_{level}"] = heterogeneity
                prediction[f"interval_width_{level}"] = 0.4 if heterogeneity else 0.2
            predictions.append(prediction)
        config = PopulationHeterogeneityConfig(1, 1, 1, rho, draws=2, tune=3, seed=17)
        fit = None if i in infeasible else synthetic_fit(train, config=config)
        accepted = (
            B0HAttempt("initial", config, "not_attempted", "fold_preflight_infeasible")
            if fit is None
            else B0HAttempt("initial", config, "accepted", None, 0, fit.diagnostics)
        )
        retry = B0HAttempt(
            "retry",
            replace(config, draws=4, tune=6, seed=19),
            "not_attempted",
            "initial_not_attempted" if fit is None else "initial_accepted",
        )
        results.append(
            (
                split,
                B0HFoldResult(
                    state,
                    "preflight" if i in infeasible else ("scoring" if reason else None),
                    reason,
                    (accepted, retry),
                    fit,
                    None,
                    None,
                    (),
                ),
            )
        )
        if state == "completed":
            for variant in sorted({r.variant_id for r in test if r.an}):
                available = [r for r in train if r.variant_id == variant and r.an]
                posteriors.append(
                    dict(
                        split_id=split,
                        variant_id=variant,
                        training_observation_count=len(available),
                        training_ac=0,
                        training_an=sum(r.an for r in available),
                        posterior_alpha=1.0,
                        posterior_beta=1.0 + sum(r.an for r in available),
                    )
                )
    summary = summarize_benchmark(
        pd.DataFrame(predictions, columns=PREDICTION_COLUMNS), statuses, [f["split_id"] for f in folds]
    )
    summary.update(
        target="reference_panel_within_resource",
        evidence_role="synthetic",
        joint_prediction_supported=False,
        weighting_unit="source_population_group_not_independent_study",
        total_row_count=len(rows),
        unavailable_row_count=sum(r["status"] == "unavailable_denominator" for r in row_status),
        failed_row_count=sum(r["status"] in {"failed", "infeasible"} for r in row_status),
    )
    files = {
        "splits.json": json_bytes(dict(configuration=configuration, split_seed=1, folds=folds)),
        "row_status.tsv": tsv(row_status, ["split_id", "record_id", "status", "reason"]),
        "predictions.tsv": tsv(predictions, PREDICTION_COLUMNS),
        "posteriors.tsv": tsv(posteriors, POSTERIOR_COLUMNS),
        "summary.json": json_bytes(summary),
    }
    if heterogeneity:
        diagnostics, draws, posterior_frame = encode_b0h(results)
        files.update(
            {
                "fit_diagnostics.json": diagnostics,
                "posterior_draws.npz": draws,
                "posteriors.tsv": posterior_frame.to_csv(sep="\t", index=False).encode(),
            }
        )
    manifest = dict(
        schema_version=2 if heterogeneity else 1,
        target="reference_panel_within_resource",
        joint_prediction_supported=False,
        limitations=["Synthetic reporting demonstration; no scientific fit evidence."],
        configuration=configuration,
        dependency_qualification="synthetic dependent groups",
        input_files={k: fingerprint(b"synthetic") for k in ("counts", "dependencies")},
        seeds=dict(root=42, split=1, pit_by_fold={f["split_id"]: f["pit_seed"] for f in folds}),
        git=dict(head="0" * 40, dirty=False),
        science_source_sha256={"synthetic.py": "0" * 64},
        package_versions={
            k: "synthetic"
            for k in (
                "numpy",
                "scipy",
                "pandas",
                "pymc",
                "pytensor",
                "arviz",
                "xarray",
                "numpyro",
                "jax",
                "jaxlib",
            )
        },
        output_files={k: fingerprint(v) for k, v in files.items()},
    )
    if heterogeneity:
        manifest.update(
            model=MODEL,
            runtime={
                k: dict(status="unavailable", value=None, reason="synthetic")
                for k in ("python_version", "jax_backend", "cdf_backend")
            },
        )
        manifest["seeds"]["fit_by_fold"] = {f["split_id"]: dict(initial=17, retry=19) for f in folds}
    files["manifest.json"] = json_bytes(manifest)
    return files

"""B1G matched-comparison contract tests (design §§4–8, 12; issue #331)."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict

import pandas as pd
import pytest

from genomeos.validation.b1g_comparison import (
    ASSIGNMENTS_SHA256,
    B2_OBSERVATIONS_SHA256,
    DEPENDENCIES_SHA256,
    FIT_CONFIG_SHA256,
    OBSERVATIONS_SHA256,
    compare_b1g_benchmarks,
)
from genomeos.validation.spatial_gp_checkpoint import build_checkpoint_header
from genomeos.validation.splits import BenchmarkSplit


def _splits() -> tuple[BenchmarkSplit, ...]:
    return tuple(
        BenchmarkSplit(
            split_id=f"split-{index}",
            block_id=f"block-{index}",
            train_ids=(f"train-{index}",),
            test_ids=(f"row-{index}",),
            excluded_ids=(),
            exclusion_reasons=(),
            min_edge_separation_km=301.0,
            input_fingerprint="a" * 64,
            buffer_km=300.0,
            data_version="frozen",
        )
        for index in range(5)
    )


def _inputs(*, observational: bool = False) -> dict[str, dict[str, object]]:
    return {
        "assignments": {
            "sha256": ASSIGNMENTS_SHA256 if observational else "b" * 64,
            "size_bytes": 2,
        },
        "dependencies": {
            "sha256": DEPENDENCIES_SHA256 if observational else "c" * 64,
            "size_bytes": 3,
        },
        "fit_config": {
            "sha256": FIT_CONFIG_SHA256 if observational else "d" * 64,
            "size_bytes": 4,
        },
        "observations": {
            "sha256": OBSERVATIONS_SHA256 if observational else "e" * 64,
            "size_bytes": 5,
        },
    }


def _configuration() -> dict[str, object]:
    return {
        "buffer_km": 300.0,
        "candidate_grid": {
            "radii_km": [500.0, 1000.0, 2000.0],
            "basis_counts": [8, 16, 32],
        },
        "cdf_backend": "cupy",
        "data_version": "frozen",
        "fit_config": {"max_rhat": 1.05, "min_ess": 200.0},
        "query_chunk_size": 1024,
        "sampler_convergence_gate": {
            "maximum_divergences": 0,
            "maximum_rhat": 1.05,
            "minimum_bulk_ess": 200.0,
            "minimum_tail_ess": 200.0,
        },
        "seed": 42,
    }


def _header(*, observational: bool = False) -> dict[str, object]:
    splits = _splits()
    return build_checkpoint_header(
        model_id="B1G",
        evidence_kind="observational_research" if observational else "synthetic_fixture",
        qualification={
            "assignment_review_status": "algorithmic_development_unreviewed",
            "dependency_review_status": "not_checked",
            "scientific_promotion_decision": "not_made",
        },
        configuration=_configuration(),
        input_files=_inputs(observational=observational),
        planned_splits=[asdict(split) for split in splits],
        seed_schedule=[{"split_id": split.split_id} for split in splits],
        code_revision="f" * 40,
        science_source_sha256={"science.py": "1" * 64},
        package_versions={"python": "3.12.0"},
    )


def _baseline_manifest(model_id: str, *, observational: bool = False) -> dict[str, object]:
    inputs = _inputs(observational=observational)
    inputs.pop("fit_config")
    if model_id == "B2-current":
        inputs["fit_config"] = {"sha256": "9" * 64, "size_bytes": 9}
        if observational:
            inputs["observations"] = {
                "sha256": B2_OBSERVATIONS_SHA256,
                "size_bytes": 10,
            }
    splits = []
    for split in _splits():
        splits.append(
            json.loads(
                json.dumps(
                    {
                        **asdict(split),
                        "status": "completed",
                        "failure_reason": None,
                    }
                )
            )
        )
    return {
        "model": {"model_id": model_id},
        "evidence_kind": "observational_research" if observational else "synthetic_fixture",
        "publication_eligible": False,
        "configuration": {"buffer_km": 300.0, "data_version": "frozen", "seed": 42},
        "input_files": inputs,
        "splits": splits,
    }


def _candidate_manifest(header: dict[str, object]) -> dict[str, object]:
    return {
        "model": {"model_id": "B1G"},
        "evidence_kind": header["evidence_kind"],
        "publication_eligible": False,
        "qualification": deepcopy(header["qualification"]),
        "configuration": deepcopy(header["configuration"]),
        "input_files": deepcopy(header["input_files"]),
        "checkpoint_header_sha256": header["header_sha256"],
        "code_revision": header["code_revision"],
        "folds": [
            {
                "ordinal": index,
                "status": {
                    "split_id": split.split_id,
                    "status": "completed",
                    "expected_test_ids": list(split.test_ids),
                    "selected_radius_km": 500.0,
                    "selected_basis_count": 8,
                    "failure_reason": None,
                },
                "runtime": {
                    "elapsed_seconds": 1.0,
                    "peak_rss_bytes": 1,
                    "device": "synthetic",
                    "query_chunk_size": 1024,
                },
            }
            for index, split in enumerate(_splits())
        ],
    }


def _predictions(log_scores: list[float], errors: list[float]) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        {
            "split_id": f"split-{index}",
            "block_id": f"block-{index}",
            "source_record_id": f"row-{index}",
            "variant_id": "chr11-5227002-T-A",
            "region_id": f"region-{index}",
            "variant_group": "hbs",
            "cohort_id": f"cohort-{index}",
            "observed_ac": 0 if index < 2 else index,
            "observed_an": 100,
            "log_score": log_score,
            "absolute_error": error,
            "squared_error": error**2,
            "coverage_50": index < 3,
            "interval_width_50": 0.1,
            "coverage_80": index < 4,
            "interval_width_80": 0.2,
            "coverage_95": True,
            "interval_width_95": 0.3,
            "randomized_pit": 0.5,
        }
        for index, (log_score, error) in enumerate(zip(log_scores, errors, strict=True))
    )


def _comparison_inputs(*, observational: bool = False):
    header = _header(observational=observational)
    return {
        "candidate_predictions": _predictions([-1.0] * 5, [0.08] * 5),
        "b0_predictions": _predictions([-3.0] * 5, [0.12] * 5),
        "b2_predictions": _predictions([-2.0] * 5, [0.10] * 5),
        "candidate_manifest": _candidate_manifest(header),
        "candidate_checkpoint_header": header,
        "b0_manifest": _baseline_manifest("B0", observational=observational),
        "b2_manifest": _baseline_manifest("B2-current", observational=observational),
    }


def test_dual_comparison_uses_exact_rows_and_retains_unresolved_gates():
    report, matched = compare_b1g_benchmarks(**_comparison_inputs())

    assert report["models"] == {
        "candidate": "B1G",
        "baselines": ["B0", "B2-current"],
        "strongest_predeclared_baseline": "B2-current",
    }
    assert report["scientific_promotion_decision"] == "not_made"
    assert set(matched) == {"B0", "B2-current"}
    for baseline in ("B0", "B2-current"):
        comparison = report["comparisons"][baseline]
        assert comparison["matched_observation_count"] == 5
        assert comparison["paired_outer_block_log_score_interval"]["ordered_resample_count"] == 3125
        assert set(comparison["matched_row_count_strata"]) == {"positive", "zero"}
    gates = report["strongest_baseline_gate_evidence"]
    assert gates["balanced_macro_mae"]["passed"] is True
    assert gates["predictive_coverage"]["passed"] is False
    assert gates["paired_log_score_interval"]["numerically_excludes_zero"] is True
    assert gates["paired_log_score_interval"]["dependency_aware_certified"] is False
    assert gates["stratum_noninferiority"]["status"] == "not_evaluated"
    assert gates["admission_evidence_complete"] is False


def test_comparison_refuses_checkpoint_or_split_identity_drift():
    inputs = _comparison_inputs()
    inputs["candidate_checkpoint_header"] = deepcopy(inputs["candidate_checkpoint_header"])
    inputs["candidate_checkpoint_header"]["configuration"]["seed"] = 7
    with pytest.raises(ValueError, match="integrity"):
        compare_b1g_benchmarks(**inputs)

    inputs = _comparison_inputs()
    inputs["b2_manifest"]["splits"][0]["test_ids"] = ["different-row"]
    with pytest.raises(ValueError, match="split identity"):
        compare_b1g_benchmarks(**inputs)


def test_comparison_refuses_incomplete_candidate_fold():
    inputs = _comparison_inputs()
    inputs["candidate_manifest"]["folds"][-1]["status"]["status"] = "failed"
    inputs["candidate_manifest"]["folds"][-1]["status"]["failure_reason"] = "fit failed"
    with pytest.raises(ValueError, match="every planned fold"):
        compare_b1g_benchmarks(**inputs)


def test_observational_comparison_requires_the_preregistered_input_hashes():
    inputs = _comparison_inputs(observational=True)
    compare_b1g_benchmarks(**inputs)

    inputs["b2_manifest"]["input_files"]["observations"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frozen observations"):
        compare_b1g_benchmarks(**inputs)

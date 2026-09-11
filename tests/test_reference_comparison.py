"""Synthetic paired reporting acceptance tests (design §§5, 7–8, 12)."""

from __future__ import annotations

import importlib.util
import json
from math import sqrt

import pytest
from reference_comparison_synthetic import publication, read_tsv, refresh, tsv

from genomeos.validation.reference_b0h_artifacts import json_bytes


def compare(b0, b0h):
    name = "genomeos.validation.reference_comparison"
    assert importlib.util.find_spec(name) is not None, "missing public paired report module"
    from genomeos.validation.reference_comparison import compare_reference_publications

    return compare_reference_publications(b0, b0h)


@pytest.mark.parametrize("rho", [9, 4])
def test_hand_weighted_complete_pair_and_rmse(rho):
    report = compare(publication(), publication(heterogeneity=True, rho=rho))
    assert report["comparison_complete"] is True
    assert report["publication_eligible"] is False
    assert report["evidence_kind"] == "descriptive_paired_comparison"
    assert report["configurations"]["b0h"]["rho_prior_beta"] == rho
    full = report["full_pair"]
    assert full["b0"]["metrics"]["mae"] == pytest.approx(0.3)
    assert full["b0h"]["metrics"]["mae"] == pytest.approx(0.275)
    assert full["differences"]["mae"]["value"] == pytest.approx(-0.025)
    assert full["differences"]["rmse"]["value"] == pytest.approx(sqrt(0.0925) - 0.35)
    assert full["differences"]["coverage_95"] == {"value": 100.0, "reason": None, "unit": "percentage_points"}
    assert full["differences"]["interval_width_95"]["value"] == pytest.approx(0.2)
    assert report["counts"] == {
        "total_rows": 8,
        "matched_rows": 7,
        "unavailable_rows": 1,
        "excluded_scoreable_rows": 0,
        "failed_rows_b0": 0,
        "failed_rows_b0h": 0,
    }
    assert full["b0"]["represented_cell_count"] == 2
    assert {r["cohort_id"] for r in full["b0"]["declared_cohort_cell_metrics"]} == {
        "001",
        "NA",
        "é:/g",
        "g3",
        "g4",
    }
    assert any(
        row["record_id"] == "NA" and row["status"] == "unavailable_denominator"
        for row in report["row_status"]["b0"]
    )
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    ("left", "right", "common"),
    [((0,), (), 4), ((0,), (0,), 4), ((0, 1, 2), (3, 4), 0), (tuple(range(5)), tuple(range(5)), 0)],
)
def test_valid_failed_folds_are_retained_and_only_common_folds_scored(left, right, common):
    report = compare(publication(failed=left), publication(heterogeneity=True, failed=right))
    assert report["comparison_complete"] is False
    assert report["full_pair"]["available"] is False
    assert report["full_pair"]["differences"] is None
    assert report["full_pair"]["b0"] is report["full_pair"]["b0h"] is None
    conditional = report["completed_fold_conditional"]
    assert len(conditional["split_ids"]) == common
    assert conditional["available"] is bool(common)
    assert len(report["fold_outcomes"]) == 5
    assert sum(f["b0"]["status"] == "failed" for f in report["fold_outcomes"]) == len(left)
    assert len(report["fit_diagnostics_b0h"]["folds"]) == 5
    assert report["counts"]["unavailable_rows"] == 1
    if not common:
        assert conditional["b0"] is conditional["b0h"] is conditional["differences"] is None
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize(
    ("a", "b", "value", "reason"),
    [
        (-1, -2, -1.0, None),
        (float("-inf"), -2, "Infinity", None),
        (-1, float("-inf"), "-Infinity", None),
        (float("-inf"), float("-inf"), None, "both_negative_infinity"),
    ],
)
def test_log_score_contrasts_and_zero_probability_counts(a, b, value, reason):
    report = compare(publication(log_score=a), publication(heterogeneity=True, log_score=b))
    full = report["full_pair"]
    assert full["differences"]["mean_log_score"] == dict(value=value, reason=reason, unit="natural_log")
    for model, score in [("b0", a), ("b0h", b)]:
        summary = full[model]
        assert summary["zero_probability_count"] == (7 if score == float("-inf") else 0)
        if score == float("-inf"):
            assert all(r["mean_log_score"] == "-Infinity" for r in summary["cell_metrics"])
            assert all(r["zero_probability_count"] > 0 for r in summary["declared_cohort_cell_metrics"])
    json.dumps(report, allow_nan=False)


def test_row_reordering_changes_only_publication_fingerprints():
    left, right = publication(), publication(heterogeneity=True)
    first = compare(left, right)
    for files in (left, right):
        for name in ("predictions.tsv", "row_status.tsv", "posteriors.tsv"):
            rows = read_tsv(files[name])
            refresh(files, name, tsv(list(reversed(rows)), list(rows[0])))
    second = compare(left, right)
    assert first.pop("publication_fingerprints") != second.pop("publication_fingerprints")
    assert first == second


@pytest.mark.parametrize(
    "key",
    [
        "source_release",
        "cohort_stage",
        "count_kind",
        "evidence_role",
        "prior_alpha",
        "prior_beta",
        "folds",
        "seed",
    ],
)
def test_configuration_identity_disagreement_refused(key):
    left, right = publication(), publication(heterogeneity=True)
    manifest = json.loads(left["manifest.json"])
    original = manifest["configuration"][key]
    manifest["configuration"][key] = original + 1 if type(original) in (int, float) else "other"
    left["manifest.json"] = json_bytes(manifest)
    with pytest.raises(ValueError):
        compare(left, right)


@pytest.mark.parametrize(
    "mode",
    [
        "target",
        "joint",
        "counts",
        "dependencies",
        "qualification",
        "root",
        "split",
        "pit",
        "schema",
        "boolean_seed",
    ],
)
def test_manifest_identity_and_seed_disagreement_refused(mode):
    left, right = publication(), publication(heterogeneity=True)
    manifest = json.loads(left["manifest.json"])
    if mode in ("counts", "dependencies"):
        manifest["input_files"][mode]["sha256"] = "1" * 64
    elif mode == "qualification":
        manifest["dependency_qualification"] = "other"
    elif mode in ("root", "split"):
        manifest["seeds"][mode] += 1
    elif mode == "pit":
        manifest["seeds"]["pit_by_fold"]["000"] += 1
    elif mode == "boolean_seed":
        manifest["seeds"]["split"] = True
    else:
        key, value = {
            "target": ("target", "resident"),
            "joint": ("joint_prediction_supported", True),
            "schema": ("schema_version", 2),
        }[mode]
        manifest[key] = value
    left["manifest.json"] = json_bytes(manifest)
    with pytest.raises(ValueError):
        compare(left, right)


@pytest.mark.parametrize(
    "mode",
    ["train", "test", "group", "pit", "duplicate_split", "duplicate_test", "failed_membership", "reason"],
)
def test_split_membership_is_checked_independently_of_outcome(mode):
    left, right = publication(failed=(0,)), publication(heterogeneity=True, failed=(0,))
    document = json.loads(left["splits.json"])
    fold = document["folds"][0]
    if mode in ("train", "test", "group", "failed_membership"):
        key = {
            "train": "train_ids",
            "test": "test_ids",
            "group": "test_groups",
            "failed_membership": "test_ids",
        }[mode]
        fold[key][0] = "different"
    elif mode == "pit":
        fold["pit_seed"] += 1
    elif mode == "duplicate_split":
        document["folds"][1]["split_id"] = fold["split_id"]
    elif mode == "duplicate_test":
        fold["test_ids"].append(fold["test_ids"][0])
    else:
        fold["failure_reason"] = None
    refresh(left, "splits.json", json_bytes(document))
    with pytest.raises(ValueError):
        compare(left, right)


@pytest.mark.parametrize(
    "mode",
    [
        "duplicate",
        "missing",
        "unknown",
        "variant_id",
        "cohort_id",
        "region_id",
        "variant_group",
        "observed_ac",
        "observed_an",
        "fractional",
        "large_fractional",
        "negative",
        "nan",
        "infinite",
        "boolean",
        "failed_prediction",
        "count_domain",
    ],
)
def test_prediction_corruption_is_refused(mode):
    left = publication(failed=(0,)) if mode == "failed_prediction" else publication()
    right = publication(heterogeneity=True)
    rows = read_tsv(left["predictions.tsv"])
    columns = list(rows[0])
    if mode == "duplicate":
        rows.append(rows[0].copy())
    elif mode == "missing":
        rows.pop()
    elif mode == "unknown":
        rows[0]["source_record_id"] = "unknown"
    elif mode in ("variant_id", "cohort_id", "region_id", "variant_group"):
        rows[0][mode] = "other"
    elif mode in ("observed_ac", "observed_an"):
        rows[0][mode] = "1" if mode == "observed_ac" else "11"
    elif mode in ("fractional", "large_fractional", "negative", "count_domain"):
        rows[0]["observed_ac"] = {
            "fractional": "0.1",
            "large_fractional": "9007199254740992.1",
            "negative": "-1",
            "count_domain": "11",
        }[mode]
    elif mode == "failed_prediction":
        rows[0].update(split_id="000", source_record_id="001:001", cohort_id="001")
    else:
        key, value = {
            "nan": ("absolute_error", "nan"),
            "infinite": ("randomized_pit", "inf"),
            "boolean": ("coverage_50", "0"),
        }[mode]
        rows[0][key] = value
    refresh(left, "predictions.tsv", tsv(rows, columns))
    with pytest.raises(ValueError):
        compare(left, right)


@pytest.mark.parametrize("mode", ["duplicate", "missing", "unavailable", "reason", "status"])
def test_row_status_corruption_is_refused(mode):
    left, right = publication(), publication(heterogeneity=True)
    rows = read_tsv(left["row_status.tsv"])
    columns = list(rows[0])
    if mode == "duplicate":
        rows.append(rows[0].copy())
    elif mode == "missing":
        rows.pop()
    elif mode == "unavailable":
        rows[-1].update(status="scored", reason="")
    elif mode == "reason":
        rows[0]["reason"] = "not empty"
    else:
        rows[0]["status"] = "failed"
    refresh(left, "row_status.tsv", tsv(rows, columns))
    with pytest.raises(ValueError):
        compare(left, right)


@pytest.mark.parametrize("side", ["b0", "b0h"])
@pytest.mark.parametrize(
    "mode",
    [
        "missing_file",
        "extra_file",
        "hash",
        "duplicate_json",
        "nan_json",
        "overflow_json",
        "short_tsv",
        "extra_tsv",
        "duplicate_header",
        "empty_tsv",
        "summary_count",
        "summary_complete",
        "summary_target",
        "posterior_nan",
        "posterior_count",
        "posterior_duplicate",
    ],
)
def test_malformed_publications_refused(side, mode):
    left, right = publication(), publication(heterogeneity=True)
    files = left if side == "b0" else right
    if mode == "missing_file":
        files.pop("row_status.tsv")
    elif mode == "extra_file":
        files["extra"] = b"x"
    elif mode == "hash":
        files["predictions.tsv"] += b"x"
    elif mode in ("duplicate_json", "nan_json", "overflow_json"):
        payload = {
            "duplicate_json": b'{"a":1,"a":2}',
            "nan_json": b'{"a":NaN}',
            "overflow_json": b'{"a":1e999}',
        }[mode]
        refresh(files, "summary.json", payload)
    elif mode.startswith("summary"):
        summary = json.loads(files["summary.json"])
        summary[
            {
                "summary_count": "scored_observation_count",
                "summary_complete": "comparison_complete",
                "summary_target": "target",
            }[mode]
        ] = {"summary_count": 99, "summary_complete": False, "summary_target": "other"}[mode]
        refresh(files, "summary.json", json_bytes(summary))
    elif mode.startswith("posterior"):
        rows = read_tsv(files["posteriors.tsv"])
        columns = list(rows[0])
        if mode == "posterior_duplicate":
            rows.append(rows[0].copy())
        else:
            rows[0][columns[-1] if mode == "posterior_nan" else "training_an"] = (
                "nan" if mode == "posterior_nan" else "4.2"
            )
        refresh(files, "posteriors.tsv", tsv(rows, columns))
    else:
        lines = files["predictions.tsv"].decode().splitlines()
        if mode == "empty_tsv":
            payload = b""
        elif mode == "duplicate_header":
            lines[0] = lines[0].replace("variant_id", "cohort_id")
            payload = ("\n".join(lines) + "\n").encode()
        else:
            lines[1] = lines[1] + "\textra" if mode == "extra_tsv" else "\t".join(lines[1].split("\t")[:-1])
            payload = ("\n".join(lines) + "\n").encode()
        refresh(files, "predictions.tsv", payload)
    with pytest.raises(ValueError):
        compare(left, right)


def test_stored_metric_values_are_not_used():
    left, right = publication(), publication(heterogeneity=True)
    summary = json.loads(left["summary.json"])
    summary["metrics"]["mae"] = 999
    refresh(left, "summary.json", json_bytes(summary))
    assert compare(left, right)["full_pair"]["b0"]["metrics"]["mae"] == pytest.approx(0.3)


@pytest.mark.parametrize("side", ["b0", "b0h"])
def test_summary_boolean_count_is_not_an_integer(side):
    left, right = publication(), publication(heterogeneity=True)
    files = left if side == "b0" else right
    document = json.loads(files["summary.json"])
    document["split_counts"]["failed"] = False
    refresh(files, "summary.json", json_bytes(document))
    with pytest.raises(ValueError):
        compare(left, right)


def test_large_integer_counts_are_compared_exactly():
    left, right = publication(), publication(heterogeneity=True)
    for files, count in ((left, 9007199254740992), (right, 9007199254740993)):
        rows = read_tsv(files["predictions.tsv"])
        rows[0]["observed_an"] = str(count)
        refresh(files, "predictions.tsv", tsv(rows, list(rows[0])))
    with pytest.raises(ValueError, match="identity/count"):
        compare(left, right)


@pytest.mark.parametrize(
    "column", ["cohort_id", "variant_id", "region_id", "source_record_id", "variant_group"]
)
def test_empty_literal_prediction_id_is_refused(column):
    left, right = publication(), publication(heterogeneity=True)
    rows = read_tsv(left["predictions.tsv"])
    rows[0][column] = ""
    refresh(left, "predictions.tsv", tsv(rows, list(rows[0])))
    with pytest.raises(ValueError):
        compare(left, right)


def test_infinite_log_contrasts_are_retained_at_cell_and_group_levels():
    report = compare(
        publication(log_score=float("-inf")), publication(heterogeneity=True, log_score=float("-inf"))
    )
    for key in ("cell_differences", "declared_cohort_cell_differences"):
        for row in report["full_pair"][key]:
            assert row["zero_probability_count_b0"] == row["zero_probability_count_b0h"] > 0
            assert row["differences"]["mean_log_score"]["value"] is None
            assert row["differences"]["mean_log_score"]["reason"] == "both_negative_infinity"


def test_source_hashes_backend_and_fit_seed_are_not_pairing_keys():
    left, right = publication(), publication(heterogeneity=True)
    document = json.loads(left["manifest.json"])
    document["science_source_sha256"]["synthetic.py"] = "1" * 64
    document["git"]["head"] = "1" * 40
    left["manifest.json"] = json_bytes(document)
    assert compare(left, right)["comparison_complete"] is True


def test_b0_fractional_prior_preserves_integer_subtraction_before_float_addition():
    left, right = publication(), publication(heterogeneity=True)
    for files in (left, right):
        manifest = json.loads(files["manifest.json"])
        manifest["configuration"]["prior_beta"] = 0.1
        files["manifest.json"] = json_bytes(manifest)
        document = json.loads(files["splits.json"])
        document["configuration"]["prior_beta"] = 0.1
        refresh(files, "splits.json", json_bytes(document))
    rows = read_tsv(left["posteriors.tsv"])
    for row in rows:
        row["training_ac"] = str(int(row["training_an"]) - 1)
        row["posterior_alpha"] = row["training_an"]
        row["posterior_beta"] = "1.1"
    refresh(left, "posteriors.tsv", tsv(rows, list(rows[0])))
    assert compare(left, right)["comparison_complete"] is True


def test_valid_preflight_infeasible_fold_retains_unused_attempts():
    report = compare(publication(infeasible=(0,)), publication(heterogeneity=True, infeasible=(0,)))
    assert report["comparison_complete"] is False
    assert report["counts"]["failed_rows_b0"] == report["counts"]["failed_rows_b0h"] == 2
    assert report["model_run_summaries"]["b0"]["split_counts"]["infeasible"] == 1
    assert report["fit_diagnostics_b0h"]["folds"][0]["attempts"][0]["status"] == "not_attempted"
    assert report["completed_fold_conditional"]["split_ids"] == ["001", "002", "003", "004"]


def test_all_an0_has_valid_empty_predictions_and_posteriors_with_no_metrics():
    report = compare(publication(all_zero=True), publication(heterogeneity=True, all_zero=True))
    assert report["counts"]["unavailable_rows"] == 8
    assert report["counts"]["matched_rows"] == report["counts"]["excluded_scoreable_rows"] == 0
    assert report["model_run_summaries"]["b0"]["split_counts"]["infeasible"] == 5
    assert report["completed_fold_conditional"]["available"] is False
    assert all(fold["posterior_status"] == "not_available" for fold in report["fit_diagnostics_b0h"]["folds"])


@pytest.mark.parametrize("name", ["predictions.tsv", "posteriors.tsv", "row_status.tsv"])
def test_empty_table_needs_schema_even_when_all_folds_infeasible(name):
    left, right = publication(all_zero=True), publication(heterogeneity=True, all_zero=True)
    refresh(left, name, b"")
    with pytest.raises(ValueError):
        compare(left, right)


@pytest.mark.parametrize(("key", "value"), [("seed", 42.0), ("folds", 5.0), ("prior_alpha", True)])
def test_split_configuration_types_cannot_change_identity(key, value):
    left, right = publication(), publication(heterogeneity=True)
    document = json.loads(left["splits.json"])
    document["configuration"][key] = value
    refresh(left, "splits.json", json_bytes(document))
    with pytest.raises(ValueError):
        compare(left, right)

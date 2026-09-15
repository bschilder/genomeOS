"""Pure publication decoding for paired reference reports (design §§5, 7–8, 12).

The legacy B0 and B0H wire formats stay unchanged. Bytes are validated before
comparison; unavailable rows and scientific failures are retained as evidence.
This module does not read files or fit, predict, or score observations.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

import pandas as pd

from genomeos.validation.benchmark import BenchmarkFoldStatus, summarize_benchmark
from genomeos.validation.reference_b0h_artifacts import (
    B0H_OUTPUT_FILENAMES,
    B0H_POSTERIOR_COLUMNS,
    fingerprint,
    validate_b0h_publication,
)

B0_OUTPUT_FILENAMES = ("splits.json", "row_status.tsv", "predictions.tsv", "posteriors.tsv", "summary.json")
BASE_CONFIGURATION = frozenset(
    "source_release cohort_stage count_kind evidence_role prior_alpha prior_beta folds seed".split()
)
PREDICTION_COLUMNS = tuple(
    (
        "split_id source_record_id variant_id region_id variant_group cohort_id observed_ac observed_an "
        "log_score absolute_error squared_error coverage_50 interval_width_50 coverage_80 "
        "interval_width_80 coverage_95 interval_width_95 randomized_pit"
    ).split()
)
B0_POSTERIOR_COLUMNS = tuple(
    (
        "split_id variant_id training_observation_count training_ac training_an "
        "posterior_alpha posterior_beta"
    ).split()
)


@dataclass(frozen=True)
class ReferencePublication:
    """Validated literal identities, complete ledgers, and recomputed diagnostics."""

    manifest: dict[str, Any]
    folds: tuple[dict[str, Any], ...]
    row_status: tuple[dict[str, str], ...]
    predictions: pd.DataFrame
    statuses: tuple[BenchmarkFoldStatus, ...]
    summary: dict[str, Any]
    fit_diagnostics: dict[str, Any] | None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _label(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _finite(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value)


def _json(data: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON object key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    def number(token):
        value = float(token)
        _require(isfinite(value), "nonfinite JSON number")
        return value

    result = json.loads(
        data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_float=number
    )
    _require(isinstance(result, dict), "JSON document must be an object")
    return result


def _tsv(data: bytes, columns: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t", strict=True))
    except csv.Error as error:
        raise ValueError("malformed TSV") from error
    _require(bool(rows) and tuple(rows[0]) == columns, "TSV columns must match publication schema")
    _require(all(len(row) == len(columns) for row in rows[1:]), "TSV field count mismatch")
    return [dict(zip(columns, row, strict=True)) for row in rows[1:]]


def _count(token: str) -> int:
    _require(re.fullmatch(r"[+-]?[0-9]+", token) is not None, "count must be an exact base-10 integer")
    value = int(token)
    _require(value >= 0, "count must be nonnegative")
    return value


def _number(token: str, *, log_score: bool = False) -> float:
    value = float(token)
    _require(isfinite(value) or (log_score and value == float("-inf")), "nonfinite diagnostic")
    return value


def _labels(values: object) -> list[str]:
    _require(
        isinstance(values, list) and bool(values) and all(_label(v) for v in values),
        "membership must contain nonempty literal strings",
    )
    _require(len(set(values)) == len(values), "duplicate membership identity")
    return sorted(values)


def _validate_manifest(manifest: dict[str, Any], *, heterogeneity: bool) -> None:
    base_keys = set(
        (
            "schema_version target joint_prediction_supported limitations configuration "
            "dependency_qualification input_files seeds git science_source_sha256 "
            "package_versions output_files"
        ).split()
    )
    _require(
        set(manifest) == base_keys | ({"model", "runtime"} if heterogeneity else set()),
        "invalid manifest fields",
    )
    _require(
        type(manifest["schema_version"]) is int and manifest["schema_version"] == (2 if heterogeneity else 1),
        "invalid manifest schema",
    )
    _require(
        manifest["target"] == "reference_panel_within_resource"
        and manifest["joint_prediction_supported"] is False,
        "invalid target or joint claim",
    )
    config = manifest["configuration"]
    _require(isinstance(config, dict) and BASE_CONFIGURATION <= set(config), "invalid configuration")
    if not heterogeneity:
        _require(set(config) == BASE_CONFIGURATION, "invalid B0 configuration fields")
    for key in ("source_release", "cohort_stage"):
        _require(_label(config[key]), f"invalid {key}")
    _require(
        config["count_kind"] in {"called", "quality"}
        and config["evidence_role"] in {"synthetic", "development"},
        "invalid configuration labels",
    )
    for key in ("prior_alpha", "prior_beta"):
        _require(_finite(config[key]) and config[key] > 0, "invalid prior")
    _require(
        _integer(config["seed"]) and type(config["folds"]) is int and config["folds"] == 5,
        "expected nonnegative seed and five folds",
    )
    seeds = manifest["seeds"]
    _require(
        isinstance(seeds, dict)
        and set(seeds) == {"root", "split", "pit_by_fold"} | ({"fit_by_fold"} if heterogeneity else set()),
        "invalid seed fields",
    )
    _require(
        _integer(seeds["root"]) and seeds["root"] == config["seed"] and _integer(seeds["split"]),
        "invalid root/split seeds",
    )
    _require(
        isinstance(seeds["pit_by_fold"], dict)
        and len(seeds["pit_by_fold"]) == 5
        and all(_label(k) and _integer(v) for k, v in seeds["pit_by_fold"].items()),
        "invalid PIT seeds",
    )
    _require(_label(manifest["dependency_qualification"]), "invalid dependency qualification")
    inputs = manifest["input_files"]
    _require(isinstance(inputs, dict) and set(inputs) == {"counts", "dependencies"}, "invalid input files")
    for record in inputs.values():
        _require(
            isinstance(record, dict)
            and set(record) == {"sha256", "size_bytes"}
            and isinstance(record["sha256"], str)
            and re.fullmatch("[0-9a-f]{64}", record["sha256"]) is not None
            and _integer(record["size_bytes"]),
            "invalid input fingerprint",
        )
    _require(
        isinstance(manifest["limitations"], list)
        and bool(manifest["limitations"])
        and all(_label(v) for v in manifest["limitations"]),
        "invalid limitations",
    )
    git = manifest["git"]
    _require(
        isinstance(git, dict)
        and set(git) == {"head", "dirty"}
        and isinstance(git["head"], str)
        and re.fullmatch("[0-9a-f]{40}", git["head"]) is not None
        and type(git["dirty"]) is bool,
        "invalid Git provenance",
    )
    sources = manifest["science_source_sha256"]
    _require(isinstance(sources, dict) and bool(sources), "missing source hashes")
    for key, value in sources.items():
        _require(
            _label(key)
            and not key.startswith("/")
            and ".." not in key.split("/")
            and isinstance(value, str)
            and re.fullmatch("[0-9a-f]{64}", value) is not None,
            "invalid source hash",
        )
    versions = manifest["package_versions"]
    _require(
        isinstance(versions, dict)
        and {"numpy", "scipy", "pandas"} <= set(versions)
        and all(_label(v) for v in versions.values()),
        "invalid package versions",
    )


def _folds(document: dict[str, Any], manifest: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    _require(set(document) == {"configuration", "split_seed", "folds"}, "invalid split document")
    _require(document["configuration"] == manifest["configuration"], "split configuration mismatch")
    _require(
        all(
            type(document["configuration"][key]) is type(value)
            for key, value in manifest["configuration"].items()
        ),
        "split configuration type mismatch",
    )
    _require(
        _integer(document["split_seed"]) and document["split_seed"] == manifest["seeds"]["split"],
        "split seed mismatch",
    )
    folds = document["folds"]
    _require(isinstance(folds, list) and len(folds) == 5, "expected five folds")
    all_test, all_groups, split_ids = set(), set(), set()
    for fold in folds:
        _require(
            isinstance(fold, dict)
            and set(fold)
            == set("split_id train_ids test_ids test_groups status failure_reason pit_seed".split()),
            "invalid fold fields",
        )
        split = fold["split_id"]
        _require(_label(split) and split not in split_ids, "invalid or duplicate split ID")
        split_ids.add(split)
        for key in ("train_ids", "test_ids", "test_groups"):
            fold[key] = _labels(fold[key])
        _require(not set(fold["test_ids"]) & all_test, "test records overlap between folds")
        _require(not set(fold["test_groups"]) & all_groups, "test groups overlap between folds")
        all_test.update(fold["test_ids"])
        all_groups.update(fold["test_groups"])
        _require(
            _integer(fold["pit_seed"]) and fold["pit_seed"] == manifest["seeds"]["pit_by_fold"].get(split),
            "fold PIT seed mismatch",
        )
        BenchmarkFoldStatus(split, fold["status"], tuple(fold["test_ids"]), fold["failure_reason"])
    _require(split_ids == set(manifest["seeds"]["pit_by_fold"]), "PIT split identities mismatch")
    for fold in folds:
        _require(set(fold["train_ids"]) == all_test - set(fold["test_ids"]), "train/test membership mismatch")
    return tuple(sorted(folds, key=lambda f: f["split_id"]))


def _rows(files: Mapping[str, bytes], folds: tuple[dict[str, Any], ...]):
    rows = _tsv(files["row_status.tsv"], ("split_id", "record_id", "status", "reason"))
    by_key = {(row["split_id"], row["record_id"]): row for row in rows}
    _require(len(by_key) == len(rows), "duplicate row status")
    expected = {(f["split_id"], key) for f in folds for key in f["test_ids"]}
    _require(set(by_key) == expected, "row status does not cover test IDs exactly")
    statuses = []
    for fold in folds:
        scoreable = []
        for record_id in fold["test_ids"]:
            row = by_key[(fold["split_id"], record_id)]
            if row["status"] == "unavailable_denominator":
                _require(row["reason"] == "AN is zero", "invalid unavailable reason")
                continue
            scoreable.append(record_id)
            expected_status = "scored" if fold["status"] == "completed" else fold["status"]
            _require(
                row["status"] == expected_status and row["reason"] == (fold["failure_reason"] or ""),
                "row/fold status or reason mismatch",
            )
        statuses.append(
            BenchmarkFoldStatus(
                fold["split_id"],
                fold["status"],
                tuple(scoreable if fold["status"] == "completed" else fold["test_ids"]),
                fold["failure_reason"],
            )
        )
    return tuple(by_key[key] for key in sorted(by_key)), tuple(statuses)


def _predictions(files: Mapping[str, bytes], folds: tuple[dict[str, Any], ...]) -> pd.DataFrame:
    rows = _tsv(files["predictions.tsv"], PREDICTION_COLUMNS)
    groups = {f["split_id"]: set(f["test_groups"]) for f in folds}
    group_regions, variant_groups, group_variants = {}, {}, set()
    for row in rows:
        _require(all(_label(row[k]) for k in PREDICTION_COLUMNS[:6]), "invalid prediction label")
        _require(
            row["cohort_id"] in groups.get(row["split_id"], set()), "prediction group membership mismatch"
        )
        for key in ("observed_ac", "observed_an"):
            row[key] = _count(row[key])
        _require(
            0 <= row["observed_ac"] <= row["observed_an"] and row["observed_an"] > 0,
            "invalid scoreable AC/AN domain",
        )
        for key in PREDICTION_COLUMNS[8:]:
            if key.startswith("coverage_"):
                _require(row[key] in {"True", "False"}, "coverage must be Boolean")
                row[key] = row[key] == "True"
            else:
                row[key] = _number(row[key], log_score=key == "log_score")
        _require(
            group_regions.setdefault(row["cohort_id"], row["region_id"]) == row["region_id"],
            "group has inconsistent region",
        )
        _require(
            variant_groups.setdefault(row["variant_id"], row["variant_group"]) == row["variant_group"],
            "variant has inconsistent variant group",
        )
        key = (row["cohort_id"], row["variant_id"])
        _require(key not in group_variants, "duplicate group/variant prediction")
        group_variants.add(key)
    return (
        pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
        .sort_values(["split_id", "source_record_id"])
        .reset_index(drop=True)
    )


def _posteriors(files, manifest, folds, predictions, arrays, diagnostics):
    heterogeneity = diagnostics is not None
    columns = B0H_POSTERIOR_COLUMNS if heterogeneity else B0_POSTERIOR_COLUMNS
    rows = _tsv(files["posteriors.tsv"], columns)
    by_key = {}
    for row in rows:
        key = row["split_id"], row["variant_id"]
        _require(all(_label(v) for v in key) and key not in by_key, "invalid/duplicate posterior identity")
        for name in ("training_observation_count", "training_ac", "training_an"):
            row[name] = _count(row[name])
        _require(
            row["training_observation_count"] > 0
            and row["training_an"] > 0
            and row["training_ac"] <= row["training_an"],
            "invalid posterior training counts",
        )
        for name in columns[-2:]:
            row[name] = _number(row[name])
        by_key[key] = row
    if heterogeneity:
        expected = set()
        for fold in diagnostics["folds"]:
            if fold["posterior_status"] != "retained":
                continue
            prefix = fold["posterior_prefix"]
            for index, variant in enumerate(arrays[prefix + "__variant_ids"].tolist()):
                key = fold["split_id"], variant
                expected.add(key)
                _require(key in by_key, "missing posterior summary")
                row = by_key[key]
                for kind in ("mean", "rho"):
                    value = row[f"posterior_{kind}_mean"]
                    _require(
                        0 < value < 1
                        and value == float(arrays[prefix + f"__{kind}_draws"][:, :, index].mean()),
                        "posterior summary/draw mismatch",
                    )
        _require(set(by_key) == expected, "posterior identities mismatch")
        prediction_keys = set(zip(predictions.split_id, predictions.variant_id, strict=True))
        _require(prediction_keys <= expected, "prediction variant absent from retained posterior")
        by_split = {f["split_id"]: f for f in folds}
        for fold in diagnostics["folds"]:
            _require(
                fold["reason"] == by_split[fold["split_id"]]["failure_reason"],
                "diagnostic/split failure reason mismatch",
            )
    else:
        expected = set(zip(predictions.split_id, predictions.variant_id, strict=True))
        _require(set(by_key) == expected, "B0 posterior identities mismatch")
        for row in rows:
            _require(
                row["posterior_alpha"] == manifest["configuration"]["prior_alpha"] + row["training_ac"]
                and row["posterior_beta"]
                == manifest["configuration"]["prior_beta"] + (row["training_an"] - row["training_ac"]),
                "B0 posterior parameters mismatch",
            )


def decode_reference_publication(files: Mapping[str, bytes], *, heterogeneity: bool) -> ReferencePublication:
    """Validate one complete immutable wire publication, retaining valid failed folds."""
    try:
        expected = set(B0H_OUTPUT_FILENAMES if heterogeneity else B0_OUTPUT_FILENAMES) | {"manifest.json"}
        _require(
            set(files) == expected and all(isinstance(v, bytes) for v in files.values()),
            "publication file set or bytes mismatch",
        )
        documents = {key: _json(value) for key, value in files.items() if key.endswith(".json")}
        manifest = documents["manifest.json"]
        _validate_manifest(manifest, heterogeneity=heterogeneity)
        _require(
            manifest["output_files"] == {k: fingerprint(v) for k, v in files.items() if k != "manifest.json"},
            "publication fingerprints mismatch",
        )
        arrays = validate_b0h_publication(files) if heterogeneity else None
        folds = _folds(documents["splits.json"], manifest)
        row_status, statuses = _rows(files, folds)
        predictions = _predictions(files, folds)
        summary = summarize_benchmark(predictions, statuses, tuple(f["split_id"] for f in folds))
        summary.update(
            target=manifest["target"],
            evidence_role=manifest["configuration"]["evidence_role"],
            joint_prediction_supported=False,
            weighting_unit="source_population_group_not_independent_study",
            total_row_count=len(row_status),
            unavailable_row_count=sum(r["status"] == "unavailable_denominator" for r in row_status),
            failed_row_count=sum(r["status"] in {"failed", "infeasible"} for r in row_status),
        )
        stored = documents["summary.json"]
        metadata = (
            "comparison_complete",
            "split_counts",
            "scored_observation_count",
            "represented_cell_count",
            "represented_declared_cohort_cell_count",
            "zero_probability_count",
            "target",
            "evidence_role",
            "joint_prediction_supported",
            "weighting_unit",
            "total_row_count",
            "unavailable_row_count",
            "failed_row_count",
        )
        for key in metadata:
            _require(
                type(stored[key]) is type(summary[key]) and stored[key] == summary[key],
                f"stored summary {key} mismatch",
            )
        _require(
            all(_integer(value) for value in stored["split_counts"].values()),
            "stored split counts must be integers",
        )
        stored_statuses = {f["split_id"]: f for f in stored["fold_status"]}
        _require(len(stored_statuses) == len(stored["fold_status"]) == 5, "invalid stored fold statuses")
        for status in summary["fold_status"]:
            original = stored_statuses[status["split_id"]].copy()
            original["expected_test_ids"] = _labels(original["expected_test_ids"])
            _require(original == status, "stored summary fold status mismatch")
        _require(
            sorted(stored["failure_reasons"], key=lambda f: f["split_id"]) == summary["failure_reasons"],
            "stored summary failure reasons mismatch",
        )
        diagnostics = documents.get("fit_diagnostics.json")
        _posteriors(files, manifest, folds, predictions, arrays, diagnostics)
        return ReferencePublication(manifest, folds, row_status, predictions, statuses, summary, diagnostics)
    except (KeyError, TypeError, AttributeError, OverflowError, UnicodeError) as error:
        raise ValueError(f"malformed reference publication: {error}") from error

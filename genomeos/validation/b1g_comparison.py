"""Matched B1G benchmark comparison (design §§4–8, 12; issue #331).

Scientific objective
    Test whether B1G improves held-out HbS count prediction against both frozen B0 and B2 without
    changing the observations, geographic folds, support, or prediction semantics.
Acceptance evidence
    Every planned fold is complete; both comparisons use exactly the same held-out rows; balanced
    macro metrics, zero/positive strata, regions, calibration, and exhaustive outer-block intervals
    remain visible.
Engineering interface
    :func:`compare_b1g_benchmarks` validates immutable artifact identities and returns two ordinary
    paired-benchmark reports. It performs no fitting, file access, rendering, or serving inference.
Assumptions and refusals
    Observational evidence must use the preregistered hashes. Header, input, split, model, row, or
    fold-status drift is an error. Unreviewed dependency evidence and undefined stratum power leave
    promotion explicitly undecided.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.paired_benchmark import compare_paired_benchmarks
from genomeos.validation.spatial_gp_checkpoint import validate_checkpoint_header

OBSERVATIONS_SHA256 = "820d725fae9859a6cebca98296676e8c525b103f7033aa5237b9aaa00f79b331"
ASSIGNMENTS_SHA256 = "c922b240624c761f0752821d9e6986bb1479bbc97a0d9931da7db3a17ee20b20"
DEPENDENCIES_SHA256 = "fa7b4c093dc2f83a2ea3c7f0810b9130e65feac7c94dc80fb8475d03c2d3cf22"
FIT_CONFIG_SHA256 = "349df9dac9655dfe56c67b369093b97f36a74800076ecd797cc777d075c43ada"
B2_OBSERVATIONS_SHA256 = "466034e22015ce5f4e0b90067adb2232491b625591d50c8ac83d955565345b4b"

_CORE_SPLIT_FIELDS = (
    "split_id",
    "block_id",
    "buffer_km",
    "data_version",
    "input_fingerprint",
    "train_ids",
    "test_ids",
    "excluded_ids",
    "exclusion_reasons",
    "min_edge_separation_km",
)
_BASELINES = ("B0", "B2-current")
_STRONGEST_BASELINE = "B2-current"
_COVERAGE_LEVELS = (50, 80, 95)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty list")
    if any(not isinstance(record, Mapping) for record in value):
        raise ValueError(f"{label} records must be objects")
    return value


def _model_manifest(manifest: object, expected_model: str) -> Mapping[str, object]:
    record = _mapping(manifest, f"{expected_model} manifest")
    model = _mapping(record.get("model"), f"{expected_model} model")
    if model.get("model_id") != expected_model:
        raise ValueError(f"artifact is not the expected {expected_model} model")
    if record.get("publication_eligible") is not False:
        raise ValueError(f"{expected_model} evidence must remain nonpublication")
    return record


def _file_record(manifest: Mapping[str, object], name: str, model: str) -> Mapping[str, object]:
    inputs = _mapping(manifest.get("input_files"), f"{model} input_files")
    record = _mapping(inputs.get(name), f"{model} {name} input")
    digest = record.get("sha256")
    size = record.get("size_bytes")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{model} {name} input hash is invalid")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError(f"{model} {name} input size is invalid")
    return record


def _require_equal_input(
    left: Mapping[str, object],
    right: Mapping[str, object],
    name: str,
    left_model: str,
    right_model: str,
) -> None:
    if _file_record(left, name, left_model) != _file_record(right, name, right_model):
        raise ValueError(f"{left_model} and {right_model} {name} inputs differ")


def _require_hash(
    manifest: Mapping[str, object], name: str, model: str, expected: str
) -> None:
    if _file_record(manifest, name, model)["sha256"] != expected:
        raise ValueError(f"{model} does not use the frozen {name} input")


def _configuration_identity(manifest: Mapping[str, object], model: str) -> tuple[object, ...]:
    configuration = _mapping(manifest.get("configuration"), f"{model} configuration")
    return tuple(configuration.get(field) for field in ("buffer_km", "data_version", "seed"))


def _split_identity(record: Mapping[str, object], label: str) -> dict[str, object]:
    missing = [field for field in _CORE_SPLIT_FIELDS if field not in record]
    if missing:
        raise ValueError(f"{label} split is missing identity fields: {missing}")
    return {field: record[field] for field in _CORE_SPLIT_FIELDS}


def _verify_split_ledgers(
    header: Mapping[str, object],
    b0_manifest: Mapping[str, object],
    b2_manifest: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    candidate = tuple(
        _split_identity(record, "B1G")
        for record in _records(header.get("planned_splits"), "B1G planned_splits")
    )
    if len(candidate) != 5:
        raise ValueError("the frozen HbS comparison requires exactly five outer folds")
    for model, manifest in (("B0", b0_manifest), ("B2-current", b2_manifest)):
        baseline = tuple(
            _split_identity(record, model)
            for record in _records(manifest.get("splits"), f"{model} splits")
        )
        if baseline != candidate:
            raise ValueError(f"B1G and {model} split identity differs")
        if any(record.get("status") != "completed" for record in manifest["splits"]):
            raise ValueError(f"{model} comparison requires every planned fold to be completed")
    return candidate


def _candidate_statuses(
    manifest: Mapping[str, object], planned_splits: Sequence[Mapping[str, object]]
) -> tuple[BenchmarkFoldStatus, ...]:
    folds = _records(manifest.get("folds"), "B1G folds")
    if len(folds) != len(planned_splits):
        raise ValueError("B1G fold ledger does not cover every planned fold")
    statuses = []
    for ordinal, (fold, split) in enumerate(zip(folds, planned_splits, strict=True)):
        if fold.get("ordinal") != ordinal:
            raise ValueError("B1G fold ordinals must follow the frozen split order")
        status = _mapping(fold.get("status"), f"B1G fold {ordinal} status")
        expected_ids = status.get("expected_test_ids")
        if status.get("split_id") != split["split_id"] or expected_ids != split["test_ids"]:
            raise ValueError("B1G fold status contradicts the frozen split identity")
        states = status.get("status")
        failure_reason = status.get("failure_reason")
        statuses.append(
            BenchmarkFoldStatus(
                str(split["split_id"]),
                states,
                tuple(str(value) for value in expected_ids),
                failure_reason,
            )
        )
    if any(status.status != "completed" for status in statuses):
        raise ValueError("B1G comparison requires every planned fold to be completed")
    return tuple(statuses)


def _verify_identity(
    candidate_manifest: object,
    candidate_checkpoint_header: object,
    b0_manifest: object,
    b2_manifest: object,
) -> tuple[
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
    tuple[BenchmarkFoldStatus, ...],
]:
    candidate = _model_manifest(candidate_manifest, "B1G")
    b0 = _model_manifest(b0_manifest, "B0")
    b2 = _model_manifest(b2_manifest, "B2-current")
    header = validate_checkpoint_header(candidate_checkpoint_header)
    if header["model_id"] != "B1G":
        raise ValueError("checkpoint header is not B1G")
    for field in (
        "evidence_kind",
        "qualification",
        "configuration",
        "input_files",
        "code_revision",
    ):
        if candidate.get(field) != header[field]:
            raise ValueError(f"B1G manifest and checkpoint header differ at {field}")
    if candidate.get("checkpoint_header_sha256") != header["header_sha256"]:
        raise ValueError("B1G manifest checkpoint header hash differs")

    _require_equal_input(candidate, b0, "observations", "B1G", "B0")
    for name in ("assignments", "dependencies"):
        _require_equal_input(candidate, b0, name, "B1G", "B0")
        _require_equal_input(candidate, b2, name, "B1G", "B2-current")
    identities = {
        _configuration_identity(manifest, model)
        for model, manifest in (("B1G", candidate), ("B0", b0), ("B2-current", b2))
    }
    if len(identities) != 1:
        raise ValueError("B1G, B0, and B2 configuration identity differs")

    evidence_kinds = {candidate.get("evidence_kind"), b0.get("evidence_kind"), b2.get("evidence_kind")}
    if len(evidence_kinds) != 1:
        raise ValueError("B1G, B0, and B2 evidence kinds differ")
    if candidate.get("evidence_kind") == "observational_research":
        for manifest, model in ((candidate, "B1G"), (b0, "B0")):
            _require_hash(manifest, "observations", model, OBSERVATIONS_SHA256)
        _require_hash(b2, "observations", "B2-current", B2_OBSERVATIONS_SHA256)
        for manifest, model in ((candidate, "B1G"), (b0, "B0"), (b2, "B2-current")):
            _require_hash(manifest, "assignments", model, ASSIGNMENTS_SHA256)
            _require_hash(manifest, "dependencies", model, DEPENDENCIES_SHA256)
        _require_hash(candidate, "fit_config", "B1G", FIT_CONFIG_SHA256)

    planned_splits = _verify_split_ledgers(header, b0, b2)
    statuses = _candidate_statuses(candidate, planned_splits)
    return candidate, header, b0, b2, statuses


def _gate_evidence(comparison: Mapping[str, object]) -> dict[str, object]:
    differences = _mapping(
        comparison.get("balanced_macro_metric_differences"), "metric differences"
    )
    relative_mae = differences.get("relative_mae_improvement")
    mae_passed = (
        isinstance(relative_mae, (int, float))
        and not isinstance(relative_mae, bool)
        and relative_mae >= 0.05
    )
    coverage = {
        str(level): {
            "absolute_deviation_percentage_points": differences[
                f"candidate_coverage_{level}_absolute_deviation_percentage_points"
            ],
            "passed": differences[
                f"candidate_coverage_{level}_absolute_deviation_percentage_points"
            ]
            <= 3.0,
        }
        for level in _COVERAGE_LEVELS
    }
    interval = _mapping(
        comparison.get("paired_outer_block_log_score_interval"), "log-score interval"
    )
    numerical_interval_pass = (
        bool(interval.get("available"))
        and interval.get("lower") is not None
        and float(interval["lower"]) > 0.0
    )
    dependency_certified = interval.get("certified_dependency_aware") is True
    coverage_passed = all(record["passed"] for record in coverage.values())
    return {
        "balanced_macro_mae": {
            "threshold_relative_improvement": 0.05,
            "observed_relative_improvement": relative_mae,
            "passed": mae_passed,
        },
        "paired_log_score_interval": {
            "interval": dict(interval),
            "numerically_excludes_zero": numerical_interval_pass,
            "dependency_aware_certified": dependency_certified,
            "passed": numerical_interval_pass and dependency_certified,
        },
        "predictive_coverage": {
            "absolute_tolerance_percentage_points": 3.0,
            "levels": coverage,
            "passed": coverage_passed,
        },
        "all_primary_folds_complete": True,
        "matched_coverage": True,
        "stratum_noninferiority": {
            "status": "not_evaluated",
            "reason": "adequately_powered_prespecified_strata_are_not_defined",
            "maximum_relative_mae_degradation": 0.05,
        },
        "admission_evidence_complete": False,
    }


def compare_b1g_benchmarks(
    candidate_predictions: pd.DataFrame,
    b0_predictions: pd.DataFrame,
    b2_predictions: pd.DataFrame,
    *,
    candidate_manifest: Mapping[str, object],
    candidate_checkpoint_header: Mapping[str, object],
    b0_manifest: Mapping[str, object],
    b2_manifest: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, pd.DataFrame]]:
    """Validate frozen identities and compare B1G with both required baselines."""
    candidate, header, b0, b2, statuses = _verify_identity(
        candidate_manifest,
        candidate_checkpoint_header,
        b0_manifest,
        b2_manifest,
    )
    split_ids = tuple(status.split_id for status in statuses)
    comparisons: dict[str, object] = {}
    matched: dict[str, pd.DataFrame] = {}
    for model, predictions in (("B0", b0_predictions), ("B2-current", b2_predictions)):
        comparison, rows = compare_paired_benchmarks(
            candidate_predictions,
            predictions,
            statuses,
            split_ids,
        )
        comparisons[model] = comparison
        matched[model] = rows

    strongest = _mapping(comparisons[_STRONGEST_BASELINE], "B2-current comparison")
    report = {
        "schema_version": 1,
        "analysis_role": "prespecified_matched_development_comparison",
        "publication_eligible": False,
        "scientific_promotion_decision": "not_made",
        "models": {
            "candidate": "B1G",
            "baselines": list(_BASELINES),
            "strongest_predeclared_baseline": _STRONGEST_BASELINE,
        },
        "artifact_identity": {
            "checkpoint_header_sha256": header["header_sha256"],
            "candidate_code_revision": candidate["code_revision"],
            "candidate_configuration": candidate["configuration"],
            "shared_input_files": {
                name: candidate["input_files"][name]
                for name in ("observations", "assignments", "dependencies")
            },
            "baseline_models": {
                "B0": b0["model"],
                "B2-current": b2["model"],
            },
        },
        "qualification": candidate["qualification"],
        "comparisons": comparisons,
        "strongest_baseline_gate_evidence": _gate_evidence(strongest),
        "interpretation": {
            "status": "descriptive_development_evidence",
            "automatic_winner": None,
            "open_requirements": [
                "reviewed_dependency_evidence",
                "defined_and_adequately_powered_prespecified_strata",
                "independent_variant_and_external_confirmation",
            ],
        },
    }
    return report, matched

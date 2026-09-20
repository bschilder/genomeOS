"""Read-only B1/B0 artifact verification adapter (design §§4–8, 12; #307).

Hashes verify bytes, not truth. Replayed summaries and public semantic validation additionally
bind the retained evidence to the requested observations and shared frozen split ledger. No fit,
repair, checkpoint upgrade, scientific qualification or publication happens here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields
from pathlib import Path

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import (
    BenchmarkFoldStatus,
    inventory_observations,
    summarize_benchmark,
    validate_allele_observations,
)
from genomeos.validation.local_count_benchmark import LocalCountFoldResult, LocalCountFoldStatus
from genomeos.validation.local_count_evidence import validate_local_count_fold
from genomeos.validation.local_count_selection import LocalCountBenchmarkConfig
from genomeos.validation.splits import BenchmarkSplit

SUMMARY_RTOL = 1e-12
SUMMARY_ATOL = 1e-14
B0_OUTPUTS = {"fold_status.tsv", "inventory.json", "predictions.tsv", "summary.json"}
B1_OUTPUTS = B0_OUTPUTS | {"bandwidth_selection.tsv", "support.tsv"}
SPLIT_FIELDS = tuple(field.name for field in fields(BenchmarkSplit))


def file_record(path: Path) -> dict[str, object]:
    """Hash the bytes actually consumed, including their length."""
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def equivalent_summary(left: object, right: object) -> bool:
    """Compare replayed JSON with explicit TSV-roundtrip numerical tolerances."""
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(equivalent_summary(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            equivalent_summary(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, float) and isinstance(right, float):
        return bool(np.isclose(left, right, rtol=SUMMARY_RTOL, atol=SUMMARY_ATOL, equal_nan=False))
    return type(left) is type(right) and left == right


def _json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("artifact JSON must be an object")
    return value


def _table(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        sep="\t",
        keep_default_na=False,
        dtype={
            key: str
            for key in (
                "split_id",
                "block_id",
                "source_record_id",
                "variant_id",
                "region_id",
                "variant_group",
                "cohort_id",
            )
        },
    )
    for column in (
        "bandwidth_km",
        "nearest_edge_distance_km",
        "posterior_alpha",
        "posterior_beta",
        "posterior_mean",
        "selected_bandwidth_km",
        "mean_log_score",
        "log_score",
    ):
        if column in frame:
            frame[column] = pd.to_numeric(
                frame[column].replace({"": np.nan, "-Infinity": -np.inf}), errors="raise"
            )
    return frame


def _manifest(root: Path, model: str, role: str | None) -> tuple[dict, dict]:
    manifest = _json(root / "manifest.json")
    required_fields = {
        "schema_version",
        "model",
        "evidence_kind",
        "publication_eligible",
        "configuration",
        "configuration_sha256",
        "input_files",
        "inputs_sha256",
        "source_provenance",
        "splits",
        "split_manifest_sha256",
        "code_revision",
        "science_source_sha256",
        "package_versions",
        "output_files",
    }
    if not required_fields <= set(manifest):
        raise ValueError("artifact manifest is incomplete")
    expected_model = (
        {
            "model_id": "B0",
            "name": "per_variant_pooled_beta_posterior_binomial_count_model",
            "resident_calibrated": False,
            "survey_heterogeneity_model": False,
        }
        if model == "B0"
        else {
            "model_id": "B1-local-count",
            "name": "compact_triweight_spherical_weighted_count_power_posterior",
            "kernel": "compact_triweight",
            "distance": "great_circle_footprint_edge_km",
            "posterior_semantics": "weighted_count_generalized_bayes_power_posterior",
            "environmental_covariates": False,
            "source_specific_features": False,
        }
    )
    if manifest.get("model") != expected_model:
        raise ValueError("artifact model contract differs")
    required = B0_OUTPUTS if model == "B0" else B1_OUTPUTS
    if set(manifest.get("output_files", {})) != required:
        raise ValueError("artifact output inventory is incomplete or unexpected")
    for name in required:
        if file_record(root / name) != manifest["output_files"][name]:
            raise ValueError(f"artifact output hash/size mismatch: {name}")
    summary = _json(root / "summary.json")
    if manifest.get("model", {}).get("model_id") != model or summary.get("model_id") != model:
        raise ValueError("artifact model identity mismatch")
    for value in (manifest, summary):
        if (
            type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
            or value.get("publication_eligible") is not False
        ):
            raise ValueError("artifact must be schema-v1 nonpublication evidence")
        if value.get("evidence_kind") not in ("synthetic_fixture", "observational_research"):
            raise ValueError("artifact evidence kind is missing or invalid")
        if role is not None and value.get("analysis_role") != role:
            raise ValueError("artifact analysis role mismatch")
    if summary["evidence_kind"] != manifest["evidence_kind"]:
        raise ValueError("summary evidence kind differs")
    if set(manifest.get("input_files", {})) != {"observations", "assignments", "dependencies"}:
        raise ValueError("artifact input inventory is incomplete")
    for name, value in (
        ("configuration_sha256", "configuration"),
        ("inputs_sha256", "input_files"),
        ("split_manifest_sha256", "splits"),
    ):
        if manifest.get(name) != canonical_hash(manifest.get(value)):
            raise ValueError(f"artifact {value} identity hash mismatch")
    if role is not None:
        qualification = manifest.get("qualification", {})
        if qualification.get("assignment_review_status") not in (
            "reviewed",
            "algorithmic_development_unreviewed",
        ) or qualification.get("dependency_review_status") not in ("reviewed", "not_checked"):
            raise ValueError("B1 review states are missing or invalid")
        model_record = manifest["model"]
        if any(
            model_record.get(key) is not False
            for key in ("environmental_covariates", "source_specific_features")
        ):
            raise ValueError("B1 must remain source neutral without environmental covariates")
        if manifest.get("qualification", {}).get("scientific_promotion_decision") != "not_made":
            raise ValueError("B1 evidence has no promotion decision")
    return manifest, summary["benchmark"]


def _split(record: dict) -> BenchmarkSplit:
    values = {name: record[name] for name in SPLIT_FIELDS}
    for name in ("train_ids", "test_ids", "excluded_ids"):
        values[name] = tuple(values[name])
    values["exclusion_reasons"] = tuple((key, tuple(reasons)) for key, reasons in values["exclusion_reasons"])
    return BenchmarkSplit(**values)


def _validate_splits(manifest: dict, observation_ids: set[str]) -> None:
    records = manifest["splits"]
    if not records or len({row["split_id"] for row in records}) != len(records):
        raise ValueError("split identities must be nonempty and unique")
    test_ids = []
    for record in records:
        split = _split(record)
        groups = [split.train_ids, split.test_ids, split.excluded_ids]
        joined = [key for group in groups for key in group]
        if not split.test_ids or len(joined) != len(set(joined)) or set(joined) != observation_ids:
            raise ValueError("split membership must partition exact observation identities")
        test_ids.extend(split.test_ids)
        for name in ("buffer_km", "data_version"):
            if getattr(split, name) != manifest["configuration"][name]:
                raise ValueError("split configuration identity mismatch")
    if len(test_ids) != len(set(test_ids)) or set(test_ids) != observation_ids:
        raise ValueError("requested test identities must cover observations exactly once")


def _validate_b0(root: Path, manifest: dict, summary: dict, observations: pd.DataFrame) -> pd.DataFrame:
    predictions = _table(root / "predictions.tsv")
    statuses = tuple(
        BenchmarkFoldStatus(row["split_id"], row["status"], tuple(row["test_ids"]), row["failure_reason"])
        for row in manifest["splits"]
    )
    if any(status.status != "completed" for status in statuses):
        raise ValueError("matched B1 report requires a complete B0 comparator")
    replay = summarize_benchmark(predictions, statuses, tuple(s.split_id for s in statuses))
    if not equivalent_summary(replay, summary):
        raise ValueError("replayed B0 summary differs")
    by_id = observations.set_index("source_record_id")
    split_by_id = {key: split for split in manifest["splits"] for key in split["test_ids"]}
    if predictions["source_record_id"].duplicated().any() or set(predictions["source_record_id"]) != set(
        by_id.index
    ):
        raise ValueError("B0 predictions must cover requested observation keys exactly")
    for row in predictions.itertuples(index=False):
        expected = split_by_id[row.source_record_id]
        if row.split_id != expected["split_id"] or row.block_id != expected["block_id"]:
            raise ValueError("B0 prediction split identity mismatch")
        for field, observed in (
            ("variant_id", "variant_id"),
            ("cohort_id", "cohort_id"),
            ("observed_ac", "ac"),
            ("observed_an", "an"),
        ):
            if getattr(row, field) != by_id.loc[row.source_record_id, observed]:
                raise ValueError(f"B0 prediction {field} identity mismatch")
    ledger = _table(root / "fold_status.tsv")
    if len(ledger) != len(statuses) or ledger["split_id"].duplicated().any():
        raise ValueError("B0 status ledger coverage mismatch")
    for row in ledger.to_dict("records"):
        match = next((record for record in manifest["splits"] if record["split_id"] == row["split_id"]), None)
        if match is None or any(
            row[field] != match[field]
            for field in ("block_id", "status", "posterior_seed", "predictive_seed")
        ):
            raise ValueError("B0 status ledger identity mismatch")
        if (
            json.loads(row["expected_test_ids"]) != match["test_ids"]
            or (row["failure_reason"] or None) != match["failure_reason"]
        ):
            raise ValueError("B0 status ledger result mismatch")
    return predictions


def _validate_b1(
    root: Path, manifest: dict, summary: dict, observations: pd.DataFrame, assignments: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    support, predictions = _table(root / "support.tsv"), _table(root / "predictions.tsv")
    ledger, candidates = _table(root / "fold_status.tsv"), _table(root / "bandwidth_selection.tsv")
    split_ids = tuple(row["split_id"] for row in manifest["splits"])
    if len(ledger) != len(split_ids) or set(ledger["split_id"]) != set(split_ids):
        raise ValueError("B1 status ledger coverage mismatch")
    if not set(support["split_id"]) <= set(split_ids) or not set(predictions["split_id"]) <= set(split_ids):
        raise ValueError("B1 contains extra split keys")
    config_values = {
        field.name: manifest["configuration"][field.name] for field in fields(LocalCountBenchmarkConfig)
    }
    config_values["candidate_bandwidths_km"] = tuple(config_values["candidate_bandwidths_km"])
    model_config = LocalCountBenchmarkConfig(**config_values)
    statuses, requested, emitted = [], 0, 0
    for record in manifest["splits"]:
        split = _split(record)
        value = dict(record["result"])
        for field in ("expected_test_ids", "emitted_test_ids", "refused_test_ids"):
            value[field] = tuple(value[field])
        status = LocalCountFoldStatus(**value)
        retained = ledger.loc[ledger["split_id"] == split.split_id].iloc[0].to_dict()
        for field in ("expected_test_ids", "emitted_test_ids", "refused_test_ids"):
            retained[field] = tuple(json.loads(retained[field]))
        retained["failure_reason"] = retained["failure_reason"] or None
        if pd.isna(retained["selected_bandwidth_km"]):
            retained["selected_bandwidth_km"] = None
        if retained != asdict(status):
            raise ValueError("B1 fold status ledger differs from manifest")
        fold = LocalCountFoldResult(
            status,
            predictions.loc[predictions.split_id == split.split_id],
            support.loc[support.split_id == split.split_id],
            (),
        )
        validate_local_count_fold(fold, split, observations, assignments, config=model_config)
        statuses.append(
            BenchmarkFoldStatus(
                split.split_id,
                status.status,
                status.emitted_test_ids if status.status == "completed" else split.test_ids,
                status.failure_reason,
            )
        )
        requested += len(split.test_ids)
        emitted += len(status.emitted_test_ids)
    replay = {
        "comparison_complete": all(s.status == "completed" for s in statuses),
        "requested_observation_count": requested,
        "emitted_observation_count": emitted,
        "excluded_observation_count": requested - emitted,
        "excluded_fraction": (requested - emitted) / requested,
        "supported_only_benchmark": summarize_benchmark(predictions, statuses, split_ids),
    }
    if not equivalent_summary(replay, summary):
        raise ValueError("replayed B1 summary differs")
    config = manifest["configuration"]
    if candidates.duplicated(["split_id", "bandwidth_km"]).any() or not set(candidates.split_id) <= set(
        split_ids
    ):
        raise ValueError("candidate ledger has duplicate or extra identities")
    for record in manifest["splits"]:
        rows = candidates.loc[candidates.split_id == record["split_id"]]
        if record["train_ids"] and set(rows.bandwidth_km) != set(config["candidate_bandwidths_km"]):
            raise ValueError("candidate ledger is incomplete")
        for row in rows.itertuples(index=False):
            if (
                not 0 <= row.emitted_count <= row.requested_count
                or row.requested_count <= 0
                or not np.isclose(
                    row.emission_fraction,
                    row.emitted_count / row.requested_count,
                    rtol=SUMMARY_RTOL,
                    atol=SUMMARY_ATOL,
                )
            ):
                raise ValueError("candidate emission counts contradict fraction")
            eligible = (
                row.failed_inner_fold_count == 0
                and row.emitted_count > 0
                and row.emission_fraction >= config["minimum_inner_emission_fraction"]
                and not pd.isna(row.mean_log_score)
            )
            if row.eligible != eligible:
                raise ValueError("candidate eligibility contradicts retained evidence")
        selected = record["result"]["selected_bandwidth_km"]
        if selected is not None and not ((rows.bandwidth_km == selected) & rows.eligible).any():
            raise ValueError("selected bandwidth has no eligible candidate")
    return support, predictions


def read_local_count_comparison(observations_path: Path, primary: Path, sensitivity: Path, b0: Path) -> tuple:
    """Verify all required bytes and semantic identities before returning plotting evidence."""
    manifests, summaries = [], []
    for path, model, role in (
        (primary, "B1-local-count", "prespecified_primary"),
        (sensitivity, "B1-local-count", "posthoc_sensitivity"),
        (b0, "B0", None),
    ):
        manifest, summary = _manifest(path, model, role)
        manifests.append(manifest)
        summaries.append(summary)
    first = manifests[0]
    if any(
        m["input_files"] != first["input_files"] or m["evidence_kind"] != first["evidence_kind"]
        for m in manifests
    ):
        raise ValueError("comparison requires identical input records and evidence kinds")
    if file_record(observations_path) != first["input_files"]["observations"]:
        raise ValueError("observations hash/size differs from frozen input")
    observations = validate_allele_observations(
        pd.read_csv(
            observations_path,
            sep="\t",
            keep_default_na=False,
            dtype={
                key: str
                for key in (
                    "source_record_id",
                    "variant_id",
                    "population_id",
                    "cohort_id",
                    "rsid",
                    "ac",
                    "an",
                )
            },
        )
    )
    for manifest, path in zip(manifests, (primary, sensitivity, b0), strict=True):
        _validate_splits(manifest, set(observations.source_record_id))
        if not equivalent_summary(inventory_observations(observations), _json(path / "inventory.json")):
            raise ValueError("replayed observation inventory differs")
        for other, expected in zip(manifest["splits"], first["splits"], strict=True):
            if any(other[name] != expected[name] for name in SPLIT_FIELDS):
                raise ValueError("comparison frozen split identities differ")
        if any(
            manifest["configuration"][field] != first["configuration"][field]
            for field in ("buffer_km", "data_version", "seed")
        ):
            raise ValueError("comparison configuration identity differs")
    b0_predictions = _validate_b0(b0, manifests[2], summaries[2], observations)
    assignments = b0_predictions.loc[:, ["source_record_id", "block_id", "region_id", "variant_group"]]
    evidence = [
        _validate_b1(path, manifest, summary, observations, assignments)
        for path, manifest, summary in zip((primary, sensitivity), manifests[:2], summaries[:2], strict=True)
    ]
    support, predictions = evidence[1]
    if set(support.source_record_id) != set(observations.source_record_id):
        raise ValueError("coordinate coverage must equal all requested identities")
    support = support.merge(
        observations[["source_record_id", "lat", "lon", "ac", "an"]],
        on="source_record_id",
        how="left",
        validate="one_to_one",
    )
    primary_support = evidence[0][0].merge(
        observations[["source_record_id", "lat", "lon", "ac", "an"]],
        on="source_record_id",
        how="left",
        validate="one_to_one",
    )
    return manifests, summaries, support, predictions, b0_predictions, primary_support, evidence[0][1]

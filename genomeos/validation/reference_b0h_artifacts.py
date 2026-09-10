"""Pure B0H evidence serialization and reading (design §§5, 7–8, 12; integration §§4–7)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from genomeos.validation.reference_b0h_fold import B0HFoldResult

MODEL = "B0H_population_heterogeneity"
B0H_POSTERIOR_COLUMNS = (
    "split_id",
    "variant_id",
    "training_observation_count",
    "training_ac",
    "training_an",
    "posterior_mean_mean",
    "posterior_rho_mean",
)
B0H_OUTPUT_FILENAMES = (
    "splits.json",
    "row_status.tsv",
    "predictions.tsv",
    "posteriors.tsv",
    "summary.json",
    "fit_diagnostics.json",
    "posterior_draws.npz",
)
FOLD_KEYS = set("split_id status failure_phase reason posterior_status posterior_prefix attempts".split())
ATTEMPT_KEYS = set(
    "attempt seed draws tune chains target_accept status reason divergence_count diagnostics".split()
)
DIAGNOSTIC_KEYS = set("variant_id max_rhat min_bulk_ess min_tail_ess".split())
MANIFEST_KEYS = set(
    "schema_version target joint_prediction_supported limitations configuration dependency_qualification "
    "input_files seeds git science_source_sha256 package_versions output_files model runtime".split()
)
CONFIGURATION_KEYS = set(
    "source_release cohort_stage count_kind evidence_role prior_alpha prior_beta folds seed model "
    "rho_prior_alpha rho_prior_beta draws tune chains target_accept cdf_backend".split()
)


def json_bytes(value: object) -> bytes:
    text = json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def fingerprint(data: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _integer(value, minimum=0) -> bool:
    return type(value) is int and value >= minimum


def _finite(value) -> bool:
    return type(value) in (int, float) and isfinite(value)


def _hex(value, length) -> bool:
    return (
        isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)
    )


def _object(value, keys, name):
    _require(isinstance(value, dict) and set(value) == keys, f"invalid {name} fields")


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON object key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def _validate_diagnostics(document, manifest):
    _object(document, {"schema_version", "model", "folds"}, "diagnostics")
    _require(
        type(document["schema_version"]) is int
        and document["schema_version"] == 1
        and document["model"] == MODEL,
        "invalid diagnostics schema/model",
    )
    folds = document["folds"]
    _require(isinstance(folds, list) and len(folds) == 5, "expected five diagnostic folds")
    split_ids = [fold["split_id"] for fold in folds]
    _require(
        all(_text(item) for item in split_ids) and len(set(split_ids)) == 5,
        "invalid diagnostic split identities",
    )
    _require(set(manifest["seeds"]["fit_by_fold"]) == set(split_ids), "fit seed split mismatch")
    _require(set(manifest["seeds"]["pit_by_fold"]) == set(split_ids), "PIT seed split mismatch")
    config = manifest["configuration"]
    for index, fold in enumerate(folds):
        _object(fold, FOLD_KEYS, "fold")
        _require(fold["status"] in {"completed", "infeasible", "failed"}, "invalid fold state")
        completed = fold["status"] == "completed"
        _require(
            (fold["reason"] is None and fold["failure_phase"] is None)
            if completed
            else (
                _text(fold["reason"])
                and fold["failure_phase"] in {"preflight", "fit", "prediction", "scoring"}
            ),
            "invalid fold failure",
        )
        attempts = fold["attempts"]
        _require(isinstance(attempts, list) and len(attempts) == 2, "expected two attempt slots")
        seeds = manifest["seeds"]["fit_by_fold"][fold["split_id"]]
        _object(seeds, {"initial", "retry"}, "fit seeds")
        for number, attempt in enumerate(attempts):
            _object(attempt, ATTEMPT_KEYS, "attempt")
            label = ("initial", "retry")[number]
            _require(
                attempt["attempt"] == label and _integer(attempt["seed"]) and attempt["seed"] == seeds[label],
                "attempt seed/name mismatch",
            )
            for name in ("draws", "tune"):
                _require(
                    _integer(attempt[name], 1) and attempt[name] == config["draws"] * (number + 1)
                    if name == "draws"
                    else _integer(attempt[name], 1) and attempt[name] == config["tune"] * (number + 1),
                    "attempt budget mismatch",
                )
            _require(
                _integer(attempt["chains"], 4) and attempt["chains"] == config["chains"],
                "attempt chains mismatch",
            )
            _require(
                _finite(attempt["target_accept"])
                and 0 < attempt["target_accept"] < 1
                and attempt["target_accept"] == config["target_accept"],
                "attempt target mismatch",
            )
            status = attempt["status"]
            _require(
                status in {"not_attempted", "accepted", "convergence_failed", "infeasible", "failed"},
                "invalid attempt state",
            )
            diagnostics = attempt["diagnostics"]
            _require(isinstance(diagnostics, list), "diagnostics must be a list")
            ids = []
            for diagnostic in diagnostics:
                _object(diagnostic, DIAGNOSTIC_KEYS, "variant diagnostic")
                _require(_text(diagnostic["variant_id"]), "invalid variant identity")
                ids.append(diagnostic["variant_id"])
                _require(
                    all(_finite(diagnostic[key]) for key in DIAGNOSTIC_KEYS - {"variant_id"}),
                    "nonfinite variant diagnostic",
                )
                if status == "accepted":
                    _require(
                        diagnostic["max_rhat"] <= 1.05
                        and diagnostic["min_bulk_ess"] >= 200
                        and diagnostic["min_tail_ess"] >= 200,
                        "accepted diagnostics fail gates",
                    )
            _require(ids == sorted(set(ids)), "diagnostic identities must be unique and sorted")
            divergence = attempt["divergence_count"]
            _require(divergence is None or _integer(divergence), "invalid divergence count")
            if status == "accepted":
                _require(
                    attempt["reason"] is None and divergence == 0 and bool(ids), "invalid accepted evidence"
                )
            else:
                _require(_text(attempt["reason"]), "nonaccepted attempt needs reason")
                if status != "convergence_failed":
                    _require(divergence is None and not ids, "fabricated unavailable diagnostics")
        initial, retry = attempts
        if initial["status"] != "convergence_failed":
            expected = {"accepted": "initial_accepted", "not_attempted": "initial_not_attempted"}.get(
                initial["status"], "initial_not_retryable"
            )
            _require(
                retry["status"] == "not_attempted" and retry["reason"] == expected,
                "retry must follow typed initial convergence failure only",
            )
        else:
            _require(retry["status"] != "not_attempted", "missing admitted retry")
        if initial["status"] == "not_attempted":
            _require(
                initial["reason"] == "fold_preflight_infeasible" and fold["failure_phase"] == "preflight",
                "invalid unused initial attempt",
            )
        accepted = [item for item in attempts if item["status"] == "accepted"]
        _require(len(accepted) <= 1, "multiple accepted attempts")
        retained = bool(accepted)
        _require(
            fold["posterior_status"] == ("retained" if retained else "not_available"),
            "posterior status mismatch",
        )
        _require(
            fold["posterior_prefix"] == (f"fold_{index:04d}" if retained else None),
            "posterior prefix mismatch",
        )
        _require(not completed or retained, "completed fold requires accepted fit")
        _require(
            not retained or completed or fold["failure_phase"] in {"prediction", "scoring"},
            "accepted fit has inconsistent failure phase",
        )
    return folds


def _npz(arrays):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for key in sorted(arrays):
            payload = io.BytesIO()
            np.lib.format.write_array(payload, arrays[key], version=(1, 0), allow_pickle=False)
            item = zipfile.ZipInfo(key + ".npy", date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o600 << 16
            item.internal_attr = item.flag_bits = 0
            item.create_version = item.extract_version = 20
            item.comment = item.extra = b""
            archive.writestr(item, payload.getvalue(), compress_type=zipfile.ZIP_STORED)
    return buffer.getvalue()


def encode_b0h(folds: Sequence[tuple[str, B0HFoldResult]]) -> tuple[bytes, bytes, pd.DataFrame]:
    """Serialize five planned results; accepted fits survive later fold failure."""
    _require(len(folds) == 5, "expected five folds")
    split_ids = [split for split, result in folds]
    _require(
        all(_text(split) for split in split_ids) and len(set(split_ids)) == 5, "invalid split identities"
    )
    records, rows, arrays = [], [], {}
    for index, (split_id, result) in enumerate(folds):
        fit = result.fit
        prefix = f"fold_{index:04d}" if fit is not None else None
        attempts = [
            {
                "attempt": attempt.attempt,
                "seed": attempt.config.seed,
                "draws": attempt.config.draws,
                "tune": attempt.config.tune,
                "chains": attempt.config.chains,
                "target_accept": attempt.config.target_accept,
                "status": attempt.status,
                "reason": attempt.reason,
                "divergence_count": attempt.divergence_count,
                "diagnostics": [asdict(item) for item in attempt.diagnostics],
            }
            for attempt in result.attempts
        ]
        records.append(
            {
                "split_id": split_id,
                "status": result.status,
                "failure_phase": result.failure_phase,
                "reason": result.reason,
                "posterior_status": "retained" if fit is not None else "not_available",
                "posterior_prefix": prefix,
                "attempts": attempts,
            }
        )
        if fit is None:
            continue
        length = max(map(len, fit.variant_ids))
        ids = np.asarray(fit.variant_ids, dtype=f"<U{length}")
        _require(tuple(ids.tolist()) == fit.variant_ids, "variant IDs must round-trip losslessly")
        arrays[prefix + "__variant_ids"] = ids
        for name in ("mean_draws", "rho_draws"):
            arrays[prefix + "__" + name] = np.ascontiguousarray(getattr(fit, name), dtype="<f8")
        for position, counts in enumerate(fit.training_counts):
            rows.append(
                {
                    "split_id": split_id,
                    **asdict(counts),
                    "posterior_mean_mean": float(fit.mean_draws[:, :, position].mean()),
                    "posterior_rho_mean": float(fit.rho_draws[:, :, position].mean()),
                }
            )
    frame = (
        pd.DataFrame.from_records(rows, columns=B0H_POSTERIOR_COLUMNS)
        .sort_values(["split_id", "variant_id"])
        .reset_index(drop=True)
    )
    document = {"schema_version": 1, "model": MODEL, "folds": records}
    config = folds[0][1].attempts[0].config
    _validate_diagnostics(
        document,
        {
            "configuration": asdict(config),
            "seeds": {
                "fit_by_fold": {
                    split: {attempt.attempt: attempt.config.seed for attempt in result.attempts}
                    for split, result in folds
                },
                "pit_by_fold": dict.fromkeys(split_ids),
            },
        },
    )
    return json_bytes(document), _npz(arrays), frame


def validate_b0h_publication(files: Mapping[str, bytes]) -> dict[str, np.ndarray]:
    """Refuse missing/altered publication bytes and malformed posterior companions."""
    _require(set(files) == set(B0H_OUTPUT_FILENAMES) | {"manifest.json"}, "publication file set mismatch")
    manifest = _json(files["manifest.json"])
    _object(manifest, MANIFEST_KEYS, "manifest")
    _require(
        type(manifest["schema_version"]) is int
        and manifest["schema_version"] == 2
        and manifest["model"] == MODEL,
        "invalid manifest schema/model",
    )
    _require(
        manifest["target"] == "reference_panel_within_resource"
        and manifest["joint_prediction_supported"] is False,
        "invalid comparison target",
    )
    configuration = manifest["configuration"]
    _object(configuration, CONFIGURATION_KEYS, "configuration")
    _require(
        all(_text(configuration[name]) for name in ("source_release", "cohort_stage")),
        "invalid source qualification",
    )
    _require(
        configuration["count_kind"] in {"called", "quality"}
        and configuration["evidence_role"] in {"synthetic", "development"}
        and configuration["cdf_backend"] in {"scipy", "cupy"},
        "invalid configuration labels",
    )
    for name in ("prior_alpha", "prior_beta", "rho_prior_alpha", "rho_prior_beta"):
        _require(_finite(configuration[name]) and configuration[name] > 0, "invalid prior shape")
    _require(
        _integer(configuration["seed"])
        and _integer(configuration["draws"], 1)
        and _integer(configuration["tune"], 1)
        and _integer(configuration["chains"], 4),
        "invalid sampler configuration",
    )
    _require(
        _finite(configuration["target_accept"]) and 0 < configuration["target_accept"] < 1,
        "invalid target acceptance",
    )
    _require(
        configuration["model"] == MODEL and _integer(configuration["folds"]) and configuration["folds"] == 5,
        "invalid model configuration",
    )
    _require(_text(manifest["dependency_qualification"]), "invalid dependency qualification")
    _require(
        isinstance(manifest["limitations"], list)
        and bool(manifest["limitations"])
        and all(_text(item) for item in manifest["limitations"]),
        "invalid limitations",
    )
    _object(manifest["input_files"], {"counts", "dependencies"}, "input fingerprints")
    for value in manifest["input_files"].values():
        _object(value, {"sha256", "size_bytes"}, "input fingerprint")
        _require(_hex(value["sha256"], 64) and _integer(value["size_bytes"]), "invalid input fingerprint")
    _object(manifest["git"], {"head", "dirty"}, "git provenance")
    _require(
        _hex(manifest["git"]["head"], 40) and type(manifest["git"]["dirty"]) is bool, "invalid Git provenance"
    )
    sources = manifest["science_source_sha256"]
    _require(isinstance(sources, dict) and bool(sources), "missing source fingerprints")
    for name, digest in sources.items():
        _require(
            _text(name) and not name.startswith("/") and ".." not in name.split("/") and _hex(digest, 64),
            "invalid source fingerprint",
        )
    versions = manifest["package_versions"]
    required = {"numpy", "scipy", "pandas", "pymc", "pytensor", "arviz", "xarray", "numpyro", "jax", "jaxlib"}
    if configuration["cdf_backend"] == "cupy":
        required.add("cupy")
    _require(
        isinstance(versions, dict)
        and required <= set(versions)
        and all(_text(value) for value in versions.values()),
        "missing required distribution provenance",
    )
    _object(manifest["seeds"], {"root", "split", "pit_by_fold", "fit_by_fold"}, "seeds")
    _require(
        manifest["seeds"]["root"] == configuration["seed"] and _integer(manifest["seeds"]["split"]),
        "invalid manifest seeds",
    )
    _require(all(_integer(seed) for seed in manifest["seeds"]["pit_by_fold"].values()), "invalid PIT seed")
    _object(manifest["runtime"], {"python_version", "jax_backend", "cdf_backend"}, "runtime")
    for value in manifest["runtime"].values():
        _object(value, {"status", "value", "reason"}, "runtime observation")
        _require(
            (value["status"] == "available" and _text(value["value"]) and value["reason"] is None)
            or (value["status"] == "unavailable" and value["value"] is None and _text(value["reason"])),
            "invalid runtime observation",
        )
    _require(
        manifest["output_files"] == {name: fingerprint(files[name]) for name in B0H_OUTPUT_FILENAMES},
        "publication fingerprints mismatch",
    )
    folds = _validate_diagnostics(_json(files["fit_diagnostics.json"]), manifest)
    splits = _json(files["splits.json"])["folds"]
    _require(
        [(fold["split_id"], fold["status"]) for fold in splits]
        == [(fold["split_id"], fold["status"]) for fold in folds],
        "split ledger mismatch",
    )
    complete = _json(files["summary.json"])["comparison_complete"]
    _require(
        type(complete) is bool and complete == all(fold["status"] == "completed" for fold in folds),
        "comparison completion mismatch",
    )
    retained = [fold for fold in folds if fold["posterior_status"] == "retained"]
    expected = {
        fold["posterior_prefix"] + "__" + suffix
        for fold in retained
        for suffix in ("mean_draws", "rho_draws", "variant_ids")
    }
    data = files["posterior_draws.npz"]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            _require(len(names) == len(set(names)), "duplicate archive member")
            _require(set(names) == {key + ".npy" for key in expected}, "archive member set mismatch")
        with np.load(io.BytesIO(data), allow_pickle=False) as archive:
            _require(set(archive.files) == expected, "NPZ companion mismatch")
            arrays = {key: archive[key] for key in sorted(expected)}
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("invalid posterior archive") from error
    for fold in retained:
        prefix = fold["posterior_prefix"]
        accepted = next(item for item in fold["attempts"] if item["status"] == "accepted")
        labels = tuple(item["variant_id"] for item in accepted["diagnostics"])
        ids = arrays[prefix + "__variant_ids"]
        _require(
            ids.shape == (len(labels),)
            and ids.dtype.str == f"<U{max(map(len, labels))}"
            and tuple(ids.tolist()) == labels,
            "posterior variant identity/dtype mismatch",
        )
        for suffix in ("mean_draws", "rho_draws"):
            array = arrays[prefix + "__" + suffix]
            _require(
                array.dtype.str == "<f8"
                and array.flags.c_contiguous
                and array.shape == (accepted["chains"], accepted["draws"], len(labels)),
                "posterior dtype/shape mismatch",
            )
            _require(
                bool(np.all(np.isfinite(array))) and bool(np.all((array > 0) & (array < 1))),
                "posterior outside finite open unit interval",
            )
    return arrays

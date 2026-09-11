#!/usr/bin/env python3
"""Publish local paired B0/B0H matrix reports (design §§5, 7–8, 12; Matrix CLI).

This adapter reads complete immutable publications and delegates all descriptive
science to the public paired comparison boundary. Missing directories remain
explicit unavailable evidence; present malformed publications are refused. It
does not fit, acquire, select, rank, or promote any result.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import genomeos.validation.benchmark as benchmark_module  # noqa: E402
import genomeos.validation.reference_b0h_artifacts as artifacts_module  # noqa: E402
import genomeos.validation.reference_comparison as comparison_module  # noqa: E402
import genomeos.validation.reference_comparison_inputs as inputs_module  # noqa: E402
from genomeos.validation.reference_b0h_artifacts import (  # noqa: E402
    B0H_OUTPUT_FILENAMES,
    fingerprint,
    json_bytes,
)
from genomeos.validation.reference_comparison import compare_reference_publications  # noqa: E402
from genomeos.validation.reference_comparison_inputs import (  # noqa: E402
    B0_OUTPUT_FILENAMES,
    decode_reference_publication,
)

COHORT_STAGES = ("technical_qc_4117", "paper_ancestry_exclusion_4094")
COUNT_KINDS = ("called", "quality")
SEEDS = (42, 43, 44)
RHO_PRIOR_BETAS = (9, 4)
MATRIX = tuple(itertools.product(COHORT_STAGES, COUNT_KINDS, SEEDS, RHO_PRIOR_BETAS))
PAIR_FIELDS = (
    "cohort_stage",
    "count_kind",
    "seed",
    "rho_prior_beta",
    "b0_directory",
    "b0h_directory",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _strict_json(data: bytes) -> dict[str, object]:
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
        _require(value not in (float("inf"), float("-inf")), "nonfinite JSON number")
        return value

    document = json.loads(
        data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_float=number
    )
    _require(isinstance(document, dict), "pair specification must be a JSON object")
    return document


def _identity(record: dict[str, object]) -> tuple[str, str, int, int]:
    stage, kind = record["cohort_stage"], record["count_kind"]
    seed, rho = record["seed"], record["rho_prior_beta"]
    _require(isinstance(stage, str) and stage in COHORT_STAGES, "invalid cohort_stage in matrix")
    _require(isinstance(kind, str) and kind in COUNT_KINDS, "invalid count_kind in matrix")
    _require(type(seed) is int and seed in SEEDS, "invalid seed in matrix")
    _require(type(rho) in (int, float) and rho in RHO_PRIOR_BETAS, "invalid rho_prior_beta in matrix")
    return stage, kind, seed, int(rho)


def _pair_records(document: dict[str, object]) -> dict[tuple[str, str, int, int], dict[str, object]]:
    _require(set(document) == {"schema_version", "pairs"}, "invalid pair specification fields")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1, "invalid schema")
    records = document["pairs"]
    _require(isinstance(records, list), "matrix pairs must be a list")
    by_identity = {}
    for value in records:
        _require(isinstance(value, dict) and set(value) == set(PAIR_FIELDS), "invalid matrix pair fields")
        identity = _identity(value)
        _require(identity not in by_identity, "duplicate matrix identity")
        for name in ("b0_directory", "b0h_directory"):
            _require(isinstance(value[name], str) and value[name].strip(), f"invalid {name}")
        by_identity[identity] = value
    expected = set(MATRIX)
    actual = set(by_identity)
    _require(actual == expected, f"matrix identities mismatch: missing={sorted(expected - actual)!r}")
    return by_identity


def _publication_files(directory: Path, *, heterogeneity: bool) -> dict[str, bytes] | None:
    if not directory.exists():
        return None
    _require(directory.is_dir(), f"publication path is not a directory: {directory}")
    expected = set(B0H_OUTPUT_FILENAMES if heterogeneity else B0_OUTPUT_FILENAMES) | {"manifest.json"}
    entries = tuple(directory.iterdir())
    _require(
        {entry.name for entry in entries} == expected and all(entry.is_file() for entry in entries),
        f"publication file set is incomplete or unexpected: {directory}",
    )
    return {name: (directory / name).read_bytes() for name in sorted(expected)}


def _bind_configuration(
    configuration: dict[str, object], identity: tuple[str, str, int, int], *, heterogeneity: bool
) -> None:
    stage, kind, seed, rho = identity
    expected = {"cohort_stage": stage, "count_kind": kind, "seed": seed}
    if heterogeneity:
        expected["rho_prior_beta"] = rho
    for field, value in expected.items():
        _require(
            configuration[field] == value,
            f"declared {field} does not match publication configuration",
        )


def _directory(base: Path, value: object) -> Path:
    return (base / str(value)).resolve()


def _source_hashes() -> dict[str, str]:
    modules = {
        "genomeos/validation/benchmark.py": benchmark_module,
        "genomeos/validation/reference_b0h_artifacts.py": artifacts_module,
        "genomeos/validation/reference_comparison.py": comparison_module,
        "genomeos/validation/reference_comparison_inputs.py": inputs_module,
    }
    result = {}
    for relative, module in modules.items():
        actual = Path(module.__file__).resolve()
        _require(actual == (ROOT / relative).resolve(), f"imported source {relative} is outside checkout")
        result[relative] = hashlib.sha256(actual.read_bytes()).hexdigest()
    relative = "scripts/compare_reference_counts.py"
    actual = Path(__file__).resolve()
    _require(actual == (ROOT / relative).resolve(), f"imported source {relative} is outside checkout")
    result[relative] = hashlib.sha256(actual.read_bytes()).hexdigest()
    return result


def _package_versions() -> dict[str, str]:
    result = {name: importlib.metadata.version(name) for name in ("numpy", "pandas")}
    _require(all(value.strip() for value in result.values()), "package versions must be nonempty")
    return result


def _not_available_reason(b0: object, b0h: object) -> str:
    if b0 is None and b0h is None:
        return "b0 and b0h publication directories are absent"
    return f"{'b0' if b0 is None else 'b0h'} publication directory is absent"


def _evaluate(
    specification_path: Path, records: dict[tuple[str, str, int, int], dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows, consumed = [], []
    base = specification_path.parent
    for identity in MATRIX:
        declaration = records[identity]
        b0_path = _directory(base, declaration["b0_directory"])
        b0h_path = _directory(base, declaration["b0h_directory"])
        b0 = _publication_files(b0_path, heterogeneity=False)
        b0h = _publication_files(b0h_path, heterogeneity=True)
        fingerprints = {}
        comparison = None
        if b0 is not None and b0h is not None:
            comparison = compare_reference_publications(b0, b0h)
            for side, heterogeneity in (("b0", False), ("b0h", True)):
                _bind_configuration(comparison["configurations"][side], identity, heterogeneity=heterogeneity)
            fingerprints = comparison["publication_fingerprints"]
        else:
            for side, files, heterogeneity in (("b0", b0, False), ("b0h", b0h, True)):
                if files is not None:
                    publication = decode_reference_publication(files, heterogeneity=heterogeneity)
                    _bind_configuration(
                        publication.manifest["configuration"], identity, heterogeneity=heterogeneity
                    )
                    fingerprints[side] = fingerprint(files["manifest.json"])
        stage, kind, seed, rho = identity
        row = {
            "cohort_stage": stage,
            "count_kind": kind,
            "seed": seed,
            "rho_prior_beta": rho,
            "b0_directory": declaration["b0_directory"],
            "b0h_directory": declaration["b0h_directory"],
        }
        if b0 is None or b0h is None:
            row.update(status="not_available", reason=_not_available_reason(b0, b0h), comparison=None)
        else:
            row.update(status="available", reason=None, comparison=comparison)
        rows.append(row)
        if fingerprints:
            consumed.append(
                {
                    **{key: row[key] for key in PAIR_FIELDS[:4]},
                    "publication_fingerprints": fingerprints,
                }
            )
    return rows, consumed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare the complete local B0/B0H reference matrix.")
    parser.add_argument("--pairs", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def run(args: argparse.Namespace) -> int:
    """Validate every matrix identity, then publish report and manifest last."""
    if args.out.exists():
        raise ValueError(f"output directory already exists: {args.out}")
    specification_bytes = args.pairs.read_bytes()
    records = _pair_records(_strict_json(specification_bytes))
    rows, consumed = _evaluate(args.pairs.resolve(), records)
    sources = _source_hashes()
    versions = _package_versions()
    available = sum(row["status"] == "available" for row in rows)
    complete = available == len(MATRIX) and all(row["comparison"]["comparison_complete"] for row in rows)
    report = {
        "schema_version": 1,
        "evidence_kind": "descriptive_paired_comparison_matrix",
        "publication_eligible": False,
        "matrix_complete": complete,
        "difference_direction": "B0H_minus_B0",
        "available_pair_count": available,
        "not_available_pair_count": len(MATRIX) - available,
        "limitations": [
            "Source populations and adjacent variants are dependent development evidence.",
            "No confidence interval, winner, promotion, geographic, resident, or joint-LD claim.",
            "Missing directories are unavailable evidence, not scientifically failed folds.",
        ],
        "pairs": rows,
    }
    report_bytes = json_bytes(report)
    manifest = {
        "schema_version": 1,
        "evidence_kind": "descriptive_paired_comparison_matrix",
        "matrix_complete": report["matrix_complete"],
        "input_specification": fingerprint(specification_bytes),
        "consumed_publications": consumed,
        "executed_source_sha256": sources,
        "package_versions": versions,
        "output_files": {"report.json": fingerprint(report_bytes)},
    }
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "report.json").write_bytes(report_bytes)
    (args.out / "manifest.json").write_bytes(json_bytes(manifest))
    return 0 if report["matrix_complete"] else 2


def main() -> int:
    parser = _parser()
    try:
        return run(parser.parse_args())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan and execute the synthetic spatial-activity campaign (design §§4–5, 7–8; #384).

``manifest`` reconstructs and freezes the complete experiment without fitting. ``run`` first
reconstructs that manifest byte-for-byte, then evaluates exactly one content-addressed task and
writes one exclusive terminal artifact. Real HbS counts are never fitted by this adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, fields
from math import isfinite
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from genomeos.surfaces.config import FitConfig  # noqa: E402
from genomeos.surfaces.spatial_activity_fit import (  # noqa: E402
    SpatialActivitySamplerConfig,
)
from genomeos.surfaces.spatial_activity_model import (  # noqa: E402
    SpatialActivityModelConfig,
)
from genomeos.validation.benchmark import validate_allele_observations  # noqa: E402
from genomeos.validation.spatial_activity_artifacts import (  # noqa: E402
    load_spatial_activity_task_results,
    read_spatial_activity_task_result,
    write_spatial_activity_task_result,
)
from genomeos.validation.spatial_activity_campaign import (  # noqa: E402
    SpatialActivityCampaignResult,
    finalize_spatial_activity_campaign,
)
from genomeos.validation.spatial_activity_plan import (  # noqa: E402
    SpatialActivityPreflightPlan,
    plan_spatial_activity_preflight,
)
from genomeos.validation.spatial_activity_simulation import (  # noqa: E402
    default_spatial_activity_scenarios,
)
from genomeos.validation.spatial_activity_tasks import (  # noqa: E402
    evaluate_spatial_activity_task,
    plan_spatial_activity_tasks,
)
from genomeos.validation.spatial_gp_benchmark import (  # noqa: E402
    plan_single_variant_gp_benchmark,
)

FORMAT = "spatial_activity_campaign_manifest"
VERSION = 1
ASSIGNMENT_COLUMNS = ("source_record_id", "block_id", "region_id", "variant_group")
DEPENDENCY_COLUMNS = ("source_record_id_a", "source_record_id_b")
OBSERVATION_LITERAL_COLUMNS = (
    "variant_id",
    "rsid",
    "population_id",
    "ac",
    "an",
    "source_record_id",
    "source",
    "assay",
    "date_lower",
    "date_upper",
    "sampling_design",
    "cohort_id",
    "ingest_version",
)
SCIENCE_SOURCE_PATHS = (
    "genomeos/surfaces/activity_likelihood.py",
    "genomeos/surfaces/convergence.py",
    "genomeos/surfaces/spatial_activity_fit.py",
    "genomeos/surfaces/spatial_activity_model.py",
    "genomeos/validation/benchmark.py",
    "genomeos/validation/nested_folds.py",
    "genomeos/validation/count_legacy.py",
    "genomeos/validation/predictive.py",
    "genomeos/validation/predictive_cupy.py",
    "genomeos/validation/spatial_activity_artifacts.py",
    "genomeos/validation/spatial_activity_assessment.py",
    "genomeos/validation/spatial_activity_campaign.py",
    "genomeos/validation/spatial_activity_codec.py",
    "genomeos/validation/spatial_activity_plan.py",
    "genomeos/validation/spatial_activity_preflight.py",
    "genomeos/validation/spatial_activity_runner.py",
    "genomeos/validation/spatial_activity_simulation.py",
    "genomeos/validation/spatial_activity_tasks.py",
    "genomeos/validation/spatial_gp_benchmark.py",
    "genomeos/validation/splits.py",
    "scripts/preflight_spatial_activity.py",
)


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive finite number") from error
    if not isfinite(result) or result <= 0.0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return result


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--baseline-fit-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--sampler-config", required=True, type=Path)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--buffer-km", required=True, type=_positive_float)
    parser.add_argument("--cdf-backend", required=True, choices=("scipy", "cupy"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the simulation-only spatial activity preflight."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest", help="freeze the complete campaign task ledger")
    _common(manifest)
    manifest.add_argument("--out", required=True, type=Path)
    worker = commands.add_parser("run", help="execute exactly one registered campaign task")
    _common(worker)
    worker.add_argument("--manifest", required=True, type=Path)
    worker.add_argument("--task-id", required=True)
    worker.add_argument("--results-dir", required=True, type=Path)
    shard = commands.add_parser(
        "run-shard", help="execute an ordered task subset in one resumable process"
    )
    _common(shard)
    shard.add_argument("--manifest", required=True, type=Path)
    shard.add_argument("--tasks", required=True, type=Path)
    shard.add_argument("--results-dir", required=True, type=Path)
    finalizer = commands.add_parser(
        "finalize", help="validate all task artifacts and apply the registered gate"
    )
    _common(finalizer)
    finalizer.add_argument("--manifest", required=True, type=Path)
    finalizer.add_argument("--results-dir", required=True, type=Path)
    finalizer.add_argument("--out", required=True, type=Path)
    return parser


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _file_record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"sha256": _sha256(data), "size_bytes": len(data)}


def _science_files() -> dict[str, dict[str, object]]:
    records = {}
    for relative in SCIENCE_SOURCE_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"campaign science source is unavailable: {relative}")
        records[relative] = _file_record(path)
    return records


def _code_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    if len(revision) != 40:
        raise ValueError("git revision is unavailable or malformed")
    return revision


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"configuration contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_config(path: Path, cls: type):
    raw = json.loads(path.read_text(), object_pairs_hook=_unique_object)
    names = tuple(field.name for field in fields(cls) if field.init)
    if not isinstance(raw, dict) or set(raw) != set(names):
        raise ValueError(f"{path.name} must contain exactly the {cls.__name__} fields")
    values = dict(raw)
    if "hsgp_m" in values and isinstance(values["hsgp_m"], list):
        values["hsgp_m"] = tuple(values["hsgp_m"])
    return cls(**values)


def _read_observations(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return validate_allele_observations(pd.read_parquet(path))
    if path.suffix not in {".tsv", ".txt"}:
        raise ValueError("observations must be a .tsv, .txt, or .parquet file")
    frame = pd.read_csv(
        path,
        sep="\t",
        dtype={column: str for column in OBSERVATION_LITERAL_COLUMNS},
        keep_default_na=False,
        na_filter=False,
    )
    return validate_allele_observations(frame)


def _read_auxiliary(path: Path, columns: tuple[str, ...], label: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
    if frame.columns.duplicated().any() or tuple(frame.columns) != columns:
        raise ValueError(f"{label} TSV columns must be exactly {list(columns)}")
    for column in columns:
        if not frame[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError(f"{label} {column} values must be nonempty literal strings")
    return frame


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "assignments": args.assignments,
        "baseline_fit_config": args.baseline_fit_config,
        "dependencies": args.dependencies,
        "model_config": args.model_config,
        "observations": args.observations,
        "sampler_config": args.sampler_config,
    }


def _build_plan(args: argparse.Namespace) -> tuple[SpatialActivityPreflightPlan, dict[str, object]]:
    if not isinstance(args.data_version, str) or not args.data_version.strip():
        raise ValueError("data_version must be a nonempty string")
    paths = _input_paths(args)
    input_files = {name: _file_record(path) for name, path in sorted(paths.items())}
    observations = _read_observations(args.observations)
    assignments = _read_auxiliary(args.assignments, ASSIGNMENT_COLUMNS, "assignments")
    dependencies = _read_auxiliary(args.dependencies, DEPENDENCY_COLUMNS, "dependencies")
    dependency_pairs = tuple(
        dependencies.loc[:, DEPENDENCY_COLUMNS].itertuples(index=False, name=None)
    )
    baseline_config = _read_config(args.baseline_fit_config, FitConfig)
    model_config = _read_config(args.model_config, SpatialActivityModelConfig)
    sampler_config = _read_config(args.sampler_config, SpatialActivitySamplerConfig)
    baseline = plan_single_variant_gp_benchmark(
        observations,
        assignments,
        dependency_pairs,
        buffer_km=args.buffer_km,
        data_version=args.data_version,
        config=baseline_config,
        seed=baseline_config.seed,
    )
    plan = plan_spatial_activity_preflight(
        baseline,
        dependencies=dependency_pairs,
        model_config=model_config,
        sampler_config=sampler_config,
        scenarios=default_spatial_activity_scenarios(),
    )
    return plan, input_files


def _plan_node(plan: SpatialActivityPreflightPlan) -> dict[str, object]:
    return {
        "baseline_fit_config": asdict(plan.baseline_plan.config),
        "baseline_seed": plan.baseline_plan.seed,
        "dependencies": [list(pair) for pair in plan.dependencies],
        "inner_plans": [asdict(inner) for inner in plan.inner_plans],
        "model_config": asdict(plan.model_config),
        "modes": list(plan.modes),
        "outer_splits": [asdict(split) for split in plan.outer_splits],
        "sampler_config": asdict(plan.sampler_config),
        "scenarios": [asdict(scenario) for scenario in plan.scenarios],
    }


def _manifest_document(
    plan: SpatialActivityPreflightPlan,
    input_files: dict[str, object],
    *,
    cdf_backend: str,
) -> dict[str, object]:
    tasks = plan_spatial_activity_tasks(plan)
    return {
        "cdf_backend": cdf_backend,
        "code_revision": _code_revision(),
        "evidence_kind": "synthetic_preflight",
        "format": FORMAT,
        "input_files": input_files,
        "plan": _plan_node(plan),
        "publication_eligible": False,
        "real_hbs_fit_permitted": False,
        "science_files": _science_files(),
        "task_count": len(tasks),
        "tasks": [asdict(task) for task in tasks],
        "version": VERSION,
    }


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as error:
        raise FileExistsError(f"refusing to overwrite existing output: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _verified_plan(
    args: argparse.Namespace,
) -> tuple[SpatialActivityPreflightPlan, dict[str, object]]:
    plan, input_files = _build_plan(args)
    document = _manifest_document(plan, input_files, cdf_backend=args.cdf_backend)
    try:
        retained = args.manifest.read_bytes()
    except OSError as error:
        raise ValueError(f"campaign manifest cannot be read: {args.manifest}") from error
    if retained != _canonical(document):
        raise ValueError("campaign manifest does not match reconstructed inputs, plan, or code")
    return plan, document


def _run_manifest(args: argparse.Namespace) -> int:
    plan, input_files = _build_plan(args)
    _write_exclusive(
        args.out,
        _canonical(_manifest_document(plan, input_files, cdf_backend=args.cdf_backend)),
    )
    return 0


def _run_task(args: argparse.Namespace) -> int:
    plan, _ = _verified_plan(args)
    tasks = {task.task_id: task for task in plan_spatial_activity_tasks(plan)}
    task = tasks.get(args.task_id)
    if task is None:
        raise ValueError("task_id is not present in the verified campaign manifest")
    result = evaluate_spatial_activity_task(plan, task, cdf_backend=args.cdf_backend)
    write_spatial_activity_task_result(args.results_dir, result)
    return 0 if result.result.status.status == "completed" else 2


def _read_task_ids(path: Path) -> tuple[str, ...]:
    try:
        task_ids = tuple(line.strip() for line in path.read_text().splitlines() if line.strip())
    except OSError as error:
        raise ValueError(f"task shard cannot be read: {path}") from error
    if not task_ids:
        raise ValueError("task shard must not be empty")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("task shard contains duplicate task identities")
    return task_ids


def _run_shard(args: argparse.Namespace) -> int:
    plan, _ = _verified_plan(args)
    task_ids = _read_task_ids(args.tasks)
    planned = {task.task_id: task for task in plan_spatial_activity_tasks(plan)}
    unknown = sorted(set(task_ids) - set(planned))
    if unknown:
        raise ValueError(f"task shard contains {len(unknown)} identities outside the manifest")
    terminal_failure = False
    for task_id in task_ids:
        task = planned[task_id]
        path = args.results_dir / f"{task_id}.json"
        if path.exists():
            result = read_spatial_activity_task_result(path)
            if result.task != task:
                raise ValueError(f"retained task result contradicts planned task {task_id}")
        else:
            result = evaluate_spatial_activity_task(
                plan,
                task,
                cdf_backend=args.cdf_backend,
            )
            write_spatial_activity_task_result(args.results_dir, result)
        terminal_failure |= result.result.status.status != "completed"
    return 2 if terminal_failure else 0


def _campaign_document(
    campaign: SpatialActivityCampaignResult,
    *,
    manifest_bytes: bytes,
    task_artifacts: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "campaign_manifest_sha256": _sha256(manifest_bytes),
        "comparisons": [asdict(item) for item in campaign.comparisons],
        "completed_task_count": campaign.completed_task_count,
        "decision": asdict(campaign.decision),
        "evidence_kind": "synthetic_preflight",
        "format": "spatial_activity_campaign_result",
        "publication_eligible": False,
        "retried_task_count": campaign.retried_task_count,
        "task_artifacts": task_artifacts,
        "task_count": campaign.task_count,
        "version": VERSION,
    }


def _run_finalize(args: argparse.Namespace) -> int:
    plan, _ = _verified_plan(args)
    results = load_spatial_activity_task_results(args.results_dir)
    campaign = finalize_spatial_activity_campaign(plan, results)
    task_artifacts = {
        path.name: _file_record(path)
        for path in sorted(args.results_dir.iterdir())
        if path.is_file()
    }
    document = _campaign_document(
        campaign,
        manifest_bytes=args.manifest.read_bytes(),
        task_artifacts=task_artifacts,
    )
    _write_exclusive(args.out, _canonical(document))
    return 0 if campaign.decision.eligible_for_real_fit else 2


def run(args: argparse.Namespace) -> int:
    """Dispatch one explicit campaign operation."""
    if args.command == "manifest":
        return _run_manifest(args)
    if args.command == "run":
        return _run_task(args)
    if args.command == "run-shard":
        return _run_shard(args)
    if args.command == "finalize":
        return _run_finalize(args)
    raise ValueError(f"unsupported command: {args.command}")


def main() -> int:
    try:
        return run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

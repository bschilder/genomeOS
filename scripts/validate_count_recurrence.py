#!/usr/bin/env python3
"""Run an immutable, explicitly sourced synthetic numerical matrix (design §7, §8).

Requires the predeclared matrix, complement declaration and exact source hash manifest.
Every started law/control is journaled before execution, every outcome is flushed, and
failures produce nonzero exit after complete accounting. No automatic retry or fallback.
Interrupted runs retain their initial plan and journal even without a final receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from genomeos.validation import count_recurrence, predictive, predictive_cupy  # noqa: E402
from scripts import (  # noqa: E402
    count_recurrence_controls,
    count_recurrence_evaluate,
    count_recurrence_oracle,  # noqa: E402
)

SOURCE_PATHS = (
    "genomeos/validation/count_recurrence.py",
    "genomeos/validation/predictive.py",
    "genomeos/validation/predictive_cupy.py",
    "scripts/count_recurrence_oracle.py",
    "scripts/count_recurrence_evaluate.py",
    "scripts/count_recurrence_controls.py",
    "scripts/validate_count_recurrence.py",
    "scripts/plot_count_recurrence.py",
)
SUCCESS = {"pass", "expected_domain_refusal"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n")


def json_safe(value: Any) -> Any:
    """Nonfinite observations remain explicit strings, never a dropped failed record."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def checked_json(path: Path, expected: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(path) != expected:
        raise ValueError(f"hash mismatch: {path}")
    return json.loads(path.read_text())


def validate_matrix(matrix: dict) -> list[tuple[str, dict]]:
    groups = [(group, case) for group in ("small", "long") for case in matrix[group]]
    if len(matrix["small"]) != 480 or len(matrix["long"]) != 68:
        raise ValueError("matrix must retain 480 small and 68 long laws")
    if [sum(len(case["queried_ac"]) for case in matrix[group]) for group in ("small", "long")] != [
        10920,
        444,
    ]:
        raise ValueError("matrix support-point inventory changed")
    if Counter(case["expected_operation"] for case in matrix["small"]) != {
        "evaluate": 456,
        "refuse_numeric_domain": 24,
    }:
        raise ValueError("matrix expected refusal inventory changed")
    if len({case["case_id"] for _, case in groups}) != 548:
        raise ValueError("matrix case IDs must be unique")
    for group, case in groups:
        for field in ("mean", "concentration"):
            if float(case[field]).hex() != case[field + "_hex"]:
                raise ValueError(f"inconsistent binary64 input: {case['case_id']}")
        counts, n = case["queried_ac"], case["an"]
        if counts != sorted(set(counts)) or not all(isinstance(k, int) and 0 <= k <= n for k in counts):
            raise ValueError("invalid queried support")
        if group == "small" and counts != list(range(n + 1)):
            raise ValueError("small law omits support")
    return groups


def provenance(args: argparse.Namespace) -> tuple[dict, dict, dict]:
    if sys.flags.optimize:
        raise ValueError("validation requires Python assertions enabled (no -O)")
    if args.out.exists():
        raise ValueError(f"output directory already exists: {args.out}")
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_source_revision):
        raise ValueError("expected source revision must be a full Git SHA")
    manifest = json.loads(args.source_hashes.read_text())
    revision = manifest["revision"]
    if revision != args.expected_source_revision:
        raise ValueError("source manifest revision mismatch")
    if args.source_mode == "checkout":
        observed = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if observed != revision:
            raise ValueError("source revision mismatch")
    sources = manifest["files"]
    if set(sources) != set(SOURCE_PATHS):
        raise ValueError("source manifest must declare exactly SOURCE_PATHS")
    for relative, expected in sources.items():
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(ROOT / relative) != expected:
            raise ValueError(f"source hash mismatch: {relative}")
    origins = {}
    for module in (
        count_recurrence,
        predictive,
        predictive_cupy,
        count_recurrence_oracle,
        count_recurrence_evaluate,
        count_recurrence_controls,
    ):
        path = Path(inspect.getfile(module)).resolve()
        relative = path.relative_to(ROOT).as_posix()
        if relative not in sources:
            raise ValueError(f"undeclared imported source: {path}")
        origins[module.__name__] = str(path)
    matrix = checked_json(args.matrix, args.expected_matrix_sha256)
    declaration = checked_json(args.complement_declaration, args.expected_complement_sha256)
    if declaration["matrix_sha256"] != args.expected_matrix_sha256:
        raise ValueError("complement declaration does not bind this matrix")
    if declaration["absolute_log_tolerance"] != "5e-8":
        raise ValueError("complement tolerance changed")
    if declaration["spec_sha256"] != matrix["spec_sha256"]:
        raise ValueError("spec declaration mismatch")
    return (
        matrix,
        declaration,
        {
            "revision": revision,
            "source_sha256": sources,
            "revision_provenance": "git_observed"
            if args.source_mode == "checkout"
            else "supplied_snapshot_bound_to_source_manifest",
            "import_origins": origins,
        },
    )


def append_event(path: Path, event: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(json_safe(event), allow_nan=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def environment(backend: str) -> tuple[Any, dict]:
    versions = {}
    for name in ("numpy", "scipy", "pandas", "cupy-cuda12x", "cupy-cuda13x"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    details = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": versions,
    }
    if backend == "scipy":
        if "cupy" in sys.modules:
            raise RuntimeError("CPU run must not import CuPy")
        return np, details
    cp, _ = predictive_cupy._load_cupy()
    device = int(cp.cuda.runtime.getDevice())
    properties = cp.cuda.runtime.getDeviceProperties(device)
    cp.asarray([1.0]).sum().get()
    cp.cuda.get_current_stream().synchronize()
    name = properties["name"]
    details["device"] = {
        "id": device,
        "name": name.decode() if isinstance(name, bytes) else name,
        "runtime_version": cp.cuda.runtime.runtimeGetVersion(),
        "driver_version": cp.cuda.runtime.driverGetVersion(),
        "cupy_origin": cp.__file__,
    }
    return cp, details


def run(args: argparse.Namespace) -> int:
    matrix, declaration, source = provenance(args)
    cases = validate_matrix(matrix)
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / "matrix.json", matrix)
    # Copy exact declaration bytes; its digest binds the superseding operand decision.
    (args.out / "complement-declaration.json").write_bytes(args.complement_declaration.read_bytes())
    for relative in SOURCE_PATHS:
        target = args.out / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    header = {
        "evidence_kind": "synthetic_numerical_validation",
        "publication_eligible": False,
        "backend": args.backend,
        "command": sys.argv,
        "cwd": os.getcwd(),
        "matrix_sha256": args.expected_matrix_sha256,
        "complement_sha256": args.expected_complement_sha256,
        "complement_limitation": declaration["evidence_limitation"],
        "planned_laws": len(cases),
        "planned_points": 11364,
        "planned_controls": list(count_recurrence_controls.CONTROLS),
        **source,
    }
    # Preserve the exact matrix bytes as well as its parsed case inventory.
    (args.out / "matrix.json").write_bytes(args.matrix.read_bytes())
    write_json(args.out / "plan.json", header)
    journal = args.out / "events.jsonl"
    outcomes, controls = [], []
    fatal = None
    try:
        xp, details = environment(args.backend)
        append_event(journal, {"event": "environment", **details})
        for group, case in cases:
            append_event(journal, {"event": "started", "group": group, **case})
            try:
                result = count_recurrence_evaluate.evaluate_case(
                    case, group, args.backend, xp, lambda event: append_event(journal, event)
                )
            except Exception as error:
                result = {
                    "status": "unexpected_evaluation_failure",
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                    "points": [],
                }
            result = {"event": "outcome", "group": group, **case, **result}
            append_event(journal, result)
            outcomes.append(result)
        for name, operation in count_recurrence_controls.CONTROLS.items():
            append_event(journal, {"event": "control_started", "name": name})
            try:
                evidence = operation(
                    args.backend,
                    xp,
                    lambda evidence, name=name: append_event(
                        journal, {"event": "control_evidence", "name": name, "evidence": evidence}
                    ),
                )
                result = {
                    "status": "pass" if evidence.get("passed", True) else "control_failure",
                    "evidence": evidence,
                }
            except Exception as error:
                result = {
                    "status": "control_failure",
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                }
            result = {"event": "control_outcome", "name": name, **result}
            append_event(journal, result)
            controls.append(result)
    except BaseException as error:
        fatal = {
            "status": "incomplete_execution"
            if isinstance(error, (KeyboardInterrupt, SystemExit))
            else "backend_absence"
            if not outcomes
            else "incomplete_execution",
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        append_event(journal, {"event": "fatal", **fatal})
    summary = {
        "law_status_counts": dict(Counter(item["status"] for item in outcomes)),
        "completed_laws": len(outcomes),
        "incomplete_laws": len(cases) - len(outcomes),
        "evaluated_points": sum(len(item["points"]) for item in outcomes),
        "accounted_planned_points": sum(len(item["queried_ac"]) for item in outcomes),
        "completed_controls": len(controls),
        "fatal": fatal,
        "passed": fatal is None
        and len(outcomes) == len(cases)
        and len(controls) == len(count_recurrence_controls.CONTROLS)
        and all(item["status"] in SUCCESS for item in outcomes + controls),
    }
    files = {
        path.relative_to(args.out).as_posix(): sha256(path) for path in args.out.rglob("*") if path.is_file()
    }
    write_json(args.out / "receipt.json", {**header, "summary": summary, "file_sha256": files})
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--expected-matrix-sha256", required=True)
    parser.add_argument("--complement-declaration", type=Path, required=True)
    parser.add_argument("--expected-complement-sha256", required=True)
    parser.add_argument("--expected-source-revision", required=True)
    parser.add_argument("--source-hashes", type=Path, required=True)
    parser.add_argument("--source-mode", choices=("checkout", "snapshot"), default="checkout")
    parser.add_argument("--backend", choices=("scipy", "cupy"), required=True)
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())

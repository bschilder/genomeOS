"""Checks for the public CuGen pilot adapter and immutable artifact verifier (design §7)."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import shutil
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from genomeos.validation.ld_contract import LDVariant, validate_training_selection
from genomeos.validation.ld_reference import LDPair, VariantMoments

SOURCE_CALLS = np.array([[0, 0], [1, 1], [2, 2], [0, 2], [2, 0]], dtype=np.uint8)
VARIANTS = (
    LDVariant(30, "1-101-A-C", "1", 101, "A", "C"),
    LDVariant(10, "1-201-A-C", "1", 201, "A", "C"),
)
SELECTION = validate_training_selection(
    ("s0", "s1", "s2", "s3", "s4"),
    (4, 0, 2, 1),
    held_out_ids=("s3",),
    excluded_ids=(),
)
REVISION = "0123456789abcdef0123456789abcdef01234567"


def _comparison() -> object:
    spec = importlib.util.find_spec("genomeos.validation.ld_comparison")
    assert spec is not None, "public CuGen LD comparison module must exist"
    return importlib.import_module("genomeos.validation.ld_comparison")


def _pilot_modules() -> tuple[Any, Any]:
    pilot_spec = importlib.util.find_spec("genomeos.validation.cugen_pilot")
    artifact_spec = importlib.util.find_spec("genomeos.validation.cugen_artifact")
    assert pilot_spec is not None, "public CuGen pilot adapter module must exist"
    assert artifact_spec is not None, "public CuGen artifact verifier module must exist"
    return (
        importlib.import_module("genomeos.validation.cugen_pilot"),
        importlib.import_module("genomeos.validation.cugen_artifact"),
    )


def _encode_cugen(calls: np.ndarray) -> bytes:
    """Build canonical format-1 bytes independently from hard calls."""
    samples, variant_count = calls.shape
    means: list[float] = []
    sxx: list[float] = []
    mafs: list[float] = []
    for column in calls.T:
        called = column[column != 3].astype(np.float64)
        if not len(called):
            means.append(0.0)
            sxx.append(0.0)
            mafs.append(0.0)
        else:
            mean = float(called.mean())
            means.append(mean)
            sxx.append(float(np.sum((called - mean) ** 2)))
            mafs.append(min(mean / 2, 1 - mean / 2))
    bpv = (samples + 3) // 4
    packed = bytearray(variant_count * bpv)
    for variant_row, column in enumerate(calls.T):
        for sample_row, dosage in enumerate(column):
            packed[variant_row * bpv + sample_row // 4] |= int(dosage) << (6 - 2 * (sample_row % 4))
    header = bytearray(256)
    struct.pack_into(
        "<8sIIQQQQQQI",
        header,
        0,
        b"CUPGEN01",
        1,
        0,
        samples,
        variant_count,
        bpv,
        256,
        256 + 20 * variant_count,
        256 + 12 * variant_count,
        2 | int(bool(np.any(calls == 3))),
    )
    stats = b"".join(struct.pack(f"<{variant_count}f", *values) for values in (means, sxx, mafs))
    gidx = (30, 10)[:variant_count]
    return bytes(header) + stats + struct.pack(f"<{variant_count}q", *gidx) + bytes(packed)


def _pair_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [[1, 101, "1-101-A-C", 0.375, 1, 201, "1-201-A-C", 0.375, 4, 5 / 11, 25 / 121, 30, 10]],
        columns=(
            "CHR_A",
            "POS_A",
            "ID_A",
            "MAF_A",
            "CHR_B",
            "POS_B",
            "ID_B",
            "MAF_B",
            "N_OBS",
            "R",
            "R2",
            "gidx_a",
            "gidx_b",
        ),
    )


def _install_boundary_double(
    monkeypatch: pytest.MonkeyPatch,
    pilot: Any,
    *,
    gpu_result: pd.DataFrame | BaseException | None = None,
) -> None:
    allowlist = pilot._source_manifest()
    source_files = {item["path"]: item["sha256"] for item in allowlist["files"]}

    def validated_source(_root: Path) -> dict[str, object]:
        return {
            "repository": allowlist["repository"],
            "revision": allowlist["revision"],
            "files": source_files,
        }

    def subset(
        input_path: Path,
        output_path: Path,
        sample_indices: np.ndarray,
        *,
        chunk_size: int,
        verbose: bool,
        use_pinned: bool,
    ) -> float:
        if input_path.name != "source.cugen" or chunk_size != 2 or verbose or use_pinned:
            raise AssertionError("adapter changed the explicit public subset contract")
        selected = SOURCE_CALLS[np.asarray(sample_indices, dtype=np.int64)]
        Path(output_path).write_bytes(_encode_cugen(selected))
        return 0.25

    def ld_matrix(path: Path, **kwargs: object) -> pd.DataFrame:
        expected = {
            "annotation",
            "window",
            "window_kb",
            "stats",
            "precision",
            "sign_reference",
            "missing",
            "min_obs",
            "maf_min",
            "min_r2",
            "output",
            "output_format",
            "tile_size",
            "max_pairs",
            "backend",
            "verbose",
        }
        if set(kwargs) != expected or Path(path).name != "training.cugen":
            raise AssertionError("adapter changed the explicit public LD contract")
        if (
            kwargs["stats"] != ("r", "r2")
            or kwargs["precision"] != "fp32"
            or kwargs["sign_reference"] != "alt"
            or kwargs["missing"] != "pairwise"
            or kwargs["min_obs"] != 2
            or kwargs["maf_min"] != 0
            or kwargs["min_r2"] != 0
            or kwargs["output"] is not None
            or kwargs["output_format"] != "pairs"
            or kwargs["tile_size"] != 2
            or kwargs["max_pairs"] != 2016
            or kwargs["verbose"] is not False
            or kwargs["backend"] not in ("numpy", "gpu")
        ):
            raise AssertionError("adapter changed an explicit public LD argument")
        annotation = kwargs["annotation"]
        assert isinstance(annotation, pd.DataFrame)
        assert annotation.to_dict("list") == {
            "gidx": [30, 10],
            "CHR": ["1", "1"],
            "POS": [101, 201],
            "ID": ["1-101-A-C", "1-201-A-C"],
        }
        if kwargs["backend"] == "gpu" and isinstance(gpu_result, BaseException):
            raise gpu_result
        if kwargs["backend"] == "gpu" and isinstance(gpu_result, pd.DataFrame):
            return gpu_result.copy()
        return _pair_frame()

    monkeypatch.setattr(pilot, "_validate_cugen_source_root", validated_source)
    monkeypatch.setattr(
        pilot,
        "_load_cugen_api",
        lambda _root: (
            subset,
            ld_matrix,
            {
                "cugen/__init__.py": source_files["cugen/__init__.py"],
                "cugen/subset.py": source_files["cugen/subset.py"],
                "cugen/ld.py": source_files["cugen/ld.py"],
            },
        ),
    )


def _pilot_kwargs(tmp_path: Path) -> dict[str, object]:
    source = tmp_path / "input.cugen"
    source.write_bytes(_encode_cugen(SOURCE_CALLS))
    return {
        "source": source,
        "variants": VARIANTS,
        "selection": SELECTION,
        "genome_build": "GRCh38",
        "ploidy": "autosomal_diploid",
        "evidence_kind": "synthetic_fixture",
        "data_version": "fixture-v1",
        "cugen_root": tmp_path / "cugen-source",
        "window_variants": None,
        "window_bp": None,
        "chunk_size": 2,
        "tile_size": 2,
        "out": tmp_path / "artifact",
        "source_revision": REVISION,
    }


def _run_pilot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Any]:
    pilot, artifact = _pilot_modules()
    _install_boundary_double(monkeypatch, pilot)
    manifest = pilot.run_cugen_pilot(**_pilot_kwargs(tmp_path))
    return manifest, artifact


def test_reconcile_ld_output_accepts_exact_observed_pair() -> None:
    """Catch a comparator that cannot admit an exactly identified numeric result."""
    comparison = _comparison()
    variants = (
        LDVariant(30, "1-101-A-C", "1", 101, "A", "C"),
        LDVariant(10, "1-201-A-C", "1", 201, "A", "C"),
    )
    reference = (LDPair(0, 1, 30, 10, 4, (1, 0, 0, 0, 1, 0, 1, 0, 1), "observed", 5 / 11, 25 / 121),)
    moments = (
        VariantMoments(4, 5, 1.25, 2.75, 0.375),
        VariantMoments(4, 3, 0.75, 2.75, 0.375),
    )
    output = pd.DataFrame(
        [[1, 101, "1-101-A-C", 0.375, 1, 201, "1-201-A-C", 0.375, 4, 5 / 11, 25 / 121, 30, 10]],
        columns=(
            "CHR_A",
            "POS_A",
            "ID_A",
            "MAF_A",
            "CHR_B",
            "POS_B",
            "ID_B",
            "MAF_B",
            "N_OBS",
            "R",
            "R2",
            "gidx_a",
            "gidx_b",
        ),
    )

    assert comparison.reconcile_ld_output(reference, variants, moments, output) == {
        "requested_pairs": 1,
        "observed_pairs": 1,
        "invalid_pairs": 0,
        "maximum_absolute_r_error": 0.0,
        "maximum_absolute_r2_error": 0.0,
        "maximum_absolute_maf_error": 0.0,
        "passed": True,
    }


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "extra",
        "duplicate",
        "reversed",
        "chrom",
        "position",
        "id",
        "n_obs",
        "maf",
        "nan_r",
        "infinite_r2",
        "r_range",
        "r_budget",
        "r2_range",
        "r2_budget",
        "float_integer",
    ],
)
def test_reconcile_ld_output_refuses_identity_count_and_numeric_defects(defect: str) -> None:
    """Catch any permissive reconciliation of wrong pairs, metadata, counts, or precision."""
    comparison = _comparison()
    reference = (LDPair(0, 1, 30, 10, 4, (1, 0, 0, 0, 1, 0, 1, 0, 1), "observed", 5 / 11, 25 / 121),)
    moments = (
        VariantMoments(4, 5, 1.25, 2.75, 0.375),
        VariantMoments(4, 3, 0.75, 2.75, 0.375),
    )
    output = _pair_frame()
    if defect == "missing":
        output = output.iloc[:0]
    elif defect == "extra":
        extra = output.copy()
        extra.loc[0, ["gidx_a", "gidx_b"]] = [90, 80]
        output = pd.concat([output, extra], ignore_index=True)
    elif defect == "duplicate":
        output = pd.concat([output, output], ignore_index=True)
    elif defect == "reversed":
        pairs = (
            ("CHR_A", "CHR_B"),
            ("POS_A", "POS_B"),
            ("ID_A", "ID_B"),
            ("MAF_A", "MAF_B"),
            ("gidx_a", "gidx_b"),
        )
        for left, right in pairs:
            output.loc[0, [left, right]] = output.loc[0, [right, left]].to_numpy()
    elif defect == "chrom":
        output.loc[0, "CHR_A"] = 2
    elif defect == "position":
        output.loc[0, "POS_B"] = 202
    elif defect == "id":
        output.loc[0, "ID_A"] = "NA"
    elif defect == "n_obs":
        output.loc[0, "N_OBS"] = 3
    elif defect == "maf":
        output.loc[0, "MAF_A"] = 0.4
    elif defect == "nan_r":
        output.loc[0, "R"] = float("nan")
    elif defect == "infinite_r2":
        output.loc[0, "R2"] = float("inf")
    elif defect == "r_range":
        output.loc[0, "R"] = 1.01
    elif defect == "r_budget":
        output.loc[0, "R"] = 5 / 11 + 1.1e-5
    elif defect == "r2_range":
        output.loc[0, "R2"] = 1.01
    elif defect == "r2_budget":
        output.loc[0, "R2"] = 25 / 121 + 2.1e-5
    elif defect == "float_integer":
        output["N_OBS"] = pd.Series([4.0], dtype=object)

    with pytest.raises((TypeError, ValueError)):
        comparison.reconcile_ld_output(reference, VARIANTS, moments, output)


def test_reconcile_ld_output_refuses_emission_of_independently_invalid_pair() -> None:
    """Catch treating an omitted insufficient or zero-variance pair as observed LD evidence."""
    comparison = _comparison()
    invalid = (LDPair(0, 1, 30, 10, 1, (1, 0, 0, 0, 0, 0, 0, 0, 0), "insufficient_observations", None, None),)
    moments = (
        VariantMoments(1, 0, 0.0, 0.0, 0.0),
        VariantMoments(1, 0, 0.0, 0.0, 0.0),
    )

    with pytest.raises(ValueError, match="unexpected or invalid"):
        comparison.reconcile_ld_output(invalid, VARIANTS, moments, _pair_frame())


def test_run_and_verify_cugen_pilot_recompute_completed_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch completion before immutable members and independent science verification exist."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)

    assert manifest_path == tmp_path / "artifact" / "manifest.json"
    assert {path.name for path in manifest_path.parent.iterdir()} == {
        "source.cugen",
        "training.cugen",
        "reference.json",
        "cpu.tsv",
        "gpu.tsv",
        "validation.json",
        "runtime.json",
        "manifest.json",
    }
    verified = artifact.verify_cugen_pilot(manifest_path.parent)
    assert verified["status"] == "completed"
    assert verified["evidence_kind"] == "synthetic_fixture"
    assert verified["publication_eligible"] is False
    assert verified["joint_covariance_admitted"] is False
    assert verified["sources"]["genomeos"]["revision"] == REVISION
    assert verified["sources"]["genomeos"]["provenance"] == "supplied"
    assert verified["validation"]["cpu"]["passed"] is True
    assert verified["validation"]["gpu"]["passed"] is True


def _forbid_import(monkeypatch: pytest.MonkeyPatch, pilot: Any) -> None:
    monkeypatch.setattr(
        pilot,
        "_validate_cugen_source_root",
        lambda _root: {
            "repository": "https://github.com/bschilder/cugen",
            "revision": "b95adbaabef1ca5ff2795b9435e9bb7d6aebb9a1",
            "files": {"cugen/__init__.py": "0" * 64},
        },
    )

    def forbidden(_root: Path) -> object:
        raise AssertionError("invalid input reached CuGen import/device boundary")

    monkeypatch.setattr(pilot, "_load_cugen_api", forbidden)


@pytest.mark.parametrize("evidence_kind", ["", "real_data", None, True])
def test_adapter_requires_explicit_synthetic_evidence_before_cugen_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evidence_kind: object
) -> None:
    """Catch missing, defaulted, or non-synthetic provenance reaching the external library."""
    pilot, _ = _pilot_modules()
    _forbid_import(monkeypatch, pilot)
    arguments = _pilot_kwargs(tmp_path)
    arguments["evidence_kind"] = evidence_kind

    with pytest.raises(ValueError, match="synthetic_fixture"):
        pilot.run_cugen_pilot(**arguments)
    assert (tmp_path / "artifact" / "failure.json").is_file()
    assert not (tmp_path / "artifact" / "manifest.json").exists()


def test_adapter_does_not_default_a_missing_evidence_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch adding a default that manufactures the required caller provenance declaration."""
    pilot, _ = _pilot_modules()
    _forbid_import(monkeypatch, pilot)
    arguments = _pilot_kwargs(tmp_path)
    arguments.pop("evidence_kind")

    with pytest.raises(TypeError, match="evidence_kind"):
        pilot.run_cugen_pilot(**arguments)
    assert not (tmp_path / "artifact").exists()


@pytest.mark.parametrize("defect", ["selection", "layout", "chunk", "budget", "empty_pairs"])
def test_adapter_refuses_invalid_plan_before_cugen_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    """Catch selector, binary, allocation, or empty-work defects reaching device code."""
    pilot, _ = _pilot_modules()
    _forbid_import(monkeypatch, pilot)
    arguments = _pilot_kwargs(tmp_path)
    if defect == "selection":
        arguments["selection"] = type(SELECTION)(
            SELECTION.sample_ids,
            (0.0,),  # type: ignore[arg-type]
            ("s0",),
            ("s1", "s2", "s3", "s4"),
            (),
        )
    elif defect == "layout":
        source = Path(arguments["source"])
        source.write_bytes(b"BADMAGIC" + source.read_bytes()[8:])
    elif defect == "chunk":
        arguments["chunk_size"] = 65
    elif defect == "budget":

        def over_budget(**_kwargs: object) -> object:
            raise ValueError("estimated device workspace exceeds the pilot budget")

        monkeypatch.setattr(pilot, "estimate_ld_workspace", over_budget)
    else:
        arguments["variants"] = VARIANTS[:1]
        Path(arguments["source"]).write_bytes(_encode_cugen(SOURCE_CALLS[:, :1]))

    with pytest.raises((TypeError, ValueError)):
        pilot.run_cugen_pilot(**arguments)
    assert (tmp_path / "artifact" / "failure.json").is_file()
    assert not (tmp_path / "artifact" / "manifest.json").exists()


def test_adapter_refuses_overlarge_source_before_open_or_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch an unbounded source read before the fixed 67,072-byte admission check."""
    pilot, _ = _pilot_modules()
    _forbid_import(monkeypatch, pilot)
    arguments = _pilot_kwargs(tmp_path)
    source = Path(arguments["source"])
    source.write_bytes(b"x" * 67_073)
    original_open = Path.open

    def guarded_open(path: Path, *args: object, **kwargs: object) -> object:
        if path == source:
            raise AssertionError("overlarge source was opened before size refusal")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    with pytest.raises(ValueError, match="67072-byte"):
        pilot.run_cugen_pilot(**arguments)
    assert not (tmp_path / "artifact" / "manifest.json").exists()


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
def test_adapter_refuses_every_existing_output_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Catch overwriting or mingling an immutable output, including a symlink target."""
    pilot, _ = _pilot_modules()
    arguments = _pilot_kwargs(tmp_path)
    output = Path(arguments["out"])
    if kind == "directory":
        output.mkdir()
    elif kind == "file":
        output.write_text("keep", encoding="utf-8")
    else:
        target = tmp_path / "target"
        target.mkdir()
        output.symlink_to(target, target_is_directory=True)

    with pytest.raises(FileExistsError):
        pilot.run_cugen_pilot(**arguments)
    if kind == "file":
        assert output.read_text(encoding="utf-8") == "keep"


def test_adapter_refuses_source_output_collision(tmp_path: Path) -> None:
    """Catch replacing an input file by treating it as the exclusive output directory."""
    pilot, _ = _pilot_modules()
    arguments = _pilot_kwargs(tmp_path)
    arguments["out"] = arguments["source"]

    with pytest.raises(FileExistsError):
        pilot.run_cugen_pilot(**arguments)


def test_cugen_source_allowlist_matches_the_pinned_public_checkout() -> None:
    """Catch drift between the frozen allowlist and the explicitly qualified CuGen revision."""
    root = Path("/private/tmp/genomeos-cugen-precision.jfAGjg/source")
    if not root.is_dir():
        pytest.skip("controller-qualified pinned CuGen source is unavailable")
    pilot, _ = _pilot_modules()

    result = pilot._validate_cugen_source_root(root)

    assert result["revision"] == "b95adbaabef1ca5ff2795b9435e9bb7d6aebb9a1"
    assert len(result["files"]) == 37
    assert (
        result["files"]["cugen/ld.py"] == "1a692f73109699b69840079b0ce28010dcc8a041d5be1e0893c449f34259ecab"
    )


def test_validated_pinned_root_resolves_actual_public_function_sources() -> None:
    """Catch importing same-named public functions from an unqualified CuGen installation."""
    root = Path("/private/tmp/genomeos-cugen-precision.jfAGjg/source")
    if not root.is_dir():
        pytest.skip("controller-qualified pinned CuGen source is unavailable")
    pilot, _ = _pilot_modules()
    admitted = pilot._validate_cugen_source_root(root)

    subset, ld_matrix, imported = pilot._load_cugen_api(root)

    assert subset.__module__ == "cugen.subset"
    assert ld_matrix.__module__ == "cugen.ld"
    assert imported == {
        path: admitted["files"][path] for path in ("cugen/__init__.py", "cugen/subset.py", "cugen/ld.py")
    }


def test_source_hash_mismatch_refuses_before_cugen_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch a source label or package location being trusted instead of actual bytes."""
    pinned = Path("/private/tmp/genomeos-cugen-precision.jfAGjg/source")
    if not pinned.is_dir():
        pytest.skip("controller-qualified pinned CuGen source is unavailable")
    pilot, _ = _pilot_modules()
    copied = tmp_path / "cugen-copy"
    shutil.copytree(pinned, copied, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    target = copied / "cugen" / "ld.py"
    target.write_bytes(target.read_bytes() + b"\n")
    arguments = _pilot_kwargs(tmp_path)
    arguments["cugen_root"] = copied

    def forbidden(_root: Path) -> object:
        raise AssertionError("source mismatch reached CuGen import")

    monkeypatch.setattr(pilot, "_load_cugen_api", forbidden)
    with pytest.raises(ValueError, match="source hash mismatch"):
        pilot.run_cugen_pilot(**arguments)
    assert not (tmp_path / "artifact" / "manifest.json").exists()


@pytest.mark.parametrize("revision", ["short", "g" * 40, "0" * 39, "0" * 41])
def test_adapter_refuses_malformed_genomeos_revision_before_cugen_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision: str
) -> None:
    """Catch malformed source-only provenance reaching execution or a completion manifest."""
    pilot, _ = _pilot_modules()
    _forbid_import(monkeypatch, pilot)
    arguments = _pilot_kwargs(tmp_path)
    arguments["source_revision"] = revision

    with pytest.raises(ValueError, match="40-character hexadecimal"):
        pilot.run_cugen_pilot(**arguments)
    assert not (tmp_path / "artifact" / "manifest.json").exists()


def test_adapter_records_git_observed_genomeos_revision_when_not_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch invented source-only provenance when the actual package Git root is available."""
    pilot, artifact = _pilot_modules()
    _install_boundary_double(monkeypatch, pilot)
    arguments = _pilot_kwargs(tmp_path)
    arguments["source_revision"] = None

    manifest = artifact.verify_cugen_pilot(pilot.run_cugen_pilot(**arguments).parent)

    assert manifest["sources"]["genomeos"]["provenance"] == "git_observed"
    assert manifest["sources"]["genomeos"]["revision"] == subprocess_revision()


def test_adapter_refuses_missing_git_revision_before_cugen_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch a missing Git checkout being replaced with invented runtime provenance."""
    pilot, _ = _pilot_modules()
    _forbid_import(monkeypatch, pilot)
    arguments = _pilot_kwargs(tmp_path)
    arguments["source_revision"] = None

    def missing_git(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("git absent")

    monkeypatch.setattr(pilot.subprocess, "run", missing_git)
    with pytest.raises(ValueError, match="unavailable"):
        pilot.run_cugen_pilot(**arguments)
    assert not (tmp_path / "artifact" / "manifest.json").exists()


@pytest.mark.parametrize("mode", ["gpu_error", "gpu_numeric"])
def test_external_gpu_boundary_failure_retains_failure_without_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Catch a failed or numerically wrong GPU request being reported as completed evidence."""
    pilot, _ = _pilot_modules()
    if mode == "gpu_error":
        result: pd.DataFrame | BaseException = RuntimeError("controlled GPU boundary failure")
    else:
        result = _pair_frame()
        result.loc[0, "R"] = 0.5
    _install_boundary_double(monkeypatch, pilot, gpu_result=result)

    with pytest.raises((RuntimeError, ValueError)):
        pilot.run_cugen_pilot(**_pilot_kwargs(tmp_path))
    output = tmp_path / "artifact"
    assert (output / "source.cugen").is_file()
    assert (output / "training.cugen").is_file()
    assert (output / "failure.json").is_file()
    assert not (output / "manifest.json").exists()


def test_partial_subset_write_retains_failure_without_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch a partial external write being mistaken for a completed training snapshot."""
    pilot, _ = _pilot_modules()
    _install_boundary_double(monkeypatch, pilot)
    _subset, ld_matrix, imported = pilot._load_cugen_api(tmp_path)

    def partial_subset(_input: Path, output: Path, _indices: np.ndarray, **_kwargs: object) -> float:
        output.write_bytes(b"partial")
        raise RuntimeError("controlled partial subset failure")

    monkeypatch.setattr(pilot, "_load_cugen_api", lambda _root: (partial_subset, ld_matrix, imported))
    with pytest.raises(RuntimeError, match="partial subset"):
        pilot.run_cugen_pilot(**_pilot_kwargs(tmp_path))
    output = tmp_path / "artifact"
    assert (output / "training.cugen").read_bytes() == b"partial"
    assert (output / "failure.json").is_file()
    assert not (output / "manifest.json").exists()


def subprocess_revision() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _rewrite_manifest_hash(output: Path, name: str) -> dict[str, object]:
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][name] = hashlib.sha256((output / name).read_bytes()).hexdigest()
    identity = json.loads(json.dumps(manifest))
    identity.pop("scientific_identity_sha256")
    identity["files"].pop("runtime.json")
    canonical = (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    manifest["scientific_identity_sha256"] = hashlib.sha256(canonical).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest


@pytest.mark.parametrize(
    "name",
    [
        "source.cugen",
        "training.cugen",
        "reference.json",
        "cpu.tsv",
        "gpu.tsv",
        "validation.json",
        "runtime.json",
        "manifest.json",
    ],
)
def test_verifier_refuses_every_missing_completed_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Catch accepting a partial bundle because only a subset of members was consulted."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    (manifest_path.parent / name).unlink()

    with pytest.raises(ValueError):
        artifact.verify_cugen_pilot(manifest_path.parent)


@pytest.mark.parametrize(
    "name",
    [
        "source.cugen",
        "training.cugen",
        "reference.json",
        "cpu.tsv",
        "gpu.tsv",
        "validation.json",
        "runtime.json",
    ],
)
def test_verifier_refuses_every_tampered_data_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Catch accepting changed artifact bytes under the original completed manifest."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    target = manifest_path.parent / name
    target.write_bytes(target.read_bytes() + b"x")

    with pytest.raises(ValueError, match="hash mismatch"):
        artifact.verify_cugen_pilot(manifest_path.parent)


def test_verifier_refuses_extra_member_and_member_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch unmanifested or redirected bytes entering a supposedly closed artifact."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    output = manifest_path.parent
    (output / "extra").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="exact admitted member set"):
        artifact.verify_cugen_pilot(output)
    (output / "extra").unlink()
    runtime = output / "runtime.json"
    target = tmp_path / "runtime-target.json"
    runtime.rename(target)
    runtime.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        artifact.verify_cugen_pilot(output)


@pytest.mark.parametrize("path", ["../source.cugen", "/tmp/source.cugen"])
def test_verifier_refuses_traversal_or_absolute_manifest_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """Catch manifest paths escaping the closed artifact directory."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][path] = manifest["files"].pop("source.cugen")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError):
        artifact.verify_cugen_pilot(manifest_path.parent)


def test_verifier_recomputes_reference_from_snapshotted_training_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch a verifier that checks hashes but trusts stored scientific reference values."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    reference_path = manifest_path.parent / "reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["pairs"][0]["r"] = 0.5
    reference_path.write_text(
        json.dumps(reference, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    _rewrite_manifest_hash(manifest_path.parent, "reference.json")

    with pytest.raises(ValueError, match="recomputed evidence"):
        artifact.verify_cugen_pilot(manifest_path.parent)


def test_verifier_recomputes_selected_calls_from_both_binary_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch trusting a self-consistent training file that is not the declared source subset."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    calls = SOURCE_CALLS[np.asarray(SELECTION.training_indices)].copy()
    calls[0, 0] = 1
    training = manifest_path.parent / "training.cugen"
    training.write_bytes(_encode_cugen(calls))
    _rewrite_manifest_hash(manifest_path.parent, "training.cugen")

    with pytest.raises(ValueError, match="selected source calls"):
        artifact.verify_cugen_pilot(manifest_path.parent)


def _mutate_tsv_field(path: Path, column: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    row = lines[1].split("\t")
    row[header.index(column)] = value
    path.write_text("\t".join(header) + "\n" + "\t".join(row) + "\n", encoding="utf-8")


def test_verifier_rejects_fractional_raw_integer_token_without_float_rounding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch pandas-style 4.0-to-integer coercion hiding a malformed raw count token."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    cpu = manifest_path.parent / "cpu.tsv"
    _mutate_tsv_field(cpu, "N_OBS", "4.0")
    _rewrite_manifest_hash(manifest_path.parent, "cpu.tsv")

    with pytest.raises(ValueError, match="canonical base10 integer"):
        artifact.verify_cugen_pilot(manifest_path.parent)


def test_verifier_preserves_literal_na_id_instead_of_treating_it_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch default NA parsing that loses a literal identifier before identity checks."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    cpu = manifest_path.parent / "cpu.tsv"
    _mutate_tsv_field(cpu, "ID_A", "NA")
    _rewrite_manifest_hash(manifest_path.parent, "cpu.tsv")

    with pytest.raises(ValueError, match="annotation disagrees"):
        artifact.verify_cugen_pilot(manifest_path.parent)


def test_runtime_measurement_and_hash_do_not_change_scientific_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch runtime measurements leaking into the deterministic scientific identity."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    before = json.loads(manifest_path.read_text(encoding="utf-8"))["scientific_identity_sha256"]
    runtime_path = manifest_path.parent / "runtime.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["total_wall_seconds"] += 1.0
    runtime_path.write_text(
        json.dumps(runtime, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    after = _rewrite_manifest_hash(manifest_path.parent, "runtime.json")

    assert after["scientific_identity_sha256"] == before
    assert artifact.verify_cugen_pilot(manifest_path.parent)["status"] == "completed"


@pytest.mark.parametrize("field", ["execution", "cugen_source", "genomeos_paths"])
def test_verifier_refuses_rehashed_provenance_or_public_path_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """Catch a self-rehashed manifest rewriting which sources and public APIs executed."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if field == "execution":
        manifest["execution"]["executed"][2]["arguments"]["backend"] = "numpy"
    elif field == "cugen_source":
        manifest["sources"]["cugen"]["allowlist_files"]["cugen/ld.py"] = "f" * 64
    else:
        manifest["sources"]["genomeos"]["imported_files"].pop("genomeos/validation/ld_reference.py")
    identity = json.loads(json.dumps(manifest))
    identity.pop("scientific_identity_sha256")
    identity["files"].pop("runtime.json")
    manifest["scientific_identity_sha256"] = hashlib.sha256(
        (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        artifact.verify_cugen_pilot(manifest_path.parent)


def test_verifier_refuses_rehashed_stored_validation_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch trusting a hash-consistent validation claim rather than recomputing it."""
    manifest_path, artifact = _run_pilot(tmp_path, monkeypatch)
    validation_path = manifest_path.parent / "validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["cpu"]["observed_pairs"] = 0
    validation_path.write_text(
        json.dumps(validation, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    _rewrite_manifest_hash(manifest_path.parent, "validation.json")

    with pytest.raises(ValueError, match="validation summary"):
        artifact.verify_cugen_pilot(manifest_path.parent)

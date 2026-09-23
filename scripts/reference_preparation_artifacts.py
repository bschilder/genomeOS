"""Write and validate immutable preparation artifacts (design §6.2)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from genomeos.validation.reference_acquisition_codec import decode_acquisition
from genomeos.validation.reference_acquisition_types import ArtifactRef
from genomeos.validation.reference_cohorts import (
    PAPER_STAGE,
    TECHNICAL_STAGE,
    QualifiedCohortInputs,
)
from genomeos.validation.reference_preparation_codec import (
    decode_preparation,
    decode_preparation_inputs,
    encode_preparation,
)
from genomeos.validation.reference_preparation_types import PreparationManifest
from genomeos.validation.reference_window_manifest import decode_manifest
from scripts.reference_acquisition_artifacts import validate_acquisition
from scripts.reference_artifact_inventory import (
    check_tsv as _check_tsv,
)
from scripts.reference_artifact_inventory import (
    preparation_inventory_paths,
)
from scripts.reference_artifact_inventory import (
    validate_inventory as _inventory,
)
from scripts.reference_artifact_inventory import (
    windows_rows as _windows_rows,
)
from scripts.reference_artifact_io import (
    artifact_identity as _identity,
)
from scripts.reference_artifact_io import (
    artifact_path as _path,
)
from scripts.reference_artifact_io import (
    artifact_root as _root,
)
from scripts.reference_artifact_io import (
    checked_ref as _check_ref,
)
from scripts.reference_artifact_io import (
    read_bounded as _bounded_bytes,
)
from scripts.reference_artifact_io import (
    read_bounded_ref as _bounded_ref,
)
from scripts.reference_artifact_io import (
    require as _require,
)
from scripts.reference_artifact_io import (
    write_exclusive as _write_exclusive,
)
from scripts.reference_artifact_run_validation import _check_provenance, _check_stage_runs
from scripts.reference_cohort_artifacts import (
    COHORT_PATHS as _COHORT_PATHS,
)
from scripts.reference_cohort_artifacts import (
    qualify_cohort_files as _qualify_cohort_files,
)
from scripts.reference_count_artifacts import (
    expected_native_rows,
    expected_qc_rows,
    validate_count_tables,
)
from scripts.reference_io_common import fsync_artifact_tree

_PREPARATION_COLUMNS = (
    "window_id", "chrom", "state", "reason", "raw_records", "retained_variants",
)
_QC_COLUMNS = ("window_id", "stage", "category", "key", "origin", "count")
_NATIVE_COLUMNS = (
    "window_id", "stage", "state", "variants", "native_ac_an_matches", "native_interpreted_calls",
)
_MANIFEST_LIMIT = 16_777_216
_SIDECAR_LIMIT = 16_777_216

def _validate_preparation_content(
    root: Path,
    manifest: PreparationManifest,
    acquisition_root: Path,
    *,
    deep: bool = True,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> None:
    _require(type(deep) is bool, "invalid preparation validation mode")
    _check_provenance(manifest.provenance, phase="preparation")
    parent_root = _root(acquisition_root)
    if deep:
        acquisition = validate_acquisition(parent_root, cohort_inputs=cohort_inputs)
    else:
        acquisition = decode_acquisition(
            _bounded_bytes(
                _path(parent_root, "acquisition.json"),
                _MANIFEST_LIMIT,
                "acquisition manifest",
            )
        )
    _require(
        (
            manifest.provenance.code_revision,
            manifest.provenance.imported_source_sha256,
        )
        == (
            acquisition.provenance.code_revision,
            acquisition.provenance.imported_source_sha256,
        ),
        "preparation implementation differs from reviewed acquisition",
    )
    parent_raw = _bounded_bytes(
        _path(parent_root, "acquisition.json"), _MANIFEST_LIMIT, "acquisition manifest"
    )
    copied = _bounded_ref(
        root, manifest.inputs.acquisition, _MANIFEST_LIMIT, "copied acquisition manifest"
    )
    _require(copied == parent_raw, "copied acquisition manifest differs from acquisition root")
    _require(manifest.inputs.acquisition.sha256 == hashlib.sha256(parent_raw).hexdigest(),
             "preparation acquisition hash mismatch")
    _require(
        manifest.inputs.acquisition.path == "inputs/acquisition.json"
        and manifest.inputs.dependency_audit.path == _COHORT_PATHS["dependency_audit"],
        "preparation input paths differ from the fixed layout",
    )
    _require(
        manifest.inputs.cohort == acquisition.inputs.cohort,
        "preparation cohort inputs differ from acquisition",
    )
    technical, paper, source_samples = _qualify_cohort_files(
        root, manifest.inputs.cohort, cohort_inputs
    )
    _require(manifest.inputs.dependency_audit.sha256 == manifest.inputs.cohort.dependency_audit,
             "preparation dependency-audit identity mismatch")
    preparation_caps = {
        "windows.tsv": _SIDECAR_LIMIT,
        "qc-dispositions.tsv": _SIDECAR_LIMIT,
        "native-controls.tsv": _SIDECAR_LIMIT,
        "inputs.json": _SIDECAR_LIMIT,
        manifest.inputs.acquisition.path: _MANIFEST_LIMIT,
        **{value: _SIDECAR_LIMIT for value in _COHORT_PATHS.values()},
        f"{TECHNICAL_STAGE}.dependencies.json": _SIDECAR_LIMIT,
        f"{PAPER_STAGE}.dependencies.json": _SIDECAR_LIMIT,
        **{track.dependencies.path: _SIDECAR_LIMIT for track in manifest.tracks},
    }
    _inventory(
        root,
        manifest,
        "manifest.json",
        allowed_paths=preparation_inventory_paths(manifest),
        caps=preparation_caps,
    )
    for window in manifest.windows:
        for stage in window.stages:
            _check_stage_runs(window, stage)
    _require(decode_preparation_inputs(
        _bounded_bytes(_path(root, "inputs.json"), _SIDECAR_LIMIT, "preparation inputs")
    ) == manifest.inputs,
             "preparation inputs sidecar mismatch")
    _check_tsv(
        _path(root, "windows.tsv"),
        _PREPARATION_COLUMNS,
        _windows_rows(manifest.windows, preparation=True),
    )
    _check_tsv(
        _path(root, "qc-dispositions.tsv"), _QC_COLUMNS, expected_qc_rows(manifest)
    )
    _check_tsv(
        _path(root, "native-controls.tsv"), _NATIVE_COLUMNS, expected_native_rows(manifest)
    )
    acquisition_windows = {value.window_id: value for value in acquisition.windows}
    frozen = decode_manifest(
        _bounded_bytes(
            _path(_root(acquisition_root), "inputs/window-manifest.json"),
            _MANIFEST_LIMIT,
            "window manifest",
        ),
        windows_bytes=_bounded_bytes(
            _path(_root(acquisition_root), "inputs/windows.tsv"),
            _SIDECAR_LIMIT,
            "windows sidecar",
        ),
    )
    admitted_bcf = {
        value.native_bcf.path: value.native_bcf
        for value in acquisition.windows
        if value.native_bcf is not None
    }
    acquisition_root = parent_root
    for window in manifest.windows:
        parent_window = acquisition_windows[window.window_id]
        if window.raw_records is not None:
            _require(
                window.raw_records == parent_window.raw_records,
                "preparation raw count differs from acquisition",
            )
        if window.state == "refused":
            _require(
                window.retained_variants is None,
                "refused preparation cannot claim a retained variant count",
            )
        for stage in window.stages:
            _require(
                stage.native_tokens is None or stage.native_control is not None,
                "native token evidence lacks its count control",
            )
            if stage.native_control is None:
                continue
            sample_relative = _COHORT_PATHS[
                "technical_samples" if stage.stage == TECHNICAL_STAGE else "paper_samples"
            ]
            sample_size, sample_sha = _identity(_path(root, sample_relative))
            _require(
                stage.native_control.requested_samples
                == ArtifactRef(sample_relative, sample_size, sample_sha),
                "native requested samples differ from the qualified cohort",
            )
            if stage.native_tokens is not None:
                _require(
                    stage.native_control.selected_bcf is not None
                    and stage.native_tokens.input_bcf == stage.native_control.selected_bcf,
                    "native token input differs from selected cohort BCF",
                )
            parent = stage.native_control.input_bcf
            _require(parent.path.startswith("@acquisition/"), "native input lacks parent prefix")
            relative = parent.path.removeprefix("@acquisition/")
            expected = admitted_bcf.get(relative)
            _require(
                expected is not None
                and (parent.size_bytes, parent.sha256) == (expected.size_bytes, expected.sha256),
                "native input differs from admitted acquisition BCF",
            )
            _check_ref(acquisition_root, expected)
    _require(acquisition.complete, "preparation requires complete acquisition")
    if deep:
        validate_count_tables(
            root,
            manifest,
            acquisition_root,
            acquisition,
            frozen,
            (technical, paper),
            source_samples,
        )



def write_preparation_manifest(
    directory: Path,
    manifest: PreparationManifest,
    *,
    acquisition_root: Path,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> ArtifactRef:
    """Validate a count tree and exclusively write manifest.json last."""
    root = _root(directory)
    _require(type(manifest) is PreparationManifest, "invalid preparation manifest")
    _require(not (root / "manifest.json").exists(), "preparation manifest already exists")
    _validate_preparation_content(
        root,
        manifest,
        acquisition_root,
        deep=True,
        cohort_inputs=cohort_inputs,
    )
    fsync_artifact_tree(root)
    raw = encode_preparation(manifest)
    final = root / "manifest.json"
    published = False
    try:
        _check_provenance(manifest.provenance, phase="preparation")
        _write_exclusive(final, raw)
        published = True
        retained = _bounded_bytes(
            final,
            _MANIFEST_LIMIT,
            "written preparation manifest",
        )
        _require(
            retained == raw and decode_preparation(retained) == manifest,
            "written preparation manifest failed readback",
        )
        _require(
            validate_preparation(
                root,
                acquisition_root=acquisition_root,
                cohort_inputs=cohort_inputs,
            )
            == manifest,
            "written preparation manifest failed deep readback",
        )
    except BaseException:
        if published:
            final.unlink(missing_ok=True)
        raise
    return ArtifactRef("manifest.json", len(raw), hashlib.sha256(raw).hexdigest())


def validate_preparation(
    directory: Path,
    *,
    acquisition_root: Path,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> PreparationManifest:
    """Deeply validate one preparation root and its external acquisition binding."""
    root = _root(directory)
    manifest = decode_preparation(
        _bounded_bytes(_path(root, "manifest.json"), _MANIFEST_LIMIT, "preparation manifest")
    )
    _validate_preparation_content(
        root, manifest, acquisition_root, cohort_inputs=cohort_inputs
    )
    return manifest

"""Acquisition-ledger invariants for reference acquisition design §6.1."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from genomeos.validation.reference_acquisition_types import (
    ACQUISITION_POLICY,
    AcquisitionInputs,
    AcquisitionManifest,
    AcquisitionSourceReceipt,
    AcquisitionTotals,
    AcquisitionWindowReceipt,
    ArtifactRef,
    CohortInputHashes,
    MetadataReceipt,
    RunProvenance,
)
from tests.reference_acquisition_fixture import synthetic_preflight_case


def _artifact(path: str, raw: bytes = b"") -> ArtifactRef:
    return ArtifactRef(path, len(raw), hashlib.sha256(raw).hexdigest())


def _refused_manifest() -> AcquisitionManifest:
    window_manifest, _, _, _, _ = synthetic_preflight_case()
    digest = hashlib.sha256(b"fixture").hexdigest()
    inputs = AcquisitionInputs(
        _artifact("inputs/window-manifest.json"),
        _artifact("inputs/windows.tsv"),
        _artifact("inputs/preflight.json"),
        _artifact("inputs/review.json"),
        CohortInputHashes(digest, digest, digest, digest, digest, digest),
    )
    provenance = RunProvenance("1" * 40, "3.12", (), (), (), ())
    metadata = MetadataReceipt(
        "not_attempted",
        "metadata_mismatch",
        0,
        0,
        None,
        None,
        None,
        False,
        False,
    )
    sources = tuple(
        AcquisitionSourceReceipt(
            source,
            _artifact(f"inputs/indexes/{source.chrom}.tbi"),
            metadata,
            (),
            "refused",
            "metadata_mismatch",
            None,
            None,
        )
        for source in window_manifest.sources
    )
    windows = tuple(
        AcquisitionWindowReceipt(
            window.window_id,
            window.chrom,
            "refused",
            "metadata_mismatch",
            None,
            None,
            None,
            None,
            None,
            None,
            (),
        )
        for window in window_manifest.windows
    )
    totals = AcquisitionTotals(0, 0, 0, 0, 0, 0, 0, 0, None, None, None)
    return AcquisitionManifest(
        "reference_window_acquisition_v1",
        inputs,
        provenance,
        ACQUISITION_POLICY,
        sources,
        windows,
        (),
        totals,
        False,
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda windows: windows[:-1],
        lambda windows: windows + (windows[-1],),
        lambda windows: (windows[1], windows[0]) + windows[2:],
    ),
)
def test_acquisition_manifest_refuses_noncanonical_frozen_window_sets(mutate):
    """Missing, duplicate, and reordered windows must all falsify the 66-window claim."""
    manifest = _refused_manifest()

    with pytest.raises(ValueError, match="frozen 66 IDs"):
        replace(manifest, windows=mutate(manifest.windows))


def test_acquisition_manifest_refuses_a_false_complete_claim():
    """The public completion flag must agree with every retained source/window receipt."""
    manifest = _refused_manifest()
    assert manifest.complete is False

    with pytest.raises(ValueError, match="completeness disagrees"):
        replace(manifest, complete=True)

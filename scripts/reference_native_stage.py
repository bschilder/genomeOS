"""Open one preparation-stage native control chain (reference acquisition design §§5,7)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from genomeos.validation.reference_acquisition_types import (
    AcquisitionWindowReceipt,
    ArtifactRef,
    NativeCountFiles,
    NativeTokenFiles,
)

STAGE_REASONS = frozenset(
    {
        "native_count_unavailable",
        "native_encoding_refused",
        "native_mismatch",
        "limit_exceeded",
        "timeout",
        "record_invalid",
        "artifact_mismatch",
    }
)
PreparationStage = Literal["technical_qc_4117", "paper_ancestry_exclusion_4094"]


class CountRunner(Protocol):
    def __call__(
        self,
        bcf: ArtifactRef,
        cohort_samples: ArtifactRef,
        *,
        acquisition_root: Path,
        artifact_root: Path,
        bcftools: Path,
        output_prefix: str,
    ) -> NativeCountFiles: ...


class TokenRunner(Protocol):
    def __call__(
        self,
        bcf: ArtifactRef,
        *,
        artifact_root: Path,
        bcftools: Path,
        output_prefix: str,
    ) -> NativeTokenFiles: ...


def normalize_stage_reason(error: ValueError) -> str:
    reason = str(error)
    if reason == "artifact identity mismatch":
        return "artifact_mismatch"
    return reason if reason in STAGE_REASONS else "native_mismatch"


def open_native_stage(
    *,
    root: Path,
    acquisition_root: Path,
    parent_window: AcquisitionWindowReceipt,
    stage: PreparationStage,
    sample_ref: ArtifactRef,
    bcftools: Path,
    count_runner: CountRunner,
    token_runner: TokenRunner,
) -> tuple[NativeCountFiles | None, NativeTokenFiles | None, str | None]:
    """Run the bounded native count and token queries for one stage."""
    control = None
    tokens = None
    try:
        prefix = f"native/{parent_window.window_id}.{stage}"
        control = count_runner(
            parent_window.native_bcf,
            sample_ref,
            acquisition_root=acquisition_root,
            artifact_root=root,
            bcftools=bcftools,
            output_prefix=prefix,
        )
        if control.state != "complete" or control.selected_bcf is None:
            raise ValueError(control.reason or "native_encoding_refused")
        tokens = token_runner(
            control.selected_bcf,
            artifact_root=root,
            bcftools=bcftools,
            output_prefix=f"{prefix}.tokens",
        )
        if tokens.state != "complete":
            raise ValueError(tokens.reason or "native_encoding_refused")
    except ValueError as error:
        return control, tokens, normalize_stage_reason(error)
    return control, tokens, None

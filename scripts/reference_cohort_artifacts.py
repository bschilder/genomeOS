"""Qualify retained cohort inputs (reference acquisition design §§2, 6.1)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from genomeos.validation.reference_cohorts import (
    Cohort,
    QualifiedCohortInputs,
    qualify_cohort_inputs,
    qualify_real_cohort_inputs,
)
from scripts.reference_artifact_io import artifact_path, read_bounded, require

COHORT_PATHS = {
    "metadata": "inputs/cohort/metadata.tsv",
    "outliers": "inputs/cohort/outliers.txt",
    "exclusions": "inputs/cohort/exclusions.json",
    "technical_samples": "inputs/cohort/technical.samples.txt",
    "paper_samples": "inputs/cohort/paper.samples.txt",
    "dependency_audit": "inputs/cohort/dependency-audit.json",
}
COHORT_INPUT_LIMIT_BYTES = 16_777_216


def qualify_cohort_files(
    root: Path,
    hashes: object,
    expected: QualifiedCohortInputs | None = None,
) -> tuple[Cohort, Cohort, tuple[str, ...]]:
    """Bind retained cohort files and hashes to strict typed cohort values."""
    raw = {
        field: read_bounded(
            artifact_path(root, relative), COHORT_INPUT_LIMIT_BYTES, f"cohort {field}"
        )
        for field, relative in COHORT_PATHS.items()
    }
    for field, value in raw.items():
        require(
            hashlib.sha256(value).hexdigest() == getattr(hashes, field),
            f"cohort {field} hash mismatch",
        )
    arguments = tuple(raw[field] for field in COHORT_PATHS)
    qualified = (
        qualify_real_cohort_inputs(*arguments)
        if expected is None
        else qualify_cohort_inputs(*arguments)
    )
    if expected is not None:
        require(type(expected) is QualifiedCohortInputs, "invalid qualified cohort inputs")
        require(qualified == expected, "retained cohort inputs differ from qualified values")
    return qualified.technical, qualified.paper, qualified.source_samples

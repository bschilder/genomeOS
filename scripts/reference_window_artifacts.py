"""Public facade for immutable reference artifacts (acquisition design §6.2)."""

from __future__ import annotations

from scripts.reference_acquisition_artifacts import (
    validate_acquisition,
    write_acquisition_manifest,
)
from scripts.reference_preparation_artifacts import (
    validate_preparation,
    write_preparation_manifest,
)

__all__ = [
    "validate_acquisition",
    "validate_preparation",
    "write_acquisition_manifest",
    "write_preparation_manifest",
]

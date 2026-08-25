"""Immutable artifact discovery and reads (design §5, §6, §10, P4)."""

from .catalog import ArtifactCatalog, ArtifactUnavailable
from .manifest import ArtifactManifest, VariantEntry

__all__ = ["ArtifactCatalog", "ArtifactManifest", "ArtifactUnavailable", "VariantEntry"]

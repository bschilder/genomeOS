"""Synthetic structural fixtures for B0H integration; never calibration evidence."""

from __future__ import annotations

import numpy as np

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityFit,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation.reference_counts import ReferenceCount


def synthetic_rows(groups=6, variants=("001", "NA", "é:/v")):
    return tuple(
        ReferenceCount(f"g{g}:{v}", v, f"g{g}", "synthetic-region", "synthetic-block", 1, 4)
        for g in range(groups) for v in variants
    )


def synthetic_fit(training, *, config):
    available = tuple(row for row in training if row.an > 0)
    variants = tuple(sorted({row.variant_id for row in available}))
    shape = (config.chains, config.draws, len(variants))
    return PopulationHeterogeneityFit(
        config, variants, np.full(shape, 0.25), np.full(shape, 0.1),
        tuple(sorted(row.record_id for row in training)),
        tuple(sorted({row.group_id for row in training})),
        tuple(sorted(row.record_id for row in training if row.an == 0)),
        tuple(VariantTrainingCounts(
            variant, sum(row.variant_id == variant for row in available),
            sum(row.ac for row in available if row.variant_id == variant),
            sum(row.an for row in available if row.variant_id == variant),
        ) for variant in variants),
        tuple(VariantHeterogeneityDiagnostics(v, 1.01, 300.0, 250.0) for v in variants),
        0,
    )

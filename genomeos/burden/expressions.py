"""Burden expressions under Hardy–Weinberg (design §9, sub-project P3).

Turns an allele frequency into people. Pure functions over numpy arrays, so they broadcast over
posterior draws unchanged and unit-test against hand-computed values without any model.

**HWE is an assumption, not a fact**, and §9 requires it recorded per artifact and surfaced on
the layer info panel rather than buried. `hwe_assumed` is carried through the propagation output
for exactly that reason.

**One deliberate departure from §9's wording.** The spec writes the recessive case as
`affected_count = affected_freq × births × penetrance` but the dominant case as
`affected_freq = (1-(1-p)²) × penetrance` — so `affected_freq` means genotype frequency for one
inheritance mode and a penetrance-adjusted frequency for the other. Since §6 exposes
`affected_freq` as a selectable map metric, that would make the same layer mean different things
for different variants. Here penetrance is applied once, at the affected stage, for every mode:
`affected_freq = P(genotype) × penetrance`. Final counts are identical to §9's; only the
intermediate is made consistent. Raised on #87.
"""

from __future__ import annotations

import numpy as np

INHERITANCE_MODES: tuple[str, ...] = (
    "autosomal_recessive",
    "autosomal_dominant",
    "x_linked_recessive",
)


def _validate(p: np.ndarray, inbreeding: float) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    if np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("allele frequency must lie in [0, 1]")
    if not 0.0 <= inbreeding <= 1.0:
        raise ValueError("inbreeding coefficient F must lie in [0, 1]")
    return p


def carrier_frequency(
    p: np.ndarray,
    inheritance: str,
    inbreeding: float = 0.0,
    female_fraction: float = 0.5,
) -> np.ndarray:
    """Frequency of heterozygous carriers.

    Only meaningful where heterozygotes are unaffected. For a dominant condition a heterozygote
    is a case rather than a carrier, so this returns zeros — the concept does not apply, and
    returning the heterozygote frequency would invite reading it as a carrier layer.
    """
    p = _validate(p, inbreeding)
    if inheritance == "autosomal_recessive":
        return 2.0 * p * (1.0 - p) * (1.0 - inbreeding)
    if inheritance == "autosomal_dominant":
        return np.zeros_like(p)
    if inheritance == "x_linked_recessive":
        # Hemizygous males are affected, not carriers, so only females contribute.
        return female_fraction * 2.0 * p * (1.0 - p) * (1.0 - inbreeding)
    raise ValueError(f"unknown inheritance {inheritance!r}; expected one of {INHERITANCE_MODES}")


def affected_frequency(
    p: np.ndarray,
    inheritance: str,
    penetrance: float,
    inbreeding: float = 0.0,
    female_fraction: float = 0.5,
) -> np.ndarray:
    """Frequency of affected individuals: P(genotype) × penetrance."""
    p = _validate(p, inbreeding)
    if not 0.0 <= penetrance <= 1.0:
        raise ValueError("penetrance must lie in [0, 1]")

    if inheritance == "autosomal_recessive":
        genotype = p**2 + inbreeding * p * (1.0 - p)
    elif inheritance == "autosomal_dominant":
        genotype = 1.0 - (1.0 - p) ** 2
    elif inheritance == "x_linked_recessive":
        # Males are hemizygous, so a single copy manifests; females need two (plus the
        # inbreeding term). §9: computed separately by sex, using cell-level sex ratios.
        male_fraction = 1.0 - female_fraction
        female_genotype = p**2 + inbreeding * p * (1.0 - p)
        genotype = male_fraction * p + female_fraction * female_genotype
    else:
        raise ValueError(
            f"unknown inheritance {inheritance!r}; expected one of {INHERITANCE_MODES}"
        )

    return genotype * penetrance

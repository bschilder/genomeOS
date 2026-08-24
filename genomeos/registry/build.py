"""Assemble the population registry from source adapters (design §6, P0).

A `(source, label)` pair resolving to two different `population_id`s would silently split one
population's observations across two map points — the most damaging failure mode available in
P0 — so it raises rather than warns (design §12: schema violations are hard errors).
"""

from __future__ import annotations

import pandas as pd

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA


class AliasCollisionError(ValueError):
    """One (source, label) pair maps to more than one population_id."""


def build_registry(
    loaded: list[tuple[pd.DataFrame, pd.DataFrame]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not loaded:
        raise ValueError("build_registry requires at least one source")

    populations = pd.concat([p for p, _ in loaded], ignore_index=True)
    aliases = pd.concat([a for _, a in loaded], ignore_index=True)

    collisions = (
        aliases.groupby(["source", "label"])["population_id"].nunique().loc[lambda s: s > 1]
    )
    if not collisions.empty:
        detail = ", ".join(f"{src}/{lbl}" for src, lbl in collisions.index)
        raise AliasCollisionError(
            f"alias collisions (one label -> several population_id): {detail}"
        )

    orphans = set(aliases["population_id"]) - set(populations["population_id"])
    if orphans:
        raise ValueError(f"aliases reference unknown population_id: {sorted(orphans)}")

    return POPULATIONS_SCHEMA.validate(populations), ALIASES_SCHEMA.validate(aliases)

"""Posterior-draw uncertainty propagation and burden refusals (design §9, §12, P3).

**Why draws rather than analytic propagation.** §9 is explicit: the burden transformations are
nonlinear and the posterior is not Gaussian on the frequency scale, so pushing a mean and an sd
through the expressions would understate the interval and misplace the centre. Every cell's
posterior draws go through the expressions individually and the summary is taken afterwards.

**Refusals are the point of this module as much as the arithmetic is.** §9 requires the pipeline
to emit no number rather than a wrong one when:

- the cell's support is `unknown` — and `prior_dominated` on the same footing (§7, #38)
- no penetrance estimate exists — carrier frequency still ships, affected counts do not
- no population denominator exists for the cell

A refused cell is returned with null values and a stated reason rather than dropped, so a caller
can tell "we will not say" apart from "this cell does not exist".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from genomeos.burden.expressions import INHERITANCE_MODES, affected_frequency, carrier_frequency
from genomeos.surfaces.mask import MASKED_STATES

SEED = 42

METRICS: tuple[str, ...] = ("carrier_freq", "affected_freq", "carrier_count", "affected_count")

#: Metrics that describe affected individuals, so they need a penetrance estimate (§9).
_NEEDS_PENETRANCE = frozenset({"affected_freq", "affected_count"})
#: Metrics expressed as people, so they need a population denominator (§9).
_NEEDS_DENOMINATOR = frozenset({"carrier_count", "affected_count"})

REFUSAL_UNSUPPORTED = "support_masked"
REFUSAL_NO_PENETRANCE = "penetrance_missing"
REFUSAL_NO_DENOMINATOR = "denominator_missing"


@dataclass(frozen=True)
class BurdenConfig:
    inheritance: str
    metric: str
    #: None is a legitimate state, not an omission: many variants have no defensible penetrance
    #: estimate. Affected metrics are then refused; carrier metrics still ship (§9).
    penetrance: float | None = None
    #: §9: F defaults to 0 and is overridden per region only where a published consanguinity
    #: coefficient exists, with the source recorded.
    inbreeding_coefficient: float = 0.0
    denominator_source: str | None = None
    penetrance_source: str | None = None
    hwe_assumed: bool = True
    draws: int = 500
    seed: int = SEED

    def __post_init__(self) -> None:
        if self.inheritance not in INHERITANCE_MODES:
            raise ValueError(
                f"unknown inheritance {self.inheritance!r}; expected one of {INHERITANCE_MODES}"
            )
        if self.metric not in METRICS:
            raise ValueError(f"unknown metric {self.metric!r}; expected one of {METRICS}")
        if self.draws <= 0:
            raise ValueError("draws must be > 0")


def compute_burden(
    frequency_draws: np.ndarray,
    cells: pd.DataFrame,
    config: BurdenConfig,
) -> pd.DataFrame:
    """Burden per cell with a 95% credible interval, or a stated refusal.

    `frequency_draws` is `(n_draws, n_cells)` of posterior allele frequency. `cells` carries
    `h3_index`, `support`, and — for count metrics — `denominator`, plus an optional
    `female_fraction` used by the X-linked expressions.
    """
    draws = np.asarray(frequency_draws, dtype=float)
    if draws.ndim != 2:
        raise ValueError("frequency_draws must be 2-D (n_draws, n_cells)")
    if draws.shape[1] != len(cells):
        raise ValueError(
            f"frequency_draws has {draws.shape[1]} cells but `cells` has {len(cells)}"
        )

    draws = _thin(draws, config)
    cells = cells.reset_index(drop=True)

    refusals = _refusals(cells, config)
    female_fraction = (
        cells["female_fraction"].to_numpy(dtype=float)
        if "female_fraction" in cells
        else np.full(len(cells), 0.5)
    )

    mean = np.full(len(cells), np.nan)
    q025 = np.full(len(cells), np.nan)
    q975 = np.full(len(cells), np.nan)

    allowed = np.flatnonzero(pd.isna(refusals))
    for i in allowed:
        per_draw = _metric_draws(draws[:, i], cells, i, float(female_fraction[i]), config)
        mean[i] = per_draw.mean()
        q025[i], q975[i] = np.quantile(per_draw, [0.025, 0.975])

    return pd.DataFrame(
        {
            "h3_index": cells["h3_index"].to_numpy(),
            "metric": config.metric,
            "mean": mean,
            "q025": q025,
            "q975": q975,
            "denominator_source": config.denominator_source,
            "penetrance_source": config.penetrance_source,
            "hwe_assumed": config.hwe_assumed,
            "refusal": refusals,
        }
    )


def _thin(draws: np.ndarray, config: BurdenConfig) -> np.ndarray:
    """Take `config.draws` draws, deterministically (§5)."""
    available = draws.shape[0]
    if available <= config.draws:
        return draws
    rng = np.random.default_rng(config.seed)
    return draws[rng.choice(available, size=config.draws, replace=False), :]


def _refusals(cells: pd.DataFrame, config: BurdenConfig) -> np.ndarray:
    """One refusal reason per cell, or NA where a number may be emitted."""
    refusals = np.full(len(cells), None, dtype=object)

    masked = cells["support"].isin(MASKED_STATES).to_numpy()
    refusals[masked] = REFUSAL_UNSUPPORTED

    if config.metric in _NEEDS_PENETRANCE and config.penetrance is None:
        refusals[pd.isna(refusals)] = REFUSAL_NO_PENETRANCE

    if config.metric in _NEEDS_DENOMINATOR:
        if "denominator" not in cells:
            refusals[pd.isna(refusals)] = REFUSAL_NO_DENOMINATOR
        else:
            missing = cells["denominator"].isna().to_numpy()
            refusals[missing & pd.isna(refusals)] = REFUSAL_NO_DENOMINATOR

    return refusals


def _metric_draws(
    p: np.ndarray, cells: pd.DataFrame, i: int, female_fraction: float, config: BurdenConfig
) -> np.ndarray:
    if config.metric in _NEEDS_PENETRANCE:
        assert config.penetrance is not None  # guaranteed by _refusals
        frequency = affected_frequency(
            p,
            config.inheritance,
            penetrance=config.penetrance,
            inbreeding=config.inbreeding_coefficient,
            female_fraction=female_fraction,
        )
    else:
        frequency = carrier_frequency(
            p,
            config.inheritance,
            inbreeding=config.inbreeding_coefficient,
            female_fraction=female_fraction,
        )

    if config.metric in _NEEDS_DENOMINATOR:
        return frequency * float(cells.loc[i, "denominator"])
    return frequency

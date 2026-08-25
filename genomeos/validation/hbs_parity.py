"""Golden test 1 — HbS parity scoring (design §8, P3).

§8 is the definition of done for v1, and it is deliberately not a smoke test: the pipeline is
correct when it reproduces estimates somebody else derived independently. Three criteria, all of
which must hold:

1. our national point estimate falls inside the published interval for **≥80%** of countries
   with published estimates,
2. our credible interval overlaps the published interval for **≥95%** of them, and
3. global totals agree within the published uncertainty.

Failing this blocks publication of any other variant's burden layer, so the scoring is written
to be pessimistic wherever it could flatter us:

- **The denominator is every country with a published estimate**, not every country we happened
  to produce a number for. A country we cannot estimate counts against us, because otherwise the
  score improves as coverage shrinks — refusing to answer would look like accuracy.
- **Intervals must be like for like.** The published intervals are IQRs (50%), so the caller must
  pass an IQR, not a 95% interval; comparing 95% against 50% makes criterion 2 nearly free (#92).
  This is not checkable at runtime, so it is a documented precondition of `score_parity`.
- **The global comparison takes our global posterior**, never a sum of our national medians.
  Medians are not additive, and summing them understates the total by roughly 5% — an artifact
  that would read as model failure (#92).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from genomeos.reference.piel2013 import (
    GLOBAL_AS_NEONATES,
    GLOBAL_SS_NEONATES,
    national_estimates,
)

METRICS: tuple[str, ...] = ("as", "ss")

REQUIRED_COLUMNS: tuple[str, ...] = ("country", "point", "iqr_lower", "iqr_upper")


@dataclass(frozen=True)
class ParityCriteria:
    """§8's thresholds. Named so a change to the bar is a visible diff, not a magic number."""

    point_inside_interval_min: float = 0.80
    interval_overlap_min: float = 0.95


@dataclass(frozen=True)
class ParityResult:
    metric: str
    n_published: int
    n_estimated: int
    point_inside_fraction: float
    interval_overlap_fraction: float
    global_within_published: bool
    criteria: ParityCriteria
    per_country: pd.DataFrame = field(repr=False)

    @property
    def point_criterion_met(self) -> bool:
        return self.point_inside_fraction >= self.criteria.point_inside_interval_min

    @property
    def overlap_criterion_met(self) -> bool:
        return self.interval_overlap_fraction >= self.criteria.interval_overlap_min

    @property
    def passed(self) -> bool:
        return (
            self.point_criterion_met and self.overlap_criterion_met and self.global_within_published
        )

    def worst_countries(self, n: int = 10) -> pd.DataFrame:
        """Countries failing the point criterion, largest published burden first.

        A bare pass/fail is not actionable; §8 failures need to be diagnosable.
        """
        failed = self.per_country[~self.per_country["point_inside"].fillna(False)]
        return failed.nlargest(n, "published_point")

    def __str__(self) -> str:
        def mark(ok: bool) -> str:
            return "PASS" if ok else "FAIL"

        return "\n".join(
            [
                f"HbS parity ({self.metric.upper()} neonates) — {mark(self.passed)}",
                f"  point inside published IQR: {self.point_inside_fraction:.1%} "
                f"(need {self.criteria.point_inside_interval_min:.0%}) {mark(self.point_criterion_met)}",
                f"  intervals overlap:          {self.interval_overlap_fraction:.1%} "
                f"(need {self.criteria.interval_overlap_min:.0%}) {mark(self.overlap_criterion_met)}",
                f"  global total within IQR:    {mark(self.global_within_published)}",
                f"  countries: {self.n_estimated} estimated of {self.n_published} published",
            ]
        )


def score_parity(
    ours: pd.DataFrame,
    metric: str = "ss",
    global_estimate: tuple[float, float, float] | None = None,
    criteria: ParityCriteria | None = None,
    targets: pd.DataFrame | None = None,
) -> ParityResult:
    """Score our national estimates against Piel et al. 2013 (§8).

    `ours` needs `country`, `point`, `iqr_lower`, `iqr_upper`. **The interval must be an IQR**,
    matching the published one — see the module docstring.

    `global_estimate` is `(point, lower, upper)` from our *global* posterior. Omitting it fails
    criterion 3 rather than skipping it: an unmeasured criterion is not a met one.
    """
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; expected one of {METRICS}")
    missing = set(REQUIRED_COLUMNS) - set(ours.columns)
    if missing:
        raise ValueError(f"`ours` is missing required columns {sorted(missing)}")
    if ours["country"].duplicated().any():
        raise ValueError("`ours` must have one row per country")

    criteria = criteria or ParityCriteria()
    published = national_estimates() if targets is None else targets

    left = published[
        ["country", f"{metric}_neonates_per_year", f"{metric}_iqr_lower", f"{metric}_iqr_upper"]
    ].rename(
        columns={
            f"{metric}_neonates_per_year": "published_point",
            f"{metric}_iqr_lower": "published_lower",
            f"{metric}_iqr_upper": "published_upper",
        }
    )
    # Left join, so a country we failed to estimate stays in the denominator (see docstring).
    merged = left.merge(ours, on="country", how="left")

    estimated = merged["point"].notna()
    merged["point_inside"] = (
        estimated
        & (merged["point"] >= merged["published_lower"])
        & (merged["point"] <= merged["published_upper"])
    )
    merged["interval_overlaps"] = (
        estimated
        & (merged["iqr_lower"] <= merged["published_upper"])
        & (merged["iqr_upper"] >= merged["published_lower"])
    )

    n_published = len(merged)
    published_global = GLOBAL_SS_NEONATES if metric == "ss" else GLOBAL_AS_NEONATES
    global_ok = bool(
        global_estimate is not None
        and published_global[1] <= global_estimate[0] <= published_global[2]
    )

    return ParityResult(
        metric=metric,
        n_published=n_published,
        n_estimated=int(estimated.sum()),
        point_inside_fraction=float(merged["point_inside"].sum() / n_published),
        interval_overlap_fraction=float(merged["interval_overlaps"].sum() / n_published),
        global_within_published=global_ok,
        criteria=criteria,
        per_country=merged,
    )

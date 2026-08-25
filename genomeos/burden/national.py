"""National burden totals from a fitted surface (design §8, §9, §10, P3).

The missing middle of golden test 1: §8 has an input (332 georeferenced MAP HbS surveys, #91), a
target (Piel et al.'s 191 national estimates, #93) and a scorer (`validation.hbs_parity`), and
this is what turns a fitted surface into the one AS/SS neonate number per country the scorer
consumes.

**Population-weighted, never a centroid value.** Evaluating the surface at a country centroid is
the shortcut, and it fails worst exactly where the answer matters: Nigeria, India and the DRC
carry most of the global burden and are the countries whose internal HbS variation is largest. A
centroid value for India is not a number anyone should score parity against. §9's rule is a sum
over cells — births in the cell × affected frequency in the cell — and that is what happens here.

**The interval is an IQR, and the point estimate is a median of sums.** Both follow from #92:

- Piel's published intervals are IQRs — 50% credible intervals — so a 95% interval scored against
  them makes §8's overlap criterion nearly free. `national_totals` emits the 25th and 75th
  percentiles for that reason, and `hbs_parity.score_parity` documents it as a precondition.
- Medians do not sum. Piel's own 191 national medians total 4-7% *below* their published global
  posterior, and reproducing that shortfall by summing our national medians would read as model
  failure. So every country total, and the global total, is formed **draw by draw** — sum the
  cells within a draw, then take quantiles across draws — never by combining per-cell summaries.

This is why the input is `frequency_draws` rather than a fitted surface object: the summaries a
surface exposes per cell cannot be re-summed into a national interval, and a function that
accepted them would be quietly computing the wrong thing. `SurfaceFit` currently exposes only
those summaries, so a real run waits on #112.

**Partial coverage is the hard part, and it is governed by population, not by area.** Most
countries have a posterior for some cells and a masked one (`unknown`, `prior_dominated`) for the
rest, and §7/§10 require the masked cells excluded from every statistic with the excluded share
returned alongside it. Two shares are returned, and only one of them governs:

- `mapped_population_fraction` — the share of the country's **denominator** that sat in included
  cells. This is the number that decides whether a national total means anything. (With a
  national crude birth rate, births are proportional to population within a country, so the
  births-weighted and population-weighted shares are the same number.)
- `unmapped_cell_fraction` — §10's share of *cells* excluded. Reported because §10 names it, and
  because the gap between the two is informative, but it must not be read as coverage: a country
  can be 60% unmapped by area and 95% covered by population when its cities sit near surveys, and
  the cell-count number badly misrepresents that country in both directions.

**Below `MIN_MAPPED_POPULATION_FRACTION` of mapped population, the country gets no number.** The
three things this rollup must never do instead are all tempting and all forbidden by §4 and §9:
fill masked cells with a point value and total them (that is what `prior_dominated` *means*);
assume the mapped part's rate applies to the unmapped part; or scale the mapped total up by the
inverse coverage. Each produces a confident national number out of an absence of data. A refusal
is a valid output, and it is correctly self-penalising — `score_parity` left-joins on every
published country, so a country we refuse counts against us — which is exactly why coverage must
not be widened to improve a score.

**Two methods, one of which is an experiment.** Partial coverage has a second possible answer,
and which one scores better on §8 is an empirical question rather than a matter of taste, so both
are implemented and compared:

- `national_totals` — **Method A**, the default and the only one any existing call site reaches.
  Supported cells only, refusal below the coverage threshold. This is §4/§10 as written.
- `national_totals_propagating_masked` — **Method B**. Every populated cell, masked ones
  included, each carrying its full posterior rather than a point value. A masked cell's posterior
  has barely moved off the prior, so it contributes a wide distribution and the national interval
  widens with the unmapped share; every country gets a number, and a badly covered one gets an
  interval that is visibly untrustworthy.

**Method B does not satisfy the invariant that masked cells are excluded from every aggregation
statistic.** It is here to be measured against Method A, not to be adopted: adopting it for
published artifacts needs its own issue and a decision (#113). The two are separate functions
rather than a flag precisely so that no call site can reach B by accident, and the method is
recorded on every result and every row written to disk.

**What the emitted number covers.** `point` is the burden over the country's *mapped* population
only, never an extrapolation to the whole country, so it is systematically low against Piel's
whole-country estimate by at most `1 - mapped_population_fraction`. That bound is the entire
reason the threshold exists: comparing an 80%-mapped estimate against a whole-country published
one is a known, bounded mismatch, and comparing a 30%-mapped one is not a parity test at all.

Pure offline functions over arrays and frames, with no I/O (§5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from genomeos.burden.expressions import affected_frequency, carrier_frequency
from genomeos.burden.propagate import BurdenConfig, cell_refusals
from genomeos.geo.countries import rollup_by_country

#: Metrics this rollup can total. A national *frequency* is not a sum of cell frequencies, and
#: what it should be instead — population-weighted mean, unweighted mean, per-capita — is §10's
#: statistic selector, not a burden question. `geo.countries.rollup_by_country` does that job.
COUNT_METRICS: tuple[str, ...] = ("carrier_count", "affected_count")

#: §8 scores against Piel et al.'s interquartile ranges, so ours must be one too (#92).
IQR_QUANTILES: tuple[float, float] = (0.25, 0.75)

#: Least mapped population share a country may have and still receive a national total.
#:
#: The emitted total covers the mapped population only (see the module docstring), so this bounds
#: how far below a whole-country published estimate ours can sit for structural reasons rather
#: than modelling ones: at 0.80, at most a fifth of a country's people are unrepresented, which
#: is a mismatch a reviewer can reason about. Below it the comparison stops being a parity test
#: and starts being a coverage measurement wearing a parity test's clothes.
#:
#: 0.80 is a starting value, not a derived one, and it is the kind of threshold #39's HbS
#: calibration should set from data. It is a named constant so that changing it is a visible
#: diff rather than an argument someone passed once.
MIN_MAPPED_POPULATION_FRACTION: float = 0.80

REQUIRED_COLUMNS: tuple[str, ...] = ("h3_index", "iso3", "support", "denominator")

#: **Method A**, and the only one any default reaches: total the supported cells, refuse a
#: country whose mapped population share is too small to stand for it. Satisfies §4/§10 as
#: written — masked cells are excluded from every aggregation statistic.
SUPPORTED_ONLY = "supported_only"
#: **Method B**, an experiment (#113): total every populated cell, masked ones included, carrying
#: their full posteriors so the national interval widens with the unmapped share. Reachable only
#: through `national_totals_propagating_masked`, never by passing a flag to the default path.
PROPAGATE_MASKED = "propagate_masked"
COVERAGE_METHODS: tuple[str, ...] = (SUPPORTED_ONLY, PROPAGATE_MASKED)

#: Any support state outside `mask.MASKED_STATES`; see `_included`.
_UNMASKED_PROBE = "interpolated"

#: A country with a posterior over too little of its population to stand for the country (§9).
#: Distinct from `propagate.REFUSAL_UNSUPPORTED`, which is a *cell* having no usable posterior:
#: this one is about what a national total is allowed to claim.
REFUSAL_LOW_COVERAGE = "population_coverage_below_threshold"


@dataclass(frozen=True)
class NationalRollup:
    """Per-country totals, the global total from the same draws, and their provenance.

    **`point` is the burden over each country's mapped population**, not over the country. It is
    never extrapolated to the unmapped remainder, and `mapped_population_fraction` states how much
    of the country it stands for; countries below `min_mapped_population` carry no number at all.

    `global_total` is `(median, iqr_lower, iqr_upper)` over the summed draws, which is what §8's
    third criterion needs — our global posterior, not a sum of our national medians (#92). It is
    `None` when every cell was refused, because §9 emits no number rather than a wrong one. It
    sums every unmasked cell, **including cells in countries whose national total was refused for
    coverage**: that refusal is about what may be attributed to a country, not about whether those
    people exist. So the global total is not the sum of the national rows — which is separately
    true anyway, because medians do not sum.
    """

    metric: str
    #: Which of `COVERAGE_METHODS` produced these rows. Recorded so a frame written to disk
    #: cannot be read back without knowing whether masked cells are inside its totals.
    method: str
    n_draws: int
    quantiles: tuple[float, float]
    #: `None` under Method B, which has no coverage refusal.
    min_mapped_population: float | None
    denominator_source: str | None
    hwe_assumed: bool
    global_total: tuple[float, float, float] | None
    per_country: pd.DataFrame = field(repr=False)

    @property
    def n_estimated(self) -> int:
        return int(self.per_country["point"].notna().sum())

    def refused(self) -> pd.DataFrame:
        """Countries we produced no number for, with the reason. A refusal is an output (§9)."""
        return self.per_country[self.per_country["refusal"].notna()]

    def __str__(self) -> str:
        countries = len(self.per_country)
        mapped = self.per_country["mapped_population_fraction"].median()
        total = "refused" if self.global_total is None else f"{self.global_total[0]:,.0f}"
        bar = (
            "no coverage refusal"
            if self.min_mapped_population is None
            else f"refusing below {self.min_mapped_population:.0%}"
        )
        return (
            f"{self.metric} [{self.method}]: {self.n_estimated} of {countries} countries "
            f"estimated from {self.n_draws} draws; global total {total}; median mapped "
            f"population {mapped:.1%} ({bar})"
        )


def national_totals(
    cells: pd.DataFrame,
    frequency_draws: np.ndarray,
    config: BurdenConfig,
    *,
    quantiles: tuple[float, float] = IQR_QUANTILES,
    min_mapped_population: float = MIN_MAPPED_POPULATION_FRACTION,
) -> NationalRollup:
    """**Method A.** Total the per-cell burden inside each country, draw by draw (§9).

    Supported cells only: masked cells are excluded from the sum, as §4 and §10 require, and a
    country whose *mapped population* share falls below `min_mapped_population` gets no number.

    `frequency_draws` is `(n_draws, n_cells)` of posterior allele frequency, column-aligned with
    `cells`. `cells` carries `h3_index`, `iso3` (see `geo.countries.assign_countries`), `support`
    (see `surfaces.mask`) and `denominator` — annual births per cell for a neonate estimate, from
    `geo.population.births_from_population` — plus an optional `female_fraction` for the X-linked
    expressions.

    The denominator column is named as `burden.propagate` names it rather than `births`, because
    the same rollup totals carriers over a resident population as readily as neonates over annual
    births; which one it is, is recorded in `config.denominator_source`.

    `min_mapped_population` defaults to the named `MIN_MAPPED_POPULATION_FRACTION` and is carried
    on the result, so every rollup states the coverage bar it was produced under rather than
    leaving a reader to assume one.
    """
    return _rollup(
        cells,
        frequency_draws,
        config,
        quantiles=quantiles,
        method=SUPPORTED_ONLY,
        min_mapped_population=min_mapped_population,
    )


def national_totals_propagating_masked(
    cells: pd.DataFrame,
    frequency_draws: np.ndarray,
    config: BurdenConfig,
    *,
    quantiles: tuple[float, float] = IQR_QUANTILES,
) -> NationalRollup:
    """**Method B — an experiment, not the default.** Total over every populated cell, masked
    ones included, carrying each cell's full posterior rather than a point value.

    **This does not satisfy the §4/§10 invariant that masked cells are excluded from every
    aggregation statistic.** It is built to be compared against `national_totals` (Method A), not
    to be adopted: no existing call site reaches it, and adopting it for published artifacts
    needs its own issue and a decision (#113). Read the module docstring's argument for and
    against before using it for anything.

    **What makes it honest, and where that rests.** Nothing is imputed and no point value is
    substituted: the masked cells' own draws go through the burden expression per draw, exactly
    as the supported cells' do, and the national quantiles are taken afterwards. A masked cell's
    posterior has by construction barely moved off the prior — that is what `prior_dominated`
    means, and an `unknown` cell has no observation within 2ρ — so it contributes a wide
    distribution, and a country's interval widens roughly in proportion to how much of its
    population sits in unmapped territory. Every country gets a number, and a country with poor
    coverage gets an interval wide enough to be visibly untrustworthy.

    That argument rests entirely on the caller's draws actually being near-prior in masked cells.
    They are for a posterior sampled at those cells (`SurfaceFit.prior_frequency_sd` is the prior
    scale the mask's `posterior_contraction` is measured against). They are not if a caller
    passes draws that were narrowed, clipped or filled elsewhere — and this function cannot tell,
    which is one of the arguments against adopting it.

    Denominator and penetrance refusals still stand: masked support is the only reason this
    method sets aside, and `mapped_population_fraction` is reported exactly as Method A reports
    it, so the coverage a number rests on travels with it either way.
    """
    return _rollup(
        cells,
        frequency_draws,
        config,
        quantiles=quantiles,
        method=PROPAGATE_MASKED,
        min_mapped_population=None,
    )


def _rollup(
    cells: pd.DataFrame,
    frequency_draws: np.ndarray,
    config: BurdenConfig,
    *,
    quantiles: tuple[float, float],
    method: str,
    min_mapped_population: float | None,
) -> NationalRollup:
    """The arithmetic both methods share. They differ only in which cells enter the sum."""
    if config.metric not in COUNT_METRICS:
        raise ValueError(
            f"{config.metric!r} is not a national total; expected one of {COUNT_METRICS}. "
            "A national frequency is a choice of statistic — use geo.countries.rollup_by_country"
        )
    draws = _check_draws(frequency_draws, cells)
    cells = _check_cells(cells)
    if not 0.0 <= quantiles[0] < quantiles[1] <= 1.0:
        raise ValueError(f"quantiles must be an increasing pair within [0, 1]; got {quantiles}")
    if min_mapped_population is not None and not 0.0 <= min_mapped_population <= 1.0:
        raise ValueError("min_mapped_population must be a fraction in [0, 1]")

    refusals = _method_refusals(cells, config, method)
    included = pd.isna(refusals)
    weights = cells["denominator"].to_numpy(dtype=float)
    frequency = _frequency_draws(draws, cells, config)

    # §10's excluded-cell fraction, from the one implementation of it (`mask.aggregate_cells`),
    # so this rollup cannot drift from the aggregation the rest of the pipeline performs. It is
    # reported under both methods: what Method B changes is what it *does* about the exclusion,
    # never whether the exclusion is stated.
    support_rollup = rollup_by_country(cells, column="denominator", statistic="sum")
    unmapped = support_rollup.set_index("iso3")
    # Coverage is always measured against the strict view, whichever method did the summing.
    supported = pd.isna(cell_refusals(cells, config))

    rows = []
    for iso3, sub in cells.groupby("iso3", sort=True):
        index = sub.index.to_numpy()
        keep = index[included[index]]
        # Coverage always measures the *supported* population, whichever cells were summed:
        # under Method B it is the caveat on a number that was emitted anyway.
        mapped = _mapped_fraction(
            weights[index[supported[index]]], np.nansum(weights[index])
        )
        # Order matters. With no usable cell at all the cell-level reason is the informative one
        # ("every cell was masked"); the coverage rule only has something to say about a country
        # that *did* produce cells and still cannot stand for itself.
        if not len(keep):
            refusal = _dominant_refusal(refusals[index])
        elif min_mapped_population is not None and mapped < min_mapped_population:
            refusal = REFUSAL_LOW_COVERAGE
        else:
            refusal = None
        rows.append(
            {
                "iso3": iso3,
                **_country_interval(frequency, weights, keep, quantiles, refused=refusal),
                "refusal": refusal,
                "n_cells": len(index),
                "n_included": len(keep),
                "mapped_population_fraction": mapped,
                "unmapped_cell_fraction": float(unmapped.loc[iso3, "unmapped_fraction"]),
                "mapped_denominator": float(np.nansum(weights[index[supported[index]]])),
            }
        )

    keep_all = np.flatnonzero(included)
    global_draws = frequency[:, keep_all] @ weights[keep_all] if len(keep_all) else None

    return NationalRollup(
        metric=config.metric,
        method=method,
        n_draws=int(draws.shape[0]),
        quantiles=quantiles,
        min_mapped_population=min_mapped_population,
        denominator_source=config.denominator_source,
        hwe_assumed=config.hwe_assumed,
        global_total=None if global_draws is None else _summarise(global_draws, quantiles),
        per_country=pd.DataFrame(rows),
    )


def _method_refusals(cells: pd.DataFrame, config: BurdenConfig, method: str) -> np.ndarray:
    """The refusal reasons a method recognises per cell — the only place the two differ.

    A cell with no reason enters that method's sum, and a country with no such cell is refused
    for the reason most of its cells give, so this decides both.
    """
    if method == SUPPORTED_ONLY:
        return cell_refusals(cells, config)
    if method != PROPAGATE_MASKED:
        raise ValueError(f"unknown method {method!r}; expected one of {COVERAGE_METHODS}")
    # Ask the same refusal policy what it would refuse if support were not a reason, rather than
    # restating the denominator and penetrance rules here. `_UNMASKED_PROBE` is any state outside
    # `mask.MASKED_STATES`; the cells themselves are untouched.
    return cell_refusals(cells.assign(support=_UNMASKED_PROBE), config)


def _check_draws(frequency_draws: np.ndarray, cells: pd.DataFrame) -> np.ndarray:
    draws = np.asarray(frequency_draws, dtype=float)
    if draws.ndim != 2:
        raise ValueError("frequency_draws must be 2-D (n_draws, n_cells)")
    if draws.shape[1] != len(cells):
        raise ValueError(f"frequency_draws has {draws.shape[1]} cells but `cells` has {len(cells)}")
    return draws


def _check_cells(cells: pd.DataFrame) -> pd.DataFrame:
    """Every way this frame can be wrong is a way a national total can be wrong silently."""
    missing = [column for column in REQUIRED_COLUMNS if column not in cells.columns]
    if missing:
        raise ValueError(f"`cells` is missing required columns {missing}")
    unassigned = int(cells["iso3"].isna().sum())
    if unassigned:
        raise ValueError(
            f"{unassigned} cells have no iso3. Assign or drop them explicitly "
            "(geo.countries.assign_countries): a cell dropped here understates its country"
        )
    duplicated = int(cells["h3_index"].duplicated().sum())
    if duplicated:
        raise ValueError(f"{duplicated} duplicate h3_index values would be counted twice")
    return cells.reset_index(drop=True)


def _frequency_draws(
    draws: np.ndarray, cells: pd.DataFrame, config: BurdenConfig
) -> np.ndarray:
    """Genotype frequency per (draw, cell), through the same expressions as the cell layer (§9).

    The expressions are elementwise in `p`, so the whole `(n_draws, n_cells)` block goes through
    at once; `female_fraction` is per cell and broadcasts along the last axis.
    """
    female_fraction = (
        cells["female_fraction"].to_numpy(dtype=float)
        if "female_fraction" in cells
        else 0.5
    )
    if config.metric == "affected_count":
        if config.penetrance is None:
            # `cell_refusals` has already refused every cell, so no total will be formed from
            # this. NaN rather than a stand-in penetrance: a substituted default that happened
            # to reach a sum would be indistinguishable from an estimate (§12).
            return np.full(draws.shape, np.nan)
        return affected_frequency(
            draws,
            config.inheritance,
            penetrance=config.penetrance,
            inbreeding=config.inbreeding_coefficient,
            female_fraction=female_fraction,
        )
    return carrier_frequency(
        draws,
        config.inheritance,
        inbreeding=config.inbreeding_coefficient,
        female_fraction=female_fraction,
    )


def _country_interval(
    frequency: np.ndarray,
    weights: np.ndarray,
    keep: np.ndarray,
    quantiles: tuple[float, float],
    *,
    refused: str | None,
) -> dict[str, float]:
    """Sum the country's cells within each draw, then summarise across draws (#92).

    A refused country returns nulls rather than the total of whatever cells it did have: a
    partial total presented as a national one is the failure mode the threshold exists to stop.
    """
    if refused is not None or not len(keep):
        return {"point": np.nan, "iqr_lower": np.nan, "iqr_upper": np.nan}
    point, lower, upper = _summarise(frequency[:, keep] @ weights[keep], quantiles)
    return {"point": point, "iqr_lower": lower, "iqr_upper": upper}


def _summarise(totals: np.ndarray, quantiles: tuple[float, float]) -> tuple[float, float, float]:
    """Median and interval of a per-draw total. The median is the point estimate because that is
    what Piel et al. publish, and because the burden posterior is right-skewed (#102)."""
    lower, upper = np.quantile(totals, quantiles)
    return float(np.median(totals)), float(lower), float(upper)


def _mapped_fraction(included: np.ndarray, total: float) -> float:
    """Share of a country's denominator that sat in cells we could use.

    NaN where the country's denominator totals zero: with nobody in it there is no population
    share to report, and returning 1.0 would read as full coverage. Its total is still a number
    — zero people is zero burden — and the null coverage says why it should not be read as one.
    """
    if not np.isfinite(total) or total <= 0.0:
        return float("nan")
    return float(np.nansum(included) / total)


def _dominant_refusal(refusals: np.ndarray) -> str:
    """Why a country got no number: the most common reason among its cells (§9's vocabulary)."""
    return str(pd.Series(refusals).value_counts().idxmax())

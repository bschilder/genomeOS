"""Roll a fitted surface up to national burden estimates and score them (design §8, §9, §10).

The pipeline #94 specifies, end to end: predict per H3 cell → weight each cell by its births →
sum inside each country boundary → compare against Piel et al.'s published national estimates.

    python scripts/national_estimates.py --draws draws.npz \
        --population-cells data/worldpop_res4.csv --out data/national_ss.csv

**Two real inputs, one of which nothing in this repository can produce yet.**

- `--population-cells` is a CSV of `h3_index,population`, from
  `genomeos.geo.population.aggregate_raster_to_h3` over a WorldPop mosaic
  (`scripts/fetch_worldpop.py`). The mosaic is ~870 MB and is fetched, never committed.
- `--draws` is an `.npz` holding `h3_index` (n_cells), `support` (n_cells) and `draws`
  (n_draws × n_cells) of posterior allele frequency. **`SurfaceFit` exposes posterior summaries
  per cell but not the draws**, and summaries cannot be re-summed into a national interval —
  medians do not sum (#92) — so this file has no producer yet. See #112.

`--synthetic` substitutes a deterministic stand-in for both, so the plumbing, the refusals and
the figures can be exercised without either. **Its numbers are not estimates of anything.** The
allele-frequency field is a pair of analytic bumps, and each country's population is spread
evenly over its cells; only the country geometry, the national populations and the crude birth
rates are real, and they are there so the arithmetic runs at a believable scale rather than to
make the output mean something. Everything it writes is labelled `synthetic-demonstration`, and
per AGENTS.md a synthetic artifact must never be presented as a scientific result.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from genomeos.burden.national import MIN_MAPPED_POPULATION_FRACTION, national_totals
from genomeos.burden.propagate import BurdenConfig
from genomeos.geo.countries import assign_countries
from genomeos.geo.population import births_from_population
from genomeos.reference.piel2013 import national_estimates
from genomeos.surfaces.mask import MaskConfig, classify_support
from genomeos.validation.hbs_parity import score_parity, to_parity_frame

SEED = 42

#: HbS is autosomal recessive and fully penetrant for the neonate counts §8 is scored on: SS
#: neonates are the homozygotes, AS neonates the heterozygotes (§9).
METRICS = {"ss": ("affected_count", 1.0), "as": ("carrier_count", None)}

SYNTHETIC = "synthetic-demonstration"
#: Where the synthetic field is centred, and how wide. Roughly where HbS actually is, so the
#: demonstration exercises the same countries a real run would — and nowhere near a real map.
SYNTHETIC_FOCI = ((6.0, 15.0, 0.16, 2_000.0), (20.0, 78.0, 0.06, 1_200.0))
#: Correlation range and survey spacing for the stand-in mask. Chosen so coverage is genuinely
#: patchy: a demonstration where every country is fully mapped exercises none of §10.
SYNTHETIC_RANGE_KM = 600.0
SYNTHETIC_SITE_STRIDE = 5


def _haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0088
    dlat, dlon = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    )
    return 2 * radius * np.arcsin(np.sqrt(a))


def synthetic_inputs(resolution: int, n_draws: int) -> tuple[pd.DataFrame, np.ndarray]:
    """A stand-in surface and mask. Deterministic given `(resolution, n_draws)`.

    The mask comes from the pipeline's own `classify_support` against a grid of pretend survey
    sites, so the partial coverage in the figures is produced by the real rule rather than drawn
    on afterwards — which is the only part of this that is worth looking at.
    """
    import h3

    from genomeos.viz.basemap import h3_land_cells

    cells = h3_land_cells(resolution)
    centres = np.array([h3.cell_to_latlng(cell) for cell in cells], dtype=float)
    lat, lon = centres[:, 0], centres[:, 1]

    sites = np.array(
        [h3.cell_to_latlng(cell) for cell in h3_land_cells(2)[::SYNTHETIC_SITE_STRIDE]],
        dtype=float,
    )
    distance = _haversine_km(
        lat[:, None], lon[:, None], sites[None, :, 0], sites[None, :, 1]
    ).min(axis=1)

    field = np.zeros(len(cells))
    for site_lat, site_lon, peak, width in SYNTHETIC_FOCI:
        field += peak * np.exp(-0.5 * (_haversine_km(lat, lon, site_lat, site_lon) / width) ** 2)

    support = classify_support(
        has_observation_centre=distance < 100.0,
        dist_nearest_obs_km=distance,
        # Contraction grows with distance, so cells far inside the range still fall out as
        # prior-dominated: both masked states appear, as they do in a real fit.
        posterior_contraction=np.clip(0.3 + 0.75 * distance / SYNTHETIC_RANGE_KM, 0.0, 1.2),
        correlation_range_km=SYNTHETIC_RANGE_KM,
        config=MaskConfig(),
    )

    rng = np.random.default_rng(SEED)
    draws = np.clip(
        rng.normal(field[None, :], 0.25 * field[None, :] + 0.002, size=(n_draws, len(cells))),
        0.0,
        1.0,
    )
    return pd.DataFrame({"h3_index": cells, "support": support}), draws


def synthetic_population(cells: pd.DataFrame, published: pd.DataFrame) -> pd.Series:
    """Each country's published population, spread evenly over the cells it was assigned.

    Uniform within a country and real between them: the national scale is right, so the run
    exercises the arithmetic at the magnitudes a real one would, while nothing about *where*
    people are inside a country is claimed. A country with no published row gets no population,
    and is refused for want of a denominator rather than given a stand-in.
    """
    people = published.set_index("iso3")["population_thousands"] * 1_000.0
    return cells["iso3"].map(people) / cells.groupby("iso3")["iso3"].transform("size")


def load_inputs(args) -> tuple[pd.DataFrame, np.ndarray]:
    """Cells with `population` and `support`, plus `(n_draws, n_cells)` frequency draws."""
    payload = np.load(args.draws, allow_pickle=False)
    cells = pd.DataFrame(
        {"h3_index": payload["h3_index"].astype(str), "support": payload["support"].astype(str)}
    )
    population = pd.read_csv(args.population_cells, dtype={"h3_index": str})
    merged = cells.merge(population[["h3_index", "population"]], on="h3_index", how="left")
    if merged["population"].isna().any():
        # §9: no denominator, no number — but silently dropping the cell would understate the
        # country instead of refusing it, so it travels on and `national_totals` refuses it.
        print(f"{int(merged['population'].isna().sum())} cells have no population denominator")
    return merged, payload["draws"]


def _markdown(frame: pd.DataFrame) -> str:
    """A markdown table without pulling in tabulate for one function."""
    header = list(frame.columns)
    rows = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    for record in frame.itertuples(index=False):
        rows.append("| " + " | ".join(_format(value) for value in record) + " |")
    return "\n".join(rows)


def _format(value) -> str:
    if isinstance(value, float):
        return "—" if pd.isna(value) else (f"{value:,.0f}" if abs(value) >= 10 else f"{value:.3f}")
    return str(value)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=Path, help="npz of h3_index, support, draws")
    ap.add_argument("--population-cells", type=Path, help="csv of h3_index,population")
    ap.add_argument("--synthetic", action="store_true", help="stand-in inputs; NOT an estimate")
    ap.add_argument("--metric", choices=sorted(METRICS), default="ss")
    ap.add_argument("--h3-res", type=int, default=4, help="resolution for --synthetic")
    ap.add_argument("--draws-n", type=int, default=200, help="draw count for --synthetic")
    ap.add_argument("--top", type=int, default=10, help="rows at each end of the printed table")
    ap.add_argument(
        "--min-mapped-population", type=float, default=MIN_MAPPED_POPULATION_FRACTION,
        help="refuse a country below this mapped population share",
    )
    ap.add_argument("--out", type=Path, help="write the per-country rollup here")
    args = ap.parse_args()

    if args.synthetic:
        print(f"*** {SYNTHETIC}: these numbers estimate nothing. See the module docstring. ***")
        cells, draws = synthetic_inputs(args.h3_res, args.draws_n)
        source = SYNTHETIC
    elif args.draws and args.population_cells:
        cells, draws = load_inputs(args)
        source = f"{args.draws.name}+{args.population_cells.name}"
    else:
        raise SystemExit("pass --draws and --population-cells, or --synthetic")

    countries = assign_countries(cells["h3_index"])
    cells = cells.merge(countries, on="h3_index", how="left")
    in_a_country = cells["iso3"].notna().to_numpy()
    print(
        f"{len(cells):,} cells, {int(in_a_country.sum()):,} inside a country "
        f"({cells['iso3'].nunique()} countries)"
    )
    cells, draws = cells[in_a_country].reset_index(drop=True), draws[:, in_a_country]

    # §9's births: cell population × the country's crude birth rate, which the published Piel
    # table already carries per country — so the parity run needs no separate UN WPP fetch.
    published = national_estimates()
    if args.synthetic:
        cells["population"] = synthetic_population(cells, published)
    birth_rate = cells["iso3"].map(published.set_index("iso3")["crude_birth_rate"])
    if birth_rate.isna().any():
        # Web Table 1 has no row for these, so there is no birth rate and therefore no
        # denominator. They travel on with a null denominator and are refused by name (§9),
        # rather than being given a stand-in rate or dropped out of the run.
        missing = sorted(set(cells.loc[birth_rate.isna(), "iso3"]))
        print(f"no published crude birth rate for {missing}; those countries will be refused")
    cells = births_from_population(cells, birth_rate).rename(columns={"births": "denominator"})

    metric, penetrance = METRICS[args.metric]
    rollup = national_totals(
        cells,
        draws,
        BurdenConfig(
            inheritance="autosomal_recessive",
            metric=metric,
            penetrance=penetrance,
            denominator_source=f"{source}+piel2013-cbr",
        ),
        min_mapped_population=args.min_mapped_population,
    )
    print(rollup)
    print(rollup.refused()["refusal"].value_counts().to_string())

    frame = to_parity_frame(rollup.per_country)
    result = score_parity(frame, metric=args.metric, global_estimate=rollup.global_total)
    print(result)

    table = result.top_bottom(args.top)
    print(f"\nTop and bottom {args.top} by estimated {args.metric.upper()} neonates/year:")
    print(_markdown(table))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        rollup.per_country.assign(
            metric=rollup.metric,
            denominator_source=rollup.denominator_source,
            min_mapped_population=rollup.min_mapped_population,
            source=source,
        ).to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

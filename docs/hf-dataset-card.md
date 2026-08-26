---
license: other
license_name: mixed-see-provenance
license_link: https://github.com/bschilder/genomeOS/issues/117
language:
  - en
tags:
  - population-genetics
  - spatial-statistics
  - bayesian
  - hla
  - genomeos
pretty_name: genomeOS Atlas data store
size_categories:
  - 100K<n<1M
---

# genomeOS Atlas data store

Working store for [genomeOS](https://github.com/bschilder/genomeOS) — an open atlas of human
genetic variation where every number can be traced back to the measurement behind it.

It holds three kinds of thing: **source tables** the pipeline ingests, **trained models**, and the
**published per-cell surfaces** those models produce.

> **This is interim storage.** The project's artifact home is GCS
> ([#33](https://github.com/bschilder/genomeOS/issues/33)); this dataset exists so the store lives
> in one addressable place until that is set up. Everything here is plain files, so the migration
> is a copy.

> **Nothing here is validated science yet.** No golden test has passed. Held-out validation of the
> HbS surface shows it predicting held-out surveys only marginally better than a global constant
> ([#109](https://github.com/bschilder/genomeOS/issues/109)). Treat these as pipeline outputs, not
> as results.

## Contents

```
raw/
  afnd_populations.tsv        1,821 AFND populations: coordinates, settlement class, ascertainment
  afnd_frequencies.tsv        123,502 HLA/KIR/MIC/cytokine allele frequencies
  map_hbs_surveys.csv         1,287 Malaria Atlas Project HbS surveys
  map_g6pd_surveys.csv        1,749 MAP G6PD deficiency surveys
store/
  artifacts/<variant>__<model_version>__<data_version>/
    cells.parquet             per-H3-cell posterior summaries  <- the citable output
    manifest.json             what was published, under which assumptions
  fits/<variant>.fit.pkl      trained PyMC models  <- a CACHE, not an artifact (see below)
  INVENTORY.json              sha256 of every file
```

## How it was made

**`raw/afnd_populations.tsv`** — harvested from
[allelefrequencies.net](http://www.allelefrequencies.net) by
[`scripts/fetch_afnd.py`](https://github.com/bschilder/genomeOS/blob/main/scripts/fetch_afnd.py),
in two public hops: `pop6001b.asp` lists every population as a `?pop_name=` link in one request,
and `pop6001c.asp?pop_name=<name>` prints the coordinate. 1,821 of 1,825 retained; the four
refusals print no coordinate at all. Coordinates are kept in AFND's printed sexagesimal
(`6º 25' S`) because the printed precision is what bounds them — `41º 0' N` is degree precision and
earns a ~78 km uncertainty floor, not an arcminute fix.

**`raw/afnd_frequencies.tsv`** — not ours. Redistributed by
[slowkow/allelefrequencies](https://github.com/slowkow/allelefrequencies) (MIT-licensed code),
scraped from AFND's public frequency search endpoints.

**`raw/map_*.csv`** — Malaria Atlas Project WFS layers `Explorer:HbS_Data` and `Explorer:G6PD_Data`,
by `scripts/fetch_map_hbs.py`. Open, no credentials.

**`store/fits/`** — `scripts/build_surfaces.py`. A binomial/beta-binomial likelihood over a
Gaussian process on the **unit sphere** (not lon/lat — a degree of longitude is 111 km at the
equator and 47 km at 65°N), with inducing points placed on an H3 geodesic grid, sampled with
numpyro NUTS. A fit that has not mixed is refused rather than published.

**`store/artifacts/`** — `scripts/publish_artifacts.py`, predicting each fit onto H3 res-3 land
cells.

## Using it

```python
from huggingface_hub import snapshot_download
import pandas as pd

path = snapshot_download("bschilder/genomeos-data", repo_type="dataset")
```

### The surfaces (start here)

```python
cells = pd.read_parquet(f"{path}/store/artifacts/chr11-5227002-T-A__v1__map-2026-08/cells.parquet")
print(cells.columns.tolist())
# ['h3_index', 'variant_id', 'post_median', 'post_mean', 'post_sd',
#  'q025', 'q975', 'q25', 'q75', 'support', 'posterior_contraction',
#  'dist_nearest_obs_km', 'model_version', 'data_version']
```

**Read the `support` column before the numbers.** It is the point of the whole design:

| `support` | meaning |
|---|---|
| `observed` | a survey sits in this cell |
| `interpolated` | inferred, with data within twice the correlation range |
| `unknown` | no data close enough — **the model is not making a claim here** |
| `prior_dominated` | the posterior never moved off the prior |

```python
# Never aggregate without masking. A mean over unmasked cells is a mean over the prior.
claimed = cells[~cells["support"].isin(["unknown", "prior_dominated"])]
print(f"{len(claimed)}/{len(cells)} cells carry a claim")
print(claimed["post_median"].describe())
```

`dist_nearest_obs_km` travels with each row so you can apply a stricter threshold than ours
without refitting.

### The manifest

```python
import json
m = json.load(open(f"{path}/store/artifacts/chr11-5227002-T-A__v1__map-2026-08/manifest.json"))
# correlation_range_km, likelihood, lengthscale_sigma, n_observations, support_counts, ...
```

A fitted correlation range is meaningless without the prior that produced it, which is why the
manifest carries both. Artifacts are keyed `(variant_id, model_version, data_version)` and are
immutable: a refit publishes alongside rather than overwriting, so an older citation keeps
resolving.

### The observations

```python
pops = pd.read_csv(f"{path}/raw/afnd_populations.tsv", sep="\t")
freq = pd.read_csv(f"{path}/raw/afnd_frequencies.tsv", sep="\t")
# Join on population name — AFND's own public key, shared by both tables, so it is exact.
joined = freq.merge(pops, left_on="population", right_on="population")
```

Watch for two things that cost real data when missed: `n` carries **thousand separators**
(`"3,732"`), and `alleles_over_2n` is a **frequency, not a count** — allele counts are
reconstructed as `round(af * 2n)`.

### The fits — read this first

```python
from genomeos.surfaces.fit import load_fit          # genomeOS must be installed
fit = load_fit(f"{path}/store/fits/chr11-5227002-T-A.fit.pkl")
```

**A fit is a cache, not an artifact.** It is a pickled PyMC graph, so it is coupled to the exact
PyMC/pytensor versions that wrote it, and **pickle executes arbitrary code on load** — only load
files you trust. It is here because refitting costs ~20 minutes, not because it is archival. The
parquet is the durable form: 1.1 MB against a 121 MB fit, carrying everything a consumer needs.

Reproduce the environment exactly with
[`requirements.lock`](https://github.com/bschilder/genomeOS/blob/main/requirements.lock).

## Provenance and terms

**This dataset is private, and that is deliberate.** AFND publishes no licence — its "Licensing"
link carries only a disclaimer, and re3data's "public domain" record is third-party catalogue
metadata rather than a grant. Collection here proceeds on an assumed-open basis
([#117](https://github.com/bschilder/genomeOS/issues/117)); keeping the dataset private makes this
**storage rather than redistribution**, which is what that decision covers. Redistribution of
anything derived from indigenous-population panels is separately unsettled
([#66](https://github.com/bschilder/genomeOS/issues/66)).

Cite the sources, not this store:

- **AFND** — Gonzalez-Galarza et al., *Allele frequency net database (AFND) 2020 update*, Nucleic
  Acids Research 48:D783. [doi:10.1093/nar/gkz1029](https://doi.org/10.1093/nar/gkz1029)
- **MAP HbS** — Piel et al., *Global epidemiology of sickle haemoglobin in neonates*, The Lancet
  381:142 (2013).
- **MAP G6PD** — Howes et al., *G6PD deficiency prevalence and estimates of affected populations in
  malaria endemic countries*, PLoS Medicine 9:e1001339 (2012).
- **Frequency redistribution** — [slowkow/allelefrequencies](https://github.com/slowkow/allelefrequencies).

## Known limitations

- **No golden test has passed.** §8's HbS parity test is blocked on population-weighted national
  aggregation.
- **Held-out skill is marginal.** Under spatially-blocked cross-validation the HbS surface scores
  MAE 0.0388 against a constant baseline's 0.0391 ([#109](https://github.com/bschilder/genomeOS/issues/109)).
- **HLA surfaces are not published here.** A screen of twenty alleles fitted correlation ranges of
  1,036–4,111 km — a range that long makes the field near-constant and indistinguishable from the
  intercept ([#122](https://github.com/bschilder/genomeOS/issues/122)).
- **One population can dominate.** AFND's DKMS German donor entry has `an` = 6,912,132, about
  23,000× the median; a binomial likelihood weights by `an`
  ([#123](https://github.com/bschilder/genomeOS/issues/123)).
- **G6PD is a phenotype, not a variant.** `phenotype:g6pd-deficiency` aggregates ~200 alleles
  assayed by enzyme activity ([#116](https://github.com/bschilder/genomeOS/issues/116)).

# Genome OS Atlas v1 — Design

**Status:** approved design, pending spec review
**Date:** 2026-08-22
**Scope:** sub-projects P0–P5 (the Mendelian burden map). P6+ are named here only to fix their boundaries.

---

## 1. Objective

An interactive global map of **predicted disease burden for Mendelian and single-variant genetic conditions**, derived from the geographic distribution of allele frequencies, at the finest geographic resolution the underlying observations honestly support.

v1 renders three distinct, never-blended layers:

1. **Observations** — georeferenced allele counts, as measured.
2. **Surfaces** — fitted allele frequency with posterior uncertainty and an explicit data-support mask.
3. **Burden** — expected carriers / affected individuals, with propagated credible intervals.

## 2. Non-goals for v1

Named so their absence is a decision rather than an omission:

- Genome-wide polygenic (PRS) maps — deferred to P8 pending the uncertainty and portability machinery built in P2/P3. Rationale in §4.
- Time-sliced ancient-DNA surfaces (P6), Globe mode (P7), semantic trait search and polygenic layers over the map (P8), Chromosome mode (P9), Chromatin mode (P10), individual-genome upload (P11), conversational analysis agent (P12).
- Any behavioural, cognitive, or anthropometric trait. Out of scope for burden rendering in v1 and gated by policy thereafter (§13).
- Real-time surface fitting. All inference is offline and batch, by design (§5).

## 3. Decisions taken

| Decision | Choice | Consequence |
|---|---|---|
| v1 flagship layer | Mendelian + single-variant burden | Validation set exists; science is settled; polygenic risk deferred |
| Surface derivation | Precomputed posteriors over a curated variant set | Real uncertainty; fixed variant list; simple read path |
| Query engine | DuckDB-on-Cloud-Run for reads, BigQuery for batch | ~10–100ms interactive reads at near-zero marginal cost; two systems to operate |
| Spatial index | H3, parquet-backed | Composes with lasso aggregation and deck.gl's `H3HexagonLayer` without a second geometry stack |
| Basemap | MapLibre GL + open raster/vector tiles | No per-load billing on a public site; works offline in dev. Google Maps Platform remains a drop-in swap via deck.gl's `GoogleMapsOverlay` if we later want Street View / Places |

## 4. Scientific constraints, and how the design answers each

These are design inputs, not caveats. Each has a structural answer in the architecture.

| Constraint | Evidence | Structural answer |
|---|---|---|
| Spatial interpolation manufactures convincing clines with no demographic cause | Novembre & Stephens 2008 | **Data-support mask** is mandatory on every surface. Cells with no observation inside 2× the fitted correlation range render as `unknown`, hatched — never smoothly interpolated toward zero. Observations and surfaces are separate layers that the UI cannot blend. |
| PRS portability collapses across ancestries; between-group mean differences are unidentifiable | Multi-ancestry portability studies; PGS Catalog ancestry-normalisation work | Polygenic layers excluded from v1 entirely. When they arrive (P8), within-population variance renders alongside any between-population comparison, and the GWAS-Catalog ancestry composition of the underlying evidence is itself a togglable map layer. |
| Geographic precision is a per-region property, not a global setting | Locator; IBD localisation in UK Biobank (median 45 km); Elhaik GPS (Sardinian villages ≤50 km) | Rendered resolution is driven by local observation density (§7), not by zoom level. Zooming in past the data does not invent detail; it reveals the mask. |
| Population *labels* are not coordinates, and sampling location ≠ ancestral location | 1KG labels such as GBR/ASW are diaspora/urban sampling sites | P0 registry carries an explicit `location_type` (`sampling` \| `ancestral` \| `inferred`) and an `uncertainty_radius_km` on every entry. Surfaces weight observations by that radius. |
| Several of the best georeferenced panels are indigenous-population data | CARE Principles; FAIR/CARE operationalisation | Registry schema carries provenance and a Biocultural Notice field; entries derived from HGDP/SGDP/AADR/AFND link to source consent terms (§13). |

## 5. Architecture

```
sources: gnomAD HGDP+1KG · AFND · AADR · MAP HbS/G6PD surveys · GAsP · MCPS · IndiGen
   │  ingest (bioDB-style) → BigQuery staging
   ▼
[P0] population geolocation registry — versioned, coordinates + radius + provenance
   │  join
   ▼
[P1] observations (parquet on GCS, partitioned by chromosome)   ← "what was measured"
   │  BigQuery batch: per-variant INLA-SPDE fit
   ▼
[P2] surfaces: posterior mean + sd + data-support mask, H3-keyed  ← "what was inferred"
   │  × gridded population × penetrance, via posterior draws
   ▼
[P3] burden: expected cases, mean + 95% CI, H3-keyed
   │  resolution-laddered parquet shards → GCS + CDN
   ▼
[P4] Cloud Run + DuckDB read API ──────────► [P5] Next.js + deck.gl client
       search · region aggregation · stats        map · layers · legend · lasso
       (no inference on this path)                (no science in this layer)
```

**Boundary rules that make this maintainable:**

- `surface-fit` (P2) and `burden-calc` (P3) are **pure offline functions**, deterministic given `(config, data_version, seed)`. All science lives here. Both are unit-testable against published numbers, which is what makes §8 a test rather than a demo.
- **The serving path performs no inference.** P4 reads precomputed artifacts and aggregates them. This is what makes it cheap, fast, and cacheable.
- Surfaces and burden rasters are **immutable artifacts** keyed by `(variant_id, model_version, data_version)`. A model change publishes new artifacts; it never mutates a map someone has cited.
- The client renders; it contains no genetics. Any number shown on screen exists in an artifact or came from an aggregation endpoint.

## 6. Data model

**P0 — `population_registry`** (curated, versioned, human-reviewed)

| column | type | notes |
|---|---|---|
| `population_id` | string | canonical id, our namespace |
| `source_labels` | array<struct<source, label>> | every alias across AFND / HGDP / 1KG / SGDP / PGG / GAsP / GenomeIndia / AADR |
| `lat`, `lon` | float64 | decimal degrees, WGS84 |
| `uncertainty_radius_km` | float64 | sampling extent; required, no default |
| `location_type` | enum | `sampling` \| `ancestral` \| `inferred` |
| `provenance` | string | publication DOI or database accession for the coordinate |
| `biocultural_notice` | string, nullable | CARE-aligned notice / consent terms link |
| `registry_version` | string | semver; surfaces record which version they used |

**P1 — `observations`** (parquet on GCS, partitioned by `chrom`)

`variant_id` (chr-pos-ref-alt, GRCh38) · `rsid` · `population_id` · `lat` · `lon` · `radius_km` · `ac` · `an` · `source` · `assay` (array/exome/genome/HLA-typing) · `date_lower`, `date_upper` (years BP; modern = 0, ancient from AADR) · `ingest_version`

**P2 — `surfaces`** (parquet, keyed by `variant_id`, `h3_res`, `h3_parent`)

`h3_index` · `post_mean` · `post_sd` · `q025` · `q975` · `support` (enum `observed` \| `interpolated` \| `unknown`) · `dist_nearest_obs_km` · `eff_n_in_range` · `model_version` · `registry_version`

**P3 — `burden`** — same key, plus `metric` (`carrier_count` \| `affected_count` \| `carrier_freq` \| `affected_freq`), `mean`, `q025`, `q975`, `denominator_source`, `penetrance_source`.

**Why H3 parquet rather than GeoTIFF:** region aggregation (§10) becomes a `WHERE h3_parent IN (...)` predicate pushdown in DuckDB, the resolution ladder is a column rather than a file pyramid, and deck.gl's `H3HexagonLayer` consumes the indexes directly — one geometry stack instead of two.

**Resolution ladder.** H3 res 4 (~1,770 km²/cell, 288,122 cells globally) is the global default. Res 5 (~253 km²) and res 6 (~36 km²) are populated only where observation density supports them, determined per-cell by `eff_n_in_range` (§7). Res 6 is the finest v1 will emit — finer than that exceeds what any open georeferenced panel justifies.

## 7. P2 — Surface inference specification

**Model.** Binomial likelihood with a logit-link Gaussian process over space:

```
AC_i ~ Binomial(AN_i, expit(f(s_i)))
f    ~ GP(μ, Matérn-3/2(range ρ, marginal variance σ²))
```

**Fit.** INLA with SPDE approximation. Chosen over MCMC (Piel's approach) and over variational GPs because it gives proper marginal posteriors at batch-feasible cost, and because it is the same lineage the model-based geostatistics literature in this exact application already uses — which matters for defensibility.

**Hierarchical hyperpriors.** ρ and σ² are fitted per variant, but under a prior shared across variants binned by global allele frequency decile. Variants observed in few populations therefore borrow spatial structure from better-observed variants at similar frequency, rather than producing an unconstrained fit. Bin-level hyperparameters are fitted first, in one pass, then frozen.

**Observation weighting.** Each observation is placed as a disc of radius `uncertainty_radius_km`, not a point, so a country-wide sample does not act as a pinpoint measurement.

**Data-support mask.** Per cell: `dist_nearest_obs_km` and `eff_n_in_range` (sum of `an` within ρ, distance-weighted). Then:
- `observed` — an observation centre falls within the cell
- `interpolated` — nearest observation within 2ρ
- `unknown` — otherwise; **rendered hatched, and excluded from every aggregation statistic**

**Resolution promotion.** A cell is emitted at res 5 or 6 only if `eff_n_in_range` at that resolution exceeds a threshold set during the HbS calibration (§8). Elsewhere the res-4 value is authoritative and the client does not subdivide it.

**Time axis (AADR).** Observations carry `date_lower`/`date_upper`. v1 fits **modern-only** surfaces (date = 0) and ingests ancient observations into P1 without fitting them, so the schema and pipeline are ready. Time-sliced surfaces are P6 work; putting the columns in now costs nothing and avoids a migration.

## 8. Definition of done — HbS parity

v1 is correct when the pipeline reproduces published, independently-derived estimates.

**Golden test 1 — HbS (rs334, HBB).** Inputs: the open georeferenced HbS survey database (MAP/ROAD-MAP). Target: Piel et al. 2013 national annual AS and SS neonate estimates.

Acceptance:
- our national point estimate falls inside the published interval for **≥80%** of countries with published estimates, **and**
- our credible interval overlaps the published interval for **≥95%** of them, **and**
- global totals agree within the published uncertainty.

**Golden test 2 — G6PD deficiency.** Same structure against Howes et al. Run second; it exercises X-linked inheritance, which HbS does not.

**Calibration outputs.** These two fits set the resolution-promotion thresholds (§7) and the consanguinity-correction defaults (§9). They are calibration data, not just tests.

Failing either test blocks publication of any other variant's burden layer. The frequency and surface layers may ship independently of burden.

## 9. P3 — Burden calculation specification

**Autosomal recessive**, under Hardy–Weinberg with an inbreeding correction F:

```
carrier_freq   = 2p(1-p)(1-F)
affected_freq  = p² + F·p(1-p)
affected_count = affected_freq × births_in_cell × penetrance
```

F defaults to 0 and is overridden per region only where a published consanguinity coefficient exists, with the source recorded in `denominator_source`. **HWE is an assumption, and it is recorded as such per artifact** — the UI surfaces it on the layer info panel rather than burying it.

**Autosomal dominant:** `affected_freq = (1-(1-p)²) × penetrance`. **X-linked:** computed separately by sex using cell-level sex ratios from the population raster.

**Denominators.** Cell population from WorldPop 100m (fallback GPWv4 30 arc-second), aggregated to H3. Births = cell population × national crude birth rate (UN WPP) — no global gridded birth raster exists, and this approximation is recorded in `denominator_source`.

**Uncertainty propagation.** 500 draws from each cell's GP posterior, pushed through the expressions above, yielding mean and 2.5/97.5 percentiles. Analytic propagation is not used: the transformations are nonlinear and the posterior is not Gaussian on the frequency scale.

**Refusals — the pipeline emits no number rather than a wrong one when:**
- the cell's support is `unknown`
- no penetrance estimate exists for the variant (carrier frequency is still emitted; affected counts are not)
- no population denominator exists for the cell

## 10. P4 — Backend specification

**Read path (Cloud Run + DuckDB over parquet in GCS).** Stateless containers; DuckDB reads parquet directly from GCS with predicate/projection pushdown; artifacts are immutable so a CDN sits in front with long TTLs keyed by `model_version`.

| Endpoint | Purpose |
|---|---|
| `GET /variants/search?q=` | rsID, HGVS, gene symbol, or trait name → variant list |
| `GET /surface/{variant_id}?res=&h3_parents=` | surface cells for a viewport |
| `GET /burden/{variant_id}?res=&h3_parents=&metric=` | burden cells for a viewport |
| `GET /observations/{variant_id}` | the points layer (whole genome, always available) |
| `POST /aggregate` | `{geometry, variant_id, metric, statistic}` → sum \| mean \| per-capita \| per-sq-mile over an arbitrary polygon or admin unit |

Viewport requests are keyed by H3 parent cells, so "render only what's needed at this resolution" is a predicate, not a tiling service.

**Batch path (BigQuery).** Ingest and normalisation; the per-variant INLA fits (containerised, orchestrated as a job array); H3 rollups; admin-unit precomputation against GADM. Nothing on the interactive path touches BigQuery.

**Aggregation semantics.** `unknown` cells are excluded from every statistic and the excluded fraction is **returned with the result and displayed** — an aggregate over a region that is 70% unmapped must say so.

## 11. P5 — Map mode v1 specification

deck.gl over MapLibre GL. Layers, all independently togglable, never blended:

- **Observations** — `ScatterplotLayer`, radius = sampling extent, opacity = sample size. Always available, whole genome.
- **Surface** — `H3HexagonLayer` coloured by `post_mean`, resolution selected per frame from viewport scale (the same pattern hg-horizon-web already uses for its bp-per-pixel zoom pyramid).
- **Uncertainty** — toggle between colouring by `post_mean` and colouring by `post_sd`; the two-panel comparison is the default for first-time views of any surface.
- **Data support** — hatched overlay for `unknown`, on by default and requiring an explicit click to hide.
- **Burden** — `H3HexagonLayer` on the burden artifact, metric selector (carrier/affected × count/frequency).
- **Admin aggregation** — country / province choropleth from precomputed GADM rollups, statistic selector (sum, mean, per-capita, per-sq-mile).

**Region selection.** Rectangle, circle, and lasso via `@deck.gl/editable-layers`; the drawn geometry posts to `/aggregate`. Results panel shows the statistic, its CI, and the unmapped fraction.

**State in the URL.** Every view — variant, layers, viewport, metric, drawn geometry — is URL-encodable, so a finding is shareable as a link. This is the single highest-value thing Nextstrain does and it is nearly free if designed in from the start.

**Legend.** Carries the variant, the model version, the data version, the HWE assumption flag, and a link to the observations backing the surface.

## 12. Failure modes

| Failure | Detection | Behaviour |
|---|---|---|
| Population label with no coordinate | P0 validation, blocking | Ingest fails loudly; the observation is not silently dropped |
| Variant observed in <3 georeferenced populations | P2 precondition | No surface fitted; observations layer still serves it |
| INLA fit fails to converge | Per-variant job exit status | Variant excluded from the surface set; logged to a published exclusion list |
| Penetrance missing | P3 precondition | Carrier layers ship; affected-count layers do not |
| Registry version bump changes coordinates | Artifact key includes `registry_version` | Old surfaces remain valid and citable; new ones are published alongside |
| Aggregation over mostly-unmapped region | `unknown` fraction computed per request | Returned and displayed, not hidden |
| Client zooms past supported resolution | Resolution ladder is data-driven | Cells stop subdividing; the mask becomes visible. No invented detail. |

## 13. Governance

**Variant class policy for v1.** Only variants with established Mendelian inheritance or CPIC-graded pharmacogenomic function are eligible for burden rendering. Behavioural, cognitive, and anthropometric traits are ineligible — and since they are not Mendelian, v1 excludes them at no cost. The policy exists now so that P8 inherits a decision rather than reopening one.

**Population data.** Registry entries derived from HGDP, SGDP, AADR, and AFND carry provenance and, where applicable, a Biocultural Notice, per the CARE Principles. Before the repository goes public we need a stated position on whether fitted surfaces derived from indigenous-population panels are redistributable as a standalone dataset — flagged in §14, not decided here.

**Publication defaults.** Every artifact carries `model_version`, `data_version`, `registry_version`, and its assumption flags. Every map view is citable at a fixed version.

## 14. Deferred questions

Each has a named next step, not an open ended one.

1. **Redistribution of derived surfaces from indigenous-population panels.** Needs a written position before the repo goes public. Owner: @bschilder + @ctbio123 (governance framing).
2. **Consanguinity coefficient source.** Default F=0 ships; a literature-sourced regional table is a follow-up issue calibrated during §8.
3. **PGG.SNV bulk access** (977 populations — the largest free coverage gain available). Direct author outreach.
4. **23andMe collaboration.** Proposal drafted in issue #3: *k*-anonymised AF by 3-digit ZIP for a curated variant list, **or** a fitted surface with posteriors and no counts. Owner: @bschilder via founder connection.
5. **Basemap at scale.** MapLibre for v1; revisit if Places/Street View become product requirements.

## 15. Sub-project acceptance criteria

| | Done when |
|---|---|
| **P0** | Every population label across the Tier-A sources resolves to coordinates + radius + provenance; validation suite passes; registry is versioned and published |
| **P1** | Observations table built from gnomAD HGDP+1KG, AFND, AADR, GAsP, MCPS, IndiGen, and the MAP survey sets; curated variant set defined and frozen for v1 |
| **P2** | HbS and G6PD surfaces reproduce their published frequency maps; resolution-promotion thresholds calibrated; full curated set fitted with an exclusion list published |
| **P3** | **HbS parity achieved (§8)**; G6PD parity achieved; refusal conditions verified by test |
| **P4** | All endpoints serve p95 <150ms warm and <500ms cache-cold at res 4; `/aggregate` returns the unmapped fraction; batch orchestration reproducible from a clean project |
| **P5** | All six layers render; lasso aggregation works; every view is URL-round-trippable; the data-support mask is on by default |

## 16. Later phase — conversational analysis agent (P12)

A natural-language agent that accepts arbitrary user queries, reads the database, runs analyses, returns results, and composes new visualisation layers on demand.

Deferred to P12. Three boundaries are fixed **now**, because retrofitting any of them is expensive:

1. **The agent's only tool surface is the P4 read API.** No raw SQL, no direct parquet access. Every agent action therefore inherits the refusals already specified in §9 and §10 — `unknown`-cell exclusion, missing-penetrance refusal, unmapped-fraction reporting — automatically, and none of them depend on the agent's prompt being well written.
2. **The variant-class policy (§13) is enforced server-side, in the API, not in a system prompt.** An agent that can compose arbitrary layers can otherwise trivially render exactly the maps the policy forbids, and prompt-level guardrails are not a control. `/surface` and `/burden` reject ineligible variant classes regardless of caller — human, script, or agent.
3. **Agent-composed layers are artifacts, not opinions.** Any layer the agent creates is written as a versioned artifact keyed as in §5, with the generating query recorded. A map an agent drew must be exactly as citable and reproducible as one the batch pipeline drew.

Left to P12's own spec: whether the agent may fit *new* surfaces on demand — expensive, and it breaks the "no inference on the serving path" invariant that makes §5 cheap — or may only compose existing artifacts; and whether generated layers are session-private or publishable.

## 17. References

Marcus & Novembre 2017 (GGV, *Bioinformatics*) · Piel et al. 2010 (*Nat Commun*) · Piel et al. 2013 (*Lancet*) · Howes et al. (G6PD) · Novembre & Stephens 2008 (*Nat Genet*) · Petkova et al. 2016 (EEMS, *Nat Genet*) · Marcus et al. 2021 (FEEMS, *eLife*) · Battey et al. 2020 (Locator, *eLife*) · Nunes et al. 2014 (GENE[RATE], *Tissue Antigens*) · Koenig et al. 2024 (harmonised HGDP+1kGP, *Genome Research*) · Mallick et al. 2024 (AADR) · Gonzalez-Galarza et al. 2020 (AFND, *NAR*) · Nextstrain (Hadfield et al. 2018) · Full annotated review: [Discussion #4](https://github.com/bschilder/genomeOS/discussions/4) · Scored dataset assessment: [Issue #3](https://github.com/bschilder/genomeOS/issues/3)

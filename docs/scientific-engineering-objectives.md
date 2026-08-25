# Scientific objectives and engineering contracts

This is the compact contract connecting the Atlas's scientific purpose to buildable, testable
components. The design spec remains authoritative for method detail. An implementation is complete
only when its engineering output supports the stated scientific claim and its acceptance evidence.

## Scope and north-star claim

GenomeOS v1 asks: **for a curated clinically defensible variant, what was measured where, what can
be inferred between measurements, how uncertain is that inference, and what population burden can
be reported without manufacturing precision?**

The product must expose evidence and uncertainty rather than use geography as a proxy for an
individual's genotype. It must emit no estimate where data support, penetrance, or a denominator is
insufficient. HbS, G6PD, and measured carrier-screening rates are the scientific controls; a
plausible-looking map is not validation.

## Objective-to-engineering map

| Part | Scientific objective | Engineering goal and contract | Acceptance evidence |
|---|---|---|---|
| **P0 Registry** | Locate each sampled population without confusing sampling location, ancestral origin, or administrative centroid. Represent spatial uncertainty and governance provenance explicitly. | A versioned population and alias registry. Required WGS84 coordinates, `location_type`, `uncertainty_radius_km`, provenance, and biocultural notice. Source adapters implement the same typed load contract; collisions and orphan aliases are hard errors. | Every supported source label resolves exactly once. Schema, coordinate, collision, and round-trip tests pass. Registry version is reproducible from declared inputs. |
| **P1 Observations** | Preserve what was measured as allele counts and retain enough ascertainment information to estimate sampling bias. Never turn absence of evidence into zero frequency. | A frozen, schema-validated observations contract partitioned for per-variant reads. Required `ac`, `an`, coordinates, `sampling_design`, `disease_ascertainment_excluded`, `cohort_id`, source, and data version. Adapters join through P0 or provide explicit survey coordinates. | Invalid or unmapped rows fail before storage; zero-count rows survive; at least two sampling designs are present; Parquet round trips preserve the contract. |
| **P2 Surfaces** | Estimate allele-frequency surfaces while distinguishing observed, interpolated, prior-dominated, and unknown regions. Correct measurable ascertainment effects. | A pure offline fitter consuming only the P1 contract plus typed model configuration. It emits immutable H3 artifacts containing posterior summaries, support state, effective sample information, model version, and data version. No HTTP, storage, or UI dependency. | Published HbS and G6PD frequency patterns are reproduced within predeclared tolerances; calibration and posterior diagnostics pass; unsupported cells are masked and excluded. Spatial-statistics expert review remains required for the inference model. |
| **P3 Burden** | Convert supported frequency estimates into expected carriers and affected people without hiding inheritance, penetrance, denominator, or uncertainty assumptions. | Pure offline burden functions consuming P2 artifacts, versioned population denominators, inheritance configuration, penetrance evidence, and posterior draws. Outputs contain estimates, intervals, assumption flags, support/refusal status, and versions. | HbS national estimates fall inside published intervals for at least 80% of countries and intervals overlap for at least 95%; G6PD exercises X-linked logic; screening variants validate ascertainment correction; every refusal condition has a test. |
| **P4 Read API** | Make evidence and precomputed results queryable without changing or recomputing the science. Return coverage limitations with every aggregate. | A stateless adapter over immutable artifacts: variant search, observations, surfaces, burden, and polygon/admin aggregation. Variant-class policy is enforced server-side. No inference on request paths. Interfaces are versioned and bounded. | Contract tests cover every endpoint and refusal; aggregates exclude masked cells and report the excluded fraction; target p95 is <150 ms warm and <500 ms cache-cold at H3 resolution 4. |
| **P5 Map UI** | Let users distinguish measurement from inference, see uncertainty before interpretation, and share a citable view. | A client of P4 only. Separate observation, surface, uncertainty, support-mask, burden, and administrative layers. URL state includes variant, versions, viewport, layers, metric, and geometry. The support mask is on by default. | A user can select a variant, inspect evidence and uncertainty, lasso a region, see the unmapped fraction, and reproduce the same versioned view from its URL. Accessibility and visual-regression checks cover uncertainty and refusal states. |

## Cross-cutting scientific objectives

### Provenance and reproducibility

Every derived artifact is immutable and keyed by `(variant_id, model_version, data_version)`.
Configuration, seed, inputs, exclusions, and assumptions must be sufficient to reproduce it.

### Honest uncertainty and refusal

`unknown` and `prior_dominated` are scientific outputs, not errors to smooth away. They are
excluded from aggregation, and the excluded fraction travels through P4 and P5. Missing penetrance
or population denominators produce an explicit refusal rather than a guessed number.

### Ascertainment and representation

Sampling design and cohort effects are modeled from recorded fields, never inferred from broad
population labels. Continental genetic-analysis groups are not geography, race, ethnicity, or
nationality. The clinical-testing-intensity layer distinguishes an unobserved variant from an
unstudied region.

### Governance

Access terms and CARE-aligned notices are part of the data contract. Restricted data may inform a
model only within its permitted environment and may not be exported. The unresolved policy on
redistributing surfaces derived from indigenous-population panels blocks public release.

## Engineering composition rules

The dependency direction is:

```text
source adapters -> P0/P1 contracts -> pure P2 -> pure P3 -> immutable artifacts -> P4 -> P5
```

- Modules exchange validated, versioned data contracts. They do not reach into another module's
  private implementation.
- Scientific functions accept data and typed configuration explicitly and return data. Storage,
  networks, command-line parsing, and HTTP live in thin adapters.
- Defaults may tune engineering behavior, such as batch size or cache size. Scientific assumptions,
  governance policy, coordinates, ascertainment, penetrance, and refusal thresholds must be explicit
  and versioned.
- The Pan-UKB evidence API is a parallel evidence layer. Its associations may annotate variants, but
  continental analysis groups must never be passed into P0 as geographic observations.
- P6–P12 and real-time fitting remain deferred. Their future interfaces must consume the stable read
  API and immutable artifacts rather than couple to fitting internals.

## Required verification

Every change runs `python scripts/smoke.py` plus focused tests. Schema changes also regenerate and
check frozen contracts. Before commit or push, `python scripts/check_private_files.py` must pass.
Before merge, run the full lint, contract, test, module-size, and privacy checks documented in
`AGENTS.md`.

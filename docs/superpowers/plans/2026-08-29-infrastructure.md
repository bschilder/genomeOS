# GenomeOS infrastructure delivery plan

**Date:** 2026-08-29  
**Scope:** Atlas P4 infrastructure and the production boundary required by P5  
**Issues:** #33, #49, #50, #51, #52, #53, #54  
**Design authority:** `docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md`
§5, §6, §10, §13, §16

## 1. Delivery claim

Deploy a bounded, read-only Atlas service that lets the map search for an eligible variant,
request only the observation, surface, and burden cells needed for a viewport, and aggregate an
arbitrary region without performing inference or hiding unsupported geography.

The M3 acceptance journey is:

1. open the map in a browser;
2. select a variant;
3. render observations separately from inferred surface and burden layers;
4. draw a region;
5. receive a versioned aggregate with its excluded/unmapped fraction; and
6. reproduce the view from the same immutable artifact versions.

This plan does not declare the science publishable. P2/P3 validation and the governance decision
on redistribution remain independent release gates.

## 2. Non-negotiable properties

- The serving path performs no fitting, imputation, or other scientific inference.
- Observations, surfaces, and burden remain separate artifacts and API resources.
- Artifacts are immutable and addressed by variant, model version, and data version.
- `unknown` and `prior_dominated` cells never contribute to an aggregate. The response reports
  both the excluded cell fraction and, where population denominators exist, the excluded
  population fraction.
- Surface and burden endpoints enforce variant-class eligibility for every caller.
- Every list or viewport response is bounded. There is no arbitrary SQL or bulk-matrix REST API.
- A production service account has read-only access to published artifacts and no permission to
  mutate them.
- Logs contain request and artifact metadata, never authorization headers, cookies, raw controlled
  data, or user-drawn geometry at full precision.

## 3. Current baseline

The repository already has:

- a FastAPI service and Cloud Run template;
- local DuckDB reads with projection, bounding-box predicates, and row limits;
- `/ready`, `/v1/atlas/variants`, `/v1/atlas/observations`, and `/v1/atlas/surface`;
- a synthetic diagnostic preview;
- immutable per-variant surface artifacts for HbS and G6PD; and
- request-completion logging and basic refusal tests.

The current vertical slice is not a production path because it defaults to synthetic local
artifacts, the published artifact format is not the catalog format, GCS is not wired to DuckDB,
the Cloud Run template has unresolved placeholders, and search, burden, aggregation, caching,
performance evidence, and deployment evidence are incomplete.

## 4. Target architecture

```text
offline sources
    -> deterministic build/fitting jobs
    -> validation and publication gate
    -> immutable versioned Parquet + manifest in GCS
    -> optional resolution/admin rollups
    -> CDN for cacheable versioned reads
    -> Cloud Run FastAPI + DuckDB read adapter
    -> MapLibre/deck.gl client

Cloud SQL remains the Pan-UKB metadata store. BigQuery is batch-only. Neither is allowed to become
an inference path or a requirement for reading an otherwise healthy Atlas artifact catalog unless
a documented metadata contract requires it.
```

## 5. Work sequence

### Phase 0 — freeze contracts and decisions

Before infrastructure code changes:

1. Define one manifest contract for local, CI, GCS, and CDN-backed artifact sets. It must include
   schema, artifact, registry, data, and model versions; creation time; assumptions; eligibility;
   object checksums; and observation/surface/burden locations.
2. Define stable response models for search, observations, surfaces, burden, aggregate results,
   refusals, and version metadata.
3. Decide whether Atlas readiness is independent of Cloud SQL. The preferred boundary is separate
   readiness components so a Pan-UKB database outage does not hide healthy immutable Atlas data.
4. Define cache keys and URL version semantics before a CDN is introduced.
5. Record the governance owner and approval evidence required before a catalog becomes public.

**Exit gate:** frozen JSON schemas and contract tests describe every P4 request, response, and
refusal used by P5.

### Phase 1 — publish immutable artifacts to GCS (#33)

1. Create separate staging and published prefixes or buckets.
2. Publish to a temporary staging prefix, verify schema and checksums, then create the immutable
   published manifest as the final operation.
3. Refuse overwrite when a key already exists.
4. Pin every catalog to explicit registry, data, and model versions.
5. Add inventory verification and a restore/read test from a clean environment.
6. Give the runtime service account object-viewer access only; give the publisher a separate,
   narrowly scoped identity.

**Exit gate:** a clean machine can resolve a pinned manifest, verify every object, and read it
without repository-local data files.

### Phase 2 — production artifact adapter and service (#49)

1. Replace the local-path-only assumption with an artifact-store interface having local and GCS
   implementations.
2. Configure DuckDB's GCS access explicitly and prove projection and predicate pushdown.
3. Keep one catalog/connection lifecycle per container where safe; bound memory, concurrency,
   request time, and scanned bytes.
4. Separate liveness from component readiness. Readiness reports artifact and database component
   state without leaking connection or object details.
5. Parameterize the Cloud Run service, artifact root, project, region, service account, Cloud SQL
   attachment, image digest, minimum/maximum instances, concurrency, timeout, and resource limits.
6. Add CORS allowlisting for the deployed map origin, structured logs, request IDs, latency and
   error metrics, and alerts for readiness failures, elevated 5xx, and latency-budget violations.

**Exit gate:** a deployed revision reads a pinned GCS catalog using least privilege and passes live
HTTP smoke tests without local artifact files.

### Phase 3 — complete bounded read endpoints (#50, #54)

Implement the versioned contracts for:

- variant search by canonical identifier and supported metadata;
- observations for a variant;
- surface cells by resolution and H3 parents;
- burden cells by resolution, H3 parents, and metric; and
- artifact/catalog version discovery needed to reproduce a URL.

All endpoints must have request-size, row-count, H3-parent-count, and execution-time limits.
Surface and burden eligibility is checked server-side before object reads. Responses identify
artifact, registry, data, and model versions and the relevant assumptions.

**Exit gate:** contract tests cover success, unknown variants, ineligible variants, partial or
invalid viewports, excessive requests, unavailable artifacts, and version pinning.

### Phase 4 — region aggregation (#51)

1. Accept GeoJSON polygon/multipolygon or a supported admin-unit identifier.
2. Validate geometry type, coordinates, vertex count, area, and payload size before spatial work.
3. Resolve intersecting H3 cells and compute only the allowed statistics: sum, mean, per-capita,
   and per-area where their denominators are defined.
4. Exclude `unknown` and `prior_dominated` cells and return exclusion counts/fractions alongside
   mapped denominator coverage and uncertainty intervals.
5. Return no estimate, with a typed reason, when coverage or a required denominator is absent.
6. Test antimeridian, polar, empty, invalid, self-intersecting, entirely unmapped, and
   mostly-unmapped geometries.

**Exit gate:** a lasso request used by P5 returns a reproducible aggregate and makes a 70%-unmapped
region visibly 70% unmapped.

### Phase 5 — resolution ladder and caching (#52)

1. Produce deterministic shards keyed by variant, artifact versions, H3 resolution, and H3 parent.
2. Ensure zooming cannot request a scientific resolution finer than the artifact supports.
3. Set immutable cache headers only on version-pinned responses. Mutable catalog aliases use short
   TTLs or revalidation.
4. Put CDN keys, invalidation rules, compression, and content type under tests.
5. Benchmark representative sparse, dense, warm, and cache-cold requests.

**Exit gate:** resolution-4 reads meet p95 below 150 ms warm and 500 ms cache-cold under a recorded
load profile, with scanned bytes and response sizes reported.

### Phase 6 — reproducible batch orchestration (#53)

1. Containerize ingestion, normalization, per-variant fitting, H3 rollups, and GADM precomputation
   as separate deterministic jobs.
2. Use BigQuery only for batch inputs/intermediates that benefit from it; interactive reads never
   query BigQuery.
3. Make every job idempotent by version key, seed stochastic work with `SEED = 42`, and record image
   digest, inputs, configuration, checksums, and validation results.
4. Fail publication when schemas, scientific validation, privacy, governance, or inventory checks
   fail.
5. Add retry and resume semantics that cannot overwrite a published artifact.

**Exit gate:** a clean project can rebuild, validate, publish, and serve a fixture catalog through
one documented pipeline without manual mutation.

### Phase 7 — production hardening and P5 handoff

1. Run dependency, container, secret, IAM, and tracked-file privacy checks in CI.
2. Pin production images by digest and retain rollback-ready revisions.
3. Document backup/restore, incident response, artifact withdrawal without mutation, rollback,
   cost budgets, quotas, and ownership.
4. Publish an OpenAPI snapshot and generated client contract for P5.
5. Run the M3 browser journey against production-like infrastructure.

**Exit gate:** the map team can implement all required layers and URL state using P4 only, and an
operator can deploy, observe, roll back, and restore the service from repository documentation.

## 6. Verification matrix

| Concern | Required evidence |
|---|---|
| Immutability | overwrite-refusal test, checksummed manifest, version-pinned URL |
| Scientific boundary | test proving no fitter/model dependency is imported or called by P4 |
| Refusals | contract tests for ineligible, unsupported, missing-denominator, and unmapped cases |
| Geometry | property and regression tests including antimeridian and invalid polygons |
| Performance | versioned load-test script, environment description, p50/p95/p99, scanned bytes |
| Security | least-privilege IAM review, secret scan, CORS test, bounded-input tests |
| Privacy | repository privacy gate plus log-redaction tests |
| Reliability | liveness/readiness tests, rollback exercise, GCS read failure behavior |
| Reproducibility | clean-project fixture build and immutable publication proof |
| Client contract | OpenAPI snapshot and end-to-end M3 browser journey |

The standard repository gates remain mandatory:

```bash
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python scripts/smoke.py
pytest
```

## 7. Ownership and sequencing

Issues #33 and #49–#53 are currently assigned to `@JirachiWishmaster`; #54 is assigned to
`@bschilder`. Work from this branch should be coordinated through those issues rather than
silently replacing their implementation. The first proposed PR should contain this plan and any
contract-only decisions accepted by the issue owners. Implementation PRs should be small and
issue-scoped in the phase order above.

The recommended first implementation slice is Phase 0 plus a fixture-backed local/GCS artifact
store contract. It unblocks deployment work without coupling the service to unfinished search,
burden, aggregation, or UI code.

## 8. Explicitly deferred

- real-time fitting or model execution on request paths;
- arbitrary SQL and bulk genome-wide exports;
- P5 component implementation;
- P6+ time, globe, polygenic, chromosome, chromatin, upload, and agent products;
- public release before the redistribution/governance decision is recorded; and
- replacing the scientific validation gates with infrastructure smoke tests.

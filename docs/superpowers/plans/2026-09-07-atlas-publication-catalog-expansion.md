# Atlas Publication and Catalog Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a fail-closed 30-map browser catalog with immutable downloads, cacheable external variant annotations, finite request deadlines, and a WorldPop-backed target grid that includes supported small islands.

**Architecture:** Offline Python code owns scientific publication, target-cell selection, source validation, checksums, and external-cache normalization. The static TypeScript provider only validates and reads those published capabilities; surface-only artifacts remain a first-class state rather than pretending to contain zero observations. Hugging Face is the temporary immutable origin and the `AtlasDataProvider` boundary preserves the later GCP migration.

**Tech Stack:** Python 3.12, pandas, pyarrow, rasterio, H3, pytest, Astro 7.3.1, TypeScript 6.0.3, Zod 4.5.4, Vitest 5.0.0, Hugging Face Hub.

**Spec:** `docs/superpowers/specs/2026-09-07-cesium-explorer-interaction-design.md`

## Global Constraints

- Cite Atlas design §5, §6, §7, §9, or §11 in every new production-module docstring, according to responsibility.
- No inference runs in the browser, website build, API read path, or external-annotation provider.
- Observations and inferred surfaces remain separate payloads and capabilities.
- Missing WorldPop coverage, population conflicts, identifiers, versions, checksums, or required provenance are hard errors.
- `uncertainty_radius_km`, ascertainment fields, study identity, rsID, and normalized variant IDs receive no defaults.
- WorldPop-positive cells and retained observation cells are predicted from saved fits offline and published under new immutable artifact identities.
- Natural Earth remains geographic context only; it is not a scientific target-grid fallback.
- The public catalog contains exactly 2 MAP entries and 28 AFND surface-only entries for this release.
- The 28 AFND entries expose no browser observations until PR #160 is merged and a new validated observation export is built.
- A missing standalone licence statement is recorded as `no_restriction_found`, not treated as a veto; explicit restrictions still govern use.
- Cached gnomAD/dbSNP payloads are contextual annotations and never alter genomeOS observations or surfaces.
- The browser receives no Hugging Face, Cesium, GCP, gnomAD, or NCBI write credential.
- Static catalog and artifact requests fail visibly after 15 seconds and preserve caller cancellation.
- Run `python scripts/smoke.py` after every code, configuration, schema, dependency, or runtime change.
- Before each commit, run `python scripts/check_private_files.py` and inspect `git diff --cached --name-only`.

---

### Task 1: Finish surface-only and timeout contracts

**Files:**

- Modify: `website/src/atlas/contracts.ts`
- Modify: `website/src/atlas/provider.ts`
- Modify: `website/src/atlas/static-provider.ts`
- Modify: `website/tests/atlas-contracts.test.ts`
- Modify: `website/tests/atlas-provider.test.ts`
- Modify: `scripts/export_atlas_web.py`
- Modify: `tests/test_export_atlas_web.py`

**Interfaces:**

- Consumes: schema-version 1 static catalog and optional caller `AbortSignal`.
- Produces: `ArtifactRef` discriminated by `observations_available`, `AtlasCatalog.registry_versions: string[]`, browser observations with required `study_id`/`study_label`, and `getObservations(ref, signal): Promise<ObservationArtifact | null>`.

- [ ] **Step 1: Add the failing surface-only and timeout tests**

```ts
it("does not request an unavailable observation payload", async () => {
  const provider = new StaticAtlasDataProvider("/data/atlas/", 50);
  const ref = surfaceOnlyArtifactRef();
  globalThis.fetch = vi.fn();
  await expect(provider.getObservations(ref)).resolves.toBeNull();
  expect(globalThis.fetch).not.toHaveBeenCalled();
});

it("turns a stalled catalog into a finite error", async () => {
  vi.useFakeTimers();
  globalThis.fetch = vi.fn(
    (_url, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
  ) as typeof fetch;
  const result = new StaticAtlasDataProvider("/data/atlas/", 25).getCatalog();
  await vi.advanceTimersByTimeAsync(25);
  await expect(result).rejects.toThrow("timed out after 25 ms");
});

it("requires stable study identity for browser observations", () => {
  expect(() =>
    observationSchema.parse({ ...validObservation(), study_id: undefined }),
  ).toThrow();
  expect(() =>
    observationSchema.parse({ ...validObservation(), study_label: "" }),
  ).toThrow();
});
```

- [ ] **Step 2: Run the focused tests and confirm the old contract fails**

Run: `cd website && npm test -- atlas-contracts.test.ts atlas-provider.test.ts`

Expected: FAIL because the old catalog requires observation URLs and has no request deadline.

- [ ] **Step 3: Implement the discriminated contract and deadline**

Use this exact public provider signature:

```ts
export type AtlasDataProvider = {
  getCatalog(signal?: AbortSignal): Promise<AtlasCatalog>;
  getSurface(ref: ArtifactRef, signal?: AbortSignal): Promise<SurfaceArtifact>;
  getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<ObservationArtifact | null>;
};
```

`StaticAtlasDataProvider.#getJson` must combine a 15,000 ms internal deadline with caller cancellation, distinguish timeout errors from caller aborts, remove the forwarded listener in `finally`, and cache only successfully validated payloads.

- [ ] **Step 4: Make the exporter emit matching catalog fields**

For each entry, emit `observations_available`, nullable observation URL/hash fields, and add every per-variant registry version to a sorted top-level `registry_versions` array. Reject `observation_source: null` if the allowlist nevertheless supplies any observation download metadata.

For MAP HbS, export `study_id` from the adapter's validated `cohort_id` and `study_label` from the non-empty source-native `source` accession. For MAP G6PD, export `study_id` from validated `cohort_id` and `study_label` from its non-empty source citation. Reject missing or blank values; do not synthesize either field from geography, row order, or free-form browser logic.

- [ ] **Step 5: Run the focused suites**

Run:

```bash
python -m pytest tests/test_export_atlas_web.py -q
cd website && npm test -- atlas-contracts.test.ts atlas-provider.test.ts
```

Expected: all selected tests PASS.

- [ ] **Step 6: Commit the contract slice**

```bash
git add scripts/export_atlas_web.py tests/test_export_atlas_web.py website/src/atlas/contracts.ts website/src/atlas/provider.ts website/src/atlas/static-provider.ts website/tests/atlas-contracts.test.ts website/tests/atlas-provider.test.ts
python scripts/check_private_files.py
git diff --cached --name-only
git commit -m "feat: support surface-only Atlas artifacts (#55)"
```

### Task 2: Make population-backed publication targets explicit

**Files:**

- Modify: `genomeos/geo/population.py`
- Modify: `genomeos/surfaces/artifacts.py`
- Modify: `tests/test_population.py`
- Modify: `tests/test_artifacts.py`
- Create: `tests/test_publish_artifacts.py`
- Modify: `scripts/publish_artifacts.py`
- Create: `scripts/build_population_grid.py`
- Create: `tests/fixtures/worldpop_small_islands.csv`

**Interfaces:**

- Consumes: `PopulationGrid.cells` with `h3_index` and `population`, a pinned source/version string, and retained observation coordinates.
- Produces: `publication_target_cells(population_grid, observation_cells) -> list[str]`, a reproducible population-grid CLI, and artifact-format 2 manifests carrying the target-grid source/version.

- [ ] **Step 1: Create a readable small-island fixture**

The fixture contains verified H3-resolution-3 cells `835494fffffffff` for Praia/Cabo Verde and `833f30fffffffff` for Malta with positive population, plus `835969fffffffff` as a valid zero-population conflict fixture. Store `h3_index,population,source,source_version`; represent nodata by omitting its cell, as the production aggregator does.

- [ ] **Step 2: Write the failing grid tests**

```python
def test_publication_grid_keeps_populated_islands_and_observation_cells() -> None:
    grid = PopulationGrid(
        cells=pd.DataFrame(
            {
                "h3_index": ["835494fffffffff", "833f30fffffffff"],
                "population": [1.0, 2.0],
            }
        ),
        resolution=3,
        source=WORLDPOP_SOURCE,
        source_version="2020-unconstrained-v1",
        pixels_counted=2,
        pixels_nodata=0,
        coverage_stride=16,
    )
    assert publication_target_cells(grid, ["835494fffffffff"]) == ["833f30fffffffff", "835494fffffffff"]


def test_publication_grid_refuses_observation_in_zero_population_cell() -> None:
    grid = island_fixture_grid()
    with pytest.raises(ValueError, match="zero population"):
        publication_target_cells(grid, ["835969fffffffff"])
```

Also test an observation cell absent from coverage, a mismatched H3 resolution, duplicate population cells, and a blank source version.

- [ ] **Step 3: Run the tests and verify the helper is absent**

Run: `python -m pytest tests/test_population.py -q`

Expected: FAIL because `publication_target_cells` and `source_version` do not exist.

- [ ] **Step 4: Implement the target-grid contract**

```python
def publication_target_cells(
    population_grid: PopulationGrid,
    observation_cells: Iterable[str],
) -> list[str]:
    """Select versioned WorldPop-positive targets and refuse denominator conflicts (§7, §9)."""
```

Validate unique H3 indices, finite non-negative population, non-empty source/version, and matching resolution. Return the sorted union of positive-population cells and observation cells only after proving each observation cell has coverage and positive population.

- [ ] **Step 5: Add a reproducible population-grid command**

```python
def build_population_grid(
    raster: Path,
    out: Path,
    *,
    resolution: int,
    source_version: str,
) -> PopulationGrid:
    grid = aggregate_raster_to_h3(
        raster,
        resolution,
        source_version=source_version,
    )
    grid.cells.assign(
        source=grid.source,
        source_version=grid.source_version,
    ).to_parquet(out, index=False)
    return grid
```

The CLI accepts `--raster`, `--out`, `--resolution`, and required `--source-version`. It writes a checksum-bearing `.parquet.manifest.json` sidecar containing resolution, source, version, pixel counts, nodata count, and coverage stride. It refuses either existing output unless `--overwrite` is explicitly supplied and prints cell count, total population, source, version, and output SHA-256.

- [ ] **Step 6: Replace `h3_land_cells` in the artifact publisher**

Add required CLI arguments `--population-cells`, `--population-source`, and `--population-version`. Load the table, map every retained observation through `h3.latlng_to_cell`, call `publication_target_cells`, and assert after `cell_table` that every observation cell appears in the emitted frame. Do not keep a code path that silently falls back to `h3_land_cells`.

- [ ] **Step 7: Record the target grid in artifact format 2**

Add required `target_grid_source` and `target_grid_version` fields to `ArtifactManifest` and bump new writes to artifact format 2. `read()` continues to read frozen format-1 artifacts but never supplies invented target-grid values for them. The web exporter requires both fields from format-2 manifests.

- [ ] **Step 8: Prove immutability**

Add a test that publishes the original identity, attempts the WorldPop-backed publication with the same identity and gets `FileExistsError`, then succeeds under a new model version while leaving both directories byte-readable.

- [ ] **Step 9: Run the publication tests and smoke**

Run:

```bash
python -m pytest tests/test_population.py tests/test_artifacts.py tests/test_publish_artifacts.py -q
python scripts/smoke.py
```

Expected: PASS; the fixture names both Cabo Verde and Malta in assertion messages.

- [ ] **Step 10: Commit the target-grid slice**

```bash
git add genomeos/geo/population.py genomeos/surfaces/artifacts.py scripts/build_population_grid.py scripts/publish_artifacts.py tests/test_population.py tests/test_artifacts.py tests/test_publish_artifacts.py tests/fixtures/worldpop_small_islands.csv
python scripts/check_private_files.py
git diff --cached --name-only
git commit -m "fix: publish surfaces over populated islands (#55)"
```

### Task 3: Expand metadata and allowlist to 30 maps

**Files:**

- Modify: `data/store/catalog-metadata.json`
- Modify: `website/src/atlas/public-artifacts.json`
- Modify: `tests/test_export_atlas_web.py`
- Modify: `scripts/sync_store.py`
- Modify: `docs/hf-dataset-card.md`

**Interfaces:**

- Consumes: 30 immutable manifest directories under `data/store/artifacts` and the approved Issue #66 reuse decision.
- Produces: exactly 30 unique allowlist entries with per-entry registry version, human label, entity type, measurement, assumptions, and nullable observation source.

- [ ] **Step 1: Write the failing catalog inventory test**

```python
def test_public_catalog_inventory_has_two_map_and_twenty_eight_afnd_entries() -> None:
    allowlist = json.loads(ALLOWLIST.read_text())
    entries = allowlist["artifacts"]
    assert len(entries) == 30
    assert sum(entry["observation_source"] is not None for entry in entries) == 2
    assert len({entry["id"] for entry in entries}) == 30
    assert {entry["variant_id"].split(":", 1)[0] for entry in entries} == {
        "chr11-5227002-T-A",
        "phenotype",
        "cyt",
        "hla",
        "kir",
    }
```

- [ ] **Step 2: Run the test and confirm the current two-entry failure**

Run: `python -m pytest tests/test_export_atlas_web.py::test_public_catalog_inventory_has_two_map_and_twenty_eight_afnd_entries -q`

Expected: FAIL with `2 != 30`.

- [ ] **Step 3: Add all manifest-backed entries**

Use each manifest's literal `variant_id`, `model_version`, `data_version`, and measurement. Add 4 cytokine, 20 HLA, and 4 KIR entries with `observation_source: null` and the adapter's literal `registry_version: afnd-2026-08`. Do not derive study identity or browser observations from artifact counts.

- [ ] **Step 4: Correct interim-storage policy text**

Update `scripts/sync_store.py` and `docs/hf-dataset-card.md` so they say the dataset is public, AFND surfaces are publishable under Issue #66 with attribution/Biocultural Notices/explicit restrictions preserved, and GCP remains the intended storage/serving destination. Remove the obsolete statement that `private=True` is required.

- [ ] **Step 5: Validate metadata against every manifest**

Run:

```bash
python -m pytest tests/test_export_atlas_web.py -q
python scripts/sync_store.py status
```

Expected: every allowlist entry resolves to one immutable manifest; the Hub status reports the public dataset without changing remote state.

- [ ] **Step 6: Commit the catalog inventory**

```bash
git add data/store/catalog-metadata.json website/src/atlas/public-artifacts.json scripts/sync_store.py docs/hf-dataset-card.md tests/test_export_atlas_web.py
python scripts/check_private_files.py
git diff --cached --name-only
git commit -m "feat: publish thirty Atlas map choices (#55)"
```

### Task 4: Publish immutable WorldPop-backed artifacts

**Files:**

- Modify: `data/store/INVENTORY.json`
- Create: new immutable directories under `data/store/artifacts/`
- Modify: `website/src/atlas/public-artifacts.json`
- Test: `tests/test_artifacts.py`

**Interfaces:**

- Consumes: pinned WorldPop 2020 unconstrained raster, saved MAP/AFND fits, validated source tables, and Task 2's publication target.
- Produces: 30 new immutable surface directories, each with `cells.parquet` and `manifest.json`, plus an inventory recording source URL, SHA-256, target-grid version, command, and artifact identity.

- [ ] **Step 1: Fetch and checksum WorldPop outside Git**

Run:

```bash
python scripts/fetch_worldpop.py --year 2020 --out data/raw/worldpop_1km_2020.tif
sha256sum data/raw/worldpop_1km_2020.tif
```

Expected: a finite raster with a recorded checksum. If download or checksum validation fails, stop publication; do not substitute Natural Earth.

- [ ] **Step 2: Aggregate the target grid**

Run:

```bash
python scripts/build_population_grid.py --raster data/raw/worldpop_1km_2020.tif --out data/store/worldpop-res3-2020.parquet --resolution 3 --source-version 2020-unconstrained-v1
```

Expected: the output has unique cells, finite population values, and positive population for Cabo Verde cell `835494fffffffff`.

- [ ] **Step 3: Republish MAP artifacts under new identities**

Run:

```bash
python scripts/publish_artifacts.py --fits data/store/fits --out data/store/artifacts --hbs data/raw/map_hbs_surveys.csv --g6pd data/raw/map_g6pd_surveys.csv --population-cells data/store/worldpop-res3-2020.parquet --population-source worldpop-1km-unconstrained --population-version 2020-unconstrained-v1 --h3-res 3 --model-version v2 --data-version map-2026-08
```

Expected: two new format-2 artifacts; the format-1 directories remain untouched.

- [ ] **Step 4: Republish AFND artifacts under new identities**

Run:

```bash
python scripts/publish_artifacts.py --fits data/store/screen_v2 --out data/store/artifacts --afnd data/raw/afnd_frequencies.tsv --afnd-populations data/raw/afnd_populations.tsv --cytokines --kir --min-populations 30 --population-cells data/store/worldpop-res3-2020.parquet --population-source worldpop-1km-unconstrained --population-version 2020-unconstrained-v1 --h3-res 3 --model-version v3 --data-version afnd-2026-08
```

Expected: 28 new format-2 artifacts. A missing fit aborts the release because the catalog inventory must stay at exactly 30 entries.

- [ ] **Step 5: Verify island and observation-cell coverage**

Run a test that loads both MAP artifacts and asserts every source observation's H3 cell is present. Assert at least one emitted Cabo Verde cell has a literal model support state and posterior summaries produced by `cell_table`; never accept a copied neighboring value.

- [ ] **Step 6: Update the immutable inventory and allowlist**

Record each new directory and SHA-256 in `data/store/INVENTORY.json`. Point all 30 allowlist entries at the new directories. Keep the old directories intact.

- [ ] **Step 7: Sync the new artifacts to Hugging Face**

Add `data/store/worldpop-res3-2020.parquet` to `SYNCED`, then run:

```bash
python scripts/sync_store.py push --dry-run
python scripts/sync_store.py push
python scripts/sync_store.py status
```

Expected: the dry run names only approved sync roots; the final status shows the new immutable artifacts. Record the resulting Hub revision in the allowlist before export.

- [ ] **Step 8: Commit publication metadata, not raw source credentials**

```bash
git add data/store/INVENTORY.json data/store/worldpop-res3-2020.parquet data/store/artifacts website/src/atlas/public-artifacts.json scripts/sync_store.py
python scripts/check_private_files.py
git diff --cached --name-only
git commit -m "data: publish WorldPop-backed Atlas surfaces (#55)"
```

### Task 5: Cache verified gnomAD and dbSNP context

**Files:**

- Create: `genomeos/external/variant_info.py`
- Create: `genomeos/external/__init__.py`
- Create: `scripts/cache_external_variant_info.py`
- Create: `tests/test_external_variant_info.py`
- Create: `tests/fixtures/gnomad_rs334.json`
- Create: `tests/fixtures/dbsnp_rs334.json`
- Modify: `scripts/sync_store.py`
- Modify: `website/src/atlas/public-artifacts.json`

**Interfaces:**

- Consumes: only explicit catalog capabilities `{source, normalized_variant_id|rsid, dataset}`.
- Produces: `normalize_gnomad(payload, request) -> dict`, `normalize_dbsnp(payload, request) -> dict`, and versioned cache files under `data/store/external/`.

- [ ] **Step 1: Add representative source fixtures and failing normalization tests**

```python
def test_gnomad_cache_preserves_verified_request_identity() -> None:
    normalized = normalize_gnomad(
        json.loads(GNOMAD_FIXTURE.read_text()),
        GnomadRequest(variant_id="11-5227002-T-A", dataset="gnomad_r4"),
    )
    assert normalized["source"] == "gnomad"
    assert normalized["normalized_variant_id"] == "11-5227002-T-A"
    assert normalized["dataset"] == "gnomad_r4"


def test_cache_refuses_identifier_mismatch() -> None:
    with pytest.raises(ValueError, match="identifier mismatch"):
        normalize_dbsnp(json.loads(DBSNP_FIXTURE.read_text()), DbsnpRequest(rsid="rs1"))
```

Also reject remote error objects, non-finite frequencies, a different reference allele, missing release metadata, and any unrecognized response shape.

- [ ] **Step 2: Run the tests and verify the module is absent**

Run: `python -m pytest tests/test_external_variant_info.py -q`

Expected: FAIL on import.

- [ ] **Step 3: Implement narrow source normalizers**

Use frozen request dataclasses. Return only reviewed fields: request identity, source/release, alleles, available aggregate frequency summaries, source URL, retrieved UTC timestamp, and raw-payload SHA-256. Do not store a whole remote response when only a small stable contract is used.

- [ ] **Step 4: Implement deterministic maintenance fetches**

`scripts/cache_external_variant_info.py` must enumerate allowlist capabilities, query gnomAD GraphQL and NCBI RefSNP with finite connect/read timeouts, validate before write, and use canonical sorted JSON. It refuses phenotype, HLA, KIR, cytokine-label, or unresolved identifiers. For this release only HbS advertises `gnomad` and `dbsnp` capabilities.

- [ ] **Step 5: Sync and pin the cache**

Add `data/store/external` to `SYNCED`, run the script for `hbs-rs334`, push through `scripts/sync_store.py`, and update the allowlist's `hf_revision` plus capability cache paths. Never place `HF_TOKEN` in an argument, tracked file, or output.

- [ ] **Step 6: Run focused tests and commit**

```bash
python -m pytest tests/test_external_variant_info.py -q
git add genomeos/external scripts/cache_external_variant_info.py scripts/sync_store.py tests/test_external_variant_info.py tests/fixtures/gnomad_rs334.json tests/fixtures/dbsnp_rs334.json website/src/atlas/public-artifacts.json
python scripts/check_private_files.py
git diff --cached --name-only
git commit -m "feat: cache verified variant context (#55)"
```

### Task 6: Export downloads, capabilities, and the final static catalog

**Files:**

- Modify: `scripts/export_atlas_web.py`
- Modify: `tests/test_export_atlas_web.py`
- Modify: `website/src/atlas/contracts.ts`
- Modify: `website/tests/atlas-contracts.test.ts`
- Regenerate: `website/public/data/atlas/catalog.json`
- Regenerate: `website/public/data/atlas/*.surface.json`
- Regenerate: `website/public/data/atlas/*.observations.json`
- Create: `website/public/data/atlas/*.manifest.json`
- Create: `website/public/data/atlas/external/*.json`

**Interfaces:**

- Consumes: allowlist, immutable surface manifests/parquets, two MAP observation tables, and validated external cache objects.
- Produces: `ArtifactDownloads`, `ExternalResource[]`, 30 lazily loadable artifacts, and checksum-bearing URLs under `/data/atlas/`.

- [ ] **Step 1: Write the failing download/capability tests**

```python
def test_export_emits_downloads_and_only_verified_external_capabilities(tmp_path: Path) -> None:
    export_test_catalog(tmp_path)
    catalog = json.loads((tmp_path / "web/catalog.json").read_text())
    hbs = next(item for item in catalog["artifacts"] if item["id"] == "hbs-rs334")
    g6pd = next(item for item in catalog["artifacts"] if item["id"] == "g6pd-deficiency")
    assert set(hbs["downloads"]) == {"surface", "observations", "manifest"}
    assert {item["source"] for item in hbs["external_resources"]} == {"gnomad", "dbsnp"}
    assert g6pd["external_resources"] == []
    assert g6pd["downloads"]["observations"] is not None
```

Add an AFND assertion that its observation download is `null`, and reject a capability missing its verified literal identifier.

- [ ] **Step 2: Run Python and TypeScript contract tests and confirm failure**

Run:

```bash
python -m pytest tests/test_export_atlas_web.py -q
cd website && npm test -- atlas-contracts.test.ts
```

Expected: FAIL because downloads and external resources are not yet in schema version 1.

- [ ] **Step 3: Extend the strict Python and Zod contracts**

Define `DownloadRef` as `{url, media_type, sha256, label}`. Define external resources as a discriminated union where gnomAD requires verified GRCh38 `normalized_variant_id`, dataset, and cache URL; dbSNP requires `rsid` matching `^rs[1-9][0-9]*$` and a cache URL.

- [ ] **Step 4: Export canonical manifest and cache payloads**

Copy normalized manifest metadata—not local file paths—into one JSON per artifact. Recompute SHA-256 from every emitted browser file and fail when a declared checksum disagrees. Keep the external cache out of catalog readiness.

- [ ] **Step 5: Generate and validate all public files**

Run:

```bash
python scripts/export_atlas_web.py --store data/store --hbs-csv data/raw/map_hbs_surveys.csv --g6pd-csv data/raw/map_g6pd_surveys.csv --allowlist website/src/atlas/public-artifacts.json --out website/public/data/atlas
python -m pytest tests/test_export_atlas_web.py -q
cd website && npm test -- atlas-contracts.test.ts atlas-provider.test.ts
```

Expected: catalog validates, contains 30 entries, and emits observation payloads for exactly 2 entries.

- [ ] **Step 6: Run the subsystem gate and commit generated publication files**

```bash
python scripts/smoke.py
python scripts/check_module_size.py
python scripts/check_private_files.py
git add scripts/export_atlas_web.py tests/test_export_atlas_web.py website/src/atlas/contracts.ts website/tests/atlas-contracts.test.ts website/public/data/atlas
git diff --cached --name-only
git commit -m "feat: export the expanded Atlas catalog (#55)"
```

# genomeOS Cesium Globe Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/app/` diagnostic iframe with a responsive CesiumJS explorer that renders
real MAP HbS and G6PD observations and posterior surfaces on 3D, 2D, and oblique geographic views,
including uncertainty, evidence support, and topographic elevation.

**Architecture:** A client-only React island owns UI state and talks to an engine-independent
`AtlasDataProvider`. A deterministic Python exporter converts allowlisted, versioned Atlas
artifacts into compact static web payloads; Cesium consumes those payloads through batched
primitives now and retains a metadata-rich 3D Tiles scale path. Scientific data, scene rendering,
and application controls remain separate modules.

**Tech Stack:** Astro 7.3.1, React 19.2.8, CesiumJS 1.145.0, `h3-js` 4.5.0, Zod 4.5.4,
TypeScript 6.0.3, Vitest 5.0.0, Playwright 1.63.0, Python 3.12, pandas/pyarrow.

**Spec:** `docs/superpowers/specs/2026-09-06-cesium-globe-explorer-design.md`

## Global Constraints

- Cite Atlas design §11 in every new production-module docstring.
- No inference runs in the browser, the website build, or the serving path.
- Observations, posterior surfaces, and support are separate visual and data layers.
- `unknown` and `prior_dominated` cells never receive elevation or enter aggregation.
- Missing radius, coordinate, support, metric, provenance, or version is a hard validation error.
- No Hugging Face or GCP credential may enter a tracked file or static build output.
- The public exporter allowlist contains only MAP HbS and G6PD while Issue #66 is unresolved.
- URL state never silently substitutes another entity for an unavailable requested identifier.
- The support mask is visible by default.
- Production TypeScript modules stay below 500 logical lines.
- Every dependency is pinned exactly in `website/package-lock.json`.
- The initial Hugging Face revision is
  `fc17bc1c1d96a0d0766746dcf26277ccdc669717`; the exported catalog records it.
- The Natural Earth fallback is pinned to upstream revision
  `ca96624a56bd078437bca8184e78163e5039ad19` and remains visibly attributed as public-domain
  Natural Earth data.
- The existing dirty primary worktree is untouched; work remains in
  `/private/tmp/genomeos-153-docs` on `feat/55-cesium-globe`.

---

### Task 1: Install and package the Cesium runtime

**Files:**

- Modify: `website/package.json`
- Modify: `website/package-lock.json`
- Modify: `website/astro.config.mjs`
- Create: `website/tests/cesium-assets.test.ts`

**Interfaces:**

- Consumes: Astro's normalized `BASE_PATH` and static build pipeline.
- Produces: React island support and a `CESIUM_BASE_URL` containing copied Cesium `Assets`,
  `ThirdParty`, `Widgets`, and `Workers` directories in both root and project-site builds.

- [x] **Step 1: Write the failing asset contract**

```ts
// website/tests/cesium-assets.test.ts
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("Cesium static runtime", () => {
  it.each(["Assets", "ThirdParty", "Widgets", "Workers"])(
    "copies %s into the production build",
    (directory) => {
      expect(existsSync(resolve("dist/cesium", directory))).toBe(true);
    },
  );
});
```

- [x] **Step 2: Run the contract and verify that it fails**

Run: `cd website && npm test -- cesium-assets.test.ts`

Expected: FAIL because `dist/cesium/Assets` and the other runtime directories do not exist.

- [x] **Step 3: Install exact dependencies**

Run:

```bash
cd website
npm install --save-exact @astrojs/react@6.0.5 cesium@1.145.0 h3-js@4.5.0 react@19.2.8 react-dom@19.2.8 zod@4.5.4
npm install --save-dev --save-exact vite-plugin-static-copy@4.1.1
```

- [x] **Step 4: Configure React and Cesium assets**

Update `website/astro.config.mjs` to add `react()` and `viteStaticCopy()`. Copy each directory from
`node_modules/cesium/Build/Cesium` to `cesium/`, and expose the deployment-aware base:

```js
vite: {
  define: {
    CESIUM_BASE_URL: JSON.stringify(`${normalizedBase}cesium/`),
  },
  plugins: [
    viteStaticCopy({
      targets: ['Assets', 'ThirdParty', 'Widgets', 'Workers'].map((name) => ({
        src: `node_modules/cesium/Build/Cesium/${name}`,
        dest: 'cesium',
      })),
    }),
  ],
},
```

- [x] **Step 5: Verify root and fallback asset builds**

Run:

```bash
cd website
npm test -- cesium-assets.test.ts
npm run build:fallback
test -d dist-fallback/cesium/Workers
```

Expected: the Vitest contract passes and both build roots contain Cesium runtime assets.

- [x] **Step 6: Commit the runtime**

```bash
git add website/package.json website/package-lock.json website/astro.config.mjs website/tests/cesium-assets.test.ts
git commit -m "feat: package Cesium globe runtime (#55)"
```

### Task 2: Export allowlisted scientific artifacts for the browser

**Files:**

- Create: `scripts/export_atlas_web.py`
- Create: `tests/test_export_atlas_web.py`
- Create: `website/src/atlas/public-artifacts.json`
- Create: `website/public/data/atlas/catalog.json`
- Create: `website/public/data/atlas/hbs-rs334.surface.json`
- Create: `website/public/data/atlas/hbs-rs334.observations.json`
- Create: `website/public/data/atlas/g6pd-deficiency.surface.json`
- Create: `website/public/data/atlas/g6pd-deficiency.observations.json`
- Create: `website/public/data/atlas/ne-110m-admin-0.geojson`

**Interfaces:**

- Consumes: `export_atlas_web.export_catalog(source_root, hbs_csv, g6pd_csv, allowlist_path,
out_dir, hf_revision) -> list[Path]`, the two immutable surface manifests/parquets, and MAP raw
  survey exports.
- Produces: schema-versioned JSON payloads with `catalog.artifacts[].surface_url` and
  `observations_url`; every file includes its source revision and artifact versions.

- [x] **Step 1: Write failing exporter tests**

Create tiny temp parquets and MAP CSVs in `tests/test_export_atlas_web.py`, then assert:

```python
def test_export_refuses_an_artifact_outside_the_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not allowlisted"):
        export_catalog(..., requested_ids=["hla:a-02-01"])


def test_export_preserves_support_and_refuses_missing_radius(tmp_path: Path) -> None:
    paths = export_catalog(...)
    surface = json.loads((tmp_path / "web/hbs-rs334.surface.json").read_text())
    observations = json.loads((tmp_path / "web/hbs-rs334.observations.json").read_text())
    assert {cell["support"] for cell in surface["cells"]} == {"observed", "unknown"}
    assert all(row["radius_km"] > 0 for row in observations["observations"])
    assert surface["artifact"]["hf_revision"] == HF_REVISION
```

Also cover missing versions, checksum generation, non-finite posterior values, mismatched
`variant_id`, and a row that loses `radius_km` after adapter validation.

- [x] **Step 2: Run exporter tests and verify that they fail**

Run:

```bash
/Users/bschilder/code/genomeOS/.venv/bin/python -m pytest tests/test_export_atlas_web.py -v
```

Expected: FAIL because `scripts.export_atlas_web` does not exist.

- [x] **Step 3: Implement the exporter and immutable allowlist**

`website/src/atlas/public-artifacts.json` contains exact identities and source files:

```json
{
  "schema_version": 1,
  "hf_dataset": "bschilder/genomeos-data",
  "hf_revision": "fc17bc1c1d96a0d0766746dcf26277ccdc669717",
  "artifacts": [
    {
      "id": "hbs-rs334",
      "variant_id": "chr11-5227002-T-A",
      "artifact_dir": "chr11-5227002-T-A__v1__map-2026-08",
      "observation_source": "map_hbs_surveys.csv"
    },
    {
      "id": "g6pd-deficiency",
      "variant_id": "phenotype:g6pd-deficiency",
      "artifact_dir": "phenotype__g6pd-deficiency__v1__map-2026-08",
      "observation_source": "map_g6pd_surveys.csv"
    }
  ]
}
```

The exporter calls the existing `map_surveys.load` and `map_g6pd.load` adapters so radius,
denominator, ascertainment, and refusal rules have one implementation. It joins verbatim citation
text back by source-native ID, rounds only serialized floating-point precision, calculates SHA-256
over canonical JSON, and writes with stable key ordering. It never supplies a radius or scientific
default.

- [x] **Step 4: Download the two raw MAP tables from the pinned Hugging Face revision**

Use `hf_hub_download()` through the already authenticated local Hugging Face client, writing its
cache outside the repository. Do not print or inspect the token. If anonymous download becomes
available, the identical command works without a token.

- [x] **Step 5: Download the immutable Natural Earth fallback**

Download `geojson/ne_110m_admin_0_countries.geojson` from Natural Earth revision
`ca96624a56bd078437bca8184e78163e5039ad19`, write it as
`website/public/data/atlas/ne-110m-admin-0.geojson`, and record the source URL and revision in the
catalog's `context_sources`. Natural Earth is the neutral country-outline fallback, not the detailed
context map.

- [x] **Step 6: Generate and inspect the public payloads**

Run:

```bash
/Users/bschilder/code/genomeOS/.venv/bin/python scripts/export_atlas_web.py \
  --store data/store \
  --hbs-csv /private/tmp/genomeos-hf/map_hbs_surveys.csv \
  --g6pd-csv /private/tmp/genomeos-hf/map_g6pd_surveys.csv \
  --allowlist website/src/atlas/public-artifacts.json \
  --out website/public/data/atlas
```

Inspect row counts, support counts, metric domains, versions, citations, checksums, and filenames
against both source manifests and the export test.

- [x] **Step 7: Run exporter and privacy tests**

Run:

```bash
/Users/bschilder/code/genomeOS/.venv/bin/python -m pytest tests/test_export_atlas_web.py -v
/Users/bschilder/code/genomeOS/.venv/bin/python scripts/check_private_files.py
```

Expected: PASS, with only the two MAP collections in the catalog.

- [x] **Step 8: Commit the browser artifacts**

```bash
git add scripts/export_atlas_web.py tests/test_export_atlas_web.py website/src/atlas/public-artifacts.json website/public/data/atlas
git commit -m "feat: export public MAP atlas artifacts (#55)"
```

### Task 3: Add strict browser contracts and the replaceable provider

**Files:**

- Create: `website/src/atlas/contracts.ts`
- Create: `website/src/atlas/provider.ts`
- Create: `website/src/atlas/static-provider.ts`
- Create: `website/tests/atlas-contracts.test.ts`
- Create: `website/tests/atlas-provider.test.ts`

**Interfaces:**

- Consumes: generated catalog/surface/observation JSON.
- Produces: `AtlasCatalog`, `ArtifactRef`, `SurfaceArtifact`, `ObservationArtifact`,
  `AtlasDataProvider`, and `StaticAtlasDataProvider`.

- [x] **Step 1: Write failing schema tests**

```ts
it("does not invent support or an observation radius", () => {
  expect(() => surfaceArtifactSchema.parse(surfaceWithoutSupport)).toThrow();
  expect(() =>
    observationArtifactSchema.parse(observationsWithoutRadius),
  ).toThrow();
});

it("rejects stale responses after cancellation", async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(provider.getCatalog(controller.signal)).rejects.toMatchObject({
    name: "AbortError",
  });
});
```

Tests also reject unknown support enums, unsupported schema versions, non-positive denominators,
invalid latitude/longitude, missing source revision, missing checksums, and mismatched artifact IDs.

- [x] **Step 2: Run tests and verify that they fail**

Run: `cd website && npx vitest run tests/atlas-contracts.test.ts tests/atlas-provider.test.ts`

Expected: FAIL because the contract and provider modules do not exist.

- [x] **Step 3: Implement Zod schemas and inferred types**

Define:

```ts
export const supportSchema = z.enum([
  "observed",
  "interpolated",
  "prior_dominated",
  "unknown",
]);

export type AtlasDataProvider = {
  getCatalog(signal?: AbortSignal): Promise<AtlasCatalog>;
  getSurface(ref: ArtifactRef, signal?: AbortSignal): Promise<SurfaceArtifact>;
  getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<ObservationArtifact>;
};
```

All scientific numeric fields use finite-number refinements. No `.default()` appears in a
scientific schema.

- [x] **Step 4: Implement `StaticAtlasDataProvider`**

The provider resolves deployment-aware URLs from a constructor-supplied base, uses `fetch` with
the caller's `AbortSignal`, checks response status, validates decoded JSON, and verifies that the
loaded artifact matches the requested catalog identity and version. It performs no rendering or
fallback substitution.

- [x] **Step 5: Run provider contracts**

Run: `cd website && npx vitest run tests/atlas-contracts.test.ts tests/atlas-provider.test.ts`

Expected: PASS.

- [x] **Step 6: Commit the provider boundary**

```bash
git add website/src/atlas/contracts.ts website/src/atlas/provider.ts website/src/atlas/static-provider.ts website/tests/atlas-contracts.test.ts website/tests/atlas-provider.test.ts
git commit -m "feat: add strict atlas data provider (#55)"
```

### Task 4: Implement deterministic visual encodings and URL state

**Files:**

- Create: `website/src/atlas/visual-encoding.ts`
- Create: `website/src/atlas/url-state.ts`
- Create: `website/tests/atlas-visual-encoding.test.ts`
- Create: `website/tests/atlas-url-state.test.ts`

**Interfaces:**

- Consumes: `SurfaceArtifact`, catalog entity IDs, and `URLSearchParams`.
- Produces: `Metric = 'post_mean' | 'post_sd'`, `ExplorerSceneMode = 'globe' | 'map' |
'perspective'`, `ExplorerState`, `colorForCell`, `heightForCell`, `parseExplorerState`, and
  `serializeExplorerState`.

- [x] **Step 1: Write failing encoding and URL tests**

```ts
it.each(["unknown", "prior_dominated"] as const)(
  "never gives %s a height",
  (support) => {
    expect(heightForCell(cell({ support }), domain, 3)).toBe(0);
  },
);

it("preserves an unavailable requested entity instead of substituting", () => {
  const parsed = parseExplorerState("?entity=missing", catalog);
  expect(parsed.state.entityId).toBe("missing");
  expect(parsed.corrections).toContainEqual(
    expect.objectContaining({ field: "entity", reason: "unavailable" }),
  );
});
```

Also test stable artifact-wide domains, metric palette endpoints, elevation/map behavior, camera
bounds, malformed booleans, complete round-tripping, and omission of transient inspector state.

- [x] **Step 2: Run tests and verify that they fail**

Run: `cd website && npx vitest run tests/atlas-visual-encoding.test.ts tests/atlas-url-state.test.ts`

Expected: FAIL because the modules do not exist.

- [x] **Step 3: Implement encoding**

Use frequency colors `#10213e → #27a9d0 → #72e7c1` and uncertainty colors
`#24144b → #ad8bff → #f4c86a`. Interpolate in linear RGB. `heightForCell` maps the catalog's full
metric domain to `0..180_000 * exaggeration` metres and returns zero unless support is `observed`
or `interpolated`.

- [x] **Step 4: Implement URL state**

The serializer writes `entity`, `version`, `metric`, comma-separated `layers`, `view`, `elevation`,
`exaggeration`, `lon`, `lat`, `height`, `heading`, and `pitch`. The parser validates each field
independently and returns `{ state, corrections }`; an unavailable requested entity is retained in
state and blocks artifact loading until the user makes an explicit choice.

- [x] **Step 5: Run encoding and state tests**

Run: `cd website && npx vitest run tests/atlas-visual-encoding.test.ts tests/atlas-url-state.test.ts`

Expected: PASS.

- [x] **Step 6: Commit deterministic state**

```bash
git add website/src/atlas/visual-encoding.ts website/src/atlas/url-state.ts website/tests/atlas-visual-encoding.test.ts website/tests/atlas-url-state.test.ts
git commit -m "feat: encode atlas metrics and shareable state (#55)"
```

### Task 5: Build the Cesium scene and scientific layers

**Files:**

- Create: `website/src/atlas/scene/atlas-scene.ts`
- Create: `website/src/atlas/scene/surface-layer.ts`
- Create: `website/src/atlas/scene/observation-layer.ts`
- Create: `website/src/atlas/scene/support-material.ts`
- Create: `website/src/atlas/scene/camera.ts`
- Create: `website/tests/atlas-scene.test.ts`

**Interfaces:**

- Consumes: validated artifacts, visual encodings, and `ExplorerState`.
- Produces: `createAtlasScene(container, options) -> AtlasSceneController`,
  `buildSurfaceLayer(artifact, options) -> ScientificPrimitiveGroup`,
  `buildObservationLayer(artifact) -> ObservationPrimitiveGroup`, and typed `AtlasPick` events.

- [x] **Step 1: Write failing pure scene-policy tests**

Test quantization, H3 boundary ordering, pick IDs, support partitioning, view transitions, and
keyboard-command filtering without constructing a WebGL context:

```ts
it("partitions inferred values from unsupported cells", () => {
  const groups = partitionSurfaceCells(
    artifact.cells,
    "post_mean",
    artifact.metric_domains,
  );
  expect(groups.surface.flatMap((group) => group.cells)).not.toContainEqual(
    expect.objectContaining({ support: "unknown" }),
  );
  expect(groups.support.unknown).toHaveLength(1);
});
```

- [x] **Step 2: Run tests and verify that they fail**

Run: `cd website && npx vitest run tests/atlas-scene.test.ts`

Expected: FAIL because scene modules do not exist.

- [x] **Step 3: Implement the scene controller**

Create `Viewer` with all ion-dependent widgets and the default base layer disabled. Style the
ellipsoid, sky atmosphere, stars, fog, globe lighting, resolution scale, and bloom using the site
palette. Expose methods:

```ts
export interface AtlasSceneController {
  setArtifact(
    surface: SurfaceArtifact,
    observations: ObservationArtifact,
  ): Promise<void>;
  setMetric(metric: Metric): Promise<void>;
  setLayerVisibility(layers: LayerVisibility): void;
  setElevation(enabled: boolean, exaggeration: number): Promise<void>;
  setSceneMode(mode: ExplorerSceneMode, reducedMotion: boolean): Promise<void>;
  setCamera(camera: CameraState, animated: boolean): void;
  onPick(listener: (pick: AtlasPick | null) => void): () => void;
  onCameraSettled(listener: (camera: CameraState) => void): () => void;
  destroy(): void;
}
```

- [x] **Step 4: Implement batched surface and support primitives**

Use `h3-js.cellToBoundary()` for exact cells, Cesium `PolygonGeometry` instances, and 32 shared
color bins so cells do not become independent draw calls. Supported cells use a material color;
unsupported cells use separate shader materials for crosshatch and stipple. Elevation rebuilds
geometry asynchronously with `extrudedHeight`; old primitives remain visible until the new group
is ready, then spatially registered groups and their palettes morph with an eased 720 ms blend
unless reduced motion is active.

- [x] **Step 5: Implement measured-observation primitives**

Batch geodesic radius rings into one `GroundPolylinePrimitive`, add a point collection for precise
centres, scale point pixels from explicit denominator quantiles, and attach pick IDs that identify
the object as `kind: 'observation'`. Never derive a radius in TypeScript.

- [x] **Step 6: Implement context imagery and camera controls**

Add a replaceable OSM-derived `UrlTemplateImageryProvider` below scientific layers, with attribution.
Load the pinned Natural Earth GeoJSON as a low-resolution country-outline layer that remains visible
when imagery is disabled or unavailable. Cesium handles mouse/touch controls; `camera.ts` adds
focus-scoped arrow/WASD and `+`/`-` controls, ignores editable elements, and debounces settled camera
state for URL synchronization.

- [x] **Step 7: Run scene tests and a production build**

Run:

```bash
cd website
npx vitest run tests/atlas-scene.test.ts
npm run check
npm run build
```

Expected: unit tests, Astro diagnostics, and static Cesium bundle all pass.

- [x] **Step 8: Commit the scene**

```bash
git add website/src/atlas/scene website/tests/atlas-scene.test.ts
git commit -m "feat: render scientific layers on a Cesium globe (#55)"
```

### Task 6: Replace the iframe with the responsive explorer UI

**Files:**

- Create: `website/src/components/atlas/AtlasExplorer.tsx`
- Create: `website/src/components/atlas/ExplorerControls.tsx`
- Create: `website/src/components/atlas/AtlasLegend.tsx`
- Create: `website/src/components/atlas/InspectorPanel.tsx`
- Create: `website/src/components/atlas/AtlasStatus.tsx`
- Create: `website/src/styles/atlas.css`
- Modify: `website/src/pages/app.astro`
- Modify: `website/src/styles/global.css`
- Modify: `website/tests/content.test.ts`
- Modify: `website/tests/site.spec.ts`

**Interfaces:**

- Consumes: `StaticAtlasDataProvider`, `AtlasSceneController`, and URL state.
- Produces: the complete `/app/` experience and accessible UI controls identified by stable labels.

- [x] **Step 1: Replace iframe expectations with failing explorer contracts**

Add content assertions that `/app/` references `AtlasExplorer` and does not contain an iframe.
Add Playwright flows using stable roles:

```ts
test("explorer changes entity, metric, context, and elevation", async ({
  page,
}) => {
  await page.goto("/app/");
  await expect(
    page.getByRole("application", { name: "genomeOS globe explorer" }),
  ).toBeVisible();
  await page.getByLabel("Variant or phenotype").selectOption("g6pd-deficiency");
  await page.getByRole("radio", { name: "Uncertainty" }).check();
  await page.getByLabel("Geographic context").uncheck();
  await page.getByLabel("Elevation").check();
  await expect(
    page.getByText("G6PD deficiency in hemizygous males"),
  ).toBeVisible();
  await expect(page).toHaveURL(/entity=g6pd-deficiency/);
});
```

Mock only external context tiles; load scientific artifacts from the built site.

Add separate browser tests that switch through Globe, Map, and Perspective; verify Elevation moves
Map to Perspective; open a surface cell and observation inspector; round-trip a complete URL; and
replace `HTMLCanvasElement.getContext` before startup to verify the non-WebGL failure panel and Retry
control. Run the flows in both configured desktop and mobile projects.

- [x] **Step 2: Run targeted tests and verify that they fail**

Run:

```bash
cd website
npx vitest run tests/content.test.ts
npx playwright test --grep "explorer changes"
```

Expected: FAIL because `/app/` still embeds the Cloud Run diagnostic.

- [x] **Step 3: Implement the React state machine**

`AtlasExplorer` loads the catalog, parses URL state, aborts stale requests, validates both artifact
payloads, builds the replacement scene, and commits only the newest request. It retains a previous
valid scene during loading and reports `loading catalog`, `loading artifact`, `validating`,
`rendering`, `ready`, or a typed error in an `aria-live="polite"` status region.

- [x] **Step 4: Implement large, responsive controls**

Desktop uses a left observatory dock, bottom legend, and conditional right inspector. Mobile uses a
top entity selector and `<details>` bottom sheets. Provide:

- Variant or phenotype selector.
- Posterior estimate/Uncertainty radio group.
- Observations, Inferred surface, Evidence support, and Geographic context checkboxes.
- Globe, Map, and Perspective radio group.
- Elevation checkbox and `1×..3×` range control.
- Home, Zoom in, Zoom out, and keyboard-help buttons.

All visible `genomeOS` strings use the `brand-name` class.

- [x] **Step 5: Implement legend, inspector, and failure panels**

Legend copy identifies the active metric, fixed artifact-wide domain, height scale, support
materials, model/data versions, and observation/surface distinction. Inspector fields are rendered
from validated data only. The WebGL failure panel links to provenance and supported-browser help;
artifact errors preserve the requested identifier and provide Retry.

- [x] **Step 6: Replace the Astro preview route**

Render `<AtlasExplorer client:load dataBaseUrl={sitePath('/data/atlas/')} />` in a full-width
application shell below the sticky site header. The React island server-renders its loading shell so
the route keeps one useful `<h1>` before hydration; remove the PageIntro, illustration, diagnostic
notice, iframe, and Cloud Run URL from the public route.

- [x] **Step 7: Implement the orbital-observatory visual system**

Use the established tokens, a deep-space vignette, cyan atmospheric framing, violet/gold
uncertainty accents, glass panels, large controls, and non-obstructive transitions. Respect
`prefers-reduced-motion`, `prefers-contrast`, coarse pointers, safe-area insets, and a 20rem minimum
viewport without horizontal scrolling.

- [x] **Step 8: Run component, browser, and accessibility tests**

Run:

```bash
cd website
npm test
npm run check
npm run test:e2e
```

Expected: all prior site contracts plus the new desktop/mobile explorer flows pass with no serious
or critical axe findings.

- [x] **Step 9: Commit the product UI**

```bash
git add website/src/components/atlas website/src/styles/atlas.css website/src/styles/global.css website/src/pages/app.astro website/tests
git commit -m "feat: launch the interactive Cesium explorer, closes #55"
```

### Task 7: Capture visual and measured performance evidence

**Files:**

- Create: `website/scripts/capture-atlas.mjs`
- Create: `website/tests/atlas-performance.spec.ts`
- Create: `docs/figures/cesium-globe-explorer.png`
- Modify: `website/package.json`
- Modify: `website/tests/site.spec.ts`

**Interfaces:**

- Consumes: locally built `/app/` and its `data-atlas-ready="true"` signal.
- Produces: reproducible 2560×1440 review figure and browser-measured interaction/load evidence.

- [x] **Step 1: Write the failing performance contract**

Instrument long tasks and scene frame events. The test loads HbS, performs a drag/zoom sequence,
switches to G6PD on a warm cache, and asserts:

```ts
expect(metrics.warmArtifactMs).toBeLessThan(2_000);
expect(metrics.longTasks.filter((duration) => duration > 250)).toEqual([]);
expect(metrics.interactionFrameRate).toBeGreaterThanOrEqual(45);
```

The test records evidence to Playwright output. Warm-load latency always runs. FPS and render-loop
long-task thresholds apply only when Chromium reports hardware acceleration; under SwiftShader,
the test records both metrics without treating CPU raster time as evidence about a mid-range GPU.

- [x] **Step 2: Run the performance contract and verify that it finds the first bottleneck**

Run: `cd website && npm run test:performance`

Expected: an initial measured result. If any threshold fails, profile and change only the measured
bottleneck—bin count, geometry construction scheduling, payload size, or redundant React updates.

- [x] **Step 3: Add a deterministic high-resolution capture script**

`capture-atlas.mjs` launches Chromium at 2560×1440, stubs external context tiles with a local neutral
tile only for reproducibility, loads the committed scientific artifacts, waits for the scene-ready
signal, selects a camera over Africa, enables observations and elevation, and writes
`docs/figures/cesium-globe-explorer.png`.

- [x] **Step 4: Visually inspect and refine**

Inspect the screenshot at original resolution. Verify that the globe is the focal point, controls
do not cover the evidence, labels remain readable, observation rings are distinct, low-to-high
color meaning is obvious without reading the legend, and an unsupported region is visible. Make
targeted CSS/material changes and recapture until each condition holds.

- [x] **Step 5: Run the measured contracts again**

Run:

```bash
cd website
npm run test:performance
node scripts/capture-atlas.mjs
```

Expected: thresholds pass and the PNG is 2560×1440.

- [x] **Step 6: Commit review evidence**

```bash
git add website/scripts/capture-atlas.mjs website/tests/atlas-performance.spec.ts website/package.json website/package-lock.json docs/figures/cesium-globe-explorer.png
git commit -m "test: capture Cesium explorer evidence (#55)"
```

### Task 8: Verify, show locally, and prepare the pull request

**Files:**

- Modify: `docs/superpowers/specs/2026-09-06-cesium-globe-explorer-design.md`
- Modify: `docs/superpowers/plans/2026-09-06-cesium-globe-explorer.md`
- Modify: `.github/workflows/pages.yml` if Cesium assets require an explicit Pages cache/build step.

**Interfaces:**

- Consumes: every preceding task and the repository's mandatory gates.
- Produces: checked-off plan, approved spec status, live local review URL, pushed branch, and a PR
  that closes #55 and documents which follow-on P5 issues it advances.

- [x] **Step 1: Mark the spec approved and check completed plan boxes**

Change the spec status to `approved` and check each completed task step only after its command and
artifact evidence exist.

- [ ] **Step 2: Run all website gates**

```bash
cd website
npm run format:check
npm run check
npm test
npm run build
npm run check:links -- dist /
npm run build:fallback
npm run check:links -- dist-fallback /genomeOS/
npm run test:e2e
```

- [ ] **Step 3: Run repository gates in the pinned environment**

```bash
cd /private/tmp/genomeos-153-docs
/Users/bschilder/code/genomeOS/.venv/bin/python scripts/freeze_contract.py --check
/Users/bschilder/code/genomeOS/.venv/bin/python scripts/check_module_size.py
/Users/bschilder/code/genomeOS/.venv/bin/python scripts/check_private_files.py
/Users/bschilder/code/genomeOS/.venv/bin/python scripts/smoke.py
/Users/bschilder/code/genomeOS/.venv/bin/python -m pytest
```

- [ ] **Step 4: Inspect the local explorer with the user**

Start `npm run dev -- --host 127.0.0.1` from `website/`, keep the process alive, open
`http://127.0.0.1:4321/app/`, and provide that URL to the user before pushing. Do not treat the
automated screenshot as a substitute for the interactive checkpoint.

- [ ] **Step 5: Apply review feedback and rerun affected gates**

For each requested visual or interaction change, add or update a contract, implement the change,
rerun the focused test, recapture the figure when appearance changes, and rerun the full website
gates.

- [ ] **Step 6: Commit plan/spec completion metadata**

```bash
git add docs/superpowers/specs/2026-09-06-cesium-globe-explorer-design.md docs/superpowers/plans/2026-09-06-cesium-globe-explorer.md
git commit -m "docs: complete Cesium explorer plan (#55)"
```

- [ ] **Step 7: Run final privacy and staged-path checks**

```bash
/Users/bschilder/code/genomeOS/.venv/bin/python scripts/check_private_files.py
git diff --cached --name-only
git status --short
```

Expected: privacy passes, no private path is staged or tracked, and the only uncommitted files are
explicitly explained build outputs or none.

- [ ] **Step 8: Push and open the pull request**

```bash
git push origin feat/55-cesium-globe
gh pr create --repo bschilder/genomeOS --base main --head feat/55-cesium-globe
```

The PR body includes `Closes #55`, Atlas design §11, the screenshot, exact verification commands
and results, the measured performance evidence, the MAP-only publication boundary, and an explicit
note that #56/#57/#58/#59/#63/#64 are advanced but not automatically closed unless their complete
acceptance criteria are independently satisfied.

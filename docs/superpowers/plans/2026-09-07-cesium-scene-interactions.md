# Cesium Scene and Scientific Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a layered Cesium scene with reliable geography, visible elevation, continuously morphing heatmaps, three observation shapes, configurable encodings, and distinct hover/selection feedback.

**Architecture:** `atlas-scene.ts` becomes a small coordinator over focused Cesium layer controllers. Scientific values enter only through validated artifacts and pure visual-encoding functions; context, terrain, surface faces/edges, sampling footprints, symbols, and highlights are independently replaceable. Presentation-only transitions update existing primitives or bounded overlay layers without refetching or recomputing science.

**Tech Stack:** CesiumJS 1.145.0, `h3-js` 4.5.0, TypeScript 6.0.3, Vitest 5.0.0, Playwright 1.63.0.

**Spec:** `docs/superpowers/specs/2026-09-07-cesium-explorer-interaction-design.md`

## Global Constraints

- This plan consumes the catalog/provider contract from `2026-09-07-atlas-publication-catalog-expansion.md`.
- Cite Atlas design §11 in every new production TypeScript module docstring.
- Scene modules never read files, environment variables, browser URLs, or remote APIs.
- Observations, inferred faces, support, and sampling footprints remain separate primitive groups.
- `unknown` and `prior_dominated` cells never receive scientific elevation.
- Observation altitude uses a supported cell's rendered height; missing/unsupported cells use geographic base without a fabricated cell height.
- Sampling footprints use literal `radius_km`, never point-size variables or visual clamping.
- Palette, opacity, edge, shape, size, color, basemap, terrain, and highlight changes never alter artifact values.
- Pointer picking is throttled to one Cesium pick per animation frame and observations win overlapping picks.
- Reduced-motion mode removes interpolation, crossfade, camera flight, and glow animation.
- The previous valid basemap or terrain remains active until a replacement is ready.
- Ion-backed providers are disabled when no assets-read token is supplied; OSM and ellipsoid remain functional.
- Production TypeScript modules stay below 500 logical lines.

---

### Task 1: Define deterministic visual encodings

**Files:**

- Modify: `website/src/atlas/visual-encoding.ts`
- Modify: `website/tests/atlas-visual-encoding.test.ts`
- Create: `website/src/atlas/observation-encoding.ts`
- Create: `website/tests/atlas-observation-encoding.test.ts`

**Interfaces:**

- Consumes: `SurfaceCell`, `Observation`, selected metric, domain, palette, shape, min/max size, and color variable.
- Produces: `colorForCell`, `heightForCell`, `observationSize`, `observationColor`, `studyColor`, and metric-specific defaults.

- [ ] **Step 1: Write failing palette and observation tests**

```ts
it("uses distinct defaults for estimate and uncertainty", () => {
  expect(defaultPalette("post_mean")).toBe("genome");
  expect(defaultPalette("post_sd")).toBe("signal");
});

it("never uses sampling radius as marker size", () => {
  const a = observation({ ac: 10, an: 100, radius_km: 1 });
  const b = observation({ ac: 10, an: 100, radius_km: 564 });
  expect(observationSize(a, "ac", [6, 18], [0, 100])).toBe(
    observationSize(b, "ac", [6, 18], [0, 100]),
  );
});
```

Cover Genome, Signal, Viridis, Cividis, and Plasma endpoints; ordered domain handling; zero AC; equal domains; square-root AC/AN scaling; linear frequency scaling; deterministic study colors; and bounds refusal.

- [ ] **Step 2: Run tests and confirm missing APIs**

Run: `cd website && npm test -- atlas-visual-encoding.test.ts atlas-observation-encoding.test.ts`

Expected: FAIL because named palettes and observation encodings are absent.

- [ ] **Step 3: Implement pure encoding functions**

Use exact unions:

```ts
export type PaletteId = "genome" | "signal" | "viridis" | "cividis" | "plasma";
export type ObservationSizeVariable = "fixed" | "frequency" | "ac" | "an";
export type ObservationColorVariable = "white" | "study" | "frequency" | "ac";
export type ObservationShape = "circle" | "hemisphere" | "pin";
```

Interpolate color stops continuously. Treat `ac / an` as observed frequency only after validated `0 <= ac <= an`; do not coerce invalid values. Study colors hash the exported `study_id` into a fixed categorical palette.

- [ ] **Step 4: Run the focused tests and commit**

```bash
cd website && npm test -- atlas-visual-encoding.test.ts atlas-observation-encoding.test.ts
git add website/src/atlas/visual-encoding.ts website/src/atlas/observation-encoding.ts website/tests/atlas-visual-encoding.test.ts website/tests/atlas-observation-encoding.test.ts
git commit -m "feat: define Atlas visual encodings (#55)"
```

### Task 2: Split the scene into explicit controllers

**Files:**

- Modify: `website/src/atlas/scene/atlas-scene.ts`
- Create: `website/src/atlas/scene/types.ts`
- Create: `website/src/atlas/scene/basemap-controller.ts`
- Create: `website/src/atlas/scene/geographic-overlay.ts`
- Create: `website/src/atlas/scene/surface-edge-layer.ts`
- Create: `website/src/atlas/scene/highlight-layer.ts`
- Modify: `website/tests/atlas-scene.test.ts`

**Interfaces:**

- Consumes: validated artifacts plus one `AtlasSceneOptions` object.
- Produces: an `AtlasSceneController` with narrow setters for provider, scientific presentation, hover, selection, view, camera, and teardown.

- [ ] **Step 1: Write a failing controller contract test**

```ts
expectTypeOf<AtlasSceneController>().toMatchTypeOf<{
  setBasemap(id: BasemapId): Promise<void>;
  setTerrain(id: TerrainId): Promise<void>;
  setSurfaceStyle(style: SurfaceStyle): Promise<void>;
  setObservationStyle(style: ObservationStyle): Promise<void>;
  setHover(pick: AtlasPick | null): void;
  setSelection(pick: AtlasPick | null): void;
  clearArtifact(): void;
  destroy(): void;
}>();
```

- [ ] **Step 2: Run the scene suite and confirm contract failure**

Run: `cd website && npm test -- atlas-scene.test.ts`

Expected: FAIL because the coordinator has no provider/style/highlight APIs and exceeds its intended responsibility.

- [ ] **Step 3: Introduce shared scene types**

Define `AtlasPick`, `SurfaceStyle`, `ObservationStyle`, `BasemapId`, `TerrainId`, `SceneWarning`, and `RenderedCellHeight`. Export them from `scene/types.ts`; remove duplicate local pick types.

- [ ] **Step 4: Reduce `atlas-scene.ts` to orchestration**

The coordinator owns viewer lifecycle, stable visual-stack order, camera events, request sequence, and controller teardown. It delegates Cesium geometry/material work to layer modules and remains under 500 logical lines.

- [ ] **Step 5: Run tests and module-size check**

Run:

```bash
cd website && npm test -- atlas-scene.test.ts
cd .. && python scripts/check_module_size.py
```

Expected: PASS and no production module exceeds the repository budget.

- [ ] **Step 6: Commit the decomposition**

```bash
git add website/src/atlas/scene website/tests/atlas-scene.test.ts
git commit -m "refactor: split Atlas scene controllers (#55)"
```

### Task 3: Add resilient basemaps and terrain

**Files:**

- Modify: `website/src/atlas/scene/basemap-controller.ts`
- Create: `website/tests/atlas-basemap.test.ts`
- Modify: `website/astro.config.mjs`
- Modify: `.github/workflows/pages.yml`

**Interfaces:**

- Consumes: `{ionToken: string | null, onWarning(SceneWarning)}` supplied by the React boundary.
- Produces: dark streets, roads, aerial, aerial-with-labels, smooth ellipsoid, and Cesium World Terrain choices with last-good rollback.

- [ ] **Step 1: Write failing provider lifecycle tests**

```ts
it("keeps the last valid imagery when a replacement fails", async () => {
  const controller = basemapHarness({ ionToken: "read-only-token" });
  await controller.setBasemap("dark-streets");
  controller.failNextProvider("roads");
  await expect(controller.setBasemap("roads")).rejects.toThrow("roads");
  expect(controller.activeBasemap()).toBe("dark-streets");
});

it("disables ion choices without a token", () => {
  expect(providerAvailability(null)).toEqual({
    aerial: false,
    "aerial-labels": false,
    "dark-streets": true,
    roads: false,
    "smooth-globe": true,
    "world-terrain": false,
  });
});
```

- [ ] **Step 2: Run the tests and confirm failure**

Run: `cd website && npm test -- atlas-basemap.test.ts`

Expected: FAIL because provider selection and rollback do not exist.

- [ ] **Step 3: Implement two-phase provider replacement**

Create the incoming imagery/terrain provider without removing the active one. Wait for its readiness/error signal; only then swap and destroy the prior layer. Emit one typed warning on failure. Keep attribution visible and preserve label imagery above scientific faces.

- [ ] **Step 4: Wire the read-only Cesium token into builds**

Expose `process.env.CESIUM_TOKEN` as `PUBLIC_CESIUM_TOKEN` through Vite `define`, defaulting to an empty string. Add `CESIUM_TOKEN: ${{ secrets.CESIUM_TOKEN }}` to both Pages jobs' build/check environment. Add a unit assertion that the empty-token build contains no `undefined` token and leaves OSM/smooth choices enabled.

- [ ] **Step 5: Run unit and production builds**

```bash
cd website
npm test -- atlas-basemap.test.ts
npm run build
BASE_PATH=/genomeOS OUT_DIR=dist-fallback npm run build
```

Expected: both builds succeed; absent local token disables only ion-backed choices.

- [ ] **Step 6: Commit the provider slice**

```bash
git add website/src/atlas/scene/basemap-controller.ts website/tests/atlas-basemap.test.ts website/astro.config.mjs .github/workflows/pages.yml
git commit -m "feat: add Cesium maps and terrain (#55)"
```

### Task 4: Render faces, edges, and geography in the correct order

**Files:**

- Modify: `website/src/atlas/scene/surface-layer.ts`
- Modify: `website/src/atlas/scene/support-material.ts`
- Modify: `website/src/atlas/scene/surface-edge-layer.ts`
- Modify: `website/src/atlas/scene/geographic-overlay.ts`
- Modify: `website/tests/atlas-scene.test.ts`

**Interfaces:**

- Consumes: `SurfaceArtifact`, `SurfaceStyle`, and validated Natural Earth context.
- Produces: separately toggled surface faces, support material, top/vertical edges, and depth-independent country overlay.

- [ ] **Step 1: Add failing stack and elevation tests**

```ts
it("orders geography above scientific faces and below observations", () => {
  expect(SCIENTIFIC_STACK).toEqual([
    "surface",
    "support",
    "cell-edges",
    "geography",
    "sampling-footprints",
    "observations",
    "hover",
    "selection",
  ]);
});

it("keeps unsupported cells flat", () => {
  expect(renderedHeight(cell({ support: "unknown" }), elevatedStyle())).toBe(0);
  expect(
    renderedHeight(cell({ support: "prior_dominated" }), elevatedStyle()),
  ).toBe(0);
});
```

- [ ] **Step 2: Run tests and confirm ordering/edge failure**

Run: `cd website && npm test -- atlas-scene.test.ts`

Expected: FAIL because context is currently clamped beneath later surface geometry and no edge layer exists.

- [ ] **Step 3: Implement per-instance surface color and opacity**

Use `PerInstanceColorAppearance` and keep `GeometryInstance` attributes addressable by H3 index. Faces use the selected palette at default opacity `0.86`; support materials stay semantic and palette-independent.

- [ ] **Step 4: Implement elevation edges and overlay altitude**

Build top and vertical lines from the same H3 boundaries/heights as the faces. Country strokes render depth-independently when flat and sample the intersected cell's visual height plus a documented small render offset when elevated. The offset is presentation-only and never exposed as data.

- [ ] **Step 5: Run tests and commit**

```bash
cd website && npm test -- atlas-scene.test.ts atlas-visual-encoding.test.ts
git add website/src/atlas/scene/surface-layer.ts website/src/atlas/scene/support-material.ts website/src/atlas/scene/surface-edge-layer.ts website/src/atlas/scene/geographic-overlay.ts website/tests/atlas-scene.test.ts
git commit -m "feat: clarify elevated Atlas geography (#55)"
```

### Task 5: Add circle, hemisphere, pin, and faithful sampling footprints

**Files:**

- Modify: `website/src/atlas/scene/observation-layer.ts`
- Create: `website/src/atlas/scene/observation-symbols.ts`
- Create: `website/tests/atlas-observation-layer.test.ts`

**Interfaces:**

- Consumes: `ObservationArtifact`, `ObservationStyle`, and `(h3Index) => RenderedCellHeight | null`.
- Produces: independently controlled sampling footprints and circle/hemisphere/pin symbols whose bases remain above the scientific surface.

- [ ] **Step 1: Write failing shape and altitude tests**

```ts
it.each(["circle", "hemisphere", "pin"] as const)(
  "builds a pickable %s symbol above its supported cell",
  (shape) => {
    const symbol = symbolDescriptor(observation(), shape, () => 42_000);
    expect(symbol.pick.kind).toBe("observation");
    expect(symbol.baseHeight).toBeGreaterThan(42_000);
  },
);

it("preserves the 563.9 km source-supported footprint", () => {
  const footprint = samplingFootprint(observation({ radius_km: 563.9 }));
  expect(footprint.radiusKm).toBe(563.9);
});
```

Also verify 2D hemisphere becomes a disk, 2D pin remains a map-pin glyph, unsupported cell lookup does not fabricate height, and shape controls never change radius.

- [ ] **Step 2: Run tests and confirm shape APIs are absent**

Run: `cd website && npm test -- atlas-observation-layer.test.ts`

Expected: FAIL because the current layer only renders points and ground rings.

- [ ] **Step 3: Implement focused symbol builders**

Use point primitives for circles, hemisphere geometry for domes, and a bounded stem/head primitive pair for pins. Keep pin height a fixed presentation constant. Give every symbol the same `ObservationPick` identity and compute its base from the active surface-height lookup.

- [ ] **Step 4: Separate footprints from symbols**

Return `symbols` and `footprints` primitive collections with independent visibility/opacity setters. Sampling rings use only geodesic `radius_km`; their lower opacity and explanatory state are not coupled to point color or size.

- [ ] **Step 5: Run tests and commit**

```bash
cd website && npm test -- atlas-observation-layer.test.ts atlas-observation-encoding.test.ts
git add website/src/atlas/scene/observation-layer.ts website/src/atlas/scene/observation-symbols.ts website/tests/atlas-observation-layer.test.ts
git commit -m "feat: add Atlas observation symbols (#55)"
```

### Task 6: Add heatmap morphing, hover glow, and persistent selection

**Files:**

- Modify: `website/src/atlas/scene/surface-layer.ts`
- Modify: `website/src/atlas/scene/highlight-layer.ts`
- Modify: `website/src/atlas/scene/atlas-scene.ts`
- Create: `website/src/atlas/scene/surface-transition.ts`
- Create: `website/tests/atlas-transition.test.ts`
- Modify: `website/tests/atlas-scene.test.ts`

**Interfaces:**

- Consumes: old/new validated artifacts, palette/style state, Cesium clock time, and pick events.
- Produces: frame-throttled hover, persistent selection, and 650 ms cell-keyed color/value morphs with smooth palette interpolation.

- [ ] **Step 1: Write failing interpolation and highlight tests**

```ts
it("interpolates a shared cell between two maps", () => {
  const frame = transitionFrame(oldArtifact(), newArtifact(), 0.5);
  expect(frame.get("83754efffffffff")?.value).toBeCloseTo(0.35);
});

it("keeps hover and selection independent", () => {
  const state = highlightState();
  state.hover(surfacePick("83754efffffffff"));
  state.select(observationPick("map-surveys:12"));
  state.hover(null);
  expect(state.selection()).toEqual(observationPick("map-surveys:12"));
});
```

Also test cells present on only one side, support-state changes, palette-only transitions, reduced motion, selection clear on artifact change, and observation-first `drillPick` precedence.

- [ ] **Step 2: Run tests and confirm transition/highlight failure**

Run: `cd website && npm test -- atlas-transition.test.ts atlas-scene.test.ts`

Expected: FAIL because artifact changes currently replace primitives without a cell-keyed morph or overlay highlights.

- [ ] **Step 3: Implement the transition model**

Join old/new cells by H3 index. For shared supported cells, interpolate metric values and per-instance colors continuously. Fade entering/leaving cells through zero alpha; support-state material changes crossfade without turning masked values into numeric color. At animation completion, install the validated destination layer and dispose the old layer.

- [ ] **Step 4: Implement bounded highlights**

Maintain exactly one hover overlay and one selection overlay. Surface overlays trace the H3 top boundary; observation overlays match active shape/base height. Hover uses cyan-white with a 160 ms eased fade, selection uses a signal-gold outline/halo until replaced or explicitly cleared.

- [ ] **Step 5: Throttle pointer movement and honor reduced motion**

Run at most one `drillPick` per animation frame. Reduced motion applies destination colors and highlight opacity immediately. Keyboard focus and touch call the same persistent `setSelection` API as mouse clicks.

- [ ] **Step 6: Run scene/performance unit tests**

Run:

```bash
cd website
npm test -- atlas-transition.test.ts atlas-scene.test.ts atlas-observation-layer.test.ts atlas-visual-encoding.test.ts
```

Expected: all selected tests PASS and no test reconstructs the full scientific layer for hover.

- [ ] **Step 7: Commit interaction behavior**

```bash
git add website/src/atlas/scene website/tests/atlas-transition.test.ts website/tests/atlas-scene.test.ts
git commit -m "feat: morph and highlight Atlas layers (#55)"
```

### Task 7: Verify the complete scene in Cesium

**Files:**

- Modify: `website/tests/atlas-performance.spec.ts`
- Modify: `website/tests/site.spec.ts`

**Interfaces:**

- Consumes: the completed scene controller and 30-entry static catalog.
- Produces: browser evidence for provider rollback, visual ordering, map morphs, altitude, picking, reduced motion, and bounded performance.

- [ ] **Step 1: Add browser scenarios**

Exercise all four basemaps, both terrain modes, all three camera modes, both metrics, every palette, three observation shapes, every size/color variable, footprints, elevation, hover, selection, and one surface-only AFND artifact. Mock provider failure and assert the previous map remains visible with a warning event.

- [ ] **Step 2: Add performance assertions**

Assert catalog selection fetches only the selected artifact; pointer movement does not increase full scientific primitive counts; warm switching settles in under 2 seconds on the test fixture; and no main-thread task exceeds the existing browser-test threshold.

- [ ] **Step 3: Run browser tests**

```bash
cd website
npm run test:e2e
npm run test:performance
```

Expected: all browser and performance contracts PASS in Chromium.

- [ ] **Step 4: Commit the scene verification**

```bash
git add website/tests/site.spec.ts website/tests/atlas-performance.spec.ts
git commit -m "test: verify Cesium explorer interactions (#55)"
```

# Atlas mobile / fast-load / GCS — cross-task interface contract

Companion to `docs/superpowers/plans/2026-10-07-atlas-mobile-fast-load-gcs.md` and the spec
`docs/superpowers/specs/2026-10-07-atlas-mobile-fast-load-gcs-design.md`. Every task that crosses one
of these boundaries uses exactly these paths, names and shapes. A task may add internals; it may
not rename or reshape anything here without a plan amendment. The plan's "Plan rulings" (R1–R28)
record every amendment folded in below.

Paths below are relative to the repository root; `website/` paths are the Astro site.

## Part A (mobile)

| Module | Exports |
| --- | --- |
| `website/src/components/atlas/useMediaQuery.ts` | `useMediaQuery(query: string): boolean` — `useSyncExternalStore`, server snapshot `false`; `MOBILE_QUERY = '(max-width: 52rem)'`; internal `createMediaQueryStore(query, getMatchMedia?)` |
| `website/src/components/atlas/escape-stack.ts` | pure core: `type EscapeLayerOrder = 'popover' \| 'dialog' \| 'external' \| 'inspector' \| 'sheet'` (closing precedence, innermost first), `createEscapeStack()`, `handleEscapeKey(stack, event)`, `ESCAPE_LAYER_ORDER` |
| `website/src/components/atlas/useEscapeStack.ts` | `EscapeStackProvider` (React context provider; one capture-phase `document` `keydown` listener), `useEscapeLayer(active: boolean, close: () => void, order: EscapeLayerOrder): void` (throws outside the provider); re-exports `EscapeLayerOrder` |
| `website/src/components/atlas/sheet-geometry.ts` | pure core: `type SheetState = 'peek' \| 'half' \| 'full'`, `SheetSnaps`, `snapHeights`, `nextSheetState`, `stepSheetState`, `clampSheetHeight`, `nearestSheetState`, `releaseSheetState`, `sheetStateLabel`, `VelocityTracker`, `DRAG_SLOP_PX = 8`, `FLICK_PX_PER_MS = 0.5`, `PROJECTION_MS = 120`, `TOP_CHROME_GAP_PX = 8` |
| `website/src/components/atlas/useBottomSheet.ts` | re-exports `SheetState`; `type SheetHandleProps`; `useBottomSheet(options: { initial: SheetState; enabled: boolean; explorer: HTMLElement \| null; topChrome: () => number; dockedHeight: () => number }): { state: SheetState; setState(s: SheetState): void; cycle(): void; handleProps: SheetHandleProps; sheetRef: React.RefCallback<HTMLElement>; bodyInert: boolean }` — writes `--atlas-sheet-offset` (and `--atlas-sheet-rest`) on the explorer element per animation frame (Plan ruling R1) |
| `website/src/components/atlas/BottomSheetHandle.tsx` | `BottomSheetHandle(props: { label: string; state: SheetState; controls: string; handleProps: SheetHandleProps }): JSX.Element` |
| `website/src/components/atlas/sheet-layout.ts` | `topChromeBottom(explorer)`, `dockedHeight(explorer)`, `writeDockedStack(explorer)`, `peekHeight(sheet)`, `observeSheetLayout(explorer, onChange)`, `PEEK_GAP_PX = 8` |
| `website/src/components/atlas/useExplorerPanels.ts`, `panel-arbiter.ts` | `ExplorerPanelsProvider`, `useExplorerPanel(kind, open, close)`, `useOpenPanel()`, `usePanelBodyInert()`, `useSetPanelBodyInert()`; `createPanelArbiter({ exclusive, onChange })`, `type PanelKind = 'inspector' \| 'external'` |
| `website/src/components/atlas/ControlsSheet.tsx`, `PanelSheet.tsx`, `ExplorerHeading.tsx`, `AtlasDataCredit.tsx`, `site-header.ts` | the controls sheet, the panel sheet (`{ explorer, children }`), `ExplorerHeading`/`ControlsLoading`, `AtlasDataCredit`, `siteHeaderBottom(root?)`, `clampPickerTop(anchorTop, headerBottom, maxOffset)`, `PICKER_GUTTER_PX = 8` |

DOM hooks: `.atlas-top-slot` (first child of `.atlas-explorer`), `data-sheet-state` on
`aside.atlas-controls` and on `.atlas-right-rail`, `[data-sheet-peek]`, `[data-sheet-body]`,
`data-sheet-dragging` on the explorer during a drag; `data-site-header` already exists on the site
header (`SiteHeader.astro`) and is read, not added. Page props: `SiteLayout` `viewportFit?: 'cover'`
and `htmlClass?: string` (`/app/` passes `atlas-page`). Test helpers (`website/tests/atlas-mobile-helpers.ts`):
`PHONE_PROFILES`, `skipUnlessProject`, `waitForAtlasReady`, `controlsSheet`, `setSheetState`,
`expandExplorerSheet`, `sheetGeometry`, `dockedStackInOrder`, `startTouch`, `touchDrag`, `centreOf`,
`INSPECTOR_CAMERA`, `panelSheet`, `tapSelectNearCenter`, `canvasCoverage`, `dockedOutsideCentre`,
`uncoveredCredits`, `topChromeClearance`; `topLevelRoutes` lives in `website/tests/site-routes.ts`.

## Part B (fast load)

### Python

`genomeos/publication/surface_codec.py`

```python
SUPPORT_CODES: tuple[str, ...] = ("observed", "interpolated", "prior_dominated", "unknown")
FORMAT_VERSION: int = 1
GOSA_ERROR_CODES: tuple[str, ...]          # the 25 codes, in check order (table below)
TIER_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]]   # tier -> ((name, dtype, encoding), ...)
DETAIL_FIELDS: tuple[str, ...]; HEADER_KEYS: frozenset[str]; COLUMN_KEYS: frozenset[str]
IDENTITY_FIELDS: tuple[str, ...]           # the 13 catalog-ref identity fields
class GosaError(ValueError):               # GosaError(code, message); .code in GOSA_ERROR_CODES
    code: str
@dataclass(frozen=True)
class GosaContainer:
    tier: str                      # "grid" | "render" | "detail"
    header: dict                   # parsed header JSON
    columns: dict[str, tuple]      # name -> decoded values (ints for h3/support, floats otherwise)
def grid_sha256(h3: Sequence[int]) -> str: ...
def container_sha256(data: bytes) -> str: ...
def validate_identity(artifact: Any) -> None: ...
def encode_grid(h3: Sequence[int], resolution: int) -> bytes: ...
def encode_render(*, artifact: Mapping, source_surface_sha256: str, grid_sha256: str,
                  support: Sequence[str], post_mean: Sequence[float], post_sd: Sequence[float]) -> bytes: ...
def encode_detail(*, artifact: Mapping, source_surface_sha256: str, grid_sha256: str,
                  post_mean, post_sd, q025, q975, posterior_contraction, dist_nearest_obs_km) -> bytes: ...
def decode(data: bytes, *, tier: str) -> GosaContainer: ...   # every intrinsic B.3 hard error -> GosaError
def verify_container(data: bytes, *, tier: str, sha256: str, size: int) -> GosaContainer: ...
def verify_artifact_tiers(*, grid, render, detail, ref: Mapping, grid_sha256: str) -> None: ...
```

`scripts/encode_atlas_web.py` — CLI: `python scripts/encode_atlas_web.py [--in DIR] [--out DIR]
[--with-downloads]`; default `--in` and `--out` = `website/public/data/atlas`; with `--out` ≠ `--in`
the objects **and** the rewritten `catalog.json` go to `--out` and the input catalog is untouched.
Python API: `encode_export(in_dir, out_dir, *, with_downloads=False)` (the keyword arrives in Part
C), `encode_catalog(catalog, *, out_dir, load_surface, observations_size)`, `SurfaceSource`,
`SharedGrid`, `canonical_bytes`, `data_key`, `grid_key`, `tier_key`, `write_object`,
`CATALOG_FIELDS`, `REF_FIELDS`, `DATA_KEY`, `main(argv)`. `--with-downloads` is added by Part C.

`scripts/build_atlas_e2e_fixture.py` — CLI: `--from-dir DIR` (default `website/public/data/atlas`),
`--out website/tests/fixtures/atlas/e2e`; API `build_fixture(from_dir, out, *, cell_budget=256,
observation_budget=64)`, `select_rows`, `select_observations`, `prepare_out`, `CELL_BUDGET = 256`,
`OBSERVATION_BUDGET = 64`, `INSPECTOR_TARGET = (40.4407, -3.7201)`.
`scripts/build_atlas_parity_subset.py` (`--from-dir`, `--out`) writes `website/tests/fixtures/atlas/parity/`;
`scripts/plot_surface_codec_parity.py` (`--data-dir`, `--out`, `--dpi`) writes `docs/figures/surface-codec-parity.png`.

### Catalog contract (`website/src/atlas/contracts.ts`, strict; written by the encoder only)

```ts
export const dataKeySchema: z.ZodString;               // ^[a-z0-9][a-z0-9._/-]*$, no '..' segment
export const webObjectSchema = z.strictObject({ url: dataKeySchema, sha256: sha256Schema, bytes: positiveInt });
export const gridEntrySchema = z.strictObject({ url, sha256, bytes, resolution, n_cells });
// atlasCatalogSchema gains: grids: z.record(sha256Schema, gridEntrySchema)  (exactly one entry in v1;
//   each artifact's web.grid_sha256 must name a declared grid of its own resolution)
// artifactRefSchema gains:  web: z.strictObject({ grid_sha256, render: webObjectSchema, detail: webObjectSchema }),
//                           observations_bytes: positiveInt | null   (non-null iff observations_available)
// dataKeySchema also guards surface_url, observations_url, downloads.*.url, context_sources[].url,
//   external_resources[].cache_url. The schema does not compare artifact n_cells with the grid entry
//   (the decoders do).
export type WebObject; export type GridEntry;
```

`SurfaceArtifact` exported by `contracts.ts` stays the JSON surface type (tests import it as
`SurfaceArtifact as SurfaceArtifactJson`); the columnar `SurfaceArtifact` lives in `surface-columns.ts`.

### TypeScript modules (all Cesium-free unless marked)

| Module | Exports |
| --- | --- |
| `website/src/lib/data-url.ts` | `assertDataBase(base: string): void`, `assertDataKey(key: string): void`, `resolveDataUrl(key: string, base: string, docBase: string): string`, `dataHref(key: string, base: string): string`, `dataOrigin(base: string): string \| null` (preconnect); Part C adds `artifactDataBaseFrom(configured: string \| undefined, siteDataBase: string): string` |
| `website/src/atlas/gosa/container.ts` | `GOSA_ERROR_CODES`, `type GosaErrorCode`, `class GosaError extends Error { readonly code: GosaErrorCode }` (`new GosaError(code, message)`, message prefixed `code: `), `type GosaTier`, `FORMAT_VERSION`, `TIER_COLUMNS`, `DTYPE_BYTES`, `align8`, `unshuffle`, `parseContainer(bytes, tier): { artifact: ArtifactIdentity \| null; columns: Uint8Array<ArrayBuffer>[]; header: GosaHeader }` (checks 1–15) |
| `website/src/atlas/gosa/decode.ts` | re-exports `FORMAT_VERSION`, `GOSA_ERROR_CODES`, `GosaError`, `GosaErrorCode`, `GosaTier`; `SUPPORT_CODES`; `type DecodeTiming = (phase: 'verify' \| 'decode', start: number, end: number) => void`; `verifyContainer(bytes, declared: { bytes; sha256 }, label)`; `decodeGrid(buf: ArrayBuffer, expect: { gridSha256: string; entry: GridEntry }, timing?): DecodedGrid`, `decodeRender(buf, expect: { ref: ArtifactRef; grid: DecodedGrid }, timing?): DecodedRender`, `decodeDetail(buf, expect: { ref: ArtifactRef; grid: DecodedGrid; render: DecodedRender }, timing?): DecodedDetail` (the B.2 cross-tier checks; codes and order: table below) |
| `website/src/atlas/gosa/types.ts` | `DecodedGrid { gridSha256; resolution; n: number; h3Lo: Uint32Array<ArrayBuffer>; h3Hi: Uint32Array<ArrayBuffer> }`, `DecodedRender { artifact: ArtifactIdentity; support: Uint8Array<ArrayBuffer>; post_mean: Float32Array<ArrayBuffer>; post_sd: Float32Array<ArrayBuffer> }`, `DecodedDetail { post_mean, post_sd, q025, q975, posterior_contraction, dist_nearest_obs_km: Float64Array<ArrayBuffer> }` |
| `website/src/atlas/gosa/sha256.ts` | `sha256Hex(bytes: Uint8Array): string` (`@noble/hashes` 2.4.0, exact) |
| `website/src/atlas/identity.ts` | `IDENTITY_FIELDS`, `identityMessage(field, requested, received)`, `identityMismatch(ref, loaded)`, `assertIdentity(ref, loaded)` (wording `Atlas artifact identity mismatch for <field>: …`) |
| `website/src/atlas/surface-columns.ts` | `artifactKeyFor(ref: ArtifactIdentity): string` (`id:model_version:data_version`), `interface SurfaceArtifact { artifactKey; artifact: ArtifactIdentity; grid: DecodedGrid; support: Uint8Array; values: { post_mean: Float32Array; post_sd: Float32Array }; detail: DecodedDetail \| null }`, `rowForH3(s, h3: string): number \| null`, `h3At(s, row): string`, `renderAt(s, row): RenderCell`, `cellAt(s, row): SurfaceCell` (throws `DetailNotLoadedError`), `type RenderCell = { h3: string; support: Support; post_mean: number; post_sd: number }` |
| `website/src/atlas/visual-encoding.ts` (existing) | adds `type LinearRgb`, `colorBytesAtStops(stopsLinear: readonly LinearRgb[], t: number): [number, number, number]`, `linearStops(palette: PaletteId): readonly LinearRgb[]`, `heightFor(support: Support, value: number, domain: MetricDomain, exaggeration: number): number`, `normalizedValue`, `quantizeMetric` (moved here); `colorAtPosition` keeps its signature and formats `colorBytesAtStops` |
| `website/src/atlas/geometry/wgs84.ts` | `interface BoundingSphere { center: [number, number, number]; radius: number }`, `boundingSphereOf`, `geodeticToEcef`, `normalizeInto`, `needsLongitudeSplit(sphere)` (the scheduler's "costly" test), `scaleToGeocentricSurface`, `surfacePointToDegrees`, `magnitude` |
| `website/src/atlas/geometry/topology.ts` | `interface GridTopology { n; centreLat: Float64Array; centreLon: Float64Array; cornerOffsets: Uint32Array /* n+1 */; cornerIds: Uint32Array; vertexLat: Float64Array; vertexLon: Float64Array }`, `buildGridTopology(grid: DecodedGrid): GridTopology` |
| `website/src/atlas/geometry/polygon-parts.ts` | `h3PolygonParts`, `h3BoundaryDegrees`, `crossesAntimeridian` (the highlight layer's Cesium-free source) |
| `website/src/atlas/geometry/chunks.ts` | `interface PlannedChunk { id: number; rows: Uint32Array; seam: boolean; centroid: { lat: number; lon: number } }`, `interface ChunkPlan { chunks: PlannedChunk[] }`, `planChunks(grid: DecodedGrid, topology: GridTopology): ChunkPlan` (merge eligible while the group-bound radius ≤ 1,800 km; seam chunks keyed by side and hemisphere — Plan ruling R19, subject to the owner's ruling at Task 43 (B3.4) Step 0; Step 4a updates this note if the ruling differs), `orderChunksForCamera(plan, lookAt: { lat: number; lon: number }): number[]`, `CHUNK_MIN_CELLS = 2048`, `CHUNK_MAX_RADIUS_METRES` |
| `website/src/atlas/geometry/surface-buffers.ts` | `interface SurfaceChunkBuffers { chunk: number; positions: Float64Array; normals: Float32Array; elevationNormals: Float32Array; colors: Float32Array; heights: Float32Array; values: Float32Array; indices: Uint16Array \| Uint32Array; boundingSphere: BoundingSphere }`, `buildSurfaceChunk(input: MeshInput, chunk: PlannedChunk): SurfaceChunkBuffers`, `interface MeshInput { grid; topology; support: Uint8Array; values: Float32Array; domain: MetricDomain; palette: PaletteId; geometry: SurfaceGeometry; vertexHeights?: Float32Array }` (`vertexHeights`, when given, equals `vertexMeans(input).heights`), `vertexMeans(input): { heights: Float32Array; values: Float32Array }` (`values` hold the normalised position `t`), `paletteBins`, `isSmoothGeometry`, `SURFACE_CLEARANCE_METRES = 650`, `CPU_EXTRUSION_EPSILON_METRES`, `MAX_ELEVATION_FACTOR` |
| `website/src/atlas/geometry/support-buffers.ts` | `interface SupportChunkBuffers { chunk; unknown: FlatCellBuffers \| null; priorDominated: { bin: number; color: [number, number, number] /* sRGB bytes */; buffers: FlatCellBuffers }[] }`, `buildSupportChunk(input: MeshInput, chunk): SupportChunkBuffers`; `FlatCellBuffers { positions: Float64Array; normals: Float32Array; st: Float32Array; indices: Uint16Array \| Uint32Array; boundingSphere }` |
| `website/src/atlas/geometry/edge-buffers.ts` | `type EdgeColorSpec = { mode: 'matched' } \| { mode: 'fixed'; color: string /* #rrggbb */ }`, `interface EdgeChunkBuffers { chunk; ringOffsets: Uint32Array /* rings + 1 */; positions: Float64Array /* raised to the requested factor */; basePositions: Float64Array /* factor 0, 1,050 m clearance */; baseHeights: Float64Array /* mesh height at exaggeration 1 */; normals: Float32Array; colors: Float32Array /* RGBA per ring */ }`, `buildEdgeChunk(input: MeshInput, chunk, edgeColor: EdgeColorSpec, factor = 0): EdgeChunkBuffers`, `edgeCapacity(buffers): { primitiveCountMax; vertexCountMax }`, `brighterEdgeBytes`, `EDGE_CLEARANCE_METRES = 1_050` (Plan ruling R7) |
| `website/src/atlas/geometry/anchors.ts` | `interface ObservationAnchors { heights: Float64Array /* per point, exaggeration 1 */; triangles: Float64Array /* 9 per point: lat, lon, height ×3; NaN when flat */ }`, `observationAnchors(input: MeshInput, points: Float64Array /* lon, lat interleaved */): ObservationAnchors` |
| `website/src/atlas/geometry/pick-resolver.ts` | `interface PickRay { origin: Vec3; direction: Vec3 }`, `interface SurfacePickInput { cartesian: [number, number, number] \| null; ellipsoidHit: { lat: number; lon: number } \| null /* degrees */; factor: number; geometry: SurfaceGeometry; clearance: number; ray?: PickRay \| null /* globe ECEF; only extruded reads it: the first prism it enters wins, the altitude test is the fallback */; mapFrame?: MapFrameHit \| null /* Columbus view and 2D; when set, cartesian and ray are not read */ }`, `resolveSurfaceRow(input: SurfacePickInput, surface: SurfaceArtifact, heights: (row: number) => number /* render height at exaggeration 1; 0 when masked */, meshed?: (row: number) => boolean /* map frame only; default heights(row) > 0 */): number \| null` (spec §B.6.6, amended in Part B's final review) |
| `website/src/atlas/geometry/map-frame-pick.ts` | `interface MapFrameHit { point: Vec3 /* [x, y, height] */; ray: PickRay \| null }`, `interface MapFrameMesh`, `alignToRay(point, ray)`, `firstDrawnRow(ray, point, mesh)` (the first drawn cell the ray meets within the depth-noise window), `unshearedBase(…)` (the base from the hit height when there is no ray) |
| `website/src/atlas/geometry/natural-earth.ts` | `interface NaturalEarthBuffers { ringOffsets: Uint32Array; lonLat: Float64Array /* lon, lat interleaved */; labels: { text: string; lon: number; lat: number; minLabel: number }[] }`, `parseNaturalEarth(json: unknown): NaturalEarthBuffers` (outer rings; one label per distinct `countryLabelText`), `naturalEarthHeights(buffers, surface: { grid; support; values; domain }): { borderHeights: Float32Array; labelHeights: Float32Array }`, `countryLabelText` |
| `website/src/atlas/worker/protocol.ts` | the complete protocol of Task 52 (B3.13), reproduced below |
| `website/src/atlas/worker/state.ts` | `interface WorkerState { grids: Map<string, DecodedGrid>; renderGrids: Map<string, string> /* artifactKey -> grid_sha256 */; renders: Map<string, DecodedRender> }`, `createWorkerState()` — the worker never evicts a render tier on its own (the provider caches every surface it hands out and never re-sends a render tier on a cache hit) |
| `website/src/atlas/worker/dispatcher.ts` | `WorkerPort`, `HandlerContext { id; signal; state; post(message, transfer?); timing(step, start, end, scope?: { artifactKey?; chunk? }) }`, `RequestHandler<K>`, `HandlerRegistry` (mapped over `WorkerRequestMap`: every request type needs a handler), `errorCodeFor(error, signal)` (`container_sha256` → `checksum`, other `GosaError` → `validation`, aborted → `cancelled`, else `internal`), `createDispatcher(port, handlers, state?)` |
| `website/src/atlas/worker/data-handlers.ts`, `handlers.ts`, `geometry-handlers.ts` | `DATA_HANDLERS`, `copyGrid`, `copyRender` (the worker keeps its own arrays and transfers copies); `ATLAS_WORKER_HANDLERS: HandlerRegistry` (data + geometry; warms the grid topology after `grid-ready`), `geometryRuntime(context)`; `interface GeometryWorkerContext { post; now /* epoch ms */; isCancelled; grid; gridFor; render; yieldToEventLoop }`, `createGeometryWorker(context): { handlers: GeometryHandlers; warmGrid(id, gridSha256) }`, `transferablesOf`, `messageChannelYield()` |
| `website/src/atlas/worker/atlas-data.worker.ts` | worker entry (no exports): `createDispatcher({ post: (m, t) => self.postMessage(m, { transfer: t }) }, ATLAS_WORKER_HANDLERS)` |
| `website/src/atlas/worker/client.ts` | `class AtlasWorkerClient { constructor(worker?: Worker); static unavailable(reason); loadGrid(buf: ArrayBuffer, expect: GridExpect, signal?): Promise<DecodedGrid>; loadRender(buf, ref, signal?): Promise<DecodedRender>; loadDetail(buf, ref, signal?): Promise<DecodedDetail>; buildChunks(req: BuildChunksBody, onChunk: (c: ChunkMessage) => void, signal?: AbortSignal): Promise<void>; recolour(req: RecolourBody, onChunk: (c: ChunkMessage) => void, signal?): Promise<void>; buildEdges(req: BuildEdgesBody, onChunk: (m: EdgesChunkMessage) => void, signal?): Promise<void>; parseContext(json: ArrayBuffer, signal?): Promise<NaturalEarthBuffers>; contextHeights(req: ContextHeightsBody, signal?): Promise<ContextHeights>; onStepTiming(listener: (t: StepTiming) => void): () => void; terminate(): void }`; `AtlasWorkerError { code: WorkerErrorCode; gosaCode: GosaErrorCode \| null }`, `isArtifactValidationError(error)`, `type StepTiming = { step: StepName; chunk: number \| null; artifactKey: string \| null; start; end /* page time */ }`; `startAtlasWorker(): AtlasWorkerClient` (never throws). An aborted request rejects with `name === 'AbortError'` |
| `website/src/atlas/boot.ts` | `bootAtlas()` (island module evaluation: starts the worker and `import('./scene/atlas-scene')`), `atlasWorker(): AtlasWorkerClient` (the page's single client), `loadAtlasSceneModule()`, `type AtlasSceneModule`, `atlasRequestStallMs(): number | undefined` (Task 67 (B5.1): reads `PUBLIC_ATLAS_REQUEST_STALL_MS`, set only by `build:e2e`) |
| `website/src/components/atlas/useAtlasSceneLifecycle.ts` | `useAtlasSceneLifecycle(options: { attempt; bind; cesiumToken; element; naturalEarthUrl; onReset; onUnavailable; reducedMotion; scene; markTarget; worker }): number` (scene generation; `markTarget`/`worker` added by Task 69 (B4.15)) |
| `website/src/atlas/scene-style.ts`, `frame-coalescer.ts`, `context-sources.ts`, `inline-catalog.ts`, `website/src/lib/catalog-build.ts` | `applySceneStyle`, `observationStyleFor`; `createFrameCoalescer`; `NATURAL_EARTH_BORDERS`, `NATURAL_EARTH_PLACES`, `contextSourceKey`; `INLINE_CATALOG_ID = 'atlas-catalog'`, `escapeInlineJson`, `readInlineCatalog`; `DEFAULT_ATLAS_CATALOG_PATH`, `loadPageCatalog(catalogPath?, cwd?)` (Node-only); `E2E_ATLAS_CATALOG_PATH`, `assertRequestStallOverride(catalogPath, override)` (Task 67 (B5.1); the build fails if `PUBLIC_ATLAS_REQUEST_STALL_MS` is set without the e2e catalog) |
| `website/src/atlas/static-provider.ts` (existing) | constructor `(options: { artifactDataBase: string; siteDataBase: string; inlineCatalog: unknown; worker: AtlasWorkerClient; requestStallMs?: number; documentBase?: () => string })`; `getCatalog()` resolves the inline catalog; `getSurface(ref, signal?, progress?)` returns the columnar `SurfaceArtifact` (grid + render); `getSurfaceDetail(ref, signal?, progress?)` returns `DecodedDetail` (fetched `priority: 'low'`) and attaches it; `contextSourceUrl(catalog, id)`; `getObservations(ref)`, `getExternalInfo(…)` unchanged in signature; the transitional `getSurfaceJson` exists from Task 37 (B2.14) until Task 69 (B4.15) deletes it. The explorer builds it only in the browser (`null` during server rendering) |
| `website/src/atlas/scene/surface-chunk-layer.ts` (Cesium) | `createSurfaceChunkGroup(options): SurfaceChunkGroup`, `interface SurfaceChunkGroup extends ScientificPrimitiveGroup { addChunk(surface: SurfaceChunkBuffers, support: SupportChunkBuffers): void; chunkCount(): number; readyChunkCount(): number; opacity(): number; edges: EdgeLayer; artifactKey: string }`, `surfaceChunkPickId(artifactKey, chunk)` |
| `website/src/atlas/scene/chunk-scheduler.ts` (Cesium) | `scheduleChunks(scene, group, chunks: AsyncIterable<ChunkMessage> \| ChunkMessage[], options: { frameBudgetMs: number; order: number[]; signal?; onBeforeAdd?; onAdded?; now?; stallTimeoutMs?; measureFrame?; isHidden? }): Promise<RevealStats>`; `RevealStats { frames; totalMs; longestFrameMs }`; `createMessageQueue<T>()`, `nextBatchCost`, `revealFrameBudgetMs(coarsePointer)`, `DESKTOP_FRAME_BUDGET_MS = 8`, `COARSE_POINTER_FRAME_BUDGET_MS = 50`, `SEAM_CHUNK_COST = 4`, `MAX_BATCH_COST = 64`, `CHUNK_FRAME_MEASURE = 'atlas:chunk-frame'`, `measureChunkFrame`, `interface ChunkFrameDetail { artifactKey; chunks: number[] }`; the stall timeout waits while the tab is hidden |
| `website/src/atlas/scene/edge-layer.ts`, `context-overlay.ts`, `scientific-layers.ts` (Cesium) | `createEdgeLayer`, `EdgeLayer`, `EDGE_WIDTH_PIXELS = 2`, `EDGE_ALPHA = 0.92`; `ContextOverlay` (`setSurface(artifactKey \| null, metric)`, heights from `worker.contextHeights`); `ScientificLayers` (cold reveal vs atomic swap, one commit) |
| `website/src/atlas/scene/types.ts` (existing) | `SurfacePick` becomes `{ kind: 'surface-chunk'; artifactKey: string; chunk: number }` at the scene boundary and `{ kind: 'surface'; artifactKey: string; row: number; h3Index: string }` after resolution; `ObservationPick` gains `artifactKey`; `ArtifactLoad`, `DisplayedLayer { artifactKey; metric; palette; geometry }`, `ArtifactSceneApi { setArtifact(load, progress?); onCommit(listener: (artifactKey: string) => void): () => void; onMark(listener: (mark: AtlasMark) => void): () => void; displayedLayer(); markValuesReady(artifactKey); removeSurface(artifactKey) }`; `AtlasSceneController extends ArtifactSceneApi` (the old `setArtifact(surface, observations, progress)` is removed); `AtlasSceneOptions` gains `worker: AtlasWorkerClient`, `markTarget?`, `frameBudgetMs?`; `ScientificPrimitiveGroup` moves here; `AtlasMark = 'observations-visible' \| 'surface-first-chunk' \| 'surface-visible' \| 'ready' \| 'values-ready' \| 'edges-ready' \| 'context-ready'` |

### Worker protocol (`website/src/atlas/worker/protocol.ts`)

Requests are `{ id, type } & WorkerRequestMap[type]`, responses `{ id, type } & WorkerResponseMap[type]`;
callers pass bodies (`*Body`), handlers receive full requests (`*Request = WorkerRequestOf<…>`).
`TERMINAL_RESPONSES` = `chunks-done`, `context-heights-ready`, `context-ready`, `detail-ready`,
`edges-done`, `grid-ready`, `render-ready`; `chunk` and `edges-chunk` are intermediate (Plan rulings R7–R9).

| Request (`type`) | Body | Responses |
| --- | --- | --- |
| `load-grid` | `{ buf: ArrayBuffer; expect: { entry: GridEntry; gridSha256 } }` | `grid-ready { grid: DecodedGrid }` |
| `load-render` | `{ buf; ref: ArtifactRef }` | `render-ready { render: DecodedRender }` |
| `load-detail` | `{ buf; ref; render: DecodedRender }` | `detail-ready { detail: DecodedDetail }` |
| `build-chunks` | `BuildChunksBody { artifactKey; geometry; gridSha256; lookAt: { lat; lon }; metric; observationPoints: Float64Array /* lon, lat */ \| null; palette }` | `chunk { artifactKey; chunk; index; seam; total; surface: SurfaceChunkBuffers; support: SupportChunkBuffers; anchors: ObservationAnchorBuffers \| null /* first chunk only */ }` × n, then `chunks-done { artifactKey; total }` |
| `recolour` | `RecolourBody { artifactKey; geometry; gridSha256; metric; palette }` | the same `chunk` stream in plan order (anchors `null`), then `chunks-done` |
| `build-edges` | `BuildEdgesBody { artifactKey; edgeColor: EdgeColorSpec; factor; geometry; gridSha256; lookAt; metric; palette }` | `edges-chunk { artifactKey; edges: EdgeChunkBuffers; index; total; primitiveCountMax; vertexCountMax }` × n, then `edges-done { artifactKey; total }` |
| `parse-context` | `{ json: ArrayBuffer }` | `context-ready { buffers: NaturalEarthBuffers }` |
| `context-heights` | `ContextHeightsBody { artifactKey; metric }` (the worker finds the grid via `renderGrids`) | `context-heights-ready { borderHeights: Float32Array; labelHeights: Float32Array }` (`ContextHeights`) |
| `cancel` | `{ id }` | the cancelled request ends with `error { code: 'cancelled' }` |

Every request may also produce `step-timing { id; step: StepName; chunk: number \| null; artifactKey:
string \| null; startEpochMs; endEpochMs }` (`StepName` = `verify-grid`, `decode-grid`, `topology`,
`verify-render`, `decode-render`, `mesh`, `support`, `verify-detail`, `decode-detail`) and ends with
`error { id; code: 'checksum' \| 'validation' \| 'cancelled' \| 'internal'; gosaCode: GosaErrorCode \| null;
message }` on failure. Aliases: `ObservationAnchorBuffers = ObservationAnchors`, `NaturalEarthBuffers`
re-exported, `GeometryRequestType`, `GeometryResponse`, `LookAt`, `GridExpect`.

### User Timing (read by `tests/atlas-cold-load.spec.ts`)

| Entry | Kind | Written by | `detail` |
| --- | --- | --- | --- |
| `atlas:<AtlasMark>` | mark, in the `scene.postRender` that satisfies it (with the `data-atlas-*` attribute): `context-ready` once per scene; the epoch marks (`observations-visible`, `surface-first-chunk`, `surface-visible`, `ready`) at most once per `setArtifact` (a new epoch drops the previous artifact's pending ones); `values-ready` and `edges-ready` again after each `clear()` at a commit. A page load can therefore hold several entries of one name; the cold-load harness reads the first (`firstMarkTime`) | scene marks (Tasks 58, 62 (B4.6, B4.10)) | none |
| `atlas:worker:<step>` | measure, page-time `start`/`end` | `AtlasWorkerClient` on each `step-timing` (Task 32 (B2.9)) | `{ step, chunk, artifactKey }` |
| `atlas:chunk-frame` | measure, `scene.preUpdate` → `scene.postRender` of the render after each batch add | `scheduleChunks` (Task 57 (B4.5)) | `{ artifactKey, chunks }` |
| `atlas:chunk-add` | mark per added chunk | `ScientificLayers` (Task 62 (B4.10)) | `{ artifactKey, chunk }` |
| `atlas:last-byte:<tier>:<key>` | mark when a tier's last byte arrives (`tier` ∈ grid, render, detail, observations; key = grid sha256 or `artifactKey`) | provider (Task 37 (B2.14)) | none |

`data-atlas-reveal` on `.atlas-explorer` holds `{"frames","totalMs","longestFrameMs"}` of the cold reveal.

### Inline catalog and head script

- `website/src/pages/app.astro` embeds, in `SiteLayout`'s `head` slot, `<script type="application/json"
  id="atlas-catalog" data-artifact-data-base="…">` (with `<` escaped as `<`), validated at build
  time with `atlasCatalogSchema` (`loadPageCatalog`), and an inline module-free `<script>` built from
  `website/src/atlas/preload-script.ts` (`preloadScriptSource(): string`, Cesium-free) that inserts
  `<link rel="preload" as="fetch" crossorigin="anonymous">` for the URL-selected artifact's grid,
  render and observations (default `artifacts[0]`), plus `<link rel=preconnect>` only for an absolute
  base. The Astro integration `website/integrations/atlas-scene-preload.mjs` adds
  `<link rel="modulepreload">` for the scene chunk and its static imports (the `cesium.<hash>.js`
  chunk of Task 80 (B5.11)).
- Build variable `ATLAS_CATALOG_PATH` (default `public/data/atlas/catalog.json`, resolved from `website/`).
- Build variable `PUBLIC_ATLAS_REQUEST_STALL_MS` (e2e build only, `120000`; any other build refuses it, so production keeps the 15 s stall window of §B.2).

### Readiness attributes (on `.atlas-explorer`)

`data-atlas-ready`, `data-atlas-active` (existing), plus `data-atlas-observations-visible` and
`data-atlas-surface-visible` (turn `'true'` once per scene and stay true), `data-atlas-values-ready`
and `data-atlas-edges-ready` (describe the displayed artifact; reset at each commit),
`data-atlas-context-ready`, `data-atlas-displayed` (space-separated artifact ids of the shown groups;
tests compare the set).

### Test fixtures

- `tests/fixtures/atlas-web/export/` — a real resolution-3 export tree (`catalog.json`,
  `hbs-rs334.{surface,observations,manifest}.json`, `g6pd-deficiency.{surface,manifest}.json`,
  `grids/…`, `surfaces/…`), written by `tests/fixtures/atlas-web/regenerate.py`; `tests/fixtures/atlas-web/mutations/`
  — the shared corpus (30 `.gosa` + `manifest.json`).
- `website/tests/fixtures/atlas/golden/` — byte copy of `export/` plus `golden/mutations/`.
- `website/tests/fixtures/atlas/parity/` — the 1,986-cell `cyt-il-6-174-c` subset (`catalog.json`,
  surface and manifest JSON, its own grid and render/detail objects).
- `website/tests/fixtures/atlas/e2e/` — compact catalog for all 30 artifacts (256 cells, 64
  observations each); every key K the client fetches (`grids.*.url`, `web.render.url`, `web.detail.url`,
  `observations_url`) is the file `e2e/K`; `surface_url` and the surface/manifest downloads keep naming
  the full canonical artifacts and are not in the tree.

### Test support

`website/tests/atlas-browser-fixture.ts` (imports only `node:` built-ins and type-only Playwright):
`type ArtifactTier = 'grid' | 'render' | 'detail' | 'observations'`, `interface FixtureCatalog`,
`E2E_FIXTURE_DIR`, `E2E_CATALOG_PATH`, `E2E_ARTIFACT_DATA_BASE = '/data/atlas/'`,
`installAtlasBrowserFixture(page, options?: { appUrl?: string })`, `readInlineCatalog(page, appUrl?)`,
`extractInlineCatalog(html)`, `artifactTierKey(catalog, id, tier)`, `fetchedKeys(catalog)`,
`urlMatchesKey(url, key)`, `readE2eCatalog()`, `readE2eObject(key)`,
`delayArtifactTier(page, id, tier, ms, options?) → { hits(); release() }`,
`corruptArtifactTier(page, id, tier, options?)`, `failArtifactTier(page, id, tier, options?)`
`→ { hits(); restore() }`, `displayedArtifactIds(page)`; Part C adds `extractArtifactDataBase(html)` and
fulfils objects only for a same-origin artifact base. npm scripts: `build:e2e`, `test:e2e`,
`capture:fast-load`; `website/serve.json`; `website/tests/support/{gosa-builder,in-process-worker,production-build}.ts`;
the Cesium chunk is `dist/_astro/cesium.<hash>.js` (Rolldown `codeSplitting.groups`, Plan ruling R16; the group matches Cesium's `.js` modules only, so `widgets.css` never pulls the chunk into the island).


### GOSA error codes and check order

`GosaError` (Python `GosaError(code, message)`, attribute `.code`; TS `GosaError` with
`readonly code: GosaErrorCode`) carries one code of `GOSA_ERROR_CODES` (exported by
`surface_codec.py` and `website/src/atlas/gosa/container.ts`, re-exported by `decode.ts`), in this
vocabulary order: `truncated, magic, format_version, reserved, header_encoding, header_json,
header_schema, tier, identity, columns, column_length, offset, trailing_bytes, padding, grid_order,
h3_cell, grid_sha256, support_code, non_finite, value_range, interval_order, n_cells, source_sha256,
cross_tier, container_sha256`. Python `decode` and the TS `decodeGrid`/`decodeRender`/`decodeDetail`
run the checks below in this order and raise the first failure with the code shown; the TS decoders
run the container digest first (check 0) and the catalog-context checks last. "Same error class" in
spec §B.3 means equal `code`.

| # | Check | Code |
| - | ----- | ---- |
| 0 | (context, before decoding) container length ≠ declared `bytes` or SHA-256 ≠ declared `sha256` | `container_sha256` |
| 1 | fewer than 12 bytes | `truncated` |
| 2 | bytes 0–3 ≠ `GOSA` | `magic` |
| 3 | u16 at 4 ≠ 1 | `format_version` |
| 4 | u16 at 6 ≠ 0 | `reserved` |
| 5 | `12 + header_length` > file length | `truncated` |
| 6 | header not UTF-8 (`TextDecoder('utf-8', {fatal: true})`; one leading BOM is consumed) | `header_encoding` |
| 7 | header not JSON (`JSON.parse`; `NaN`/`Infinity` are not JSON) | `header_json` |
| 8 | strict header: an object with exactly the 8 keys; `schema_version` 1; `tier` ∈ {grid, render, detail}; `n_cells` safe integer ≥ 0; `resolution` integer 0–15; `grid_sha256` 64 lowercase hex; `columns` an array of objects with exactly `{dtype, encoding, length, name, offset}`, strings for the first three and safe integers ≥ 0 for the last two; grid ⇒ `artifact` and `source_surface_sha256` null; render/detail ⇒ `artifact` an object and `source_surface_sha256` 64 hex. Integers are JS numbers: `3.0` is 3, booleans are never integers | `header_schema` |
| 9 | header `tier` ≠ requested tier | `tier` |
| 10 | render/detail: `artifact` fails `artifactIdentitySchema`, or header `resolution` ≠ `artifact.resolution` | `identity` |
| 11 | `[name, dtype, encoding]` list ≠ the normative list for the tier | `columns` |
| 12 | any `length` ≠ `n_cells × width` (u8 1, f32 4, f64 8, u64 8) | `column_length` |
| 13 | `offset[0] ≠ 0` or `offset[i] ≠ align8(offset[i-1] + length[i-1])` | `offset` |
| 14 | file shorter / longer than `align8(12 + header_length) + last.offset + last.length` | `truncated` / `trailing_bytes` |
| 15 | any non-zero byte between header end and the column area, or between columns | `padding` |
| 16 | grid: per row i ≥ 1, `delta == 0` or the running sum reaches 2⁶⁴ (carry out of the high u32 lane) | `grid_order` |
| 17 | grid: per row, `!isValidCell([lo, hi])` or `getResolution ≠ resolution` | `h3_cell` |
| 18 | grid: SHA-256 of the decoded little-endian u64 column ≠ header `grid_sha256` | `grid_sha256` |
| 19 | render: per row, support code > 3 | `support_code` |
| 20 | render `post_mean`, `post_sd`; detail the six columns in order — per column, per row: not finite, then out of range (`post_mean`, `q025`, `q975` ∈ [0, 1]; all others ≥ 0; no `metric_domains` check) | `non_finite` / `value_range` |
| 21 | detail: per row `q025 > post_mean` or `post_mean > q975` (float64) | `interval_order` |
| 22 | (context, `verify_artifact_tiers`) grid header `grid_sha256` ≠ catalog `grids` key | `grid_sha256` |
| 23 | (context) grid, render or detail `n_cells` ≠ ref `n_cells` | `n_cells` |
| 24 | (context) render/detail header `grid_sha256` ≠ catalog key | `grid_sha256` |
| 25 | (context) any of the 13 `IDENTITY_FIELDS` (absent ≡ absent), `label`, or `metric_domains` (deep) differs from the ref | `identity` |
| 26 | (context) `source_surface_sha256` ≠ ref `surface_sha256` | `source_sha256` |
| 27 | (context) `Math.fround(detail.post_mean/post_sd[i])` bits ≠ render's; then per state (in `SUPPORT_CODES` order) histogram ≠ `support_counts[state] ?? 0` | `cross_tier` |

TS `decodeGrid(buf, { gridSha256, entry })`: `entry.n_cells` mismatch → `n_cells`; `entry.resolution`
mismatch → `header_schema` (the only TS-only check; Python decodes a grid without an entry). The
render tier's support histogram mismatch (check 27, second half) is raised by `decodeRender`, the
float32 comparison (first half, bit-exact) by `decodeDetail`.

### Shared mutation corpus

- Python copy: `tests/fixtures/atlas-web/mutations/`; website copy (byte-identical, asserted by
  `tests/test_atlas_web_fixtures.py`): `website/tests/fixtures/atlas/golden/mutations/`.
- `manifest.json` = `{"codes": GOSA_ERROR_CODES, "mutations": [entry…]}`, each entry
  `{artifact, base, bytes, code, file, grid_sha256, sha256, tier}`: `tier` is the tier to request;
  `code` the expected `GosaError.code`; `base` the golden object (relative to the golden tree) the
  file was derived from; `artifact` the catalog id for render/detail bases (`hbs-rs334`), `null` for
  grid; `grid_sha256` the golden `grids` key; `sha256`/`bytes` describe **the mutated file**, so a
  TS test passes them as the declared digest/size (override `entry.sha256/bytes` or
  `ref.web.<tier>.sha256/bytes`) and step 0 passes. Render/detail mutations decode against the
  golden grid (and, for detail, the golden render) of `golden/catalog.json`.
- Files and codes (all derived from `hbs-rs334` and the golden grid):

| File | Tier requested | Code |
| ---- | -------------- | ---- |
| `grid-truncated-preamble.gosa` | grid | `truncated` |
| `grid-bad-magic.gosa` | grid | `magic` |
| `grid-format-version-2.gosa` | grid | `format_version` |
| `grid-reserved-1.gosa` (spec) | grid | `reserved` |
| `render-header-invalid-utf8.gosa` | render | `header_encoding` |
| `render-header-not-json.gosa` | render | `header_json` |
| `render-header-extra-key.gosa` | render | `header_schema` |
| `grid-header-boolean-n-cells.gosa` | grid | `header_schema` |
| `render-requested-as-detail.gosa` | **detail** | `tier` |
| `render-identity-missing-label.gosa` | render | `identity` |
| `render-columns-reordered.gosa` | render | `columns` |
| `render-column-wrong-dtype.gosa` | render | `columns` |
| `render-column-length.gosa` | render | `column_length` |
| `render-offset-plus-8.gosa` (spec) | render | `offset` |
| `grid-trailing-byte.gosa` (spec) | grid | `trailing_bytes` |
| `detail-truncated-column.gosa` | detail | `truncated` |
| `render-pad-byte.gosa` (spec, 0x01) | render | `padding` |
| `grid-msb-first-planes.gosa` (spec) | grid | `grid_order` |
| `grid-zero-delta.gosa` (spec) | grid | `grid_order` |
| `grid-reserved-h3-bit.gosa` (spec) | grid | `h3_cell` |
| `grid-mode-2.gosa` (spec) | grid | `h3_cell` |
| `grid-digit-7.gosa` (spec) | grid | `h3_cell` |
| `grid-base-cell-122.gosa` (spec) | grid | `h3_cell` |
| `grid-wrong-resolution.gosa` (spec) | grid | `h3_cell` |
| `grid-header-sha-mismatch.gosa` | grid | `grid_sha256` |
| `render-support-code-4.gosa` | render | `support_code` |
| `render-post-mean-nan.gosa` | render | `non_finite` |
| `detail-post-sd-negative.gosa` | detail | `value_range` |
| `detail-post-mean-above-one.gosa` | detail | `value_range` |
| `detail-q025-above-mean.gosa` | detail | `interval_order` |

  h3-js 4.5.0 was checked on the five mutated H3 cells (`[lo, hi]` lanes): `isValidCell` is false
  for the reserved bit, mode 2, digit 7 and base cell 122, and the wrong-resolution cell is valid at
  resolution 4 — the same verdicts as h3-py. Context codes (`n_cells`, `identity` vs ref,
  `source_sha256`, `cross_tier`, `container_sha256`) are not file mutations; the TS tests
  exercise them with altered refs, as `tests/test_surface_codec.py::test_context_refusals_use_their_own_codes`
  does in Python.

## Part C (GCS)

| Item | Name |
| --- | --- |
| build variable | `PUBLIC_ATLAS_DATA_BASE_URL` (absolute `https://…/atlas/web/`, trailing `/`; `''` = unset), validated by `artifactDataBaseFrom` |
| repository variables | `ATLAS_DATA_BASE_URL`, `ATLAS_DATA_BUCKET` |
| scripts | `scripts/provision_atlas_web_bucket.py --mode edge\|cloud-cdn [--dry-run] --bucket NAME [--project ID]`, `scripts/publish_atlas_web.py --staging DIR --bucket NAME [--dry-run] [--work-dir DIR]`, `scripts/check_atlas_web_data.py --catalog PATH --base URL --bucket NAME --dist DIR [--production] [--api-root URL]` (`--production` also requires `dist/app/index.html` to bake `--base` and inline exactly `--catalog`); the provisioning script adopts an existing bucket only with the `genomeos-purpose=atlas-web` label it sets at creation and the project's `projectNumber`, and never lifts public-access prevention |
| GCS metadata keys | `sha256`, `decoded-bytes` (served as `x-goog-meta-sha256`, `x-goog-meta-decoded-bytes`) |
| baked bases | `<script type="application/json" id="atlas-data-bases">{"artifact":…,"site":…}</script>` in `/app/` (same artifact base as `data-artifact-data-base`) |
| modules | `genomeos/publication/web_layout.py` (`apply_download_layout`, `DownloadCopy`, `WebLayoutError`, `artifact_objects`, `critical_objects`, `site_objects`, …), `scripts/atlas_web_gcloud.py`, `scripts/atlas_web_staging.py` (`write_download_copies`, `StagingError`), `deploy/atlas-web-cors.json`, `website/scripts/serve-atlas-data.mjs`, `website/tests/support/atlas-data-target.ts` |
| npm scripts | `serve:atlas-data`; `test:e2e` = `PUBLIC_ATLAS_DATA_BASE_URL=http://127.0.0.1:4323/ npm run build:e2e && playwright test` |
| opt-in data | `ATLAS_DATA_DIR` (a staging tree: `catalog.json` + objects at their keys) |

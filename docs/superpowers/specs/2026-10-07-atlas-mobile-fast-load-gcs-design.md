# genomeOS Atlas — Mobile Sheets, Near-Instant Default Load, and GCS-Hosted Web Data — Design

**Status:** approved (owner, 2026-10-07); revised after a five-lens adversarial review (62 confirmed
findings folded in; see the rulings table at the end)

**Date:** 2026-10-07

**Scope:** The `/app/` explorer (Atlas design §11; Cesium explorer design 2026-09-06 §7.3, §9, §12;
interaction design 2026-09-07 §8–§9, §15–§16) and the web publication path that follows
`scripts/export_atlas_web.py`. Three sub-projects, each a stacked branch and pull request, merged
in order A → B → C:

| Part | Branch                     | Outcome                                                                  |
| ---- | -------------------------- | ------------------------------------------------------------------------ |
| A    | `feat/atlas-mobile-sheets` | Phones get a usable globe: bottom sheets, no page zoom-out               |
| B    | `feat/atlas-fast-load`     | The default HbS points and surface appear in seconds, not 15–33 s        |
| C    | `feat/atlas-gcs-web-data`  | Per-artifact web data lives in a public GCS bucket; 598 MB leaves `main` |

No P0–P4 scientific contract, fitted value or `contract/` schema changes. No coarse aggregated
preview tier is introduced (§B.6.10).

**Issues first (AGENTS "Filing work").** Before the first work commit of each part, one issue is
filed for it, citing this spec and #172 (the transition/progress rules). Labels: A and B —
`type:ui`, `P5:map-ui`, `skill:frontend`, `priority:high`; C — `type:infra`, `P5:map-ui`,
`skill:data-engineering`, `priority:high`. The commit that completes each part carries
`closes #N`; each PR body repeats it. When C's issue is filed, a cross-reference comment is posted
on #33: the public web bucket serves only encoded site data and does not replace #33's private
artifact staging and pinning.

---

## 0. Evidence this design answers

Measured on the deployed site and on HEAD `5a10b15` (cold cache, navigation → `data-atlas-ready`):

| Run                                        | Today                                        |
| ------------------------------------------ | -------------------------------------------- |
| Desktop, no throttling                     | 9.6–12.9 s                                   |
| Mobile emulation (4× CPU, Fast 4G)         | 33.1 s                                       |
| Mobile emulation, Slow 4G                  | **never loads** (15 s whole-request timeout) |

Mobile cost centres: (1) one 12.8 s main-thread task in `AtlasScene.setArtifact` — per-cell h3
string calls (`cellToVertexes` 5× per cell, vertex heights computed twice), the Natural Earth
border re-height that runs even at elevation 0 (2.5 s), ~429k per-vertex CSS colour-string round
trips; (2) surface download 8.8 s (5.1 MB gzip / 20 MB JSON); (3) cell-outline build 6.9 s, awaited
before ready; (4) Cesium's synchronous first-frame `combineGeometry` and outline upload 4.0 s;
(5) 2.9 s before the data request starts (it waits for the 1.18 MB-gzip Cesium chunk, the viewer
and the catalog). JSON parse + zod are under 1 s. **A smaller file alone removes ~10 of 33 s; the
render pipeline must change too.** On a 390×844 phone the header overflows to 443 px so the browser
zooms out, the control dock covers 52% of the globe even fully collapsed, and the inspector raises
coverage to 91.5%.

---

## Part A — Mobile layout

Applies at `(max-width: 52rem)` (≤ 832 px; the existing single mobile switch point). Landscape
phones under 34rem tall use the same sheets with `peek` reduced to the handle row. Landscape phones
833–932 px wide keep the desktop dock (out of scope; noted in the PR).

### A.1 Outcome and acceptance

1. **No horizontal overflow and no zoom-out.** For every route in the Playwright `topLevelRoutes`
   list, in `isMobile` contexts at 360, 390 and 412 px:
   `document.documentElement.scrollWidth <= document.documentElement.clientWidth`, and
   `visualViewport.scale === 1`. `SiteLayout` emits `width=device-width, initial-scale=1` on every
   page; it takes a `viewportFit?: 'cover'` prop that only `/app/` sets. `src/pages/app/polygon.astro`
   gets the same `initial-scale=1`. The `/contribute/` `<article>` cards that reach 364 px at 360 px
   are fixed so the new meta does not turn them into a horizontal scroll.
2. **No vertical page scroll on `/app/`.** On `/app/` the body is a `100svh` flex column: the
   header takes its natural height and `.atlas-explorer` fills the rest (`flex: 1 1 auto;
   min-height: 0`), replacing `calc(100svh - 4.75rem)` (which is 1 px short of the 86.5 px header and
   lets the document rubber-band). `.site-header--compact` does not change the header height on
   `/app/`. Assert `scrollHeight <= clientHeight` and explorer bottom == viewport bottom in both
   Playwright projects and the 360/390 contexts. `html` gets `overscroll-behavior-y: none` on
   `/app/` only (page-scoped class), so pull-to-refresh cannot fire during sheet drags. Picker
   `top` clamps (today hard-coded 76/96/104 px) read
   `document.querySelector('[data-site-header]').getBoundingClientRect().bottom` plus a gutter.
3. **Globe reachable.** With every sheet at `peek`, at least **65%** of the explorer area hit-tests
   to the Cesium canvas (`document.elementFromPoint` on a 12 × 20 grid), and the central region
   (middle 60% of width × middle 40% of height) is 100% canvas. At `peek` the legend strip, credit
   block and status stack lie entirely outside the central region. A one-finger drag at the centre
   changes the camera.
4. **Top entity selector.** Only the `MapCatalogPicker` trigger moves to the top on mobile, into an
   always-rendered `<div class="atlas-top-slot">` that is the first child of `.atlas-explorer`
   (absolutely positioned; empty on desktop, so desktop layout is unchanged). The slot element is
   handed to `ExplorerControls` through a callback ref stored in state. `ExplorerControls` still
   renders exactly once; the trigger is placed with a React portal selected by a
   `useSyncExternalStore` hook over `matchMedia('(max-width: 52rem)')` with
   `getServerSnapshot = () => false`. The "Select dataset" title is not repeated (the trigger's
   aria-label starts with it); the dataset InfoTip moves into the sheet's peek row. The dense trigger
   and InfoTip rules (`atlas.css` ~2136–2146, 2190–2192) are re-scoped to
   `:is(.atlas-controls, .atlas-top-slot)`. Focus order on mobile: header → selector → canvas →
   sheet.
5. **The controls bottom sheet.** `aside.atlas-controls` is restyled in place as a bottom sheet with
   states `peek | half | full`, exposed as `data-sheet-state` on the sheet root.
   - **Handle**: a `<button>` outside every inert region, `aria-controls` the sheet body,
     `aria-expanded="false"` at peek and `"true"` at half/full, accessible name including the state
     ("Explorer controls, peek" / "… half height" / "… full height"). Enter/Space cycle
     peek → half → full → peek with focus staying on the handle. ≥ 44 px tall.
   - **Peek**: handle plus one plain-text summary row (current dataset short label and metric; no
     focusable descendants, no `<details>`). Everything below it carries `inert` (never
     `aria-hidden`). Peek height ≤ 18% of the explorer, ≥ 56 px.
   - **Half** ≈ 50% of the explorer; **full** = `min(0.88 × explorerHeight, explorerHeight −
     topChromeBottom − 8 px − dockedHeight)`, where `topChromeBottom` is the largest
     `getBoundingClientRect().bottom` (relative to the explorer) of the warning banner, top selector,
     status stack and view notice, recomputed by ResizeObserver/MutationObserver, and `dockedHeight`
     is the legend strip plus credit block (A.1.7).
   - At half and full the sheet body is a scroll container whose height is the visible sheet height
     (`overscroll-behavior: contain`); it never translates a taller panel off-screen, so every
     focusable control can scroll into view.
   - **Drag**: only the handle starts a drag; it has `touch-action: none` and calls
     `setPointerCapture` on pointerdown. Movement ≥ 8 CSS px from pointerdown is a drag, less is a
     tap. On release project `y + v × 120 ms` and snap to the nearest state; a flick faster than
     0.5 px/ms moves exactly one state in its direction; travel is clamped between peek and full, no
     rubber band. `pointercancel`/`lostpointercapture` without `pointerup` restores the pre-drag
     state. A drag that ends on pointerup sets a suppress flag; the handle's click listener calls
     `preventDefault()` and clears it when set; the flag also clears on the next task
     (`setTimeout(0)` after pointerup) and on any later pointerdown/keydown, so a touch drag never
     swallows the next real tap or Enter/Space.
   - During drag the sheet writes `--atlas-sheet-offset` (px) on `.atlas-explorer` once per
     animation frame without a React re-render.
   - **Entering peek** (tap, drag, Escape, or restoring after a panel closes): if focus is inside
     the region about to become inert, move focus to the handle **before** setting `inert`.
   - Native `<details>` sections inside the sheet keep their `summary` text, `open` attribute and
     `::details-content` transition. "Scientific layers" stays open by default inside the sheet.
6. **The panel sheet (inspector / More info).** `.atlas-right-rail` is restyled in place as a second
   sheet (the `[data-atlas-external-slot]` portal target is never moved or remounted), with its own
   handle `<button>` and the same snap/drag rules. Its peek row is the panel's `<h2>` and Close
   button; it opens at `half`. The inspector and the external panel are mutually exclusive on mobile:
   whichever opened most recently is shown and opening one closes the other (closing the inspector
   clears the scene selection; closing the external panel aborts its request). While either is
   open the controls sheet has `inert` and `hidden`. Focus: opening from "More info" moves focus to
   the panel's Close button; opening from a canvas tap leaves focus where it is; on close, first
   restore the controls sheet to its previous snap state and remove `inert`, then move focus to
   "More info" if that opened the panel, otherwise to the canvas region (`tabIndex=-1` if needed).
   Focus never falls to `<body>`.
7. **Legend and attribution docking.** The legend strip and the credit block are positioned with
   `bottom: var(--atlas-sheet-offset)` (compositor `transform` during drag) so they always sit
   directly above the active sheet's top edge; the full-height cap (A.1.5) leaves room for them.
   - **Legend strip** — one row `[metric label | ramp | info trigger]`: the visible label is a short
     form at 0.8rem ("Frequency" / "Uncertainty") with the full label as `.visually-hidden` text and
     in the popover heading; ramp `minmax(6rem, 1fr)` with numeric endpoints under its ends in a
     two-column sub-grid at 0.72rem; the scale container is `role="img"` with an `aria-label` built
     from the data (e.g. "Modeled frequency colour scale, 0.08% to 17.3%"); the info trigger is ≥
     24 × 24 CSS px. The legend `<details>` gains Escape handling (close, focus the summary,
     `stopPropagation()`), which it lacks today (interaction design §9.2).
   - **Credit block** — Cesium's `bottomContainer` stays inside `.atlas-scene` (Viewer.resize writes
     inline left/bottom/right, so placement rules keep `!important`); on mobile it and the data
     credit form one wrapping block (not limited to one line): the ion logo at its native size plus
     map credits, then the data credit as a short link "Data: genomeOS" at the same 10 px size.
     `.atlas-data-credit` is re-enabled at ≤ 52rem (hidden today). Its height is measured with a
     ResizeObserver (basemap credits change; Stadia makes it three lines at 360 px) and counted in
     `dockedHeight`.
8. **Header status.** Scoped to `body:has(.atlas-explorer)` at ≤ 52rem: wordmark 1rem with .08em
   letter-spacing (Raleway kept); the Menu summary becomes a 44 × 44 icon target with "Menu" kept as
   `.visually-hidden` text; `.site-header__actions { min-width: 0; flex: 1 1 auto }`; the status
   slot drops its fixed width (`flex: 0 1 auto; min-width: 0`); the chip label is always the full
   `activity.label` cut by CSS ellipsis (never a different string); the progress meter row stays
   visible; the detail `<small>` becomes `.visually-hidden` instead of `display:none` so it stays in
   the live region. At 360 and 390 px: `.site-header__inner` `scrollWidth <= clientWidth` and the
   chip's right edge ≤ the Menu summary's left edge.
9. **One Escape stack.** Each Escape closes only the innermost open layer, in order: InfoTip or
   legend popover → catalog or earth dialog → external panel → inspector → controls sheet to peek.
   It is implemented as an ordered layer stack in the explorer with one capture-phase `document`
   `keydown` listener that closes the top layer and calls `preventDefault()`; pickers, panels,
   popovers and the sheets register and unregister their close callbacks. The independent window
   listeners (`AtlasExplorer.tsx` ~606–615, `ExternalInfoPanel.tsx` ~245–251) are replaced. The
   sheet handle's own keyboard handling is an `onKeyDown` on the handle button (no children, so
   portal bubbling cannot reach it).
10. **Touch targets (WCAG 2.2 SC 2.5.8 as axe measures it).** Every enabled interactive target in
    the explorer is ≥ 24 × 24 CSS px or has a non-overlapping 24 px circle. InfoTip triggers and the
    legend summary keep their glyph but grow to a ≥ 24 px box via padding/min-size **on desktop
    too** (this fixes the existing violation on "About displayed metric"). Sheet handles and summary
    rows are ≥ 44 px at ≤ 52rem.
11. **Constraints kept.** Exactly one `<h1>` (visually hidden on mobile with the existing
    `.visually-hidden` utility, placed in an always-present node so it stays in the accessibility
    tree while the controls sheet is hidden); landmarks and names tests query (`complementary`
    "Explorer controls", "Map legend", "Selected map cell" / "Selected observation",
    "External variant information"; root `application` "genomeOS globe explorer"; canvas `region`
    "Interactive globe canvas"); the hard-coded ids and radio names are not duplicated; the
    once-only slot lookups (`[data-atlas-external-slot]`, `[data-atlas-status-slot]`) still find a
    stable node; the dense type sizes tests pin (13.25 px field, 14.4 px summary) — the
    interaction-spec §9.1 16 px conflict is recorded in the PR, not silently resolved; reduced motion
    snaps sheets without animation.
12. **CSS placement.** New mobile rules go inside `atlas.css` between the end of the "Dense Atlas
    UI" block and the preference blocks (`prefers-reduced-motion`, `prefers-contrast: more`,
    `pointer: coarse`), so they override the dense rules but not the preference rules.
13. **Desktop.** Desktop layout and behaviour are unchanged except for these listed deltas: the
    24 px target boxes (A.1.10), the legend Escape handling, the Escape stack, the header-height
    flex layout (+1 px explorer height) and the empty top slot. Desktop axe, keyboard and existing
    tests keep passing.

### A.2 Code organisation

`AtlasExplorer.tsx` (755 logical lines) does not grow: the sheet state machine, drag handling,
media hook, Escape stack and top-slot wiring live in new hooks/components under
`src/components/atlas/` (e.g. `useBottomSheet.ts`, `useMediaQuery.ts`, `useEscapeStack.ts`,
`BottomSheetHandle.tsx`), each Cesium-free.

### A.3 Tests

Playwright `mobile-chromium` (Pixel 7) plus explicit 360×780 and 390×844 contexts:

- overflow and zoom (A.1.1) for every top-level route; header fit (A.1.8); no vertical scroll (A.1.2);
- canvas coverage and centre region at peek (A.1.3), with the default basemap and one Stadia basemap,
  including credit/legend placement outside the centre;
- selector visible without opening any sheet (A.1.4); Tab from the header reaches the selector before
  the canvas;
- sheet cycle by tap and Enter with the exact `aria-expanded` values and handle names; Tab order at
  peek skips the inert body; at full/half with and without a forced warning banner, the sheet top is
  ≥ `topChromeBottom` + 8 and no docked element intersects top chrome;
- touch drag through a CDP session (`Input.dispatchTouchEvent` touchStart → touchMoves → touchEnd on
  the handle): `data-sheet-state` peek → half → full; a downward drag at scrollTop 0 leaves
  `window.scrollY` unchanged; no pointercancel reached the handle; mouse drag moves exactly one step
  with no trailing-click advance, and a following click and Enter each cycle once; a synthetic
  pointercancel mid-drag restores the pre-drag state; one-finger globe drag via the same helper;
- legend: ramp ≥ 108 px wide, visible label non-empty, no legend overflow, popover opens on tap and
  Escape closes it with focus on the summary and the selection intact;
- inspector on mobile: load the camera URL used by the desktop picking test, `page.touchscreen.tap`
  near the centre (retrying with `clickNearCenter` offsets), assert the inspector sheet is visible
  and the controls sheet is hidden/inert (no hover-preview assertions), Escape clears the selection,
  restores the controls sheet's prior state, and `document.activeElement` is not `<body>`; with a cell
  selected, open the catalog and press Escape — the inspector stays; open "More info", focus is on
  its Close button, close it, focus returns to "More info";
- axe after `data-atlas-ready="true"` at peek, half and full in Pixel 7 and the plain 390×844
  context; the existing route axe test also waits for ready;
- existing mobile-project explorer tests that assume the dock is open expand the sheet first via a
  shared helper; their assertions are otherwise unchanged. The dense font-size assertion for the
  selector moves to `.atlas-top-slot` on mobile.

Capture: `website/scripts/capture-atlas.mjs` gains a 390×844 mobile capture; before/after PNGs are
committed as `docs/figures/atlas-mobile-{before,after}.png`.

---

## Part B — Near-instant default load

### B.1 Outcome and acceptance

**Measurement contract** (`website/tests/atlas-cold-load.spec.ts`, run by
`npm run build && npm run test:performance`):

- **Environment.** Headed Chrome (`channel: 'chrome'`) on a hardware GPU; the spec records the
  `WEBGL_debug_renderer_info` renderer and the machine in its JSON attachment and skips budget
  assertions on SwiftShader/software renderers. Each run is a fresh browser context with a cold HTTP
  cache; the spec reports the median of 3 runs and asserts budgets on the median.
- **Profiles.** Desktop: 1440×900, no throttling. Mobile: 390×844 at DPR 3, `isMobile`, `hasTouch`,
  CDP `Emulation.setCPUThrottlingRate {rate: 4}` on the page **and on every dedicated-worker target**
  (`Target.setAutoAttach {autoAttach: true, flatten: true, waitForDebuggerOnStart: true}`, throttle
  each worker session, then resume it). If worker throttling is refused by Chrome, the spec instead
  rebuilds the critical path from the worker's step timings (below) with each worker step's duration
  × 4, keeping dependencies (topology waits for grid bytes; mesh waits for topology and render bytes;
  a chunk's reveal waits for its mesh), and reports both raw and scaled times. Network via CDP
  `Network.emulateNetworkConditions` (Chrome DevTools presets):
  Fast 4G `{latency: 165, downloadThroughput: 1012500, uploadThroughput: 168750}`;
  Slow 4G `{latency: 562.5, downloadThroughput: 180000, uploadThroughput: 84375}`.
- **Marks.** Taken in a `scene.postRender` callback (the scene uses `requestRenderMode`), each also
  mirrored as a `data-*` attribute on `.atlas-explorer`:

  | Mark / attribute                                    | Meaning                                                                                     |
  | --------------------------------------------------- | ------------------------------------------------------------------------------------------- |
  | `atlas:observations-visible` / `data-atlas-observations-visible` | first frame where the observation group is ready and shown                       |
  | `atlas:surface-first-chunk`                         | first frame where one surface chunk (with its masked cells) is ready and shown               |
  | `atlas:surface-visible` / `data-atlas-surface-visible` | every surface chunk and its support cells are ready and shown at non-zero opacity (the fade is not counted) |
  | `atlas:ready` / `data-atlas-ready`                  | unchanged meaning: surface, support, observations of the requested artifact visible          |
  | `atlas:values-ready` / `data-atlas-values-ready`    | the verified detail tier for the displayed artifact is loaded                                |
  | `atlas:edges-ready` / `data-atlas-edges-ready`      | cell outlines built (when enabled)                                                          |
  | `atlas:context-ready` / `data-atlas-context-ready`  | Natural Earth borders and labels built (when enabled)                                        |

  `data-atlas-displayed` lists the artifact id of each shown scientific primitive group (test hook
  for B.6.8).
- **Worker step timings.** The worker posts `{step, start, end}` (page time origin) for: verify grid,
  decode grid, topology, verify render, decode render, mesh per chunk, support per chunk; the
  provider records when each tier's last byte arrives; the main thread records each chunk add.
- **Long tasks.** Window: navigation start → max(`atlas:edges-ready`, `atlas:context-ready`) plus a
  1 s quiet period. Collected with `PerformanceObserver` `long-animation-frame` (`buffered: true`),
  attributed by `scripts[].sourceURL`: Atlas chunks and worker-message handlers count as Atlas; the
  Cesium chunk (stable name via Vite `manualChunks`) counts as Cesium, except that `Primitive.update`
  work on frames that add Atlas chunk primitives counts as Atlas. Cesium module evaluation is reported
  separately.
- **Transport.** The spec asserts `content-encoding` ∈ {`gzip`, `br`} on grid, render and
  observations responses and records which; the context sends `Accept-Encoding: gzip, deflate` so
  local transfer matches production (GCS and Pages send gzip). It asserts each preloaded resource is
  fetched exactly once.
- **Baseline.** The "Today" column is re-measured with this harness on a build of `5a10b15`.

**Budgets** (median of 3; mobile = 4× CPU incl. workers or the scaled critical path):

| Profile        | `observations-visible` | `surface-visible` | Today (to ready) |
| -------------- | ---------------------- | ----------------- | ---------------- |
| Desktop        | ≤ 1.5 s                | ≤ 2.5 s           | 9.6–12.9 s       |
| Mobile Fast 4G | ≤ 4 s                  | ≤ 6 s             | 33 s             |
| Mobile Slow 4G | ≤ 13 s                 | ≤ 18 s            | fails            |

The PR includes a bytes ledger per milestone (gzip bytes on the link ÷ bandwidth + serial round
trips × latency + CPU) showing each budget is achievable, and the Slow 4G budgets are tightened in
the PR if the measurement allows. Additionally:

- no request timeout or error on any profile;
- **no Atlas main-thread long animation frame > 200 ms on desktop or > 800 ms on mobile** within the
  window; surface reveal on mobile Fast 4G completes in ≤ 1 s from the first chunk, and the spec
  reports reveal frame count, total reveal time and the longest reveal frame;
- warm layer switch stays < 2 s (`atlas-performance.spec.ts`), with ≥ 45 fps interaction;
- a real mid-range Android cold load (Chrome remote debugging) is recorded in the PR as ground truth
  when a device is available; its absence is stated, not hidden.

**Visual parity.** Same-input parity (the legacy main-thread builder fed `Math.fround` of the JSON
`post_mean`/`post_sd`, i.e. exactly the render-tier inputs) on the committed fixtures and the
2,000-cell subset, for all geometry modes, both metrics and all seven palettes: positions within
1e-6 m; `surfaceHeight` and `surfaceValue` within 1 f32 ULP; identical 32-bin membership; effective
diffuse colour within 1/255 per channel (old hexagon/extruded = gamma-corrected bin material × (1,1,1);
new = white material × gamma-corrected bin vertex colour); identical index topology up to vertex
sharing. Separately, a precision report over all 30 layers bounds the f32-vs-f64 effect analytically
(|Δnormalised| ≤ 2⁻²⁴·max|v| / (hi − lo); height delta ≤ 180,000 m × that) and lists every 32-bin
flip (today exactly one: `cyt-il-10-819-t` post_sd, `84194e9ffffffff`, bin 4 → 5; no bin's
first-cell colour changes). Rendered bins come from the render tier; flips are reported, not hidden.
HbS and G6PD screenshots at the default camera, for `triangles`, `hexagons`, `extruded` and
`honmoon`, match the pre-change build within 0.5% of pixels, captured after the sky box has loaded:
`docs/figures/atlas-fast-load-{before,after}-{hbs,g6pd}.png`.

### B.2 Data tiers and the shared grid

All 30 published surfaces share one sorted, unique 77,844-cell H3 resolution-4 grid. The web
rendition splits into immutable, content-addressed binary objects. **Normative per-tier columns**
(name, dtype, encoding, in this order):

| Tier     | Columns                                                                                                                     | HbS raw / gzip    | Fetched                   |
| -------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------- | ------------------------- |
| `grid`   | `h3` u64 `delta_shuffle`                                                                                                    | 623 KB / ~15 KB   | once per session          |
| `render` | `support` u8 `raw`; `post_mean` f32 `shuffle`; `post_sd` f32 `shuffle`                                                      | 700 KB / ~433 KB  | on selection (critical)   |
| `detail` | `post_mean`, `post_sd`, `q025`, `q975`, `posterior_contraction`, `dist_nearest_obs_km` — all f64 `shuffle`, in that order | 3.7 MB / ~3 MB    | after reveal, low priority |

- **Render values drive colour, height and bins only; they are never displayed as numbers.** Every
  number the hover preview or inspector shows comes from the f64 detail tier, bit-identical to the
  published artifact. Two accessors make this a type guarantee:
  `renderAt(row) → { h3, support, post_mean, post_sd }` (render tier; used by heights, highlight,
  observation anchors, Natural Earth heights) and `cellAt(row) → SurfaceCell` (detail tier; throws
  if not loaded; the only source for `HoverPreview` and `InspectorPanel` values). Heights always
  come from the render tier, even after the detail tier loads (`heightFor(supportCode, value,
  domain, exaggeration)` replaces `heightForCell(SurfaceCell, …)`), so highlight and anchors stay
  bit-consistent with the worker mesh.
- Before the detail tier loads, hover and the inspector show the cell id, the support label (exact,
  from the u8 column; Cesium design §8.4) and "Loading cell values…", never a number. If the detail
  tier fails or stalls (15 s stall timeout), they show "Cell values unavailable" with a retry. If it
  fails its checksum or validation, the artifact's surface and support layers are removed, the map is
  marked not ready, and the validation error appears with "Retry data" (Cesium design §12).
- **Cross-tier binding** (worker, O(n)): `Math.fround(detail.post_mean[i]) === render.post_mean[i]`
  and the same for `post_sd`; the decoded support histogram equals the catalog ref's
  `support_counts`. Either failing is a validation failure as above. Render and detail headers carry
  `source_surface_sha256` (the canonical JSON's sha256), which must equal the ref's `surface_sha256`.
- The canonical full-precision `*.surface.json`, `*.observations.json` and `*.manifest.json` remain
  the citable downloads. Observations stay JSON (80 KB gzip) and are never packed into a surface
  object (AGENTS: observations and surfaces never conflated).
- `posterior_contraction` is kept in the detail tier although no UI reads it: the surface contract
  requires it and AGENTS forbids omitting an uncertainty column.

### B.3 Container format `GOSA`, version 1

Little-endian throughout. The container is defined and hashed **uncompressed**; transport
compression is applied by the server (GitHub Pages; locally `serve` via the B.9 rule; GCS stores
the gzip transport bytes, Part C).

```text
offset 0   : magic "GOSA" (4 bytes)
offset 4   : u16 format_version = 1
offset 6   : u16 reserved = 0
offset 8   : u32 header_length (bytes of UTF-8 JSON)
offset 12  : header JSON
           : 0x00 padding to column_area_start = align8(12 + header_length)
           : column payloads; columns[0].offset = 0,
             columns[i].offset = align8(columns[i-1].offset + columns[i-1].length),
             0x00 padding between columns;
             file length == column_area_start + last.offset + last.length (no trailing bytes)
```

- **Header JSON** is `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`
  encoded UTF-8; decoders parse it with a fatal UTF-8 decoder (`new TextDecoder('utf-8',
  {fatal: true})`) and do not check canonical form (the container sha256 covers the bytes). Strict
  schema: top-level keys exactly `{artifact, columns, grid_sha256, n_cells, resolution,
  schema_version, source_surface_sha256, tier}`; each column exactly `{dtype, encoding, length,
  name, offset}`; integers non-negative safe integers; no booleans.
  - `artifact`: for `render`/`detail`, the canonical `*.surface.json` `"artifact"` object
    **exactly** (every `artifactIdentitySchema` key including `label` and `metric_domains`; keys
    absent from the source stay absent — never `null`, e.g. the target-grid fields of a format-1
    identity); `null` for `grid`.
  - `source_surface_sha256`: the canonical JSON's sha256 for `render`/`detail`; `null` for `grid`.
  - `resolution` equals `artifact.resolution` (render/detail) and the catalog `grids` entry (grid).
  - `grid_sha256`: SHA-256 of the grid's decoded little-endian u64 column bytes (n × 8 bytes).
- **Encodings.** `raw`. `shuffle`: for n elements of width w with `E[i][k]` the k-th little-endian
  byte of element i, `encoded[k·n + i] = E[i][k]` for k = 0 (least significant) … w−1.
  `delta_shuffle` (u64 only): `d[0] = x[0]`, `d[i] = x[i] − x[i−1]` for i ≥ 1, then `shuffle`; every
  `d[i]` (i ≥ 1) must be ≥ 1 and no reconstructed `x[i]` may reach 2⁶⁴. JS decodes with two u32 lanes
  and carry; a carry out of the high lane is the "grid not strictly increasing" error.
- **Support codes** `SUPPORT_CODES = ("observed", "interpolated", "prior_dominated", "unknown")` →
  0, 1, 2, 3, defined once in `genomeos/publication/surface_codec.py` (a test asserts it equals
  `genomeos.surfaces.mask.SUPPORT_STATES`) and mirrored in TS (a test asserts it equals
  `supportSchema.options`).
- Resolution-generic: indices are full u64; nothing assumes resolution 4.

**Decoder hard errors** (spec v1 §12; identical set in Python and TS): wrong magic or
`format_version`; `reserved ≠ 0`; non-zero padding byte; non-minimal offset; trailing bytes;
header not valid UTF-8 or JSON or failing the strict header schema; `tier` mismatch with the
requested tier; columns not exactly the normative list for the tier (catches extra, missing,
duplicate, misplaced, wrong-dtype, wrong-encoding and reordered columns); `length ≠ n × width`;
`n_cells ≠` catalog `n_cells`; `header.artifact` failing `artifactIdentitySchema`; identity mismatch
with the catalog ref on the 13 `IDENTITY_FIELDS` (existing `assertIdentity` wording), or `label` or
`metric_domains` (deep) differing; `source_surface_sha256 ≠` ref `surface_sha256`; `grid_sha256`
recomputed over the decoded grid ≠ header ≠ catalog `grids` key; grid not strictly increasing; any
cell that is not a valid H3 cell or whose resolution ≠ `resolution` (h3-js `isValidCell`/
`getResolution` on the u32 lanes; h3-py `is_valid_cell`/`get_resolution`; both pinned to the same H3
core, 4.x); support code > 3; any non-finite value; `post_mean`, `q025`, `q975` outside [0, 1];
negative `post_sd`, `posterior_contraction` or `dist_nearest_obs_km`; `q025 > post_mean` or
`post_mean > q975` (detail, f64); container SHA-256 ≠ the catalog's declared digest. **Values outside
`metric_domains` are valid** (six layers have prior-dominated cells outside it; colour and height
clamp, numbers do not).

Shared tests: for every golden fixture `encode(decode(f)) == f` (Python); a shared mutation corpus
(reserved = 1, pad byte 0x01, one trailing byte, offset + 8, MSB-first planes, a zero delta, a set
reserved H3 bit, mode ≠ 1, a digit 7 inside the resolution, base cell > 121, wrong resolution) is
rejected by both decoders with the same error class.

### B.4 Catalog contract additions

`catalog.json` stays in the Pages bundle and is inlined into `/app/` (B.6.1), so JS, contract and
catalog deploy atomically. Additions, all **required** in the strict `atlasCatalogSchema` and
written **only** by `encode_atlas_web.py`:

```json
"grids": {
  "<grid_sha256>": { "url": "grids/h3-r4.<container sha256[:16]>.gosa", "sha256": "<container sha256>",
                     "bytes": 622808, "resolution": 4, "n_cells": 77844 }
},
"artifacts": [{ …existing fields…,
  "observations_bytes": 780599,
  "web": {
    "grid_sha256": "<grid_sha256>",
    "render": { "url": "surfaces/hbs-rs334/v3/map-2026-08/render.<sha256[:16]>.gosa", "sha256": "…", "bytes": 700664 },
    "detail": { "url": "surfaces/hbs-rs334/v3/map-2026-08/detail.<sha256[:16]>.gosa", "sha256": "…", "bytes": 3736576 }
  }
}]
```

(byte counts illustrative.) `grids` holds exactly one entry in v1. `observations_bytes` is required
when `observations_available` is true and `null` otherwise, mirroring `observations_sha256`.

- **Progress honesty.** `bytes` and `observations_bytes` are **decoded** sizes; every
  progress-reporting fetch takes `totalBytes` only from catalog-declared decoded sizes and reports
  `null` (indeterminate) otherwise. The `Content-Length`/`Content-Encoding` heuristic in
  `static-provider.ts` is deleted: cross-origin, `Content-Encoding` is hidden while `Content-Length`
  (the compressed size) stays visible, so header totals are wrong, not merely missing.
- **Keys** are relative paths validated by zod: `^[a-z0-9][a-z0-9._/-]*$`, no `..` segment, no
  leading `/`, no scheme. A violation fails the build (app.astro validates at build time).
- **Two bases** (B.6.1): `artifactDataBase` resolves `grids.*.url`, `web.render.url`,
  `web.detail.url`, `surface_url`, `observations_url`, `downloads.*.url`; `siteDataBase =
  sitePath('/data/atlas/')` always resolves `context_sources[].url` (Natural Earth borders and
  places, taken by id from the catalog instead of hard-coded filenames) and
  `external_resources[].cache_url`. In Part B both bases are the same-origin `/data/atlas/`.
- One pure resolver, `src/lib/data-url.ts`:
  `resolveDataUrl(key, base, docBase) = new URL(key, new URL(base, docBase)).href`, called lazily at
  fetch time (never during SSR) with `docBase = document.baseURI` (tests pass an explicit absolute
  `docBase`); `dataHref(key, base)` gives the string emitted in HTML — the absolute result for an
  absolute base, the root-relative `pathname` for a root-relative base (resolved against a fixed
  `http://x.invalid` placeholder, never against `Astro.url`/`Astro.site`). A base must be either
  root-relative (`/` but not `//`) or absolute `https:` (or `http://localhost`/`http://127.0.0.1`),
  and must end in `/`; anything else is a build error. Every existing string concatenation of
  `dataBaseUrl` (`useObservationPlaces.ts`, `AtlasExplorer.tsx` Natural Earth URL,
  `ExplorerControls.tsx` downloads, provider) goes through it. `<link rel=preconnect>` is emitted only
  for an absolute base.

### B.5 Producer

- `genomeos/publication/surface_codec.py` (pure; no I/O; standard library plus `h3`; docstring cites
  Atlas design §11 and this spec §B.3): `encode_grid`, `encode_render`, `encode_detail`, `decode`,
  `SUPPORT_CODES`, and all validation.
- `scripts/encode_atlas_web.py` (thin I/O; idempotent): reads an export directory (the output of
  `export_atlas_web.py`; today the committed `website/public/data/atlas/`); the shared grid is the
  first catalog artifact's `h3_index` sequence and any surface that differs fails the encoder
  (positional alignment is otherwise a silent wrong-value bug); writes `grids/` and `surfaces/` under
  `--out` (default: the same directory); and rewrites `catalog.json` with `grids`, `web` and
  `observations_bytes`. Before rewriting the catalog it decodes every object it wrote and hard-fails
  unless, for every cell of every artifact: each detail f64 equals the JSON value bit-for-bit; each
  render f32 equals `float32(JSON value)`; each support code equals `SUPPORT_CODES.index(JSON support)`;
  the support histogram equals `support_counts`. Pipeline docs gain:
  "`export_atlas_web.py` output is an intermediate; the site build fails until `encode_atlas_web.py`
  has run." `export_atlas_web.py` (784/800 logical lines) is not grown.
- **Part B delivery (no binaries in git).** `website/public/data/atlas/grids/` and `…/surfaces/` are
  git-ignored. `pages.yml` `validate` and `build` jobs set up Python, install `.` with the `read`
  extra (`h3`), and run `python scripts/encode_atlas_web.py` before `npm test` / `npm run build`,
  then `git diff --exit-code website/public/data/atlas/catalog.json` (the encoder is byte-
  deterministic, so the committed catalog must already be the encoder's output). The `paths` filters
  gain `genomeos/publication/**`, `scripts/encode_atlas_web.py`, `pyproject.toml`.
  `local-development.md` documents the encoder as a prerequisite for `npm run dev`, `npm test` and the
  performance specs. (Committing the objects would add ~103 MB of packed binaries to history
  permanently.)
- **Committed fixtures** (`tests/fixtures/atlas-web/`, readable by eye, regenerated by a committed
  script): a real export tree at resolution 3 with ~8–12 cells per artifact sorted by u64 `h3_index`,
  containing all four support states, at least one `prior_dominated` cell outside `metric_domains` for
  both metrics, one cell with `q025 == post_mean` and one with `post_mean == q975`, one format-1 and
  one format-2 artifact; the golden `.gosa` objects generated from it; and a pytest that re-encodes the
  JSON and asserts byte equality with the committed `.gosa` and their catalog digests. The golden test
  also asserts the raw support bytes against a hard-coded list. The `_write_source_tree` export (which
  is descending) is a negative test: refused with "grid not strictly increasing". The website copies
  the golden objects under `website/tests/fixtures/atlas/` (with `tests/fixtures/**` added to
  `website/.prettierignore`).
- **2,000-cell parity subset**: from `cyt-il-6-174-c` (all four states and out-of-domain cells), all
  cells under named, contiguous H3 resolution-1 parents, extracted by a committed deterministic script
  that asserts the four states and an out-of-domain cell are present; committed under
  `website/tests/fixtures/atlas/parity/` with its own subset grid object and `grid_sha256`, so it
  survives Part C.
- **E2E fixture tree** (`website/tests/fixtures/atlas/e2e/`, committed, ~1 MB): written by
  `scripts/build_atlas_e2e_fixture.py` (reuses `surface_codec`) for **all 30** artifacts — a sorted
  256-cell subset per artifact (same pinned-then-sampled selection rules as today's
  `atlas-browser-fixture.ts`, then sorted), 64 observations, a compact grid, and a compact catalog
  whose `n_cells`, `n_observations`, `observations_sha256`, `observations_bytes`, `grids`,
  `web.grid_sha256` and `web.*.{sha256,bytes}` all match. It accepts `--from-dir` so it can be re-run
  after Part C from a bucket download.
- **Review figure** (AGENTS "show the map"): `scripts/plot_surface_codec_parity.py` →
  `docs/figures/surface-codec-parity.png` with panels: (a) a 32-bin change summary across 30 layers ×
  2 metrics (f32 render vs f64), counts printed, and a map of the one changed cell circled; (b) the
  HbS render-tier palette-bin map with unknown cells hatched and a low-to-high ramp; (c) `kir-3ds1`
  (out of domain in both metrics) post_mean and post_sd with unknown hatched and prior-dominated
  stippled in its palette colour, out-of-domain (clamped) cells marked; (d) a text panel with
  max |detail − JSON| over all six fields and 30 layers (expected 0).

### B.6 Runtime architecture

```text
/app/ HTML (build time)
 ├─ <script type="application/json" id="atlas-catalog"> validated catalog, '<' escaped as <
 ├─ tiny inline head script: reads the inline catalog and location.search (entity), resolves the
 │  selected artifact's grid, render and observations URLs with the data-url rules, and inserts
 │  <link rel="preload" as="fetch" crossorigin="anonymous"> for them (+ preconnect if absolute)
 └─ <link rel="modulepreload"> for the scene/Cesium chunk

island module evaluation (before React mounts)
 ├─ starts import('…/atlas-scene') and constructs the data worker
 └─ AtlasExplorer (client:load) imports NO cesium value

AtlasDataProvider (main thread)  ── fetch (matches preloads; stall timeout; progress from declared bytes)
   └─ transfers ArrayBuffers ──► atlas-data.worker.ts (module worker, Cesium-free, h3-js, @noble/hashes)
                                   verify sha256 → decode/validate (B.3) → cross-tier checks (B.2)
                                   topology as soon as the grid arrives (cached per grid)
                                   per chunk, camera order: surface mesh + support (mask) buffers
                                   edges ring buffers; Natural Earth parse; observation anchor heights
                                 ◄── transferable typed arrays, one message per chunk
scene (when import resolves) ── observations → chunk scheduler (B.6.7) → edges, context (deferred)
```

1. **Inline catalog and preloads.** `app.astro` reads the catalog (path from `ATLAS_CATALOG_PATH`,
   default `public/data/atlas/catalog.json`), validates it with the same zod schema (build fails
   loudly), and embeds it with `<` escaped. The head script picks the URL-selected artifact
   (default `artifacts[0]`), so a shared link preloads the right map and the default's ~0.5 MB is not
   wasted. The provider's `getCatalog()` resolves from the inline JSON. `tests/content.test.ts`'s
   P-code check runs on the HTML with only the `#atlas-catalog` element removed (narrow regex on that
   id), plus a positive check that the element exists and parses with `atlasCatalogSchema`; the
   catalog text is unchanged.
2. **Fetch on the main thread, compute in the worker.** Preloads are matched only by document
   fetches, so the provider fetches (`mode: 'cors'`, `credentials: 'same-origin'`, matching
   `crossorigin="anonymous"`) and transfers each `ArrayBuffer`. A **stall timeout** (15 s without a
   new body chunk) replaces the 15 s whole-request budget; abort and retry are otherwise unchanged.
   The detail tier is fetched with `priority: 'low'` after `atlas:surface-visible`.
3. **Worker.** One dedicated module worker
   (`new Worker(new URL('./atlas-data.worker.ts', import.meta.url), { type: 'module' })`; Vite
   `worker.format: 'es'`; no dynamic `import()` inside it). Typed request/response messages with ids;
   superseded requests are cancelled by id; posts use `postMessage(msg, { transfer })`. Every
   computation is in importable Cesium-free modules that vitest tests directly. SHA-256 uses
   `@noble/hashes` (pinned exact) because `crypto.subtle` is unavailable on the plain-HTTP origin.
4. **Columnar surface model.** `SurfaceArtifact` becomes
   `{ artifactKey, artifact, grid: { h3Lo, h3Hi: Uint32Array, resolution }, support: Uint8Array,
   values: { post_mean, post_sd: Float32Array }, detail?: { …Float64Array } }` with `rowForH3(h3)`
   (binary search over the sorted grid), `h3At(row)`, `renderAt(row)`, `cellAt(row)` (B.2).
   `artifact` is the validated header identity (one source of `metric_domains` for worker and main
   thread). `artifactKey = id:model_version:data_version`. Nobody materialises 77,844 objects.
5. **Mesh, support and colour in the worker.**
   - Vertex values are accumulated in float64 from the f32 column values, summing adjacent supported
     cells in grid order, and stored in `Float32Array`.
   - `triangles`/`honmoon`/`honmoon-fill`: shared-vertex fan mesh (cell centres + unique corners,
     numeric vertex ids from the grid topology); vertex height and value equal today's "mean over
     adjacent supported cells"; positions at `SURFACE_CLEARANCE_METRES` (650 m); `elevationNormal`
     geocentric.
   - Colours: a Cesium-free `colorBytesAtStops(stopsLinear, t) → [r, g, b]` factored out of
     `visual-encoding.ts` with today's exact arithmetic (clamp; `scaled = t·(n−1)`;
     `lower = min(floor(scaled), n−2)`; `v + (w−v)·(scaled−lower)` in linear light; `toSrgb` with
     `Math.round(clamp(…)·255)`); `colorAtPosition` formats its result, and the worker calls it
     directly. `surfaceColor` holds `bytes / 255`. No lookup table.
   - `hexagons`/`extruded`: per-cell flat geometry; `surfaceColor` holds the sRGB bin colour from
     `paletteBinsForCells` semantics ("colour of the first supported cell in grid order within the
     bin"); the chunk material is white (alpha as today, so opacity fades keep working); the fragment
     shader gamma-corrects the vertex colour only in these modes
     (`material.diffuse *= u_vertexColorGamma > 0.5 ? czm_gammaCorrect(v_surfaceColor) :
     v_surfaceColor;` or an equivalent define), reproducing today's HDR behaviour.
   - **Support (mask) geometry** is built in the worker too, as flat per-cell buffers at the
     clearance with the `st` coordinates the existing `Grid` (unknown) and `Dot` (prior-dominated,
     per palette bin) materials need, grouped by the same chunks. The Cesium async `PolygonGeometry`
     route leaves the critical path; "support-material rendering" (B.7) means the same materials and
     colours, not the same tessellation. Pole-enclosing cells keep today's fan split.
   - **Chunks**: seed groups by H3 resolution-0 base cell (a base cell straddling ±180° is split by
     the sign of each cell centre's longitude); greedily merge a group into an adjacent group
     (`gridDisk(base, 1)` adjacency, same side of ±180°), iterating base cells in index order, until
     ≥ 2,048 cells (a group with no eligible neighbour may stay smaller); cells whose own boundary
     crosses ±180° go into one dedicated seam chunk per side. Index arrays are `Uint32Array` when a
     chunk exceeds 65,535 vertices, else `Uint16Array`. Bounding spheres are computed in the worker
     from each chunk's positions (including the maximum elevated height).
   - One `GeometryInstance` per chunk, in its own `Primitive`, built synchronously from the transferred
     arrays; a chunk is never added without its masked cells.
   - Observation anchor heights (smooth modes need the per-vertex mean heights) are returned with
     the first chunk batch; anchors never use `cellAt`.
6. **Picking without per-cell instances.** Surface and support pick ids are
   `{ kind: 'surface-chunk', artifactKey, chunk }`. A pure, Cesium-math-only resolver:
   - at elevation factor 0, the cell comes from `camera.pickEllipsoid(p)` (or `globe.pick` of the
     pick ray) → lat/lon → `latLngToCell` → `rowForH3` (no extra render pass);
   - at factor > 0, `scene.pickTranslucentDepth = true` is set only around the Atlas
     `scene.pickPosition(p)` call and restored immediately (it is scene-wide and also drives camera
     pivots); the picked Cartesian is projected along the geocentric radial
     (`Ellipsoid.WGS84.scaleToGeocentricSurface`) before `cartesianToCartographic` → `latLngToCell`,
     undoing the shader's `elevationNormal` displacement;
   - `extruded`: the projected cell and its `gridDisk(cell, 1)` neighbours are candidates; the hit
     altitude `z = |p| − |scaleToGeocentricSurface(p)| − clearance` selects the cell whose top is
     ≥ z among the two either side of a wall (ray-testing the ≤ 7 prisms is the equivalent fallback).
   - `preferredAtlasPick` drops surface/support picks whose `artifactKey` is not the displayed key
     **before** choosing; observation picks still win. Depth comes from the displayed group only
     (the incoming group is excluded from picking until the swap commits). `sameAtlasPick` and
     `createStableHover` compare `artifactKey` and row. The inspector selection is held as
     `{ kind: 'surface', artifactKey, row }` and dropped if `artifactKey` no longer matches; the
     detail gate checks the detail tier for that `artifactKey`. The highlight layer is keyed the same
     way. Only `drillPick` results containing a `surface-chunk` pick trigger cell resolution.
7. **Chunk scheduler.** Add a batch of k chunk primitives, call `scene.requestRender()`, and time the
   render that follows (`scene.preUpdate` → `scene.postRender`); size the next batch so chunk work
   stays within ~8 ms over the baseline frame on desktop and ~50 ms at 4× CPU; always add at least one
   chunk per frame; add the next batch only after the previous batch's primitives report `ready` (or
   its postRender fired). Order: nearest to the camera's look-at point first. Seam chunks are budgeted
   as costly.
8. **Reveal vs swap.** Progressive reveal (observations as soon as the scene and observations exist;
   then chunks with their masked cells) applies **only when no scientific layer is displayed**: the
   cold initial load, or a scene recreated by "Retry globe". Whenever a scientific layer is displayed,
   every replacement — another artifact, metric, palette recolour, geometry mode, elevation rebuild —
   builds the incoming observations, chunks and support primitives in a collection that stays shown
   (`collection.show = true`, so Cesium builds them) at opacity 0, and they become visible in a single
   `animateSwap` that also retires the outgoing surface, support and observations. A recolour is
   applied to all chunks in one frame. `activeArtifact`, the legend, the inspector artifact,
   `data-atlas-active` and `data-atlas-displayed` change in that same swap, exposed by the scene as
   one commit callback at which the explorer also clears hover and selection. During the cold reveal
   the legend renders from the artifact ref being revealed (with its loading status) as soon as the
   first chunk is added. At elevation > 0, no chunk is raised until the anchor heights are applied in
   the same frame.
9. **Off the critical path.** Cell outlines are built after `atlas:surface-visible` from worker ring
   buffers: the worker sends exact `primitiveCountMax`/`vertexCountMax` first; polylines are added to
   the `BufferPolylineCollection` (width 2, `allowPicking: false`) in slices sized to the frame budget
   (~2–4k per frame on desktop, fewer at 4×), with `scene.requestRender()` after each slice and a
   `MessageChannel` yield (no `setTimeout(0)` clamps). The Natural Earth GeoJSON is fetched after
   `atlas:surface-visible`, parsed in the worker into ring vertex buffers and a label table, and drawn
   as a time-sliced `BufferPolylineCollection` plus a `LabelCollection` added in slices;
   `GeoJsonDataSource` and its entities are dropped. Its height adjustment is skipped at elevation 0
   and computed in the worker from grid rows on the first non-zero factor. The sky box is hidden
   (`viewer.scene.skyBox.show = false` right after `new Viewer`, keeping sun and moon) until
   `data-atlas-ready`, then shown.
10. **No coarse aggregated tier.** Averaging res-4 children into res-3/2 parents is an aggregation that
    must exclude masked cells and report the excluded fraction (AGENTS invariant; spec v1 §10) — a
    `needs-human-decision` this work does not take. Camera-ordered chunked reveal of the real res-4
    cells gives progressive appearance without new science. Deviation from Cesium design §3 (3D Tiles
    as the scale path) is recorded: 3D Tiles remains the path for artifacts that outgrow this format.
11. **Lazy Cesium.** No module imported statically by `AtlasExplorer.tsx` imports a Cesium value (a
    build test asserts the island chunk does not contain Cesium). Cesium-free helpers
    (`availableBasemaps`, `availableTerrains`, `ionCapability`, `resolveElevationView`) move to
    `earth-style-catalog.ts` with re-exports kept for tests. Every scene-style effect (metric, surface
    style, observation style, layers, earth style) re-applies its current value when the scene becomes
    available or is recreated by "Retry globe" (fixing the existing missing-`sceneAttempt` dependency);
    `setBasemap` is a no-op when the requested id is already active.
12. **Re-render cost.** `useAtlasActivity` coalesces to at most one React state update per animation
    frame. New load orchestration (provider wiring, worker client, lazy scene, scheduler) lives in
    hooks/modules, not in `AtlasExplorer.tsx`; `atlas-scene.ts` (650 lines) delegates to new modules.
13. **Cache keys** include tier, artifactKey and every geometry input used; a palette change
    recolours cached per-vertex values in the worker instead of rebuilding topology.

### B.7 Behaviour that must not change

URL round-trip (all params) and default URL state (including `cellEdges=true`); 32-bin palette
quantisation (bins from the render tier, flips reported); support materials and colours; selection
highlight; inspector content and wording (plus the new loading/unavailable states); the #172
transition and progress rules; reduced motion; keyboard camera controls; camera pivot behaviour;
error and retry flows; the WebGL failure path; and every scientific value shown.

### B.8 Tests

- **Python**: codec round-trip and every hard error incl. the shared mutation corpus; determinism
  (encode twice → identical bytes); `SUPPORT_CODES` equals `SUPPORT_STATES`; golden fixture byte
  equality and digests; alignment refusal when a surface's h3 order differs from the grid; the
  descending `_write_source_tree` export refused; encoder CLI and full-artifact round-trip checks on
  the committed fixture tree; e2e-fixture generator determinism.
- **Vitest** (`vitest.config.ts` `include: ['tests/**/*.test.ts']` so `.spec.ts` Playwright files are
  never picked up): TS decoder against golden objects and the mutation corpus; `SUPPORT_CODES` equals
  `supportSchema.options`; cross-tier checks; `rowForH3`/`h3At` round-trip; `cellAt` throws without
  detail; mesh same-input parity (B.1) for all modes, metrics and palettes on the res-3 fixtures and
  the 2,000-cell subset; colour sweep (≥ 100k `t` points plus every stop ± 1e-9, all seven palettes,
  bytes equal `colorAtPosition`); chunk rule (every supported and masked cell exactly once; each
  chunk's support buffers cover exactly its masked cells; bounding radius ≤ 2,500 km; at most two
  chunks per artifact fail the `splitLongitude` early-out; max index fits its index type, checked in
  `extruded` on the full HbS grid shape); pick resolver (flat, elevated smooth near edges at
  exaggeration 5, extruded walls → taller cell); `resolveDataUrl`/`dataHref` (bases `/data/atlas/`,
  `/genomeOS/data/atlas/`, absolute with slash; absolute without slash throws; rejected keys; preload
  href resolves to the fetch URL); provider stall timeout, abort, retry; progress with declared bytes
  (compressed `Content-Length`, hidden `Content-Encoding` → total = declared bytes; no declared bytes →
  null; aggregate stays < 1 until observations finish); inline-catalog parse and escaping; fixture
  catalogs pass `atlasCatalogSchema` and their objects match declared digests/bytes; the island chunk
  contains no Cesium.
- **Playwright** (`tests/atlas-browser-fixture.ts` rewritten, importing no app modules so the capture
  scripts keep running under Node type stripping): the e2e build sets `ATLAS_CATALOG_PATH` to the e2e
  fixture catalog, and the fixture fulfils grid/render/detail/observations URLs from the committed e2e
  tree (no `route.fetch()` of production files, no runtime re-encoding). A helper
  `delayArtifactTier(page, id, tier, ms)` reads URLs from the inline catalog and counts its hits;
  `site.spec.ts:121-147` (#172 transition) and `scripts/capture-atlas-progress.mjs` use it, plus a
  variant that delays only the render tier while observations load fast — asserting via
  `data-atlas-displayed` that only `hbs-rs334` is displayed while G6PD is pending. Detail tier delayed:
  hover/click shows cell id, support label and "Loading cell values…", no number, no exception, then
  updates in place. A corrupted render object shows "Retry data" and renders nothing. Existing explorer
  tests keep passing. The cold-load spec (B.1) runs locally; its numbers go in the PR.
- `playwright.performance.config.ts`: `testMatch: /atlas-(performance|cold-load)\.spec\.ts/`, with
  the cold-load spec creating its own contexts per profile.

### B.9 Local serving

`website/serve.json` (outside `public/`) sets `Content-Type: application/octet-stream` for
`**/*.gosa` (which `serve`'s `compression` middleware then gzips; octet-stream is compressible in
mime-db); `serve:test` becomes `serve dist -c ../serve.json -l tcp://127.0.0.1:4322 --no-clipboard`.
The Part B PR records what GitHub Pages actually sends for `.gosa` (`curl -H 'Accept-Encoding:
gzip'`).

---

## Part C — Web data on GCS behind a CDN

### C.1 Outcome and acceptance

1. Per-artifact web data — the `.gosa` grid/render/detail objects and the canonical surface,
   observations and manifest JSON — is served from a public GCS bucket under immutable,
   content-addressed keys with `Cache-Control: public, max-age=31536000, immutable`. Natural Earth,
   places and `external/` caches stay in the Pages bundle (the only tracked copies; small).
2. The site fetches each layer on selection from the artifact base; only the URL-selected artifact
   is preloaded.
3. `main` no longer tracks the 90 per-artifact files (~598 MB). `catalog.json` stays (atomic deploys;
   `check_commercial_use.py`). History is not rewritten. `.gitignore` gains separate lines for the
   staging directory and `website/public/data/atlas/*.surface.json`, `*.observations.json`,
   `*.manifest.json`.
4. No GCP project id or bucket name is committed (`docs/repo-gcloud-auth.md`). The artifact base is
   the build variable `PUBLIC_ATLAS_DATA_BASE_URL`: an absolute `https://` URL that includes the
   `atlas/web/` prefix and ends in `/`; empty means unset (same-origin fallback, used only by local dev
   and tests). `pages.yml` sets it from the repository variable `ATLAS_DATA_BASE_URL` in the
   production `build` job only. `tests/setup/build.ts` and the `test:e2e` build set it to `''`
   explicitly. A wiring test (like `google-maps-config.test.ts`) pins the `pages.yml` line, the
   `.env.example` entry and the absence of any `ORIGIN`-named variant.
5. **Deploy gate** (`scripts/check_atlas_web_data.py`, run in `pages.yml` `build` before deploy, and in
   `validate` for same-repo PRs): fails when the baked-in base is empty or not absolute; for every
   artifact-base key (`grids.*.url`, `web.render.url`, `web.detail.url`, `surface_url`,
   `observations_url`, `downloads.*.url`) it sends `HEAD` with `Accept-Encoding: gzip` and an
   `Origin` for each production origin and requires: 200; `Content-Encoding: gzip`; the immutable
   `Cache-Control`; `Access-Control-Allow-Origin` echoing the origin or `*`; and, read from the public
   JSON API (`storage/v1/b/<bucket>/o/<key>?fields=size,contentEncoding,cacheControl,metadata,crc32c`,
   anonymous for public objects; bucket name from a repository variable), metadata `sha256` equal to
   the catalog digest and `decoded-bytes` equal to the declared decoded size where declared. It never
   compares `Content-Length` with decoded bytes. It also GETs, gunzips and sha256-checks the default
   artifact's grid, render and observations. It checks that every site-base key exists in `dist/`.
   Metadata is what the publisher asserts; it is trusted only because keys are content-addressed,
   uploads refuse overwrite, and publishing verifies the uploaded bytes.

### C.2 Bucket, publishing and CDN

- Bucket in `us-east1`, uniform bucket-level access, objects public (`allUsers:
  roles/storage.objectViewer`); provisioning checks and reports public-access prevention and any
  domain-restricted-sharing org policy that would block it. No object versioning (keys are
  content-addressed); default soft delete. Published objects are never deleted (cached HTML references
  old keys).
- **Layout** under prefix `atlas/web/`: `grids/h3-r{res}.{container sha256[:16]}.gosa`;
  `surfaces/{id}/{model_version}/{data_version}/{render|detail}.{sha256[:16]}.gosa`;
  `downloads/{id}/{model_version}/{data_version}/{id}.{surface|observations|manifest}.{sha256[:16]}.json`
  with `Content-Disposition: attachment; filename="{id}.{kind}.json"` (the canonical filename). In
  Part C, `encode_atlas_web.py --with-downloads` copies each canonical JSON byte-for-byte into
  `downloads/…` and rewrites `surface_url`, `observations_url` and `downloads.*.url` to those keys
  (every sha256 unchanged; `observations_url` and `downloads.observations.url` name the same object).
  `publish_atlas_web.py` uploads exactly what the rewritten catalog references, never renaming keys.
- **Upload** (`scripts/publish_atlas_web.py`, via `python scripts/gcloud_repo.py run storage …`, never
  bare `gcloud`): compress each staged file itself with `gzip.compress(data, compresslevel=9,
  mtime=0)` (never `--gzip-local*`, which forces `no-transform`); upload with
  `--if-generation-match=0`, `--content-encoding=gzip`, explicit `--content-type`
  (`application/octet-stream` for `.gosa`, `application/json` for JSON),
  `--cache-control='public, max-age=31536000, immutable'`, `--content-disposition` for downloads, and
  `--custom-metadata=sha256=<decoded hex>,decoded-bytes=<n>`. **Identity is the decoded content read
  from metadata**: before uploading, `storage objects describe`; absent → upload; present with both
  metadata fields matching → skip; present with different/missing metadata or `contentEncoding ≠ gzip`
  → hard error (never overwrite); a 412 on upload → the same comparison. Post-upload: metadata equals
  the catalog; stored size and md5 equal the uploaded gzip bytes (same base64 encoding on both sides;
  `hashlib.md5`, no new dependency). `--dry-run` prints every command. Compressed bytes and CRC32C are
  never compared across runs.
- **CORS** (`gcloud storage buckets update --cors-file`): `GET`, `HEAD` from `https://genome-os.org`,
  `http://genome-os.org` (the site still answers on HTTP), `https://www.genome-os.org`,
  `https://bschilder.github.io`, and `http://localhost` / `http://127.0.0.1` on ports 4321, 4322 and
  4323; response headers `Content-Length`, `Content-Type`, `Content-Encoding`, `ETag`;
  `maxAgeSeconds` 3600.
- **CDN modes** (`scripts/provision_atlas_web_bucket.py --mode edge|cloud-cdn`, idempotent,
  `--dry-run`):
  1. **`edge` (default; provisioned in this work):** public objects with `Cache-Control: public` are
     served from Google's edge caches at `https://storage.googleapis.com/<bucket>/atlas/web/`.
  2. **`cloud-cdn` (scripted, not provisioned):** a backend bucket with Cloud CDN behind a global
     external HTTPS load balancer with a Google-managed certificate on `data.genome-os.org`. It needs a
     DNS A record at the registrar (GoDaddy; a human step) and incurs load-balancer cost; the deploy
     gate then checks status, gzip, CORS and Cache-Control at the CDN origin and metadata via the JSON
     API.

### C.3 Site and CI changes

- `app.astro` passes `artifactDataBase` (`PUBLIC_ATLAS_DATA_BASE_URL` or `siteDataBase`) and
  `siteDataBase`; `StaticAtlasDataProvider` takes both (its `#getJson` serves artifact and external
  fetches); `useObservationPlaces` and the Natural Earth URL use `siteDataBase`;
  `ExplorerControls.downloadUrl` uses `artifactDataBase`. A test serves artifact objects under a
  different origin than site data and asserts borders, places and the external panel still load.
- `pages.yml`: the Part B encode step and catalog-diff guard are removed (the source JSON is gone);
  the C.1.5 gate is added; the production build fails without the variable.
- E2E: the validate job's builds set `PUBLIC_ATLAS_DATA_BASE_URL=http://127.0.0.1:4323/` and
  `ATLAS_CATALOG_PATH` to the e2e fixture catalog; a second Playwright `webServer` serves the e2e tree
  with CORS and gzip, exercising absolute-URL resolution, `crossorigin` preload matching, CORS and
  `Content-Encoding`. The production `build` job refuses to run with `ATLAS_CATALOG_PATH` set.
- Tests that read per-artifact files: `atlas-public-data.test.ts` becomes a catalog-only contract test
  plus an opt-in `ATLAS_DATA_DIR` integrity test (sha256 and decode of every object, h3 order equals the
  grid, the six island cells checked against the grid object); `site.spec.ts:635-649` (77,844 cells,
  1,071 observations) moves there; `site.spec.ts:981-987` derives expected download hrefs from the
  catalog through the resolver; `atlas-performance.spec.ts` and the cold-load spec run against
  `ATLAS_DATA_DIR` (a local staging tree) or the bucket; `check_commercial_use.py` keeps reading the
  repo catalog.
- Script tests: provisioning and publishing are tested with a fake gcloud executable
  (`GENOMEOS_GCLOUD_EXECUTABLE`), covering dry-run output, refuse-overwrite, skip-if-identical (publish
  twice; second run skips everything) and metadata-mismatch hard errors.
- Docs: `website/src/content/docs/docs/deployment.md`, `local-development.md`,
  `docs/deployment-gcp.md`, `docs/data-store.md`: the bucket, variables, provision/publish runbook
  (`python scripts/gcloud_repo.py init --account <account> --project <project>` first), how to run the
  site against the bucket or a local staging tree, and how to re-encode after Part C (a full
  `export_atlas_web.py` run or a bucket download into a staging tree; observation sha256 values must
  stay byte-identical; only `catalog.json` returns to the repo).

### C.4 Ordering

1. Part B complete on its branch (encoder, `web` blocks, CI encode step; Part B's final gates pass).
2. Authenticated operator (the owner authorised the agent, 2026-10-07): provision `edge` mode; run
   `encode_atlas_web.py --with-downloads --out <staging>` from the Part C branch tip; run
   `publish_atlas_web.py`; set repository variables `ATLAS_DATA_BASE_URL` and the bucket name. This
   does not wait for the owner to merge A and B: keys are content-addressed, so publishing early only
   adds objects, and if review changes the encoded bytes the steps are re-run (idempotent).
3. Part C's PR commits the rewritten catalog and removes the per-artifact files; it merges after
   Part B (stacked), and the deploy gate makes a premature merge fail its deploy rather than ship a
   broken site.

---

## Rulings

| Ruling | Why | Cost if wrong |
| --- | --- | --- |
| No coarse aggregated preview; camera-ordered chunked reveal | Aggregating masked cells is a `needs-human-decision` scientific rule | A `preview` tier can be added later; the client supports tiers |
| f64 detail tier for every displayed number; f32 render tier for colour/height/bins | Displayed values stay bit-identical to the citable artifact | ~3 MB extra, fetched lazily per layer |
| Bins from the render tier; the one f32 bin flip is reported | Recolouring when detail arrives would visibly change the map after load | One cell in one layer differs by one bin from an f64 binning |
| Progressive reveal only on cold load/retry; every replacement is one atomic swap | Never show two artifacts (or two palettes) under one legend (Cesium design §9) | Warm switches stay all-at-once, as today |
| Support mask built in the worker per chunk, in lockstep with the surface | A chunk without its mask reads as "low value" | Replaces Cesium's async `PolygonGeometry` path for support cells |
| Pick ids carry `artifactKey`; geometry-aware cell resolver | All layers share one grid, so an unkeyed lookup shows the wrong artifact's numbers | More picking code than per-cell instances |
| Exact colour function shared by old and new paths; no LUT | A 256-entry LUT cannot meet 1/255 between samples | None material |
| Catalog stays in the Pages bundle, inlined into `/app/`; preloads chosen by an inline script from the URL | Atomic deploys; shared links preload the right map | Catalog changes need a site deploy (already true) |
| Transport gzip; digests over the decoded container; progress only from declared decoded bytes | One code path for Pages, local and GCS; honest cross-origin progress | Relies on `Accept-Encoding: gzip` (universal) |
| SHA-256 in the worker with `@noble/hashes` | `crypto.subtle` is unavailable on the plain-HTTP origin | One small pinned dependency |
| Part B generates `.gosa` in CI (git-ignored), not committed | Committing adds ~103 MB packed binaries to history forever | CI gains a Python step until Part C |
| Two data bases; Natural Earth, places and `external/` stay in the repo | They are the only tracked copies and small | ~4 MB stays in the Pages bundle |
| Slow 4G budgets 13 s / 18 s (not 9 / 14) | Bytes on a 180 KB/s, 562 ms link make 9/14 infeasible with Cesium on the path | Tightened in the PR if measurement allows |
| Mobile budgets judged with workers throttled (or scaled ×4) | CDP page throttling does not slow dedicated workers | A real-device check is still recommended |
| Natural Earth parsed in the worker and drawn time-sliced; `GeoJsonDataSource` dropped | Its single onload task exceeds every long-task budget | Geographic overlay code is rewritten |
| GCS `edge` mode provisioned; `cloud-cdn` scripted only | DNS is at GoDaddy (human step) and the load balancer costs money monthly | `edge` URLs carry the bucket name in a build variable (not git) |
| Credit block wraps on mobile instead of one line | Required attributions cannot fit one line at 360 px | Slightly taller docked block |
| 24 px target boxes also on desktop | Fixes an existing WCAG 2.2 2.5.8 violation | A small desktop visual change |
| Issues filed before each part's first work commit (owner's approval authorises filing) | AGENTS "issue first" | None |
| Part C operations run on the stacked branch before the owner merges A and B | Merges are the owner's call; content-addressed keys make early publishing safe | Re-run encode/publish if review changes Part B's bytes |
| Stacked PRs A → B → C, one spec, one plan | AGENTS "one PR per coherent unit"; B and C share the format | Merge order is fixed |

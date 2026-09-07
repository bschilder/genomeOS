# Atlas Explorer Controls and Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the expanded Cesium capabilities through a compact, accessible explorer UI with shareable state, clear help, actionable downloads, external context, and non-obscuring warnings.

**Architecture:** React hooks own catalog/request and URL state; presentational components own one concern each. The inspector remains the only large right-side panel, warnings occupy a single top rail, and the legend moves explanation into reusable accessible popovers. External annotation is cache-first and non-blocking, while the scene remains usable whenever annotation services fail.

**Tech Stack:** React 19.2.8, Astro 7.3.1, TypeScript 6.0.3, Zod 4.5.4, Vitest 5.0.0, Playwright 1.63.0, axe-core 4.13.0.

**Spec:** `docs/superpowers/specs/2026-09-07-cesium-explorer-interaction-design.md`

## Global Constraints

- This plan consumes both `2026-09-07-atlas-publication-catalog-expansion.md` and `2026-09-07-cesium-scene-interactions.md`.
- Cite Atlas design §11 in every new production-module docstring.
- Ordinary interface text is at least 16 px; Figtree is the interface font and Raleway is reserved for the genomeOS wordmark.
- GitHub, source, gnomAD, and dbSNP links open in a new tab with `rel="noreferrer"`.
- Hover is never the only path to help, selection, external data, or downloads.
- Information popovers open by hover/focus on hover-capable devices and by click/tap everywhere; Escape closes and returns focus.
- Color is never the only indicator of selected state, support, failure, or disabled capability.
- Warnings are deduplicated into one top banner and never overlap the inspector.
- Catalog/artifact failures retain a visible retry action; external failures never change map readiness.
- Unknown URL enum values, non-finite numbers, and reversed min/max ranges are corrected field-by-field and reported.
- External lookup controls exist only for explicit catalog capabilities; UI code never manufactures identifiers.
- The full catalog is lazy: selecting one map does not fetch all 30 surfaces.
- Production TypeScript/React modules stay below 500 logical lines.

---

### Task 1: Extend shareable explorer state

**Files:**

- Modify: `website/src/atlas/url-state.ts`
- Modify: `website/tests/atlas-url-state.test.ts`

**Interfaces:**

- Consumes: `AtlasCatalog` and query parameters.
- Produces: validated, round-trippable presentation state for basemap, terrain, palette, opacity, edges, observation shape/color/size, min/max size, and sampling footprints.

- [ ] **Step 1: Write failing round-trip and refusal tests**

```ts
it("round-trips every presentation control", () => {
  const state = explorerState({
    basemap: "aerial-labels",
    terrain: "world-terrain",
    palette: "cividis",
    surfaceOpacity: 0.72,
    cellEdges: true,
    observationShape: "pin",
    observationColor: "study",
    observationSize: "ac",
    observationMin: 7,
    observationMax: 22,
    samplingAreas: false,
  });
  expect(
    parseExplorerState(serializeExplorerState(state), catalog()).state,
  ).toEqual(state);
});

it("refuses a reversed observation size range", () => {
  const parsed = parseExplorerState("?obsMin=20&obsMax=5", catalog());
  expect(parsed.corrections.map(({ field }) => field)).toEqual([
    "obsMin",
    "obsMax",
  ]);
  expect(parsed.state.observationMin).toBeLessThanOrEqual(
    parsed.state.observationMax,
  );
});
```

- [ ] **Step 2: Run the URL tests and confirm failure**

Run: `cd website && npm test -- atlas-url-state.test.ts`

Expected: FAIL because the new fields do not exist.

- [ ] **Step 3: Implement explicit enums, bounds, and defaults**

Use `surfaceOpacity` range `0.45..1`, circle/pin pixel ranges validated separately from hemisphere-kilometre ranges, and metric-specific palette defaults only when the URL contains no explicit palette. Preserve a user's explicit palette when changing metric.

- [ ] **Step 4: Run tests and commit**

```bash
cd website && npm test -- atlas-url-state.test.ts
git add website/src/atlas/url-state.ts website/tests/atlas-url-state.test.ts
git commit -m "feat: share Atlas presentation state (#55)"
```

### Task 2: Build reusable information popovers and keyboard help

**Files:**

- Create: `website/src/components/atlas/InfoPopover.tsx`
- Create: `website/src/components/atlas/KeyboardHelp.tsx`
- Create: `website/tests/atlas-info-popover.test.tsx`
- Modify: `website/src/styles/atlas.css`

**Interfaces:**

- Consumes: trigger label, title, React content, and optional placement.
- Produces: accessible disclosure behavior shared by controls, legend, downloads, and keyboard help.

- [ ] **Step 1: Write failing accessibility/interaction tests**

```tsx
it("opens from focus and returns focus after Escape", async () => {
  render(
    <InfoPopover label="About uncertainty" title="Uncertainty">
      Meaning
    </InfoPopover>,
  );
  const trigger = screen.getByRole("button", { name: "About uncertainty" });
  trigger.focus();
  expect(screen.getByRole("dialog")).toBeVisible();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(trigger).toHaveFocus();
});
```

Also test click/tap toggle, outside click, described-by linkage, only one open popover, and keyboard-help copy containing only actually bound keys.

- [ ] **Step 2: Run the test and confirm the component is absent**

Run: `cd website && npm test -- atlas-info-popover.test.tsx`

Expected: FAIL on import.

- [ ] **Step 3: Implement anchored popovers**

Use a real `<button>` trigger with an accessible name and an adjacent `role="dialog"` disclosure positioned from the trigger container. Do not use native `title` as the explanation. Support hover/focus only when the media query reports hover capability; always support click/tap.

- [ ] **Step 4: Replace ambiguous `Keys` disclosure**

Render a keyboard icon plus “Keyboard help”. List Arrow/WASD pan, `+`/`−` zoom, and `Q`/`E` tilt only after confirming those handlers are bound. Position the dialog beside the trigger rather than at a fixed viewport corner.

- [ ] **Step 5: Run tests and commit**

```bash
cd website && npm test -- atlas-info-popover.test.tsx
git add website/src/components/atlas/InfoPopover.tsx website/src/components/atlas/KeyboardHelp.tsx website/tests/atlas-info-popover.test.tsx website/src/styles/atlas.css
git commit -m "feat: explain Atlas controls accessibly (#55)"
```

### Task 3: Replace status clutter with one warning rail and compact legend

**Files:**

- Create: `website/src/components/atlas/WarningBanner.tsx`
- Create: `website/src/components/atlas/CompactLegend.tsx`
- Create: `website/tests/atlas-warning-banner.test.tsx`
- Create: `website/tests/atlas-legend.test.tsx`
- Modify: `website/src/components/atlas/AtlasStatus.tsx`
- Modify: `website/src/styles/atlas.css`

**Interfaces:**

- Consumes: deduplicated `ExplorerWarning[]`, retry callback, active artifact, palette/domain, symbol style, and version metadata.
- Produces: one-line top warning summary plus details, and a small bottom legend with an information popover.

- [ ] **Step 1: Write failing warning/legend tests**

```tsx
it("deduplicates warnings and keeps retry in the top rail", () => {
  render(
    <WarningBanner
      warnings={[timeoutWarning(), timeoutWarning()]}
      onRetry={vi.fn()}
    />,
  );
  expect(screen.getAllByText(/timed out/i)).toHaveLength(1);
  expect(screen.getByRole("button", { name: /retry/i })).toBeVisible();
});

it("keeps versions in the legend info disclosure", async () => {
  render(<CompactLegend artifact={artifactRef()} style={surfaceStyle()} />);
  expect(screen.queryByText("map-2026-08")).toBeNull();
  await userEvent.click(
    screen.getByRole("button", { name: /legend details/i }),
  );
  expect(screen.getByText("map-2026-08")).toBeVisible();
});
```

- [ ] **Step 2: Run tests and confirm missing components**

Run: `cd website && npm test -- atlas-warning-banner.test.tsx atlas-legend.test.tsx`

Expected: FAIL on import.

- [ ] **Step 3: Implement one warning model**

Deduplicate on `{source, code, message}`. Show a single-line summary in a full-width rail above both side panels, with a details disclosure for multiple warnings. Treat “Atlas ready” as transient status, not a warning. Keep fatal data errors actionable with retry.

- [ ] **Step 4: Implement the compact legend**

The closed form contains active map, numeric endpoints, gradient, visible symbol keys, and one info trigger. The disclosure defines measured observations, inferred surface, uncertainty, support states, visual elevation, palette, and immutable model/data/registry versions in plain language.

- [ ] **Step 5: Run tests and commit**

```bash
cd website && npm test -- atlas-warning-banner.test.tsx atlas-legend.test.tsx
git add website/src/components/atlas/WarningBanner.tsx website/src/components/atlas/CompactLegend.tsx website/src/components/atlas/AtlasStatus.tsx website/tests/atlas-warning-banner.test.tsx website/tests/atlas-legend.test.tsx website/src/styles/atlas.css
git commit -m "feat: compact Atlas status and legend (#55)"
```

### Task 4: Rebuild explorer controls around plain-language groups

**Files:**

- Modify: `website/src/components/atlas/ExplorerControls.tsx`
- Create: `website/src/components/atlas/MapActions.tsx`
- Create: `website/tests/atlas-controls.test.tsx`
- Modify: `website/src/styles/atlas.css`

**Interfaces:**

- Consumes: catalog, `ExplorerState`, provider availability, selected artifact capabilities, and explicit callbacks.
- Produces: Map, Display, Geography, Observations, and Camera control groups with contextual help and valid disabled states.

- [ ] **Step 1: Write failing capability and labeling tests**

```tsx
it("disables observation controls for a surface-only artifact", () => {
  renderControls(surfaceOnlyState());
  expect(screen.getByLabelText("Observation shape")).toBeDisabled();
  expect(
    screen.getByText(/measured observations are not available yet/i),
  ).toBeVisible();
});

it("distinguishes physical terrain from scientific elevation", () => {
  renderControls(mapState());
  expect(screen.getByLabelText("Physical terrain")).toBeVisible();
  expect(screen.getByLabelText("Scientific elevation")).toBeVisible();
});
```

Also verify the four basemaps, two terrain choices, palette/opacity/edges, circle/hemisphere/pin, size/color variables, min/max controls, footprints, and info buttons.

- [ ] **Step 2: Run the controls test and confirm failure**

Run: `cd website && npm test -- atlas-controls.test.tsx`

Expected: FAIL because the current component exposes only metric/layer/view/elevation controls.

- [ ] **Step 3: Implement grouped controls**

Remove the tracked all-capital kicker. Keep labels at 16 px or larger. Render ion choices disabled with a plain explanation when no token exists. Default observation color to white. Switch size units between pixels and visual kilometres according to shape, retaining one validated range per shape family.

- [ ] **Step 4: Add help to every non-obvious control**

Attach `InfoPopover` to map meaning, posterior estimate, uncertainty, support, basemap, physical terrain, scientific elevation, observation shape, marker size, marker color, and sampling area. Explicitly explain that 563.9 km G6PD rings are source-supported administrative-location uncertainty.

- [ ] **Step 5: Run tests and commit**

```bash
cd website && npm test -- atlas-controls.test.tsx atlas-info-popover.test.tsx
git add website/src/components/atlas/ExplorerControls.tsx website/src/components/atlas/MapActions.tsx website/tests/atlas-controls.test.tsx website/src/styles/atlas.css
git commit -m "feat: expand Atlas explorer controls (#55)"
```

### Task 5: Add downloads and cache-first external information

**Files:**

- Modify: `website/src/atlas/provider.ts`
- Modify: `website/src/atlas/static-provider.ts`
- Create: `website/src/atlas/external-info.ts`
- Create: `website/src/components/atlas/DownloadMenu.tsx`
- Create: `website/src/components/atlas/ExternalInfoPanel.tsx`
- Modify: `website/tests/atlas-provider.test.ts`
- Create: `website/tests/atlas-external-info.test.tsx`

**Interfaces:**

- Consumes: `ArtifactRef.downloads`, `ArtifactRef.external_resources`, cached JSON, and optional live gnomAD/NCBI responses.
- Produces: `getExternalInfo(ref, source, signal): Promise<ExternalInfoResult>`, visible immutable downloads, cache-first display, and non-blocking live status.

- [ ] **Step 1: Write failing eligibility and fallback tests**

```ts
it("refuses lookup without an advertised verified capability", async () => {
  const provider = providerWithCatalog(g6pdArtifact());
  await expect(
    provider.getExternalInfo(g6pdArtifact(), "gnomad"),
  ).rejects.toThrow("not available for this map");
});

it("keeps a dated cache when live revalidation fails", async () => {
  const result = await externalInfoWithFailedLive(hbsArtifact());
  expect(result.origin).toBe("cache");
  expect(result.retrievedAt).toMatch(/^2026-/);
  expect(result.liveWarning).toMatch(/could not refresh/i);
});
```

Also test cache schema rejection, live identifier mismatch, 10-second live timeout, caller cancellation, and map readiness remaining `ready` throughout.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd website && npm test -- atlas-provider.test.ts atlas-external-info.test.tsx`

Expected: FAIL because external lookup and download components do not exist.

- [ ] **Step 3: Implement capability-gated provider calls**

The provider first finds the exact discriminated capability; absence is a local refusal with no fetch. Validate and return cache immediately, then let `external-info.ts` run source-specific live revalidation with a 10-second deadline. A live result replaces only in-memory annotation state after identifier/schema validation.

- [ ] **Step 4: Implement prominent map actions**

Place “More info” and “Download data” directly below the map selector. Downloads use catalog-provided immutable URLs, labels, media types, hashes, and the HTML `download` attribute. Surface-only maps show observations as unavailable, not as an empty file.

- [ ] **Step 5: Implement external context display**

Only render gnomAD/dbSNP buttons advertised by the artifact. Label results Cached or Live with retrieval/release metadata. Links open new tabs. A live failure raises a non-blocking warning while preserving cached content and the active map.

- [ ] **Step 6: Run tests and commit**

```bash
cd website && npm test -- atlas-provider.test.ts atlas-external-info.test.tsx
git add website/src/atlas/provider.ts website/src/atlas/static-provider.ts website/src/atlas/external-info.ts website/src/components/atlas/DownloadMenu.tsx website/src/components/atlas/ExternalInfoPanel.tsx website/tests/atlas-provider.test.ts website/tests/atlas-external-info.test.tsx
git commit -m "feat: add Atlas downloads and variant context (#55)"
```

### Task 6: Extract hooks and integrate scene, state, and UI

**Files:**

- Create: `website/src/components/atlas/useAtlasCatalog.ts`
- Create: `website/src/components/atlas/useExplorerUrlState.ts`
- Modify: `website/src/components/atlas/AtlasExplorer.tsx`
- Modify: `website/src/components/atlas/InspectorPanel.tsx`
- Modify: `website/tests/site.spec.ts`

**Interfaces:**

- Consumes: static provider, URL contract, scene controller, control callbacks, warnings, and selection.
- Produces: a small explorer orchestrator with atomic artifact transitions, persistent selection during presentation changes, and synchronized inspector/highlight clearing.

- [ ] **Step 1: Write failing integration scenarios**

Assert catalog timeout shows retry within 15 seconds; changing palette preserves selection; changing artifact clears hover/selection/inspector together; selecting an observation wins over its underlying surface; closing the inspector clears the gold highlight; surface-only selection never fetches observations; and URL corrections appear only in the warning disclosure.

- [ ] **Step 2: Run the browser integration test and confirm failure**

Run: `cd website && npm run test:e2e -- site.spec.ts`

Expected: FAIL on the new interaction assertions.

- [ ] **Step 3: Extract catalog/request state**

`useAtlasCatalog(provider)` owns catalog loading, artifact loading, aborts, retries, and request sequence. It retains the last valid rendered artifact until a complete replacement validates. It returns typed status/warnings rather than formatted panels.

- [ ] **Step 4: Extract validated URL state**

`useExplorerUrlState(catalog)` owns initial parse, field corrections, `history.replaceState`, and typed update functions. Hover/selection remain session state and are excluded from the URL for this release.

- [ ] **Step 5: Integrate scene and panels**

Keep `AtlasExplorer.tsx` below 500 logical lines. Route scene warnings into `WarningBanner`; route clicks/touch/keyboard selection into both highlight and inspector; route all style changes to the narrow scene setters; and preserve selection across presentation-only changes.

- [ ] **Step 6: Run tests, check size, and commit**

```bash
cd website && npm test && npm run check
cd .. && python scripts/check_module_size.py
git add website/src/components/atlas website/tests/site.spec.ts
git commit -m "feat: integrate the enriched Atlas explorer (#55)"
```

### Task 7: Polish responsive behavior and produce review evidence

**Files:**

- Modify: `website/src/styles/atlas.css`
- Modify: `website/tests/site.spec.ts`
- Modify: `website/tests/atlas-performance.spec.ts`
- Modify: `website/scripts/capture-atlas.mjs`
- Create: `scripts/plot_atlas_explorer_review.py`
- Create: `docs/figures/atlas-explorer-review.png`

**Interfaces:**

- Consumes: integrated explorer at `/app/` and the immutable publication files.
- Produces: desktop/mobile accessibility evidence, high-resolution visual review, Cabo Verde regression evidence, and final performance measurements.

- [ ] **Step 1: Add layout and accessibility browser tests**

At desktop and mobile widths, assert the top warning rail does not intersect controls/inspector, minimum computed font size is 16 px for ordinary control text, popovers remain in the viewport, focus rings are visible, and axe reports no serious/critical violations with popovers both closed and open.

- [ ] **Step 2: Add visual behavior tests**

Capture MAP HbS flat, MAP G6PD with footprints, elevated perspective with country borders, circle/hemisphere/pin shapes, surface-only AFND, hover vs selection, and a Cabo Verde close-up. Exercise reduced motion separately.

- [ ] **Step 3: Generate a reproducible high-resolution review figure**

`scripts/plot_atlas_explorer_review.py` reads committed/public artifacts and composes labeled panels for context-above-surface, observation priority, hover/selection distinction, elevation edges, and Cabo Verde coverage. It must keep measured observations and inferred faces visually separate and show unknown cells explicitly.

- [ ] **Step 4: Run the full website gate**

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
npm run test:performance
```

Expected: every command exits 0; warm switch is under 2 seconds and interaction remains at or above 45 fps on the reference laptop.

- [ ] **Step 5: Run repository-wide gates**

```bash
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python scripts/smoke.py
pytest
```

Expected: every command exits 0. Record exact outputs in the PR body.

- [ ] **Step 6: Commit final evidence**

```bash
git add website/src/styles/atlas.css website/tests/site.spec.ts website/tests/atlas-performance.spec.ts website/scripts/capture-atlas.mjs scripts/plot_atlas_explorer_review.py docs/figures/atlas-explorer-review.png
python scripts/check_private_files.py
git diff --cached --name-only
git commit -m "docs: show the expanded Cesium explorer (#55)"
```

### Task 8: Push and open the reviewable pull request

**Files:**

- No new files; verify the complete branch and GitHub metadata.

**Interfaces:**

- Consumes: all three completed implementation plans and their commits.
- Produces: one PR that explicitly closes Issue #55 and names Atlas design §5, §6, §7, §9, and §11 evidence.

- [ ] **Step 1: Inspect final scope and privacy**

Run:

```bash
git status --short
git diff --stat origin/main...HEAD
python scripts/check_private_files.py
git log --oneline origin/main..HEAD
```

Expected: only approved source, docs, contracts, static public artifacts, and review evidence are included; no local state, tokens, raw private data, or credentials appear.

- [ ] **Step 2: Push the feature branch**

Run: `git push origin feat/55-care-unblock`

Expected: push succeeds without rewriting remote history.

- [ ] **Step 3: Open the PR**

The body must include `Closes #55`, the implemented design sections, why the island fix required republication, why 28 AFND entries are surface-only, how external lookup eligibility is enforced, exact verification commands/results, the raw URL for `docs/figures/atlas-explorer-review.png`, and an explicit request for expert review of WorldPop coverage and AFND reuse notices.

# genomeOS Cesium Explorer Interaction and Catalog Expansion — Design

**Status:** approved in conversation; awaiting written-spec review

**Date:** 2026-09-07

**Scope:** Issue #55, Atlas design §11, and the interaction review of the first Cesium explorer.
This document extends the approved
`2026-09-06-cesium-globe-explorer-design.md`. Where the two differ, this document governs the
explorer controls, scene ordering, observation encodings, external annotations, target geography,
and expanded public catalog. It does not move scientific inference onto the browser or serving
path.

---

## 1. Scientific objective and product claim

The explorer should make geographic patterns in human genetic variation understandable without
letting visual polish erase the boundary between evidence and inference. A person must be able to:

1. identify the selected measured observation or inferred map cell;
2. see ordinary geographic context at the same time as the scientific layer;
3. inspect how marker size, marker colour, surface colour, sampling extent, and visual height were
   encoded;
4. reach the versioned data and external variant records behind the view; and
5. see populated islands and small land masses whenever the published artifact actually supports
   them.

Measured observations and inferred surfaces remain separate data tables and scene layers. Changing
a palette, marker, basemap, or terrain changes presentation only. It never changes a posterior,
support state, measurement, sampling radius, or artifact identity.

## 2. Acceptance evidence

The extension is accepted only when `/app/` demonstrates all of the following with the public
catalog:

- Country boundaries and place labels remain legible above a visible inferred surface.
- Basemap choices include dark streets, roads, aerial imagery, and aerial imagery with labels.
- Terrain choices include a smooth ellipsoid and Cesium World Terrain.
- The last valid basemap remains visible when a newly selected provider fails, with a one-line
  warning that names the failed choice.
- Clicking a surface cell or observation gives it a persistent highlight that is visibly distinct
  from the transient hover glow.
- Moving the pointer over a surface cell or observation smoothly moves a glow to that item; moving
  away fades the glow without changing the selection.
- The legend occupies substantially less map area and exposes its explanation and immutable
  versions through a keyboard-accessible information popover.
- Observation symbols remain above flat and elevated surface cells.
- Observation symbols offer circle, hemisphere, and pin shapes.
- Observation size can be fixed or driven by observed frequency, allele count, or allele
  denominator, with user-controlled minimum and maximum display sizes.
- Observation colour can be white, study-categorical, observed-frequency, or allele-count.
- Sampling-area footprints remain faithful to their source-supported radii and can be controlled
  independently of the observation symbol.
- Posterior and uncertainty each have a metric-specific default palette, with additional
  accessible palette choices.
- Elevation has legible top and vertical edges, opaque-enough faces, and an explicit height scale
  in Globe and Perspective views.
- Warnings appear in a single top banner and are not covered by the inspector.
- Every control whose meaning is not self-evident has an information button operable by hover,
  focus, touch, and keyboard.
- Keyboard help visibly opens beside its trigger and lists only shortcuts that are actually bound.
- The selected artifact offers direct downloads for every available versioned payload.
- gnomAD and dbSNP information is available only for an artifact with the corresponding verified
  normalized identifier; ineligible entities explain why lookup is unavailable.
- The catalog contains both MAP artifacts and all 28 currently published AFND surfaces, for 30
  selectable maps in total. A surface without a validated browser observation export does not
  display or imply measured points.
- A regression view of Cabo Verde contains emitted surface cells for its retained observations;
  the publication test proves those values came from a newly published artifact rather than a
  browser-side fill.
- Catalog load either completes or reaches a visible retry state within 15 seconds. It cannot wait
  forever.

Automated unit, integration, accessibility, and browser tests cover these behaviors. A committed
high-resolution review figure shows the country overlay, observation priority, hover/selection
states, elevation edges, and Cabo Verde coverage.

## 3. Architecture and component boundaries

The scene uses an explicit visual stack:

```text
base imagery + optional physical terrain
  -> inferred H3 surface faces
  -> evidence-support material
  -> H3 top/vertical edges
  -> geographic labels and country boundaries
  -> source-supported sampling-area footprints
  -> measured observation symbols
  -> transient hover highlight
  -> persistent selection highlight
```

The ordering is a visual contract. It does not merge the underlying objects. Picking still returns
either `{kind: "surface", h3Index}` or `{kind: "observation", sourceRecordId}`.

The React island remains an orchestrator rather than accumulating every control and network state.
The implementation splits responsibilities before the existing `AtlasExplorer.tsx` exceeds the
repository's module-size budget:

```text
AtlasExplorer
  |- useAtlasCatalog             catalog and artifact state machine
  |- useExplorerUrlState         validated, shareable presentation state
  |- CesiumAtlasScene
  |    |- BasemapController      imagery and terrain providers
  |    |- SurfaceLayer           faces and support
  |    |- SurfaceEdgeLayer       top and vertical legibility
  |    |- GeographicOverlay      country outlines above the surface
  |    |- ObservationLayer       symbols and sampling footprints
  |    `- HighlightLayer         hover and persistent selection
  |- ExternalInfoProvider        static cache plus live revalidation
  `- ExplorerUI
       |- ExplorerControls
       |- InfoPopover
       |- CompactLegend
       |- WarningBanner
       `- InspectorPanel
```

Each new production TypeScript module cites Atlas design §11 in its module docstring. No scene
module reads an environment variable, artifact file, or remote API. Configuration enters through
typed scene options and provider interfaces.

## 4. Public contracts

### 4.1 Catalog capability metadata

An artifact reference carries capabilities rather than making the UI infer them from identifier
spelling:

```ts
type ExternalResource =
  | {
      source: "gnomad";
      normalizedVariantId: string; // verified GRCh38 chrom-pos-ref-alt
      dataset: "gnomad_r4";
      cacheUrl: string;
    }
  | {
      source: "dbsnp";
      rsid: `rs${number}`;
      cacheUrl: string;
    };

type ArtifactDownloads = {
  surface: DownloadRef;
  observations: DownloadRef | null;
  manifest: DownloadRef;
};
```

Every `DownloadRef` contains a URL, media type, SHA-256 digest, and human-readable label. The
catalog decoder rejects a declared external resource without its verified identifier, a download
without its digest, or an observations capability whose observations download is null.

Phenotypes such as aggregate G6PD deficiency, HLA allele names, cytokine promoter labels, and KIR
gene-presence maps do not become dbSNP or gnomAD queries by string manipulation. They advertise no
external-resource capability unless a separate reviewed mapping identifies a literal variant.

### 4.2 Provider interfaces

The provider adds two narrow operations:

```ts
interface AtlasDataProvider {
  getCatalog(signal?: AbortSignal): Promise<AtlasCatalog>;
  getSurface(ref: ArtifactRef, signal?: AbortSignal): Promise<SurfaceArtifact>;
  getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<ObservationArtifact | null>;
  getExternalInfo(
    ref: ArtifactRef,
    source: "gnomad" | "dbsnp",
    signal?: AbortSignal,
  ): Promise<ExternalInfoResult>;
}
```

`ExternalInfoResult` reports the normalized source payload, source release when available,
retrieval time, whether it came from the published cache or live revalidation, and any
non-blocking live-refresh error. No external lookup participates in catalog, surface, observation,
or scene readiness.

### 4.3 Shareable presentation state

The URL adds validated fields for:

```text
basemap · terrain · surface palette · surface opacity · cell edges
observation shape · observation colour variable · observation size variable
observation minimum size · observation maximum size · sampling-area visibility
```

Allowed enums and numeric bounds are explicit. `observationMin <= observationMax` is required.
Malformed state produces a visible correction and resets only the malformed field. Scientific
identifiers and artifact versions are never substituted.

Hover state is ephemeral. Persistent selection may remain ephemeral for this delivery because the
selected cell is not yet part of the citable-view contract; it must survive palette, basemap, and
terrain changes during the current session.

## 5. Geographic context and Cesium ion

### 5.1 Basemaps

The choices are:

- **Dark streets** — the current OSM-derived context, toned for the genomeOS night palette;
- **Roads** — Cesium world road imagery;
- **Aerial** — Cesium world aerial imagery;
- **Aerial + labels** — Cesium world aerial imagery with place labels.

Provider metadata supplies the visible attribution. Switching is asynchronous: the incoming layer
loads below the existing valid layer, becomes visible when ready, and then replaces the old layer.
A failure leaves the old layer intact and raises the top warning banner.

### 5.2 Terrain

The choices are:

- **Smooth globe** — Cesium's ellipsoid terrain provider;
- **World terrain** — Cesium World Terrain with vertex normals and water masks when available.

Physical terrain and scientific elevation are different controls. The first describes Earth's
topography; the second encodes a selected statistical metric. Labels, legend text, and information
popovers use those exact terms.

The GitHub Actions secret `CESIUM_TOKEN` is exposed to Astro as a public build variable only for
the Pages build. A browser token is necessarily readable by the browser, so it is treated as a
restricted public capability rather than as a confidential server credential: assets-read only,
no write or account scopes, and restricted in Cesium ion to the production and GitHub Pages URLs.
The tracked repository contains only an empty placeholder. If the token is missing, OSM plus the
smooth globe remain functional while ion-backed choices are disabled with an explanation.

### 5.3 Country overlay

Natural Earth boundaries move from a clamped background data source to a dedicated overlay.
Boundary strokes use a depth-independent path for flat surfaces. With scientific elevation, their
display altitude follows the top of the intersected H3 cell plus a small documented rendering
offset. This keeps boundaries readable without changing cell values or treating political borders
as model inputs.

Place labels remain an imagery layer above the scientific faces where the provider supports a
separate label overlay. If a basemap combines labels and imagery, the scientific surface opacity
control and country overlay preserve enough geographic context to orient the user.

## 6. Surface appearance, palettes, and elevation

### 6.1 Palettes

Palettes are named, fixed color-stop definitions interpolated in perceptually linear light. The
metric-specific defaults remain:

- posterior estimate: **Genome**, deep blue -> ion cyan -> aurora mint;
- posterior uncertainty: **Signal**, violet -> lavender -> signal gold.

Additional choices are **Viridis**, **Cividis**, and **Plasma**. The active metric chooses its
default only when no explicit palette is present in URL state. Switching metrics after a user has
chosen a palette preserves the explicit choice. Unknown and prior-dominated materials never use a
numeric palette.

The surface-opacity range is bounded from 0.45 to 1.0 and defaults to 0.86. Country outlines,
support patterns, and observation symbols have independent opacities.

### 6.2 Cell edges and elevated geometry

Every supported cell receives a subtle top edge. In elevation mode, visible vertical edges and a
darker side treatment make height readable without relying on transparency alone. The edge layer
uses the same artifact-wide height function as the faces. It never computes a second scale or
gives masked cells height.

Perspective mode uses an oblique default camera after elevation is first enabled, while respecting
subsequent user camera movement. The compact legend states the statistical domain and its visual
height range. Physical terrain height is never added to, or reported as, the scientific metric.

## 7. Measured observations

### 7.1 Independent encodings

An observation has three independent visual channels:

1. **shape** — circle, hemisphere, or pin;
2. **size** — fixed, observed frequency (`ac / an`), allele count (`ac`), or allele denominator
   (`an`);
3. **colour** — white, study, observed frequency, or allele count.

Sampling radius is not a fourth size variable. It is drawn only by the separate sampling-area
footprint, so a large coordinate uncertainty cannot be mistaken for a large allele frequency or
sample.

Continuous observation scales use the full selected observation artifact, not the viewport.
Frequency uses its fixed scientific domain `[0, 1]`; AC and AN use a documented square-root scale
between the artifact's validated minimum and maximum so a single very large study does not make
every other point invisible. A zero AC remains a valid minimum. Study colours are assigned from a
stable study identifier and a deterministic categorical palette; the exporter never derives study
identity by truncating citation prose.

Circle and pin size ranges are expressed in screen pixels. Hemisphere ranges are expressed in
kilometres and clearly labeled as visual glyph size, not sampling extent. Min/max controls switch
units with shape and retain one validated range per shape family. The browser refuses a reversed,
non-finite, or out-of-bounds range rather than silently swapping it.

### 7.2 Shapes

- **Circle** is a luminous screen-space disk with an outline.
- **Hemisphere** is a translucent dome resting on the observation's rendered base. In 2D Map mode
  it becomes a disk because a 3D dome has no honest top-down silhouette beyond its footprint.
- **Pin** uses a stem and head in Globe/Perspective and an equivalent map-pin glyph in 2D.

Pin height is a fixed presentation constant and conveys no data value. The information popover and
legend say so explicitly.

### 7.3 Ordering and elevation

For each observation, the renderer looks up the H3 cell at the artifact's declared resolution.
Its base altitude is the rendered surface height for that cell plus a small visual offset. On a
flat surface the base is just above the ellipsoid or physical terrain. Unknown or absent cells do
not produce a fabricated surface height; the observation remains visible at the geographic base
and its inspector reports that no supported surface cell exists there.

Sampling-area boundaries use the source-supported `radius_km`. MAP G6PD administrative-centroid
records legitimately reach 563.9 km because their subnational sampling location is unknown. Those
large rings are evidence about low spatial precision, not a rendering bug. Footprints receive
lower opacity, their own toggle, and an information popover; their radius is never clamped to make
the map prettier.

### 7.4 Study identity and browser schema

Browser observation rows add a stable `study_id` and human-readable `study_label`, both supplied by
the source adapter/exporter. They are required before the Study colour option is enabled. The
existing source ID, cohort ID, verbatim population label, AC, AN, radius, citation, and source
locator remain available in the inspector.

## 8. Hover, selection, and inspection

Pointer movement is sampled at most once per animation frame. Cesium `drillPick` retains the rule
that an observation wins when it overlaps a surface cell. The highlight controller owns two small
overlay objects rather than rebuilding the scientific primitives:

- **hover** — cyan-white glow, eased on/off over 160 ms and moved to the item under the cursor;
- **selection** — persistent signal-gold outline/halo that remains until another item is selected,
  the inspector is closed, or the artifact changes.

Surface highlights trace the exact H3 boundary at its rendered top height. Observation highlights
follow the active symbol shape and base altitude. Reduced-motion mode changes opacity immediately.
Keyboard focus and touch selection produce the same persistent highlight as a mouse click.

The inspector is the only large right-side panel. It never overlaps the warning banner. Closing it
also clears the persistent selection, so the scene and panel cannot disagree about what is active.

## 9. Compact controls, legend, and warnings

### 9.1 Visual system

The explorer keeps the existing orbital-observatory identity but spends its strongest visual
effect on the map interaction itself—the cursor-following scientific highlight—rather than on
decorative panel motion. Its six interface tokens are Space `#020712`, Atlas navy `#071b35`, Ion
cyan `#70e6ff`, Aurora mint `#72e7c1`, Signal gold `#f4c86a`, and Support violet `#ad8bff`.
Figtree remains the readable interface face; Raleway remains restricted to the styled genomeOS
wordmark. Controls and prose are left-aligned, ordinary interface text is at least 16 px, and
tracked all-capital eyebrow labels are removed from the control hierarchy.

Panels use one restrained radius and translucency treatment because they are instruments over the
globe, not a collection of interchangeable cards. Section labels, spacing, and disclosure state
carry hierarchy; decorative dividers do not. Motion answers a user action—provider change,
selection, hover, disclosure, or scene morph—and no independent ambient panel animation competes
with the globe.

### 9.2 Layout and disclosure

The desktop hierarchy is:

```text
+---------------------------+                       +----------------------+
| Map selector              |  one-line warnings   | selected-item panel  |
| More info / Download      |<-------------------->| (only after click)   |
| Display                   |                       +----------------------+
| Geography                 |
| Observations              |        globe/map
| Camera + keyboard help    |
+---------------------------+
                  [active label | compact gradient | keys | info]
```

The bottom legend contains only the active map label, numeric endpoints, color ramp, visible symbol
keys, and one information button. The popover contains the measurement/inference explanation,
support definitions, visual-height mapping, model/data/registry versions, and palette name. It
opens on hover or focus when a hover-capable pointer exists, and on click/tap everywhere. Escape
closes it and focus returns to the trigger.

Control labels remain plain language. Information buttons explain at least: selected map,
posterior estimate, uncertainty, support, basemap, physical terrain, scientific elevation,
observation shape, marker size, marker colour, and sampling area. Popovers are not native `title`
attributes and meet keyboard, touch, focus-management, and contrast requirements.

Warnings are deduplicated into a single top banner. Multiple active warnings are summarized in one
line with a disclosure for details. Readiness is not a warning; the `Atlas ready` chip disappears
after a short confirmation. Errors that prevent scientific rendering retain their retry action.

Keyboard help replaces the ambiguous **Keys** label with a keyboard icon plus **Keyboard help**.
Its popover is positioned relative to its trigger, never fixed to an unrelated viewport corner.

## 10. Downloads

The selected-map header has a prominent **Download data** menu. It offers:

- inferred surface JSON;
- measured observations JSON when published;
- artifact manifest/provenance JSON.

Each item names the model/data version and expected file type. The links point to immutable,
checksum-bearing public artifacts and use the browser's download behavior. A surface-only AFND map
states that measured observations are not yet available rather than presenting an empty download.
The menu never exposes a raw private path, credential, or unrestricted bulk query.

## 11. gnomAD and dbSNP information

### 11.1 Eligibility

The **More info** disclosure sits immediately below the selected map. gnomAD appears only when the
catalog carries a verified GRCh38 `chrom-pos-ref-alt`. dbSNP appears only when it carries a verified
rsID. No radius, allele orientation, coordinate conversion, rsID, or phenotype-to-variant mapping
is inferred in the browser.

The HbS map can expose both resources after its `chr11-5227002-T-A`/`rs334` identity is verified in
the export metadata. The aggregate G6PD-deficiency phenotype exposes neither. AFND HLA/KIR/cytokine
entries expose neither unless a future reviewed crosswalk supplies a literal compatible variant.

### 11.2 Cache and revalidation

A deterministic maintenance script calls the public gnomAD GraphQL API and NCBI RefSNP API for the
allowlisted identifiers, validates a narrow response schema, records source release/retrieval time,
and publishes the normalized JSON to the Hugging Face dataset. The website exporter pins and copies
those cache objects beside the scientific artifacts.

At runtime, choosing a resource displays the validated cache immediately and starts a live request
to that resource. A valid response replaces the session copy and is labeled **Live**. A timeout,
CORS failure, remote schema change, or rate limit leaves the cached record visible with its
retrieval date and a non-blocking warning. The public browser never writes to Hugging Face and never
receives an HF credential; cache refresh remains a maintainer or scheduled build job.

External records are contextual annotations, not genomeOS measurements or posterior inputs. They
cannot alter the selected artifact, its legend, or its scientific values.

## 12. Small islands and the surface target grid

The missing Cabo Verde cells originate before rendering. Current MAP artifacts use
`h3_land_cells()`, which keeps only cells whose centers fall inside Natural Earth 1:110m polygons.
That coarse file omits several small states entirely. Filling those gaps in JavaScript would invent
posterior values and is forbidden.

The publication target changes to a versioned, population-supported grid:

1. aggregate the pinned WorldPop raster to the artifact's H3 resolution;
2. retain cells with valid WorldPop coverage and population greater than zero;
3. union the H3 cell containing every retained observation;
4. require every unioned observation cell to have explicit population-coverage status;
5. predict the saved fit at the new cell centers offline;
6. classify support with the existing mask logic;
7. publish a new immutable artifact version; never mutate the existing surface;
8. assert that every retained observation maps to an emitted cell.

If WorldPop is unavailable, inconsistent, or unversioned, publication fails. Natural Earth remains
valid for visual country outlines but is no longer a scientific population-grid fallback. An
observation cell with valid zero population is a source/denominator conflict that fails review; it
is not silently painted. A cell with no WorldPop coverage remains unresolved until coverage is
supplied.

The first regression fixture includes Cabo Verde and a comparably small populated island. Tests
show that center-in-coarse-polygon selection misses them and the population-supported grid includes
them. The review figure shows the resulting published cells and their support state.

## 13. Catalog expansion and surface-only artifacts

The public catalog contains 30 entries from the pinned Hugging Face revision:

- 2 MAP maps with browser-ready measured observations: HbS and aggregate G6PD deficiency;
- 4 AFND cytokine-variant surfaces;
- 20 AFND HLA-allele surfaces;
- 4 AFND KIR carrier-frequency surfaces.

AFND observation overlays remain unavailable until the duplicate `source_record_id` defect tracked
by #154/#160 is resolved and the corpus is rebuilt. The catalog sets
`observations_available: false`, the provider returns `null` without issuing an observation fetch,
and every observation control is disabled with a plain-language explanation. Manifest
`n_observations` remains the number used to fit the surface; it is not displayed as though those
rows were downloadable.

Issue #66 now permits publication of fitted AFND surfaces subject to preserved attribution,
Biocultural Notices, measured/inferred separation, and any explicit source restriction. Missing
standalone license text is not itself a publication veto. The website and repository policy text
are updated to reflect that resolved decision.

## 14. State transitions and failure behavior

The load state machine remains fail-closed:

```text
loading catalog -> loading artifact -> validating -> rendering -> ready
       |                  |                |             |
       +------------------+----------------+-------------+-> visible error + retry
```

Catalog and artifact requests have a 15-second deadline and preserve caller cancellation. Scene
changes retain the last valid rendered layer until the replacement validates and becomes ready.

| Failure                                        | Required behavior                                                                              |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Catalog request stalls                         | Abort at 15 seconds; show retry and requested URL category, never spin forever                 |
| Basemap or terrain fails                       | Keep last valid provider; show one-line warning; scientific layers remain usable               |
| Cesium token absent                            | Disable ion choices; keep OSM/smooth globe available; explain the requirement                  |
| External annotation fails                      | Keep dated cached result if present; otherwise show source-specific failure; map remains ready |
| External payload changes schema                | Reject it; do not show partially parsed fields                                                 |
| Observations unavailable                       | Render inferred surface only and disable observation controls/download                         |
| Observation has no surface cell                | Keep the measurement visible at geographic base; report no supported cell                      |
| WorldPop target grid incomplete                | Refuse publication; do not fall back to a coarse land-center mask                              |
| Highlighted item disappears on artifact change | Clear hover, selection, and inspector together                                                 |
| URL field is malformed                         | Correct that field only and report it in the warning disclosure                                |

## 15. Performance and accessibility

Scientific geometry remains batched. Hover and selection use at most two small overlay groups; they
do not rebuild or duplicate all H3 primitives. Pointer picking is frame-throttled. Palette and
opacity changes update existing material state where possible; geometry is rebuilt only when height
or edge geometry changes. The cache key includes every geometry-affecting field and excludes
presentation-only fields.

Adding 28 catalog entries does not fetch 28 surfaces. Only the selected surface loads; adjacent
choices may be warmed within the existing bounded cache. The catalog target remains under 100 KiB
compressed, warm map switching under 2 seconds, and camera interaction at 45+ frames per second on
the reference laptop.

All information popovers use buttons with accessible names and described-by relationships. Hover
is never the only activation mechanism. Focus indicators remain visible over the map. Color is
never the only indicator of selected state, support state, or layer availability. Every palette is
checked for ordered lightness and common color-vision deficiencies. Reduced-motion mode disables
glow interpolation, crossfades, camera flight, and scene morph animation.

## 16. Verification plan

### Python and publication tests

- The target-grid builder includes WorldPop-positive small-island cells and every observation cell.
- Missing/unversioned WorldPop data and observation/population conflicts fail loudly.
- Republishing changes the artifact identity and leaves the original artifact intact.
- The exporter produces 30 allowlisted catalog entries and never creates observation URLs for the
  28 surface-only entries.
- Download references and external-resource capabilities have checksums and verified identifiers.
- gnomAD/dbSNP cache normalization rejects remote error payloads and incompatible schema changes.

### TypeScript unit and component tests

- URL state round-trips every new control and refuses reversed size ranges or unknown enums.
- Palette endpoints, height mapping, square-root AC/AN scaling, and study colors are deterministic.
- Sampling radius never enters symbol-size calculations.
- Surface/observation pick precedence and highlight state transitions are deterministic.
- Observation base height follows the selected cell's rendered elevation and refuses fabricated
  height for unsupported/missing cells.
- External lookup is impossible without a catalog capability and remains outside readiness state.
- Provider timeouts, cancellation, surface-only observation behavior, and cache/live annotation
  fallbacks are covered.

### Browser, accessibility, and review evidence

- Exercise every basemap, both terrain choices, all three views, both metrics, palettes, opacity,
  edges, all observation shapes, size/color variables, sampling areas, and downloads.
- Hover and click both a cell and an observation; verify transient and persistent highlights differ.
- Enable elevation and verify point/outline altitudes remain above their cells.
- Open every information popover by keyboard and touch; run axe in open and closed states.
- Simulate imagery, terrain, annotation, and catalog failures and verify the top banner never
  overlaps the inspector.
- Select at least one MAP and one surface-only AFND artifact.
- Capture desktop, mobile, elevation, and Cabo Verde screenshots at device scale.
- Record warm-load latency, frame rate, long tasks, catalog transfer size, and selected-artifact
  transfer size.

Before commit and push, run the repository's focused suites, full website checks, mandatory smoke,
schema freeze check, module-size check, privacy gate, Ruff, and full pytest suite. The PR lists the
exact commands and outputs rather than claiming generic verification.

## 17. Assumptions, refusals, and downstream consumers

Assumptions:

- The existing saved posterior fits can be used to predict the new WorldPop-backed target cells. If
  a fit is unavailable, that artifact cannot claim the small-island fix until it is reproducibly
  refit.
- `CESIUM_TOKEN` remains assets-read only and is restricted to the deployment URLs before release.
- Hugging Face is the temporary artifact/cache origin; the provider boundary later moves to GCP.
- The currently published AFND surfaces passed their artifact publication checks; observation
  overlays are a separate capability.

Refusals:

- Never generate a radius, study identity, rsID, normalized variant, palette domain, surface cell,
  or posterior value in the browser because a display control needs one.
- Never size a symbol by sampling uncertainty or describe a visual hemisphere/pin height as a
  scientific value.
- Never query gnomAD/dbSNP for a phenotype, gene, or allele label without a verified compatible
  identifier in the catalog.
- Never let an external annotation alter the genomeOS artifact or block map readiness.
- Never publish a small-island value by nearest-neighbor copying, polygon fill, or client-side
  interpolation.
- Never ship a Cesium, Hugging Face, GCP, or external-service write credential in a static asset.
- Never render an unavailable observation set as zero observations.

Downstream consumers are the future GCP `AtlasDataProvider`, 3D Tiles publication path,
administrative aggregation, burden layers, region selection, and conversational data interface.
They depend on versioned catalog capabilities, immutable downloads, and semantic visual state—not
Cesium implementation details.

## 18. Alternatives rejected

### Patch the current component directly

Rejected because `AtlasExplorer.tsx` is already near the module-size budget and would combine scene
lifecycle, external requests, URL correction, and complex control state. The resulting behavior
would be harder to test and replace when GCP serving arrives.

### Render country borders or missing islands as CSS/SVG overlays

Rejected because a screen overlay cannot follow a rotating globe or elevated cell geometry, and a
browser-created island fill would imply a posterior that the artifact does not contain.

### Use live external APIs as the only annotation source

Rejected because network latency, rate limits, CORS policy, and remote schema drift would make a
nonessential annotation control unreliable and unreproducible. Cache-first display with live
revalidation keeps the source fresh without making it critical path.

### Encode the sampling radius through marker size

Rejected because that would make the large G6PD administrative footprints look like high-frequency
or high-count samples. A separate footprint layer preserves their actual scientific meaning.

### Migrate immediately to 3D Tiles and GCP

Rejected for this catalog size. The provider and layer contracts retain that scale path, but this
delivery first makes the scientific semantics and interaction behavior correct on static artifacts.

# genomeOS Cesium Globe Explorer — Design

**Status:** approved

**Date:** 2026-09-06

**Scope:** Issue #55 and the P5 visualization interfaces in Atlas design §11. This design
supersedes the earlier MapLibre/deck.gl renderer choice for the globe explorer; it does not alter
the P0–P4 scientific or serving contracts.

---

## 1. Product claim and scientific objective

The explorer lets a person move continuously between a global view and a local geographic view of
human genetic variation while preserving the distinction between:

1. **measured observations** — where a source actually sampled people;
2. **inferred surfaces** — posterior estimates between measurements;
3. **uncertainty and support** — where estimates are imprecise, prior-dominated, or unavailable.

The product claim is not that genomeOS knows a value everywhere. It is that a user can explore what
the current evidence supports, see the uncertainty, and reach the source and artifact version behind
every displayed result.

The first public build uses the open MAP HbS and G6PD collections already present in the genomeOS
artifact store. The rendering and data-provider boundaries must support additional variants,
alleles, burden layers, and larger tiled datasets without replacing the application shell.

## 2. Measurable output and acceptance evidence

The implementation is accepted when the deployed `/app/` route provides all of the following:

- a responsive CesiumJS Earth that rotates, tilts, pans, and zooms smoothly with mouse, touch,
  trackpad, and keyboard-accessible controls;
- animated transitions among **Globe**, **Map**, and **Perspective** views;
- variant or phenotype selection that swaps the displayed artifact without a page reload;
- a data-layer selector for posterior estimate and posterior uncertainty;
- independently togglable observations, inferred surface, support mask, and geographic context;
- an **Elevation** control that renders the active metric as height in Globe or Perspective view;
- geographic context containing country, subregion, city, and road labels from an OSM-derived map;
- an inspector for a selected cell or observation with values, interval, support, provenance, and
  immutable data/model versions;
- URL round-tripping for the selected entity, metric, layers, view mode, elevation, and camera;
- visible attribution for CesiumJS and every active map/data source;
- a mobile layout that keeps the globe usable without permanent side panels covering it;
- a reduced-motion path and a non-WebGL failure message with direct access to the data provenance;
- automated unit, integration, accessibility, and browser tests plus a committed review figure.

Target interactive performance for the initial MAP artifacts on a current mid-range laptop is a
steady 45+ frames per second while rotating, no more than 2 seconds from selection to a visible new
surface on a warm cache, and no main-thread task over 250 ms during ordinary camera interaction.
Performance evidence is captured in the PR; the target is not inferred from a successful build.

## 3. Decisions

| Decision                    | Choice                                                                       | Consequence                                                                                                           |
| --------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Rendering engine            | CesiumJS, Apache-2.0                                                         | Native high-precision globe, 2D/2.5D modes, terrain-aware camera, PBR, post-processing, and a native path to 3D Tiles |
| Website integration         | React island inside the existing Astro `/app/` route                         | The documentation site and explorer share one deployment while Cesium remains client-only                             |
| Initial scientific data     | Curated MAP HbS and G6PD export from Hugging Face                            | A real end-to-end path without publishing unresolved AFND-derived artifacts                                           |
| Permanent data boundary     | `AtlasDataProvider` interface                                                | Hugging Face/static files can be replaced by the GCP read API without changing controls or rendering                  |
| Initial scientific geometry | Batched Cesium primitives, never one Entity per H3 cell                      | Exact H3 boundaries with substantially lower CPU/draw-call overhead                                                   |
| Scale-up geometry           | Metadata-rich 3D Tiles with spatial LOD                                      | Large and heterogeneous future layers stream by viewport and screen-space error                                       |
| Geographic context          | Toggleable OSM-derived raster context through a replaceable imagery provider | Familiar place labels now; production tiles can move to a self-hosted GCP service later                               |
| Elevation                   | Scientific-value extrusion, not physical terrain                             | Height is explicitly a visual encoding and never described as geographic altitude                                     |
| Support mask                | On by default and not silently disabled                                      | A smooth, cinematic globe cannot hide evidence gaps                                                                   |

## 4. Application architecture

```text
Astro /app route
  └─ React island: AtlasExplorer
       ├─ ExplorerStore                 URL-backed UI state
       ├─ AtlasDataProvider             engine-independent data contract
       │    ├─ StaticHfProvider         initial compiled Hugging Face export
       │    └─ GcpApiProvider           later P4 HTTP implementation
       ├─ CesiumScene                   camera, view modes, imagery, atmosphere
       ├─ ScientificLayerController
       │    ├─ ObservationLayer         measured samples only
       │    ├─ SurfaceLayer             posterior estimates only
       │    └─ SupportLayer             unknown/prior-dominated overlay
       └─ ExplorerUI                    selectors, legend, inspector, mobile sheets

Hugging Face dataset at a pinned revision
  └─ allowlisted build-time exporter
       └─ immutable browser artifacts + catalog + checksums
            └─ GitHub Pages /app data
```

No Cesium component imports a Python model, reads a fit file, or computes a posterior. It consumes
only versioned, precomputed artifacts. No provider decides how data is colored or rendered. No UI
component knows whether an artifact came from Hugging Face, a local fixture, or GCP.

### 4.1 Public interfaces

The TypeScript provider contract exposes narrow asynchronous methods:

```ts
interface AtlasDataProvider {
  getCatalog(signal?: AbortSignal): Promise<AtlasCatalog>;
  getSurface(ref: ArtifactRef, signal?: AbortSignal): Promise<SurfaceArtifact>;
  getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<ObservationArtifact>;
}
```

`SurfaceArtifact` contains the H3 index, posterior mean, posterior standard deviation, interval,
support state, nearest-observation distance, and artifact versions. `ObservationArtifact` contains
coordinates, sampling radius, sample size or denominator, source locator, and citation. The
renderer refuses an artifact that omits its version, support state, or metric definition.

The initial static provider uses content-addressed files named by artifact identity and checksum.
The future GCP provider implements the same interface using P4 endpoints and viewport requests.

## 5. Data preparation and publication boundary

The Hugging Face repository is an artifact origin, not a browser database. A deterministic exporter
will:

1. read a repository-owned allowlist;
2. pin the Hugging Face dataset revision rather than following mutable `main`;
3. accept authenticated or anonymous download, depending on repository gating;
4. validate the source manifest and required surface columns;
5. export only MAP HbS and G6PD artifacts plus their observations;
6. generate a catalog, compact web payloads, checksums, attribution, and source revision;
7. fail if a requested artifact is absent, malformed, unversioned, or not allowlisted.

There is no permissive fallback from a requested real artifact to synthetic data. Tests may use
explicitly named fixtures, but production builds may not. AFND-derived surfaces and other datasets
covered by open governance questions are excluded even if the Hugging Face repository itself is
public or gated.

The generated browser assets are immutable and safe to cache indefinitely. Switching to GCP changes
the provider composition and artifact URLs, not scientific values or explorer behavior.

## 6. Scene and visual direction

The scene is an **orbital observatory**, visually continuous with the genomeOS banner and existing
site art:

- near-black space (`#020712`) with restrained stars;
- a deep-blue Earth with a cyan atmospheric rim;
- posterior surfaces moving from low-luminance blue to ion cyan and aurora mint;
- uncertainty using a distinct violet-to-signal-gold scale rather than a brighter version of the
  frequency palette;
- measured observations drawn as crisp luminous rings or beacons above, never merged into, the
  inferred surface;
- unsupported cells drawn with visibly different materials: muted crosshatch for `unknown` and
  violet stipple for `prior_dominated`;
- subtle bloom and atmosphere, with legibility taking priority over glow;
- no continuous autorotation after the introductory camera flight.

The globe occupies the viewport. Controls use translucent observatory panels with large type and
large touch targets. They do not reproduce the documentation landing page inside `/app/`.

## 7. Interaction model

### 7.1 View modes

The primary segmented control is **Globe · Map · Perspective**:

- **Globe** maps to Cesium `SCENE3D`.
- **Map** maps to `SCENE2D` for a familiar top-down geographic view.
- **Perspective** maps to `COLUMBUS_VIEW` for an oblique 2.5D topographic view.

Cesium morph transitions preserve the selected entity, layers, region, and inspector selection.
Reduced-motion mode uses immediate scene-mode changes instead of morphing.

If Elevation is enabled from Map view, the app moves to Perspective view after explaining that
height needs an oblique or globe view. Returning to Map preserves the elevation setting but renders
the metric by color only.

### 7.2 Camera

Mouse, trackpad, touch, and keyboard controls support rotate, pan, tilt, and smooth zoom. The initial
visit uses one short camera flight that frames the available artifact. After direct user input, the
application never takes control of the camera unless the user selects **Home**, chooses a search
result, or changes view mode.

Camera updates are written to the URL only after interaction settles so history and rendering are
not flooded on every frame.

### 7.3 Desktop and mobile controls

Desktop uses a compact left control dock, a bottom legend, and a right inspector that opens only
after selection. Mobile uses a top entity selector plus collapsible bottom sheets; the central
portion of the globe remains available for one-finger rotation and pinch zoom.

All icon-only controls have visible tooltips and accessible names. Layer and metric controls are
real form controls, not click handlers on decorative elements.

## 8. Scientific layers

Each layer has a separate Cesium primitive or imagery collection and an independent visibility
state.

### 8.1 Posterior surface

The surface uses exact H3 boundaries. Color encodes either posterior mean or posterior standard
deviation according to the selected metric. Selecting an H3 cell opens an inspector containing:

- estimate and 95% credible interval;
- uncertainty;
- support state;
- distance to nearest observation when available;
- model, data, registry, and artifact versions;
- a link to the observations and provenance.

Zoom never subdivides a scientific cell beyond the published H3 resolution.

### 8.2 Elevation

Elevation is off by default. When enabled, the top face of each supported H3 cell is extruded
outward from the ellipsoid according to the active metric. A labeled exaggeration control changes
visual scale, with the legend reporting both the scientific value and the visual height mapping.

Height is normalized within a documented metric domain shared across the active artifact, not
renormalized to the current viewport. This prevents the same value from appearing taller merely
because the camera moved. `unknown` and `prior_dominated` cells never receive a fabricated height.

Geometry changes are built off the interaction path, then smoothly morphed into the scene over an
eased 720 ms transition. Both spatially registered H3 layers remain alive during the transition so
heatmap patterns and palette changes blend continuously rather than flashing between states. Camera
motion continues against the old geometry until the replacement is ready; the app never freezes
rotation while rebuilding an elevation layer. Reduced-motion mode swaps immediately.

### 8.3 Observations

Measured samples render as rings sized by the source-supported sampling radius and visually scaled
by sample size where available. A null radius is a schema error rather than a default circle. The
observation inspector includes the verbatim population label, denominator, citation, source
locator, assay, and sampling design.

### 8.4 Support mask

The support layer is on by default. `unknown` and `prior_dominated` remain distinct and are excluded
from every displayed aggregation. Hiding the visual overlay requires an explicit control, while
the inspector and legend continue to report support status.

### 8.5 Geographic context

The context layer is independently togglable and contains an OSM-derived map with country,
subregion, city, and road labels. It appears beneath scientific layers and carries visible
attribution. Its provider is configuration at the application boundary; no scientific module knows
which imagery service is active.

The prototype may use a responsibly rate-limited public OSM-derived tile endpoint. Production must
use a provider whose service terms cover expected traffic or a self-hosted tile service on GCP.
Cesium ion is optional and is not required by this design.

## 9. Variant and metric changes

Selection follows an explicit state machine:

```text
idle → loading catalog → loading artifact → validating → rendering → ready
                                    └───────────────→ error
```

Changing the entity or metric aborts stale requests. The current scene remains visible with a
loading indicator until the replacement is validated and ready, then spatially registered layers
morph continuously with an eased blend, including a smooth palette transition. The UI does not
clear to an empty globe and does not briefly display one entity under another entity's legend.

Posterior mean and uncertainty use the same artifact, so switching between them requires no network
request. A future burden artifact may be lazy-loaded because it has a separate scientific meaning
and version.

## 10. URL and shareability

The query string records only stable public state:

```text
entity · artifact version · metric · visible layers · scene mode
elevation enabled · exaggeration · longitude · latitude · height · heading · pitch
```

Unknown or malformed values produce a visible correction message and revert only the invalid field.
They never trigger a different scientific default silently. Loading a shared URL waits for both the
catalog and scene before applying camera state.

## 11. Performance and scale path

The first artifacts contain thousands, not millions, of H3 cells. They use batched primitives and
worker-backed geometry creation. The implementation must not create a Cesium Entity or React
component per cell.

When an artifact exceeds a measured threshold, the publication pipeline emits 3D Tiles partitioned
spatially and hierarchically. Tiles carry structured metadata for posterior mean, uncertainty,
support, and artifact identity so styling and picking remain data-driven. Cesium then performs
screen-space-error selection, frustum/horizon culling, request prioritization, and cache eviction.

Modeling, aggregation, and artifact generation remain GCP/Python workloads. Moving rendering to
Cesium does not move scientific inference into the browser.

## 12. Failure and refusal behavior

| Failure                                | Required behavior                                                                                              |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| WebGL unavailable or context lost      | Show a plain-language failure panel, retry control, provenance link, and supported-browser guidance            |
| Artifact request fails                 | Keep the previous valid scene, identify the unavailable entity/version, and offer retry                        |
| Artifact schema or checksum fails      | Render no replacement layer and report validation failure; never drop malformed cells                          |
| Surface exists but observations do not | Surface remains visibly labeled inferred; observations control reports unavailable rather than empty           |
| Context-map provider fails             | Scientific layers remain usable over a neutral globe with Natural Earth outlines and attribution state updated |
| URL contains an unavailable artifact   | Preserve the requested identifier in the error and do not substitute another variant                           |
| Unsupported cells are present          | Render the support material and no elevation; never coerce to zero                                             |
| User selects a new artifact rapidly    | Abort stale fetch/build work; only the newest validated selection may enter the scene                          |
| Reduced motion requested               | Disable introductory flight, cross-fade, and scene morph animation                                             |

## 13. Testing and review evidence

### Unit tests

- catalog, surface, observation, and URL-state decoders reject missing or invented fields;
- metric color and height domains are deterministic;
- `unknown` and `prior_dominated` cannot receive height or enter aggregations;
- provider cancellation prevents stale artifacts from committing;
- view-mode/elevation transitions follow §7.1;
- provenance and attribution are present for every public artifact.

### Component and browser tests

- load `/app/`, rotate, zoom, and select a cell;
- switch entity without reloading the page;
- switch posterior mean/uncertainty and verify legend plus inspector;
- toggle observations, support, and context independently;
- toggle Elevation and verify 3D geometry plus Map/Perspective behavior;
- round-trip a complete shared URL;
- exercise mobile controls, keyboard controls, and reduced motion;
- simulate failed artifact and imagery requests;
- run axe against all stable panel states.

### Visual and performance evidence

The PR includes a high-resolution screenshot or scripted capture committed under `docs/figures/`.
It must show observations and inferred surfaces as distinct layers, visibly show an unsupported
region, and use an unambiguous low-to-high color ramp. A scripted browser trace records frame rate,
load latency, and long tasks for the initial HbS artifact. Hardware-accelerated runs enforce all
three targets; software-rendered CI runs enforce warm-load latency and record the renderer-bound
frame/long-task measurements for comparison rather than presenting them as laptop GPU evidence.

## 14. Assumptions and downstream consumers

Assumptions:

- MAP HbS and G6PD artifacts are explicitly approved for the public prototype;
- the Hugging Face repository remains the temporary artifact origin and may remain gated;
- a GitHub Actions secret may authenticate the build-time export while no token is shipped to the
  browser;
- the first release uses precomputed artifacts and performs no fitting or burden inference;
- OSM-derived geographic context is attribution-bearing and replaceable.

Refusal conditions:

- do not publish an artifact absent from the allowlist;
- do not infer a missing sampling radius, support state, metric, coordinate, or version;
- do not render an inferred layer as an observation or vice versa;
- do not expose a Hugging Face or GCP credential in static assets;
- do not ship AFND-derived public artifacts while Issue #66 remains unresolved;
- do not represent visual extrusion as physical terrain or absolute geographic height.

Downstream consumers are the later burden layer, administrative aggregation, region selection,
conversational data interface, and GCP artifact service. They depend on the provider, URL state, and
layer metadata contracts rather than Cesium implementation details.

## 15. Alternatives considered

### MapLibre GL JS

MapLibre is the strongest choice for vector cartography and would make OpenFreeMap integration
direct. It now supports globe projection, terrain, heatmaps, and fill extrusion. It was rejected as
the primary engine because game-quality lighting, heterogeneous 3D content, and massive 3D Tiles
would require custom WebGL/Three.js integrations at the exact point where Cesium provides native
abstractions.

### MapLibre plus Cesium

Running synchronized engines would provide the best vector basemap and the best 3D globe, but it
duplicates cameras, picking, render loops, GPU memory, accessibility state, and failure modes. The
complexity is not justified for the first explorer.

### Custom Three.js globe

This provides maximum visual control but requires rebuilding ellipsoid precision, tile selection,
terrain, labels, attribution, picking, navigation, and accessibility. It was rejected because those
are infrastructure rather than genomeOS product value.

## 16. Delivery boundary

Issue #55 delivers the Cesium application shell, static provider, initial MAP surfaces and
observations, view modes, scientific layer controls, Elevation, context map, inspector, URL state,
tests, and review evidence described above. It advances the existing P5 layer issues but does not
claim to finish burden, administrative aggregation, or region-selection interfaces that depend on
later backend artifacts.

# Terrain covariate qualification: source before model

Status: `automated_proposal` / `pending`, 2026-09-10. Advances WP3 of
[#189](https://github.com/bschilder/genomeOS/issues/189), not a completed
covariate admission. No raster extraction, model fit or predictive gain is claimed.
Implements research preparation for Atlas design §§4–7, 12 and the
[global modeling plan](../superpowers/plans/2026-09-09-global-af-modeling.md).

## Scientific contract

Objective: test whether qualified elevation and water-context features improve
withheld allele-count prediction beyond the strongest eligible genetic/spatial
baseline, at unchanged evaluation populations and coverage.

Output now: inspected source choices, measurement semantics, access boundaries
and a falsifiable extraction/ablation checklist. The future engineering boundary
is an offline, versioned footprint-feature artifact consumed by training and
benchmark adapters; no network or raster I/O enters pure science or serving.

Assumptions: reviewed population support exists, source reuse is permitted, and
feature timing is meaningful for the observation target. Missing support, masks,
datum, dates or permissions do not become plausible defaults. Terrain detail
does not identify residence, ancestry, migration or validated genetic resolution.

## Source choices remain distinct

| Candidate | Evidence and remaining decision |
| --- | --- |
| Current CDSE GLO-30/GLO-90 DGED | The current releases table ends at `2024_1`; registered general-public users can obtain these instances. Reconcile the effective snapshot through the delivery manifest and product identifiers before retrieval. |
| Public Sinergise/AWS COG mirror | Its registry identifies a 2021 source release, with narrower GLO-30 availability. Account-free access is technically convenient, but this is not a substitute for the current release without an explicit version decision. |
| Existing Cesium display integration | A rendering provider/asset ID is not a pinned scientific feature dataset or evidence of offline-extraction permission. |

CDSE describes predominantly 2011–2015 acquisitions, with older gap-filling data;
release date is not measurement date. Some updates change access/licensing rather
than elevations. Retain per-product acquisition support and effective tile
versions; do not assume a latest-release attribute alone reconstructs the whole
snapshot. [CDSE product page and release table](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM),
[official delivery manifest](https://s3.waw3-1.cloudferro.com/swift/v1/portal_uploads_prod/COP-DEM_delivery_sheet_2024_1_LatLon_v3.1.xlsx).

The AWS mirror has no ocean tiles. Its conversion removes shared east/south
border posts, so geotransforms and edge ownership must follow that distribution.
Our policy is to preserve missing coverage, not adopt an ocean-zero assumption.
The registry, not the bucket readme, establishes the 2021 release attribution.
[AWS registry](https://registry.opendata.aws/copernicus-dem/),
[distributor conversion documentation](https://copernicus-dem-30m.s3.amazonaws.com/readme.html).

## Measurement semantics that an extractor must retain

Copernicus DEM is an edited surface model, including vegetation and buildings,
not bare-earth terrain. [Provider description](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).
DGED stores point-post elevations in metres, with
WGS84-G1150 horizontal and EGM2008 orthometric vertical references. Latitude
spacing is 1 arcsecond for GLO-30 and 3 for GLO-90; longitude spacing varies by
latitude. Nominal metres are not uniform pixel areas.

EDM and FLM describe editing and fill provenance; WBM classifies non-water,
ocean, lake and river. These categorical masks are already majority-resampled;
hydrological consistency is not guaranteed. HEM represents selected random
height errors, not total uncertainty; edited areas use an unavailable sentinel.
SRC supplies scene/time provenance. Preserve ACM's tile-level accuracy support
count: the handbook considers it reliable with at least 200 filtered ICESat GLAS
points per geocell. Unsupported or absent ACM is missing, not good accuracy.
Availability in documentation does not establish availability in a chosen mirror.
[Product Handbook i5.0, §§1.2.1–1.2.5](https://dataspace.copernicus.eu/sites/default/files/media/files/2024-06/geo1988-copernicusdem-spe-002_producthandbook_i5.0.pdf).

A bounded audit inspected one NYC tile per AWS resolution. All eight advertised
assets returned HTTP 200 to HEAD requests, including DEM/EDM/FLM/WBM/HEM;
neither item advertised SRC. This is sample accessibility, not global completeness
or raster-content validation. Provider version headers were null: freeze content
hashes, not keys/ETags alone. [GLO-30 item](https://copernicus-dem-30m-stac.s3.eu-central-1.amazonaws.com/items/Copernicus_DSM_COG_10_N40_00_W074_00.json),
[GLO-90 item](https://copernicus-dem-90m-stac.s3.eu-central-1.amazonaws.com/items/Copernicus_DSM_COG_30_N40_00_W074_00.json).

## Cesium and reuse boundaries

The inspected app selects World Terrain through `createWorldTerrainAsync`,
requesting water masks and normals. Public APIs describe optional server content;
terrain sampling interpolates mesh triangles and returns ellipsoid heights.
Those values cannot silently be mixed with orthometric DEM heights. A reflective
water-rendering mask is not a measured historical hydrology layer.
[Cesium API reference](https://cesium.com/learn/cesiumjs/ref-doc/global.html),
[water-mask semantics](https://cesium.com/learn/cesiumjs/ref-doc/CesiumTerrainProvider.html#hasWaterMask).

Cesium's public agreement restricts offline output storage, with a separate
Clips route and third-party conditions. No organizational agreement or specific
extraction permission was established here. Prefer evaluating independently
distributed scientific rasters; their terms must be checked separately.
[Cesium agreement §§2.2–2.4](https://cesium.com/legal/terms-of-service/).

The current Copernicus GLO-30-F and GLO-90-F licences are custom free licences,
not CC0. They condition rights on acceptance and include attribution, modified-data
notices, liability/no-endorsement and downstream obligations. Acceptance mechanics
and obligations for derived feature artifacts need responsible human review;
no agreement was accepted by this audit. Provider documents are retained locally
for inspection, not uploaded as purportedly unrestricted data.
[Current free licences, pp. 19–24, Articles 1, 4, 6–9](https://dataspace.copernicus.eu/sites/default/files/media/files/2025-06/copernicus_contributing_mission_data_access_v2_cop_dem_licenses.pdf).
Separate general AWS site/service terms were not inspected; distribution-specific
due diligence remains incomplete.

## Next experiment, before any claim of benefit

1. Resolve the chosen distribution and reuse conditions; reconcile a complete
   effective tile manifest. With authorized access, inspect one current package
   per resolution, including actual mask contents, nodata, grid/datum and source
   times. Missing required layers remain refusals.
2. Specify footprint integration explicitly: point-post interpolation followed
   by area-weighted integration is a modeling choice, not a reported pixel mean.
   Preserve valid/excluded fractions and edited/fill classes. No centre-point
   fallback or invented recruitment footprint. GLO-90 is a sensitivity comparator,
   not an automatically acceptable replacement when GLO-30 is unavailable.
3. Test dateline/polar geometry, latitude-band transitions, adjacent-tile borders,
   unavailable masks/tiles, datum mismatch and ordering invariance on tiny synthetic
   rasters before processing real observations. Record checksums, support, units,
   acquisition intervals, extraction version and feature dependencies.
4. Freeze baseline, added terrain family, missingness-only and spatially structured
   negative-control comparisons. Keep outer folds/populations/coverage unchanged;
   fit transformations and select features inside training partitions. Then test
   incremental benefit beyond available genomic structure. Report failed layers,
   calibration, rare/regional strata and acquisition costs, not only mean error.

## Inspection limits

The bounded audit read the handbook, validation report, current free licences,
mission annex, distributor documents, catalogue samples and delivery workbook.
Root separately read the full handbook and both free licences, visually checked
their relevant grid/product/terms pages, and checked current CDSE/AWS pages.
Workbook snapshot counts, global catalogue completeness and every captured asset
header have not been independently rechecked by root; no numerical claims from
those counts or the validation report are used as acceptance evidence here.

App source inspection was against commit `a071a7b134d368ff4f2359272cb03f8c770f2100`,
`website/src/atlas/earth-style-catalog.ts` and the terrain/provider blocks in
`website/src/atlas/scene/context-controller.ts`. It did not access tokens or
terrain services. No accounts, raster data, agreements, genetic observations,
coordinates, production contracts or serving paths changed. This note remains
an automated research proposal, not a reviewed P1 evidence row or source admission.

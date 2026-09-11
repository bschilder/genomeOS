# CHELSA V2.1: bounded complete-file decoding checks

Status: `automated_proposal` / `pending`, September 10, 2026 America/New_York;
captures September 11, 01:34–01:38 UTC. Advances #189 WP3/WP7, Atlas design
§§4–9,12. Companion to the [climate qualification note](climate-covariate-qualification-2026-09-10.md).
The two current January files decode successfully. Precipitation time semantics,
land/coast support and climate-feature admission remain unresolved.

## Scientific contract

Objective: establish byte identity, native geometry, packing and validity for
exactly the current January 1981–2010 temperature and precipitation climatologies
before using them in genetic prediction. Acceptance evidence is complete bounded
acquisition/decompression, fixed point checks, independent raw-value/affine
calculations and explicit missing cases. Local diagnostics produce a retained
JSON report; an eventual immutable offline feature interface remains unimplemented.

The consumers are WP3 source qualification and separately supported WP7 research.
Nominal coordinates are format diagnostics, not qualified genetic sample sites,
land classifications or ancestral exposure. Changed/incomplete bytes, invalid
cells and unsupported temporal transformations refuse. Decoding does not establish
climate accuracy, allele-frequency skill or continuous ancient coverage.

## Exact assets and acquisition

Fresh [dataset-page](https://www.chelsa-climate.org/datasets/chelsa_climatologies)
and [catalogue](https://www.envidat.ch/api/3/action/package_show?id=chelsa-climatologies)
inspection found CC0 1.0 and the current V2.1 resource
`ee935f48-b3da-432d-961d-f815289e476f`. Its decoded viewer bucket/prefix identifies
these assets. The data terms are separate from the model code's GPLv3 terms.
The automated reuse record remains pending; no account or agreement was used.

| Asset | Complete bytes | ETag | Last-Modified UTC |
|---|---:|---|---|
| [January tas](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/tas/1981-2010/CHELSA_tas_01_1981-2010_V.2.1.tif) | 149,078,236 | `6ffa315be924d742db8cb084d8964d4d-14` | 2025-09-09 10:13:32 |
| [January pr](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_01_1981-2010_V.2.1.tif) | 346,942,826 | `3b404cfa9cb9a6d247f3e876d618c33f-33` | 2025-09-09 10:10:09 |

HEAD lengths fixed the combined 496,021,062-byte transfer (473.04 MiB), below
the predeclared 512 MiB cap. One full GET per asset sent identity encoding,
`If-Match` and `If-Unmodified-Since`; both returned HTTP 200 with unchanged
URL/ETag/Last-Modified/length, no range response and exactly the expected bytes.
Streams enforced 65,536-byte chunks, a 30-second socket timeout and 600-second
hard per-file deadline. No retries or partials remain. Deliberately incorrect
conditional-header rejection was not tested. Retained documentation/source
bodies totaled 502,693 bytes, below their separate 10 MiB cap.

Full SHA-256 values were computed during download, recomputed before decoding,
and independently matched when preserving the files locally:

```text
tas 7a5dd952882a19358a9e3c0efa9cbcb4ebf26d534f095a93a28a78da3a7c68b1
pr  1657fe39e8eafee5c29bd7f211e144b1cc8422bf8d51af7d22b5583b615ac642
```

These establish retained byte identity. The inspected catalogue supplied no
independent provider whole-file SHA-256; ETags are identifiers, not SHA-256.
This follow-up verifies only the current delivery, not legacy pixel equivalence.

## Native geometry, packing and complete decompression

Both files are little-endian UInt16 GeoTIFFs, 43,200 × 20,880, EPSG:4326,
PixelIsArea, LZW, 512 × 512 tiles, scale 0.1, offset 0 and nodata 65535.
Dataset `variable_unit` is `K` for tas and `kg m-2 month-1` for pr; Rasterio's
band-unit field is null for both. Raw reads remain packed and require one
explicit scale/offset application.

Independent TIFF-directory parsing found eight IFDs per file, with every
compressed tile extent inside its retained body. Rasterio decoded all 3,485
base tiles and all 1,238 overview tiles per file, one block at a time.
At every decoded base/overview pixel its **nodata-derived mask** agreed with
`raw != 65535`. This is decompression and storage/mask consistency, not a
separate quality mask, land/ocean validation or COG-compliance result.

Use these exact per-file affine declarations:

```text
spacing = 0.0083333333 degrees
x0 = -180.00013888885002
y0_tas = 83.99986041515
y0_pr  = 83.99986041515001
column = floor((longitude - x0) / spacing)
row = floor((y0 - latitude) / spacing)
center_longitude = x0 + (column + 0.5) * spacing
center_latitude = y0 - (row + 0.5) * spacing
valid = within_grid AND mask != 0 AND raw != 65535
value = raw * 0.1 + 0 ONLY IF valid; otherwise unavailable
```

The north boundary is slightly below 84°N; east is 179.99985967115003°;
west/south extend slightly past -180°/-90°. Do not snap to an ideal grid,
wrap or clamp points. The tiny difference between y origins is retained;
byte-identical geometry is not claimed.

## Fixed point checks and independent readers

Six nominal coordinates were fixed before pixel inspection. Centers are shown
to nine decimals; retained JSON preserves the full returned precision. Every
in-bounds row has native mask 255. Precipitation values below use only the
file's declared unit, without a calendar or flux conversion.

| Nominal latitude, longitude | Row, column | Actual center latitude, longitude | tas packed → K | pr packed → declared unit |
|---|---|---|---|---|
| 40.75, -73.98 | 5189, 12722 | 40.754027255, -73.979305980 | 2726 → 272.6 | 845 → 84.5 |
| 0, 0 | 10079, 21600 | 0.004027418, 0.004027058 | 2994 → 299.4 | 1113 → 111.3 |
| -24.5, -69.5 | 13019, 13260 | -24.495972484, -69.495972664 | 2921 → 292.1 | 13 → 1.3 |
| 27.98, 86.92 | 6722, 32030 | 27.979027306, 86.920693377 | 2350 → 235.0 | 355 → 35.5 |
| 83.5, -40 | 59, 16800 | 83.504027084, -39.995972782 | 2469 → 246.9 | 192 → 19.2 |
| 84.1, 0 | -13, 21600 | Out of bounds; no pixel read | unavailable | unavailable |

Pillow-bundled LibTIFF 4.7.1 independently decoded the relevant tiles and
reproduced all ten packed values. Pillow's Python TIFF-directory reader plus
manual arithmetic reproduced Rasterio's indices/centers within 1e-12 degrees;
Decimal arithmetic independently checked scaling. A separate reviewer confirmed
that Rasterio/GDAL and Pillow load distinct LibTIFF binaries, with distinct
install names and hashes, and recalculated the saved arithmetic.

No fixed point was a valid zero or source nodata cell: both real-cell checks
were **unmet in that fixed-point audit**. Synthetic zero/sentinel guard examples
test software behavior only; they do not replace those observations. No replacement
coordinates were searched for that audit. Validity near nominal (0,0) illustrates why a nodata mask
cannot serve as a land mask. Land, ocean and coastal support remain unqualified.

## Subsequent source-zero and nodata control

A separate control on September 11, 2026 (UTC), froze a deterministic search rule
before pixel access: base TIFF blocks in block-row/block-column order, then cells
in local row/column order, retaining at most the first valid raw zero and first
raw `65535` per raster. This new source-inspection control does not replace or
expand the earlier six-point acceptance set. It used the same unchanged files,
checked by size and SHA-256 before and after execution, with no downloads.

| Asset | Base blocks inspected | Result |
|---|---:|---|
| `tas` | 3,485 of 3,485 | Neither raw `0` nor `65535` occurred; no real temperature zero/sentinel cell was available to check independently. |
| `pr` | 3,434 of 3,485 | Valid raw zero at row 7,428, column 24,063; raw `65535` at row 20,877, column 16,950. |

The precipitation zero has native mask 255 and decodes to `0.0` under the stored
packing. The sentinel has mask 0 and remains unavailable, rather than being scaled
into a climate value. Pillow-bundled LibTIFF independently reproduced both packed
values; Pillow's TIFF-directory tags and manual affine arithmetic reproduced both
pixel centers within 1e-12 degrees. The edge tile was clipped to the actual raster
height for selection, so the sentinel is an in-image source cell. Both paths
decoded individual tiles without allocating a full raster array.

The frozen rule SHA-256 is
`1892e32f9a6158f41882fafc1b1e30f0dc8cc448d2ba2f6a152f295b82ddd35c`;
the result SHA-256 is
`860ae54b8f83fa670ce8ca38b03f3f2341d053cd9c1223f31affbf5628943d6a`.
The same Python/NumPy/Rasterio/GDAL/Pillow versions listed below were used, with
LibTIFF 4.7.1 on the recorded little-endian runtime. An independent automated
review approved the bounded results and checked the distinct decoder binaries,
selection arithmetic, edge handling, hashes and missing-value refusal. Portable
native-buffer byte-order behavior beyond this runtime is not qualified. Local code
order and timestamps support the prospective sequence; they are not a tamper-evident
preregistration. Scripts, results and review evidence remain preserved locally.

This resolves the two precipitation packed-value/missingness controls. It does not
establish land support, precipitation temporal semantics, climate accuracy or
suitability as a genetic feature. Evidence remains `automated_proposal` / `pending`,
with P1, publication and model eligibility false.

## Precipitation semantics remain ambiguous

The pr asset retains `cf_standard_name=precipitation_flux`, whose canonical
units are `kg m-2 s-1`, alongside its monthly unit. The provider descriptions
support a monthly-amount interpretation, but do not resolve the exact numerical
aggregation of these files. [CF Standard Name Table v81](https://cfconventions.org/Data/cf-standard-names/81/build/cf-standard-name-table.html#precipitation_flux).
The earlier note inspected the technical specification; this audit's fresh PDF
request returned 403, so that inspection was not independently repeated.

The provider-linked V2.1 code resolved to commit
`e785897c1b9443d7e0f9aa794856b27a213d1b34`. Four captured source bodies matched
GitLab's content hashes. The generic converter writes caller-supplied units and
standard names separately; the inspected Canary converter describes a different
product. Neither establishes the generator or numerical provenance of these
2025-dated global raster objects. [Source revision](https://gitlabext.wsl.ch/karger/chelsa_v2/-/tree/e785897c1b9443d7e0f9aa794856b27a213d1b34).

Both rasters declare 1981–2010 climatologies, ERA5 forcing and model output;
filenames identify January. The precipitation metadata names GPCC Full Data
Monthly Product v2018 bias correction. They do not supply calendar, explicit
month bounds, cell methods, completeness or averaging denominators. No assumed
seconds/month conversion, legacy Celsius offset, annual sum or annual temperature
summary is admitted. Independent reader agreement cannot resolve those semantics.

## Verification and remaining work

The audit used Python 3.12.13, Rasterio 1.5.1/GDAL 3.12.4, NumPy 2.4.6 and
Pillow 12.3.0, without installing packages. Complete decoding finished with empty
stderr. Retained scripts, response metadata, source bodies, file hashes and JSON
results were preserved locally; they are one-off diagnostics, not a packaged
public extraction pipeline. An independent automated factual/scientific review
approved the bounded claims and requested the precise CF-version citation used
above. Neither independent reader paths nor automated review make this human-
verified source evidence.

The remaining boundary includes the unavailable temperature zero/sentinel controls,
land/coast support, exact temporal semantics, the other 22 current monthly assets, legacy
equivalence, full COG validation and climate accuracy/uncertainty. Feature use
still requires qualified genetic footprints and unchanged-population ablations.
No raster, genetic observations, model, production schema, denominator, serving
path or scientific map is changed by this documentation follow-up.

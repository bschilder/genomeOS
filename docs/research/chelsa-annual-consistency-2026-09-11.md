# CHELSA V2.1 annual precipitation: retained storage-consistency evidence

Status: `automated_proposal` / `pending`, September 11, 2026. Advances #189
WP3/WP7 and Atlas design §§4–9,12.

The exact stored-integer formula
`annual_raw == floor(sum(monthly_raw) / 10)` is false at 822,830 of
902,015,154 comparable cells (0.0912213%). The 1981–2010 CHELSA V2.1 annual
file has no stored SCALE or OFFSET declaration, so this result does not establish
its physical scale, the generating algorithm, climate accuracy, or genetic
predictive value. GDAL's returned scale 1 and offset 0 are unqualified reader
defaults rather than source packing evidence.

![Native-block exact-formula failures and signed raw-integer residuals](https://raw.githubusercontent.com/bschilder/genomeOS/main/docs/figures/chelsa_annual_consistency.png)

The public [aggregate JSON](chelsa-annual-consistency-2026-09-11.json) contains
the complete signed histogram, all 3,485 native-block summaries, thirteen source
identities, and the bounded provenance needed by the owned
[plotting CLI](../../scripts/plot_chelsa_annual_consistency.py). It reproduces
this figure without raster or network access. It does not contain raster pixels
and cannot independently replicate the full-raster audit by itself.

## Scientific contract

The objective was to test the provider-documented relationship between twelve
monthly precipitation amounts and annual bio12 for one same-period, same-release
delivery. Acceptance required exact source identities, unchanged native geometry,
explicit missingness, two-reader selected-cell checks, and a complete integer
residual census without a result-chosen tolerance.

The delivered component is an immutable research aggregate plus an offline figure
CLI. It is climate storage-consistency evidence for WP3 and a prerequisite for
separately supported WP7 research. No production schema, P0/P1 observation,
inferred surface, fitter, API, serving artifact, model input, or genetic result is
changed or admitted.

Every compared cell had to be valid under all thirteen native masks and raw
nodata guards. Missing cells were excluded and counted; they were not imputed.
The audit did not resample, infer a land mask, area-weight cells, or treat nominal
diagnostic coordinates as genetic sampling locations. Unsupported packing,
lineage, climate calibration, population-footprint support, or held-out genetic
gain remains a refusal.

## Exact source delivery

The current [CHELSA climatology page](https://www.chelsa-climate.org/datasets/chelsa_climatologies)
describes V2.1 monthly precipitation as an amount in `kg m-2 month-1`; the
[bioclim page](https://www.chelsa-climate.org/datasets/chelsa_bioclim) describes
bio12 as the sum of monthly totals and the retained annual file labels its unit
`kg m-2 year-1`. These are current source-intended meanings. They do not resolve
the absent annual packing declaration or prove the numerical producer of these
particular raster bodies. CHELSA data terms were checked as CC0 1.0; the authors'
code is separately GPLv3.

All assets are one-band UInt16, nodata 65535, EPSG:4326, 43,200 × 20,880,
PixelIsArea, and tiled 512 × 512. Their exact affine is
`[0.0083333333, 0, -180.00013888885002, 0, -0.0083333333, 83.99986041515001]`.
The twelve monthly files explicitly store binary64 scale 0.1 and offset 0. The
rational division by 10 in the tested raw-integer formula is a distinct arithmetic
statement. Bio12 stores neither SCALE nor OFFSET; its physical scale remains
unqualified.

| Role | Exact provider object | Bytes | SHA-256 |
|---|---|---:|---|
| pr_01 | [CHELSA_pr_01_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_01_1981-2010_V.2.1.tif) | 346,942,826 | `1657fe39e8eafee5c29bd7f211e144b1cc8422bf8d51af7d22b5583b615ac642` |
| pr_02 | [CHELSA_pr_02_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_02_1981-2010_V.2.1.tif) | 339,601,774 | `3a3006c0d2128b75638cd515f914e1edd2d03b369503e5c96e499631974bd9cc` |
| pr_03 | [CHELSA_pr_03_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_03_1981-2010_V.2.1.tif) | 354,216,394 | `9f43a227c3f4a68b812cf717d0d6290682e4bd5b0403fa5807bffb7c4692ea26` |
| pr_04 | [CHELSA_pr_04_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_04_1981-2010_V.2.1.tif) | 355,984,276 | `d5709f61daed306428af6abf9e3f6e9c263c45e1d1d113ab9a00b36fef84c53e` |
| pr_05 | [CHELSA_pr_05_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_05_1981-2010_V.2.1.tif) | 365,712,838 | `37a0fd48d53cfde0d2a76daea650d417fc2a575aeb415469939987b93f4282f5` |
| pr_06 | [CHELSA_pr_06_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_06_1981-2010_V.2.1.tif) | 372,652,111 | `5f2fd40e8e03b36faaf8c7e8dca38186a75eb2d48bec6e6de3ed05e01866cc0f` |
| pr_07 | [CHELSA_pr_07_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_07_1981-2010_V.2.1.tif) | 384,971,425 | `7cbc319f68db465d7f75409d8f583b0c4c2385c2fc7ccd8deb772884b5ee783f` |
| pr_08 | [CHELSA_pr_08_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_08_1981-2010_V.2.1.tif) | 384,394,279 | `c0af8e4b7d1ecc122a245428cc794c6404135bc03133f54bbd4d834ae474dec7` |
| pr_09 | [CHELSA_pr_09_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_09_1981-2010_V.2.1.tif) | 375,349,612 | `aa97ca7737c9471d9ecb738b0f4ce7be9760f578f41283502e1204f760088bb2` |
| pr_10 | [CHELSA_pr_10_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_10_1981-2010_V.2.1.tif) | 370,435,995 | `7858ab0e4d2979b0582fef9f37e1ad7c193eabf8f80dd0bec83cb184bd91ba7f` |
| pr_11 | [CHELSA_pr_11_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_11_1981-2010_V.2.1.tif) | 354,232,642 | `5ea59a5603fdb9b93cb220c3055fec7c1c22fbfdc6c8ce7d9e6c36b7a0d805ac` |
| pr_12 | [CHELSA_pr_12_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_12_1981-2010_V.2.1.tif) | 349,117,178 | `a004e17d99eed0523515a33db6a219124b22836c39344fc08e2b5b2e6833dc3c` |
| bio12 | [CHELSA_bio12_1981-2010_V.2.1.tif](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/bioclim/bio12/1981-2010/CHELSA_bio12_1981-2010_V.2.1.tif) | 349,254,899 | `918441cac0b633227d2a6dcc0ddcfb5efd40e015a426951a01cfbf9ba2f7a22c` |

The provider-linked [source revision](https://gitlabext.wsl.ch/karger/chelsa_v2/-/tree/e785897c1b9443d7e0f9aa794856b27a213d1b34)
was committed September 10, 2026, while the retained objects have September 2025
Last-Modified dates (bio12 September 7; monthly files September 9). That mismatch
does not prove different code, but it prevents attributing these objects to that
revision. The inspected revision documents a daily producer path. It does not
establish the unknown global monthly or climatology generator for the retained
files.

## Preserved selection and failure chronology

The original six nominal diagnostics were fixed at `(40.75, -73.98)`, `(0, 0)`,
`(-24.5, -69.5)`, `(27.98, 86.92)`, `(83.5, -40)`, and `(84.1, 0)` in
latitude/longitude order. The two previously frozen January controls were
row/column `(7428, 24063)` for a raw zero and `(20877, 16950)` for nodata. No
coordinate was replaced after pixels were inspected.

Attempt 1 failed before an annual comparison because its independent parser
supported classic little-endian TIFF but refused annual little-endian BigTIFF.
Attempt 2 preserved all twelve monthly results, then refused bio12 because the
required explicit annual SCALE/OFFSET was absent. Both outcomes remain failures.

Two conditional annual packing hypotheses were then frozen: GDAL's identity
defaults (scale 1, offset 0), and scale 0.1/offset 0 from an older technical
specification whose applicability to this body is unverified. Monthly values had
already been seen, but no annual pixel or annual-sum comparison had been read.
Under the identity-default hypothesis, six usable fixed cells produced annual
integers just below their monthly sums; the alternative 0.1 hypothesis was far
away. Neither comparison qualified annual physical packing.

The whole-grid formula was selected after those six fixed cells matched it. It is
therefore a post-hoc descriptive follow-up rather than an independent discovery
test or preregistered genetic benchmark. The subsequent worst-cell check likewise
selected the first maximum absolute residual from the completed grid result and
then decoded it a second way.

## Whole-grid result and figure interpretation

The audit read all 3,485 native blocks in each of thirteen files. Twelve UInt16
monthly arrays were summed as UInt32; the comparison and signed residual used
integer arithmetic with no floating tolerance. A cell was comparable only where
all thirteen raw values differed from 65535 and every native mask was nonzero.

| Outcome | Cells |
|---|---:|
| Entire retained grid | 902,016,000 |
| Comparable | 902,015,154 |
| Excluded | 846 |
| Exact floor formula holds | 901,192,324 |
| Exact floor formula fails | 822,830 |

The signed residual `10 * annual_raw - sum(monthly_raw)` spans −10 through 0.
Every exact-floor failure is −10; the other 901,192,324 cells have residuals from
−9 through 0. The sum of absolute raw residuals is 4,067,620,160. No residual was
below −20 or above 20. All thirteen assets individually have 902,015,154 native
valid cells, equal to the common comparable intersection.

The selected first maximum-residual cell is row 383, column 1, centered at
longitude −179.98763888890002 and latitude 80.80402709460002. Monthly raw
integers `[74, 64, 60, 70, 100, 153, 234, 286, 201, 134, 78, 66]` sum to 1,520;
the annual raw integer is 151, giving residual −10. Rasterio/GDAL and the distinct
Pillow-bundled LibTIFF reader reproduced all thirteen selected values and masks.
The second reader checked selected cells only, not the full grid.

The map shows exact-formula failure fractions within native blocks. Its final
edge blocks use the source affine and their true clipped dimensions. The color
ramp increases from low to high failure fraction; the maximum block fraction is
0.7369995%. The spatial pattern is not a precipitation amount, land map, fitted
surface, or biological result. Native masks include both land and ocean, and no
cell is area-weighted. The histogram reports every comparable cell; the 846
excluded source cells remain visible in the figure header.

## Reproduction and retained provenance

From the repository root, with a new output path and the locked figure
dependencies available:

```sh
python scripts/plot_chelsa_annual_consistency.py \
  --evidence docs/research/chelsa-annual-consistency-2026-09-11.json \
  --out chelsa-annual-consistency.png
```

The CLI performs source-role, eligibility, grid tiling, count, histogram,
failure, residual-extrema, and selected-cell reconciliation before opening the
output. It refuses to overwrite an existing file and makes no network or raster
read.

The aggregate SHA-256 is
`a86a8bc2876fb97bda895813a5aaf2429c101a5a7d9cd5f0a773e8d14f903eb9`;
the plotting script SHA-256 is
`28fcbda5c1499e440f62ae43fce92267e491174ddf0d21f0d0c6ee6d73695ac1`;
the committed PNG SHA-256 is
`c1885e8b0857b6569d5cf6e5eab6c46c8eabd6519424e1f7c3ea3a638af2ab9b`.
These new public-artifact hashes are separate from the retained source-record
hashes below:

| Original retained record | SHA-256 |
|---|---|
| `acquisition-selection.json` | `d229faf20c005c0f6157ea21c1457f2bf3dd04b6ef60399a96d88948d5638f36` |
| `headers-before-pixels.json` | `a6bf9d694f5fd2b46326af5b6c37edf590bc5d33836f1ec186f50962fb5d8b35` |
| `attempt-3/fixed-cell-results.json` | `73b8b3481526261c0cd4ef8a39b06373f0f30ae6c9d02c9fffb04b2c2d082a7a` |
| `packing-hypotheses.json` | `07621afbcb6e9722fbac8d95440ca8c18c4d56b45067e7a7b4aad6d9067fe8d5` |
| `whole-grid-plan.json` | `dabc9f3ca1b894c6ff337da597f5b9680e5187b14927385102813bfd63669e53` |
| `check_whole_grid.py` | `c669f8635f15929a5b8849929d2c398b4f61a369134e551344d2bee12f9a672e` |
| `whole-grid-1/results.json` | `80a3428f72159ed842fac661f8fc9e88b915951fce432245c36cfafd6d8d11ca` |
| `worst-cell-independent-check.json` | `e25b30acf22b987e228584101a9865313227e839838726d5e83c53d3975d0b97` |
| `plot_annual_consistency.py` | `b92abd40542e9973aad9c472d5b4f87258514057f807b2b4f76b2f096e27c941` |
| `figure-1/receipt.json` | `bcbba7668de7b617ff5c4acfeba1bc3e8f75628f809d44c2e6b16846d0fb61e6` |
| Annual audit `report.md` | `bbc0932c5e9f4b8328c1f0055deee1029010c22478286faae05d14f42696e785` |
| Daily source-trace `report.md` | `ba261ebe97d01253ef5cdf08bb5e8fbee098ac9856b9eaf580e748a09b293a41` |

The original whole-grid plan/result/script identities are therefore
`dabc9f3c…e53`, `80a3428f…1ca`, and `c669f863…672e`. The retained whole-grid
runtime was Python 3.12.13, NumPy 2.4.6, Rasterio 1.5.1, and GDAL 3.12.4.
Selected checks also used Pillow 12.3.0 and LibTIFF 4.7.1; the separate LibTIFF
binary SHA-256 is
`e8988717b7470394a47d5ccd343130796b24ee70b6d885d3818e0e0b53238be1`.

## Remaining gates

Source qualification still needs the exact bio12 packing and generating lineage,
native land/coast support, climate accuracy and uncertainty, and population-
footprint support. A climate feature remains ineligible until a separately frozen,
paired held-out genetic comparison shows unchanged-population gain. This result
does not authorize source admission, model use, publication, or a claim about
genetic effects. It remains automated evidence awaiting human review.

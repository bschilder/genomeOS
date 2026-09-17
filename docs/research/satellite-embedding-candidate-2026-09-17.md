# Satellite Embedding candidate record — 2026-09-17

**Scope:** issue [#290](https://github.com/bschilder/genomeOS/issues/290), global-modeling WP3,
Atlas design §7. This note records a candidate source and its terms. It does not report a raster
extraction, an allele-frequency model input, predictive improvement, or benchmark admission.

## Scientific contract

The candidate is tested only for incremental, geographically transferable information after the
strongest eligible genomic-structure baseline. The measurable output of this slice is a strict,
versioned metadata record and an offline inspection boundary. Later extraction must retain exact
per-image identity and produce a content-addressed receipt. Downstream consumers are fold-local
WP3 feature pipelines; the serving path has no Earth Engine dependency.

Satellite Embedding is an opaque recent-surface representation. It is not historical ancestry,
migration, malaria exposure, or fine-scale genetic evidence. Its nominal 10 m pixels do not imply
10 m validated allele-frequency resolution. The 64 axes form one vector and are not individually
interpretable.

## Verified catalog facts

The official Earth Engine catalog was inspected on 2026-09-17:

- asset: `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`;
- publisher: Google Earth Engine and Google DeepMind;
- `DATASET_VERSION=1.1` for current layers and AlphaEarth Foundations model v2.1;
- annual support from 2017 through 2024, expressed as the half-open interval
  `[2017-01-01, 2025-01-01)`;
- 64 dimensionless bands `A00` through `A63`, nominally 10 m, with values in `[-1, 1]` and
  unit-length vector semantics;
- per-image `DATASET_VERSION`, `MODEL_VERSION`, `PROCESSING_SOFTWARE_VERSION`, and `UTM_ZONE`
  properties, plus temporal bounds;
- global terrestrial and shallow-water coverage, with limited polar coverage and remaining swath
  or data-availability artifacts;
- CC BY 4.0 with the required attribution retained verbatim in the registry.

The catalog does not publish one collection-wide processing-software value or one empirical scale
measurement for a selected export. Those values remain absent. A later receipt must read them from
the exact images used rather than copy a plausible value from this note.

Sources:

- [Earth Engine Satellite Embedding catalog](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL)
- [CC BY 4.0 deed and legal-code link](https://creativecommons.org/licenses/by/4.0/)
- [WP3 source-neutral qualification contract](https://github.com/bschilder/genomeOS/issues/290)

## Reproducible inspection

The canonical registry is
`genomeos/covariates/earth_engine_assets.json`, SHA-256
`2d3b44f7a49f56c7402ce30c20996b2f780a0c53e6dfe07e390b81fde80dc121`.

```bash
PYTHONPATH=. python scripts/inspect_covariate_asset.py --list
PYTHONPATH=. python scripts/inspect_covariate_asset.py \
  --asset-key google_satellite_embedding_v1_annual
```

Both commands are offline and validate the complete registry before emitting deterministic JSON.
The registry is also included in the built wheel; `uv build --wheel` copied it to
`genomeos/covariates/earth_engine_assets.json` inside the package.

## Remaining admission evidence

The next slice must select one year using explicit observation-time semantics; inspect exact image
properties; perform a vectorized footprint reduction over reviewed supports; and retain export,
code, input, and output hashes in an immutable receipt. It must measure empirical scale and
missingness rather than inheriting the 10 m catalog value. Only then may a frozen comparison test
the genomic baseline, coordinates, the 64-dimensional family, missingness, a structured negative
control, and simpler interpretable environmental sources under unchanged buffered splits.

No MAP-published asset is admitted by this record. Such an asset still needs its own mechanism,
time interpretation, simpler comparator, terms record, and source-overlap audit.

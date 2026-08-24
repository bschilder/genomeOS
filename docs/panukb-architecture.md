# Pan-UKB architecture

## Decision

GenomeOS uses a hybrid serving model:

1. PostgreSQL stores releases, assets, phenotypes, ancestry-specific analysis
   metadata, provenance, and selected association indexes.
2. Source BGZF files and Hail matrices remain in Pan-UKB public storage.
3. Genomic-region requests use the source Tabix indexes and HTTP range reads.
4. Full cross-phenotype computations run asynchronously near the Hail data and
   publish compact derived results, never the full matrix, to PostgreSQL.

This avoids flattening roughly 7,228 phenotypes by 29 million variants into
hundreds of billions of database rows.

## Source semantics

The native phenotype identity is the five-part key:

```text
trait_type + phenocode + pheno_sex + coding + modifier
```

Source coordinates are GRCh37. `alt` is the effect allele and is not
necessarily the minor allele. Any GRCh38 representation is a versioned mapping;
it never overwrites the source observation.

The labels AFR, AMR, CSA, EAS, EUR, and MID are Pan-UKB genetic-analysis
groupings. They are not interchangeable with race, ethnicity, nationality, or
geography.

## P-values

Pan-UKB documentation currently contains conflicting statements about whether
some release files contain `ln(p)` or `-log10(p)`. Importers therefore infer
encoding only from unambiguous column names, accept an explicit operator
override, preserve the encoded value, and store canonical `-log10(p)`. Generic
`pval_*` columns fail closed without an explicit encoding.

## Data layers

### PostgreSQL

- `data_sources`, `source_releases`, `source_assets`
- `phenotypes`, `phenotype_populations`
- `variants`
- `associations`
- source row number and asset ID on every indexed observation

### External object storage

- phenotype summary-statistics BGZF and TBI files
- Hail MatrixTables and LD matrices
- immutable snapshots and derived Parquet artifacts when needed

## Query paths

| Query | Execution path |
|---|---|
| Search/list phenotypes | PostgreSQL |
| Phenotype metadata and QC | PostgreSQL |
| Top phenotype associations | PostgreSQL selective index |
| Variant across indexed phenotypes | PostgreSQL selective index |
| Phenotype plus genomic region | Source BGZF/TBI through Tabix |
| Full cross-phenotype analysis | Asynchronous Hail job |

Every list endpoint is bounded. Full matrix exports are not REST operations.

## Ontologies

Source phenotypes remain authoritative. EFO/MONDO/HPO mappings will be separate,
versioned assertions with relationship type, method, confidence, and review
state. Text similarity never silently merges phenotypes.

## MCP

MCP is a read-only adapter over this API, not a database or ingestion layer.
Future tools should expose bounded searches, ancestry comparisons, QC
explanations, and provenance. Arbitrary SQL and arbitrary Hail execution are
explicitly out of scope.

## Production topology

```text
Pan-UKB GCS/AWS ── Tabix range reads ──┐
                                       ├─ Cloud Run API ─ clients/MCP
Cloud SQL PostgreSQL ──────────────────┘

Pan-UKB Hail ─ Dataproc/Hail jobs ─ GCS derived artifacts ─ selective index
```

## Implementation milestones

1. Manifest ingestion and phenotype catalog.
2. Strict association parser with explicit p-value semantics.
3. Selective significant-association indexes.
4. Tabix region adapter with row limits and feature flag.
5. GCP deployment using Cloud Run and Cloud SQL.
6. Async Hail jobs and ontology mappings.
7. Open Targets reconciliation as a derived source.

# Trait evidence and geographic comparison — implementation contract

Approved by the user on 2026-09-14. Tracks #282. Implements Atlas design §§5, 6,
10–13 and extends the Cesium design §10; does not change scientific publication gates.

## Claim and evidence

Users can inspect source-indexed trait–variant evidence with its exact identity and
coverage, and visually juxtapose independently published maps. Neither operation
establishes trait prevalence, causation, genetic correlation, or gene pleiotropy.
Acceptance requires strict identity/provenance checks, explicit missingness, a
reproducible local source audit, and separate real-data maps with synchronized cameras.
No production path supplies fixture data or substitutes a dataset, variant, or method.

## Module boundaries

- `genomeos/evidence/schema.py`: frozen typed read contracts; no I/O.
- `genomeos/evidence/policy.py`: pure provenance/eligibility checks; no SQL or HTTP.
- `genomeos/evidence/query.py`: bounded SQL adapter and source inventory; no science.
- `genomeos/evidence/api.py`: thin routes over query functions.
- `scripts/audit_trait_evidence.py`: explicitly configured, read-only database audit.
- `genomeos/static/evidence.html`: source-index browser, no scientific computation.
- `website/src/atlas/comparison.ts`: camera synchronization and URL contracts.
- `website/src/components/atlas/AtlasComparison.tsx`: comparison composition.
- Existing `AtlasExplorer` and provider: each panel's independently versioned data,
  measurement, legend, observations, surface, and mask.

Do not create a parallel fitting stack or generic adapter registry. Dependencies
point into contracts and pure functions. Configuration belongs at composition boundaries.

## Delivery and tests

1. Evidence contracts and read adapter: exact assembly-qualified variant selection;
   release-specific native trait keys; unknown QC preserved; no effect units guessed;
   no counts called genome-wide test counts. Refuse non-Pan-UKB source locations and
   missing source checksum. Test unknown IDs, pagination, malformed stored values,
   source/release mismatches, nonfinite statistics and empty databases.
2. Source audit: no database initialization or ingestion; counts refer only to the
   inspected database. Include per-asset counts and missing provenance. No URI with
   embedded credentials may reach public output. Full-input availability and scientific
   qualification remain unknown unless actually audited, never inferred from an index.
3. Evidence browser: bounded exact variant or trait-ID lookup, provenance and explicit
   refusals; no seed, sample result, guessed phenotype, or synthetic map link.
4. Map juxtaposition: select two catalog identities explicitly. URL stores both panel
   states; move one camera without changing the other panel's scientific layers. Each
   panel reports its own scale. Failed or unavailable selections cannot load a different
   entity. No subtraction, combined color, geographic correlation, or automatic resampling.
5. Cross-trait analysis: BLOCKED pending qualified full summary statistics, matching LD,
   overlap protocol, frozen test families and independent benchmark acceptance. Do not
   implement placeholder numbers or switch methods on failure.
6. Gene pleiotropy: BLOCKED pending trait distinctness review, gene-attribution evidence,
   qualified signal analysis and independent validation. A locus/nearby-gene lookup is
   not a substitute. #116 remains the composite-phenotype clinical decision.

## Actual input audit at implementation start

The inspected local Pan-UKB database contains zero associations, zero phenotypes, and
zero registered releases. This is local availability, not a claim about the deployed
service or public Pan-UKB. The browser must report unavailable evidence. The public
Atlas catalog contains real maps and can support visual juxtaposition. It cannot supply
GWAS effects, overlap metadata, LD, or validated gene attribution by implication.

## Scientific validation still required

For genetic correlation: predeclare population/trait eligibility, full-genome inclusion,
LD-score compatibility, sample-overlap handling, diagnostics and multiplicity correction.
For colocalization: predeclare locus/allele alignment, variant coverage, LD compatibility,
multi-signal method, priors and sensitivity analysis. Reproduce independent published
benchmarks and adversarial simulations before accepting either protocol.

Gene dossiers must distinguish repeated phenotype definitions, shared versus distinct
signals, ambiguous gene attribution and mediation. Do not claim direct pleiotropy from
multiple significant rows. Genotype-derived disease maps require a separately validated
inheritance/penetrance/denominator contract and existing golden publication gates.

Small synthetic fixtures are isolated software tests only. Real-data demonstrations
must use committed, provenance-bearing inputs. Full task completion is blocked until
steps 5–6 have actual evidence and validation; completing steps 1–4 does not close #282.

## Running this implementation

- `/evidence` on the existing FastAPI service: exact variant or registered phenotype-ID
  browser, with explicit source refusals. It never seeds the database.
- `GET /v1/evidence/associations`: exactly one of `variant` or `phenotype_id`,
  `limit` 1–200 and `offset`. Pagination counts examined indexed rows, including refusals.
- `GET /v1/evidence/audit`: bounded asset inventory with total counts and limitations.
- `python scripts/audit_trait_evidence.py --sqlite genomeos.db --out audit.json`:
  explicit SQLite read-only connection, exclusive output creation. Audit asset pages
  contain at most 200 entries; use `--offset` for additional pages. The snapshot under
  `docs/audits/2026-09-15-trait-evidence-local.json` describes only this local database.
- `/app/compare/` on the website: explicitly select both real published maps. Artifact
  queries and versions round-trip in the URL. One shared provider loads the complete
  selected artifacts before renderer startup; no cell subsampling or fixture replacement.
- `python scripts/plot_trait_comparison.py --base-url http://127.0.0.1:4322
  --out docs/figures/trait-map-comparison.png` verifies/captures the real HbS/G6PD maps.

The association importer records the SHA-256 of the actual input bytes and refuses
changed bytes for an already checksummed source asset in the same release. This does
not certify that a supplied source URI corresponds to those bytes.

Source checksums are required for serving indexed association rows. A registered checksum
and source pointer establish traceability only, not independent verification; neither is
claimed to authorize inference. Source content verification, phenotype effect scales,
counted-allele joins, ontology assertions and scientific qualification remain outstanding.
An existing index without those checksum records yields explicit refusals, never a presumed
verified record. No automatically harvested association is promoted to a scientific claim.

The scientific environment failure (`numpy.row_stack` removed while the installed fitting
stack references it) is separately tracked as #285. No monkeypatch or substitute sampler
is introduced by this implementation.

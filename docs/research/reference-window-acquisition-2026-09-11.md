# Reference-window acquisition and count preparation

This completes the bounded data-preparation deliverable for #255 and advances #189 WP0/WP1.
The reviewed offline pipeline acquired the exact generation-bound byte ranges for the 66 windows
frozen by #254, preserved the original VCF records, and prepared four development count tracks.
The row-level artifacts remain private and untracked; this note reports aggregate evidence only.

This result expands a reference-panel development benchmark. It does not establish present-day
resident geography, independent loci, model improvement, calibration, P1 eligibility, or
publication eligibility. No environmental covariate, MAP product, or fitted surface enters this
preparation.

## Frozen source and execution

The source is the original-call gnomAD v3.1.2 HGDP+1000 Genomes dense adjusted release: one
generation-pinned VCF/TBI pair for each autosome. The controller consumed the reviewed #254
manifest and byte plan without changing, replacing, or redrawing a window after data inspection.
The run was bound to implementation commit
`0e27e3fa9bfa94768b25b2a8e4d2b94c2f7b2fe0` and these input identities:

| Input | SHA-256 |
|---|---|
| Frozen window manifest | `d469f05d6ee96556d1e23ca9f95e1914d4364b1bc02f89fd6f88288e3110f0b7` |
| Window table | `048bfcba9b01c8f520940965039f926d5c43325c4a0b882c4ba7a755c360df71` |
| Reviewed index preflight | `8560c0b17c6c90595a0e44be9514e9880632f10960046d3ce5d82ee1fdabd081` |
| Pre-retrieval review receipt | `83d9115891e615be806aa74441b2b776281ce5d7251af632abe7aa53efb0d2e8` |

The controller invoked the two reviewed interfaces below with hash-qualified private inputs and
new output directories. Placeholder names hide local paths, not optional arguments.

```bash
PYTHONPATH=. .venv/bin/python scripts/acquire_reference_windows.py \
  --windows-dir WINDOWS_DIR --preflight-dir PREFLIGHT_DIR --review REVIEW_JSON \
  --metadata METADATA_TSV --outliers OUTLIERS_TXT \
  --cohort-exclusions EXCLUSIONS_JSON --technical-samples TECHNICAL_SAMPLES \
  --paper-samples PAPER_SAMPLES --dependency-audit DEPENDENCY_AUDIT \
  --bcftools BCFTOOLS --tabix TABIX --bgzip BGZIP --out NEW_ACQUISITION_DIR

PYTHONPATH=. .venv/bin/python scripts/prepare_reference_window_counts.py \
  --acquisition NEW_ACQUISITION_DIR --metadata METADATA_TSV \
  --outliers OUTLIERS_TXT --cohort-exclusions EXCLUSIONS_JSON \
  --technical-samples TECHNICAL_SAMPLES --paper-samples PAPER_SAMPLES \
  --dependency-audit DEPENDENCY_AUDIT --bcftools BCFTOOLS --out NEW_COUNTS_DIR
```

The execution used Python 3.12.13, bcftools/HTSlib/fill-tags 1.23.1, tabix/bgzip 1.23.1,
and Google Cloud SDK 574.0.0. The manifests retain executable hashes, the relevant Cloud SDK
storage-source hashes, and a 32-file imported-source hash map. The acquisition and preparation
manifest SHA-256 values are respectively
`14b61409f22971db48fb54e2588c033b32c539f2a13291ccba1df06a91a6a307` and
`78543a6f9745d82f637033eabb897a9b6afeb10800af1c241f0403cd6e6f5221`.

## Acquisition result

All 22 chromosome sources passed generation, index, header, sample-order, and retained-range
validation. The fixed byte plan requested 109 VCF ranges and received the exact requested number
of bytes, with no application retry or source fallback.

| Measure | Result |
|---|---:|
| Sources ready / planned | 22 / 22 |
| VCF ranges verified | 109 |
| Retained index bytes | 3,000,550 |
| VCF bytes requested and received | 2,348,475,924 |
| Total planned bytes including indexes | 2,351,476,474 |
| Windows with records | 65 |
| Explicit no-record windows | 1 (`chr16-s2`) |
| Refused windows | 0 |
| Original records / native records | 47,845 / 47,845 |

The acquisition manifest inventories 713 content files. Its three eligibility flags remain
false. The retained sparse files are verified collections of selected byte extents rather than
verified whole VCF objects; the manifest records that distinction explicitly.

## Prepared count tracks

Site selection retained 32,415 distinct PASS biallelic uppercase A/C/G/T SNPs. Both cohort stages
preserve all 80 literal population identities. The called track uses every complete diploid GT;
the quality track additionally applies the frozen GQ, DP, and heterozygote allele-balance rules.
An unavailable denominator remains an explicit `AN=0` row.

| Cohort stage | Track | Rows | Variants | Unavailable rows | AC sum | AN sum |
|---|---|---:|---:|---:|---:|---:|
| Technical QC, 4,117 samples | Called | 2,593,200 | 32,415 | 5,700 | 6,606,237 | 261,002,218 |
| Technical QC, 4,117 samples | Quality | 2,593,200 | 32,415 | 7,946 | 6,442,141 | 259,604,260 |
| Paper ancestry exclusion, 4,094 samples | Called | 2,593,200 | 32,415 | 5,771 | 6,569,887 | 259,549,352 |
| Paper ancestry exclusion, 4,094 samples | Quality | 2,593,200 | 32,415 | 8,043 | 6,406,844 | 258,157,846 |

All 132 stage/window receipts completed. Native bcftools cohort totals match all 32,415 variants
in each cohort stage, for 64,830 exact variant-level AC/AN matches. The preparation also retained
130 native count controls and 130 native token controls for the 65 nonempty windows. The four
tables have identical variant/population key sets, and the preparation manifest inventories 1,578
content files. Its eligibility flags also remain false.

The native total is an independent check of cohort-wide **called** AC/AN for each retained
variant. Population allocation, sequential quality exclusions, and quality-track counts are
validated by exact sample/token identity and an independent replay of the retained original and
native token streams; they are not a second independently implemented population-level quality
counter. This is the precise limit of the validation claim.

## Verification and audit

Before retrieval, an independent exact-source review passed the transport, source, cohort, count,
and #254 input invariants. After preparation, a separate aggregate real-evidence audit reran the
deep acquisition and preparation validators. They rehashed every inventoried artifact, replayed
original/native records and count construction, checked all 66 windows, and confirmed the
4,117/4,094 sample cohorts and 80 population labels. Both terminal validators exited zero.

At the execution revision, verification comprised 246 focused tests with zero skips, 3,101 full
repository tests passed with 30 expected optional-tool skips, 40 smoke checks, Ruff, frozen
contracts, module-size, privacy, and diff checks. The later #299 mutation tests add seven focused
negative controls for native-count disagreement, the exact 66-window set, and manifest
completeness; the current 253-test focused suite passes.

No participant ID, genotype, per-variant count row, private input, or generated real-data artifact
is tracked by Git. The private acquisition and preparation directories remain the reviewable
source of row-level evidence and are bound by the manifest hashes above.

## Scientific limits and downstream use

These 66 windows were selected before genotype inspection, but physical separation does not make
the 32,415 variants independent loci. The source populations describe reference-panel origins,
not verified present-day residence or probabilistic sampling from mapped populations. The known
participant, kinship, discovery, cohort, and QC dependencies remain part of every future split.

The four tables may support broader **development** comparisons after each experiment freezes its
target, dependency-aware folds, and admission record. They do not replace independent external
confirmation and do not authorize a model or public surface. No map is shown because reviewed P0
resident coordinates are outside this task; drawing these counts geographically would imply a
qualification the source does not have.

Design references: Atlas §§4–8,12 and the
[reference-window acquisition design](../superpowers/specs/2026-09-11-reference-window-acquisition.md).

# Reference-window acquisition software verification

This completes the software-only implementation tasks for #255 and advances #189
WP0/WP1. The two offline CLIs consume the independently reviewed #254 byte plan,
acquire its exact generation-bound ranges, preserve original VCF tokens, independently
check native extraction and called AC/AN, and prepare technical/paper × called/quality
count tracks. This evidence does **not** report a real acquisition, an allele-frequency
result, a calibrated model, or a publication-ready dataset.

## Implemented boundary

`scripts/acquire_reference_windows.py` validates all manifest, review, retained-index,
cohort, dependency, executable and runtime inputs before its first source request. It
then emits one receipt for every source and all 66 frozen windows. A partial source
cannot become complete, and preparation refuses any incomplete parent acquisition.

`scripts/prepare_reference_window_counts.py` requalifies the frozen cohorts, parses
the original retained record bytes, applies the preserved sequential QC tree, and
checks each retained variant against native cohort totals and native GT/GQ/DP/AD
tokens. It writes one sorted fragment per stage/window/track and externally merges
those fragments with `heapq.merge`. Within the composer, each source-record pass
classifies site disposition once and counts the paired cohorts together; the deep
validator independently replays the source and native streams rather than trusting
the composer's summaries. Each pass is streaming and disk-backed, so neither retains
a full campaign matrix in memory.

Runtime evidence resolves normal executable symlinks and hashes the targets that run.
Acquisition records `bcftools`, linked HTSlib, `fill-tags`, `tabix`, `bgzip` and
`gcloud`, plus six installed Cloud SDK storage source files. Preparation records only
its offline `bcftools`/HTSlib/`fill-tags` runtime. The local exact-version probe passed
with bcftools/HTSlib/fill-tags 1.23.1, tabix/bgzip 1.23.1 and Google Cloud SDK 574.0.0.

## Synthetic and fault evidence

The CLI suite has 26 tests. The complete synthetic acquisition contains 22 ready
sources and 66 explicitly accounted windows. Its complete-empty preparation writes
four real header-only count tables rather than treating absence as an omitted result.

A nonempty composition retains one chr1-s1 A/G SNP. Each track contains exactly one
variant × 80 populations. Hand-checked aggregate counts are:

| Cohort stage | Samples | Called AC/AN | Quality AC/AN | Rows per track |
|---|---:|---:|---:|---:|
| Technical QC | 4,117 | 4,117 / 8,234 | 4,117 / 8,234 | 80 |
| Paper ancestry exclusion | 4,094 | 4,094 / 8,188 | 4,094 / 8,188 | 80 |

The native count and token artifacts carry the same variant and sample identities and
pass the deep preparation validator. A forced short transfer for chr1 produces three
refused chr1 windows and 63 explicit no-record windows; the acquisition is incomplete
and preparation creates no output. A separate begun-preparation parse failure writes
a terminal 66-window refusal manifest with both stages marked not attempted. Missing
review, changed reviewed source hash, synthetic public-evidence cohorts and an existing
destination all refuse before external work.

## Verification

The current software state passed:

- 231 focused acquisition/preparation tests, zero skips, including the live native
  full-versus-sparse/count/normalization fixture.
- 3,086 full-repository tests with 30 optional-tool skips and no failures, out of
  3,116 collected tests.
- The 40-check smoke suite, Ruff, frozen-contract, module-size and private-file gates.

An independent controller review found no material Task 6 issue after checking runtime
evidence, causal refusal replay, exact inventories, native identity joins, ordering,
refusal ledgers and post-publication rollback. No network or real acquisition was run.

## Remaining controller phase

No real VCF range was retrieved and no private real cohort input or participant ID was
published by this software task. Before real retrieval, the controller must obtain the
specified independent review of the exact source and complete #254 artifacts. The real
run then needs a separate all-window evidence audit. Any refused window keeps #255
incomplete.

These count tracks do not establish independent loci, verified residence, predictive
improvement, calibration, or geographic eligibility. Population coordinates are not
part of this task, so no heatmap or geographic surface is generated. A later review
figure must use reviewed P0 population coordinates, distinguish measured observations
from inferred surfaces, and mask unsupported cells.

Design references: Atlas §§4–8,12 and the
[reference-window acquisition design](../superpowers/specs/2026-09-11-reference-window-acquisition.md).

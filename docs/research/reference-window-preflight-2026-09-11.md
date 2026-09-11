# Autosomal reference-window preflight

This completes the bounded index/geometry acceptance for #254 and advances #189
WP0/WP1. The original chr22 pilot covers one linked 10 kb interval; broader genomic
coverage is needed before evaluating generalization across windows or chromosomes.
The new manifest freezes 66 windows before inspecting their genotype content.
This is development-data preparation, with P1 and publication eligibility false.

## Frozen selection and sources

The selector draws one uniformly jittered 10 kb window within each of three physical
strata on chr1–chr22, using PCG64 seed 42 and NumPy 2.4.6. It removes starts overlapping
the original chr22 `[20,000,000,20,010,000)` pilot geometrically before drawing. There
is no outcome-based redraw, external mask or inferred independence between windows.
GRCh38 contig lengths come from the previously inspected release header declarations.

Sources remain the original dense adjusted gnomAD v3.1.2 HGDP+1KG VCF/TBI release,
with explicit object generations. The saved source audit is supplied prior evidence;
this preflight independently checked current pinned metadata and exact index bodies.
It did not establish whole-VCF byte integrity or validate upstream genotype calls.

| Frozen artifact | SHA-256 |
|---|---|
| Manifest | `d469f05d6ee96556d1e23ca9f95e1914d4364b1bc02f89fd6f88288e3110f0b7` |
| Window TSV | `048bfcba9b01c8f520940965039f926d5c43325c4a0b882c4ba7a755c360df71` |
| Completed preflight | `8560c0b17c6c90595a0e44be9514e9880632f10960046d3ce5d82ee1fdabd081` |

## Observed index-only result

The single real preflight ran from reviewed implementation
`af68e348fce51599e673e612f49dde8f1c837996` and completed with exit 0 on September 11,
2026, at 03:25:00 UTC. Its original manifest and windows remained unchanged.

| Check | Result |
|---|---:|
| Verified autosomal indexes | 22 of 22 |
| Retained compressed index bytes | 3,000,550 |
| Windows with planned index chunks | 65 |
| Windows with no index chunks | 1 (`chr16-s2`) |
| Refused windows | 0 |
| Total planned compressed bytes, including indexes | 2,351,476,474 (2.189983 GiB) |
| Fixed transfer ceiling | 26,843,545,600 bytes (25 GiB) |
| VCF body bytes acquired by this preflight | 0 |

The planned total includes the conservative overlapping-bin chunk ranges, a fixed
1 MiB header prefix and 28-byte EOF allowance per source, merged within each exact
VCF generation, plus all 22 index fees. No linear-index pruning was used.
`no_index_chunks` does not establish an empty source interval or allele count zero;
`chr16-s2` remains in the manifest for subsequent explicit source/native checks.

There were 44 metadata and 22 index-body **wrapper invocations**. These are not HTTP
request counts. The repository gcloud wrapper ran anonymously with storage body
retries set to zero. SDK 574.0.0 performs additional internal metadata activity whose
HTTP attempts remain unobserved; invocation time and output are bounded. Retained
body sizes do not measure HTTP/TLS/wire bytes.

## Verification and limits

Independent task and whole-branch review identified and resolved provenance,
termination and accounting boundary defects before the real invocation. The final
implementation passed:

- `python -m pytest`: 2,008 passed, 17 skipped, 426.19 seconds.
- The final amended planner/CLI controls: 53 passed, including seven new regression
  cases observed failing before the final provenance fix.
- `python scripts/smoke.py`: all 40 checks passed.
- Ruff, frozen-contract, module-size, tracked-file privacy and whitespace gates.
- An explicit live synthetic native fixture check using bgzip/tabix/bcftools 1.23.1,
  with zero skips; the native fixture/parser were unchanged by later boundary fixes.

A separate controller checker, with no genomeOS imports or network requests,
recomputed all 66 bin/chunk plans, physical range unions and fees from retained TBI
bytes. It matched all 22 index sizes, MD5/CRC32C/SHA-256 values, source identities,
frozen input hashes and executed source hashes. Its first attempt failed on a mixed
list/tuple sorting bug in the checker; the original checker and failure were retained,
and the corrected local audit passed without reacquisition or preflight changes.
Original indexes, invocation/exit records, exact test evidence and audit receipts
are retained locally; source genomic data and participant material are not published.

This result establishes that the frozen index-derived plan fits its transfer ceiling.
Header/sample reconciliation, original-token validation, genotype/count extraction
and native count controls belong to #255. It provides no new allele-frequency
accuracy result, geographic qualification, independent-locus claim or model release.
The original B0 inputs and separately frozen B0H calibration remain unchanged.

Design references: Atlas §§4–8,12 and the
[reference-window preflight design](../superpowers/specs/2026-09-10-reference-window-preflight-design.md).
Expert review should assess the sampling frame and the limits of index-derived
coverage before interpreting later population/window/chromosome comparisons.

# Count-scoring boundary-fix hardware refresh

September 9, 2026; advances [#189](https://github.com/bschilder/genomeOS/issues/189)
and verifies the numerical correction for [#194](https://github.com/bschilder/genomeOS/issues/194).

## Question and scope

Does the complete count-diagnostics workflow still agree between the explicit SciPy and CuPy
backends after the reviewed endpoint/log-mass correction? This is synthetic numerical and
computational evidence, **not** improved allele-frequency accuracy or scientific publication
evidence. Both reports retain `publication_eligible=false`.

The tested source is `0a2459b7c9564167d3097c1e526238e123363843`. It uses paired finite products
and near-one `log1p` arithmetic for beta-binomial mass, and the exact support maximum for the
100% quantile. Interior beta-binomial log scoring/diagnostics explicitly refuse AN above 65,536;
the documented CDF-only and degenerate/binomial domains are unchanged. No approximation or
silent fallback was added. See [the numerical-domain contract](../global-af-benchmark.md#count-scoring-numerical-domain).

Seven committed source/test files were uploaded without repository history, genomic records or
credentials; their actual remote SHA256 values were checked before execution. The three source
hashes in both retrieved reports also match the committed local files:

```text
e04644ce19b562a60a97332f089f5849f42631a65c04b424d83cdfeeec16e409  genomeos/validation/predictive.py
3f9978de4f0262b3c6f6ecd07a8ccc5f15f138e920b5031b37811cd666f5e341  genomeos/validation/predictive_cupy.py
abe3d1e6b0b3a5bdae72ae9071b15af161238a356cfbb48f65ee60a6db91002c  scripts/profile_count_scoring.py
```

## Correctness and integration

The actual A100 suite passed **116 tests, zero skips, failures or errors**, in 65.32 seconds.
It includes analytical endpoint/near-degenerate cases and CPU/CUDA comparisons. Retrieved JUnit
records 116 tests and 65.314 seconds; its SHA256 is
`32b2298e4ee8338f4149d3727e1053c88fad5aa7a9cbf24dec2b489f3fbe0346`.

Both profiling workloads passed complete-frame parity, seeded count equality and exact integer
quantile equality at all seven separately recorded levels; the maximum endpoint discrepancy was
zero. The 100% support-boundary behavior is covered by the test suite rather than these seven
profiler levels. Maximum randomized-PIT differences were `7.771561172376096e-16` (small) and
`4.3454129183828627e-13` (large). Log-score differences were zero, but both backends share the
CPU mass scorer, so that equality is not an independent validation of the mass formula.
Analytical Bernoulli and independent high-precision Decimal tests provide that separate evidence.

Fresh controller integration on the committed numerical source passed **694 tests, 11 expected
local GPU skips and 5 unchanged warnings**, in 287.74 seconds. The implementer independently
reported the same counts in 289.82 seconds. Smoke passed 40 tests; Ruff, frozen-contract and
module-budget checks passed. The five inducing-point redundancy warnings are enumerated in
[the original workflow note](count-scoring-gpu-workflow-2026-09-09.md#revisions-and-correctness-gates);
no scientific configuration was changed to silence them. Independent scoped re-review found the
reported numerical/support issues addressed, with no new Critical/Important finding.

## Same-host measurements

The new task pod was an A100-SXM4-80GB in US-MD-1. Python 3.12.3, NumPy 2.4.6, SciPy 1.18.1,
pandas 3.0.5, pytest 8.4.2, CuPy CUDA-12 14.2.0 and cuda-pathfinder 1.8.1 were pinned. Runtime
CUDA API was 12.9, driver API 13.0, NVIDIA driver 580.126.16. Raw reports record all installed
distribution versions. Each workload used a separate fresh CuPy compilation-cache directory.

| Workload | CPU first (s) | CPU warm median (s) | GPU context + first (s) | GPU warm median (s) | Warm ratio |
|---|---:|---:|---:|---:|---:|
| 32 draws, 2 observations, AN 20 | 0.294957 | 0.293290 | 9.909501 | 0.032769 | 8.95× |
| 2,048 draws, 10 observations, AN 1,000 | 214.408505 | 214.092823 | 17.233294 | 4.413921 | 48.50× |

Both use concentration 20, seed 42 and five warm repeats. Timings include construction, complete
diagnostics, host/device transfer and synchronization; they exclude pod/environment setup,
imports and synthetic input generation. Cold GPU includes separately measured context time.
The small cold GPU path is substantially slower than CPU. The large warm ratio combines batching
and GPU execution versus the current looping SciPy reference; it is not a pure hardware speedup
or a comparison against the best optimized CPU implementation. Mass, errors, sampling and final
frame assembly remain on CPU. This is not an LD computation and makes no CuGen performance claim.

The separate memory runs sampled additional device usage of 2,097,152 bytes (small) and
10,485,760 bytes (large), with final pool reservations of 57,856 and 8,629,248 bytes. These are
sampled device-wide deltas and allocator reservations, not exact peak live array memory.

All repeats, endpoint arrays, source/input hashes and environment details are preserved
byte-for-byte in:

- [Small raw report](count-scoring-profile-small-0a2459b.json), SHA256
  `2ea1acc71c872a5b3ada84ccc4ab5e1781c2c31192a200753a2f83a695062846`.
- [Large raw report](count-scoring-profile-large-0a2459b.json), SHA256
  `c1464c9bec57ff97f674097311b9f42862c61161743a6ecc25cc3dd9e6dabcb0`.

## Resource closure

Task-owned pod `dmlckeqtczcw75` was created at 15:04:59.608 UTC and stopped at 15:39:40 UTC
on September 9 after both reports and JUnit had been retrieved and verified. The control plane
reported `EXITED`; deletion returned HTTP 204 at 15:39:54 UTC, followed by a 404 lookup.
Its disposable disk/source environment was deleted; the retrieved reports remain available.
At the API-reported $1.59/hour, the 2,080.392-second creation-to-stop interval corresponds to
estimated compute of **$0.9188398**, not an invoice and excluding storage or other charges.
No task-owned GPU remains running. The earlier pod and reports retain their separate lifecycle
and source revisions in the original workflow note.

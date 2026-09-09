# Synthetic complete-workflow count-scoring GPU evidence

September 9, 2026; [research program #189](https://github.com/bschilder/genomeOS/issues/189).

## Question and limits

This experiment asks whether an explicitly selected CuPy backend can accelerate the exact
finite-count CDF work inside the complete public `predictive_diagnostics` workflow while retaining
the SciPy backend's numerical results. It is computational evidence, not allele-frequency model
accuracy, calibration, scientific validation, or publication evidence. Every report is labelled
`evidence_kind="synthetic_performance_probe"` and `publication_eligible=false`.

The comparison is between the current same-host SciPy reference, which sums beta-binomial CDFs in
a Python loop over draws, and the bounded batched CuPy implementation. Its ratio therefore combines
an algorithmic batching improvement with GPU execution; it is neither a pure hardware speedup nor
a comparison with the best possible optimized CPU implementation. Log mass, error ingredients,
replicated-count sampling, and final frame assembly remain on CPU in both workflows.

## Revisions and correctness gates

The initial implementation snapshot was commit
`ee14584cdaa85b72105f3094091a2d49a06336fd`. All seven uploaded source/test files matched their
committed local SHA-256 values. Its actual-device suite passed 75 tests with zero failures and zero
skips in 46.86 seconds. The initial small and large reports passed all then-recorded parity checks,
but compared interval width and coverage without separately recording integer endpoints.

Pre-review identified that two shifted intervals can have equal width and identical coverage for
one observed count. Commit `6fd7693164794359fd18749e6afe71b8c5ba490c` therefore exposed the
existing exact left-continuous count quantiles, directly compared all seven diagnostic levels, made
any endpoint mismatch fail profiler parity, and added a synthetic regression demonstrating that
equal widths/coverage cannot conceal shifted endpoints. All seven updated uploaded files again
matched the committed local hashes. The refined actual-device suite passed 77 tests with zero
failures and zero skips in 65.10 seconds, including:

- binomial and beta-binomial complete diagnostic frames;
- heterogeneous allele numbers, p=0/1, zero/all counts, and the AC=-1 CDF boundary;
- supported numerical limits and an analytical tiny nonzero lower tail with zero absolute
  tolerance;
- row, draw, and support chunk boundaries;
- seeded replicated counts and randomized PIT;
- exact quantile endpoints, including an exact half-mass tie; and
- missing-library, hidden-device, and every shared parameter/count refusal without fallback.

The three refined executed-source hashes are:

```text
3c25cd5bd57d7fbe81ff5990dbcbb716e53ff0395de85277574b5ac4028b2acb  genomeos/validation/predictive.py
3f9978de4f0262b3c6f6ecd07a8ccc5f15f138e920b5031b37811cd666f5e341  genomeos/validation/predictive_cupy.py
abe3d1e6b0b3a5bdae72ae9071b15af161238a356cfbb48f65ee60a6db91002c  scripts/profile_count_scoring.py
```

Repository-wide integration at the refined source state independently passed 657 tests with eight
expected local GPU skips and five existing warnings in 290.65 seconds. Smoke passed 40 tests;
lint, frozen-contract, and module-size checks also passed.

The five pre-existing warnings are `UserWarning` inducing-point redundancy warnings, also present
in the controller's fresh full suite at `8da0398` (657 passed, 8 skipped, 5 warnings in 294.57s).
`tests/test_crossval.py::test_cross_validation_runs_and_reports_coverage_between_zero_and_one`
and `tests/test_crossval.py::test_predictive_coverage_exceeds_latent_coverage_on_the_same_data`
each emit warnings for spacing/range 179 km/738 km and 173 km/708 km (four warnings total).
`tests/test_surface_fit.py::test_the_inducing_approximation_fits_and_predicts` emits the fifth
at 175 km/887 km. Their rounded ratios are
0.24, 0.24, and 0.20, below 0.25; adjacent inducing points correlate at approximately 0.99, and
the warning recommends reducing `n_inducing`. These are unchanged production-fitting test paths;
their scientific configurations were not changed to suppress warnings.

## Environment and measurement scope

The task-owned RunPod used an NVIDIA A100-SXM4-80GB in `US-MD-1`, CUDA runtime API 12.9, driver API
13.0, NVIDIA driver 580.126.16, and Python 3.12.3. Its isolated scoring environment pinned NumPy
2.4.6, SciPy 1.18.1, pandas 3.0.5, pytest 8.4.2, CuPy CUDA-12 14.2.0, and cuda-pathfinder 1.8.1;
each raw report records the complete transitive installed-version inventory. No real genomic data,
credentials, editable installation, repository history, fitter, surface, serving, or burden code
was uploaded. Only the seven allowlisted source/test files were extracted from each Git commit.

Each timing constructs `CountPredictive` and runs the full `predictive_diagnostics` call. GPU
timings include transfers and explicit stream synchronization. Import, isolated-environment
installation, source upload, pod startup, and synthetic input generation are excluded. CUDA
preflight/context time is reported separately; `GPU context + first` adds it to the first scoring
call and is the relevant cold figure. Warm results preserve all five individual repeats.

The backend bounds each temporary log-mass grid to 4 rows × 128 draws × 1,024 support terms =
524,288 float64 elements. Memory profiling is a separate, untimed run. The reported sampled peak
is a 0.5 ms sampled device-wide change from the pre-run baseline and can include other processes;
it is not an exact allocator high-water mark. CuPy pool `reserved` bytes are reported separately
and are not represented as peak live memory.

## Received measurements

| Snapshot | Workload | CPU first (s) | CPU warm median (s) | GPU context + first (s) | GPU warm median (s) | Warm ratio |
|---|---|---:|---:|---:|---:|---:|
| `ee14584` | 32 draws, 2 observations, AN 20 | 0.296859 | 0.290127 | 9.439314 | 0.032242 | 9.00× |
| `ee14584` | 2,048 draws, 10 observations, AN 1,000 | 210.336527 | 210.088570 | 16.652602 | 4.131881 | 50.85× |
| `6fd7693` | 32 draws, 2 observations, AN 20 | 0.298544 | 0.298048 | 9.686129 | 0.033099 | 9.01× |
| `6fd7693` | 2,048 draws, 10 observations, AN 1,000 | 210.547394 | 209.635023 | 16.653441 | 4.107564 | 51.04× |

The small workload is deliberately overhead-dominated: its warm GPU path is faster, but a fresh
CUDA context/JIT makes the cold GPU path much slower than CPU. The refined large workload shows a
51.04× warm improvement against the current CPU reference and also amortizes context/JIT on its
first call. This is the combined batching-plus-device comparison defined above, not a pure hardware
speedup or evidence against an optimized CPU challenger.

Refined warm repeats in seconds, retained individually rather than summarized away:

- small CPU: `0.2973643616`, `0.2982055470`, `0.2975054197`, `0.2980482765`,
  `0.2993935198`;
- small GPU: `0.0335689746`, `0.0330986008`, `0.0331726037`, `0.0330869257`,
  `0.0330483578`;
- large CPU: `209.5748007260`, `209.8864820376`, `209.4379044510`, `210.0595042929`,
  `209.6350233369`; and
- large GPU: `4.0941758603`, `4.1060915403`, `4.1075639240`, `4.1162406988`,
  `4.1112253927`.

All individual seconds, hashes, dependency versions, parity fields, and memory records received so
far are preserved byte-for-byte in:

- [`count-scoring-profile-small-ee14584.json`](count-scoring-profile-small-ee14584.json)
- [`count-scoring-profile-large-ee14584.json`](count-scoring-profile-large-ee14584.json)
- [`count-scoring-profile-small-6fd7693.json`](count-scoring-profile-small-6fd7693.json)
- [`count-scoring-profile-large-6fd7693.json`](count-scoring-profile-large-6fd7693.json)

The refined small run passed exact quantile equality with maximum integer endpoint difference 0.
Its maximum absolute randomized-PIT difference was `7.771561172376096e-16`; log score difference
was 0. Its sampled additional device use was 2,097,152 bytes and post-run pool reservation was
57,856 bytes. The initial large run's maximum PIT difference was `4.3454129183828627e-13`, log
score difference was 0, sampled additional device use was 10,485,760 bytes, and post-run pool
reservation was 8,629,248 bytes. The refined large run reproduced those two memory measurements,
passed exact quantile equality with maximum endpoint difference 0, and had the same maximum PIT
difference (`4.3454129183828627e-13`) and zero log-score difference.

## Resource lifecycle and interpretation

Task pod `5cxjrqb15ngolk` was created at 2026-09-09 13:21:55.581 UTC at a quoted rate of
$1.59/hour. It was stopped at 14:28:02 UTC with control-plane state `EXITED`, after all reports and
test logs were retrieved, and deletion returned HTTP 204 at 14:28:15 UTC. Creation-to-stop duration
was 3,966.419 seconds; a subsequent control-plane lookup returned 404, confirming deletion. The
duration corresponds to an estimated compute cost of $1.751835. That estimate is not an invoice and
does not include separate storage or other possible charges.

The hardware execution gates are complete: the refined device suite had zero skips/failures, both
refined profiler reports passed complete diagnostics and exact integer endpoint parity, raw evidence
was retrieved, and the task-owned resource was stopped and deleted. Independent review of the
implementation and this evidence remains a separate process gate; this note does not mark that
review complete or promote the backend into a default.

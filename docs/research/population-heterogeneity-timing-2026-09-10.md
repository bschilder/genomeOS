# Eight-case B0H GPU timing evidence — 2026-09-10

The unchanged B0H fitter ran successfully on an A100: eight predeclared initial
attempts, eight accepted fits, zero divergences, and no recorded generation or
diagnostic failures. This resolves the narrow runtime-feasibility question.
It does **not** establish calibration, improvement over B0, spatial validity,
global allele-frequency accuracy or production eligibility. Advances #211/#189;
Atlas design §§5,7–8,12. No scientific source or dependency lock changed.

## Scientific and engineering contract

Question: what do the actual public fitter and subsequent diagnostics return,
and how long do they take on one explicitly verified float64 GPU?
Acceptance evidence: every fixed case identity and outcome, whole-call timings,
actual source/runtime/config, and labeled memory observations. The consumer is
future offline resource planning, not model promotion. Assumptions and refusals
are specified in the [pre-result protocol](population-heterogeneity-timing-protocol-2026-09-10.md).
Protocol commit `6c10683` predates generation and fitting; scientific source is
`df0b71dfca1edd2c209abe8f9829cd103feaffdd` throughout.

Exactly eight study-0 prior-simulation cases ran in the declared order, with no
retries, redraws, replacements or convergence-threshold changes. Each fit used
four vectorized NumPyro chains, 1,000 tuning steps and 500 posterior draws per
chain, target acceptance 0.9. The two rho priors remained separate tracks:
Beta(1,9) and Beta(1,4). Training AN was `(0,1,2,5,10,20,40,64)` repeated twice;
the two AN=0 rows stayed unavailable. One fresh-population heldout had AN=20.

Only accepted fits received the selected-quantity call, then one SciPy and one
CuPy summary call in that fixed order. All eight reached these calls. Stored
R-hat and ESS numbers below were inspected, not recomputed by the auditor.
No rank-uniformity or negative-control-rejection test was run on this pilot.

## Observed outcomes

- Eight fits returned `accepted`, with zero divergences and no identity mismatch.
- Across fits, maximum R-hat ranged from 1.0025033433116324 to
  1.0083429854408046. Minimum bulk ESS ranged from 564.1197353820959 to
  1045.63016856032; minimum tail ESS from 505.52574654573397 to
  921.2625295613657. Existing gates remain R-hat≤1.05, bulk/tail ESS≥200,
  and no divergences.
- Eight prior controls retained four pairs each and no failure; all 144 ranks
  were `ranked`, all 104 reference points were marked resolved, and all 24
  dependence comparisons were resolved. These are completed calculations, not
  evidence that the controls passed the full study's statistical tests.
- All 16 nested predictive summaries were `complete`. There were no recorded
  stage, control, scalar, reference, rank or predictive errors. Top-level
  summary `status:null` in the timing report is not the nested outcome.
- The largest stored reference field named `error_bound` was
  4.9141101414874714e-12. It is a cross-order diagnostic, not a rigorous
  mathematical error bound. Full-chain h ESS and MCSE remain `not_computed`.

All identities, truths, fit diagnostics, ranks and saved predictive metrics are
retained in the [inspection extraction](../../data/validation/b0h-timing-20260910-01-inspection.json),
with the [original debug records](../../data/validation/b0h-timing-20260910-01/debug)
and [arrays](../../data/validation/b0h-timing-20260910-01/arrays).

## Whole-call timings

Seconds rounded to three decimals below; exact integer nanoseconds are in the
[original timing report](../../data/validation/b0h-timing-20260910-01/report.json).
Tuple fields are `(track, study, case, replicate)`. These are different datasets,
not repeated timing replicates of one workload.

| Case | Fit | Selected quantities | SciPy summary | CuPy summary |
| --- | ---: | ---: | ---: | ---: |
| (0,0,0,0) | 33.204 | 0.828 | 10.701 | 43.609 |
| (1,0,0,0) | 18.871 | 0.833 | 18.010 | 1.317 |
| (0,0,0,1) | 23.649 | 0.841 | 14.377 | 0.429 |
| (1,0,0,1) | 18.746 | 0.849 | 18.429 | 0.431 |
| (0,0,0,2) | 23.199 | 0.824 | 11.820 | 0.374 |
| (1,0,0,2) | 20.997 | 0.823 | 13.097 | 0.430 |
| (0,0,0,3) | 23.445 | 0.832 | 13.304 | 0.453 |
| (1,0,0,3) | 23.363 | 0.831 | 11.286 | 0.393 |

Heavy imports took 9.237041015 seconds; device preflight took 3.841889830.
Generation took 0.002002447–0.002564660 seconds per case. Summed public-call
timers total 350.614061936 seconds; including imports and preflight gives
363.692992781 seconds. Wrapper timestamps span approximately 368 seconds
(15:46:41–15:52:49 UTC, one-second resolution), with exit 0.

The first fit took 33.203659406 seconds; the subsequent seven took
18.746262583–23.649378654 (median 23.199308683). The first CuPy summary took
43.608658989 seconds; subsequent median was 0.430099534, compared with
13.303844531 for the corresponding seven SciPy summaries. Startup costs are
retained, not discarded. Neither first-call cost is isolated JIT/kernel time:
device libraries were initialized during preflight, and whole public calls
include host-side work. Stage timers exclude debug/report writes and other
uninstrumented orchestration. Fixed backend order, one device and eight prior
cases do not establish a general speedup, stress-tail timing or concurrency.

## Descriptive backend comparison

Both backends used identical saved fits, targets and purpose-7 seeds.
Predictive mean/concentration arrays were bit-identical. Parameter summaries,
log scores, errors, coverage flags and interval widths were also bit-identical
in these saved results. The only numerical summary differences were six
randomized-PIT values; maximum absolute difference was
6.161737786669619e-15. Backend labels and array filenames also differ as expected.
No new tolerance or generalized parity verdict is introduced.

`complete` does not mean every interval covered the heldout count: ordinal 4
missed its 50% interval, ordinal 5 missed its 50% and 80% intervals. All eight
95% intervals covered. Eight outcomes are insufficient to establish calibrated
coverage. This pilot also contains no paired B0 comparison.

## Runtime, resources and collection

Actual device: NVIDIA A100-SXM4-80GB, 81,920 MiB, driver 580.126.16, US-MD-1.
The first requested pod was available. Linux Python 3.12.3 used the frozen
project requirements plus constrained CUDA12 JAX and CuPy wheels. Both actual
device probes were float64; JAX reported platform `gpu`, with explicit
`JAX_PLATFORMS=cuda`, `JAX_ENABLE_X64=1`, and preallocation disabled.
The [observed environment](../../data/validation/b0h-timing-20260910-01-environment.txt)
records all 89 installed package versions; it is not a project-lock change.
Setup used the documented [JAX CUDA12 installation path](https://docs.jax.dev/en/latest/installation.html)
and unset inherited `LD_LIBRARY_PATH` without disabling compatibility checks.

Linux process high-water RSS was 802,428 KiB after preflight and 2,152,848 KiB
at completion. All 40 post-stage JAX allocator snapshots were available; their
largest reported `peak_bytes_in_use` was 134,359,552 bytes. That counter is not
a measured whole-GPU/all-library peak and excludes any unreported CuPy/runtime
overhead. No device-utilization or memory-capacity extrapolation follows.

One task-owned pod was created at 15:32:34 UTC, stopped at 15:56:38 and deleted
at 15:56:50 after complete collection and checksum verification. At the quoted
$1.59/hour rate, creation-to-stop elapsed time corresponds to about $0.64;
this is not an invoice and excludes any separately billed storage. The pod's
remote disks were permanently deleted; original collected evidence is retained
locally and the synthetic output tree is included here. Other pods were untouched.

Collected archive SHA256:
`73ddc1188e9d3a3979054ea125616924eb94a858807c25c968067571f9f65b73`.
The remote and downloaded hashes matched before extraction. Original report
SHA256: `91abea1b1f41a3fa58b0be7cdfa1ca31139dcc17805592f5d66366ab450e9666`.

## Reproducibility and verification

The [frozen instrumentation and inspector](population-heterogeneity-timing-instrumentation-2026-09-10.md)
retain the exact source used for setup, execution and inspection, with hashes.
They are historical, one-off scripts in Markdown, not supported production
runners or a safe scientific-record reconstruction interface.

Independent read-only inspection verified all 48 debug trees and all 48 array
references/files. Arrays are finite float64: sixteen `(4,500,1)` and thirty-two
`(2000,1)`. It checked 1,328 dataclass nodes across 28 encountered classes,
all 6,928 field occurrences against static declarations at the exact scientific
SHA. No scientific constructors or numerical diagnostics were invoked.

Root verified all 98 retained output-file hashes, all four embedded script
hashes, and reran the inspector against this branch's output tree with only
its historical input paths changed. Its JSON output reproduced byte-for-byte:
`081174570c02b64a28953e68e326260ec20aff18570c2623c4f028a9ab5a239a`.
The output directory contains only original run files; the derived extraction
and observed environment are sibling files so the file-hash manifest remains
reproducible. The scientific progress log contains only case/stage markers.

Pre-run evidence: probe syntax/import-boundary/help-path and literal dump/error
checks passed, as did Ruff; both shell wrappers passed `bash -n`. Remote pinned
installation passed `pip check`, environment-option inspection and 40 mandatory
smoke checks. Local report-branch baseline: 40 focused summaries passed in
6.13 seconds and 40 smoke checks passed. Final local branch verification used
the locked Python environment: `pytest -o addopts='' -q` returned 1,629 passed,
17 skipped and 15 existing Rasterio PendingDeprecationWarnings in 406.89 seconds.
`scripts/smoke.py` passed all 40 checks. Ruff, frozen-contract drift, module-size
(82 modules), privacy (827 tracked paths) and exact staged-path/whitespace gates
passed. No test or scientific threshold was changed. Remote CI for the result
commit is a separate check recorded in the PR, not implied by these local gates.

These one-way debug records preserve this timing experiment for inspection;
they do not establish archival compatibility, authenticated invocation,
restart/durability guarantees or final calibration evidence. They cannot be
counted toward the separate 1,936-initial-fit calibration study. Its fixed
manifest, failures, permitted retry and statistical controls remain binding.

## Next scientific step

Use these measurements to inform an explicitly tested execution strategy for
the full frozen calibration study. Keep evidence retention work delegated;
do not change priors, thresholds or case selection to accelerate it. Only after
the calibration and misspecification checks should B0H enter the unchanged
twelve-run B0 development comparison. B0H remains a nonspatial ablation and does
not replace the planned spatial, multi-variant or temporal models.

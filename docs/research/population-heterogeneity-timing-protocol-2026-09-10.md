# Predeclared B0H runtime spike, not the calibration study

Root choice before generation or results, 2026-09-10. Advances #211/#189.
Scientific source df0b71dfca1edd2c209abe8f9829cd103feaffdd (PR224).
Protocol b0h_timing_spike_v1, execution label b0h-timing-20260910-01.

## Scientific / engineering contract

Question: how long do the unchanged public B0H fitter and subsequent actual
diagnostic stages take, and what outcomes do they return, on one float64 GPU?
Acceptance evidence: all eight fixed case identities, generation/fit/diagnostic
outcomes, individual stage wall times, actual backend/dtype/device/runtime
metadata and clearly labeled memory observations. No calibration verdict,
global accuracy, pure JIT-time claim, hardware comparison or concurrency claim.
Component: disposable instrumentation script, calling public functions only;
no package source changes. Future scheduling decisions consume the timings.
Assumptions/refusals: one process, one CUDA GPU, explicit x64, unchanged four
vectorized chains / 500 draws / 1000 tune / target_accept0.9 and all scientific
gates. No retries, redraws, replacement cases, precision fallback or CPU fit.

## Exact workload, order and outcomes

Case tuple fields are (track_id, study_id, case_id, replicate_id). Execute:
(0,0,0,0), (1,0,0,0), (0,0,0,1), (1,0,0,1),
(0,0,0,2), (1,0,0,2), (0,0,0,3), (1,0,0,3).
These are independent prior-simulation datasets with the standard mixed AN;
they are NOT eight accepted fits selected after observing convergence.
Each calls generate_sbc_case once. A GenerationFailure is retained, not fitted.
Every GeneratedDataset calls plan_fit_attempt(attempt_id=0), then exactly one
run_fit_attempt. Retain its actual return, whatever status it has.
Only accepted fits call selected_sbc_quantities once and then
summarize_heterogeneity_fit once each with cdf_backend='scipy' and 'cupy', in
that order. No predictive-backend winner selection. Each diagnostic call has
its own measured exception boundary; an exception remains an observed failure
and does not manufacture a scientific typed result. Preserve actual returned
records and error class/message. Unexpected fitter exceptions propagate after
logging, because its public wrapper already defines admitted failure handling.
KeyboardInterrupt/SystemExit/MemoryError are not swallowed or retried.

## Measurements and temporary evidence

Measure heavy-library imports separately; no claim to include Python startup
before the script's first timer. Measure generation, each whole public fitter
call, selected quantities and each complete summary call individually using
perf_counter_ns. Returned validated host arrays synchronize successful fits;
failed call elapsed time is retained too. Label ordinal0 as first call, not
pure compilation time. No warm-up fitter invocation before these eight cases.
Preflight may initialize JAX/CuPy and execute a tiny float64 device check;
record that explicitly so first-fit timing does not imply cold CUDA context.
Record Python/platform/package versions, environment settings needed for GPU
and precision only (never arbitrary env/secrets), nvidia-smi GPU/driver data,
JAX device platform/kind, observed float64 array dtype and actual sample config.
Linux ru_maxrss is process high-water RSS in KiB; device.memory_stats snapshots
are allocator observations, not a profiled peak over all stages. Missing
device stats are explicitly unavailable, never zero. No inferred device peak.

Temporary diagnostic dump: write each actual returned dataclass tree as an
inspection-only tagged JSON tree, with exact integer hex, binary64 bit hex,
surrogate-preserving string hex and explicit class names; arrays are separate
allow_pickle=False .npy files. This is a throwaway one-way debug dump, NOT the
versioned evidence codec or a safe/reviewed reconstruction interface. No
decoder, eval, dynamic import, scientific status reconstruction or reuse in
the full study. Preserve class and every dataclass field rather than selecting
successful metrics. Ordinary timing/status/environment report is readable JSON.
Write only to a new exclusive output directory; refuse an existing destination.
Flush per-stage progress so setup/call failure is observable. Partial output is
explicitly an incomplete spike, never a resumable/completed study. Local root
collects and checks files/hashes before task-owned pod deletion. No durability,
restart, ext4 or power-loss claim; no checkpoint protocol is being implemented.

## Resource and termination scope

One new task-owned US/CA-first GPU Pod, prefer A100 then H100/H200 available
FP64 hardware; retain actual SKU/DC/quoted cost. Check live catalog/API rather
than interpreting a stale DC or one sold-out SKU as absent capacity. One GPU
is a measurement substrate, not a statement that the full study needs one.
Public image runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404; isolated Python3.12
environment with requirements.lock plus constrained JAX CUDA/CuPy additions.
Do not alter the local environment or any existing Pod. Only reviewed public
source and synthetic inputs/output; no private caches, credentials or real
genomic observations in the bundle. No GitHub PAT is needed for source transfer.
Root owns runtime setup, smoke, exact source hash, execution, retrieval and
stop/delete after collection. Stop this spike's process after 30 minutes if
incomplete; report exact completed/unfinished cases and do not resume it under
the same execution label. This operational cap cannot turn a partial result
into a scientific success. Root will diagnose actual failures before a new
separately identified measurement; no automatic restart loops.

## Rulings

1. Ruling: run a separately labeled runtime spike while the full evidence codec
   is developed — measure the actual fitter without making archive work a
   prerequisite — cost if wrong: the inspection-only dump cannot be promoted
   into the final calibration study and its code is disposable.
2. Ruling: eight fixed initial attempts, no retry — enough to observe first and
   repeated calls across both priors without selecting outcomes — cost if wrong:
   timings may not cover worst-case stress or full-study tail behavior.
3. Ruling: initialize device checks before timing fits and label all phases —
   establish GPU/x64 admission — cost if wrong: first-fit timing is not cold
   process/CUDA startup or isolated JIT cost.
4. Ruling: one sequential GPU measurement with a 30-minute process cap — bound
   this diagnostic action, not the study — cost if wrong: any incomplete spike
   yields no full-throughput claim and requires a distinct follow-up experiment.
5. Ruling: keep the protocol and resulting research note on an isolated
   `research/global-af-b0h-timing` branch — preserve unrelated original-checkout
   changes — cost if wrong: one additional explicit workspace path.

This is a brainstorming spike under the user's explicit continue/delegate
authorization, not a new production subsystem. Any retained reusable runner
still requires its own reviewed implementation plan. No execution yet.

Scientific source archive SHA256:
`a6714b6166181eba453b6fad638e255dd09948777c7213e30b2450f8277390e6`.
The [JAX installation guide](https://docs.jax.dev/en/latest/installation.html)
was checked for the explicit CUDA12 pip path and library-path caveat.

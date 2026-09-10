# CuGen training-only LD synthetic pilot — pre-hardware state

**Status:** implementation complete locally; hardware admission pending. This document contains no
GPU result, speedup claim, allele-frequency improvement claim, joint-covariance claim, or
publication claim. Issue #195 remains open until the controller supplies and verifies real hardware
evidence; #205 is advanced by preserving its precision controls.

## Scientific and engineering contract

The tested claim is narrow: pinned CuGen revision
`b95adbaabef1ca5ff2795b9435e9bb7d6aebb9a1` can be evaluated for correctly identified,
pairwise-complete, unphased ALT-dosage correlations on bounded synthetic training calls. Admission
requires exact identities/counts, absolute R error at most `1e-5`, absolute R2 error at most
`2e-5`, complete requested-pair reconciliation, independently decoded subset calls/statistics, and
held-out mutation invariance.

The engineering surface is an offline synthetic CLI over the public verified CuGen loader and
`run_cugen_pilot`. It generates no user-supplied or real genotypes. Missingness remains dosage value
3, undefined pairs remain explicit refusals, and the workflow runs the independent reference plus
both CuGen CPU and GPU backends. It is an admission workflow, not a GPU-only production alternative.

## Implemented experiment cases

| Case | Synthetic source | Training partition | Purpose |
|---|---:|---:|---|
| `hand` | 8 samples × 7 variants | reordered 4-sample training set | hand-derived signs, missingness, invalid states and non-PSD pairwise counterexample |
| `scale` | 4,096 × 64 | 3,072 train / 512 held out / 512 excluded | fixed pilot caps, all 2,016 unordered pairs and held-out mutation control |
| `precision` | 4,096 × 16 | all 4,096 training | n=3,072/4,096, overlapping/disjoint near-fixed calls and original/double-flipped coding |

The CLI requires a new output root, an explicit pinned source root and data version, at least three
repeats, and seed 42. Each planned baseline and held-out-mutated execution has its own immutable
artifact directory. `experiment.json` accounts for every planned run, including retained failures.

## Provenance and measurement boundaries

The shared loader verifies all 37 allowlisted CuGen source files before import and returns frozen
path/hash tuples. Imported provenance includes `cugen/__init__.py`, `cugen/write.py`,
`cugen/subset.py`, and `cugen/ld.py`. Synthetic sources are validated before the public
`write_cugen(..., encoding=0, gidx=...)` call and independently decoded afterward.

The adapter emits exactly one ordered start/end boundary for each of 12 stages: input validation,
source snapshot, CuGen import, subset, training validation, independent reference, CPU LD and
reconciliation, GPU LD and reconciliation, artifact writing, and completed-reader verification.
The external observer synchronizes before and after subset/GPU stages. It reports individual stage
intervals, source-generation time, CuGen source-loading time, CUDA preflight time, and a full adapter
interval through serialized verification. Process RSS is labeled as a high-water observation;
device pool readings are stage-boundary used/retained snapshots, never total CUDA or workflow peaks.
Report finalization is outside its own elapsed interval.

## Local evidence

The locked local Task 1–4 contract run reported `266 passed, 7 skipped`. All seven skips are the
explicit actual-CUDA cases because this workspace has no working CUDA device. The non-CUDA tests
verify subprocess argument/output refusals, missing-GPU nonzero failure with complete planned-run
accounting, deterministic source bytes, public writer provenance, exact observer ordering and
failure propagation, immutable scientific outputs under passive observation, and controlled-clock
measurement boundaries.

The local missing-GPU path is a requested-experiment failure, not a skip: it returns exit status 2,
retains all planned outcomes as failed at `cuda_preflight`, and writes no completed GPU artifact.
The actual-CUDA test module is expected to execute without skips on the controller's hardware run.

The full repository suite reported `960 passed, 18 skipped, 20 warnings` in 293.19 seconds. The
seven Task 4 skips are itemized above; the other 11 are pre-existing optional predictive-GPU tests.
The warnings are pre-existing surface inducing-point and Rasterio deprecation warnings, not CuGen
pilot warnings. Full Ruff, frozen-contract, module-size, privacy, whitespace, and the mandatory
40-test smoke gates passed.

Separate local source-generation preflights exercised the `scale` and `precision` CLI cases through
their deliberate unavailable-CUDA failure. Scale retained all six planned outcomes, generated six
canonical 67,072-byte cap-sized sources with two identities (baseline versus held-out-mutated), and
marked all six `cuda_preflight` failures. Precision retained all three planned outcomes and produced
three identical 16,960-byte deterministic sources before the same explicit nonzero CUDA refusal.
These are source-generation/refusal checks, not device execution.

## Hardware evidence still required

No Task 4 pod was launched or contacted by this implementation worker. Before any admission claim,
the controller must run the source-only bundle and actual CLI/tests on one audited US/Canada GPU,
retain raw CPU/GPU numeric and timing failures as well as successes, retrieve and independently
verify all output hashes, and delete the task pod. The final report must record the executing commit,
CuGen allowlist, environment controls, installed distributions, device/driver/runtime identity,
per-repeat cold and warm intervals, memory semantics, maximum numerical errors, and held-out
invariance results.

Even if all hardware checks pass, this pilot does not establish source-specific real-genome access,
predictive AF improvement, new-region extrapolation, phased/haplotype estimation, a valid joint
covariance matrix, expanded scale, or publication eligibility. Those remain WP6 follow-up gates.

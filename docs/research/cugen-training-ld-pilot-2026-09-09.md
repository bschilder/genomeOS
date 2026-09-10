# CuGen training-only LD synthetic pilot — corrected-source hardware evidence

**Status:** the bounded synthetic hardware-admission checks passed for CuGen revision
`b95adbaabef1ca5ff2795b9435e9bb7d6aebb9a1` at corrected genomeOS commit
`b46c9596c26aa978da28f77f40299af5f82fd55b`. This admits only the tested pairwise-complete,
unphased ALT-dosage correlation behavior. The earlier run at genomeOS commit
`50e583a06d772c21d1bf81f3b814ba0fd4947761` remains below as historical review rationale and cost,
not as proof of the corrected source.

## Scientific and engineering contract

The tested claim is narrow: pinned CuGen can correctly identify and calculate bounded synthetic
training-call correlations. Acceptance requires exact identities and counts, absolute R error at
most `1e-5`, absolute R2 error at most `2e-5`, complete requested-pair reconciliation,
independently decoded subset calls and statistics, and held-out mutation invariance.

The engineering surface is an offline synthetic CLI over the public verified CuGen loader and
`run_cugen_pilot`. It generates no user-supplied or real genotypes. Missingness remains dosage value
3, undefined pairs remain explicit refusals, and the workflow runs the independent reference plus
both CuGen CPU and GPU backends. It is an admission workflow, not a GPU-only production path.

## Experiment cases

| Case | Synthetic source | Training partition | Purpose |
|---|---:|---:|---|
| `hand` | 8 samples × 7 variants | reordered 4-sample training set | hand-derived signs, missingness, invalid states and non-PSD pairwise counterexample |
| `scale` | 4,096 × 64 | 3,072 train / 512 held out / 512 excluded | fixed pilot caps, all 2,016 unordered pairs and held-out mutation control |
| `precision` | 4,096 × 16 | all 4,096 training | n=3,072/4,096, overlapping/disjoint near-fixed calls and original/double-flipped coding |

The CLI used seed 42 and three repeats. Hand and scale scheduled a baseline and held-out-mutated run
for each repeat; precision scheduled one baseline per repeat. Each planned execution wrote a
separate immutable artifact directory, and each `experiment.json` accounts for every planned run.

## Review correction and report schema

Ordinary tests no longer depend on an untracked absolute controller checkout. Clean-checkout CLI
contracts use an explicit unavailable source to verify deterministic planning and complete retained
failure accounting. Checks that require actual pinned CuGen source read `CUGEN_ROOT` and skip
explicitly when that qualified root is absent; actual CUDA execution additionally requires the
executing genomeOS revision.

Planning now records `cold=true` only on the first invocation in process order while retaining the
independent integer `repeat` and boolean `held_out_mutated` fields. For hand and scale, the later
repeat-0 held-out-mutated run is therefore machine-labeled warm rather than merely interpreted that
way in prose.

The experiment report now records these separately scoped top-level intervals:

| Field | Scope |
|---|---|
| `startup_seconds` | `main()` entry through argument parsing, in-main imports, case construction, planning and output/report initialization; excludes interpreter-before-main time |
| `source_load_seconds` | verification and import of the exact qualified CuGen source; later genomeOS revision and executing-file hash collection is outside this interval |
| `cuda_preflight_seconds` | CuPy/device discovery, selection, synchronization and recorded hardware/environment identity |

The corrected `measurement_scope.startup` value is
`main_entry_through_argument_parsing_imports_case_construction_planning_and_output_initialization`.
No startup value is inferred for the earlier hardware run, which predates this field.

## Corrected-source execution audit

Pod `83og5j5yjkxbm8` ran the exact pinned name and image in `US-MD-1` at `$1.59/hour`. It was
created at `02:00:25Z`; deletion returned HTTP 204 and a subsequent lookup returned 404 at
approximately `02:09:25Z`. Elapsed-time arithmetic estimates a `$0.24` rerun charge, not an exact
billing record. Together with the historical `$0.56` estimate, the two-cycle estimate is `$0.80`.
An unrelated scorer owned by the root workspace neither delayed nor altered the pod.

The corrected genomeOS source-only bundle contained 14 committed files from
`b46c9596c26aa978da28f77f40299af5f82fd55b`; its tar SHA-256 was
`a6653ed046c99e95418a3e589bb819e0526aff649903fe9b2f6a71a519b240b5` and compressed SHA-256
was `2186c51ec38250649065cc46ff3b7889bc82e8402f7dff4473fb3e245b428cd0`. The CuGen bundle
contained the exact 37-member allowlist at the pinned revision; its tar SHA-256 was
`b0c08ab99910ecfd7a6cdbfb3d63592cc8c099e567fa531c4afe375a97f9cb1f` and compressed SHA-256
was `994196c56a6ab1837c89d4234b9c7ae08c4e7067eb03f71e22a98484731ae0c8`.

No Git history, credentials, private files, or real genotypes were uploaded. The retrieved aggregate
archive SHA-256 was `981a152d187205391c270d8884a13d09c163cdf2d535d360a6c831200b10c569`.
All 138 files in its checksum manifest were independently reverified after retrieval. Raw outputs
remain outside Git.

## Corrected-source hardware and environment

| Property | Recorded value |
|---|---|
| Device | NVIDIA A100-SXM4-80GB, 81,920 MiB |
| Host driver | 580.126.16 |
| CUDA image | 12.8.1 |
| Python | 3.12.3 |
| CuPy | 14.2.0 (`cupy-cuda12x`) |
| CuPy runtime / driver API values | 12090 / 13000 |
| Numeric controls | `CUPY_TF32=0`, `NVIDIA_TF32_OVERRIDE=0`, `USE_PINNED_READER=0` |

Exact installed distributions were `cuda-pathfinder==1.8.1`, `cupy-cuda12x==14.2.0`,
`iniconfig==2.3.0`, `numpy==2.4.6`, `packaging==26.3`, `pandas==3.0.5`, `pip==24.0`,
`pluggy==1.6.0`, `pyarrow==25.0.1`, `Pygments==2.21.0`, `pytest==9.0.2`,
`python-dateutil==2.9.0.post0`, `scipy==1.18.1`, and `six==1.17.0`.

## Corrected-source hardware results

All seven actual-CUDA tests passed in 13.26 seconds. They emitted 84 unsuppressed upstream
`Pandas4Warning` instances from CuGen's `astype(..., copy=False)` call, tracked in #201; the
warnings did not suppress or replace a test result.

| Case | Completed / planned | GPU pair reconciliation | Held-out invariance | `cold=true` runs |
|---|---:|---|---|---:|
| `hand` | 6 / 6 | 6 observed + 15 explicitly invalid = 21 requested, every run | 3 / 3 passed | 1 |
| `scale` | 6 / 6 | 2,016 / 2,016 observed, every run | 3 / 3 passed | 1 |
| `precision` | 3 / 3 | 15 / 15 observed, every run | not applicable; all samples train | 1 |

All CPU and GPU validations passed, with zero failed planned runs. Across all corrected runs, the
maximum absolute GPU discrepancies from the independent reference were:

| Quantity | Maximum absolute error | Required limit |
|---|---:|---:|
| MAF | `1.9868214962137642e-8` | identity/statistics check |
| R | `2.7423209814081417e-8` | `1e-5` |
| R2 | `6.39536562596632e-8` | `2e-5` |

Startup, source loading and CUDA preflight were measured separately in each fresh CLI process:

| Case | Startup (s) | CuGen source load (s) | CUDA preflight (s) |
|---|---:|---:|---:|
| `hand` | 0.4354434600 | 0.2191 | 0.7840 |
| `scale` | 0.4444814241 | 0.2181 | 0.7013 |
| `precision` | 0.4043588000 | 0.2221 | 0.8747 |

The following are synchronized LD-stage intervals and complete admission-workflow intervals, not an
end-to-end GPU speedup. The full workflow includes subset validation, the independent reference,
both CPU and GPU backends, reconciliation, artifact writing, and completed-reader verification.

| Case | Invocation group | CPU LD (s) | GPU LD (s) | Full admission workflow (s) |
|---|---|---:|---:|---:|
| `hand` | first process invocation | 0.0117 | 0.0862 | 0.3372 |
| `hand` | subsequent five | 0.0087–0.0090 | 0.0119–0.0123 | 0.0459–0.0477 |
| `scale` | first process invocation | 0.0673 | 0.2183 | 5.3134 |
| `scale` | subsequent five | 0.0535–0.0563 | 0.0105–0.0125 | 4.7638–4.8678 |
| `precision` | first process invocation | 0.0123 | 0.1074 | 0.5744 |
| `precision` | subsequent two | 0.0098–0.0099 | 0.0178–0.0179 | 0.1760–0.1761 |

The corrected machine-readable schedule has exactly one `cold=true` run per case, always the first
baseline invocation. These bounded synthetic timings are descriptive pilot measurements, not
production throughput or scaling claims.

Peak observed process RSS was 655,753,216 bytes. The largest retained device-pool reading at a
stage boundary was 2,362,368 bytes. The RSS number is an observed process high-water mark; the
device number is a used/retained pool snapshot at an observer boundary, explicitly not total CUDA
memory or a within-stage peak.

## Historical first-run provenance and execution audit

The controller first attempted the requested A100-SXM4-80GB in `US-NY-1` and `US-NJ-1`; neither had
capacity. Pod `x274644i80dnwy` then ran in `US-MD-1` with the required pinned name and image. It was
created at `2026-09-10T00:47:32Z`. Deletion returned HTTP 204 and a subsequent lookup returned 404
at approximately `2026-09-10T01:08:37Z`. At `$1.59/hour`, elapsed-time arithmetic estimates a
`$0.56` charge; this is not an exact billing record.

The official checksum-pinned RunPod encrypted transfer path was used after an HTTP-port approach
was rejected. The genomeOS source-only bundle contained 14 committed files from the executing
commit; its uncompressed tar SHA-256 was
`89543080efa097607668879c922735ecc80b7f5437cd758eed20c4eb4ae94926` and compressed bundle SHA-256
was `f8d9e5f99fd40e3e7e9ef0c6e307ae694abe5090f04de37784890d57656c2fc9`. The locally
prevalidated CuGen bundle contained the exact 37-member allowlist at the pinned revision; its tar
SHA-256 was `b0c08ab99910ecfd7a6cdbfb3d63592cc8c099e567fa531c4afe375a97f9cb1f` and compressed SHA-256
was `cafb273901c9ea0fe265bbb3943f28c7298f989936e1bc04d85efb77f473fbd3`.

No Git history, credentials, private files, or real genotypes were uploaded. The retrieved aggregate
archive SHA-256 was `c17e0fb0c62c9b811e36e47095dbdf08263be09c71bab9e897e3ecbac2bb6363`.
All 138 files listed in its internal checksum manifest were independently verified after retrieval.
Raw artifacts remain outside Git.

The shared loader verified all 37 CuGen files before import. Imported provenance included
`cugen/__init__.py`, `cugen/write.py`, `cugen/subset.py`, and `cugen/ld.py`. Synthetic sources were
validated before the public `write_cugen(..., encoding=0, gidx=...)` call and independently decoded
afterward.

## Historical first-run hardware and environment

| Property | Recorded value |
|---|---|
| Device | NVIDIA A100-SXM4-80GB, 81,920 MiB |
| Host driver | 580.126.16 |
| CUDA image | 12.8.1 |
| Python | 3.12.3 |
| CuPy | 14.2.0 (`cupy-cuda12x`) |
| CuPy runtime / driver API values | 12090 / 13000 |
| Numeric controls | `CUPY_TF32=0`, `NVIDIA_TF32_OVERRIDE=0`, `USE_PINNED_READER=0` |

Exact installed distributions were `cuda-pathfinder==1.8.1`, `cupy-cuda12x==14.2.0`,
`iniconfig==2.3.0`, `numpy==2.4.6`, `packaging==26.3`, `pandas==3.0.5`, `pip==24.0`,
`pluggy==1.6.0`, `pyarrow==25.0.1`, `Pygments==2.21.0`, `pytest==9.0.2`,
`python-dateutil==2.9.0.post0`, `scipy==1.18.1`, and `six==1.17.0`.

## Historical first-run hardware results

All seven actual-CUDA tests passed in 12.98 seconds. They emitted 84 unsuppressed upstream
`Pandas4Warning` instances from CuGen's `astype(..., copy=False)` call, tracked separately in #201;
the warnings did not suppress or replace any test result.

| Case | Completed / planned | GPU pair reconciliation | Held-out invariance |
|---|---:|---|---|
| `hand` | 6 / 6 | 6 observed + 15 explicitly invalid = 21 requested, every run | passed in all 3 baseline/mutation comparisons |
| `scale` | 6 / 6 | 2,016 / 2,016 observed, every run | passed in all 3 baseline/mutation comparisons |
| `precision` | 3 / 3 | 15 / 15 observed, every run | not applicable; all samples are training samples |

Every CPU and GPU validation passed, with zero failed planned runs. Across all cases and repeats,
the maximum absolute GPU discrepancies from the independent reference were:

| Quantity | Maximum absolute error | Required limit |
|---|---:|---:|
| MAF | `1.9868214962137642e-8` | identity/statistics check |
| R | `2.7423209814081417e-8` | `1e-5` |
| R2 | `6.39536562596632e-8` | `2e-5` |

The following are synchronized stage intervals and complete admission-workflow intervals, not an
end-to-end GPU speedup. The complete workflow includes subset validation, the independent reference,
both CPU and GPU backends, reconciliation, artifact writing, and completed-reader verification.

| Case | Invocation group | CPU LD (s) | GPU LD (s) | Full admission workflow (s) |
|---|---|---:|---:|---:|
| `hand` | first process invocation | 0.0118 | 0.0903 | 0.3472 |
| `hand` | subsequent five | 0.0087–0.0088 | 0.0118–0.0120 | 0.0456–0.0475 |
| `scale` | first process invocation | 0.0604 | 0.2172 | 5.1690 |
| `scale` | subsequent five | 0.0533–0.0563 | 0.0109–0.0135 | 4.5618–4.8359 |
| `precision` | first process invocation | 0.0120 | 0.1015 | 0.5708 |
| `precision` | subsequent two | 0.0096–0.0097 | 0.0171–0.0173 | 0.1728–0.1767 |

In the historical raw schedule, `cold` incorrectly labels every repeat-0 condition. Only the first
invocation within each CLI process is a true process/library cold start, so the table includes the
later repeat-0 held-out-mutated execution for hand and scale among the subsequent warmed
observations rather than treating it as a second cold start. The corrected report will encode this
fact directly. These small synthetic timings are descriptive first-run measurements, not production
throughput or scaling claims.

Peak observed process RSS was 657,702,912 bytes. The largest retained device-pool reading at a
stage boundary was 2,362,368 bytes. The RSS number is an observed process high-water mark; the
device number is a used/retained pool snapshot at an observer boundary, explicitly not total CUDA
memory or a within-stage peak.

## Measurement boundaries and conclusion

The adapter emitted exactly one ordered start/end boundary for each of 12 stages: input validation,
source snapshot, CuGen import, subset, training validation, independent reference, CPU LD and
reconciliation, GPU LD and reconciliation, artifact writing, and completed-reader verification.
The external observer synchronized before and after subset and GPU stages. Report finalization was
outside the measured full-workflow interval.

The corrected-source evidence supports the bounded synthetic admission claim at the two pinned
source revisions and recorded environment. The historical first run remains review context only;
none of its results were substituted for missing corrected-source evidence.

This pilot does not establish predictive AF improvement, new-region extrapolation, source-specific
real-genome access, phased or haplotype inference, a valid joint covariance matrix, larger-scale
performance, portability beyond the recorded environment, or publication eligibility. Both cycles'
artifacts record `joint_covariance_admitted=false` and `publication_eligible=false`. These broader
claims remain WP6 follow-up gates.

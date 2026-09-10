# Minimum B0H calibration executor and reducer

Status: root personally reviewed, corrected and adopted for detailed planning.
Implementation awaits personal plan review; this is not launch admission.
Advances #211/#189; Atlas design §§5,7–8,12. The tracked 2026-09-10 SBC,
generation, attempts, quantities, summaries and codec specifications govern.

## 1. Scientific and engineering contract

Claim: the actual B0H computation respects its declared posterior and marginal
predictive law across independent simulated datasets, with sensitivity to ignored
counts and destroyed pairing. Non-rejection is not equivalence or geographic validity.
Acceptance: account for all 1,938 planned records, all actual calls and failures;
evaluate the twelve correct-run rank tests and four predeclared control assertions
at full N512 per prior, and report boundary/shared-history stress separately.
Components: a fixed offline campaign manifest, immutable local record adapter,
case executor using existing public science, and pure study reduction over typed
evidence. These are validation interfaces, with no serving or production-schema change.
Assumptions/refusals: pinned source/runtime, verified float64 and explicit backend;
independent datasets are units, not chains, paired tracks or heldout targets.
No redraw, refit of a known outcome, implicit scientific retry, precision/backend
fallback, missing-value invention or success inferred from an exit code.
Consumers: the scientific evidence report and later unchanged B0 comparison;
this campaign alone grants no clinical, global, spatial or real-data eligibility.

## 2. Fixed campaign and minimum operational policy

Freeze protocol `b0h_sbc_v1`, reviewed source revision/content digest, dependency
lock and actual environment fingerprint, runner/codec versions, explicit CDF
backend, runtime/device/float64 evidence, storage-admission receipt, complete
ordered case manifest and disjoint worker assignments before generation.
Use `enumerate_sbc_cases()` unchanged: order is (study,case,replicate,track),
although `SbcCaseId` constructor field order is (track,study,case,replicate).
The manifest has 1,024 prior, 768 fixed, 128 shared-history, two structural and
16 exact-boundary records: 1,938 total, 1,936 initial-fit slots, at most 1,936
convergence-only retry slots. Failures reduce actual calls, never planned totals.
Paired stress records share generation track99 and count data; they retain two
distinct fitted-track identities and are not independent replicates.

Each assigned case executes independently; scheduling cannot choose cases,
priors, seeds or diagnostics from observed results. The minimum measured basis
supports one worker on one GPU. A larger worker count requires a separately
frozen scheduling/memory measurement and explicit assignments before launch.
The first campaign uses one worker; it can continue untouched cases after a
recorded case failure when storage/runtime integrity remains valid. There is no
managed retry queue, timeout-based ownership transfer, hidden process restart,
lease renewal, cross-Pod recovery or optional recovery strategy abstraction.

There is one operational delivery for each scientific stage/attempt. Once START
is published, that slot cannot acquire another delivery. Matching completed
records are loaded and reused; a live owner can finish publication using the
same retained bytes. An unstarted dependent stage may start after validating its
completed prerequisites. An ambiguous START-only owner loss remains unresolved;
it receives no replacement call and permanently bars unconditional campaign success.
Scientific attempt1 remains distinct and requires a completed actual attempt0
`convergence_failed` result. Owner loss alone never admits attempt1.

Compatibility: the tracked SBC requirement to “resume matching immutable records
without overwriting” and distinguish infrastructure restart from scientific retry
is retained through reuse and continuation of provably unstarted stages/cases.
No tracked text inspected requires operational delivery1. Root supersedes the
historical, unimplemented two-delivery policy: one delivery reduces operational
states; ambiguous lost calls remain unresolved rather than being repeated.

## 3. Typed contracts and responsibility boundaries

All new contracts are closed, versioned and immutable; no arbitrary extension
maps, caller-selected imports, dynamic scientific deserialization or private helpers.
Names below specify architectural interfaces; the later plan freezes field-level
wire grammar and signatures before code, not after actual study execution.

| Boundary | Typed public input/output and owned responsibility |
| --- | --- |
| `CampaignManifest` | Version/protocol/source/lock/runtime identities, frozen `cupy`, codec limits, admission receipt, prepared null digest, ordered `SbcCaseId` tuple and exact worker assignment; no scientific override fields |
| `StageKey` | Campaign digest, case, closed stage (`generation`, `structural`, `fit`, `quantities`, `summary`), attempt0/1 only where applicable; structural/generation have no invented fit attempt |
| `StageStart` | Key, assigned worker, actual owner identity, exact prerequisite receipt digests, source/runtime/backend binding, actual timing origin; exclusive admission to one call |
| `EvidenceReceipt` | START digest, exact codec metadata digest/length, ordered payload digest/length set and returned root type; contains no synthesized science |
| `StageExecutionFailure` | START digest, actual failing adapter phase, qualified exception class and literal message; a propagated execution defect, not an invented scientific result |
| `StageCompletion` | START digest, exactly one receipt or execution-failure digest, actual whole-call elapsed nanoseconds and labeled observations if obtained; completion means accounted outcome, not scientific acceptance |
| `OwnerLoss` | START digest, actually observed loss/exclusion evidence and surviving receipt references; unresolved attribution, never proof a call did not return |
| `CaseEvidence` | Manifest case plus ordered validated stage records and existing public evidence roots; missing/unstarted/lost stages explicit |
| `StudyReduction` | Manifest/snapshot identities, case/attempt/status accounting, twelve correct tests, four control decisions, all other control results, descriptive rows and claim eligibility reasons |

`execute_b0h_case(manifest, case, store)` owns admission, public calls and receipts;
`load_b0h_case(manifest, case, store)` owns integrity and dataset-bound restoration;
`reduce_b0h_study(manifest, cases, null_reference)` is pure, accepts immutable
typed inputs and produces `StudyReduction`. One concrete local SQLite store supplies
exclusive START publication, exact-byte evidence publication, completion and reads.
Its public methods exchange the named records and `EncodedB0HEvidence`; callers
do not reach into its paths or locks. A thin offline command composes these parts.
Keep contracts, filesystem adapter, executor and reducer separate responsibilities,
targeting the repository module budget; no plugin registry or general workflow engine.

Use `encode_b0h_evidence`/`decode_b0h_evidence` and explicit `B0HCodecLimits`
unchanged for every scientific root. Null/test and execution records are outside
the codec's closed seven-root union; their small, fixed versioned envelopes need
explicit serialization, not a widening of the scientific codec or type registry.
Preserve exact integer seeds, signed zero and permitted nonfinite failure/score
values. Receipt hashes anchor metadata as well as payloads; codec hashes alone
cannot detect a self-consistent metadata rewrite or authenticate an invocation.
Missing timing/resource observations have an explicit unavailable reason; never
derive a call duration from filesystem timestamps. Separate startup, preflight,
whole public calls and storage/collection time; no isolated JIT-time claim.

## 4. Lifecycle, call counts and retained outcomes

Before any stage call, validate assignment, manifest/runtime, prerequisites,
existing records and absence of a prior START. Acquire exclusive campaign ownership,
publish and confirm START, then call the exact public entry point once.
The single worker holds a stable campaign-wide process lock across these calls;
no database transaction stays open during scientific computation.
Planning/identity/admission errors occur before the science call and are reported
as adapter refusal. Never fabricate a realized `GenerationFailure` or `AttemptError`.

1. Call `generate_sbc_case(case)` once per track-specific case. Thus an intact
   campaign has 1,938 generation calls, including two no-RNG structural returns.
   Paired stress calls intentionally repeat the unchanged generator using shared
   generation identity; compare retained generation content excluding fitted case
   identity, without rewriting either result. Any discrepancy is an integrity defect.
   Retain `GeneratedDataset`, `AllUnavailableDataset` or `GenerationFailure`.
   Generation failure is terminal for that case, with zero fitter/diagnostic calls;
   a propagated exception is a distinct execution failure, never a redraw.
2. For `AllUnavailableDataset`, call `exercise_unavailable` once, retaining every
   `StructuralCheckResult`. It invokes the public fitter once to exercise refusal,
   with zero expected graph/sampler entries. No fit seed, attempt, heldout, ranks
   or summary is invented. `expected_sampler_calls=0` is not measured call evidence.
3. For `GeneratedDataset`, call `plan_fit_attempt(..., attempt_id=0)` then
   `run_fit_attempt` once. Store every status, actual error, rejected typed fit or
   returned-type evidence. Only after immutable completion of actual
   `convergence_failed` attempt0, admit `plan_fit_attempt(..., attempt_id=1)` and
   one `run_fit_attempt`. Retry uses its original doubled budget and declared seed.
   No attempt2; failed/identity-rejected/structural/numerical/operational outcomes
   cannot authorize retry. An accepted retry retains attempt0 and consumes only
   its own `(4,1000,1)` draw arrays, never concatenated initial/retry draws.
4. For the accepted attempt of study0 only, call `selected_sbc_quantities` once.
   Retain selection identities, four paired indices, prior-control prefix/failure,
   scalar quantities, raw reference components, comparison matrices and all 18
   rank states. Never recompute h, change orders, reinterpret a near tie or select
   replacement points in the executor/reducer. Full-chain h ESS/MCSE stay not_computed.
5. For every accepted attempt in studies0/1/2/4, call
   `summarize_heterogeneity_fit(..., cdf_backend=manifest.cdf_backend)` once,
   after the quantities stage for study0. Retain parameter summaries even with a
   returned predictive failure. A recorded quantities execution failure does not
   suppress this independent summary call, provided accepted fit integrity holds.
   The summary owns its one predictor call and, if admitted, one diagnostics call;
   do not call either again from the executor. Structural/failed fits get neither.
6. Publish every returned root through the codec and store before advancing its
   dependent stage. Ordinary propagated exceptions become actual stage-execution
   failures. Codec/storage errors retain their adapter classification and do not
   become science failures; keep known evidence live for same-byte publication.
   BaseException/process loss is unresolved if no exact result survives. No
   reconstruction of unavailable partial outputs or guessed RNG consumption.

Healthy no-retry totals: 1,936 fit-attempt calls, two structural public-fitter
refusal calls, 1,024 selected-quantity calls and 1,936 summary calls. Scientific
slots, public-wrapper calls and actual internal sampler calls are distinct counts.
Full arrays and diagnostics travel with actual attempts; diagnostic outcomes do
not replace those arrays. Public `require_fit_identity` guards restored accepted
fits against their exact retained dataset/spec before any downstream consumption.
Also bind quantities/summary specs, selected points/indices, truth and targets to
their referenced retained dataset/fit; validate exact public fields without
re-running ranks, reference integration, prediction, RNG or summary algorithms.

## 5. Storage receipt, reuse, loss and integrity

Use one standard-library SQLite database on a verified local filesystem. Store
exact codec bytes as BLOBs, not narrowed SQL floats or seed integers. Logical
records are immutable INSERT-only rows with unique identities; never UPDATE,
DELETE, REPLACE or ignore a conflicting insert. The database file itself grows.
Freeze `journal_mode=DELETE`, `synchronous=EXTRA`, explicit transactions and
foreign-key enforcement; verify the actual connection settings. EXTRA adds the
journal-directory sync to FULL in DELETE mode. This is a configuration choice,
not a measured power/Pod-loss guarantee. See [SQLite synchronous modes](https://www.sqlite.org/pragma.html#pragma_synchronous).

Commit START in its own transaction before a call. Commit the exact result or
execution failure, payloads, receipt and COMPLETE in one second transaction.
There are no external payload files or receipt-only partial-publication states.
A receipt without its completion is an integrity refusal. Atomicity is delegated
to [SQLite's transaction boundary](https://www.sqlite.org/atomiccommit.html),
subject to its filesystem assumptions. Retain the campaign process lock through
the call; SQLite's short transaction lock is not sufficient scientific ownership.

Existing identical complete evidence is reused after full identity/hash/codec
validation, with zero scientific calls. Conflicts, unknown versions, missing
payloads, wrong dependencies and unexplained stages refuse, never mean absent.
After uncertain live publication, inspect transaction state and read back exact
completion; a retained live result can retry only its same-byte publication.
An uncertain START commit admits no call until its exact state is established.
Do not treat a SQLite exception as proof that a transaction did not commit.
Storage that cannot be inspected stops execution; preserve the known live result.

A typed `PendingPublication` carries that exact immutable live packet to its
caller. The CLI pauses all science, retries only publication reconciliation
every60 seconds for at most1800 seconds of monotonic elapsed time, and retains
the same packet/call timing throughout. Only retryable storage I/O/locking
failures qualify, with transaction state established before writes; integrity,
identity and programming errors do not. No fit or diagnostic call is repeated.
On expiry or explicit interruption, report unresolved publication and exit
nonzero; the surviving START remains unresolved. This is bounded in-memory
retention, not durable recovery. No emergency payload file or interactive control
framework is added. API callers may keep the pending packet alive independently.

After confirmed process loss, START without COMPLETE is terminal unresolved,
even if loss occurred before the call. It receives no redelivery. Acquiring a
released process lock does not erase START or prove the call did not return.
Unstarted stages can continue from completed prerequisites under identical
campaign identities. No elapsed-time owner takeover or last-writer-wins result.

Final reduction uses a quiescent, consistently closed database and an immutable
inventory listing every planned case and all observed stage digests, including
missing/lost/conflicting evidence. Retain its digest independently at collection.
Never copy a live database without a supported consistent snapshot mechanism;
the first campaign needs only closed-store collection, not online backup support.
Rerunning pure reduction has no scientific-call effects. Self-consistent hashes
do not authenticate an invocation or protect against rewriting the entire store.

## 6. Full-study reduction and meaning of decisions

Validate exact manifest membership, ordering, uniqueness and all receipt chains.
Always output 1,938 case-accounting entries and planned-versus-actual fit counts.
Retain generation, convergence/retry, identity, prediction, reference, ordering,
calculation, execution, storage and owner-loss outcomes separately. A terminal
failed record is accounted evidence; it is not a successful calibrated case.

Prepare the campaign null through existing `simulate_rank_null(sample_size=512,
replicates=100000, seed=1653499886)` with its frozen entropy provenance and retain
`RankNullReference`, not just p-values. Require one matching complete null record
before freezing the campaign manifest or executing a case; a failed preparation
admits zero case calls. Seeded deterministic null preparation/reduction can be
repeated from identical inputs without invoking generation, fits or case diagnostics.
Reuse identical published bytes and refuse
conflicts. This is not operational redelivery of a scientific case stage.
Use `test_rank_uniformity` unchanged.
For each track and six quantities, only a complete 512-rank correct-mode vector
admits a full-family decision: raw p and existing Bonferroni-adjusted p retained,
rejection at raw p<=.05/12. Missing/unresolved ranks produce no full-N p-value.
For each track, prior-only quantity3 and cyclic-pairing quantity5 must each reject
at the same .05/12 threshold. These four assertions have their separately stated
budget; retain all other control quantities without post-result witness selection.
A missed or uncomputable control limits sensitivity; it is not evidence that the
correct fitter failed. Correct-family rejection is separately identified evidence
of discrepancy. Neither a missed control nor a rank failure is calibration rescue.

Unconditional claim eligibility requires no unresolved campaign outcomes, complete
planned evidence, no rejection in the twelve-test family and all four detected
controls. An authorized attempt1 may supply its case's accepted result; retained
attempt0 convergence failure is not erased or automatically an unresolved outcome.
Any owner loss precludes unconditional success. Completed predictive failures and
missing required diagnostics also preclude it; secondary coverage/error
values themselves are descriptive, with no added coverage threshold or success gate.
The permitted wording is only “no discrepancy detected at this design's resolution.”

Conditional rank plots retain actual per-track/mode/quantity N and failure counts,
without optional conditional p-values or extra null simulations in this runner.
They are descriptions and never substitute for N512 or rescue a claim; N0 has no test.
Retain per-case parameter/PIT/50–80–95% coverage/width/proper-score/error rows;
report descriptive averages with actual denominators and failed counts by study,
case, track and target kind. Preserve valid negative-infinite log scores explicitly.
Study1 N16 cells are descriptive; study4 repeats are degenerate boundary-support
stress. Study2 `shared_cluster0` and `fresh_cluster` remain separate, with shared
history and paired-track dependence labels. No pooling them into independent N.

## 7. Literal acceptance examples required in the later plan

- Fresh accepted prior case: generation1/fit1/quantities1/summary1; reloading its
  complete records adds zero calls. Fresh accepted stress:1/1/0/1.
- Actual convergence failure then accepted retry:1/2/1/1 for a prior case;
  attempt0 complete precedes attempt1 START. Only retry indices/draws feed diagnostics.
  Runtime failure, rejected identity, generation failure and owner loss admit zero retries.
- Structural case: generation1, structural-wrapper1, public-fitter1, graph0,
  sampler0, quantities0, summary0. Unexpected structural return is retained, not accepted.
- Admission failure before START: zero calls. Confirmed START then crash before call,
  during call, or after return before receipt: no redelivery and unresolved status.
  Result transaction commits then acknowledgement is lost: reload with zero calls.
  Inject receipt without COMPLETE: integrity refusal, no repair or invocation.
- Live publication failure after a known result: republish identical bytes without
  refit. Concurrent claimants: exactly one START/call; stale owner cannot erase it.
- Flip one payload byte; rewrite metadata without updating externally anchored receipt;
  remove a payload; add an orphan retry; swap two equal-total datasets or track IDs;
  reorder shared heldouts or selected mean/rho pairing: refuse, never regenerate.
- Literal rank counts(103,103,102,102,102) sum512 and give T6; counts(512,0,0,0,0)
  give T2048. A literal mock null with99999 lower values and one equal value yields
  p=2/100001 and adjusted p=24/100001, testing inclusive comparison, not real calibration.
- 511 valid ranks plus one unresolved h ordering yields no N512 decision. A conditional
  N511 reference cannot be used for the full family. N0 refuses testing.
- Twelve non-rejections plus one missed control: sensitivity-limited, not a correct-
  fitter rejection; twelve non-rejections/four detections plus owner loss: no
  unconditional claim. Never fill a missing case with an otherwise valid duplicate.

## 8. Backend choice, launch facts and tradeoffs

Root freezes CuPy for the full campaign, subject to actual runtime admission.
Existing numerical/backend work supports that implementation;
the eight-case timing evidence found complete summaries on both backends, identical
saved parameter/predictive arrays and at most6.161737786669619e-15 PIT difference.
Repeated CuPy summaries had median .430s versus13.304s for SciPy in that fixed order;
first CuPy call cost43.609s. This motivates an engineering choice, not a new tolerance,
general parity/speedup guarantee or selection between scientific priors/results.
Freeze one backend before results; failure never triggers alternate-backend rescue.

The timing result8fb80bd/PR226 concerns eight ordinary prior cases on one A100 only.
It measures no full-study calibration, stress tail, concurrent throughput, filesystem
durability or current capacity. Before launch observe actual US/CA capacity and cost,
source/runtime/driver/device identities, CPU/GPU and float64 behavior, storage type,
mount/options and required publication/exclusion/flush behavior, scratch/disk capacity,
memory headroom including all libraries, collection checksums and ownership/cleanup.
An advertised mount or allocator snapshot cannot establish those facts. Any future
probe is separate platform admission, not a science change or power-loss certificate.

Single delivery minimizes states and prevents repeat work, at the cost of losing
conditional diagnostic output for ambiguous owner loss. Historical two-delivery
policy could recover one such output with the same seed, but still barred
unconditional success and required extra loss/admission/conflict states. A managed
automatic-retry queue adds duplicate-delivery ambiguity and cannot itself enforce
science retry rules or turn unknown outcomes into valid N512 evidence. None changes
sample sizes, seeds, convergence gates or the public numerical methods.

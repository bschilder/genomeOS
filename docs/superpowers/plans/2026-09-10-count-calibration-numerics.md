# Count-calibration numerical repair

Follow-up to the reference-count baseline, prompted by empirical failures at
`fabbf53`; [#209](https://github.com/bschilder/genomeOS/issues/209), advancing #189.
Atlas design §§7–8. Use subagent-driven development and test-driven development.
This is a new empirical bug task, not a repeated whole-branch review fix wave.

## Scientific contract

1. **Objective:** preserve the declared count distribution in its cumulative
   probabilities and randomized calibration, and retain every failed evaluation.
2. **Acceptance evidence:** independently calculated synthetic probabilities,
   both allele orientations and mixture checks, unchanged existing analytical
   and tiny-tail regressions, explicit numerical refusal tests, and complete
   failed-fold output tests. Reexecute all twelve frozen development runs after
   the correction; compare no model using the failed attempt as if it completed.
3. **Component/interface:** pure `CountPredictive` CDF calculations and the
   benchmark diagnostic validation boundary, consumed by the two offline
   research benchmark runners. No observation schema or serving changes.
4. **Assumptions/refusals/consumers:** preserve existing count and concentration
   work limits, the distribution, seed streams, priors, data and fold membership.
   Do not clip invalid values, loosen scoring bounds, substitute binomial
   semantics, hide failures, or turn the repair into a performance claim.

## Evidence and root cause to verify

The first four predeclared seed-42 runs contained two completed technical-QC
tracks and two failed ancestry-exclusion tracks. Each failed track had two PIT
values above one by approximately 4e-13 and 5.5e-13. The remaining eight runs
were not launched. Failed runs aborted during global summary validation and
therefore did not create their promised per-fold output artifacts.

`log_prob` already uses stable finite-product mass arithmetic. The CDF uses
log-beta finite sums of the shorter support tail. That tail need not have the
smaller probability. Switching tails only when its log sum becomes nonnegative
does not protect near-one sums that remain slightly negative. A read-only
synthetic diagnosis must independently confirm the failure before implementation.

## One bounded implementation task

Files in scope:

- `genomeos/validation/predictive.py`
- `genomeos/validation/predictive_cupy.py`
- `genomeos/validation/benchmark.py`
- `scripts/benchmark_reference_counts.py`
- `scripts/benchmark_allele_frequency.py`
- directly corresponding predictive, GPU, benchmark and CLI tests

- [x] Add failing synthetic CDF/PIT regressions with an independent standard-
  library Decimal or exact-rational oracle. Use invented inputs, not real panel
  rows. Check the complementary orientation and a mixture; preserve the tiny
  lower-tail and large-support-short-tail cases. Report exact RED commands.
- [x] Add a failure-accounting regression: inject an invalid diagnostic frame
  into one fold, then require a nonzero completed report, an explicit failed
  fold with reason, no prediction rows from that fold, all planned identities,
  and successful later folds. Cover both existing research runners.
- [x] Correct the tail choice in CPU and CuPy implementations consistently.
  Prefer directly summing the small-probability complement when the initially
  shorter tail is near one (a one-half crossover is a deterministic algorithmic
  choice, not a fitted parameter). Maintain bounded temporary arrays, exact
  boundary semantics, explicit numerical-domain refusal, and no CPU fallback
  for an explicitly requested CUDA backend. If diagnosis shows a larger change
  is required, report evidence before expanding this task.
- [x] Expose the existing diagnostic validator as a narrow public benchmark
  boundary, validate its input structure without mutating it, and reuse it in
  the summary and inside each runner's per-fold handler before global rows are
  appended. Keep one set of range/finite/coverage rules and legitimate negative-
  infinite log scores. Invalid output must not become a completed fold.
- [x] Run focused tests and mandatory smoke, Ruff, contract, module-size and
  privacy gates. Inspect the exact staged paths/diff before a dedicated-branch
  fix commit referencing #209; preserve unrelated work and real local data.
- [x] Independent task review, including the numerical oracle and failure
  accounting; no broad unrelated cleanup. Address actual findings within the
  task review budget.
- [ ] Verify changed CuPy code on actual CUDA hardware with synthetic inputs
  and exact executed-source hashes. An unavailable device is not a passed test.
  This hardware check may run independently of the CPU empirical matrix.

## Controller empirical handoff

After code review, freeze the corrected source revision and rerun the unchanged
two-stage × two-count-kind × three-seed protocol, five folds and Beta(1,1), in
a fresh output parent. Retain the original attempted run directories and the
two terminal failure records. Inspect all twelve outcomes and every manifest;
do not choose data/folds/priors from their results. Record aggregate-only
evidence, full stable-source CI and the dedicated-branch PR. These runs remain
within-resource development checks, not resident-geographic or release evidence.

## Controller evidence (September 10)

Reviewed source `92659aa6999b04652fd0c3208c1e0836c96832a6` passed the full
CPU suite (963 passed, 17 CUDA-dependent skips, 15 existing warnings), all
mandatory gates, and the unchanged twelve-run real-data protocol. Every run
completed all five folds and passed the independent input/source/output,
training-posterior, membership and metric audit. See the
[aggregate report](../../research/reference-count-baseline-2026-09-10.md).

Actual CUDA acceptance is still pending: a task-owned A40 was provisioned, but
automatic approval review refused the source upload before execution. The pod
was deleted immediately; no source was uploaded or scorer checks run. The
specific source-only authorization was requested asynchronously. Keep this
hardware item open and the repair unmerged; local model work can proceed.

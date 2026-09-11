# Reference paired-report implementation plan

Use superpowers:subagent-driven-development task by task. This is the reporting
portion of #211 and #189, not permission to execute or alter the frozen fits.
Spec: ../specs/2026-09-11-reference-paired-report-design.md.

## Global Constraints

The spec's complete Global constraints and interface sections are binding.
Preserve all existing scientific source files and artifacts. New production
modules are pure; thin scripts own I/O. No new dependencies, real-data fits,
publication of real research records, remote resource operations, merge or
cleanup/deletion. User recovery instructions require retaining every workspace.

## Verification environment

Worktree: /private/tmp/genomeos-b0h-paired-report-20260911.
Base:26827fbd8cb0cb66ce9d6f93512ecc3fcd37ceeb.
Use /Users/bschilder/code/genomeOS/.venv/bin/python with PYTHONPATH set to this
worktree, PYTHONDONTWRITEBYTECODE=1 and isolated PyTensor/MPL/XDG caches under
/private/tmp/genomeos-paired-report-cache-20260911. Do not reinstall dependencies.
Run focused tests, scripts/smoke.py, Ruff, contract drift, module-size and privacy
gates for each task. Inspect staged paths and rerun privacy before each commit.
Full CI commands are required before PR delivery. Retain exact commands/results.

### Task 1: Pure, identity-checked paired publication report

Implement the spec's Pair interface and validation and all Global constraints in
new reference_comparison.py and, if separation is needed, a focused typed input
decoder module. Existing science, codecs, scorer and runner stay unchanged.
Tests live in tests/test_reference_comparison.py; a focused synthetic fixture
helper is allowed if readable and reused by subsequent tasks.

- [ ] RED: missing public function; independent hand-weighted metrics distinguish
  cell weighting from row pooling and correct RMSE from averaging roots.
- [ ] Cover matched complete pairs, one/both failed folds, disjoint completed
  folds, all failed, AN0 preservation, both prior tracks, exact identity/seed/
  count/dependency/split/label refusals, duplicates, corrupt publication hashes,
  malformed JSON/TSV, nonfinite diagnostics, every log-infinity contrast, and
  deterministic row order. Test valid failures separately from corrupt inputs.
- [ ] GREEN: implement the public pure report by reusing public artifact
  validation and benchmark aggregation. No private imports or new abstractions
  unrelated to the concrete pair. Preserve complete failure and support evidence.
- [ ] Run focused tests and all task gates. Self-review and commit new task files
  with a message advancing #211 (do not close the whole issue). Report exact
  commands, source/base/head, outcomes and concerns. Independent task review.

### Task 2: Complete-matrix local CLI

Implement the spec's Matrix CLI in scripts/compare_reference_counts.py with
tests/test_reference_comparison_cli.py, consuming Task1's public pair function.
The full literal matrix and absent-versus-corrupt behavior are in the spec.

- [ ] RED: subprocess fixture test for all24 rows and both exit states; reject
  duplicate/missing declarations, identity mismatch, partial/corrupt publications
  and existing output. Preserve literal IDs and deterministic report bytes.
- [ ] GREEN: thin local I/O, relative-path resolution, complete identity matrix,
  exclusive outputs, report and manifest-last fingerprints/provenance.
- [ ] Verify all Task1 and CLI tests and task gates, commit, independent review.

### Task 3: Reviewable comparison figure and delivery

Implement the spec's Figure script, synthetic example/PNG and a short public
usage note in docs/reference-paired-comparison.md. No real comparison is run.

- [ ] Generate a clearly synthetic full-matrix example including valid missing,
  failed/conditional and infinite/undefined contrasts; render every identity.
- [ ] Independently replay plotted finite values, statuses, units and all24 labels
  from report bytes. Visually inspect the PNG; retain source and output hashes.
- [ ] Run plot-focused verification, task tests and full repository CI commands.
  Commit synthetic figure and usage documentation, obtain task and whole-branch
  review, push the dedicated branch, and open a PR advancing #211/#189. Do not
  merge or delete the worktree/evidence. The main campaign remains incomplete.

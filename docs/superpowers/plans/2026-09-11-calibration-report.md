# Calibration reduction reporting implementation plan

Use superpowers:subagent-driven-development task by task.
Spec: ../specs/2026-09-11-calibration-report-design.md (binding in full).
Base: e20aed4b3ec199fc5d9960b8cdc804f264ffebd3, existing runner branch.
This delivers the requested calibration visualization; it does not execute,
change or admit the current study. Preserve every workspace and evidence file.

## Global constraints

All spec sections apply to both tasks. Existing science, reducer/serializer,
runner/collection, contracts, dependency declarations and frozen experiments
remain byte-identical. No live database, cloud operation, real-data access,
simulation, fitting, public research-result post, merge or cleanup. New files
only unless the controller approves a necessary documentation integration.
Use the existing environment with an explicit checkout PYTHONPATH and isolated
PyTensor base_compiledir plus compiledir, Matplotlib and XDG caches. No install.
Run focused tests and smoke, Ruff, contracts, module-size and privacy gates;
inspect staged paths and run privacy immediately before commits. Full suite runs
once on final reviewed source before PR; do not repeat unchanged full suites.

### Task 1: Canonical reduction decoder

Implement spec §2 in new genomeos/validation/heterogeneity_report.py, with
tests/test_heterogeneity_report.py and a small reusable synthetic fixture helper
tests/heterogeneity_report_fixtures.py if needed. Include spec §§1/4 safeguards.

- [ ] RED: import/public interface missing; actual reduction_bytes round trip.
- [ ] Test p-value bit preservation, all36rows/all1938cases, descriptive negative
  infinity and missing values, N511/N0, raw duplicate keys/nonfinite tokens,
  malformed versions/fields/bit strings, inconsistent membership/decisions/claim
  reasons, and canonical byte refusal. Verify no scientific computation occurs.
- [ ] GREEN: strict pure decoding through existing public types and serializer;
  no private imports or new scientific computation. Retain all data exactly.
- [ ] Run affected tests and all task gates; inspect staged paths/privacy, commit
  with a message advancing #211, self-review and provide complete RED/GREEN logs.
  Include the spec/plan in the first commit if not already tracked. Independent
  task review follows; do not dispatch a reviewer or another subagent yourself.

### Task 2: Offline graphics, reproducible demonstration and delivery

Implement spec §§3/4 in scripts/plot_b0h_calibration.py,
tests/test_plot_b0h_calibration.py, a deterministic
scripts/build_calibration_report_demo.py generator, both synthetic PNGs under
docs/figures/calibration_report_synthetic_{ranks,accounting}.png, and a focused
docs/calibration-report.md usage/interpretation note. Reuse Task1's public decoder;
tests may reuse its fixture helper. The generator uses public constructors and
does not import tests. Keep fixtures clearly authored, not executed evidence.

- [ ] RED: exact CLI input/hash/outputs/refusals and renderer data binding.
- [ ] GREEN: both tracks/all36rank rows, all1938case statuses in six panels,
  explicit missingness/roles/decisions, unchanged complete reduction copy,
  source/output hashes and final receipt. Existing outputs are never overwritten.
- [ ] Replay all artists/counts/labels against input, verify both output hashes,
  generate/view synthetic PNGs, and document exact commands and limitations.
- [ ] Run task tests and gates; privacy/staged inspection before commit; independent
  task review. The controller handles whole-branch review, final full CI, push and
  a stacked PR on feat/global-af-b0h-runner. Preserve worktree/evidence.

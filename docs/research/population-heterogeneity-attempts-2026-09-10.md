# B0H declared fit-attempt boundary — bounded implementation evidence

This note records engineering evidence for the one-call B0H fit-attempt
component specified in
`docs/superpowers/specs/2026-09-10-population-heterogeneity-attempts-design.md`.
It advances #211 and #189. It does not complete either issue or constitute a
population-heterogeneity calibration study.

## Implemented boundary

`genomeos.validation.heterogeneity_attempts` now provides the frozen
`FitAttemptSpec`, `AttemptError`, `FitAttemptResult`, and
`StructuralCheckResult` contracts; immutable ordered `FitIdentityError`
evidence; exact initial/retry planning; one explicit public fitter invocation;
lossless accounting for the declared known exception classes; returned-fit
identity refusal; and the real all-unavailable structural check.

The generated training tuple is forwarded unchanged, including AN=0 rows.
Accepted fits must match the planned config, single variant, exact four-chain
draw axes, lexical record IDs, sorted unique group IDs, unavailable IDs, and
positive-AN count totals. Unknown ordinary exceptions and `BaseException`
values are not converted into completed fit-attempt results. There is no hidden
retry, batching, posterior recomputation, clipping, or fabricated failed-fit
array.

The production generator and public fitter contracts were not edited. The
scoped change consists only of the new attempt module, its focused tests, and
this note.

## TDD and execution evidence

The test was written before the production module. The initial focused command
was:

```text
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor \
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python \
  -m pytest tests/test_heterogeneity_attempts.py -q -rA
```

The actual RED was the following captured collection-failure summary while the
module path did not exist:

```text
ERROR tests/test_heterogeneity_attempts.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

The implementation GREEN for the same command was `58 passed`. A subsequent
test-first immutability check initially failed because assigning
`FitIdentityError.mismatches` did not raise `AttributeError`; changing the
public field to a read-only property made it pass. The final focused suite,
including seed-collision and stricter malformed-error coverage, contains 60
passing cases.

Most focused fixtures use the real planner, constructors, identity guard, and
runner with a controlled replacement for the public fitter. These establish
the exact call count, argument forwarding, return preservation, exception
classification, and result-state behavior. Their artificial float64 posterior
arrays and diagnostics `(1.0, 200.0, 200.0)` are mock metadata; they are not
measured convergence evidence.

The two study-3 track fixtures leave the public fitter implementation real.
They pass all sixteen AC=AN=0 rows, observe the actual
`genomeos.validation.reference_counts.ReferenceInfeasibleError` with message
`training data have no available rows`, and install sentinels at `pm.Model`
and `pm.sample`. Both sentinels record zero calls. This is actual structural
refusal evidence before graph or sampler entry, not an actual NUTS fit.

## Verification recorded before the scoped commit

All commands used the locked interpreter and existing cache paths; no package
was installed or changed. For readability below, `LOCKED_ENV` denotes the
literal prefix actually used for Python test/runtime commands:

```text
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor \
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python
```

```text
LOCKED_ENV -m pytest tests/test_heterogeneity_attempts.py -q -rA
............................................................             [100%]
60 passed

LOCKED_ENV scripts/smoke.py
contract up to date
........................................                                 [100%]
smoke checks passed

/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
All checks passed!

PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
module-size check passed (76 modules)

wc -l -c genomeos/validation/heterogeneity_attempts.py
478 18912 genomeos/validation/heterogeneity_attempts.py

PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
private-file check passed (705 tracked files)

git diff --check
[exit 0; no output]
```

After staging exactly the three scoped paths, the same privacy command reported
`private-file check passed (708 tracked files)` and
`git diff --cached --name-only` listed only those three paths.

The test and smoke commands above were invoked through
`/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python` with `PYTHONPATH=.`,
`PYTHONDONTWRITEBYTECODE=1`, the declared `PYTENSOR_FLAGS` compiledir, and the
declared `MPLCONFIGDIR`. Imports resolved to this worktree. The full pytest
suite and actual NUTS sampling were intentionally not run in this bounded task;
stable-head full CI and independent review belong to the controller.

## Rulings and costs

- One call is one attempt. Only a separately durable convergence-failure
  checkpoint may authorize attempt 1. Cost if wrong: a later adapter needs an
  explicit durability transition; no retry is hidden here.
- `FitIdentityError.mismatches` is a public immutable ordered tuple so run and
  restored consumers retain the exact refusal fields. Cost: one small public
  exception interface.
- A typed identity-rejected fit is retained for audit but never accepted for
  consumption. Cost: a later artifact adapter may need to store rejected
  arrays.
- The all-unavailable check uses a valid inert constructor config with seed 42.
  The sampler never consumes it and the result carries no scientific fit seed.
  Cost: future reporting must preserve the distinction between an unused
  constructor seed and a scientific fit seed.

## Limits and remaining work

This evidence does not establish fitting calibration, rank uniformity,
coverage, predictive gain, convergence of actual sampled fits, complete corpus
execution, durable checkpoint/resume behavior, dataset-byte/runtime binding,
CLI orchestration, or GPU performance. Those remain requirements of the later
actual SBC/stress study and benchmark-admission work.

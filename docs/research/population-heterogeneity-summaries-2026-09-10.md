# B0H descriptive summary adapter evidence — 2026-09-10

This unit advances #211/#189 and implements Atlas design §§5,7–8,12 and the
bounded predictive/parameter summary contract. It makes no actual-fitter
calibration, spatial validity, worldwide accuracy or benchmark-admission claim.

All fit fixtures are directly constructed immutable arrays with synthetic
passing diagnostics. No NUTS sampler ran. A valid sixteen-row generator contract
provides row identity; no constructor is bypassed. All-draw linear quantiles are
anchored by an arithmetic progression, separately from selected SBC quantities.

The actual public predictor and diagnostic function are exercised once together
with constant mean=.5 and rho=1/3 arrays. The intended analytical Beta(1,1)
law implies uniform counts 0..20; binary64 rho=1/3 yields nearby shapes, not
bitwise-exact integer concentration. Independent uniform-count values, with
explicit absolute tolerances and no default relative tolerance, anchor the proper score,
errors, discrete interval coverage/width and vector PIT alignment. The two study2
targets use AC2 and AC17 in shared_cluster0/fresh_cluster order. They are paired
targets within a dataset, not independent datasets.

Purpose7 records retain the fitted track/attempt identity, exact four uint32
words and exact Python uint128 seed. Planned seed metadata does not certify RNG
consumption. Backend failure fixtures exercise explicit cupy retention without
launching GPU work, installing CuPy or claiming backend parity.

Actual predictor/diagnostic call failures preserve parameter summaries. A
diagnostic-call failure also retains the returned immutable predictive object;
its derived arrays cost additional memory alongside fitted arrays. Constructors
validate consistency, not invocation history. The absence of a public prediction
variant-label field means row/variant binding
uses declared targets and the dataset guard; it cannot certify array provenance.
Malformed returned evidence and
identity mismatches propagate as defects. Negative-infinite log scores are
retained as explicit zero-mass outcomes; no codec is chosen here.

Predictive intervals are discrete count intervals divided by AN. Full-posterior
parameter intervals are distinct. Boundary-support noncoverage and shared-history
stress are descriptive outputs, not additional success gates. Full-chain h ESS
and MCSE remain not_computed. Checkpoints, durable failure ledgers, array codecs,
study reductions and complete calibration execution remain outside this unit.

## Verification record

RED (expected):

```text
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_summaries.py -o addopts='' -q
exit 2: ModuleNotFoundError: No module named 'genomeos.validation.heterogeneity_summaries'
```

GREEN after adding the adapter:

```text
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_summaries.py -o addopts='' -q
40 passed in 5.16s
```

The locked sibling Ruff `check --fix`, `format`, and clean scoped `check` on
`genomeos/validation/heterogeneity_summaries.py` and
`tests/test_heterogeneity_summaries.py` exited 0. The locked Python prefix above
also ran `scripts/freeze_contract.py --check` (contract up to date),
`scripts/check_module_size.py` (82 modules passed),
`scripts/check_private_files.py` (722 tracked files passed), and
`scripts/smoke.py` (smoke checks passed), all with exit 0. The full suite is
reserved for the controller handoff.

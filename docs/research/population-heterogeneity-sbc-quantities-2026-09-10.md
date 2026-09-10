# B0H selected SBC quantity adapter evidence

This unit advances #211/#189 and implements Atlas design §§5,7–8,12.
It evaluates six declared quantities at one uniformly selected postwarmup
draw per chain, preserving pairing across quantities. Prior-only controls
use a separate frozen scalar stream; cyclic controls apply the fixed c-1
rho pairing. Only accepted prior-SBC study0 fits are eligible.

Tests use valid sixteen-row synthetic metadata and constructed accepted-fit
objects with synthetic diagnostics. Rational beta-binomial products provide
independent scalar expectations. Mock dependence references test state and
call behavior only; they are not evidence of scientific separability or
reference accuracy for the mixed-count fixture. One test calls the actual
reference and existing comparison guard, accepting its actual outcome.

No NUTS study, negative-control detection result, full-study p-value,
conditional-success rescue, parameter/predictive summary or real-data result
is reported. Future study accounting must retain incomplete quantities and
execution defects; constructor consistency is not source or fitting provenance.

## Observed implementation evidence

The focused RED command failed during collection before implementation because
`genomeos.validation.heterogeneity_sbc_quantities` did not exist. The relevant
error was `ImportError: cannot import name 'heterogeneity_sbc_quantities' from
'genomeos.validation'`.

After implementation, the single quantity test file passed: `61 passed in
2.15s`.

The final focused command was:

```text
python -m pytest tests/test_heterogeneity_diagnostic_seeds.py \
  tests/test_heterogeneity_sbc_controls.py \
  tests/test_heterogeneity_sbc_quantities.py -o addopts='' -q
```

Its observed result was `105 passed in 1.60s`. The observed mandatory gate
outputs were `smoke checks passed`, `All checks passed!` (Ruff), `contract up
to date`, and `module-size check passed (80 modules)`.

## Enclosing-state correction

The closed evidence record also binds every successful scalar vector to its
canonical retained-point count (thirteen after complete controls, nine after a
control failure). It rejects a `control_failed` mode-one rank unless its parent
control actually failed, while retaining true failed-control mode-one states.
The focused post-correction command passed `124` tests in `1.74s`; it includes
empty, short, long, and opposite-map scalar-vector regressions for quantities
3 and 4, plus scalar and dependence contradictory control-state regressions.

## Point-slot domain correction

Constructed or restored canonical point-slot maps now require the public
non-Boolean integer domain before their normalized Python integers are checked
against the complete-control or failed-control map. The correction rejects
Boolean and floating identifiers even where Python equality would make them
numerically match slots, while accepting and normalizing signed and unsigned
NumPy integer identifiers. The final focused command passed `138` tests in
`1.70s`; no normal-execution rank failure, reference study, or NUTS result is
reported by this domain-boundary regression.

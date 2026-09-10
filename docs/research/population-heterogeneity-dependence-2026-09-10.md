# Continuous B0H posterior-dependence reference

This note advances #211 and #189 under Atlas design §§5, 7–8 and 12. It
records bounded numerical evidence for the pure continuous-dependence primitive
at base `53126eb1835d965b76f816ebf4b2925bd9c684fa`. It is not an actual sampler
study, a proof of quadrature error, evidence of geographic validity, or a claim
that B0H improves global allele-frequency prediction.

## Scientific and engineering contract

The objective is to independently evaluate whether paired interior B0H
parameters retain the posterior dependence implied by the declared count
likelihood and independent Beta priors. The measurable output is the log density
ratio `h`, its four independently evaluated log components at orders 64, 128 and
256, an empirical numerical guard, and four draw-versus-truth orderings. The
pure validation interface consumes the public finite-product log mass,
posterior-evidence oracle and validated public Beta nodes. It performs no fit,
sampling, scoring, I/O, serving inference or production-artifact change.

The result is refused as unresolved when adjacent-order gaps exceed `1e-6`, a
separable raw result is farther than `1e-6` from zero, a draw ordering changes
sign, a non-identity comparison is numerically equal, or its strict contrast
does not exceed both point guards. Nonfinite arithmetic raises instead of
producing a value. All finite raw order values remain available in unresolved
results. The later simulation-calibration adapter is the downstream consumer;
these primitives alone cannot establish sampler calibration.

## Independent rational anchors

For one observed count `AC=0, AN=2`, the finite-product likelihood is

```text
L(m,r) = (1-m) ((1-m) + m r).
```

With independent uniform priors, direct polynomial integration gives

```text
Z = 5/12
integral L(m,r') dr' = (1-m)(1-m/2)
integral L(m',r) dm' = (2+r)/6.
```

At `(m,r)=(1/4,1/4),(3/4,3/4),(1/4,3/4)`, respectively, the
likelihoods are `39/64, 13/64, 45/64`, the fixed-mean integrals are
`21/32, 5/32, 21/32`, the fixed-rho integrals are
`3/8, 11/24, 11/24`, and `exp(h)` is `65/63, 13/11, 75/77`.

For `m ~ Beta(2,3)` and `r ~ Beta(3,2)`, direct integration instead gives

```text
Z = 13/25
integral L(m,r') pi_r(r') dr' = (1-m)(1-2m/5)
integral L(m',r) pi_m(m') dm' = (2+r)/5.
```

At the same points, the fixed-mean integrals are
`27/40, 7/40, 27/40`, the fixed-rho integrals are
`9/20, 11/20, 11/20`, and `exp(h)` is
`169/162, 169/154, 65/66`. Tests check every component at every order, not
only the final ratios.

The closed separability anchor contains only `AN=0/AC=0`, `AN=1/AC=0 or 1`,
and `AN=2/AC=1` rows. If there are `s` successes, `f` failures and `t`
heterozygous `AN=2` rows, then

```text
L = 2**t * m**(s+t) * (1-m)**(f+t) * (1-r)**t.
```

Independent priors therefore make `h=0` exactly. The interface returns literal
zero only for this predicate, while retaining and checking all numerical raw
values. In particular, the distinct points `(1/4,1/2)` and `(3/4,1/2)` both
have `h=0` for the nonseparable `AC=0, AN=2` anchor, but are not declared a
tie.

## Locked execution evidence

All Python commands used
`/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python` with
`PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`,
`PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor`,
and
`MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib`. No
ambient JAX override was set.

The genuine test-first RED was:

```text
python -m pytest tests/test_heterogeneity_dependence.py -q
E   ModuleNotFoundError: No module named 'genomeos.validation.heterogeneity_dependence'
ERROR tests/test_heterogeneity_dependence.py
```

After implementation and one correction to the test-only exact guard-equality
fixture, the focused GREEN was:

```text
python -m pytest tests/test_heterogeneity_dependence.py -q
91 passed (dot progress reached 100%; no warnings)
```

A bounded read-only measurement over the specified node moments, rational
components, separability points and complement pair reported:

| Check | Maximum absolute error |
| --- | ---: |
| Beta constant/mean/second-moment anchors | `3.3306690738754696e-16` |
| Rational likelihood/evidence/integral/h anchors | `9.7699626167013776e-15` |
| Rational-anchor adjacent-order h gap | `4.4408920985006262e-15` |
| Closed-separability raw `abs(h)` | `8.8817841970012523e-16` |
| Allele-complement components and raw h | `8.8817841970012523e-16` |

The required deliberate mutation changed the h construction from `+logZ` to
`-logZ`. The exact command

```text
python -m pytest tests/test_heterogeneity_dependence.py -q \
  -k nonseparable_reference_has_independent_rational_anchors
```

failed both prior cases. The first returned `1.7821900182119197` instead of
`log(65/63)=0.03125254350410453`; the asymmetric case returned
`1.3501553145040182` instead of
`log(169/162)=0.04230237969068937`. The mutation was restored, and the same
command then passed both cases.

## Refusal and ordering coverage

The focused suite exercises every declared refusal family:

- five Boolean, nonintegral and out-of-range quadrature orders; thirteen
  malformed, Boolean, nonpositive, nonfinite and non-real priors; and seven
  injected malformed/repeated/out-of-domain node or nonpositive/nonfinite
  weight results;
- fifteen empty, malformed, Boolean, non-real, nonfinite or boundary point
  inputs; validation of malformed counts on an otherwise separable path; and
  injected nonfinite likelihood arithmetic;
- exact four-draw index cardinality, integer type, bounds, distinctness and
  truth exclusion across twelve invalid cases;
- seven forged point-shape, nonfinite-value or negative-guard cases, an
  incorrect order tuple, and a non-reference input;
- retained raw 3-by-4 order-major signs for changing-sign, numerical-equality,
  exact-guard-equality and nonconverged-point outcomes. Exact separability and
  repeated identical input points are the only analytic tie rules.

The guard

```text
max(abs(h128-h64), abs(h256-h128),
    64*eps64*max_order(1 + sum(abs(component))))
```

is an empirical finite-precision ordering check. It is deliberately not called
a rigorous integration-error bound, and increasing the order after inspecting
an unresolved comparison is outside this frozen protocol.

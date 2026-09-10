# B0H bounded beta-binomial likelihood evaluation (2026-09-10)

This note records the localized numerical correction tracked by #214. It changes
only evaluation of the declared normalized beta-binomial observation law in
`B0H_population_heterogeneity`; it does not change the model, priors, sampler,
diagnostic gates, prediction contract, or predictive-domain refusals. All evidence
is synthetic. No global-accuracy, calibration, geographic, or real-data claim follows.

## Scientific and engineering contract

The objective is accurate float64 evaluation of the normalized beta-binomial log
mass and its gradients in logit(mean), logit(rho) coordinates on the frozen checks.
The measurable evidence is comparison with independently evaluated finite-product,
small-count, normalization, symmetry, and 400-digit ordinary logGamma/digamma
references, followed by the unchanged actual sampler oracles. The engineering
component is the pure PyTensor function
`beta_binomial_logp(value, n, mean, rho)`, consumed only by the offline fitter's
observed node.

Integer `0 <= AC <= AN <= 65536`, float64, and strict interior mean/rho are
assumed. The helper still checks parameter and count support when evaluated
directly. AN=0 has log mass zero and zero gradient. Invalid observed support has
log mass negative infinity. The fitter's existing validation and every output
refusal remain authoritative.

## Failure and correction

The original PyMC `BetaBinomial` observed graph formed a concentration
`(1-rho)/rho` and evaluated differences of log-gamma terms. At the captured
mean `0.9120608465340185`, rho `8.091265212637455e-18`, and counts
`((0,1),(1,2),(2,4),(3,9),(12,20))`, its JAXified observed log likelihood was
`+6160` with logit gradient `[0,0]`. The independent finite-product answer was
`-26.757334358778397` with gradient
`[-14.834190475224663,2.7841657124119296e-15]`. This false high-density plateau
explains the previously retained trapped-chain failure; it is numerical
cancellation, not a different statistical model.

Let `d=1-rho` and

```text
S(a,r,n) = sum(j=0..n-1) log(a+j*r).
```

The corrected normalized mass is

```text
logchoose(n,value)
  + S(mean*d,rho,value)
  + S((1-mean)*d,rho,n-value)
  - S(d,rho,n).
```

The powers of rho cancel algebraically, so the graph never forms concentration.
Each S receives log(a) and log(rho). Terms 0 through 15 are accumulated exactly
with row-vector `logaddexp` factors and symbolic count masks. For the remaining
`N=max(n-16,0)`, define

```text
logA = logaddexp(loga, log(16)+logr)
w = exp(logr-logA)
t = N*w
L = log1p(t)
tail = N*logA + N*h(t) + (N-1/2)*L + correction
h(t) = log1p(t)/t - 1
correction = sum(c*w**p*expm1(-p*L))
```

with `(p,c)` equal to `(1,1/12)`, `(3,-1/360)`, `(5,1/1260)`,
`(7,-1/1680)`, `(9,1/1188)`, and `(11,-691/360360)`. For `t<=1/8`,
`h` uses its degree-24 alternating series evaluated by Horner's method. The
polynomial and direct operands use the same `t<=1/8` predicate through `where`;
using min/max at this join produced a wrong half-gradient in the rejected
prototype. Computing `w` in the log domain avoids inverse-power overflow for
jointly tiny parameters.

The parameter-free combinatorial constant uses ordinary `gammaln` differences
for interior counts and exact zero when `min(value,n-value)==0`. The endpoint
branch avoids a measured `5.82e-10` cancellation residue at AN=65536 while
retaining the full normalized constant for all other counts.

## Independent numerical evidence

The RED test captured the old production graph returning exactly `+6160.0`
instead of the fixed `-26.757334358778397` target. After integration, the same
actual-model graph returned `-26.757334358778415`; its summed gradient was
`[-14.834190475224663,2.784165712411924e-15]`.

The independent high-precision test uses 400-digit Python `Decimal` arithmetic,
ordinary logGamma and digamma shifted to arguments at least 128, and eleven
Bernoulli correction terms. `Decimal.from_float` preserves the exact binary64
logits sent to JAX. It imports neither the candidate kernel nor any production
scorer. Across nine count pairs and ten frozen parameter points (90 comparisons),
the maximum absolute value discrepancy was `7.450580596923828e-09` and the
maximum absolute logit-gradient discrepancy was `7.275957614183426e-12`.
The largest absolute value discrepancy was one-ULP-scale on a log mass of order
`-3.7e7`; every value satisfied `atol=5e-10, rtol=1e-14`, and every gradient
satisfied `atol=1e-9, rtol=1e-12`.

Additional measured checks were:

| Check | Result |
|---|---:|
| AN1, AN2/AC1 and AN0 exact identities | passed, including logit gradients |
| Tail join and both sides, AN33/64/65536 (9 cases) | max value error `1.4551915228366852e-11`; max gradient error `9.322320693172514e-12` |
| Exact symbolic `h(t)` join and adjacent floats | passed value and derivative checks |
| Full PMF normalization, AN1/2/16/17/32/64 at three points | max absolute sum-minus-one `1.3766765505351941e-14` |
| Complement symmetry on the same PMFs | max absolute log-mass discrepancy `1.1368683772161603e-13` |
| Supplied value, integer support, n and strict parameter domains | passed |

The raw symbolic row-vector graph had 941 nodes, all outputs at most one
dimensional, with no Scan and no GenomeOS custom Op. Its construction has 16
fixed prefix iterations regardless of AN and creates no support-sized tensor.
The tests exercise PyTensor-to-JAX compilation and transformed model logits, not
only a NumPy transcription.

The final standalone numerical command deliberately omitted ambient
`JAX_ENABLE_X64`; its restoring per-test fixture enabled the required precision
and restored the prior JAX setting after every test:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor \
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest \
tests/test_heterogeneity_likelihood.py -q
```

Outcome: all 32 tests passed (exit 0).

## Integration and sampler evidence

The fitter retains a named integer observed node through
`pm.CustomDist(..., logp=beta_binomial_logp, observed=ac, dtype="int64")`.
No random callback is supplied. Direct PyMC random generation from this observed
node is intentionally unsupported and raises `NotImplementedError`; public
prediction continues unchanged through `CountPredictive`.

The unchanged exact sampler test passed (`1 passed in 7.77s`) with zero
divergences, exact identical-seed repetition, and every analytical moment and
predictive comparison inside its original MCSE-derived bound. The unchanged
nonconjugate file passed (`6 passed in 23.90s`). All four prior/orientation tracks
had zero divergences and every one of 132 moment/predictive comparisons passed.
The corrected primary Beta(1,9), original track had maximum R-hat
`1.0008114355758624`, minimum bulk ESS `6076.380470871822`, and minimum tail ESS
`3587.5423526342706`. Complete per-track diagnostics and per-quantity results
are appended to `population-heterogeneity-quadrature-2026-09-10.md`, after its
unchanged original failure history.

## Bounds and limitations

After shifting, the Stirling argument is at least 16 and `t<=4095`. At
`t<=1/8`, the alternating-series contribution has remainder below `6.68e-20`
after multiplication by the maximum AN. After the `x^-11` Stirling term, the
first omitted-term bound at `x>=16` is approximately `1.424e-18` per gamma
remainder. These analytic truncation bounds are much smaller than measured
float64 discrepancies, but they are not a uniform floating-point gradient proof.

The checks do not certify every representable logit, another compiler/runtime,
or AN above the declared maximum. Sigmoid saturation and platform rewrites remain
possible limitations. Passing synthetic samplers establishes bounded computational
fidelity only; future calibration design, real-data fitting, and promotion remain
separate work.

# Independent Population-Heterogeneity Oracles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Check actual B0H sampling for nonconjugate count datasets against an independently implemented, convergence-checked numerical posterior reference.

**Architecture:** A validation-only module evaluates the count likelihood by finite products and integrates it using Beta-weighted Gauss-Jacobi quadrature. Tests first verify this reference against exact distributions, then compare actual public fitter/predictor outputs with its nonconjugate results. The production fitter and scorer remain independently implemented.

**Tech Stack:** Existing Python3.12, NumPy, SciPy, PyMC/NumPyro, ArviZ and pytest; no new dependency.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-design.md`, especially §Pre-real-data scientific verification; methodological derivation in `docs/research/population-heterogeneity-calibration-methods-2026-09-10.md`.

This is the independent numerical-reference unit of #211/#189, not broad prior-SBC, a real-data comparison, or a global AF accuracy claim. The user authorized continuing these checks without routine approval pauses. A passed numerical oracle does not complete #211.

## Scientific contract

1. Claim: on explicitly listed nonconjugate synthetic cases, actual B0H posterior moments and withheld-count probabilities agree with a separately computed reference within measured Monte Carlo error.
2. Evidence: exact-reference anchors, quadrature refinement at four orders, complement symmetry, actual NUTS comparison for both fixed rho priors, retained diagnostics and disagreements.
3. Interface: pure validation log-mass and single-variant quadrature functions; tests consume the production fit/predict public interfaces without mocks.
4. Limits/refusals: finite-order quadrature is numerical, not exact; nonconvergence or sampler failure fails the check. No source population, coordinate, ancestry, LD, release or real-world performance claim. Consumers are later computational calibration and research benchmark admission.

## Global Constraints

- Model identifier: `B0H_population_heterogeneity`; target: `reference_panel_within_resource`.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Pure science modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- All real counts, posterior draws and per-row predictions remain local and untracked.
- AN=0 is retained as unavailable, never converted to frequency zero.
- Fitting consumes training rows only; prediction rejects training group/record overlap.
- No cross-variant parameter pooling, LD likelihood, independent-locus or joint-site prediction claim.
- No clipping, silent fallback, relaxed scoring domain, or discarded failed variant/fold.
- Convergence requires four or more chains, zero divergences, finite rank-normalized R-hat <=1.05, and finite bulk and tail ESS >=200 for both mean and rho in every fitted variant.
- Keep existing clinical gates and global promotion defaults unchanged.
- CuGen and source-export permission for remote CUDA are not prerequisites for local model work.

## Scope, files and environment

Use the existing isolated `global-af-empirical` worktree on a new dedicated branch `feat/global-af-heterogeneity-oracles`, stacked on the reviewed core branch. Root records its exact starting SHA before dispatch. Do not change parent branches or CuGen's worktree.

Create only:

- `genomeos/validation/heterogeneity_oracle.py`: independent count mass and quadrature reference, no imports from production fit/predict/scoring modules.
- `tests/test_heterogeneity_oracle.py`: exact mathematical anchors and explicit numeric-domain/refinement checks.
- `tests/test_reference_heterogeneity_quadrature.py`: actual NUTS comparisons using nonconjugate synthetic datasets and both fixed priors.
- `docs/research/population-heterogeneity-quadrature-2026-09-10.md`: commands, exact inputs, measured diagnostics/refinement/discrepancies and limits.

Only change production heterogeneity code if a failing independent test demonstrates a defect; report it to root before implementing the localized fix. Root owns full CI and PR workflow. Every implementation task runs focused tests and mandatory smoke; run privacy and inspect staged paths before every commit.

Locked interpreter `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python`; Ruff is its sibling. Prefix test/check commands with:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor \
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib
```

### Task 1: Independent finite-product likelihood and refined quadrature

**Files:** Create `genomeos/validation/heterogeneity_oracle.py` and `tests/test_heterogeneity_oracle.py`.

**Interfaces:** This module does not consume production science functions. It produces:

```python
def heterogeneity_log_mass(ac: int, an: int, *, mean: np.ndarray, rho: np.ndarray) -> np.ndarray: ...

@dataclass(frozen=True)
class HeterogeneityQuadrature:
    order: int
    log_evidence: float
    mean: float
    mean_squared: float
    rho: float
    rho_squared: float
    mean_rho: float
    predictive_an: int
    predictive_masses: tuple[float, ...]

def heterogeneity_quadrature(
    counts: Sequence[tuple[int, int]], *,
    mean_prior: tuple[float, float], rho_prior: tuple[float, float],
    predictive_an: int, order: int,
) -> HeterogeneityQuadrature: ...
```

`counts` contains literal `(AC, AN)` pairs. The numerical reference deliberately accepts empty/all-AN0 data to check prior integration; the production fitter must continue refusing all-unavailable training. Restrict this small-case reference to `0 <= AC <= AN <= 64`, `0 <= predictive_an <= 64`, and integer `2 <= order <= 512`. These are its explicit verification domain, not changes to production count limits. Reject Boolean/fractional counts/orders, malformed pairs, nonfinite/nonpositive/Boolean prior shapes. Copy consumed sequences to tuples. Empty input has log evidence0. No silent clipping or coercion of invalid input.

For `heterogeneity_log_mass`, mean/rho must be nonempty, finite real numeric arrays with broadcast-compatible shapes, `0 < mean < 1`, `0 <= rho < 1`; reject Boolean/object/string/complex arrays. Conversion of valid real numeric arrays to float64 is allowed for this numerical reference. AN0 returns an array of zeros in the broadcast shape. Underflow in an individual final mass may be numerically zero; nonfinite log likelihood/evidence, negative probabilities or failed normalization are hard errors.

- [ ] **Step 1: Write failing independent anchor and refusal tests.**

```python
np.testing.assert_allclose(
    [np.exp(heterogeneity_log_mass(a, 2, mean=np.array([0.25]), rho=np.array([0.2])))[0]
     for a in range(3)],
    [0.6, 0.3, 0.1], rtol=0, atol=1e-14,
)
```

At rho0 require binomial AN2 masses `(0.5625, 0.375, 0.0625)` for mean0.25. Check broadcast behavior, normalized complete count masses, AN0, complement symmetry, and every invalid-domain category above.

For order32 verify exact posterior anchors with absolute tolerance1e-12:

| Counts and priors | Evidence | E(m), E(m²) | E(r), E(r²) | E(mr) | Future AN2 masses P0,P1,P2 |
| --- | --- | --- | --- | --- | --- |
| Empty; mean(1,1), rho(1,9) | 1 | 1/2,1/3 | 1/10,1/55 | 1/20 | 7/20,3/10,7/20 |
| Five AN1 AC0,1,1,0,1; same priors | 1/60 | 4/7,5/14 | 1/10,1/55 | 2/35 | 33/140,27/70,53/140 |
| Four AN2 AC1; same priors | 8/455 | 1/2,3/11 | 1/14,1/105 | 1/28 | 89/308,65/154,89/308 |
| Empty; mean(2,3), rho(2,5) | 1 | 2/5,1/5 | 2/7,3/28 | 4/35 | 16/35,2/7,9/35 |

Check `log_evidence` against the logarithm of the exact evidence; include AN0 rows without changing the answer. The asymmetric-prior case must catch reversed Jacobi exponents. Inputs are not mutated. A deliberately swapped exponent or missing likelihood must fail an existing anchor; report one narrowly scoped mutation test, then restore it without committing the mutation.

- [ ] **Step 2: Run and record RED.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_oracle.py
```

- [ ] **Step 3: Implement the independent reference.**

Evaluate the following log product with `math.comb` and NumPy logs, without `betaln`, `gammaln`, PyMC, CountPredictive or SciPy's beta-binomial:

```python
logp = np.full(broadcast_shape, math.log(math.comb(an, ac)), dtype=np.float64)
for j in range(ac):
    logp += np.log(mean * (1 - rho) + j * rho)
for j in range(an - ac):
    logp += np.log((1 - mean) * (1 - rho) + j * rho)
for j in range(an):
    logp -= np.log((1 - rho) + j * rho)
```

For a Beta(a,b) prior use `roots_jacobi(order, b-1, a-1)`, map nodes to `(x+1)/2`, normalize each positive finite weight vector by its sum. Validate interior finite nodes and positive finite normalized weights; refuse numerical degeneration. This mapping follows the documented weight `(1-x)^alpha*(1+x)^beta` in [SciPy's primary documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.roots_jacobi.html).

Evaluate the tensor-product grid with `mean[:,None]`, `rho[None,:]`, accumulate training log masses, and add log prior weights. Use max-shift normalization (or `scipy.special.logsumexp`) for posterior grid weights and log evidence. Integrate the five stated moments and full predictive count support. Preserve positive finite normalization; masses must sum to1 within1e-10, with no renormalization of a defective output. Return numeric scalars and an immutable mass tuple. Document that a single result is finite-order quadrature, not certified convergence.

- [ ] **Step 4: Run GREEN, smoke and static gates.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_oracle.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] **Step 5: Inspect/stage only task files and commit.**

```bash
git add genomeos/validation/heterogeneity_oracle.py tests/test_heterogeneity_oracle.py
git commit -m "test: add independent heterogeneity quadrature reference" -m "Advances #211 and #189; numerical reference only."
```

### Task 2: Actual NUTS comparison on nonconjugate synthetic cases

**Files:** Create `tests/test_reference_heterogeneity_quadrature.py` and `docs/research/population-heterogeneity-quadrature-2026-09-10.md`.

**Interfaces:** Consume Task1 `heterogeneity_log_mass`, `heterogeneity_quadrature`, `HeterogeneityQuadrature`; production `PopulationHeterogeneityConfig`, `fit_reference_population_heterogeneity`, `predict_reference_population_heterogeneity`; public ReferenceCount. No mocks, alternate fitter, remote GPU or real data.

- [ ] **Step 1: Freeze the following test matrix in code before running it.**

```python
SEED = 42
CASES = {
    "mixed": ((0, 2), (1, 3), (4, 5), (8, 8), (2, 6)),
    "rare": ((0, 20), (0, 12), (1, 18), (0, 5), (0, 0)),
    "unequal_an": ((0, 1), (1, 2), (2, 4), (3, 9), (12, 20), (0, 0)),
}
ORDERS = (32, 64, 128, 256)
RHO_PRIORS = ((1.0, 9.0), (1.0, 4.0))
```

Mean prior(1,1), future AN5, actual sampler config four chains,2000draws,2000tune,target_accept0.9,seed42. This is a predeclared small-case numerical test, not the later broad simulation protocol. Both priors, all cases and their count complements must be reported; no favorable selection. Construct stable synthetic source/group/region/record/variant identities with disjoint query groups.

For each prior and original/complement data, calculate all four quadrature orders before using the final-order reference. For log evidence, all five moments, and every predictive mass, require absolute changes <=1e-8 for BOTH64->128 and128->256. Report all refinement gaps, including32->64; do not drop a nonconverged case. Complemented reference must preserve rho moments/log evidence, map mean to1-mean, mean² to1-2E(mean)+E(mean²), mean*rho toE(rho)-E(mean*rho), and reverse predictive masses, within1e-8.

- [ ] **Step 2: Compare actual public sampler/predictor outputs with that reference.**

Batch the three independent synthetic variant cases in each actual fitter call. Parameterize the two prior tracks; each uses an original and complemented fit. Four actual calls total. Apply the unchanged production diagnostic gates and retain all diagnostics. No retry or tolerance tuning in this unit; failures return to root for investigation.

For each fitted variant use labeled chain/draw slices to form `mean`, `mean**2`, `rho`, `rho**2`, `mean*rho`. For each future AC0..5 form per-draw masses via the independently anchored Task1 log-mass function. Calculate ArviZ MCSE on each derived chain/draw array. Require finite positive MCSE<=0.005, and each discrepancy against order256 <=max(5*MCSE,0.003). Compare the actual predictor's `exp(log_prob(AC,AN=5))` against every reference mass using its corresponding mass MCSE, not only the independent function's mean. Verify AN0 training IDs remain unavailable. Never flatten chains before MCSE.

```python
bound = max(5.0 * mcse, 0.003)
assert np.isfinite(mcse) and 0 < mcse <= 0.005
assert abs(actual - reference) <= bound
```

- [ ] **Step 3: Run the new scientific check and investigate failures without changing its criterion.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_reference_heterogeneity_quadrature.py -s
```

Record an initial pass honestly as independent characterization, not fabricated RED. If quadrature does not converge or sampling fails, preserve the failing data/config/output and report it to root; a changed verification domain requires a documented scientific decision, not selecting easier counts.

- [ ] **Step 4: Record exact inputs, commands and measured evidence; run regressions.**

The committed research note must contain the full fixed matrix, priors, budgets, environment versions, all refinement maxima per case/track/orientation, sampler divergences/R-hat/ESS, per-quantity estimates/reference/MCSE/bounds and exact executed gate commands with their outcomes. Synthetic summary tables are safe to commit; do not commit posterior arrays or local runtime directories. Distinguish numerical reference convergence from exact proof, computational fidelity from empirical improvement, and this unit from broad SBC.

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_oracle.py tests/test_reference_heterogeneity_quadrature.py tests/test_reference_heterogeneity.py tests/test_reference_heterogeneity_sampling.py tests/test_reference_counts.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] **Step 5: Inspect/stage only task files and commit.**

```bash
git add tests/test_reference_heterogeneity_quadrature.py docs/research/population-heterogeneity-quadrature-2026-09-10.md
git commit -m "test: compare heterogeneity sampling with refined quadrature" -m "Advances #211 and #189; no real-data improvement claim."
```

### Task 3: Correct the demonstrated likelihood cancellation (#214)

Task 2 remains incomplete: its fixed primary-original case failed with 276
divergences, preserved in commit be684318 and the research note. This task is
the localized production correction permitted above, not a new model.

**Scientific contract:** evaluate the declared normalized beta-binomial law and
its logit gradients accurately on the stated numerical checks; the measurable
evidence is independent exact/high-precision comparisons and then the unchanged
actual sampler oracles. A pure PyTensor expression helper is consumed by the
offline fitter's observed node. Integer counts already validated by the fitter,
float64, and strict interior mean/rho are assumed; output-domain refusals and all
fit gates stay unchanged. No real/global-accuracy claim follows.

**Files:** Create `genomeos/surfaces/heterogeneity_likelihood.py` and focused
`tests/test_heterogeneity_likelihood.py`; modify only the observed-likelihood
integration in `genomeos/surfaces/reference_heterogeneity.py`. A separate
test-only high-precision reference helper and literal synthetic fixture are
allowed under `tests/`; do not add dependencies. Record the numerical derivation,
measured checks and limitations in
`docs/research/population-heterogeneity-likelihood-2026-09-10.md`. Append the
post-fix actual evidence to the existing quadrature note without deleting its
failure history. Existing sampler tests, inputs and thresholds are frozen.

**Interface:** `beta_binomial_logp(value, n, mean, rho) -> TensorVariable`,
typed symbolic per-observation normalized log masses. It must use its supplied
`value`, not close over a different observed array. Preserve `obs` as an observed
node via `pm.CustomDist(..., logp=beta_binomial_logp, observed=ac, dtype="int64")`.
Document unsupported direct PyMC random generation; the public prediction path
continues to use CountPredictive. Retain support and parameter checks, including
integer count support. No production import from the independent oracle, test
reference or private scorer. No environment/global configuration or I/O.

- [ ] **Step 1: Add failing numerical regressions before production edits.**

Test the actual model's JAXified observed log likelihood and transformed logit
gradients at mean `0.9120608465340185`, rho `8.091265212637455e-18`, counts
`((0,1),(1,2),(2,4),(3,9),(12,20))`. Independent finite products give summed
logp `-26.757334358778397` and gradient
`[-14.834190475224663, 2.7841657124119296e-15]`; old code gives +6160 and zeros.
The known RED must be numerical, not merely a missing-module import.

Also test AN1 and AN2/AC1 exact identities, zero AN value/gradient, and supplied
value/support handling. Freeze count pairs
`(0,1),(1,2),(12,20),(0,65536),(1,65536),(32768,65536),(65535,65536),
(65536,65536),(17,33)` at parameter points
`(0.9120608465340185,8.091265212637455e-18),(.5,.1),(.01,.8),
(.999999,.999999),(1e-12,1e-20),(1e-100,1e-100),(1e-250,1e-250),
(.5,1e-300),(1e-250,.8),(.5,nextafter(1.,0.))`.
Compare actual PyTensor/JAX values and logit gradients with independent
400-digit Decimal ordinary logGamma/digamma calculations (not the candidate
kernel). Literal fixtures may avoid repeating high-precision setup on every
test, but retain a reproducible test helper and exact logits/provenance.
Numerical bounds: value `atol=5e-10, rtol=1e-14`; logit gradient
`atol=1e-9, rtol=1e-12`. These are not changes to sampler MCSE/gates.

- [ ] **Step 2: Implement the stabilized expression and observed integration.**

Let `d=1-rho` and `S(a,r,n)=sum(j=0..n-1) log(a+j*r)`. Return
`logchoose(n,value)+S(mean*d,rho,value)+S((1-mean)*d,rho,n-value)-S(d,rho,n)`.
Pass logs of a/r rather than forming kappa. For each S accumulate j0..15 with
masked row-vector factors: j0 is loga; others
`logaddexp(loga, log(j)+logr)`. For the remaining `N=max(n-16,0)` use
`logA=logaddexp(loga,log(16)+logr)`, `w=exp(logr-logA)`, `t=N*w`, `L=log1p(t)`:

```text
tail = N*logA + N*h(t) + (N-1/2)*L + correction
h(t) = log1p(t)/t - 1
correction = sum(c*w**p*expm1(-p*L))
(p,c) = (1,1/12),(3,-1/360),(5,1/1260),(7,-1/1680),
        (9,1/1188),(11,-691/360360)
```

For `t<=1/8`, h uses its degree24 alternating series
`sum(i=1..24) (-1)**i*t**i/(i+1)`, evaluated by Horner. Protect inactive
operands with the SAME predicate: `u=where(small,t,1/8)` for the polynomial,
`v=where(small,1/8,t)` for the direct expression. Do not use min/max at this
join: half-gradients at ties caused a demonstrated error. Do not compute r/A
directly: intermediate AD inverse powers overflow for joint tiny parameters.
Parameter-free logchoose must include its constant and meet max-AN bounds.
Six Stirling terms after shifting x>=16 bound truncation far below rounding;
do not describe that as a full uniform floating-point gradient proof.

- [ ] **Step 3: Pass focused tests before rerunning samplers.**

Check exact helper branch join and both sides for AN33/64/65536. Use
mean=.5, AC=AN, `kappa=(8*(AN-16)-16)/.5`,
`rho=1/(1+kappa*factor)` for factors `1-1e-10,1,1+1e-10`; also directly
verify the exact symbolic helper join so transformed rounding cannot mask it.
Check full PMF normalization and complement symmetry at AN1/2/16/17/32/64
and parameters `(.01,.8),(.5,.1),(.9120608465340185,8.091265212637455e-18)`.
Inspect/test graph structure for bounded row-vector work independent of AN,
without a support-sized matrix, scan, custom Op or VJP. Exercise actual
PyTensor/JAX and model transforms, not only a NumPy transcription.
Run existing structural fitter tests to preserve priors, labels, AN0 filtering,
float64 checks, numerical refusals and fixed diagnostics.

- [ ] **Step 4: Rerun the unchanged actual oracles and retain all outcomes.**

Run `tests/test_reference_heterogeneity_sampling.py` and
`tests/test_reference_heterogeneity_quadrature.py` with the original configs,
counts, priors, seeds and thresholds. A code-corrected rerun is identified as
such, not substituted for the original failure. Any failure is reported to root;
no retry/seed/threshold change. Record every track and per-quantity comparison
in the existing evidence note. No broad SBC or real fit in this task.

- [ ] **Step 5: Run gates, inspect and commit only owned files.**

Use the locked environment and prefixes above. Run focused new and existing
heterogeneity/reference-count tests, mandatory smoke, Ruff, module-size and
privacy gates. Inspect `git diff --cached --name-only` before the commit and
rerun the privacy gate after staging. Root owns full CI, independent review,
push and PR. Do not close #211/#189. If all #214 checks genuinely pass, use
`fix: stabilize heterogeneity likelihood evaluation` with `Closes #214` in
the commit body; otherwise preserve honest evidence and escalate before commit.

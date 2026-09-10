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

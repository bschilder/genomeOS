# Population-Heterogeneity Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a training-only B0H fitter and marginal predictor, and verify actual posterior sampling against exact tractable distributions.

**Architecture:** Immutable validated contracts separate the reference-count
model from PyMC and from I/O. A pure offline fitter consumes training counts;
a separate predictor composes the fitted draws into the existing CountPredictive.
Exact posterior cases verify the sampler and prediction adapter together.

**Tech Stack:** Existing Python3.12, NumPy, PyMC/NumPyro, ArviZ, xarray and pytest.
No dependency changes.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-design.md`

This independently reviewable core unit advances #211 and #189. It implements
the spec's model, types, fit/predict contracts and first analytical sampler
oracles. The separately scoped runner integration, general quadrature/SBC/stress
study and real paired comparison remain required follow-on work before #211
can be completed. They are not claimed by finishing this core plan.

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
- Convergence requires four or more chains, zero divergences, finite rank-normalized R-hat <=1.05,
  and finite bulk and tail ESS >=200 for both mean and rho in every fitted variant.
- Keep existing clinical gates and global promotion defaults unchanged.
- CuGen and source-export permission for remote CUDA are not prerequisites for local model work.

## Workspace and verification

Existing isolated checkout:
`/Users/bschilder/code/genomeOS/.claude/worktrees/global-af-empirical`.
Dedicated branch: `feat/global-af-population-heterogeneity`, base
`5d295706cac9c7bec945e563d03c7fc69c6335f2`. Do not switch another checkout,
modify the pending PR210 branch, or alter CuGen's worktree.

Use `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python` and sibling ruff.
All test commands below run with PYTHONPATH=., PYTHONDONTWRITEBYTECODE=1,
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor,
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib.
The current environment was empirically checked: PyMC6.3.1, PyTensor3.3.0,
NumPyro0.21.0, JAX/JAXlib0.11.1, ArviZ1.3.0. Run env_report before disputing
sampler routing. No package installation is required.

After code changes run focused tests, smoke, Ruff, frozen-contract, module-size
and privacy gates. Before commits inspect staged paths and diff. Root owns full
CI, task/final reviews and the branch PR. An unavailable review agent is not a
passed review; record the limitation without inventing its result.

### Task 1: Validated training-only fitter and withheld-population predictor

**Files:**
- Create: `genomeos/surfaces/heterogeneity_types.py`
- Create: `genomeos/surfaces/reference_heterogeneity.py`
- Create: `tests/test_reference_heterogeneity.py`

**Interfaces:** Consume public ReferenceCount, validate_reference_counts,
ReferenceInfeasibleError, B0InfeasibleError, CountPredictive and
MAX_BETA_SCORING_COUNT. Produce every type and both function signatures defined
in spec §Public fit and prediction contracts, with those exact field names.
Keep prior shapes required, sampler settings explicit and convergence gates
fixed. No CLI, saving/loading, remote work or real data in this task.

- [ ] **Step 1: Write failing contract and model-graph tests.**

The breaks to catch are dropped unavailable rows, test-count access, prior/
variant misalignment, wrong beta-binomial parameterization, misread posterior
axes, numerical clipping and acceptance of a failed sampler.

Use tiny invented rows:

```python
def row(group, variant="v", ac=1, an=2):
    return ReferenceCount(f"{group}:{variant}", variant, group, "synthetic", "block", ac, an)

config = PopulationHeterogeneityConfig(
    mean_prior_alpha=1, mean_prior_beta=1,
    rho_prior_alpha=1, rho_prior_beta=9,
)
```

Parameterize invalid prior shapes (0,-1,NaN,infinity,True), fractional/Boolean
draws/tune/chains/seed, fewer than four chains and invalid target_accept.
Validate copied immutable float64 posterior storage, exact axes/identities,
finite/in-range mean/rho and CountPredictive's unchanged numeric domain.

Mock only pm.sample for fast structural/refusal tests, leaving the real PyMC
graph and ArviZ computation intact. Capture pm.Model.get_context() in that
sampler double and return an explicitly labeled xarray posterior and full
sample_stats.diverging. Generate independent seeded Beta chains for successful
diagnostic fixtures; make every coordinate and model-dependent variant explicit.
Do not use the graph's own calculation as its expected likelihood.

For a fixed mean=0.25, rho=0.2, an=2 the independent count masses are
P0=0.6,P1=0.3,P2=0.1. Assert the observed graph contribution for submitted AC=1
equals log(0.3), not the binomial log(0.375). Two observed rows contribute the
sum of their log masses, with unavailable rows contributing none.
Check swapping the actual likelihood or rho-to-kappa mapping fails this test.
Test asymmetric prior shapes through the real graph's prior contribution.

Cover empty/all-unavailable training, unsupported AN, absent query variants,
record/group overlap, unavailable query rows and preservation of literal
identities. A held-out count perturbation must not change predictions.

```python
first = predict_reference_population_heterogeneity(fitted, [row("query", ac=0)])
changed = predict_reference_population_heterogeneity(fitted, [row("query", ac=2)])
np.testing.assert_array_equal(first.marginal_predictive.mean_draws,
                              changed.marginal_predictive.mean_draws)
np.testing.assert_array_equal(first.marginal_predictive.concentration,
                              changed.marginal_predictive.concentration)
```

Inject missing/duplicate/reordered variant labels, wrong chain/draw sizes,
mismatched mean/rho coordinates, missing/non-Boolean divergence flags, NaN
diagnostics, nonmixing chains, divergence and low bulk/tail ESS. Reordering
valid labeled variant axes must align correctly; losing identity must fail.
Use actual ArviZ on controlled chains where possible. A narrow diagnostic
stub is allowed only for distinct threshold branches, with its complete
structure and named variables retained. Do not assert mock existence.

- [ ] **Step 2: Run RED and preserve the exact command/output.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_reference_heterogeneity.py
```

A missing new module is expected initially. Once imports exist, verify new
behavioral tests actually fail before implementing their respective behavior.

- [ ] **Step 3: Implement the validated contracts and real model.**

Use sorted available variant IDs and an explicit row-to-variant index:

```python
with pm.Model(coords={"variant": variant_ids}) as model:
    mean = pm.Beta("mean", config.mean_prior_alpha, config.mean_prior_beta, dims="variant")
    rho = pm.Beta("rho", config.rho_prior_alpha, config.rho_prior_beta, dims="variant")
    kappa = (1 - rho) / rho
    pm.BetaBinomial(
        "obs", n=an, alpha=mean[index] * kappa[index],
        beta=(1 - mean[index]) * kappa[index], observed=ac,
    )
    idata = pm.sample(
        draws=config.draws, tune=config.tune, chains=config.chains,
        random_seed=config.seed, nuts_sampler="numpyro",
        target_accept=config.target_accept,
        nuts={"chain_method": "vectorized"}, progressbar=False,
    )
```

No clipping, prior-only fallback, test data, file/network/env access or global
configuration mutation. Sum training totals with Python integers; retain all
training identities and unavailable IDs. Fit every available training variant.

Extract labeled posterior arrays before positional conversion. Validate exactly
chain/draw/variant axes, canonical integer chain/draw positions, expected sizes,
matching sample_stats coordinates, exact variant sets, float64 and finite
parameters. Reindex by labels. Get rank R-hat plus bulk/tail ESS using ArviZ,
reject any nonfinite cell before reductions and gate every variant. Count
divergences globally and refuse malformed flags. Carry finite diagnostics and
known global divergence counts in HeterogeneityConvergenceError; never attribute
a global trajectory divergence to a particular variant.

Derived concentration is (1-rho)/rho. Use the public CountPredictive constructor
to enforce its numeric domain rather than importing private scoring validators.
Validated output arrays use immutable byte-backed copies:

```python
copied = np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)
```

Prediction validates disjoint IDs/groups, retains AN0, rejects absent variants,
and gathers aligned flat mean/kappa draws for only scoreable rows in submitted
order. Pass the explicitly requested backend to CountPredictive. Do not add
a production method solely to make tests convenient.

- [ ] **Step 4: Run GREEN and mandatory gates; self-review against the spec.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_reference_heterogeneity.py tests/test_reference_counts.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] **Step 5: Commit the core after staged-path inspection.**

```bash
git add genomeos/surfaces/heterogeneity_types.py genomeos/surfaces/reference_heterogeneity.py tests/test_reference_heterogeneity.py
git commit -m "feat: add training-only population heterogeneity model" -m "Advances #211 and #189; no geographic or release claim."
```

### Task 2: Actual NUTS proof against exact posterior distributions

**Files:**
- Create: `tests/test_reference_heterogeneity_sampling.py`
- Create: `docs/research/population-heterogeneity-exact-oracles-2026-09-10.md`
- Modify only if the failing scientific test demonstrates a defect:
  `genomeos/surfaces/heterogeneity_types.py`,
  `genomeos/surfaces/reference_heterogeneity.py`

**Interfaces:** Consume Task1's public config, fitter, predictor, fit arrays and
diagnostics. No mocks, real data, remote GPU, benchmark runner or new dependency.
This task cannot be reported complete merely because structural tests passed.

- [ ] **Step 1: Add an actual-sampling test using two exact posterior cases.**

Create one training table with a Bernoulli variant at five groups, AN=1 and
AC=(0,1,1,0,1), and a second variant at four groups, AN=2 and AC=1 for every group.
Keep source group/region labels consistent. Add one AN0 row for each variant.
The prior is mean Beta(1,1), rho Beta(1,9). Use four chains,1000 draws,1000 tune,
target_accept0.9,seed42; apply the same unrelaxed production diagnostic gates.

Exact independent posterior moments:

| Variant | E(mean) | E(mean^2) | E(rho) | E(rho^2) |
| --- | --- | --- | --- | --- |
| Bernoulli | 4/7 | 5/14 | 1/10 | 1/55 |
| Central AN2 | 1/2 | 3/11 | 1/14 | 1/105 |

Their future AN=2 P(AC=1) are27/70 and65/154; P(AC=0) are33/140 and89/308.
These are literal rational expectations, not outputs of the fitter.

Use test-side ArviZ MCSE on each derived chain/draw array. Require finite,
positive MCSE <=0.01 and absolute discrepancy <=max(5*MCSE,0.003). Check both
first and second moments. For predictive probabilities use the derived
per-draw functions:

```python
mass_one = 2 * mean * (1 - mean) * (1 - rho)
mass_two = mean - mass_one / 2
mass_zero = 1 - mass_one - mass_two
```

Compare the actual predictor's exp(log_prob(AC=1,AN=2)) and cdf(AC=0,AN=2)
against the exact rational values using the corresponding derived MCSE.
Do not let a large MCSE make an inaccurate sampler pass. Preserve actual
diagnostic values and measured discrepancies in the test output/report.

- [ ] **Step 2: Run the scientific test and investigate any failure.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_reference_heterogeneity_sampling.py -s
```

If existing Task1 code already passes, record that this is a new independent
characterization/proof rather than inventing a RED result. If a model defect
appears, preserve RED, fix only that defect and rerun. Do not weaken the oracle,
gates, declared seed or tolerance to make the fit pass. A precision failure is
not model success and must be reported.

- [ ] **Step 3: Add real complement and same-seed reproducibility checks.**

Run the same actual fitter again with identical training/config and require
identical stored draws on this pinned CPU environment. Then complement all
available counts (AN-AC), use the same declared configuration, and check the
analytically complemented posterior/predictive expectations with MCSE.
Do not require bit-identical draws under complementation: different trajectories
may target the correctly transformed distribution. Keep AN0 rows unavailable.
For the Bernoulli variant complemented E(mean)=3/7 and E(mean^2)=3/14;
rho remains Beta(1,9). The symmetric AN2 posterior is unchanged.
Future P1 stays27/70, while P0 becomes53/140 for the Bernoulli variant.

- [ ] **Step 4: Run focused tests/gates and record evidence without a calibration claim.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_reference_heterogeneity.py tests/test_reference_heterogeneity_sampling.py tests/test_reference_counts.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

The research note states the two exact posterior derivations, commands,
runtime versions, actual diagnostics/moment/probability discrepancies,
determinism/complement results and limits. No synthetic pass is an empirical
AF improvement. General quadrature, SBC/stress simulation, runner integration
and the real paired comparison remain open #211 work.

- [ ] **Step 5: Commit the exact-oracle proof after privacy/staged-path checks.**

```bash
git add tests/test_reference_heterogeneity_sampling.py docs/research/population-heterogeneity-exact-oracles-2026-09-10.md
git commit -m "test: verify population posterior against exact oracles" -m "Advances #211; actual synthetic sampler evidence, not global model validation."
```

The controller then runs full CI and final scoped-branch review, opens a PR
stacked on PR210, and continues #211's independent benchmark/calibration units.
Do not close #211 or #189 from this core component.

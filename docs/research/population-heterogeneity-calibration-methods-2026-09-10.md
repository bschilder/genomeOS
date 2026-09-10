# B0H computational calibration: methods and failure probes

Advances #211 and #189; design §§5,7,8. This note informs the next experiment
protocol. It is not a record of completed simulations, a frozen simulation
budget, or evidence of improved real-data predictions.

## Scientific contract

- **Claim under examination:** the implemented B0H sampler and predictor
  approximate their declared population-heterogeneity model faithfully.
- **Evidence:** exact posterior cases first, then independent quadrature and
  repeated simulation checks with measured sensitivity to deliberate defects.
- **Components:** the training-only fitter, its marginal CountPredictive
  adapter, and a separate offline validation runner. No serving-path changes.
- **Limits and consumers:** simulation checks assess computation under known
  generating assumptions, not worldwide AF accuracy. A numerical failure is
  retained, not converted to a prediction. Results inform benchmark admission;
  held-out real populations remain necessary for model comparison.

## Primary texts inspected

1. Talts, Betancourt, Simpson, Vehtari and Gelman, *Validating Bayesian
   Inference Algorithms with Simulation-Based Calibration*,
   [arXiv:1804.06788v2](https://arxiv.org/abs/1804.06788v2), 21 October 2020
   revision. Read the full main text and its embedded code/proof appendices
   using the arXiv HTML and PDF. The identifier is **1804.06788**, not
   1805.09294. No accompanying code was executed.
2. Modrák et al., *Simulation-Based Calibration Checking for Bayesian
   Computation: The Choice of Test Quantities Shapes Sensitivity*,
   [DOI:10.1214/23-BA1404](https://doi.org/10.1214/23-BA1404).
   Read the full publisher early-version PDF (28 article pages plus repository
   cover) in the [Aalto repository](https://acris.aalto.fi/ws/portalfiles/portal/164226299/Simulation-Based_Calibration_Checking_for_Bayesian_Computation.pdf).
   Visually inspected article pages4,15,22, including Figures1,3,4,11.
   The PDF is the 2023 early version; the final issue is 20(2),461–488,2025.
   The separately linked mathematical supplements and simulation code were
   **not** inspected or executed. Web access to PMC encountered a browser
   challenge; the university-hosted PDF supplied the full main text.

PDFs remain local research copies, not repository artifacts. No paper's
source data or publication-evidence rows were imported.

## What the papers change in our checks

Talts et al. §§4–5 establish a rank-based computational check across datasets
generated from the prior and observation model. Raw correlated MCMC draws do
not satisfy the independent-draw rank reference; their §5.1 proposes
ESS-informed thinning, including attention to quantile ESS and antithetic
chains. Their §4.3 and examples distinguish this check from validation against
real observations. We will retain chain identities and apply a declared
rank-draw selection rule, not flatten all stored draws and assume independence.
[Primary text](https://arxiv.org/html/1804.06788v2)

Modrák et al. §§1.2,3.3–3.6,4,6 show why parameter-only ranks can miss ignored
data or incorrect posterior dependence. They recommend adding data-dependent
quantities such as joint likelihood, and handle tied values by randomized rank
selection among tied positions. A finite collection of checks has limited
sensitivity, and multiple comparisons matter. Accordingly, B0H should check
mean, rho, a prediction-relevant function and independently evaluated training
log likelihood. A prior-only negative control must demonstrate why a pleasant
parameter-rank plot is insufficient.
[Primary text](https://doi.org/10.1214/23-BA1404)

## Independent numerical reference

The following is our proposed B0H-specific construction, not an algorithm
reported by either paper. With `m=mean`, `r=rho`, `n=AN`, `a=AC`, the conditional
count mass can be written without the fitter's gamma-function evaluation:

```text
P(a | n,m,r) = choose(n,a)
  * product[j=0..a-1]   (m*(1-r) + j*r)
  * product[j=0..n-a-1] ((1-m)*(1-r) + j*r)
  / product[j=0..n-1]   ((1-r) + j*r)
```

Empty products equal1. Implement a validation-only log-product calculation
independently of PyMC and the production scorer. Check the literal AN2 masses
in the core plan before using it as a reference. Integrate the product of
training likelihoods against the two declared Beta priors with tensor-product
quadrature. Increase quadrature orders and verify convergence of the normalizer,
first/second/cross moments and future count probabilities. Do not call a
finite-order grid an exact answer, or hide nonconvergence through averaging.

This provides nonconjugate cases beyond the two algebraically exact posterior
oracles. It does not replace the actual sampler tests or independently
validate every numerical component used by the reference.

## Required controls for the next frozen protocol

Before launching that experiment, freeze simulation identities, seeds, count
designs, budgets, retries, comparison quantities and uncertainty references.
The current core plan fixes only its two exact cases; no broad SBC run has
yet been launched.

- Generate data with a separate NumPy Beta-then-Binomial construction, without
  calling the fitted graph or CountPredictive.sample_counts. Keep training
  and held-out populations distinct. An all-unavailable training dataset is
  an intended refusal, not a simulated zero-frequency population.
- Evaluate primary and sensitivity priors separately. Do not average their
  ranks or choose a prior using withheld real counts.
- Keep each independent simulated dataset as the replication unit. Multiple
  parameters, held-out rows sharing parameters, posterior draws, and linked
  real variants are not additional independent replications.
- Predeclare rank thinning for all monitored quantities, including log
  likelihood. Quantile ESS, retained draws, residual dependence diagnostics
  and failure reasons belong in the output. Thinning is not proof of exact
  independence; compare against independent quadrature where available.
- Check prior-only and deliberately mispaired mean/rho draws as negative
  controls. Their magnitude and detection requirements must be fixed before
  seeing the correct implementation's simulation results.
- Report complete-run counts and every failed fit. At most the one permitted
  doubled-budget convergence retry is allowed. Rank plots conditional on
  successful fits must be labeled as such; dropping failures cannot establish
  unconditional calibration.
- Treat fixed low-frequency and heterogeneous-AN scenarios as stress tests,
  not prior-SBC. Include homogeneous `rho=0` as a misspecification/boundary
  stress case: the continuous Beta prior has no atom there, so demanding
  nominal equal-tail interval coverage of exactly zero is inappropriate.
- Keep predictive count checks separate from parameter checks. Discrete
  count intervals can overcover; randomized PIT and proper scores provide
  complementary evidence. Do not alter the global production promotion
  gates as a side effect of this developmental experiment.

## Decision boundary

Passing these checks would support computational fidelity only over the
tested domain and sensitivity. Failure motivates a localized investigation;
it does not justify clipping, replacing the requested backend, deleting a
variant, or relaxing a convergence threshold. Geographic interpolation,
covariate value, ancestral migration and temporal reconstruction remain
separate model hypotheses with their own data and held-out benchmarks.

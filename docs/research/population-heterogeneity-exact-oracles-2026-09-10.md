# B0H exact-posterior NUTS oracles (2026-09-10)

This note records an actual synthetic CPU sampling proof for
`B0H_population_heterogeneity` under the fixed mean `Beta(1,1)` and rho `Beta(1,9)`
priors. It is an independent characterization of the reviewed B0H core: the
existing production implementation passed without a production-code change. This
is not a real-data benchmark, an allele-frequency improvement result, or global
model validation.

## Exact distributions

The first synthetic variant has five independent population rows with `AN=1` and
`AC=(0,1,1,0,1)`. A beta-binomial draw with `AN=1` is Bernoulli in `mean` and is
independent of `rho`. The posterior therefore factorizes as

```text
mean | data ~ Beta(4,3)
rho  | data ~ Beta(1,9).
```

Thus `E(mean)=4/7`, `E(mean^2)=5/14`, `E(rho)=1/10`, and
`E(rho^2)=1/55`.

The second variant has four independent population rows with `AN=2, AC=1`. Its
per-row beta-binomial mass is
`2 * mean * (1 - mean) * (1 - rho)`. The four-row likelihood is therefore
proportional to `[mean * (1 - mean) * (1 - rho)]^4`, so the posterior factorizes
as

```text
mean | data ~ Beta(5,5)
rho  | data ~ Beta(1,13).
```

Thus `E(mean)=1/2`, `E(mean^2)=3/11`, `E(rho)=1/14`, and
`E(rho^2)=1/105`.

For a future `AN=2` count, each aligned posterior draw uses

```text
P(AC=1) = 2 * mean * (1 - mean) * (1 - rho)
P(AC=2) = mean - P(AC=1) / 2
P(AC=0) = 1 - P(AC=1) - P(AC=2).
```

Integrating those expressions gives Bernoulli-case probabilities `27/70` and
`33/140` for `AC=1` and `AC=0`; the central-AN2 case gives `65/154` and
`89/308`. These are literal rational answers, not fitter output. One `AN=0` row
per variant was retained as unavailable and did not enter either likelihood.

## Sampling and acceptance rule

The public fitter ran four vectorized NumPyro NUTS chains with 1,000 tuning steps,
1,000 retained draws, `target_accept=0.9`, and seed 42. The production gates were
unchanged: zero divergences, rank-normalized R-hat at most 1.05, and bulk and tail
ESS at least 200 for both parameters of every variant.

Every checked quantity used test-side ArviZ MCSE on its `(chain, draw)` array. An
MCSE had to be finite, positive, and at most 0.01. The estimate had to be within
`max(5 * MCSE, 0.003)` of its exact value, so a large MCSE cannot excuse an
inaccurate chain. Predictive estimates below are the public predictor's
`exp(log_prob(AC=1, AN=2))` and `cdf(AC=0, AN=2)`; their MCSEs come from the
corresponding per-draw probability functions above.

### Original counts

| Variant and quantity | Estimate | Exact | MCSE | Absolute discrepancy | Tolerance |
|---|---:|---:|---:|---:|---:|
| Bernoulli mean | 0.573993499 | 0.571428571 | 0.002648491 | 0.002564927 | 0.013242454 |
| Bernoulli mean squared | 0.360021049 | 0.357142857 | 0.003116580 | 0.002878192 | 0.015582899 |
| Bernoulli rho | 0.098145725 | 0.100000000 | 0.001272573 | 0.001854275 | 0.006362865 |
| Bernoulli rho squared | 0.017587568 | 0.018181818 | 0.000493896 | 0.000594250 | 0.003000000 |
| Bernoulli predictive `P(AC=1)` | 0.385789925 | 0.385714286 | 0.001665220 | 0.000075639 | 0.008326100 |
| Bernoulli predictive `P(AC=0)` | 0.233111539 | 0.235714286 | 0.002447923 | 0.002602747 | 0.012239615 |
| Central-AN2 mean | 0.499710927 | 0.500000000 | 0.002388304 | 0.000289073 | 0.011941519 |
| Central-AN2 mean squared | 0.272751145 | 0.272727273 | 0.002576756 | 0.000023872 | 0.012883779 |
| Central-AN2 rho | 0.071517411 | 0.071428571 | 0.000964270 | 0.000088840 | 0.004821351 |
| Central-AN2 rho squared | 0.009382401 | 0.009523810 | 0.000270821 | 0.000141409 | 0.003000000 |
| Central-AN2 predictive `P(AC=1)` | 0.421461830 | 0.422077922 | 0.001349029 | 0.000616093 | 0.006745145 |
| Central-AN2 predictive `P(AC=0)` | 0.289558158 | 0.288961039 | 0.002427778 | 0.000597119 | 0.012138890 |

Diagnostics were:

| Variant | Maximum R-hat | Minimum bulk ESS | Minimum tail ESS |
|---|---:|---:|---:|
| Bernoulli | 1.001614632 | 3492.988280 | 1905.104509 |
| Central-AN2 | 1.000749865 | 3274.685659 | 2146.518063 |

There were zero divergences.

## Repetition and allele complementation

Repeating the actual fitter with identical rows and configuration produced
bit-identical stored `mean_draws` and `rho_draws` on this pinned CPU runtime.

All counts were then complemented as `AC := AN - AC`; both `AN=0` rows remained
unavailable. The Bernoulli posterior becomes `mean ~ Beta(3,4)`, giving
`E(mean)=3/7` and `E(mean^2)=3/14`, while its rho posterior is unchanged. The
central-AN2 posterior is symmetric and unchanged. Bernoulli `P(AC=1)` remains
`27/70`, while complemented `P(AC=0)` is the original `P(AC=2)`, `53/140`.

| Variant and quantity | Estimate | Exact | MCSE | Absolute discrepancy | Tolerance |
|---|---:|---:|---:|---:|---:|
| Bernoulli mean | 0.430286243 | 0.428571429 | 0.002681245 | 0.001714815 | 0.013406225 |
| Bernoulli mean squared | 0.217046236 | 0.214285714 | 0.002545358 | 0.002760522 | 0.012726791 |
| Bernoulli rho | 0.098417187 | 0.100000000 | 0.001273661 | 0.001582813 | 0.006368307 |
| Bernoulli rho squared | 0.017934236 | 0.018181818 | 0.000504763 | 0.000247582 | 0.003000000 |
| Bernoulli predictive `P(AC=1)` | 0.384526859 | 0.385714286 | 0.001847941 | 0.001187427 | 0.009239706 |
| Bernoulli predictive `P(AC=0)` | 0.377450327 | 0.378571429 | 0.003032291 | 0.001121101 | 0.015161457 |
| Central-AN2 mean | 0.497272955 | 0.500000000 | 0.002459570 | 0.002727045 | 0.012297851 |
| Central-AN2 mean squared | 0.270616026 | 0.272727273 | 0.002613312 | 0.002111246 | 0.013066559 |
| Central-AN2 rho | 0.071244027 | 0.071428571 | 0.000987175 | 0.000184544 | 0.004935875 |
| Central-AN2 rho squared | 0.009493584 | 0.009523810 | 0.000291112 | 0.000030226 | 0.003000000 |
| Central-AN2 predictive `P(AC=1)` | 0.420912905 | 0.422077922 | 0.001298160 | 0.001165017 | 0.006490798 |
| Central-AN2 predictive `P(AC=0)` | 0.292270593 | 0.288961039 | 0.002497663 | 0.003309554 | 0.012488314 |

Complement diagnostics were:

| Variant | Maximum R-hat | Minimum bulk ESS | Minimum tail ESS |
|---|---:|---:|---:|
| Bernoulli | 1.004835393 | 3771.630209 | 2060.050688 |
| Central-AN2 | 1.003534751 | 3324.585870 | 1965.874374 |

There were zero complement-run divergences. In the recorded focused run, sampler
times were 2.675 seconds initially, 1.134 seconds for the identical-seed warm
repeat, and 1.125 seconds for the complemented fit; the complete pytest command
took 6.28 seconds. These timings only describe this tiny synthetic unit oracle and
are not performance benchmarks.

## Runtime and commands

The locked environment was Python 3.12.13 on macOS 26.5.1 arm64, using NumPy
2.4.6, SciPy 1.18.1, PyMC 6.3.1, PyTensor 3.3.0, ArviZ 1.3.0, xarray 2026.7.0,
JAX/JAXlib 0.11.1, and NumPyro 0.21.0. JAX reported one CPU device. The test
consumes float64 posterior arrays as required by the public fit contract.

The scientific proof was run with the prescribed cache locations and interpreter:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor \
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest \
tests/test_reference_heterogeneity_sampling.py -s
```

Focused regression tests, smoke, lint, and privacy checks were subsequently run
with the same locked interpreter/environment; their fresh results are reported in
the Task 2 handoff.

## Limits

These conjugate synthetic cases establish that the actual sampler and public
predictor reproduce two exact posterior distributions within predeclared Monte
Carlo uncertainty, preserve same-seed draws on this pinned CPU environment, and
respect allele-complement expectations. They do not establish an empirical AF
improvement, population-wide calibration, robustness under misspecification, or a
real-data advantage over B0. General quadrature, simulation-based calibration and
stress simulation, benchmark-runner integration, and the real paired comparison
remain open work under #211.

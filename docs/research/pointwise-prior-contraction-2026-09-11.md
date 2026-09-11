# Pointwise prior normalization for surface support

Issue [#266](https://github.com/bschilder/genomeOS/issues/266) repairs the denominator of the
Atlas support statistic. Posterior contraction now compares the posterior standard deviation of
latent frequency at each cell with the approximate latent prior standard deviation at that same
cell. The old scalar came from the first observation location. For finite HSGP and inducing
representations, marginal prior uncertainty can vary with the basis or inducing geometry, so a
different location's denominator can report apparent learning even when the local distribution
has not changed.

![Synthetic pointwise-prior normalization counterexample](https://raw.githubusercontent.com/bschilder/genomeOS/main/docs/figures/prior_normalization.png)

The figure is an authored synthetic counterexample, not population evidence or a fitted genetic
surface. A 96-point geometry grid determines 16 H3 inducing points; it does not represent measured
people. The Matérn-5/2 lengthscale is 1,500 km, amplitude is 1, production jitter is applied, and
the intercept is `Normal(-3.5, 1.5)`. An independent covariance solve and 256-point Gauss-Hermite
quadrature calculate the approximate prior frequency SD at 77 midpoint queries. The hypothetical
posterior SD is set equal to each query's local prior SD. At `(-25, 64)`, the unchanged local
distribution has ratio 1.0 with the matched denominator but about 0.895338 with the old scalar
reference, which crosses the 0.9 support threshold. Four distant controls remain `unknown` by the
unchanged distance rule. Grey background is unevaluated.

The production interface samples the retained PyMC model's existing `freq_pred` node at requested
coordinates. This includes the model's actual hyperpriors and HSGP or inducing geometry. The
protocol identifier is `pointwise_approximate_latent_v1`: 500 draws, the fit's explicit seed, and
population SD (`ddof=0`). Tests compare this interface with direct prior sampling on actual HSGP
and inducing graphs, including replay, order, batching, saved-fit reload, and model-data
restoration after success and failure.

New fit caches use format 2. Known owner-produced format-1 caches are reconstructed from their
retained posterior and predictive graph without refitting or rewriting the source cache; unknown
or incomplete structures refuse. New surface artifacts use format 3 and store the full-precision
per-cell denominator plus protocol metadata. Formats 1 and 2 remain readable as historical
artifacts without inferring new fields for them. Plot caches use format 2 and bind arrays to
the exact ordered H3 indexes and coordinates; incompatible caches remain untouched and require a
new path.

The denominator is a finite Monte Carlo estimate and therefore has sampling error. This repair
does not restore the inducing approximation's omitted `K-Q` covariance, evaluate the effect on a
real map, or establish calibrated fitted uncertainty. Those claims require the separate WP2
reference checks.

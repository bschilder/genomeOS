# B0H posterior and predictive-domain reconciliation

Issue #341 advances #211 and the global AF modeling plan. This design implements
Atlas design §§7–8 for exact offline count prediction. It repairs a numerical
contract mismatch exposed by the immutable B0H v2 calibration; it does not alter
that retained run, establish B0H superiority, or authorize publication.

## Scientific contract

1. **Objective.** Retain every valid finite B0H posterior draw admitted by the
   preregistered `rho ~ Beta(...)` model and evaluate its declared finite
   beta-binomial predictive law without clipping, dropping, or silently replacing
   a draw with a binomial law.
2. **Evidence.** A deterministic reproducer at the old concentration boundary,
   independent high-precision mass and CDF values, normalization and complement
   checks, exact discrete quantiles and PIT checks, the accepted direct-probability
   numerical evidence, focused regressions, full repository gates, and CPU/CUDA
   parity before a new GPU campaign.
3. **Component and interface.** `PopulationHeterogeneityFit` remains the immutable
   posterior artifact. `CountPredictive` remains the public scoring interface.
   New pure numerical helpers provide complete-support beta-binomial mass, lower
   tail, and upper tail on an explicit NumPy or CuPy namespace.
4. **Assumptions, refusals, and consumers.** Counts remain bounded by the public
   int32 domain. Complete-support arithmetic for high-concentration draws is
   admitted only through `AN=65,536`. Lower-concentration log mass uses the
   bounded rising-factorial route across the public count domain, while its
   large-count CDF retains the validated shorter-tail route. Inputs whose beta
   shapes underflow, overflow, or exceed the proved concentration ceiling are
   refused. Consumers are the B0H diagnostics, #211 comparison, #331, and later
   WP4 comparisons.

## Failure and scope

The frozen B0H v2 runner completed, but one fit-bearing case failed while
constructing `PopulationHeterogeneityFit`. The model admitted a positive `rho`
whose derived concentration exceeded the predictor's old
`1/sqrt(float64 epsilon) = 67,108,864` ceiling. The frozen reducer therefore
correctly made the whole scientific claim ineligible.

The minimal deterministic neighborhood uses concentration `2**27 = 134,217,728`
and `rho = 1/(concentration+1)`, immediately across the old boundary. Tests also
cover larger finite concentrations and the limit behavior without treating the
limit as the finite law.

## Numerical route

For draws above the legacy concentration boundary with `AN <= 65,536`, compute
adjacent-mass ratios from a legal modal anchor and visit the complete finite
support in bounded chunks. Store weights as a normalized float64 high/residual
pair and a separate int64 binary exponent. This prevents physical underflow
during products and summation. Partition every support into mass below the
target, mass at the target, and mass above it, normalize once, and average the
selected posterior draws with the same scaled arithmetic. Lower-concentration
draws retain the existing finite-product log mass through `AN=65,536` and the
shorter-tail CDF path. Above that count, log mass uses the independently
qualified bounded rising-factorial formulation from #314; it evaluates a fixed
prefix and Euler--Maclaurin tail without materializing the count support.

The implementation is the independently reviewed direct-probability core whose
frozen source hashes are:

- `count_probability.py`:
  `3c396fca458fd0fbd241f127b14694fca2ad2a03927b1acc106ddce25edecebe`
- `count_scaled.py`:
  `239a4a71e6c917f14efbb97abde380a1294f0b1ebdf9310bfc9bd4aa33de30a8`

Its E1–E3 numerical campaign accepted the four frozen numerical stages. Importing
the reviewed source does not itself establish production integration or CUDA
performance; those are separate checks in this issue.

Select an existing proved support chunk from the validated host maximum:

- `32` for maximum `AN <= 32`;
- `256` for maximum `AN <= 256`;
- `1024` otherwise.

This keeps B0H's short supports vectorized without constructing 1,024-wide work
arrays. The scientific loops are over bounded support, draw, and observation
chunks; arithmetic within each chunk is array-based. No loop dispatches one
posterior draw or one support point at a time.

For a selected high-concentration subgroup, the direct core returns its mean mass
and both tails together. `log_prob` takes the logarithm from the scaled
representation so a representable log score is not erased when physical
probability is subnormal. It combines the high and legacy subgroup means using
their original draw counts in log space, with a near-one residual formula.
`cdf` combines the corresponding subgroup CDFs at the public float64 boundary.
Quantiles continue to binary-search the finite support using the same CDF.

## Domain policy

`CountPredictive` construction validates the artifact rather than a particular
operation. Interior means require finite positive alpha and beta. Finite positive
concentration is supported through the direct core's proved ceiling `1e300`.
This allows `PopulationHeterogeneityFit` to retain a valid posterior independently
of which diagnostic is requested later.

Operation policy is explicit:

| Operation | Complete-support route | Legacy route | Refusal |
| --- | --- | --- | --- |
| mass/log score | draws above `67,108,864`, `AN <= 65,536` | lower-concentration draws through the public count bound | high concentration and larger `AN` |
| CDF/quantile | draws above `67,108,864`, `AN <= 65,536` | lower-concentration draws through the public count bound | high concentration and larger `AN` |
| sampling | NumPy beta then binomial after the same operation-domain check | lower concentration through public count bound | high concentration and larger `AN` |
| exact mean endpoints | analytical point mass | analytical point mass | none within public count bound |

The policy is evaluated per draw and observation. A high concentration in one
posterior draw never causes that draw to be discarded and never forces every
ordinary draw through the costlier scaled recurrence. Mixed subgroups are
recombined using the unchanged total draw count.

## CPU and CUDA boundaries

The numerical core accepts an explicit array namespace. The CPU path passes
NumPy. `CuPyCDF` keeps ordinary observation columns on its established batched
tail path and sends columns containing a high-concentration draw through the
direct CuPy core, followed by one blocking conversion of the packed result. It
never falls back to CPU. Binomial prediction retains its current backend. A
missing CUDA device remains a hard error.

The existing local RunPod credential currently receives HTTP 403 from the exact
v2 pod endpoint, including through the credential used by `runpodctl`. Therefore
CUDA qualification cannot be claimed from local tests. Production code may be
prepared and CPU-verified, but a new immutable B0H run remains barred until the
frozen GPU parity/performance seam completes and deletion authority passes its
pre-create watchdog check.

## Acceptance and refusal evidence

The implementation is acceptable only when all of the following hold:

- construction succeeds for the equivalent frozen failure neighborhood and the
  resulting fit round-trips through the existing evidence codec;
- mass and CDF match an independent Decimal oracle at unchanged or stronger
  tolerances across the old boundary, extremes, complements, and identities;
- integrated mass plus strict upper/lower partitions normalize, quantiles remain
  left-continuous, randomized PIT stays in `[0,1]`, and binomial-limit convergence
  is demonstrated without substituting the binomial distribution;
- all accepted direct-core tests and existing predictive/B0H tests pass;
- Ruff, contracts, module-size, privacy, smoke, and full pytest pass;
- actual-device CPU/CuPy parity and bounded performance pass before campaign use;
- a new immutable calibration version completes all 1,936 fit-bearing cases and
  two expected structural refusals before #211 consumes it.

Malformed shapes, nonfinite parameters, nonpositive concentration, unusable beta
shapes, counts outside the public domain, and unsupported operation domains remain
hard errors. Numerical errors are never relabeled as convergence failures.

## Rejected approaches

- Truncating the rho prior would change the preregistered model and hide the
  original mismatch.
- Clipping or dropping posterior draws would bias the predictive mixture.
- Replacing large finite concentration with a binomial would change the declared
  law even when the two are close.
- Reusing closed PR #274 would restore 11 known subnormal mass/tail mismatches and
  measured runtime regressions.
- Extending beta-normalizer subtraction beyond its observed stable boundary would
  reproduce the failure without a numerical argument.

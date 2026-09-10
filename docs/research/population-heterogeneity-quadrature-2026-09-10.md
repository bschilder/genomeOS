# B0H nonconjugate quadrature/NUTS evidence (2026-09-10)

This note records a predeclared small-case numerical characterization of
`B0H_population_heterogeneity`. It does not use real data and makes no empirical
allele-frequency improvement claim.

## Frozen protocol

Before the first sampler run, the synthetic `(AC, AN)` matrix was fixed as:

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

The mean prior was `Beta(1,1)`. Every case was evaluated as written and after
allele complementation (`AC := AN - AC`). The withheld predictive denominator
was 5. Each of the four actual fits used four vectorized NumPyro NUTS chains,
2,000 tuning steps, 2,000 retained draws, `target_accept=0.9`, and seed 42.
There was no retry, hidden seed selection, or tolerance adjustment.

For every scalar quadrature result (log evidence, five moments, and six
predictive masses), both the order 64-to-128 and order 128-to-256 absolute gaps
had to be at most `1e-8`; order 32-to-64 gaps were retained as evidence. Actual
sampler quantities required finite positive ArviZ MCSE at most `0.005`, and
absolute discrepancy at most `max(5 * MCSE, 0.003)`.

## Measured evidence

The exact frozen protocol above was written to the test source before sampling
began. All quadrature refinement and complement-symmetry assertions passed. The
maximum absolute scalar gap for each case, prior, orientation, and adjacent order
pair is below; every maximum covers log evidence, all five moments, and all six
predictive masses.

| Rho prior | Orientation | Case | 32→64 | 64→128 | 128→256 |
|---|---|---|---:|---:|---:|
| Beta(1,9) | original | mixed | 1.083578e-13 | 1.616485e-13 | 2.255973e-13 |
| Beta(1,9) | original | rare | 1.387779e-14 | 2.066403e-14 | 2.581269e-14 |
| Beta(1,9) | original | unequal_an | 4.796163e-14 | 6.039613e-14 | 4.973799e-14 |
| Beta(1,9) | complement | mixed | 1.083578e-13 | 1.616485e-13 | 2.255973e-13 |
| Beta(1,9) | complement | rare | 1.393330e-14 | 2.067790e-14 | 2.581269e-14 |
| Beta(1,9) | complement | unequal_an | 4.796163e-14 | 6.039613e-14 | 4.973799e-14 |
| Beta(1,4) | original | mixed | 3.375078e-14 | 5.861978e-14 | 1.012523e-13 |
| Beta(1,4) | original | rare | 1.332268e-14 | 1.618150e-14 | 1.726397e-14 |
| Beta(1,4) | original | unequal_an | 4.263256e-14 | 8.704149e-14 | 3.375078e-14 |
| Beta(1,4) | complement | mixed | 3.552714e-14 | 5.861978e-14 | 1.012523e-13 |
| Beta(1,4) | complement | rare | 1.332268e-14 | 1.634803e-14 | 1.720846e-14 |
| Beta(1,4) | complement | unequal_an | 4.263256e-14 | 8.881784e-14 | 3.197442e-14 |

The worst refinement gap was `2.255973186038318e-13`, well inside the
predeclared `1e-8` threshold. At order 256, complement symmetry also held within
`1e-8` for log evidence, all five required moment mappings, and reversal of all
six predictive masses. This is strong finite-order numerical convergence, not an
exact proof.

## Actual sampler and predictor

The first complete command did not pass. The original-orientation `Beta(1,9)`
fit failed *inside the public fitter*, before any test-side draw adapter or
predictor call, with 276 divergent transitions. The unchanged production gate
raised `HeterogeneityConvergenceError("sampler produced divergent transitions")`;
PyMC also logged that ESS per chain was below 100 for some parameters. The fit
returned no posterior contract, so no MCSE comparison exists for that call. This
failed primary-prior result was retained and was not retried to obtain a pass.

One explicitly labeled instrumented reproduction by the root investigator (not
a retry or a seed search) reproduced exactly 276 divergences, all in chain 0, and
captured the finite diagnostics carried by the public exception:

| Variant | Maximum R-hat | Minimum bulk ESS | Minimum tail ESS |
|---|---:|---:|---:|
| mixed | 1.525862537 | 7.238695151 | 9.234441171 |
| rare | 1.531188058 | 7.182769247 | 12.601968165 |
| unequal_an | 1.524777390 | 7.142152216 | 4.016064257 |

The same capture showed chain 0 numerically frozen. In particular, its rare-case
rho was `0.9999996067208309`, while its unequal-AN state had mean
`0.9120608465340185` and rho `8.091265212637455e-18` (kappa approximately
`1.2e17`). The other three chains moved. These values describe the failure; they
do not establish its cause by themselves.

A subsequent root-owned fixed-point probe localized the defect. At that trapped
unequal-AN point, the JAXified PyMC `BetaBinomial` log likelihood was spuriously
`+6160` with gradient `[0, 0]`; the independent finite-product likelihood was
`-26.757334358778397` with gradient
`[-14.834190475224663, 2.784e-15]`. Other trapped-case likelihood terms agreed.
Chain 0's NUTS step size was `6.756e-14`, versus approximately `0.32`–`0.45` for
the moving chains. The evidence therefore identifies numerical gamma-function
cancellation and a spurious high-density trap in the current production graph,
not quadrature nonconvergence or a justification to relax the sampler gates.
The local diagnostic source is
`/private/tmp/genomeos-b0h-oracle-plan.SWEvS5/extreme-gradient-results.jsonl`;
it is intentionally not a committed artifact.

The other three independently parametrized calls passed the production gates
and every fixed MCSE/discrepancy rule. Values below are public-predictor estimates
for predictive rows and direct labeled-chain/draw means for moments. `Ref` is the
order-256 quadrature result.

### Rho Beta(1,4), original counts

| Case | Quantity | Estimate | Ref | MCSE | Bound |
|---|---|---:|---:|---:|---:|
| mixed | mean | 0.557490107 | 0.560150095 | 0.001501489 | 0.007507443 |
| mixed | mean_squared | 0.329667528 | 0.331501744 | 0.001608856 | 0.008044282 |
| mixed | rho | 0.269651927 | 0.268845097 | 0.001574714 | 0.007873571 |
| mixed | rho_squared | 0.094435389 | 0.093430519 | 0.000988922 | 0.004944609 |
| mixed | mean_rho | 0.146974924 | 0.147482017 | 0.000935236 | 0.004676182 |
| mixed | predictive AC=0 | 0.129866892 | 0.126335725 | 0.001551641 | 0.007758203 |
| mixed | predictive AC=1 | 0.133228081 | 0.132893009 | 0.000619470 | 0.003097352 |
| mixed | predictive AC=2 | 0.160476786 | 0.161067289 | 0.000625842 | 0.003129212 |
| mixed | predictive AC=3 | 0.181110095 | 0.182321989 | 0.000803970 | 0.004019850 |
| mixed | predictive AC=4 | 0.186652133 | 0.188153019 | 0.000782677 | 0.003913385 |
| mixed | predictive AC=5 | 0.208666013 | 0.209228969 | 0.001479348 | 0.007396741 |
| rare | mean | 0.077878355 | 0.078025049 | 0.000844397 | 0.004221987 |
| rare | mean_squared | 0.010802808 | 0.010604879 | 0.000302858 | 0.003000000 |
| rare | rho | 0.198870471 | 0.200178725 | 0.002003303 | 0.010016517 |
| rare | rho_squared | 0.067229036 | 0.066586554 | 0.001214411 | 0.006072055 |
| rare | mean_rho | 0.021560405 | 0.021312892 | 0.000492169 | 0.003000000 |
| rare | predictive AC=0 | 0.777100899 | 0.776174436 | 0.001458390 | 0.007291949 |
| rare | predictive AC=1 | 0.132186039 | 0.132452036 | 0.000661920 | 0.003309602 |
| rare | predictive AC=2 | 0.047135128 | 0.047753703 | 0.000415047 | 0.003000000 |
| rare | predictive AC=3 | 0.021475931 | 0.021899012 | 0.000304361 | 0.003000000 |
| rare | predictive AC=4 | 0.012002325 | 0.012135298 | 0.000254388 | 0.003000000 |
| rare | predictive AC=5 | 0.010099678 | 0.009585515 | 0.000394667 | 0.003000000 |
| unequal_an | mean | 0.473657393 | 0.472498284 | 0.001183784 | 0.005918918 |
| unequal_an | mean_squared | 0.235635186 | 0.234758513 | 0.001140671 | 0.005703356 |
| unequal_an | rho | 0.104435294 | 0.102803690 | 0.000922256 | 0.004611278 |
| unequal_an | rho_squared | 0.019686675 | 0.018880615 | 0.000407360 | 0.003000000 |
| unequal_an | mean_rho | 0.048662091 | 0.047554080 | 0.000482856 | 0.003000000 |
| unequal_an | predictive AC=0 | 0.102143808 | 0.102743035 | 0.001140507 | 0.005702533 |
| unequal_an | predictive AC=1 | 0.188174178 | 0.188844504 | 0.000714709 | 0.003573546 |
| unequal_an | predictive AC=2 | 0.247950519 | 0.248103415 | 0.000658515 | 0.003292576 |
| unequal_an | predictive AC=3 | 0.234010280 | 0.233925357 | 0.000722766 | 0.003613829 |
| unequal_an | predictive AC=4 | 0.156425169 | 0.156254427 | 0.000685182 | 0.003425911 |
| unequal_an | predictive AC=5 | 0.071296047 | 0.070129262 | 0.000845469 | 0.004227346 |

Diagnostics: mixed R-hat `1.000840289`, bulk ESS `7275.554106`, tail ESS
`4140.470682`; rare `1.000009761`, `5998.334991`, `4477.090994`; unequal_an
`1.000786762`, `8070.754658`, `3963.385473`. There were zero divergences.

### Rho Beta(1,9), complemented counts

| Case | Quantity | Estimate | Ref | MCSE | Bound |
|---|---|---:|---:|---:|---:|
| mixed | mean | 0.422703014 | 0.422923999 | 0.001454857 | 0.007274283 |
| mixed | mean_squared | 0.194873238 | 0.194091718 | 0.001324256 | 0.006621279 |
| mixed | rho | 0.163544756 | 0.163151323 | 0.001106494 | 0.005532469 |
| mixed | rho_squared | 0.037905092 | 0.037506906 | 0.000449017 | 0.003000000 |
| mixed | mean_rho | 0.071273582 | 0.070991527 | 0.000652559 | 0.003262794 |
| mixed | predictive AC=0 | 0.172352623 | 0.170201518 | 0.001522815 | 0.007614075 |
| mixed | predictive AC=1 | 0.215806365 | 0.216525351 | 0.000811911 | 0.004059554 |
| mixed | predictive AC=2 | 0.221506462 | 0.222971931 | 0.000811437 | 0.004057184 |
| mixed | predictive AC=3 | 0.184506644 | 0.185645511 | 0.000646278 | 0.003231392 |
| mixed | predictive AC=4 | 0.127963677 | 0.128064197 | 0.000751889 | 0.003759444 |
| mixed | predictive AC=5 | 0.077864228 | 0.076591493 | 0.001088712 | 0.005443560 |
| rare | mean | 0.942250107 | 0.943240698 | 0.000565448 | 0.003000000 |
| rare | mean_squared | 0.890018075 | 0.891728926 | 0.001005476 | 0.005027380 |
| rare | rho | 0.100912576 | 0.099471525 | 0.001030804 | 0.005154020 |
| rare | rho_squared | 0.018587959 | 0.018192607 | 0.000383001 | 0.003000000 |
| rare | mean_rho | 0.093190844 | 0.092107201 | 0.000896807 | 0.004484036 |
| rare | predictive AC=0 | 0.001724628 | 0.001560845 | 0.000100563 | 0.003000000 |
| rare | predictive AC=1 | 0.004604223 | 0.004311150 | 0.000146216 | 0.003000000 |
| rare | predictive AC=2 | 0.012766842 | 0.012288943 | 0.000244725 | 0.003000000 |
| rare | predictive AC=3 | 0.039615496 | 0.039026754 | 0.000428687 | 0.003000000 |
| rare | predictive AC=4 | 0.144177916 | 0.143827350 | 0.000758949 | 0.003794747 |
| rare | predictive AC=5 | 0.797110895 | 0.798984958 | 0.001398152 | 0.006990761 |
| unequal_an | mean | 0.522106733 | 0.522716430 | 0.001133956 | 0.005669782 |
| unequal_an | mean_squared | 0.282972181 | 0.283522689 | 0.001229114 | 0.006145569 |
| unequal_an | rho | 0.068517925 | 0.068965480 | 0.000599994 | 0.003000000 |
| unequal_an | rho_squared | 0.008613257 | 0.008690006 | 0.000168444 | 0.003000000 |
| unequal_an | mean_rho | 0.036404134 | 0.036741495 | 0.000374298 | 0.003000000 |
| unequal_an | predictive AC=0 | 0.059062382 | 0.058652279 | 0.000674164 | 0.003370820 |
| unequal_an | predictive AC=1 | 0.157885351 | 0.157668476 | 0.000748507 | 0.003742533 |
| unequal_an | predictive AC=2 | 0.249425115 | 0.249378686 | 0.000694394 | 0.003471970 |
| unequal_an | predictive AC=3 | 0.263379134 | 0.263271478 | 0.000633677 | 0.003168387 |
| unequal_an | predictive AC=4 | 0.187579411 | 0.187803535 | 0.000773916 | 0.003869578 |
| unequal_an | predictive AC=5 | 0.082668608 | 0.083225545 | 0.000959838 | 0.004799188 |

Diagnostics: mixed R-hat `1.000582490`, bulk ESS `6540.113016`, tail ESS
`3410.273824`; rare `1.000081704`, `6459.914971`, `4064.012613`; unequal_an
`1.000281403`, `7414.923613`, `4219.253418`. There were zero divergences.

### Rho Beta(1,4), complemented counts

| Case | Quantity | Estimate | Ref | MCSE | Bound |
|---|---|---:|---:|---:|---:|
| mixed | mean | 0.440229540 | 0.439849905 | 0.001495851 | 0.007479257 |
| mixed | mean_squared | 0.212585206 | 0.211201554 | 0.001449659 | 0.007248293 |
| mixed | rho | 0.270661629 | 0.268845097 | 0.001482895 | 0.007414474 |
| mixed | rho_squared | 0.094978260 | 0.093430519 | 0.000943533 | 0.004717663 |
| mixed | mean_rho | 0.122692146 | 0.121363080 | 0.000973506 | 0.004867528 |
| mixed | predictive AC=0 | 0.211012783 | 0.209228969 | 0.001503176 | 0.007515879 |
| mixed | predictive AC=1 | 0.187449369 | 0.188153019 | 0.000762255 | 0.003811274 |
| mixed | predictive AC=2 | 0.180886925 | 0.182321989 | 0.000799343 | 0.003996715 |
| mixed | predictive AC=3 | 0.159583829 | 0.161067289 | 0.000591856 | 0.003000000 |
| mixed | predictive AC=4 | 0.132162480 | 0.132893009 | 0.000644250 | 0.003221251 |
| mixed | predictive AC=5 | 0.128904615 | 0.126335725 | 0.001486106 | 0.007430531 |
| rare | mean | 0.921009942 | 0.921974951 | 0.000955818 | 0.004779088 |
| rare | mean_squared | 0.853096358 | 0.854554780 | 0.001559246 | 0.007796231 |
| rare | rho | 0.201867819 | 0.200178725 | 0.001924956 | 0.009624780 |
| rare | rho_squared | 0.067920004 | 0.066586554 | 0.001224323 | 0.006121615 |
| rare | mean_rho | 0.179994296 | 0.178865832 | 0.001537394 | 0.007686972 |
| rare | predictive AC=0 | 0.010108044 | 0.009585515 | 0.000499338 | 0.003000000 |
| rare | predictive AC=1 | 0.012412959 | 0.012135298 | 0.000272173 | 0.003000000 |
| rare | predictive AC=2 | 0.022119662 | 0.021899012 | 0.000316864 | 0.003000000 |
| rare | predictive AC=3 | 0.047927309 | 0.047753703 | 0.000432126 | 0.003000000 |
| rare | predictive AC=4 | 0.132544628 | 0.132452036 | 0.000692232 | 0.003461158 |
| rare | predictive AC=5 | 0.774887397 | 0.776174436 | 0.001606481 | 0.008032403 |
| unequal_an | mean | 0.529334492 | 0.527501716 | 0.001299186 | 0.006495932 |
| unequal_an | mean_squared | 0.291793391 | 0.289761944 | 0.001431940 | 0.007159698 |
| unequal_an | rho | 0.102971701 | 0.102803690 | 0.000902536 | 0.004512682 |
| unequal_an | rho_squared | 0.018934370 | 0.018880615 | 0.000369483 | 0.003000000 |
| unequal_an | mean_rho | 0.055324580 | 0.055249610 | 0.000565117 | 0.003000000 |
| unequal_an | predictive AC=0 | 0.069756415 | 0.070129262 | 0.000881600 | 0.004407999 |
| unequal_an | predictive AC=1 | 0.154670756 | 0.156254427 | 0.000711918 | 0.003559589 |
| unequal_an | predictive AC=2 | 0.232761146 | 0.233925357 | 0.000745461 | 0.003727304 |
| unequal_an | predictive AC=3 | 0.248597767 | 0.248103415 | 0.000690075 | 0.003450376 |
| unequal_an | predictive AC=4 | 0.190383472 | 0.188844504 | 0.000734613 | 0.003673065 |
| unequal_an | predictive AC=5 | 0.103830444 | 0.102743035 | 0.001253207 | 0.006266037 |

Diagnostics: mixed R-hat `1.000439585`, bulk ESS `8204.732651`, tail ESS
`4177.757487`; rare `0.999946493`, `5998.107961`, `4381.085709`; unequal_an
`1.000299179`, `6928.079706`, `3809.038997`. There were zero divergences.

Across the three successful calls, all MCSE values were finite and positive; the
largest was `0.002003303`, below `0.005`. The largest absolute discrepancy was
`0.003531167` for the original Beta(1,4) mixed-case `AC=0` predictive mass, below
its measured bound `0.007758203`. The public predictor values were checked against
every order-256 predictive mass with the corresponding independently evaluated
per-draw mass MCSE. All `AN=0` training record IDs remained explicitly unavailable,
and query groups were disjoint from all training groups.

## Environment and commands

The locked environment was Python 3.12.13, NumPy 2.4.6, SciPy 1.18.1, PyMC
6.3.1, PyTensor 3.3.0, ArviZ 1.3.0, xarray 2026.7.0, JAX 0.11.1, and NumPyro
0.21.0. Posterior quantities were selected through explicit `chain`, `draw`, and
`variant` labels; chains were never flattened before MCSE computation.

The first prescribed command was:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor \
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest \
tests/test_reference_heterogeneity_quadrature.py -s
```

Outcome: `4 failed in 42.39s`: one scientific convergence refusal and three
test-harness stops described above. After correcting only the two mechanical
harness defects, the quadrature-only command passed (`2 passed in 1.31s`) and a
single command covering the three previously incomplete comparison nodes passed
(`3 passed in 8.26s`). The original Beta(1,4) fit was repeated solely because its
first execution had stopped at the corrected xarray adapter before comparisons;
this plumbing rerun is explicit and was not seed selection. The original
primary-prior fit was not duplicated by this task agent.

To avoid duplicating the known failed fit while its scoped diagnosis was in
progress, the unaffected regression set was run separately:

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest \
tests/test_heterogeneity_oracle.py tests/test_reference_heterogeneity.py \
tests/test_reference_heterogeneity_sampling.py tests/test_reference_counts.py
```

Outcome: `192 passed in 7.17s`.

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
```

Outcome: `contract up to date`, 40 smoke tests passed, and
`smoke checks passed`.

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
```

Outcome: `All checks passed!`.

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

Outcome before staging: `private-file check passed (685 tracked files)`.
After staging exactly the test and research note, the mandatory privacy rerun
passed with `687 tracked files`; `git diff --cached --name-only` listed only
those two task files and `git diff --cached --check` was clean.

The exact combined regression command including the new scientific file is not
reported as passing: its primary-prior/original node is the retained convergence
failure above. It was not duplicated after the instrumented capture merely to
produce a second identical failing log.

## Interpretation and limits

The deterministic reference is a convergence-checked order-256 numerical
calculation, not exact symbolic proof. The three successful actual fits establish
computational agreement on their stated synthetic cases only. The asymmetric
failure of the original primary-prior batched fit is negative computational
fidelity evidence and a hard RED regression for the localized production
numerical defect; it remains blocking for this full scientific check. None of
these results establishes empirical improvement, broad simulation-based
calibration, robustness to model misspecification, geographic validity, or a
real-data advantage over B0.


## Code-corrected rerun after #214

The bounded likelihood correction was applied only to the observed density evaluation. The
frozen counts, priors, sampler configuration, seed, quadrature references, diagnostic gates,
MCSE rule and discrepancy threshold above were unchanged. This rerun does not replace or erase
the original 276-divergence failure; it tests the corrected arithmetic against the same oracles.

The unchanged exact sampler oracle passed in 7.77 seconds (`1 passed`). Its original,
identical-seed repeat and complemented fits each had zero divergences, and the repeated posterior
draw arrays remained exactly equal. All 24 exact posterior/predictive comparisons passed their
fixed MCSE-derived bounds. The unchanged full nonconjugate file then passed in 23.90 seconds
(`6 passed`): both quadrature refinement nodes and all four actual sampler tracks passed. The
test output does not separate compilation from sampling time, so no compile-versus-sampling
speed claim is made.

A follow-up output-capture invocation selected the same four already-passing actual NUTS nodes,
with the same seed and configuration, solely to retain the complete per-quantity evidence below.
It was not a retry after failure or a favorable-seed selection. Every track had zero divergences.

### Post-fix diagnostics

| Rho prior | Orientation | Case | Max R-hat | Min bulk ESS | Min tail ESS |
|---|---|---|---:|---:|---:|
| Beta(1,9) | original | mixed | 1.00038097 | 6447.43656 | 3629.18050 |
| Beta(1,9) | original | rare | 1.00041873 | 6076.38047 | 4001.66563 |
| Beta(1,9) | original | unequal_an | 1.00081144 | 6164.33544 | 3587.54235 |
| Beta(1,4) | original | mixed | 1.00120851 | 6364.04739 | 3635.44888 |
| Beta(1,4) | original | rare | 1.00003310 | 5830.41990 | 4534.01988 |
| Beta(1,4) | original | unequal_an | 1.00135254 | 5943.66478 | 3129.40886 |
| Beta(1,9) | complement | mixed | 1.00039688 | 6568.54913 | 3785.99041 |
| Beta(1,9) | complement | rare | 1.00085259 | 6160.62904 | 4205.80313 |
| Beta(1,9) | complement | unequal_an | 1.00111538 | 6378.68878 | 3731.18230 |
| Beta(1,4) | complement | mixed | 1.00059571 | 7671.59315 | 3955.32486 |
| Beta(1,4) | complement | rare | 1.00010745 | 5501.64579 | 4194.28375 |
| Beta(1,4) | complement | unequal_an | 1.00075508 | 5923.66877 | 3631.26217 |

All R-hat values were finite and at most 1.00135254; all bulk ESS values were finite
and at least 5,501.64579; all tail ESS values were finite and at least 3,129.40886.
These are inside the unchanged R-hat <=1.05 and ESS >=200 gates.

### Post-fix per-quantity comparisons

| Rho prior | Orientation | Case | Quantity | Estimate | Reference | MCSE | Absolute discrepancy | Bound |
|---|---|---|---|---:|---:|---:|---:|---:|
| Beta(1,9) | original | mixed | mean | 0.574344150 | 0.577076001 | 0.00141818681 | 0.00273185106 | 0.00709093405 |
| Beta(1,9) | original | mixed | mean_squared | 0.346122617 | 0.348243720 | 0.00153066813 | 0.00212110256 | 0.00765334063 |
| Beta(1,9) | original | mixed | rho | 0.163501784 | 0.163151323 | 0.00115695613 | 0.000350461120 | 0.00578478065 |
| Beta(1,9) | original | mixed | rho_squared | 0.0378654666 | 0.0375069059 | 0.000489918522 | 0.000358560711 | 0.00300000000 |
| Beta(1,9) | original | mixed | mean_rho | 0.0917502906 | 0.0921597960 | 0.000650123396 | 0.000409505394 | 0.00325061698 |
| Beta(1,9) | original | mixed | predictive_ac_0 | 0.0794319700 | 0.0765914928 | 0.00126364036 | 0.00284047721 | 0.00631820179 |
| Beta(1,9) | original | mixed | predictive_ac_1 | 0.129137480 | 0.128064197 | 0.000719601546 | 0.00107328312 | 0.00359800773 |
| Beta(1,9) | original | mixed | predictive_ac_2 | 0.185527964 | 0.185645511 | 0.000644952632 | 0.000117546732 | 0.00322476316 |
| Beta(1,9) | original | mixed | predictive_ac_3 | 0.221637240 | 0.222971931 | 0.000817143065 | 0.00133469084 | 0.00408571532 |
| Beta(1,9) | original | mixed | predictive_ac_4 | 0.214711110 | 0.216525351 | 0.000826253670 | 0.00181424134 | 0.00413126835 |
| Beta(1,9) | original | mixed | predictive_ac_5 | 0.169554236 | 0.170201518 | 0.00128941710 | 0.000647281414 | 0.00644708551 |
| Beta(1,9) | original | rare | mean | 0.0556689502 | 0.0567593023 | 0.000577739165 | 0.00109035205 | 0.00300000000 |
| Beta(1,9) | original | rare | mean_squared | 0.00517810097 | 0.00524753019 | 0.000170101628 | 0.0000694292235 | 0.00300000000 |
| Beta(1,9) | original | rare | rho | 0.0987794113 | 0.0994715248 | 0.00103285686 | 0.000692113554 | 0.00516428428 |
| Beta(1,9) | original | rare | rho_squared | 0.0183766613 | 0.0181926074 | 0.000402750862 | 0.000184053887 | 0.00300000000 |
| Beta(1,9) | original | rare | mean_rho | 0.00726680630 | 0.00736432382 | 0.000202198472 | 0.0000975175162 | 0.00300000000 |
| Beta(1,9) | original | rare | predictive_ac_0 | 0.802441623 | 0.798984958 | 0.00144241226 | 0.00345666513 | 0.00721206129 |
| Beta(1,9) | original | rare | predictive_ac_1 | 0.141996443 | 0.143827350 | 0.000805322506 | 0.00183090717 | 0.00402661253 |
| Beta(1,9) | original | rare | predictive_ac_2 | 0.0378811223 | 0.0390267538 | 0.000424714252 | 0.00114563154 | 0.00300000000 |
| Beta(1,9) | original | rare | predictive_ac_3 | 0.0118171182 | 0.0122889433 | 0.000229021593 | 0.000471825123 | 0.00300000000 |
| Beta(1,9) | original | rare | predictive_ac_4 | 0.00418375798 | 0.00431114985 | 0.000137789564 | 0.000127391865 | 0.00300000000 |
| Beta(1,9) | original | rare | predictive_ac_5 | 0.00167993546 | 0.00156084489 | 0.000146067822 | 0.000119090570 | 0.00300000000 |
| Beta(1,9) | original | unequal_an | mean | 0.477368301 | 0.477283570 | 0.00121949663 | 0.0000847311048 | 0.00609748313 |
| Beta(1,9) | original | unequal_an | mean_squared | 0.238249991 | 0.238089829 | 0.00112686954 | 0.000160162017 | 0.00563434772 |
| Beta(1,9) | original | unequal_an | rho | 0.0690587302 | 0.0689654800 | 0.000638574167 | 0.0000932501985 | 0.00319287083 |
| Beta(1,9) | original | unequal_an | rho_squared | 0.00869986187 | 0.00869000588 | 0.000176990552 | 0.00000985598952 | 0.00300000000 |
| Beta(1,9) | original | unequal_an | mean_rho | 0.0322648194 | 0.0322239851 | 0.000319633989 | 0.0000408343357 | 0.00300000000 |
| Beta(1,9) | original | unequal_an | predictive_ac_0 | 0.0835514970 | 0.0832255452 | 0.00114975003 | 0.000325951837 | 0.00574875013 |
| Beta(1,9) | original | unequal_an | predictive_ac_1 | 0.187314874 | 0.187803535 | 0.000793619900 | 0.000488661179 | 0.00396809950 |
| Beta(1,9) | original | unequal_an | predictive_ac_2 | 0.263044004 | 0.263271478 | 0.000638965668 | 0.000227474215 | 0.00319482834 |
| Beta(1,9) | original | unequal_an | predictive_ac_3 | 0.249605680 | 0.249378686 | 0.000761396081 | 0.000226993046 | 0.00380698040 |
| Beta(1,9) | original | unequal_an | predictive_ac_4 | 0.157798142 | 0.157668476 | 0.000770855910 | 0.000129666563 | 0.00385427955 |
| Beta(1,9) | original | unequal_an | predictive_ac_5 | 0.0586858030 | 0.0586522791 | 0.000673664774 | 0.0000335239490 | 0.00336832387 |
| Beta(1,4) | original | mixed | mean | 0.557915093 | 0.560150095 | 0.00154994720 | 0.00223500177 | 0.00774973599 |
| Beta(1,4) | original | mixed | mean_squared | 0.330078147 | 0.331501744 | 0.00168288176 | 0.00142359723 | 0.00841440879 |
| Beta(1,4) | original | mixed | rho | 0.270549207 | 0.268845097 | 0.00167052402 | 0.00170411039 | 0.00835262012 |
| Beta(1,4) | original | mixed | rho_squared | 0.0946515428 | 0.0934305194 | 0.00102184493 | 0.00122102337 | 0.00510922466 |
| Beta(1,4) | original | mixed | mean_rho | 0.147464981 | 0.147482017 | 0.000970371417 | 0.0000170360671 | 0.00485185709 |
| Beta(1,4) | original | mixed | predictive_ac_0 | 0.129942525 | 0.126335725 | 0.00156548564 | 0.00360679962 | 0.00782742820 |
| Beta(1,4) | original | mixed | predictive_ac_1 | 0.132953785 | 0.132893009 | 0.000634725115 | 0.0000607763060 | 0.00317362558 |
| Beta(1,4) | original | mixed | predictive_ac_2 | 0.160096461 | 0.161067289 | 0.000621145327 | 0.000970828257 | 0.00310572663 |
| Beta(1,4) | original | mixed | predictive_ac_3 | 0.180876599 | 0.182321989 | 0.000834658496 | 0.00144539039 | 0.00417329248 |
| Beta(1,4) | original | mixed | predictive_ac_4 | 0.186854190 | 0.188153019 | 0.000798914718 | 0.00129882892 | 0.00399457359 |
| Beta(1,4) | original | mixed | predictive_ac_5 | 0.209276441 | 0.209228969 | 0.00150951870 | 0.0000474716344 | 0.00754759350 |
| Beta(1,4) | original | rare | mean | 0.0772285316 | 0.0780250492 | 0.000924100144 | 0.000796517644 | 0.00462050072 |
| Beta(1,4) | original | rare | mean_squared | 0.0106072095 | 0.0106048787 | 0.000349520246 | 0.00000233085772 | 0.00300000000 |
| Beta(1,4) | original | rare | rho | 0.197574952 | 0.200178725 | 0.00201877214 | 0.00260377311 | 0.0100938607 |
| Beta(1,4) | original | rare | rho_squared | 0.0654739132 | 0.0665865537 | 0.00118828810 | 0.00111264051 | 0.00594144051 |
| Beta(1,4) | original | rare | mean_rho | 0.0209529624 | 0.0213128925 | 0.000524485050 | 0.000359930111 | 0.00300000000 |
| Beta(1,4) | original | rare | predictive_ac_0 | 0.777917180 | 0.776174436 | 0.00157033471 | 0.00174274365 | 0.00785167356 |
| Beta(1,4) | original | rare | predictive_ac_1 | 0.131836019 | 0.132452036 | 0.000711721084 | 0.000616016020 | 0.00355860542 |
| Beta(1,4) | original | rare | predictive_ac_2 | 0.0472932659 | 0.0477537032 | 0.000441544223 | 0.000460437296 | 0.00300000000 |
| Beta(1,4) | original | rare | predictive_ac_3 | 0.0215812041 | 0.0218990125 | 0.000326114963 | 0.000317808388 | 0.00300000000 |
| Beta(1,4) | original | rare | predictive_ac_4 | 0.0118851604 | 0.0121352976 | 0.000268583401 | 0.000250137287 | 0.00300000000 |
| Beta(1,4) | original | rare | predictive_ac_5 | 0.00948717060 | 0.00958551526 | 0.000428685009 | 0.0000983446594 | 0.00300000000 |
| Beta(1,4) | original | unequal_an | mean | 0.472469845 | 0.472498284 | 0.00129995419 | 0.0000284389792 | 0.00649977095 |
| Beta(1,4) | original | unequal_an | mean_squared | 0.234439657 | 0.234758513 | 0.00123771736 | 0.000318855431 | 0.00618858681 |
| Beta(1,4) | original | unequal_an | rho | 0.104195556 | 0.102803690 | 0.000984908888 | 0.00139186626 | 0.00492454444 |
| Beta(1,4) | original | unequal_an | rho_squared | 0.0196402659 | 0.0188806147 | 0.000398163194 | 0.000759651124 | 0.00300000000 |
| Beta(1,4) | original | unequal_an | mean_rho | 0.0484566911 | 0.0475540796 | 0.000503787679 | 0.000902611571 | 0.00300000000 |
| Beta(1,4) | original | unequal_an | predictive_ac_0 | 0.102670791 | 0.102743035 | 0.00121103741 | 0.0000722437665 | 0.00605518703 |
| Beta(1,4) | original | unequal_an | predictive_ac_1 | 0.189034642 | 0.188844504 | 0.000787837837 | 0.000190138819 | 0.00393918919 |
| Beta(1,4) | original | unequal_an | predictive_ac_2 | 0.248414249 | 0.248103415 | 0.000692715117 | 0.000310833953 | 0.00346357558 |
| Beta(1,4) | original | unequal_an | predictive_ac_3 | 0.233629829 | 0.233925357 | 0.000780980567 | 0.000295528134 | 0.00390490283 |
| Beta(1,4) | original | unequal_an | predictive_ac_4 | 0.155655840 | 0.156254427 | 0.000764453755 | 0.000598587141 | 0.00382226878 |
| Beta(1,4) | original | unequal_an | predictive_ac_5 | 0.0705946478 | 0.0701292616 | 0.000855655891 | 0.000465386269 | 0.00427827946 |
| Beta(1,9) | complement | mixed | mean | 0.422979149 | 0.422923999 | 0.00145029805 | 0.0000551501676 | 0.00725149024 |
| Beta(1,9) | complement | mixed | mean_squared | 0.195036592 | 0.194091718 | 0.00132252943 | 0.000944873843 | 0.00661264714 |
| Beta(1,9) | complement | mixed | rho | 0.164263282 | 0.163151323 | 0.00111991340 | 0.00111195932 | 0.00559956699 |
| Beta(1,9) | complement | mixed | rho_squared | 0.0379320525 | 0.0375069059 | 0.000462724989 | 0.000425146641 | 0.00300000000 |
| Beta(1,9) | complement | mixed | mean_rho | 0.0714320525 | 0.0709915267 | 0.000672495527 | 0.000440525725 | 0.00336247764 |
| Beta(1,9) | complement | mixed | predictive_ac_0 | 0.172520363 | 0.170201518 | 0.00148402549 | 0.00231884523 | 0.00742012747 |
| Beta(1,9) | complement | mixed | predictive_ac_1 | 0.215289489 | 0.216525351 | 0.000817443862 | 0.00123586276 | 0.00408721931 |
| Beta(1,9) | complement | mixed | predictive_ac_2 | 0.221169953 | 0.222971931 | 0.000804401702 | 0.00180197823 | 0.00402200851 |
| Beta(1,9) | complement | mixed | predictive_ac_3 | 0.184726392 | 0.185645511 | 0.000658658158 | 0.000919118495 | 0.00329329079 |
| Beta(1,9) | complement | mixed | predictive_ac_4 | 0.128381843 | 0.128064197 | 0.000756426990 | 0.000317645735 | 0.00378213495 |
| Beta(1,9) | complement | mixed | predictive_ac_5 | 0.0779119613 | 0.0765914928 | 0.00110533942 | 0.00132046852 | 0.00552669708 |
| Beta(1,9) | complement | rare | mean | 0.942486874 | 0.943240698 | 0.000564083177 | 0.000753823931 | 0.00300000000 |
| Beta(1,9) | complement | rare | mean_squared | 0.890505692 | 0.891728926 | 0.00100007795 | 0.00122323347 | 0.00500038973 |
| Beta(1,9) | complement | rare | rho | 0.100911383 | 0.0994715248 | 0.00103365591 | 0.00143985839 | 0.00516827957 |
| Beta(1,9) | complement | rare | rho_squared | 0.0187142111 | 0.0181926074 | 0.000383245538 | 0.000521603693 | 0.00300000000 |
| Beta(1,9) | complement | rare | mean_rho | 0.0931962825 | 0.0921072010 | 0.000910725689 | 0.00108908148 | 0.00455362845 |
| Beta(1,9) | complement | rare | predictive_ac_0 | 0.00177633873 | 0.00156084489 | 0.000106893553 | 0.000215493837 | 0.00300000000 |
| Beta(1,9) | complement | rare | predictive_ac_1 | 0.00458975909 | 0.00431114985 | 0.000145587539 | 0.000278609244 | 0.00300000000 |
| Beta(1,9) | complement | rare | predictive_ac_2 | 0.0126649130 | 0.0122889433 | 0.000244239534 | 0.000375969674 | 0.00300000000 |
| Beta(1,9) | complement | rare | predictive_ac_3 | 0.0393490175 | 0.0390267538 | 0.000424925048 | 0.000322263696 | 0.00300000000 |
| Beta(1,9) | complement | rare | predictive_ac_4 | 0.143632127 | 0.143827350 | 0.000774564036 | 0.000195222926 | 0.00387282018 |
| Beta(1,9) | complement | rare | predictive_ac_5 | 0.797987845 | 0.798984958 | 0.00139727473 | 0.000997113526 | 0.00698637366 |
| Beta(1,9) | complement | unequal_an | mean | 0.522945229 | 0.522716430 | 0.00115027302 | 0.000228799351 | 0.00575136511 |
| Beta(1,9) | complement | unequal_an | mean_squared | 0.283628534 | 0.283522689 | 0.00125637918 | 0.000105844865 | 0.00628189591 |
| Beta(1,9) | complement | unequal_an | rho | 0.0688486691 | 0.0689654800 | 0.000645418445 | 0.000116810863 | 0.00322709223 |
| Beta(1,9) | complement | unequal_an | rho_squared | 0.00872083145 | 0.00869000588 | 0.000179785641 | 0.0000308255656 | 0.00300000000 |
| Beta(1,9) | complement | unequal_an | mean_rho | 0.0367121041 | 0.0367414949 | 0.000398967239 | 0.0000293908270 | 0.00300000000 |
| Beta(1,9) | complement | unequal_an | predictive_ac_0 | 0.0583785421 | 0.0586522791 | 0.000647329142 | 0.000273736962 | 0.00323664571 |
| Beta(1,9) | complement | unequal_an | predictive_ac_1 | 0.157368174 | 0.157668476 | 0.000756519445 | 0.000300302190 | 0.00378259722 |
| Beta(1,9) | complement | unequal_an | predictive_ac_2 | 0.249506050 | 0.249378686 | 0.000718585215 | 0.000127363333 | 0.00359292608 |
| Beta(1,9) | complement | unequal_an | predictive_ac_3 | 0.263748892 | 0.263271478 | 0.000625610309 | 0.000477413879 | 0.00312805155 |
| Beta(1,9) | complement | unequal_an | predictive_ac_4 | 0.187892514 | 0.187803535 | 0.000784078755 | 0.0000889790596 | 0.00392039377 |
| Beta(1,9) | complement | unequal_an | predictive_ac_5 | 0.0831058281 | 0.0832255452 | 0.000997791758 | 0.000119717120 | 0.00498895879 |
| Beta(1,4) | complement | mixed | mean | 0.438812280 | 0.439849905 | 0.00151476979 | 0.00103762460 | 0.00757384894 |
| Beta(1,4) | complement | mixed | mean_squared | 0.211343651 | 0.211201554 | 0.00146270206 | 0.000142097067 | 0.00731351030 |
| Beta(1,4) | complement | mixed | rho | 0.270998850 | 0.268845097 | 0.00148902987 | 0.00215375277 | 0.00744514936 |
| Beta(1,4) | complement | mixed | rho_squared | 0.0945858921 | 0.0934305194 | 0.000931961695 | 0.00115537273 | 0.00465980847 |
| Beta(1,4) | complement | mixed | mean_rho | 0.122038435 | 0.121363080 | 0.000973309463 | 0.000675355892 | 0.00486654732 |
| Beta(1,4) | complement | mixed | predictive_ac_0 | 0.212858650 | 0.209228969 | 0.00151158986 | 0.00362968098 | 0.00755794931 |
| Beta(1,4) | complement | mixed | predictive_ac_1 | 0.187327833 | 0.188153019 | 0.000763019002 | 0.000825186163 | 0.00381509501 |
| Beta(1,4) | complement | mixed | predictive_ac_2 | 0.180401155 | 0.182321989 | 0.000763036707 | 0.00192083417 | 0.00381518353 |
| Beta(1,4) | complement | mixed | predictive_ac_3 | 0.159420901 | 0.161067289 | 0.000591609249 | 0.00164638791 | 0.00300000000 |
| Beta(1,4) | complement | mixed | predictive_ac_4 | 0.132288750 | 0.132893009 | 0.000638721081 | 0.000604258940 | 0.00319360540 |
| Beta(1,4) | complement | mixed | predictive_ac_5 | 0.127702711 | 0.126335725 | 0.00146323624 | 0.00136698620 | 0.00731618121 |
| Beta(1,4) | complement | rare | mean | 0.920094380 | 0.921974951 | 0.00100202493 | 0.00188057100 | 0.00501012467 |
| Beta(1,4) | complement | rare | mean_squared | 0.851592837 | 0.854554780 | 0.00164756593 | 0.00296194300 | 0.00823782965 |
| Beta(1,4) | complement | rare | rho | 0.203355805 | 0.200178725 | 0.00202057763 | 0.00317708019 | 0.0101028881 |
| Beta(1,4) | complement | rare | rho_squared | 0.0691902819 | 0.0665865537 | 0.00124864004 | 0.00260372814 | 0.00624320021 |
| Beta(1,4) | complement | rare | mean_rho | 0.180837992 | 0.178865832 | 0.00161509559 | 0.00197215982 | 0.00807547793 |
| Beta(1,4) | complement | rare | predictive_ac_0 | 0.0106266419 | 0.00958551526 | 0.000521114578 | 0.00104112668 | 0.00300000000 |
| Beta(1,4) | complement | rare | predictive_ac_1 | 0.0127141798 | 0.0121352976 | 0.000285148618 | 0.000578882115 | 0.00300000000 |
| Beta(1,4) | complement | rare | predictive_ac_2 | 0.0223785904 | 0.0218990125 | 0.000331150624 | 0.000479577879 | 0.00300000000 |
| Beta(1,4) | complement | rare | predictive_ac_3 | 0.0480573354 | 0.0477537032 | 0.000442105072 | 0.000303632217 | 0.00300000000 |
| Beta(1,4) | complement | rare | predictive_ac_4 | 0.132287731 | 0.132452036 | 0.000670714899 | 0.000164304926 | 0.00335357449 |
| Beta(1,4) | complement | rare | predictive_ac_5 | 0.773935522 | 0.776174436 | 0.00164392587 | 0.00223891396 | 0.00821962937 |
| Beta(1,4) | complement | unequal_an | mean | 0.529410058 | 0.527501716 | 0.00127166155 | 0.00190834210 | 0.00635830777 |
| Beta(1,4) | complement | unequal_an | mean_squared | 0.291858566 | 0.289761944 | 0.00143271177 | 0.00209662173 | 0.00716355887 |
| Beta(1,4) | complement | unequal_an | rho | 0.102744099 | 0.102803690 | 0.000944206801 | 0.0000595911517 | 0.00472103400 |
| Beta(1,4) | complement | unequal_an | rho_squared | 0.0190089104 | 0.0188806147 | 0.000379064218 | 0.000128295689 | 0.00300000000 |
| Beta(1,4) | complement | unequal_an | mean_rho | 0.0554894405 | 0.0552496101 | 0.000599840606 | 0.000239830383 | 0.00300000000 |
| Beta(1,4) | complement | unequal_an | predictive_ac_0 | 0.0692100539 | 0.0701292616 | 0.000772544526 | 0.000919207621 | 0.00386272263 |
| Beta(1,4) | complement | unequal_an | predictive_ac_1 | 0.155119095 | 0.156254427 | 0.000731110218 | 0.00113533207 | 0.00365555109 |
| Beta(1,4) | complement | unequal_an | predictive_ac_2 | 0.233249586 | 0.233925357 | 0.000798099133 | 0.000675771531 | 0.00399049567 |
| Beta(1,4) | complement | unequal_an | predictive_ac_3 | 0.248415914 | 0.248103415 | 0.000682800532 | 0.000312498573 | 0.00341400266 |
| Beta(1,4) | complement | unequal_an | predictive_ac_4 | 0.189842477 | 0.188844504 | 0.000760520160 | 0.000997973351 | 0.00380260080 |
| Beta(1,4) | complement | unequal_an | predictive_ac_5 | 0.104162874 | 0.102743035 | 0.00130555458 | 0.00141983930 | 0.00652777292 |

Across these 132 comparisons, every MCSE was finite, positive and below the frozen
0.005 maximum, and every absolute discrepancy was below its recorded bound. The largest
absolute discrepancy was 0.00362968098 (Beta(1,4), complement, mixed,
`predictive_ac_0`) against a 0.00755794931 bound. The largest MCSE was 0.00202057763
(Beta(1,4), complement, rare, `rho`). The smallest relative margin occurred for
Beta(1,4), complement, mixed `predictive_ac_3`: discrepancy 0.00164638791 against
a 0.003 bound.

This corrected synthetic result supports computational fidelity for the declared bounded
checks only. It does not establish empirical improvement, broad calibration, robustness to
misspecification, geographic validity, or a real-data advantage over B0.

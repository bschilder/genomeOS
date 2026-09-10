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

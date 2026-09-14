# Reference-count development baseline: twelve frozen runs

Follow-up to #189, WP0–WP1/WP4; Atlas design §§5, 7–8. This report advances
the modeling program but does not establish a better worldwide model.

## Scientific contract and outcome

**Question:** how well does one pooled uncertain frequency per variant predict
counts in withheld groups from this reference resource? The measured output is
integrated count prediction, with point error, predictive intervals and
randomized PIT. The pure count/fold interfaces and offline
`scripts/benchmark_reference_counts.py` produce the evidence.

All twelve predeclared development configurations completed at reviewed source
`92659aa6999b04652fd0c3208c1e0836c96832a6`. Each has five completed folds,
40,800 retained population/variant rows, 40,797 scored rows, three explicitly
unavailable denominators, and no failed rows. Each row is held out exactly once
per run. These are repeated evaluations of overlapping data, not twelve
independent datasets or 489,564 independent observations.

An independent read-only audit reconciled every input/output hash, executed
source hash against its recorded Git object, seed stream, fold membership,
declared cross-population dependency, training-only posterior total, available
row/count/label alignment, missing-row status and macro-aggregated metric.
All twelve passed. Full-precision aggregate results, PIT histograms, per-run
manifest hashes and runtimes are in the
[aggregate JSON](reference-count-baseline-2026-09-10.json). It contains no
population/variant record IDs, participant IDs, genotypes or prediction rows.

The assumptions and refusals remain those of the
[reference-count design](../superpowers/specs/2026-09-09-reference-count-baseline-design.md).
The consumers are research comparisons, not serving or burden publication.
Reference groups are not certified resident samples or independent studies.
No coordinate, radius, sampling design, date or ancestry history was invented.

## Frozen experiment

The [source qualification](hgdp-count-pilot-2026-09-09.md) established the fixed
GRCh38 chr22:20,000,001–20,010,000 pilot: 510 PASS biallelic SNPs and 80 literal
source population groups. This is one short locus block. The three reported
cross-population dependency pairs remain in the same fold, yielding 77
reported-edge components; the graph is only a lower bound on dependence.

Two cohort stages were declared before fitting:

- **T:** technical QC, 4,117 samples.
- **P:** technical QC plus the paper's ancestry exclusions, 4,094 samples.

Each stage has a called-count and a quality-filtered-count track, evaluated at
seeds 42, 43 and 44 with five folds and Beta(1,1) priors. All variants and
zero-count rows remain included. The four inputs have matching fold membership
within each seed. Split and PIT RNG streams are separate. No priors, rows,
cohort stages or folds were selected from these results.

Protocol SHA-256:
`c6c7219a7938e8a73a29db13437f1f51fdc1c47cfc3f48eddf032a9e58e1242c`.

| Input | SHA-256 |
| --- | --- |
| T called | `b50ed9a07e8fcaec3c718ce7116ddcc1f66c1cf335d9048c6139e89c0d37c6ac` |
| T quality | `d756bf8ebcf37ad9f778ec71efcae7ad158e65718e53f2deeae19c97b3eeea46` |
| P called | `8d80bf794e3585830e1d54a18c26f69c186e75c8450e058a4a8d0400a43c980f` |
| P quality | `313c85bf13679975c3be62488f74e94466ea2c00a57d2cfb13fa3aac5341e858` |

Both dependency inputs have SHA-256
`fd6991af790d1bdf85da3fb1e3ff082f22892ff086689c5b8a75c624a379e60a`.
The source, count definitions and earlier independent bcftools cohort-total
checks are documented in the qualification note; this runner does not redo
acquisition or certify every upstream preparation step.

B0 integrates its pooled Beta posterior exactly as a beta-binomial marginal.
This is uncertainty about a shared frequency, **not** a fitted model of
between-population heterogeneity and not the current production spatial GP.
Marginal outputs are not joint-site posterior draws.

## Results and interpretation

Errors are on the 0–1 frequency scale. Coverage columns are percentages.
Log score is the mean log predictive probability of the observed count, higher
being better. Scores first average within source population/operational-region/
locus-block groups, then within represented region/block cells, then equally
across cells. The source's seven `Genetic.region` labels are operational bins,
not independently verified geographic or resident strata.

| Stage / counts / seed | MAE | RMSE | Log score | 50% coverage | 95% coverage | Mean PIT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P / called / 42 | 0.006818 | 0.034420 | -0.587361 | 92.76 | 96.47 | 0.483294 |
| P / called / 43 | 0.006822 | 0.034396 | -0.604037 | 92.74 | 96.41 | 0.482601 |
| P / called / 44 | 0.006694 | 0.033987 | -0.590294 | 92.84 | 96.51 | 0.480547 |
| P / quality / 42 | 0.006801 | 0.034400 | -0.585189 | 92.80 | 96.50 | 0.483230 |
| P / quality / 43 | 0.006806 | 0.034379 | -0.601883 | 92.76 | 96.43 | 0.482526 |
| P / quality / 44 | 0.006686 | 0.033970 | -0.588114 | 92.87 | 96.54 | 0.480337 |
| T / called / 42 | 0.006770 | 0.034203 | -0.587811 | 92.77 | 96.47 | 0.483408 |
| T / called / 43 | 0.006786 | 0.034183 | -0.604453 | 92.68 | 96.40 | 0.482733 |
| T / called / 44 | 0.006640 | 0.033794 | -0.590896 | 92.81 | 96.53 | 0.480682 |
| T / quality / 42 | 0.006747 | 0.034180 | -0.585690 | 92.80 | 96.49 | 0.483341 |
| T / quality / 43 | 0.006777 | 0.034163 | -0.602346 | 92.71 | 96.42 | 0.482655 |
| T / quality / 44 | 0.006638 | 0.033774 | -0.588767 | 92.86 | 96.55 | 0.480469 |

The aggregate JSON also retains 80% coverage and all interval widths. Across
these runs, 95% frequency-scale interval widths average approximately
0.01885–0.01914 under the same macro weighting.

Several cautions materially change the interpretation:

- Approximately 91.7% of available population/variant rows have observed AC=0.
  Their true frequencies are not known to be zero. Overall MAE of about
  0.66–0.68 percentage points is not evidence of similarly good performance
  for rare/localized alleles.
- A post hoc, outcome-selected check on rows with observed AC>0 gives
  **unweighted** MAE of about 7.34–7.54 percentage points. Its different weighting
  and outcome selection mean it is not directly comparable to the macro MAE,
  a prespecified deployment stratum, or an estimate of latent-frequency error.
  It nevertheless identifies a useful failure mode to investigate.
- Discrete, zero-heavy count intervals can exceed their nominal coverage.
  The roughly 93% coverage of nominal 50% intervals cannot be interpreted
  through a continuous-interval calibration rule. Mean PIT near 0.48 alone
  does not establish calibration; the retained histograms matter too.
- The QC/stage comparisons and seeds are correlated sensitivities. There is
  no independence-based confidence interval, significance claim, best-seed
  selection, or model-improvement claim here.
- Joint discovery/calling/QC and incomplete relatedness information remain
  shared-source dependencies. No external validation, effective geographic
  resolution, resident calibration or genome-wide learning curve was tested.

## Failed attempts and numerical correction

Before these runs, source `fabbf53` attempted the four seed-42 configurations.
Both technical-QC tracks completed; both paper-exclusion tracks exited 2 with
`randomized_pit values must be finite and between 0 and 1`. Summary validation
aborted before those failed tracks wrote their promised fold artifacts.
The other eight configurations were not launched. Both successful directories
and terminal failure records remain preserved locally as superseded attempts.
An earlier successful engineering run at `a69f594` is also preserved.

Issue [#209](https://github.com/bschilder/genomeOS/issues/209) records the
independent synthetic Decimal-oracle reproduction. Summing the shorter support
tail could still mean summing a probability nearly equal to one. The repair
switches to the small-probability complement using a one-half crossover,
without clipping, changing the count distribution or relaxing tolerances.
Both runners now validate diagnostic frames inside their per-fold failure
handlers before appending prediction rows. CuPy also validates each component
before averaging, so cancellation cannot hide an invalid component.

The corrected experiment reran **all twelve unchanged configurations**, not
only the failed ones, in a fresh source-keyed directory. All completed in
164.12–211.80 seconds per process. The first wave overlapped the full CPU test
suite; these timings are not a controlled backend comparison or a speedup claim.

## Verification and outstanding CUDA evidence

At the clean reviewed source:

- Full suite: **963 passed, 17 skipped, 15 existing rasterio warnings**, 394.88s.
- Focused numerical tests: 111 passed; 17 CUDA-dependent tests skipped locally.
- Smoke: 40 passed. Ruff, frozen-contract, module-size and privacy gates passed.
- Independent implementation and scoped fix review cleared the numerical,
  failure-accounting and component-refusal changes.
- The actual-data twelve-run artifact audit passed as described above.

Commands used the locked Python 3.12 environment, `PYTHONPATH=.`, and isolated
PyTensor/Matplotlib caches: `python -m pytest`, `python scripts/smoke.py`,
`ruff check .`, `python scripts/freeze_contract.py --check`,
`python scripts/check_module_size.py`, and
`python scripts/check_private_files.py`.

**Actual CUDA verification of this changed source remains pending.** A
task-owned A40 in CA-MTL-1 was available at a quoted $0.49/hour, but automatic
approval review rejected the exact source-archive upload as requiring more
specific export authorization. Nothing was uploaded and no CUDA scorer check
ran. The pod was deleted immediately after the refusal, confirmed by HTTP 204
then 404. Estimated compute was at most $0.027643, excluding other charges;
this is not an invoice. The audited local payload and evidence remain available
for resumption. There is no task-owned GPU still running for this check.

That permission issue does not affect these CPU runs or authorize a claim that
the CUDA gate passed. Issue #209's hardware acceptance remains incomplete;
this branch should not be merged as a fully verified GPU repair yet.

## Reproduction and next comparison

Given the already qualified local count and dependency inputs, run the reviewed
source from the repository root, using a fresh output directory each time:

```bash
PYTHONPATH=. python scripts/benchmark_reference_counts.py \
  --counts INPUTS/technical_qc_4117.called.tsv \
  --dependencies INPUTS/technical_qc_4117.dependencies.json \
  --source-release gnomad-3.1.2-hgdp-tgp-original-calls \
  --cohort-stage technical_qc_4117 --count-kind called \
  --evidence-role development --prior-alpha 1 --prior-beta 1 \
  --folds 5 --seed 42 --out NEW_OUTPUT_DIRECTORY
```

Repeat both stage names, both count kinds and all three seeds above. The locked
numerical versions were NumPy 2.4.6, SciPy 1.18.1 and pandas 3.0.5. Manifests bind
consumed input bytes and all generated artifacts to source hashes. Real inputs,
per-row outputs and unbundled preparation diagnostics remain local; this is a
reproducible runner given qualified inputs, not a newly packaged end-to-end
public genotype acquisition pipeline.

The [next-model research note](reference-count-next-models-2026-09-10.md)
separates population heterogeneity, conditional shared-variant imputation and
unsampled-geography prediction. The next count comparison should integrate
uncertainty in mean and dispersion, undergo known-truth/independent-oracle
checks, preserve these folds and all failures, and remain a within-resource
development experiment. Broader locus coverage and qualified spatial support
are still required for the larger neural-operator program. CuGen is independent
of this work; no LD integration is a prerequisite for the count challenger.

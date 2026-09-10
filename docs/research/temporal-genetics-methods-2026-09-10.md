# Temporal genetic evidence: CLUES2 reading and pilot implications

September 10, 2026. This methods note informs WP7 of the
[global-frequency plan](../superpowers/plans/2026-09-09-global-af-modeling.md).
It complements the [three climate time horizons](temporal-climate-source-qualification-2026-09-10.md),
but admits no dataset, feature or model. Advances #189; Atlas design §§5,7–8,12.

## Source and reading boundary

Vaughn and Nielsen (2024), *Molecular Biology and Evolution* 41(8),
[CLUES2, DOI 10.1093/molbev/msae156](https://doi.org/10.1093/molbev/msae156).
The complete 20-page [author-hosted main article](https://nielsen-lab.github.io/pdfs/papers/clues2.pdf)
was read, including references; rendered pages9/12 were inspected for equations
and the acceleration schematic. PDF SHA256:
`43116e1debba571a5f7be72402c0f6202e1e7f7366471951b684e90f9bb7c6e9`.
The main article states CC BY4.0. The supplement remains **unread**: its findings
are claims reported by the main article, not independently inspected evidence.
An independent source review and scoped wording re-review found no remaining
Important attribution issue. Neither review is a numerical reproduction.

## What the main paper establishes about its method

- Pages2–4: a finite frequency-state model, with denser boundary bins, normal
  transitions and a single-origin infinite-sites assumption. Present frequency
  initializes a point mass rather than a finite modern count likelihood.
- Pages3,7–8: ancient emissions can use genotype likelihoods. The ancient-genealogy
  path instead requires hard-called leaves and fixed sampling times. In its
  true-tree simulation, incorporating ancient samples into genealogies reduced
  selection-estimate variance relative to ancient emissions with modern trees;
  both were approximately unbiased in that example.
- Pages8–10: historical outputs are time-specific marginal posteriors, not joint
  trajectories. Selection uncertainty uses a normal approximation around the MLE.
- Pages10–13: A1 truncates/renormalizes transitions; A2 skips already-zero terms
  without additional approximation error. B further restricts forward-state
  support; abrupt informative emissions can make that approximation inaccurate.
- Pages15–17: changing ancestry composition can change frequencies under
  neutrality. An ancestry-stratified analysis does not model adaptive
  introgression. Environmental explanations remain hypotheses.

## Proposed genomeOS tests—not results of CLUES2

Scientific objective: test whether past genetic observations improve held-out
modern prediction, and whether withheld ancient observations can be predicted.
These are separate claims from detecting selection. Acceptance requires frozen
site/time/dependency holdouts, known-history simulations, predictive scores and
uncertainty checks. The engineering interface would be a separate offline
state-space experiment consuming qualified modern counts and ancient likelihoods;
it does not alter the active B0H calibration or its comparison data.

Start the regional pilot with direct ancient likelihoods to preserve uncertain
observations. That is a data-integrity/implementation choice, **not** a claim of
superior statistical efficiency. Compare a genealogy-informed arm separately
when its inputs qualify. Keep finite modern AC/AN, date distributions, damage,
contamination, pseudohaploidy, kin/site dependence and ascertainment explicit.
Genotype posterior probabilities are not genotype likelihoods: any conversion
requires an explicit prior-removal derivation, not a renamed column. Never
silently flip observed alleles to satisfy a method's mutation assumptions.

Use coherent joint trajectory draws for cross-time change, occupancy or origin
claims; independently sampled marginals do not form a history. Include
migration/admixture-only controls before attributing changes to selection or
climate. Present residence is not ancestral location, and a present variant need
not have existed throughout the requested primate-divergence climate horizon.
Model mutation-age and location uncertainty without inventing either.

Benchmark dense small-state reference calculations against sparse/banded or GPU
implementations. Prespecify numerical tolerances and test abrupt emissions,
ancestry shifts, rare/boundary alleles, long unsupported gaps and demographic
misspecification. Measure total runtime as well as predictive error. Neither an
asymptotic normal approximation nor the paper's timing examples guarantees
adequacy for these cases.

Refuse temporal/origin claims when date, assay, ancestry/geography or dependency
evidence is insufficient. The consumers are a qualified regional WP7 pilot and
its modern-prediction ablation, not a global historical map or clinical layer.
Read the actual supplement before reproducing its simulations or transition
approximations; that source task does not block the current modern-model work.

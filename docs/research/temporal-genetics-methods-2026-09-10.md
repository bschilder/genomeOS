# Temporal genetic evidence: CLUES2 reading and pilot implications

September 10, 2026; supplement inspected September 11 (UTC). This methods note informs WP7 of the
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
The main article states CC BY4.0. An independent source review and scoped wording
re-review of the initial main-article note found no remaining Important attribution
issue. Neither review is a numerical reproduction.

The complete text of the 25-page
[published supplement](https://pmc-oa-opendata.s3.amazonaws.com/PMC11321360.1/msae156_supplementary_data.pdf)
has now been read. Rendered pages3–4,6–10,20–25 were inspected for equations,
simulation definitions and the frequency/population-size sensitivity figures.
The PDF is 8,433,007 bytes; SHA256:
`56174bc01b26e272dce4fda54c3d3a6a7b2456373eccbfd82c6a6f557837e89b`.
Its MD5 matches the article metadata's `5c7c0442e8d492929eb1f83e3ab6afa4`.
Source: NIH NLM NCBI PubMed Central Article Datasets on AWS, accessed September11,
2026. The retrieved article XML explicitly links this supplement and states
CC BY4.0; the metadata identifies the published, non-manuscript article and
reports it as not retracted. Local evidence retains both metadata and XML,
retrieval headers, checksums, extracted text and inspected page renders.
This is a source reading, not a simulation reproduction or dataset promotion.

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

## What the supplement adds

- **An additional approximation precedes the speedups.** §§1,4 (pages2–4,6)
  distinguish the implemented backward HMM from a formally reversed
  Wright–Fisher process. It starts at the present frequency, admits both absorbing
  boundaries, truncates the history, and omits a selection-dependent denominator
  in the ascertainment-conditioned sampling probability. The authors explicitly
  acknowledge possible bias from that omission and support the approximation
  with simulations. Agreement with their dense HMM would therefore test
  implementation accuracy; it would not alone establish the correctness of the
  underlying generative approximation. This is separate from A1/A2/B acceleration.
- **The simulation ascertainment is specified.** §6.1 (pages7–8) retains only
  trajectories still segregating at the present. Mutation-origin time is sampled
  uniformly for constant population size and proportionally to population size
  when it varies. §6.2 (page8) says the true-tree cases labelled `s=0` used
  `s=1e-6`, because the chosen sweep simulator required positive selection.
  A reproduction must label that approximation; an exact-neutral control is a
  separate experiment.
- **The importance-sampling validation has a narrow scope.** §6.3 (pages8–9)
  fixes the true topology of a 24-leaf tree without recombination, then samples
  branch times and compatible coalescence orderings. It validates that conditional
  problem, not uncertainty over real inferred topologies. §6.4 (pages9–10)
  compares 20 modern haplotypes plus 160 ancient lineages at each of 50 and 100
  generations with the corresponding 80 diploid genotypes at each ancient time.
  This does not establish performance under uncertain dates or damaged reads.
- **A large selection estimate can reflect weak information.** §7 and
  FiguresS18–S23 (pages10,20–25) study six present frequencies (0.01–0.99), four
  population-size values (100–100,000), `s=0.005`, 200 leaves and 50 replicates per
  combination. At small population size, flat objectives and unstable maxima can
  accompany weak likelihood evidence. The alternative conditional-transition arm
  is a useful comparator, not a general calibration guarantee. We have inspected
  plots, not reproduced their values or proved numerical equivalence.
- **Input alterations and dominance remain explicit.** §5 (page7) explains that
  equally minimal leaf-flipping solutions can change different leaves. §3
  (pages4–6) holds dominance fixed rather than estimating it; the MCM6 comparison
  uses dominance values chosen to match the modern equilibrium frequency.
  These analyses do not justify silently changing observed alleles or treating
  a chosen dominance value as independently measured.

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

Separately compare the CLUES2 generative approximation with an explicitly
ascertainment-conditioned reference under matched simulation settings. Keep
fixed-topology, uncertain-topology and direct-likelihood controls distinct.
Require likelihood profiles and uncertainty checks before interpreting large
selection maxima. Audit haploid/diploid population-size and selection conventions
at every simulator boundary. The supplement's page7 binomial expression contains
an unexplained `p` where page6 uses the current frequency: resolve the formula
against its derivation and versioned author code before reproducing it; do not
silently transcribe a guessed correction.

Refuse temporal/origin claims when date, assay, ancestry/geography or dependency
evidence is insufficient. The consumers are a qualified regional WP7 pilot and
its modern-prediction ablation, not a global historical map or clinical layer.
The supplement-reading gap is closed. Numerical reproduction, input qualification
and the prespecified predictive tests remain open; none of this changes the
current modern-model calibration or admits a temporal implementation.

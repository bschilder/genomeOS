# What the count pilot should test next

Research follow-up for #189, WP2/WP4; Atlas design §§7–8. No challenger has
been fitted or selected by this note. The numerical repair in #209 and the
unchanged twelve-run baseline protocol remain separate work.

## Scientific contract

The immediate question is whether between-population variation improves
prediction of withheld reference-panel counts beyond a single pooled frequency.
Acceptance requires paired count scores, calibration, interval widths and point
errors on the same dependency-grouped folds, with every failure retained.
The prospective interface remains a pure training-count fitter returning an
explicit predictive distribution and fit diagnostics to the offline runner.
This is a within-resource target, not a substitute for resident-geographic skill.
Unknown geography, sampling design and dependence do not become known through
fitting. Nothing in this note changes production observations or surfaces.

## Additional full-text reading

Fumagalli et al., *Quantifying Population Genetic Differentiation from Next-
Generation Sequencing Data*, Genetics 195:979–992 (2013), doi:
10.1534/genetics.113.154740. Read the full main article and its inline Appendix
from the publisher copy; separate supplementary files were not read here.
Equations 5–8 give a beta-binomial population-count model, with concentration
`(1-F)/F`, conditional population independence and a common-frequency parameter.
The paper also integrates genotype uncertainty and documents bias from calling
and filtering at low coverage. Its simulations assume independent sites and
discard nonconvergent optimization cases; neither practice establishes validity
for this linked pilot or replaces genomeOS's failure ledger. The Discussion
warns that joint SNP discovery can affect ascertainment. These are reasons to
qualify observation and dependency assumptions, not evidence that our next model
will win. [Full text](https://academic.oup.com/genetics/article/195/3/979/5935465).

Hao, Song and Storey, *Probabilistic models of genetic variation in structured
populations applied to global human studies*, Bioinformatics 32:713–721 (2016),
doi:10.1093/bioinformatics/btv641. Read the complete main article; the separate
supplementary archive was not read here. Its logistic factor model represents
individual-specific allele probabilities through shared latent structure,
without requiring each factor to mean an ancestral population. Unlike ordinary
PCA frequency estimates, the logit construction respects probability bounds.
The reported comparisons concern structure and frequency estimation from
genotype matrices and simulations, not geographical prediction where all local
genotypes are absent. [Full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC4795615/).

Paperclip returned empty text and metadata for the first lookup; public
publisher/PMC full text was used instead. No authenticated profile, uploads,
publication-evidence rows or verification claims were created.

## Proposed sequence, not a frozen challenger configuration

1. **Population-heterogeneity ablation.** Compare pooled B0 with a beta-binomial
   working model of population-specific frequencies. Integrate uncertainty in
   the frequency mean and dispersion; do not plug in an estimated dispersion
   and call its conditional interval a full posterior. Fit using training groups
   only. First verify on simulated counts with known truth, including a genuinely
   homogeneous case, boundary-heavy alleles and unmodeled shared population
   history. Specify priors, numerical limits and failure criteria before running
   the real challenger. Do not label the fitted mean ancestral or the dispersion
   historical FST merely because the algebra permits that interpretation.
2. **Shared-structure comparison.** A low-rank logit count model is an economical
   precursor to field attention. It requires a declared source of context at the
   query population. Withheld-population genotypes cannot be used to learn its
   factors in an all-variant population holdout. A conditional-imputation track
   may permit separate context loci, but then needs whole-block separation,
   training-only transformations and an explicit, matched information budget.
3. **Spatial/shared model.** For unsampled-region prediction, extend shared
   structure through qualified spatial or other externally available features.
   The current source region labels and legacy 50-km registry radius are not
   automatically admissible features or verified sampling footprints. Acquire
   wider locus and population support while testing the preceding count model;
   no CuGen prerequisite is imposed on those experiments.

The two-stage/QC/seed baseline sensitivities are correlated, not replicates.
The current 510 adjacent SNPs do not establish a genome-wide learning curve.
Future inference must not multiply their likelihoods into a falsely precise
shared-parameter posterior without addressing their dependence. Conditional
prediction gains, marginal calibration gains and geographic gains should each
be reported under their actual target, not combined into one headline.

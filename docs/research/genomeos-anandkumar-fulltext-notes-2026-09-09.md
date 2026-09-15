# Anandkumar full-text reading notes for genomeOS

September 9, 2026. Companion to the [research and benchmarking plan](genomeos-model-research-2026-09-09.md).

## Scope and access

I read the main text and scientific appendices of the ten selected coauthored papers below, where appendices are present. This includes methods, experiments, limitations, and extracted table/figure captions—not just abstracts. Bibliography entries and conference administrative checklists were not treated as scientific reading. Public author or proceedings copies were sufficient; the authenticated Chrome profile was not needed or accessed. Versions are specified because preprints and later publications can differ.

This is a focused selection for sparse spatial inference, multivariant sharing, uncertainty, and changing resolution—not a claim to have read Anandkumar's entire publication record. The larger plan also cites population-genetic papers and dataset documentation with differing review depth. In particular, the long Kovachki et al. operator-theory monograph, PINO, and every related population-genetics paper were **not** all read cover to cover. Akbari et al. 2026 is retained as an abstract-level methodological lead, not a fully evaluated method. All proposed genomic transfers below are research hypotheses, not results from these papers.

## 1. Fourier Neural Operator

Li et al., *Fourier Neural Operator for Parametric Partial Differential Equations*, ICLR 2021; [arXiv v3, May 2021](https://arxiv.org/abs/2010.08895v3). Read main text and Appendix A.

**Sections 3–5 and A.5:** FNO learns a transformation between fields. Its global spectral operation works alongside pointwise operations and nonlinearities. Super-resolution experiments concern particular simulated distributions; they do not establish recovery of unobserved genetic detail. Section 5.5 also places a learned forward operator inside Bayesian inverse inference, conditioning on sparse noisy observations.

**genomeOS implication:** investigate both a direct conditional field model and a simulator surrogate inside Bayesian inference. Neither requires abandoning the count likelihood. Test surrogate-induced posterior error separately from speed. Querying a finer grid is not a new source of evidence.

## 2. Adaptive Fourier Neural Operators

Guibas et al., *Adaptive Fourier Neural Operators: Efficient Token Mixers for Transformers*; [arXiv v2, March 2022](https://arxiv.org/abs/2111.13587v2). Read main text and appendices.

**Methods and Appendix A:** AFNO replaces token mixing with a structured Fourier-domain transformation, including blockwise channel mixing and sparsification. This is different from running ordinary full attention alongside an FFT. Comparisons show competitive, not universally superior, performance. Appendix A.4 reports maximum validation performance across training; total-model compute also need not track mixer-only efficiency.

**genomeOS implication:** use a precisely specified architecture and report complete training/inference costs. Checkpoint selection belongs inside development folds; final evaluation must not be the best repeatedly inspected validation score.

## 3. FourCastNet

Pathak et al., *FourCastNet: A Global Data-driven High-resolution Weather Model using Adaptive Fourier Neural Operators*; [arXiv v1, February 2022](https://arxiv.org/abs/2202.11214v1). Read main text and Appendices A–D.

**Sections 2–4 and 6:** training uses many densely represented global weather states. Ensemble generation perturbs initial conditions; this alone is not a general uncertainty-calibration method. Section 3.6 describes underestimated extreme precipitation. Section 4's finer-resolution scaling discussion includes hypothetical throughput rather than demonstrated fine-resolution predictive skill. Data assimilation remains a separate problem.

**genomeOS implication:** sparse genetic surveys are not analogous to complete weather training states. Evaluate rare/localized alleles and hotspot contrasts separately from average error. Report a throughput experiment as throughput, never as validated genetic resolution.

## 4. Spherical Fourier Neural Operators

Bonev et al., *Spherical Fourier Neural Operators: Learning Stable Dynamics on the Sphere*, ICML 2023; [published full text and supplement](https://proceedings.mlr.press/v202/bonev23a.html). Read main text and scientific appendices.

**Architecture, rollout experiments, Appendix B:** spherical harmonic transforms respect spherical geometry. Equivariance depends on the actual filters and nonlinear construction, and numerical discretization matters. Stable long rollouts are not equivalent to accurate detailed weather prediction at those horizons. Spherical-transform cost should not be inferred directly from a flat FFT's complexity.

**genomeOS implication:** use appropriate spherical geometry and integration, but allow geography, environment, and migration to break isotropy. Test poles, antimeridian behavior, and weighted aggregation. Do not interpret rollout stability as identified demographic history.

## 5. Geometry-Informed Neural Operator

Li et al., *Geometry-Informed Neural Operator for Large-Scale 3D PDEs*, NeurIPS 2023; [proceedings full text](https://proceedings.neurips.cc/paper_files/paper/2023/file/70518ea42831f02afc3a2828993935ad-Paper-Conference.pdf). Read main text and scientific appendix.

**Methods, Section 7, appendix:** graph operators transfer between irregular locations and a regular latent representation, with integration weights. In the car experiments, a dense signed-distance representation can make the graph encoder unnecessary; some best results use only the decoder. Geometry-conditioned forward prediction is not sparse noisy inverse inference. Resolution experiments distinguish retraining from transferring fixed weights.

**genomeOS implication:** test the encoder rather than assuming it helps. Include sample-density and footprint weighting, and avoid making oversampled regions dominate. Evaluate both point predictions and scientifically meaningful aggregates.

## 6. Localized integral and differential kernels

Liu-Schiaffini et al., *Neural Operators with Localized Integral and Differential Kernels*; [arXiv v2, June 2024](https://arxiv.org/abs/2402.16845v2). Read main text and scientific appendices.

**Methods; Appendices C.6–C.7:** local support must have a consistent physical interpretation under refinement. The paper explicitly discusses resolution overfitting; different differential-layer choices can win at native and transferred resolution. Adding every branch is not uniformly best. Fixed physical neighborhoods can become more expensive as resolution increases.

**genomeOS implication:** separately ablate global, local, and differential components. Freeze physical support and test identical weights across resolutions. A local branch is a plausible way to retain gradients, not evidence that fine-scale gradients have been learned correctly.

## 7. Codomain Attention Neural Operator

Rahman et al., *Pretraining Codomain Attention Neural Operators for Solving Multiphysics PDEs*, NeurIPS 2024; [proceedings full text](https://papers.nips.cc/paper_files/paper/2024/file/bc75fa9843a7905bbed9d83895a88f7f-Paper-Conference.pdf). Read main text and scientific Appendices A–H.

**Methods; Tables 5 and 12:** CoDA-NO attends between whole variable-fields using operator-valued transformations. Masked pretraining is useful, but reconstruction and downstream prediction can rank models differently. Runtime overhead is substantial in the reported comparison, despite competitive parameter counts.

**genomeOS implication:** this is the most direct candidate for the proposed Fourier/attention multivariant combination. Begin with bounded blocks or shared latent fields, not genome-wide dense attention. Match pretraining access and compute across competitors; compare against low-rank sharing. Field normalization must preserve the allele-prevalence information that the genomic task needs.

## 8. FourCastNet 3

Bonev et al., *FourCastNet 3: A geometric approach to probabilistic machine-learning weather forecasting at scale*; [arXiv v1, July 2025](https://arxiv.org/html/2507.12144v1). Read main text and Appendices A–G.

**Probabilistic objective and evaluation appendices:** the architecture is convolutional. Its correlated stochastic process and distributional training differ from merely repeating a deterministic model. Marginal calibration does not determine spatial dependence. The appendices also identify remaining dispersion and initialization limitations; the training scale is substantial.

**genomeOS implication:** preserve joint field draws for regional uncertainty, and assess observation noise separately from uncertainty about an unsampled population. Spectral validation needs independent dense truth or simulations; an interpolated test map is not such truth. A weather ensemble recipe is not automatically a Bayesian posterior.

## 9. Scientific-simulation review

Azizzadenesheli et al., *Neural Operators for Accelerating Scientific Simulations and Design*; [arXiv v5, January 2024](https://arxiv.org/abs/2309.15325v5). Read the full main text; no scientific appendix in this copy.

**Sections 2–3:** the review distinguishes continuous field representations from operators mapping between functions, and discusses physics constraints, inverse design, and open problems including uncertainty, scarce data, and generalization.

**genomeOS implication:** define what transformation is learned before choosing a network. The immediate task is inference from an irregular observation set; the temporal task could instead learn a transition. Drift/migration assumptions can regularize a model, but uncertain human history is not a known governing equation. Test misspecified mechanisms explicitly.

## 10. NeuralOperator library

Kossaifi et al., *A Library for Learning Neural Operators*, JMLR 27, June 2026; [published paper](https://jmlr.org/papers/v27/26-0434.html). Read the complete six-page paper.

**Introduction and package description:** the toolkit provides reusable operator implementations and scientific-learning utilities. The paper distinguishes discretization-related architecture properties from actual cross-resolution generalization and physical consistency.

**genomeOS implication:** reuse tested primitives for experiments rather than inventing a new operator framework. Pin the package and numerical environment, keep it in offline optional dependencies, and wrap it behind genomeOS's existing scientific contracts. Library support is implementation feasibility, not empirical validation for allele-frequency inference.

## Decisions changed by the reading

1. Add CoDA-NO as a distinct blockwise challenger, alongside a simpler spherical/local operator—not an undifferentiated “Fourier transformer.”
2. Keep the Bayesian-simulator-surrogate route open for temporal work.
3. Require fixed-weight resolution-transfer tests, not just retraining on a finer grid.
4. Compare final count prediction, rare/localized signals, and regional joint uncertainty; reconstruction quality or a plausible-looking map is insufficient.
5. Match data, pretraining, tuning, and complete workflow costs. Let simpler models win.

The [main plan](genomeos-model-research-2026-09-09.md) translates these decisions into data-admission rules, model comparisons, leakage-resistant benchmarks, and staged acceptance gates. No genomic performance claim has been established by this reading alone.

# CuGen full-text methods review — September 9, 2026

**Implementation target remains the owner's local CuGen**, pinned for the existing source preflight at `03df1688abf52d295bd85d47f1aca6130440b553`. The [LD preflight](cugen-ld-preflight-2026-09-09.md) records executable CPU evidence and the narrower API contract. This note adds the paper's methods; it does not substitute pg_gpu, introduce a dependency, or claim GPU LD validation.

**Scientific objective:** determine which demonstrated computational ideas could support training-only multivariant AF experiments. **Measurable output:** an explicit adoption/refusal matrix, followed by independently checked LD and held-out AF experiments. **Engineering boundary:** offline CuGen sample/block preparation and `cugen.ld.ld_matrix`; no phenotype model or inference on the serving path. **Assumptions and consumers:** the paper studies different statistical targets and populations; its findings inform WP4/WP6 hypotheses, not model promotion or population-data qualification under [#189](https://github.com/bschilder/genomeOS/issues/189).

## Source and reading record

Kiiskinen, Richland, Wang, Lu, Narasimhan, Hastie, Tibshirani and Rivas. *CuGen: A GPU-accelerated framework for large-scale genomics*. Preprint, July 17, 2026; [DOI 10.64898/2026.07.15.26358178](https://doi.org/10.64898/2026.07.15.26358178), [PubMed record](https://pubmed.ncbi.nlm.nih.gov/42523429/), [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC13405381/).

The publisher route was blocked and Paperclip's server was unavailable. The public [Europe PMC full-text XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13405381/fullTextXML) succeeded. Its retrieved bytes have SHA256 `9428bbc324c00b0bd11b4b89d4d69ecf776cd66894d0343ac548bed3c4f590a6`. The entire article text, all Methods sections, 14 displayed MathML equations, figure captions, references and availability statements were read. Figure images were not visually inspected; referenced supplementary tables/figures were not obtained or read. Reading a reference entry is not reading that cited paper. Section IDs below are locators in this exact XML snapshot.

The article explicitly carries CC BY 4.0; its code-availability statement reports MIT licensing for software. These do not grant access to UK Biobank participants' data: the data-availability statement requires formal application. No restricted genotype data, copied implementation, publication-evidence observation rows or derived population surfaces were created by this review.

## What the authors actually measured

These are **author-reported results**, not genomeOS replications. Runtime comparisons combine different algorithms and hardware. They cannot establish an isolated GPU speedup or geographic predictive gain.

| Evidence | Scope and qualification | Locator |
|---|---|---|
| Full GWAS plus fine-mapping in roughly ten minutes | Single H100 80 GB, approximately 6.8 million imputed variants; white British UK Biobank cohorts, with/without relatives | Results S8; Methods S24 |
| Eight-trait batch: 37.7 minutes | Measured single-GPU batching; reuse of decoding amortizes I/O | S8 |
| Eight GPUs, 16-trait batches: 2,579 traits/day; approximately 1,700/day at 100 million variants | **Projections/estimates**, not demonstrated throughput of those configurations | S8; S24 |
| Array conversion: 21 minutes across 22 CPU jobs | One-time preparation, outside the headline downstream runtime; genotype conversion is not free | S4 |
| Common-variant null calibration across 200 simulations | Simulation evidence for their association procedure, not calibration of AF count prediction | S5; S21 |

Utility timings for LD/subsetting and other tools are demonstrations rather than controlled cross-tool comparisons (S10). The authors explicitly identify non-European, admixed and founder-cohort validation, probabilistic/dosage genotypes, and smaller-device operation as remaining work (S11). The current analysis uses hard-called imputed genotypes (S14); uncertainty discarded during hard-calling cannot be recovered by treating the output as exact dosage.

## Methods that inform the next experiments

| Learning from the paper | Proposed genomeOS use — an inference, not a demonstrated result | Required counter-test or refusal |
|---|---|---|
| Hierarchical univariate/local sparse screening followed by a joint sparse fit (S3, S15–S16) | Test blockwise compression before a shared multivariant model if independent-population/locus counts justify it | Perform screening entirely inside training folds; compare to unscreened and simpler shared-factor baselines at equal information/tuning budgets |
| The joint pruning step and fresh chromosome-excluded refits matter; deleting fitted coefficients is not equivalent (S3, S16, equation 4) | Treat every derived training statistic as part of the fitted pipeline, with explicit dependency and refit provenance | Deliberate-leakage tests must fail when held-out rows or variants affect selection; the paper's chromosome sensitivity correlation does not waive geographic fold isolation |
| Reuse exact cohort-specific sufficient statistics in fine-mapping (S7, S19, equation 13) | Cache training-only block statistics once and reuse them across compatible AF challengers | Key caches by source bytes, samples, alleles/orientation, missingness, block, split and code/statistic version; a new subset invalidates them |
| Batched traits share genotype decoding and transfers (S8) | Consider batching compatible variant-block experiments to amortize input preparation | Measure selection, conversion, recomputed metadata, transfers, setup, compute and serialization; report cold and repeated costs separately |
| Sparse representations reduce device memory but do not remove statistical dependence (S3, S16) | Compare sparse local/block representations to shared factors before whole-genome attention | Preserve rare/localized alleles; compare regional and whole-locus holdouts, not only conditional imputation |

The fresh LOCO solve includes an explicit ridge term proportional to sample count, not an unspecified numerical epsilon (S16). Such regularization changes a calculation and must be declared and tested if adopted. GenomeOS does not inherit this value or the binary association procedure's fallback policies merely because they work for that paper's target.

The held-out PRS evaluation uses distinct training, validation and test sets, with feature selection in training and tuning via validation (S23). That separation is useful precedent, but individual-level PRS prediction is not the present-day resident AF target. Reported full-model height variance explained includes covariates; it is not an incremental genotype-only effect. Reading these methods does not expand genomeOS's server-side restrictions on anthropometric burden rendering.

## Software-version and LD boundaries

The article's Results describe utility capabilities that its code-availability text also lists as future work. Resolve actual availability through a pinned implementation and executable tests, not either prose passage alone. The inspected local checkout has `ld_matrix`; the [preflight](cugen-ld-preflight-2026-09-09.md) documents its concrete restrictions.

For the initial LD pilot, request unphased `r` and `r2` explicitly. The selected LD API accepts encoding 0 hard calls; CuGen's separate phased encoding 4 exists elsewhere and is refused by this path. Estimated D/D-prime remain a separate admission decision. Marginal AF tables do not identify LD, pairwise missingness does not guarantee a positive-semidefinite joint matrix, and LD-assisted imputation with local genotypes does not demonstrate extrapolation into an unsampled region.

Next evidence remains unchanged: validate exact sample-subset identity and recomputed metadata, compare independent CPU counts/correlations against CuGen CPU/GPU on bounded synthetic blocks, measure the complete workflow, and only then use source-qualified real blocks in frozen predictive comparisons. No worldwide AF accuracy claim follows from this methods review or the twelve existing CPU preflight tests.

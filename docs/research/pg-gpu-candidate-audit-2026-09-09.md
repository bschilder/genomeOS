# pg_gpu candidate audit — 2026-09-09

Status: primary code/documentation inspection, **not** a validated genomeOS dependency, full-paper review or hardware benchmark. This extends the candidate inventory for [#189](https://github.com/bschilder/genomeOS/issues/189), WP6 and the later temporal/connectivity work; it does not change the active count-scoring experiment.

## Evidence inspected

The author repository describes CuPy-based population-genetics statistics, including LD, SFS, divergence, relatedness and local PCA. The inspected source revision is `d2643eac9e187b56a8d814fb2658b49f3d6a4421`, resolved directly through GitHub on September 9; its recorded commit time is 04:22:59 UTC. Its source licence is MIT, inspected at that exact revision. These facts concern software, not permission to use or redistribute any genomic input. [Author repository](https://github.com/kr-colab/pg_gpu), [pinned licence](https://github.com/kr-colab/pg_gpu/blob/d2643eac9e187b56a8d814fb2658b49f3d6a4421/LICENSE).

The pg_gpu preprint DOI is `10.64898/2026.05.29.728868`. Publisher access failed, so its full text was **not** read; no paper-level speedup is adopted here. CuGen's publisher full text also remained inaccessible, and the supported Chrome connection failed before opening a browser/profile. This audit does not change either paper's reading status.

## Semantics that matter

The public `ld_statistics.r` and `r_squared` APIs accept four phased-haplotype counts per variant pair, ordered `[n11, n10, n01, n00]`, with optional valid-sample counts. Their documented output is float64; monomorphic/undefined cases produce NaN. An adapter must preserve an explicit undefined-status mask, not turn undefined LD into zero association. Signed r and r-squared are different inputs to downstream models. [Pinned API source, inspected signatures/docstrings](https://github.com/kr-colab/pg_gpu/blob/d2643eac9e187b56a8d814fb2658b49f3d6a4421/pg_gpu/ld_statistics.py).

The streaming tutorial specifies diploid VCZ input and rejects haploid/polyploid stores. It distinguishes reducible, chunked statistics from full pairwise r-squared matrices, which require materializing a bounded region. Streaming LD bins carry boundary context; relatedness output can still consume quadratic host memory. Consequently, a GPU-friendly reader alone does not make whole-genome all-pairs LD or biobank all-pairs relatedness scalable. These are documented capabilities/limits, not independently measured ones. [Pinned streaming tutorial, read fully](https://github.com/kr-colab/pg_gpu/blob/d2643eac9e187b56a8d814fb2658b49f3d6a4421/docs/source/tutorials/biobank_streaming.rst).

The LD-block example computes a full regional pairwise matrix, then detects low bridging scores around simulated hotspots. That is a useful small-region experiment, not evidence that inferred blocks are universally independent resampling units. GenomeOS should retain prespecified locus/chromosome holdouts and evaluate any learned block boundaries using training information only. [Pinned LD-block tutorial, read fully](https://github.com/kr-colab/pg_gpu/blob/d2643eac9e187b56a8d814fb2658b49f3d6a4421/docs/source/tutorials/ld_blocks.rst).

The audited revision merges a correction making public `pi2` symmetrization consistent across population-index patterns. The upstream issue explicitly distinguishes this public-API inconsistency from its then-existing pipelines, which it reports already agreed with their reference. We have not independently reproduced that claim. This is a concrete reason to pin definitions and revisions rather than assume identically named statistics are interchangeable. [Issue #279](https://github.com/kr-colab/pg_gpu/issues/279), [fix revision](https://github.com/kr-colab/pg_gpu/commit/d2643eac9e187b56a8d814fb2658b49f3d6a4421).

## Proposed admission experiment, not yet executed

**Scientific objective:** determine whether compatible training-only genomic data provide valid, useful cross-variant or connectivity information. **Measurable output:** exact count/defined-status parity, declared LD-estimator agreement, bounded complete-workflow cost, then improvement on the unchanged geographic or conditional-imputation target. **Component/interface:** an offline adapter returning versioned block statistics with source/sample/variant orientation, ploidy, missingness and definition provenance. **Assumptions/refusals:** no LD inference from marginal frequencies alone; no unauthorised data export; no silent phase, denominator, ancestry or missingness conversion.

Admission should proceed in this order:

1. Tiny hand-calculated phased blocks: independent, positively/negatively associated, rare and monomorphic pairs, explicit missing calls and sample subsets. Compare exact pair counts before comparing statistics. Flipping one allele changes signed r, not r-squared.
2. Independently implemented CPU references and pinned pg_gpu/CuGen candidates on compatible input representations. Keep phased haplotype LD, unphased genotype correlation and imputed-dosage correlation distinct; explicitly refuse unsupported ploidy instead of converting ancient pseudohaploidy to diploidy.
3. Boundary-sensitive regional/streaming parity, including pairs crossing chunk edges, sample-axis chunks, absent calls, inaccessible sites and allele orientation. Check host as well as device memory and include conversion, decompression, transfers, setup and artifact writing in end-to-end costs.
4. If the output becomes a covariance/correlation model, test positive semidefiniteness and valid joint probabilities. Pairwise deletion or independently predicted pair statistics need not yield a valid joint matrix; do not silently project, truncate or fill missing entries.
5. Admit statistics only after training-partition derivation and matched-access ablations establish incremental predictive value. Local held-out genotypes helping imputation are not evidence of geographic extrapolation into an unsampled population.

For intuition, two loci can both have marginal frequency 0.5 while their haplotypes occur only as `00/11`, equally as all four haplotypes, or only as `01/10`. The corresponding association differs even though the two frequency maps are identical. More accurate marginal maps therefore do not identify LD by themselves.

No package was installed, genotype downloaded, source repository uploaded, or additional GPU job launched for this audit. The active synthetic count-scoring environment remained unchanged.

# A research program for worldwide allele-frequency inference

Research memo • September 9, 2026 • No model training or implementation performed.

Reading scope: ten selected Anandkumar coauthored papers were read through their main text and scientific appendices where present, using public full-text copies. See the [full-text reading notes](genomeos-anandkumar-fulltext-notes-2026-09-09.md) for exact versions, section-level findings, and coverage limits. Other references below have varying review depth; inclusion in the bibliography does not mean every cited publication was read in full. This is a focused research synthesis, not an exhaustive systematic review.

## Recommendation

Develop a **probabilistic, multivariant model of population structure on the sphere**, with an explicit observation process, local geographic connections, and supported long-distance connections. Evaluate a spherical neural operator as one candidate implementation of that model. Choose the architecture through a frozen benchmark that rewards accurate predictions, calibrated uncertainty, and defensible spatial resolution.

The strongest near-term hypothesis is that genomeOS will gain more from representing sampling, ancestry, and shared structure correctly than from replacing its Gaussian process with a large neural network. This is a research judgment, not a measured result. A richer model can ultimately combine these improvements: a shared genomic representation, a migration-aware spatial prior, selected environmental covariates, and a probabilistic neural operator that amortizes inference across loci.

Anandkumar's work contributes three particularly useful ideas: continuous rather than grid-bound representations; efficient global interactions combined with local structure; and evaluation of distributions and their spatial dependence. Population genetics contributes the mechanisms that must accompany those ideas: drift, migration, admixture, recombination, selection, and observation error. Neither body of work establishes that a neural operator will outperform genomeOS on sparse human genetic surveys. That comparison remains to be done.

The proposed order is: **benchmark and observation contract → stronger statistical baselines → multivariant sharing and spatial connectivity → neural-operator comparison → LD and temporal extensions**. Data acquisition and evaluation run throughout. An additional source or model component earns inclusion through a predeclared ablation, not through the plausibility of its story.

## 1. Scientific contract

**Scientific objective.** Estimate the frequency of a specified allele among a defined target population, in a geographic region and time period, as accurately and finely as independent evidence supports. For the principal product, the target should be present-day residents under a stated population-sampling definition. Ancestral-origin distributions and historical distributions are separate estimands and separate outputs.

**Measurable output and acceptance evidence.** Produce predictive distributions for held-out allele counts given their denominators and sampling metadata; posterior distributions for latent population frequency; and a map of validated support and effective resolution. Acceptance requires improvement over strong baselines on geographic and study holdouts, calibrated predictive uncertainty, stability under data perturbation, and evaluation on a sealed external set. Published HbS/G6PD/screening comparisons remain additional scientific controls, with their actual outcome definitions and interval levels preserved.

**Engineering component and interface.** Extend offline P2 through typed observation, covariate, split, model, prediction, and evaluation contracts. Keep P0/P1 evidence separate from predictions. P3 consumes coherent posterior draws; P4/P5 consume immutable precomputed artifacts. A candidate fitter must accept explicit data/configuration and return both a distribution over the latent field and a distribution over observable measurements.

**Assumptions, refusals, and consumers.** Sampling and location semantics must be known sufficiently to identify the requested target. Missing denominators, unresolvable coordinates, unverified population composition, unsupported dates, failed inference, and unsuccessful calibration are explicit limitations or refusals. Unsupported regions do not become supported because an environmental raster is available. Consumers include the Atlas, burden calculations, scientific analysis, and prioritization of additional sampling; none should interpret a geographic frequency as an individual's genotype.

This is a proposed research program, not evidence that performance has improved. The temporal work deliberately extends beyond the original modern-only P2 scope.

## 2. What the podcast actually contributes

The supplied episode is *“We have foundation models for language, not for physics”*, Latent Space, August 26, 2026. Relevant passages in its timestamped transcript are summarized below; automatic transcription contains occasional technical-word errors.[^1]

| Passage | Learning |
|---|---|
| 16:32–18:51 | Continuous representations permit changing resolution; finer predictions still require regularization or new information. |
| 19:13–24:34 | Fourier mixing captures global interactions efficiently; nonlinearities and residual connections retain neural-network flexibility. |
| 32:34–33:10 | Operator learning is not restricted to known PDEs; usable training data motivated the weather application. |
| 39:20–39:59; 50:28–51:37 | Training examples are global weather states, and reanalysis combines observations with physical modeling. |
| 53:03–56:41 | Ensemble calibration is a training/evaluation objective; ensemble size alone is insufficient. |
| 58:22–58:43; 62:51–63:08 | Spherical geometry matters; finer-grid validity still needs supporting constraints. |

The application-specific inference is crucial: genomeOS does not possess a weather-reanalysis equivalent containing tens of thousands of well-constrained global genetic states. Millions of variants are also not millions of independent realizations: linked variants and variants measured in the same small set of populations share information and biases. We should borrow the operator architecture and benchmarking discipline without assuming the weather data regime transfers.

“Infinite discretization” means that the learned mathematical map can be evaluated under changing discretizations. It does not mean infinite recoverable information, unlimited spatial accuracy, or zero discretization error. Existing continuous GPs also allow arbitrary query coordinates. The potential advantage is learning reusable transformations across fields and scales, not simply drawing a smoother map.[^2][^3]

## 3. Publications and their specific relevance

| Work | Established contribution | Proposed genomeOS use and limit |
|---|---|---|
| Li et al., Fourier Neural Operator; Kovachki et al., Neural Operator | Learn maps between function spaces, with efficient spectral parameterizations.[^2][^3] | Learn a map from available genetic observations and covariates to a frequency distribution. Sparse inverse inference is a different task from the PDE examples. |
| Guibas et al., AFNO | Fourier-domain token mixing with quasi-linear sequence complexity.[^4] | A global spatial mixer. AFNO replaces attention-style mixing; it is not automatically “FFT plus full attention everywhere.” |
| Pathak et al., FourCastNet | Global weather forecasting using AFNO.[^5] | Reuse training/evaluation patterns across many related fields. Weather performance numbers are not predictions of genetic performance. |
| Bonev et al., SFNO | Spherical harmonic operators avoid flat-grid artifacts in spherical dynamics.[^6] | A global spherical component, with explicit geometry and quadrature. GenomeOS geography still needs spatially varying covariates and connectivity. |
| Li et al., GINO | Graph operators connect irregular inputs/outputs with an efficient regular latent representation.[^7] | Encode irregular surveys and decode onto H3 cells or a scientific mesh. Its aerodynamics experiments do not validate genetic interpolation. |
| Liu-Schiaffini et al., localized operators | Combine global operators with localized integral/differential kernels.[^8] | Test whether a local branch preserves regional gradients that a low-frequency global representation misses. |
| Rahman et al., CoDA-NO | Attention between variable-fields, with Fourier operators inside the attention mechanism; masked-field pretraining.[^50] | A direct Fourier/attention candidate for cross-variant sharing, restricted initially to small locus blocks. Mixed task results require comparison against shared factors and equally pretrained alternatives. |
| Bonev et al., FourCastNet 3 | Probabilistic spherical forecasting; spatial and spectral scoring address different distributional properties.[^9] | Evaluate spatial dependence as well as per-cell intervals. Do not compute spectral “truth” by interpolating sparse test observations. |
| Lam et al., GraphCast; Kochkov et al., NeuralGCM; Price et al., GenCast | Graph-based forecasting, hybrid dynamical modeling, and probabilistic forecasting provide distinct successful alternatives.[^10][^11][^12] | Include graph and mechanistic hybrids; neural operators should face architectural competition. |
| Gordon et al., ConvCNP | Conditions predictions on variable sets of observations through functional representations.[^13] | A useful smaller neural baseline for sparse-context prediction. Joint uncertainty requires an appropriate latent-process extension. |
| Yang et al., SPA; Battey et al., Locator | Spatial allele-frequency modeling and genotype-to-location prediction.[^14][^15] | SPA is relevant prior art; Locator is an auxiliary benchmark, not proof of AF prediction or grounds for assigning inferred locations as observed. |
| Bradburd et al., BEDASSLE and conStruct | Model ecological/geographic differentiation and mixtures of continuous population structure.[^16][^17] | Test covariance and ancestry components before large models. Do not treat learned components as fixed ethnic categories. |
| Petkova et al., EEMS; Marcus et al., FEEMS | Estimate spatial genetic connectivity/effective migration.[^18][^19] | Motivate nonstationary graph structure; effective migration is not a directly observed count of people moving. |
| Al-Asadi et al., MAPS | Uses haplotype sharing to estimate recent migration and population-size surfaces.[^20] | A route to time-sensitive connectivity when genotype/haplotype data are available. |
| *Jointly representing long-range genetic similarity…* (2025) | Extends local spatial structure to represent long-distance genetic similarity.[^21] | Particularly relevant to diaspora and nonlocal connections. An inferred connection alone does not identify its historical cause. |
| Wohns et al.; Vaughn and Nielsen, CLUES2 | Genealogies linking modern/ancient genomes; temporal and linkage information for allele histories and selection.[^22][^23] | Later-stage temporal priors and locus-specific checks, with genealogy uncertainty. Not ready-made worldwide frequency engines. |
| Akbari et al. (2026), West Eurasian ancient-DNA selection | Recent work separates directional temporal signals from major population-history confounding.[^24] | A current methodological lead and regional comparison, not global temporal ground truth. |
| Rasp et al., WeatherBench 2; Roberts et al., structured cross-validation | Reproducible comparison across targets and evaluation respecting dependence.[^25][^26] | Build a benchmark before optimizing a favorite architecture. |

A particularly useful point from FourCastNet 3 is that marginal CRPS can remain unchanged when ensemble members are independently shuffled at every location, even though the resulting fields are spatially implausible. GenomeOS regional totals similarly depend on cross-location dependence, not just individual intervals. This motivates joint-field checks and draw-level aggregation.[^9]

The full-text review also distinguishes three different recipes: AFNO replaces a transformer's token mixer; CoDA-NO applies attention across function-valued variables; FourCastNet 3 uses convolutional spherical operators rather than a transformer. They should not be conflated into a single architecture. The broader review explains the surrogate/inverse-modeling alternative, while the 2026 library paper explicitly cautions that resolution-agnostic parameterization alone guarantees neither cross-resolution generalization nor physical consistency.[^51][^52]

## 4. What genomeOS already has, and what needs testing

The local source snapshot inspected was commit `a071a7b`. The findings below are source inspection, not a new numerical evaluation.

| Current component | Implication for the research program |
|---|---|
| `genomeos/surfaces/fit.py`: beta-binomial default, Matérn-5/2, unit-sphere coordinates, HSGP or inducing approximation | Freeze this actual implementation as the baseline. The original INLA/Matérn-3/2 design text is not an accurate description of current code. |
| A single variant per `fit_surface` call | Shared factors and joint models are substantive extensions. Existing issue #128 already frames pooling. |
| One spatial lengthscale per variant | Nonstationarity is a known research direction (#129), not a new discovery. |
| `predict` versus `predict_observation` | Preserve the distinction between uncertainty about frequency and uncertainty about a new survey. The latter includes sampling variability. |
| `validation/crossval.py`: spatial, random, and whole-cohort splits | Build on existing work; add combined geography/cohort exclusions and explicit geographic buffers. |
| Current log score uses a binomial expression evaluated at the predicted median | Retain it as a legacy point-prediction diagnostic, but add integrated predictive log probability under the actual observation distribution. It does not evaluate the beta-binomial posterior predictive distribution. |
| `batch.py`: skill gate exists, with `skill_folds=0` at the function default | Check launch manifests before claiming the deployed build always uses it. Research comparisons must make the gate explicit. |
| Failed folds are reported but successful-fold summaries remain available | Publication decisions need a rule for all planned folds; a difficult fold cannot disappear from model selection. Existing #111 documents this risk. |
| Fitting uses coordinate centers; no `radius_km` integration appears in `fit_surface` | Test an explicit footprint observation model. Carrying a radius in P1 is not equivalent to using it in the likelihood. |
| Inducing implementation uses a deterministic conditional field | Compare its uncertainty against a small full-GP reference and simulated truth; coherent draws alone do not establish that approximation uncertainty is represented. |

Additional audit targets: matching predictive design/cohort assumptions to each held-out survey; handling a missing reference sampling-design level; and ensuring micro-scale heterogeneity is included in the relevant predictive target. These need focused diagnostics before conclusions about their numerical impact.

The issue record already contains measured examples of variants with little or negative spatial skill (#130), and a warning that Piel's published national intervals are IQRs rather than 95% intervals (#92). Reproducing an existing paper is an important integration check, but reuse of its training surveys prevents calling that comparison fully independent validation.[^27]

Issue #66 has been resolved: the recorded decision permits publishing derived surfaces from the named panels while preserving attribution/notices and honoring explicit source restrictions. Some repository prose still describes that decision as open. The proposed program follows the recorded decision rather than reinstating a blanket restriction.[^28]

## 5. Define the population before the surface

For an allele `v`, location `s`, and time `t`, define a resident-population target `p_v(s,t)`. If a modeled population mixture is needed, write:

`p_v(s,t) = Σ_k w_k(s,t) p_v,k(s,t)`

Here `w_k` describes a specified mixture of ancestry/history components among residents; it is not a nationality label. The mixture must be supported by evidence, and its uncertainty must propagate. Without adequate composition data, an ancestry-conditioned surface can be estimable while a resident-population surface is not.

For survey `i`, its expected frequency is an average over its actual sampling support:

`q_iv = ∫∫∫ p_v(s,t,a) w_i(s,t,a) ds dt da`

`AC_iv ~ BetaBinomial(AN_iv, q_iv, concentration_iv)`

The notation is schematic: the implemented model must specify ascertainment, assay error, and cohort effects separately, with a declared parameterization. A survey's spatial averaging weights are determined by recruitment, not automatically by land area or present-day population density. A radius alone is not a sampling distribution; if only a radius is documented, compare explicitly declared footprint assumptions and report sensitivity. Average probabilities over space, rather than applying the inverse-logit to an averaged latent logit.

Allele count and denominator belong in the likelihood. The held-out count is the outcome and cannot also be an input feature. Preserve zero-count rows; distinguish unassayed/missing sites from observed absence. Use the correct ploidy, callable denominator, and assay representation for sex chromosomes, structural variants, and typed loci.

The UK/Sudan example suggests valuable evidence, but not a deterministic relocation rule. A sampled diaspora community may originate from a small subregion, have experienced a founder effect, be related, or have mixed after migration. Its counts can update an origin-conditioned distribution through documented origin information and a migration model. They cannot establish that contemporary Sudan has the world's highest frequency. Highest frequency and largest number of carriers are also different targets: the second requires population denominators.

A historical layer should represent frequencies at the historical time, not a modern community moved backward on a map. Place of burial, birthplace, residence, and ancestral origin are distinct metadata. Uncertain origins can be multimodal distributions; do not collapse them to a false pinpoint.

## 6. Model ladder and the neural-operator candidate

### Statistical and neural comparisons

| Arm | Model | Question answered |
|---|---|---|
| B0 | Pooled count model with calibrated uncertainty and matched ascertainment target | Is any spatial model justified? |
| B1 | Local count smoother, simple spherical trend, and regularized covariate regression | Can inexpensive methods explain the gain? |
| B2 | Frozen current GP; then GP with footprint integration and selected covariates | How much comes from observation semantics and information rather than architecture? |
| B3 | Partially pooled multivariant spatial factors, with variant-specific residuals | Does shared structure improve sparse variants without erasing distinctive histories? |
| B4 | Sparse graph/GMRF or nonstationary GP, with local edges and justified long-distance links | Does connectivity outperform geographic distance alone? |
| N0 | Parameter-controlled graph network or conditional neural process | Is a neural operator necessary for neural-model gains? |
| N1 | Sparse encoder → spherical global operator plus local branch → probabilistic query decoder | Does amortized operator learning improve accuracy, calibration, resolution, or cost? |
| N2 | Blockwise CoDA-NO-style cross-variant attention, with the same probabilistic output contract | Does attention between fields improve over shared factors and N1 under matched information and compute? |
| T1 | Temporal state-space extension of the best supported spatial model | Do historical anchors improve held-out present and past predictions? |

A useful shared model is `logit p_v(s) = μ_v + X(s)β_v + Σ_k a_vk z_k(s) + r_v(s)`: shared spatial fields `z_k`, variant loadings `a_vk`, and a variant-specific residual `r_v`. Pool scales and effects softly; do not impose a single range across all alleles. Fit all shared representations and frequency-based variant bins within the training partition. Partial pooling of related variants is not equivalent to modeling LD.

The spherical challenger should encode each available survey's counts, denominators, footprint, date support, assay, and sampling design. Use set/graph operations to transfer irregular evidence to a latent spherical representation with appropriate density normalization and integration weights. Preserve an explicit missingness channel: unsampled is not zero frequency. Missingness may also encode the sampling process, so it requires a dedicated ablation.

A global SFNO-like branch captures broad relationships; a local graph branch handles boundaries and fine-scale variation; sparse attention can connect selected population-history or locus representations. Do not build all-pairs attention over every variant × every geographic cell. Do not apply a rectangular FFT directly to an H3 array. A regular spherical harmonic grid, or a carefully constructed graph basis, needs explicit transfer and aggregation operators.

Use environmental covariates to break inappropriate homogeneity: the Earth being spherical does not make all rotations biologically interchangeable. Ocean crossings and mountain barriers are learned or evidence-supported connections, not universally forbidden routes. A historical ocean may be a corridor, and a border may have little genetic relevance.

Train on tasks consisting of a permitted context set and held-out count observations, initially across loci and simulated demographic histories. Never generate dense “ground truth” by interpolating the whole observation dataset before splitting. GP-generated surfaces can support a labeled distillation/speed experiment, but reproducing them is not evidence of better inference of reality.

Retain an explicit stochastic latent field and observation model. Compare approximate Bayesian inference with reference inference on tractable subsets, and test ensemble calibration separately. An ensemble's spread is not automatically posterior uncertainty. The first neural experiment may learn a covariate mean or shared prior while retaining a Bayesian spatial residual, provided uncertainty from learning that component is evaluated and not silently ignored.

For N2, distinguish spatial tokens from variant-field tokens. Begin with a bounded block or a small set of shared fields; preserve allele identity, count exposure, masks, and baseline prevalence. Normalization must not erase the frequency differences being predicted. Match masked-pretraining data across neural competitors, and select on held-out count prediction rather than reconstruction of the input. CoDA-NO's Appendix G includes a joint-system setting where FNO predicts better despite CoDA-NO reconstructing better; its runtime comparison also shows substantial overhead.[^50]

An alternative temporal branch keeps Bayesian inference and replaces an expensive **forward simulator** with a learned surrogate. FNO already demonstrates a surrogate inside Bayesian inverse inference (§5.5; Appendix A.5). For genomeOS this is a proposal: first establish a suitable stochastic demographic simulator, then validate surrogate error and posterior calibration against exact simulation on small problems. Unknown migration and selection processes make physical constraints less secure here than in a benchmark with known equations.[^2]

## 7. Data layers: collection first, then predictive value

These are candidate acquisition paths, not a claim that every release has been downloaded or approved. The first batch should use a small global feature set with versioned metadata. “Global” coverage of a modeled raster does not imply equally good observations everywhere.

| Layer | Collectable source and scale | Recommended first role; limitation |
|---|---|---|
| Counts, denominators, assays, sampling metadata | Existing P1 surveys; harmonized HGDP/1KG; additional qualified literature (#3 and #180 onward) | Highest priority. Additional independent, precisely located populations can be more valuable than more SNPs in the same populations.[^27] |
| Genomic structure | Permitted genotypes, unrelated samples, allele/genotype likelihoods, neutral-marker covariance, IBD/haplotypes | Shared ancestry/connectivity. Large ancestry-only summary resources cannot supply precise geographic truth or individual LD. |
| Elevation and terrain | Copernicus DEM GLO-30/GLO-90; global nominal 30/90 m products | Aggregate elevation, slope, ruggedness, and barriers over footprints. Product/service access differs; use a permitted pinned distribution, not an assumption based on map availability.[^29] |
| Water and drainage | HydroRIVERS/HydroLAKES/HydroATLAS | Distances and connectivity features; HydroATLAS is CC BY 4.0. Rivers can be corridors as well as barriers.[^30] |
| Land cover and vegetation | ESA WorldCover global 10 m maps for 2020/2021 | Fractions of cover classes and modest regional summaries, not a 10 m genetic claim. CC BY 4.0; two maps are not deep-time land-use history.[^31] |
| Recent climate | ERA5-Land, hourly since 1950, approximately 9 km | Long-term temperature/precipitation summaries and seasonality first. Reanalysis is model-assisted; pair covariate periods with survey dates.[^32] |
| Paleoclimate and paleogeography | CHELSA-TraCE21k: approximately 1 km, 100-year steps across 21,000 years | Later temporal prior; includes reconstructed orography. Downscaled detail is conditional on climate-model assumptions, not observed kilometer-scale ancient climate.[^33] |
| Population density and age/sex | WorldPop country/global products; UN demographic series | Needed for resident-mixture weights, burden, and observation-process diagnostics. Check product/year: some years are projections and fine grids inherit coarse demographic inputs.[^34] |
| Historical population and land use | HYDE 3.2, 10,000 BCE–2015 CE | Coarse demographic scenarios and sensitivity analyses. Historical reconstructions are not census observations and census size is not effective population size.[^35] |
| Modern migration | UN migrant-stock tables; Gaskin & Abel 2026 annual migration model and downloadable ensemble | Country-level long-distance priors. Stocks are not flows; model-derived flows have uncertainty and are not reproductive migration rates.[^36][^37] |
| Forced displacement | UNHCR country/year origin/asylum data, supplemented only by verified finer sources | Time-varying demographic evidence. Nationality/origin fields do not identify genetic ancestry or village-level origins.[^38] |
| Malaria and other pathogens | MAP malaria layers and underlying evidence | High-priority mechanistic pilot for HbS and relevant alleles. Contemporary prevalence need not represent historic selection; audit source overlap and derived-map dependencies.[^39] |
| Biodiversity, fungi, bacteria, parasites | GBIF occurrences plus specific validated pathogen/vector datasets | Later, narrow hypotheses. Occurrence density is not exposure or absence; reporting effort and access can dominate apparent signal. GBIF licenses vary by contributing dataset.[^40] |
| Conflict and displacement shocks | UCDP georeferenced events and precision metadata | Recent temporal/migration covariates; preserve location uncertainty and ascertainment. Bulk downloads are preferable for a pinned release; API access now requires a token.[^41] |
| Historical polities, trade, enslavement | Seshat/Cliopatria; SlaveVoyages routes and methodology | Selected, documented regional pilots. Polity maps are reconstructions; ports are not the geographic origins of all transported people. No global exhaustive event ledger is established by these sources.[^42][^43] |
| Famines, colonial transitions, alliances, trade agreements | Individually qualified historical/census sources | Defer universal ingestion. Require event dates, spatial support, uncertainty, ascertainment, and a mechanism through demography or selection. No event-specific coefficient without enough independent contrasts. |
| Wind, atmospheric composition, volcanic activity, celestial trajectories | Consider only through a concrete exposure/history hypothesis | Lower priority than ancestry, migration, terrain, and count quality. Orbital forcing may enter an existing paleoclimate reconstruction; adding it again may only encode time. Modern weather is usually the wrong timescale. |

Useful additions include recombination rate, variant age uncertainty, local ancestry, introgression, endogamy/relatedness, bottlenecks, and historical diet/agriculture. Technical variables—callability, assay platform, typing resolution, coverage, laboratory, imputation panel, and recruitment—can matter more than an exotic environmental layer. Clinical association annotations do not establish the sign or magnitude of natural selection.

### Cesium's role

The current `website/src/atlas/earth-style-catalog.ts` includes Cesium World Terrain and multiple imagery providers. These are display integrations, not a versioned scientific covariate store. Prefer scientific source rasters with units, quality flags, dates, and terms, while reusing the application's globe for inspection. Cesium explicitly distinguishes its assets from third-party content and links their respective terms.[^44]

Do not treat a styled basemap, shaded relief, or mosaic imagery as a calibrated measurement. If a Cesium-derived feature is useful and permitted, extract it offline, pin the provider/asset/version/sampling level, and compare it against a scientific raster. Rendering level of detail must not change the feature used by the fitted model.

### Admission protocol for each layer

Record source/release/checksum, units, spatial support and native resolution, valid time, publication/availability time, observed-versus-modeled status, missingness, uncertainty, upstream dependencies, and source-specific use terms. Measure coverage over intended prediction regions and time periods before evaluating the layer.

Then run a paired experiment with the same outcomes and splits: baseline; baseline plus the layer; layer without geography; missingness-only; and a spatially structured negative control. Test incremental value after ancestry/structure adjustment and after related feature groups. If gains require dropping hard-to-cover regions, score both the common comparison set and the complete deployment population. Do not call selective coverage an accuracy improvement.

Use lagged or historical features only when their temporal meaning is appropriate. No future covariate information enters a forecasting track. If reconstruction uses later information, label it reconstruction. Persist rejected layers and negative experiments so repeated searches do not quietly select chance successes.

## 8. Multiple alleles, linkage, and GPU computation

There are three different experiments:

1. **Sharing across loci:** learn recurring population structure across many variants, including unlinked ones.
2. **Multiple alleles at one locus:** use a categorical/multinomial or Dirichlet-multinomial observation model, with latent allele probabilities constrained to sum to one.
3. **Linkage across loci:** model dependence between alleles carried on the same chromosomes, using compatible genotype/haplotype information.

AFND allele lists cannot automatically become complete multinomial observations. Typing resolution, reported allele subsets, and denominators must be compatible; unreported alleles cannot be converted to zeros. HLA alleles, KIR presence, structural variants, and phenotype-level G6PD deficiency require their own measurement semantics. Do not relabel a deficiency phenotype as a particular causal SNP.

LD is not identifiable from marginal allele frequencies alone. For two biallelic loci, the same two marginal frequencies permit many haplotype distributions. A predicted LD surface therefore needs haplotype/genotype data or explicit assumptions, and must retain its uncertainty. Cross-population covariance is also not within-population LD: admixture can create associations that pooled calculations exaggerate.

Start with short loci, population-aware LD, and genotype/haplotype likelihoods. Compare no sharing, shared factors without LD, an LD-based conditional predictor, and a haplotype model. Evaluate rare alleles and ancestry mixtures separately. Enforce valid haplotype probabilities, appropriate correlation bounds, and positive-semidefinite covariance where required. Never assemble independently predicted pairwise correlations into an unconstrained “LD matrix.”

CuGen is a relevant candidate: its public repository describes a GPU-native genotype format, allele-frequency operations, random-access locus statistics, and in-sample LD in its fine-mapping workflow. The July 2026 manuscript is a preprint, and the repository describes parts of the toolkit as beta.[^45][^46] This supports a feasibility spike, not an assumption that every genotype representation or LD operation already exists.

The spike should reproduce AC/AN exactly against a CPU reference and compare signed dosage correlation, r², and any required phased haplotype statistic under stated definitions. Test missingness, monomorphic sites, rare variants, mixed ploidy, sample subsets, and allele orientation. Confirm support for uncertain dosages and ancient genotype likelihoods rather than forcing them into hard calls. Measure conversion, disk reads, transfers, computation, and peak memory separately. GPU speed is useful only if the complete workflow improves.

Compute LD on demand **inside the offline experiment/build**, then cache it by genotype release, sample subset, locus, statistic, and implementation version. It remains outside the P4/P5 serving path. Full genome-wide pairwise LD is unnecessary and quadratically expensive.

Most importantly, separate two benchmarks: predicting an allele when other genotypes from that population are available, versus predicting in a population with no genotypes. The first is conditional imputation; the second is geographic extrapolation. Their scores answer different questions.

## 9. Temporal modeling and ancient anchors

Begin with a regional modern-plus-ancient pilot where the same well-harmonized alleles are measured across multiple time periods. LCT/MCM6 is a sensible candidate for frequency/history research if the staged evidence qualifies, but do not substitute neighboring tagging SNPs across populations as though they were identical causal alleles. Include neutral or weakly selected comparison loci. A successful West Eurasian pilot establishes regional feasibility, not global historical resolution.[^23][^24]

A useful first temporal model evolves a distribution over deme frequencies by migration, drift, and optional selection. With destination-normalized migration fractions `M_ij(t)`, the post-migration frequency is `p̃_i = Σ_j M_ij p_j`, with nonnegative rows summing to one. A subsequent Wright–Fisher-style transition can represent genetic drift through effective population size; mutation and selection enter only under explicit parameterizations.

Human movement counts are not automatically those migration fractions: fertility, survival, age, mating, and admixture intervene. Present-day population density does not identify effective population size. Use demographic inputs as uncertain priors, and allow unobserved source populations in simulation stress tests.

A neural operator may later emulate this **forward stochastic transition** or amortize posterior inference. Do not run a diffusion or migration process backward deterministically to infer history: many past states can generate the same present observations. Infer past states by smoothing over a distribution of histories conditioned on modern and ancient evidence. Any learned mechanistic constraint must compete with a less constrained model when the assumed process is misspecified.

AADR provides a valuable centralized, versioned resource, but much of its ancient data are pseudohaploid calls at an ascertained SNP panel. The original resource paper documents geography/time imbalance, technical processing differences, date uncertainty, and modern samples incorporated from other panels.[^47] Its modern component must not be counted again when overlapping reference datasets are included.

For pseudohaploid data, one sampled allele is not two confidently observed chromosomes. For raw reads, use an observation likelihood integrating genotype, depth, contamination, damage, and mapping error; for high-quality diploid calls, use their documented ploidy and uncertainty. Read depth does not equal independent chromosome count. Preserve reference/alternate orientation through assembly harmonization and exclude unresolved mappings explicitly.

Integrate over calibrated date distributions where available; an interval midpoint creates artificial temporal precision. If only a range exists, label any distributional assumption. Convert years BP consistently with the source's epoch; the existing modern=0 convention needs an explicit calendar-date contract before annual migration covariates can be joined. Do not set every modern survey to the present date.

Model archaeological-site and close-kin dependence, and account for preservation, burial, and sampling selection. A well-sampled cemetery is not a random sample of a continent. Imputed ancient calls and reconstructed genealogies are inferred evidence; they cannot serve as independent truth when the evaluation model shares their reference panels.

Evaluate spatial-temporal hole filling, forward forecasting from a historical cutoff, and retrospective smoothing separately. Hold out entire sites/studies and time blocks. Add assays withheld from model development and high-quality reads where possible. Retain joint uncertainty over trajectories, rather than connecting independent per-time posterior means into a falsely precise animation.

## 10. A benchmark designed to resist self-deception

### A. Freeze tasks and leakage boundaries

Construct an observation dependency graph before splitting: original study, cohort, participant/kinship where known, reused table, overlapping panel release, genotype/imputation reference, geographic support, and locus/LD block. Keep connected duplicates and source dependencies out of opposing train/test partitions. If participant overlap cannot be ruled out, mark the evaluation accordingly rather than claiming independence.

| Track | Holdout | Claim it can support |
|---|---|---|
| Nearby interpolation | Whole new studies within a sampled region | A new survey near existing evidence |
| Regional extrapolation | Whole geographic blocks plus buffers, removing overlapping studies and footprints | Prediction into geographic gaps |
| Population transfer | Entire populations and relevant related/diaspora dependencies | Generalization beyond represented groups |
| Locus transfer | Entire genes/LD blocks or chromosomes from shared-model training | Transfer to a new locus rather than memorized linkage |
| Conditional imputation | Hide target alleles while explicitly allowing other local genotypes | Usefulness of available LD/genomic context |
| New-region, all-variant holdout | Hide all genomic outcomes from the region | Geographic generalization of a shared model |
| Temporal forecasting | Training evidence and covariates restricted to an as-of cutoff | Prediction forward in time |
| Historical reconstruction | Withhold ancient sites/time windows; later evidence permitted and labeled | Reconstruction conditional on later observations |
| External confirmation | Sealed studies/data releases never used for development | Final out-of-development performance |

Use multiple predeclared geographic buffer distances, for example 100, 300, and 1,000 km where sample support permits. These are proposed stress-test distances, not biological constants. Report the realized train–test separation and overlap of spatial footprints. K-means clusters alone do not enforce a minimum gap. If a buffer leaves too few independent training units, report infeasibility for that track rather than quietly shrinking it.

All outcome-dependent processing belongs inside the training fold: variant selection, allele-frequency bins, learned ancestry representations, LD, imputation, migration inferred from genetics, feature selection, hyperpriors, calibration, and early stopping. Pre-existing target-area genotypes may be used only in a separately declared conditional/transductive track. External embeddings or summary statistics must have an overlap audit too.

### B. Separate development from confirmation

Use nested, dependency-aware validation. Inner folds choose hyperparameters, covariates, and architecture; outer development folds estimate comparative performance. Repeatedly consulted outer folds eventually become development data. Reserve a final sealed source/geography set, and ideally a later prospective release, for a limited number of confirmations.

Repeat stochastic models using a fixed seed list derived from the project seed 42. Repeat spatial partitions where feasible, but do not treat repetitions as independent populations. Allocate comparable tuning budgets and report both predictive quality and compute. Maintain a ledger of every model/feature trial, including failures and negative results.

Match pretraining access, target-data versions, and checkpoint-selection rules explicitly. Report the cost of preparation, spatial transfer, training, posterior sampling, and aggregation—not just Fourier mixing. A model with access to additional fields or a larger pretraining corpus is a different information-budget experiment, even if its supervised training rows match.

### C. Score distributions and decisions

The primary probabilistic score should be held-out log predictive density for counts:

`log P(AC_i | AN_i, metadata_i, training data)`

Integrate over latent frequency, overdispersion, and relevant new-cohort/assay effects. For posterior samples, average probabilities using log-sum-exp; do not average log probabilities or insert a posterior median into the likelihood and call it the integrated score. Include the count normalization term when reporting absolute density scores.

Report both survey-macro and hierarchical region/variant-macro averages, with predeclared weights. A single very large cohort or locus with thousands of linked variants must not decide the global headline. A secondary per-chromosome score can be useful, but changes the target weighting and should be named separately. Denominator strata expose differences driven by sampling precision.

Complement this with predictive CRPS or weighted interval score; 50/80/95% predictive coverage; interval width; randomized PIT or rank diagnostics for discrete counts; MAE using posterior medians; and RMSE using posterior means. Display calibration and error by allele-frequency band, sample size, sampling design, assay, geographic region, and distance from training observations. Report effective numbers of independent studies/populations, not only row counts.

A noisy survey proportion is not the true population frequency. Latent-frequency coverage can be measured directly in simulations and approximately challenged with large representative independent studies; it cannot be inferred simply by counting small-survey proportions inside latent intervals. For clinically relevant thresholds, evaluate exceedance probabilities with an appropriate observed target and sampling model, not by treating a noisy proportion's threshold crossing as error-free truth.

Evaluate joint predictions using held-out multi-site contrasts, regional count distributions, and simulation-based spatial variograms or multivariate scores. Compute aggregate means and intervals from coherent field draws with declared denominators. Do not add medians or assume independent cells. Full-field spectral comparisons belong to simulations or sufficiently dense independent evidence, not manufactured test maps.

### D. Make resolution a measured outcome

Define effective resolution as the smallest tested spatial scale at which a model recovers independent local contrasts with adequate calibration and predeclared error. Establish this with nested regional holdouts, paired nearby surveys, and simulated fields with known gradients. Plot error and calibration against both output-cell size and distance to independent training data.

Separate three numbers: covariate pixel size, computational evaluation grid, and validated genetic resolution. They need not match. A 30 m elevation raster cannot by itself substantiate a 30 m allele-frequency estimate. Test numerical consistency by predicting on increasingly fine meshes and comparing appropriately weighted aggregates, including antimeridian and polar cases.

Choose resolution promotion from training/development evidence, not from the held-out outcomes it will later be scored against. For area-average claims use area integration; for resident-frequency claims use supported population weights. Sampling footprints and demographic uncertainty place practical limits on the resolution claim.

Keep physical support fixed when refining a local kernel, and measure the resulting memory/runtime growth. Separately test retraining at each resolution and evaluating identical weights on a new resolution. The localized-operator paper explicitly reports resolution overfitting and task-dependent choices of differential layers (Appendix C.6); its native-grid winner need not transfer best.[^8] Compare actual independent fine-scale outcomes, not merely agreement between a model's own coarse and fine predictions.

### E. Test refusal and uncertainty honestly

Compare candidates on the same declared target regions. Report error on supported predictions, geographic/population coverage, failure rates, and risk-versus-coverage curves. A model cannot win by refusing only the hard cases while its competitor is scored everywhere. At deployment, an explicit pooled-frequency fallback can be evaluated as a policy alongside refusal, but must not masquerade as a validated spatial surface.

The existing `posterior_contraction` statistic has a Bayesian meaning. Do not populate it with ensemble disagreement from an unrelated model. A neural candidate either supplies a defensible prior/posterior comparison or requires an explicit, versioned support-contract extension. Until then it stays experimental. Preserve existing exclusions for `unknown` and `prior_dominated` artifacts.

All planned comparison folds must complete under a predeclared retry policy to substantiate an across-fold improvement claim. Nonconvergence, numerical errors, and absent data are reported as outcomes. Failed folds are not assigned invented numeric performance, and are not erased from the eligibility decision.

### F. Falsification and simulation

Build a simulator suite using documented demographic models plus spatial forward simulation where needed. stdpopsim supplies standardized demographic models; SLiM supports flexible forward and spatial/ecological experiments.[^48][^49] Simulations provide known truth, but validate a model only under the simulated mechanisms.

Include isolation by distance, sharp barriers, founder events, long-distance admixture, changes in population size, spatial selection, neutral variants, recombination, and extinct/unsampled sources. Add the actual observation process: unequal sample sizes, selective recruitment, duplicate studies, coordinate error, panel ascertainment, ancient DNA damage/missingness, and biased archaeological sampling.

Use simulator settings withheld from training, and deliberately misspecified mechanisms. A model trained on a particular simulator must not be crowned using only matching simulator tests. Compare to a second simulation family and independent empirical holdouts.

Negative controls include spatially structured but irrelevant covariates, appropriately blocked label/permutation controls, removed true predictors, geographic downsampling, coordinate perturbations, and withheld entire data sources. A detailed surface on a null spatial target should fail promotion. Deliberately introduced train/test overlap should trigger the split audit.

### G. Promotion rules

Before the expensive runs, preregister practical effect sizes and noninferiority margins using scientific needs and development-set precision. A reasonable *proposal* is at least a 5% reduction in region/variant-macro MAE against the strongest baseline, improvement in integrated predictive log score whose paired block-bootstrap interval excludes zero, and no material calibration or regional regression. Five percent is a planning target, not a literature-derived universal threshold; near-zero baseline errors require an absolute-error rule instead.

Use paired resampling at independent study/geographic and locus-block levels, accounting for crossed dependencies. Ten random seeds do not replace ten independent regions. Report uncertainty around calibration itself; a small subgroup may be insufficient to confirm or reject performance. If the available data cannot resolve the predeclared margin, the result is inconclusive.

Promotion also requires complete planned folds, preserved provenance, acceptable cost, and performance at matched coverage. A fine-resolution claim needs additional success on local contrasts; a worldwide claim needs validation outside the best-sampled regions. Per-variant or per-variant-family eligibility remains necessary even when a shared model wins on average.

HbS, G6PD, and carrier-screening gates remain in force for burden publication. Report the legacy parity criteria and any proposed corrected comparison side by side; do not silently rewrite acceptance. Compare matching interval levels and populations, and distinguish reproducing Piel from improving prediction on genuinely new surveys.[^27]

## 11. Concrete implementation roadmap

The sequence below specifies research deliverables, not a commitment to implement every candidate. Each stage ends with a decision based on its evidence. Engineering effort estimates would be misleading before a data inventory and timed baseline exist.

| Stage | Scientific objective | Component/interface | Acceptance evidence and stopping rule |
|---|---|---|---|
| 0. Inventory and target contract | Establish which resident/origin/time claims are identifiable | Versioned observation audit, source-dependency graph, target definitions | Counts of usable independent studies/populations/loci, metadata completeness, coverage by region/time, qualified source terms. Narrow unsupported claims. |
| 1. Benchmark foundation | Measure present skill without geographic, cohort, or locus leakage | Immutable split manifests; prediction and score tables; B0/B1/B2 runners | Reproduce current baseline metrics from recorded configuration, retain every failed fold, verify leakage controls, reserve external evidence. Advance #109/#110/#111/#127/#130 work. |
| 2. Observation and covariate pilot | Quantify gains from faithful measurement and simple information | Footprint likelihood and typed covariate adapter/store | Paired improvement for footprint/ascertainment handling and each small feature family; audit reference inference. Reject unhelpful layers. |
| 3. Shared structure | Improve sparse alleles through cross-locus information | Shared-factor fitter and cohort/locus manifest | Gains on held-out populations and whole loci; no collapse of uncommon or regional alleles. Builds on #128. |
| 4. Nonstationary connectivity | Represent local barriers and nonlocal similarity | Sparse graph/GMRF or nonstationary-GP fitter | Better regional/diaspora-track performance versus equally informed GP; uncertainty for learned edges. Builds on #129. |
| 5. Neural challenger | Test reusable nonlinear multiscale inference | Sparse-context spherical operator and probabilistic decoder | Same data/splits/tuning accounting as B3/B4; effective-resolution, joint-field, calibration, and cost checks. Stop if learning curves do not support benefit. |
| 6. LD and GPU spike | Determine whether linkage adds independent predictive information economically | Versioned locus/sample LD artifact and CPU/GPU comparator | Numerical equivalence under declared definitions, end-to-end speed benefit, conditional-imputation gains kept separate from geographic extrapolation. |
| 7. Temporal pilot | Determine whether ancient evidence improves modern inference and reconstruction | Ancient observation likelihood; temporal state-space fitter | Independent site/time holdouts, date/error sensitivity, neutral controls, and modern prediction ablation. P6 extension, aligned with #20. |
| 8. External confirmation and publication | Establish the final supported claim | Sealed evaluation report; immutable release manifest | Preregistered gains, calibrated uncertainty, truthful coverage/resolution, scientific gates, and expert review of population/measurement assumptions. |

### First experiment batch

Start with HbS, carefully distinguished G6PD measurement targets, and a stratified HLA allele subset containing both previously skillful and unskillful cases. Add qualified non-HLA loci as soon as their data meet the same contract; HLA alone cannot demonstrate genome-wide transfer. Use the genomic reference panel for a separate broad-locus experiment with its much smaller number of independent geographic populations.

For the first empirical batch, compare B0/B1/B2 on frozen five-fold geographic and whole-study splits where feasible. Then add footprint handling, a small terrain/water feature family, climate normals, and a locus-appropriate pathogen feature, one group at a time. Use three fixed stochastic seeds for exploratory repeatability; choose final replication counts from measured variance. Reserve the combined buffered study/geography and external tracks for stronger confirmation. Produce learning curves by independent population count and independent locus block count before scheduling a large neural run.

The data decision at the end is as important as the model decision: if uncertainty primarily reflects absent independent locations, prioritize targeted literature curation or new sampling partnerships. Evaluate acquisition strategies retrospectively by hiding regions and comparing uncertainty-driven selection, geographic diversity, and random acquisition. Keep prospectively acquired evaluation samples separate from samples adaptively chosen for training.

### Interfaces and versioning

Proposed narrow interfaces, to be refined in an implementation issue:

- `fit(training_observations, covariates, connectivity, config) -> FittedModel`
- `predict_latent(model, population_queries) -> JointFieldDraws`
- `predict_observations(model, survey_designs) -> PredictiveDistribution`
- `evaluate(predictions, heldout_observations, split_manifest) -> EvaluationReport`

These are design signatures, not existing APIs. The query contract must state population target, spatial support, and time. Covariates/connectivity enter explicitly; pure science modules do not fetch rasters or environment settings.

Keep current per-variant immutable artifacts, but record a **shared fit identifier** with hashes of the complete co-fitted variant set, observations, features, sample selection, training splits, code, and weights. Joint modeling does not inherently break immutability: a new joint fit publishes new versioned outputs, while old outputs remain unchanged. This addresses #128's dependency concern without prohibiting shared models. Joint covariance/draw identities must remain recoverable where P3 needs them.

Before implementation, attach the plan to the relevant existing issues and triage genuinely new work. The research program does not authorize silent schema changes, a new R dependency, live fitting, or replacement of published artifacts. GPU experiments should follow the project's existing US/Canada datacenter preferences and explicit reproducibility controls.

## Sources

The research cutoff is September 9, 2026. Sources below support the stated methods and candidate data availability, not an empirical claim that the proposed genomeOS system works. Provider pages are living documentation; pin exact releases and inspect contributing-file terms during acquisition. Full deployment data and numerical fits were not audited or rerun for this memo.

[^1]: Latent Space. [“We have foundation models for language, not for physics” — Anima Anandkumar](https://www.latent.space/p/anima). August 26, 2026. Timestamped episode transcript, passages listed above.
[^2]: Li et al. [Fourier Neural Operator for Parametric Partial Differential Equations](https://arxiv.org/abs/2010.08895). 2020 preprint; ICLR 2021.
[^3]: Kovachki et al. [Neural Operator: Learning Maps Between Function Spaces](https://arxiv.org/abs/2108.08481). 2021 preprint, subsequently revised; JMLR 2023.
[^4]: Guibas et al. [Adaptive Fourier Neural Operators: Efficient Token Mixers for Transformers](https://arxiv.org/abs/2111.13587). 2021/2022.
[^5]: Pathak et al. [FourCastNet: A Global Data-driven High-resolution Weather Model using Adaptive Fourier Neural Operators](https://arxiv.org/abs/2202.11214). 2022.
[^6]: Bonev et al. [Spherical Fourier Neural Operators: Learning Stable Dynamics on the Sphere](https://proceedings.mlr.press/v202/bonev23a.html). ICML 2023.
[^7]: Li et al. [Geometry-Informed Neural Operator for Large-Scale 3D PDEs](https://arxiv.org/abs/2309.00583). NeurIPS 2023.
[^8]: Liu-Schiaffini et al. [Neural Operators with Localized Integral and Differential Kernels](https://arxiv.org/abs/2402.16845). 2024.
[^9]: Bonev et al. [FourCastNet 3: A geometric approach to probabilistic machine-learning weather forecasting at scale](https://arxiv.org/html/2507.12144v1). 2025 preprint version consulted; particularly the probabilistic spatial/spectral objectives.
[^10]: Lam et al. [GraphCast: Learning skillful medium-range global weather forecasting](https://arxiv.org/abs/2212.12794). 2022/2023; Science 2023.
[^11]: Kochkov et al. [Neural general circulation models for weather and climate](https://www.nature.com/articles/s41586-024-07744-y). Nature, 2024.
[^12]: Price et al. [Probabilistic weather forecasting with machine learning](https://www.nature.com/articles/s41586-024-08252-9). Published online 2024; Nature 637, 2025.
[^13]: Gordon et al. [Convolutional Conditional Neural Processes](https://arxiv.org/abs/1910.13556). ICLR 2020.
[^14]: Yang et al. [A model-based approach for analysis of spatial structure in genetic data](https://pubmed.ncbi.nlm.nih.gov/22610118/). Nature Genetics, 2012.
[^15]: Battey, Ralph and Kern. [Predicting geographic location from genetic variation with deep neural networks](https://elifesciences.org/articles/54507). eLife, 2020.
[^16]: Bradburd, Ralph and Coop. [Disentangling the effects of geographic and ecological isolation on genetic differentiation](https://arxiv.org/abs/1302.3274). 2013.
[^17]: Bradburd, Coop and Ralph. [Inferring Continuous and Discrete Population Genetic Structure Across Space](https://pubmed.ncbi.nlm.nih.gov/30026187/). Genetics, 2018.
[^18]: Petkova, Novembre and Stephens. [Visualizing spatial population structure with estimated effective migration surfaces](https://pmc.ncbi.nlm.nih.gov/articles/PMC4696895/). Nature Genetics, 2016.
[^19]: Marcus et al. [Fast and flexible estimation of effective migration surfaces](https://elifesciences.org/articles/61927). eLife, 2021.
[^20]: Al-Asadi, Petkova, Stephens and Novembre. [Estimating recent migration and population-size surfaces](https://journals.plos.org/plosgenetics/article?id=10.1371/journal.pgen.1007908). PLOS Genetics, 2019.
[^21]: [Jointly representing long-range genetic similarity and spatially heterogeneous isolation-by-distance](https://journals.plos.org/plosgenetics/article?id=10.1371/journal.pgen.1011612). PLOS Genetics, 2025.
[^22]: Wohns et al. [A unified genealogy of modern and ancient genomes](https://pmc.ncbi.nlm.nih.gov/articles/PMC10027547/). Science, 2022.
[^23]: Vaughn and Nielsen. [Fast and Accurate Estimation of Selection Coefficients and Allele Histories from Ancient and Modern DNA](https://nielsen-lab.github.io/pdfs/papers/clues2.pdf). Molecular Biology and Evolution 41, msae156, 2024. [CLUES2 code](https://github.com/avaughn271/CLUES2).
[^24]: Akbari et al. [Ancient DNA reveals pervasive directional selection across West Eurasia](https://doi.org/10.1038/s41586-026-10358-1). Nature, 2026. Used as a recent regional methodological lead; no global extrapolation of its findings is assumed.
[^25]: Rasp et al. [WeatherBench 2: A benchmark for the next generation of data-driven global weather models](https://arxiv.org/abs/2308.15560). 2023/2024. [Evaluation/data documentation](https://weatherbench2.readthedocs.io/en/latest/data-guide.html).
[^26]: Roberts et al. [Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure](https://www.wsl.ch/lud/biodiversity_events/papers/Roberts_et_al-2017-Ecography.pdf). Ecography, 2017.
[^27]: genomeOS source snapshot `a071a7b`: `genomeos/surfaces/{fit,batch,mask}.py`, `genomeos/validation/crossval.py`, `docs/overview.md`, `docs/scientific-engineering-objectives.md`, and Atlas design §§4–8,12–13. Issue history: [#3 datasets](https://github.com/bschilder/genomeOS/issues/3), [#34 engine decision](https://github.com/bschilder/genomeOS/issues/34), [#92 parity semantics](https://github.com/bschilder/genomeOS/issues/92), [#111 failed folds](https://github.com/bschilder/genomeOS/issues/111), [#128 pooling](https://github.com/bschilder/genomeOS/issues/128), [#129 nonstationarity](https://github.com/bschilder/genomeOS/issues/129), [#130 spatial skill](https://github.com/bschilder/genomeOS/issues/130). Historical issue metrics are not fresh benchmark results.
[^28]: genomeOS. [Issue #66: recorded publication and redistribution decision](https://github.com/bschilder/genomeOS/issues/66). Closed; owner decision inspected September 9, 2026.
[^29]: Copernicus Data Space. [Copernicus DEM product description](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM), [DEM documentation](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM.html), and [July 2026 view-service access change](https://dataspace.copernicus.eu/news/2026-7-17-copernicus-dem-30m-view-service-license-acceptance). Product and service permissions must be distinguished.
[^30]: HydroSHEDS. [HydroATLAS](https://www.hydrosheds.org/hydroatlas). Product description, source components, and CC BY 4.0 terms.
[^31]: ESA WorldCover. [Data access](https://esa-worldcover.org/en/data-access). 2020/2021 products and attribution terms.
[^32]: ECMWF. [ERA5-Land](https://www.ecmwf.int/en/era5-land). Coverage, temporal frequency, and grid spacing.
[^33]: Karger et al. [CHELSA-TraCE21k – high-resolution (1 km) downscaled transient temperature and precipitation data since the Last Glacial Maximum](https://cp.copernicus.org/articles/19/439/2023/). Climate of the Past, 2023.
[^34]: WorldPop. [Choosing the right population data](https://www.worldpop.org/choosing-the-right-worldpop-population-data-for-you/) and [age/sex data categories](https://hub.worldpop.org/project/categories?id=8). Check individual product years and provenance before use.
[^35]: PBL Netherlands Environmental Assessment Agency. [New anthropogenic land use estimates for the Holocene; HYDE 3.2](https://www.pbl.nl/en/publications/new-anthropogenic-land-use-estimates-for-the-holocene-hyde-32). 2017.
[^36]: UN DESA. [International Migrant Stock](https://www.un.org/development/desa/pd/content/international-migrant-stock). 2024 edition and source documentation.
[^37]: Gaskin and Abel. [Deep learning four decades of human migration](https://www.nature.com/articles/s41586-026-10611-7). Nature, June 10, 2026. Annual 1990–2023 country/region migration estimates; [data, models, and ensemble](https://huggingface.co/datasets/ThGaskin/Migration_flows).
[^38]: UNHCR. [Refugee Data Finder: data content](https://popstats.unhcr.org/refugee-statistics/methodology/data-content/). Country/year and origin/asylum definitions.
[^39]: Malaria Atlas Project. [Data catalogue definitions](https://data.malariaatlas.org/about). Layer-specific coverage and metadata require acquisition review.
[^40]: GBIF. [Occurrence-data quality requirements](https://www.gbif.org/data-quality-requirements-occurrences) and [terms](https://www.gbif.org/terms). Dataset-specific licenses and observation semantics.
[^41]: UCDP. [Dataset download center](https://ucdp.uu.se/downloads/) and [API documentation](https://ucdp.uu.se/apidocs/). Versioned event data and current token requirement.
[^42]: Seshat. [Data](https://seshatdatabank.info/data), [Cliopatria spatial histories](https://seshat-db.com/core/cliopatria/), and [codebook](https://seshatdatabank.info/sitefiles/code-book-4.20.2021.pdf). Historical reconstructions with varying temporal/spatial support.
[^43]: SlaveVoyages. [Database downloads](https://legacy.slavevoyages.org/voyage/downloads) and [methodology](https://legacy.slavevoyages.org/blog/methodology-trans-atlantic). Voyage and route records; not a complete global history of forced migration.
[^44]: Cesium. [Content Usage and Attribution Guide](https://cesium.com/learn/ion/content-usage-and-attribution-guide/). Asset-specific attribution and links to third-party terms. Local integration inspected in `website/src/atlas/earth-style-catalog.ts`.
[^45]: CuGen developers. [CuGen repository and README](https://github.com/yuj1r0/cugen). Living implementation documentation; commit/version must be pinned for experiments.
[^46]: Kiiskinen et al. [CuGen: A GPU-accelerated framework for large-scale genomics](https://www.medrxiv.org/content/10.64898/2026.07.15.26358178v1.full). July 2026 preprint. Performance claims require replication on the intended workload.
[^47]: Mallick et al. [The Allen Ancient DNA Resource (AADR): a curated compendium of ancient human genomes](https://www.nature.com/articles/s41597-024-03031-7). Scientific Data 11, 182, 2024. Technical processing, pseudohaploid calls, dates, overlap, and sampling distribution.
[^48]: Population Simulation Consortium. [stdpopsim](https://github.com/popsim-consortium/stdpopsim). Standardized population-genetic models; pin catalog and simulator releases.
[^49]: Haller and Messer. [SLiM 4: Multispecies Eco-Evolutionary Modeling](https://benhaller.com/pubs/HallerMesser2023AmNat.pdf). American Naturalist, 2023; [current simulator documentation](https://messerlab.org/slim/).
[^50]: Rahman et al. [Pretraining Codomain Attention Neural Operators for Solving Multiphysics PDEs](https://papers.nips.cc/paper_files/paper/2024/file/bc75fa9843a7905bbed9d83895a88f7f-Paper-Conference.pdf). NeurIPS 2024. Main text and scientific appendices A–H read; particularly runtime Table 5 and joint-system Table 12.
[^51]: Azizzadenesheli et al. [Neural Operators for Accelerating Scientific Simulations and Design](https://arxiv.org/abs/2309.15325v5). January 2024 author version; full main text read.
[^52]: Kossaifi et al. [A Library for Learning Neural Operators](https://jmlr.org/papers/v27/26-0434.html). JMLR 27, June 2026; complete six-page paper read.

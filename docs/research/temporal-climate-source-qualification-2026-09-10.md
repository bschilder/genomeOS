# Temporal climate: source coverage and testable genetic questions

Status: `automated_proposal` / `pending`, 2026-09-10. Advances
[#189](https://github.com/bschilder/genomeOS/issues/189), WP3/WP7 and Atlas design
§§4–9,12. Companion to the [climate decoding note](climate-covariate-qualification-2026-09-10.md).
This is a research/source qualification proposal, not admission of climate data,
ancestral locations, a model or an allele-frequency performance claim.

## Scientific contract

Objective: determine whether dated environmental information improves withheld
allele-count prediction beyond eligible genetic, geographic, terrain and population
baselines. Present-day, historical and ancient climate remain separate research
tracks; ancient includes the full requested human/non-human-primate divergence
interval, without inventing one exact divergence date or replacing it with the LGM.

Output now: a source-to-question map and falsifiable evaluation sequence. Eventual
engineering interface: immutable offline feature artifacts carrying source identity,
space-time support, transformations, uncertainty and information-availability date.
Acceptance requires reproducible source decoding first, then matched out-of-sample
improvement with calibration and independent confirmation. The consumers are WP3
resident-frequency experiments and separately validated WP7 historical/origin models.

Refuse unsupported dates, missing paleolocations, fabricated continuity, unreviewed
reuse and observation-like presentation of reconstructed fields. Finer rendering
or downscaling is not evidence of finer genetic or historical resolution.

## Candidate coverage, not one continuous product

`ka` and `Ma` denote thousands and millions of years; each source's actual age
origin, calendar and slice definition still require explicit qualification.

| Candidate | Inspected temporal/spatial scope | First useful role and principal limitation |
|---|---|---|
| [ERA5 / ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview) | ERA5 1940–present, hourly, approximately 31 km native; Land 1950–present, approximately 9 km | Contemporary conditions/anomalies. Land is an ERA5-forced replay, not independent corroboration. Exact catalogue product, units and calendar must be pinned. |
| [20CRv3](https://www.psl.noaa.gov/data/gridded/data.20thC_ReanV3.html) | 1806–2015, 80-member reanalysis; commonly delivered at 1° | Open recent-historical bridge. Surface pressure is assimilated; temperature/precipitation are inferred. Treat 1806–1835 as experimental. |
| [ModE-RA v1](https://doi.org/10.26050/WDCC/ModE-RA_s14203-18501) | 1421–2008, monthly, 20 members, T63 approximately 1.8° | Historical anomalies and uncertainty. Sparse early areas approach the model prior; absolute precipitation can become negative. |
| [CHELSA-TraCE21k v1.0](https://doi.org/10.16904/envidat.211) | Approximately 21 ka–1990; centennial paleo windows; 30 arc-second land grid | Late-glacial/holocene sensitivity, not the full ancient interval. One downscaled transient climate simulation, not a multi-model ensemble. |
| [Beyer et al., corrected v4](https://doi.org/10.6084/m9.figshare.12293345.v4) | 120 ka–preindustrial, 72 climatological snapshots, 0.5° land grid | Longer discrete late-Quaternary comparison; single-model lineage and bias-correction assumptions remain. |
| [PALEO-PGEM-Series](https://zenodo.org/records/21327244) | 5 Ma–preindustrial, 1 kyr steps, 1° land grid | Dense modeled deep-time candidate within that interval. Fixed land–sea geography and emulator variability do not represent full climate/chronology uncertainty. |
| [PhanDA](https://doi.org/10.1126/science.adk3705) | 485 Ma reconstruction; 85 assimilated geological slices | Deep-time temperature context and sparse fields. Marine temperature evidence updates land temperature through model covariance; no continuous local or assimilated precipitation history. |
| [PMIP and related MIPs](https://pmip4.lsce.ipsl.fr/), including [DeepMIP-Eocene-p1 v1.0](https://doi.org/10.5285/95aa41439d564756950f89921b6ef215) | Experiment-specific snapshots or simulated intervals on model-specific grids | Multi-model sensitivity at supported ages, not observed historical weather. No family-wide calendar, coverage or terms assumption. |

Among these eight inspected families, none establishes continuous high-resolution
local climate across the entire requested divergence-to-present interval. That is
a bounded audit result, not proof that no other source exists. Preserve gaps and
source boundaries rather than stitching them into apparently observed history.

For comparison, LGM 21 ka is a potential CHELSA/Beyer/PMIP overlap. Beyer's oldest
120 ka slice and PMIP's `lig127k` experiment are **not the same age**, and CHELSA
does not reach either. Free-running PMIP `past1000` climate is not a reanalysis of
the actual sequence of weather. Regridding cannot remove those differences.

PhanDA's complete nine-page main article was inspected, including its methods and
figures. Geological stages are sometimes merged; the prior ensemble comes from
HadCM3L simulations, not independent climate models. Terrestrial temperatures
are not directly assimilated. Its methods supplement was not retrieved, and
posterior arrays, exact chronological treatment and filtering have not been
qualified here. Its [output README](https://github.com/EJJudd/PhanDA) distinguishes
temperature posteriors from climate-model priors. Do not relabel prior precipitation
as reconstructed precipitation or stage-scale temperatures as seasonal exposure.

## Three different candidate features

The following are modeling deductions from those evidence boundaries, not claims
made by the source papers or implemented features.

1. **Present-location environmental history.** Summarize climate over a declared
   interval at a reviewed geographic footprint, with time-appropriate coastline/
   land support. This asks whether environmental history of a place predicts its
   present allele frequency. It does not assert the sampled people's ancestors
   stayed there. Retain uniform-area versus population-weighted support sensitivity.
2. **Population-path exposure.** Integrate climate over an independently supported
   probability distribution of ancestral locations and dates. Migration histories,
   ancient samples and paleogeography are additional uncertain inputs, not implicit
   defaults. Marginalize their uncertainty jointly with climate uncertainty where
   a defensible joint model exists; report sensitivity where it does not. Without
   a qualified location/history model, this feature is unavailable.
3. **Evolutionary context.** A global temperature curve is identical for every
   present-day site under a common time window. By itself it adds no spatial
   discrimination. Variant-age, functional or lineage-specific interactions may
   create testable variation, but introduce additional assumptions and leakage
   risks. Do not assume every present variant existed throughout the ancient
   interval, or call a predictive climate association evidence of selection.

In a separately fitted per-variant spatial model, a site-constant climate summary
is absorbed by the variant intercept; even a variant-specific historical window
does not by itself identify geographic variation within that variant. Testing such
context across variants therefore requires a separately declared pooled prediction
task, not an extra column in the current per-variant model. Compare against a matched
baseline containing the same age/function/lineage main effects without climate,
and hold out whole variants and locus/LD dependency groups as well as geography.
All annotations must be externally frozen and independent of held-out counts.
A proposed spatial interaction instead needs qualified site-varying exposure and
its own matched main-effect baseline. Neither extension is admitted by this note.

Never infer ancestral paths, variant ages, LD structure or feature weights from
held-out allele counts and then treat those derived inputs as independent test
covariates. Fit permitted transformations only on training partitions, or use
genuinely external frozen information with its dependency and access date recorded.

## Smallest informative experiment sequence

First qualify a tiny public 20CRv3 subset and the proposed contemporary normal
assets: calendar, units, accumulation semantics, missingness, ensemble identity,
native grid and reproducible transformations. This ordinary public subset work
is within the existing research authorization; no new approval gate is added.
Source qualification must finish before those values enter a genetic benchmark.

Next compare historical anomaly summaries over actual overlapping source intervals,
keeping reference periods explicit. ModE-RA recommends anomalies rather than
unqualified absolute fields; source disagreements become a sensitivity analysis,
not an invitation to choose whichever feature scores best on the final holdout.
[ModE-RA usage notes](https://mode-ra.unibe.ch/).

For each admitted temporal track, freeze a baseline and one bounded feature family
on the same eligible outcome rows, folds and weights. Compare baseline, added
climate, missingness-only and spatially structured controls; retain failed folds,
coverage and prior-dominated exclusions. Report paired uncertainty, calibration,
regional and rare-allele strata. Feature-window and source selection use training/
development data only; independent final confirmation remains untouched.

Present-location history can enter WP3 without claiming reconstructed migration.
Population-path features wait for the WP7 history contract. Deep-time global
context does not receive automatic priority merely because it reaches further
back: test whether its specified interaction adds information beyond geography,
genomic structure and younger climate before expanding the model.

Use forward-time holdouts for information-cutoff prediction. Retrospective models
may use later reconstructions only under that explicit label, with independent
ancient sites/time windows held out. Neighboring years, related samples, shared
proxy/model inputs and linked loci are not independent replicates. Source agreement
and climate ensemble spread do not establish genetic predictive calibration.

## Reuse and inspection boundary

20CRv3's provider lists CC0; ModE-RA and Beyer v4 list CC BY 4.0. ERA5 access uses
CDS terms/account acceptance, which requires the correct authority rather than an
assumed new agreement. CHELSA-TraCE's current structured CC BY-SA 4.0 record differs
from its CC BY 2.0 prose/paper: retain the conflict and do not admit it silently.
The current PALEO-PGEM record lists version `v1`, CC BY 4.0 and file checksums;
equivalence to its earlier delivery was not tested. PhanDA prior terms do not
establish posterior-output terms; that output review remains `not_checked`.
MIP reuse can be file/model-specific and requires inspection of selected assets.

An absent named licence is not itself a restriction. A completed check with no
explicit restriction is `no_restriction_found`; an unperformed check remains
`not_checked`. No climate arrays, genetic features or derived surfaces are committed
by this note. Full method-text inspection covered 20CRv3, ERA5-Land, ModE-RA,
CHELSA-TraCE, Beyer, PALEO-PGEM and DeepMIP; PhanDA's main article was read separately
as described above. PlioMIP/MioMIP individual method papers and selected model-file
headers were not inspected. Article inspection never substitutes for asset-level
decoding, chronological, geographic or reuse qualification.

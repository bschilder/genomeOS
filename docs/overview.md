# genomeOS — project overview

*Explore the genome; worldwide.* 🧬🌍🧬

## 1. Why this project exists

Any two people's DNA differs in a few million places. Almost all of those differences do
nothing at all. A small number matter enormously: they cause a disease, or protect against one,
or change whether a particular medicine will work or cause harm.

**Those differences are not spread evenly around the world.** Human populations have moved,
mixed, and adapted to local conditions for tens of thousands of years, and their DNA carries
the record. A genetic change that is common in one region can be almost absent a thousand
kilometres away.

That fact has real consequences for real people. Here is the clearest example.

### One example, worked through

There is a single change in the gene for haemoglobin — the protein that carries oxygen in your
blood — called **HbS**, better known as the sickle-cell change.

Everyone carries two copies of most genes, one from each parent. If you inherit **one** copy of
HbS, you are healthy, and you are also substantially protected against severe malaria. That
protection is why the change became common in the first place: in places where malaria killed
large numbers of children, carrying one copy was an advantage. If you inherit **two** copies,
you have [sickle-cell anaemia](https://medlineplus.gov/genetics/condition/sickle-cell-disease/) —
a serious, lifelong, sometimes fatal condition.

So this one change produces a map. It is common in parts of sub-Saharan Africa, the
Mediterranean, the Middle East and India — the places where malaria was historically
widespread — and rare elsewhere. And the map has direct medical meaning: knowing how common the
change is in a given region tells health services roughly how many children will be born with
sickle-cell anaemia there, which tells them whether to run newborn screening, and how much
treatment capacity to plan for.

Somebody did build that map. A research team spent years assembling blood-survey data from
across the world, fitting a statistical model to estimate the frequency in places nobody had
surveyed, multiplying by local birth rates, and publishing the result — an estimate that around
**300,000 babies are born with sickle-cell anaemia each year**, broken down by country, with
honest error bars ([Piel et al., *The Lancet*,
2013](https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(12)61229-X/fulltext)).

That work is the model for this entire project. And it has been done properly for roughly
**two** genetic changes.

### The gap

There are thousands of other conditions caused by single genetic changes — [cystic
fibrosis](https://medlineplus.gov/genetics/condition/cystic-fibrosis/),
[Tay-Sachs](https://medlineplus.gov/genetics/condition/tay-sachs-disease/), the
[thalassaemias](https://medlineplus.gov/genetics/condition/beta-thalassemia/), [spinal muscular
atrophy](https://medlineplus.gov/genetics/condition/spinal-muscular-atrophy/), many others — plus
a large set of
changes that determine whether common drugs are safe or effective for you.

For almost all of them, **nobody can tell you how common they are where you live.** Not because
the data doesn't exist, but because:

1. **It is scattered** across dozens of databases, national programmes, and individual papers,
   in incompatible formats, with no common way to join them.
2. **The biggest datasets threw the geography away.** This is the crux of the whole project.
The largest open collection of human genetic variation,
[gnomAD](https://gnomad.broadinstitute.org/),
   covers over 800,000 people — and
   records their origins only as broad continental labels. You cannot put a continent on a map
   at any useful resolution. Meanwhile the datasets that *do* record where people came from are
   small, sometimes only a few hundred people.
3. **Producing an honest answer is genuinely hard.** Between two places where somebody actually
   measured, you have to estimate — and a coloured map is very good at looking confident about
   estimates that are, in truth, guesses.

So the answer to "how common is this condition among people from my region?" is usually: nobody
has worked that out, and finding out would be a multi-year research project.

**We think it should be a map you can open in a browser.**

### Why now

Three things changed. Enough open genetic data now exists to be worth joining up. The
statistical methods for building honest maps from sparse geographic measurements are settled
and published — the sickle-cell work used them, and so did decades of [malaria
mapping](https://malariaatlas.org/). And the
tools for serving big interactive maps cheaply are mature and mostly free.

What is missing is nobody has done the unglamorous connective work: giving every population in
every dataset a location, joining the sources, running the statistics once for many conditions
instead of once per PhD, and putting the result behind a map anyone can use.

## 2. What we are building

Two atlases of human genetic variation, and eventually a bridge between them.

### Map 1 — variation across the Earth

An interactive world map. Search for a genetic change, a gene, a condition, or a place, and see:

- **Where it was actually measured**, and how many people were sampled.
- **An estimate of how common it is everywhere else**, with an honest statement of how confident
  that estimate is — and, crucially, **a clear marking of everywhere we simply don't know**.
- **What it means for people** — roughly how many carriers and how many affected individuals
  that implies, given how many people live there.
- **What else it is associated with** — the conditions and traits linked to it, and the other
  genetic changes it tends to travel with, always with the evidence attached.

Plus something nobody has built: **a time slider.** Thousands of ancient human genomes have now
been sequenced
([AADR](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/FFIDCW)),
most with a known location and a known date. That makes it possible to show how
a genetic change spread across a continent over the last ten thousand years, and to press play.

### Map 2 — the genome inside the cell

Your DNA is about two metres long and folded into a nucleus a few thousandths of a millimetre
across. That folding is not random, and it matters: which stretches of DNA end up physically
touching determines which genes get switched on. The second atlas maps this — zoom from the
whole nucleus, into a single chromosome's territory, into folded domains and loops, down to an
individual gene.

### The bridge between them

This is the long-term payoff. Find a gene, see where it sits on its chromosome and how that
region is folded in three dimensions, then step outward to the world map to see which variants
in that gene exist, where they are common, and what they do — without leaving the system. Both
halves exist separately in the world today. The connection does not.

### What people could do with it

From [Discussion #1](https://github.com/bschilder/genomeOS/discussions/1):

| Who | What they get |
|---|---|
| **Anyone curious** | What genetic variants are common where my family comes from, and what do they actually do? Population genetics, made directly explorable instead of locked in papers. |
| **Patients and families** | Context for a diagnosis: how common is this, where, and who else is affected. |
| **Drug developers** | Naturally occurring *protective* variants are among the best therapeutic targets there are — several major drug classes came from exactly that observation. This makes them findable, and shows where the populations to study them live. |
| **Researchers** | Move from a variant to its associated variants, traits, and distributions, generating hypotheses about gene function and natural selection. |
| **Health agencies and governments** | Evidence for which screening programmes are worth running for their population, and where to direct resources. |
| **Sequencing programmes** | **See where the world's genetic data is missing.** A map of what we don't know is a map of where to look next — which is why marking the gaps is a headline feature here, not an apology. |

### What success looks like

We are not aiming to produce a plausible-looking map. The test we set ourselves is
**reproduction of published science**: our pipeline must independently arrive at the same
sickle-cell numbers that the *Lancet* paper did, and the same numbers for a second condition
([G6PD
deficiency](https://medlineplus.gov/genetics/condition/glucose-6-phosphate-dehydrogenase-deficiency/),
a genetic trait affecting hundreds of millions of people that makes certain common drugs
dangerous — mapped by [Howes et al., *PLoS
Medicine*, 2012](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1001339)),
and it must recover carrier rates for conditions like cystic fibrosis
that national screening programmes have already measured directly.

If we cannot reproduce results that are already known to be right, we have not earned the right
to publish results that aren't yet known. That is the bar, and it is written into the plan as a
blocking test rather than a hope.

## 3. What makes this hard, and the rules we adopted

This project could be done badly, and doing it badly would be worse than not doing it. It is
worth understanding why before you contribute, because these constraints shape almost every
technical decision that follows.

### The three traps

**1. A smooth map is a persuasive liar.** If you measure allele frequency in two cities and
colour in everything between them, you get a beautiful gradient. It looks like a finding. It may
be pure arithmetic. This isn't hypothetical — a [landmark 2008
paper](https://stephenslab.uchicago.edu/assets/papers/Novembre2008b.pdf) showed that the sweeping
gradient maps used for decades as evidence of ancient human migrations can arise with **no
migration event at all**, and that the interpolation used to draw them can manufacture the very
pattern they were taken as evidence for.

**2. Most genetic research has studied European populations, and scores don't transfer.**
Predictors built from studies of European-ancestry participants [lose much of their accuracy when
applied to anyone else](https://www.medrxiv.org/content/10.1101/2024.06.13.24308905v1). Draw a
world map of such a score and you have largely drawn a map of
*where geneticists have done their sampling* — while it looks like a map of risk. Worse, the
differences between groups on such a map cannot be cleanly separated into real biology versus
statistical artefact. The single most eye-catching feature of such a map — which country ranks
highest — is the least trustworthy number on it.

**3. The reference datasets are deliberately missing the very people you'd want to count.** The
largest variant database ([gnomAD](https://gnomad.broadinstitute.org/)) excludes people with
severe childhood genetic disease *and their close
relatives*, by design, because it was built to be a comparison baseline for diagnosing patients.
Use it naively to ask "how common is this severe childhood disease variant?" and it will
under-report, sometimes badly. Separately, the catalogues of known disease variants
([ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/)) reflect *who has access to genetic testing* — a
variant common in West Africa may simply have no entry,
because nobody was ever tested for it.

And a fourth, which is not a statistical problem but a human one: **a colour-coded world map of
"genetic disease burden" by country or ethnic group is one of the most misusable objects you
could build in this field.** For a project that intends to be public and to accept
contributions worldwide, that has to be a design input from day one, not a disclaimer added at
the end.

### The rules that follow

None of this is a reason not to build it. It is a reason to build it with specific properties
baked in so deeply that they cannot be accidentally removed. Six rules — and in the code, these
are treated as **invariants**, meaning breaking one is a bug, not a matter of taste:

1. **What was measured and what was estimated are never mixed.** They live in separate tables,
   render as separate layers, and carry separate provenance. The interface cannot blend them,
   and no amount of clicking will get you a view where you can't tell which is which.
2. **Every map must show where it doesn't know.** Areas with no nearby measurement are drawn as
   *unknown* — visibly hatched, never smoothly shaded toward zero. Areas where the statistics
   couldn't extract a real signal are marked separately as such. This layer is on by default and
   turning it off takes a deliberate click. When you ask for a summary of a region, the answer
   tells you what fraction of that region is unmapped.
3. **Zooming in never invents detail.** Resolution is determined by how much real data supports a
   given area, not by how far you've zoomed. Zoom past the data and you don't get a
   finer-grained guess — you see the gaps appear.
4. **Corrections for biased sampling are visible, measured numbers** — recorded alongside every
   result, not hidden adjustments buried in code.
5. **We start where the science is settled.** Version 1 covers only conditions caused by single
   genetic changes with well-understood inheritance, plus drug-response variants with formal
   clinical guidelines. The complicated, poorly-transferable, many-genes-at-once predictors are
   excluded for now — and traits relating to behaviour, cognition, or physical appearance are
   excluded on purpose and permanently for burden mapping. That restriction is enforced by the
   server, for every request from anyone, rather than being a policy someone might forget.
6. **When the data won't support a number, we publish no number** and say why. A missing answer
   is a valid, deliberate output.

There is also a governance dimension. Several of the best datasets with real geographic detail
come from indigenous populations, whose data is governed by the [CARE
Principles](https://www.gida-global.org/careprinciples) — a framework asserting that the
communities a dataset came from have a continuing say in how it is used. Every population entry
in our registry carries provenance and a place to record those terms, and whether our derived
maps can be redistributed at all is an open question we intend to answer in writing before
going further ([#66](https://github.com/bschilder/genomeOS/issues/66)).

## 4. How it works, in outline

Five steps, each a separate piece of the project you could work on independently:

| | Step | In plain terms |
|---|---|---|
| **P0** | **Population registry** | Give every population in every dataset a location — latitude, longitude, *how uncertain that location is*, and where the coordinate came from. Sounds mundane; it is the single thing blocking everything else, and nobody has published it. |
| **P1** | **Observations** | Assemble the actual measurements: for this genetic change, in this population, at this place, this many copies were seen out of this many chromosomes tested. Plus — critically — *how* those people were recruited, because that determines what biases need correcting. |
| **P2** | **Surfaces** | Fit a statistical model that estimates frequency continuously across the globe, and — the whole point — reports how uncertain it is everywhere, plus where it has no business estimating at all. |
| **P3** | **Burden** | Turn frequency into people: combine with how many people live in each area and how likely the condition is to actually manifest, carrying the uncertainty all the way through so the final numbers have honest error bars. |
| **P4 / P5** | **API and map** | Serve the precomputed results fast and cheap, and render them in a browser. No science happens here — the API reads finished results, and the map draws them. Every view is shareable as a link. |

Two structural choices are worth knowing even at this level:

- **All the science happens offline, in advance.** Nothing is computed while you're looking at
  the map. That's what makes it fast and nearly free to run — and it means the science can be
  tested against published numbers in isolation, which is what makes the "reproduce the *Lancet*
  paper" test possible at all.
- **Results are immutable and versioned.** Improving the model publishes a *new* map; it never
  silently changes a map somebody has already cited. Every view is citable at a fixed version.

---

*Everything above is the whole picture. Below is the detail — read the section relevant to what
you want to work on, and see §9 for a glossary.*

---

## 5. The data, and the tension that shapes every design decision

[Issue #3](https://github.com/bschilder/genomeOS/issues/3) scores every candidate dataset on
three axes, 1–5, and is the upstream document for the entire design:

- **C — Comprehensiveness**: variants × individuals × ancestry breadth.
- **A — Accessibility**: 5 = open bulk download, no auth; 3 = browser/API or registration;
  1 = proprietary.
- **G — Geographic precision**: 5 = per-individual coordinates; 4 = population sampling
  coordinates; 3 = subnational region; 2 = country; 1 = continental ancestry label only
  (**unmappable**).

> **The core data problem:** the most comprehensive resources have the *worst* geographic
> precision, and vice versa. gnomAD v4 is **C5 / A5 / G1** — 730,947 exomes plus 76,215 genomes,
> and not one usable coordinate. HGDP is **C2 / G4** — 929 individuals with real coordinates.
> **There is no dataset that is both.** Every design decision downstream flows from this tension.

That sentence is why this project has a sub-project devoted to *coordinates* before it has one
line of mapping code.

### What each class of source is for

| Class | Role in the system | Anchors |
|---|---|---|
| **A. Georeferenced population panels** | **The geographic backbone** — the only sources that can place an allele count somewhere | **[gnomAD HGDP+1KG harmonized callset](https://genome.cshlp.org/content/34/5/796)** (C3/A5/G4; 4,094 genomes, 80 populations, 153M variants, CC0, already on GCP) is the best single starting point: the only open resource that is simultaneously WGS-depth *and* georeferenceable. **[HGDP](https://www.internationalgenome.org/data-portal/data-collection/hgdp)** is the original coordinate set. **[AADR v66](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/FFIDCW)** is the only G5 source — per-individual lat/long *plus dates* — and therefore the only path to a time axis. **[AFND](http://www.allelefrequencies.net/)** covers 1,324 populations (HLA/KIR only, but the deepest georeferenced frequency data per locus anywhere; [paper](https://pubmed.ncbi.nlm.nih.gov/31722398/), [scraped mirror](https://github.com/slowkow/allelefrequencies)). **[GAsP](https://www.nature.com/articles/s41586-019-1793-z)** gives 219 Asian populations. **[PGG.SNV](https://pmc.ncbi.nlm.nih.gov/articles/PMC6805450/)** is C5 with 977 populations but A2 — browser-only, so bulk access is an outreach ask. |
| **B. Large aggregate resources** | **Variant context** — indispensable for what a variant *is*, useless for geography alone | **[gnomAD v4](https://gnomad.broadinstitute.org/news/2023-11-gnomad-v4-0/)** ([CC0](https://gnomad.broadinstitute.org/policies); note bundled SpliceAI annotations are CC BY-NC), **[NCBI ALFA](https://www.ncbi.nlm.nih.gov/snp/docs/gsr/alfa/)** (904M variants, 316M novel to [dbSNP](https://www.ncbi.nlm.nih.gov/snp/) — underused), [TOPMed/BRAVO](https://bravo.sph.umich.edu/), [Ensembl](https://www.ensembl.org/). **[All of Us](https://www.researchallofus.org/)** is deliberately diverse with 3-digit-ZIP geography, but data cannot leave its Researcher Workbench — **it can inform models and can never be served by our backend.** |
| **C. National / regional programmes** | **Filling specific geographic holes**, mostly under controlled access | **[UK Biobank](https://www.ukbiobank.ac.uk/)** holds birth coordinates, and IBD [localises birth to a median 45 km](https://www.nature.com/articles/s41467-020-19588-x) — the single best proof that fine-scale geographic genetics is real, *and* a warning: [birth location correlates with BMI, hypertension and lung function even after PC adjustment](https://www.nature.com/articles/s41467-018-08219-1). **[MCPS](https://www.nature.com/articles/s41586-023-06595-3)** exposes 142M variants through a public browser and is massively under-exploited for Latin American coverage. **[GenomeIndia](https://genomeindia.in/)** (99 populations), [IndiGen](https://academic.oup.com/nar/article/49/D1/D1225/5943190), [FinnGen](https://www.finngen.fi/en) (founder-effect validation), [H3Africa](https://h3africa.org/). |
| **D. Primary publications and curated compilations** | **Expanding beyond fixed panels and locus-specific databases** while preserving each independently sampled measurement | PubMed discovery manifests retain every candidate and screening decision. The [literature evidence contract](literature-evidence-curation.md) stores exact counts or honest intervals, allele orientation, sample/cohort identity, ascertainment, exact table/figure/dataset location, independent verification, and checked reuse terms. Only complete reviewed records resolve through P0 into P1; unresolved evidence remains valuable staging data. The commit-pinned LCT/MCM6 rs4988235 pilot reconciles 426 source rows, but it is an audit inventory—not 426 promoted observations. HBB and G6PD are the next round-trip corpora. |
| **E. Direct-to-consumer** | **The highest geographic precision on Earth — and closed** | [23andMe](https://pubmed.ncbi.nlm.nih.gov/25529636/) (>12M) and [AncestryDNA](https://www.nature.com/articles/ncomms14238) (>20M) are C5/G5/A1. Published work is *ancestry proportions* by state, never allele frequency by location. The concrete ask is drafted in #3 and tracked as [#68](https://github.com/bschilder/genomeOS/issues/68): *k*-anonymised AF for a curated variant list binned to 3-digit ZIP, **or** — easier for a privacy team to defend and exactly what our renderer consumes — a fitted surface with posteriors and no counts at all. |
| **F. Trait and effect-size layers** | **What turns a frequency into a statement about a phenotype** | **[PanUKBB](https://pan.ukbb.broadinstitute.org/)** — multi-ancestry summary statistics, and the cleanest way to quantify PRS portability loss and render it as uncertainty. This is what the shipped `genomeos/` service serves. **[PGS Catalog](https://www.pgscatalog.org/) + [`pgsc_calc`](https://github.com/PGScatalog/pgsc_calc)** is a non-negotiable dependency: score normalisation is the only principled way to render PRS across populations. **[Open Targets](https://platform.opentargets.org/)** — fine-mapped credible sets are the right unit, not raw GWAS hits. **[GWAS Catalog](https://www.ebi.ac.uk/gwas/)** ancestry metadata makes *"how European is the evidence for this trait?"* a renderable map layer — a powerful honesty feature. **[CPIC](https://cpicpgx.org/) / [PharmGKB](https://www.pharmgkb.org/) / [PharmVar](https://www.pharmvar.org/)** already tabulate PGx frequencies by biogeographic group: the most clinically actionable and least ethically fraught layer available, and a strong flagship-demo candidate. Plus **[EFO](https://www.ebi.ac.uk/efo/)/[MONDO](https://mondo.monarchinitiative.org/)** as the ontology backbone, and **[GBMI](https://www.globalbiobankmeta.org/)**. |
| **G. Burden and denominator layers** | **What earns the word "burden"** | **[WorldPop](https://www.worldpop.org/) / [GPWv4](https://www.earthdata.nasa.gov/data/projects/gpw)** gridded population ([also on Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/CIESIN_GPWv411_GPW_Population_Density)) (100 m / ~1 km) is both the per-capita denominator and the multiplier that converts a frequency surface into expected case counts. **[GBD 2023](https://www.healthdata.org/data-tools-practices/interactive-visuals/gbd-results)** (375 diseases, 204 countries + 660 subnational locations) is the validation ground truth and the UX benchmark. **[GADM](https://gadm.org/) / [Natural Earth](https://www.naturalearthdata.com/)** for admin aggregation. **[Orphadata](http://www.orphadata.org/)** gives prevalence for 6,172 rare diseases annotated by geographic area *and by founder population* — the natural partner to a carrier-frequency map. **[Glottolog](https://glottolog.org/) / [D-PLACE](https://d-place.org/)** are unglamorous and essential: they are how population *labels* become coordinates. |
| **H. Synthetic and internal** | **Testing before real data lands** | [HAPNEST](https://www.ebi.ac.uk/biostudies/studies/S-BSST936) for backend load-testing; [`bioDB`](https://github.com/standardmodelbio/bioDB) for bulk pulls; [`synthlab`](https://github.com/bschilder/synthlab). |

### The five recommendations, and where each one landed

Issue #3 closes with five recommendations. Every one is now a structural feature of the design —
the clearest illustration of how this project works:

1. **Build on the gnomAD HGDP+1KG harmonized callset.** → the first observations adapter
   ([#25](https://github.com/bschilder/genomeOS/issues/25)).
2. **The binding constraint is coordinates, not variants** — so build a population geolocation
   registry with provenance, a sampling-vs-ancestral flag, and an explicit uncertainty radius.
   Nobody has published this; it is independently publishable. → **became sub-project P0**, and
   is publishable as a standalone citable dataset
   ([#23](https://github.com/bschilder/genomeOS/issues/23)).
3. **Separate observations from surfaces in the data model, permanently** — cheap at
   schema-design time, impossible to retrofit. → invariant 1 in §3.
4. **Validate against HbS/G6PD before anything else.** → **HbS parity is the definition of done
   for v1** ([#45](https://github.com/bschilder/genomeOS/issues/45)).
5. **Two outreach asks worth making now** — PGG.SNV bulk access and the 23andMe fitted-surface
   proposal → [#67](https://github.com/bschilder/genomeOS/issues/67),
   [#68](https://github.com/bschilder/genomeOS/issues/68).

The scores in #3 are explicitly "a first pass and deliberately arguable — please edit them
directly." Stated weak spots: national biobank AF browsers outside the Anglophone literature,
and Latin American / Oceanian / Central Asian coverage. **Correcting them is a real
contribution.**

## 6. Architecture and sub-project goals

```
sources: gnomAD HGDP+1KG · AFND · AADR · MAP HbS/G6PD surveys · GAsP · MCPS · IndiGen
   ▼
[P0] population geolocation registry — coordinates + uncertainty radius + provenance
   ▼
[P1] observations (parquet on GCS)                           ← "what was measured"
   ▼  BigQuery batch: per-variant INLA-SPDE fit
[P2] surfaces: posterior mean + sd + data-support mask, H3-keyed   ← "what was inferred"
   ▼  × gridded population × penetrance, via posterior draws
[P3] burden: expected cases, mean + 95% CI, H3-keyed
   ▼
[P4] Cloud Run + DuckDB read API ──────────► [P5] Next.js + deck.gl client
       search · region aggregation · stats        map · layers · legend · lasso
       (no inference on this path)                (no genetics in this layer)
```

The batch tier runs on [BigQuery](https://cloud.google.com/bigquery) with artifacts on
[GCS](https://cloud.google.com/storage); the read tier is [Cloud Run](https://cloud.google.com/run)
+ [DuckDB](https://duckdb.org/) over [Parquet](https://parquet.apache.org/), indexed by
[H3](https://h3geo.org/); the client is [Next.js](https://nextjs.org/) with
[deck.gl](https://deck.gl/) over [MapLibre GL](https://maplibre.org/).

**Boundary rules that make this maintainable:** P2 and P3 are pure offline functions,
deterministic given `(config, data_version, seed)` — all science lives there, and both are unit
-testable against published numbers. The serving path performs no inference. Artifacts are
immutable, keyed by `(variant_id, model_version, data_version)`. The client contains no
genetics: every number on screen came from an artifact or an aggregation endpoint.

| | Goal — done when |
|---|---|
| **P0 registry** ([#7](https://github.com/bschilder/genomeOS/issues/7)) | Every population label across the Tier-A sources resolves to coordinates + uncertainty radius + provenance; validation passes; the registry is versioned and published |
| **P1 observations** ([#8](https://github.com/bschilder/genomeOS/issues/8)) | Observations built from all Tier-A sources, **every row carrying `sampling_design` and `cohort_id`**; disease-variant sets ascertained outside Western clinical genetics ingested; clinical-testing-intensity layer built; curated variant set defined and frozen |
| **P2 surfaces** ([#9](https://github.com/bschilder/genomeOS/issues/9)) | HbS and G6PD surfaces reproduce their published frequency maps; resolution-promotion and posterior-contraction thresholds calibrated; full curated set fitted, with the `prior_dominated` fraction reported per variant |
| **P3 burden** ([#10](https://github.com/bschilder/genomeOS/issues/10)) | **HbS parity** — our national estimate inside the published interval for ≥80% of countries and overlapping intervals for ≥95%; G6PD parity (X-linked); carrier-screening parity; every refusal condition verified by test |
| **P4 backend** ([#11](https://github.com/bschilder/genomeOS/issues/11)) | All endpoints serve p95 <150 ms warm and <500 ms cache-cold at H3 res 4; `/aggregate` returns the unmapped fraction; batch orchestration reproducible from a clean project |
| **P5 map UI** ([#12](https://github.com/bschilder/genomeOS/issues/12)) | All layers render; lasso aggregation works; every view is URL-round-trippable; the data-support mask is on by default |

The three golden tests are [#45](https://github.com/bschilder/genomeOS/issues/45) (HbS parity),
[#46](https://github.com/bschilder/genomeOS/issues/46) (G6PD, which exercises X-linked
inheritance), and [#47](https://github.com/bschilder/genomeOS/issues/47) (carrier-screening
parity — **the only test that validates the ascertainment correction at all**). Failing them
blocks publication of any other variant's burden layer.

### Milestones

| Milestone | Covers | The question it answers |
|---|---|---|
| **M1 — Data foundation** | P0 + P1 (22 issues) | Does every observation have a coordinate and a known ascertainment design? |
| **M2 — HbS parity** | P2 + P3 (17 issues) | Can we reproduce Piel et al.'s published national estimates? |
| **M3 — Map mode** | P4 + P5 (18 issues) | Can someone open a browser and use it? |
| **M4 — Public launch** | governance + outreach (6 issues) | Is it safe and legible to open to outside contributors? |

Priority is derived from the **dependency graph**, not enthusiasm: `critical` means it blocks
other work or *is* the definition of done. Twelve issues are critical — including the registry
schema (blocks every P0 adapter), the MAP survey adapter (without it `β_design` is
unidentifiable, so P2 cannot start), and golden test 1.

### The Pan-UKB evidence slice

The working service in `genomeos/` implements the **trait and effect-size layer** (category E
above): a provenance-first API over Pan-UK Biobank metadata and selectively indexed
ancestry-stratified GWAS associations. Full summary statistics stay in public object storage and
are queried by genomic region through a [Tabix](https://www.htslib.org/doc/tabix.html) boundary —
deliberately avoiding flattening ~7,228
phenotypes × 29M variants into hundreds of billions of rows.

Milestones from [`panukb-architecture.md`](panukb-architecture.md): manifest ingestion and
phenotype catalog → strict association parser with explicit p-value semantics → selective
significant-association indexes → Tabix region adapter → GCP deployment → async Hail jobs and
versioned ontology mappings → Open Targets reconciliation. The first four are implemented (the
region adapter behind the `PANUKB_REGION_QUERY_ENABLED` flag, with a row cap); the [Cloud
Run](https://cloud.google.com/run) +
[Cloud SQL](https://cloud.google.com/sql) path is defined in
[`deployment-gcp.md`](deployment-gcp.md).

Three source-semantics traps before touching this code: phenotype identity is a five-part key
(`trait_type + phenocode + pheno_sex + coding + modifier`); Pan-UKB documentation contradicts
itself about whether files carry `ln(p)` or `-log10(p)`, so importers infer encoding only from
unambiguous column names and **fail closed** otherwise; and AFR/AMR/CSA/EAS/EUR/MID are
genetic-analysis groupings, not race, ethnicity, nationality, or geography.

### Explicitly deferred

Named so their absence is a decision rather than an omission: time-sliced ancient-DNA surfaces
(P6), Globe mode (P7), semantic trait search and polygenic layers (P8), Chromosome mode (P9),
Chromatin mode (P10), individual-genome upload (P11), the conversational analysis agent (P12),
and real-time surface fitting (never — all inference is offline and batch, by design).

Three boundaries for the eventual agent are fixed *now*, because retrofitting them is expensive:
its only tool surface is the read API (so it inherits every refusal automatically),
variant-class policy is enforced in the API rather than in a system prompt, and any layer it
composes is a versioned, citable artifact.

## 7. Where things stand

- **Atlas:** Plan 1's P0/P1 foundation has landed: strict registry and observations schemas,
  HGDP, gnomAD HGDP+1KG, and MAP survey adapters, H3 indexing, partitioned Parquet storage, and
  frozen contracts. Remaining work and current status are tracked in the issue board.
- - **Pan-UKB API:** running, with tests and a [Cloud Run](https://cloud.google.com/run)
  deployment manifest.
- **Open questions with named next steps** (spec §14): a written position on redistributing
  derived surfaces from indigenous-population panels
  ([#66](https://github.com/bschilder/genomeOS/issues/66), `needs-human-decision`); a
  consanguinity-coefficient source; PGG.SNV bulk access
  ([#67](https://github.com/bschilder/genomeOS/issues/67) — 977 populations, the largest free
  coverage gain available); the 23andMe fitted-surface proposal
  ([#68](https://github.com/bschilder/genomeOS/issues/68)).
- `CONTRIBUTING.md`, a code of conduct, and issue templates are themselves an open issue
  ([#65](https://github.com/bschilder/genomeOS/issues/65)). Until they land, this document is the
  contributor guide.

## 8. How to contribute

**Start here:** introduce yourself in
[Discussion #76](https://github.com/bschilder/genomeOS/discussions/76) — your name, where in the
world you are, your background, and what you'd like to contribute (code, data, compute,
connections, or ideas). All levels of experience are welcome; the sections above are written so
that no part of this project requires you to already be an expert in the others.

**Reading order:** this document → the [scored dataset assessment
(#3)](https://github.com/bschilder/genomeOS/issues/3) → the [design
spec](superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md) → the [prior-art review
(#4)](https://github.com/bschilder/genomeOS/discussions/4) → the plan for your sub-project.

**Find work** on the [project board](https://github.com/users/bschilder/projects/8). Conventions
live in [`board-conventions.md`](board-conventions.md); the short version:

- Every issue carries a `type:*`, a `P*:` sub-project, a `skill:*`, and a `priority:*` label.
- **Filter by `skill:*` to find what you can actually do** — `spatial-stats`, `popgen`,
  `clinical-genetics`, `data-engineering`, `frontend`, `geospatial`, `governance`,
  `partnerships`.
- **Status `Ready` means fully specified and unblocked — pick it up without asking.**

Three labels describe *what kind of help* an issue needs — the fastest way to find where you are
most useful:

| Label | Meaning |
|---|---|
| `wants-expert-review` | An agent implements it; a domain expert reviewing afterwards materially lowers the risk. **This is the highest-leverage way for a specialist to contribute** — you do not have to write the code to make the difference. Currently on the surface-fitting model, its hyperpriors, the inference-runtime decision, the curated variant set, and the penetrance table. |
| `needs-recruiting` | Would benefit from a dedicated collaborator, but does not gate the work. |
| `needs-human-decision` | Requires a person to commit on the project's behalf — a judgement call, not a skills gap. |

Shortest paths to something load-bearing:

- **Spatial statistics / geostatistics** — [#34](https://github.com/bschilder/genomeOS/issues/34)
(the INLA-SPDE runtime decision, which blocks all of P2, since [R-INLA](https://www.r-inla.org/)
is R-only),
  [#35](https://github.com/bschilder/genomeOS/issues/35) (the binomial-GP fit with ascertainment
  offsets), [#36](https://github.com/bschilder/genomeOS/issues/36).
- **Clinical genetics** — [#32](https://github.com/bschilder/genomeOS/issues/32) (which ClinVar
  P/LP variants have defensible penetrance) and
  [#42](https://github.com/bschilder/genomeOS/issues/42) (the penetrance table). These gate P2
  and P3 respectively.
- **Population genetics / data engineering** — the M1 adapters:
  [#15](https://github.com/bschilder/genomeOS/issues/15) (HGDP, the reference adapter),
  [#25](https://github.com/bschilder/genomeOS/issues/25) (gnomAD HGDP+1KG),
  [#26](https://github.com/bschilder/genomeOS/issues/26) (MAP HbS/G6PD surveys — critical,
  because it is what identifies `β_design`),
  [#18](https://github.com/bschilder/genomeOS/issues/18) (AFND, 1,324 populations),
  [#20](https://github.com/bschilder/genomeOS/issues/20) (AADR, and with it the time axis).
- - **Frontend / geospatial** — [#55](https://github.com/bschilder/genomeOS/issues/55)
  ([Next.js](https://nextjs.org/) 16
  + [deck.gl](https://deck.gl/) + [MapLibre](https://maplibre.org/) scaffold) onward, and
  [#27](https://github.com/bschilder/genomeOS/issues/27) (the H3 resolution ladder).
- **Governance** — [#66](https://github.com/bschilder/genomeOS/issues/66),
  [#22](https://github.com/bschilder/genomeOS/issues/22) (CARE-aligned biocultural notices).
- **Partnerships** — [#67](https://github.com/bschilder/genomeOS/issues/67),
  [#68](https://github.com/bschilder/genomeOS/issues/68).
- **No genetics background?** There is real work in the frontend, the API, the data pipeline,
  documentation, and governance that needs no genetics at all. And if a section of this document
  was hard to follow, saying so in an issue is a genuine contribution — the project needs to be
  legible to outside contributors ([#65](https://github.com/bschilder/genomeOS/issues/65)).
- **Know a dataset we've missed, or think a score in #3 is wrong?** Edit it directly.

**Conventions when writing code:**

- Science lives in pure, offline, deterministic functions — no HTTP or I/O dependency — so it
  unit-tests directly against published numbers. Thin wrappers do the serving.
- Module docstrings cite the spec section they implement, e.g. `design §7.1`.
- The schema is the contract, validated on ingest and frozen into `contract/` so drift shows up
  in diffs. **Validation failures are hard errors, never dropped rows** — a population label
  with no coordinate must fail the build loudly.
- Artifacts are immutable and keyed by `(variant_id, model_version, data_version)`.
- Respect each source's access terms: some data (notably All of Us) may inform models but may
  never be served by our backend, and redistribution of derived surfaces from
  indigenous-population panels is an open question
  ([#66](https://github.com/bschilder/genomeOS/issues/66)). A source with no named licence is not
  automatically restricted, but its checked surfaces and lack of explicit restrictions must be
  logged before promotion.
- Coordinates are WGS84 decimal degrees; variant IDs are `chr-pos-ref-alt` on
  [GRCh38](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000001405.26/); dates are
  years BP (modern = 0). `uncertainty_radius_km` has no default.
- CI must stay green. GCP operations go through the
  [repository-local gcloud wrapper](repo-gcloud-auth.md).

Corrections and additions to the design are very welcome — especially from the non-English
literature, national biobank browsers we have missed, and anyone who can tell us where the
statistics are wrong.

## 9. Glossary

Terms used in the later sections, in rough order of how much you need them.

**Variant** — a specific place where DNA sequence differs between people. **Allele** — one of
the alternative sequences at that place. **Allele frequency (AF)** — what fraction of copies in
a population are a given allele. **AC / AN** — allele count (how many copies observed) out of
allele number (how many were looked at); the raw form of a measurement, and more informative
than a frequency because it carries the sample size.

**Carrier** — someone with one copy of a variant that only causes disease with two.
**Recessive** — needs two copies to cause disease. **Dominant** — one copy is enough.
**X-linked** — on the X chromosome, so it affects males and females differently. **Mendelian** —
a condition caused by variants in a single gene with a well-understood inheritance pattern; the
scope of version 1. **Penetrance** — the probability that someone with the genotype actually
develops the condition. **Burden** — expected numbers of carriers or affected people in a place,
i.e. frequency turned into people.

**Ascertainment** — how the people in a dataset came to be in it. It is the central technical
problem here, because every dataset was assembled for some purpose that biases who is in it.
**Founder population** — a group descended from a small number of ancestors, so specific
variants are unusually common; often heavily studied, which itself distorts the map.

**Surface** — an estimate of allele frequency drawn continuously across space, as opposed to
individual measured points. **Posterior / credible interval** — Bayesian statistics' output: not
a single number but a distribution, from which "the estimate" and "how uncertain it is" both
come. **Prior** — what the model assumes before seeing data; if a cell's answer is still mostly
prior afterwards, we mark it `prior_dominated` rather than pretending it's a measurement.
**GP / Gaussian process** — the model class used to estimate a smooth spatial surface with
uncertainty. **[INLA](https://www.r-inla.org/) /
[SPDE](https://rss.onlinelibrary.wiley.com/doi/10.1111/j.1467-9868.2011.00777.x)** — the specific
fast approximation used to fit it; the same lineage
the published malaria-mapping work used, which matters for defensibility.

**[GWAS](https://www.ebi.ac.uk/gwas/docs/about)** — genome-wide association study: scanning the
genome for statistical associations with
a trait. **Summary statistics** — a GWAS's per-variant results. **PRS / polygenic score** ([PGS
Catalog](https://www.pgscatalog.org/)) — a
prediction combining thousands of variants; excluded from version 1 for the portability reasons
in §3. **[Pan-UKBB](https://pan.ukbb.broadinstitute.org/)** — multi-ancestry GWAS results across
UK Biobank, the trait layer here.

**[H3](https://h3geo.org/)** — a system that tiles the globe in hexagons at nested zoom levels;
our spatial index. **[Parquet](https://parquet.apache.org/)** — a columnar file format that lets
a query read only the columns and rows it needs. **[DuckDB](https://duckdb.org/)** — an
in-process analytics database that queries Parquet directly, including from cloud storage.
**[Tabix](https://www.htslib.org/doc/tabix.html)** — an index that allows fetching one genomic
region out of a huge compressed file without downloading the whole thing.
**[deck.gl](https://deck.gl/) / [MapLibre](https://maplibre.org/)** — the browser libraries that
draw the map layers and the basemap. **[Hail](https://hail.is/)** — the distributed genomics
engine the Pan-UKB source data lives in.

**[gnomAD](https://gnomad.broadinstitute.org/)** — the largest open variant-frequency database;
comprehensive, no usable geography. **[1KG](https://www.internationalgenome.org/) /
[HGDP](https://www.internationalgenome.org/data-portal/data-collection/hgdp) /
[SGDP](https://ega-archive.org/studies/EGAS00001001959)** — reference panels with population
coordinates; small but mappable.
**[AADR](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/FFIDCW)** — the
ancient-DNA resource, with per-individual coordinates *and dates*; the time axis.
**[ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/)** — the catalogue of clinically interpreted
variants. **[CPIC](https://cpicpgx.org/) / [PharmGKB](https://www.pharmgkb.org/)** —
drug-response variant guidelines. **[CARE Principles](https://www.gida-global.org/careprinciples)**
— a framework for indigenous data governance, asserting the originating communities' continuing
authority over use ([operationalised alongside
FAIR](https://www.nature.com/articles/s41597-021-00892-0)).

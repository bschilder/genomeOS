# genomeOS

> **Explore the genome; worldwide.** 🧬🌍🧬

An open atlas of human genetic variation — across the world's populations, and inside the
cell — where every number can be traced back to the measurement behind it.

---

## Why

Any two people's DNA differs in a few million places. Almost all of those differences do
nothing. A small number cause disease, protect against it, or decide whether a medicine will
work or cause harm — and they are **not spread evenly around the world**.

Take the sickle-cell change. Inherit one copy and you are healthy and substantially protected
against severe malaria; inherit two and you have
[sickle-cell anaemia](https://medlineplus.gov/genetics/condition/sickle-cell-disease/). So it is
common where malaria was historically widespread, and rare elsewhere — and knowing *how* common,
*where*, tells health services how many children will be born with the condition and whether to
screen for it. A research team spent years building exactly that map, and published an estimate
of around 300,000 affected births a year with honest error bars
([Piel et al., *The Lancet*, 2013](https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(12)61229-X/fulltext)).

That has been done properly for roughly **two** genetic changes. For the thousands of others —
[cystic fibrosis](https://medlineplus.gov/genetics/condition/cystic-fibrosis/),
[Tay-Sachs](https://medlineplus.gov/genetics/condition/tay-sachs-disease/), the
[thalassaemias](https://medlineplus.gov/genetics/condition/beta-thalassemia/), and the many
variants that determine whether a common drug is safe for you — nobody can tell you how common
they are where you live. The data is scattered; the largest open collection of human variation
([gnomAD](https://gnomad.broadinstitute.org/)) covers 800,000 people but records their origins
only as broad continental labels, which cannot be put on a map; and producing an honest answer
is genuinely hard, because a smoothly coloured map is very good at looking confident about
guesses.

**We think it should be a map you can open in a browser.**

## What we are building

- **A world map of genetic variation** — where a variant was actually measured, an estimate of
  how common it is everywhere else *with explicit uncertainty*, a clear marking of everywhere we
  don't know, and what that implies in terms of real people: expected carriers and affected
  individuals, with credible intervals.
- **A time slider** over that map, driven by thousands of georeferenced ancient genomes
  ([AADR](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/FFIDCW)) —
  allele frequency across the last ten thousand years. Nobody has shipped this.
- **A 3D atlas of the genome inside the cell** — from the nucleus, into chromosome territories,
  into chromatin domains and loops, down to individual genes.
- **The bridge between them** — go from a gene's physical context in the nucleus out to where
  its variants are common in the world, without leaving the system. Both halves exist
  separately today. The connection does not.

## How it is different

A colour-coded world map of "genetic disease burden" is one of the most misusable objects you
could build in this field, and interpolation between sparse measurements will happily
manufacture convincing patterns that have no cause. So a few properties are built in as
invariants rather than added as disclaimers:

- **What was measured and what was estimated are never mixed** — separate tables, separate
  layers, separate provenance.
- **Every map shows where it doesn't know.** Unmapped areas are hatched, on by default, and
  excluded from every summary statistic — and the unmapped fraction is reported with the answer.
- **Zooming in never invents detail.** Resolution follows data density, not zoom level.
- **When the data won't support a number, we publish no number** and say why.
- **Scope is enforced server-side**: v1 covers single-gene conditions and drug-response variants
  with formal clinical guidelines. Behavioural, cognitive and anthropometric traits are excluded
  from burden mapping, for every caller, by the API rather than by policy someone might forget.

And the bar for v1 is reproducing published science, not shipping a demo: the pipeline must
independently arrive at the *Lancet* sickle-cell numbers, at Howes et al.'s G6PD numbers, and at
carrier rates that national screening programmes have already measured directly. Failing those
tests blocks publication of anything else.

## Status

| | |
|---|---|
| **Atlas (Map mode)** | Design approved, task-level plan written, 64 issues across 4 milestones. **No code yet — the data foundation is the open frontier.** |
| **Pan-UKB evidence API** | Running. Provenance-first API over Pan-UK Biobank metadata and selectively indexed ancestry-stratified GWAS associations — the trait and effect-size layer of the atlas. Full summary-statistics files stay in public object storage and are queried by genomic region through a [Tabix](https://www.htslib.org/doc/tabix.html) boundary. This is what the code in this repo currently does. |

## Documentation

**New here? Start with [the project overview](docs/overview.md)** — what this is, why it
matters, the specific goals, and how to contribute. The first half assumes no genetics
background; there is a glossary at the end.

| Document | What it covers |
|---|---|
| [Project overview](docs/overview.md) | **Start here.** Motivation, vision, goals, data sources, how to contribute |
| [Atlas v1 design spec](docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md) | The full technical design for sub-projects P0–P5 |
| [Implementation plan 1](docs/superpowers/plans/2026-08-22-atlas-data-foundation.md) | Task-by-task plan for the data foundation (P0 + P1) |
| [Pan-UKB architecture](docs/panukb-architecture.md) | The serving model for the GWAS evidence layer |
| [Board conventions](docs/board-conventions.md) | Labels, priorities, milestones, automation |
| [Deployment guide](docs/deployment-gcp.md) · [gcloud wrapper](docs/repo-gcloud-auth.md) | GCP operations |
| [Dataset assessment (#3)](https://github.com/bschilder/genomeOS/issues/3) | Every candidate data source, scored — the upstream document for the whole design |
| [Prior art review (#4)](https://github.com/bschilder/genomeOS/discussions/4) | Everything that has tried this before, and what is genuinely unbuilt |

## Contributing

Contributors from every background are welcome — this needs population geneticists, spatial
statisticians, clinical geneticists, data and frontend engineers, governance expertise, and
people who can open doors to datasets.

1. **Introduce yourself** in [Discussions](https://github.com/bschilder/genomeOS/discussions/76).
2. **Read [the overview](docs/overview.md)**, which ends with a per-skill list of the issues
   that actually block progress.
3. **Check [the issues](https://github.com/bschilder/genomeOS/issues?q=is%3Aissue)** — open
   *and* closed. Open issues are the work queue; closed ones record what was already done and
   what was considered and rejected, so search before starting anything.
4. **Pick something up** from the [project board](https://github.com/users/bschilder/projects/8).
   Filter by `skill:*` to find what you can do; `Ready` means fully specified and unblocked, so
   take it without asking.

**Found a bug, or want a feature?** Open an issue. Features get triaged before implementation —
priority here is derived from the dependency graph, so please don't arrive with an unrequested
feature PR. **All changes to the repository go through a pull request**, including docs.

Issues labelled `wants-expert-review` are the highest-leverage contribution a specialist can
make — you don't have to write the code to make the difference. Corrections to the design, the
dataset scores, and the statistics are actively wanted.

## Local development

```bash
python -m pip install -e '.[dev]'
genomeos init-db
uvicorn genomeos.api:app --reload
pytest
```

By default the service uses `sqlite:///./genomeos.db` for local development. Production requires
a PostgreSQL `DATABASE_URL`. GCP operations must use the
[repository-local gcloud wrapper](docs/repo-gcloud-auth.md).

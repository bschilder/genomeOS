---
title: Technical overview
description: Start with the genomeOS scientific and engineering contracts, then follow the part of the system you want to understand or change.
sidebar:
  order: 1
  label: Overview
---

genomeOS asks a precise question: for a curated, clinically defensible genetic variant, **what
was measured where, what can be estimated between measurements, how uncertain is that estimate,
and where should the system refuse to publish a number?**

The website explains that mission. These technical guides point to the contracts that govern the
implementation.

## The system in six parts

| Part   | Responsibility                                                            | Public result                                 |
| ------ | ------------------------------------------------------------------------- | --------------------------------------------- |
| **P0** | Resolve sampled populations to locations with provenance and uncertainty. | Versioned population registry.                |
| **P1** | Preserve allele counts, source anchors, and ascertainment.                | Validated observation store.                  |
| **P2** | Estimate frequency offline with uncertainty and support masks.            | Immutable surface artifacts.                  |
| **P3** | Propagate supported frequency into population burden.                     | Versioned estimates, intervals, and refusals. |
| **P4** | Read observations and precomputed artifacts.                              | Bounded API with no request-time inference.   |
| **P5** | Make evidence, uncertainty, and gaps explorable.                          | Shareable map views with distinct layers.     |

Read [the system overview](./system-overview/) for how those contracts compose.

## Start with the authoritative sources

- [Project overview](https://github.com/bschilder/genomeOS/blob/main/docs/overview.md) — the
  non-technical problem, two-atlas vision, and safeguards.
- [Scientific and engineering objectives](https://github.com/bschilder/genomeOS/blob/main/docs/scientific-engineering-objectives.md)
  — the objective, interface, acceptance evidence, and refusal conditions for P0–P5.
- [Atlas v1 design](https://github.com/bschilder/genomeOS/blob/main/docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md)
  — method and architecture detail.
- [Repository contributor contract](https://github.com/bschilder/genomeOS/blob/main/AGENTS.md) —
  the rules every human or agent follows before changing code or data.

These guides summarize. Frozen schemas, design documents, plans, and issue decisions remain
authoritative.

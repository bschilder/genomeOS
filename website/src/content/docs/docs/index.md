---
title: Technical overview
description: Start with the genomeOS scientific and engineering contracts, then follow the part of the system you want to understand or change.
sidebar:
  order: 1
  label: Overview
---

genomeOS is building an open, worldwide resource for exploring human genetic variation and its
possible implications for health and research. The public website explains that vision; these
guides explain how contributors are turning it into reliable software and data.

The repository divides the work into six parts and gives them short internal labels from P0 to P5.
You do not need to know those labels to understand the project. They simply help contributors
connect an issue or code change to the right part of the system.

## The system in six parts

| Internal label | Plain-language part     | What it does                                                                  |
| -------------- | ----------------------- | ----------------------------------------------------------------------------- |
| **P0**         | Population locations    | Records where sampled populations were studied and how precise that place is. |
| **P1**         | Measured evidence       | Preserves allele counts, study methods, and exact source references.          |
| **P2**         | Frequency modeling      | Estimates geographic patterns and reports uncertainty and missing support.    |
| **P3**         | Disease-burden modeling | Connects supported frequencies to carefully defined health estimates.         |
| **P4**         | Data service            | Delivers prepared measurements and model results to applications.             |
| **P5**         | Interactive map         | Makes the evidence, estimates, uncertainty, and gaps explorable.              |

Read [the system overview](./system-overview/) for how those contracts compose.

## Start with the authoritative sources

- [Project overview](https://github.com/bschilder/genomeOS/blob/main/docs/overview.md) — the
  non-technical problem, multi-scale vision, and safeguards.
- [Scientific and engineering objectives](https://github.com/bschilder/genomeOS/blob/main/docs/scientific-engineering-objectives.md)
  — the objectives, interfaces, evidence required for acceptance, and conditions that make the
  system decline to publish a number.
- [Atlas v1 design](https://github.com/bschilder/genomeOS/blob/main/docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md)
  — method and architecture detail.
- [Repository contributor contract](https://github.com/bschilder/genomeOS/blob/main/AGENTS.md) —
  the rules every human or agent follows before changing code or data.

These guides summarize. Frozen schemas, design documents, plans, and issue decisions remain
authoritative.

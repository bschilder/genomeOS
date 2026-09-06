---
title: Data and literature evidence
description: How genomeOS expands evidence from publications and databases without inventing missing scientific metadata.
sidebar:
  order: 4
---

The Data working group expands geographic evidence through exact publication measurements and
compatible database transfers. More rows are useful only when their meaning survives extraction.

## Never infer a required field from plausibility

An agent or human must not invent a coordinate, uncertainty radius, denominator, counted allele,
sampling design, disease exclusion, cohort identifier, date, or source locator. Nearby place names,
typical study practice, and values in a secondary compilation are not substitutes for source
evidence.

If a field is not supported, preserve it as unresolved in the publication ledger. Do not promote
the row into P1.

## Anchor every claim

Publication work records an immutable source record, citation, exact table/figure/page/supplement
locator, verbatim population label, verbatim printed frequency, and field-level evidence. A note can
explain a caveat but cannot replace a structured field.

Reuse status is checked and recorded. When no restriction is found after a documented check, use
`no_restriction_found`; lack of an explicit license does not automatically discard valuable data.
Explicit restrictions still control.

## Keep database transfers source-aware

gnomAD, 1000 Genomes, HGDP, AFND, national resources, and other datasets differ in geography,
ascertainment, samples, and access terms. A continental genetic-analysis group is not a geographic
observation. Cohort overlap must not be counted twice.

Follow the [literature evidence curation guide](https://github.com/bschilder/genomeOS/blob/main/docs/literature-evidence-curation.md)
and the source-specific access decisions in [Issue #3](https://github.com/bschilder/genomeOS/issues/3).

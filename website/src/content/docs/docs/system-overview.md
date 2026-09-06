---
title: System overview
description: How population evidence moves through the genomeOS P0–P5 contracts without mixing measurements and inferences.
sidebar:
  order: 2
---

The dependency direction is intentionally one-way:

```text
source adapters → P0/P1 contracts → pure P2 → pure P3 → immutable artifacts → P4 → P5
```

## P0: population registry

P0 answers where an independently sampled population can be located, how uncertain that location
is, and where the coordinate and governance metadata came from. A missing coordinate or
`uncertainty_radius_km` is a hard refusal, not an invitation to guess.

## P1: observations

P1 stores what a source measured: counted allele, allele count, denominator, population, sampling
design, cohort identity, assay, citation, and exact source locator. Publication proposals remain
in staging ledgers until every required field is independently verified and the population resolves
through P0.

## P2 and P3: offline science

P2 produces frequency surfaces with posterior summaries and explicit support states. P3 combines
supported surfaces with inheritance, penetrance, and population denominators. Both are pure offline
modules. Missing support or assumptions produce no number.

## P4 and P5: reading and rendering

P4 reads finished, immutable artifacts; it never fits a model. P5 consumes P4 and gives
observations, modeled surfaces, uncertainty, masks, and burden separate visual layers. Every
shareable view names its model and data versions.

See the [scientific and engineering objectives](https://github.com/bschilder/genomeOS/blob/main/docs/scientific-engineering-objectives.md)
for acceptance evidence at each boundary.

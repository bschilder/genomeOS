---
title: System overview
description: How population evidence moves from original sources to models and the public map.
sidebar:
  order: 2
---

<span class="brand-name">genomeOS</span> separates the journey into six parts. Contributors use the codes P0 through P5 as short
project-board labels; each code is translated below before its technical role is described. The
information moves in one direction:

```text
original sources → population locations → measured evidence → frequency models
→ disease-burden models → versioned result files → data service → interactive map
```

## Population locations (internal label: P0)

The population-location registry records where an independently sampled population can be located,
how uncertain that location is, and where the location and community-governance information came
from. If a source does not support a location or uncertainty range, the build stops instead of
guessing one.

## Measured evidence (internal label: P1)

The observation store preserves what a source measured: the allele being counted, its count and
denominator, the sampled population, how participants were recruited, the study group, laboratory
method, citation, and exact table or figure location. Proposed rows remain in a review area until
every required field is independently verified and the population has a supported location.

## Frequency and disease-burden modeling (internal labels: P2 and P3)

Frequency models estimate how a variant may vary between measured locations and report both
uncertainty and places with inadequate evidence. Disease-burden models combine supported frequency
results with inheritance, the chance that a variant produces a condition, and population counts.
Both run before results reach the website. Missing evidence or required assumptions produce no
number.

## Data service and interactive map (internal labels: P4 and P5)

The data service reads finished, versioned result files; it never fits a model while someone is
using the website. The interactive map requests those results and shows measured evidence, modeled
patterns, uncertainty, insufficient-evidence areas, and disease-burden estimates as clearly separate
layers. Every shareable view identifies the model and data versions behind it.

See the <a href="https://github.com/bschilder/genomeOS/blob/main/docs/scientific-engineering-objectives.md" target="_blank" rel="noopener noreferrer">scientific and engineering objectives</a>
for acceptance evidence at each boundary.

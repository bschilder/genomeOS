---
title: Scientific safeguards
description: The genomeOS invariants that keep attractive visual output from outrunning the evidence.
sidebar:
  order: 3
---

The following rules are part of the product contract. They are not optional presentation choices.

## Measurements stay separate from estimates

Observed data and inferred surfaces use separate tables, layers, provenance, and visual marks. A
caller cannot request a view that makes their status indistinguishable.

## Unknown is an output

Cells marked `unknown` or `prior_dominated` are excluded from aggregates, and the excluded fraction
travels with the result. An unmeasured place is not treated as zero. A visually empty area is
explicitly labeled rather than silently filled.

## Zoom follows evidence

Map resolution responds to support, not interface zoom. Zooming past the evidence reveals gaps; it
does not manufacture local precision.

## Assumptions remain explicit

Coordinates, location uncertainty, recruitment, cohort identity, allele orientation, penetrance,
and denominators never receive convenient scientific defaults.

## Clinical scope is enforced server-side

The burden system excludes behavioral, cognitive, and anthropometric traits for every caller.
Prompt wording, frontend state, and configuration flags cannot bypass that policy.

## Refusal beats plausibility

When the evidence cannot support a number, genomeOS returns no number and says why. Published HbS,
G6PD, and screening-program results are the validation controls; a plausible-looking map is not.

Read the complete [repository invariants](https://github.com/bschilder/genomeOS/blob/main/AGENTS.md#invariants).

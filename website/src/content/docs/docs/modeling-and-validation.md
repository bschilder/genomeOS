---
title: Modeling and validation
description: The offline artifact contract shared by Bayesian, geometric, and other statistically defensible models.
sidebar:
  order: 5
---

Modeling estimates the underlying allele-frequency distribution between sparse measurements while
making uncertainty and unsupported regions first-class results.

## More than one model class

Brian leads the Bayesian spatial modeling line. The working group also welcomes geometric deep
learning and other statistically defensible approaches. Models compete on scientific acceptance
evidence rather than on visual smoothness or novelty.

## One artifact boundary

Every model runs offline and emits the same versioned surface contract: posterior summaries,
support state, effective sample information, `model_version`, and `data_version`. Artifacts are
immutable and keyed by variant and versions. P4 reads them; it does not know how they were fitted.

## Validation before publication

The blocking controls are published HbS geography and burden, G6PD frequency and X-linked logic,
and measured carrier-screening rates. Calibration, held-out spatial prediction, posterior
diagnostics, ascertainment correction, and stability all matter. A model that cannot beat an
appropriate baseline or reproduce known science is refused.

The current inference decision is PyMC with a Hilbert-space Gaussian process. Read
[Issue #34](https://github.com/bschilder/genomeOS/issues/34) before proposing a different runtime,
and use the [scientific objectives](https://github.com/bschilder/genomeOS/blob/main/docs/scientific-engineering-objectives.md)
to keep alternative models on the same acceptance contract.

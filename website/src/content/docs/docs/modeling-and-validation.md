---
title: Modeling and validation
description: How Bayesian, geometric, and other models produce comparable, testable geographic estimates.
sidebar:
  order: 5
---

Modeling estimates the underlying allele-frequency distribution between sparse measurements while
making uncertainty and unsupported regions first-class results.

## More than one model class

Brian leads the Bayesian spatial modeling line. The working group also welcomes geometric deep
learning and other statistically defensible approaches. Models compete on scientific acceptance
evidence rather than on visual smoothness or novelty.

## One shared result format

Every model runs ahead of publication and produces the same kind of versioned result file. That
file records the estimated frequency, its uncertainty, whether the available data support the
estimate, the effective sample information, and the exact model and data versions. Published files
are never overwritten. The data service can read them without needing to know how a particular
model was fitted.

## Validation before publication

The blocking checks are published geography and disease burden for haemoglobin S (HbS), published
frequency and X-linked inheritance results for glucose-6-phosphate dehydrogenase (G6PD) deficiency,
and measured carrier-screening rates. Calibration, prediction in locations withheld from model
training, statistical diagnostics, correction for how participants were recruited, and stability
all matter. A model that cannot beat an appropriate baseline or reproduce known science is refused.

The current inference decision is PyMC with a Hilbert-space Gaussian process. Read
<a href="https://github.com/bschilder/genomeOS/issues/34" target="_blank" rel="noopener noreferrer">Issue #34</a> before proposing a different runtime,
and use the <a href="https://github.com/bschilder/genomeOS/blob/main/docs/scientific-engineering-objectives.md" target="_blank" rel="noopener noreferrer">scientific objectives</a>
to keep alternative models on the same acceptance contract.

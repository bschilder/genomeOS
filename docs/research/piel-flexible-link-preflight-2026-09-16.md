# Piel flexible-link preflight: do not advance to a spatial fit

Status: `automated_analysis` / `pending_expert_review`, 2026-09-16. Advances
[#103](https://github.com/bschilder/genomeOS/issues/103), Atlas design §§7–8, and
the [global modeling plan](../superpowers/plans/2026-09-09-global-af-modeling.md).
This is a method preflight, not a fitted surface or publication result.

## Scientific contract

The objective was to determine whether Piel et al.'s unpublished empirical cubic
link is promising enough to justify another full HbS spatial fit. The measurable
output is a deterministic reconstruction of two explicit readings of the paper's
ambiguous smoothing equation, evaluated at the canonical fit's posterior-median
intercept and against empirical quantiles. The acceptance decision is whether the
link suppresses the diffuse non-endemic floor without making the weak-peak problem
worse.

The engineering components are the pure
`genomeos.surfaces.piel_flexible_link` module and the offline
`scripts/preflight_piel_flexible_link.py` runner. They emit coefficients, link
curves, aggregate quantiles, source and input hashes, and a review figure. They do
not modify the production surface fitter, serve data, or make any artifact
publication eligible.

Piel's fitted coefficients are unavailable. Web Appendix 1 does not completely
specify its posterior-CDF fitting procedure, and its printed equation conflicts
with the stated uniform-prior binomial model. The reconstruction therefore names
every added choice and preserves both equation arms. A favorable fixed-latent
diagnostic would still require a spatial fit with held-out count and burden
validation; an unfavorable diagnostic can avoid that compute. Downstream consumers
are issue #103 and the model-selection ladder, not the serving path.

## Frozen reconstruction

The private input contains 994 count-bearing Piel-comparable survey observations;
963 pass the appendix's `AN >= 50` threshold and 31 are reported as excluded. The
input SHA-256 is
`466034e22015ce5f4e0b90067adb2232491b625591d50c8ac83d955565345b4b`.
No row-level observation is committed.

The two preserved smoothing rules are:

- appendix equation as printed: `(AC + 1) / (AN + AC + 2)`;
- uniform-binomial conjugate equation: `(AC + 1) / (AN + 2)`.

Each arm uses average ranks, Hazen plotting positions, a plug-in normal MLE on
smoothed logits, and a five-start least-squares fit. The cubic derivative is a
strictly positive floor plus the square of a linear function, so monotonicity holds
globally rather than only at sampled points. Input frequencies are sorted before
floating reductions, making the result exactly invariant to row order.

## Result

| Reconstruction | Normal location | Normal scale | Logit RMSE | Frequency at `x = -4.599069` |
| --- | ---: | ---: | ---: | ---: |
| Current inverse-logit | — | — | — | 0.9961% |
| Appendix equation as printed | -3.8138 | 1.5123 | 0.19424 | 1.2126% |
| Uniform-binomial conjugate | -3.7674 | 1.5542 | 0.19459 | 1.1939% |

At the canonical fit's posterior-median intercept, the reconstructed links raise
the frequency by 21.7% and 19.9% relative to inverse-logit. They agree closely
through most of the observed distribution and differ mainly in upper-tail
compression. That compression addresses the implausibly heavy right tail described
by Piel et al.; it does not address this campaign's combination of an overly high
background and under-resolved peaks. At the tested operating point, it moves the
background in the wrong direction.

![Piel flexible-link preflight](../figures/piel_flexible_link_preflight.png)

The committed aggregate receipt and tables are in
[`piel-flexible-link-preflight-2026-09-16/`](piel-flexible-link-preflight-2026-09-16/).
The receipt records `spatial_fit_performed: false`,
`publication_eligible: false`, and an empty list of environmental covariates.

## Decision and source scope

Do **not** spend a GPU fit on this link now. This is a bounded negative result, not
proof that every refitted flexible-link model must fail: a joint refit could move
the latent intercept and spatial field. Revisit only if the original coefficients
or a fully specified fitting procedure become available, or if the link is tested
inside a model that separately targets low background and localized peaks. Any
such candidate must beat the unchanged inverse-logit baseline on held-out counts,
calibration, supported-only national burden, and peak/background contrasts.

This analysis does not grant MAP data special status. The count-bearing HbS survey
observations are used because they directly instantiate the Piel benchmark. MAP
malaria-risk, EVI, friction, and other modeled environmental layers are neither
inputs nor implied next steps. A MAP layer should enter WP3 only when a named
variant-specific mechanism, source/dependency audit, unchanged holdouts, and a
controlled incremental comparison show that it adds useful information beyond the
qualified baseline.

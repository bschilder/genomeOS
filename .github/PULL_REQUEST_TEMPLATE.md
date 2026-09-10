<!--
New here? Read CONTRIBUTING.md and AGENTS.md first. Delete any section that does not apply,
but do not delete the gates checklist — a reviewer reads it to know what was actually run.
-->

## What this changes, and why

<!-- The scientific objective or product claim, not just the mechanics. What would be wrong or
     missing without this change? -->

## Issues

<!-- Repeat the keyword for EACH issue: `Closes #14, closes #15`. A bare list like
     `Closes #14, #15` links only #14. Put a `closes #N` in the commit message too — a squash
     merge concatenates commit messages, so that half is the more reliable one.
     If this only ADVANCES an issue without finishing it, say so in words instead. -->

Closes #

## Design sections implemented

<!-- e.g. design §7.1, §12. Module docstrings should cite these too. -->

## Gates

Paste the result, not a tick. `passed` alone is not evidence; a count or the failure text is.

- [ ] `ruff check .`
- [ ] `python scripts/freeze_contract.py --check`
- [ ] `python scripts/check_module_size.py`
- [ ] `python scripts/check_private_files.py`
- [ ] `python scripts/smoke.py`
- [ ] `pytest` — full suite
- [ ] Focused tests for the touched behaviour:

<details><summary>Output</summary>

```
paste here
```

</details>

**Schema changed?** Then `python scripts/freeze_contract.py` was run and the `contract/` diff is
committed in this PR. CI fails if it is stale.

## What I verified, and what I did not

<!-- Be specific and be honest. An unverified claim of completion is worse than an honest partial.
     State anything you could not check, and why — "not verified: X, because Y" is a good answer. -->

## For data and evidence PRs only

- [ ] Discovery used an existing tool (`scripts/fetch_pubmed_manifest.py` for literature) rather
      than a new fetcher. If you wrote capture code, say why the existing tool did not fit.
- [ ] Raw source payloads are committed alongside the manifest, so it can be replayed.
- [ ] Every timestamp that feeds an identifier is pinned, not read from the clock.
- [ ] Screening decisions are a separate, versioned manifest revision over an all-`pending`
      snapshot — not fused into the capture step.
- [ ] No invented value anywhere: no coordinate, radius, population identity, cohort or sample ID,
      assay, sampling design, ascertainment, date, denominator, count, allele orientation, citation,
      locator, reviewer, or reuse check.
- [ ] Unresolved fields use the exact allowed state (`not_reviewed`, `not_reported`, `ambiguous`,
      `not_checked`) rather than a plausible substitute. Notes never stand in for a structured field.
- [ ] Automated or LLM output is `automated_proposal` / `pending`. The extractor is not the verifier.
- [ ] Source reuse terms inspected and logged for every contributing source.
- [ ] Coverage totals reconcile, and the report counts what it says it counts (manifest rows and
      unique papers are different numbers).

## Figure

<!-- Once a change affects something renderable — observations, a surface, a mask, a burden layer —
     put a figure here rather than describing it. Generate it with a script under scripts/plot_*.py,
     commit the PNG under docs/figures/, and embed the raw URL. A committed figure is reviewable,
     diffable and regenerable; a screenshot is none of those.

     Review figures obey the same invariants as the product: never draw a fitted surface and
     measured observations as one layer, always show where there is no data rather than leaving it
     blank, and check the colour ramp reads low-to-high without the legend. -->

## Scope

- [ ] I did not widen scope silently. Real problems found outside this task were filed as issues,
      linked here, rather than fixed in passing.

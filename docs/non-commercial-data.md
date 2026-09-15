# Non-commercial data in genomeOS

## TL;DR

Some of the data genomeOS uses comes with a licence that allows non-commercial use only. We are
allowed to publish that data, and we do. The condition is that every piece of it is labelled, so
that if this project ever grows a commercial side, one command tells you exactly what has to come
out. That command is:

```bash
python scripts/check_commercial_use.py --list
```

If you are adding data, you do not need to know the rules below. You need to fill in one small
block saying what the source's terms are, and the build will tell you if something is wrong.

---

## Why label rather than refuse

The Atlas draws on sources whose terms are **mixed inside a single response**. Google DeepMind
carves the AlphaGenome AVI Score out for commercial use while leaving the AVI Score Feature
Breakdown non-commercial. gnomAD is CC0, but the SpliceAI annotations it bundles are CC BY-NC.
A licence label attached to the whole source would be wrong in both cases: it would either
over-claim the restricted half or condemn the permissive half.

So the marking is **field-level**. A declaration names the exact record fields that carry the
restriction, which is also the only granularity at which an extraction is useful — a commercial
build wants to drop `top_attributions` and keep `avi_phred`, not drop AlphaGenome entirely.

## What you write

Every external resource in [`website/src/atlas/public-artifacts.json`](../website/src/atlas/public-artifacts.json)
carries a `commercial_use` block. Two fields are always required:

| Field | Meaning |
|---|---|
| `finding` | one of the five values below |
| `restricted_fields` | the record fields that carry the restriction; `[]` when none do |

Three more are required whenever a check was actually performed, which means any `finding` other
than `not_checked`:

| Field | Meaning |
|---|---|
| `checked_at` | the date the source's terms were read |
| `terms_url` | the https URL of the terms that were read |
| `recorded_in` | where the reasoning lives — an audit note in `docs/audits/`, or an issue |

### The findings

This is the same vocabulary the literature reuse checks use in
[`genomeos/observations/evidence.py`](../genomeos/observations/evidence.py), so a source's terms
read the same wherever they are recorded.

| Finding | Use it when |
|---|---|
| `explicitly_open` | an explicit licence permits commercial use (CC0, CC BY, a written carve-out) |
| `permission_granted` | the provider gave written permission |
| `no_restriction_found` | you read the terms and there was no restriction to find |
| `restricted` | there is an explicit non-commercial restriction; name the fields |
| `not_checked` | nobody has read this source's terms yet |

### `not_checked` is allowed on purpose

The build does **not** refuse `not_checked`, and this is deliberate rather than an oversight.
Refusing it would leave a contributor with a choice between abandoning the data and inventing a
licence finding to make the export run — and inventing a reuse check is exactly what the
publication-evidence safeguards in [`AGENTS.md`](../AGENTS.md) forbid. The absence of a named
licence is not itself a restriction, but it is not proof that anyone looked either.

Unchecked sources are reported by the gate as unresolved instead. For an extraction, "we never
read these terms" is every bit as actionable as "we know this is restricted".

## What the build enforces

Two gates, so neither depends on convention:

- [`scripts/export_atlas_web.py`](../scripts/export_atlas_web.py) refuses to publish a resource
  with no `commercial_use` block, a finding outside the vocabulary, a `restricted` finding that
  names no fields, a named field the payload does not actually contain, or a performed check
  missing its date, terms URL or record.
- `KNOWN_NON_COMMERCIAL_FIELDS` in the same file is a **tripwire**. A field already known to be
  restricted cannot reach the published payload unless the declaration names it. This is what the
  earlier blanket refusal of `top_attributions` became: restricted data may ship marked, and may
  never ship unmarked.

`python scripts/check_commercial_use.py` runs in CI. It validates every declaration and, separately,
checks that the catalog which actually shipped still agrees with the allowlist a human edits — a
stale export is otherwise how a restriction quietly disappears from the published data.

## Finding it in the code

Code that handles restricted data carries a `NON-COMMERCIAL:` comment, so a plain search finds
every site:

```bash
grep -rn "NON-COMMERCIAL:" --include='*.py' --include='*.ts' .
```

Issues and pull requests that add or touch non-commercial data carry the
`licence:non-commercial` label.

## Current state

Run the inventory for the live answer. As of the commit that introduced this document:

- **Restricted fields published: none.** The AlphaGenome AVI Score Feature Breakdown is the one
  known restriction and it is not currently in any payload. Its licensing record is in
  [`docs/audits/alphagenome-avi-licensing.md`](audits/alphagenome-avi-licensing.md), and the
  machinery here is what would let it be added and stay findable.
- **Unchecked sources: gnomAD and dbSNP.** Issue #3 records gnomAD as CC0 with a policies link, but
  no dated check exists in this repository for either source, so they are `not_checked` rather than
  a finding transcribed from memory. Resolving them is tracked in
  [#294](https://github.com/bschilder/genomeOS/issues/294).

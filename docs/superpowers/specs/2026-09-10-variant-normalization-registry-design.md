# Variant Normalization Registry — Design

**Status:** design approved by the user on 2026-09-10; spec awaiting review
**Date:** 2026-09-10
**Scope:** a reviewed lookup from an internal `variant_id` to a normalized GRCh38 identity, so that
legacy-named variants can carry coordinate-keyed external annotations and join to other sources.
Seeded from the AFND cytokine promoter loci. Does **not** change any existing `variant_id`.

---

## 1. Scientific contract

### Objective and product claim

A variant that this project already maps can be stated in a second, canonical way — a GRCh38
`chr-pos-ref-alt` identity with a resolved rsID and strand — **without changing the identity it is
already published under**, and without any step in that resolution being invented.

The claim is narrow and worth stating precisely: *this internal identifier and this normalized
identifier denote the same base and the same substitution, and here is the evidence and the named
resource that establishes it.* Everything else the registry might be asked to do is out of scope.

### Measurable output and acceptance evidence

A checked-in table where every row either resolves a variant or **records why it could not be
resolved**, and where:

1. the printed alleles round-trip to the normalized reference and alternate under the recorded
   strand, asserted by test — this catches a strand error, the failure mode most likely to look
   plausible in review, **except for palindromic alleles, where it has no power and separate strand
   evidence is required** (§5);
2. two independent resources agree on the resolution before a row may be marked resolved;
3. a resolved row names the citation that establishes the legacy-name-to-rsID claim, and a row
   without one is refused rather than accepted;
4. an unknown `variant_id` is a refusal at every consumer, never a fallback or a blank;
5. no published `variant_id`, `source_record_id`, or artifact identity changes as a result of this
   work — verified by diffing the published catalogue before and after.

### Engineering component and public interfaces

`genomeos/registry/variants.py`, mirroring the population registry: a pandera schema, a loader, and
a single resolution function. Data at `data/registry/variant_normalization.tsv`.

```python
def load(path: Path, *, registry_version: str) -> pd.DataFrame: ...
def normalized_identity(variant_id: str, registry: pd.DataFrame) -> NormalizedIdentity | None: ...
```

`None` means *no reviewed entry*, and every caller must treat that as a refusal. There is no
`force`, no default, and no partial resolution.

### Assumptions, refusal conditions, and downstream consumers

**Assumed.** That a legacy promoter name denotes one base, that a named external resource can be
cited for the placement, and that the reviewer can check the citation. Where any of those fails the
row is refused; none of them is assumed silently.

**Refused.** No candidate rsID; more than one candidate that the evidence cannot separate; no
citation establishing the naming; the two resources disagreeing; the alleles failing to round-trip
under the recorded strand; any required field missing.

**Consumers.** The web exporter, when deciding whether an artifact may carry a coordinate-keyed
external resource. Adapters, if they later wish to publish a normalized identity alongside their
own. Nothing consumes an unresolved or refused row except a coverage report.

---

## 2. Scope boundaries

### Included

- The registry module, schema, loader, and refusal semantics.
- The resolution pipeline and its evidence requirements.
- An initial batch of AFND cytokine loci, resolved and reviewed, with refusals recorded for any
  that do not resolve cleanly.
- Replacing the shape check requested in review of #207 with a registry lookup, so there is one
  source of truth for what may carry a coordinate-keyed annotation rather than a regex duplicated
  in Python and TypeScript.

### Excluded

- **Changing any `variant_id`.** Considered and rejected in §3. Published identities do not move.
- **The full sweep of 60 cytokine loci.** The corpus holds 60 distinct loci and publishes 4. The
  first batch is the 4 published ones, deliberately, so the refusal rate is measured before
  committing to the rest; the remaining 56 are follow-on work gated on that measurement.
- **HLA, KIR, and phenotype artifacts.** An HLA allele group is not a substitution and this registry
  does not attempt to represent one. Scoring such alleles with a sequence model is a separate
  question with its own validation burden, noted in §7.
- **The counted allele.** It stays data-dependent under the adapter's minor-allele rule; reference
  and alternate are fixed by the genome. The registry must not conflate them.
- **Automated verification policy.** Whether an agent-resolved row may be verified by another agent
  is [#242](https://github.com/bschilder/genomeOS/issues/242) and is not decided here.
- **CI checks for data PRs.** Related but separate; filed independently.

---

## 3. Approaches considered

### A. Replace the `variant_id` with the coordinate

Cleanest long-term: cytokine artifacts would be keyed the way HbS already is and would join natively
to every external source. **Rejected.** It re-mints four published artifact identities and every
cytokine `source_record_id`, requiring a `data_version` bump and republication, and breaking anything
that cites the current identifiers. The immutability invariant (§5 of the Atlas design) exists to
prevent exactly this, and the benefit is convenience rather than correctness.

### B. Columns on `OBSERVATIONS_SCHEMA`

Most discoverable: every observation would carry its own normalization. **Rejected.** It is a frozen
contract change every adapter must then satisfy or explicitly null, it repeats one mapping across
~89,000 rows, and it puts a reviewed lookup inside a measurement table.

### C. A reviewed registry keyed by `variant_id` — **chosen**

Mirrors P0, which is already a reviewed lookup keyed by a label, carrying provenance, that adapters
consult and may not invent entries for. Frozen contracts stay untouched, the mapping is stated once,
and any consumer can use it. The cost is one more artifact to keep reviewed, which P0 already
demonstrates is manageable.

---

## 4. Data flow and component boundaries

```
legacy name in source          "IL-6/ - 174"  +  allele letter
        |
        |  (adapter, unchanged)
        v
internal variant_id            cyt:il-6-174-c        <- still the published identity
        |
        |  registry lookup, reviewed, may refuse
        v
normalized identity            chr<N>-<pos>-<REF>-<ALT>  + rsid + strand
        |
        |  consumed by
        v
exporter: may this artifact carry a coordinate-keyed external resource?
```

The adapter is untouched. The registry sits beside it, and the exporter is the first consumer. No
component gains a dependency on the registry that it cannot express as "resolved, or refused."

---

## 5. Contract: `variant_normalization`

One row per internal `variant_id`. No column has a default.

| Column | Requirement | Refusal if |
|---|---|---|
| `variant_id` | The internal identity, exactly as the adapter mints it | Absent, or not unique in the table |
| `status` | `resolved` or `unresolved` | Any other value |
| `rsid` | `rs` followed by a positive integer; required when `resolved` | Malformed, or present when `unresolved` |
| `normalized_variant_id` | GRCh38 `chr-pos-ref-alt`; required when `resolved` | Fails the coordinate pattern, or present when `unresolved` |
| `printed_alleles` | The alleles exactly as the source prints them, e.g. `G/C` | Absent — it is the input to the round-trip check |
| `printed_convention` | What the source's coordinate means, e.g. a promoter offset and its reference point | Absent, or a bare number with no stated convention |
| `strand` | `plus` or `minus`: how the printed alleles relate to the plus strand | Absent when `resolved`, or any other value |
| `strand_evidence` | How strand was established. **Required when `printed_alleles` are palindromic** (`A/T` or `G/C`), because the round-trip cannot check those | Absent on a palindromic resolved row |
| `reference_resource` | Named **and versioned**, e.g. a dbSNP build or an Ensembl release | Absent, or names a resource without a version |
| `naming_citation` | The citation establishing that the legacy name denotes this rsID | Absent when `resolved` — see §6 |
| `resolved_at` | UTC timestamp | Absent or in the future |
| `reviewed_by` | `human:<slug>` or `agent:<provider>:<model>` | Absent |
| `verification_status` | `verified` or `pending` | Absent; see #242 |
| `refusal_reason` | Required when `unresolved`; forbidden otherwise | Absent when `unresolved`, or a vague reason |
| `notes` | Free text; never a substitute for a structured field | A value that belongs in a column above |

### Invariants

- **The round-trip.** Complement `printed_alleles` under `strand` and the pair must equal the
  reference and alternate of `normalized_variant_id`. Asserted per row by test. This is the reason
  `printed_alleles` and `strand` are stored rather than derived.
- **The round-trip has a blind spot, and it must be declared.** For a **palindromic** pair — `A/T`
  or `G/C` — complementing returns the same set, so the check cannot detect a strand error at all.
  It is powerless precisely where the letters alone are ambiguous. `IL-6 -174 G>C` is such a case,
  so this is not hypothetical for the seeded batch. A row whose `printed_alleles` are palindromic
  therefore **may not rely on the round-trip** and must carry `strand_evidence`: an explicit
  statement of strand from the naming citation or the reference resource, or a flanking-sequence
  match. Absent that, the row is `unresolved` with `refusal_reason` naming strand ambiguity. A
  palindromic row marked `resolved` without `strand_evidence` fails the build.
- **Two resources or nothing.** A row may only be `resolved` if two **independent** resources
  returned the same placement. Independent means separately maintained: Ensembl and NCBI qualify.
  LitVar2 does **not** count as a second resource for a dbSNP placement — both are NCBI, so
  agreement between them is not corroboration. One resource is a proposal, not a resolution.
- **Refusal is a row.** An unresolvable locus is recorded with its reason, not omitted. §6 explains
  why this is load-bearing rather than tidiness.
- **No invention.** Nothing in a row may be produced by inference from another row, by a default, or
  by an agent's unsupported judgement.

---

## 6. Resolution pipeline

Two steps with very different answerability, and conflating them is the main risk.

### Step 1 — legacy name to candidate rsID: not reliably automatable

No service takes `IL-6/ - 174` and authoritatively returns an rsID. The offset is relative to a
transcription start site whose definition varies between publications, and **AFND carries no rsIDs
at all**, so there is nothing upstream to inherit.

**LitVar2** is the best available proposal generator: it maps variant mentions in literature to
rsIDs and returns a citation trail. It proposes; it never decides.

The evidence that settles step 1 is a **citation**, not a statistic. dbSNP records carry a citation
list, which the existing `normalize_dbsnp` already reads. The question becomes: does the candidate
rsID's record, or LitVar2's trail, cite literature that uses the legacy name? That is a checkable
claim about naming, which is what step 1 actually is.

> **Rejected: frequency concordance.** Comparing AFND's allele frequency to a reference population's
> was considered and rejected. It varies by population and dataset, and — decisively — it has no
> discriminating power near a frequency of 0.5, because a strand flip returns approximately the same
> number. It is blindest at exactly the alleles most likely to be mislabelled.

### Step 2 — rsID to GRCh38 identity: automatable and verifiable

Ensembl Variant Recoder and NCBI dbSNP resolve independently and must agree. `normalize_dbsnp`
already refuses anything but an exact SPDI match on position, deleted and inserted sequence, so most
of this exists and verifies rather than trusts.

### Agentic review, and its refusal rule

An agent reads the cited literature and determines whether the legacy name denotes the candidate
rsID, recording **which specific citation establishes it**. Its failure mode is confident wrongness,
so the discipline that makes it usable is a hard rule:

> **If the agent cannot name the source that establishes the naming, the row is refused, not
> guessed.**

The agent's second job is the case where the tools return nothing. A locus with no candidate is not
a gap to leave; it is an `unresolved` row with the reason, what was attempted, and which resources
returned nothing. This is expected to be common rather than exceptional: the well-known promoter
SNPs will resolve cleanly, while obscure loci may have no clean trail at all. Recording those
refusals stops the same dead end being re-investigated, keeps coverage honest across three distinct
states — resolved, refused, not yet attempted — and surfaces whether the remaining loci are worth
attempting at all.

Agent-resolved rows land as `pending` unless #242 decides otherwise.

---

## 7. Error handling and refusals

- A consumer receiving `None` from `normalized_identity` **must refuse**, and must say which
  `variant_id` had no reviewed entry. It may not fall back to a pattern match on the identifier.
- A row failing the round-trip fails the build. It is not downgraded to `unresolved`; a
  contradiction between stored fields is a defect in the row, not an unresolved variant.
- An `unresolved` row is not an error. Consumers skip it exactly as they skip an absent one; the
  difference is that a reader can see it was attempted.
- HLA and KIR artifacts are refused earlier, by entity type, and never reach the registry. Nothing
  here should be read as a claim that a sequence model could not score such an allele — only that
  this registry represents substitutions, and an allele group is not one.

---

## 8. Testing and acceptance evidence

1. **Round-trip.** For every `resolved` row, the printed alleles under the recorded strand equal the
   normalized reference and alternate. A deliberately flipped fixture fails.
2. **Refusal coverage.** Unknown `variant_id`; missing required field; `rsid` on an `unresolved`
   row; `refusal_reason` absent on an `unresolved` row; a malformed normalized identifier.
3. **No identity moved.** The published catalogue is byte-identical before and after, except for
   any external resource deliberately added. This is the acceptance evidence for the non-breaking
   claim and should be run as a diff, not asserted.
4. **Consumer refusal.** The exporter refuses a coordinate-keyed external resource for an artifact
   with no reviewed entry, naming the variant.
5. **The seeded batch.** Every resolved row cites its naming source; every unresolved row states
   what was attempted.
6. Repository gates: `ruff`, `freeze_contract.py --check` (expected clean — no frozen contract
   changes), module size, private files, smoke, full suite.

---

## 9. Open questions

1. **Verification policy** — [#242](https://github.com/bschilder/genomeOS/issues/242). Whether an
   agent-resolved row may be verified by a different agent, or requires a human. This design defers
   to whatever that decides and marks rows `pending` in the meantime. **The four cytokine loci do
   not become eligible for external annotation until their rows are verified**, so the verification
   policy, not this spec, determines when the immediate motivation is satisfied.
2. **What refusal rate would make the remaining 56 not worth attempting?** The first batch measures
   it; this spec does not set the threshold. Worth agreeing before the follow-on is scheduled, so
   the answer is not argued after the effort is spent.
3. **Whether `printed_convention` should be a controlled vocabulary** rather than free text. Left
   free for the first batch; if the same three conventions recur, close it.

## 10. Tracker and documentation changes

- The review of [#207](https://github.com/bschilder/genomeOS/pull/207) asked for a coordinate-shape
  check in the exporter. This design supersedes that with a registry lookup; the review comment
  should be updated so the contributor does not implement the weaker version.
- `docs/literature-evidence-curation.md` already documents `variant_normalization` as an allowlisted
  derivation for the literature ledger. This registry is the adapter-side counterpart and should be
  cross-referenced from it, so the two are visibly the same discipline in two places.

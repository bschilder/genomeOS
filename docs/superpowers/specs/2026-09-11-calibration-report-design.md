# B0H calibration reduction visualization

## 1. Scientific contract and scope

Objective: make the frozen calibration's rank outcomes and complete case
accounting reviewable without changing any scientific calculation or gate.
Acceptance evidence: exact canonical reduction round trips; all36 rank rows,
five rank bins plus missing counts, all1938 case identities and their six stage
statuses represented; independent replay of plotted counts/labels; corrupt
inputs refused; synthetic examples clearly separated from executed calibration.
Component: pure bytes-to-StudyReduction decoder plus a thin offline plotting CLI.
Consumers: human review of the eventual verified closed calibration reduction.
Assumptions: the caller obtains the expected reduction hash from the existing
verified collection/reduction workflow. Hash identity and schema consistency do
not independently certify fitting, provenance, p-values or scientific acceptance.

This is reporting work within #211/#189 and Atlas design §§5,7–8,12. No live
database reads, fits, simulations, null generation, data transfers or cloud
operations. Existing scientific modules, gates, schemas, serializer, collection,
source snapshots and artifacts stay unchanged. No new dependencies. No source
data are committed. Retain all worktrees and evidence; no merge or deletion.

## 2. Pure canonical input boundary

New public `read_study_reduction(data: bytes) -> StudyReduction` in
`genomeos/validation/heterogeneity_report.py` consumes exactly the version1
canonical bytes emitted by the existing `reduction_bytes` serializer. Require
exact bytes; reject duplicate JSON keys, nonfinite JSON tokens, malformed roots,
unknown fields, wrong versions and noncanonical representations. Decode the two
rank-test binary64 bit strings losslessly to the existing RankTestResult fields.
Use the public existing types/validators and `reduction_bytes`; equality of its
complete output bytes to the input is mandatory. Existing case membership,
rank roles/decisions and claim-reason validation must remain authoritative.
Do not duplicate a rank test, null calculation, reducer or private helper.

Preserve every case, descriptive row/aggregate, unavailable value, negative-
infinite log score, failure reason and exact bit string even when it is not
drawn. This decoder validates a serialized report, not its original observations
or execution. No inference imports are called as a decoding side effect.

## 3. Offline CLI and graphics

`scripts/plot_b0h_calibration.py` requires `--reduction FILE`,
`--expected-reduction-sha256 DIGEST`, `--evidence-kind` with exactly
`synthetic_fixture` or `executed_simulation_calibration`, and `--out NEW_DIR`.
Validate hash and canonical content before creating output. Refuse an existing
destination; no overwrite or partial success. Use an explicit source-checkout
import path in documentation and subprocess tests. Record actual imported-source
hashes; refuse a different checkout's decoder/reducer. Matplotlib is offline/Agg.

Save the exact input as reduction.json, ranks.png, accounting.png, and a JSON
receipt last. The receipt has input/output hashes, renderer/decoder/reducer source
hashes, supplied evidence kind, versions, all plotted data/labels, original claim
eligibility/reasons and `publication_eligible=false`. No absolute personal paths,
secrets, model-winner label or invented uncertainty bar. Output/input names and
ordering are deterministic; the input bytes remain unchanged. If hash/schema
validation or plotting fails, return nonzero and preserve any partial output as
failure evidence; a receipt must not falsely claim success.

Ranks: display both tracks separately, all18 mode/quantity rows per track in
frozen order. Display exact counts for bins0..4 and a separate missing column;
use common count limits0..512, without normalizing away missing outcomes. Show
actual_n/512, role, decision and recorded raw/adjusted p-values; unavailable tests
read unavailable, never zero or a full-N test. Distinguish correct-family
rejection from required-control detection and other controls. Keep mode/quantity
IDs in labels. Friendly labels may supplement IDs only when traced to the frozen
quantity spec: modes0 correct,1 prior-only,2 cyclic-rho; quantities0 mean,1 rho,
2 mean*rho,3 training log likelihood,4 log mass AC0/AN20,5 dependence quantity.
No new acceptance threshold, significance calculation or claim wording.

Accounting: six panels for generation, structural, attempt0, attempt1, quantities,
summary. Each has all ten study/track groups (study0..4, track0/1), their case
denominators, and the literal observed statuses as columns with exact counts.
Every case contributes once per panel, so each panel sums to1938; stages are not
independent observations. `not_admitted` is explicit and is not automatically
called a failure: it can represent an unnecessary retry or a blocked downstream
stage. Show top-level claim eligibility and all claim reasons. Use a sequential
low-to-high count ramp, readable labels and sufficient spacing.

Both figures prominently distinguish an authored synthetic reporting fixture
from an executed simulation-calibration report. Neither is a real-population
prediction benchmark, geographic surface or publication gate. The only allowed
positive claim text is the existing permitted_claim, and only when eligible;
an authored fixture never becomes observed acceptance.

## 4. Examples, verification and delivery

Provide a deterministic synthetic generator using existing public constructors
and serialization. No sampler, null simulation, runner stage or source data.
Include all1938 identities/36rank rows and examples of complete, missing-rank,
failed/ambiguous stage, correct-family rejection and missed/detected control
states. Preserve source distinctions; use no inferred real metadata. Commit
the small generator and both rendered PNGs under docs/figures; generate the full
canonical fixture locally rather than committing a large repetitive JSON.

Tests must establish decoder bit-exact round trips including valid -Infinity
descriptives and unavailable tests, duplicate-key/unknown-field/wrong-version/
noncanonical rejection, inconsistent cases/ranks/claims and corrupt hashes.
Use counted/forbidden-call sentinels to show plotting/decoding does not fit or
simulate. Independently replay every plotted count/label/status from input bytes
and actual Matplotlib artists, including both tracks and all1938 case accounting.
Exercise unavailable N511/N0, missed versus detected controls, and existing-output
refusal. Generate and visually inspect both figures. Test evidence must not
present constructor-valid fixtures as realized calibration or provenance.

Use focused tests plus mandatory smoke and repository gates during tasks, and
all full CI commands before PR. Source files carry design-section docstrings.
Keep new modules within the module budget. Deliver a dedicated stacked PR on
the existing runner branch, advancing #211/#189 and closing neither. Actual
calibration remains separately collected/reduced only after its owner terminates.

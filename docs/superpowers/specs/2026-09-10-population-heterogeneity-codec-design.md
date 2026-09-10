# B0H lossless evidence codec

Status: personally reviewed, corrected and adopted for implementation;
representation-only scope, not an executed calibration study.
Design §§5,7–8,12; representation unit advancing the B0H work under #211/#189.
Authority: public record contracts at reviewed scientific source
`df0b71dfca1edd2c209abe8f9829cd103feaffdd`, parent SBC design and adopted
summaries design. The original draft used the equivalent Task1 record
contracts; root checked all35field maps against this completed source.

## 1. Contract and boundary

Claim: supported public evidence round-trips through deterministic bytes while
preserving record class and supported normalized field values, exact integers, binary64
bits, ordered tuples and chain/draw/target array alignment. This proves
representation correctness, not calibration, invocation provenance or durability.
Acceptance: independent literal byte/scalar anchors; every allowed outcome;
corruption/missing/extra/unknown rejection; immutable reconstructed arrays; no
code-executing deserialization. Future storage and offline reduction consume it.
Assumptions: explicit closed records only, accepted public structural contracts,
and IEEE-754 binary64. Existing validation remains authoritative. No invented
metadata, scientific defaults, numerical tolerances, status changes or recovery.

Scope excludes filesystem/environment/network/HTTP, fitting/scoring, random
draws, execution identity/events, storage paths, publication protocols, locks,
fsync/probes, retry admission, scheduling, reducers, CLI and resource pilots.
Existing constructors' deterministic seed-identity expansion is validation;
the codec never constructs a Generator or consumes a scientific random stream.
No pickle/cloudpickle/eval/importlib, object hooks invoking named classes,
dynamic imports, arbitrary dataclass traversal or extensible type registry.

## 2. Public interface and implementation boundaries

Proposed module `validation/heterogeneity_codec.py` exposes:

```python
B0HEvidence = (
    GeneratedDataset | AllUnavailableDataset | GenerationFailure
    | FitAttemptResult | StructuralCheckResult | SelectedSbcQuantities
    | HeterogeneityFitSummary
)

@dataclass(frozen=True)
class B0HCodecLimits:
    max_metadata_bytes: int
    max_total_payload_bytes: int

@dataclass(frozen=True)
class EncodedB0HEvidence:
    metadata: bytes
    payloads: tuple[tuple[str, bytes], ...]  # digest, raw bytes

class B0HCodecError(ValueError): ...

def encode_b0h_evidence(
    value: B0HEvidence, *, limits: B0HCodecLimits,
) -> EncodedB0HEvidence: ...

def decode_b0h_evidence(
    encoded: EncodedB0HEvidence, *, limits: B0HCodecLimits,
) -> B0HEvidence: ...
```

Both limit fields are exact Python integers, not bool; no defaults.
max_metadata_bytes must be positive; max_total_payload_bytes may be zero.
They are caller resource budgets, not scientific eligibility switches. A
budget refusal returns no partial evidence and is never a generation failure.
Budgets bound encoded bytes, not peak process memory: parsed trees, validation
and public constructor copies require additional memory. No RSS guarantee.
The buffer record is a transport container, not evidence and not a supported
root; the decoder validates it even if its constructor has already run.
Only exact listed root classes are accepted, not their subclasses or tuples
of roots. Standalone fits, references, controls, seeds and error records are
nested types only. PredictiveSummaryEvidence is nested under
HeterogeneityFitSummary; no current producer needs it as a standalone root.

Use three coherent modules: heterogeneity_codec.py for the public buffer
interface and checked encode/decode orchestration; heterogeneity_codec_contract.py
for the closed versioned record/field contract and explicit construction;
heterogeneity_codec_wire.py for canonical scalar/array byte grammar and limits.
Cross-module interfaces must be public, explicit and typed, specified in the
implementation plan. The encoder and decoder are the two consumers of this
closed contract, not a user-extensible registry or generic framework.
Module docstrings cite the design sections and representation-only boundary.

## 3. Wire grammar and canonical metadata bytes

The metadata document is exactly the JSON object:
`{"format":"b0h_evidence","root":NODE,"version":"1"}`.
No optional keys, defaulted fields or extension bag. Version is a literal
string, not a JSON number. Unknown format/version is a hard refusal, with no
best-effort reader, downgrade, or implicit migration. A field/tag/meaning change
requires a new version and explicitly selected reader; v1 bytes stay fixed.

NODE is exactly one of these forms (quoted tokens are literal ASCII):

| Kind | JSON form | Meaning |
| --- | --- | --- |
| absent | `null` | Python None, only at declared nullable positions |
| Boolean | `true` or `false` | exact bool, only Boolean positions |
| integer | `["i","HEXINT"]` | arbitrary signed integer |
| float | `["f","BITS"]` | exact binary64 bit pattern |
| string | `["s","UTF8HEX"]` | exact Python string code-point sequence |
| tuple | `["t",[NODE,...]]` | ordered immutable sequence |
| record | `["r","TYPE",{"FIELD":NODE,...}]` | exact closed record |
| array | `["a",{"dtype":"<f8","nbytes":INT,"order":"C","sha256":"DIGEST","shape":TUPLE}]` | external raw payload |

INT denotes an integer NODE, and shape is a tuple NODE containing positive
integer NODEs. Records require every listed field, including explicit nulls.
NODE lists have exact arity. No arbitrary list/dict, JSON numeric literal,
NaN/Infinity token, object array or raw bytes value is a scientific NODE.

HEXINT grammar is `0` or `-?[1-9a-f][0-9a-f]*`: lowercase, no plus, prefix,
negative zero, leading zero or whitespace. Convert base16 without decimal
roundtrips; no fixed-width narrowing or decimal-string conversion limit.
BITS is exactly 16 lowercase hexadecimal digits representing the unsigned
64-bit IEEE-754 word, most-significant byte first. Use bit packing, never
numeric string parsing or float arithmetic to serialize a float.
UTF8HEX is an even-length lowercase hex string, including empty. Decode bytes
as UTF-8 with Python's surrogatepass semantics and require exact re-encoding.
Overlong encodings, invalid continuations and out-of-range code points fail.
This preserves empty messages, control characters, Unicode and individual
surrogate code points, without normalization or JSON surrogate-pair ambiguity.
DIGEST is exactly 64 lowercase hex digits: SHA-256 of raw payload bytes only.
TYPE and FIELD are the case-sensitive ASCII names in §4, never import paths.

Canonical JSON: ASCII bytes, no BOM/trailing newline/whitespace; object keys
sorted lexicographically by ASCII bytes at every level; separators `,` and `:`;
all strings minimally escaped (`\"`, `\\`, short JSON control escapes where
available, otherwise lowercase four-digit `\u` escape). Actual wire strings
are ASCII because scientific strings use UTF8HEX. No escaped slash or escaped
printable ASCII. Reject duplicate object keys before dictionary construction.
Reject noncanonical bytes by canonical reserialization equality after parsing;
do not silently normalize input. Reject trailing documents/data and any
unknown/missing/extra object key, tag, record field or NODE form.

Every input scientific field must match its explicitly declared node type.
Normal public normalized values use Python int/float/bool/str and tuples.
The narrow public NumPy scalar allowances normalize only where the existing
field contract permits them: integer to exact Python int, float16/32/64 to its
exact binary64 value, np.bool_ to bool in Boolean fields that allow it. These
scalar implementation types are not retained; their declared scalar values
are. Reject longdouble, complex, string subclasses/custom numeric objects,
coercible strings, Boolean integers and list-for-tuple inputs at the codec
boundary. No value is made valid by rounding, clipping or default insertion.

## 4. Closed record/field map

Each row is the full ordered constructor field list; JSON object keys sort
independently. Field types, nullable positions, tuple structure and literal
domains are frozen to the named public annotations plus constructor/public
validation at the supplied baseline, not rediscovered from future annotations.
An implementation must transcribe them explicitly, not introspect arbitrary
dataclasses or accept fields because a runtime class happens to expose them.
Before use, check that each of the 35 known runtime dataclasses' constructor
field sets match the frozen map. Bounded introspection of only these classes
is allowed for this drift check, never for accepting new fields/types. This
refuses a future defaulted field instead of silently reconstructing invented
evidence. Constructor/field drift requires explicit compatibility work.

| Source module | TYPE: exact fields |
| --- | --- |
| `heterogeneity_simulation_types` | `SbcCaseId`: track_id, study_id, case_id, replicate_id |
| same | `GenerationId`: track_id, study_id, case_id, replicate_id |
| same | `SeedIdentity`: entropy |
| same | `ParameterTruth`: mean, rho |
| same | `GenerationProvenance`: generation_id, seeds |
| same | `SharedHistory`: cluster_frequencies, candidate_frequencies, uses_cluster |
| same | `HeldoutTarget`: kind, row, latent_frequency, cluster_id, cluster_frequency, candidate_frequency, uses_cluster |
| same | `GeneratedDataset`: case_id, provenance, truth, training, latent_frequencies, shared_history, heldouts, beta_zero_draws, beta_one_draws |
| same | `AllUnavailableDataset`: case_id, provenance, training |
| same | `GenerationFailure`: case_id, provenance, stage, index, reason, truth, sampled_mean, sampled_rho, offending_value, exception_type, exception_message |
| `reference_counts` | `ReferenceCount`: record_id, variant_id, group_id, region_id, variant_group, ac, an |
| `heterogeneity_attempts` | `FitAttemptSpec`: case, attempt_id, seed, config |
| same | `AttemptError`: category, exception_class, message, reason, diagnostics, divergence_count |
| same | `FitAttemptResult`: spec, status, fit, error, identity_mismatches, returned_type |
| same | `StructuralCheckResult`: case, status, error, fit, returned_type |
| `surfaces.heterogeneity_types` | `PopulationHeterogeneityConfig`: mean_prior_alpha, mean_prior_beta, rho_prior_alpha, rho_prior_beta, draws, tune, chains, target_accept, seed |
| same | `VariantTrainingCounts`: variant_id, training_observation_count, training_ac, training_an |
| same | `VariantHeterogeneityDiagnostics`: variant_id, max_rhat, min_bulk_ess, min_tail_ess |
| same | `PopulationHeterogeneityFit`: config, variant_ids, mean_draws, rho_draws, training_record_ids, training_group_ids, unavailable_training_ids, training_counts, diagnostics, divergence_count |
| same | `ReferenceHeterogeneityPrediction`: marginal_predictive, observation_ids, unavailable_ids |
| `predictive` | `CountPredictive`: mean_draws, concentration, cdf_backend |
| `heterogeneity_diagnostic_seeds` | `DiagnosticSeedIdentity`: case, attempt_id, purpose_id, spawn_key |
| `heterogeneity_sbc_controls` | `DiagnosticCallError`: exception_class, message |
| same | `PriorControlFailure`: chain, parameter, reason, sampled_mean, sampled_rho, returned_type, error |
| same | `PriorControlResult`: seed, pairs, failure |
| `heterogeneity_dependence` | `DependencePointReference`: mean, rho, components, raw_values, value, error_bound, resolved |
| same | `HeterogeneityDependenceReference`: orders, analytic_separability, points |
| same | `DependenceComparisons`: status, comparisons_by_order, comparisons |
| `heterogeneity_sbc_quantity_types` | `ScalarQuantityEvidence`: quantity_id, values, error, failed_training_row |
| same | `QuantityRankEvidence`: mode_id, quantity_id, seed, status, rank, comparisons, error |
| same | `SelectedSbcQuantities`: spec, selected_indices, selection_seeds, control, point_slots, points, scalar_quantities, reference, reference_error, ranks |
| `heterogeneity_summary_types` | `ParameterPosteriorSummary`: parameter, truth, estimate, quantiles, draw_count |
| same | `HeldoutPredictiveSummary`: target, log_score, absolute_error, squared_error, coverage, interval_width, randomized_pit |
| same | `PredictiveSummaryEvidence`: seed, seed_words, seed_uint128, cdf_backend, draw_count, targets, status, prediction, rows, error |
| same | `HeterogeneityFitSummary`: spec, variant_id, parameters, predictive |

This is 35 closed record types. Array fields are only the two fit fields and
the two CountPredictive fields. The latter concentration annotation is nullable,
but its enclosing B0H summary validation requires it present.
Properties are not duplicate fields: e.g. canonical IDs, provenance labels,
generation status, expected_sampler_calls, selection_method, control status,
derived parameter errors/coverage/width and not_computed h ESS/MCSE follow the
versioned public contract. Seed entropy/derived scalar properties likewise
remain properties; predictive seed_words and seed_uint128 ARE actual fields
and must be retained. No exception object, traceback or original wrong-type
return is serialized; only the existing typed error/type-name evidence.

## 5. Raw arrays, payload identity and reconstruction

Encoder accepts actual immutable native float64 ndarrays at the declared array
positions, with the shape required by their public context. No lossy cast,
object/complex dtype or writable array is accepted. Preserve C-index element
order; original strides, memory addresses and sharing are not evidence.
Canonical raw bytes are C-order little-endian binary64 without header/padding.
On big-endian hosts swap bytes bitwise, not through numeric conversion; restore
native-endian float64 the same way before calling public constructors.

Payload entries are unique digest/bytes pairs in strictly increasing digest
order. Deduplicate identical raw bytes even for different shapes. Every array
reference carries its own shape and byte length. Repeated references are legal;
duplicate payload entries, even identical, are invalid. Encoder encountering
same digest with different bytes refuses a collision; never overwrite. Decode
requires supplied payload digest set exactly equal the referenced digest set:
missing and unreferenced payloads both fail. Every supplied byte length and
digest must match every referencing descriptor. Do not decompress or fetch.

Fit dimensions are `(chains, draws, variants)`; predictions are `(draws, targets)`.
Never sort, transpose, flatten-away axes, concatenate attempts, or broadcast
concentration to repair input. Check positive dimensions and Python/NumPy
index representability before reshape. Check `nbytes == len(payload)` and
`8 * product(shape) == nbytes` using bounded checked integer arithmetic before
allocation; divide against available actual byte length while accumulating
the product to reject huge metadata early. Check context dimensions before
public constructors. No allocation may be sized solely from declared shape.
Arrays reconstructed from owned immutable bytes must remain nonwriteable,
including refusal to re-enable their write flag. Public constructors may copy
them. Sharing of equal payloads is optional; mutability is never optional.

Metadata is canonical but not self-authenticating. Payload hashes detect a
mismatched payload; they do not prove authorship, and a self-consistent rewrite
of metadata and hashes cannot be detected by this codec. A future storage
adapter must anchor exact metadata bytes/digest externally for that guarantee.

## 6. Validation order, exceptional values and errors

1. Validate exact buffer/limits types and actual metadata/payload lengths before
   parsing or copying. Sum unique payload bytes within the explicit budget.
2. Parse with duplicate-key/numeric-literal refusal and a depth ceiling of 64;
   enforce the ceiling during parsing/preflight, not after unbounded recursion.
   Bound strings, nodes and integer digits by admitted metadata bytes. A
   streaming/capped writer enforces the encoder's metadata budget too.
3. Validate envelope/version, canonical bytes, closed root/field/type grammar,
   fixed tuple arities/order constraints, descriptors and complete payload set.
   Hash actual bytes and check dimensions/lengths before materializing arrays.
4. Reconstruct leaves to parents through explicit public constructor calls.
   No `__new__`, `object.__setattr__` bypass, imported type names or private
   validators. Reconstruct nested diagnostics/config/counts even if enclosing
   constructors merely test their type. CountPredictive constructor validation
   must not call its scorer, CDF backend, sampling or diagnostics methods.
5. DependencePointReference, HeterogeneityDependenceReference and
   DependenceComparisons have no validating constructors. Their exact wire
   field types are checked first, then SelectedSbcQuantities establishes
   context through its public reference/comparison checks and rank constructors.
   Never call reference integration or comparison algorithms to recreate them.
   PredictiveSummaryEvidence similarly invokes require_summary_prediction via
   its constructor. AllUnavailable/GeneratedDataset establish synthetic row
   identities and layout through their public constructors.
6. Re-encode the reconstructed fields with the same explicit contract and
   require bit/type/value equality with parsed evidence and identical payload
   references; reject any constructor normalization that changed wire evidence.
   On encode, perform the same reconstruction/validation comparison before
   returning bytes. Compare floats by bits, not NaN equality or tolerances.
   Use a bounded internal walk/validation pass, not recursively calling the
   two public encode/decode entry points into one another.

Do not claim FitAttemptResult independently proves dataset/fit identity:
its constructor checks its local status/config relationships. Typed rejected
fits and unexpected structural returns retain their own valid config/shapes,
even when differing from the requested attempt. Preserve ordered mismatches;
do not regenerate or re-adjudicate them. Selected quantities and summaries
cannot prove their values came from a separately retained fit/dataset or that
any call/RNG consumption occurred. No missing external object is invented.

Binary64 nonfinite evidence is legal only where public contracts admit it:
GenerationFailure sampled/offending fields and PriorControlFailure sampled
fields may retain NaN (including payload/sign), either infinity and arbitrary
signed integers. Stage/parameter/state validation still applies. A predictive
log_score may be negative infinity, never NaN or positive infinity. All other
domains follow existing finite/probability/interior validations. Signed zero
is preserved wherever admitted. Null, integer zero and floating zero differ.
No nonfinite value is changed to null, a string label or an imputed finite value.

Malformed/unsupported wire, budget violations, payload defects and public
constructor TypeError/ValueError/OverflowError become B0HCodecError with a
bounded field/path explanation and chained cause, never echoed whole payloads.
Unexpected implementation/runtime errors, MemoryError and BaseException
propagate. Existing scientific failures serialize as ordinary successful codec
results; codec errors never become AttemptError/DiagnosticCallError. Neither
entry point promises partial bytes or a partial reconstructed record on failure.

## 7. Independent anchors and exhaustive acceptance checklist

Literal primitive anchors (assert these bytes, not encoder-derived expectations):
`0 -> ["i","0"]`, `-42 -> ["i","-2a"]`,
`2**128-1 -> ["i","ffffffffffffffffffffffffffffffff"]`;
positive/negative arbitrary integers exceeding 4,300 decimal digits survive.
`0.0 -> ["f","0000000000000000"]`, `-0.0 -> ["f","8000000000000000"]`,
`0.5 -> ["f","3fe0000000000000"]`, `1.0 -> ["f","3ff0000000000000"]`,
`+inf -> ["f","7ff0000000000000"]`, `-inf -> ["f","fff0000000000000"]`;
quiet NaN payloads `7ff8000000000001` and `fff8000000000042` stay distinct.
Also retain signaling NaN bits `7ff0000000000001` where failure fields admit NaN.
`"" -> ["s",""]`, `"A\n" -> ["s","410a"]`, `"é" -> ["s","c3a9"]`;
one NUL -> `["s","00"]`; never repair or normalize returned exception text.
one U+D800 -> `["s","eda080"]`; U+10000 -> `["s","f0908080"]`,
two code points U+D800,U+DC00 -> `["s","eda080edb080"]`, distinct on decode.
Case(0,0,0,0) nested node is exactly
`["r","SbcCaseId",{"case_id":["i","0"],"replicate_id":["i","0"],"study_id":["i","0"],"track_id":["i","0"]}]`.
Array shape(2,2), rows(.125,.25),(.5,.75), has 32 raw bytes with hex
`000000000000c03f000000000000d03f000000000000e03f000000000000e83f`.
Independent hash primitive anchor: SHA256(bytes `616263`) is
`ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`;
that three-byte payload must separately fail float64-array length validation.

- Generation: available ordinary/prior/fixed/rho-zero/boundary/shared-history
  on both fit tracks; all-unavailable with all 16 explicit rows; all 12 failure
  stages and their allowed indices/reasons, absent/known truth, both shape
  failure forms, exception classes, invalid/absent scalar evidence, endpoints.
- Attempts: accepted; convergence_failed with empty/nonempty diagnostics and
  absent/present divergence count; failed for every other error category;
  identity_rejected typed fit and wrong-type evidence. Both attempt budgets.
- Structural: expected_refusal, unexpected_exception, unexpected_return with
  typed fit and with wrong-type evidence. No extra sampler-call field.
- Selected quantities: complete and every prior-control prefix failure at
  mean/rho, all three reasons and both invalid-scalar evidence forms; q3/q4
  failures; reference error, resolved/unresolved references; all eight rank
  statuses, scalar/dependence rank failures, retained comparison matrices.
- Summaries: complete, prediction_failed, diagnostics_failed within the
  HeterogeneityFitSummary root; both backends without importing/initializing CuPy; both attempts;
  ordinary and asymmetric two-target order; all parameter fields and seven
  quantiles; negative-infinite score; full uint128 and four seed words.
- Representation: independent axis-varying arrays, identical-byte dedup,
  C/Fortran/strided immutable inputs with equal logical values, endian anchors,
  all legal scalar exceptions, Unicode/surrogates, empty messages, immutable
  output arrays, canonical repeat encoding and decode/re-encode byte identity.
- Refusals: every omitted/extra field, unknown/wrong-position tag/root/version,
  duplicate JSON/payload keys, unsorted payloads, noncanonical scalar/string/JSON,
  truncation/extra documents, payload corruption/removal/extra payload, bad
  hash/length/shape/dtype/order, writable/coercible arrays, incompatible public
  states/alignment/seed evidence, huge declared shapes, excessive depth/budgets,
  forbidden scalar classes and nonfinite values in finite-only positions.
- Verify no fitting/scoring/RNG draw, filesystem/network/dynamic deserialization
  side effects. Use literal constructed records, never NUTS or full studies.
  Preserve every existing scientific threshold; roundtrip equality is bitwise.

## 8. Review decisions and limits

Root personally reviewed, corrected and adopted the implementation plan before
branch execution. Executable acceptance evidence is recorded in the research
note; final whole-branch review remains a separate handoff step. No
primitive/runtime anchor has been executed.
String hex trades human readability and metadata size for exact arbitrary
Python string preservation. Budgets stay explicit because unexpected typed
fit returns may be larger than the planned B0H fit; no new scientific cap is
inferred. Cross-runtime constructor/seed/property compatibility requires a
pinned compatible runtime and v1 contract; portable bytes alone do not certify
all future library versions. No other scientific decision is reopened here.

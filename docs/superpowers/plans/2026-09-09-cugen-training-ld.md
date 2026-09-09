# Training-only CuGen LD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Checkboxes describe implementation, not AF accuracy.

**Goal:** Produce independently checked training-only CuGen LD artifacts and measured synthetic GPU evidence for #195/#205.

**Architecture:** Pure identity/statistical and binary contracts feed a thin offline public-CuGen adapter. A synthetic-only CLI exercises the entire workflow; a verifier refuses incomplete/tampered artifacts.

**Tech Stack:** Existing NumPy/Pandas/Python; optional explicit external CuGen/CuPy, no default dependency changes.

**Spec:** `docs/superpowers/specs/2026-09-09-cugen-training-ld-design.md`.

## Global Constraints

- Fixed pilot caps: 64 source variants, 4096 source samples, 2016 unordered pairs.
- Pin CuGen `b95adbaabef1ca5ff2795b9435e9bb7d6aebb9a1`; never substitute pg_gpu, auto-backend, private monkeypatches or another checkout.
- No AF improvement, haplotype or joint covariance claim. Publication eligibility remains false.
- Pure science has no CuGen, filesystem, HTTP, environment or GPU dependencies.
- Missingness is value3, never a zero dosage; undefined correlations are None and every requested pair is reconciled.
- Exact identities/counts; R absolute error <=1e-5 and R2 <=2e-5. No tolerance relaxation.
- Explicit GRCh38/autosomal_diploid and training/held-out/excluded partition; no inferred metadata.
- No changes to production schemas, fitters, serving, UI, burden gates or dependencies.
- Deterministic science; stochastic modules declare SEED=42. Use apply_patch for edits.
- Dedicated existing worktree branch; smoke and focused tests after changes; privacy and staged-path checks before commits/push; no restricted inputs or private files committed/uploaded.

## Task 1: Independent identity and pairwise-count reference

**Files:** create `genomeos/validation/ld_contract.py`, `genomeos/validation/ld_reference.py`, `tests/test_ld_reference.py`.
**Scientific contract:** correctly identified pairwise-complete unphased ALT correlations and explicit invalid-pair states, not a joint model. Consumers are binary admission and public-output reconciliation.

**Interfaces:** frozen `LDVariant(gidx:int, variant_id:str, chrom:str, position:int, ref:str, alt:str)` with spec§3 validation; public `validate_ld_variants(variants, *, genome_build, ploidy) -> tuple[LDVariant,...]` verifies block semantics. Public `validate_hard_calls(calls) -> np.ndarray` validates/snapshots a read-only uint8 samples-by-variants array at the caps. Public `validate_training_selection(sample_ids, training_indices, *, held_out_ids, excluded_ids) -> TrainingSelection`, with frozen tuple fields `sample_ids`, `training_indices`, `training_ids`, `held_out_ids`, `excluded_ids`. Inputs accept in-memory sequences/1Darrays but must inspect original element types before conversion; no path or string selector.

`reference_ld(calls, variants, *, genome_build, ploidy, window_variants, window_bp) -> tuple[LDPair,...]`: frozen LDPair fields `row_a,row_b,gidx_a,gidx_b,n_obs,counts,status,r,r2`; counts is9integer tuple, statuses exactly spec§4. `variant_moments(calls) -> tuple[VariantMoments,...]` with `n_called,ac,mean,sxx,maf`; undefined moments None. `requested_pairs(variants, *, window_variants, window_bp) -> tuple[tuple[int,int],...]` supplies one public pair-planning contract; both inclusive windows, exact integer validation. All public functions validate input; mutation of caller arrays/sequences cannot change returned state.

- [ ] RED: first test requests the absent public API at test execution (not collection), then hand-checks the fixture. Example core assertion:

  ```python
  pairs = reference_ld(calls[[4,0,2,1]], variants, genome_build="GRCh38",
                       ploidy="autosomal_diploid", window_variants=None, window_bp=None)
  first = pairs[0]
  assert (first.gidx_a, first.gidx_b, first.n_obs) == (30,10,4)
  assert first.counts == (1,0,0,0,1,0,1,0,1)
  assert first.r == pytest.approx(5/11)
  assert Counter(p.status for p in pairs) == {
      "observed":6, "insufficient_observations":11, "zero_variance":4}
  ```

  Add exact signed pairs and moments in spec§4; all-missing versus dosage0; non-PSD determinant;
  windows at exact boundaries including equal positions; single/double flips; n3072/4096
  near-fixed disjoint/overlap references; selection reordering/complete three-way partition,
  alias/mutation protection; invalid raw integer types, labels, identities, shapes, caps and
  ploidy/build. Every test names the break it catches. Run focused tests and preserve RED.
- [ ] GREEN: implement exact integer nine-cell accumulation independently of CuGen, with this epilogue:

  ```python
  if n < 2:
      status, r, r2 = "insufficient_observations", None, None
  elif var_x == 0 or var_y == 0:
      status, r, r2 = "zero_variance", None, None
  else:
      r = numerator / math.sqrt(var_x * var_y)
      status, r2 = "observed", r * r
  ```

  Derive n/sums/variance from exact9counts, not NumPy corrcoef or CuGen helpers; no clipping
  invalid values or matrix repair. Share public contracts, not private cross-module imports.
- [ ] Verify focused tests, smoke, Ruff/module/privacy/whitespace; independently review; commit
  `feat: add independent training-only LD reference refs #195`. Full suite runs once at task
  checkpoint, with interpreter/source pinned to this worktree. Do not close #195.

## Task 2: Canonical CuGen binary and allocation admission

**Files:** create `genomeos/validation/cugen_format.py`, `tests/test_cugen_format.py`.
**Consumes:** Task1 public contracts, `variant_moments`; no CuGen import.
**Produces:** `decode_cugen_bytes(content:bytes, variants, *, expected_samples:int) -> DecodedCuGen`
with immutable/read-only `calls,gidx,mean,sxx,maf,has_missing`; validates spec§5 and storage
moments/budgets. `estimate_ld_workspace(*, source_variants,source_samples,training_samples,
requested_pair_count,chunk_size,tile_size) -> LDWorkspaceEstimate` with `host_bytes,device_bytes`
and named terms; exact spec§6 formulas/budgets, fail before allocation if dimensions/budget invalid.

- [ ] RED: independent struct/bit test writer (test utility only) makes canonical bytes, with
  `header[0:8]=b"CUPGEN01"`, fields/offsets from spec§5 and literal byte-packed calls. Hand
  decode checks variant-major high-bit layout, missing flags, zero padding and statistics.
  Mutate each header field, truncate/append bytes, gidx order/duplicate, nonfinite/wrong stats,
  encoding4/phased/unknown flags, nonzero reserved bytes and dimension bombs. Use behavioral
  allocation tests: a huge header must refuse before constructing a genotype matrix.
- [ ] GREEN: use struct unpacking and bounded frombuffer only after length/dimension/layout
  checks. Decode with `((packed[:,s//4] >> (6-2*(s%4))) & 3)` then transpose to samples×variants.
  Exclude padding from missingness/statistics. Compare stored zero stats for all-missing rows
  without overwriting biological None. Implement named allocation terms exactly per spec§6.
- [ ] Verify focused+Task1 tests/smoke/lint/privacy, review, commit refs #195. Record all
  allocation quantities as estimates, not measured total peaks.

## Task 3: Public CuGen adapter and verifiable immutable artifacts

**Files:** create `genomeos/validation/cugen_pilot.py`, `genomeos/validation/cugen_artifact.py`,
`genomeos/validation/cugen_source.json`, `tests/test_cugen_pilot.py`.
**Consumes:** Tasks1/2 contracts. **Produces:** `run_cugen_pilot(source:Path, *, variants,
selection:TrainingSelection, genome_build, ploidy, evidence_kind:str, data_version:str, cugen_root:Path,
window_variants,window_bp,chunk_size:int,tile_size:int,out:Path) -> Path` returning the completed
manifest path only on success. `verify_cugen_pilot(out:Path) -> dict` rechecks spec§7 artifacts.
`reconcile_ld_output(reference, variants, moments, output:pd.DataFrame) -> dict` in ld_reference or a
focused pure `ld_comparison.py` if needed; exact pair/annotation/count reconciliation and
finite in-range precision checks. Failure raises, retains failure.json and omits manifest.

- [ ] RED: actual public CPU fixture characterization then controlled external GPU boundary
  doubles for adapter error injection only. Assert invalid selector/layout/collision/budget
  refuses before import/device calls; an overlarge source refuses before unbounded reading
  (spec§7 max67072bytes, bounded read67073bytes); empty requested-pair plan refuses rather than
  claiming GPU work; wrong/missing/extra/reversed pairs, N_OBS/annotation/MAF,
  nonfinite/out-of-budget R/R2 fail; existing output, partial writes and every missing/tampered
  artifact refuse. Require explicit evidence_kind="synthetic_fixture", reject all other values;
  missing declaration is not defaulted. Test completed-reader recomputation, not merely a hash parser. CPU doubles
  never count as GPU verification. Source-root/hash mismatch must fail before import. Verifier
  regressions include fractional integer tokens that round to integers in float64 and literal
  NA labels; preserve raw tokens and reject coercion rather than relying on CSV type inference.
- [ ] GREEN: freeze source hash allowlist from the explicit tested revision. Validate and
  snapshot source, then call `subset_cugen_file(..., use_pinned=False, chunk_size=chunk_size)`.
  Re-decode subset and compare `source_calls[selection.training_indices]` exactly. For each
  explicit backend numpy/gpu call `ld_matrix(..., stats=("r","r2"), precision="fp32",
  sign_reference="alt",missing="pairwise",min_obs=2,maf_min=0,min_r2=0,output=None,
  output_format="pairs",tile_size=tile_size,max_pairs=2016,verbose=False)` with supplied
  annotation and exact windows. Reconcile before output completion. Write all seven member
  files and hash them; create manifest exclusively and last. Verifier reads exact allowlisted
  member names, revalidates data/config/identities/results and refuses symlinks/path escape.
- [ ] Verify focused tests/smoke/lint/module/privacy, review and commit refs #195/#205. No
  mocked success is reported as admitted GPU execution. Preserve known warnings separately.

## Task 4: Synthetic CLI, hardware verification and measured report

**Files:** create `scripts/pilot_cugen_ld.py`, `tests/test_cugen_pilot_cli.py`,
`tests/test_cugen_pilot_gpu.py`, `docs/research/cugen-training-ld-pilot-2026-09-09.md`.
**Consumes:** public run/verify adapter. CLI requires `--cugen-root`, `--out`, `--data-version`;
`--case hand|scale|precision`, `--repeats`>=3, `--seed` defaults42. Output root must be new;
one immutable subdirectory per case/repeat and a complete planned-run outcome summary.

- [ ] RED: subprocess tests with explicit source PYTHONPATH verify invalid args, existing output,
  unavailable CuGen/GPU nonzero exit (no skip), planned-run accounting and fixture reproducibility.
  Actual GPU tests cover spec§4 sizes/chunks/tiles, zero/allmissing/monomorphic, precision cases
  and held-out mutation invariance. Expected numeric values derive independently.
- [ ] GREEN: generate only synthetic inputs using public write_cugen with explicit encoding0
  and gidx; configure/record the three precision/reader environment controls before imports.
  Every stochastic path declares SEED=42. Timing uses perf_counter with CUDA synchronization
  before/after device stages; retain each cold/repeat, source generation, CPU/GPU LD and full
  workflow times. RSS is process high-water; pool measurements labeled stage snapshots, not
  peaks. Serialize exact source/environment/hardware hashes and retained failures.
- [ ] Run source-only bundle/privacy preflight; launch singleton GPU/DC requests in preferred
  US/Canada regions, execute real GPU tests/CLI. Retrieve and verify all hashes, then delete
  task pod. Report actual failures/limitations and numerical errors, not only green summaries.
- [ ] Full local CI gates, independent whole-branch review, history/privacy scan, push and PR
  against feat/global-af-modeling. Report exact evidence and remaining WP6 predictive/scale
  gates. No merge or closing umbrella #189. Close #195 only if all its explicit admission
  requirements are evidenced; otherwise state which remain.

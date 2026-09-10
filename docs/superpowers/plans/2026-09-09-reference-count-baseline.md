# Reference-panel Count Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an auditable real-data reference-panel B0 benchmark without weakening the resident-survey contract.

**Architecture:** Extract the pooled-count posterior kernel from the P1 adapter. Add a separate pure reference-count/fold interface and a thin offline artifact runner, reusing existing count diagnostics and weighted summary contracts.

**Tech Stack:** Python 3.12, existing NumPy/SciPy/pandas, pytest; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-09-reference-count-baseline-design.md`

## Global Constraints

- Research target is `reference_panel_within_resource`; evidence role is `development` or `synthetic`.
- No P1 schema changes, invented ascertainment, coordinates, radii, dates, or cohort metadata.
- No network or file I/O in pure science modules; no fitting on the serving path.
- `SEED = 42`; scientific artifacts are deterministic given input bytes, configuration, and source bytes.
- Real genotypes, sample identifiers, count tables, and derived research predictions stay local and untracked in this slice.
- Zero AN is retained as `unavailable_denominator`, never converted to frequency zero or silently dropped.
- Known population dependency components must never cross train/test boundaries.
- All planned folds and all held-out rows have explicit outcomes; failed folds are not omitted from summaries.
- The baseline uses explicit positive finite Beta priors and never trains on held-out counts.
- Marginal predictions are labeled `joint_prediction_supported=false` and are not a coherent joint-site sampler.
- No dependency additions, no GPU prerequisite, and no CuGen dependency in this slice.

## Execution and file map

Work in the existing isolated `global-af-empirical` checkout on
`feat/global-af-reference-counts`, advancing #189 without closing it. Read the
repository AGENTS.md and its required project context. New module docstrings
cite Atlas design §§5,7,8 and the reference-count spec section they implement.

Use `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python` and sibling `ruff`;
set `PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`,
`PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor`,
`MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib`.
Use focused tests while iterating; before each task commit run smoke, Ruff,
module-size, privacy, and inspect staged paths/diff. Root runs full CI before PR.

| File | Responsibility |
| --- | --- |
| `genomeos/validation/count_baseline.py` | Validated positive-AN datum and exact posterior parameters |
| `genomeos/validation/baseline.py` | Existing strict P1 adapter and sampled shared latent draws |
| `genomeos/validation/reference_counts.py` | Reference table, component folds, marginal adapter |
| `scripts/benchmark_reference_counts.py` | Local-file CLI and deterministic artifact orchestration |
| `tests/test_count_baseline.py` | Kernel and P1 regression tests |
| `tests/test_reference_counts.py` | Research contract and graph/marginal tests |
| `tests/test_reference_counts_cli.py` | Subprocess artifact, failure and determinism tests |
| `tests/fixtures/reference_counts/` | Tiny synthetic count and dependency inputs |
| `tests/test_benchmark_cli.py` | Existing runner fingerprint regression |

---

### Task 1: Extract the shared count posterior without changing the P1 model

**Files:**
- Create: `genomeos/validation/count_baseline.py`
- Modify: `genomeos/validation/baseline.py`
- Modify: `scripts/benchmark_allele_frequency.py` (executed science fingerprint)
- Create: `tests/test_count_baseline.py`
- Modify: `tests/test_benchmark_cli.py` (expected fingerprint files)

**Interfaces:**
- Consumes: existing `validate_allele_observations` and `CountPredictive` in the unchanged P1 adapter.
- Produces: immutable `PooledAlleleCount(record_id: str, variant_id: str, ac: int, an: int)`; existing-shaped `B0VariantPosterior` and `B0InfeasibleError` in the new module.
- Produces: `pooled_beta_posteriors(training_counts: Sequence[PooledAlleleCount], variant_ids: Sequence[str], *, prior_alpha: float, prior_beta: float) -> tuple[B0VariantPosterior, ...]`.
- Preserves: `fit_pooled_b0(...) -> PooledB0Fit`, and imports of posterior/error types from `baseline`.

- [ ] **Step 1: Add failing arithmetic and validation tests.**

```python
def test_posterior_pools_only_matching_variant():
    rows = [PooledAlleleCount("a", "v", 1, 4),
            PooledAlleleCount("b", "v", 3, 6),
            PooledAlleleCount("c", "w", 9, 10)]
    result = pooled_beta_posteriors(rows, ["v"], prior_alpha=1, prior_beta=1)
    assert result == (B0VariantPosterior("v", 2, 4, 10, 5.0, 7.0),)

@pytest.mark.parametrize("ac,an", [(True, 4), (1.5, 4), (-1, 4), (5, 4), (0, 0)])
def test_invalid_counts_are_not_coerced(ac, an):
    with pytest.raises(ValueError):
        PooledAlleleCount("a", "v", ac, an)
```

Also assert blank/nonstring IDs, duplicate training IDs, duplicate/empty requested
variants, absent variants, nonfinite/nonpositive/bool priors, and numeric overflow
are errors; NumPy integer inputs normalize losslessly. Sum beyond int64 using
Python integers without wraparound and refuse resulting unstable shapes.

- [ ] **Step 2: Run RED.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_count_baseline.py -q
```

Expect missing-module failure before implementation; preserve output in report.

- [ ] **Step 3: Implement the pure kernel and adapt P1.**

```python
# count_baseline.py: validate datum at construction and function inputs explicitly.
total_ac = sum(row.ac for row in rows)
total_an = sum(row.an for row in rows)
alpha = alpha_prior + total_ac
beta = beta_prior + (total_an - total_ac)
# Require positive finite alpha, beta and alpha + beta before returning.

# baseline.py: keep P1 validation before this conversion.
counts = tuple(PooledAlleleCount(row.source_record_id, row.variant_id, row.ac, row.an)
               for row in training.itertuples(index=False))
posteriors = pooled_beta_posteriors(
    counts, tuple(sorted(testing["variant_id"].unique())),
    prior_alpha=prior_alpha, prior_beta=prior_beta,
)
rng = np.random.default_rng(normalized_seed)
draws_by_variant = {
    posterior.variant_id: rng.beta(posterior.alpha, posterior.beta, size=draws)
    for posterior in posteriors
}
```

Preserve sampled output test-row ordering, public names, seed checks and shared
draws. New kernel has no pandas/P1 imports. Include its executed module path/hash
in the existing CLI source map, not merely a string naming an unexecuted file.

- [ ] **Step 4: Add P1 regression and run GREEN plus existing runner tests.**

```python
# In a test using the existing tiny valid observation fixture, compare the
# returned draws with this independent pre-extraction calculation:
rng = np.random.default_rng(42)
expected = rng.beta(1.0 + train_ac, 1.0 + train_an - train_ac, size=32)
np.testing.assert_array_equal(fit.predictive.mean_draws[:, 0], expected)
np.testing.assert_array_equal(fit.predictive.mean_draws[:, 0],
                              fit.predictive.mean_draws[:, 1])
```

Also keep the missing-ascertainment P1 hard-error test; no research input should
be admitted by the P1 adapter. Run both test files and mandatory task gates.

- [ ] **Step 5: Commit after staged-path/privacy review.**

```bash
git add genomeos/validation/count_baseline.py genomeos/validation/baseline.py scripts/benchmark_allele_frequency.py tests/test_count_baseline.py tests/test_benchmark_cli.py
git commit -m "refactor: share pooled allele-count posterior kernel" -m "Advances #189; preserves the P1 observation contract."
```

### Task 2: Add reference counts, dependency folds, and exact marginal predictions

**Files:**
- Create: `genomeos/validation/reference_counts.py`
- Create: `tests/test_reference_counts.py`

**Interfaces:**
- Consumes: `PooledAlleleCount`, `B0VariantPosterior`, `B0InfeasibleError`, `pooled_beta_posteriors` from `count_baseline`; existing `CountPredictive`.
- Produces: immutable `ReferenceCount(record_id: str, variant_id: str, group_id: str, region_id: str, variant_group: str, ac: int, an: int)`.
- Produces: `validate_reference_counts(rows: Sequence[ReferenceCount]) -> tuple[ReferenceCount, ...]` preserving order.
- Produces: immutable `ReferenceFold(split_id: str, train_ids: tuple[str, ...], test_ids: tuple[str, ...], test_groups: tuple[str, ...])`.
- Produces: `reference_group_folds(rows: Sequence[ReferenceCount], *, dependency_edges: Sequence[tuple[str, str]], n_folds: int = 5, seed: int = SEED) -> tuple[ReferenceFold, ...]`.
- Produces: immutable `ReferenceB0Fit(marginal_predictive: CountPredictive, observation_ids: tuple[str, ...], unavailable_ids: tuple[str, ...], posteriors: tuple[B0VariantPosterior, ...])`.
- Produces: `fit_reference_b0(training: Sequence[ReferenceCount], testing: Sequence[ReferenceCount], *, prior_alpha: float, prior_beta: float) -> ReferenceB0Fit`.
- Produces: `ReferenceInfeasibleError(ValueError)` for no scoreable test rows; reuse `B0InfeasibleError` for missing training variants.

- [ ] **Step 1: Add RED tests for missingness, folds, and analytic agreement.**

```python
def row(group, ac=1, an=4):
    return ReferenceCount(group + ":v", "v", group, "r", "block", ac, an)

def test_missing_denominator_is_retained():
    missing = row("missing", 0, 0)
    assert validate_reference_counts([missing]) == (missing,)
    fit = fit_reference_b0([row("train")], [missing, row("test")],
                           prior_alpha=1, prior_beta=1)
    assert fit.unavailable_ids == ("missing:v",)
    assert fit.observation_ids == ("test:v",)

def test_exact_marginal_matches_beta_binomial():
    fit = fit_reference_b0([row("train", 1, 4)], [row("test", 2, 5)],
                           prior_alpha=1, prior_beta=1)
    np.testing.assert_allclose(fit.marginal_predictive.log_prob([2], [5]),
                               [scipy.stats.betabinom.logpmf(2, 5, 2, 4)])
```

Use groups a..f and edges(a,b),(b,c), n_folds=3: verify transitive component
co-location, every row held out once, no overlap, same membership after row or
edge reordering/count changes. Test unknown/self/duplicate edges, too few
components, bool/invalid seeds/fold counts, duplicate records/group-variants,
inconsistent labels and invalid counts/IDs.

- [ ] **Step 2: Run RED.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_reference_counts.py -q
```

- [ ] **Step 3: Implement the narrow pure interfaces.**

```python
# Graph components are canonical before any RNG use.
components = sorted(tuple(sorted(component)) for component in components)
permutation = np.random.default_rng(seed).permutation(len(components))
fold_groups = [set() for _ in range(n_folds)]
for position, index in enumerate(permutation):
    fold_groups[position % n_folds].update(components[index])

# Marginal adapter: only positive denominators enter the kernel/scorer.
scoreable = tuple(row for row in testing if row.an > 0)
counts = tuple(PooledAlleleCount(row.record_id, row.variant_id, row.ac, row.an)
               for row in training if row.an > 0)
posteriors = pooled_beta_posteriors(
    counts, tuple(sorted({row.variant_id for row in scoreable})),
    prior_alpha=prior_alpha, prior_beta=prior_beta,
)
by_variant = {posterior.variant_id: posterior for posterior in posteriors}
shape_a = np.array([by_variant[row.variant_id].alpha for row in scoreable])
shape_b = np.array([by_variant[row.variant_id].beta for row in scoreable])
concentration = shape_a + shape_b
mean = shape_a / concentration
# Refuse means outside (0,1) or reconstructed shapes differing beyond rtol1e-10.
marginal = CountPredictive(mean[None, :], concentration=concentration[None, :])
```

Enforce disjoint train/test record IDs and groups. Empty positive training data
with scoreable testing must raise absent-variant infeasibility. Do not require
test variant/group label identities to exist in training. No optional metadata
registry or spatial fallback. Keep the module under the repository size budget.

- [ ] **Step 4: Run GREEN and leakage/numerical regressions.**

```python
first = fit_reference_b0([row("train")], [row("test", 0, 4)],
                         prior_alpha=1, prior_beta=1)
changed = fit_reference_b0([row("train")], [row("test", 4, 4)],
                           prior_alpha=1, prior_beta=1)
assert first.posteriors == changed.posteriors
np.testing.assert_array_equal(first.marginal_predictive.mean_draws,
                              changed.marginal_predictive.mean_draws)
```

Assert full missing folds infeasible; absent training variants refused; marginal
CDF/quantiles agree with SciPy published-function values on small supports;
extreme shapes that round mean to1 are refused, not clipped. Run task1 and task2
focused tests plus mandatory task gates.

- [ ] **Step 5: Commit.**

```bash
git add genomeos/validation/reference_counts.py tests/test_reference_counts.py
git commit -m "feat: add dependency-aware reference count baseline" -m "Advances #189; development-only exact marginal count predictions."
```

### Task 3: Run a deterministic reference benchmark with complete artifacts

**Files:**
- Create: `scripts/benchmark_reference_counts.py`
- Create: `tests/test_reference_counts_cli.py`
- Create: `tests/fixtures/reference_counts/counts.tsv`
- Create: `tests/fixtures/reference_counts/dependencies.json`

**Interfaces:**
- Consumes all Task2 public types/functions; existing `predictive_diagnostics`, `BenchmarkFoldStatus`, and `summarize_benchmark`.
- Produces CLI and six artifacts exactly specified in spec §CLI and artifact contract.
- Main returns0 for complete comparison,2 for completed artifact publication with failed/infeasible folds; structural validation raises with nonzero exit and no scientific artifacts.

- [ ] **Step 1: Create tiny synthetic fixtures and failing subprocess tests.**

```text
record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\tan
a:v\tv\ta\tr1\tblock\t0\t4
b:v\tv\tb\tr1\tblock\t1\t4
c:v\tv\tc\tr1\tblock\t2\t4
d:v\tv\td\tr2\tblock\t3\t4
e:v\tv\te\tr2\tblock\t4\t4
f:v\tv\tf\tr2\tblock\t0\t0
```

```json
{"edges": [["a", "b"]], "qualification": "Synthetic dependency; not a statement about real participants."}
```

With5folds one missing-only component creates an infeasible fold: use2folds
for the completed-run fixture test. Explicitly test5folds retains the missing-only
fold, incomplete status and unavailable row. Required subprocess command:

```python
command = [sys.executable, str(ROOT / "scripts/benchmark_reference_counts.py"),
           "--counts", str(counts), "--dependencies", str(dependencies),
           "--source-release", "synthetic-v1", "--cohort-stage", "synthetic",
           "--count-kind", "quality", "--evidence-role", "synthetic",
           "--prior-alpha", "1", "--prior-beta", "1", "--folds", "2",
           "--seed", "42", "--out", str(out)]
```

- [ ] **Step 2: Run RED.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_reference_counts_cli.py -q
```

- [ ] **Step 3: Implement local parsing, fold scoring, and artifacts.**

```python
# Preserve labels literally and validate raw integer tokens before conversion.
raw = pd.read_csv(counts_path, sep="\t", dtype=str, keep_default_na=False)
# Require exact schema; integer tokens match [+-]?[0-9]+ and then int(token).
# Validate metadata, graph and configuration before creating output files.

for index, fold in enumerate(folds):
    training = tuple(by_id[key] for key in fold.train_ids)
    testing = tuple(by_id[key] for key in fold.test_ids)
    # Catch declared infeasibility separately from numeric ValueError.
    fitted = fit_reference_b0(training, testing,
                             prior_alpha=args.prior_alpha, prior_beta=args.prior_beta)
    scored = tuple(by_id[key] for key in fitted.observation_ids)
    diagnostics = predictive_diagnostics(
        fitted.marginal_predictive, [row.ac for row in scored],
        [row.an for row in scored], seed=pit_seeds[index],
    )
```

Seed protocol: `SeedSequence(seed).spawn(2)` generates one split seed and one PIT
parent; PIT parent spawns one uint32 seed per fold. Record all seeds. Fold
membership itself uses the generated split seed, not test counts. Build complete
row outcomes before aggregation. Integrate all ten diagnostics by their existing
returned names, with one record per scoreable test row. Frame indexes must never
implicitly misalign observations. Empty prediction/posterior files retain headers.

Use explicit checkout bootstrap and imported module objects for executed-source
hashes: count_baseline, reference_counts, predictive, benchmark,
observations/schema (benchmark imports it), and the runner. Hash exact input
bytes and emitted output bytes. Record Git HEAD/dirty state without absolute
paths. Validate a new output destination and refuse overwriting existing paths.
Write deterministic JSON (sorted keys, no NaN/Infinity; follow existing CLI's
representation for zero-probability log scores) and deterministic TSV. Keep the
runner under500logical lines; ask controller before introducing another module.

- [ ] **Step 4: Run complete and incomplete artifact tests plus all focused tests.**

```python
assert summary["target"] == "reference_panel_within_resource"
assert summary["joint_prediction_supported"] is False
assert len(row_status) == len(input_rows)
assert set(row_status.record_id) == set(input_rows.record_id)
assert row_status.loc[row_status.record_id == "f:v", "status"].item() == "unavailable_denominator"
for name in ("splits.json", "row_status.tsv", "predictions.tsv",
             "posteriors.tsv", "summary.json", "manifest.json"):
    assert (first_out / name).read_bytes() == (second_out / name).read_bytes()
```

Test missing training variants, injected numeric failure, all missing test rows,
zero scoreable predictions, invalid dependency/metadata/count tokens, preserved
literal `NA`/leadingzero labels, output reuse refusal, conflicting PYTHONPATH,
and recomputed file hashes. Verify scoreable membership matches fold status and
summary; no failed fold or unavailable row vanishes. Run mandatory task gates.

- [ ] **Step 5: Commit and hand off real-data execution to the controller.**

```bash
git add scripts/benchmark_reference_counts.py tests/test_reference_counts_cli.py tests/fixtures/reference_counts
git commit -m "feat: add reproducible reference count benchmark runner" -m "Advances #189; preserves every planned fold and unavailable denominator."
```

Controller then runs full CI and final review, prepares local inputs from the
already qualified count audit (never re-downloads or reclassifies samples), and
executes the spec's12predeclared runs. Aggregate evidence and hashes go in a new
research note and the dedicated branch PR. Do not commit real input/output rows,
claim sealed validation, or close #189 from this development baseline.

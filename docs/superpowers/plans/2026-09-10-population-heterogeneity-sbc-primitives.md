# B0H Calibration Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build independently testable continuous dependence and discrete
rank/null primitives for the frozen B0H calibration design.

**Architecture:** Two pure validation modules, using the existing finite-product
oracle but never production fitting/scoring to generate or evaluate reference
data. An explicitly public Beta quadrature helper serves two real consumers.
Synthetic generation, actual study orchestration and1936fits are later,
separately frozen implementation units.

**Tech Stack:** Locked Python3.12, NumPy, SciPy, pytest; no new dependency.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-sbc-design.md`
and its parent `2026-09-10-population-heterogeneity-design.md`.

## Global Constraints

- Pure validation modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Keep existing clinical gates and global promotion defaults unchanged.
- AN=0 is retained as unavailable, never converted to frequency zero.
- No cross-variant pooling or independence claim for linked loci.
- All sampler/prior/scorer/convergence contracts in the parent B0H spec stand.
- Existing analytical, quadrature and numerical regression thresholds stay unchanged.
- Public science functions reject Boolean integers, malformed shapes, nonfinite
  values and unsupported domains; failures are not coerced into output.
- Production modules target at most500 logical lines; split by responsibility
  before crossing the repository limit.

Controller owns a final stable-tree full CI and one broad review. Implementers
run covering tests, mandatory smoke, Ruff, module-size and privacy, inspect staged
paths and commit only their owned files. No actual sampler study, real-data run,
dependency change, resource launch or serving modification is part of these tasks.

---

### Task 1: Continuous posterior-dependence reference and numerical ordering

**Files:** Modify `genomeos/validation/heterogeneity_oracle.py`; create
`genomeos/validation/heterogeneity_dependence.py`,
`tests/test_heterogeneity_dependence.py`,
`docs/research/population-heterogeneity-dependence-2026-09-10.md`.

**Interfaces:** Consume public `heterogeneity_log_mass` and
`heterogeneity_quadrature`. Produce:

```python
def beta_prior_quadrature(
    prior: tuple[float, float], *, order: int,
) -> tuple[np.ndarray, np.ndarray]: ...

@dataclass(frozen=True)
class DependencePointReference:
    mean: float
    rho: float
    components: tuple[tuple[float, float, float, float], ...]
    raw_values: tuple[float, ...]
    value: float
    error_bound: float
    resolved: bool

@dataclass(frozen=True)
class HeterogeneityDependenceReference:
    orders: tuple[int, ...]
    analytic_separability: bool
    points: tuple[DependencePointReference, ...]

@dataclass(frozen=True)
class DependenceComparisons:
    status: str
    comparisons_by_order: tuple[tuple[int, ...], ...]
    comparisons: tuple[int, ...] | None

def heterogeneity_dependence_reference(
    counts: Sequence[tuple[int, int]], *,
    mean_prior: tuple[float, float], rho_prior: tuple[float, float],
    points: Sequence[tuple[float, float]],
) -> HeterogeneityDependenceReference: ...

def dependence_comparisons(
    reference: HeterogeneityDependenceReference, *,
    truth_index: int, draw_indices: Sequence[int],
) -> DependenceComparisons: ...
```

Orders are exactly(64,128,256), not an argument. Component order is training
log likelihood,logZ,log fixed-mean integral,log fixed-rho integral. Result
`value` is highest-order raw h, except exact separability gives literal0.
`resolved` requires both gaps<=1e-6 and, for separability, each raw|h|<=1e-6.
Return finite unresolved results with all raw evidence; nonfinite arithmetic
raises ArithmeticError rather than inventing a value. Results use immutable
scalar/tuple fields. Comparison statuses are exactly `resolved`,
`dependence_reference_unresolved`, `dependence_rank_order_unresolved`.
Comparisons encode less=-1,equal=0,greater=1; never convert a numerical guard
failure to a tie. `comparisons_by_order` always retains raw comparisons, even
when analytic values establish ties or a point is unresolved.

- [ ] **Step 1: Write exact failing anchors before implementation.**

```python
@pytest.mark.parametrize(
    "mean_prior,rho_prior,z,ratios",
    [((1.,1.),(1.,1.),5/12,(65/63,13/11,75/77)),
     ((2.,3.),(3.,2.),13/25,(169/162,169/154,65/66))],
)
def test_nonseparable_reference_has_independent_rational_anchors(
    mean_prior, rho_prior, z, ratios,
):
    result = heterogeneity_dependence_reference(
        ((0,2),), mean_prior=mean_prior, rho_prior=rho_prior,
        points=((.25,.25),(.75,.75),(.25,.75)),
    )
    assert not result.analytic_separability
    assert result.orders == (64,128,256)
    for point, ratio in zip(result.points, ratios, strict=True):
        assert point.resolved
        assert point.value == pytest.approx(math.log(ratio), abs=1e-11)
        for components in point.components:
            assert components[1] == pytest.approx(math.log(z), abs=1e-11)
```

Add literal component checks: uniform likelihoods39/64,13/64,45/64;
fixed-mean integrals21/32,5/32,21/32; fixed-rho integrals3/8,11/24,11/24.
Asymmetric fixed-mean27/40,7/40,27/40; fixed-rho9/20,11/20,11/20.
These all use absolute1e-11. Cover empty/allAN0, mixedAN1 and repeatedAC1/AN2
separability, asymmetric priors, AN0 insertion, complement m->1-m/counts->AN-AC,
preserved/repeated point order and input immutability.

Public node tests: orders2,32; priors(1,1),(2,3),(3,2); integrate constant1,
mean a/(a+b), second moment a(a+1)/((a+b)(a+b+1)) within1e-13. Reject
Boolean/nonintegral/out-of-range orders outside2..512 and malformed/nonpositive/
nonfinite priors. Refuse degenerated nodes or nonpositive/nonfinite weights.

Run `python -m pytest tests/test_heterogeneity_dependence.py -q`; expect a
genuine missing-interface import failure. Record it, never fabricate a RED.

- [ ] **Step 2: Implement the public nodes and finite-order reference.**

Expose the existing checked Beta quadrature through `beta_prior_quadrature`:
normalize the prior and order using local existing validators, then call the
existing quadrature implementation. Route the existing posterior oracle through
this public function without changing numerical formulas or its outputs. Do not
import private helpers into the new dependence module.

Consume/validate counts once using the existing public posterior oracle with
predictiveAN0. That gives each order's logZ without a second density formula.
Validate points as a nonempty sequence of exactly two finite non-Boolean real
scalars strictly inside(0,1). Validate counts even for an empty/separable likelihood.
For fixed-m and fixed-r integrals use public Beta nodes and sum rowwise independent
finite-product log masses plus log prior weights. Use stable logsumexp, with
finite checks. Reuse logZ and nodes once per order, not once per point. Work is
bounded by a256x256 evidence grid and point-by256 conditional vectors.

```python
components = (ell, log_z, log_fixed_mean, log_fixed_rho)
h = ell + log_z - log_fixed_mean - log_fixed_rho
guard = max(
    abs(h128-h64), abs(h256-h128),
    64*np.finfo(np.float64).eps * max(
        1+sum(abs(term) for term in terms) for terms in all_components
    ),
)
```

Only the spec's closed count predicate declares separability. No low-correlation
or small-value heuristic. Do not hide failing raw reference checks behind literal0.

- [ ] **Step 3: Test and implement explicit rank-order resolution.**

Require exactly four draw indices, non-Boolean integers in range, distinct and
different from truth_index. Identical parameter values at different indices are
allowed. Raw comparisons use each order separately. If any used point is
unresolved, return `dependence_reference_unresolved` and no final comparisons.
Otherwise separability or identical point pairs establish exact zero comparisons.
All other comparisons require identical nonzero signs across orders and
strict highest-order contrast greater than the sum of guards. Return
`dependence_rank_order_unresolved` if any comparison fails; preserve all raw signs.

```python
signs = tuple((draw > truth) - (draw < truth) for draw, truth in order_values)
strict_resolved = (
    signs[0] != 0 and len(set(signs)) == 1
    and abs(draw256-truth256) > draw_guard+truth_guard
)
```

Test full resolved mixed signs on analytically anchored points plus repeats;
literal ties for separable points and identical inputs; known nonseparable h=0
but distinct points must remain unresolved if equality lacks the allowed identity.
Use frozen dataclass replacements in unit tests to inject sign changes,
cancelling comparisons, guard equality, point nonconvergence and nonfinite
evidence. Refuse malformed forged reference shapes/nonfinite/negative guards;
do not accept incorrect order tuples. No actual sampler is called by these tests.

- [ ] **Step 4: Record bounded evidence, run regression gates and commit.**

The research note derives the rational anchors and h, records exact commands,
measured maximum errors and all refusal tests, and distinguishes an empirical
ordering guard from a proof. Use one deliberate restored mutation replacing
`+logZ` with `-logZ`; the rational anchor test must fail. Restore before gates.
No extra adaptive probes or sampler runs. Run:

```bash
python -m pytest tests/test_heterogeneity_dependence.py tests/test_heterogeneity_oracle.py -q
python scripts/smoke.py
ruff check .
python scripts/check_module_size.py
python scripts/check_private_files.py
git diff --check
git add genomeos/validation/heterogeneity_oracle.py genomeos/validation/heterogeneity_dependence.py tests/test_heterogeneity_dependence.py docs/research/population-heterogeneity-dependence-2026-09-10.md
git diff --cached --name-only
python scripts/check_private_files.py
git commit -m "feat: add independent posterior-dependence reference" -m "Advances #211 and #189; no completed calibration study claim."
```

### Task 2: Four-draw randomized ranks and discrete null reference

**Files:** Create `genomeos/validation/sbc_ranks.py` and `tests/test_sbc_ranks.py`.

**Interfaces:** Standalone pure functions, no production or Task1 imports:

```python
def randomized_rank(truth: float, draws: Sequence[float], *, seed: int) -> int: ...
def rank_ecdf_statistic(counts: Sequence[int]) -> int: ...
@dataclass(frozen=True)
class RankNullReference:
    sample_size: int
    seed: int
    statistics: tuple[int, ...]
@dataclass(frozen=True)
class RankTestResult:
    counts: tuple[int, ...]
    statistic: int
    p_value: float
    bonferroni_p_value: float
def simulate_rank_null(*, sample_size: int, replicates: int, seed: int) -> RankNullReference: ...
def test_rank_uniformity(ranks: Sequence[int], *, reference: RankNullReference) -> RankTestResult: ...
```

Function name `test_rank_uniformity` must not accidentally be pytest-collected
when imported: tests import its module alias, not a bare test_* symbol.
Reference constructor validates positive non-Boolean sample_size, nonnegative
seed, nonempty integer statistics each0..4N; normalize immutable tuples.
All counts are exactly five nonnegative integers with positive total. Rank
samples are nonempty integers0..4 and must have length exactly reference N.
Sampler null defaults are not inferred: callers supply all arguments, future
study uses N512,100000replicates and its frozen null seed.

- [ ] **Step 1: Write failing exhaustive and literal-tie tests.**

```python
@pytest.mark.parametrize("n,expected",[
    (1,{2:1,3:2,4:2}), (2,{2:2,3:6,4:9,6:6,8:2}),
])
def test_exact_small_n_null(n, expected):
    observed = Counter()
    for ranks in itertools.product(range(5), repeat=n):
        counts = tuple(ranks.count(k) for k in range(5))
        observed[sbc.rank_ecdf_statistic(counts)] += 1
    assert dict(observed) == expected
```

Ranks have exact endpoints0/4 when truth below/above every draw; all tied draws
use an integer0..4 from the declared seeded generator. Partial ties use their
exact number less/tied. A nextafter difference is strict, not approximately tied.
Fixed seed repeats exactly; changing seed changes the all-tie sequence across
a deterministic set of seeds (do not impose a distributional frequency gate).
Reject Boolean/NaN/Inf/malformed values, wrong draw count and bad seeds.
Run `python -m pytest tests/test_sbc_ranks.py -q`; record genuine initial RED.

- [ ] **Step 2: Implement integer null and inclusive p-values.**

```python
rng = np.random.default_rng(seed)
rank = less + int(rng.integers(0, tied+1))
statistic = max(abs(5*sum(counts[:k+1])-n*(k+1)) for k in range(4))
p_value = (1+sum(t >= observed for t in reference.statistics))/(1+len(reference.statistics))
adjusted = min(1.0,12*p_value)
```

Generate null via NumPy multinomial(N,(.2,)*5,size=replicates), not continuous
uniform/KS. Preserve the seed and all integer statistics. Use Python integer
arithmetic for T; reject unreasonable overflow inputs before passing N to
NumPy (sample_size<=1_000_000, replicates<=1_000_000), no silently capped values.
Do not allow incomplete ranks to use a full-study null. Refuse nonfinite/corrupt
reference values rather than repairing them.

Test deterministic generation against a directly seeded literal multinomial
fixture, exact inclusive tie p-values, minimum plus-one p, adjusted cap1,
wrong-N rejection and immutable input/result handling. The tiny exhaustive
reference tests are not claims that the future study has passed.

- [ ] **Step 3: Run covering tests, gates and commit.**

```bash
python -m pytest tests/test_sbc_ranks.py -q
python scripts/smoke.py
ruff check .
python scripts/check_module_size.py
python scripts/check_private_files.py
git diff --check
git add genomeos/validation/sbc_ranks.py tests/test_sbc_ranks.py
git diff --cached --name-only
python scripts/check_private_files.py
git commit -m "feat: add discrete simulation-calibration rank checks" -m "Advances #211 and #189; no actual study executed."
```

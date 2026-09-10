# B0H independent synthetic-generation evidence

Date: 2026-09-10. Advances #211 and #189. Implements Atlas design
§§5, 7–8, and 12 and the frozen B0H generation design. This freezes a
generator and its unit evidence; it is not an executed calibration study or a
sampler-passing claim.

## Scientific contract and implementation

The objective is to generate known-truth allele counts independently of the
fitted B0H likelihood, including ordinary beta-binomial, deliberately shared-
history, boundary, and structurally unavailable cases. The public facade is
`genomeos.validation.heterogeneity_simulation`; immutable case/result contracts
and their joint validation live in `heterogeneity_simulation_types`. Sampling
depends inward on those contracts and neither module imports fitting, scoring,
quadrature, storage, HTTP, environment, filesystem, or UI code.

The first readable single-module draft was about 610 logical lines/37 KiB. The
controller ruled that sampling and contracts should be split, then retained the
cohesive contract module as a documented exception to the preferred 500-line
target rather than compress or drop joint validation. After fix review, the
sampling module is 418 logical lines/16,449 bytes; the final contract module is
764 logical lines/36,493 bytes. Both remain below the hard 800-line/50-KiB gate.

Protocol is `b0h_sbc_v1`; algorithm is `b0h_generation_v1`; the bit generator is
PCG64 with float64 arithmetic and `SEED = 42`. Entropy is exactly
`(42,211,1,track,study,case,replicate,purpose,attempt)`. Purposes 0–3 use
attempt 0 and the scientific-generation track; purpose 4 alone is collapsed to
one uint32 fit seed and permits attempts 0–1. Prior cases use their fit track;
fixed stress cases use shared generation track 99. Literal first/last fit-seed
anchors, both retries, and both tracks are unit-tested.

Every used stream is a fresh `Generator(PCG64(SeedSequence(entropy)))`; calls
are scalar and omit `size`. Prior truth draws mean then rho. Ordinary cases draw
all 16 population frequencies before 16 training counts, then the heldout
frequency and count. Shared cases visit B0, its eight V/U row pairs, B1, and its
eight V/U pairs before any count. Their heldout stream draws V0/U0/count,
followed by fresh B2/V2/U2/count. A switch uses its cluster only when
`U < sqrt(1/2)`, so exact equality selects V. Rho-zero cases omit Beta and shape
work but still call Binomial for all 16 training rows and the heldout.

Synthetic labels encode the generation ID and distinguish every training and
heldout record/group. Region is `synthetic_nonspatial`; variant group is
`synthetic_single_variant`. No coordinate, radius, resident-population meaning,
or cross-variant independence claim is introduced. Paired fit tracks reuse the
same stress-generation rows while retaining distinct fit seeds.

## Refusal and endpoint evidence

AN=0 rows remain explicit `ReferenceCount(ac=0, an=0)` records. Their latent
frequency is retained separately and is never interpreted as frequency zero.
Study 3 returns 16 such rows before constructing any RNG; it has no truth,
heldout, or sampler call.

Machine Beta endpoints are valid latent draws and are forwarded unchanged to
Binomial. Endpoint counters inspect all retained raw latent Beta values: 17 in
ordinary interior construction, 21 in shared construction, and zero at rho
zero. Shared B0 is counted once even when the cluster-0 heldout reuses it, and
unselected V candidates remain counted. Prior truth endpoints instead produce
`rounded_prior_boundary`. Invalid/nonfinite/nonscalar RNG values, invalid Beta
shapes, and invalid counts produce a typed failure with exact stage and index;
no partial rows are returned. ValueError, FloatingPointError, and OverflowError
from an individual RNG call become `rng_exception`; RuntimeError, MemoryError,
and subclasses of the three admitted built-ins propagate for the later runner
to resolve. Failure construction enforces the exact case/truth/stage/index
table, closed exception names, and mutually exclusive exception/scalar shape
evidence. Invalid prior integer returns remain exact `float | int | None`
candidate evidence, including integers beyond binary64 precision or range.
For downstream `invalid_rng_scalar` artifacts, non-null evidence must also fail
the actual operation domain: Beta values use finite supported `[0,1]`, switches
use `[0,1)`, and counts use the index-specific integral Binomial range. Thus a
float count such as `10.0`, switch value `1.0`, nonfinite or out-of-range value,
and huge exact integer remain valid failure evidence, while a valid return may
not certify a numerical refusal. There is no redraw or successful-subset path.

## Shared-history derivation

Let `s = sqrt(1/2)` and let each independent Beta source have CDF F, mean m,
and variance `sigma^2 = m(1-m)rho`. Each row selects its cluster source with
probability s and otherwise its fresh candidate. Its marginal CDF is therefore
`sF + (1-s)F = F`. Two rows in the same cluster share random variation only
when both select B, so

`Cov(Q_i,Q_j) = s^2 sigma^2 = sigma^2/2`.

Conditional independent Binomial sampling gives count covariance
`n_i n_j sigma^2/2` and marginal variance
`n_i m(1-m)(1+(n_i-1)rho)`. Thus latent correlation is one half, but count
correlation is not generally one half and is undefined for AN=0. For the exact
anchor `m=rho=1/2, n=2`, latent variance is 1/8, latent covariance 1/16,
the count PMF is `(3/8,1/4,3/8)`, count variance is 3/4, covariance is 1/4,
and correlation is 1/3. Fraction arithmetic checks this derivation; controlled
source-selection fixtures check the implemented mechanism without Monte Carlo.

## Executed evidence and limits

TDD RED was the focused test file before either production module existed. The
actual collection failure was `ImportError: cannot import name
'heterogeneity_simulation' from 'genomeos.validation'`. The final focused
command used the locked Python and required isolated environment:

```text
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor \
MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib \
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python \
  -m pytest tests/test_heterogeneity_simulation.py -q
```

The initial implementation passed 61/61 cases. Fix-round RED on the expanded
focused file produced 6 failures and 59 passes: an admitted-exception subclass
was serialized, huge integer candidates overflowed, `2**53+1` candidates were
rounded, and impossible failure artifacts were accepted. A supplemental RED
constructor test produced 1 failure for positive finite shape evidence. Final
GREEN, run with `-o addopts=''` so pytest printed its count, reported `67 passed
in 0.60s`.

The same final environment ran `python scripts/smoke.py`, which reported
`contract up to date`, 40 passing smoke cases, and `smoke checks passed`. Locked
`ruff check .` reported `All checks passed!`; module-size reported `module-size
check passed (75 modules)`; privacy reported `private-file check passed (703
tracked files)`; and `git diff --check` exited zero without output. Fixtures
independently reconstruct one fixed and one prior realization from literal
PCG64 entropies, verify shared stream order and selection, explicitly exhaust
all 16 training plus one rho-zero/boundary heldout Binomial calls, preserve huge
integer evidence, enforce the failure-state table, and check endpoint accounting,
AN=0 behavior, all failure stages, immutability, paired-track reuse, and order
independence.

Final-review TDD added two constructor tests. The targeted RED command reported
`1 failed, 1 passed in 0.58s`: contradictory valid downstream evidence was
accepted while legitimate invalid evidence already remained accepted. Targeted
GREEN reported `2 passed in 0.55s`; the complete focused generator file then
reported `69 passed in 0.57s`. Final smoke again reported current contracts, 40
dots and `smoke checks passed`; Ruff, module-size, privacy and whitespace gates
all exited zero. The controller's earlier `1389 passed, 17 skipped` full-suite
run predates this final-fix commit and is not evidence for the corrected head.

These checks do not establish exact mathematical continuous draws from NumPy,
sampler calibration, convergence, timing, demographic realism, biological
independence, geographic validity, real-data performance, external validation,
or promotion eligibility. The frozen runner, actual prior/SBC execution,
negative controls, and real B0H comparison remain separate required work.

# Local CuGen LD preflight — September 9, 2026

**Implementation target:** the owner's `/Users/bschilder/code/cugen` checkout, clean at `03df1688abf52d295bd85d47f1aca6130440b553`, package version `0.1.7`. No pg_gpu substitution. This advances the WP6 admission investigation in [#189](https://github.com/bschilder/genomeOS/issues/189); no genomeOS LD adapter or GPU LD benchmark has been implemented yet.

**Scientific objective:** establish the selected library's genotype-correlation semantics before feeding training-only LD into a joint allele-frequency model. **Measurable output:** explicit pair identity, co-observed counts and independent-reference agreement, followed later by GPU parity, full-workflow cost and held-out predictive benefit. **Interface:** CuGen's existing `cugen.ld.ld_matrix`, wrapped later by an offline, versioned genomeOS adapter. **Refusals:** no marginal-AF-to-LD inference, unknown genotype encoding, invented sample mapping, missing annotation, silent missing-as-reference conversion or unauthorized data movement.

## Inspection and executable evidence

Read the local README, package configuration, `ld.py` module documentation and public `ld_matrix` implementation through its backend dispatch, relevant LD tests, the complete test fixture module, and writer encoding documentation. This is source inspection, not a claim to have read the entire CuGen codebase or its publisher-blocked paper.

**Later September 9 update:** the full article was subsequently obtained through Europe PMC and read. The [full-text methods note](cugen-fulltext-notes-2026-09-09.md) records its exact snapshot, inspected sections and missing supplementary material. It does not change the executable scope of this preflight.

Twelve existing CPU tests passed, **zero skips**, in 0.11 seconds under Python 3.12.13, NumPy 2.4.6, SciPy 1.18.1 and pandas 3.0.5. They exercise:

- correlation against NumPy and internal r/r-squared consistency;
- exact contingency counts and pairwise-complete missingness;
- co-observed counts with and without missing calls;
- window pair identity, local-row selection and nonvacuous allele-sign flips;
- monomorphic-pair omission, unsupported encoding and an allocation guard.

The run emitted **70 `Pandas4Warning` warnings** from `cugen/ld.py:582`: its `astype(..., copy=False)` uses a keyword deprecated under pandas 3.0 Copy-on-Write. This preflight is not warning-free. No library code or shared environment was changed. Existing upstream fixture seeds were retained; no new stochastic implementation was added.

Reproduction command (create a fresh temporary directory first; replace only the temporary path):

```bash
cd /Users/bschilder/code/cugen
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/bschilder/code/cugen \
MPLCONFIGDIR=/private/tmp/genomeos-cugen-preflight.RAuhlh/matplotlib \
/Users/bschilder/code/genomeOS/.venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp=/private/tmp/genomeos-cugen-preflight.RAuhlh/pytest \
  --junitxml=/private/tmp/genomeos-cugen-preflight.RAuhlh/cpu-ld-tests.xml \
  tests/test_ld.py::test_r_matches_corrcoef \
  tests/test_ld.py::test_r2_internal_consistency \
  tests/test_ld.py::test_counts_are_exact_integers \
  tests/test_ld.py::test_pairwise_complete_case \
  tests/test_ld.py::test_n_obs_equals_n_samples_without_missing \
  tests/test_ld.py::test_window_pairs_emitted_exactly_once \
  tests/test_ld.py::test_variant_range_selects_rows \
  tests/test_ld.py::test_sign_reference_major_flips_exactly_the_right_pairs \
  tests/test_ld.py::test_monomorphic_variant_is_dropped \
  tests/test_ld.py::test_plink2_n_obs_matches_pairwise_complete \
  tests/test_ld.py::test_non_2bit_encoding_raises \
  tests/test_ld.py::test_max_pairs_guard_raises_before_decode
```

Generated files and JUnit remain outside Git. Bytecode writes and pytest's repository cache were disabled. The selected tests synthesize inputs or use the repository's tiny fixtures and perform no network requests. This was **not** a rerun of CuGen's complete suite, GPU kernels, live PLINK, or real-data accuracy benchmarks.

## Integration requirements established by inspection

1. **Choose the statistic explicitly.** Request `stats=("r", "r2")`, `sign_reference="alt"`, `missing="pairwise"` and an explicit backend. The default statistic list also requests D/D-prime, which adds a different estimation problem and unnecessary work. A NumPy path in the same library is useful cross-backend evidence but does not replace an independently formulated reference.
2. **Keep encodings distinct.** This LD path requires `ENCODING_2BIT=0`, unphased hard calls with missing code 3. CuGen also supports a separate `ENCODING_HAP2BIT=4` for phased haplotypes elsewhere; this LD function rejects nonzero encoding. The same packed bits have different meanings. Do not infer universal phase support or absence from the filename extension.
3. **Subset samples before LD.** `ld_matrix` has variant selectors but no sample selector. Training/cohort-specific LD therefore needs a separately materialized sample subset with an explicit identity manifest. CuGen's public subset API is the next inspection target; the writer documentation states that per-variant statistics must be recomputed after sample subsetting. Its implementation has not been validated by this preflight.
4. **Validate annotations before calling.** Local row indices, global `gidx`, chromosome positions and allele orientation are distinct. The inspected annotation lookup can substitute position zero for a missing mapping; genomeOS must instead require complete, unique, correctly typed annotation before invoking it. No such permissive behaviour should enter the genomeOS science contract.
5. **Account for omitted pairs.** Monomorphic or insufficiently co-observed pairs may be dropped. Preserve requested versus emitted pair sets and explicit exclusion reasons; do not fill absent correlation entries with zero. Pairwise-complete correlations do not automatically form a positive-semidefinite joint matrix.
6. **Measure the complete operation.** Include sample/variant selection, conversion, statistics recomputation, reading, transfers, GPU setup and output serialization. Window limits and pair limits must be explicit. Bounded device tiling does not by itself bound total output size or whole-genome all-pairs work.

The next CuGen experiment must use pinned local code and synthetic training/test identities, then validate an approved real-data block only after source/access qualification. Any later geographic gain must be tested without leaked local genotypes; gains from held-out-variant imputation remain a separate target. These CPU results establish a useful starting point, not worldwide allele-frequency improvement.

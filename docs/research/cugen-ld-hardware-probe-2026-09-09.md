# CuGen GPU LD diagnostic — September 9, 2026

## Scientific contract and result

Objective: test whether the owner's pinned CuGen can supply correctly identified, training-only
unphased ALT-genotype correlations for a later multivariant AF experiment (design §7–§8;
[WP6 / #195](https://github.com/bschilder/genomeOS/issues/195)). Acceptance evidence is exact
sample/pair identity and counts, independent numerical agreement, and held-out-mutation
invariance. The interfaces exercised are public `cugen.write.write_cugen`,
`cugen.subset.subset_cugen_file` and `cugen.ld.ld_matrix`, outside the serving path.

**Result: hand-fixture subsetting and LD pass; general GPU precision admission fails.** Two
fresh-process runs reproduce four near-fixed-allele R-budget failures, including two R2-budget
failures. Every corresponding CuGen CPU result passes. This is synthetic engineering evidence,
not an AF accuracy benchmark, production integration, joint-covariance qualification or permission
to export population data. The downstream consumer is the still-incomplete pilot, not the map.
The numerical defect is tracked in [#205](https://github.com/bschilder/genomeOS/issues/205).

## Exact implementation and environment

CuGen 0.1.7 at clean revision `03df1688abf52d295bd85d47f1aca6130440b553`, from the
owner-requested local checkout; no pg_gpu. CuGen source was not modified. The source-only bundle
contained 34 tracked Python files plus LICENSE, README and pyproject, with all 37 extracted
file hashes checked. Bundle SHA256:
`d796a16a633264c14314286c5ed89e3436ca14ee9f626ac8bfd3c2a1cc7943f4`.

RunPod Secure Cloud, US-MD-1, one NVIDIA A100-SXM4-80GB; driver 580.126.16, CUDA runtime API
12090 and driver API 13000, CuPy CUDA12x 14.2.0. Isolated Python 3.12.3 environment: NumPy 2.4.6,
pandas 3.0.5, SciPy 1.18.1, PyArrow 25.0.1, python-dateutil 2.9.0.post0, six 1.17.0,
cuda-pathfinder 1.8.1. The environment did not inherit genomeOS dependencies.

Fresh-process controls before CuPy/CuGen import: `CUPY_TF32=0`, `NVIDIA_TF32_OVERRIDE=0`,
`USE_PINNED_READER=0`. These are recorded controls, not an instruction-level math-mode
measurement. The selected annotated/nonfused path resolves the precision argument but does
not receive the resolved `use_tf32` value at its dispatch boundary; do not infer execution mode
from `precision="fp32"` alone.

Both runs use seed 42 (the fixtures themselves are deterministic), encoding 0 diploid unphased
hard calls, missing code 3, explicit gidx/CHR/POS/ID annotation, ALT sign, pairwise missingness,
`min_obs=2`, `maf_min=0`, `min_r2=0`, `stats=("r","r2")`, no index or base-pair window,
pairs output with `output=None`, `tile_size=2`, `max_pairs=21`. No biological identity is inferred
from the synthetic labels. Initial precision budgets were fixed before hardware execution:
absolute R error <= 1e-5; R2 error <= 2e-5. They were not changed after seeing failures.

## Training-only subsetting and hand fixture

Eight synthetic people by seven synthetic variants, with file-row gidx `[30,10,70,20,60,40,50]`:

```text
[[0,0,2,3,1,0,3], [1,1,1,3,1,3,3], [2,2,0,3,1,2,3], [0,2,0,3,1,3,0],
 [2,0,2,3,1,1,1], [1,2,0,3,1,2,3], [0,1,1,3,1,0,0], [2,0,2,3,1,2,3]]
```

Annotation has chromosome 1, positions `101+100*i` and IDs `synthetic-i` in file-row order.
GPU subsetting explicitly selects int64 rows `[4,0,2,1]`, `chunk_size=2`, `use_pinned=False`.
Independent header/offset/bit decoding checks every output call, gidx, actual sample count,
missingness flag and recomputed mean, centered sum of squares and MAF. Storage budgets were
mean absolute 2e-7, MAF absolute 1e-7, sxx absolute `1e-5*max(1, reference_sxx)`; the selected
hand fixture's stored statistics match exactly.

Independent integer co-observed sums classify all 21 requested pairs: six valid correlations,
11 insufficient pairs and four zero-variance pairs (insufficient classification takes priority).
Returned pair identities, CHR/POS/ID and N_OBS all match exactly. Omitted undefined pairs are
reconciled explicitly, not interpreted as zero correlation. Maximum GPU absolute errors:
R 5.960464477539063e-8, R2 1.1920928955078125e-7.

Changing all held-out rows `[3,5,6,7]` to `(calls+1)%4` changes the source bytes but leaves the
training subset and every CPU/GPU LD value unchanged. Both training files have SHA256
`d6e76b55abb74f8fbf0fd8999bf205295dce433a19fbadef4c54086a7c8d6011`.
This tests isolation for this explicit selection, not arbitrary cohort mapping or all leakage paths.

## Precision stress cases and minimal reproducer

For each n in 3072/4096, X is dosage 2 except X[0]=1. Y is dosage 2 except either Y[1]=Y[2]=1
(disjoint) or Y[0]=Y[1]=1 (overlapping). Repeat each case after flipping both variants to `2-G`;
the mathematical correlation is unchanged. The independent reference uses exact integer
`n*sum_xy-sum_x*sum_y` and variances, with float64 square-root/division only at the end.

| n | Rare calls overlap | Reference R | CuGen GPU R | GPU absolute R2 error |
|---|---|---|---|---|
| 3072 | no | -0.0004605808764446619 | 0 | 2.121347437465329e-7 |
| 3072 | yes | 0.706991645342556 | 0.7073370218276978 | 4.884931948782589e-4 |
| 4096 | no | -0.0003453934724429183 | 0 | 1.1929665080617694e-7 |
| 4096 | yes | 0.7070204380906536 | 0.7072794437408447 | 3.663003517450081e-4 |

All four original-code GPU cases fail R; the overlapping cases also fail R2. All four
double-flipped GPU controls and all eight CPU controls pass. Maximum CPU R error is
2.7173313155159917e-8. Both runs exit 2 with four budget failures, not success with hidden skips.

With the pinned package and environment above, set the three controls before starting Python:

```python
from pathlib import Path
from tempfile import mkdtemp
import numpy as np
import pandas as pd
from cugen.write import write_cugen
from cugen.ld import ld_matrix

calls = np.full((3072, 2), 2, dtype=np.uint8)
calls[0, 0] = 1
calls[[1, 2], 1] = 1
path = Path(mkdtemp(prefix="cugen-ld-repro-")) / "synthetic.cugen"
write_cugen(path, calls, gidx=[30, 10], encoding=0)
annotation = pd.DataFrame({"gidx": [30, 10], "CHR": ["1", "1"],
                           "POS": [101, 201], "ID": ["synthetic-0", "synthetic-1"]})
for backend in ("numpy", "gpu"):
    print(backend, ld_matrix(
        path, annotation=annotation, backend=backend, precision="fp32",
        stats=("r", "r2"), sign_reference="alt", missing="pairwise",
        min_obs=2, maf_min=0, min_r2=0, window=None, window_kb=None,
        output_format="pairs", output=None, tile_size=2, max_pairs=21,
        verbose=False))
```

Expected: CPU R -0.0004605808644555509, GPU R 0, both N_OBS 3072. This minimal excerpt
reproduces the numerical defect; it is not the full diagnostic runner or a production adapter.

## Mechanism and limits

Pinned `ld.py:2078` computes correlations from float32 raw moments in `_r_block`. A separate
on-device experiment checks every raw sum, square sum and matrix product against exact int64
values for the four original-code inputs: all are exact before covariance/variance subtraction.
Float32 produces covariance numerators 0/3072/0/4096 instead of -2/3070/-2/4094 in table order.
Widening those moments before products/subtraction recovers reference R within 1.12e-16.

This localizes the demonstrated loss, but is **not a general fix**: at greater sample counts,
accumulation itself can be inexact. No CuGen patch, hidden allele recoding, CPU fallback,
private-function monkeypatch, tolerance relaxation or production precision policy was adopted.
Correctness must precede speed comparisons; the timings in these logs are diagnostics, not
controlled full-workflow throughput benchmarks.

The warnings captured by each call are retained in the logs, including pandas deprecations and
the CPU reader ResourceWarning tracked separately in [#201](https://github.com/bschilder/genomeOS/issues/201).
Empty stderr does not mean warning-free: the diagnostic catches and records warning categories.
Runtime timings differ between runs, but removing only `elapsed_seconds` and `wall_seconds`
from the JSON objects yields identical complete records. Repeats check reproducibility, not
independent sampling or statistical replication.

## Artifacts and operational correction

Frozen synthetic-only output logs:

- [Initial run](cugen-ld-hardware-initial-03df168.jsonl), SHA256
  `a815dce803f02e850abf2c9547ce3f133d520826e61ba697fd404fdef24cfc70`.
- [Fresh-process repeat](cugen-ld-hardware-repeat-03df168.jsonl), SHA256
  `0fae9a7842e62a1b633ee25c3608aa42dcc2840010d44a2daa5a3f22213a0c45`.
- [Moment-isolation experiment](cugen-ld-moment-diagnostic-03df168.jsonl), SHA256
  `2cf3fac25c75033ffe4e298506104241723576a49db052985a8e42fcc12f6355`.

Original full diagnostic script SHA256:
`4210c9b69a91d014bc1bd740db05c4f4f8d84b94a2a535f0f4b3f70ea8f51488`.
The full script and binary fixtures remain local research scratch, not committed production
tools or publicly available artifacts. The minimal reproducer and input definitions above are
provided separately. All retrieved binary/log hashes matched their remote counterparts before
the disposable task pod was deleted. No real genomes, credentials or private checkout history
were uploaded. No active task-owned CuGen pod remains from this diagnostic.

The allocation failure was initially overgeneralized. RunPod's [live v2 API contract](https://api.runpod.io/v2/openapi.json)
states that create places one GPU type and does not try other types. Earlier requests passed
lists beginning with RTX 4090, assuming fallback; they did not establish absence of capacity
across those alternatives. An explicit singleton A100 request succeeded in US-MD-1 at $1.59/h;
a singleton A40 request there failed. The MCP's exact list translation was not observed, so
the first-element explanation remains an inference. Future fallback must explicitly attempt
individual GPU/DC candidates. The approximately eight-minute pod lifetime implies about $0.22
at the quoted compute rate; this is an estimate, not an invoice.

Remaining before #195 admission: typed fail-closed wrapper, validated precision implementation,
padding/chunk/tile/missingness boundary coverage, conservative host/device memory checks,
immutable completed-artifact validation and complete workflow benchmarking. Any later
resident-AF improvement requires its own sealed geographic/cohort benchmark.

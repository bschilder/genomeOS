# Synthetic count-scoring GPU probe

September 9, 2026; [research program #189](https://github.com/bschilder/genomeOS/issues/189).

## Question and interpretation

Can the beta-binomial special-function/reduction workload benefit from GPU batching without
changing count-distribution mathematics? This tests one batched lower-tail log-CDF primitive,
not the complete `CountPredictive` interface, its intervals/PIT, a fit, or model accuracy.
The CPU and GPU evaluate the same vectorized expression; comparison to the existing Python
per-draw loop would additionally confound algorithmic batching with hardware acceleration.

The result supports implementing and testing a complete optional GPU path. It does **not** yet
establish a full-workflow speedup, correctness at all supported boundaries, calibration, or a
reason to replace the CPU reference.

## Measured result

Synthetic seed 42; 2,048 predictive draws; 1,024 support terms per draw; AN=2,048; concentration
20; means uniform on [0.01, 0.99]; float64 throughout. CPU and GPU ran on the same RunPod host.
The arrays and source code were generated for this experiment; no genomic observations,
restricted files, GitHub tokens or cloud credentials were uploaded.

| Measurement | Seconds |
| --- | ---: |
| CPU first call | 0.132681479 |
| GPU first call, including transfer/context/kernel setup | 3.003719383 |
| CPU warm median, five repeats | 0.130375935 |
| GPU warm median, including input/output transfers and synchronization | 0.001190273 |
| GPU kernel-only median, CUDA events | 0.000705088 |

The warm transfer-inclusive ratio is approximately 109.5x for **this primitive**. The first GPU
call is substantially slower than the first CPU call. Imports, package installation, pod startup
and synthetic input generation are outside these function timings. Warm-up does not imply these
costs disappear from a short-lived workflow. CUDA event timing and synchronization follow
[CuPy's benchmarking guidance](https://docs.cupy.dev/en/stable/user_guide/performance.html).

Maximum absolute difference between GPU and SciPy log-CDF results: `2.5357493882438575e-12`.
The predeclared comparison `rtol=1e-10, atol=1e-10` passed. This tolerance applies to these
log-CDF values, not an assertion of zero error or correct handling of arbitrarily tiny tails.
CuPy memory-pool reservation after the run was 67,174,912 bytes; this is a pool reservation
measurement, **not** a profiled peak-live-memory measurement.

Raw warm measurements in seconds:

- CPU: 0.1311939809, 0.1303759350, 0.1303947320, 0.1302227640, 0.1300732900.
- GPU including transfer: 0.0012129860, 0.0011785210, 0.0011750240, 0.0011949519, 0.0011902731.
- GPU kernel: 0.0007124160, 0.0007050880, 0.0007168000, 0.0007011840, 0.0006977600.

## Environment and resource lifecycle

A100-SXM4-80GB in US-MD-1, NVIDIA driver 580.126.16; image
`runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`. Python 3.12.3, NumPy 2.4.6,
SciPy 1.18.1, CuPy CUDA-12 wheel 14.2.0, cuda-pathfinder 1.8.1.
CuPy's published compatibility table does not yet list SciPy 1.18; this probe verifies only the
specific primitives exercised here, not broad API compatibility.

The image's system Python refused global installation under PEP 668. A separate disposable
virtual environment was created; system-package protections were not bypassed. The local project
environment, dependency declarations and lock file were not changed for the probe.

Task-owned pod `9xmlq8m0bmhekl` started at 06:21:20 UTC, was stopped at approximately 06:24:33
UTC and then deleted successfully (HTTP 204). Quoted compute was $1.59/hour; roughly 193 seconds
corresponds to an estimated $0.09, not an account invoice or an exact storage-inclusive bill.
Only its disposable environment and synthetic temporary arrays were removed. No other pod was
modified, and no scientific input or output was lost.

## Reproduce the primitive

In an isolated Python 3.12 environment on a CUDA-12-capable GPU host:

```bash
python -m pip install numpy==2.4.6 scipy==1.18.1 cupy-cuda12x==14.2.0 cuda-pathfinder==1.8.1
```

Run this exact probe code. Production integration must additionally test heterogeneous AN,
counts/means at boundaries, tiny/complementary tails, bounded-memory chunking, unsupported input
refusal, full interval/PIT parity, missing-device errors and complete transfer-inclusive workflow
cost. Do not install GPU-only dependencies on the serving path.

```python
import json,time,platform
import numpy as np
import scipy
from scipy import special as sp
import cupy as cp
from cupyx.scipy import special as csp
rng=np.random.default_rng(42)
n=2048
a=rng.uniform(.01,.99,(2048,1))*20
b=20-a
k=np.arange(1024,dtype=np.float64)[None,:]
def kernel(xp,special,ka,aa,bb):
    mass=special.gammaln(float(n+1))-special.gammaln(ka+1)-special.gammaln(n-ka+1)+special.betaln(ka+aa,n-ka+bb)-special.betaln(aa,bb)
    return special.logsumexp(mass,axis=1)
t=time.perf_counter()
reference=kernel(np,sp,k,a,b)
first_cpu=time.perf_counter()-t
t=time.perf_counter()
ka,aa,bb=[cp.asarray(x) for x in (k,a,b)]
device=kernel(cp,csp,ka,aa,bb)
result=cp.asnumpy(device)
cp.cuda.Stream.null.synchronize()
first_gpu=time.perf_counter()-t
np.testing.assert_allclose(result,reference,rtol=1e-10,atol=1e-10)
cpu_times=[];gpu_times=[];kernel_times=[]
for i in range(5):
    t=time.perf_counter();kernel(np,sp,k,a,b);cpu_times.append(time.perf_counter()-t)
    cp.cuda.Stream.null.synchronize()
    t=time.perf_counter()
    ka,aa,bb=[cp.asarray(x) for x in (k,a,b)]
    result=cp.asnumpy(kernel(cp,csp,ka,aa,bb))
    cp.cuda.Stream.null.synchronize()
    gpu_times.append(time.perf_counter()-t)
    start,end=cp.cuda.Event(),cp.cuda.Event()
    start.record();kernel(cp,csp,ka,aa,bb);end.record();end.synchronize()
    kernel_times.append(cp.cuda.get_elapsed_time(start,end)/1000)
report=dict(kind="synthetic_primitive_probe_not_full_diagnostics",python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,cupy=cp.__version__,gpu=cp.cuda.runtime.getDeviceProperties(0)["name"].decode(),dtype="float64",draws=2048,support_terms=1024,AN=n,seed=42,concentration=20,cpu_cold_seconds=first_cpu,gpu_cold_including_transfer_seconds=first_gpu,cpu_warm_seconds=cpu_times,gpu_warm_including_transfer_seconds=gpu_times,gpu_kernel_seconds=kernel_times,max_absolute_log_cdf_error=float(np.max(np.abs(result-reference))),gpu_pool_reserved_bytes=cp.get_default_memory_pool().total_bytes(),tolerance_rtol=1e-10,tolerance_atol=1e-10)
print(json.dumps(report,sort_keys=True),flush=True)
```

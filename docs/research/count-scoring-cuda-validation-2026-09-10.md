# Actual CUDA verification of the count-scoring repair

Follow-up to #209 and [PR210](https://github.com/bschilder/genomeOS/pull/210),
Atlas design §§7–8. This resolves the previously outstanding hardware check
for science revision `92659aa6999b04652fd0c3208c1e0836c96832a6`.
It does not change the twelve CPU baseline results or establish better AF
prediction, publication eligibility, or a general speedup.

## Scope and execution

Only seven exact public source/test files and the historical CuPy backend
were transferred. No reference-panel counts, individual genotypes, credentials,
private history or model artifacts were included.

The earlier source-transfer request was denied. After the source was publicly
pushed, an anonymous audit returned HTTP200 and exact byte equality for every
payload member and its Git blob. A single same-channel automatic approval
re-review disclosed the prior denial and the changed public-source evidence;
it approved the unchanged payload. The earlier unanswered user question was
not treated as consent, and no alternate transport bypassed the denial.

The new task pod `pgngkpcx8t29nd` ran an NVIDIA A40 in CA-MTL-1, created
2026-09-10 03:37:23.238 UTC. CUDA preflight executed a float64 sum-of-squares
kernel with the exact expected result1240 and explicit synchronization.
Runtime: Python3.12.3, NumPy2.4.6, SciPy1.18.1, pandas3.0.5, pytest8.4.2,
CuPy14.2.0, CUDA runtime12090, driver580.159.04, compute capability8.6.

## Results

| Check | Result |
| --- | --- |
| Final predictive CPU and GPU test modules |128passed,0failed,0errors,0skipped; JUnit84.968s |
| Historical hybrid: old CuPy backend, final regression tests |2expected failures,1boundary pass,0skips; JUnit6.543s |
| Small synthetic complete-diagnostic parity probe |Passed all exact/tolerance comparisons |
| Seven integer count-quantile levels |Exactly equal; maximum discrepancy0 |
| Randomized PIT |Maximum CPU/GPU discrepancy5.551115123125783e-17 |
| Integrated log score |CPU/GPU discrepancy0 |
| Seeded replicated counts, interval coverage/width and point errors |Exactly equal |

The historical hybrid replaces **only** predictive_cupy.py with its version
at `6c042c7`; it is not a claimed test of the whole historical checkout.
One failure demonstrates cancellation concealing an invalid component; the
NaN case demonstrates refusal occurring at the aggregate rather than the
required component check. The exact-boundary control still passes.

Final command: `python -m pytest -q -ra tests/test_predictive.py tests/test_predictive_gpu.py`.
The profiler used32draws,2observations,AN20,concentration20,repeats2,seed42.
Its [unaltered machine-readable report](count-scoring-cuda-validation-2026-09-10.json)
retains source hashes, configuration, versions, parity, memory semantics and
timings. This tiny probe establishes correctness at its tested inputs, not
scaling to a full posterior or production panel. GPU startup and warm timing
are distinct; no end-to-end model speedup is inferred.

## Provenance and cleanup

- Profiler report SHA256:
  `b98962215002820b1a366d00e799039156254b65c18fa24099d93824508b29ca`.
- Final JUnit SHA256:
  `111f133ca9186a0513e313bc8a04af16221c140ef613373625cecd58922a1024`.
- Anonymous public-source audit SHA256:
  `0ebc664aea0b11cfcdd04308f269812135b6e8132443c2e26ed30199e7bb28fb`.
- All13retrieved files retained locally;12payload hashes match the remote
  manifest. Final executed source hashes were unchanged and verified.
- An orchestration postcheck initially expected a revision string where the
  existing report contains a revision/provenance object. The failed log was
  retained and the actual contract validated; science, tests and report were
  not changed or rerun to hide that orchestration mistake.
- The pod was deleted by03:46:01UTC; HTTP204 then404 confirmed removal.
  At the quoted$0.49/hour, its elapsed-time compute bound is approximately
  $0.071, excluding any billing-specific/storage charges. This is not an invoice.
- GitHub CI for PR210 independently completed successfully at03:13:18UTC,
  [run34431226958](https://github.com/bschilder/genomeOS/actions/runs/34431226958).
  That CPU/container CI and this CUDA check are separate evidence.

The scientific interface remains CountPredictive; no model, numerical
threshold, production schema or source-data permission was changed.

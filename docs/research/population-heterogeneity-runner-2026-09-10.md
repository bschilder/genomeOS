# B0H runner engineering boundary

This adapter implements the frozen B0H runner design, §§3–8. It advances #211
and #189 without completing the calibration study or baseline comparison.

One local worker owns one SQLite database. START is exclusive stage admission,
not proof that a graph or sampler ran. Exact scientific codec bytes, receipt and
completion publish atomically. An unresolved START is never redelivered.
Only a completed typed convergence failure admits the single scientific retry.

Known live publication bytes remain in one immutable packet. The command pauses
science and retries publication only every 60 seconds for at most 1,800 seconds.
Storage integrity and programming defects are not retryable. Expiry/interruption
reports loss risk and exits nonzero; this is not durable process-loss retention.

Actual source/import origins, JAX/CuPy float64 support, memory observations and
local storage probes precede case execution. Initial mount admission accepts
ext4, xfs, btrfs or tmpfs; tmpfs is volatile. A filesystem name proves no power,
host or Pod-loss durability. Unverified container backing requires investigation
and reviewed pre-case correction, not GPU-capacity fallback.

Closed collection copies the database while campaign exclusion is retained and
publishes database/inventory digests. Evidence consumers independently retain
those digests and supply both to the read-only collected-snapshot reader.
Collected provenance never authorizes execution on another machine. The reader
uses SQLite mode=ro, a stable read transaction, sidecar refusal and before/after
checksums; it does not assert immutable=1.

Reduction accounts for all 1,938 cases, twelve correct-family full-N tests, four
predeclared sensitivity assertions and all remaining control/diagnostic outcomes.
Missing ranks have explicit actual-N counts but no full-N p-value. Missing
predictive evidence blocks unconditional wording. Secondary values have no new
decision thresholds. Linked loci and paired tracks are not independent datasets.

The checked-in tests use synthetic constructor-valid fixtures and counted-call
sentinels. They are engineering evidence, not realized calibration or admission
measurements. Actual verification commands/results belong in the implementing PR
report; this note makes no unobserved test or full-study success claim.

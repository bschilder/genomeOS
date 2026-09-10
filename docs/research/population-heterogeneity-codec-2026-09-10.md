# B0H codec evidence — 2026-09-10

The codec represents seven existing outcome roots using 35 closed records,
canonical version-1 metadata and SHA-256-keyed little-endian float64 payloads.
It advances #211/#189 without completing either issue. The design authority is
the population-heterogeneity codec specification, implementing Atlas §§5,7–8,12.

The acceptance fixtures are literal constructor-valid synthetic records.
Their fitted arrays, diagnostic numbers, reference components, comparison
matrices and ranks are representation fixtures, not realized scientific output.
No NUTS, scoring, reference integration, RNG draw or real-data operation is part
of codec verification. Deterministic seed identity expansion is retained public
validation and does not establish RNG consumption.

Tests require exact field types/values, binary64 bit patterns, array axes,
immutable reconstructed arrays and repeatable canonical bytes. Independent
anchors include signed zero, infinities, distinct NaN payloads, surrogatepass
strings, arbitrary-size integers, literal case metadata and raw array bytes.
Missing/extra fields, malformed nodes, canonicalization defects, budgets and
payload identity errors refuse. Existing scientific constructors remain the
authority for valid scientific record states.

Byte budgets do not bound peak RSS. Metadata is canonical but is not externally
authenticated: self-consistent replacement cannot be detected without an
external metadata anchor. Constructor/runtime compatibility requires a pinned
compatible implementation. The codec establishes no fit/dataset provenance,
calibration, durability, recovery, publication eligibility or full-study result.

## Executed verification

Only commands actually run and their captured results are recorded below.

```text
RED
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec.py
ERROR during collection: ValueError: Exceeds the limit (4300 digits) for integer string conversion.

GREEN / focused dependencies
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec.py tests/test_heterogeneity_codec_wire.py tests/test_heterogeneity_codec_contract.py tests/test_heterogeneity_summaries.py tests/test_heterogeneity_sbc_quantities.py tests/test_heterogeneity_attempts.py tests/test_heterogeneity_simulation.py
404 passed in 13.83s

smoke
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
contract up to date; 40 passed; smoke checks passed

ruff
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
All checks passed!

contract
.../python scripts/freeze_contract.py --check
contract up to date

module size
.../python scripts/check_module_size.py
module-size check passed (85 modules)

privacy
.../python scripts/check_private_files.py
private-file check passed (730 tracked files)
```

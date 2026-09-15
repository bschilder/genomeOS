# Frozen instrumentation for the B0H timing spike

This is the exact disposable instrumentation used for execution
`b0h-timing-20260910-01`, not a supported runner, archival codec or restart
interface. It accompanies the predeclared
[protocol](population-heterogeneity-timing-protocol-2026-09-10.md).
It operates only on synthetic cases and the pinned scientific source. No
production module or test imports this snapshot; it is retained to make the
measurement procedure inspectable. Repeating it is a new timing experiment,
not continuation of the calibration study. Paths and execution label below
are historical literals. They are not general-purpose settings.

The source archive was created with `git archive` at scientific commit
`df0b71dfca1edd2c209abe8f9829cd103feaffdd`, containing `genomeos`, `contract`,
`demo/artifacts`, `requirements.lock`, `pyproject.toml`, `README.md`, the smoke,
environment-report and contract-check scripts, and their synthetic smoke tests
and fixtures. No real observations, credentials or private Git history were
transferred. The source bundle hash is in the protocol.

Hashes of the exact UTF-8 files (including terminal newline):

- `probe.py`: `3800714b6a5bc00fa33cde23f6f4992d16591ff79c0d13aedce9bfc65f2ad61f`
- `setup.sh`: `8bc0e8786e962d0057ea8a02acd34cf545894f0f8736c63a5596bfe6a7dfa7ba`
- `run.sh`: `25ca2b20c44d4ccbab04fdb3f79172ba04b044f158c2ca068bf2026fd9a4a416`

## probe.py

```python
#!/usr/bin/env python3
"""Disposable B0H GPU timing spike; not the durable evidence codec."""

from __future__ import annotations

import argparse
import dataclasses
import importlib.metadata
import json
import os
import platform
import resource
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SOURCE_SHA = "df0b71dfca1edd2c209abe8f9829cd103feaffdd"
EXECUTION_LABEL = "b0h-timing-20260910-01"
CASES = ((0, 0, 0, 0), (1, 0, 0, 0), (0, 0, 0, 1), (1, 0, 0, 1), (0, 0, 0, 2),
         (1, 0, 0, 2), (0, 0, 0, 3), (1, 0, 0, 3))
ENV_NAMES = ("JAX_ENABLE_X64", "JAX_PLATFORMS", "XLA_PYTHON_CLIENT_PREALLOCATE")
PINNED = ("arviz", "jax", "jaxlib", "numpy", "numpyro", "pandas", "pymc", "pytensor", "scipy", "xarray")
def qualified(value: object) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"
def error_record(error: BaseException) -> dict[str, str]:
    return {"class": qualified(error), "message": str(error)}
def debug_string(value: str) -> dict[str, str]:
    return {"tag": "string", "utf8_surrogatepass_hex": value.encode("utf-8", "surrogatepass").hex()}
def rss_observation(point: str) -> dict[str, Any]:
    return {"point": point, "value": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "unit": "KiB"}
class Recorder:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.array_ordinal = 0
    def _write_json(self, path: Path, value: object) -> None:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    def progress(self, message: str) -> None:
        with (self.out / "progress.log").open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    def report(self, value: dict[str, Any]) -> None:
        path = self.out / "report.json"
        temporary = self.out / "report.json.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    def dump(self, case_ordinal: int, stage: str, value: object, np: Any) -> str:
        debug = self.out / "debug"
        debug.mkdir(exist_ok=True)
        path = debug / f"case-{case_ordinal:02d}-{stage}.json"
        self._write_json(path, self._tree(value, case_ordinal, stage, np))
        return str(path.relative_to(self.out))
    def dump_error(self, case_ordinal: int, stage: str, error: BaseException) -> str:
        debug = self.out / "debug"
        debug.mkdir(exist_ok=True)
        path = debug / f"case-{case_ordinal:02d}-{stage}-error.json"
        self._write_json(path, {"tag": "exception", "class": debug_string(qualified(error)),
                                "message": debug_string(str(error))})
        return str(path.relative_to(self.out))
    def _tree(self, value: object, case_ordinal: int, stage: str, np: Any) -> dict[str, Any]:
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                "tag": "dataclass", "class": qualified(value),
                "fields": [{"name": field.name,
                            "value": self._tree(getattr(value, field.name), case_ordinal, stage, np)}
                           for field in dataclasses.fields(value)],
            }
        if value is None:
            return {"tag": "none"}
        if isinstance(value, (bool, np.bool_)):
            return {"tag": "bool", "value": bool(value)}
        if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
            return {"tag": "int", "class": qualified(value), "hex": format(int(value), "#x")}
        if isinstance(value, (float, np.floating)):
            return {"tag": "float", "class": qualified(value),
                    "binary64_be_hex": struct.pack("!d", float(value)).hex()}
        if isinstance(value, (str, np.str_)):
            return {"tag": "string", "utf8_surrogatepass_hex": str(value).encode(
                "utf-8", "surrogatepass").hex()}
        if isinstance(value, tuple):
            return {"tag": "tuple", "items": [self._tree(item, case_ordinal, stage, np)
                                                    for item in value]}
        if isinstance(value, np.ndarray):
            if value.dtype != np.dtype("float64"):
                raise TypeError(f"debug dump only accepts float64 arrays, got {value.dtype}")
            arrays = self.out / "arrays"
            arrays.mkdir(exist_ok=True)
            ordinal = self.array_ordinal
            self.array_ordinal += 1
            path = arrays / f"case-{case_ordinal:02d}-{stage}-{ordinal:04d}.npy"
            with path.open("xb") as handle:
                np.save(handle, value, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            return {"tag": "float64_ndarray", "path": str(path.relative_to(self.out)),
                    "shape": list(value.shape)}
        raise TypeError(f"debug dump refuses unsupported value class {qualified(value)}")
def science_imports() -> tuple[dict[str, Any], int]:
    started = time.perf_counter_ns()
    import cupy as cp
    import jax
    import jax.numpy as jnp
    import numpy as np
    from genomeos.validation.heterogeneity_attempts import plan_fit_attempt, run_fit_attempt
    from genomeos.validation.heterogeneity_sbc_quantities import selected_sbc_quantities
    from genomeos.validation.heterogeneity_simulation import SbcCaseId, generate_sbc_case
    from genomeos.validation.heterogeneity_simulation_types import GeneratedDataset, GenerationFailure
    from genomeos.validation.heterogeneity_summaries import summarize_heterogeneity_fit

    import genomeos
    return {
        "cp": cp, "jax": jax, "jnp": jnp, "np": np, "genomeos": genomeos,
        "plan_fit_attempt": plan_fit_attempt, "run_fit_attempt": run_fit_attempt,
        "selected_sbc_quantities": selected_sbc_quantities, "SbcCaseId": SbcCaseId,
        "generate_sbc_case": generate_sbc_case, "GeneratedDataset": GeneratedDataset,
        "GenerationFailure": GenerationFailure,
        "summarize_heterogeneity_fit": summarize_heterogeneity_fit,
    }, time.perf_counter_ns() - started
def lock_versions(source_root: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (source_root / "requirements.lock").read_text(encoding="utf-8").splitlines():
        name, marker, version = line.partition("==")
        if marker and name in PINNED:
            pins[name] = version
    if set(pins) != set(PINNED):
        raise RuntimeError("requirements.lock is missing a required direct scientific pin")
    actual = {name: importlib.metadata.version(name) for name in PINNED}
    wrong = {name: (pins[name], actual[name]) for name in PINNED if pins[name] != actual[name]}
    if wrong:
        raise RuntimeError(f"scientific package pins do not match requirements.lock: {wrong}")
    return actual
def installed_distribution(module: str, actual_version: str) -> dict[str, str]:
    for item in importlib.metadata.distributions():
        distribution = item.metadata["Name"]
        if not distribution.lower().startswith(module) or item.version != actual_version:
            continue
        try:
            return {"distribution": distribution, "version": importlib.metadata.version(distribution)}
        except importlib.metadata.PackageNotFoundError:
            continue
    raise RuntimeError(f"no installed distribution reports module {module}")
def gpu_metadata(science: dict[str, Any]) -> dict[str, Any]:
    jax, jnp, cp = science["jax"], science["jnp"], science["cp"]
    if platform.system() != "Linux" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("runtime spike requires Linux Python 3.12")
    if os.environ.get("JAX_ENABLE_X64") != "1" or os.environ.get("JAX_PLATFORMS") != "cuda":
        raise RuntimeError("runtime spike requires JAX_ENABLE_X64=1 and JAX_PLATFORMS=cuda")
    devices = jax.devices()
    if len(devices) != 1 or devices[0].platform != "gpu" or cp.cuda.runtime.getDeviceCount() != 1:
        raise RuntimeError("runtime spike requires exactly one CUDA device")
    probe = jnp.asarray([1.0], dtype=jnp.float64)
    probe.block_until_ready()
    if str(probe.dtype) != "float64":
        raise RuntimeError("runtime spike requires an actual float64 JAX device probe")
    cupy_probe = cp.asarray([1.0], dtype=cp.float64)
    cp.cuda.Stream.null.synchronize()
    if str(cupy_probe.dtype) != "float64":
        raise RuntimeError("runtime spike requires an actual float64 CuPy device probe")
    try:
        smi = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                              "--format=csv,noheader"], text=True, capture_output=True,
                             check=False).stdout.strip() or "unavailable"
    except OSError:
        smi = "unavailable"
    properties = cp.cuda.runtime.getDeviceProperties(0)
    return {"jax_device": {"platform": devices[0].platform, "kind": devices[0].device_kind},
            "cupy_device_name": properties["name"].decode("utf-8"), "cupy_version": cp.__version__,
            "jax_probe_dtype": str(probe.dtype), "cupy_probe_dtype": str(cupy_probe.dtype),
            "nvidia_smi": smi, "preflight_note": "CUDA and CuPy initialized before fit timing"}
def memory_observation(device: Any) -> dict[str, Any]:
    try:
        stats = device.memory_stats()
    except MemoryError:
        raise
    except Exception as error:
        return {"status": "unavailable", "error": error_record(error)}
    return {"status": "available" if stats is not None else "unavailable", "stats": stats}
def stage(recorder: Recorder, report: dict[str, Any], science: dict[str, Any], case: int,
          name: str, call: Any) -> tuple[object, dict[str, Any]]:
    recorder.progress(f"case={case} stage={name} start")
    started = time.perf_counter_ns()
    try:
        value = call()
    except MemoryError as error:
        elapsed = time.perf_counter_ns() - started
        report["fatal_stage"] = {"stage": name, "elapsed_ns": elapsed, "error": error_record(error),
                                 "debug_error": recorder.dump_error(case, name, error)}
        recorder.progress(f"case={case} stage={name} memory_error")
        raise
    except Exception as error:
        elapsed = time.perf_counter_ns() - started
        item = {"stage": name, "elapsed_ns": elapsed, "error": error_record(error),
                "debug_error": recorder.dump_error(case, name, error),
                "device_memory_observation": memory_observation(science["jax"].devices()[0]),
                "rss_high_water": rss_observation(f"after_{name}")}
        recorder.progress(f"case={case} stage={name} exception")
        return error, item
    elapsed = time.perf_counter_ns() - started
    item = {"stage": name, "elapsed_ns": elapsed, "returned_class": qualified(value),
            "status": getattr(value, "status", None),
            "debug_dump": recorder.dump(case, name, value, science["np"]),
            "device_memory_observation": memory_observation(science["jax"].devices()[0]),
            "rss_high_water": rss_observation(f"after_{name}")}
    recorder.progress(f"case={case} stage={name} complete")
    return value, item
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if args.source_sha != SOURCE_SHA:
        parser.error(f"--source-sha must equal fixed protocol SHA {SOURCE_SHA}")
    if args.out.exists():
        parser.error("--out must name a new, non-existing directory")
    args.out.mkdir(parents=True)
    recorder = Recorder(args.out)
    report: dict[str, Any] = {
        "protocol": "b0h_timing_spike_v1", "execution_label": EXECUTION_LABEL,
        "source_sha": SOURCE_SHA, "complete": False, "first_fit_case_ordinal": None,
        "first_fit_note": (
            "set immediately before the first whole public fitter call; not pure compilation time"
        ),
        "cases": [], "environment": {name: os.environ.get(name) for name in ENV_NAMES},
    }
    try:
        science, report["heavy_import_elapsed_ns"] = science_imports()
        report["package_versions"] = lock_versions(Path(science["genomeos"].__file__).parent.parent)
        report["package_versions"]["cupy"] = installed_distribution("cupy", science["cp"].__version__)
        report["platform"] = {"python": sys.version, "platform": platform.platform()}
        preflight_started = time.perf_counter_ns()
        report["runtime"] = gpu_metadata(science)
        report["preflight_elapsed_ns"] = time.perf_counter_ns() - preflight_started
        report["rss_high_water"] = rss_observation("after_preflight")
        for ordinal, identity in enumerate(CASES):
            case = science["SbcCaseId"](*identity)
            generated, generated_item = stage(
                recorder, report, science, ordinal, "generation",
                lambda case=case: science["generate_sbc_case"](case),
            )
            case_report: dict[str, Any] = {"case": list(identity), "stages": [generated_item]}
            report["cases"].append(case_report)
            if isinstance(generated, BaseException):
                recorder.report(report)
                raise generated
            if not isinstance(generated, (science["GeneratedDataset"], science["GenerationFailure"])):
                raise RuntimeError(f"generation returned unexpected class {qualified(generated)}")
            if not isinstance(generated, science["GeneratedDataset"]):
                recorder.report(report)
                continue
            spec = science["plan_fit_attempt"](generated, attempt_id=0)
            case_report["plan"] = {"returned_class": qualified(spec),
                                   "debug_dump": recorder.dump(ordinal, "plan", spec, science["np"]),
                                   "sample_config": dataclasses.asdict(spec.config)}
            if report["first_fit_case_ordinal"] is None:
                report["first_fit_case_ordinal"] = ordinal
            attempt, attempt_item = stage(
                recorder, report, science, ordinal, "fit",
                lambda generated=generated, spec=spec: science["run_fit_attempt"](generated, spec=spec),
            )
            if isinstance(attempt, BaseException):
                case_report["stages"].append(attempt_item)
                recorder.report(report)
                raise attempt
            case_report["stages"].append(attempt_item)
            if attempt.status == "accepted":
                _, item = stage(
                    recorder, report, science, ordinal, "selected_quantities",
                    lambda generated=generated, attempt=attempt: science["selected_sbc_quantities"](
                        generated, attempt=attempt
                    ),
                )
                case_report["stages"].append(item)
                for backend in ("scipy", "cupy"):
                    _, item = stage(
                        recorder, report, science, ordinal, f"summary-{backend}",
                        lambda generated=generated, attempt=attempt, backend=backend:
                        science["summarize_heterogeneity_fit"](
                            generated, attempt=attempt, cdf_backend=backend
                        ),
                    )
                    case_report["stages"].append(item)
            recorder.report(report)
        report["complete"] = True
    except BaseException as error:
        report["fatal_error"] = error_record(error)
        recorder.progress("spike incomplete")
        raise
    finally:
        report["final_rss_high_water"] = rss_observation("final")
        recorder.report(report)

if __name__ == "__main__":
    main()
```

## setup.sh

```bash
#!/usr/bin/env bash
# Disposable runtime preparation for the predeclared B0H timing spike.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
export JAX_ENABLE_X64=1
export JAX_PLATFORMS=cuda
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export PYTENSOR_FLAGS=base_compiledir=/workspace/b0h-timing-cache/pytensor
export MPLCONFIGDIR=/workspace/b0h-timing-cache/matplotlib
# Use the constrained pip CUDA wheels, not libraries inherited from the image.
unset LD_LIBRARY_PATH
date -u
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
python3 --version
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
python3 -c 'from pathlib import Path; import hashlib; p=Path("/workspace/source-df0b71d.tar"); assert hashlib.sha256(p.read_bytes()).hexdigest() == "a6714b6166181eba453b6fad638e255dd09948777c7213e30b2450f8277390e6"'
mkdir /workspace/b0h-timing-source
tar -xf /workspace/source-df0b71d.tar -C /workspace/b0h-timing-source
python3 -m venv /workspace/b0h-timing-env
cd /workspace/b0h-timing-source
export PYTHONPATH=/workspace/b0h-timing-source
if ! /workspace/b0h-timing-env/bin/python -m pip install -r requirements.lock; then
    echo 'SETUP_FAILED: locked base installation'
    exit 1
fi
if ! /workspace/b0h-timing-env/bin/python -m pip install -c requirements.lock 'jax[cuda12]==0.11.1' 'cupy-cuda12x==14.2.0' 'cuda-pathfinder==1.8.1'; then
    echo 'SETUP_FAILED: constrained GPU additions'
    exit 1
fi
/workspace/b0h-timing-env/bin/python -m pip check
/workspace/b0h-timing-env/bin/python -m pip freeze
/workspace/b0h-timing-env/bin/python scripts/env_report.py
/workspace/b0h-timing-env/bin/python scripts/smoke.py
date -u
echo 'SETUP_COMPLETE: no scientific fit has run'
```

## run.sh

```bash
#!/usr/bin/env bash
# One disposable predeclared timing run; no restart or scientific retry.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
export JAX_ENABLE_X64=1
export JAX_PLATFORMS=cuda
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export PYTHONPATH=/workspace/b0h-timing-source
export PYTENSOR_FLAGS=base_compiledir=/workspace/b0h-timing-cache/pytensor
export MPLCONFIGDIR=/workspace/b0h-timing-cache/matplotlib
unset LD_LIBRARY_PATH
cd /workspace/b0h-timing-source
test ! -e /workspace/b0h-timing-20260910-01
/workspace/b0h-timing-env/bin/python -c 'from pathlib import Path; import hashlib; assert hashlib.sha256(Path("/workspace/probe.py").read_bytes()).hexdigest() == "3800714b6a5bc00fa33cde23f6f4992d16591ff79c0d13aedce9bfc65f2ad61f"'
date -u
pilot_exit=0
timeout --signal=INT --kill-after=30s 1800 /workspace/b0h-timing-env/bin/python -u /workspace/probe.py --out /workspace/b0h-timing-20260910-01 --source-sha df0b71dfca1edd2c209abe8f9829cd103feaffdd || pilot_exit=$?
date -u
echo "SPIKE_EXIT: ${pilot_exit}"
exit "${pilot_exit}"
```

## One-off read-only evidence inspector

The independent inspector below was executed after collection. It reads saved
values into ordinary Python containers, not scientific dataclasses, and does
not rerun fitting, convergence statistics, ranks or predictive diagnostics.
Its assertions concern this completed pilot, not a general failure-tolerant
runner. It must not be applied as a success filter to other experiments.

SHA256 of the exact file:
`ce51a8c89281f3256ab6a6cf885b625be67ed86668cb5d5a98cdcc3ef18bbc78`.
To inspect the committed evidence, set only `ROOT` to this checkout's
`data/validation/b0h-timing-20260910-01` and `REPO` to the checkout root;
retain the scientific SHA. The original literals are kept here for provenance.
Run with the locked Python/NumPy environment. Output should reproduce the
[inspection extraction](../../data/validation/b0h-timing-20260910-01-inspection.json),
including the per-file hashes of the 98 original output files.

```python
"""One-off read-only inspection of tagged debug trees, never scientific reconstruction."""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import struct
import subprocess

import numpy as np

ROOT = Path('/private/tmp/genomeos-b0h-collected.OiUaIk/b0h-timing-20260910-01')
REPO = Path('/private/tmp/genomeos-b0h-summaries.8tf98k')
SHA = 'df0b71dfca1edd2c209abe8f9829cd103feaffdd'
CASES = [[t, 0, 0, r] for r in range(4) for t in range(2)]
refs = []
classes = {}
class_counts = Counter()
source_cache = {}
array_cache = {}


def fields_at_source(qualified):
    module, _, name = qualified.rpartition('.')
    path = module.replace('.', '/') + '.py'
    if path not in source_cache:
        source_cache[path] = ast.parse(subprocess.check_output(
            ['git', '-C', str(REPO), 'show', f'{SHA}:{path}'], text=True))
    cls = next(n for n in source_cache[path].body if isinstance(n, ast.ClassDef) and n.name == name)
    assert not cls.bases, (qualified, 'static field check requires no inheritance')
    return [n.target.id for n in cls.body if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and not (isinstance(n.annotation, ast.Subscript)
                     and isinstance(n.annotation.value, ast.Name)
                     and n.annotation.value.id in {'ClassVar', 'InitVar'})]


def plain(node):
    tag = node['tag']
    if tag == 'dataclass':
        qualified = node['class']
        names = [f['name'] for f in node['fields']]
        assert len(names) == len(set(names)), qualified
        assert names == fields_at_source(qualified), (qualified, names, fields_at_source(qualified))
        classes[qualified] = names
        class_counts[qualified] += 1
        return {'class': qualified, **{f['name']: plain(f['value']) for f in node['fields']}}
    if tag == 'tuple':
        return [plain(v) for v in node['items']]
    if tag == 'string':
        return bytes.fromhex(node['utf8_surrogatepass_hex']).decode('utf-8', 'surrogatepass')
    if tag == 'int':
        return int(node['hex'], 16)
    if tag == 'float':
        return struct.unpack('!d', bytes.fromhex(node['binary64_be_hex']))[0]
    if tag == 'none':
        return None
    if tag == 'bool':
        return node['value']
    if tag == 'float64_ndarray':
        relative = node['path']
        assert Path(relative).parts[0] == 'arrays' and '..' not in Path(relative).parts
        array = np.load(ROOT / relative, allow_pickle=False)
        assert array.dtype == np.dtype('float64')
        assert list(array.shape) == node['shape'], relative
        assert array.size == 2000 and bool(np.isfinite(array).all()), relative
        refs.append(relative)
        array_cache[relative] = array
        return node
    raise ValueError(tag)


def arr(node):
    return array_cache[node['path']]


def same_bits(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def stats(values):
    return {'n': len(values), 'sum_s': sum(values), 'mean_s': statistics.mean(values),
            'median_s': statistics.median(values), 'min_s': min(values), 'max_s': max(values)}


def differences(a, b, path=''):
    """Descriptive leaf differences; no scientific acceptance threshold."""
    result = []
    if isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            result.extend(differences(a[k], b[k], f'{path}.{k}'))
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            result.extend(differences(x, y, f'{path}[{i}]'))
    elif type(a) is float:
        assert type(b) is float, path
        if struct.pack('!d', a) != struct.pack('!d', b):
            result.append({'path': path, 'scipy': a, 'cupy': b, 'cupy_minus_scipy': b-a})
    elif a != b:
        result.append({'path': path, 'scipy': a, 'cupy': b})
    return result


report = json.loads((ROOT / 'report.json').read_text())
assert report['source_sha'] == SHA
assert report['complete'] is True and 'fatal_error' not in report and 'fatal_stage' not in report
assert [c['case'] for c in report['cases']] == CASES
trees = {p.name: plain(json.loads(p.read_text())) for p in sorted((ROOT / 'debug').glob('*.json'))}
assert len(trees) == 48
assert len(refs) == len(set(refs)) == 48
array_files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'arrays').glob('*.npy'))
assert sorted(refs) == array_files
case_results = []
stages = ['generation', 'fit', 'selected_quantities', 'summary-scipy', 'summary-cupy']
times = {s: [] for s in stages}
all_rss = [report['rss_high_water']['value'], report['final_rss_high_water']['value']]
device_snapshots = []
for ordinal, record in enumerate(report['cases']):
    assert [s['stage'] for s in record['stages']] == stages
    assert all('error' not in s for s in record['stages'])
    for item in record['stages']:
        assert item['rss_high_water']['unit'] == 'KiB'
        all_rss.append(item['rss_high_water']['value'])
        times[item['stage']].append(item['elapsed_ns'] / 1e9)
        device_snapshots.append(item['device_memory_observation'])
        assert Path(item['debug_dump']).name in trees
    assert Path(record['plan']['debug_dump']).name in trees
    gen, plan, fit, selected, scipy, cupy = [trees[f'case-{ordinal:02d}-{s}.json']
                                          for s in ['generation', 'plan', *stages[1:]]]
    assert gen['class'].endswith('.GeneratedDataset')
    identity_fields = ['track_id', 'study_id', 'case_id', 'replicate_id']
    assert [gen['case_id'][k] for k in identity_fields] == record['case']
    assert [plan['case'][k] for k in identity_fields] == record['case']
    assert plan == fit['spec'] == selected['spec'] == scipy['spec'] == cupy['spec']
    assert plan['config'] == fit['fit']['config']
    assert {k:v for k,v in plan['config'].items() if k != 'class'} == record['plan']['sample_config']
    assert plan['attempt_id'] == 0
    assert plan['config']['chains'] == 4 and plan['config']['draws'] == 500
    assert plan['config']['tune'] == 1000 and plan['config']['target_accept'] == 0.9
    assert plan['config']['rho_prior_beta'] == (9.0 if ordinal % 2 == 0 else 4.0)
    assert plan['seed']['entropy'] == [42, 211, 1, *record['case'], 4, 0]
    assert list(arr(fit['fit']['mean_draws']).shape) == [4, 500, 1]
    assert list(arr(fit['fit']['rho_draws']).shape) == [4, 500, 1]
    assert scipy['parameters'] == cupy['parameters']
    for key in ('seed', 'seed_words', 'seed_uint128', 'targets', 'draw_count'):
        assert scipy['predictive'][key] == cupy['predictive'][key]
    assert scipy['predictive']['targets'] == gen['heldouts']
    assert scipy['predictive']['seed']['purpose_id'] == 7
    assert scipy['predictive']['seed']['case'] == plan['case']
    assert scipy['predictive']['seed']['attempt_id'] == 0
    assert scipy['predictive']['seed']['spawn_key'] == []
    assert selected['control']['seed']['purpose_id'] == 8
    assert selected['control']['seed']['case'] == plan['case']
    assert len(selected['control']['pairs']) == 4
    assert len(gen['heldouts']) == 1
    assert gen['heldouts'][0]['kind'] == 'fresh_population'
    assert gen['heldouts'][0]['row']['an'] == 20
    array_comparisons = {}
    for key in ('mean_draws', 'concentration'):
        a = arr(scipy['predictive']['prediction']['marginal_predictive'][key])
        b = arr(cupy['predictive']['prediction']['marginal_predictive'][key])
        assert a.shape == b.shape == (2000, 1)
        array_comparisons[key] = {'same_bits': same_bits(a, b),
                                 'max_abs_difference': float(np.max(np.abs(a-b)))}
    assert same_bits(arr(fit['fit']['mean_draws']).reshape(2000, 1),
                     arr(scipy['predictive']['prediction']['marginal_predictive']['mean_draws']))
    diag = fit['fit']['diagnostics'][0]
    ranks = [[x['mode_id'], x['quantity_id'], x['status'], x['rank'],
              None if x['comparisons'] is None else x['comparisons']['status'], x['error']]
             for x in selected['ranks']]
    reference = selected['reference']
    case_results.append({
        'ordinal': ordinal, 'case': record['case'], 'truth': gen['truth'],
        'fit_status': fit['status'], 'fit_error': fit['error'],
        'identity_mismatches': fit['identity_mismatches'],
        'fit_diagnostics': diag, 'divergences': fit['fit']['divergence_count'],
        'generation_boundary_counts': [gen['beta_zero_draws'], gen['beta_one_draws']],
        'training_an': [x['an'] for x in gen['training']],
        'selected_indices': selected['selected_indices'],
        'control_failure': selected['control']['failure'],
        'scalar_errors': [x['error'] for x in selected['scalar_quantities']],
        'scalar_failed_training_rows': [x['failed_training_row'] for x in selected['scalar_quantities']],
        'reference_error': selected['reference_error'],
        'reference_orders': reference['orders'],
        'reference_resolved_count': sum(x['resolved'] for x in reference['points']),
        'reference_point_count': len(reference['points']),
        'reference_max_recorded_error_bound': max(x['error_bound'] for x in reference['points']),
        'ranks': ranks,
        'summary_status': {b: t['predictive']['status'] for b, t in [('scipy', scipy), ('cupy', cupy)]},
        'summary_error': {b: t['predictive']['error'] for b, t in [('scipy', scipy), ('cupy', cupy)]},
        'parameters': scipy['parameters'],
        'predictive_rows_scipy': scipy['predictive']['rows'],
        'predictive_rows_cupy': cupy['predictive']['rows'],
        'prediction_array_comparison': array_comparisons,
        'entire_summary_leaf_differences': differences(scipy, cupy),
        'stage_seconds': {s: times[s][-1] for s in stages},
        'case_summed_stage_seconds': sum(times[s][-1] for s in stages),
    })

timing_stats = {s: {'all': stats(v), 'first_call_s': v[0], 'subsequent': stats(v[1:])}
                for s, v in times.items()}
summary = {
    'inspection_protocol': 'ordinary JSON/primitive parsing and NumPy file inspection only; no scientific dataclasses imported or reconstructed',
    'source_sha': SHA,
    'complete': report['complete'],
    'case_count': len(case_results),
    'debug_file_count': len(trees),
    'debug_array_reference_count': len(refs),
    'array_file_count': len(array_files),
    'array_shapes': dict(Counter(str(tuple(x.shape)) for x in array_cache.values())),
    'array_raw_payload_bytes': sum(x.nbytes for x in array_cache.values()),
    'array_npy_file_bytes': sum((ROOT / x).stat().st_size for x in array_files),
    'dataclass_instance_count': sum(class_counts.values()),
    'dataclass_field_occurrence_count': sum(class_counts[k] * len(v) for k, v in classes.items()),
    'dataclass_class_count': len(classes),
    'class_counts': dict(sorted(class_counts.items())),
    'class_fields': dict(sorted(classes.items())),
    'timings': timing_stats,
    'summed_public_call_seconds': sum(sum(v) for v in times.values()),
    'heavy_import_seconds': report['heavy_import_elapsed_ns'] / 1e9,
    'preflight_seconds': report['preflight_elapsed_ns'] / 1e9,
    'sum_of_recorded_phase_seconds': sum(sum(v) for v in times.values()) +
        (report['heavy_import_elapsed_ns'] + report['preflight_elapsed_ns']) / 1e9,
    'rss_highwater_kib': {'after_preflight': report['rss_high_water']['value'],
                         'final': report['final_rss_high_water']['value'],
                         'max_observed': max(all_rss)},
    'device_snapshots': {
        'count': len(device_snapshots),
        'statuses': dict(Counter(x['status'] for x in device_snapshots)),
        'first': device_snapshots[0], 'last': device_snapshots[-1],
        'max_snapshot_bytes_in_use': max(x['stats']['bytes_in_use'] for x in device_snapshots),
        'max_snapshot_jax_peak_bytes_in_use': max(x['stats']['peak_bytes_in_use'] for x in device_snapshots),
    },
    'files_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(ROOT.rglob('*')) if p.is_file()},
    'cases': case_results,
}
print(json.dumps(summary, indent=2, sort_keys=True))
```

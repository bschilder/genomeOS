"""Observed offline B0H platform admission (design §§5,7–8,12; runner §8)."""

from __future__ import annotations

import fcntl
import importlib.metadata
import inspect
import json
import os
import platform
import resource
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt,
    RuntimeIdentity,
    SourceIdentity,
    StorageAdmission,
)
from genomeos.validation.heterogeneity_runner_wire import sha256


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True
    ).stdout


def require_execution_source(root: Path) -> None:
    from genomeos.surfaces import reference_heterogeneity
    from genomeos.validation import (
        heterogeneity_attempts,
        heterogeneity_codec,
        heterogeneity_runner,
        heterogeneity_sbc_quantities,
        heterogeneity_simulation,
        heterogeneity_summaries,
        sbc_ranks,
    )

    functions = (
        (heterogeneity_simulation.generate_sbc_case, "genomeos/validation/heterogeneity_simulation.py"),
        (heterogeneity_attempts.run_fit_attempt, "genomeos/validation/heterogeneity_attempts.py"),
        (heterogeneity_attempts.exercise_unavailable, "genomeos/validation/heterogeneity_attempts.py"),
        (
            heterogeneity_sbc_quantities.selected_sbc_quantities,
            "genomeos/validation/heterogeneity_sbc_quantities.py",
        ),
        (
            heterogeneity_summaries.summarize_heterogeneity_fit,
            "genomeos/validation/heterogeneity_summaries.py",
        ),
        (heterogeneity_codec.encode_b0h_evidence, "genomeos/validation/heterogeneity_codec.py"),
        (heterogeneity_codec.decode_b0h_evidence, "genomeos/validation/heterogeneity_codec.py"),
        (heterogeneity_runner.execute_b0h_case, "genomeos/validation/heterogeneity_runner.py"),
        (sbc_ranks.simulate_rank_null, "genomeos/validation/sbc_ranks.py"),
        (
            reference_heterogeneity.fit_reference_population_heterogeneity,
            "genomeos/surfaces/reference_heterogeneity.py",
        ),
        (
            reference_heterogeneity.predict_reference_population_heterogeneity,
            "genomeos/surfaces/reference_heterogeneity.py",
        ),
    )
    for function, relative in functions:
        actual = inspect.getsourcefile(function)
        if actual is None or Path(actual).resolve() != (root / relative).resolve():
            raise ValueError("imported public entrypoint differs from attested source_root: " + relative)
    if Path(__file__).resolve() != (root / "genomeos/validation/heterogeneity_runner_admission.py").resolve():
        raise ValueError("admission adapter differs from attested source_root")


def _source(root: Path) -> SourceIdentity:
    require_execution_source(root)
    paths = ("genomeos", "scripts", "pyproject.toml", "requirements.lock")
    if _git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths):
        raise ValueError("source/runtime files must match reviewed committed revision")
    revision = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    names = _git(root, "ls-files", "-z", "--", *paths).split(b"\0")
    entries = []
    for name in sorted(name for name in names if name):
        path = root / name.decode("utf-8")
        if path.is_symlink() or not path.is_file():
            raise ValueError("source path is not a regular file")
        entries.append((name.hex(), sha256(path.read_bytes())))
    return SourceIdentity(
        revision=revision,
        content_sha256=sha256(_json(entries)),
        lock_sha256=sha256((root / "requirements.lock").read_bytes()),
    )


def _mount(parent: Path) -> tuple[str, str]:
    if sys.platform != "linux":
        raise ValueError("actual GPU campaign storage admission requires Linux mount evidence")
    found = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        parts = line.split()
        divider = parts.index("-")
        mount = parts[4]
        for encoded, literal in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
            mount = mount.replace(encoded, literal)
        if parent == Path(mount) or Path(mount) in parent.parents:
            found.append((len(mount), parts[divider + 1], parts[5] + "," + parts[divider + 3]))
    if not found:
        raise ValueError("cannot establish actual filesystem mount")
    _, kind, options = max(found)
    if kind not in ("ext4", "xfs", "btrfs", "tmpfs"):
        raise ValueError("local filesystem backing not established for " + kind)
    return kind, options


def _storage(parent: Path) -> StorageAdmission:
    parent = parent.resolve(strict=True)
    kind, options = _mount(parent)
    with tempfile.TemporaryDirectory(prefix="b0h-admission-", dir=parent) as temporary:
        probe = Path(temporary)
        lockpath = probe / "exclusion.lock"
        with lockpath.open("xb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import fcntl,sys\nf=open(sys.argv[1],'rb')\ntry:\n"
                    " fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
                    "except BlockingIOError:\n sys.exit(0)\nsys.exit(1)\n",
                    str(lockpath),
                ],
                check=False,
                capture_output=True,
            )
            if child.returncode != 0:
                raise ValueError("cross-process exclusion probe failed")
        database = probe / "proof.sqlite3"
        connection = sqlite3.connect(database, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=EXTRA")
            connection.execute("PRAGMA foreign_keys=ON")
            settings = tuple(
                connection.execute("PRAGMA " + name).fetchone()[0]
                for name in ("journal_mode", "synchronous", "foreign_keys")
            )
            if settings != ("delete", 3, 1):
                raise ValueError("SQLite admission setting mismatch")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE proof(value BLOB NOT NULL)")
            connection.execute("INSERT INTO proof VALUES(?)", (b"committed",))
            connection.execute("COMMIT")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO proof VALUES(?)", (b"rolled_back",))
            connection.execute("ROLLBACK")
        finally:
            connection.close()
        with sqlite3.connect(database) as restored:
            if restored.execute("SELECT value FROM proof").fetchall() != [(b"committed",)]:
                raise ValueError("SQLite commit/rollback readback probe failed")
        descriptor = os.open(probe, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        digest = sha256(
            _json(
                {
                    "version": "1",
                    "settings": settings,
                    "exclusive_lock": True,
                    "commit_readback": True,
                    "rollback": True,
                    "directory_fsync": True,
                }
            )
        )
    return StorageAdmission(
        database_parent=str(parent),
        device_id=parent.stat().st_dev,
        mount_type=kind,
        mount_options=options,
        free_bytes=shutil.disk_usage(parent).free,
        probe_sha256=digest,
        exclusive_lock_observed=True,
        rollback_observed=True,
        commit_readback_observed=True,
        directory_fsync_observed=True,
    )


def observe_b0h_admission(source_root: Path, database_parent: Path) -> AdmissionReceipt:
    start = time.monotonic_ns()
    source = _source(source_root.resolve(strict=True))
    import cupy as cp
    import jax
    import jax.numpy as jnp

    startup = time.monotonic_ns() - start
    preflight = time.monotonic_ns()
    devices = jax.devices()
    if len(devices) != 1 or devices[0].platform != "gpu" or cp.cuda.runtime.getDeviceCount() != 1:
        raise ValueError("admission requires exactly one visible GPU in JAX and CuPy")
    jax_probe = jnp.asarray([1.0], dtype=jnp.float64)
    jax_probe.block_until_ready()
    cupy_probe = cp.asarray([1.0], dtype=cp.float64)
    cp.cuda.get_current_stream().synchronize()
    if str(jax_probe.dtype) != "float64" or str(cupy_probe.dtype) != "float64":
        raise ValueError("actual JAX/CuPy float64 probes failed")
    versions = sorted(
        (distribution.metadata["Name"], distribution.version)
        for distribution in importlib.metadata.distributions()
    )
    settings = tuple(
        (name, os.environ.get(name))
        for name in (
            "JAX_PLATFORMS",
            "JAX_ENABLE_X64",
            "XLA_PYTHON_CLIENT_PREALLOCATE",
            "CUDA_VISIBLE_DEVICES",
            "PYTENSOR_FLAGS",
        )
    )
    driver = (
        subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if type(device_name) is bytes:
        device_name = device_name.decode("utf-8")
    runtime = RuntimeIdentity(
        python_version=platform.python_version(),
        platform=platform.platform(),
        machine=platform.machine(),
        environment_sha256=sha256(_json((versions, settings))),
        jax_version=jax.__version__,
        cupy_version=cp.__version__,
        jax_device=str(devices[0]),
        cupy_device=device_name,
        driver_version=driver,
        jax_float64=True,
        cupy_float64=True,
    )
    storage = _storage(database_parent)
    free, total = cp.cuda.runtime.memGetInfo()
    return AdmissionReceipt(
        format="b0h_admission",
        version="1",
        source=source,
        runtime=runtime,
        storage=storage,
        observed_unix_ns=time.time_ns(),
        startup_elapsed_ns=startup,
        preflight_elapsed_ns=time.monotonic_ns() - preflight,
        device_total_bytes=int(total),
        device_free_bytes=int(free),
        process_peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
        memory_observation_label="post_preflight_device_free_and_process_high_water_not_campaign_peak",
    )

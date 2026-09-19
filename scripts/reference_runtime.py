"""Freeze native and transport runtime identity (reference acquisition design §7)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path

from scripts.reference_io_common import _run_process

_VERSION_STDOUT_LIMIT = 65_536
_STDERR_LIMIT = 1_048_576
_SDK_FILES = (
    "lib/googlecloudsdk/api_lib/storage/api_factory.py",
    "lib/googlecloudsdk/api_lib/storage/gcs_download.py",
    "lib/googlecloudsdk/api_lib/storage/gcs_json/download.py",
    "lib/googlecloudsdk/api_lib/storage/retry_util.py",
    "lib/surface/storage/cat.py",
    "lib/surface/storage/objects/describe.py",
)
CAMPAIGN_SOURCE_FILES = (
    "genomeos/validation/reference_acquisition_codec.py",
    "genomeos/validation/reference_acquisition_evidence.py",
    "genomeos/validation/reference_acquisition_types.py",
    "genomeos/validation/reference_byte_plan.py",
    "genomeos/validation/reference_cohorts.py",
    "genomeos/validation/reference_count_types.py",
    "genomeos/validation/reference_genotypes.py",
    "genomeos/validation/reference_preflight_input.py",
    "genomeos/validation/reference_preparation.py",
    "genomeos/validation/reference_preparation_codec.py",
    "genomeos/validation/reference_preparation_types.py",
    "genomeos/validation/reference_tbi.py",
    "genomeos/validation/reference_vcf_tokens.py",
    "genomeos/validation/reference_window_manifest.py",
    "genomeos/validation/reference_window_types.py",
    "genomeos/validation/reference_windows.py",
    "scripts/acquire_reference_windows.py",
    "scripts/gcloud_repo.py",
    "scripts/prepare_reference_window_counts.py",
    "scripts/reference_artifact_inventory.py",
    "scripts/reference_artifact_io.py",
    "scripts/reference_cohort_artifacts.py",
    "scripts/reference_count_artifacts.py",
    "scripts/reference_count_replay.py",
    "scripts/reference_count_rows.py",
    "scripts/reference_io_common.py",
    "scripts/reference_native_io.py",
    "scripts/reference_native_stage.py",
    "scripts/reference_preparation_outputs.py",
    "scripts/reference_runtime.py",
    "scripts/reference_window_artifacts.py",
    "scripts/reference_window_io.py",
)
_CORE_RUNTIME_KEYS = frozenset({"bcftools", "bcftools_fill_tags", "bcftools_htslib"})
_ACQUISITION_RUNTIME_KEYS = frozenset({*_CORE_RUNTIME_KEYS, "tabix", "bgzip", "gcloud"})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def campaign_source_hashes(checkout: Path | None = None) -> tuple[tuple[str, str], ...]:
    """Hash the complete reviewed acquisition and preparation implementation surface."""
    root = Path(__file__).resolve().parents[1] if checkout is None else checkout
    _require(isinstance(root, Path) and root.is_dir(), "invalid source checkout")
    root = root.resolve(strict=True)
    result = []
    for relative in CAMPAIGN_SOURCE_FILES:
        candidate = root / relative
        _require(candidate.is_file() and not candidate.is_symlink(), "invalid campaign source")
        expected = candidate.resolve(strict=True)
        _require(expected.is_relative_to(root), "invalid campaign source")
        module_name = relative.removesuffix(".py").replace("/", ".")
        loaded = sys.modules.get(module_name)
        if loaded is not None:
            origin = getattr(loaded, "__file__", None)
            _require(
                isinstance(origin, str) and Path(origin).resolve(strict=True) == expected,
                "campaign import origin mismatch",
            )
        result.append((relative, _sha(expected)))
    return tuple(result)


def validate_runtime_provenance(provenance: object, *, phase: str) -> None:
    """Require the exact pinned runtime evidence set for one campaign phase."""
    _require(phase in ("acquisition", "preparation"), "invalid provenance phase")
    versions = dict(provenance.tool_versions)
    executable_hashes = dict(provenance.executable_sha256)
    expected = _ACQUISITION_RUNTIME_KEYS if phase == "acquisition" else _CORE_RUNTIME_KEYS
    _require(set(versions) == expected, "runtime version evidence is incomplete")
    _require(set(executable_hashes) == expected, "runtime executable evidence is incomplete")
    _require(
        versions["bcftools"] == "bcftools 1.23.1"
        and versions["bcftools_htslib"] == "Using htslib 1.23.1"
        and versions["bcftools_fill_tags"].splitlines()
        == [
            "bcftools  1.23.1 using htslib 1.23.1",
            "plugin at 1.23.1 using htslib 1.23.1",
        ],
        "native runtime version evidence differs from the pinned toolchain",
    )
    if phase == "preparation":
        _require(provenance.sdk_source_sha256 == (), "preparation must not claim SDK source evidence")
        return
    _require(
        versions["tabix"].splitlines()[:1] == ["tabix (htslib) 1.23.1"]
        and versions["bgzip"].splitlines()[:1] == ["bgzip (htslib) 1.23.1"],
        "HTSlib utility version evidence differs from the pinned toolchain",
    )
    try:
        gcloud = json.loads(versions["gcloud"])
    except json.JSONDecodeError as error:
        raise ValueError("invalid gcloud version evidence") from error
    _require(
        type(gcloud) is dict and gcloud.get("Google Cloud SDK") == "574.0.0",
        "gcloud version evidence differs from the pinned SDK",
    )
    _require(
        {name for name, _ in provenance.sdk_source_sha256} == set(_SDK_FILES),
        "gcloud SDK source evidence is incomplete",
    )


def _resolved(path: Path) -> Path:
    _require(isinstance(path, Path) and path.exists() and path.is_file(), "invalid executable")
    result = path.resolve(strict=True)
    _require(result.is_file() and not result.is_symlink(), "invalid executable target")
    return result


def _capture(argv: list[str]) -> str:
    with tempfile.TemporaryDirectory(prefix="genomeos-runtime-") as directory:
        root = Path(directory)
        result = _run_process(
            argv,
            artifact_root=root,
            stdout_path="stdout",
            stderr_path="stderr",
            stdout_limit=_VERSION_STDOUT_LIMIT,
            stderr_limit=_STDERR_LIMIT,
            timeout=10,
        )
        raw = (root / result.stdout.path).read_bytes() + (root / result.stderr.path).read_bytes()
    _require(
        result.exit_code == 0
        and not result.timed_out
        and not result.stdout_limit_exceeded
        and not result.stderr_limit_exceeded
        and 0 < len(raw) <= _VERSION_STDOUT_LIMIT + _STDERR_LIMIT,
        "runtime version check failed",
    )
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ValueError("runtime version output is not UTF-8") from error


def _htslib(bcftools: Path) -> Path:
    if platform.system() == "Darwin":
        output = _capture(["/usr/bin/otool", "-L", str(bcftools)])
        candidates = [
            Path(line.strip().split(" ", 1)[0]).resolve(strict=True)
            for line in output.splitlines()[1:]
            if "libhts." in line
        ]
    else:
        ldd = shutil.which("ldd")
        _require(ldd is not None, "unable to locate linked HTSlib")
        output = _capture([ldd, str(bcftools)])
        candidates = []
        for line in output.splitlines():
            if "libhts.so" not in line:
                continue
            token = line.split("=>", 1)[-1].strip().split(" ", 1)[0]
            candidates.append(Path(token).resolve(strict=True))
    unique = tuple(sorted(set(candidates)))
    _require(len(unique) == 1 and unique[0].is_file(), "unable to identify linked HTSlib")
    return unique[0]


def _fill_tags(bcftools: Path) -> Path:
    roots = []
    configured = os.environ.get("BCFTOOLS_PLUGINS")
    if configured:
        roots.extend(Path(value) for value in configured.split(os.pathsep) if value)
    prefix = bcftools.parent.parent
    roots.extend((prefix / "libexec" / "bcftools", prefix / "lib" / "bcftools"))
    matches = {
        candidate.resolve(strict=True)
        for root in roots
        for candidate in (root / "fill-tags.so", root / "fill-tags.dylib")
        if candidate.is_file()
    }
    _require(len(matches) == 1, "unable to identify fill-tags plugin")
    return matches.pop()


def _bcftools_runtime(path: Path) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    executable = _resolved(path)
    version = _capture([str(executable), "--version"])
    lines = version.splitlines()
    _require(
        len(lines) >= 2
        and lines[0] == "bcftools 1.23.1"
        and lines[1] == "Using htslib 1.23.1",
        "unsupported bcftools or HTSlib version",
    )
    plugin_version = _capture([str(executable), "+fill-tags", "--version"])
    _require(
        plugin_version.splitlines() == [
            "bcftools  1.23.1 using htslib 1.23.1",
            "plugin at 1.23.1 using htslib 1.23.1",
        ],
        "unsupported fill-tags plugin version",
    )
    htslib = _htslib(executable)
    plugin = _fill_tags(executable)
    versions = (
        ("bcftools", lines[0]),
        ("bcftools_fill_tags", plugin_version),
        ("bcftools_htslib", lines[1]),
    )
    hashes = (
        ("bcftools", _sha(executable)),
        ("bcftools_fill_tags", _sha(plugin)),
        ("bcftools_htslib", _sha(htslib)),
    )
    return versions, hashes


def _htslib_tool(name: str, path: Path) -> tuple[str, Path]:
    executable = _resolved(path)
    output = _capture([str(executable), "--version"])
    _require(output.splitlines()[0] == f"{name} (htslib) 1.23.1", f"unsupported {name} version")
    return output, executable


def resolve_executable(path: Path) -> Path:
    """Resolve one executable once for later identity checks and invocation."""
    return _resolved(path)


def resolve_gcloud() -> Path:
    """Resolve the gcloud executable selected by the current PATH once."""
    located = shutil.which("gcloud")
    _require(located is not None, "gcloud is unavailable")
    return _resolved(Path(located))


def _gcloud(executable: Path | None = None) -> tuple[str, Path, tuple[tuple[str, str], ...]]:
    executable = resolve_gcloud() if executable is None else _resolved(executable)
    output = _capture([str(executable), "version", "--format=json"])
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise ValueError("invalid gcloud version output") from error
    _require(
        type(value) is dict and value.get("Google Cloud SDK") == "574.0.0",
        "unsupported gcloud version",
    )
    sdk_root = executable.parent.parent
    files = tuple((relative, sdk_root / relative) for relative in _SDK_FILES)
    _require(all(path.is_file() and not path.is_symlink() for _, path in files),
             "gcloud SDK source is unavailable")
    return output, executable, tuple((relative, _sha(path)) for relative, path in files)


def acquisition_runtime(
    bcftools: Path,
    tabix: Path,
    bgzip: Path,
    gcloud: Path | None = None,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Verify and hash every native/transport runtime used by acquisition."""
    versions, hashes = _bcftools_runtime(bcftools)
    tabix_version, tabix_path = _htslib_tool("tabix", tabix)
    bgzip_version, bgzip_path = _htslib_tool("bgzip", bgzip)
    gcloud_version, gcloud_path, sdk = _gcloud(gcloud)
    return (
        tuple(sorted((*versions, ("tabix", tabix_version), ("bgzip", bgzip_version),
                      ("gcloud", gcloud_version)))),
        tuple(sorted((*hashes, ("tabix", _sha(tabix_path)), ("bgzip", _sha(bgzip_path)),
                      ("gcloud", _sha(gcloud_path))))),
        tuple(sorted(sdk)),
    )


def preparation_runtime(
    bcftools: Path,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Verify and hash the native runtime used by offline count preparation."""
    versions, hashes = _bcftools_runtime(bcftools)
    return tuple(sorted(versions)), tuple(sorted(hashes)), ()

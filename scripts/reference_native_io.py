"""Bounded native reference controls (reference acquisition design §§4–4.1)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from genomeos.validation.reference_acquisition_types import (
    ArtifactRef,
    NativeCountFiles,
    NativeRunReceipt,
    NativeTokenFiles,
    VerifiedSource,
)
from genomeos.validation.reference_byte_plan import SourceBytePlan
from genomeos.validation.reference_genotypes import NativeVariantTokens
from genomeos.validation.reference_window_types import ReferenceWindow
from scripts.reference_io_common import (
    _existing,
    _require,
    _run_process,
    _validate_artifact,
    validate_verified_source,
)

NATIVE_TIMEOUT_SECONDS = 1_800
NATIVE_STDOUT_LIMIT_BYTES = 2_147_483_648
NATIVE_SAMPLE_STDOUT_LIMIT_BYTES = 1_048_576
NATIVE_VERSION_STDOUT_LIMIT_BYTES = 65_536
STDERR_LIMIT_BYTES = 1_048_576
RECORD_LIMIT_BYTES = 16_777_216
_NATURAL = re.compile(r"[0-9]+\Z")


def _native_receipt(
    operation: str,
    argv: list[str],
    argv_template: tuple[str, ...],
    *,
    artifact_root: Path,
    stdout_path: str,
    stderr_path: str,
    stdout_limit: int,
) -> NativeRunReceipt:
    result = _run_process(
        argv,
        artifact_root=artifact_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        stdout_limit=stdout_limit,
        stderr_limit=STDERR_LIMIT_BYTES,
        timeout=NATIVE_TIMEOUT_SECONDS,
    )
    if result.stdout_limit_exceeded or result.stderr_limit_exceeded:
        reason = "limit_exceeded"
    elif result.timed_out:
        reason = "timeout"
    elif result.exit_code != 0:
        reason = "native_encoding_refused"
    else:
        reason = None
    state = "complete" if reason is None else "refused"
    return NativeRunReceipt(
        operation,
        argv_template,
        state,
        reason,
        result.exit_code,
        result.stdout,
        result.stderr,
        stdout_limit,
        STDERR_LIMIT_BYTES,
        result.stdout_limit_exceeded,
        result.stderr_limit_exceeded,
    )


def extract_native(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    window: ReferenceWindow,
    *,
    artifact_root: Path,
    bcftools: Path,
    stdout_path: str,
    stderr_path: str,
) -> NativeRunReceipt:
    """Extract one window from the verified local sparse source through bounded stdout."""
    validate_verified_source(verified, plan, artifact_root=artifact_root)
    _require(isinstance(bcftools, Path) and bcftools.is_file(), "invalid bcftools executable")
    _require(
        window.chrom == plan.source.chrom
        and sum(value.window_id == window.window_id for value in plan.windows) == 1,
        "window plan identity mismatch",
    )
    sparse = _existing(
        artifact_root, ArtifactRef(verified.sparse_path, verified.logical_size_bytes, "0" * 64)
    )
    region = f"{window.chrom}:{window.start0 + 1}-{window.end0}"
    template = (
        "bcftools",
        "view",
        "--no-version",
        "-r",
        region,
        "--regions-overlap",
        "0",
        "-Ob",
        verified.sparse_path,
    )
    return _native_receipt(
        "extract_bcf",
        [str(bcftools), *template[1:-1], str(sparse)],
        template,
        artifact_root=artifact_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        stdout_limit=NATIVE_STDOUT_LIMIT_BYTES,
    )


def query_native_tokens(
    bcf: ArtifactRef,
    *,
    artifact_root: Path,
    bcftools: Path,
    output_prefix: str,
) -> NativeTokenFiles:
    """Query sample IDs and GT/GQ/DP/AD tokens from the same hash-bound BCF."""
    input_path = _validate_artifact(artifact_root, bcf)
    sample_path = f"{output_prefix}.samples.txt"
    sample_stderr = f"{output_prefix}.samples.stderr"
    sample_template = ("bcftools", "query", "-l", bcf.path)
    sample_run = _native_receipt(
        "query_samples",
        [str(bcftools), "query", "-l", str(input_path)],
        sample_template,
        artifact_root=artifact_root,
        stdout_path=sample_path,
        stderr_path=sample_stderr,
        stdout_limit=NATIVE_SAMPLE_STDOUT_LIMIT_BYTES,
    )
    if sample_run.state != "complete":
        return NativeTokenFiles(bcf, None, None, sample_run, None, "refused", sample_run.reason)
    token_path = f"{output_prefix}.tokens.tsv"
    token_stderr = f"{output_prefix}.tokens.stderr"
    format_ = r"%CHROM\t%POS\t%REF\t%ALT[\t%GT:%GQ:%DP:%AD]\n"
    token_template = ("bcftools", "query", "-f", format_, bcf.path)
    token_run = _native_receipt(
        "query_tokens",
        [str(bcftools), "query", "-f", format_, str(input_path)],
        token_template,
        artifact_root=artifact_root,
        stdout_path=token_path,
        stderr_path=token_stderr,
        stdout_limit=NATIVE_STDOUT_LIMIT_BYTES,
    )
    if token_run.state != "complete":
        return NativeTokenFiles(
            bcf,
            sample_run.stdout,
            None,
            sample_run,
            token_run,
            "refused",
            token_run.reason,
        )
    return NativeTokenFiles(
        bcf,
        sample_run.stdout,
        token_run.stdout,
        sample_run,
        token_run,
        "complete",
        None,
    )


def _text_lines(path: Path, *, limit: int) -> tuple[str, ...]:
    _require(path.stat().st_size <= limit, "text artifact limit exceeded")
    raw = path.read_bytes()
    _require(not raw or raw.endswith(b"\n"), "text artifact lacks terminal LF")
    _require(b"\r" not in raw and b"\0" not in raw, "text artifact has invalid bytes")
    try:
        return tuple(raw.decode("ascii").splitlines())
    except UnicodeDecodeError as error:
        raise ValueError("native text artifact must be ASCII") from error


def iter_native_tokens(query: NativeTokenFiles, *, artifact_root: Path) -> Iterator[NativeVariantTokens]:
    """Yield identity-carrying native token rows from complete query artifacts."""
    _require(
        type(query) is NativeTokenFiles and query.state == "complete", "native token query is incomplete"
    )
    assert query.samples is not None and query.tokens is not None
    samples_path = _validate_artifact(artifact_root, query.samples)
    tokens_path = _validate_artifact(artifact_root, query.tokens)
    samples = _text_lines(samples_path, limit=NATIVE_SAMPLE_STDOUT_LIMIT_BYTES)
    _require(
        bool(samples) and len(samples) == len(set(samples)) and all(samples), "invalid native sample IDs"
    )
    seen: set[str] = set()
    with tokens_path.open("rb") as handle:
        for raw in handle:
            _require(len(raw) <= RECORD_LIMIT_BYTES and raw.endswith(b"\n"), "invalid native token line")
            try:
                fields = raw[:-1].decode("ascii").split("\t")
            except UnicodeDecodeError as error:
                raise ValueError("native token line must be ASCII") from error
            _require(len(fields) == 4 + len(samples), "native token column count mismatch")
            chrom, pos, ref, alt = fields[:4]
            _require(_NATURAL.fullmatch(pos) is not None and int(pos) > 0, "invalid native position")
            variant_id = f"GRCh38:{chrom}:{int(pos)}:{ref}:{alt}"
            _require(variant_id not in seen, "duplicate native variant identity")
            seen.add(variant_id)
            yield NativeVariantTokens(variant_id, samples, tuple(fields[4:]))


def _refused_counts(
    bcf: ArtifactRef,
    samples: ArtifactRef,
    runs: list[NativeRunReceipt],
    reason: str,
    files: list[ArtifactRef],
) -> NativeCountFiles:
    padded = [*files, None, None, None, None][:4]
    return NativeCountFiles(bcf, samples, *padded, tuple(runs), "refused", reason)


def native_called_totals(
    bcf: ArtifactRef,
    cohort_samples: ArtifactRef,
    *,
    acquisition_root: Path,
    artifact_root: Path,
    bcftools: Path,
    output_prefix: str,
) -> NativeCountFiles:
    """Recompute called cohort AC/AN using bounded local native commands."""
    input_path = _validate_artifact(acquisition_root, bcf)
    requested_path = _validate_artifact(artifact_root, cohort_samples)
    runs: list[NativeRunReceipt] = []
    files: list[ArtifactRef] = []

    def run(operation: str, suffix: str, arguments: list[str], template: tuple[str, ...], limit: int) -> bool:
        receipt = _native_receipt(
            operation,
            [str(bcftools), *arguments],
            template,
            artifact_root=artifact_root,
            stdout_path=f"{output_prefix}.{suffix}",
            stderr_path=f"{output_prefix}.{suffix}.stderr",
            stdout_limit=limit,
        )
        runs.append(receipt)
        if receipt.state == "complete":
            files.append(receipt.stdout)
            return True
        return False

    selected = f"{output_prefix}.selected.bcf"
    select_template = (
        "bcftools",
        "view",
        "--no-version",
        "-S",
        cohort_samples.path,
        "-m2",
        "-M2",
        "-v",
        "snps",
        "-f",
        "PASS",
        "-Ob",
        f"@acquisition/{bcf.path}",
    )
    if not run(
        "select_cohort",
        "selected.bcf",
        [
            "view",
            "--no-version",
            "-S",
            str(requested_path),
            "-m2",
            "-M2",
            "-v",
            "snps",
            "-f",
            "PASS",
            "-Ob",
            str(input_path),
        ],
        select_template,
        NATIVE_STDOUT_LIMIT_BYTES,
    ):
        return _refused_counts(bcf, cohort_samples, runs, runs[-1].reason or "native_encoding_refused", files)
    selected_path = _validate_artifact(artifact_root, files[0])
    fill_template = (
        "bcftools",
        "+fill-tags",
        selected,
        "--no-version",
        "-Ob",
        "--",
        "-t",
        "AC,AN",
    )
    if not run(
        "fill_tags",
        "recomputed.bcf",
        ["+fill-tags", str(selected_path), "--no-version", "-Ob", "--", "-t", "AC,AN"],
        fill_template,
        NATIVE_STDOUT_LIMIT_BYTES,
    ):
        return _refused_counts(bcf, cohort_samples, runs, runs[-1].reason or "native_encoding_refused", files)
    recomputed_path = _validate_artifact(artifact_root, files[1])
    samples_template = ("bcftools", "query", "-l", f"{output_prefix}.recomputed.bcf")
    if not run(
        "query_samples",
        "samples.txt",
        ["query", "-l", str(recomputed_path)],
        samples_template,
        NATIVE_SAMPLE_STDOUT_LIMIT_BYTES,
    ):
        return _refused_counts(bcf, cohort_samples, runs, runs[-1].reason or "native_encoding_refused", files)
    requested = _text_lines(requested_path, limit=NATIVE_SAMPLE_STDOUT_LIMIT_BYTES)
    selected_ids = _text_lines(
        _validate_artifact(artifact_root, files[2]), limit=NATIVE_SAMPLE_STDOUT_LIMIT_BYTES
    )
    if not requested or len(requested) != len(set(requested)) or set(requested) != set(selected_ids):
        return _refused_counts(bcf, cohort_samples, runs, "native_mismatch", files)
    totals_format = r"%CHROM\t%POS\t%REF\t%ALT\t%INFO/AC\t%INFO/AN\n"
    totals_template = (
        "bcftools",
        "query",
        "-f",
        totals_format,
        f"{output_prefix}.recomputed.bcf",
    )
    if not run(
        "query_totals",
        "totals.tsv",
        ["query", "-f", totals_format, str(recomputed_path)],
        totals_template,
        NATIVE_STDOUT_LIMIT_BYTES,
    ):
        return _refused_counts(bcf, cohort_samples, runs, runs[-1].reason or "native_encoding_refused", files)
    return NativeCountFiles(bcf, cohort_samples, *files, tuple(runs), "complete", None)


def read_native_totals(
    control: NativeCountFiles,
    *,
    artifact_root: Path,
) -> tuple[tuple[str, int, int], ...]:
    """Parse exact native AC/AN totals, refusing native missing values."""
    _require(
        type(control) is NativeCountFiles and control.state == "complete",
        "native count control is incomplete",
    )
    assert control.totals is not None
    path = _validate_artifact(artifact_root, control.totals)
    result: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    with path.open("rb") as handle:
        while raw := handle.readline(RECORD_LIMIT_BYTES + 1):
            _require(raw.endswith(b"\n") and len(raw) <= RECORD_LIMIT_BYTES, "invalid native totals line")
            _require(b"\r" not in raw and b"\0" not in raw, "native totals line has invalid bytes")
            try:
                fields = raw[:-1].decode("ascii").split("\t")
            except UnicodeDecodeError as error:
                raise ValueError("native totals line must be ASCII") from error
            _require(len(fields) == 6, "native totals column count mismatch")
            chrom, pos, ref, alt, ac, an = fields
            if ac == "." or an == ".":
                raise ValueError("native_count_unavailable")
            _require(
                all(_NATURAL.fullmatch(value) is not None for value in (pos, ac, an)),
                "invalid native total",
            )
            variant_id = f"GRCh38:{chrom}:{int(pos)}:{ref}:{alt}"
            _require(variant_id not in seen, "duplicate native total variant")
            seen.add(variant_id)
            result.append((variant_id, int(ac), int(an)))
    return tuple(result)

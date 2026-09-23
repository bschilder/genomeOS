"""Validate frozen native-run receipts (reference acquisition design §6.2)."""
from __future__ import annotations

from pathlib import Path

from genomeos.validation.reference_cohorts import TECHNICAL_STAGE
from scripts.reference_artifact_io import require as _require
from scripts.reference_cohort_artifacts import COHORT_PATHS as _COHORT_PATHS
from scripts.reference_runtime import campaign_source_hashes, validate_runtime_provenance

_NATIVE_STDOUT_LIMITS = {
    "extract_bcf": 2_147_483_648,
    "query_keys": 2_147_483_648,
    "select_cohort": 2_147_483_648,
    "fill_tags": 2_147_483_648,
    "query_samples": 1_048_576,
    "query_tokens": 2_147_483_648,
    "query_totals": 2_147_483_648,
}

def _check_provenance(provenance: object, *, phase: str) -> None:
    checkout = Path(__file__).resolve().parents[1]
    expected = campaign_source_hashes(checkout)
    _require(
        provenance.imported_source_sha256 == expected,
        "imported source hash map is incomplete or changed",
    )
    validate_runtime_provenance(provenance, phase=phase)


def _check_native_run_limits(run: object) -> None:
    _require(
        run.stdout_limit_bytes == _NATIVE_STDOUT_LIMITS[run.operation]
        and run.stderr_limit_bytes == 1_048_576,
        "native process receipt uses noncanonical bounds",
    )


def _check_run_template(
    run: object,
    expected: tuple[str, ...],
    *,
    stdout_path: str,
    stderr_path: str,
) -> None:
    _check_native_run_limits(run)
    _require(run.argv_template == expected, "native process argv differs from frozen command")
    suffix = ".partial" if run.state == "refused" else ""
    _require(
        run.stdout.path == f"{stdout_path}{suffix}"
        and run.stderr.path == f"{stderr_path}{suffix}",
        "native process outputs differ from the fixed layout",
    )


def _check_acquisition_runs(window: object, source: object, frozen_window: object) -> None:
    if not window.native_runs:
        return
    _require(source.verified is not None, "native window lacks verified source")
    region = f"{window.chrom}:{frozen_window.start0 + 1}-{frozen_window.end0}"
    templates = (
        (
            "bcftools", "view", "--no-version", "-r", region,
            "--regions-overlap", "0", "-Ob", source.verified.sparse_path,
        ),
        (
            "bcftools", "query", "-f",
            r"%CHROM\t%POS\t%REF\t%ALT\t%FILTER\n",
            f"windows/{window.window_id}.native.bcf",
        ),
    )
    paths = (
        (f"windows/{window.window_id}.native.bcf", f"windows/{window.window_id}.extract.stderr"),
        (f"windows/{window.window_id}.native.keys.tsv", f"windows/{window.window_id}.keys.stderr"),
    )
    for run, expected, (stdout_path, stderr_path) in zip(
        window.native_runs, templates, paths, strict=False
    ):
        _check_run_template(
            run,
            expected,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )


def _check_stage_runs(window: object, stage: object) -> None:
    control = stage.native_control
    tokens = stage.native_tokens
    prefix = f"native/{window.window_id}.{stage.stage}"
    if control is not None:
        sample_path = _COHORT_PATHS[
            "technical_samples" if stage.stage == TECHNICAL_STAGE else "paper_samples"
        ]
        templates = (
            (
                "bcftools", "view", "--no-version", "-S", sample_path,
                "-m2", "-M2", "-v", "snps", "-f", "PASS", "-Ob",
                control.input_bcf.path,
            ),
            (
                "bcftools", "+fill-tags", f"{prefix}.selected.bcf",
                "--no-version", "-Ob", "--", "-t", "AC,AN",
            ),
            ("bcftools", "query", "-l", f"{prefix}.recomputed.bcf"),
            (
                "bcftools", "query", "-f",
                r"%CHROM\t%POS\t%REF\t%ALT\t%INFO/AC\t%INFO/AN\n",
                f"{prefix}.recomputed.bcf",
            ),
        )
        paths = (
            (f"{prefix}.selected.bcf", f"{prefix}.selected.bcf.stderr"),
            (f"{prefix}.recomputed.bcf", f"{prefix}.recomputed.bcf.stderr"),
            (f"{prefix}.samples.txt", f"{prefix}.samples.txt.stderr"),
            (f"{prefix}.totals.tsv", f"{prefix}.totals.tsv.stderr"),
        )
        for run, expected, (stdout_path, stderr_path) in zip(
            control.runs, templates, paths, strict=False
        ):
            _check_run_template(
                run,
                expected,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
    if tokens is not None:
        token_templates = (
            ("bcftools", "query", "-l", tokens.input_bcf.path),
            (
                "bcftools", "query", "-f",
                r"%CHROM\t%POS\t%REF\t%ALT[\t%GT:%GQ:%DP:%AD]\n",
                tokens.input_bcf.path,
            ),
        )
        _check_run_template(
            tokens.sample_query,
            token_templates[0],
            stdout_path=f"{prefix}.tokens.samples.txt",
            stderr_path=f"{prefix}.tokens.samples.stderr",
        )
        if tokens.token_query is not None:
            _check_run_template(
                tokens.token_query,
                token_templates[1],
                stdout_path=f"{prefix}.tokens.tokens.tsv",
                stderr_path=f"{prefix}.tokens.tokens.stderr",
            )

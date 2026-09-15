"""Reference acquisition/preparation CLI controls (reference acquisition design §7)."""

from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from genomeos.validation.reference_acquisition_codec import (
    decode_acquisition_review,
    encode_acquisition_review,
)
from genomeos.validation.reference_acquisition_types import (
    AcquisitionReviewBundle,
    ArtifactRef,
    HeaderReceipt,
    MetadataReceipt,
    NativeCountFiles,
    NativeRunReceipt,
    NativeTokenFiles,
    RangeReceipt,
    RetainedIndex,
    RunProvenance,
    VerifiedRange,
    VerifiedSource,
)
from genomeos.validation.reference_cohorts import (
    PAPER_STAGE,
    TECHNICAL_STAGE,
    Cohort,
    QualifiedCohortInputs,
    Sample,
    qualify_cohort_inputs,
)
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight
from genomeos.validation.reference_preparation_codec import encode_preparation
from genomeos.validation.reference_vcf_tokens import HeaderEvidence
from genomeos.validation.reference_window_manifest import decode_manifest
from scripts import acquire_reference_windows as acquisition_cli
from scripts import prepare_reference_window_counts as preparation_cli
from scripts import reference_count_replay as count_replay
from scripts import reference_runtime as runtime
from scripts import reference_window_artifacts as artifact_io
from scripts.acquire_reference_windows import compose_acquisition
from scripts.acquire_reference_windows import main as acquire_main
from scripts.prepare_reference_window_counts import compose_preparation
from scripts.prepare_reference_window_counts import main as prepare_main
from scripts.reference_window_artifacts import validate_acquisition, validate_preparation
from tests.reference_acquisition_fixture import synthetic_preflight_case

_BGZF_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")


@pytest.mark.parametrize("main", [acquire_main, prepare_main])
def test_help_is_read_only(monkeypatch, main):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external operation")

    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr(acquisition_cli, "_revision", lambda: "a" * 40)
    monkeypatch.setattr("subprocess.run", forbidden)
    assert main(["--help"]) == 0


def test_runtime_provenance_resolves_and_hashes_every_required_component(tmp_path, monkeypatch):
    prefix = tmp_path / "bcftools-1.23.1"
    hts_prefix = tmp_path / "htslib-1.23.1"
    sdk = tmp_path / "google-cloud-sdk"
    files = {
        "bcftools": prefix / "bin" / "bcftools",
        "fill-tags": prefix / "libexec" / "bcftools" / "fill-tags.so",
        "htslib": hts_prefix / "lib" / "libhts.3.dylib",
        "tabix": hts_prefix / "bin" / "tabix",
        "bgzip": hts_prefix / "bin" / "bgzip",
        "gcloud": sdk / "bin" / "gcloud",
    }
    for name, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic-{name}\n".encode())
    for relative in runtime._SDK_FILES:
        path = sdk / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic-{relative}\n".encode())
    links = tmp_path / "bin"
    links.mkdir()
    for name in ("bcftools", "tabix", "bgzip", "gcloud"):
        (links / name).symlink_to(files[name])

    def version(argv):
        name = Path(argv[0]).name
        if name == "bcftools" and "+fill-tags" in argv:
            return "bcftools  1.23.1 using htslib 1.23.1\nplugin at 1.23.1 using htslib 1.23.1"
        if name == "bcftools":
            return "bcftools 1.23.1\nUsing htslib 1.23.1"
        if name in ("tabix", "bgzip"):
            return f"{name} (htslib) 1.23.1"
        if name == "gcloud":
            return '{"Google Cloud SDK":"574.0.0"}'
        raise AssertionError(argv)

    monkeypatch.setattr(runtime, "_capture", version)
    monkeypatch.setattr(runtime, "_htslib", lambda executable: files["htslib"])
    monkeypatch.setattr(runtime.shutil, "which", lambda name: str(links / name))
    versions, hashes, sdk_hashes = runtime.acquisition_runtime(
        links / "bcftools", links / "tabix", links / "bgzip"
    )

    assert {name for name, _ in versions} == {
        "bcftools", "bcftools_fill_tags", "bcftools_htslib", "tabix", "bgzip", "gcloud",
    }
    assert {name for name, _ in hashes} == {
        "bcftools", "bcftools_fill_tags", "bcftools_htslib", "tabix", "bgzip", "gcloud",
    }
    assert dict(hashes)["bcftools"] == hashlib.sha256(files["bcftools"].read_bytes()).hexdigest()
    assert {name for name, _ in sdk_hashes} == set(runtime._SDK_FILES)

    prep_versions, prep_hashes, prep_sdk = runtime.preparation_runtime(links / "bcftools")
    assert {name for name, _ in prep_versions} == {
        "bcftools", "bcftools_fill_tags", "bcftools_htslib",
    }
    assert {name for name, _ in prep_hashes} == {
        "bcftools", "bcftools_fill_tags", "bcftools_htslib",
    }
    assert prep_sdk == ()


def test_runtime_probe_uses_the_frozen_stderr_allowance():
    output = runtime._capture(
        [
            sys.executable,
            "-c",
            "import sys; print('version'); sys.stderr.write('x' * 70000)",
        ]
    )
    assert output.startswith("version\n")
    assert len(output) > 65_536


def test_resolved_runtime_path_survives_later_symlink_swap(tmp_path):
    first = tmp_path / "bcftools-a"
    second = tmp_path / "bcftools-b"
    first.write_bytes(b"reviewed executable\n")
    second.write_bytes(b"replacement executable\n")
    link = tmp_path / "bcftools"
    link.symlink_to(first)

    resolved = runtime.resolve_executable(link)
    link.unlink()
    link.symlink_to(second)

    assert resolved == first.resolve()
    assert resolved.read_bytes() == b"reviewed executable\n"
    assert runtime.resolve_executable(link) == second.resolve()


def test_campaign_hashes_refuse_loaded_module_from_another_checkout(tmp_path, monkeypatch):
    checkout = Path(__file__).resolve().parents[1]
    foreign = tmp_path / "reference_runtime.py"
    foreign.write_text("# foreign checkout\n")
    monkeypatch.setattr(runtime, "__file__", str(foreign))

    with pytest.raises(ValueError, match="campaign import origin mismatch"):
        runtime.campaign_source_hashes(checkout)


def test_campaign_hashes_refuse_source_symlink_outside_checkout(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    (checkout / "scripts").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("# outside checkout\n")
    (checkout / "scripts/reference_runtime.py").symlink_to(outside)
    monkeypatch.setattr(runtime, "CAMPAIGN_SOURCE_FILES", ("scripts/reference_runtime.py",))

    with pytest.raises(ValueError, match="invalid campaign source"):
        runtime.campaign_source_hashes(checkout)


@pytest.mark.parametrize("module", [acquisition_cli, preparation_cli])
def test_revision_timeout_is_a_closed_invalid_input(module, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 10)

    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="invalid_input"):
        module._revision()


def _synthetic_inputs(root: Path, *, source_size_bytes: int = 2_097_152) -> list[str]:
    manifest, manifest_raw, preflight_raw, indexes, review = synthetic_preflight_case(
        source_size_bytes=source_size_bytes
    )
    windows = root / "windows"
    preflight = root / "preflight"
    windows.mkdir()
    (preflight / "indexes").mkdir(parents=True)
    (windows / "manifest.json").write_bytes(manifest_raw)
    from genomeos.validation.reference_window_manifest import windows_tsv

    (windows / "windows.tsv").write_bytes(windows_tsv(manifest.windows))
    (preflight / "preflight.json").write_bytes(preflight_raw)
    for value in indexes:
        (preflight / "indexes" / f"{value.chrom}.tbi").write_bytes(value.raw)
    review_path = root / "review.json"
    review_path.write_bytes(
        encode_acquisition_review(
            AcquisitionReviewBundle(
                "reference_acquisition_review_bundle_v1",
                review,
                "a" * 40,
                runtime.campaign_source_hashes(),
                "reviews/reference-acquisition.md",
                "e" * 64,
                "accepted",
            )
        )
    )
    qualified = _synthetic_cohort_inputs()
    inputs = {}
    for name, raw in {
        "metadata": qualified.metadata,
        "outliers": qualified.outliers,
        "cohort-exclusions": qualified.exclusions,
        "technical-samples": qualified.technical_samples,
        "paper-samples": qualified.paper_samples,
        "dependency-audit": qualified.dependency_audit,
    }.items():
        path = root / name
        path.write_bytes(raw)
        inputs[name] = path
    tool = root / "tool"
    tool.write_text("synthetic")
    return [
        "--windows-dir", str(windows),
        "--preflight-dir", str(preflight),
        "--review", str(review_path),
        "--metadata", str(inputs["metadata"]),
        "--outliers", str(inputs["outliers"]),
        "--cohort-exclusions", str(inputs["cohort-exclusions"]),
        "--technical-samples", str(inputs["technical-samples"]),
        "--paper-samples", str(inputs["paper-samples"]),
        "--dependency-audit", str(inputs["dependency-audit"]),
        "--bcftools", str(tool),
        "--tabix", str(tool),
        "--bgzip", str(tool),
        "--out", str(root / "out"),
    ]


def _put(root: Path, relative: str, raw: bytes) -> ArtifactRef:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return ArtifactRef(relative, len(raw), hashlib.sha256(raw).hexdigest())


def _install_acquisition_adapters(
    monkeypatch,
    *,
    fail_chrom: str | None = None,
    false_metadata_refusal_chrom: str | None = None,
    retained_window: str | None = None,
    retained_records: int = 1,
    record_alts: tuple[str, ...] | None = None,
    sample_token: str = "0/1:30:20:10,10",
    source_samples: tuple[str, ...] = (),
) -> None:
    if not source_samples:
        source_samples = _synthetic_cohort_inputs().source_samples

    def validate_original(*args, artifact_root, raw, offsets, native_keys, **kwargs):
        del args, offsets, kwargs
        raw_lines = (artifact_root / raw.path).read_bytes().splitlines()
        native_lines = (artifact_root / native_keys.path).read_bytes().splitlines()
        assert len(raw_lines) == len(native_lines)
        return len(raw_lines)

    monkeypatch.setattr(artifact_io, "validate_original_records", validate_original)
    monkeypatch.setattr(acquisition_cli, "validate_original_records", validate_original)
    monkeypatch.setattr(
        artifact_io,
        "parse_header",
        lambda raw, *, expected_contigs, source_chrom, expected_samples: HeaderEvidence(
            expected_samples,
            tuple(
                [
                    (
                        source_chrom,
                        dict(expected_contigs)[source_chrom],
                        "gnomAD_GRCh38",
                    )
                ]
                + [
                    (chrom, length, "gnomAD_GRCh38")
                    for chrom, length in expected_contigs
                    if chrom != source_chrom
                ]
            ),
            (
                ("GT", "1", "String"),
                ("GQ", "1", "Integer"),
                ("DP", "1", "Integer"),
                ("AD", "R", "Integer"),
            ),
            hashlib.sha256(raw).hexdigest(),
        ),
    )

    def metadata(source, *, wrapper, artifact_root, destination, gcloud_executable):
        del wrapper, gcloud_executable
        chrom = "chr" + source.uri.rsplit(".chr", 1)[1].split(".", 1)[0]
        raw = (json.dumps(
            {
                "generation": source.generation,
                "size": str(source.size_bytes),
                "md5Hash": source.md5_b64,
                "crc32c": source.crc32c_b64,
            },
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n").encode()
        refused = chrom == false_metadata_refusal_chrom
        suffix = ".partial" if refused else ""
        stdout = _put(artifact_root, f"{destination}{suffix}", raw)
        stderr = _put(artifact_root, f"{destination}.stderr{suffix}", b"")
        return MetadataReceipt(
            "refused" if refused else "verified",
            "metadata_mismatch" if refused else None,
            1,
            len(raw),
            stdout,
            stderr,
            0,
            False,
            False,
        )

    def source_bytes(source) -> bytes:
        chrom = "chr" + source.uri.rsplit(".chr", 1)[1].split(".", 1)[0]
        header_raw = f"synthetic {chrom} header\n".encode()
        return (
            header_raw
            + b"x" * (source.size_bytes - len(header_raw) - len(_BGZF_EOF))
            + _BGZF_EOF
        )

    def fetch(source, byte_range, *, wrapper, artifact_root, destination, gcloud_executable):
        del wrapper, gcloud_executable
        raw = source_bytes(source)[byte_range.first : byte_range.last + 1]
        chrom = "chr" + source.uri.rsplit(".chr", 1)[1].split(".", 1)[0]
        if chrom == fail_chrom:
            raw = raw[:1]
        retained_path = (
            f"{destination.as_posix()}.partial" if chrom == fail_chrom else destination.as_posix()
        )
        stdout = _put(artifact_root, retained_path, raw)
        stderr_path = (
            f"{destination}.stderr.partial" if chrom == fail_chrom else f"{destination}.stderr"
        )
        stderr = _put(artifact_root, stderr_path, b"")
        requested = byte_range.last - byte_range.first + 1
        complete = chrom != fail_chrom
        return RangeReceipt(
            chrom,
            source.generation,
            byte_range.first,
            byte_range.last,
            requested,
            len(raw),
            1,
            "verified" if complete else "partial",
            None if complete else "size_mismatch",
            stdout.sha256,
            stdout,
            stderr,
            0,
            False,
            False,
        )

    def stage(plan, receipts, *, artifact_root, index, sparse_path):
        path = artifact_root / sparse_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source_bytes(plan.source.vcf))
        return VerifiedSource(
            plan.source,
            tuple(VerifiedRange(value.first, value.last, value.retained) for value in receipts),
            sparse_path,
            index,
            plan.source.vcf.size_bytes,
            path.stat().st_blocks * 512,
            False,
        )

    def header(verified, plan, *, artifact_root, expected_contigs, expected_samples, destination):
        del verified
        assert expected_samples == source_samples
        raw = f"synthetic {plan.source.chrom} header\n".encode()
        artifact = _put(artifact_root, destination.as_posix(), raw)
        contigs = tuple(
            [next(value for value in expected_contigs if value[0] == plan.source.chrom)]
            + [value for value in expected_contigs if value[0] != plan.source.chrom]
        )
        evidence = HeaderEvidence(
            source_samples,
            tuple((chrom, length, "gnomAD_GRCh38") for chrom, length in contigs),
            (("GT", "1", "String"), ("GQ", "1", "Integer"),
             ("DP", "1", "Integer"), ("AD", "R", "Integer")),
            hashlib.sha256(raw).hexdigest(),
        )
        sample_bytes = "".join(f"{sample}\n" for sample in source_samples).encode()
        receipt = HeaderReceipt(
            artifact,
            hashlib.sha256(sample_bytes).hexdigest(),
            len(source_samples),
            "exact_metadata_plus_control",
            "frozen_manifest_assembly_and_lengths",
            "verified",
        )
        return evidence, receipt

    def replay_header(
        verified, plan, *, artifact_root, expected_contigs, expected_samples
    ):
        raw = (artifact_root / verified.sparse_path).read_bytes().splitlines(keepends=True)[0]
        contigs = tuple(
            [next(value for value in expected_contigs if value[0] == plan.source.chrom)]
            + [value for value in expected_contigs if value[0] != plan.source.chrom]
        )
        return raw, HeaderEvidence(
            expected_samples,
            tuple((chrom, length, "gnomAD_GRCh38") for chrom, length in contigs),
            (("GT", "1", "String"), ("GQ", "1", "Integer"),
             ("DP", "1", "Integer"), ("AD", "R", "Integer")),
            hashlib.sha256(raw).hexdigest(),
        )

    retained_keys: bytes | None = None

    def records(
        verified, plan, window, header_evidence, *, artifact_root, raw_destination,
        offsets_destination,
    ):
        nonlocal retained_keys
        del verified, plan, header_evidence
        raw = b""
        offsets = b"ordinal\tsource_virtual_offset\traw_sha256\n"
        found = window.window_id == retained_window
        if found:
            rows = []
            keys = []
            alts = record_alts or ("G",) * retained_records
            for ordinal, alt in enumerate(alts):
                row = (
                    "\t".join(
                        (
                            window.chrom,
                            str(window.start0 + ordinal + 1),
                            ".",
                            "A",
                            alt,
                            ".",
                            "PASS",
                            ".",
                            "GT:GQ:DP:AD",
                            *(sample_token for _ in source_samples),
                        )
                    ) + "\n"
                ).encode()
                rows.append(row)
                keys.append(
                    f"{window.chrom}\t{window.start0 + ordinal + 1}\tA\t{alt}\tPASS\n".encode()
                )
                offsets += f"{ordinal}\t{ordinal}\t{hashlib.sha256(row).hexdigest()}\n".encode()
            raw = b"".join(rows)
            retained_keys = b"".join(keys)
        _put(artifact_root, raw_destination.as_posix(), raw)
        _put(
            artifact_root,
            offsets_destination.as_posix(),
            offsets,
        )
        return iter(object() for _ in range(len(alts))) if found else iter(())

    def native(verified, plan, window, *, artifact_root, bcftools, stdout_path, stderr_path):
        del plan, bcftools
        stdout = _put(artifact_root, stdout_path, b"BCF\x04\x02")
        stderr = _put(artifact_root, stderr_path, b"")
        return NativeRunReceipt(
            "extract_bcf",
            (
                "bcftools", "view", "--no-version", "-r",
                f"{window.chrom}:{window.start0 + 1}-{window.end0}",
                "--regions-overlap", "0", "-Ob", verified.sparse_path,
            ),
            "complete", None, 0,
            stdout, stderr, 2_147_483_648, 1_048_576, False, False,
        )

    def keys(bcf, *, artifact_root, stdout_path, stderr_path, **kwargs):
        del kwargs
        window_id = bcf.path.removeprefix("windows/").removesuffix(".native.bcf")
        if window_id == retained_window:
            assert retained_keys is not None
            raw = retained_keys
        else:
            raw = b""
        stdout = _put(artifact_root, stdout_path, raw)
        stderr = _put(artifact_root, stderr_path, b"")
        return NativeRunReceipt(
            "query_keys",
            (
                "bcftools", "query", "-f",
                r"%CHROM\t%POS\t%REF\t%ALT\t%FILTER\n", bcf.path,
            ),
            "complete", None, 0,
            stdout, stderr, 2_147_483_648, 1_048_576, False, False,
        )

    monkeypatch.setattr(acquisition_cli, "fetch_metadata", metadata)
    monkeypatch.setattr(acquisition_cli, "fetch_range", fetch)
    monkeypatch.setattr(acquisition_cli, "stage_sparse", stage)
    monkeypatch.setattr(acquisition_cli, "read_source_header", header)
    monkeypatch.setattr(artifact_io, "load_source_header", replay_header)
    monkeypatch.setattr(acquisition_cli, "iter_original_records", records)
    monkeypatch.setattr(acquisition_cli, "extract_native", native)
    monkeypatch.setattr(acquisition_cli, "query_native_keys", keys)


def test_public_evidence_cli_refuses_synthetic_cohort_before_external_work(tmp_path, monkeypatch):
    argv = _synthetic_inputs(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external operation")

    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr(acquisition_cli, "_revision", lambda: "a" * 40)
    monkeypatch.setattr("subprocess.run", forbidden)
    assert acquire_main(argv) == 2
    assert not (tmp_path / "out").exists()


def test_acquisition_cli_refuses_missing_review_without_output(tmp_path, monkeypatch):
    argv = _synthetic_inputs(tmp_path)
    review_index = argv.index("--review") + 1
    argv[review_index] = str(tmp_path / "missing-review.json")
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected external operation")),
    )
    assert acquire_main(argv) == 2
    assert not (tmp_path / "out").exists()


def test_acquisition_cli_refuses_changed_reviewed_source_hash_before_external_work(
    tmp_path, monkeypatch,
):
    argv = _synthetic_inputs(tmp_path)
    review_path = Path(argv[argv.index("--review") + 1])
    review = decode_acquisition_review(review_path.read_bytes())
    first, *remaining = review.implementation_sha256
    changed = replace(
        review,
        implementation_sha256=((first[0], "0" * 64), *remaining),
    )
    review_path.write_bytes(encode_acquisition_review(changed))

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external operation")

    monkeypatch.setattr(acquisition_cli, "_revision", lambda: "a" * 40)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    assert acquire_main(argv) == 2
    assert not (tmp_path / "out").exists()


def test_acquisition_cli_refuses_existing_output_before_reads(tmp_path, monkeypatch):
    output = tmp_path / "existing"
    output.mkdir()
    argv = [
        "--windows-dir", str(tmp_path / "missing"), "--preflight-dir", str(tmp_path / "missing"),
        "--review", str(tmp_path / "missing"), "--metadata", str(tmp_path / "missing"),
        "--outliers", str(tmp_path / "missing"), "--cohort-exclusions", str(tmp_path / "missing"),
        "--technical-samples", str(tmp_path / "missing"),
        "--paper-samples", str(tmp_path / "missing"),
        "--dependency-audit", str(tmp_path / "missing"), "--bcftools", str(tmp_path / "missing"),
        "--tabix", str(tmp_path / "missing"), "--bgzip", str(tmp_path / "missing"),
        "--out", str(output),
    ]
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected external operation")),
    )
    assert acquire_main(argv) == 2
    assert tuple(output.iterdir()) == ()


@pytest.mark.parametrize("entrypoint", [acquire_main, prepare_main])
def test_cli_parse_errors_emit_only_the_closed_reason(entrypoint, capsys):
    assert entrypoint([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error:invalid_input\n"


def test_preparation_cli_rejects_incomplete_acquisition_before_output(tmp_path):
    output = tmp_path / "counts"
    argv = [
        "--acquisition", str(tmp_path / "missing"), "--metadata", str(tmp_path / "missing"),
        "--outliers", str(tmp_path / "missing"), "--cohort-exclusions", str(tmp_path / "missing"),
        "--technical-samples", str(tmp_path / "missing"),
        "--paper-samples", str(tmp_path / "missing"),
        "--dependency-audit", str(tmp_path / "missing"), "--bcftools", str(tmp_path / "missing"),
        "--out", str(output),
    ]
    assert prepare_main(argv) == 2
    assert not output.exists()


def _preparation_argv(root: Path) -> list[str]:
    return [
        "--acquisition", str(root / "out"),
        "--metadata", str(root / "metadata"),
        "--outliers", str(root / "outliers"),
        "--cohort-exclusions", str(root / "cohort-exclusions"),
        "--technical-samples", str(root / "technical-samples"),
        "--paper-samples", str(root / "paper-samples"),
        "--dependency-audit", str(root / "dependency-audit"),
        "--bcftools", str(root / "tool"),
        "--out", str(root / "counts"),
    ]


def _cohort(stage: str, size: int) -> Cohort:
    populations = tuple(
        sorted(
            {
                "CDX",
                "Dai",
                "Cambodian",
                "Japanese",
                "ITU",
                "STU",
                *(f"Population{index:02d}" for index in range(74)),
            }
        )
    )
    samples = tuple(
        Sample(
            f"sample-{index:04d}",
            populations[index % len(populations)],
            "synthetic-region",
            False,
        )
        for index in range(size)
    )
    return Cohort(stage, samples)


def _synthetic_cohort_inputs(root: Path | None = None) -> QualifiedCohortInputs:
    technical = _cohort(TECHNICAL_STAGE, 4_117)
    paper = _cohort(PAPER_STAGE, 4_094)
    populations = tuple(sample.population for sample in technical.samples[:80])
    extras = (
        Sample("sample-4117", populations[37], "synthetic-region", False),
        Sample("sample-4118", populations[38], "synthetic-region", False),
        *(
            Sample(
                f"sample-{index:04d}",
                populations[index % 80],
                "synthetic-region",
                True,
            )
            for index in range(4_119, 4_150)
        ),
    )
    metadata_samples = (*technical.samples, *extras)
    metadata = (
        "s\tpopulation\thgdp_tgp_meta.Genetic.region\t"
        "sample_filters.hard_filtered\n"
        + "".join(
            f"{sample.sample_id}\t{sample.population}\t{sample.region}\t"
            f"{'true' if sample.hard_filtered else 'false'}\n"
            for sample in metadata_samples
        )
    ).encode()
    raw = {
        "metadata": metadata,
        "outliers": "".join(
            f"sample-{index:04d}\n" for index in range(4_094, 4_117)
        ).encode(),
        "exclusions": (
            b'{"contamination_ids":["sample-4117","sample-4118"],'
            b'"control_id":"synthetic-control",'
            b'"schema_version":"reference_cohort_exclusions_v1"}\n'
        ),
        "technical_samples": "".join(
            f"{sample.sample_id}\n" for sample in technical.samples
        ).encode(),
        "paper_samples": "".join(
            f"{sample.sample_id}\n" for sample in paper.samples
        ).encode(),
        "dependency_audit": b"{}\n",
    }
    if root is not None:
        for name, value in raw.items():
            disk_name = "cohort-exclusions" if name == "exclusions" else name.replace("_", "-")
            if name in ("technical_samples", "paper_samples"):
                disk_name = name.replace("_", "-")
            assert (root / disk_name).read_bytes() == value
    return qualify_cohort_inputs(*(raw[name] for name in (
        "metadata",
        "outliers",
        "exclusions",
        "technical_samples",
        "paper_samples",
        "dependency_audit",
    )))


def _fake_runtime_identity(*, acquisition: bool):
    versions = {
        "bcftools": "bcftools 1.23.1",
        "bcftools_fill_tags": (
            "bcftools  1.23.1 using htslib 1.23.1\n"
            "plugin at 1.23.1 using htslib 1.23.1"
        ),
        "bcftools_htslib": "Using htslib 1.23.1",
    }
    if acquisition:
        versions.update(
            {
                "tabix": "tabix (htslib) 1.23.1",
                "bgzip": "bgzip (htslib) 1.23.1",
                "gcloud": '{"Google Cloud SDK":"574.0.0"}',
            }
        )
    names = tuple(sorted(versions))
    return (
        tuple((name, versions[name]) for name in names),
        tuple((name, "d" * 64) for name in names),
        tuple((name, "e" * 64) for name in runtime._SDK_FILES) if acquisition else (),
    )


def _acquisition_composition(root: Path) -> acquisition_cli.AcquisitionCompositionInputs:
    manifest_raw = (root / "windows/manifest.json").read_bytes()
    windows_raw = (root / "windows/windows.tsv").read_bytes()
    preflight_raw = (root / "preflight/preflight.json").read_bytes()
    review_raw = (root / "review.json").read_bytes()
    manifest = decode_manifest(manifest_raw, windows_bytes=windows_raw)
    review = decode_acquisition_review(review_raw)
    indexes = tuple(
        RetainedIndex(
            f"chr{chrom}",
            (root / f"preflight/indexes/chr{chrom}.tbi").read_bytes(),
        )
        for chrom in range(1, 23)
    )
    preflight = decode_reviewed_preflight(
        preflight_raw,
        manifest=manifest,
        manifest_raw=manifest_raw,
        indexes=indexes,
        review=review.preflight,
    )
    return acquisition_cli.AcquisitionCompositionInputs(
        root / "out",
        manifest,
        manifest_raw,
        windows_raw,
        preflight,
        preflight_raw,
        review,
        review_raw,
        indexes,
        _synthetic_cohort_inputs(root),
        root / "tool",
        root / "tool",
        root / "tool",
        root / "tool",
        RunProvenance(
            "a" * 40,
            platform.python_version(),
            runtime.campaign_source_hashes(),
            *_fake_runtime_identity(acquisition=True),
        ),
    )


def _preparation_composition(root: Path) -> preparation_cli.PreparationCompositionInputs:
    cohort = _synthetic_cohort_inputs(root)
    acquisition_root = root / "out"
    acquisition = validate_acquisition(acquisition_root, cohort_inputs=cohort)
    return preparation_cli.PreparationCompositionInputs(
        root / "counts",
        acquisition_root,
        acquisition,
        (acquisition_root / "acquisition.json").read_bytes(),
        cohort,
        root / "tool",
        RunProvenance(
            acquisition.provenance.code_revision,
            platform.python_version(),
            acquisition.provenance.imported_source_sha256,
            *_fake_runtime_identity(acquisition=False),
        ),
    )


def test_preparation_composition_binds_qualified_cohort_bytes_to_acquisition(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    _install_acquisition_adapters(monkeypatch)
    compose_acquisition(_acquisition_composition(tmp_path))
    inputs = _preparation_composition(tmp_path)
    cohort = inputs.cohort
    changed = qualify_cohort_inputs(
        cohort.metadata,
        cohort.outliers,
        cohort.exclusions,
        cohort.technical_samples,
        cohort.paper_samples,
        b'{"changed":true}\n',
    )
    with pytest.raises(ValueError, match="invalid preparation composition inputs"):
        replace(inputs, cohort=changed)


def _install_preparation_adapters(
    monkeypatch,
    *,
    technical: Cohort | None = None,
    paper: Cohort | None = None,
    retained_variant: str | None = None,
    retained_variants: tuple[str, ...] | None = None,
    native_variants: tuple[str, ...] | None = None,
) -> None:
    technical = technical or _cohort(TECHNICAL_STAGE, 4_117)
    paper = paper or _cohort(PAPER_STAGE, 4_094)
    source_samples = _synthetic_cohort_inputs().source_samples
    def parse_header_adapter(*args, **kwargs):
        return HeaderEvidence(
            source_samples,
            ((kwargs["source_chrom"], 100_000, "gnomAD_GRCh38"),),
            (("GT", "1", "String"), ("GQ", "1", "Integer"),
             ("DP", "1", "Integer"), ("AD", "R", "Integer")),
            "c" * 64,
        )

    monkeypatch.setattr(preparation_cli, "parse_header", parse_header_adapter)
    monkeypatch.setattr(count_replay, "parse_header", parse_header_adapter)

    variants = retained_variants or (() if retained_variant is None else (retained_variant,))
    if not variants:
        def forbidden(*args, **kwargs):
            raise AssertionError("empty preparation must not invoke native adapters")

        monkeypatch.setattr(preparation_cli, "native_called_totals", forbidden)
        monkeypatch.setattr(preparation_cli, "query_native_tokens", forbidden)
        return

    parsed_native_variants = tuple(
        value.removeprefix("GRCh38:").split(":")
        for value in (native_variants or variants)
    )
    cohorts = {TECHNICAL_STAGE: technical, PAPER_STAGE: paper}

    def run(
        operation: str,
        stdout: ArtifactRef,
        stderr: ArtifactRef,
        template: tuple[str, ...],
    ) -> NativeRunReceipt:
        return NativeRunReceipt(
            operation,
            template,
            "complete",
            None,
            0,
            stdout,
            stderr,
            1_048_576 if operation == "query_samples" else 2_147_483_648,
            1_048_576,
            False,
            False,
        )

    def native_counts(
        bcf, cohort_samples, *, acquisition_root, artifact_root, bcftools, output_prefix,
    ):
        del acquisition_root, bcftools
        stage = next(value for value in cohorts if value in output_prefix)
        cohort = cohorts[stage]
        selected = _put(artifact_root, f"{output_prefix}.selected.bcf", b"BCF\x04\x02")
        recomputed = _put(artifact_root, f"{output_prefix}.recomputed.bcf", b"BCF\x04\x02tags")
        samples = _put(
            artifact_root,
            f"{output_prefix}.samples.txt",
            "".join(f"{value.sample_id}\n" for value in cohort.samples).encode(),
        )
        totals = _put(
            artifact_root,
            f"{output_prefix}.totals.tsv",
            "".join(
                f"{chrom}\t{pos}\t{ref}\t{alt}\t"
                + (
                    f"{len(cohort.samples)}\t{2 * len(cohort.samples)}\n"
                    if len(ref) == len(alt) == 1
                    and ref in "ACGT"
                    and alt in "ACGT"
                    and ref != alt
                    else ".\t.\n"
                )
                for chrom, pos, ref, alt in parsed_native_variants
            ).encode(),
        )
        stderrs = {
            "select_cohort": _put(artifact_root, f"{output_prefix}.selected.bcf.stderr", b""),
            "fill_tags": _put(artifact_root, f"{output_prefix}.recomputed.bcf.stderr", b""),
            "query_samples": _put(artifact_root, f"{output_prefix}.samples.txt.stderr", b""),
            "query_totals": _put(artifact_root, f"{output_prefix}.totals.tsv.stderr", b""),
        }
        external = ArtifactRef(f"@acquisition/{bcf.path}", bcf.size_bytes, bcf.sha256)
        runs = (
            run(
                "select_cohort",
                selected,
                stderrs["select_cohort"],
                (
                    "bcftools", "view", "--no-version", "-S", cohort_samples.path,
                    "-m2", "-M2", "-v", "snps", "-f", "PASS", "-Ob", external.path,
                ),
            ),
            run(
                "fill_tags",
                recomputed,
                stderrs["fill_tags"],
                (
                    "bcftools", "+fill-tags", selected.path, "--no-version",
                    "-Ob", "--", "-t", "AC,AN",
                ),
            ),
            run(
                "query_samples",
                samples,
                stderrs["query_samples"],
                ("bcftools", "query", "-l", recomputed.path),
            ),
            run(
                "query_totals",
                totals,
                stderrs["query_totals"],
                (
                    "bcftools", "query", "-f",
                    r"%CHROM\t%POS\t%REF\t%ALT\t%INFO/AC\t%INFO/AN\n",
                    recomputed.path,
                ),
            ),
        )
        return NativeCountFiles(
            external, cohort_samples, selected, recomputed, samples, totals, runs, "complete", None,
        )

    def native_tokens(bcf, *, artifact_root, bcftools, output_prefix):
        del bcftools
        stage = next(value for value in cohorts if value in output_prefix)
        cohort = cohorts[stage]
        samples = _put(
            artifact_root,
            f"{output_prefix}.samples.txt",
            "".join(f"{value.sample_id}\n" for value in cohort.samples).encode(),
        )
        tokens = _put(
            artifact_root,
            f"{output_prefix}.tokens.tsv",
            "".join(
                f"{chrom}\t{pos}\t{ref}\t{alt}\t"
                + "\t".join("0/1:30:20:10,10" for _ in cohort.samples)
                + "\n"
                for chrom, pos, ref, alt in parsed_native_variants
            ).encode(),
        )
        sample_stderr = _put(artifact_root, f"{output_prefix}.samples.stderr", b"")
        token_stderr = _put(artifact_root, f"{output_prefix}.tokens.stderr", b"")
        sample_run = run(
            "query_samples",
            samples,
            sample_stderr,
            ("bcftools", "query", "-l", bcf.path),
        )
        token_run = run(
            "query_tokens",
            tokens,
            token_stderr,
            (
                "bcftools", "query", "-f",
                r"%CHROM\t%POS\t%REF\t%ALT[\t%GT:%GQ:%DP:%AD]\n", bcf.path,
            ),
        )
        return NativeTokenFiles(
            bcf, samples, tokens, sample_run, token_run, "complete", None,
        )

    monkeypatch.setattr(preparation_cli, "native_called_totals", native_counts)
    monkeypatch.setattr(preparation_cli, "query_native_tokens", native_tokens)


def test_synthetic_acquisition_composes_22_sources_and_66_windows(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    _install_acquisition_adapters(monkeypatch)

    inputs = _acquisition_composition(tmp_path)
    result = compose_acquisition(inputs)
    assert validate_acquisition(tmp_path / "out", cohort_inputs=inputs.cohort) == result
    assert result.complete is True
    assert len(result.sources) == 22
    assert len(result.windows) == 66
    assert all(value.state == "ready" for value in result.sources)
    assert all(value.state == "no_records" for value in result.windows)


def test_synthetic_complete_empty_acquisition_prepares_four_tracks(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    _install_acquisition_adapters(monkeypatch)
    compose_acquisition(_acquisition_composition(tmp_path))
    _install_preparation_adapters(monkeypatch)

    inputs = _preparation_composition(tmp_path)
    result = compose_preparation(inputs)
    assert validate_preparation(
        tmp_path / "counts",
        acquisition_root=tmp_path / "out",
        cohort_inputs=inputs.cohort,
    ) == result
    assert result.status == "complete_empty"
    assert result.complete is True
    assert len(result.windows) == 66
    assert len(result.tracks) == 4
    assert all(value.rows == value.variants == value.represented_groups == 0 for value in result.tracks)


def test_synthetic_retained_snp_prepares_four_hand_checked_tracks(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    technical = _cohort(TECHNICAL_STAGE, 4_117)
    paper = _cohort(PAPER_STAGE, 4_094)
    source_samples = _synthetic_cohort_inputs().source_samples
    _install_acquisition_adapters(
        monkeypatch,
        retained_window="chr1-s1",
        source_samples=source_samples,
    )
    acquisition_inputs = _acquisition_composition(tmp_path)
    compose_acquisition(acquisition_inputs)
    parent = validate_acquisition(
        tmp_path / "out", cohort_inputs=acquisition_inputs.cohort
    )
    window = parent.windows[0]
    frozen = json.loads((tmp_path / "windows" / "manifest.json").read_bytes())
    start0 = next(value["start0"] for value in frozen["windows"] if value["window_id"] == "chr1-s1")
    variant_id = f"GRCh38:chr1:{start0 + 1}:A:G"
    _install_preparation_adapters(
        monkeypatch,
        technical=technical,
        paper=paper,
        retained_variant=variant_id,
    )

    assert window.state == "records_acquired"
    preparation_inputs = _preparation_composition(tmp_path)
    result = compose_preparation(preparation_inputs)
    assert result.status == "complete_nonempty"
    assert [(value.stage, value.kind, value.rows, value.variants) for value in result.tracks] == [
        (TECHNICAL_STAGE, "called", 80, 1),
        (TECHNICAL_STAGE, "quality", 80, 1),
        (PAPER_STAGE, "called", 80, 1),
        (PAPER_STAGE, "quality", 80, 1),
    ]
    assert [(value.ac_sum, value.an_sum) for value in result.tracks] == [
        (4_117, 8_234),
        (4_117, 8_234),
        (4_094, 8_188),
        (4_094, 8_188),
    ]


def test_two_variants_in_one_window_keep_global_record_id_order(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    technical = _cohort(TECHNICAL_STAGE, 4_117)
    paper = _cohort(PAPER_STAGE, 4_094)
    source_samples = _synthetic_cohort_inputs().source_samples
    _install_acquisition_adapters(
        monkeypatch,
        retained_window="chr1-s1",
        retained_records=2,
        source_samples=source_samples,
    )
    compose_acquisition(_acquisition_composition(tmp_path))
    frozen = json.loads((tmp_path / "windows" / "manifest.json").read_bytes())
    start0 = next(value["start0"] for value in frozen["windows"] if value["window_id"] == "chr1-s1")
    variants = tuple(f"GRCh38:chr1:{start0 + offset}:A:G" for offset in (1, 2))
    _install_preparation_adapters(
        monkeypatch,
        technical=technical,
        paper=paper,
        retained_variants=variants,
    )

    result = compose_preparation(_preparation_composition(tmp_path))
    assert all((track.rows, track.variants) == (160, 2) for track in result.tracks)
    for track in result.tracks:
        record_ids = [
            line.split("\t", 1)[0]
            for line in (tmp_path / "counts" / track.table.path).read_text().splitlines()[1:]
        ]
        assert record_ids == sorted(record_ids)
        assert len(record_ids) == len(set(record_ids)) == 160


def test_non_acgt_native_rows_are_accounted_then_excluded_before_join(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    technical = _cohort(TECHNICAL_STAGE, 4_117)
    paper = _cohort(PAPER_STAGE, 4_094)
    source_samples = _synthetic_cohort_inputs().source_samples
    _install_acquisition_adapters(
        monkeypatch,
        retained_window="chr1-s1",
        record_alts=("G", "N"),
        source_samples=source_samples,
    )
    compose_acquisition(_acquisition_composition(tmp_path))
    frozen = json.loads((tmp_path / "windows" / "manifest.json").read_bytes())
    start0 = next(value["start0"] for value in frozen["windows"] if value["window_id"] == "chr1-s1")
    retained = f"GRCh38:chr1:{start0 + 1}:A:G"
    excluded = f"GRCh38:chr1:{start0 + 2}:A:N"
    _install_preparation_adapters(
        monkeypatch,
        technical=technical,
        paper=paper,
        retained_variant=retained,
        native_variants=(retained, excluded),
    )

    result = compose_preparation(_preparation_composition(tmp_path))
    window = result.windows[0]
    assert window.raw_records == 2
    assert window.retained_variants == 1
    assert window.site_dispositions == (("not_acgt_snp", 1), ("retained", 1))
    assert all((track.rows, track.variants) == (80, 1) for track in result.tracks)


def test_invalid_original_qc_token_refuses_as_record_invalid(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    technical = _cohort(TECHNICAL_STAGE, 4_117)
    paper = _cohort(PAPER_STAGE, 4_094)
    source_samples = _synthetic_cohort_inputs().source_samples
    _install_acquisition_adapters(
        monkeypatch,
        retained_window="chr1-s1",
        sample_token="0/1:-1:20:10,10",
        source_samples=source_samples,
    )
    compose_acquisition(_acquisition_composition(tmp_path))
    frozen = json.loads((tmp_path / "windows" / "manifest.json").read_bytes())
    start0 = next(value["start0"] for value in frozen["windows"] if value["window_id"] == "chr1-s1")
    variant = f"GRCh38:chr1:{start0 + 1}:A:G"
    _install_preparation_adapters(
        monkeypatch,
        technical=technical,
        paper=paper,
        retained_variant=variant,
    )

    result = compose_preparation(_preparation_composition(tmp_path))
    assert result.windows[0].state == "refused"
    assert result.windows[0].reason == "record_invalid"
    assert all(stage.reason == "record_invalid" for stage in result.windows[0].stages)
    assert all(stage.summary is None for stage in result.windows[0].stages)


def test_one_stage_failure_withdraws_every_stage_summary(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    technical = _cohort(TECHNICAL_STAGE, 4_117)
    paper = _cohort(PAPER_STAGE, 4_094)
    source_samples = _synthetic_cohort_inputs().source_samples
    _install_acquisition_adapters(
        monkeypatch,
        retained_window="chr1-s1",
        source_samples=source_samples,
    )
    compose_acquisition(_acquisition_composition(tmp_path))
    frozen = json.loads((tmp_path / "windows" / "manifest.json").read_bytes())
    start0 = next(value["start0"] for value in frozen["windows"] if value["window_id"] == "chr1-s1")
    variant = f"GRCh38:chr1:{start0 + 1}:A:G"
    _install_preparation_adapters(
        monkeypatch,
        technical=technical,
        paper=paper,
        retained_variant=variant,
    )
    native_counts = preparation_cli.native_called_totals

    def fail_paper(*args, output_prefix, **kwargs):
        control = native_counts(*args, output_prefix=output_prefix, **kwargs)
        if PAPER_STAGE in output_prefix:
            assert control.selected_samples is not None
            sample_path = tmp_path / "counts" / control.selected_samples.path
            sample_path.write_bytes(b"unexpected-sample\n")
            samples = ArtifactRef(
                control.selected_samples.path,
                sample_path.stat().st_size,
                hashlib.sha256(sample_path.read_bytes()).hexdigest(),
            )
            totals = tmp_path / "counts" / control.runs[3].stdout.path
            totals_stderr = tmp_path / "counts" / control.runs[3].stderr.path
            totals.unlink()
            totals_stderr.unlink()
            runs = (*control.runs[:2], replace(control.runs[2], stdout=samples))
            return NativeCountFiles(
                control.input_bcf,
                control.requested_samples,
                control.selected_bcf,
                control.recomputed_bcf,
                samples,
                None,
                runs,
                "refused",
                "native_mismatch",
            )
        return control

    monkeypatch.setattr(preparation_cli, "native_called_totals", fail_paper)

    preparation_inputs = _preparation_composition(tmp_path)
    result = compose_preparation(preparation_inputs)
    window = result.windows[0]
    assert window.state == "refused"
    assert window.raw_records == 1 and window.retained_variants is None
    assert all(stage.state == "refused" and stage.summary is None for stage in window.stages)
    fragment = tmp_path / "counts/work/variant-windows/000-chr1-s1.part"
    assert fragment.is_file()
    assert any(value.path == "work/variant-windows/000-chr1-s1.part" for value in result.files)

    changed_window = replace(window, raw_records=2)
    windows = (changed_window, *result.windows[1:])
    ledger_ref = _put(tmp_path / "counts", "windows.tsv", preparation_cli._window_ledger(windows))
    changed = replace(
        result,
        windows=windows,
        files=tuple(
            ledger_ref if value.path == ledger_ref.path else value
            for value in result.files
        ),
    )
    (tmp_path / "counts/manifest.json").write_bytes(encode_preparation(changed))
    with pytest.raises(ValueError, match="raw count"):
        validate_preparation(
            tmp_path / "counts",
            acquisition_root=tmp_path / "out",
            cohort_inputs=preparation_inputs.cohort,
        )

    valid_ledger = _put(
        tmp_path / "counts",
        "windows.tsv",
        preparation_cli._window_ledger(result.windows),
    )
    valid_files = tuple(
        valid_ledger if value.path == valid_ledger.path else value
        for value in result.files
    )
    stage = result.windows[0].stages[0]
    wrong_samples = next(
        value
        for value in valid_files
        if value.path == "inputs/cohort/paper.samples.txt"
    )
    changed_stage = replace(
        stage,
        native_control=replace(stage.native_control, requested_samples=wrong_samples),
    )
    changed_window = replace(
        result.windows[0],
        stages=(changed_stage, result.windows[0].stages[1]),
    )
    changed = replace(
        result,
        windows=(changed_window, *result.windows[1:]),
        files=valid_files,
    )
    (tmp_path / "counts/manifest.json").write_bytes(encode_preparation(changed))
    with pytest.raises(ValueError, match="requested samples"):
        validate_preparation(
            tmp_path / "counts",
            acquisition_root=tmp_path / "out",
            cohort_inputs=preparation_inputs.cohort,
        )


def test_one_source_failure_keeps_full_ledger_and_blocks_preparation(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    _install_acquisition_adapters(monkeypatch, fail_chrom="chr1")

    acquisition_inputs = _acquisition_composition(tmp_path)
    result = compose_acquisition(acquisition_inputs)
    assert validate_acquisition(
        tmp_path / "out", cohort_inputs=acquisition_inputs.cohort
    ) == result
    assert result.complete is False
    assert len(result.sources) == 22
    assert len(result.windows) == 66
    assert [value.state for value in result.windows[:3]] == ["refused"] * 3
    assert all(value.state == "no_records" for value in result.windows[3:])

    assert prepare_main(_preparation_argv(tmp_path)) == 2
    assert not (tmp_path / "counts").exists()


def test_false_metadata_refusal_cannot_write_a_self_consistent_manifest(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    _install_acquisition_adapters(monkeypatch, false_metadata_refusal_chrom="chr1")

    with pytest.raises(ValueError, match="metadata refusal is not reproduced"):
        compose_acquisition(_acquisition_composition(tmp_path))
    assert not (tmp_path / "out/acquisition.json").exists()


def test_preparation_cli_reports_sqlite_failure_without_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        preparation_cli,
        "prepare",
        lambda _args: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")),
    )
    assert prepare_main(_preparation_argv(tmp_path)) == 2
    assert capsys.readouterr().err == "error:invalid_input\n"


def test_unreproducible_preparation_parse_failure_rolls_back_manifest(tmp_path, monkeypatch):
    _synthetic_inputs(tmp_path, source_size_bytes=4_096)
    _install_acquisition_adapters(monkeypatch)
    compose_acquisition(_acquisition_composition(tmp_path))
    _install_preparation_adapters(monkeypatch)
    monkeypatch.setattr(
        preparation_cli,
        "parse_header",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("record_invalid")),
    )

    preparation_inputs = _preparation_composition(tmp_path)
    with pytest.raises(ValueError, match="not reproduced"):
        compose_preparation(preparation_inputs)
    assert not (tmp_path / "counts/manifest.json").exists()

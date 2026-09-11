"""Strict reference-window source and artifact contracts (design §§4–8, 12; #254)."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from genomeos.validation.reference_window_manifest import (
    decode_manifest,
    encode_manifest,
    parse_contig_declarations,
    parse_source_listing,
)
from genomeos.validation.reference_window_types import Provenance, PublicObject

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "reference_windows"
SCRIPT = ROOT / "scripts" / "freeze_reference_windows.py"


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _command(out: Path) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--source-metadata",
        str(FIXTURES / "synthetic-sources.json"),
        "--contigs",
        str(FIXTURES / "synthetic-contigs.txt"),
        "--source-audit",
        str(FIXTURES / "synthetic-audit.md"),
        "--data-version",
        "synthetic-reference-v1",
        "--evidence-kind",
        "synthetic_fixture",
        "--out",
        str(out),
    ]


@pytest.fixture
def frozen_manifest(tmp_path):
    output = tmp_path / "frozen"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(_command(output), capture_output=True, text=True, env=environment, check=False)
    assert completed.returncode == 0, completed.stderr
    return output


@pytest.fixture
def valid_manifest_bytes(frozen_manifest):
    return (frozen_manifest / "manifest.json").read_bytes()


@pytest.fixture
def window_bytes(frozen_manifest):
    return (frozen_manifest / "windows.tsv").read_bytes()


@pytest.fixture
def valid_manifest_payload(valid_manifest_bytes):
    return json.loads(valid_manifest_bytes)


def test_source_listing_normalizes_24_pairs_to_natural_autosomes():
    raw = (FIXTURES / "synthetic-sources.json").read_bytes()
    sources = parse_source_listing(raw)
    shuffled = json.loads(raw)
    shuffled.reverse()

    assert parse_source_listing(json.dumps(shuffled).encode()) == sources
    assert tuple(source.chrom for source in sources) == tuple(f"chr{i}" for i in range(1, 23))
    assert all(source.tbi.uri == source.vcf.uri + ".tbi" for source in sources)
    assert all(type(source.vcf.size_bytes) is int for source in sources)


def test_normalized_public_object_rejects_path_traversal_and_credentials():
    common = {
        "generation": "1",
        "size_bytes": 1,
        "md5_b64": "AAAAAAAAAAAAAAAAAAAAAA==",
        "crc32c_b64": "AAAAAA==",
    }
    for uri in (
        "gs://gcp-public-data--gnomad/release/3.1.2/vcf/genomes/gnomad.genomes.v3.1.2.hgdp_tgp../secret",
        "gs://user@gcp-public-data--gnomad/release/3.1.2/vcf/genomes/gnomad.genomes.v3.1.2.hgdp_tgp.chr1.vcf.bgz",
    ):
        with pytest.raises(ValueError, match="uri|source family"):
            PublicObject(uri=uri, **common)


def _source_payload() -> list[dict[str, object]]:
    return json.loads((FIXTURES / "synthetic-sources.json").read_bytes())


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda rows: rows[0].update(unexpected="value"), "outer fields"),
        (lambda rows: rows[0].update(type="application/json"), "cloud_object"),
        (lambda rows: rows[0]["metadata"].update(unexpected="value"), "metadata fields"),
        (lambda rows: rows[0]["metadata"].update(size=1), "metadata size"),
        (lambda rows: rows[0]["metadata"].update(contentType=None), "contentType"),
        (lambda rows: rows[0]["metadata"].update(md5Hash="bad"), "md5"),
        (lambda rows: rows[0]["metadata"].update(crc32c="bad"), "crc32c"),
        (lambda rows: rows[0].update(url=rows[0]["url"].replace("#9000000000000", "#7")), "generation"),
        (lambda rows: rows[0]["metadata"].update(id="wrong"), "id"),
        (lambda rows: rows.append(copy.deepcopy(rows[0])), "duplicate"),
        (lambda rows: rows.__setitem__(slice(42, 44), []), "chr22"),
        (
            lambda rows: [
                row.update(
                    url=row["url"].replace("chrY", "chrM"),
                    metadata={
                        **row["metadata"],
                        "name": row["metadata"]["name"].replace("chrY", "chrM"),
                        "id": row["metadata"]["id"].replace("chrY", "chrM"),
                    },
                )
                for row in rows
                if "chrY" in row["url"]
            ],
            "unexpected chromosome",
        ),
        (
            lambda rows: rows[0]["metadata"].update(
                name=rows[0]["metadata"]["name"].replace("release/3.1.2", "release/4.0")
            ),
            "source family",
        ),
        (
            lambda rows: rows[0]["metadata"].update(
                name=rows[0]["metadata"]["name"].replace("chr1.vcf.bgz", "chr2.vcf.bgz")
            ),
            "URL",
        ),
    ],
)
def test_source_listing_rejects_independent_mutations(mutate, match):
    rows = _source_payload()
    mutate(rows)
    with pytest.raises(ValueError, match=match):
        parse_source_listing(json.dumps(rows).encode())


def test_source_listing_rejects_duplicate_json_keys_and_nonfinite_constants():
    raw = (FIXTURES / "synthetic-sources.json").read_bytes()
    duplicate = raw.replace(b"{", b'{"url":"duplicate",', 1)
    with pytest.raises(ValueError, match="duplicate"):
        parse_source_listing(duplicate)
    with pytest.raises(ValueError, match="nonfinite"):
        parse_source_listing(raw.replace(b'"size": "1000000"', b'"size": NaN', 1))


def test_contig_declarations_project_natural_autosomes():
    lengths = parse_contig_declarations((FIXTURES / "synthetic-contigs.txt").read_bytes())
    assert tuple(chrom for chrom, _ in lengths) == tuple(f"chr{i}" for i in range(1, 23))
    assert dict(lengths)["chr22"] == 30_720_000


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.replace(b"assembly=gnomAD_GRCh38", b"assembly=GRCh37", 1),
        lambda raw: raw + raw.splitlines(keepends=True)[0],
        lambda raw: raw.replace(b"ID=chr1,", b"ID=1,", 1),
        lambda raw: raw.replace(b"length=30090000", b"length=true", 1),
        lambda raw: raw.replace(b"##contig=", b"#contig=", 1),
    ],
)
def test_contig_declarations_reject_malformed_or_duplicate_lines(mutate):
    raw = (FIXTURES / "synthetic-contigs.txt").read_bytes()
    with pytest.raises(ValueError):
        parse_contig_declarations(mutate(raw))


def test_manifest_round_trip_is_canonical_and_strict(valid_manifest_bytes, window_bytes):
    manifest = decode_manifest(valid_manifest_bytes, windows_bytes=window_bytes)
    assert encode_manifest(manifest) == valid_manifest_bytes
    assert manifest.publication_eligible is False
    assert manifest.p1_eligible is False
    assert len(manifest.windows) == 66


def test_manifest_records_are_deeply_immutable(valid_manifest_bytes, window_bytes):
    manifest = decode_manifest(valid_manifest_bytes, windows_bytes=window_bytes)
    with pytest.raises(FrozenInstanceError):
        manifest.config.seed = 43
    assert type(manifest.provenance.input_sha256) is tuple
    assert type(manifest.windows[0].eligible_runs) is tuple


def test_manifest_constructor_rejects_cross_record_inconsistency(valid_manifest_bytes, window_bytes):
    manifest = decode_manifest(valid_manifest_bytes, windows_bytes=window_bytes)
    bad_window = replace(manifest.windows[0], stratum_end0=manifest.windows[0].stratum_end0 + 1)
    with pytest.raises(ValueError, match="stratum bounds"):
        replace(manifest, windows=(bad_window, *manifest.windows[1:]))
    with pytest.raises(ValueError, match="input_sha256"):
        replace(manifest, provenance=replace(manifest.provenance, input_sha256=(("other", "0" * 64),)))


def test_manifest_rejects_duplicate_keys(valid_manifest_bytes, window_bytes):
    raw = valid_manifest_bytes.replace(b"{", b'{"schema_version":"bad",', 1)
    with pytest.raises(ValueError, match="duplicate"):
        decode_manifest(raw, windows_bytes=window_bytes)


def test_manifest_rejects_noncanonical_json_bytes(valid_manifest_payload, window_bytes):
    raw = (json.dumps(valid_manifest_payload, sort_keys=True, indent=2) + "\n").encode()
    with pytest.raises(ValueError, match="canonical"):
        decode_manifest(raw, windows_bytes=window_bytes)


@pytest.mark.parametrize("value", [True, 1.5, "10000"])
def test_width_requires_integer(valid_manifest_payload, window_bytes, value):
    valid_manifest_payload["config"]["width"] = value
    with pytest.raises(ValueError, match="width"):
        decode_manifest(_canonical(valid_manifest_payload), windows_bytes=window_bytes)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda data: data.update(extra=True), "manifest fields"),
        (lambda data: data.pop("count_contract"), "manifest fields"),
        (lambda data: data["config"].update(seed=43), "configuration"),
        (lambda data: data["config"].update(schema_version="reference_window_config_v2"), "schema"),
        (lambda data: data["config"].update(numpy_version="0.0"), "NumPy"),
        (lambda data: data["config"].update(bit_generator="MT19937"), "bit_generator"),
        (lambda data: data["config"].update(draw_method="choice"), "draw_method"),
        (lambda data: data["config"].update(max_transfer_bytes=1), "transfer configuration"),
        (lambda data: data["config"].update(header_prefix_bytes=1), "transfer configuration"),
        (lambda data: data["config"].update(eof_bytes=1), "transfer configuration"),
        (lambda data: data["config"]["exclusion"].update(start0=19_999_999), "pilot exclusion"),
        (lambda data: data.update(windows_sha256="0" * 64), "windows.tsv"),
        (lambda data: data.update(publication_eligible=True), "publication_eligible"),
        (lambda data: data.update(p1_eligible=True), "p1_eligible"),
        (lambda data: data["sources"][0]["vcf"].update(size_bytes="100"), "size_bytes"),
        (lambda data: data["sources"][0]["vcf"].update(md5_b64="bad"), "md5"),
        (lambda data: data["windows"][0].update(window_id="chr1-s2"), "window_id"),
        (lambda data: data["provenance"]["input_sha256"].update(extra="bad"), "sha256"),
    ],
)
def test_manifest_rejects_semantic_mutations(valid_manifest_payload, window_bytes, mutation, match):
    mutation(valid_manifest_payload)
    with pytest.raises(ValueError, match=match):
        decode_manifest(_canonical(valid_manifest_payload), windows_bytes=window_bytes)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.replace(b"chr1-s1\t", b"chr1-s2\t", 1),
        lambda raw: (
            b"\n".join([raw.splitlines()[0], raw.splitlines()[2], raw.splitlines()[1], *raw.splitlines()[3:]])
            + b"\n"
        ),
        lambda raw: raw.replace(b"\t904294\n", b"\t904295\n", 1),
        lambda raw: raw + b"chr1-s1\tchr1\t1\t0\t1\t0\t1\n",
    ],
)
def test_manifest_rejects_changed_window_tsv(valid_manifest_bytes, window_bytes, mutate):
    with pytest.raises(ValueError, match="windows.tsv"):
        decode_manifest(valid_manifest_bytes, windows_bytes=mutate(window_bytes))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["config"].update(extra=True),
        lambda data: data["config"]["exclusion"].pop("end0"),
        lambda data: data["provenance"].update(extra=True),
        lambda data: data["sources"][0].pop("chrom"),
        lambda data: data["sources"][0]["vcf"].update(extra=True),
        lambda data: data["windows"][0].pop("rank"),
    ],
)
def test_manifest_rejects_unknown_or_missing_nested_fields(valid_manifest_payload, window_bytes, mutate):
    mutate(valid_manifest_payload)
    with pytest.raises(ValueError, match="fields"):
        decode_manifest(_canonical(valid_manifest_payload), windows_bytes=window_bytes)


@pytest.mark.parametrize("field", ["publication_eligible", "p1_eligible"])
@pytest.mark.parametrize("value", [True, 0, None])
def test_manifest_eligibility_flags_require_actual_false(valid_manifest_payload, window_bytes, field, value):
    valid_manifest_payload[field] = value
    with pytest.raises(ValueError, match=field):
        decode_manifest(_canonical(valid_manifest_payload), windows_bytes=window_bytes)


def test_hash_entries_reject_mutable_and_unsorted_values():
    common = dict(
        data_version="fixture-v1",
        evidence_kind="synthetic_fixture",
        source_revision="0" * 40,
        python_version="3.12.0",
        source_audit_locator="synthetic-audit.md",
    )
    with pytest.raises(ValueError, match="tuple"):
        Provenance(input_sha256={}, imported_source_sha256=(), **common)
    with pytest.raises(ValueError, match="sorted"):
        Provenance(
            input_sha256=(("z", "0" * 64), ("a", "1" * 64)),
            imported_source_sha256=(),
            **common,
        )

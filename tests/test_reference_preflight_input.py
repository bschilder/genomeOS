"""Reviewed preflight input controls (reference acquisition design §§1, 4.1, 6.1)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace

import pytest

from genomeos.validation.reference_acquisition_types import (
    ArtifactRef,
    MetadataReceipt,
    NativeRunReceipt,
    RangeReceipt,
    RetainedIndex,
)
from genomeos.validation.reference_byte_plan import ByteRange
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight
from genomeos.validation.reference_window_manifest import encode_manifest
from tests.reference_acquisition_fixture import synthetic_preflight_case


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _review_for(raw: bytes, review):
    return replace(review, preflight_sha256=hashlib.sha256(raw).hexdigest())


def _artifact(path: str, raw: bytes = b"") -> ArtifactRef:
    return ArtifactRef(path, len(raw), hashlib.sha256(raw).hexdigest())


def test_evidence_records_are_immutable_and_paths_and_counts_are_strict():
    artifact = _artifact("ranges/chr1.part", b"abc")
    with pytest.raises(FrozenInstanceError):
        artifact.path = "changed"  # type: ignore[misc]
    for path in ("/absolute", "../escape", "nested/../escape", "double//separator", r"wrong\slash"):
        with pytest.raises(ValueError):
            ArtifactRef(path, 3, artifact.sha256)
    with pytest.raises(ValueError, match="integer"):
        ArtifactRef("valid", True, artifact.sha256)


def test_range_and_metadata_success_require_complete_bounded_process_evidence():
    retained = _artifact("ranges/chr1.part", b"abc")
    stderr = _artifact("ranges/chr1.stderr")
    receipt = RangeReceipt(
        "chr1", "100", 10, 12, 3, 3, 1, "verified", None,
        retained.sha256, retained, stderr, 0, False, False,
    )
    assert receipt.received_bytes == 3
    with pytest.raises(ValueError, match="range"):
        replace(receipt, received_bytes=2, retained=_artifact("ranges/short.part", b"ab"))

    metadata = MetadataReceipt("verified", None, 1, 3, retained, stderr, 0, False, False)
    with pytest.raises(ValueError, match="verified metadata"):
        replace(metadata, exit_code=1)
    with pytest.raises(ValueError, match="invocation"):
        MetadataReceipt("not_attempted", "metadata_mismatch", 1, 0, None, None, None, False, False)


def test_native_receipts_refuse_absolute_or_failed_complete_commands():
    stdout = _artifact("native/stdout")
    stderr = _artifact("native/stderr")
    receipt = NativeRunReceipt(
        "query_keys", ("bcftools", "query", "source.bcf"), "complete", None, 0,
        stdout, stderr, 65_536, 1_048_576, False, False,
    )
    with pytest.raises(ValueError, match="absolute"):
        replace(receipt, argv_template=("/usr/bin/bcftools", "query"))
    with pytest.raises(ValueError, match="complete native"):
        replace(receipt, exit_code=1)


def test_valid_reviewed_preflight_recomputes_the_hand_enumerated_range_union():
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()

    decoded = decode_reviewed_preflight(
        raw, manifest=manifest, manifest_raw=manifest_raw, indexes=indexes, review=review
    )

    assert decoded.sources[0].merged_vcf_ranges == (
        ByteRange(0, 1_048_575),
        ByteRange(2_097_124, 2_097_151),
    )
    assert len(decoded.sources) == 22
    assert (
        sum(window.state == "no_index_chunks" for source in decoded.sources for window in source.windows)
        == 66
    )


def test_review_hash_mismatch_refuses_before_acquisition():
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()
    wrong = replace(review, preflight_sha256="0" * 64)
    with pytest.raises(ValueError, match="review"):
        decode_reviewed_preflight(
            raw, manifest=manifest, manifest_raw=manifest_raw, indexes=indexes, review=wrong
        )


def test_corrupt_retained_index_refuses():
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()
    broken = (replace(indexes[0], raw=indexes[0].raw[:-1]), *indexes[1:])
    with pytest.raises(ValueError, match="index"):
        decode_reviewed_preflight(
            raw, manifest=manifest, manifest_raw=manifest_raw, indexes=broken, review=review
        )


def test_same_size_index_corruption_refuses_on_content_identity():
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()
    changed = bytearray(indexes[0].raw)
    changed[len(changed) // 2] ^= 1
    broken = (replace(indexes[0], raw=bytes(changed)), *indexes[1:])
    with pytest.raises(ValueError, match="index MD5"):
        decode_reviewed_preflight(
            raw, manifest=manifest, manifest_raw=manifest_raw, indexes=broken, review=review
        )


def test_declared_crc_is_recomputed_from_retained_index_bytes():
    manifest, _, raw, indexes, review = synthetic_preflight_case()
    wrong_crc = base64.b64encode(b"\x00\x00\x00\x01").decode("ascii")
    first_source = replace(
        manifest.sources[0],
        tbi=replace(manifest.sources[0].tbi, crc32c_b64=wrong_crc),
    )
    changed_manifest = replace(manifest, sources=(first_source, *manifest.sources[1:]))
    changed_manifest_raw = encode_manifest(changed_manifest)
    manifest_sha = hashlib.sha256(changed_manifest_raw).hexdigest()
    payload = json.loads(raw)
    payload["manifest_sha256"] = manifest_sha
    payload["provenance"]["input_sha256"]["manifest"] = manifest_sha
    payload["sources"][0]["source"]["tbi"]["crc32c_b64"] = wrong_crc
    changed_raw = _canonical(payload)
    changed_review = replace(
        review,
        manifest_sha256=manifest_sha,
        preflight_sha256=hashlib.sha256(changed_raw).hexdigest(),
    )
    with pytest.raises(ValueError, match="index CRC32C"):
        decode_reviewed_preflight(
            changed_raw,
            manifest=changed_manifest,
            manifest_raw=changed_manifest_raw,
            indexes=indexes,
            review=changed_review,
        )


def _complete_false(raw: bytes) -> bytes:
    return raw.replace(b'"complete":true', b'"complete":false', 1)


def _duplicate_schema_version(raw: bytes) -> bytes:
    return raw.replace(b"{", b'{"schema_version":"reference_index_preflight_v1",', 1)


def _invalid_utf8(raw: bytes) -> bytes:
    return b"\xff" + raw


def _nan_count(raw: bytes) -> bytes:
    return re.sub(rb'("known_planned_bytes":)[0-9]+', rb"\1NaN", raw, count=1)


def _mutate_payload(raw: bytes, mutation: Callable[[dict], None]) -> bytes:
    payload = json.loads(raw)
    mutation(payload)
    return _canonical(payload)


def _changed_generation(raw: bytes) -> bytes:
    def mutate(payload):
        generation = payload["sources"][0]["source"]["vcf"]["generation"]
        payload["sources"][0]["source"]["vcf"]["generation"] = str(int(generation) + 1)

    return _mutate_payload(raw, mutate)


def _extra_range_byte(raw: bytes) -> bytes:
    return _mutate_payload(
        raw,
        lambda payload: payload["sources"][0]["merged_vcf_ranges"][0].__setitem__(
            "last", payload["sources"][0]["merged_vcf_ranges"][0]["last"] + 1
        ),
    )


def _omit_source(raw: bytes) -> bytes:
    return _mutate_payload(raw, lambda payload: payload["sources"].pop())


def _omit_window(raw: bytes) -> bytes:
    return _mutate_payload(raw, lambda payload: payload["sources"][0]["windows"].pop())


def _eligibility_true(raw: bytes) -> bytes:
    return _mutate_payload(raw, lambda payload: payload.__setitem__("publication_eligible", True))


def _received_bytes_bool(raw: bytes) -> bytes:
    return _mutate_payload(
        raw, lambda payload: payload["sources"][0]["receipt"].__setitem__("received_bytes", True)
    )


def _wrong_receipt_sha(raw: bytes) -> bytes:
    return _mutate_payload(
        raw, lambda payload: payload["sources"][0]["receipt"].__setitem__("sha256", "0" * 64)
    )


def _trailing_space(raw: bytes) -> bytes:
    return raw[:-1] + b" \n"


@pytest.mark.parametrize(
    "mutation",
    (
        _complete_false,
        _duplicate_schema_version,
        _invalid_utf8,
        _nan_count,
        _changed_generation,
        _extra_range_byte,
        _omit_source,
        _omit_window,
        _eligibility_true,
        _received_bytes_bool,
        _wrong_receipt_sha,
        _trailing_space,
    ),
)
def test_noncanonical_or_mismatched_preflight_refuses(mutation):
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()
    changed = mutation(raw)
    with pytest.raises(ValueError):
        decode_reviewed_preflight(
            changed,
            manifest=manifest,
            manifest_raw=manifest_raw,
            indexes=indexes,
            review=_review_for(changed, review),
        )


def test_identical_index_bytes_are_relocatable_but_chromosome_labels_cannot_rescue_wrong_identity():
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()
    relocated = tuple(RetainedIndex(index.chrom, bytes(bytearray(index.raw))) for index in indexes)
    assert decode_reviewed_preflight(
        raw, manifest=manifest, manifest_raw=manifest_raw, indexes=relocated, review=review
    ).complete

    mislabeled = (RetainedIndex("chr2", indexes[0].raw), *indexes[1:])
    with pytest.raises(ValueError, match="index"):
        decode_reviewed_preflight(
            raw, manifest=manifest, manifest_raw=manifest_raw, indexes=mislabeled, review=review
        )


def test_manifest_bytes_are_part_of_the_reviewed_identity():
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()
    with pytest.raises(ValueError, match="manifest"):
        decode_reviewed_preflight(
            raw,
            manifest=manifest,
            manifest_raw=manifest_raw + b" ",
            indexes=indexes,
            review=review,
        )


def test_review_binds_the_exact_preflight_implementation_source_map():
    manifest, manifest_raw, raw, indexes, review = synthetic_preflight_case()
    first_key, _ = review.implementation_sha256[0]
    wrong_map = ((first_key, "0" * 64), *review.implementation_sha256[1:])
    with pytest.raises(ValueError, match="source map"):
        decode_reviewed_preflight(
            raw,
            manifest=manifest,
            manifest_raw=manifest_raw,
            indexes=indexes,
            review=replace(review, implementation_sha256=wrong_map),
        )

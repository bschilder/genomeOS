"""Strict local reference-window codecs (design §§4–8, 12; preflight design §4)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import numpy as np

from genomeos.validation.reference_window_types import (
    AUTOSOMES,
    CONFIG_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    SOURCE_BUCKET,
    SOURCE_PREFIX,
    GenomicInterval,
    Provenance,
    PublicObject,
    ReferenceWindow,
    SourcePair,
    StartRun,
    WindowConfig,
    WindowManifest,
)
from genomeos.validation.reference_windows import select_reference_windows

_OUTER_KEYS = {"url", "type", "metadata"}
_USED_METADATA_KEYS = {"bucket", "name", "generation", "size", "md5Hash", "crc32c"}
_OPTIONAL_METADATA_KEYS = {
    "contentType",
    "etag",
    "id",
    "kind",
    "mediaLink",
    "metageneration",
    "selfLink",
    "storageClass",
    "timeCreated",
    "timeFinalized",
    "timeStorageClassUpdated",
    "updated",
}
_OBJECT_NAME = re.compile(
    re.escape(SOURCE_PREFIX) + r"(?P<chrom>chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M))\.vcf\.bgz(?P<tbi>\.tbi)?\Z"
)
_CONTIG = re.compile(
    rb"##contig=<ID=(chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M)),length=([1-9][0-9]*),assembly=gnomAD_GRCh38>\Z"
)
_TOP_KEYS = {
    "schema_version",
    "config",
    "contig_lengths",
    "sources",
    "windows",
    "provenance",
    "windows_sha256",
    "omitted_source_chromosomes",
    "contig_evidence",
    "source_evidence_status",
    "count_contract",
    "publication_eligible",
    "p1_eligible",
}
_CONFIG_KEYS = {
    "schema_version",
    "width",
    "strata",
    "seed",
    "numpy_version",
    "bit_generator",
    "draw_method",
    "exclusion",
    "max_transfer_bytes",
    "header_prefix_bytes",
    "eof_bytes",
}
_PROVENANCE_KEYS = {
    "data_version",
    "evidence_kind",
    "input_sha256",
    "source_revision",
    "imported_source_sha256",
    "python_version",
    "source_audit_locator",
}
_SOURCE_KEYS = {"chrom", "vcf", "tbi"}
_OBJECT_KEYS = {"uri", "generation", "size_bytes", "md5_b64", "crc32c_b64"}
_WINDOW_KEYS = {
    "window_id",
    "chrom",
    "stratum",
    "stratum_start0",
    "stratum_end0",
    "start0",
    "end0",
    "eligible_runs",
    "eligible_count",
    "rank",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON constant: {value}")


def _json(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as error:
        raise ValueError("JSON must be UTF-8") from error


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _object(value: object, fields: set[str], name: str) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == fields, f"invalid {name} fields")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{field} must be an integer >= {minimum}")
    return value


def _text(value: object, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()) and value == value.strip(), f"invalid {field}")
    return value


def parse_source_listing(raw: bytes) -> tuple[SourcePair, ...]:
    """Project a strict generation-pinned GCS audit into 22 normalized source pairs."""
    document = _json(raw)
    _require(type(document) is list, "source listing must be a JSON array")
    objects: dict[tuple[str, bool], PublicObject] = {}
    seen_chromosomes: set[str] = set()
    for item in document:
        outer = _object(item, _OUTER_KEYS, "source listing outer")
        url = _text(outer["url"], "outer URL")
        _require(outer["type"] == "cloud_object", "source listing type must be cloud_object")
        metadata = outer["metadata"]
        _require(type(metadata) is dict, "metadata must be an object")
        keys = set(metadata)
        _require(
            _USED_METADATA_KEYS <= keys <= _USED_METADATA_KEYS | _OPTIONAL_METADATA_KEYS,
            "invalid metadata fields",
        )
        for key in keys:
            _text(metadata[key], f"metadata {key}")
        _require(metadata["bucket"] == SOURCE_BUCKET, "metadata bucket is outside source family")
        name = metadata["name"]
        match = _OBJECT_NAME.fullmatch(name)
        _require(match is not None, "metadata name is outside source family")
        chrom = match.group("chrom")
        _require(chrom != "chrM", "unexpected chromosome object: chrM")
        is_tbi = match.group("tbi") is not None
        generation = metadata["generation"]
        _require(re.fullmatch(r"[1-9][0-9]*", generation) is not None, "invalid metadata generation")
        expected_uri = f"gs://{SOURCE_BUCKET}/{name}"
        _require(url == f"{expected_uri}#{generation}", "outer URL does not match object generation")
        if "id" in metadata:
            _require(
                metadata["id"] == f"{SOURCE_BUCKET}/{name}/{generation}",
                "metadata id does not match object generation",
            )
        size = metadata["size"]
        _require(re.fullmatch(r"[1-9][0-9]*", size) is not None, "metadata size must be positive decimal")
        key = (chrom, is_tbi)
        _require(key not in objects, "duplicate source object")
        objects[key] = PublicObject(
            uri=expected_uri,
            generation=generation,
            size_bytes=int(size),
            md5_b64=metadata["md5Hash"],
            crc32c_b64=metadata["crc32c"],
        )
        seen_chromosomes.add(chrom)

    expected_chromosomes = set(AUTOSOMES) | {"chrX", "chrY"}
    unexpected = seen_chromosomes - expected_chromosomes
    _require(not unexpected, f"unexpected chromosome objects: {sorted(unexpected)}")
    missing = expected_chromosomes - seen_chromosomes
    _require(not missing, f"missing source chromosomes: {sorted(missing)}")
    _require(len(objects) == 48, "source listing must contain 24 complete VCF/TBI pairs")
    for chrom in expected_chromosomes:
        _require(
            (chrom, False) in objects and (chrom, True) in objects, f"incomplete source pair for {chrom}"
        )
    return tuple(SourcePair(chrom, objects[(chrom, False)], objects[(chrom, True)]) for chrom in AUTOSOMES)


def parse_contig_declarations(raw: bytes) -> tuple[tuple[str, int], ...]:
    """Parse exact saved GRCh38 declarations and project the 22 autosomal lengths."""
    _require(bool(raw) and raw.endswith(b"\n") and b"\r" not in raw, "contig declarations require LF lines")
    values: dict[str, int] = {}
    for line in raw.splitlines():
        match = _CONTIG.fullmatch(line)
        _require(match is not None, "malformed contig declaration or wrong assembly")
        chrom = match.group(1).decode("ascii")
        _require(chrom not in values, f"duplicate contig declaration: {chrom}")
        length = int(match.group(2))
        _require(length < 2**29, "contig length must be below 2^29")
        values[chrom] = length
    missing = set(AUTOSOMES) - set(values)
    _require(not missing, f"missing autosomal contigs: {sorted(missing)}")
    return tuple((chrom, values[chrom]) for chrom in AUTOSOMES)


def windows_tsv(windows: tuple[ReferenceWindow, ...]) -> bytes:
    """Encode the review-facing 66-row coordinate table with fixed columns and LF."""
    _require(type(windows) is tuple and len(windows) == 66, "windows must contain 66 records")
    header = "window_id\tchrom\tstratum\tstratum_start0\tstratum_end0\tstart0\tend0\n"
    rows = [header]
    for window in windows:
        _require(type(window) is ReferenceWindow, "invalid reference window")
        rows.append(
            f"{window.window_id}\t{window.chrom}\t{window.stratum}\t{window.stratum_start0}\t"
            f"{window.stratum_end0}\t{window.start0}\t{window.end0}\n"
        )
    return "".join(rows).encode("ascii")


def _config_payload(config: WindowConfig) -> dict[str, object]:
    return {
        "schema_version": config.schema_version,
        "width": config.width,
        "strata": config.strata,
        "seed": config.seed,
        "numpy_version": config.numpy_version,
        "bit_generator": config.bit_generator,
        "draw_method": config.draw_method,
        "exclusion": {
            "chrom": config.exclusion.chrom,
            "start0": config.exclusion.start0,
            "end0": config.exclusion.end0,
        },
        "max_transfer_bytes": config.max_transfer_bytes,
        "header_prefix_bytes": config.header_prefix_bytes,
        "eof_bytes": config.eof_bytes,
    }


def encode_window_config(config: WindowConfig) -> bytes:
    """Encode window-selection configuration as canonical provenance bytes."""
    _require(type(config) is WindowConfig, "config must be WindowConfig")
    return _canonical(_config_payload(config))


def _object_payload(value: PublicObject) -> dict[str, object]:
    return {
        "uri": value.uri,
        "generation": value.generation,
        "size_bytes": value.size_bytes,
        "md5_b64": value.md5_b64,
        "crc32c_b64": value.crc32c_b64,
    }


def _manifest_payload(manifest: WindowManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "config": _config_payload(manifest.config),
        "contig_lengths": [[chrom, length] for chrom, length in manifest.contig_lengths],
        "sources": [
            {"chrom": source.chrom, "vcf": _object_payload(source.vcf), "tbi": _object_payload(source.tbi)}
            for source in manifest.sources
        ],
        "windows": [
            {
                "window_id": window.window_id,
                "chrom": window.chrom,
                "stratum": window.stratum,
                "stratum_start0": window.stratum_start0,
                "stratum_end0": window.stratum_end0,
                "start0": window.start0,
                "end0": window.end0,
                "eligible_runs": [[run.first, run.last] for run in window.eligible_runs],
                "eligible_count": window.eligible_count,
                "rank": window.rank,
            }
            for window in manifest.windows
        ],
        "provenance": {
            "data_version": manifest.provenance.data_version,
            "evidence_kind": manifest.provenance.evidence_kind,
            "input_sha256": dict(manifest.provenance.input_sha256),
            "source_revision": manifest.provenance.source_revision,
            "imported_source_sha256": dict(manifest.provenance.imported_source_sha256),
            "python_version": manifest.provenance.python_version,
            "source_audit_locator": manifest.provenance.source_audit_locator,
        },
        "windows_sha256": manifest.windows_sha256,
        "omitted_source_chromosomes": list(manifest.omitted_source_chromosomes),
        "contig_evidence": manifest.contig_evidence,
        "source_evidence_status": manifest.source_evidence_status,
        "count_contract": manifest.count_contract,
        "publication_eligible": manifest.publication_eligible,
        "p1_eligible": manifest.p1_eligible,
    }


def encode_manifest(manifest: WindowManifest) -> bytes:
    """Encode a validated manifest as timestamp-free canonical JSON bytes."""
    _require(type(manifest) is WindowManifest, "manifest must be WindowManifest")
    return _canonical(_manifest_payload(manifest))


def _decode_public_object(value: object) -> PublicObject:
    fields = _object(value, _OBJECT_KEYS, "public object")
    return PublicObject(
        uri=_text(fields["uri"], "uri"),
        generation=_text(fields["generation"], "generation"),
        size_bytes=_integer(fields["size_bytes"], "size_bytes", minimum=1),
        md5_b64=_text(fields["md5_b64"], "md5_b64"),
        crc32c_b64=_text(fields["crc32c_b64"], "crc32c_b64"),
    )


def _decode_config(value: object) -> WindowConfig:
    fields = _object(value, _CONFIG_KEYS, "config")
    exclusion = _object(fields["exclusion"], {"chrom", "start0", "end0"}, "exclusion")
    return WindowConfig(
        schema_version=_text(fields["schema_version"], "config schema_version"),
        width=_integer(fields["width"], "width", minimum=1),
        strata=_integer(fields["strata"], "strata", minimum=1),
        seed=_integer(fields["seed"], "seed"),
        numpy_version=_text(fields["numpy_version"], "numpy_version"),
        bit_generator=_text(fields["bit_generator"], "bit_generator"),
        draw_method=_text(fields["draw_method"], "draw_method"),
        exclusion=GenomicInterval(
            _text(exclusion["chrom"], "exclusion chrom"),
            _integer(exclusion["start0"], "exclusion start0"),
            _integer(exclusion["end0"], "exclusion end0", minimum=1),
        ),
        max_transfer_bytes=_integer(fields["max_transfer_bytes"], "max_transfer_bytes", minimum=1),
        header_prefix_bytes=_integer(fields["header_prefix_bytes"], "header_prefix_bytes", minimum=1),
        eof_bytes=_integer(fields["eof_bytes"], "eof_bytes", minimum=1),
    )


def _decode_hash_entries(value: object, field: str) -> tuple[tuple[str, str], ...]:
    _require(type(value) is dict, f"{field} must be a JSON object")
    return tuple(
        sorted(
            (_text(key, f"{field} key"), _text(digest, f"{field} digest")) for key, digest in value.items()
        )
    )


def _decode_window(value: object) -> ReferenceWindow:
    fields = _object(value, _WINDOW_KEYS, "window")
    runs = fields["eligible_runs"]
    _require(type(runs) is list, "eligible_runs must be an array")
    decoded_runs = []
    for run in runs:
        _require(type(run) is list and len(run) == 2, "eligible run must be a two-item array")
        decoded_runs.append(StartRun(_integer(run[0], "run first"), _integer(run[1], "run last")))
    return ReferenceWindow(
        window_id=_text(fields["window_id"], "window_id"),
        chrom=_text(fields["chrom"], "window chrom"),
        stratum=_integer(fields["stratum"], "stratum", minimum=1),
        stratum_start0=_integer(fields["stratum_start0"], "stratum_start0"),
        stratum_end0=_integer(fields["stratum_end0"], "stratum_end0", minimum=1),
        start0=_integer(fields["start0"], "start0"),
        end0=_integer(fields["end0"], "end0", minimum=1),
        eligible_runs=tuple(decoded_runs),
        eligible_count=_integer(fields["eligible_count"], "eligible_count", minimum=1),
        rank=_integer(fields["rank"], "rank"),
    )


def decode_manifest(raw: bytes, *, windows_bytes: bytes) -> WindowManifest:
    """Decode and independently revalidate a canonical source-bound window manifest."""
    fields = _object(_json(raw), _TOP_KEYS, "manifest")
    config = _decode_config(fields["config"])
    _require(config.numpy_version == np.__version__, "NumPy version mismatch")
    lengths = fields["contig_lengths"]
    _require(type(lengths) is list, "contig_lengths must be an array")
    contig_lengths = []
    for entry in lengths:
        _require(type(entry) is list and len(entry) == 2, "contig length must be a two-item array")
        contig_lengths.append(
            (_text(entry[0], "contig chrom"), _integer(entry[1], "contig length", minimum=1))
        )
    source_values = fields["sources"]
    _require(type(source_values) is list, "sources must be an array")
    sources = []
    for value in source_values:
        source = _object(value, _SOURCE_KEYS, "source")
        sources.append(
            SourcePair(
                _text(source["chrom"], "source chrom"),
                _decode_public_object(source["vcf"]),
                _decode_public_object(source["tbi"]),
            )
        )
    window_values = fields["windows"]
    _require(type(window_values) is list, "windows must be an array")
    windows = tuple(_decode_window(value) for value in window_values)
    provenance_fields = _object(fields["provenance"], _PROVENANCE_KEYS, "provenance")
    provenance = Provenance(
        data_version=_text(provenance_fields["data_version"], "data_version"),
        evidence_kind=_text(provenance_fields["evidence_kind"], "evidence_kind"),
        input_sha256=_decode_hash_entries(provenance_fields["input_sha256"], "input_sha256"),
        source_revision=_text(provenance_fields["source_revision"], "source_revision"),
        imported_source_sha256=_decode_hash_entries(
            provenance_fields["imported_source_sha256"], "imported_source_sha256"
        ),
        python_version=_text(provenance_fields["python_version"], "python_version"),
        source_audit_locator=_text(provenance_fields["source_audit_locator"], "source_audit_locator"),
    )
    _require(
        set(dict(provenance.input_sha256))
        == {"contigs", "selection_config", "source_audit", "source_metadata"},
        "invalid input hash fields",
    )
    _require(
        set(dict(provenance.imported_source_sha256))
        == {
            "genomeos/validation/reference_window_manifest.py",
            "genomeos/validation/reference_window_types.py",
            "genomeos/validation/reference_windows.py",
            "scripts/freeze_reference_windows.py",
        },
        "invalid imported source hash fields",
    )
    manifest = WindowManifest(
        schema_version=_text(fields["schema_version"], "manifest schema_version"),
        config=config,
        contig_lengths=tuple(contig_lengths),
        sources=tuple(sources),
        windows=windows,
        provenance=provenance,
        windows_sha256=_text(fields["windows_sha256"], "windows_sha256"),
        omitted_source_chromosomes=tuple(fields["omitted_source_chromosomes"])
        if type(fields["omitted_source_chromosomes"]) is list
        else (),
        contig_evidence=_text(fields["contig_evidence"], "contig_evidence"),
        source_evidence_status=_text(fields["source_evidence_status"], "source_evidence_status"),
        count_contract=_text(fields["count_contract"], "count_contract"),
        publication_eligible=fields["publication_eligible"],
        p1_eligible=fields["p1_eligible"],
    )
    _require(manifest.schema_version == MANIFEST_SCHEMA_VERSION, "unsupported manifest schema_version")
    _require(manifest.config.schema_version == CONFIG_SCHEMA_VERSION, "unsupported config schema_version")
    config_hash = dict(manifest.provenance.input_sha256)["selection_config"]
    _require(
        config_hash == hashlib.sha256(encode_window_config(manifest.config)).hexdigest(),
        "selection_config hash does not match configuration",
    )
    _require(
        manifest.windows == select_reference_windows(manifest.contig_lengths, manifest.config),
        "window geometry does not match deterministic selection",
    )
    expected_windows = windows_tsv(manifest.windows)
    _require(windows_bytes == expected_windows, "windows.tsv bytes do not match manifest")
    _require(
        hashlib.sha256(windows_bytes).hexdigest() == manifest.windows_sha256, "windows.tsv hash mismatch"
    )
    _require(raw == encode_manifest(manifest), "manifest JSON bytes are not canonical")
    return manifest

"""Durable B0H publication packets (design §§5,7–8,12; runner §4; #337)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path

from genomeos.validation.heterogeneity_codec import B0HCodecLimits, EncodedB0HEvidence
from genomeos.validation.heterogeneity_runner_reader import StoreIntegrityError
from genomeos.validation.heterogeneity_runner_records import (
    EvidenceReceipt,
    PublicationPacket,
    StageCompletion,
    StageExecutionFailure,
    StageStart,
)
from genomeos.validation.heterogeneity_runner_wire import (
    evidence_receipt,
    read_runner_record,
    record_digest,
    runner_record_bytes,
)

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "ascii"
    )


def _fingerprint(raw: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def _write(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _members(packet: PublicationPacket) -> tuple[dict[str, bytes], str | None, list[str]]:
    members = {
        "start.json": runner_record_bytes(packet.start),
        "completion.json": runner_record_bytes(packet.completion),
    }
    metadata_file = None
    payload_files = []
    if packet.receipt is not None:
        members["receipt.json"] = runner_record_bytes(packet.receipt)
        members["metadata.bin"] = packet.encoded.metadata
        metadata_file = "metadata.bin"
        for ordinal, (digest, raw) in enumerate(packet.encoded.payloads):
            name = f"payload-{ordinal:06d}-{digest}.bin"
            members[name] = raw
            payload_files.append(name)
    else:
        members["failure.json"] = runner_record_bytes(packet.failure)
    return members, metadata_file, payload_files


def write_publication_packet(root: Path, packet: PublicationPacket) -> Path:
    """Publish one content-verified packet directory atomically and idempotently."""
    if type(packet) is not PublicationPacket:
        raise StoreIntegrityError("spool requires exact immutable publication packet")
    if root.is_symlink():
        raise StoreIntegrityError("publication spool symlink refused")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    start_digest = record_digest(packet.start)
    final = root / start_digest
    if final.exists():
        if read_publication_packet(final, limits=packet_limits(packet)) != packet:
            raise StoreIntegrityError("immutable publication spool conflict")
        return final

    members, metadata_file, payload_files = _members(packet)
    document = {
        "format": "b0h_publication_packet",
        "version": "1",
        "start_sha256": start_digest,
        "metadata_file": metadata_file,
        "payload_files": payload_files,
        "files": {name: _fingerprint(raw) for name, raw in sorted(members.items())},
    }
    temporary = root / f".{start_digest}.{uuid.uuid4().hex}.tmp"
    temporary.mkdir(mode=0o700)
    try:
        for name, raw in members.items():
            _write(temporary / name, raw)
        _write(temporary / "packet.json", _canonical(document))
        _fsync_directory(temporary)
        try:
            temporary.rename(final)
        except FileExistsError as error:
            if read_publication_packet(final, limits=packet_limits(packet)) != packet:
                raise StoreIntegrityError("immutable publication spool conflict") from error
        _fsync_directory(root)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return final


def packet_limits(packet: PublicationPacket) -> B0HCodecLimits:
    """Return the minimum limits that still admit this exact packet."""
    if packet.encoded is None:
        return B0HCodecLimits(1, 0)
    return B0HCodecLimits(
        max(1, len(packet.encoded.metadata)),
        sum(len(raw) for _, raw in packet.encoded.payloads),
    )


def _read_member(path: Path, identity: object) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise StoreIntegrityError("publication spool member missing or not regular")
    raw = path.read_bytes()
    if type(identity) is not dict or identity != _fingerprint(raw):
        raise StoreIntegrityError("publication spool fingerprint mismatch")
    return raw


def _record(raw: bytes, cls: type):
    value = read_runner_record(raw)
    if type(value) is not cls:
        raise StoreIntegrityError("publication spool contains wrong operational root")
    return value


def read_publication_packet(path: Path, *, limits: B0HCodecLimits) -> PublicationPacket:
    if not path.is_dir() or path.is_symlink() or not _DIGEST.fullmatch(path.name):
        raise StoreIntegrityError("publication packet path is not a digest directory")
    packet_path = path / "packet.json"
    if not packet_path.is_file() or packet_path.is_symlink():
        raise StoreIntegrityError("publication packet manifest is missing")
    raw_document = packet_path.read_bytes()
    try:
        document = json.loads(raw_document)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StoreIntegrityError("publication packet manifest is invalid") from error
    if raw_document != _canonical(document) or type(document) is not dict:
        raise StoreIntegrityError("publication packet manifest is not canonical")
    if (
        set(document) != {
            "files",
            "format",
            "metadata_file",
            "payload_files",
            "start_sha256",
            "version",
        }
        or document["format"] != "b0h_publication_packet"
        or document["version"] != "1"
        or document["start_sha256"] != path.name
        or type(document["files"]) is not dict
        or type(document["payload_files"]) is not list
    ):
        raise StoreIntegrityError("publication packet manifest fields differ from contract")
    expected = set(document["files"]) | {"packet.json"}
    if {member.name for member in path.iterdir()} != expected:
        raise StoreIntegrityError("publication packet member set differs from manifest")
    raw = {
        name: _read_member(path / name, identity)
        for name, identity in document["files"].items()
    }
    start = _record(raw["start.json"], StageStart)
    completion = _record(raw["completion.json"], StageCompletion)
    if record_digest(start) != path.name:
        raise StoreIntegrityError("publication packet START digest differs from directory")
    metadata_file = document["metadata_file"]
    payload_files = document["payload_files"]
    if metadata_file is None:
        if payload_files or set(raw) != {"start.json", "completion.json", "failure.json"}:
            raise StoreIntegrityError("failure packet member set differs from contract")
        packet = PublicationPacket(
            start,
            completion,
            None,
            None,
            _record(raw["failure.json"], StageExecutionFailure),
        )
    else:
        if (
            metadata_file != "metadata.bin"
            or any(type(name) is not str for name in payload_files)
            or len(set(payload_files)) != len(payload_files)
            or set(raw) != {
                "start.json",
                "completion.json",
                "receipt.json",
                "metadata.bin",
                *payload_files,
            }
        ):
            raise StoreIntegrityError("scientific packet member set differs from contract")
        payloads = []
        for ordinal, name in enumerate(payload_files):
            match = re.fullmatch(r"payload-([0-9]{6})-([0-9a-f]{64})\.bin", name)
            if match is None or int(match.group(1)) != ordinal:
                raise StoreIntegrityError("publication payload order/name is invalid")
            payloads.append((match.group(2), raw[name]))
        encoded = EncodedB0HEvidence(raw[metadata_file], tuple(payloads))
        receipt = _record(raw["receipt.json"], EvidenceReceipt)
        if evidence_receipt(start, encoded, limits=limits) != receipt:
            raise StoreIntegrityError("publication packet scientific evidence differs from receipt")
        packet = PublicationPacket(start, completion, receipt, encoded, None)
    return packet


def publication_packets(
    root: Path,
    *,
    limits: B0HCodecLimits,
) -> tuple[PublicationPacket, ...]:
    if not root.exists():
        return ()
    if not root.is_dir() or root.is_symlink():
        raise StoreIntegrityError("publication spool is not a plain directory")
    paths = tuple(sorted(root.iterdir(), key=lambda item: item.name))
    if any(not _DIGEST.fullmatch(path.name) for path in paths):
        raise StoreIntegrityError("publication spool contains an incomplete or unknown member")
    return tuple(read_publication_packet(path, limits=limits) for path in paths)

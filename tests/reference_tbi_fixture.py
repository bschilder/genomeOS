"""Synthetic native TBI fixture helpers for reference-window tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

LONG_INFO = "ACGT" * 45_000
HEADER = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr1,length=1000000>\n"
    '##INFO=<ID=X,Number=1,Type=String,Description="Synthetic">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)
POSITIONS = (1, 16_384, 32_769, 100_000)
RECORDS = tuple(f"chr1\t{pos}\t.\tA\tC\t.\tPASS\tX={LONG_INFO}\n" for pos in POSITIONS)
QUERIES = (
    ("chr1:1-1", "1\n"),
    ("chr1:16384-16384", "16384\n"),
    ("chr1:32769-32769", "32769\n"),
    ("chr1:100001-100001", ""),
)


def synthetic_bgzf(payload: bytes) -> bytes:
    """Encode bounded test payload bytes as deterministic BGZF members."""

    def block(part: bytes) -> bytes:
        compressor = zlib.compressobj(wbits=-15)
        body = compressor.compress(part) + compressor.flush()
        size = 18 + len(body) + 8
        assert size <= 65_536
        header = bytes.fromhex("1f8b08040000000000ff060042430200") + struct.pack("<H", size - 1)
        return header + body + struct.pack("<II", zlib.crc32(part), len(part))

    return b"".join(block(payload[i : i + 32_768]) for i in range(0, len(payload), 32_768)) + block(b"")


def expanded_tbi_payload(raw: bytes) -> bytes:
    """Expand the fixed-layout synthetic/native BGZF fixture independently."""
    expanded = bytearray()
    offset = 0
    while offset < len(raw):
        block_size = int.from_bytes(raw[offset + 16 : offset + 18], "little") + 1
        expanded.extend(zlib.decompress(raw[offset : offset + block_size], wbits=31))
        offset += block_size
    assert offset == len(raw)
    return bytes(expanded)


def bgzf_record_blocks(raw: bytes, target: bytes) -> tuple[tuple[int, int], ...]:
    """Return physical BGZF members touched by a complete decompressed record."""
    blocks: list[tuple[int, int, int, int]] = []
    expanded = bytearray()
    offset = 0
    while offset < len(raw):
        block_size = int.from_bytes(raw[offset + 16 : offset + 18], "little") + 1
        payload = zlib.decompress(raw[offset : offset + block_size], wbits=31)
        blocks.append((offset, offset + block_size - 1, len(expanded), len(expanded) + len(payload)))
        expanded.extend(payload)
        offset += block_size
    begin = expanded.index(target)
    end = begin + len(target)
    return tuple(
        (lo, hi) for lo, hi, expanded_lo, expanded_hi in blocks if expanded_lo < end and expanded_hi > begin
    )


def native_tools() -> tuple[str, str, str] | None:
    found = tuple(shutil.which(tool) for tool in ("bgzip", "tabix", "bcftools"))
    return found if all(found) else None


def create_native_fixture(directory: Path) -> tuple[Path, Path, dict[str, object]]:
    """Generate the fixture and saved native-query evidence with installed tools."""
    tools = native_tools()
    if tools is None:
        raise RuntimeError("bgzip, tabix and bcftools are required")
    bgzip, tabix, bcftools = tools
    directory.mkdir(parents=True, exist_ok=True)
    vcf = directory / "synthetic.vcf.gz"
    completed = subprocess.run(
        [bgzip, "-c"], input=(HEADER + "".join(RECORDS)).encode(), check=True, capture_output=True
    )
    vcf.write_bytes(completed.stdout)
    subprocess.run([tabix, "-p", "vcf", str(vcf)], check=True, capture_output=True)
    tbi = Path(f"{vcf}.tbi")
    results = []
    for region, expected in QUERIES:
        argv = [
            "bcftools",
            "query",
            "--regions-overlap",
            "0",
            "-r",
            region,
            "-f",
            "%POS\\n",
            "synthetic.vcf.gz",
        ]
        query = subprocess.run([bcftools, *argv[1:-1], str(vcf)], check=True, capture_output=True, text=True)
        assert query.stdout == expected
        results.append({"argv": argv, "stdout": query.stdout})

    def version(executable: str) -> str:
        return subprocess.run(
            [executable, "--version"], check=True, capture_output=True, text=True
        ).stdout.splitlines()[0]

    evidence: dict[str, object] = {
        "schema_version": "synthetic_reference_tbi_evidence_v1",
        "fixture_sha256": {
            "synthetic.vcf.gz": hashlib.sha256(vcf.read_bytes()).hexdigest(),
            "synthetic.vcf.gz.tbi": hashlib.sha256(tbi.read_bytes()).hexdigest(),
        },
        "native_versions": {
            "bcftools": version(bcftools),
            "bgzip": version(bgzip),
            "tabix": version(tabix),
        },
        "queries": results,
    }
    return vcf, tbi, evidence


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()

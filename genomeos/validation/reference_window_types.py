"""Immutable reference-window contracts (design §§4–8, 12; preflight design §§3–4)."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Literal

EvidenceKind = Literal["synthetic_fixture", "public_reference_development"]
HashEntries = tuple[tuple[str, str], ...]

AUTOSOMES = tuple(f"chr{number}" for number in range(1, 23))
CONFIG_SCHEMA_VERSION = "reference_window_config_v1"
MANIFEST_SCHEMA_VERSION = "reference_windows_v1"
WIDTH = 10_000
STRATA = 3
SEED = 42
BIT_GENERATOR = "PCG64"
DRAW_METHOD = "integers(0,total,dtype=int64);natural_chr1_chr22_stratum_order"
MAX_TRANSFER_BYTES = 26_843_545_600
HEADER_PREFIX_BYTES = 1_048_576
EOF_BYTES = 28
EXCLUSION_CHROM = "chr22"
EXCLUSION_START0 = 20_000_000
EXCLUSION_END0 = 20_010_000
CONTIG_EVIDENCE = "saved_pilot_header_declarations"
SOURCE_EVIDENCE_STATUS = "supplied_audit_not_reperformed"
COUNT_CONTRACT = "pilot_stage_qc_semantics_unchanged_v1"
SOURCE_BUCKET = "gcp-public-data--gnomad"
SOURCE_PREFIX = "release/3.1.2/vcf/genomes/gnomad.genomes.v3.1.2.hgdp_tgp."

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_NORMALIZED_URI = re.compile(
    re.escape(f"gs://{SOURCE_BUCKET}/{SOURCE_PREFIX}")
    + r"chr(?:[1-9]|1[0-9]|2[0-2]|X|Y)\.vcf\.bgz(?:\.tbi)?\Z"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{field} must be an integer >= {minimum}")
    return value


def _text(value: object, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()) and value == value.strip(), f"invalid {field}")
    return value


def _chrom(value: object, field: str = "chrom") -> str:
    text = _text(value, field)
    _require(text in AUTOSOMES, f"{field} must be chr1 through chr22")
    return text


def _checksum(value: object, field: str, decoded_bytes: int) -> str:
    text = _text(value, field)
    try:
        decoded = base64.b64decode(text, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError(f"invalid {field}") from error
    _require(len(decoded) == decoded_bytes, f"invalid {field} length")
    _require(base64.b64encode(decoded).decode("ascii") == text, f"noncanonical {field}")
    return text


def _hash_entries(value: object, field: str) -> HashEntries:
    _require(type(value) is tuple, f"{field} must be a tuple")
    entries: list[tuple[str, str]] = []
    for entry in value:
        _require(type(entry) is tuple and len(entry) == 2, f"{field} entries must be pairs")
        key = _text(entry[0], f"{field} key")
        digest = _text(entry[1], f"{field} digest")
        _require(bool(_SHA256.fullmatch(digest)), f"invalid {field} sha256")
        entries.append((key, digest))
    _require(tuple(entries) == tuple(sorted(entries)), f"{field} must be key-sorted")
    _require(len({key for key, _ in entries}) == len(entries), f"{field} keys must be unique")
    return tuple(entries)


@dataclass(frozen=True)
class GenomicInterval:
    chrom: str
    start0: int
    end0: int

    def __post_init__(self) -> None:
        _chrom(self.chrom)
        _integer(self.start0, "start0")
        _integer(self.end0, "end0", minimum=1)
        _require(self.start0 < self.end0, "interval start0 must precede end0")


@dataclass(frozen=True)
class StartRun:
    first: int
    last: int

    def __post_init__(self) -> None:
        _integer(self.first, "first")
        _integer(self.last, "last")
        _require(self.first <= self.last, "start run first must not exceed last")


@dataclass(frozen=True)
class ReferenceWindow:
    window_id: str
    chrom: str
    stratum: int
    stratum_start0: int
    stratum_end0: int
    start0: int
    end0: int
    eligible_runs: tuple[StartRun, ...]
    eligible_count: int
    rank: int

    def __post_init__(self) -> None:
        chrom = _chrom(self.chrom)
        _require(self.window_id == f"{chrom}-s{self.stratum}", "window_id does not match window")
        _integer(self.stratum, "stratum", minimum=1)
        _require(self.stratum <= STRATA, "invalid stratum")
        _integer(self.stratum_start0, "stratum_start0")
        _integer(self.stratum_end0, "stratum_end0", minimum=1)
        _require(self.stratum_start0 < self.stratum_end0, "invalid stratum bounds")
        _integer(self.start0, "start0")
        _integer(self.end0, "end0", minimum=1)
        _require(
            self.stratum_start0 <= self.start0 < self.end0 <= self.stratum_end0,
            "window is outside its stratum",
        )
        _require(self.end0 - self.start0 == WIDTH, "window does not have the fixed width")
        _require(
            type(self.eligible_runs) is tuple and bool(self.eligible_runs), "eligible_runs must be a tuple"
        )
        _require(all(type(run) is StartRun for run in self.eligible_runs), "invalid eligible run")
        _require(
            all(
                self.stratum_start0 <= run.first <= run.last <= self.stratum_end0 - WIDTH
                for run in self.eligible_runs
            ),
            "eligible run is outside the stratum candidate frame",
        )
        _require(
            all(
                left.last < right.first
                for left, right in zip(self.eligible_runs, self.eligible_runs[1:], strict=False)
            ),
            "eligible runs must be sorted and disjoint",
        )
        count = sum(run.last - run.first + 1 for run in self.eligible_runs)
        _integer(self.eligible_count, "eligible_count", minimum=1)
        _require(self.eligible_count == count, "eligible_count does not match eligible_runs")
        _integer(self.rank, "rank")
        _require(self.rank < count, "rank is outside eligible starts")
        offset = self.rank
        chosen = None
        for run in self.eligible_runs:
            size = run.last - run.first + 1
            if offset < size:
                chosen = run.first + offset
                break
            offset -= size
        _require(self.start0 == chosen, "start0 does not match rank")


@dataclass(frozen=True)
class PublicObject:
    uri: str
    generation: str
    size_bytes: int
    md5_b64: str
    crc32c_b64: str

    def __post_init__(self) -> None:
        uri = _text(self.uri, "uri")
        _require("?" not in uri and "#" not in uri, "uri must not contain query or generation")
        _require(_NORMALIZED_URI.fullmatch(uri) is not None, "uri is outside public source family")
        _require(re.fullmatch(r"[1-9][0-9]*", self.generation) is not None, "invalid generation")
        _integer(self.size_bytes, "size_bytes", minimum=1)
        _checksum(self.md5_b64, "md5_b64", 16)
        _checksum(self.crc32c_b64, "crc32c_b64", 4)


@dataclass(frozen=True)
class SourcePair:
    chrom: str
    vcf: PublicObject
    tbi: PublicObject

    def __post_init__(self) -> None:
        chrom = _chrom(self.chrom)
        _require(type(self.vcf) is PublicObject and type(self.tbi) is PublicObject, "invalid source objects")
        expected = f"gs://{SOURCE_BUCKET}/{SOURCE_PREFIX}{chrom}.vcf.bgz"
        _require(self.vcf.uri == expected, "VCF URI does not match chromosome")
        _require(self.tbi.uri == f"{expected}.tbi", "TBI URI does not match VCF")


@dataclass(frozen=True)
class WindowConfig:
    schema_version: str
    width: int
    strata: int
    seed: int
    numpy_version: str
    bit_generator: str
    draw_method: str
    exclusion: GenomicInterval
    max_transfer_bytes: int
    header_prefix_bytes: int
    eof_bytes: int

    def __post_init__(self) -> None:
        _require(self.schema_version == CONFIG_SCHEMA_VERSION, "unsupported config schema_version")
        _integer(self.width, "width", minimum=1)
        _integer(self.strata, "strata", minimum=1)
        _integer(self.seed, "seed")
        _text(self.numpy_version, "numpy_version")
        _require(self.bit_generator == BIT_GENERATOR, "unsupported bit_generator")
        _require(self.draw_method == DRAW_METHOD, "unsupported draw_method")
        _require(type(self.exclusion) is GenomicInterval, "invalid exclusion")
        _integer(self.max_transfer_bytes, "max_transfer_bytes", minimum=1)
        _integer(self.header_prefix_bytes, "header_prefix_bytes", minimum=1)
        _integer(self.eof_bytes, "eof_bytes", minimum=1)
        _require(
            (self.width, self.strata, self.seed) == (WIDTH, STRATA, SEED),
            "window selection configuration is fixed",
        )
        _require(
            self.exclusion == GenomicInterval(EXCLUSION_CHROM, EXCLUSION_START0, EXCLUSION_END0),
            "pilot exclusion is fixed",
        )
        _require(
            (self.max_transfer_bytes, self.header_prefix_bytes, self.eof_bytes)
            == (MAX_TRANSFER_BYTES, HEADER_PREFIX_BYTES, EOF_BYTES),
            "transfer configuration is fixed",
        )


@dataclass(frozen=True)
class Provenance:
    data_version: str
    evidence_kind: EvidenceKind
    input_sha256: HashEntries
    source_revision: str
    imported_source_sha256: HashEntries
    python_version: str
    source_audit_locator: str

    def __post_init__(self) -> None:
        _text(self.data_version, "data_version")
        _require(
            self.evidence_kind in ("synthetic_fixture", "public_reference_development"),
            "invalid evidence_kind",
        )
        _hash_entries(self.input_sha256, "input_sha256")
        _require(bool(re.fullmatch(r"[0-9a-f]{40}", self.source_revision)), "invalid source_revision")
        _hash_entries(self.imported_source_sha256, "imported_source_sha256")
        _text(self.python_version, "python_version")
        locator = _text(self.source_audit_locator, "source_audit_locator")
        _require(
            not locator.startswith("/") and ".." not in locator.split("/"), "audit locator must be relative"
        )


@dataclass(frozen=True)
class WindowManifest:
    schema_version: str
    config: WindowConfig
    contig_lengths: tuple[tuple[str, int], ...]
    sources: tuple[SourcePair, ...]
    windows: tuple[ReferenceWindow, ...]
    provenance: Provenance
    windows_sha256: str
    omitted_source_chromosomes: tuple[str, ...]
    contig_evidence: str
    source_evidence_status: str
    count_contract: str
    publication_eligible: Literal[False]
    p1_eligible: Literal[False]

    def __post_init__(self) -> None:
        _require(self.schema_version == MANIFEST_SCHEMA_VERSION, "unsupported manifest schema_version")
        _require(type(self.config) is WindowConfig, "invalid config")
        _require(type(self.contig_lengths) is tuple, "contig_lengths must be a tuple")
        _require(
            type(self.sources) is tuple and all(type(item) is SourcePair for item in self.sources),
            "invalid sources",
        )
        _require(
            type(self.windows) is tuple and all(type(item) is ReferenceWindow for item in self.windows),
            "invalid windows",
        )
        _require(type(self.provenance) is Provenance, "invalid provenance")
        _require(bool(_SHA256.fullmatch(self.windows_sha256)), "invalid windows_sha256")
        expected_lengths = []
        for entry in self.contig_lengths:
            _require(type(entry) is tuple and len(entry) == 2, "contig length entries must be pairs")
            length = _integer(entry[1], "contig length", minimum=1)
            _require(length < 2**29, "contig length must be below 2^29")
            expected_lengths.append((_chrom(entry[0]), length))
        _require(
            tuple(chrom for chrom, _ in expected_lengths) == AUTOSOMES,
            "contig lengths must be natural autosomes",
        )
        _require(
            tuple(source.chrom for source in self.sources) == AUTOSOMES, "sources must be natural autosomes"
        )
        _require(len(self.windows) == 66, "manifest must contain 66 windows")
        expected_ids = tuple(f"chr{chrom}-s{stratum}" for chrom in range(1, 23) for stratum in range(1, 4))
        _require(
            tuple(window.window_id for window in self.windows) == expected_ids,
            "windows must be in natural order",
        )
        lengths_by_chrom = dict(expected_lengths)
        for window in self.windows:
            length = lengths_by_chrom[window.chrom]
            expected_start = length * (window.stratum - 1) // STRATA
            expected_end = length * window.stratum // STRATA
            _require(
                (window.stratum_start0, window.stratum_end0) == (expected_start, expected_end),
                "window stratum bounds do not match contig length",
            )
            _require(
                window.chrom != self.config.exclusion.chrom
                or window.end0 <= self.config.exclusion.start0
                or window.start0 >= self.config.exclusion.end0,
                "window overlaps the pilot exclusion",
            )
        _require(
            {key for key, _ in self.provenance.input_sha256}
            == {"contigs", "selection_config", "source_audit", "source_metadata"},
            "invalid input_sha256 keys",
        )
        _require(
            {key for key, _ in self.provenance.imported_source_sha256}
            == {
                "genomeos/validation/reference_window_manifest.py",
                "genomeos/validation/reference_window_types.py",
                "genomeos/validation/reference_windows.py",
                "scripts/freeze_reference_windows.py",
            },
            "invalid imported_source_sha256 keys",
        )
        _require(
            self.omitted_source_chromosomes == ("chrX", "chrY"), "source omissions must be chrX and chrY"
        )
        _require(self.contig_evidence == CONTIG_EVIDENCE, "invalid contig_evidence")
        _require(self.source_evidence_status == SOURCE_EVIDENCE_STATUS, "invalid source_evidence_status")
        _require(self.count_contract == COUNT_CONTRACT, "invalid count_contract")
        _require(self.publication_eligible is False, "publication_eligible must be false")
        _require(self.p1_eligible is False, "p1_eligible must be false")

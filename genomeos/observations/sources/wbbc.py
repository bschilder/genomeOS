"""WBBC regional WGS frequency adapter (Atlas design §§4, 6, 7.1; P1).

The public GRCh38 VCF reports ``AF`` and ``AN`` for North, Central, South and Lingnan, but no
regional ``AC``.  A full-chromosome audit in issue #325 established the source's rounding rule:
reported global ``AC`` equals nearest-integer ``AF * AN`` on every chr22 record, and every regional
product is within 0.000005 of one integer.  This adapter rechecks those controls on every retained
variant and labels the assay as reconstructed rather than presenting inferred counts as reported.

The VCF omits INFO declarations.  Consequently this parser accepts the reviewed ordered INFO
contract, including its two observed tails (numeric or missing ``VQSLOD``), and fails on other
drift.  It scans in pandas chunks, filters to an explicit curated variant set, and expands all four
regions with array reshaping; it never builds a genome-wide fourfold table in memory.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import numpy as np
import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA, VARIANT_ID_PATTERN
from genomeos.observations.source_ids import stable_source_record_id
from genomeos.registry.sources.wbbc import REGION_ORDER

SOURCE = "wbbc_wgs_frequencies"
ALIAS_SOURCE = "wbbc"
COHORT_ID = "wbbc:wgs-frequency-release-v1"
ASSAY = "genome_frequency_reconstructed"
GLOBAL_AN = 8960
GLOBAL_NS = 4480
MAX_REGIONAL_COUNT_RESIDUAL = 0.000005
REGIONAL_AN = {"North": 448, "Central": 100, "South": 8070, "Lingnan": 126}

_VCF_COLUMNS = ("CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO")
_INTEGER = r"(?:0|[1-9][0-9]*)"
_FLOAT = r"(?:[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"
_SIGNED_FLOAT = r"(?:[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"
_INFO_PATTERN = re.compile(
    rf"^AC=(?P<AC>{_INTEGER});AF=(?P<AF>{_FLOAT});AN=(?P<AN>{_INTEGER});"
    rf"NS=(?P<NS>{_INTEGER});"
    rf"North_AF=(?P<North_AF>{_FLOAT});North_AN=(?P<North_AN>{_INTEGER});"
    rf"Central_AF=(?P<Central_AF>{_FLOAT});Central_AN=(?P<Central_AN>{_INTEGER});"
    rf"South_AF=(?P<South_AF>{_FLOAT});South_AN=(?P<South_AN>{_INTEGER});"
    rf"Lingnan_AF=(?P<Lingnan_AF>{_FLOAT});Lingnan_AN=(?P<Lingnan_AN>{_INTEGER});"
    rf"RR=(?P<RR>{_INTEGER})\|RA=(?P<RA>{_INTEGER})\|AA=(?P<AA>{_INTEGER});"
    rf"DP=(?P<DP>{_INTEGER});(?:VQSLOD=(?P<VQSLOD>{_SIGNED_FLOAT}))?$"
)


class UnmappedRegionError(ValueError):
    """One of WBBC's four source regions has no reviewed P0 registry entry."""


class RequestedVariantNotFoundError(ValueError):
    """A requested variant does not occur in the supplied WBBC VCF."""


@dataclass(frozen=True)
class IngestReport:
    scanned_variants: int
    matched_variants: int
    retained_observations: int
    requested_variants: int
    maximum_regional_count_residual: float


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open(encoding="utf-8", newline="")


def _validate_header(path: Path) -> None:
    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("#CHROM"):
                columns = tuple(line.rstrip("\r\n").lstrip("#").split("\t"))
                if columns != _VCF_COLUMNS:
                    raise ValueError(
                        f"{path}: expected VCF columns {list(_VCF_COLUMNS)}, found {list(columns)}"
                    )
                return
            if not line.startswith("#"):
                break
    raise ValueError(f"{path}: missing exact VCF column header")


def _chunks(path: Path, chunk_size: int) -> Iterator[pd.DataFrame]:
    yield from pd.read_csv(
        path,
        sep="\t",
        comment="#",
        names=_VCF_COLUMNS,
        dtype=str,
        keep_default_na=False,
        compression="infer",
        chunksize=chunk_size,
    )


def _region_lookup(
    populations: pd.DataFrame, aliases: pd.DataFrame
) -> tuple[np.ndarray, pd.DataFrame]:
    source_aliases = aliases.loc[aliases["source"] == ALIAS_SOURCE]
    if source_aliases["label"].duplicated().any():
        raise UnmappedRegionError("duplicate WBBC region alias")
    unexpected = sorted(set(source_aliases["label"]) - set(REGION_ORDER))
    if unexpected:
        raise UnmappedRegionError(f"unexpected WBBC region aliases: {unexpected}")
    mapping = source_aliases.set_index("label")["population_id"]
    missing = sorted(set(REGION_ORDER) - set(mapping.index))
    if missing:
        raise UnmappedRegionError(f"WBBC regions absent from the registry: {missing}")
    population_ids = mapping.loc[list(REGION_ORDER)].to_numpy(dtype=str)
    if len(set(population_ids)) != len(population_ids):
        raise UnmappedRegionError("WBBC regions must map to distinct populations")
    placed = populations.set_index("population_id")
    missing_ids = sorted(set(population_ids) - set(placed.index))
    if missing_ids:
        raise UnmappedRegionError(f"WBBC aliases reference absent populations: {missing_ids}")
    return population_ids, placed.loc[population_ids]


def _variant_ids(frame: pd.DataFrame, path: Path) -> pd.Series:
    positions = pd.to_numeric(frame["POS"], errors="coerce")
    invalid = (
        positions.isna()
        | (positions <= 0)
        | ~frame["CHROM"].str.fullmatch(r"chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M)")
        | ~frame["REF"].str.fullmatch(r"[ACGT]+")
        | ~frame["ALT"].str.fullmatch(r"[ACGT]+")
    )
    if invalid.any():
        raise ValueError(f"{path}: invalid or non-biallelic GRCh38 variant key")
    return (
        frame["CHROM"]
        + "-"
        + positions.astype("int64").astype(str)
        + "-"
        + frame["REF"]
        + "-"
        + frame["ALT"]
    )


def _parse_info(frame: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    parsed = frame["INFO"].str.extract(_INFO_PATTERN, expand=True)
    if parsed.drop(columns="VQSLOD").isna().any(axis=None):
        raise ValueError(f"{path}: WBBC INFO schema differs from the reviewed closed contract")
    numeric = parsed.apply(pd.to_numeric, errors="raise")
    frequencies = numeric[["AF", *(f"{region}_AF" for region in REGION_ORDER)]].to_numpy(float)
    if not np.isfinite(frequencies).all() or ((frequencies < 0.0) | (frequencies > 1.0)).any():
        raise ValueError(f"{path}: nonfinite or out-of-range WBBC allele frequency")
    if not numeric["AN"].eq(GLOBAL_AN).all() or not numeric["NS"].eq(GLOBAL_NS).all():
        raise ValueError(f"{path}: WBBC global AN/NS differs from the reviewed WGS release")
    for region, expected in REGIONAL_AN.items():
        if not numeric[f"{region}_AN"].eq(expected).all():
            raise ValueError(f"{path}: {region}_AN differs from the reviewed WGS release")

    global_product = numeric["AF"].to_numpy(float) * numeric["AN"].to_numpy(float)
    if not np.array_equal(np.rint(global_product).astype(np.int64), numeric["AC"].to_numpy(int)):
        raise ValueError(f"{path}: global AC/AF/AN rounding control failed")
    genotype_n = numeric[["RR", "RA", "AA"]].sum(axis=1)
    genotype_ac = numeric["RA"] + 2 * numeric["AA"]
    if not genotype_n.eq(numeric["NS"]).all() or not genotype_ac.eq(numeric["AC"]).all():
        raise ValueError(f"{path}: global RR/RA/AA genotype count control failed")

    regional_af = numeric[[f"{region}_AF" for region in REGION_ORDER]].to_numpy(float)
    regional_an = numeric[[f"{region}_AN" for region in REGION_ORDER]].to_numpy(np.int64)
    product = regional_af * regional_an
    regional_ac = np.rint(product).astype(np.int64)
    residual = np.abs(product - regional_ac)
    if (residual >= MAX_REGIONAL_COUNT_RESIDUAL).any():
        maximum = float(residual.max())
        raise ValueError(
            f"{path}: regional AF × AN reconstruction residual {maximum:.9g} is outside the "
            f"reviewed < {MAX_REGIONAL_COUNT_RESIDUAL} contract"
        )
    return parsed, regional_ac, residual


def _observations_for_chunk(
    frame: pd.DataFrame,
    variant_ids: pd.Series,
    population_ids: np.ndarray,
    geography: pd.DataFrame,
    ingest_version: str,
    path: Path,
) -> tuple[pd.DataFrame, float]:
    if not frame["FILTER"].eq("PASS").all():
        raise ValueError(f"{path}: requested WBBC record is not PASS")
    parsed, regional_ac, residual = _parse_info(frame, path)
    row_count = len(frame)
    region_count = len(REGION_ORDER)
    regional_an = np.broadcast_to(
        np.asarray([REGIONAL_AN[region] for region in REGION_ORDER], dtype=np.int64),
        (row_count, region_count),
    )
    repeated_variants = np.repeat(variant_ids.to_numpy(dtype=str), region_count)
    repeated_regions = np.tile(np.asarray(REGION_ORDER, dtype=str), row_count)
    repeated_population_ids = np.tile(population_ids, row_count)
    repeated_af = parsed[[f"{region}_AF" for region in REGION_ORDER]].to_numpy().reshape(-1)
    repeated_an = regional_an.reshape(-1)
    source_record_ids = [
        stable_source_record_id(
            "wbbc-wgs-frequencies", "GRCh38", variant, region, af, int(an)
        )
        for variant, region, af, an in zip(
            repeated_variants,
            repeated_regions,
            repeated_af,
            repeated_an,
            strict=True,
        )
    ]
    rsids = pd.Series(np.repeat(frame["ID"].to_numpy(dtype=str), region_count), dtype="string")
    rsids = rsids.mask(rsids == ".", pd.NA)
    observations = pd.DataFrame(
        {
            "variant_id": repeated_variants,
            "rsid": rsids,
            "population_id": repeated_population_ids,
            "lat": np.tile(geography["lat"].to_numpy(float), row_count),
            "lon": np.tile(geography["lon"].to_numpy(float), row_count),
            "radius_km": np.tile(
                geography["uncertainty_radius_km"].to_numpy(float), row_count
            ),
            "ac": regional_ac.reshape(-1),
            "an": repeated_an,
            "source_record_id": source_record_ids,
            "source": SOURCE,
            "assay": ASSAY,
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "convenience",
            "disease_ascertainment_excluded": pd.array(
                [False] * (row_count * region_count), dtype="boolean"
            ),
            "cohort_id": COHORT_ID,
            "ingest_version": ingest_version,
        }
    )
    return observations, float(residual.max(initial=0.0))


def load_many(
    paths: Collection[Path],
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    ingest_version: str,
    *,
    variant_ids: Collection[str],
    chunk_size: int = 250_000,
) -> tuple[pd.DataFrame, IngestReport]:
    """Load requested variants across chromosome-partitioned WBBC VCFs."""
    source_paths = tuple(Path(path) for path in paths)
    if not source_paths:
        raise ValueError("WBBC ingestion requires at least one VCF")
    requested = frozenset(str(value) for value in variant_ids)
    if not requested:
        raise ValueError("WBBC ingestion requires a non-empty explicit variant set")
    invalid = sorted(value for value in requested if re.fullmatch(VARIANT_ID_PATTERN, value) is None)
    if invalid:
        raise ValueError(f"invalid requested variant IDs: {invalid}")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    population_ids, geography = _region_lookup(populations, aliases)

    scanned = 0
    found: set[str] = set()
    frames: list[pd.DataFrame] = []
    maximum_residual = 0.0
    for path in source_paths:
        _validate_header(path)
        for chunk in _chunks(path, chunk_size):
            scanned += len(chunk)
            ids = _variant_ids(chunk, path)
            keep = ids.isin(requested)
            if not keep.any():
                continue
            matched_ids = ids.loc[keep]
            duplicated = found.intersection(matched_ids)
            if duplicated or matched_ids.duplicated().any():
                detail = sorted(duplicated | set(matched_ids[matched_ids.duplicated()]))
                raise ValueError(f"{path}: duplicate requested variant records: {detail}")
            found.update(matched_ids)
            observations, residual = _observations_for_chunk(
                chunk.loc[keep].reset_index(drop=True),
                matched_ids.reset_index(drop=True),
                population_ids,
                geography,
                ingest_version,
                path,
            )
            frames.append(observations)
            maximum_residual = max(maximum_residual, residual)

    missing = sorted(requested - found)
    if missing:
        raise RequestedVariantNotFoundError(
            f"WBBC VCF inputs: requested variants not found: {missing}"
        )
    observations = OBSERVATIONS_SCHEMA.validate(pd.concat(frames, ignore_index=True))
    report = IngestReport(
        scanned_variants=scanned,
        matched_variants=len(found),
        retained_observations=len(observations),
        requested_variants=len(requested),
        maximum_regional_count_residual=maximum_residual,
    )
    return observations, report


def load(
    path: Path,
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    ingest_version: str,
    *,
    variant_ids: Collection[str],
    chunk_size: int = 250_000,
) -> tuple[pd.DataFrame, IngestReport]:
    """Load requested variants from one WBBC VCF; see :func:`load_many` for a release."""
    return load_many(
        (path,),
        populations,
        aliases,
        ingest_version,
        variant_ids=variant_ids,
        chunk_size=chunk_size,
    )

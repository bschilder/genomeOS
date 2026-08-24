from __future__ import annotations

import csv
import gzip
import math
from pathlib import Path
from typing import IO, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Association,
    DataSource,
    Phenotype,
    PhenotypePopulation,
    SourceAsset,
    SourceRelease,
    Variant,
)

POPULATIONS = ("AFR", "AMR", "CSA", "EAS", "EUR", "MID")
PHENOTYPE_KEY = ("trait_type", "phenocode", "pheno_sex", "coding", "modifier")


class IngestionError(ValueError):
    pass


def _text(value: str | None) -> str:
    return (value or "").strip()


def _optional_int(value: str | None) -> int | None:
    value = _text(value)
    return int(float(value)) if value and value.upper() != "NA" else None


def _optional_float(value: str | None) -> float | None:
    value = _text(value)
    return float(value) if value and value.upper() != "NA" else None


def _optional_bool(value: str | None) -> bool | None:
    value = _text(value).lower()
    if not value or value == "na":
        return None
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise IngestionError(f"invalid boolean value: {value}")


def ensure_panukb_release(session: Session, version: str) -> SourceRelease:
    source = session.scalar(select(DataSource).where(DataSource.slug == "pan-ukb"))
    if source is None:
        source = DataSource(
            slug="pan-ukb",
            name="Pan-UK Biobank",
            homepage="https://pan.ukbb.broadinstitute.org/",
            license_id="CC-BY-4.0",
        )
        session.add(source)
        session.flush()
    release = session.scalar(
        select(SourceRelease).where(
            SourceRelease.source_id == source.id, SourceRelease.version == version
        )
    )
    if release is None:
        release = SourceRelease(source_id=source.id, version=version)
        session.add(release)
        session.flush()
    return release


def register_asset(
    session: Session,
    release: SourceRelease,
    asset_type: str,
    uri: str,
    *,
    index_uri: str | None = None,
    columns: list[str] | None = None,
) -> SourceAsset:
    asset = session.scalar(
        select(SourceAsset).where(
            SourceAsset.release_id == release.id,
            SourceAsset.asset_type == asset_type,
            SourceAsset.uri == uri,
        )
    )
    if asset is None:
        asset = SourceAsset(
            release_id=release.id,
            asset_type=asset_type,
            uri=uri,
            index_uri=index_uri,
            schema_json={"columns": columns} if columns else None,
        )
        session.add(asset)
        session.flush()
    return asset


def ingest_phenotype_manifest(
    session: Session, stream: IO[str], *, version: str, source_uri: str
) -> int:
    reader = csv.DictReader(stream, delimiter="\t")
    if not reader.fieldnames:
        raise IngestionError("manifest has no header")
    missing = set(PHENOTYPE_KEY + ("description",)) - set(reader.fieldnames)
    if missing:
        raise IngestionError(f"manifest missing required columns: {sorted(missing)}")
    release = ensure_panukb_release(session, version)
    asset = register_asset(
        session, release, "phenotype_manifest", source_uri, columns=reader.fieldnames
    )
    count = 0
    for row_number, row in enumerate(reader, start=2):
        key = {name: _text(row.get(name)) for name in PHENOTYPE_KEY}
        phenotype = session.scalar(
            select(Phenotype).where(
                Phenotype.release_id == release.id,
                *(getattr(Phenotype, name) == value for name, value in key.items()),
            )
        )
        if phenotype is None:
            phenotype = Phenotype(
                release_id=release.id,
                **key,
                description=_text(row.get("description")),
                description_more=_text(row.get("description_more")) or None,
                category=_text(row.get("category")) or None,
                in_max_independent_set=_optional_bool(row.get("in_max_independent_set")),
                summary_stats_uri=_text(row.get("aws_link")) or None,
                summary_stats_index_uri=_text(row.get("aws_link_tabix")) or None,
                source_asset_id=asset.id,
                source_row=row_number,
                source_payload=row,
            )
            session.add(phenotype)
            session.flush()
        else:
            phenotype.description = _text(row.get("description"))
            phenotype.source_payload = row
            phenotype.summary_stats_uri = _text(row.get("aws_link")) or None
            phenotype.summary_stats_index_uri = _text(row.get("aws_link_tabix")) or None
        listed = {_text(code) for code in _text(row.get("pops")).split(",") if _text(code)}
        for code in POPULATIONS:
            if code not in listed and not any(row.get(f"{prefix}_{code}") for prefix in ("n_cases", "n_controls", "phenotype_qc")):
                continue
            population = next((item for item in phenotype.populations if item.code == code), None)
            if population is None:
                population = PhenotypePopulation(phenotype_id=phenotype.id, code=code)
                session.add(population)
            population.n_cases = _optional_int(row.get(f"n_cases_{code}"))
            population.n_controls = _optional_int(row.get(f"n_controls_{code}"))
            population.qc_status = _text(row.get(f"phenotype_qc_{code}")) or None
            population.lambda_gc = _optional_float(row.get(f"lambda_gc_{code}"))
        count += 1
    session.commit()
    return count


def _open_text(path: Path) -> IO[str]:
    if path.suffix in {".gz", ".bgz"}:
        return gzip.open(path, "rt", newline="")
    return path.open("r", newline="")


def _pvalue_column(fieldnames: Iterable[str], population: str, override: str | None):
    candidates = [
        (f"neglog10_pval_{population}", "neg_log10"),
        (f"ln_pval_{population}", "ln"),
        (f"pval_{population}", override),
    ]
    for column, encoding in candidates:
        if column in fieldnames:
            if encoding not in {"neg_log10", "ln", "raw"}:
                raise IngestionError(
                    f"ambiguous p-value column {column}; pass p_value_encoding"
                )
            return column, encoding
    return None


def _neg_log10(encoded: float, encoding: str) -> float:
    if encoding == "neg_log10":
        return encoded
    if encoding == "ln":
        return -encoded / math.log(10)
    if encoded <= 0 or encoded > 1:
        raise IngestionError(f"raw p-value outside (0, 1]: {encoded}")
    return -math.log10(encoded)


def ingest_associations(
    session: Session,
    path: Path,
    *,
    phenotype_id: int,
    source_uri: str,
    threshold: float = 7.30103,
    p_value_encoding: str | None = None,
) -> int:
    phenotype = session.get(Phenotype, phenotype_id)
    if phenotype is None:
        raise IngestionError(f"unknown phenotype id {phenotype_id}")
    with _open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields = reader.fieldnames or []
        required = {"chr", "pos", "ref", "alt"}
        if missing := required - set(fields):
            raise IngestionError(f"association file missing columns: {sorted(missing)}")
        specs = {
            code: spec
            for code in (*POPULATIONS, "meta", "meta_hq")
            if (spec := _pvalue_column(fields, code, p_value_encoding)) is not None
        }
        if not specs:
            raise IngestionError("no supported p-value columns found")
        asset = register_asset(
            session,
            session.get(SourceRelease, phenotype.release_id),
            "phenotype_sumstats",
            source_uri,
            index_uri=f"{source_uri}.tbi",
            columns=fields,
        )
        inserted = 0
        for row_number, row in enumerate(reader, start=2):
            chromosome, position = _text(row["chr"]), int(row["pos"])
            reference, alternate = _text(row["ref"]), _text(row["alt"])
            variant = session.scalar(
                select(Variant).where(
                    Variant.assembly == "GRCh37",
                    Variant.chromosome == chromosome,
                    Variant.position == position,
                    Variant.reference == reference,
                    Variant.alternate == alternate,
                )
            )
            for population, (p_column, encoding) in specs.items():
                encoded = _optional_float(row.get(p_column))
                if encoded is None:
                    continue
                canonical_p = _neg_log10(encoded, encoding)
                if canonical_p < threshold:
                    continue
                if variant is None:
                    variant = Variant(
                        assembly="GRCh37",
                        chromosome=chromosome,
                        position=position,
                        reference=reference,
                        alternate=alternate,
                    )
                    session.add(variant)
                    session.flush()
                kind = "meta_hq" if population == "meta_hq" else "meta" if population == "meta" else "population"
                population_code = population.upper()
                assoc = session.scalar(
                    select(Association).where(
                        Association.phenotype_id == phenotype.id,
                        Association.variant_id == variant.id,
                        Association.population_code == population_code,
                        Association.analysis_kind == kind,
                    )
                )
                values = {
                    "beta": _optional_float(row.get(f"beta_{population}")),
                    "standard_error": _optional_float(row.get(f"se_{population}")),
                    "allele_frequency": _optional_float(row.get(f"af_{population}")),
                    "case_allele_frequency": _optional_float(row.get(f"af_cases_{population}")),
                    "control_allele_frequency": _optional_float(row.get(f"af_controls_{population}")),
                    "neg_log10_p": canonical_p,
                    "encoded_p_value": encoded,
                    "p_value_encoding": encoding,
                    "low_confidence": _optional_bool(row.get(f"low_confidence_{population}")),
                    "source_asset_id": asset.id,
                    "source_row": row_number,
                }
                if assoc is None:
                    assoc = Association(
                        phenotype_id=phenotype.id,
                        variant_id=variant.id,
                        population_code=population_code,
                        analysis_kind=kind,
                        **values,
                    )
                    session.add(assoc)
                else:
                    for name, value in values.items():
                        setattr(assoc, name, value)
                inserted += 1
        session.commit()
        return inserted

"""Reviewed publication evidence to P1 observations (literature design §§4, 5.4, 8).

This adapter does not parse papers or fill gaps. It validates the evidence ledgers, recomputes
promotion gates, resolves an exact ``literature`` alias through P0, and copies that registry row's
geography unchanged. Scientifically incomplete records are reported; malformed evidence is an
error.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

import pandas as pd

from genomeos.observations.evidence import (
    FIELD_EVIDENCE_COLUMNS,
    LITERATURE_EVIDENCE_COLUMNS,
    PROMOTION_REQUIRED_FIELDS,
    validate_literature_tables,
)
from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA

SOURCE = "literature"


class UnmappedPopulationError(ValueError):
    """A source label has no exact literature alias and therefore no defensible geography."""


@dataclass(frozen=True)
class IngestReport:
    """Publication rows kept and refused under one stable primary reason."""

    total: int
    retained: int
    refusals: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot = dict(self.refusals)
        if self.total != self.retained + sum(snapshot.values()):
            raise ValueError("ingest report counts must reconcile total, retained, and refusals")
        object.__setattr__(self, "refusals", MappingProxyType(snapshot))

    def __str__(self) -> str:
        lines = [f"{self.retained}/{self.total} literature records promoted"]
        for reason, count in sorted(self.refusals.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"  refused {count:>5}  {reason}")
        return "\n".join(lines)


def _read_tsv(path: Path, expected_columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    if tuple(frame.columns) != expected_columns:
        raise ValueError(
            f"{path}: expected exact TSV header {expected_columns}, got {tuple(frame.columns)}"
        )
    for column in frame.columns:
        frame[column] = frame[column].map(lambda value: value.strip())
    frame = frame.replace("", pd.NA)
    if "disease_ascertainment_excluded" in frame:
        values = set(frame["disease_ascertainment_excluded"].dropna())
        if not values.issubset({"true", "false"}):
            raise ValueError(
                "disease_ascertainment_excluded accepts only lowercase true, false, or blank"
            )
        frame["disease_ascertainment_excluded"] = frame[
            "disease_ascertainment_excluded"
        ].map({"true": True, "false": False})
    return frame


def _reason(main: pd.Series, field_rows: pd.DataFrame) -> str | None:
    states = field_rows.set_index("field_name")["evidence_status"]
    if main["normalization_status"] != "verified":
        return "variant_ambiguous"
    if any(
        pd.isna(main[name]) or states[name] not in {"reported", "derived"}
        for name in PROMOTION_REQUIRED_FIELDS
    ):
        return "required_field_unresolved"
    if (
        main["ac_lower"] != main["ac_upper"]
        or main["count_basis"] == "frequency_reconstructed"
    ):
        return "count_not_exact"
    if main["verification_status"] == "pending":
        return "source_not_verified"
    if main["reuse_status"] == "not_checked":
        return "reuse_not_checked"
    if main["reuse_status"] == "restricted":
        return "reuse_restricted"
    return None


def _is_regional_label(label: str) -> bool:
    lowered = label.casefold()
    return "," in label or " and " in lowered or "/" in label


def load(
    evidence_path: Path,
    field_evidence_path: Path,
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    ingest_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame, IngestReport]:
    """Validate reviewed evidence and deterministically promote its eligible exact rows."""
    evidence, field_evidence = validate_literature_tables(
        _read_tsv(evidence_path, LITERATURE_EVIDENCE_COLUMNS),
        _read_tsv(field_evidence_path, FIELD_EVIDENCE_COLUMNS),
    )
    populations = POPULATIONS_SCHEMA.validate(populations).reset_index(drop=True)
    aliases = ALIASES_SCHEMA.validate(aliases).reset_index(drop=True)
    literature_aliases = aliases.loc[aliases["source"] == SOURCE]
    alias_lookup = literature_aliases.set_index("label")["population_id"]
    placed = populations.set_index("population_id")

    refusals: dict[str, int] = {}
    promoted: list[dict[str, object]] = []
    retained_ids: list[str] = []
    for main in evidence.sort_values("source_record_id").itertuples(index=False):
        main_series = pd.Series(main._asdict())
        rows = field_evidence.loc[
            field_evidence["source_record_id"] == main.source_record_id
        ]
        reason = _reason(main_series, rows)
        if reason is None and main.population_label not in alias_lookup.index:
            if _is_regional_label(main.population_label):
                reason = "population_region_unresolved"
            else:
                raise UnmappedPopulationError(
                    f"{evidence_path}: population label absent from an exact literature P0 alias: "
                    f"{main.population_label!r}"
                )
        if reason is not None:
            refusals[reason] = refusals.get(reason, 0) + 1
            continue

        population_id = alias_lookup.loc[main.population_label]
        if population_id not in placed.index:
            raise UnmappedPopulationError(
                f"{evidence_path}: alias for {main.population_label!r} points to absent P0 row "
                f"{population_id!r}"
            )
        geo = placed.loc[population_id]
        promoted.append(
            {
                "variant_id": main.variant_id,
                "rsid": main.rsid,
                "population_id": population_id,
                "lat": geo["lat"],
                "lon": geo["lon"],
                "radius_km": geo["uncertainty_radius_km"],
                "ac": main.ac_lower,
                "an": main.an,
                "source_record_id": main.source_record_id,
                "source": f"literature:{main.corpus_id}",
                "assay": main.assay,
                "date_lower": main.date_lower,
                "date_upper": main.date_upper,
                "sampling_design": main.sampling_design,
                "disease_ascertainment_excluded": main.disease_ascertainment_excluded,
                "cohort_id": main.cohort_id,
                "ingest_version": ingest_version,
                "sample_id": main.sample_id,
            }
        )
        retained_ids.append(main.source_record_id)

    if promoted:
        duplicate_frame = pd.DataFrame(promoted)
        duplicate_key = ["variant_id", "population_id", "cohort_id", "sample_id"]
        if duplicate_frame.duplicated(duplicate_key, keep=False).any():
            raise ValueError("duplicate variant/population/cohort/sample measurement")
        raw_observations = duplicate_frame.drop(columns="sample_id")
    else:
        raw_observations = pd.DataFrame(columns=OBSERVATIONS_SCHEMA.columns)
    observations = OBSERVATIONS_SCHEMA.validate(raw_observations.reset_index(drop=True))

    if len(observations):
        expected = placed.loc[observations["population_id"]]
        for target, source in (
            ("lat", "lat"), ("lon", "lon"), ("radius_km", "uncertainty_radius_km")
        ):
            if not observations[target].reset_index(drop=True).equals(
                expected[source].reset_index(drop=True).astype(float)
            ):
                raise AssertionError(f"publication {target} must equal its resolved P0 value")
    retained = (
        evidence.loc[evidence["source_record_id"].isin(retained_ids)]
        .sort_values("source_record_id")
        .reset_index(drop=True)
    )
    return observations, retained, IngestReport(
        total=len(evidence), retained=len(observations), refusals=refusals
    )

"""KIR gene presence/absence from AFND, as carrier frequency over individuals (design §6; #133).

    from genomeos.observations.sources import afnd_carriers
    carriers, report = afnd_carriers.load(
        "data/raw/afnd_frequencies.tsv", "data/raw/afnd_populations.tsv", "afnd-2026-08"
    )

**This is not an allele frequency and cannot share a table with one.** KIR genes are copy-number
variable — an individual may carry zero, one or several copies — so a study reports the fraction
of individuals in whom the gene is *present at all*. The denominator is people, not chromosomes,
and there is no diploid genotype to count alleles from. Converting via Hardy-Weinberg would assume
a model the locus does not obey, which §4 forbids as a silent substitution.

So the output validates against `CARRIER_OBSERVATIONS_SCHEMA`, whose columns mirror the
allele-frequency schema apart from `carriers`/`n_individuals` in place of `ac`/`an`. The same
geospatial machinery fits it: a binomial over individuals rather than over chromosomes.

Rows are identified by `allele == gene` ("2DL1", "2DL1"), which is how AFND writes a presence
record. Allele-level KIR rows ("3DL1*007") are genuine allele frequencies and belong to
`afnd_frequencies` instead; they are not read here.

Percentages, not fractions: presence is reported in `indivs_over_n`, which AFND writes as a
percentage (0-100) while `alleles_over_2n` is a fraction (0-1). The conversion happens once, here,
and the range is validated rather than assumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from genomeos.observations.schema import CARRIER_OBSERVATIONS_SCHEMA
from genomeos.registry.sources import afnd as afnd_registry

#: `indivs_over_n` is a percentage. Anything above this means the units changed and the release
#: needs looking at, not rescaling (§12).
MAX_PERCENT = 100.0

#: Presence is a property of the gene, not of an allele, so the id names the gene alone:
#: `kir:2dl1`. There is no allele field to slug.
def variant_id(gene: str) -> str:
    """`"2DL1"` -> `"kir:2dl1"`."""
    return f"kir:{re.sub(r'[^a-z0-9]+', '-', gene.strip().lower()).strip('-')}"


@dataclass(frozen=True)
class CarrierReport:
    """What was retained and what was refused, so the two always add to the input."""

    total_rows: int
    retained: int
    genes: int
    populations: int
    refusals: dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:
        share = self.retained / self.total_rows if self.total_rows else 0.0
        lines = [
            f"{self.retained}/{self.total_rows} presence rows retained ({share:.0%}) — "
            f"{self.genes} KIR genes across {self.populations} populations"
        ]
        for reason, count in sorted(self.refusals.items(), key=lambda kv: -kv[1]):
            lines.append(f"  refused {count:>6}  {reason}")
        return "\n".join(lines)


def load(
    frequencies: Path | str,
    populations: Path | str,
    ingest_version: str,
    *,
    min_populations: int = 1,
) -> tuple[pd.DataFrame, CarrierReport]:
    """KIR gene-presence rows as carrier observations, plus the refusal report."""
    raw = pd.read_csv(frequencies, sep="\t", dtype=str, keep_default_na=False)
    presence = raw[
        (raw["group"].str.strip().str.lower() == "kir")
        & (raw["allele"].str.strip().str.upper() == raw["gene"].str.strip().str.upper())
    ].copy()
    total = len(presence)
    refusals: dict[str, int] = {}
    keep = pd.Series(True, index=presence.index)

    def refuse(mask: pd.Series, reason: str) -> None:
        hit = mask & keep
        count = int(hit.sum())
        if count:
            refusals[reason] = refusals.get(reason, 0) + count
            keep.loc[hit] = False

    def numeric(column: pd.Series) -> pd.Series:
        return pd.to_numeric(column.str.replace(",", "", regex=False).str.strip(), errors="coerce")

    percent = numeric(presence["indivs_over_n"])
    if len(percent.dropna()) and float(percent.max()) > MAX_PERCENT:
        raise ValueError(
            f"indivs_over_n reaches {float(percent.max()):.1f}, above {MAX_PERCENT}. That column "
            f"is a percentage in every release seen so far; a value above 100 means the units "
            f"changed, and rescaling silently would misstate every carrier frequency."
        )
    presence["carrier_fraction"] = percent / 100.0
    presence["n_indiv"] = numeric(presence["n"])

    refuse(presence["carrier_fraction"].isna(), "no_presence_frequency_reported")
    refuse(presence["n_indiv"].isna() | (presence["n_indiv"] <= 0), "no_sample_size")

    registry, aliases, _ = afnd_registry.load(populations, registry_version=ingest_version)
    name_to_id = dict(zip(aliases["label"], aliases["population_id"], strict=True))
    placed = registry.set_index("population_id")[["lat", "lon", "uncertainty_radius_km"]]
    refuse(
        ~presence["population"].map(lambda p: name_to_id.get(p) in placed.index).astype(bool),
        "population_not_placed",
    )
    ascertainment = {
        row["population"]: afnd_registry.sampling_design_for(row["sample_source"])
        for row in pd.read_csv(populations, sep="\t", dtype=str,
                               keep_default_na=False).to_dict("records")
    }
    refuse(
        presence["population"].map(lambda p: ascertainment.get(p) is None),
        "ascertainment_not_stated",
    )

    rows = presence[keep].copy()
    if min_populations > 1:
        counts = rows.groupby("gene")["population"].transform("nunique")
        below = counts < min_populations
        refusals["below_min_populations"] = int(below.sum())
        rows = rows[~below]

    designs = rows["population"].map(lambda p: ascertainment[p])
    n_individuals = rows["n_indiv"].round().astype(int)
    ids = rows["population"].map(name_to_id)
    geo = placed.reindex(ids.to_numpy())
    frame = pd.DataFrame(
        {
            "variant_id": [variant_id(g) for g in rows["gene"]],
            "rsid": pd.Series([None] * len(rows), dtype="object"),
            "population_id": ids.to_numpy(),
            "lat": geo["lat"].to_numpy(),
            "lon": geo["lon"].to_numpy(),
            "radius_km": geo["uncertainty_radius_km"].to_numpy(),
            "carriers": (rows["carrier_fraction"] * n_individuals).round().astype(int).to_numpy(),
            "n_individuals": n_individuals.to_numpy(),
            "source": "afnd",
            "assay": "gene_presence_reconstructed",
            "date_lower": 0,
            "date_upper": 0,
            # `sampling_design_for` returns (design, disease_excluded); both are required with
            # no default (§7.1), so neither is invented here.
            "sampling_design": [d[0] for d in designs],
            "disease_ascertainment_excluded": pd.array(
                [d[1] for d in designs], dtype="boolean"
            ),
            # AFND publishes no study accession, so the population is the cohort — the same
            # convention `afnd_frequencies` uses, and the same caveat applies (#121).
            "cohort_id": ids.to_numpy(),
            "ingest_version": ingest_version,
        }
    )
    validated = CARRIER_OBSERVATIONS_SCHEMA.validate(frame, lazy=True)
    report = CarrierReport(
        total_rows=total,
        retained=len(validated),
        genes=int(validated["variant_id"].nunique()),
        populations=int(validated["population_id"].nunique()),
        refusals=refusals,
    )
    return validated, report

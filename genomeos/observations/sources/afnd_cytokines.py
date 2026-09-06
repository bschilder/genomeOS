"""Cytokine promoter genotypes from AFND, counted into allele frequencies (design §6; #133).

    from genomeos.observations.sources import afnd_cytokines
    obs, report = afnd_cytokines.load(
        "data/raw/afnd_frequencies.tsv", "data/raw/afnd_populations.tsv", "afnd-2026-08"
    )

AFND reports these loci as **diploid genotypes** ("IL-6/ - 174 CC", "CG", "GG") rather than as
alleles, which is why `afnd_frequencies` refuses them: there is no per-row allele count to read.

But the conversion needs no assumption. Where all three genotype classes are present — 99% of
locus x population pairs in this release — the allele frequency follows by counting:

    p(B) = f(BB) + f(AB) / 2

That is arithmetic, not Hardy-Weinberg. HWE would be required only to go the other way, from one
allele frequency to expected genotype frequencies, or to recover an allele frequency from an
incomplete genotype set. Pairs missing a genotype class are refused rather than completed.

Genotype frequencies arrive as **percentages** in `indivs_over_n` (they sum to 100), where
`alleles_over_2n` elsewhere in the same file is a fraction. The conversion happens once, here, and
the sum is validated per locus and population — a triple that does not sum to 100 is either a unit
error or a missing class, and both must fail rather than be rescaled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.source_ids import stable_source_record_id
from genomeos.registry.sources import afnd as afnd_registry

#: Genotype percentages for one locus and population must sum to 100. Measured across 1,405 full
#: triples the sum is 100.0 with a 5th-95th percentile of 99.9 to 100.1, so one point is generous
#: for rounding and tight enough to catch a unit error or a missing genotype class.
GENOTYPE_SUM_TOLERANCE = 1.0

#: Which of a locus's two alleles gets reported.
#:
#: **The minor one, by mean frequency across the corpus.** Choosing alphabetically instead maps the
#: *major* allele for roughly half of loci, and a major-allele surface is flat by construction:
#: TNF-alpha -308 rendered as a solid ~0.9 field worldwide with every population at its ceiling,
#: which invites the reader to conclude the variant is uniform when the informative half of the
#: signal is simply the complement.
#:
#: Decided once per locus, not per population, so the id cannot mean different alleles in
#: different places. A locus whose mean sits exactly at 0.5 keeps the alphabetical choice, since
#: neither allele is minor and the tie has to break somewhere.
MINOR_ALLELE_RULE = "mean frequency below 0.5 across all populations of that locus"


def variant_id(locus: str, allele: str) -> str:
    """`("IL-6/ - 174", "G")` -> `"cyt:il-6-174-g"`.

    The allele is part of the id because a locus has two and the frequency reported is for one of
    them. An id naming only the locus would be ambiguous about which.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", locus.strip().lower()).strip("-")
    return f"cyt:{re.sub(r'-+', '-', slug)}-{allele.strip().lower()}"


@dataclass(frozen=True)
class CytokineReport:
    total_pairs: int
    retained: int
    loci: int
    populations: int
    refusals: dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:
        share = self.retained / self.total_pairs if self.total_pairs else 0.0
        lines = [
            f"{self.retained}/{self.total_pairs} locus x population pairs retained ({share:.0%}) — "
            f"{self.loci} loci across {self.populations} populations"
        ]
        for reason, count in sorted(self.refusals.items(), key=lambda kv: -kv[1]):
            lines.append(f"  refused {count:>6}  {reason}")
        return "\n".join(lines)


def _genotype(call: str) -> str:
    """`"-31CC"` -> `"CC"`. AFND prefixes some calls with the position."""
    return call.strip()[-2:].upper()


def load(
    frequencies: Path | str,
    populations: Path | str,
    ingest_version: str,
    *,
    min_populations: int = 1,
) -> tuple[pd.DataFrame, CytokineReport]:
    """Cytokine genotype triples counted into allele observations, plus the refusal report."""
    raw = pd.read_csv(frequencies, sep="\t", dtype=str, keep_default_na=False)
    cyt = raw[raw["group"].str.strip().str.lower() == "cyt"].copy()
    split = cyt["allele"].str.rsplit(" ", n=1)
    cyt["locus"] = split.str[0].str.strip()
    cyt["call"] = split.str[1].map(_genotype)
    cyt["percent"] = pd.to_numeric(
        cyt["indivs_over_n"].str.replace(",", "", regex=False).str.strip(), errors="coerce"
    )
    cyt["n_indiv"] = pd.to_numeric(
        cyt["n"].str.replace(",", "", regex=False).str.strip(), errors="coerce"
    )

    registry, aliases, _ = afnd_registry.load(populations, registry_version=ingest_version)
    name_to_id = dict(zip(aliases["label"], aliases["population_id"], strict=True))
    placed = registry.set_index("population_id")[["lat", "lon", "uncertainty_radius_km"]]
    ascertainment = {
        row["population"]: afnd_registry.sampling_design_for(row["sample_source"])
        for row in pd.read_csv(populations, sep="\t", dtype=str,
                               keep_default_na=False).to_dict("records")
    }

    refusals: dict[str, int] = {}
    records: list[dict] = []
    pairs = list(cyt.groupby(["locus", "population"], sort=True))

    def refuse(reason: str) -> None:
        refusals[reason] = refusals.get(reason, 0) + 1

    for (locus, population), group in pairs:
        calls = {c: p for c, p in zip(group["call"], group["percent"], strict=True)}
        if any(pd.isna(v) for v in calls.values()):
            refuse("no_genotype_frequency_reported")
            continue
        homozygous = sorted(c for c in calls if c[0] == c[1])
        heterozygous = [c for c in calls if c[0] != c[1]]
        if len(homozygous) != 2 or len(heterozygous) != 1:
            # An incomplete genotype set. Recovering an allele frequency from it would need
            # Hardy-Weinberg, which is an assumption about the population rather than arithmetic.
            refuse("incomplete_genotype_set")
            continue
        total = sum(calls.values())
        if abs(total - 100.0) > GENOTYPE_SUM_TOLERANCE:
            refuse("genotype_percentages_do_not_sum_to_100")
            continue
        n_indiv = group["n_indiv"].max()
        if pd.isna(n_indiv) or n_indiv <= 0:
            refuse("no_sample_size")
            continue
        pid = name_to_id.get(population)
        if pid not in placed.index:
            refuse("population_not_placed")
            continue
        design = ascertainment.get(population)
        if design is None:
            refuse("ascertainment_not_stated")
            continue

        # p = f(BB) + f(AB)/2, counted against the alphabetically second homozygote. Which of
        # the two alleles is finally *reported* is decided per locus after this loop; see
        # MINOR_ALLELE_RULE.
        reference = homozygous[1][0]
        other = homozygous[0][0]
        frequency = (calls[homozygous[1]] + calls[heterozygous[0]] / 2.0) / 100.0
        an = int(round(2 * n_indiv))
        geo = placed.loc[pid]
        records.append(
            {
                "locus": locus,
                "reference_allele": reference,
                "other_allele": other,
                "variant_id": variant_id(locus, reference),
                "rsid": None,
                "population_id": pid,
                "lat": float(geo["lat"]),
                "lon": float(geo["lon"]),
                "radius_km": float(geo["uncertainty_radius_km"]),
                "ac": int(round(frequency * an)),
                "an": an,
                "source_record_id": stable_source_record_id(
                    "afnd-cytokines", locus, population
                ),
                "source": "afnd",
                "assay": "genotype_counted",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": design[0],
                "disease_ascertainment_excluded": design[1],
                "cohort_id": pid,
                "ingest_version": ingest_version,
            }
        )

    # Explicit columns, so a run where every pair is refused still returns a frame the schema
    # can validate rather than a shapeless empty one. A refusal-only result is a valid outcome.
    frame = pd.DataFrame.from_records(
        records, columns=[*OBSERVATIONS_SCHEMA.columns, "locus", "reference_allele",
                          "other_allele"]
    )
    # Second pass: report the minor allele. See MINOR_ALLELE_RULE. Frequencies are complemented
    # rather than recomputed, which is exact: p(A) = 1 - p(B) for a biallelic locus.
    if len(frame):
        mean_by_locus = (frame["ac"] / frame["an"]).groupby(frame["locus"]).transform("mean")
        flip = mean_by_locus > 0.5
        frame.loc[flip, "ac"] = frame.loc[flip, "an"] - frame.loc[flip, "ac"]
        frame.loc[flip, "variant_id"] = [
            variant_id(row.locus, row.other_allele) for row in frame[flip].itertuples()
        ]
    frame = frame.drop(columns=["locus", "reference_allele", "other_allele"])
    if min_populations > 1 and len(frame):
        counts = frame.groupby("variant_id")["population_id"].transform("nunique")
        below = counts < min_populations
        refusals["below_min_populations"] = int(below.sum())
        frame = frame[~below]
    frame["disease_ascertainment_excluded"] = pd.array(
        frame["disease_ascertainment_excluded"], dtype="boolean"
    )
    validated = OBSERVATIONS_SCHEMA.validate(frame, lazy=True)
    report = CytokineReport(
        total_pairs=len(pairs),
        retained=len(validated),
        loci=int(validated["variant_id"].nunique()),
        populations=int(validated["population_id"].nunique()),
        refusals=refusals,
    )
    return validated, report

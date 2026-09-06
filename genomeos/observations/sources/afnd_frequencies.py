"""AFND allele-frequency adapter, joined to the population registry (design §6, §7.1, P1).

Turns AFND's HLA/KIR/MIC/cytokine frequency tables into observations, taking coordinates and
ascertainment from the population metadata `registry.sources.afnd` reads. It is the widest source
in the corpus by a long way — **79,672 usable rows across 4,059 alleles and 1,477 populations**,
against 1,071 HbS surveys — and the first that lets the pipeline be exercised on thousands of
variants rather than two.

**Counts are reconstructed, and that is the main caveat.** AFND publishes a *frequency*
(`alleles_over_2n`) and a sample size (`n`), not the underlying allele count, so
``ac = round(af * 2n)``. The frequency is printed to four decimal places, which bounds the
reconstruction error at ``0.00005 * 2n`` — under half an allele for any sample below 10,000, so
the recovered integer is almost always exact. It is still a reconstruction, and a binomial
likelihood over a reconstructed count is not quite the same object as one over a measured count.
Recorded in `assay` as ``frequency_reconstructed`` rather than left to be inferred.

**Ascertainment is inherited from the population, and refused where AFND does not state it.**
§7.1 gives `sampling_design` and `disease_ascertainment_excluded` no defaults. The registry keeps
populations whose `Source:` is outside the reviewed vocabulary — a registry stores no ascertainment
— but P1 cannot: an observation needs a design, so those rows are refused here. That split is
deliberate and is where the registry's `unmapped_ascertainment` count comes due.

**`cohort_id` is the population**, because AFND publishes one study per population entry. Unlike
the MAP layers there is no separate study accession to group by, so population and cohort coincide;
that is a real limit on how much the §7.1d cohort effect can be identified from this source.

Alleles are keyed ``hla:<gene>-<fields>`` (`DQB1*03:01` -> `hla:dqb1-03-01`). An HLA allele is a
haplotype of many linked variants named by the WHO Nomenclature Committee, not a `chr-pos-ref-alt`
triple; see `observations.schema.VARIANT_ID_PATTERN`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.source_ids import stable_source_record_id
from genomeos.registry.sources import afnd as afnd_registry

SOURCE = "afnd_frequencies"

#: Frequencies are printed to four decimal places, so a reconstructed count is exact whenever
#: `0.00005 * 2n < 0.5`, i.e. for any sample below this many individuals. Larger samples are still
#: accepted — the relative error stays negligible — but the bound is stated rather than assumed.
EXACT_RECONSTRUCTION_MAX_N = 5000

#: Bone-marrow donor registries whose AFND sub-populations are **ancestry strata, not places**
#: (#141). Matched case-insensitively against the population name.
#:
#: NMDP and DKMS build these strata deliberately, because HLA matching requires a donor of the
#: same ancestral background — so the label is scientifically meaningful and the data is the
#: best-powered in the corpus. It is simply not point-referenced. Two facts make that concrete:
#:
#: - All 21 NMDP strata sit at one coordinate (38.8, -76.1), the registry's address in Maryland,
#:   and all 15 DKMS strata at one German coordinate. For `HLA-A*02:01` the NMDP strata span
#:   0.035 to 0.278 at zero geographic separation. No spatial field can reconcile that, because
#:   the variation is stratification rather than geography.
#: - Together the 37 populations carry **91% of the corpus's statistical weight** against 905
#:   genuinely geographic populations sharing the other 9%. Through a binomial likelihood that
#:   lets a registry's donor composition pin surfaces across whole continents.
#:
#: Neither relocation nor a nugget fixes it. "NMDP European Caucasian" is a blend of European
#: source populations mixed by US immigration history, which corresponds to no location in
#: Europe; "NMDP African American" is ~73% African and ~24% European (Bryc et al. 2015) and
#: matches no single source population either. And an explicit nugget was tested against exactly
#: this: it moved C*03:03's fitted range by 12% where the variogram implied 65% (#137).
#:
#: `DKMS German donors` is refused with the rest despite being a national sample rather than a
#: stratum: it shares the registry coordinate with 14 strata, it is donor-ascertained, and at
#: 6,912,132 chromosomes it alone is 49.8% of the corpus, so keeping it reproduces the pathology
#: on its own. It is the strongest candidate for re-admission once #21 (per-population radii)
#: and #123 (weight capping) exist.
DONOR_REGISTRIES = ("NMDP", "DKMS")

#: AFND's two frequency columns carry **different units**, a 100x difference in one file:
#: `alleles_over_2n` is a fraction (max 1.000 across the corpus) and `indivs_over_n` is a
#: percentage (max 100.0). Reading the wrong one without dividing yields a frequency of 63 where
#: 0.63 was meant, which no downstream check would catch because the schema only bounds `ac <= an`.
#:
#: Validated rather than assumed. A fraction column above 1.0 means the release changed units
#: under us, and §12 makes that a hard error rather than something to rescale silently.
MAX_FRACTION = 1.0
#: Genotype percentages for one locus and population must sum to 100. Measured across 1,405 full
#: triples the sum is 100.0 with a 5th-95th percentile of 99.9 to 100.1, so a 1-point tolerance
#: is generous for rounding and tight enough to catch a unit error or a missing genotype class.
GENOTYPE_SUM_TOLERANCE = 1.0


#: AFND's own `group` column mapped onto the variant_id namespace. The prefix is a provenance
#: claim, so it has to name the right family: KIR2DL1 is not an HLA allele and an id saying it is
#: is a false statement about what was measured, not a naming preference (#134). AFND ships this
#: column; the first version of this adapter hardcoded `hla:` for all four families.
GROUP_PREFIX = {"hla": "hla", "kir": "kir", "mic": "mic", "cyt": "cyt"}


def variant_id(gene: str, allele: str, group: str) -> str:
    """`("DQB1", "DQB1*03:01", "hla")` -> `"hla:dqb1-03-01"`; `("2DL1", "2DL1*003", "kir")` ->
    `"kir:2dl1-003"`.

    The gene prefix is dropped from the allele where AFND repeats it, so the id is not
    `hla:dqb1-dqb1-03-01`. Colons and asterisks become hyphens; the WHO name stays recoverable.

    `group` is required rather than defaulted. A default would put the burden of remembering the
    family on every caller and silently mislabel the ones that forget, which is exactly the bug
    this signature exists to prevent.
    """
    key = group.strip().lower()
    if key not in GROUP_PREFIX:
        raise ValueError(
            f"unknown AFND group {group!r}; expected one of {sorted(GROUP_PREFIX)}. A new family "
            f"needs a namespace and a decision about whether it is an allele frequency at all."
        )
    name = allele.strip()
    if name.upper().startswith(f"{gene.strip().upper()}*"):
        name = name[len(gene) + 1 :]
    slug = re.sub(r"[^a-z0-9]+", "-", f"{gene.strip()}-{name}".lower()).strip("-")
    return f"{GROUP_PREFIX[key]}:{re.sub(r'-+', '-', slug)}"


@dataclass(frozen=True)
class IngestReport:
    total: int
    retained: int
    refusals: dict[str, int] = field(default_factory=dict)
    n_variants: int = 0
    n_populations: int = 0
    reconstructed_beyond_exact: int = 0

    @property
    def retained_fraction(self) -> float:
        return self.retained / self.total if self.total else 0.0

    def __str__(self) -> str:
        lines = [
            f"{self.retained}/{self.total} rows retained ({self.retained_fraction:.0%}) — "
            f"{self.n_variants} alleles across {self.n_populations} populations"
        ]
        if self.reconstructed_beyond_exact:
            lines.append(
                f"  {self.reconstructed_beyond_exact} rows have n > {EXACT_RECONSTRUCTION_MAX_N}, "
                "where the reconstructed count may be off by an allele"
            )
        for reason, count in sorted(self.refusals.items(), key=lambda kv: -kv[1]):
            lines.append(f"  refused {count:>6}  {reason}")
        return "\n".join(lines)


def load(
    frequencies: Path,
    populations: Path,
    ingest_version: str,
    *,
    min_populations: int = 1,
) -> tuple[pd.DataFrame, IngestReport]:
    """Read AFND frequencies joined to population coordinates.

    `min_populations` drops alleles measured in fewer than that many populations. It is a
    *modelling* filter rather than a data judgement — a spatial field cannot be identified from a
    handful of points — so it defaults to keeping everything and the caller states the threshold.
    """
    freq = pd.read_csv(frequencies, sep="\t", dtype=str, keep_default_na=False)
    pops = pd.read_csv(populations, sep="\t", dtype=str, keep_default_na=False)
    # Coordinates and radii come from the *registry adapter*, not from re-parsing the TSV, so the
    # reviewed derivation is used once: sexagesimal parsing, the settlement extent, and the
    # coordinate-precision floor that stops `41 deg 0' N` being read as an arcminute fix.
    registry, aliases, _ = afnd_registry.load(populations, registry_version=ingest_version)
    name_to_id = dict(zip(aliases["label"], aliases["population_id"], strict=True))
    placed = registry.set_index("population_id")[["lat", "lon", "uncertainty_radius_km"]]
    total = len(freq)
    refusals: dict[str, int] = {}

    keep = pd.Series(True, index=freq.index)

    def refuse(mask: pd.Series, reason: str) -> None:
        """Refuse rows not already refused, so every input row is counted exactly once.

        Masking against `keep` is the whole point: counting each condition over the full frame
        double-counts a row that fails two of them, and then retained + refused no longer equals
        the input — which is the one property a refusal report has to have (§12).
        """
        hit = mask & keep
        count = int(hit.sum())
        if count:
            refusals[reason] = refusals.get(reason, 0) + count
            keep.loc[hit] = False

    # Family refusals come first, so a cytokine row that also lacks a frequency is reported as a
    # cytokine row rather than as missing data. Three of AFND's four families are not allele
    # frequencies and this adapter's output column is an allele count (#134, #133).
    # Ahead of every other refusal: a registry stratum that also lacks a frequency should be
    # reported as what it is, not as missing data. Same reasoning as the family refusals below.
    registry = freq["population"].str.contains(
        "|".join(DONOR_REGISTRIES), case=False, regex=True, na=False
    )
    refuse(registry, "donor_registry_ancestry_stratum")

    group_key = freq["group"].str.strip().str.lower()
    refuse(~group_key.isin(GROUP_PREFIX), "unknown_afnd_group")
    # Cytokine rows are diploid GENOTYPES ("AIF-1/ -932 CC", "-932 CT"), not alleles: 0 of 4,517
    # are gene-presence rows, they are all genotype-level. Reconstructing ac = af * 2n from a
    # genotype frequency is a category error, and recovering an allele count would require
    # assuming Hardy-Weinberg — an assumption about the population, not a parsing detail.
    refuse(group_key == "cyt", "cytokine_genotype_not_allele_frequency")
    # KIR genes are copy-number variable, so a row whose allele repeats its gene name ("2DL1",
    # "2DL1") reports the fraction of individuals CARRYING the gene. That is a carrier frequency
    # over individuals, not an allele frequency over chromosomes. 3,790 of 6,714 KIR rows are of
    # this kind; the remaining allele-level rows ("3DL1*007") are kept.
    gene_presence = freq["allele"].str.strip().str.upper() == freq["gene"].str.strip().str.upper()
    refuse((group_key == "kir") & gene_presence, "kir_gene_presence_not_allele_frequency")

    # AFND prints sample sizes with thousand separators ("3,732"). Parsing without stripping them
    # silently refused 33,514 rows — 27% of the table — as having no sample size at all, which is
    # indistinguishable in a refusal report from data that genuinely lacks one.
    def numeric(column: pd.Series) -> pd.Series:
        return pd.to_numeric(column.str.replace(",", "", regex=False).str.strip(), errors="coerce")

    freq["af"] = numeric(freq["alleles_over_2n"])
    freq["n_indiv"] = numeric(freq["n"])

    # The unit check, before anything reads the column. See MAX_FRACTION.
    over = freq["af"].dropna()
    if len(over) and float(over.max()) > MAX_FRACTION:
        raise ValueError(
            f"alleles_over_2n reaches {float(over.max()):.3f}, above {MAX_FRACTION}. That column "
            f"is a fraction in every release seen so far; a value above 1 means the units "
            f"changed, and rescaling silently would misstate every frequency downstream."
        )

    refuse(freq["af"].isna(), "no_frequency_reported")
    refuse(freq["n_indiv"].isna() | (freq["n_indiv"] <= 0), "no_sample_size")
    refuse(~freq["af"].between(0.0, 1.0), "frequency_outside_unit_interval")

    # The join is on population name, which is AFND's own public key and the key both sides
    # already use — so this is an exact join, not a fuzzy match. Unmatched names are almost all
    # mojibake in the frequency table ("Parana" written as "ParanA") and are refused, not guessed.
    known = set(pops["population"])
    refuse(~freq["population"].isin(known), "population_not_in_registry")

    # A population must be in the registry *and* have a stated ascertainment. The registry keeps
    # the latter kind because it stores no ascertainment; an observation cannot.
    refuse(
        ~freq["population"].map(lambda p: name_to_id.get(p) in placed.index).astype(bool),
        "population_not_placed",
    )
    ascertainment = {
        row["population"]: afnd_registry.sampling_design_for(row["sample_source"])
        for row in pops.to_dict("records")
    }
    refuse(
        freq["population"].map(lambda p: ascertainment.get(p) is None),
        "ascertainment_not_stated",
    )

    rows = freq[keep].copy()
    if min_populations > 1:
        counts = rows.groupby(["gene", "allele"])["population"].transform("nunique")
        below = counts < min_populations
        refusals["below_min_populations"] = int(below.sum())
        rows = rows[~below]

    an = (2 * rows["n_indiv"]).round().astype(int)
    designs = rows["population"].map(lambda p: ascertainment[p])
    ids = rows["population"].map(name_to_id)
    geo = placed.reindex(ids.to_numpy())
    obs = pd.DataFrame(
        {
            "variant_id": [
                variant_id(g, a, grp)
                for g, a, grp in zip(rows["gene"], rows["allele"], rows["group"], strict=True)
            ],
            "rsid": pd.Series([pd.NA] * len(rows), index=rows.index, dtype="string[pyarrow]"),
            "population_id": ids.to_numpy(),
            "lat": geo["lat"].to_numpy(),
            "lon": geo["lon"].to_numpy(),
            "radius_km": geo["uncertainty_radius_km"].to_numpy(),
            # Reconstructed from a four-decimal frequency; see the module docstring.
            "ac": (rows["af"] * an).round().astype(int),
            "an": an,
            "source_record_id": [
                stable_source_record_id("afnd-frequencies", group, gene, allele, population)
                for group, gene, allele, population in zip(
                    rows["group"], rows["gene"], rows["allele"], rows["population"], strict=True
                )
            ],
            "source": SOURCE,
            "assay": "frequency_reconstructed",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": [d[0] for d in designs],
            "disease_ascertainment_excluded": pd.array([d[1] for d in designs], dtype="boolean"),
            # One study per population entry in AFND, so population and cohort coincide. See the
            # module docstring on what that costs the §7.1d cohort effect.
            "cohort_id": ids.to_numpy(),
            "ingest_version": ingest_version,
        }
    )
    obs = OBSERVATIONS_SCHEMA.validate(obs.reset_index(drop=True))
    report = IngestReport(
        total=total,
        retained=len(obs),
        refusals=refusals,
        n_variants=int(obs["variant_id"].nunique()),
        n_populations=int(obs["population_id"].nunique()),
        reconstructed_beyond_exact=int((rows["n_indiv"] > EXACT_RECONSTRUCTION_MAX_N).sum()),
    )
    return obs, report

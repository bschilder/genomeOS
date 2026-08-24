"""Extract Piel et al. 2013 national estimates — the golden test 1 target (design §8).

Source: the Lancet supplementary appendix (`mmc1.pdf`) of

    Piel FB et al. Global epidemiology of sickle haemoglobin in neonates: a contemporary
    geostatistical model-based map and population estimates. Lancet 2013; 381: 142-51.
    doi:10.1016/S0140-6736(12)61229-X

Web Table 1 (pp. 31-34) gives, per country: population, crude birth rate, WHO/HbS region, number
of surveys, HbS allele frequency, AS neonates per year, and SS neonates per year — each with an
**interquartile range**, i.e. a 50% credible interval, not a 95% one. §8 scores our intervals
against these, so the comparison must be like-for-like; see #45.

    pdftotext -layout mmc1.pdf mmc1.txt
    python scripts/extract_piel2013_targets.py --text mmc1.txt --out reference/piel2013_national_estimates.csv

Transcription of published numbers, so it is committed rather than fetched: the target for the
v1 definition of done has to be citable at a fixed version.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

# The appendix uses U+2010 HYPHEN in ranges, not ASCII hyphen-minus.
_DASH = r"[‐‑‒–-]"
_INT = r"[\d,]+"
_DEC = r"\d*\.\d+|\d+"

ROW = re.compile(
    rf"^(?P<head>.+?)\s+"
    rf"(?P<surveys>\d+)\s+"
    rf"(?P<af>{_DEC})\s*\((?P<af_lo>{_DEC}){_DASH}(?P<af_hi>{_DEC})\)\s+"
    rf"(?P<as_>{_INT})\s*\((?P<as_lo>{_INT}){_DASH}(?P<as_hi>{_INT})\)\s+"
    rf"(?P<ss>{_INT})\s*\((?P<ss_lo>{_INT}){_DASH}(?P<ss_hi>{_INT})\)\s+"
    rf"(?P<md>{_INT})\s*(?P<flag>\*{{0,2}})\s*$"
)

# The head is "<country> <population> <cbr> <region>"; country names contain spaces, commas and
# apostrophes, so it is split from the numbers rather than matched positionally.
HEAD = re.compile(rf"^(?P<country>.+?)\s+(?P<population>{_INT})\s+(?P<cbr>{_DEC})\s+(?P<region>.+)$")

FIELDS = [
    "country", "population_thousands", "crude_birth_rate", "who_hbs_region", "surveys",
    "hbs_af", "hbs_af_iqr_lower", "hbs_af_iqr_upper",
    "as_neonates_per_year", "as_iqr_lower", "as_iqr_upper",
    "ss_neonates_per_year", "ss_iqr_lower", "ss_iqr_upper",
    "modell_darlison_ss", "modell_darlison_outside_flag",
]


def _int(value: str) -> int:
    return int(value.replace(",", ""))


def parse(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if not match:
            continue
        head = HEAD.match(match.group("head").strip())
        if not head:
            continue
        country = head.group("country").strip()
        if country in seen or country.lower().startswith("country"):
            continue
        seen.add(country)
        rows.append(
            {
                "country": country,
                "population_thousands": _int(head.group("population")),
                "crude_birth_rate": float(head.group("cbr")),
                "who_hbs_region": head.group("region").strip(),
                "surveys": int(match.group("surveys")),
                "hbs_af": float(match.group("af")),
                "hbs_af_iqr_lower": float(match.group("af_lo")),
                "hbs_af_iqr_upper": float(match.group("af_hi")),
                "as_neonates_per_year": _int(match.group("as_")),
                "as_iqr_lower": _int(match.group("as_lo")),
                "as_iqr_upper": _int(match.group("as_hi")),
                "ss_neonates_per_year": _int(match.group("ss")),
                "ss_iqr_lower": _int(match.group("ss_lo")),
                "ss_iqr_upper": _int(match.group("ss_hi")),
                "modell_darlison_ss": _int(match.group("md")),
                "modell_darlison_outside_flag": match.group("flag") or "",
            }
        )
    return rows


def check(rows: list[dict[str, object]]) -> list[str]:
    """Sanity checks. A silently dropped or merged PDF row would later read as a model failure."""
    problems = []
    for row in rows:
        country = row["country"]
        for stem in ("hbs_af", "as", "ss"):
            lo = row[f"{stem}_iqr_lower" if stem != "hbs_af" else "hbs_af_iqr_lower"]
            hi = row[f"{stem}_iqr_upper" if stem != "hbs_af" else "hbs_af_iqr_upper"]
            mid = row[f"{stem}_neonates_per_year"] if stem != "hbs_af" else row["hbs_af"]
            if not lo <= mid <= hi:
                problems.append(f"{country}: {stem} point {mid} outside IQR [{lo}, {hi}]")
        if not 0.0 <= row["hbs_af"] <= 0.5:
            problems.append(f"{country}: implausible HbS allele frequency {row['hbs_af']}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", type=Path, required=True, help="pdftotext -layout output of mmc1.pdf")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows = parse(args.text.read_text())
    problems = check(rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"extracted {len(rows)} countries -> {args.out}")
    print(f"  global AS neonates/year: {sum(r['as_neonates_per_year'] for r in rows):,}")
    print(f"  global SS neonates/year: {sum(r['ss_neonates_per_year'] for r in rows):,}")
    if problems:
        print(f"  {len(problems)} consistency problems:")
        for problem in problems[:10]:
            print(f"    {problem}")


if __name__ == "__main__":
    main()

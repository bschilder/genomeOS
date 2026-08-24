"""Piel et al. 2013 national HbS estimates — the golden test 1 target (design §8).

    Piel FB, Patil AP, Howes RE, et al. Global epidemiology of sickle haemoglobin in neonates:
    a contemporary geostatistical model-based map and population estimates.
    Lancet 2013; 381: 142-51. doi:10.1016/S0140-6736(12)61229-X

Transcribed from Web Table 1 of the supplementary appendix by `scripts/extract_piel2013_targets.py`
and committed, because the target for v1's definition of done must be citable at a fixed version.

**Two properties of these numbers that change how §8 must be scored.**

1. **The intervals are IQRs — 50% credible intervals**, per the appendix's footnote 5: "IQR:
   interquartile range of the posterior predictive distribution". §8 requires that "our credible
   interval overlaps the published interval", and our artifacts carry a 95% interval (q025/q975).
   Overlapping a 95% interval with a 50% one is close to free, so scoring that way would make the
   criterion pass almost regardless of model quality. The comparison has to be like for like.
   Raised on #92.

2. **The point estimates are medians, which do not sum.** These 191 national medians total
   5,239,477 AS and 288,814 SS, against the paper's global posterior of 5,476,000 AS
   (IQR 5,291,000-5,679,000) and 312,000 SS (294,000-330,000) — 4% and 7% lower, and the SS sum
   falls below the published IQR. That gap is arithmetic, not error: the global figure comes from
   the global posterior, and summing right-skewed per-country medians understates it. §8's third
   criterion, "global totals agree within the published uncertainty", must therefore compare our
   *global posterior* against theirs, never a sum of our national medians.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

CITATION = "Piel FB et al. Lancet 2013; 381: 142-51. doi:10.1016/S0140-6736(12)61229-X"
REFERENCE_YEAR = 2010

DATA_PATH = Path(__file__).resolve().parents[2] / "reference" / "piel2013_national_estimates.csv"

#: Global posterior estimates as published in the abstract, for §8's third criterion.
GLOBAL_AS_NEONATES = (5_476_000, 5_291_000, 5_679_000)  # median, IQR lower, IQR upper
GLOBAL_SS_NEONATES = (312_000, 294_000, 330_000)


@lru_cache(maxsize=1)
def national_estimates() -> pd.DataFrame:
    """One row per country: median and IQR for HbS allele frequency, AS and SS neonates/year."""
    frame = pd.read_csv(DATA_PATH)
    if frame.empty:
        raise ValueError(f"{DATA_PATH} is empty")
    return frame

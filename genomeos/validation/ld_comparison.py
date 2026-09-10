"""Pure CuGen pair-output reconciliation (CuGen pilot design §7; Atlas design §4).

The comparator admits only the independently requested observed pairs and exact annotations.
It does not import CuGen, infer missing pair identities, or treat pairwise LD as covariance.
"""

from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np
import pandas as pd

from genomeos.validation.ld_contract import validate_ld_variants
from genomeos.validation.ld_reference import validate_ld_evidence

LD_OUTPUT_COLUMNS = (
    "CHR_A",
    "POS_A",
    "ID_A",
    "MAF_A",
    "CHR_B",
    "POS_B",
    "ID_B",
    "MAF_B",
    "N_OBS",
    "R",
    "R2",
    "gidx_a",
    "gidx_b",
)


def _integer(value: object, column: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{column} must contain exact integers")
    return int(value)


def _float(value: object, column: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{column} must contain real numbers")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{column} must contain finite values in [{minimum}, {maximum}]")
    return result


def reconcile_ld_output(
    reference: object,
    variants: object,
    moments: object,
    output: pd.DataFrame,
) -> dict[str, int | float | bool]:
    """Reconcile one CuGen pair frame against exact independent reference evidence."""
    block = validate_ld_variants(variants, genome_build="GRCh38", ploidy="autosomal_diploid")
    pairs, moment_block = validate_ld_evidence(
        reference,
        block,
        moments,
        genome_build="GRCh38",
        ploidy="autosomal_diploid",
    )
    if not isinstance(output, pd.DataFrame):
        raise TypeError("output must be a pandas DataFrame")
    if tuple(output.columns) != LD_OUTPUT_COLUMNS:
        raise ValueError("CuGen pair output columns do not match the admitted schema")

    observed = {(pair.gidx_a, pair.gidx_b): pair for pair in pairs if pair.status == "observed"}
    emitted: dict[tuple[int, int], tuple[float, float, float, float]] = {}
    for values in output.itertuples(index=False, name=None):
        (
            chrom_a,
            pos_a,
            id_a,
            maf_a,
            chrom_b,
            pos_b,
            id_b,
            maf_b,
            n_obs,
            r,
            r2,
            gidx_a,
            gidx_b,
        ) = values
        parsed_identity = (_integer(gidx_a, "gidx_a"), _integer(gidx_b, "gidx_b"))
        if parsed_identity in emitted:
            raise ValueError("CuGen output contains a duplicate pair")
        if parsed_identity not in observed:
            if (parsed_identity[1], parsed_identity[0]) in observed:
                raise ValueError("CuGen output contains a reversed pair")
            raise ValueError("CuGen output contains an unexpected or invalid pair")
        pair = observed[parsed_identity]
        variant_a, variant_b = block[pair.row_a], block[pair.row_b]
        if (
            _integer(chrom_a, "CHR_A") != int(variant_a.chrom)
            or _integer(pos_a, "POS_A") != variant_a.position
            or not isinstance(id_a, str)
            or id_a != variant_a.variant_id
            or _integer(chrom_b, "CHR_B") != int(variant_b.chrom)
            or _integer(pos_b, "POS_B") != variant_b.position
            or not isinstance(id_b, str)
            or id_b != variant_b.variant_id
        ):
            raise ValueError("CuGen output annotation disagrees with supplied variants")
        if _integer(n_obs, "N_OBS") != pair.n_obs:
            raise ValueError("CuGen output N_OBS disagrees with independent counts")
        parsed_maf_a = _float(maf_a, "MAF_A", minimum=0.0, maximum=0.5)
        parsed_maf_b = _float(maf_b, "MAF_B", minimum=0.0, maximum=0.5)
        expected_maf_a = moment_block[pair.row_a].maf
        expected_maf_b = moment_block[pair.row_b].maf
        if expected_maf_a is None or expected_maf_b is None:
            raise ValueError("an observed pair cannot have an all-missing variant MAF")
        maf_error_a = abs(parsed_maf_a - expected_maf_a)
        maf_error_b = abs(parsed_maf_b - expected_maf_b)
        if maf_error_a > 1e-7 or maf_error_b > 1e-7:
            raise ValueError("CuGen output MAF disagrees with independent moments")
        parsed_r = _float(r, "R", minimum=-1.0, maximum=1.0)
        parsed_r2 = _float(r2, "R2", minimum=0.0, maximum=1.0)
        assert pair.r is not None and pair.r2 is not None
        r_error = abs(parsed_r - pair.r)
        r2_error = abs(parsed_r2 - pair.r2)
        if r_error > 1e-5:
            raise ValueError("CuGen output R exceeds the absolute error budget")
        if r2_error > 2e-5:
            raise ValueError("CuGen output R2 exceeds the absolute error budget")
        emitted[parsed_identity] = (r_error, r2_error, maf_error_a, maf_error_b)

    if set(emitted) != set(observed):
        raise ValueError("CuGen output omits an independently observed requested pair")
    errors = tuple(emitted.values())
    return {
        "requested_pairs": len(pairs),
        "observed_pairs": len(observed),
        "invalid_pairs": len(pairs) - len(observed),
        "maximum_absolute_r_error": max((item[0] for item in errors), default=0.0),
        "maximum_absolute_r2_error": max((item[1] for item in errors), default=0.0),
        "maximum_absolute_maf_error": max((max(item[2], item[3]) for item in errors), default=0.0),
        "passed": True,
    }

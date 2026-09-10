"""Independent checks for the training-only LD reference (pilot design §§3-4)."""

from __future__ import annotations

import importlib
import importlib.util
import math
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

CALLS = np.array(
    [
        [0, 0, 2, 3, 1, 0, 3],
        [1, 1, 1, 3, 1, 3, 3],
        [2, 2, 0, 3, 1, 2, 3],
        [0, 2, 0, 3, 1, 3, 0],
        [2, 0, 2, 3, 1, 1, 1],
        [1, 2, 0, 3, 1, 2, 3],
        [0, 1, 1, 3, 1, 0, 0],
        [2, 0, 2, 3, 1, 2, 3],
    ],
    dtype=np.uint8,
)
TRAINING_ROWS = (4, 0, 2, 1)
GIDX = (30, 10, 70, 20, 60, 40, 50)


class _OversizedSequence(Sequence[object]):
    def __init__(self, length: int) -> None:
        self._length = length

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, index: int) -> object:
        raise AssertionError("oversized input must be refused before materialization")


class _GuardedOversizedMoments(list[object]):
    def __len__(self) -> int:
        return 10**9

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("wrong-length moments must be refused before copying or scanning")


def _api() -> tuple[object, object]:
    spec = importlib.util.find_spec("genomeos.validation.ld_contract")
    assert spec is not None, "public LD contract module must exist"
    return (
        importlib.import_module("genomeos.validation.ld_contract"),
        importlib.import_module("genomeos.validation.ld_reference"),
    )


def _comparison() -> object:
    spec = importlib.util.find_spec("genomeos.validation.ld_comparison")
    assert spec is not None, "public CuGen LD comparison module must exist"
    return importlib.import_module("genomeos.validation.ld_comparison")


def _literal_comparison_evidence() -> tuple[tuple[object, ...], tuple[object, ...], pd.DataFrame]:
    _, reference = _api()
    pairs = (
        reference.LDPair(
            0,
            1,
            30,
            10,
            4,
            (1, 0, 0, 0, 1, 0, 1, 0, 1),
            "observed",
            5 / 11,
            (5 / 11) ** 2,
        ),
    )
    moments = (
        reference.VariantMoments(4, 5, 1.25, 2.75, 0.375),
        reference.VariantMoments(4, 3, 0.75, 2.75, 0.375),
    )
    output = pd.DataFrame(
        [[1, 101, "1-101-A-C", 0.375, 1, 201, "1-201-A-C", 0.375, 4, 5 / 11, (5 / 11) ** 2, 30, 10]],
        columns=(
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
        ),
    )
    return pairs, moments, output


def _variants() -> tuple[object, ...]:
    contract, _ = _api()
    return tuple(
        contract.LDVariant(index, f"1-{position}-A-C", "1", position, "A", "C")
        for index, position in zip(GIDX, range(101, 702, 100), strict=True)
    )


def _reference(calls: object = CALLS[np.array(TRAINING_ROWS)]) -> tuple[object, ...]:
    _, reference = _api()
    variant_count = np.asarray(calls).shape[1]
    return reference.reference_ld(
        calls,
        _variants()[:variant_count],
        genome_build="GRCh38",
        ploidy="autosomal_diploid",
        window_variants=None,
        window_bp=None,
    )


def test_reference_ld_preserves_pair_identity_counts_and_invalid_states() -> None:
    """Catch an absent or incomplete reference that loses requested-pair evidence."""
    pairs = _reference()

    first = pairs[0]
    assert (first.row_a, first.row_b) == (0, 1)
    assert (first.gidx_a, first.gidx_b, first.n_obs) == (30, 10, 4)
    assert first.counts == (1, 0, 0, 0, 1, 0, 1, 0, 1)
    assert first.r == pytest.approx(5 / 11)
    assert first.r2 == pytest.approx(25 / 121)
    assert Counter(pair.status for pair in pairs) == {
        "observed": 6,
        "insufficient_observations": 11,
        "zero_variance": 4,
    }
    assert all(pair.r is None and pair.r2 is None for pair in pairs if pair.status != "observed")


def test_reference_ld_retains_exact_sign_and_pairwise_missingness() -> None:
    """Catch allele-sign reversal or treating missing dosage three as a called genotype."""
    by_rows = {(pair.row_a, pair.row_b): pair for pair in _reference()}

    assert by_rows[1, 2].r == pytest.approx(-1.0)
    assert by_rows[0, 2].r == pytest.approx(-5 / 11)
    assert by_rows[0, 5].n_obs == 3
    assert by_rows[0, 5].r == pytest.approx(math.sqrt(3) / 2)


def test_reference_ld_does_not_repair_non_psd_pairwise_result() -> None:
    """Catch projection or imputation that disguises pairwise missingness as joint covariance."""
    by_rows = {(pair.row_a, pair.row_b): pair for pair in _reference()}
    matrix = np.array(
        [
            [1.0, by_rows[0, 1].r, by_rows[0, 5].r],
            [by_rows[0, 1].r, 1.0, by_rows[1, 5].r],
            [by_rows[0, 5].r, by_rows[1, 5].r, 1.0],
        ]
    )

    assert np.linalg.det(matrix) == pytest.approx(-3 / 121)


def test_variant_moments_distinguish_all_missing_from_dosage_zero() -> None:
    """Catch coercion of missing dosage three into a biological zero call."""
    _, reference = _api()
    moments = reference.variant_moments(CALLS[np.array(TRAINING_ROWS)])

    assert moments[0] == reference.VariantMoments(4, 5, 1.25, 2.75, 0.375)
    assert moments[1] == reference.VariantMoments(4, 3, 0.75, 2.75, 0.375)
    assert moments[3] == reference.VariantMoments(0, 0, None, None, None)

    all_missing_and_zero = reference.variant_moments([[3, 0], [3, 0], [3, 0]])
    assert all_missing_and_zero[0] == reference.VariantMoments(0, 0, None, None, None)
    assert all_missing_and_zero[1] == reference.VariantMoments(3, 0, 0.0, 0.0, 0.0)


def test_reference_ld_uses_status_precedence_for_empty_and_constant_pairs() -> None:
    """Catch zero-variance classification taking precedence over fewer than two observations."""
    contract, reference = _api()
    variants = (
        contract.LDVariant(1, "1-10-A-C", "1", 10, "A", "C"),
        contract.LDVariant(2, "1-20-A-C", "1", 20, "A", "C"),
        contract.LDVariant(3, "1-30-A-C", "1", 30, "A", "C"),
    )
    pairs = reference.reference_ld(
        [[3, 0, 0], [3, 3, 0], [3, 3, 0]],
        variants,
        genome_build="GRCh38",
        ploidy="autosomal_diploid",
        window_variants=None,
        window_bp=None,
    )

    assert [(pair.n_obs, pair.status) for pair in pairs] == [
        (0, "insufficient_observations"),
        (0, "insufficient_observations"),
        (1, "insufficient_observations"),
    ]
    constant = reference.reference_ld(
        [[0, 0], [0, 0]],
        variants[:2],
        genome_build="GRCh38",
        ploidy="autosomal_diploid",
        window_variants=None,
        window_bp=None,
    )[0]
    assert (constant.n_obs, constant.status, constant.r, constant.r2) == (
        2,
        "zero_variance",
        None,
        None,
    )


@pytest.mark.parametrize(
    "defect",
    [
        "count_sum",
        "count_type",
        "n_obs_type",
        "status_precedence",
        "zero_variance_status",
        "correlation",
        "moment_integer",
        "moment_mean",
        "moment_sxx",
        "moment_maf",
        "all_missing",
        "pair_marginal",
    ],
)
def test_comparator_refuses_malformed_independent_reference_before_reconciliation(
    defect: str,
) -> None:
    """Catch forged count or moment evidence admitting a matching forged CuGen row."""
    pairs, moments, output = _literal_comparison_evidence()
    pair = pairs[0]
    moment_list = list(moments)
    variants = _variants()[:2]
    if defect == "count_sum":
        pair = replace(pair, counts=(0,) * 9)
    elif defect == "count_type":
        pair = replace(pair, counts=(True, 0, 0, 0, 1, 0, 1, 0, 1))
    elif defect == "n_obs_type":
        pair = replace(pair, n_obs=True)
        output.loc[0, "N_OBS"] = 1
    elif defect == "status_precedence":
        pair = replace(pair, n_obs=1, counts=(1, 0, 0, 0, 0, 0, 0, 0, 0), r=0.0, r2=0.0)
        output.loc[0, ["N_OBS", "R", "R2"]] = [1, 0.0, 0.0]
    elif defect == "zero_variance_status":
        pair = replace(pair, n_obs=2, counts=(2, 0, 0, 0, 0, 0, 0, 0, 0), r=0.0, r2=0.0)
        output.loc[0, ["N_OBS", "R", "R2"]] = [2, 0.0, 0.0]
    elif defect == "correlation":
        pair = replace(pair, r=0.5, r2=0.25)
        output.loc[0, ["R", "R2"]] = [0.5, 0.25]
    elif defect == "moment_integer":
        moment_list[0] = replace(moment_list[0], n_called=True)
    elif defect == "moment_mean":
        moment_list[0] = replace(moment_list[0], mean=1.0)
    elif defect == "moment_sxx":
        moment_list[0] = replace(moment_list[0], sxx=1.75)
    elif defect == "moment_maf":
        moment_list[0] = replace(moment_list[0], maf=0.4)
        output.loc[0, "MAF_A"] = 0.4
    elif defect == "all_missing":
        _, reference = _api()
        variants = _variants()[:3]
        moment_list.append(reference.VariantMoments(0, 0, 0.0, None, None))
    else:
        moment_list[0] = replace(moment_list[0], sxx=0.75)

    with pytest.raises((TypeError, ValueError)):
        _comparison().reconcile_ld_output((pair,), variants, tuple(moment_list), output)


def test_validate_ld_evidence_refuses_wrong_moment_count_before_materialization() -> None:
    """Catch copying or scanning an unbounded moments list before its dimension check."""
    _, reference = _api()

    with pytest.raises(ValueError, match="moments must exactly match variants"):
        reference.validate_ld_evidence(
            (),
            _variants()[:2],
            _GuardedOversizedMoments(),
            genome_build="GRCh38",
            ploidy="autosomal_diploid",
        )


def test_requested_pairs_applies_both_windows_inclusively_and_keeps_equal_positions() -> None:
    """Catch exclusive boundaries, OR-combined windows, or rejection of tied positions."""
    contract, reference = _api()
    variants = (
        contract.LDVariant(1, "1-100-A-C", "1", 100, "A", "C"),
        contract.LDVariant(2, "1-100-A-G", "1", 100, "A", "G"),
        contract.LDVariant(3, "1-200-A-C", "1", 200, "A", "C"),
        contract.LDVariant(4, "1-201-A-C", "1", 201, "A", "C"),
    )

    assert reference.requested_pairs(variants, window_variants=2, window_bp=100) == (
        (0, 1),
        (0, 2),
        (1, 2),
        (2, 3),
    )
    assert reference.requested_pairs(variants[:1], window_variants=None, window_bp=None) == ()


@pytest.mark.parametrize(
    ("window_variants", "window_bp"),
    [
        (0, None),
        (-1, None),
        (True, None),
        (1.0, None),
        (None, -1),
        (None, False),
        (None, 1.0),
    ],
)
def test_requested_pairs_rejects_nonexact_or_out_of_domain_windows(
    window_variants: object, window_bp: object
) -> None:
    """Catch permissive integer conversion that changes the declared pair set."""
    _, reference = _api()
    with pytest.raises((TypeError, ValueError)):
        reference.requested_pairs(
            _variants()[:2], window_variants=window_variants, window_bp=window_bp
        )


def test_reference_ld_single_and_double_alt_flips_change_only_expected_signs() -> None:
    """Catch unsigned LD or inconsistent ALT-orientation handling."""
    calls = np.array([[0, 0], [0, 1], [1, 1], [2, 2], [3, 0]], dtype=np.uint8)
    original = _reference(calls)[:1]
    single = calls.copy()
    single[single[:, 0] != 3, 0] = 2 - single[single[:, 0] != 3, 0]
    double = single.copy()
    double[double[:, 1] != 3, 1] = 2 - double[double[:, 1] != 3, 1]

    assert _reference(single)[0].r == pytest.approx(-original[0].r)
    assert _reference(double)[0].r == pytest.approx(original[0].r)
    assert _reference(single)[0].r2 == pytest.approx(original[0].r2)


@pytest.mark.parametrize(
    ("sample_count", "overlap", "expected"),
    [
        (4096, False, -1 / 4095),
        (4096, True, 1.0),
        (3072, False, -1 / 3071),
        (3072, True, 1.0),
    ],
)
def test_reference_ld_preserves_near_fixed_precision_at_sample_caps(
    sample_count: int, overlap: bool, expected: float
) -> None:
    """Catch float accumulation loss for rare disjoint or overlapping heterozygotes."""
    calls = np.zeros((sample_count, 2), dtype=np.uint8)
    calls[0, 0] = 1
    calls[0 if overlap else 1, 1] = 1

    pair = _reference(calls)[0]
    assert pair.n_obs == sample_count
    assert pair.r == pytest.approx(expected, abs=1e-15)
    assert sum(pair.counts) == sample_count


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gidx": True},
        {"gidx": 1.0},
        {"gidx": -1},
        {"gidx": 2**63},
        {"variant_id": "1-10-A-G"},
        {"chrom": "chr1"},
        {"chrom": "23"},
        {"position": True},
        {"position": 1.0},
        {"position": 0},
        {"position": 2**31},
        {"ref": "a"},
        {"ref": "N"},
        {"ref": ""},
        {"alt": "A"},
    ],
)
def test_ld_variant_rejects_invalid_raw_identity_fields(kwargs: dict[str, object]) -> None:
    """Catch normalized or ambiguous variant identity entering the reference contract."""
    contract, _ = _api()
    values: dict[str, object] = {
        "gidx": 1,
        "variant_id": "1-10-A-C",
        "chrom": "1",
        "position": 10,
        "ref": "A",
        "alt": "C",
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        contract.LDVariant(**values)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_gidx", "duplicate_id", "mixed_chrom", "decreasing_position", "too_many"],
)
def test_validate_ld_variants_rejects_invalid_block_semantics(mutation: str) -> None:
    """Catch a block whose row order cannot be reconciled to one exact genomic identity."""
    contract, _ = _api()
    variants = list(_variants())
    if mutation == "duplicate_gidx":
        variants[1] = contract.LDVariant(30, "1-201-A-C", "1", 201, "A", "C")
    elif mutation == "duplicate_id":
        variants[1] = contract.LDVariant(10, "1-101-A-C", "1", 101, "A", "C")
    elif mutation == "mixed_chrom":
        variants[1] = contract.LDVariant(10, "2-201-A-C", "2", 201, "A", "C")
    elif mutation == "decreasing_position":
        variants[1] = contract.LDVariant(10, "1-100-A-C", "1", 100, "A", "C")
    else:
        variants = [
            contract.LDVariant(index, f"1-{index + 1}-A-C", "1", index + 1, "A", "C")
            for index in range(65)
        ]

    with pytest.raises((TypeError, ValueError)):
        contract.validate_ld_variants(
            variants, genome_build="GRCh38", ploidy="autosomal_diploid"
        )


@pytest.mark.parametrize(
    ("genome_build", "ploidy"),
    [
        ("GRCh37", "autosomal_diploid"),
        ("GRCh38", "haploid"),
        (None, "autosomal_diploid"),
        (np.array(["GRCh38"]), "autosomal_diploid"),
        ("GRCh38", np.array(["autosomal_diploid"])),
    ],
)
def test_validate_ld_variants_refuses_inferred_build_or_ploidy(
    genome_build: object, ploidy: object
) -> None:
    """Catch implicit coordinate-build or chromosome-ploidy assumptions."""
    contract, _ = _api()
    with pytest.raises((TypeError, ValueError)):
        contract.validate_ld_variants(_variants(), genome_build=genome_build, ploidy=ploidy)


def test_validate_ld_variants_snapshots_mutable_sequence() -> None:
    """Catch later caller mutation changing validated file-row identities."""
    contract, _ = _api()
    source = list(_variants())
    validated = contract.validate_ld_variants(
        source, genome_build="GRCh38", ploidy="autosomal_diploid"
    )
    source.clear()
    assert len(validated) == 7
    assert isinstance(validated, tuple)


@pytest.mark.parametrize("variants", [[], "variants.tsv", [object()]])
def test_validate_ld_variants_rejects_empty_path_or_untyped_blocks(variants: object) -> None:
    """Catch path-like, empty, or structurally guessed variant declarations."""
    contract, _ = _api()
    with pytest.raises((TypeError, ValueError)):
        contract.validate_ld_variants(
            variants, genome_build="GRCh38", ploidy="autosomal_diploid"
        )


@pytest.mark.parametrize(
    "calls",
    [
        np.array([[False, True]], dtype=bool),
        np.array([[0.0, 1.0]]),
        np.array([[0, 1]], dtype=object),
        np.array([[0 + 0j, 1 + 0j]]),
        [[0, True]],
        [[0, -1]],
        [[0, 4]],
        [0, 1],
        [[[0, 1]]],
        [],
        [[]],
        Path("calls.npy"),
        "calls.npy",
    ],
)
def test_validate_hard_calls_rejects_invalid_types_shapes_and_values(calls: object) -> None:
    """Catch coercion, missing-as-dosage, or ambiguous array shape before statistics."""
    contract, _ = _api()
    with pytest.raises((TypeError, ValueError)):
        contract.validate_hard_calls(calls)


@pytest.mark.parametrize(
    "dtype",
    [object, bool, np.float64, np.complex128],
)
def test_validate_hard_calls_rejects_nested_numpy_rows_before_dtype_normalization(
    dtype: object,
) -> None:
    """Catch nested NumPy row dtypes being normalized into accepted integer hard calls."""
    contract, _ = _api()
    with pytest.raises(TypeError):
        contract.validate_hard_calls([np.array([0, 1], dtype=dtype)])


def test_validate_hard_calls_rejects_sequence_values_before_array_normalization() -> None:
    """Catch out-of-domain Python integers reaching NumPy normalization before refusal."""
    contract, _ = _api()
    with pytest.raises(ValueError, match="ALT dosages"):
        contract.validate_hard_calls([[0, 10**100]])


@pytest.mark.parametrize("shape", [(4097, 1), (1, 65)])
def test_validate_hard_calls_enforces_fixed_pilot_caps(shape: tuple[int, int]) -> None:
    """Catch unbounded genotype allocation outside the admitted pilot."""
    contract, _ = _api()
    with pytest.raises(ValueError):
        contract.validate_hard_calls(np.zeros(shape, dtype=np.uint8))


@pytest.mark.parametrize("entry", ["calls_rows", "calls_columns", "variants", "samples"])
def test_public_contracts_refuse_oversized_sequences_before_materialization(entry: str) -> None:
    """Catch allocation or iteration occurring before fixed pilot-cap admission."""
    contract, _ = _api()
    with pytest.raises(ValueError):
        if entry == "calls_rows":
            contract.validate_hard_calls(_OversizedSequence(4097))
        elif entry == "calls_columns":
            contract.validate_hard_calls([_OversizedSequence(65)])
        elif entry == "variants":
            contract.validate_ld_variants(
                _OversizedSequence(65),
                genome_build="GRCh38",
                ploidy="autosomal_diploid",
            )
        else:
            contract.validate_training_selection(
                _OversizedSequence(4097),
                [0],
                held_out_ids=(),
                excluded_ids=(),
            )


def test_validate_hard_calls_returns_detached_bytes_backed_uint8_snapshot() -> None:
    """Catch caller aliases or re-enabled writes changing validated genotypes."""
    contract, _ = _api()
    source = np.array([[0, 1], [2, 3]], dtype=np.int64)
    validated = contract.validate_hard_calls(source)
    source[0, 0] = 2

    assert validated.dtype == np.uint8
    assert validated.tolist() == [[0, 1], [2, 3]]
    assert not validated.flags.writeable
    with pytest.raises(ValueError):
        validated.setflags(write=True)


def test_validate_training_selection_preserves_order_and_complete_partition() -> None:
    """Catch sorted training rows or silently unassigned source samples."""
    contract, _ = _api()
    selection = contract.validate_training_selection(
        ["s0", "s1", "s2", "s3", "s4"],
        np.array([4, 0, 2], dtype=np.int32),
        held_out_ids=["s1"],
        excluded_ids=["s3"],
    )

    assert selection == contract.TrainingSelection(
        sample_ids=("s0", "s1", "s2", "s3", "s4"),
        training_indices=(4, 0, 2),
        training_ids=("s4", "s0", "s2"),
        held_out_ids=("s1",),
        excluded_ids=("s3",),
    )


def test_validate_training_selection_snapshots_all_mutable_inputs() -> None:
    """Catch partition identity changing after validation through caller-owned lists."""
    contract, _ = _api()
    sample_ids = ["s0", "s1", "s2"]
    indices = [2]
    held_out = ["s0"]
    excluded = ["s1"]
    selection = contract.validate_training_selection(
        sample_ids, indices, held_out_ids=held_out, excluded_ids=excluded
    )
    sample_ids[0] = "changed"
    indices[0] = 0
    held_out.clear()
    excluded.clear()

    assert selection.sample_ids == ("s0", "s1", "s2")
    assert selection.training_indices == (2,)
    assert selection.held_out_ids == ("s0",)
    assert selection.excluded_ids == ("s1",)


@pytest.mark.parametrize(
    "indices",
    [
        [],
        [0, True],
        [0, np.bool_(False)],
        [0, 1.0],
        [0, 0.0],
        ["0"],
        [0, 0],
        [-1],
        [3],
        [[0]],
        np.array([[0]], dtype=np.int64),
        Path("indices.npy"),
        "indices.npy",
    ],
)
def test_validate_training_selection_rejects_permissive_index_coercions(
    indices: object,
) -> None:
    """Catch Boolean, float, path, nested, duplicate, or invalid training selectors."""
    contract, _ = _api()
    with pytest.raises((TypeError, ValueError)):
        contract.validate_training_selection(
            ["s0", "s1", "s2"],
            indices,
            held_out_ids=["s1"],
            excluded_ids=["s2"],
        )


def test_validate_training_selection_inspects_mixed_boolean_before_conversion() -> None:
    """Catch a Boolean hidden by NumPy or list integer promotion into a valid selector."""
    contract, _ = _api()
    with pytest.raises((TypeError, ValueError)):
        contract.validate_training_selection(
            ["s0", "s1", "s2", "s3"],
            [0, True],
            held_out_ids=["s2"],
            excluded_ids=["s3"],
        )


@pytest.mark.parametrize(
    ("sample_ids", "held_out_ids", "excluded_ids"),
    [
        (["s0", "s0", "s2"], ["s1"], ["s2"]),
        ([" s0", "s1", "s2"], ["s1"], ["s2"]),
        (["s0", "s1", "s2"], ["s1", "s1"], ["s2"]),
        (["s0", "s1", "s2"], ["missing"], ["s2"]),
        (["s0", "s1", "s2"], ["s0"], ["s2"]),
        (["s0", "s1", "s2"], [], []),
        (["s0", "s1", 2], ["s1"], ["s2"]),
        ("samples.tsv", ["s1"], ["s2"]),
    ],
)
def test_validate_training_selection_rejects_invalid_labels_or_partition(
    sample_ids: object, held_out_ids: object, excluded_ids: object
) -> None:
    """Catch untrimmed, duplicate, unknown, overlapping, or incomplete partition labels."""
    contract, _ = _api()
    with pytest.raises((TypeError, ValueError)):
        contract.validate_training_selection(
            sample_ids,
            [0],
            held_out_ids=held_out_ids,
            excluded_ids=excluded_ids,
        )


def test_validate_training_selection_allows_explicit_empty_nontraining_partitions() -> None:
    """Catch refusal of an explicit all-training numeric-control partition."""
    contract, _ = _api()
    selection = contract.validate_training_selection(
        ["s0", "s1"], [1, 0], held_out_ids=(), excluded_ids=()
    )
    assert selection.training_ids == ("s1", "s0")


def test_reference_functions_revalidate_shape_and_variant_alignment() -> None:
    """Catch public science entry points trusting mismatched or invalid caller arrays."""
    _, reference = _api()
    with pytest.raises(ValueError):
        reference.reference_ld(
            [[0, 1]],
            _variants(),
            genome_build="GRCh38",
            ploidy="autosomal_diploid",
            window_variants=None,
            window_bp=None,
        )
    with pytest.raises(ValueError):
        reference.variant_moments([[0, 4]])

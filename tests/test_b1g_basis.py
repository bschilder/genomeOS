"""B1G compact positive-basis tests (design §§4–8, 12; #331)."""

from __future__ import annotations

import importlib

import numpy as np
import pandas as pd


def _observations(*rows: tuple[object, ...]) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "variant_id": "chr11-5227002-T-A",
                "rsid": "rs334",
                "population_id": f"population-{record_id}",
                "lat": lat,
                "lon": lon,
                "radius_km": radius_km,
                "ac": ac,
                "an": an,
                "source_record_id": record_id,
                "source": "fixture",
                "assay": "fixture-assay",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": "population_random",
                "disease_ascertainment_excluded": True,
                "cohort_id": cohort_id,
                "ingest_version": "fixture-v1",
            }
            for record_id, cohort_id, lat, lon, radius_km, ac, an in rows
        ]
    )


def test_farthest_first_centres_are_reorder_invariant_and_break_ties_by_id():
    b1g = importlib.import_module("genomeos.validation.b1g_basis")
    training = _observations(
        ("a", "ca", 0.0, 0.0, 1.0, 1, 20),
        ("b", "cb", 0.0, 10.0, 1.0, 1, 20),
        ("c", "cc", 0.0, -10.0, 1.0, 1, 20),
        ("d", "cd", 0.0, 0.1, 1.0, 1, 20),
        ("e", "ce", 0.0, 0.2, 1.0, 1, 20),
        ("f", "cf", 0.0, 0.3, 1.0, 1, 20),
        ("g", "cg", 0.0, 0.4, 1.0, 1, 20),
        ("h", "ch", 0.0, 0.5, 1.0, 1, 20),
    )
    config = b1g.B1GBasisConfig(radius_km=500, basis_count=8, query_chunk_size=3)

    forward = b1g.select_b1g_centres(training, config=config)
    reverse = b1g.select_b1g_centres(training.iloc[::-1], config=config)

    assert forward.source_record_ids == reverse.source_record_ids
    assert forward.source_record_ids[:2] == ("a", "b")


def test_chunked_wendland_matrix_is_exact_read_only_and_order_invariant():
    b1g = importlib.import_module("genomeos.validation.b1g_basis")
    training = _observations(
        ("a", "ca", 0.0, 0.0, 1.0, 1, 20),
        ("b", "cb", 0.0, 10.0, 1.0, 1, 20),
        ("c", "cc", 0.0, -10.0, 1.0, 1, 20),
        ("d", "cd", 0.0, 0.1, 1.0, 1, 20),
        ("e", "ce", 0.0, 0.2, 1.0, 1, 20),
        ("f", "cf", 0.0, 0.3, 1.0, 1, 20),
        ("g", "cg", 0.0, 0.4, 1.0, 1, 20),
        ("h", "ch", 0.0, 0.5, 1.0, 1, 20),
    )
    queries = _observations(
        ("q-a", "qa", 0.0, 0.0, 1.0, 0, 20),
        ("q-b", "qb", 0.0, 10.0, 1.0, 0, 20),
    )
    chunked_config = b1g.B1GBasisConfig(radius_km=500, basis_count=8, query_chunk_size=1)
    whole_config = b1g.B1GBasisConfig(radius_km=500, basis_count=8, query_chunk_size=8)

    np.testing.assert_allclose(
        b1g.wendland_c2(np.array([0.0, 250.0, 500.0, 750.0]), radius_km=500),
        np.array([1.0, 0.1875, 0.0, 0.0]),
    )
    chunked = b1g.build_b1g_basis(training, queries, config=chunked_config)
    whole = b1g.build_b1g_basis(training.iloc[::-1], queries, config=whole_config)

    assert chunked.source_record_ids == ("q-a", "q-b")
    assert chunked.centre_source_record_ids == whole.centre_source_record_ids
    np.testing.assert_allclose(chunked.values, whole.values)
    assert chunked.values.shape == (2, 8)
    assert chunked.values[0, chunked.centre_source_record_ids.index("a")] == 1.0
    assert chunked.values[0, chunked.centre_source_record_ids.index("b")] == 0.0
    assert not chunked.values.flags.writeable


def test_preflight_preserves_every_grid_cell_and_stratifies_geometric_support():
    b1g = importlib.import_module("genomeos.validation.b1g_basis")
    rows = []
    assignments = []
    for block_id, prefix, longitude in (
        ("west", "w", 0.0),
        ("east", "e", 3.2),
    ):
        for index in range(9):
            record_id = f"{prefix}-{index}"
            rows.append(
                (
                    record_id,
                    f"cohort-{record_id}",
                    0.0,
                    longitude + index * 0.001,
                    1.0,
                    0 if index == 8 else 1,
                    20,
                )
            )
            assignments.append({"source_record_id": record_id, "block_id": block_id})

    report = b1g.preflight_b1g_basis(
        _observations(*rows),
        pd.DataFrame.from_records(assignments),
        (),
        buffer_km=300.0,
        data_version="fixture-v1",
        query_chunk_size=3,
    )

    assert len(report.splits) == 2
    assert len(report.cells) == 18
    eligible = [cell for cell in report.cells if cell.status == "eligible"]
    infeasible = [cell for cell in report.cells if cell.status == "infeasible"]
    assert len(eligible) == 6
    assert len(infeasible) == 12
    assert all(cell.basis_count == 8 for cell in eligible)
    assert all(cell.geometrically_supported_positive_count == 8 for cell in eligible)
    assert all(cell.geometrically_supported_zero_count == 1 for cell in eligible)
    assert all(cell.failure_reason is None for cell in eligible)
    assert all("unique positive footprints" in cell.failure_reason for cell in infeasible)
    assert len(report.grid_summary) == 9
    smallest = next(
        row for row in report.grid_summary if row.radius_km == 500 and row.basis_count == 8
    )
    assert smallest.eligible_fold_count == 2
    assert smallest.positive_support_fraction == 1.0
    assert smallest.zero_support_fraction == 1.0
    unavailable = next(
        row for row in report.grid_summary if row.radius_km == 500 and row.basis_count == 16
    )
    assert unavailable.eligible_fold_count == 0
    assert unavailable.positive_support_fraction is None

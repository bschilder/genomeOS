"""Exclusive spatial-activity worker artifact tests (#384)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from test_spatial_activity_codec import _record


def test_task_artifact_writes_exclusively_and_round_trips(tmp_path) -> None:
    from genomeos.validation.spatial_activity_artifacts import (
        read_spatial_activity_task_result,
        write_spatial_activity_task_result,
    )

    record = _record()
    path = write_spatial_activity_task_result(tmp_path / "results", record)

    assert path.name == f"{record.task.task_id}.json"
    assert read_spatial_activity_task_result(path).task == record.task
    with pytest.raises(FileExistsError, match="overwrite"):
        write_spatial_activity_task_result(tmp_path / "results", record)


def test_directory_loader_orders_results_by_manifest_identity(tmp_path) -> None:
    from genomeos.validation.spatial_activity_artifacts import (
        load_spatial_activity_task_results,
        write_spatial_activity_task_result,
    )

    first = _record()
    second_task = first.task.create(
        scenario_id=first.task.scenario_id,
        mode="ordinary",
        split_role=first.task.split_role,
        outer_split_id=first.task.outer_split_id,
        split_id=first.task.split_id,
    )
    second = type(first)(
        task=second_task,
        result=replace(
            first.result,
            scenario_id=second_task.scenario_id,
            mode=second_task.mode,
        ),
    )
    directory = tmp_path / "results"
    write_spatial_activity_task_result(directory, first)
    write_spatial_activity_task_result(directory, second)

    loaded = load_spatial_activity_task_results(directory)

    assert [item.task.task_id for item in loaded] == sorted(
        [first.task.task_id, second.task.task_id]
    )


def test_reader_refuses_mislabeled_or_unexpected_artifacts(tmp_path) -> None:
    from genomeos.validation.spatial_activity_artifacts import (
        SpatialActivityArtifactError,
        load_spatial_activity_task_results,
        read_spatial_activity_task_result,
        write_spatial_activity_task_result,
    )

    record = _record()
    path = write_spatial_activity_task_result(tmp_path / "results", record)
    renamed = path.with_name("0" * 64 + ".json")
    path.rename(renamed)
    with pytest.raises(SpatialActivityArtifactError, match="filename"):
        read_spatial_activity_task_result(renamed)

    (renamed.parent / "notes.txt").write_text("unexpected")
    with pytest.raises(SpatialActivityArtifactError, match="unexpected"):
        load_spatial_activity_task_results(renamed.parent)


def test_reader_refuses_missing_directory(tmp_path) -> None:
    from genomeos.validation.spatial_activity_artifacts import (
        SpatialActivityArtifactError,
        load_spatial_activity_task_results,
    )

    with pytest.raises(SpatialActivityArtifactError, match="directory"):
        load_spatial_activity_task_results(tmp_path / "missing")
